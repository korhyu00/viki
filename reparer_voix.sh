#!/usr/bin/env bash
# Répare la voix Piper (installe Piper avec un Python 3.12 séparé, retélécharge la voix).
cd "$(dirname "$(readlink -f "$0")")"
V=voices/fr_FR-siwis-medium
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"

echo "=== Diagnostic ==="
echo "Python système : $(python --version 2>&1)"
ls -la voices/ 2>&1
if [ -x .venv/bin/piper ]; then
  echo "Test de l'ancien Piper :"
  echo "test" | .venv/bin/piper -m "$V.onnx" -f /tmp/compagnon_t.wav 2>&1 | tail -4
else
  echo "Piper n'est pas installé dans .venv"
fi

echo
echo "=== Réparation ==="
sudo pacman -S --needed --noconfirm uv curl || exit 1

rm -rf .venv-piper
uv venv --python 3.12 .venv-piper || exit 1
VIRTUAL_ENV="$PWD/.venv-piper" uv pip install piper-tts || exit 1

mkdir -p voices
# retélécharge si absent ou trop petit (téléchargement raté)
if [ ! -f "$V.onnx" ] || [ "$(stat -c%s "$V.onnx")" -lt 1000000 ]; then
  echo "Téléchargement de la voix (~60 Mo)…"
  curl -fL -o "$V.onnx" "$BASE/fr_FR-siwis-medium.onnx" || exit 1
fi
if [ ! -f "$V.onnx.json" ] || [ "$(stat -c%s "$V.onnx.json")" -lt 500 ]; then
  curl -fL -o "$V.onnx.json" "$BASE/fr_FR-siwis-medium.onnx.json" || exit 1
fi

echo
echo "=== Test ==="
if echo "Bonjour ! Ma voix est réparée, ça sonne beaucoup mieux, non ?" \
   | .venv-piper/bin/piper -m "$V.onnx" -f test_piper.wav; then
  mkdir -p .venv/bin
  ln -sf "$PWD/.venv-piper/bin/piper" .venv/bin/piper     # le compagnon l'utilise directement
  pw-play test_piper.wav
  echo
  echo "✅ Voix réparée ! Quitte le compagnon (clic droit → Quitter) et relance-le."
else
  echo
  echo "❌ Ça ne marche toujours pas : copie tout ce qui est affiché au-dessus à Claude."
fi
