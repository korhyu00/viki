#!/usr/bin/env bash
# Voix naturelle (Chatterbox Multilingual) avec accélération AMD ROCm.
# Testé pour Radeon RX 6600 / 6600 XT (Navi 23). ~6 Go à télécharger.
set -e
# --- Python compatible (3.10 à 3.13) : beaucoup de systèmes récents (Bazzite, Fedora 43, Arch…) ont Python 3.14/3.15,
#     pour lequel PyTorch n'existe pas encore. On prend « uv », qui télécharge un Python 3.12 rien que pour Viki,
#     dans ton dossier perso, sans mot de passe et sans toucher au système.
viki_uv() {
  if command -v uv >/dev/null; then UV=uv; return 0; fi
  local B="${XDG_DATA_HOME:-$HOME/.local/share}/viki/uv"
  for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "$B/bin/uv"; do [ -x "$c" ] && { UV="$c"; return 0; }; done
  echo "==> J'installe « uv » (gestionnaire de Python) dans $B — sans mot de passe"
  local SP=""
  for v in python3.13 python3.12 python3.11 python3 python3.14 python3.15; do command -v "$v" >/dev/null && { SP=$v; break; }; done
  [ -n "$SP" ] || { echo "Il faut Python 3 sur ton système."; return 1; }
  rm -rf "$B"
  "$SP" -m venv "$B" && "$B/bin/pip" install -q --upgrade pip uv && UV="$B/bin/uv"
}
viki_venv_ok() {   # le .venv existe et son Python est compatible (3.10 à 3.13)
  [ -x "$1/bin/python" ] && "$1/bin/python" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)'
}
# ---
cd "$(dirname "$(readlink -f "$0")")"

echo "==> Outils (uv pour un Python 3.11 isolé, ffmpeg)"
viki_uv || exit 1
if ! command -v ffmpeg >/dev/null; then
  if command -v pacman >/dev/null; then sudo pacman -S --needed --noconfirm ffmpeg
  elif command -v apt-get >/dev/null; then sudo apt-get install -y ffmpeg
  elif command -v rpm-ostree >/dev/null; then echo "    (système immuable : ffmpeg vient en général avec ton système ou en Flatpak)"
  elif command -v dnf >/dev/null; then sudo dnf install -y ffmpeg-free || sudo dnf install -y ffmpeg
  elif command -v zypper >/dev/null; then sudo zypper install -y ffmpeg
  elif command -v xbps-install >/dev/null; then sudo xbps-install -Sy ffmpeg
  elif command -v apk >/dev/null; then sudo apk add ffmpeg
  else echo "    Installe ffmpeg avec ton gestionnaire de logiciels, puis relance."; fi
fi

echo "==> Accès au GPU AMD (groupes video/render)"
if ! id -nG "$USER" | grep -qw render; then
  sudo usermod -aG video,render "$USER"
  echo "    -> tu as été ajouté aux groupes video et render : déconnecte-toi puis reconnecte-toi après l'installation."
fi

echo "==> Environnement Python 3.11 séparé (.venv-voix)"
if [ -d .venv-voix ] && ! viki_venv_ok .venv-voix; then rm -rf .venv-voix; fi
[ -d .venv-voix ] || "$UV" venv --python 3.11 .venv-voix
export VIRTUAL_ENV="$PWD/.venv-voix"

echo "==> Chatterbox"
"$UV" pip install chatterbox-tts "setuptools<81"   # setuptools : requis par le filigrane audio (perth)

echo "==> PyTorch pour ROCm (remplace la version NVIDIA)"
"$UV" pip install --reinstall "torch==2.6.0" "torchaudio==2.6.0" \
  --index-url https://download.pytorch.org/whl/rocm6.2.4

echo "==> Vérification du GPU"
HSA_OVERRIDE_GFX_VERSION=10.3.0 .venv-voix/bin/python - <<'EOF'
import torch
if torch.cuda.is_available():
    print("    GPU détecté :", torch.cuda.get_device_name(0))
else:
    print("    ⚠ GPU non détecté : la voix marchera sur le processeur (plus lent).")
    print("      Après une reconnexion de session (groupes video/render), relance ce test.")
EOF

echo "==> Préparation d'un extrait de voix française par défaut"
# Chatterbox imite le timbre d'un extrait : on lui donne la voix Piper (française)
# pour qu'elle parle sans accent anglais. Tu pourras en choisir un autre dans le menu.
if [ -x .venv/bin/piper ] && [ -f voices/fr_FR-siwis-medium.onnx.json ]; then
  echo "Bonjour ! Je suis ravie de te retrouver. Aujourd'hui, il fait beau, et j'ai plein de choses à te raconter. Tu veux qu'on fasse une petite pause ensemble ?" \
    | .venv/bin/piper -m voices/fr_FR-siwis-medium.onnx -f voices/extrait_defaut.wav
fi

echo "==> Premier chargement (télécharge le modèle, ~3 Go, quelques minutes)"
HSA_OVERRIDE_GFX_VERSION=10.3.0 .venv-voix/bin/python -c "
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
import torch
ChatterboxMultilingualTTS.from_pretrained(device='cuda' if torch.cuda.is_available() else 'cpu')
print('    modèle prêt')"

echo
echo "Terminé ! Dans le compagnon : clic droit → Voix → Naturelle (Chatterbox)."
