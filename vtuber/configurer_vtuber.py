#!/usr/bin/env python3
"""Crée conf.yaml pour Open-LLM-VTuber, réglé en français et 100 % local :
Ollama (discussion) + faster-whisper (micro, français) + Piper (voix française).

Usage : python3 configurer_vtuber.py <dossier Open-LLM-VTuber> <modèle ollama> <chemin voix piper .onnx>
"""
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
model = sys.argv[2]
voice = sys.argv[3]

src = root / "config_templates" / "conf.default.yaml"
dst = root / "conf.yaml"
if dst.exists():
    shutil.copy(dst, root / "conf.yaml.sauvegarde")
s = src.read_text(encoding="utf-8")


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit(f"Le modèle de configuration a changé ({old!r} introuvable) : "
                 "copie-moi ce message, je mettrai le script à jour.")
    s = s.replace(old, new)


# --- personnalité en français
start = s.index("persona_prompt: |")
end = s.index("  #  =================== LLM Backend Settings")
persona = """persona_prompt: |
    Tu es Mao, une jeune femme adulte joyeuse, taquine et bienveillante, qui vit sur
    l'ordinateur de l'utilisateur comme compagne virtuelle. Tu parles toujours en
    français, de façon naturelle et chaleureuse, en phrases courtes (une à trois),
    sans émojis ni listes, car tes réponses sont lues à voix haute.

"""
s = s[:start] + persona + s[end:]
rep("human_name: 'Human'", "human_name: 'Toi'")

# --- discussion : Ollama local, sans recherche web
i = s.index("      ollama_llm:")
j = s.index("model: 'qwen2.5:latest'", i)
s = s[:j] + f"model: '{model}'" + s[j + len("model: 'qwen2.5:latest'"):]
rep("use_mcpp: True", "use_mcpp: False   # désactivé : la recherche web enverrait tes questions sur internet")

# --- micro : faster-whisper en français, sur le processeur
rep("asr_model: 'sherpa_onnx_asr'", "asr_model: 'faster_whisper'")
rep("model_path: 'large-v3-turbo'", "model_path: 'small'")
rep("language: 'en' # en, zh, or something else", "language: 'fr' # en, zh, or something else")
rep("device: 'auto' # cpu, cuda, or auto", "device: 'cpu' # cpu, cuda, or auto")

# --- voix : Piper français, local
rep("tts_model: 'edge_tts'", "tts_model: 'piper_tts'")
rep("model_path: 'models/piper/zh_CN-huayan-medium.onnx'", f"model_path: '{voice}'")

dst.write_text(s, encoding="utf-8")
print(f"    conf.yaml créé (modèle : {model}, micro : français, voix : Piper)")
