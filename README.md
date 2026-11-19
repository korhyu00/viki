
# Viki — your desktop companion

Viki is an assistant that lives on your Linux desktop. She chats, translates, proofreads, reminds you of your
appointments, creates images and music, and keeps an eye on your PC. **Everything runs on your computer**: no account,
no ads, and the internet is only used when you ask for it.

> **Beta 0.9** — there may still be bugs. Tell me what goes wrong in the *Issues* tab.

## Download

**[⬇️ Download Viki (Linux, AppImage)](https://github.com/korhyu00/viki/releases/latest/download/Viki-x86_64.AppImage)**

Also available as a **Flatpak**, from Viki's own repository (she then shows up in Discover, GNOME Software or
Bazaar and updates there):

```
flatpak install --user https://korhyu00.github.io/viki-flatpak/viki.flatpakref
```

## Run

1. Right-click the downloaded file → **Properties** → **Permissions** → tick "Allow executing file as program".
   Or, in a terminal: `chmod +x Viki-x86_64.AppImage`
2. Double-click it.

Nothing to install. To remove Viki, just delete the file.

## What she can do

- **Chat** with an AI that stays on your PC (through Ollama) — or an online AI if you prefer.
- **Translate, proofread, summarize, write an email** from the text you copied.
- **Reminders, timers, focus mode.**
- **Create** images and music locally.
- **Around me**: restaurants, cafés, pharmacies on a map (OpenStreetMap).
- **Your PC**: live resource usage, disk health check, Tor for privacy.
- **Customizable**: character, voice, and round shortcut buttons next to her.

## Requirements

- 64-bit Linux (mostly tested on KDE Plasma).
- To chat locally: [Ollama](https://ollama.com) and, ideally, a graphics card with 6 GB or more.
  Viki guides you through the installation.

## Languages

The interface is available in French, English, Spanish, Russian, Chinese, Japanese and Hindi.

## Privacy

Viki never sends anything to the internet on her own. Your conversations, memories and settings stay in
`~/.config/viki` on your computer.

## Run from source

The code is in this repository. You need Python 3.10+ and PyQt6:

```
git clone https://github.com/korhyu00/viki && cd viki
python3 compagnon.py
```

`install.sh` sets everything up on Arch-based distributions (PyQt6, Piper voice, menu entry).
Voices, AI models and image/music engines are downloaded by Viki herself when you ask for them.

## License

Viki is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License v3.0 or later](LICENSE).

---

**Français** — Viki est une compagne de bureau pour Linux : discussion avec une IA locale, traduction, correction,
rappels, création d'images et de musique, surveillance du PC. Tout tourne sur ton ordinateur. Télécharge l'AppImage
ci-dessus, rends-la exécutable et double-clique dessus. Viki est un logiciel libre (licence GPL-3.0 ou ultérieure).

Website: [korhyu.com](https://korhyu.com) · YouTube: [youtube.com/@korhyu](https://www.youtube.com/@korhyu)
