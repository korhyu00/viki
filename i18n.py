"""Traduction des menus et fenêtres de Viki (le texte source est en français).

Les traductions sont dans traductions.py : SOURCES (les textes français) et T[langue] (même ordre).
Rien à changer dans le reste du code : une fois installé, un filtre traduit chaque fenêtre, menu,
bouton, étiquette, bulle d'aide et liste au moment où ils s'affichent, et les textes changés ensuite
(setText, setToolTip…). Un texte inconnu reste en français.
"""
import re

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QListWidget, QMenu,
                             QTabWidget, QTextEdit, QPlainTextEdit, QWidget)

LANGS = [("fr", "Français"), ("en", "English"), ("es", "Español"), ("ru", "Русский"),
         ("zh", "中文"), ("ja", "日本語"), ("hi", "हिन्दी")]

_lang = "fr"
_map, _up, _tpl, _cache = {}, {}, [], {}
_PH = re.compile(r"\{\}|%s|%d")
_EDGE = re.compile(r"^([^\w«»(<{'\"]*)(.*?)(\s*)$", re.S)
_filter = None
_patched = False


def lang():
    return _lang


def _build(code):
    """Tables (exact, majuscules, modèles avec {}) d'une langue."""
    import traductions
    dst = traductions.T.get(code) or []
    mp, up, tpl = {}, {}, []
    for s, t in zip(traductions.SOURCES, dst):
        if not t:
            continue
        mp[s] = t
        if s.upper() != s:
            up.setdefault(s.upper(), t.upper())
        if _PH.search(s):
            parts = _PH.split(s)
            rx = "(.+?)".join(re.escape(p) for p in parts)
            tpl.append((len(s) - 2 * (len(parts) - 1), re.compile(rx, re.S), t))
    tpl.sort(key=lambda x: -x[0])                   # les modèles les plus précis d'abord
    return mp, up, tpl


def set_lang(code):
    """Charge les traductions de cette langue (fr = rien à traduire)."""
    global _lang, _map, _up, _tpl, _cache
    _cache = {}
    if code not in dict(LANGS) or code == "fr":
        _lang, _map, _up, _tpl = "fr", {}, {}, []
        return
    try:
        _map, _up, tpl = _build(code)
    except Exception:
        _lang, _map, _up, _tpl = "fr", {}, {}, []
        return
    _lang = code
    _tpl = [(rx, t) for _n, rx, t in tpl]


_autres = {}


def tr_to(text, code):
    """Traduit une phrase de Viki vers la langue parlée « code » (même si les menus sont dans une autre).
    Prudent : seuls les modèles avec assez de texte fixe servent, pour ne pas toucher aux réponses de l'IA."""
    global _lang, _map, _up, _tpl, _cache
    code = (code or "fr")[:2]
    if code == "fr" or code not in dict(LANGS) or not text or not isinstance(text, str):
        return text
    if code not in _autres:
        try:
            mp, up, tpl = _build(code)
        except Exception:
            mp, up, tpl = {}, {}, []
        _autres[code] = (mp, up, [(rx, t) for n, rx, t in tpl if n >= 8], {})
    sauve = (_lang, _map, _up, _tpl, _cache)
    _lang, (_map, _up, _tpl, _cache) = code, _autres[code]
    try:
        return tr(text)
    finally:
        _lang, _map, _up, _tpl, _cache = sauve


def _fill(t, args):
    """Remplace les {} (dans l'ordre) ou {0} {1}… (ordre libre) de la traduction."""
    if re.search(r"\{\d\}", t):
        return re.sub(r"\{(\d)\}", lambda m: args[int(m.group(1))] if int(m.group(1)) < len(args) else "", t)
    it = iter(args)
    return _PH.sub(lambda m: next(it, ""), t)


def _lookup(core, depth=0):
    t = _map.get(core)
    if t is not None:
        return t
    t = _up.get(core)
    if t is not None:
        return t
    if depth > 2:
        return None
    for rx, tt in _tpl:
        m = rx.fullmatch(core)
        if m:
            return _fill(tt, [tr(g, depth + 1) for g in m.groups()])
    return None


def tr(text, depth=0):
    """Traduit un texte affiché. Garde les emojis/espaces autour, essaie aussi ligne par ligne."""
    if _lang == "fr" or not text or not isinstance(text, str):
        return text
    hit = _cache.get(text)
    if hit is not None:
        return hit
    m = _EDGE.match(text)
    lead, core, trail = m.group(1), m.group(2), m.group(3)
    out = None
    if core:
        t = _lookup(core, depth)
        if t is None and core.endswith(("…", ":", " :")):        # « Réglages… », « Son prénom : »
            base = core.rstrip("…: ").rstrip()
            t2 = _lookup(base, depth) if base else None
            if t2 is not None:
                suf = core[len(base):]
                if suf.strip() == ":":
                    suf = "：" if _lang in ("zh", "ja") else ":"
                t = t2 + suf
        if t is None and "\n" in core:
            lines = core.split("\n")
            tl = [tr(x, depth + 1) for x in lines]
            if tl != lines:
                t = "\n".join(tl)
        if t is not None:
            out = lead + t + trail
    out = out if out is not None else text
    if len(_cache) < 20000:
        _cache[text] = out
    return out


