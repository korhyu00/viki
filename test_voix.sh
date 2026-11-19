#!/usr/bin/env bash
# Test des voix : génère et joue plusieurs versions pour comparer.
cd "$(dirname "$(readlink -f "$0")")"
TXT="Bonjour ! Je suis ravie de te voir. Tu veux qu'on fasse une petite pause ensemble ?"

echo "=== 1. Voix Piper ==="
echo "$TXT" | .venv/bin/piper -m voices/fr_FR-siwis-medium.onnx -f test_1_piper.wav 2>/dev/null \
  && pw-play test_1_piper.wav || echo "Piper ne marche pas"

if [ ! -x .venv-voix/bin/python ]; then
  echo "Voix naturelle non installée, test terminé."
  exit 0
fi

echo
echo "=== Génération des voix naturelles (patiente 1 à 3 minutes)… ==="
HSA_OVERRIDE_GFX_VERSION=10.3.0 TXT="$TXT" .venv-voix/bin/python - <<'EOF'
import os, torch, wave, numpy as np
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
txt = os.environ["TXT"]
def save(w, sr, name):
    pcm = (np.clip(w.squeeze().cpu().numpy(), -1, 1) * 32767).astype("<i2")
    with wave.open(name, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes(pcm.tobytes())
gpu = torch.cuda.is_available()
print("Carte graphique utilisable :", torch.cuda.get_device_name(0) if gpu else "NON")
if gpu:
    m = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    save(m.generate(txt, language_id="fr", cfg_weight=0.0), m.sr, "test_2_gpu_sans_extrait.wav")
    if os.path.exists("voices/extrait_defaut.wav"):
        save(m.generate(txt, language_id="fr", audio_prompt_path="voices/extrait_defaut.wav"),
             m.sr, "test_3_gpu_avec_extrait.wav")
    del m
m = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
save(m.generate(txt, language_id="fr", cfg_weight=0.0), m.sr, "test_4_cpu_sans_extrait.wav")
EOF

for f in test_2_*.wav test_3_*.wav test_4_*.wav; do
  [ -f "$f" ] || continue
  echo
  echo "=== $f ==="
  pw-play "$f"
done
echo
echo "Fini ! Dis à Claude quels numéros (1 à 4) sonnent bien ou mal."
