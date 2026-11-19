#!/usr/bin/env bash
# Installe une voix Piper anglaise (pour pratiquer l'anglais avec elle).
# Usage : bash installer_voix_anglaise.sh
set -e
cd "$(dirname "$0")"
mkdir -p voices
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium
for f in en_US-amy-medium.onnx en_US-amy-medium.onnx.json; do
    if [ ! -s "voices/$f" ]; then
        echo "Téléchargement de $f…"
        curl -L --fail -o "voices/$f" "$BASE/$f"
    fi
done
echo "Voix anglaise installée (Amy). Dis-lui « parlons anglais » !"