# ------------------------------------------------------------------ application aux widgets
def _skip(w):
    try:
        return bool(w.property("no_i18n"))
    except Exception:
        return False


def translate_widget(w):
    if _lang == "fr" or w is None or _skip(w):
        return
    try:
        tip = w.toolTip()
        if tip:
            nt = tr(tip)
            if nt != tip:
                _orig_tip(w, nt)
        if w.isWindow():
            wt = w.windowTitle()
            if wt:
                nt = tr(wt)
                if nt != wt:
                    _orig_title(w, nt)
        if isinstance(w, QLabel):
            s = w.text()
            nt = tr(s)
            if nt != s:
                _orig_label(w, nt)
        elif isinstance(w, QAbstractButton):
            s = w.text()
            nt = tr(s)
            if nt != s:
                _orig_button(w, nt)
        elif isinstance(w, QLineEdit):
            s = w.placeholderText()
            if s:
                w.setPlaceholderText(tr(s))
        elif isinstance(w, (QTextEdit, QPlainTextEdit)):
            s = w.placeholderText()
            if s:
                w.setPlaceholderText(tr(s))
        elif isinstance(w, QComboBox):
            for i in range(w.count()):
                s = w.itemText(i)
                nt = tr(s)
                if nt != s:
                    w.setItemText(i, nt)
                ttip = w.itemData(i, 3)                  # ToolTipRole
                if isinstance(ttip, str) and ttip:
                    w.setItemData(i, tr(ttip), 3)
        elif isinstance(w, QListWidget):
            for i in range(w.count()):
                it = w.item(i)
                s = it.text()
                nt = tr(s)
                if nt != s:
                    it.setText(nt)
                if it.toolTip():
                    it.setToolTip(tr(it.toolTip()))
        elif isinstance(w, QGroupBox):
            w.setTitle(tr(w.title()))
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                w.setTabText(i, tr(w.tabText(i)))
        if isinstance(w, QMenu):
            translate_menu(w)
    except Exception:
        pass


def translate_menu(menu):
    if _lang == "fr" or _skip(menu):
        return
    try:
        t = menu.title()
        if t:
            menu.setTitle(tr(t))
        for a in menu.actions():
            s = a.text()
            nt = tr(s)
            if nt != s:
                _orig_action(a, nt)
            if a.toolTip() and a.toolTip() != s:
                a.setToolTip(tr(a.toolTip()))
            sub = a.menu()
            if sub is not None:
                sub.setTitle(tr(sub.title()))
    except Exception:
        pass


def translate_tree(root):
    if _lang == "fr" or root is None:
        return
    translate_widget(root)
    try:
        for w in root.findChildren(QWidget):
            translate_widget(w)
    except Exception:
        pass


class _Filter(QObject):
    """Traduit chaque widget juste avant son premier affichage, et chaque menu à l'ouverture."""

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Polish or t == QEvent.Type.Show:
            if isinstance(obj, QWidget):
                if t == QEvent.Type.Show and (obj.isWindow() or isinstance(obj, QMenu)):
                    translate_tree(obj)
                else:
                    translate_widget(obj)
        return False


# setters d'origine (avant le remplacement) : utilisés par le filtre lui-même
_orig_label = QLabel.setText
_orig_button = QAbstractButton.setText
_orig_action = QAction.setText
_orig_tip = QWidget.setToolTip
_orig_title = QWidget.setWindowTitle


def _patch():
    """Les textes changés après l'affichage (états, compteurs…) passent aussi par la traduction."""
    global _patched
    if _patched:
        return
    _patched = True
    QLabel.setText = lambda self, s: _orig_label(self, tr(s) if not _skip(self) else s)
    QAbstractButton.setText = lambda self, s: _orig_button(self, tr(s) if not _skip(self) else s)
    QAction.setText = lambda self, s: _orig_action(self, tr(s))
    QWidget.setToolTip = lambda self, s: _orig_tip(self, tr(s))
    QWidget.setWindowTitle = lambda self, s: _orig_title(self, tr(s))


def install(app, code):
    """À appeler une fois au démarrage (et quand on change de langue)."""
    global _filter
    set_lang(code)
    if _lang == "fr":
        if _filter is not None:
            app.removeEventFilter(_filter)
            _filter = None
        return
    _patch()
    if _filter is None:
        _filter = _Filter(app)
        app.installEventFilter(_filter)
