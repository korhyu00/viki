#!/usr/bin/env bash
# manga-ocr : lit le japonais des bulles de manga (texte vertical, furigana…). Tourne sur le processeur, ~1 Go.
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
echo "==> Environnement Python séparé (.venv-manga-ocr)"
if [ -d .venv-manga-ocr ] && ! viki_venv_ok .venv-manga-ocr; then rm -rf .venv-manga-ocr; fi
if viki_uv; then
  [ -d .venv-manga-ocr ] || "$UV" venv --python 3.12 .venv-manga-ocr
  VIRTUAL_ENV="$PWD/.venv-manga-ocr" "$UV" pip install manga-ocr \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
else
  PY=""
  for v in python3.12 python3.11 python3.13 python3.10; do command -v $v >/dev/null && { PY=$v; break; }; done
  [ -n "$PY" ] || { echo "Il me faut Python 3.10 à 3.13 (PyTorch n'existe pas encore pour ton Python)."; exit 1; }
  $PY -m venv .venv-manga-ocr
  .venv-manga-ocr/bin/pip install --upgrade pip
  .venv-manga-ocr/bin/pip install manga-ocr --extra-index-url https://download.pytorch.org/whl/cpu
fi
echo "==> Téléchargement du modèle (une seule fois)"
.venv-manga-ocr/bin/python -c "from manga_ocr import MangaOcr; MangaOcr(); print('    manga-ocr est prêt !')"
echo
echo "C'est fini ! Dans Viki : traduire un manga → Lecture « Automatique » ou « manga-ocr »."
