#!/usr/bin/env bash
# Installe Open-LLM-VTuber (MIT) sur CachyOS, en français et 100 % local :
#   discussion = ton Ollama, micro = faster-whisper (français), voix = Piper (français)
# + (option) le client bureau avec le mode « desktop pet », compilé pour Linux.
set -e
ICI="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DEST="$HOME/Open-LLM-VTuber"            # chemin sans espaces ni accents (exigé par le projet)
WEB="$HOME/Open-LLM-VTuber-Web"

echo "==> Paquets (git, ffmpeg, uv, nodejs)"
sudo pacman -S --needed --noconfirm git ffmpeg uv nodejs npm curl

echo "==> Vérification d'Ollama"
if ! curl -s http://localhost:11434/api/tags >/dev/null; then
  echo "    Ollama ne répond pas. Lance d'abord : bash ../install_ollama.sh (dans le dossier du compagnon)"
  exit 1
fi
MODEL=$(ollama list | awk 'NR==2 {print $1}')
if [ -z "$MODEL" ]; then
  echo "    Aucun modèle Ollama installé : installe-en un depuis le compagnon"
  echo "    (clic droit → Modèles de discussion) puis relance ce script."
  exit 1
fi
echo "    Modèle utilisé : $MODEL  (modifiable plus tard dans $DEST/conf.yaml)"

echo "==> Téléchargement d'Open-LLM-VTuber"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only || true
  git -C "$DEST" submodule update --init --recursive
else
  git clone --recursive https://github.com/Open-LLM-VTuber/Open-LLM-VTuber "$DEST"
fi
cd "$DEST"

echo "==> Dépendances Python (uv choisit un Python compatible tout seul)"
uv sync
uv pip install --python .venv/bin/python piper-tts faster-whisper

echo "==> Voix française Piper"
mkdir -p models/piper
V=models/piper/fr_FR-siwis-medium
if [ -f "$ICI/../voices/fr_FR-siwis-medium.onnx" ] && [ -f "$ICI/../voices/fr_FR-siwis-medium.onnx.json" ]; then
  cp "$ICI/../voices/fr_FR-siwis-medium.onnx" "$ICI/../voices/fr_FR-siwis-medium.onnx.json" models/piper/
else
  BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"
  curl -fL -o "$V.onnx" "$BASE/fr_FR-siwis-medium.onnx"
  curl -fL -o "$V.onnx.json" "$BASE/fr_FR-siwis-medium.onnx.json"
fi

echo "==> Configuration en français, 100 % locale"
python3 "$ICI/configurer_vtuber.py" "$DEST" "$MODEL" "$DEST/$V.onnx"

echo "==> Client bureau (fenêtre + mode desktop pet)"
bash "$ICI/reparer_client_vtuber.sh"
cd "$DEST"

echo "==> Lanceur"
cp "$ICI/lancer_vtuber.sh" "$DEST/lancer_vtuber.sh"
chmod +x "$DEST/lancer_vtuber.sh"
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/open-llm-vtuber.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Open-LLM-VTuber
Comment=Compagnon IA Live2D (local)
Exec=$DEST/lancer_vtuber.sh
Terminal=false
Categories=Utility;
EOF

echo
echo "Terminé ! Lance-le avec :  ~/Open-LLM-VTuber/lancer_vtuber.sh"
echo "(ou « Open-LLM-VTuber » dans le menu KDE). Le 1er lancement télécharge le modèle du micro."
