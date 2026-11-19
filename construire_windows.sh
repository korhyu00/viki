#!/usr/bin/env bash
# Fabrique la version Windows (Viki.exe) depuis Linux, avec Wine.
# Usage : bash construire_windows.sh      Résultat : Viki-Windows.zip
set -euo pipefail
cd "$(dirname "$0")"
SRC="$(pwd)"
W="${WORK:-$SRC/.construction-windows}"
export WINEPREFIX="$W/prefix" WINEDEBUG=-all
PY_TAG="20250317"; PY_VER="3.12.9"
mkdir -p "$W/cache"
dl() { [ -s "$2" ] || { echo "  téléchargement : $(basename "$2")"; curl -L --fail --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2"; }; }
command -v wine >/dev/null || { echo "Il faut Wine : sudo pacman -S wine"; exit 1; }
RUN="wine"; command -v xvfb-run >/dev/null && RUN="xvfb-run -a wine"
CERT=()
[ -n "${PIP_CERT:-}" ] && CERT=(--cert "Z:$PIP_CERT")

echo "=== 1/6 Python pour Windows"
if [ ! -x "$W/python/python.exe" ]; then
    dl "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_TAG/cpython-$PY_VER+$PY_TAG-x86_64-pc-windows-msvc-install_only.tar.gz" "$W/cache/pywin.tar.gz"
    tar -xzf "$W/cache/pywin.tar.gz" -C "$W"
fi
PY="$W/python/python.exe"

echo "=== 2/6 Bibliothèques Windows"
# PyQt6 6.6 : n'a pas besoin de l'ICU du système (marche sur plus de versions de Windows)
$RUN "$PY" -m pip install "${CERT[@]}" --disable-pip-version-check -q --no-warn-script-location \
    "PyQt6==6.6.1" "PyQt6-Qt6==6.6.1" "numpy==1.26.4" sounddevice pyinstaller live2d-py PyOpenGL SkelToJson opencv-python-headless 2>&1 | grep -v "X connection" || true
$RUN "$PY" -m pip uninstall -y -q av 2>&1 | grep -v "X connection" || true
mkdir -p "$W/stubs/av"
cat > "$W/stubs/av/__init__.py" <<'STUB'
"""Remplaçant léger de PyAV : le compagnon lit lui-même les WAV et donne l'audio décodé à faster-whisper."""
def open(*args, **kwargs):
    raise RuntimeError("décodage audio indisponible (fichier WAV attendu)")
STUB

echo "=== 3/6 Piper (voix) pour Windows"
dl "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip" "$W/cache/piper_win.zip"
rm -rf "$W/piper_x" && mkdir -p "$W/piper_x" && unzip -q -o "$W/cache/piper_win.zip" -d "$W/piper_x"
PIPER_DIR="$(dirname "$(find "$W/piper_x" -name piper.exe | head -1)")"

echo "    + whisper.cpp (reconnaissance vocale, robuste sur tous les processeurs)"
dl "https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.2/whisper-bin-x64.zip" "$W/cache/whispercpp.zip"
rm -rf "$W/wcpp_x" && mkdir -p "$W/wcpp_x" && unzip -q -o "$W/cache/whispercpp.zip" -d "$W/wcpp_x"
WCPP_DIR="$(dirname "$(find "$W/wcpp_x" -name whisper-cli.exe | head -1)")"

echo "=== 4/6 Icône"
python3 - "$SRC" "$W/icone.ico" <<'ICON'
import json, sys
from pathlib import Path
from PIL import Image
src, out = Path(sys.argv[1]), sys.argv[2]
cfg = json.loads((src / "assets/character.json").read_text())
img = Image.open(src / "assets" / cfg["image"]).convert("RGBA")
e = cfg["eyes"]; cx = (e[0]["x"] + e[1]["x"]) / 2; cy = (e[0]["y"] + e[1]["y"]) / 2
side = int(abs(e[1]["x"] - e[0]["x"]) * 2.8)
face = img.crop((int(cx - side / 2), max(0, int(cy - side / 2)), int(cx + side / 2), int(cy + side / 2)))
face.resize((256, 256), Image.LANCZOS).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
ICON

echo "=== 5/6 Fabrication du .exe (PyInstaller)"
B="$W/app"; rm -rf "$B" && mkdir -p "$B"
for f in compagnon.py extras.py visuel.py reglages.py lieux.py ecoute.py plateforme.py ia_api.py outils.py marionnette.py galerie.py live2d_rendu.py voix.py spine_rendu.py mails.py lecture.py apprentissage.py dev.py gestionpc.py manga.py i18n.py traductions.py themes.py streamer.py quotidien.py securite.py suivi.py vie.py devplus.py plus.py media.py atelier.py cerveau.py vieprivee.py liste.py raccourcis.py astuces.py pratique.py fun.py demarrage.py apparence.py; do cp "$f" "$B/"; done
cp -r assets "$B/"; rm -rf "$B/assets/"*/original "$B/assets/original"
rm -rf "$B/piper" && cp -r "$PIPER_DIR" "$B/piper"
mkdir -p "$B/whispercpp" && cp "$WCPP_DIR"/whisper-cli.exe "$WCPP_DIR"/*.dll "$B/whispercpp/" && rm -f "$B/whispercpp/SDL2.dll"
mkdir -p "$B/voices"
[ -s voices/fr_FR-siwis-medium.onnx ] && cp voices/fr_FR-siwis-medium.onnx voices/fr_FR-siwis-medium.onnx.json "$B/voices/" || true
cd "$B"
$RUN "$PY" -m PyInstaller --noconfirm --clean --windowed --name Viki --icon "Z:$W/icone.ico" \
    --paths "Z:$W/stubs" --hidden-import av \
    --hidden-import extras --hidden-import visuel --hidden-import reglages --hidden-import lieux \
    --hidden-import plateforme --hidden-import sounddevice \
    --collect-data _sounddevice_data --collect-binaries _sounddevice_data \
    --add-data "assets;assets" --add-data "ecoute.py;." --add-data "piper;piper" --add-data "whispercpp;whispercpp" --add-data "voices;voices" \
    --exclude-module tkinter --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module PyQt6.QtQml --exclude-module PyQt6.QtQuick \
    --exclude-module PyQt6.QtMultimedia --exclude-module PyQt6.QtPdf --exclude-module PyQt6.Qt3DCore \
    compagnon.py 2>&1 | grep -E "ERROR|completed successfully" || true
D="$B/dist/Viki"
[ -f "$D/Viki.exe" ] || { echo "La fabrication a échoué."; exit 1; }
# même programme en version « console » : sert à l'oreille (reconnaissance vocale) et au diagnostic
$RUN "$PY" -m PyInstaller --noconfirm --console --name Viki-console --distpath distc --workpath buildc \
    --icon "Z:$W/icone.ico" --paths "Z:$W/stubs" --hidden-import av \
    --hidden-import extras --hidden-import visuel --hidden-import reglages --hidden-import lieux \
    --hidden-import plateforme --hidden-import sounddevice \
    --collect-data _sounddevice_data --collect-binaries _sounddevice_data \
    --add-data "assets;assets" --add-data "ecoute.py;." --add-data "piper;piper" --add-data "whispercpp;whispercpp" --add-data "voices;voices" \
    --exclude-module tkinter --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module PyQt6.QtQml --exclude-module PyQt6.QtQuick \
    --exclude-module PyQt6.QtMultimedia --exclude-module PyQt6.QtPdf --exclude-module PyQt6.Qt3DCore \
    compagnon.py 2>&1 | grep -E "ERROR|COLLECT.*completed" || true
cp distc/Viki-console/Viki-console.exe "$D/"

echo "=== 6/6 Allègement et archive"
Q="$D/_internal/PyQt6/Qt6"
for m in Quick Qml QmlModels QmlWorkerScript Pdf PdfWidgets 3D Designer Help Sql Test Sensors Bluetooth Nfc \
         Positioning SerialPort TextToSpeech WebSockets WebChannel RemoteObjects SpatialAudio ShaderTools \
         Multimedia MultimediaWidgets QuickWidgets QuickControls2 QuickTemplates2 QuickShapes QuickTest Charts \
         DataVisualization Lottie Scxml StateMachine VirtualKeyboard Labs Location; do
    rm -f "$Q"/bin/Qt6$m*.dll "$D/_internal/PyQt6/Qt$m"*.pyd
done
rm -rf "$Q/qml" "$Q/translations" "$Q/bin/avcodec"* "$Q/bin/avformat"* "$Q/bin/avutil"* "$Q/bin/swresample"* \
       "$Q/bin/swscale"* "$Q/bin/opengl32sw.dll" "$Q/plugins/multimedia" "$Q/plugins/sqldrivers" \
       "$Q/plugins/qmltooling" "$Q/plugins/position" "$Q/plugins/sensors"
cat > "$D/LISEZ-MOI.txt" <<'TXT'
Viki pour Windows
======================
Double-clique sur Viki.exe.
(Viki-console.exe sert à la reconnaissance vocale et au diagnostic : laisse-le à côté.)

- Tout reste sur ton PC. Tes réglages et souvenirs : %APPDATA%\Viki
  Voix, modèles et personnages : %LOCALAPPDATA%\Viki
- Clic droit sur elle : Réglages. Double-clic : lui écrire.
- Pour discuter avec elle : installe Ollama (https://ollama.com), puis Réglages → Discussion.
- Si elle n'a pas de voix : Réglages → Voix → « Télécharger sa voix ».
- Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » (programme non signé) :
  clique sur « Informations complémentaires » puis « Exécuter quand même ».
TXT
cd "$B/dist" && rm -f "$SRC/Viki-Windows.zip" && zip -q -r "$SRC/Viki-Windows.zip" Viki
echo
echo "C'est prêt : $SRC/Viki-Windows.zip ($(du -h "$SRC/Viki-Windows.zip" | cut -f1))"
