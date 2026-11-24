
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

**Windows 10/11 (beta):** [⬇️ Viki-Windows.zip](https://github.com/korhyu00/viki/releases/latest/download/Viki-Windows.zip)
— unzip it anywhere, then double-click `Viki.exe`. This version is still being tested: animated Live2D models
can fail on older graphics cards, and some Linux-only tools are hidden.

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
- **Shows you on screen**: ask "show me how to…" and she circles, underlines and points at what to click (you stay in control).
- **Understands your own words**: reminders, deadlines ("before the 10th"), notes — her AI picks the right feature, and asks before changing anything.
- **Remembers your files**: pick folders (notes, courses, PDFs) and ask "in my notes, …".
- **Keeps you safe**: right-click a file → "Is it safe?", Alt+E explains a terminal command before you run it, copied passwords are cleared.
- **Learn with her**: guided tours of apps, quizzes and study sheets from your own courses.
- **Cursor mode**: her own pointer with your character's face, and a wheel of actions around it.
- **Calm**: she stays focused on your request, and you choose what she tells you on her own.
- **Nothing to guess**: "✨ What I can do" shows everything as big cards with phrases to click, suggestions appear as you type, and "Did you mean…?" helps when she doesn't understand. A simple mode hides the technical parts for kids.
- **Handy card**: commands, code, links, addresses, parcels and dates she gives you come with Copy / Open / Map / Remind me buttons. Keep your favorite commands in a notebook.
- **For developers**: she offers to explain a command that fails in your terminal, writes your commit message, tells you which program uses a port, and watches a log file for errors.
- **Daily helpers**: pick up where you left off, quiet mode during calls, conversions of what you copy (°F, miles, time zones), ready-made texts (";adr").
- **Clean look**: rounded dark windows with the same buttons everywhere.

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

The code comments are in French: see [CONTRIBUTING.md](CONTRIBUTING.md) for an English map of the code.

## Support

Viki is free and always will be. If you like her and want to support my work, you can buy me a coffee on Ko-fi: https://ko-fi.com/korhyu 💜

## License

Viki is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License v3.0 or later](LICENSE).

---

**Français** — Viki est une compagne de bureau pour Linux : discussion avec une IA locale, traduction, correction,
rappels, création d'images et de musique, surveillance du PC. Tout tourne sur ton ordinateur. Télécharge l'AppImage
ci-dessus, rends-la exécutable et double-clique dessus. Viki est un logiciel libre (licence GPL-3.0 ou ultérieure).

Website: [korhyu.com](https://korhyu.com) · YouTube: [youtube.com/@korhyu](https://www.youtube.com/@korhyu)
