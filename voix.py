"""Voix et langues du compagnon.

- LANGUES : les langues de discussion (l'IA répond dans la langue, l'oreille l'écoute, une voix Piper la parle).
- Catalogue des voix Piper (voices.json officiel, téléchargé seulement quand on ouvre le catalogue).
- Réglages de voix : vitesse, hauteur, expressivité, pauses.
"""
import json
import sys
import re
import threading
import urllib.request
import wave
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QProgressBar, QPushButton, QVBoxLayout)

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# code : (nom affiché, nom en français pour l'IA, préfixe des voix Piper, phrase d'essai)
LANGUES = {
    "fr": ("Français", "français", "fr_", "Coucou ! Tu m'entends bien ?"),
    "en": ("English — anglais", "anglais", "en_", "Hi! Can you hear me well?"),
    "es": ("Español — espagnol", "espagnol", "es_", "¡Hola! ¿Me oyes bien?"),
    "de": ("Deutsch — allemand", "allemand", "de_", "Hallo! Hörst du mich gut?"),
    "it": ("Italiano — italien", "italien", "it_", "Ciao! Mi senti bene?"),
    "pt": ("Português — portugais", "portugais", "pt_", "Olá! Você me ouve bem?"),
    "nl": ("Nederlands — néerlandais", "néerlandais", "nl_", "Hallo! Hoor je me goed?"),
    "pl": ("Polski — polonais", "polonais", "pl_", "Cześć! Słyszysz mnie dobrze?"),
    "ru": ("Русский — russe", "russe", "ru_", "Привет! Ты меня хорошо слышишь?"),
    "uk": ("Українська — ukrainien", "ukrainien", "uk_", "Привіт! Ти мене добре чуєш?"),
    "tr": ("Türkçe — turc", "turc", "tr_", "Merhaba! Beni iyi duyuyor musun?"),
    "sv": ("Svenska — suédois", "suédois", "sv_", "Hej! Hör du mig bra?"),
    "ar": ("العربية — arabe", "arabe", "ar_", "مرحبا! هل تسمعني جيدا؟"),
    "zh": ("中文 — chinois", "chinois", "zh_", "你好！你听得清楚吗？"),
    "ja": ("日本語 — japonais", "japonais", "ja_", "こんにちは！よく聞こえる？"),
    "ko": ("한국어 — coréen", "coréen", "ko_", "안녕! 내 말 잘 들려?"),
    "ca": ("Català — catalan", "catalan", "ca_", "Hola! M'escoltes bé?"),
    "cs": ("Čeština — tchèque", "tchèque", "cs_", "Ahoj! Slyšíš mě dobře?"),
    "da": ("Dansk — danois", "danois", "da_", "Hej! Kan du høre mig godt?"),
    "el": ("Ελληνικά — grec", "grec", "el_", "Γεια! Με ακούς καλά;"),
    "fi": ("Suomi — finnois", "finnois", "fi_", "Hei! Kuuletko minua hyvin?"),
    "hu": ("Magyar — hongrois", "hongrois", "hu_", "Szia! Jól hallasz?"),
    "no": ("Norsk — norvégien", "norvégien", "no_", "Hei! Hører du meg godt?"),
    "ro": ("Română — roumain", "roumain", "ro_", "Salut! Mă auzi bine?"),
    "sk": ("Slovenčina — slovaque", "slovaque", "sk_", "Ahoj! Počuješ ma dobre?"),
    "sr": ("Српски — serbe", "serbe", "sr_", "Здраво! Чујеш ли ме добро?"),
    "vi": ("Tiếng Việt — vietnamien", "vietnamien", "vi_", "Xin chào! Bạn nghe rõ không?"),
    "hi": ("हिन्दी — hindi", "hindi", "hi_", "नमस्ते! क्या तुम मुझे ठीक से सुन रहे हो?"),
    "fa": ("فارسی — persan", "persan", "fa_", "سلام! صدای من را خوب می‌شنوی؟"),
    "sw": ("Kiswahili — swahili", "swahili", "sw_", "Habari! Unanisikia vizuri?"),
    "cy": ("Cymraeg — gallois", "gallois", "cy_", "Helo! Wyt ti'n fy nghlywed i'n iawn?"),
}
# voix proposée d'abord pour chaque langue (si elle existe encore dans le catalogue)
PREFEREES = {"fr": "fr_FR-siwis-medium", "en": "en_US-amy-medium", "es": "es_ES-sharvard-medium",
             "de": "de_DE-thorsten-medium", "it": "it_IT-paola-medium", "pt": "pt_BR-faber-medium"}

