#!/usr/bin/env bash
# Voix légère (Pocket TTS de Kyutai) : tourne sur le processeur, ~1 Go en tout.
# Bien plus légère que la voix naturelle (Chatterbox), et parle français.
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

echo "==> Environnement Python séparé (.venv-voix-legere)"
if [ -d .venv-voix-legere ] && ! viki_venv_ok .venv-voix-legere; then rm -rf .venv-voix-legere; fi
if viki_uv; then
  [ -d .venv-voix-legere ] || "$UV" venv --python 3.12 .venv-voix-legere
  VIRTUAL_ENV="$PWD/.venv-voix-legere" "$UV" pip install pocket-tts scipy \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
else
  PY=""
  for v in python3.12 python3.11 python3.13 python3.10; do command -v $v >/dev/null && { PY=$v; break; }; done
  [ -n "$PY" ] || { echo "Il me faut Python 3.10 à 3.13 (PyTorch n'existe pas encore pour ton Python)."; exit 1; }
  $PY -m venv .venv-voix-legere
  .venv-voix-legere/bin/pip install --upgrade pip
  .venv-voix-legere/bin/pip install pocket-tts scipy --extra-index-url https://download.pytorch.org/whl/cpu
fi

echo "==> Téléchargement du modèle français et premier essai (quelques minutes la 1re fois)"
.venv-voix-legere/bin/python - <<'EOF'
import time
from pocket_tts import TTSModel
t = time.time()
m = TTSModel.load_model(language="french")
s = m.get_state_for_audio_prompt("estelle")
a = m.generate_audio(s, "Bonjour ! Ma voix légère est prête.")
print(f"    prête : {a.shape[-1] / m.sample_rate:.1f} s de voix, calculées en {time.time() - t:.0f} s (avec le chargement)")
EOF
echo
echo "C'est fini ! Dans Viki : Réglages → Voix → Moteur de voix → « Légère (Pocket TTS) »."
