"""Thèmes de couleur des fenêtres de Viki (réglages, manga, lecture, PC…).

Les feuilles de style sont écrites en rose. Un thème transforme chaque couleur (teinte, saturation, clair ou
sombre) au moment où une fenêtre s'affiche : rien à changer dans le reste du code.
"""
import colorsys
import re

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QLabel, QWidget

# nom -> (libellé, teinte cible ou None, facteur de saturation, sombre ?, teinte de l'accent ou None)
THEMES = {
    "rose": ("🌸 Rose", None, 1.0, False, None),
    "lavande": ("💜 Lavande", 0.76, 1.0, False, None),
    "ocean": ("🌊 Océan", 0.57, 1.0, False, None),
    "menthe": ("🌿 Menthe", 0.43, 0.9, False, None),
    "peche": ("🍑 Pêche", 0.055, 1.0, False, None),
    "graphite": ("🩶 Graphite", None, 0.08, False, 0.58),
    "sombre": ("🌙 Sombre (rose)", None, 0.6, True, None),
    "nuit": ("🌌 Nuit (bleu)", 0.62, 0.7, True, None),
    "contraste": ("◐ Contraste élevé (accessibilité)", None, 0.0, False, 0.6),
}
# choix qui changent tout seuls : -> un des thèmes ci-dessus
SPECIAUX = {
    "auto": "🌗 Automatique (clair le jour, sombre le soir)",
    "systeme": "🖥️ Comme mon bureau (clair / sombre)",
    "perso": "🎨 Ma couleur",
    "perso_sombre": "🎨 Ma couleur, en sombre",
}
CLAIR, SOMBRE = "graphite", "nuit"
# barres de défilement bien visibles dans toutes les fenêtres de Viki (feuille de style de l'application)
APP_CSS = """
QScrollBar:vertical { width: 14px; background: #f6e6ee; border-radius: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: #e889ad; border-radius: 5px; min-height: 40px; margin: 2px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed { background: #d0457a; }
QScrollBar:horizontal { height: 14px; background: #f6e6ee; border-radius: 7px; margin: 2px; }
QScrollBar::handle:horizontal { background: #e889ad; border-radius: 5px; min-width: 40px; margin: 2px; }
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed { background: #d0457a; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""          # utilisés par « automatique » et « comme mon bureau »
PINK = 0.93                     # teinte des couleurs d'origine
HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

_cur = "rose"
_choice = "rose"
_SYS = {}                                    # le bureau est-il sombre ? (lu avant qu'on change la palette)
_cache = {}
_filter = None
EXTRA_CSS = ""                               # ajouté par l'accessibilité (contour du focus clavier)


def current():
    """Le choix de l'utilisateur (peut être « auto », « systeme », « perso »…)."""
    return _choice


def effective():
    """Le thème vraiment appliqué en ce moment."""
    return _cur


def choices():
    return [(v[0], k) for k, v in THEMES.items() if not k.startswith("_")] + [(v, k) for k, v in SPECIAUX.items()]


def _hue_of(hexc):
    h = (hexc or "#5b8def").lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0]


def resolve(choice, app=None, hour=None, custom=""):
    """Choix -> thème réel (pour « automatique », « comme mon bureau », « ma couleur »)."""
    import datetime
    if choice == "auto":
        hour = datetime.datetime.now().hour if hour is None else hour
        return CLAIR if 7 <= hour < 20 else SOMBRE
    if choice == "systeme":
        try:
            from PyQt6.QtGui import QPalette
            from PyQt6.QtCore import Qt
            try:                                   # Qt 6.5+ : le bureau dit s'il est sombre
                if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                    return SOMBRE
                if app.styleHints().colorScheme() == Qt.ColorScheme.Light:
                    return CLAIR
            except Exception:
                pass
            return SOMBRE if _SYS.get("sombre") else CLAIR
        except Exception:
            return CLAIR
    if choice in ("perso", "perso_sombre"):
        THEMES["_perso"] = ("🎨 Ma couleur", _hue_of(custom), 1.0, choice == "perso_sombre", None)
        return "_perso"
    return choice if choice in THEMES else "rose"