QUALITES = {"x_low": "très léger", "low": "léger", "medium": "normal", "high": "haute qualité"}


def practice_prompt(code):
    nom = LANGUES.get(code, LANGUES["en"])[1]
    return (f"Tu aides l'utilisateur à pratiquer le {nom}. Réponds TOUJOURS en {nom} simple (niveau A2-B1), "
            "en 1 à 3 phrases courtes et naturelles, puis pose une petite question pour continuer. "
            f"Si son message contient des fautes de {nom}, ajoute à la fin une correction courte en français "
            "entre crochets, par exemple : [Correction : on dit … et pas …]. "
            f"S'il écrit en français, aide-le à le dire en {nom}.")


def natural_prompt(code):
    nom = LANGUES.get(code, LANGUES["fr"])[1]
    return (f"Réponds toujours en {nom}, naturellement, même si l'utilisateur t'écrit en français. "
            "Garde la balise d'émotion au début, telle quelle.")


_FR_WORDS = set("je tu il elle on nous vous ils le la les un une des de du est suis es pas et que qui "
                "c'est moi toi ton ta mon ma tes mes avec pour dans sur au aux ce cette ça oui non "
                "bonjour coucou merci quoi tout très bien aussi mais j'ai t'es".split())
# mots qu'on ne croise presque jamais dans les autres langues
_FR_SURE = set("je j'ai suis est c'est pas moi toi avec oui ça coucou bonjour très nous vous ils elle "
               "aussi mais d'accord voilà parle rien encore déjà toujours chez être avoir veux peux fais "
               "maintenant quelque chose".split())


def looks_french(text):
    """Phrase toute faite en français (dans une autre langue, on garde la voix française pour elle)."""
    low = text.lower()
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", low)
    if not words:
        return False
    hits = sum(1 for w in words if w in _FR_WORDS)
    sure = (any(w in _FR_SURE for w in words) or "œ" in low
            or bool(re.search(r"\b(?:j|n|qu|c|t|s|m)'", low)))
    return sure and hits >= max(1, len(words) * 0.15)


_PIPER_OK = {}


def piper_compatible(model_path):
    """Le Piper intégré ne lit que les voix dont chaque phonème tient en un seul caractère
    (certaines voix récentes ont « aɪ » : Piper plante avec « is not a single codepoint »)."""
    j = Path(str(model_path) + ".json")
    try:
        key = (str(j), j.stat().st_mtime)
    except OSError:
        return False
    if key not in _PIPER_OK:
        try:
            ids = json.loads(j.read_text(encoding="utf-8")).get("phoneme_id_map", {})
            _PIPER_OK[key] = all(len(k) == 1 for k in ids)
        except Exception:
            _PIPER_OK[key] = True
        if not _PIPER_OK[key]:
            print(f"Voix ignorée (pas compatible avec Piper) : {Path(model_path).name}", file=sys.stderr)
    return _PIPER_OK[key]


def installed_voices(voice_dirs, code=None):
    """Voix Piper installées : liste de (stem, chemin). Filtrées par langue si code donné."""
    pre = LANGUES[code][2] if code in LANGUES else ""
    out, seen = [], set()
    for d in voice_dirs:
        d = Path(d)
        if not d.exists():
            continue
        for m in sorted(d.glob("*.onnx")):
            if m.stem in seen or not Path(str(m) + ".json").exists():
                continue
            if pre and not m.stem.startswith(pre):
                continue
            seen.add(m.stem)
            out.append((m.stem, str(m)))
    return out


def speakers_of(model_path):
    """Locuteurs d'un modèle à plusieurs voix : [(numéro, nom)] (vide si une seule voix)."""
    try:
        cfg = json.loads(Path(str(model_path) + ".json").read_text(encoding="utf-8"))
    except Exception:
        return []
    n = int(cfg.get("num_speakers", 1) or 1)
    if n <= 1:
        return []
    m = cfg.get("speaker_id_map") or {}
    if m:
        return sorted(((int(i), str(name)) for name, i in m.items()), key=lambda x: x[0])[:60]
    return [(i, f"voix {i + 1}") for i in range(min(n, 60))]


