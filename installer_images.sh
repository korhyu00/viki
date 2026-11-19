#!/usr/bin/env bash
# Installe ComfyUI (le moteur qui crée les images sur ton PC) pour Viki.
# Usage : bash installer_images.sh [dossier]   (par défaut : ./comfyui à côté de ce script)
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
D="${1:-$(dirname "$(readlink -f "$0")")/comfyui}"
echo "==> Moteur d'images de Viki (ComfyUI) dans : $D"
command -v git >/dev/null || { echo "Il faut git : installe-le avec ton gestionnaire de logiciels (paquet « git »)."; exit 1; }
if [ -d "$D/.git" ]; then
  echo "==> Mise à jour"
  git -C "$D" pull --ff-only || true
else
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$D"
fi
cd "$D"

# PyTorch adapté à ta carte graphique (NVIDIA, AMD, Intel Arc, ou processeur)
if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
  CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' .')
  if [ -n "$CAP" ] && [ "$CAP" -lt 75 ] 2>/dev/null; then
    IDX=https://download.pytorch.org/whl/cu126; echo "==> Carte NVIDIA plus ancienne détectée (CUDA 12.6)"
  else
    IDX=https://download.pytorch.org/whl/cu128; echo "==> Carte NVIDIA détectée"
  fi
elif grep -qs 0x1002 /sys/class/drm/card*/device/vendor && [ -e /dev/kfd ]; then
  IDX=https://download.pytorch.org/whl/rocm6.4; echo "==> Carte AMD détectée (ROCm)"
elif grep -qs 0x8086 /sys/class/drm/card*/device/vendor && lspci 2>/dev/null | grep -Eiq 'VGA|Display' && \
     lspci 2>/dev/null | grep -Ei 'VGA|Display' | grep -Eiq 'Arc|Battlemage|Alchemist|Meteor|Lunar|Arrow'; then
  IDX=https://download.pytorch.org/whl/xpu; echo "==> Carte Intel Arc détectée (XPU)"
else
  IDX=https://download.pytorch.org/whl/cpu
  echo "==> Pas de carte graphique compatible : ça marchera, mais lentement (processeur)"
fi
if grep -qs 0x1002 /sys/class/drm/card*/device/vendor && [ ! -e /dev/kfd ]; then
  echo "    (Carte AMD vue, mais le pilote de calcul /dev/kfd est absent : installe le noyau standard / amdgpu.)"
fi

echo "==> Environnement Python séparé (.venv) — environ 3 à 5 Go à télécharger"
if [ -d .venv ] && ! viki_venv_ok .venv; then
  echo "    (l'ancien .venv utilise un Python trop récent pour PyTorch : je le refais)"; rm -rf .venv
fi
if viki_uv; then
  [ -d .venv ] || "$UV" venv --python 3.12 .venv
  VIRTUAL_ENV="$PWD/.venv" "$UV" pip install torch torchvision torchaudio --index-url "$IDX"
  VIRTUAL_ENV="$PWD/.venv" "$UV" pip install -r requirements.txt
else
  PY=""
  for v in python3.12 python3.11 python3.13 python3.10; do command -v $v >/dev/null && { PY=$v; break; }; done
  [ -n "$PY" ] || { echo "Il me faut Python 3.10 à 3.13 (PyTorch n'existe pas encore pour ton Python)."; exit 1; }
  $PY -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install torch torchvision torchaudio --index-url "$IDX"
  .venv/bin/pip install -r requirements.txt
fi
mkdir -p models/checkpoints
touch .viki_ok
echo
echo "C'est fini ! Retourne dans Viki → Atelier d'images → « IA sur mon PC » et télécharge un modèle."
