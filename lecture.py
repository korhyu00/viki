"""Mode lecture : elle lit des livres à voix haute (EPUB, PDF, TXT, Markdown, DOCX, ODT, FB2, HTML).

- Les chapitres viennent de la table des matières de l'EPUB (ou des titres « Chapitre … » sinon).
- La phrase lue est surlignée ; double-clic sur une phrase = lire à partir de là.
- La phrase suivante est préparée pendant qu'elle lit (pas de blanc entre les phrases).
- La position est retenue pour chaque livre : on reprend là où on s'était arrêté.
"""
import html
import json
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from posixpath import dirname as _pdir, join as _pjoin, normpath as _pnorm
from urllib.parse import unquote

LIVRE_EXT = (".epub", ".pdf", ".txt", ".md", ".docx", ".odt", ".fb2", ".html", ".htm")
STATE_FILE = None          # fixé par compagnon.py : ~/.config/viki/lecture.json


# ------------------------------------------------------------------ découpage
_ABBR = (r"(?<!\bM\.)(?<!\bMme\.)(?<!\bMlle\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bp\.)(?<!\bcf\.)"
         r"(?<!\bex\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bvol\.)(?<!\bch\.)")


def sentences(par, maxlen=320):
    """Phrases d'un paragraphe (les très longues sont coupées sur une virgule ou un point-virgule)."""
    par = re.sub(r"\s+", " ", par).strip()
    if not par:
        return []
    raw = re.split(r"(?<=[.!?…])" + _ABBR + r"\s+(?=[«\"“—–\-A-ZÀ-ÖØ-Ý0-9(])", par)
    out = []
    for s in raw:
        while len(s) > maxlen:
            cut = max(s.rfind(";", 0, maxlen), s.rfind(":", 0, maxlen), s.rfind(",", 0, maxlen))
            if cut < 60:
                cut = s.rfind(" ", 0, maxlen)
            if cut < 40:
                cut = maxlen
            out.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            out.append(s)
    return out


def _html_paragraphs(xml):
    xml = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", xml)
    xml = re.sub(r"(?i)<br\s*/?>", " ", xml)
    xml = re.sub(r"(?i)</(p|h[1-6]|div|li|blockquote|section|tr|dd|dt|title)>", "\n\n", xml)
    txt = html.unescape(re.sub(r"<[^>]+>", "", xml)).replace("\xa0", " ")
    return [re.sub(r"[ \t\r\n]+", " ", p).strip() for p in re.split(r"\n\s*\n", txt)
            if re.sub(r"\s+", "", p)]


