#!/usr/bin/env python3
"""Serveur local de voix « légère » : Pocket TTS de Kyutai (licence MIT), ~100 M de paramètres,
fait pour tourner sur le PROCESSEUR. Parle français et imite un extrait de voix.

Lancé par Viki quand « Voix légère » est choisie. Écoute uniquement sur 127.0.0.1.
Même interface que voix_naturelle.py :
    POST /tts  {"text": "...", "out": "/chemin/sortie.wav", "ref": "/chemin/extrait.wav" | null}
    GET  /health
Variables : VIKI_LEGERE_LANGUE = french (défaut, rapide) | french_24l (meilleure, plus lente)
            VIKI_LEGERE_QUANT  = 1 (défaut : calcul en int8, plus léger) | 0
            VIKI_LEGERE_CACHE  = dossier où garder les voix déjà préparées
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("VIKI_LEGERE_PORT", "59126"))
LANGUE = os.environ.get("VIKI_LEGERE_LANGUE", "french")
QUANT = os.environ.get("VIKI_LEGERE_QUANT", "1") == "1"
STEPS = max(1, int(os.environ.get("VIKI_LEGERE_STEPS", "1")))   # plus d'étapes = son plus fin, plus lent
CACHE = Path(os.environ.get("VIKI_LEGERE_CACHE", Path.home() / ".cache" / "viki-voix-legere"))
VOIX_DEFAUT = "estelle"                   # voix française fournie par Kyutai

import numpy as np  # noqa: E402
import torch  # noqa: E402

torch.set_num_threads(max(2, min(6, (os.cpu_count() or 4) // 2)))

state = {"ready": False, "error": "", "device": "", "note": "", "busy": False}
model = None
voices = {}
lock = threading.Lock()


def log(*a):
    print("[voix légère]", *a, file=sys.stderr, flush=True)


def load():
    global model
    try:
        from pocket_tts import TTSModel
        t0 = time.time()
        try:
            model = TTSModel.load_model(language=LANGUE, quantize=QUANT, sampler_decode_steps=STEPS)
        except TypeError:                      # ancienne version sans ces options
            model = TTSModel.load_model(language=LANGUE)
        except Exception as e:
            if not QUANT:
                raise
            log("int8 impossible, calcul normal :", repr(e))
            model = TTSModel.load_model(language=LANGUE)
        voice_state(None)                      # prépare la voix par défaut
        model.generate_audio(voices[VOIX_DEFAUT], "Bonjour.")
        state["device"] = (f"processeur (Pocket TTS, {LANGUE}{', int8' if QUANT else ''}"
                           f"{f', finesse {STEPS}' if STEPS > 1 else ''})")
        state["ready"] = True
        log(f"prête en {time.time() - t0:.0f} s")
    except Exception as e:
        state["error"] = repr(e)
        log("échec :", repr(e))
        traceback.print_exc()


def _prompt_tensor(path, max_s=20.0):
    """Extrait -> tenseur [1, T] au bon taux, en mono, d'une longueur multiple du « pas » du modèle.
    (Pocket TTS refuse sinon : « Steps must be multiple of stride ».) None si le fichier n'est pas un WAV lisible."""
    try:
        with wave.open(str(path), "rb") as w:
            sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except Exception:
        return None
    if sw == 2:
        a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif sw == 4:
        a = np.frombuffer(raw, "<i4").astype(np.float32) / 2 ** 31
    elif sw == 1:
        a = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    else:
        return None
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    target = int(model.sample_rate)
    if sr != target and len(a) > 1:                      # rééchantillonnage simple (suffisant pour l'imitation)
        t_new = np.arange(int(len(a) * target / sr)) * (sr / target)
        a = np.interp(t_new, np.arange(len(a)), a).astype(np.float32)
    a = a[: int(max_s * target)]
    nz = np.where(np.abs(a) > 0.01)[0]                   # silences au début et à la fin
    if len(nz):
        a = a[max(0, nz[0] - target // 10): nz[-1] + target // 10]
    frame_rate = float(getattr(getattr(model, "mimi", None), "frame_rate", 12.5) or 12.5)
    hop = int(round(target / frame_rate))                # 1920 échantillons à 24 kHz
    a = a[: len(a) - len(a) % hop]
    if len(a) < hop * 12:                                # moins d'une seconde : inutilisable
        return None
    peak = float(np.max(np.abs(a)))
    if peak > 0:
        a = a * (0.9 / peak)
    return torch.from_numpy(np.ascontiguousarray(a)).unsqueeze(0)


def voice_state(ref):
    """Voix à imiter : un extrait audio (gardé en cache après la 1re fois), sinon Estelle."""
    key = ref if ref and os.path.exists(ref) else VOIX_DEFAUT
    if key != VOIX_DEFAUT:
        st0 = os.stat(key)
        key_mem = f"{key}|{st0.st_size}|{st0.st_mtime}"
        if key_mem in voices:
            return voices[key_mem]
    elif key in voices:
        return voices[key]
    if key == VOIX_DEFAUT:
        voices[key] = model.get_state_for_audio_prompt(VOIX_DEFAUT)
        return voices[key]
    st = os.stat(key)
    h = hashlib.sha1(f"{key}|{st.st_size}|{st.st_mtime}|{LANGUE}".encode()).hexdigest()[:16]
    cached = CACHE / f"{h}.safetensors"
    try:
        if cached.exists():
            voices[key_mem] = model.get_state_for_audio_prompt(str(cached))
            log(f"extrait repris du cache : {Path(key).name}")
            return voices[key_mem]
    except Exception:
        pass
    t0 = time.time()
    s = None
    ten = _prompt_tensor(key)
    if ten is not None:
        try:
            s = model.get_state_for_audio_prompt(ten)
        except Exception as e:
            log("extrait recalé refusé, essai avec le fichier :", repr(e))
    if s is None:
        try:
            s = model.get_state_for_audio_prompt(key, truncate=True)
        except TypeError:                      # version sans « truncate »
            s = model.get_state_for_audio_prompt(key)
    voices[key] = voices[key_mem] = s
    log(f"extrait préparé en {time.time() - t0:.1f} s : {Path(key).name}")
    try:
        from pocket_tts import export_model_state
        CACHE.mkdir(parents=True, exist_ok=True)
        export_model_state(voices[key], str(cached))
    except Exception as e:
        log("cache de voix impossible :", repr(e))
    return voices[key]


def split_sentences(text, maxlen=300):
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) < maxlen:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out or [text]


def synth(text, out, ref=None):
    ref_error = ""
    with lock:
        state["busy"] = True
        try:
            try:
                vs = voice_state(ref)
            except Exception as e:             # extrait illisible : on parle quand même, avec Estelle
                ref_error = repr(e)[:300]
                log(f"impossible d'imiter « {Path(ref).name if ref else '?'} » : {ref_error}")
                traceback.print_exc()
                vs = voice_state(None)
            chunks = []
            for s in split_sentences(text):
                t0 = time.time()
                a = model.generate_audio(vs, s, copy_state=True).float().cpu().numpy()
                dt, dur = time.time() - t0, len(a) / model.sample_rate
                log(f"{len(s)} caractères : {dt:.1f} s de calcul pour {dur:.1f} s de voix "
                    f"({'OK' if dt < dur else 'TROP LENT'})")
                chunks.append(a)
                chunks.append(np.zeros(int(model.sample_rate * 0.1), dtype=np.float32))
            audio = np.concatenate(chunks)
        finally:
            state["busy"] = False
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.97:                            # trop fort : on baisse tout (couper les crêtes = son saturé)
        audio = audio * (0.97 / peak)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(model.sample_rate)
        w.writeframes(pcm.tobytes())
    return ref_error


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, state) if self.path == "/health" else self._send(404, {})

    def do_POST(self):
        if self.path != "/tts":
            return self._send(404, {})
        if not state["ready"]:
            return self._send(503, state)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            err = synth(req["text"], req["out"], req.get("ref") or None)
            self._send(200, {"ok": True, "ref_error": err, "ref": req.get("ref") or ""})
        except Exception as e:
            log("erreur :", repr(e))
            traceback.print_exc()
            self._send(500, {"ok": False, "error": repr(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    try:
        os.nice(int(os.environ.get("COMPAGNON_VOIX_NICE", "5")))
    except Exception:
        pass
    log(f"démarrage ({LANGUE})")
    threading.Thread(target=load, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
