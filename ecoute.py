#!/usr/bin/env python3
"""Reconnaissance vocale locale (faster-whisper) pour le compagnon.

Lancé une seule fois par le compagnon ; le modèle reste chargé.
Entrée  : un chemin de fichier WAV par ligne.
Sortie  : une ligne JSON par fichier : {"text": "..."} (ou {"error": "..."}).
Le modèle est téléchargé une fois (~480 Mo pour « small »), puis tout est hors ligne.
"""
import json
import os
import sys

size = os.environ.get("COMPAGNON_WHISPER", "small")
root = os.environ.get("COMPAGNON_MODELS") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "models", "whisper")

try:
    from faster_whisper import WhisperModel
    threads = max(2, min(8, (os.cpu_count() or 4) // 2))
    model = WhisperModel(size, device="cpu", compute_type=os.environ.get("COMPAGNON_COMPUTE", "int8"),
                         download_root=root, cpu_threads=threads)
    print(json.dumps({"ready": True, "model": size}), flush=True)
except Exception as e:
    print(json.dumps({"error": repr(e)}), flush=True)
    sys.exit(1)

def load_wav(path):
    """Lit le WAV nous-mêmes (16 kHz, mono, float32) : évite le décodeur PyAV,
    dont certaines versions récentes font planter faster-whisper (« metadata_errors »)."""
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"format WAV non géré ({width * 8} bits)")
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if rate != 16000 and len(audio):
        dur = len(audio) / rate
        audio = np.interp(np.linspace(0, dur, int(dur * 16000), endpoint=False),
                          np.arange(len(audio)) / rate, audio).astype(np.float32)
    return audio


for line in sys.stdin:
    path = line.strip()
    if not path:
        continue
    try:
        try:
            audio = load_wav(path)
        except Exception:
            audio = path                  # autre format : on laisse faster-whisper le décoder
        noms = os.environ.get("COMPAGNON_NOMS", "").strip()
        opts = dict(language=os.environ.get("COMPAGNON_LANGUE", "fr"), vad_filter=True, beam_size=1,
                    condition_on_previous_text=False, without_timestamps=True)
        try:                           # aide à bien écrire les prénoms (« Lilas » et pas « Lisa »)
            segments, _ = model.transcribe(audio, hotwords=noms or None, **opts)
        except TypeError:
            segments, _ = model.transcribe(audio, initial_prompt=(noms + ".") if noms else None, **opts)
        text = " ".join(s.text.strip() for s in segments).strip()
        print(json.dumps({"text": text}), flush=True)
    except Exception as e:
        print(json.dumps({"error": repr(e)}), flush=True)