def _first_heading(xml):
    m = re.search(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", xml)
    if m:
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
        return t[:80]
    return ""


CHAP_RE = re.compile(r"^\s*(chapitre|chapter|partie|part|livre|prologue|épilogue|epilogue|"
                     r"[IVXLC]{1,6}\.?$|\d{1,3}\.?$|#{1,3}\s)", re.I)


def _split_chapters(paras, title="Texte"):
    """Texte sans structure : on coupe sur les titres « Chapitre … », sinon par blocs."""
    chaps, cur, name = [], [], title
    for p in paras:
        if len(p) < 70 and CHAP_RE.match(p) and cur:
            chaps.append((name, cur))
            cur, name = [], p.lstrip("# ").strip()[:80]
        elif len(p) < 70 and CHAP_RE.match(p) and not cur:
            name = p.lstrip("# ").strip()[:80]
        else:
            cur.append(p.lstrip("# ").strip() if p.startswith("#") else p)
    if cur:
        chaps.append((name, cur))
    if len(chaps) == 1 and len(chaps[0][1]) > 120:          # pas de chapitres : blocs de 60 paragraphes
        ps = chaps[0][1]
        chaps = [(f"Partie {i // 60 + 1}", ps[i:i + 60]) for i in range(0, len(ps), 60)]
    return chaps or [(title, ["(livre vide)"])]


# ------------------------------------------------------------------ formats
def _epub(path):
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    cont = z.read("META-INF/container.xml").decode("utf-8", "ignore")
    opf_path = re.search(r'full-path="([^"]+)"', cont).group(1)
    opf = z.read(opf_path).decode("utf-8", "ignore")
    base = _pdir(opf_path)

    def full(href):
        return _pnorm(_pjoin(base, unquote(href.split("#")[0]))) if base else _pnorm(unquote(href.split("#")[0]))
    title = re.search(r"(?is)<dc:title[^>]*>(.*?)</dc:title>", opf)
    author = re.search(r"(?is)<dc:creator[^>]*>(.*?)</dc:creator>", opf)
    manifest = {}
    for m in re.finditer(r"(?is)<item\b([^>]*)/?>", opf):
        a = m.group(1)
        i = re.search(r'\bid="([^"]+)"', a)
        h = re.search(r'\bhref="([^"]+)"', a)
        if i and h:
            manifest[i.group(1)] = (full(h.group(1)), a)
    spine = [manifest[i][0] for i in re.findall(r'(?is)<itemref\b[^>]*idref="([^"]+)"', opf) if i in manifest]
    # titres de la table des matières (EPUB 3 nav, sinon EPUB 2 toc.ncx)
    toc = {}
    nav = next((h for h, a in manifest.values() if 'properties="nav"' in a or "properties='nav'" in a), None)
    ncx = next((h for h, a in manifest.values() if "ncx" in a), None)
    try:
        if nav and nav in names:
            x = z.read(nav).decode("utf-8", "ignore")
            nb = _pdir(nav)
            for h, t in re.findall(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', x):
                f = _pnorm(_pjoin(nb, unquote(h.split("#")[0])))
                toc.setdefault(f, re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t))).strip())
        elif ncx and ncx in names:
            x = z.read(ncx).decode("utf-8", "ignore")
            nb = _pdir(ncx)
            for t, h in re.findall(r'(?is)<navLabel>\s*<text>(.*?)</text>.*?<content[^>]*src="([^"]+)"', x):
                f = _pnorm(_pjoin(nb, unquote(h.split("#")[0])))
                toc.setdefault(f, html.unescape(t).strip())
    except Exception:
        pass
    chaps = []
    for n, f in enumerate(spine):
        if f not in names:
            continue
        x = z.read(f).decode("utf-8", "ignore")
        paras = _html_paragraphs(x)
        if sum(len(p) for p in paras) < 40:          # couverture, page vide
            continue
        name = toc.get(f) or _first_heading(x) or f"Partie {len(chaps) + 1}"
        if paras and paras[0].strip().lower() == name.strip().lower():
            paras = paras[1:] or paras
        chaps.append((name[:80], paras))
    clean = (lambda m: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip() if m else "")
    return clean(title) or Path(path).stem, clean(author), chaps


def _pdf(path):
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("il faut « pdftotext » pour lire les PDF (paquet poppler)")
    r = subprocess.run([exe, "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=180)
    pages = r.stdout.decode("utf-8", "ignore").split("\f")
    paras, chaps, cur, name = [], [], [], "Début"
    for n, page in enumerate(pages, 1):
        lines = [l.rstrip() for l in page.splitlines()]
        lines = [l for l in lines if not re.fullmatch(r"\s*(page\s*)?\d{1,4}\s*", l, re.I)]   # numéros de page
        txt = "\n".join(lines)
        txt = re.sub(r"(\w)-\n(\w)", r"\1\2", txt)          # mots coupés en fin de ligne
        for p in re.split(r"\n\s*\n", txt):
            lines = [x.strip() for x in p.splitlines() if x.strip()]
            if len(lines) > 1 and len(lines[0]) < 60 and CHAP_RE.match(lines[0]):   # titre collé au texte
                paras.append(lines.pop(0))
            p = re.sub(r"\s*\n\s*", " ", "\n".join(lines)).strip()
            if p:
                paras.append(p)
    return Path(path).stem, "", _split_chapters(paras, "Début")


def _fb2(path):
    x = Path(path).read_text(encoding="utf-8", errors="ignore")
    title = re.search(r"(?is)<book-title>(.*?)</book-title>", x)
    chaps = []
    for sec in re.findall(r"(?is)<section\b[^>]*>(.*?)</section>", x):
        t = re.search(r"(?is)<title>(.*?)</title>", sec)
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t.group(1))).strip() if t else f"Partie {len(chaps) + 1}"
        body = re.sub(r"(?is)<title>.*?</title>", "", sec)
        paras = _html_paragraphs(body)
        if paras:
            chaps.append((name[:80], paras))
    return (title.group(1).strip() if title else Path(path).stem), "", chaps


