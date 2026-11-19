#!/usr/bin/env bash
# Installe Ollama (modèle de langage 100 % local) avec accélération AMD ROCm,
# réglé pour la Radeon RX 6600 (Navi 23). Rien n'est envoyé sur internet
# une fois le modèle téléchargé.
set -e

echo "==> Ollama avec support ROCm (AMD)"
sudo pacman -S --needed --noconfirm ollama-rocm

echo "==> Réglage pour la RX 6600 (gfx1032 -> gfx1030)"
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/rx6600.conf >/dev/null <<'EOF'
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=10.3.0"
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama
sleep 3

echo
echo "Quel modèle installer ?"
echo "  1) qwen2.5:7b   — meilleur français et plus de répartie (~4,7 Go)  [conseillé]"
echo "  2) llama3.2:3b  — plus léger et rapide (~2 Go), utile si tu utilises aussi la voix naturelle"
read -r -p "Ton choix [1/2] : " rep
if [ "$rep" = "2" ]; then MODEL="llama3.2:3b"; else MODEL="qwen2.5:7b"; fi

echo "==> Téléchargement de $MODEL (une seule fois)"
ollama pull "$MODEL"

echo "==> Petit test"
ollama run "$MODEL" "Réponds juste : bonjour !" || true

echo
echo "Terminé ! Dans le compagnon : clic droit → Discuter avec elle…"
echo "(si la fenêtre dit qu'Ollama est introuvable, clique sur « Réessayer »)"