def _tf(hexc):
    """Une couleur rose d'origine -> la même dans le thème choisi."""
    h = hexc.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    _lab, hue, sat, dark, acc = THEMES[_cur]
    if _cur == "contraste":                                   # noir sur blanc, accent bleu foncé bien lisible
        if ss > 0.4 and 0.3 < ll < 0.75:
            r, g, b = colorsys.hls_to_rgb(0.6, 0.28, 0.9)
        else:
            v = 1.0 if ll >= 0.92 else 0.35 if ll >= 0.8 else 0.0     # fonds blancs, bordures grises, texte noir
            r = g = b = v
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    accent = ss > 0.4 and 0.3 < ll < 0.75                       # les roses vifs : boutons, titres, curseurs
    if accent and acc is not None:
        hh = acc
    elif hue is not None and ss > 0.04:
        hh = (hh - PINK + hue) % 1.0
    if not accent:                                            # l'accent garde son éclat
        ss = min(1.0, ss * sat)
    if dark:
        ll = 0.10 + (1.0 - ll) * 0.82
        if ll < 0.3:
            ss *= 0.55
    r, g, b = colorsys.hls_to_rgb(hh, max(0.0, min(1.0, ll)), max(0.0, min(1.0, ss)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def color(hexc):
    """Couleur d'origine -> couleur du thème (pour ce qui est dessiné à la main)."""
    if _cur == "rose":
        return hexc
    k = (hexc.lower(), _cur)
    if k not in _cache:
        _cache[k] = _tf(hexc)
    return _cache[k]


def css(text):
    """Toutes les couleurs #rrggbb / #rgb d'une feuille de style ou d'un texte riche."""
    if _cur == "rose" or not text or "#" not in text:
        return text
    out = HEX.sub(lambda m: color(m.group(0)), text)
    if THEMES[_cur][3]:                                       # sombre : les fonds blancs nommés aussi
        out = re.sub(r"(background(?:-color)?\s*:\s*)white\b", lambda m: m.group(1) + color("#ffffff"), out)
    return out


def apply(w):
    """Applique le thème à un widget (une seule fois par thème)."""
    if _cur == "rose" or w is None:
        return
    try:
        if w.property("theme_fait") == _cur or w.property("sans_theme"):
            return
        w.setProperty("theme_fait", _cur)
        s = w.styleSheet()
        if s:
            ns = css(s)
            if ns != s:
                w.setStyleSheet(ns)
        if isinstance(w, QLabel):
            t = w.text()
            if "<" in t and "#" in t:
                nt = css(t)
                if nt != t:
                    w.setText(nt)
    except Exception:
        pass


def apply_tree(root):
    apply(root)
    try:
        for w in root.findChildren(QWidget):
            apply(w)
    except Exception:
        pass


class _Filter(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if (t == QEvent.Type.Polish or t == QEvent.Type.Show) and isinstance(obj, QWidget):
            if t == QEvent.Type.Show and obj.isWindow():
                apply_tree(obj)
            else:
                apply(obj)
        return False


def apply_palette(app):
    """Couleurs de base de toutes les fenêtres de Viki, quel que soit le thème du bureau (KDE sombre, Windows
    sombre…) : sinon un texte blanc du bureau sombre se retrouve sur nos fonds clairs, et on ne voit plus rien."""
    try:
        from PyQt6.QtGui import QColor, QPalette
        P, G = QPalette.ColorRole, QPalette.ColorGroup
        pal = QPalette()
        txt, muted = QColor(color("#3d2733")), QColor(color("#b49aa7"))
        for role, hexc in ((P.Window, "#fbf6f9"), (P.WindowText, "#3d2733"), (P.Base, "#ffffff"),
                           (P.AlternateBase, "#fdf0f5"), (P.Text, "#3d2733"), (P.Button, "#ffffff"),
                           (P.ButtonText, "#3d2733"), (P.Highlight, "#d0457a"), (P.ToolTipBase, "#fffafc"),
                           (P.ToolTipText, "#3d2733"), (P.PlaceholderText, "#9a8290"), (P.Link, "#b0336a"),
                           (P.LinkVisited, "#8d3a62"), (P.Light, "#ffffff"), (P.Midlight, "#f6e6ee"),
                           (P.Mid, "#e7cfdb"), (P.Dark, "#b49aa7"), (P.Shadow, "#6b4a5a")):
            pal.setColor(role, QColor(color(hexc)))
        pal.setColor(P.HighlightedText, QColor("#ffffff"))
        pal.setColor(P.BrightText, QColor("#ffffff"))
        for role in (P.WindowText, P.Text, P.ButtonText):
            pal.setColor(G.Disabled, role, muted)
        pal.setColor(G.Disabled, P.Base, QColor(color("#fbf6f9")))
        app.setPalette(pal)
        _ = txt
    except Exception:
        pass


EN_COURS = False


def install(app, name, custom=""):
    """À appeler au démarrage et quand on change de thème (les fenêtres rouvertes le prennent).
    Renvoie le thème réellement appliqué."""
    global _cur, _filter, _choice
    if "sombre" not in _SYS:
        try:
            from PyQt6.QtGui import QPalette
            _SYS["sombre"] = app.palette().color(QPalette.ColorRole.Window).lightnessF() < 0.5
        except Exception:
            _SYS["sombre"] = False
    global EN_COURS
    _choice = name if (name in THEMES or name in SPECIAUX) else "rose"
    _cur = resolve(_choice, app, custom=custom)
    _cache.clear()
    EN_COURS = True                       # toute l'appli se redessine : ne pas changer de style en plein milieu
    try:
        app.setStyleSheet(css(APP_CSS) + EXTRA_CSS)
    except Exception:
        pass
    try:
        apply_palette(app)
    finally:
        EN_COURS = False
    if _cur == "rose":
        if _filter is not None:
            app.removeEventFilter(_filter)
            _filter = None
        return _cur
    if _filter is None:
        _filter = _Filter(app)
        app.installEventFilter(_filter)
    return _cur
