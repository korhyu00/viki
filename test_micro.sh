#!/usr/bin/env bash
# Diagnostic du micro. Usage : bash test_micro.sh
cd "$(dirname "$0")"
echo "=== 1. Outil d'enregistrement"
REC=$(command -v pw-record || command -v arecord)
[ -z "$REC" ] && { echo "AUCUN : sudo pacman -S pipewire-audio"; exit 1; }
echo "OK : $REC"
echo "Micro par défaut : $(wpctl inspect @DEFAULT_AUDIO_SOURCE@ 2>/dev/null | grep -m1 'node.description' | cut -d'"' -f2)"
echo
echo "=== 2. Enregistrement de 4 secondes : parle maintenant !"
rm -f /tmp/test_micro.wav
if [[ "$REC" == *pw-record ]]; then
  timeout -s INT 4 pw-record --rate 16000 --channels 1 --format s16 /tmp/test_micro.wav
else
  arecord -q -d 4 -f S16_LE -r 16000 -c 1 /tmp/test_micro.wav
fi
ls -la /tmp/test_micro.wav 2>/dev/null || { echo "Aucun fichier enregistré !"; exit 1; }
echo
echo "=== 3. Reconnaissance vocale"
PY=""
for p in .venv-piper/bin/python .venv-voix/bin/python; do [ -x "$p" ] && { PY=$p; break; }; done
[ -z "$PY" ] && { echo "Pas d'environnement Python (.venv-piper) : relance bash install.sh"; exit 1; }
echo "Python : $PY"
"$PY" -c "import faster_whisper; print('faster-whisper', faster_whisper.__version__)" || {
  echo "faster-whisper absent. Installe-le :"; echo "  VIRTUAL_ENV=$(pwd)/.venv-piper uv pip install faster-whisper"; exit 1; }
echo "Analyse (la 1re fois, téléchargement du modèle)…"
echo /tmp/test_micro.wav | COMPAGNON_WHISPER=base "$PY" ecoute.py
echo
echo "=== Fin. Copie-moi tout ce qui est au-dessus si ça ne marche pas."
