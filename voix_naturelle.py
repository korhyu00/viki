#!/usr/bin/env python3
"""Serveur local de voix naturelle (Chatterbox Multilingual, Resemble AI, licence MIT).

Lancé automatiquement par le compagnon quand « Voix naturelle » est choisie.
Écoute uniquement sur 127.0.0.1 ; rien ne sort de la machine.

Robustesse (RX 6600, 8 Go partagés avec Ollama) :
  - essai sur la carte graphique avec une phrase de test ; en cas d'échec -> processeur ;
  - si la carte graphique plante en cours de route (mémoire pleine…) : on libère la
    mémoire et on réessaie, puis on bascule sur le processeur sans planter.

Variables : COMPAGNON_VOIX_DEVICE = auto (défaut) | gpu | cpu

POST /tts  {"text": "...", "out": "/chemin/sortie.wav",
            "ref": "/chemin/extrait.wav" | null, "exaggeration": 0.5, "cfg": 0.5}
GET  /health
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Radeon RX 6600 (Navi 23, gfx1032) : ROCm la gère en se faisant passer pour gfx1030
os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "10.3.0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# limite la fragmentation de la mémoire graphique (moins de « mémoire pleine »)
os.environ.setdefault("PYTORCH_HIP_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

PORT = int(os.environ.get("COMPAGNON_VOIX_PORT", "59125"))
WANT = os.environ.get("COMPAGNON_VOIX_DEVICE", "auto").lower()

import numpy as np  # noqa: E402
import torch  # noqa: E402

state = {"ready": False, "error": "", "device": "", "note": "", "busy": False}
model = None
last_ref = None          # extrait déjà préparé : on ne le recalcule pas à chaque phrase
lock = threading.Lock()


def log(*a):
    print("[voix]", *a, file=sys.stderr, flush=True)


def gpu_error(e):
    s = repr(e).lower()
    return any(k in s for k in ("hip", "cuda", "out of memory", "rocm", "hsa", "device-side",
                                "illegal memory", "miopen", "hipblas"))


def free_gpu():
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except Exception:
        pass


def load_on(dev):
    global last_ref
    last_ref = None
    if dev == "cpu":                          # laisse de la place au reste du PC
        torch.set_num_threads(max(2, min(8, (os.cpu_count() or 4) // 2)))
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    name = dev
    if dev == "cuda":
        name = f"carte graphique ({torch.cuda.get_device_name(0)})"
    log(f"chargement du modèle sur {name}…")
    t0 = time.time()
    m = ChatterboxMultilingualTTS.from_pretrained(device=dev)
    with torch.inference_mode():                         # phrase de test : révèle tout de suite
        m.generate("Bonjour.", language_id="fr")         # les plantages de ROCm
    log(f"prête sur {name} en {time.time() - t0:.0f} s")
    return m, name


def load():
    global model
    try:
        import perth
        if perth.PerthImplicitWatermarker is None:
            raise RuntimeError("module de filigrane indisponible : lance "
                               "`env VIRTUAL_ENV=$PWD/.venv-voix uv pip install \"setuptools<81\"` "
                               "dans le dossier du compagnon")
        use_gpu = WANT != "cpu" and torch.cuda.is_available()
        if use_gpu:
            try:
                model, state["device"] = load_on("cuda")
            except Exception as e:
                log("échec sur la carte graphique :", repr(e))
                traceback.print_exc()
                model = None
                free_gpu()
                state["note"] = "carte graphique indisponible, passage sur le processeur (plus lent)"
        if model is None:
            if WANT == "gpu" and not use_gpu:
                state["note"] = "carte graphique non détectée, voix sur le processeur"
            model, state["device"] = load_on("cpu")
            state["device"] = "processeur"
        state["ready"] = True
    except Exception as e:
        state["error"] = repr(e)
        log("échec :", repr(e))
        traceback.print_exc()


def split_sentences(text, maxlen=220):
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


def _generate(text, ref, exaggeration, cfg):
    global last_ref
    chunks = []
    for i, sentence in enumerate(split_sentences(text)):
        kwargs = dict(language_id="fr", exaggeration=exaggeration, cfg_weight=cfg)
        if ref and ref != state.get("ref_ko") and (ref != last_ref or getattr(model, "conds", None) is None):
            try:                                   # préparé une seule fois, puis gardé en mémoire
                model.prepare_conditionals(ref, exaggeration=exaggeration)
                last_ref = ref
            except Exception as e:
                if gpu_error(e):
                    raise
                state["ref_ko"] = ref               # extrait illisible : voix par défaut, et on le signale
                state["ref_error"] = repr(e)[:300]
                log("impossible d'imiter l'extrait :", repr(e))
        t0 = time.time()
        with torch.inference_mode():
            wav = model.generate(sentence, **kwargs)
        a = wav.squeeze().float().cpu().numpy()
        dt = time.time() - t0
        dur = len(a) / model.sr
        log(f"{len(sentence)} caractères : {dt:.1f} s de calcul pour {dur:.1f} s de voix "
            f"({'OK' if dt < dur else 'TROP LENT'}, {state['device']})")
        chunks.append(a)
        chunks.append(np.zeros(int(model.sr * 0.12), dtype=np.float32))
    return np.concatenate(chunks)


def synth(text, out, ref=None, exaggeration=0.5, cfg=0.5):
    global model
    with lock:
        state["busy"] = True
        try:
            try:
                audio = _generate(text, ref, exaggeration, cfg)
            except Exception as e:
                if not gpu_error(e) or state["device"] == "processeur":
                    raise
                log("erreur de la carte graphique, nouvel essai :", repr(e))
                free_gpu()
                try:
                    audio = _generate(text, ref, exaggeration, cfg)
                except Exception as e2:
                    log("la carte graphique échoue encore, bascule sur le processeur :", repr(e2))
                    model = None
                    free_gpu()
                    model, _ = load_on("cpu")
                    state["device"] = "processeur"
                    state["note"] = "la carte graphique a planté, voix passée sur le processeur"
                    audio = _generate(text, ref, exaggeration, cfg)
        finally:
            state["busy"] = False
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.97:                            # trop fort : on baisse tout plutôt que de saturer
        audio = audio * (0.97 / peak)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:              # WAV 16 bits : lisible partout + synchro bouche
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(model.sr)
        w.writeframes(pcm.tobytes())


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, state)
        else:
            self._send(404, {})

    def do_POST(self):
        if self.path != "/tts":
            return self._send(404, {})
        if not state["ready"]:
            return self._send(503, state)
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            ref = req.get("ref") or None
            if ref and not os.path.exists(ref):
                ref = None
            state["ref_error"] = ""
            synth(req["text"], req["out"], ref,
                  float(req.get("exaggeration", 0.5)), float(req.get("cfg", 0.5)))
            self._send(200, {"ok": True, "ref_error": state.get("ref_error", "") if ref else ""})
        except Exception as e:
            log("erreur :", repr(e))
            traceback.print_exc()
            self._send(500, {"ok": False, "error": repr(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    try:
        os.nice(int(os.environ.get("COMPAGNON_VOIX_NICE", "5")))   # priorité plus basse : le PC reste fluide
    except Exception:
        pass
    log(f"démarrage (appareil demandé : {WANT})")
    threading.Thread(target=load, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
