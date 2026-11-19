#!/usr/bin/env bash
# Démarre le serveur Open-LLM-VTuber puis le client bureau (fenêtre / desktop pet).
cd "$HOME/Open-LLM-VTuber" || exit 1
LOG="$HOME/Open-LLM-VTuber/serveur.log"
WEB="$HOME/Open-LLM-VTuber-Web"
ELECTRON="$WEB/node_modules/electron/dist/electron"
# sinon, l'Electron du système (sudo pacman -S electron)
[ -x "$ELECTRON" ] || ELECTRON="$(command -v electron || true)"

if ! curl -s http://localhost:12393 >/dev/null; then
  nohup uv run run_server.py >"$LOG" 2>&1 &
  echo "Démarrage du serveur (journal : $LOG)…"
  for i in $(seq 1 180); do
    curl -s http://localhost:12393 >/dev/null && break
    sleep 1
  done
fi

if ! curl -s http://localhost:12393 >/dev/null; then
  notify-send "Open-LLM-VTuber" "Le serveur n'a pas démarré : regarde $LOG" 2>/dev/null
  echo "Le serveur n'a pas démarré : regarde $LOG"
  exit 1
fi

if [ -n "$ELECTRON" ] && [ -x "$ELECTRON" ] && [ -f "$WEB/out/main/index.js" ]; then
  # X11 (XWayland) : transparence et clics traversants du mode desktop pet sous KDE
  cd "$WEB"
  nohup "$ELECTRON" . --ozone-platform=x11 >"$HOME/Open-LLM-VTuber/client.log" 2>&1 &
  sleep 4
  if ! pgrep -f "$WEB" >/dev/null; then
    # dernier recours si le bac à sable de Chromium bloque
    nohup "$ELECTRON" . --ozone-platform=x11 --no-sandbox >>"$HOME/Open-LLM-VTuber/client.log" 2>&1 &
  fi
elif [ -x ./client.AppImage ]; then
  ./client.AppImage --ozone-platform=x11 >/dev/null 2>&1 &
else
  notify-send "Open-LLM-VTuber" "Client bureau absent : lance reparer_client_vtuber.sh" 2>/dev/null
  echo "Client bureau absent : lance compagnon/vtuber/reparer_client_vtuber.sh"
fi