def voice_for(code, cfg, voice_dirs):
    """(chemin du modèle, numéro de locuteur) pour une langue, ou (None, -1)."""
    pref = (cfg.get("voix_langue") or {}).get(code) or {}
    inst = installed_voices(voice_dirs, code)
    path = next((p for s, p in inst if s == pref.get("voice")), None)
    if not path and inst:
        path = next((p for s, p in inst if s == PREFEREES.get(code)), inst[0][1])
        pref = {}
    return path, int(pref.get("speaker", -1)) if path else -1


def piper_args(cfg, pitch=1.0):
    """Options de Piper : vitesse, variation, pauses (la hauteur est appliquée après)."""
    speed = max(0.5, min(2.0, float(cfg.get("voix_vitesse", 1.0))))
    var = float(cfg.get("voix_variation", 0.667))
    pause = float(cfg.get("voix_pause", 0.2))
    return ["--length_scale", f"{(1 / speed) * pitch:.3f}", "--noise_scale", f"{var:.3f}",
            "--noise_w", f"{min(1.0, var * 1.2):.3f}", "--sentence_silence", f"{pause:.2f}"]


def pitch_shift(path, ratio):
    """Change la hauteur d'un .wav : on rééchantillonne (la durée a déjà été compensée par Piper)."""
    if abs(ratio - 1.0) < 0.01:
        return
    import numpy as np
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        data = w.readframes(params.nframes)
    if params.sampwidth != 2:
        return
    a = np.frombuffer(data, np.int16).astype(np.float32)
    ch = params.nchannels
    if ch > 1:
        a = a.reshape(-1, ch)[:, 0]
    n = int(len(a) / ratio)
    if n < 10:
        return
    out = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(params.framerate)
        w.writeframes(np.clip(out, -32768, 32767).astype(np.int16).tobytes())


# ================================================================ catalogue
class _Sig(QObject):
    done = pyqtSignal(object, object)
    prog = pyqtSignal(int, str)


