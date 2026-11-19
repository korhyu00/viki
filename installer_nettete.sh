#!/usr/bin/env bash
# Installe Real-ESRGAN (netteté par IA, 100 % local, utilise la carte graphique via Vulkan).
# Usage : bash installer_nettete.sh
set -e
cd "$(dirname "$0")"
DEST="tools/realesrgan"
if [ -x "$DEST/realesrgan-ncnn-vulkan" ]; then
    echo "Déjà installé dans $DEST."
    exit 0
fi
command -v unzip >/dev/null || { echo "Il faut unzip : sudo pacman -S unzip"; exit 1; }
mkdir -p "$DEST"
echo "Téléchargement de Real-ESRGAN (~45 Mo)…"
curl -L --fail -o /tmp/realesrgan.zip \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
unzip -o -q /tmp/realesrgan.zip -d "$DEST"
rm -f /tmp/realesrgan.zip "$DEST"/*.jpg "$DEST"/*.mp4
chmod +x "$DEST/realesrgan-ncnn-vulkan"
# pilote Vulkan pour les cartes AMD (déjà présent sur la plupart des installations)
pacman -Q vulkan-radeon >/dev/null 2>&1 || echo "Conseil : sudo pacman -S vulkan-radeon (pilote Vulkan AMD)"
echo "C'est prêt ! Dans les réglages : Personnage → « Rendre plus net »."
