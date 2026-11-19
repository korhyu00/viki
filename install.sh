#!/usr/bin/env bash
# Installation du compagnon de bureau sur CachyOS / Arch (KDE Plasma)
set -e
cd "$(dirname "$(readlink -f "$0")")"
DIR="$(pwd)"

echo "==> Paquets système (Qt6, Python, lecture audio, voix de secours)"
sudo pacman -S --needed --noconfirm python python-pip python-pyqt6 pipewire espeak-ng curl playerctl

echo "==> Environnement Python de l'appli"
[ -d .venv ] || python -m venv --system-site-packages .venv

echo "==> Piper (voix locale) dans un Python 3.12 séparé (le Python de CachyOS est trop récent)"
sudo pacman -S --needed --noconfirm uv
if [ ! -x .venv-piper/bin/piper ]; then
  uv venv --python 3.12 .venv-piper
  VIRTUAL_ENV="$PWD/.venv-piper" uv pip install piper-tts
fi

echo "==> Voix française (Siwis, ~60 Mo)"
mkdir -p voices
V=voices/fr_FR-siwis-medium
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"
if [ ! -f "$V.onnx" ] || [ "$(stat -c%s "$V.onnx")" -lt 1000000 ]; then
  curl -fL -o "$V.onnx" "$BASE/fr_FR-siwis-medium.onnx"
fi
if [ ! -f "$V.onnx.json" ] || [ "$(stat -c%s "$V.onnx.json")" -lt 500 ]; then
  curl -fL -o "$V.onnx.json" "$BASE/fr_FR-siwis-medium.onnx.json"
fi
if echo "Test." | .venv-piper/bin/piper -m "$V.onnx" -f /tmp/compagnon_test.wav >/dev/null 2>&1; then
  echo "    -> voix Piper OK"
else
  echo "    ⚠ La voix Piper ne fonctionne pas : la voix de secours (robotique) sera utilisée."
fi

read -r -p "Installer le détourage automatique des images (retire le fond, ~300 Mo) ? [O/n] " rep
if [[ ! "$rep" =~ ^[nN] ]]; then
  .venv/bin/pip install -q "rembg[cpu]" || echo "    ⚠ détourage non installé (version de Python incompatible) : utilise des PNG à fond transparent."
  echo "    -> détourage installé (le modèle se télécharge au premier usage)"
fi

echo "==> Raccourci dans le menu des applications"
chmod +x run.sh compagnon.py
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/compagnon.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Compagnon de bureau
Comment=Compagnon animé qui parle
Exec=$DIR/run.sh
Icon=$DIR/assets/character.png
Terminal=false
Categories=Utility;
EOF

read -r -p "Lancer automatiquement au démarrage de la session ? [o/N] " rep
if [[ "$rep" =~ ^[oOyY] ]]; then
  mkdir -p ~/.config/autostart
  cp ~/.local/share/applications/compagnon.desktop ~/.config/autostart/
  echo "    -> démarrage automatique activé"
fi

echo
echo "Terminé ! Lance-la avec :  $DIR/run.sh"
echo "(ou cherche « Compagnon de bureau » dans le menu KDE)"
