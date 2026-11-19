#!/usr/bin/env bash
# XWayland (xcb) : sous KDE Wayland, c'est ce qui permet le « toujours au premier plan »,
# la position mémorisée et les clics qui traversent les zones vides.
# Pour essayer en Wayland natif :  COMPAGNON_WAYLAND=1 ./run.sh
cd "$(dirname "$(readlink -f "$0")")"
if [ -z "$COMPAGNON_WAYLAND" ]; then export QT_QPA_PLATFORM=xcb; fi
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" compagnon.py "$@"