def load_catalog(cache_file, refresh=False):
    cache = Path(cache_file)
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    req = urllib.request.Request(HF + "voices.json", headers={"User-Agent": "Viki"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.load(r)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


class VoiceCatalog(QDialog):
    """Toutes les voix Piper, par langue : télécharger, choisir, essayer, supprimer."""

    def __init__(self, comp, voices_dir, voice_dirs, code=None):
        super().__init__(None)
        self.comp, self.dest, self.voice_dirs = comp, Path(voices_dir), voice_dirs
        self.setWindowTitle("Catalogue des voix")
        self.resize(680, 560)
        self.setStyleSheet("QDialog { background: #fbf6f9; } QPushButton { padding: 5px 12px; border-radius: 8px;"
                           " border: 1px solid #e3c3d2; background: white; } QPushButton#principal {"
                           " background: #d0457a; color: white; border: none; font-weight: bold; }")
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, res: fn(res))
        self.sig.prog.connect(self._on_prog)
        v = QVBoxLayout(self)
        t = QLabel("🗣️  Catalogue des voix (Piper, gratuites, sur ton PC)")
        t.setStyleSheet("font-size: 17px; font-weight: bold; color: #3d2733;")
        v.addWidget(t)
        a = QLabel("Choisis une langue, télécharge une voix (20 à 120 Mo), puis « Utiliser ». "
                   "Internet ne sert qu'au téléchargement.")
        a.setWordWrap(True)
        a.setStyleSheet("color: #8d7482;")
        v.addWidget(a)
        r = QHBoxLayout()
        self.lang = QComboBox()
        for c, (nom, *_rest) in LANGUES.items():
            self.lang.addItem(nom, c)
        self.lang.addItem("Toutes les langues", "")
        self.lang.setCurrentIndex(max(0, self.lang.findData(code or comp.cfg.get("langue", "fr"))))
        self.lang.currentIndexChanged.connect(self.fill)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Chercher un nom…")
        self.search.textChanged.connect(self.fill)
        r.addWidget(self.lang)
        r.addWidget(self.search, 1)
        v.addLayout(r)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._sel)
        v.addWidget(self.list, 1)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        v.addWidget(self.bar)
        self.status = QLabel("Chargement du catalogue…")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        row = QHBoxLayout()
        self.b_dl = QPushButton("Télécharger")
        self.b_dl.setObjectName("principal")
        self.b_use = QPushButton("Utiliser")
        self.b_try = QPushButton("▶ Essayer")
        self.b_del = QPushButton("Supprimer")
        for b, fn in ((self.b_dl, self.download), (self.b_use, self.use), (self.b_try, self.try_voice),
                      (self.b_del, self.delete)):
            b.clicked.connect(fn)
            b.setEnabled(False)
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        row.addWidget(close)
        v.addLayout(row)
        self.catalog = {}
        threading.Thread(target=lambda: self.sig.done.emit(self._loaded, self._fetch()), daemon=True).start()

    def _fetch(self):
        try:
            return load_catalog(self.dest / "voices.json")
        except Exception as e:
            return e

    def _loaded(self, res):
        if isinstance(res, Exception):
            self.status.setText(f"Impossible de charger le catalogue (internet ?) : {res}")
            return
        self.catalog = res
        self.fill()

    def _installed(self):
        return {s for s, _ in installed_voices(self.voice_dirs)}

    def fill(self, *_):
        self.list.clear()
        code = self.lang.currentData()
        pre = LANGUES[code][2] if code else ""
        q = self.search.text().strip().lower()
        inst = self._installed()
        order = {"high": 0, "medium": 1, "low": 2, "x_low": 3}
        items = sorted(((k, v) for k, v in self.catalog.items() if k.startswith(pre)),
                       key=lambda kv: (kv[0] not in inst, kv[1]["language"]["code"], kv[1]["name"],
                                       order.get(kv[1]["quality"], 9)))
        for key, info in items:
            if q and q not in key.lower():
                continue
            size = sum(f["size_bytes"] for p, f in info["files"].items() if p.endswith(".onnx")) / 1e6
            lg = info["language"]
            n = info.get("num_speakers", 1)
            txt = (f"{'✅ ' if key in inst else ''}{info['name'].replace('_', ' ').title()}  —  "
                   f"{lg.get('name_native', '')} ({lg.get('country_english', '')})  —  "
                   f"{QUALITES.get(info['quality'], info['quality'])}"
                   f"{f'  —  {n} voix' if n > 1 else ''}  —  {size:.0f} Mo")
            it = QListWidgetItem(txt)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(it)
        self.status.setText(f"{self.list.count()} voix. ✅ = déjà installée."
                            if self.list.count() else "Aucune voix pour cette langue dans le catalogue.")
        self._sel()

    def _key(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _sel(self, *_):
        k = self._key()
        inst = k in self._installed() if k else False
        self.b_dl.setEnabled(bool(k) and not inst)
        for b in (self.b_use, self.b_try, self.b_del):
            b.setEnabled(inst)

    def _on_prog(self, pct, txt):
        self.bar.setVisible(pct >= 0)
        self.bar.setValue(max(0, pct))
        self.status.setText(txt)

    def download(self):
        k = self._key()
        if not k:
            return
        files = [p for p in self.catalog[k]["files"] if p.endswith((".onnx", ".onnx.json"))]
        total = sum(self.catalog[k]["files"][p]["size_bytes"] for p in files) or 1
        self.b_dl.setEnabled(False)

        def work():
            got = 0
            try:
                self.dest.mkdir(parents=True, exist_ok=True)
                for p in files:
                    tmp = self.dest / (Path(p).name + ".part")
                    req = urllib.request.Request(HF + p, headers={"User-Agent": "Viki"})
                    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                        while True:
                            b = r.read(1 << 16)
                            if not b:
                                break
                            f.write(b)
                            got += len(b)
                            self.sig.prog.emit(int(got * 100 / total), f"Téléchargement… {got / 1e6:.0f} Mo")
                    tmp.rename(self.dest / Path(p).name)
                return ""
            except Exception as e:
                return str(e)

        def then(err):
            self.sig.prog.emit(-1, f"❌ Échec : {err}" if err else "✅ Voix installée ! Clique sur « Utiliser ».")
            self.fill()
        threading.Thread(target=lambda: self.sig.done.emit(then, work()), daemon=True).start()

    def use(self):
        k = self._key()
        if k:
            code = next((c for c, v in LANGUES.items() if k.startswith(v[2])), "fr")
            self.comp.set_lang_voice(code, k, -1)
            self.status.setText(f"✅ Elle utilise maintenant cette voix pour le {LANGUES[code][1]}. "
                                "Si elle a plusieurs voix, choisis-la dans Réglages → Voix.")

    def try_voice(self):
        k = self._key()
        if k:
            code = next((c for c, v in LANGUES.items() if k.startswith(v[2])), "fr")
            self.comp.try_voice(k, LANGUES[code][3])

    def delete(self):
        k = self._key()
        if not k:
            return
        for suf in (".onnx", ".onnx.json"):
            try:
                (self.dest / (k + suf)).unlink()
            except OSError:
                pass
        self.status.setText("Voix supprimée.")
        self.fill()
