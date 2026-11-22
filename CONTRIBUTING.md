# Contributing to Viki

Thanks for your interest! 💜 Viki is made by a French solo developer, so **the comments, docstrings and
variable names in the code are in French**. This guide explains how the code is organised, in English,
so you can find your way around without reading French.

## Ground rules

- **Everything stays local.** Viki never sends anything to the internet unless the user explicitly asks
  (web search, news, online AI they configured…). Please keep it that way.
- **No NSFW content** (personas, models, prompts). Image and music generation keep their safety filters.
- **System changes go through a visible terminal**, started by a click from the user — never silently.
- Secrets (tokens, passwords) are stored in files with `chmod 600`, never in the main config.
- The user-facing source language is **French**. Translations live in `traductions.py` (see below).

## Running from source

```
git clone https://github.com/korhyu00/viki && cd viki
python3 compagnon.py
```

You need Python 3.10+ and PyQt6. Optional features (voice, speech recognition, local AI via Ollama,
image generation…) are installed by Viki herself when the user asks for them.

To test without a display: `QT_QPA_PLATFORM=offscreen python3 compagnon.py`.

## Building

- `construire_appimage.sh` — builds `Viki-x86_64.AppImage` (the main Linux release).
- `construire_windows.sh` — Windows build.
- The Flatpak is built from the AppImage by a separate kit (repo `korhyu00/viki-flatpak`).

## Translations (i18n)

- The interface is written in French and translated **at display time** by `i18n.py`: every window,
  menu, button, tooltip and Viki's own spoken phrases go through `i18n.tr()` / `i18n.tr_to()`.
- `traductions.py` is a generated table: `SOURCES` (French strings) and `T["en"]`, `T["es"]`, `T["ru"]`,
  `T["zh"]`, `T["ja"]`, `T["hi"]` — **same order, same length**.
- Placeholders: `{}` are filled in order; use `{0}`, `{1}`… in a translation if the word order changes.
- An unknown string simply stays in French, so a missing translation never breaks anything.
- To add a language: add it to `LANGS` in `i18n.py` and add a `T["xx"]` list.

## Map of the code

### Core
| File | What it does |
|---|---|
| `compagnon.py` | Main app (~21k lines): the desktop character window, animation, speech bubble, voice (`say()`), command understanding, chat with the AI, menus, most features glue. Start here. |
| `reglages.py` | The Settings window (all options, grouped by theme). |
| `demarrage.py` | First-launch wizard (3 screens: name and language, detected system with suggested settings, character). |
| `cerveau.py` | Viki's "brain": routine detection, not repeating herself, learning habits. |
| `apprentissage.py` | Habits she learns over time (stored locally in `apprentissage.json`). |
| `i18n.py`, `traductions.py` | Translation layer and table (see above). |
| `plateforme.py` | Windows compatibility layer. |
| `paquets.py` | Installing/updating packages on any Linux (Arch, Debian/Ubuntu, Fedora, openSUSE…). |
| `mise_a_jour.py` | Self-update from GitHub releases (AppImage, Flatpak bundle, Flatpak repo). `VERSION` lives here. |
| `rapport.py` | "Report a bug": builds an anonymised report and opens a pre-filled GitHub issue. |

### Voice, listening, AI
| File | What it does |
|---|---|
| `voix.py` | Voices and languages (Piper voices, espeak-ng fallback, default voice per language). |
| `voix_legere.py` | Local "light" voice server (Kyutai Pocket TTS). |
| `voix_naturelle.py` | Local "natural" voice server (Chatterbox Multilingual). |
| `ecoute.py` | Local speech recognition (faster-whisper). |
| `ia_api.py` | Optional online AI providers (OpenAI, Claude, Gemini, Mistral, Groq…). Local AI is Ollama, handled in `compagnon.py`. |
| `ajout_ia.py` | "Add any AI": drop a model file, Viki detects what it is for and installs it. |
| `modeles_fenetre.py` | "Models and mods" window: installed AI models sorted by use. |

### Appearance and characters
| File | What it does |
|---|---|
| `apparence.py` | Character outlines and colour customisation (hair, skin, eyes, clothes…). |
| `anime_perso.py` | Animated characters from GIF / WebP / APNG / video. |
| `live2d_rendu.py`, `spine_rendu.py` | Live2D and Spine character rendering. |
| `marionnette.py` | Puppet mode (head/arms/torso animated from a `rig.json`). |
| `visuel.py` | Visual quality (AI upscaling with Real-ESRGAN). |
| `galerie.py` | Character gallery. |
| `lieux.py` | Small animated scenes (home, pool, park…). |
| `themes.py`, `pomme.py`, `menu_style.py`, `fond_couleurs.py` | Window themes, "Apple-like" style, menu style, colours taken from the wallpaper. |
| `curseur.py` | Mouse position across the whole screen. |

### Features
| File | What it does |
|---|---|
| `extras.py` | Notes, timers, `.ics` calendar, PC monitoring and many small features. |
| `aujourdhui.py` | "Now" and "Today" panels. |
| `quotidien.py`, `vie.py`, `forme.py`, `fun.py` | Daily life: things learned, sport, jokes, meals, budget, mood, birthdays, health breaks, games, seasons. |
| `pratique.py` | Online calendars, reading web pages, selected text, screenshots. |
| `plus.py` | Clipboard history (RAM only), code snippets… |
| `astuces.py` | Tips and multilingual keywords. |
| `raccourcis.py`, `touches.py` | Short menu with search, shortcut bar, global keyboard shortcuts. |
| `liste.py`, `services_fenetre.py`, `media.py` | "My list" (series, films, music links), streaming services, music/news/image requests. |
| `suivi.py`, `actu_fenetre.py` | News and follows (manga, series, films), news window with images. |
| `atelier.py` | Image studio (local Stable Diffusion or online). |
| `dessin.py` | Drawing book: layers, symmetry, tablet pressure, .ora files, turn a drawing into a character. |
| `cuisine.py` | Cooking window: illustrated recipes, weekly meal planner, shopping list. |
| `lecture.py` | Reads books aloud (EPUB, PDF, TXT, DOCX, ODT…). |
| `manga.py`, `zone.py` | Manga/comic translation; translating any area of the screen. |
| `mails.py` | Mail notifications (IMAP). |
| `autour.py`, `ville.py` | Places nearby (OpenStreetMap), choosing your city for the weather. |
| `streamer.py` | Streamer mode (reads a Twitch chat). |
| `mods.py` | `.vikimod` mods (zip packages anyone can make and share). |

### PC, developer and privacy tools
| File | What it does |
|---|---|
| `gestionpc.py`, `diagnostic.py`, `outils.py` | PC dashboard, "why is my PC slow?", one-click backup, disk health, cleaning, folder tidying. |
| `securite.py`, `vieprivee.py`, `tor_viki.py` | Security check-up, privacy centre (ports, encrypted DNS…), optional Tor for Viki only. |
| `dev.py`, `devplus.py` | Developer tools: port watching, GitHub/GitLab, CI failures, pre-commit review, commit messages. |

### Scripts
`install*.sh` / `installer_*.sh` install optional parts (Ollama, voices, manga OCR, image engine, upscaling);
they always run in a visible terminal. `test_micro.sh`, `test_voix.sh` and `reparer_voix.sh` help debug audio.

## Reporting bugs and ideas

Use **Report a bug** inside Viki (it removes personal data and pre-fills the issue), or open an issue in
English or French — both are welcome. Pull requests are welcome too: keep them small and focused.

## License

By contributing, you agree that your contributions are licensed under **GPL-3.0-or-later**, like Viki.
