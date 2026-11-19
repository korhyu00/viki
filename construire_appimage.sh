#!/usr/bin/env bash
# Fabrique l'AppImage du compagnon (un seul fichier à partager, qui marche sur la plupart des Linux).
# Usage : bash construire_appimage.sh
# Il faut internet pendant la fabrication (Python, PyQt6, Piper…). Résultat : Viki-x86_64.AppImage
set -euo pipefail
cd "$(dirname "$0")"
SRC="$(pwd)"
WORK="${WORK:-$SRC/.construction-appimage}"
APPDIR="$WORK/Viki.AppDir"
PY_TAG="20250317"; PY_VER="3.12.9"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
VOIX="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"

dl() { [ -s "$2" ] || { echo "  téléchargement : $(basename "$2")"; curl -L --fail --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2"; }; }

echo "=== 1/7 Préparation"
rm -rf "$APPDIR"
mkdir -p "$WORK/cache" "$APPDIR/usr/app" "$APPDIR/usr/lib"

echo "=== 2/7 Python autonome $PY_VER"
dl "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_TAG/cpython-$PY_VER+$PY_TAG-x86_64-unknown-linux-gnu-install_only.tar.gz" "$WORK/cache/python.tar.gz"
tar -xzf "$WORK/cache/python.tar.gz" -C "$APPDIR/usr"
PY="$APPDIR/usr/python/bin/python3"

echo "=== 3/7 Bibliothèques (interface, calculs, reconnaissance vocale)"
"$PY" -m pip install --no-cache-dir --disable-pip-version-check -q "PyQt6>=6.5" numpy faster-whisper zstandard live2d-py PyOpenGL SkelToJson opencv-python-headless

echo "=== 4/7 Le compagnon"
for f in compagnon.py extras.py visuel.py reglages.py lieux.py ecoute.py voix_naturelle.py voix_legere.py plateforme.py ia_api.py outils.py marionnette.py galerie.py live2d_rendu.py voix.py spine_rendu.py mails.py lecture.py apprentissage.py dev.py gestionpc.py manga.py i18n.py traductions.py themes.py streamer.py quotidien.py securite.py suivi.py vie.py devplus.py plus.py media.py atelier.py cerveau.py vieprivee.py liste.py raccourcis.py astuces.py pratique.py fun.py demarrage.py apparence.py install_voix_naturelle.sh install_voix_legere.sh install_manga_ocr.sh installer_images.sh; do
    [ -f "$f" ] && cp "$f" "$APPDIR/usr/app/"
done
cp -r assets "$APPDIR/usr/app/"
rm -rf "$APPDIR/usr/app/assets/"*/original "$APPDIR/usr/app/assets/original"

echo "=== 5/7 Voix (Piper + voix française)"
dl "$PIPER_URL" "$WORK/cache/piper.tar.gz"
tar -xzf "$WORK/cache/piper.tar.gz" -C "$APPDIR/usr/app/"           # crée usr/app/piper/
mkdir -p "$APPDIR/usr/app/voices"
if [ -s voices/fr_FR-siwis-medium.onnx ] && [ -s voices/fr_FR-siwis-medium.onnx.json ]; then
    cp voices/fr_FR-siwis-medium.onnx voices/fr_FR-siwis-medium.onnx.json "$APPDIR/usr/app/voices/"
else
    dl "$VOIX/fr_FR-siwis-medium.onnx" "$WORK/cache/fr_FR-siwis-medium.onnx" &&
    dl "$VOIX/fr_FR-siwis-medium.onnx.json" "$WORK/cache/fr_FR-siwis-medium.onnx.json" &&
    cp "$WORK/cache/fr_FR-siwis-medium.onnx"* "$APPDIR/usr/app/voices/" ||
    echo "  (voix non intégrée : elle proposera de la télécharger au 1er lancement)"
fi

echo "=== 6/7 Allègement"
QT="$("$PY" -c 'import PyQt6, os; print(os.path.dirname(PyQt6.__file__))')"
# modules Qt inutiles pour le compagnon (QML, 3D, PDF, capteurs, multimédia, web…)
for m in Quick Qml QmlModels QmlWorkerScript QmlMeta Pdf PdfWidgets 3D Designer Help Sql Test Sensors Bluetooth \
         Nfc Positioning SerialPort TextToSpeech WebSockets WebChannel RemoteObjects SpatialAudio ShaderTools \
         Multimedia MultimediaWidgets QuickWidgets QuickControls2 QuickTemplates2 QuickShapes QuickTest Charts \
         DataVisualization Graphs Lottie Scxml StateMachine VirtualKeyboard Labs Location; do
    rm -f "$QT"/Qt$m*.abi3.so "$QT"/Qt$m*.pyi
    rm -rf "$QT"/Qt6/lib/libQt6$m*.so* 2>/dev/null || true
done
rm -rf "$QT/Qt6/qml" "$QT/Qt6/translations" "$QT/Qt6/lib/libav"* "$QT/Qt6/lib/libsw"*
for pl in sqldrivers multimedia sensors position qmltooling designer assetimporters geometryloaders help qmllint \
          qmlls renderers renderplugins sceneparsers scxmldatamodel texttospeech; do
    rm -rf "$QT/Qt6/plugins/$pl"
done
# PyAV (décodeur vidéo, ~130 Mo) : inutile, le compagnon donne l'audio déjà décodé à faster-whisper
SITE="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
"$PY" -m pip uninstall -y -q av hf_xet >/dev/null 2>&1 || true
mkdir -p "$SITE/av"
cat > "$SITE/av/__init__.py" <<'STUB'
"""Remplaçant léger de PyAV : le compagnon lit lui-même les WAV et donne l'audio décodé à faster-whisper."""
def open(*args, **kwargs):
    raise RuntimeError("décodage audio indisponible dans l'AppImage (fichier WAV attendu)")
STUB
rm -rf "$SITE/pip" "$SITE"/pip-*.dist-info "$APPDIR/usr/python/bin/pip"*
find "$APPDIR/usr/python" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/usr/python/lib/python3.12" -maxdepth 1 -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$APPDIR/usr/python/lib/python3.12/idlelib" "$APPDIR/usr/python/lib/python3.12/tkinter" \
       "$APPDIR/usr/python/lib/python3.12/ensurepip" "$APPDIR/usr/python/include" \
       "$APPDIR/usr/python/lib/libtcl"* "$APPDIR/usr/python/lib/libtk"* "$APPDIR/usr/python/lib/tcl"* \
       "$APPDIR/usr/python/lib/tk"* 2>/dev/null || true
# bibliothèque souvent absente sur les autres distributions (nécessaire à l'affichage X11 de Qt)
LIB=$(ldconfig -p 2>/dev/null | awk '/libxcb-cursor.so.0 /{print $NF; exit}')
[ -n "$LIB" ] && cp -L "$LIB" "$APPDIR/usr/lib/" || echo "  (libxcb-cursor non trouvée : sudo pacman -S xcb-util-cursor)"

echo "=== 7/7 Assemblage"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"      # fenêtre sans bord transparente : XWayland
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 COMPAGNON_PORTABLE=1
export COMPAGNON_ORIG_LD="${LD_LIBRARY_PATH:-}"            # rendu tel quel aux programmes externes
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
unset PYTHONHOME PYTHONPATH
exec "$HERE/usr/python/bin/python3" "$HERE/usr/app/compagnon.py" "$@"
RUN
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/viki.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Viki
Comment=Une compagne animée sur ton bureau (100 % local)
Exec=AppRun
Icon=viki
Categories=Utility;
Terminal=false
DESK
"$PY" - "$APPDIR" <<'ICON'
import json, sys
from pathlib import Path
from PyQt6.QtGui import QGuiApplication, QImage
from PyQt6.QtCore import Qt, QRect
app = QGuiApplication(["x", "-platform", "offscreen"])
d = Path(sys.argv[1])
cfg = json.loads((d / "usr/app/assets/character.json").read_text())
img = QImage(str(d / "usr/app/assets" / cfg["image"]))
e = cfg["eyes"]
cx, cy = (e[0]["x"] + e[1]["x"]) / 2, (e[0]["y"] + e[1]["y"]) / 2
side = int(abs(e[1]["x"] - e[0]["x"]) * 2.8)
icon = img.copy(QRect(int(cx - side / 2), max(0, int(cy - side / 2)), side, side)).scaled(
    256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
icon.save(str(d / "viki.png"))
ICON
ln -sf viki.png "$APPDIR/.DirIcon"
dl "$TOOL_URL" "$WORK/cache/appimagetool"
chmod +x "$WORK/cache/appimagetool"
ARCH=x86_64 "$WORK/cache/appimagetool" --appimage-extract-and-run --no-appstream "$APPDIR" "$SRC/Viki-x86_64.AppImage"
echo
echo "C'est prêt : $SRC/Viki-x86_64.AppImage  ($(du -h "$SRC/Viki-x86_64.AppImage" | cut -f1))"
echo "Pour la lancer : chmod +x Viki-x86_64.AppImage && ./Viki-x86_64.AppImage"