def load_book(path):
    """-> {"titre", "auteur", "chapitres": [(titre, [paragraphes])]}"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".epub":
        title, author, chaps = _epub(p)
    elif ext == ".pdf":
        title, author, chaps = _pdf(p)
    elif ext == ".fb2":
        title, author, chaps = _fb2(p)
    elif ext in (".docx", ".odt"):
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml" if ext == ".docx" else "content.xml").decode("utf-8", "ignore")
        xml = re.sub(r"</(w:p|text:p|text:h)>", "\n\n", xml)
        title, author = p.stem, ""
        chaps = _split_chapters(_html_paragraphs(xml), p.stem)
    elif ext in (".html", ".htm"):
        x = p.read_text(encoding="utf-8", errors="ignore")
        title, author, chaps = p.stem, "", _split_chapters(_html_paragraphs(x), p.stem)
    else:
        x = p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        paras = [re.sub(r"\s*\n\s*", " ", b).strip() for b in re.split(r"\n\s*\n", x) if b.strip()]
        if len(paras) < 3:                            # une ligne = un paragraphe
            paras = [l.strip() for l in x.splitlines() if l.strip()]
        title, author, chaps = p.stem, "", _split_chapters(paras, p.stem)
    chaps = [(t, ps) for t, ps in chaps if ps]
    if not chaps:
        raise RuntimeError("je n'ai trouvé aucun texte dans ce livre (PDF scanné en images ? livre protégé ?)")
    return {"titre": title, "auteur": author, "chapitres": chaps}


def _duree(words):
    m = max(1, round(words / 160))                 # ~160 mots par minute
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


# ------------------------------------------------------------------ position et bibliothèque
def load_state():
    try:
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {"livres": {}, "dernier": ""}


def save_state(s):
    try:
        Path(STATE_FILE).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def recent_books(n=12):
    s = load_state()
    items = [(p, d) for p, d in s.get("livres", {}).items() if Path(p).exists()]
    return sorted(items, key=lambda x: -x[1].get("date", 0))[:n]


# ------------------------------------------------------------------ fenêtre de lecture
def make_window(comp):
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
    from PyQt6.QtGui import QColor, QTextCursor, QTextCharFormat, QFont
    from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMenu,
                                 QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget)

    class Bridge(QObject):
        loaded = pyqtSignal(object)

    class Reader(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.comp = comp
            self.book = None
            self.path = ""
            self.chap = 0
            self.idx = 0                  # phrase dans le chapitre
            self.sents = []               # [(texte, début, fin, n° paragraphe)]
            self.playing = False
            self.proc = None
            self.cache = {}               # (chap, idx) -> (fichier, enveloppe) ; "" = échec
            self.want = threading.Event()
            self.gen = 0                  # change quand on saute ailleurs : le préparateur repart
            self.stop_at = 0.0            # minuterie de sommeil
            self.stop_end_chapter = False
            self.lock = threading.Lock()
            self.bridge = Bridge()
            self.bridge.loaded.connect(self._loaded)
            self.setWindowTitle("📖 Mode lecture — " + comp.char.get("name", "Viki"))
            self.resize(980, 680)
            self.setStyleSheet("QWidget { background: #fffafc; color: #3d2733; font-size: 13px; }"
                               "QPushButton { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; "
                               "padding: 6px 12px; } QPushButton:hover { background: #fde7ef; }"
                               "QPushButton#play { background: #d6457f; color: white; border: none; "
                               "font-weight: bold; min-width: 110px; }"
                               "QListWidget { background: #fff; border: 1px solid #f1dfe8; border-radius: 10px; }"
                               "QListWidget::item:selected { background: #fde7ef; color: #b0336a; }"
                               "QTextEdit { background: #fff; border: 1px solid #f1dfe8; border-radius: 10px; "
                               "padding: 18px; }"
                               "QComboBox { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; "
                               "padding: 4px 8px; }")
            lay = QVBoxLayout(self)
            top = QHBoxLayout()
            self.title = QLabel("<b>Aucun livre ouvert</b>")
            top.addWidget(self.title, 1)
            self.lib_btn = QPushButton("📚 Mes livres")
            self.lib_btn.clicked.connect(self._library_menu)
            top.addWidget(self.lib_btn)
            ob = QPushButton("📂 Ouvrir un livre…")
            ob.clicked.connect(lambda: self.open_book())
            top.addWidget(ob)
            lay.addLayout(top)
            sp = QSplitter()
            self.toc = QListWidget()
            self.toc.setMaximumWidth(260)
            self.toc.currentRowChanged.connect(self._toc_clicked)
            self.text = QTextEdit()
            self.text.setReadOnly(True)
            self._set_size(float(comp.cfg.get("lecture_taille", 14)))
            self.text.viewport().installEventFilter(self)
            sp.addWidget(self.toc)
            sp.addWidget(self.text)
            sp.setSizes([220, 760])
            lay.addWidget(sp, 1)
            bar = QHBoxLayout()
            for lab, tip, fn in (("⏮", "Chapitre précédent", lambda: self.goto_chapter(self.chap - 1)),
                                 ("⏪", "Phrase précédente", lambda: self.jump(-1)),):
                b = QPushButton(lab)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                bar.addWidget(b)
            self.play_btn = QPushButton("▶  Lire")
            self.play_btn.setObjectName("play")
            self.play_btn.clicked.connect(self.toggle)
            bar.addWidget(self.play_btn)
            for lab, tip, fn in (("⏩", "Phrase suivante", lambda: self.jump(1)),
                                 ("⏭", "Chapitre suivant", lambda: self.goto_chapter(self.chap + 1))):
                b = QPushButton(lab)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                bar.addWidget(b)
            bar.addSpacing(12)
            self.speed = QComboBox()
            for lab, v in (("Lente", 0.85), ("Normale", 1.0), ("Un peu rapide", 1.15), ("Rapide", 1.3),
                           ("Très rapide", 1.5)):
                self.speed.addItem("Vitesse : " + lab, v)
            cur = float(comp.cfg.get("lecture_vitesse", 1.0))
            self.speed.setCurrentIndex(min(range(self.speed.count()),
                                           key=lambda i: abs(self.speed.itemData(i) - cur)))
            self.speed.currentIndexChanged.connect(self._speed_changed)
            bar.addWidget(self.speed)
            self.voice = QComboBox()
            self.voice.addItem("Voix Piper (rapide)", "piper")
            if comp.natural_ready or comp.cfg.get("voice_engine") in ("naturelle", "legere"):
                self.voice.addItem("Voix légère" if comp.cfg.get("voice_engine") == "legere"
                                   else "Voix naturelle (lourde)", "naturelle")
            self.voice.setCurrentIndex(max(0, self.voice.findData(comp.cfg.get("lecture_voix", "piper"))))
            self.voice.currentIndexChanged.connect(self._voice_changed)
            bar.addWidget(self.voice)
            self.sleep = QComboBox()
            for lab, v in (("Sans minuterie", 0), ("Arrêt dans 15 min", 15), ("Arrêt dans 30 min", 30),
                           ("Arrêt dans 1 h", 60), ("À la fin du chapitre", -1)):
                self.sleep.addItem("🌙 " + lab, v)
            self.sleep.currentIndexChanged.connect(self._sleep_changed)
            bar.addWidget(self.sleep)
            for lab, d in (("A−", -1), ("A+", 1)):
                b = QPushButton(lab)
                b.setToolTip("Taille du texte")
                b.clicked.connect(lambda _=False, dd=d: self._font(dd))
                bar.addWidget(b)
            bar.addStretch(1)
            self.status = QLabel("")
            self.status.setStyleSheet("color: #8d7482;")
            bar.addWidget(self.status)
            lay.addLayout(bar)
            self.tick = QTimer(self)
            self.tick.timeout.connect(self._tick)
            self.tick.start(80)
            threading.Thread(target=self._prepare_loop, daemon=True).start()
            self.text.setPlainText("Ouvre un livre (EPUB, PDF, TXT, DOCX, ODT, FB2…) ou choisis-en un dans "
                                   "« Mes livres ».\n\nPendant la lecture : double-clique sur une phrase pour "
                                   "lire à partir de là. Ta position est retenue pour chaque livre.")

        # ---------- livres
        def open_book(self, path=None, autoplay=False):
            if not path:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Choisir un livre", str(Path.home()),
                    "Livres (*.epub *.pdf *.txt *.md *.docx *.odt *.fb2 *.html *.htm);;Tous les fichiers (*)")
                if not path:
                    return
            self.pause()
            self.status.setText("Ouverture du livre…")
            self.title.setText(f"<b>{html.escape(Path(path).stem)}</b>")

            def work():
                try:
                    return path, load_book(path), autoplay
                except Exception as e:
                    return path, e, autoplay
            threading.Thread(target=lambda: self.bridge.loaded.emit(work()), daemon=True).start()

        def _loaded(self, res):
            path, book, autoplay = res
            if isinstance(book, Exception):
                self.status.setText("")
                self.comp.say(f"Je n'arrive pas à ouvrir ce livre : {str(book)[:120]}")
                return
            self.book, self.path = book, str(Path(path).resolve())
            st = load_state()
            pos = st.get("livres", {}).get(self.path, {})
            n_words = sum(len(p.split()) for _, ps in book["chapitres"] for p in ps)
            self.title.setText(f"<b>{html.escape(book['titre'])}</b>"
                               + (f" — {html.escape(book['auteur'])}" if book["auteur"] else "")
                               + f"  <span style='color:#9a8290'>({_duree(n_words)} d'écoute environ)</span>")
            self.toc.blockSignals(True)
            self.toc.clear()
            for t, _ in book["chapitres"]:
                self.toc.addItem(t)
            self.toc.blockSignals(False)
            self.goto_chapter(min(int(pos.get("chap", 0)), len(book["chapitres"]) - 1), int(pos.get("idx", 0)),
                              play=False)
            self._save()
            if pos:
                self.comp.say(f"On reprend « {book['titre'][:60]} » là où on s'était arrêtés.")
            else:
                self.comp.say(f"« {book['titre'][:60]} » ! Clique sur Lire quand tu es prêt.")
            if autoplay:
                QTimer.singleShot(1500, self.play)

        def _library_menu(self):
            m = QMenu(self)
            books = recent_books()
            if not books:
                a = m.addAction("(aucun livre pour l'instant)")
                a.setEnabled(False)
            for p, d in books:
                pc = int(100 * d.get("progres", 0))
                m.addAction(f"{d.get('titre', Path(p).stem)[:50]}  —  {pc} %",
                            lambda pp=p: self.open_book(pp))
            m.addSeparator()
            m.addAction("📂 Ouvrir un livre…", lambda: self.open_book())
            m.exec(self.lib_btn.mapToGlobal(self.lib_btn.rect().bottomLeft()))

        def _save(self):
            if not self.book:
                return
            st = load_state()
            total = sum(len(ps) for _, ps in self.book["chapitres"]) or 1
            done = sum(len(ps) for _, ps in self.book["chapitres"][:self.chap])
            par = self.sents[self.idx][3] if self.sents and self.idx < len(self.sents) else 0
            st.setdefault("livres", {})[self.path] = {
                "titre": self.book["titre"], "chap": self.chap, "idx": self.idx, "date": time.time(),
                "progres": round((done + par) / total, 4)}
            st["dernier"] = self.path
            save_state(st)

        # ---------- navigation
        def goto_chapter(self, c, idx=0, play=None):
            if not self.book:
                return
            if not 0 <= c < len(self.book["chapitres"]):
                if c >= len(self.book["chapitres"]):
                    self.pause()
                    self.comp.say("Et c'est la fin du livre ! Il t'a plu ?")
                return
            was = self.playing if play is None else play
            self.pause()
            self.chap = c
            title, paras = self.book["chapitres"][c]
            text, self.sents = "", []
            for pi, p in enumerate(paras):
                if text:
                    text += "\n\n"
                pos = 0
                for s in sentences(p):
                    k = p.find(s[:20], pos)
                    k = pos if k < 0 else k
                    self.sents.append((s, len(text) + k, len(text) + k + len(s), pi))
                    pos = k + len(s)
                text += p
            self.text.setPlainText(text)
            self.toc.blockSignals(True)
            self.toc.setCurrentRow(c)
            self.toc.blockSignals(False)
            self.idx = max(0, min(idx, len(self.sents) - 1))
            self.cache = {}
            self.gen += 1
            self._highlight()
            if was:
                self.play()

        def _toc_clicked(self, row):
            if row >= 0 and row != self.chap:
                self.goto_chapter(row)

        def jump(self, d):
            if not self.sents:
                return
            was = self.playing
            self.pause()
            n = self.idx + d
            if n < 0:
                return self.goto_chapter(self.chap - 1, 10 ** 6, play=was)
            if n >= len(self.sents):
                return self.goto_chapter(self.chap + 1, 0, play=was)
            self.idx = n
            self.gen += 1
            self._highlight()
            if was:
                self.play()

        def eventFilter(self, obj, ev):
            from PyQt6.QtCore import QEvent
            if ev.type() == QEvent.Type.MouseButtonDblClick and self.sents:
                pos = self.text.cursorForPosition(ev.position().toPoint()).position()
                i = next((k for k, s in enumerate(self.sents) if s[1] <= pos <= s[2]), None)
                if i is None:
                    i = min(range(len(self.sents)), key=lambda k: abs(self.sents[k][1] - pos))
                self.pause()
                self.idx = i
                self.gen += 1
                self._highlight()
                self.play()
                return True
            return False

        def _highlight(self):
            if not self.sents:
                return
            _, a, b, _ = self.sents[self.idx]
            sel = QTextEdit.ExtraSelection()
            cur = self.text.textCursor()
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#fde0ec"))
            fmt.setForeground(QColor("#8a1f4f"))
            sel.cursor = cur
            sel.format = fmt
            self.text.setExtraSelections([sel])
            c2 = self.text.textCursor()
            c2.setPosition(a)
            self.text.setTextCursor(c2)
            self.text.ensureCursorVisible()
            nch = len(self.book["chapitres"]) if self.book else 0
            self.status.setText(f"Chapitre {self.chap + 1}/{nch} · phrase {self.idx + 1}/{len(self.sents)}")

        # ---------- lecture
        def toggle(self):
            self.pause() if self.playing else self.play()

        def play(self):
            if not self.book or not self.sents:
                if not self.book:
                    self.open_book(autoplay=True)
                return
            self.playing = True
            self.comp.reader_active = True
            self.play_btn.setText("⏸  Pause")
            self.want.set()

        def pause(self):
            was = self.playing
            self.playing = False
            self.play_btn.setText("▶  Lire")
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            self.proc = None
            self.comp.lip_env = []
            self.comp.reader_active = False
            if was:
                self._save()

        def _speed_changed(self):
            self.comp.cfg["lecture_vitesse"] = self.speed.currentData()
            self.comp.save_cfg()
            self.cache = {}
            self.gen += 1

        def _voice_changed(self):
            self.comp.cfg["lecture_voix"] = self.voice.currentData()
            self.comp.save_cfg()
            self.cache = {}
            self.gen += 1

        def _sleep_changed(self):
            v = self.sleep.currentData()
            self.stop_end_chapter = v == -1
            self.stop_at = time.monotonic() + v * 60 if v > 0 else 0.0

        def _set_size(self, size):
            self.size = size
            self.text.setStyleSheet(f"QTextEdit {{ font-size: {size:.0f}pt; font-family: serif; background: #fff; "
                                    f"border: 1px solid #f1dfe8; border-radius: 10px; padding: 18px; }}")

        def _font(self, d):
            size = max(9.0, min(30.0, self.size + d))
            self._set_size(size)
            self.comp.cfg["lecture_taille"] = size
            self.comp.save_cfg()

        def _prepare_loop(self):
            """Prépare les 2 phrases suivantes pendant qu'elle lit."""
            n = 0
            while True:
                self.want.wait(0.5)
                self.want.clear()
                if not self.book:
                    continue
                gen, chap, base, sents = self.gen, self.chap, self.idx, self.sents
                for k in range(base, min(base + 3, len(sents))):
                    if gen != self.gen:
                        break
                    if (chap, k) in self.cache:
                        continue
                    n += 1
                    out = str(self.comp.tmpdir / f"livre{n % 12}.wav")
                    ok = self.comp.synth_reading(sents[k][0], out, self.speed.currentData(),
                                                 self.voice.currentData() == "naturelle")
                    env = None
                    if ok:
                        try:
                            env = self.comp.envelope(out)
                        except Exception:
                            env = None
                    if gen == self.gen:
                        self.cache[(chap, k)] = (out, env) if ok and env else ""

        def _tick(self):
            if not self.playing:
                return
            if self.proc and self.proc.poll() is None:
                return
            if self.proc is not None:                  # la phrase vient de finir
                self.proc = None
                for key in [k for k in self.cache if k[0] != self.chap or k[1] <= self.idx - 1]:
                    self.cache.pop(key, None)            # on garde la phrase en cours (pas re-calculée)
                if self.stop_at and time.monotonic() > self.stop_at:
                    self.pause()
                    self.sleep.setCurrentIndex(0)
                    self.comp.say("Je m'arrête là pour ce soir. Bonne nuit !")
                    return
                if self.idx + 1 >= len(self.sents):
                    if self.stop_end_chapter:
                        self.pause()
                        self.sleep.setCurrentIndex(0)
                        self.goto_chapter(self.chap + 1, play=False)
                        self._save()
                        return
                    self.goto_chapter(self.chap + 1, play=True)
                    return
                self.idx += 1
                self._highlight()
                if self.idx % 5 == 0:
                    self._save()
            item = self.cache.get((self.chap, self.idx))
            if item is None:
                self.want.set()
                self.status.setText("Je prépare la phrase…")
                return
            self.want.set()
            if item == "":                              # échec : on passe
                self.proc = _Done()
                return
            path, env = item
            try:
                self.proc = subprocess.Popen(self.comp._play_cmd(path), stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
                self.comp.lip_env, _ = env
                self.comp.lip_start = time.monotonic()
                self._highlight()
            except Exception:
                self.proc = _Done()

        def closeEvent(self, e):
            self.pause()
            self._save()
            super().closeEvent(e)

    class _Done:
        def poll(self):
            return 0

        def terminate(self):
            pass

    return Reader()
