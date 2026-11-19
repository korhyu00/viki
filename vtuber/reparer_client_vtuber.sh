#!/usr/bin/env bash
# Prépare le client bureau d'Open-LLM-VTuber (fenêtre + mode desktop pet) pour Linux,
# sans passer par l'AppImage, et met à jour le lanceur pour l'utiliser.
set -e
ICI="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
WEB="$HOME/Open-LLM-VTuber-Web"

sudo pacman -S --needed --noconfirm git nodejs npm

if [ -d "$WEB/.git" ]; then
  git -C "$WEB" pull --ff-only || true
else
  git clone https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web "$WEB"
fi
cd "$WEB"
echo "==> Dépendances (télécharge Electron, quelques minutes)"
npm ci --no-audit --no-fund
# npm récent bloque les scripts d'installation : on télécharge Electron nous-mêmes
if [ ! -x node_modules/electron/dist/electron ]; then
  echo "==> Téléchargement d'Electron"
  node node_modules/electron/install.js
fi
if [ ! -x node_modules/electron/dist/electron ]; then
  echo "==> Electron du système à la place"
  sudo pacman -S --needed --noconfirm electron
fi
echo "==> Compilation du client"
npm run build

# bac à sable de Chromium (sinon Electron peut refuser de démarrer)
if [ -f node_modules/electron/dist/chrome-sandbox ]; then
  sudo chown root:root node_modules/electron/dist/chrome-sandbox
  sudo chmod 4755 node_modules/electron/dist/chrome-sandbox
fi

cp "$ICI/lancer_vtuber.sh" "$HOME/Open-LLM-VTuber/lancer_vtuber.sh"
chmod +x "$HOME/Open-LLM-VTuber/lancer_vtuber.sh"
rm -f "$HOME/Open-LLM-VTuber/client.AppImage"

echo
echo "✅ Client bureau prêt. Relance : ~/Open-LLM-VTuber/lancer_vtuber.sh"
echo "   (ou « Open-LLM-VTuber » dans le menu KDE)"
