"""Thèmes de couleur des fenêtres de Viki (réglages, manga, lecture, PC…).

Les feuilles de style sont écrites en rose. Un thème transforme chaque couleur (teinte, saturation, clair ou
sombre) au moment où une fenêtre s'affiche : rien à changer dans le reste du code.
"""
import colorsys
import re

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QLabel, QMenu, QWidget

# nom -> (libellé, teinte cible ou None, facteur de saturation, sombre ?, teinte de l'accent ou None)
THEMES = {
    "rose": ("🌸 Rose", None, 1.0, False, None),
    "lavande": ("💜 Lavande", 0.76, 1.0, False, None),
    "ocean": ("🌊 Océan", 0.57, 1.0, False, None),
    "menthe": ("🌿 Menthe", 0.43, 0.9, False, None),
    "peche": ("🍑 Pêche", 0.055, 1.0, False, None),
    "graphite": ("🩶 Graphite", None, 0.08, False, 0.58),
    "sombre": ("🌙 Sombre (rose)", None, 0.6, True, None),
    "pomme": ("🍎 Épuré", None, 0.0, True, None),
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
CLAIR, SOMBRE = "graphite", "pomme"
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


# « épuré » : gris foncés neutres, texte presque blanc, accent bleu (comme la fenêtre du tuto)
_POMME_L = ((0.0, 0.97), (0.2, 0.90), (0.4, 0.78), (0.65, 0.50), (0.86, 0.23), (0.95, 0.16), (1.0, 0.125))


def _pomme(hh, ll, ss):
    if ss > 0.4 and 0.3 < ll < 0.75:                         # accent : le bleu système
        return colorsys.hls_to_rgb(0.588, max(0.38, min(0.66, 0.52 + (ll - 0.5) * 0.6)), 1.0)
    if ss > 0.55 and ll <= 0.3:                               # rouges / roses très foncés (texte d'accent)
        return colorsys.hls_to_rgb(0.588, 0.68, 1.0)
    for (a, va), (b, vb) in zip(_POMME_L, _POMME_L[1:]):
        if a <= ll <= b:
            l2 = va + (vb - va) * ((ll - a) / (b - a) if b > a else 0)
            break
    else:
        l2 = 0.5
    return colorsys.hls_to_rgb(0.64, l2, 0.09 if l2 < 0.3 else 0.03)


def _tf(hexc):
    """Une couleur rose d'origine -> la même dans le thème choisi."""
    h = hexc.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    _lab, hue, sat, dark, acc = THEMES[_cur]
    if _cur == "pomme":
        r, g, b = _pomme(hh, ll, ss)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
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


def _dans_menu(w):
    try:
        return isinstance(w, QMenu) or isinstance(w.window(), QMenu)
    except Exception:
        return False


def apply(w):
    """Applique le thème à un widget (une seule fois par thème).
    Avec « épuré », le menu du clic droit garde exactement le look « nuit »."""
    global _cur
    if _cur == "pomme" and w is not None and _dans_menu(w):
        _cur = "nuit"
        try:
            return apply(w)
        finally:
            _cur = "pomme"
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


POMME_CSS = """/*pomme*/
QPushButton { background: rgba(@A@,26); color: @TXT@; border: 1px solid rgba(@A@,50);
              border-radius: 12px; padding: 5px 15px; }
QPushButton:hover { background: rgba(@A@,48); }
QPushButton:pressed { background: rgba(@A@,12); }
QPushButton:checked { background: @ACC@; color: white; border: 1px solid @ACC@; }
QPushButton:disabled { color: rgba(@T2@,80); background: rgba(@A@,10); }
QPushButton:default { background: @ACC@; color: white; border: none; border-radius: 10px; font-weight: 600; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background: rgba(@A@,14); color: @TXT@; border: 1px solid rgba(@A@,24);
    border-radius: 9px; padding: 3px 8px; selection-background-color: @ACC@; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus { border: 1px solid @ACC@; }
QComboBox { background: rgba(@A@,20); color: @TXT@; border: 1px solid rgba(@A@,26);
            border-radius: 9px; padding: 3px 10px; }
QComboBox:hover { background: rgba(@A@,34); }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(@BAS@); width: 10px; height: 10px; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    border: none; background: transparent; width: 18px; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(@HAUT@); width: 9px; height: 9px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(@BAS@); width: 9px; height: 9px; }
QComboBox QAbstractItemView { background: @POP@; color: @TXT@; border: 1px solid rgba(@A@,30);
                              border-radius: 8px; selection-background-color: @ACC@; outline: none; }
QListWidget, QListView, QTreeView, QTableView { background: rgba(@A@,10); color: @TXT@;
    border: 1px solid rgba(@A@,20); border-radius: 10px; selection-background-color: @ACC@; }
QTabBar::tab { background: transparent; color: rgba(@T2@,160); padding: 6px 14px; border: none;
               border-radius: 8px; margin: 2px; }
QTabBar::tab:selected { background: rgba(@A@,34); color: @TXT@; }
QTabWidget::pane { border: 1px solid rgba(@A@,20); border-radius: 12px; top: -1px; }
QGroupBox { border: 1px solid rgba(@A@,22); border-radius: 12px; margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: rgba(@T2@,170); }
QToolTip { background: @POP@; color: @TXT@; border: 1px solid rgba(@A@,30); border-radius: 8px;
           padding: 4px 8px; }
QSlider::groove:horizontal { height: 4px; background: rgba(@A@,40); border-radius: 2px; }
QSlider::sub-page:horizontal { background: @ACC@; border-radius: 2px; }
QSlider::handle:horizontal { background: white; border: 1px solid rgba(0,0,0,40); width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }
QProgressBar { background: rgba(@A@,24); border: none; border-radius: 4px; color: transparent; max-height: 8px; }
QProgressBar::chunk { background: @ACC@; border-radius: 4px; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(@A@,60); border-radius: 3px; min-height: 40px; margin: 1px; }
QScrollBar::handle:vertical:hover { background: rgba(@A@,110); }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:horizontal { background: rgba(@A@,60); border-radius: 3px; min-width: 40px; margin: 1px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
/*finpomme*/
"""
_RX_H = re.compile(r"\n?/\*habit\*/")
_RX_POMME = re.compile(r"/\*pomme\*/.*?/\*finpomme\*/\n?", re.S)


_FLECHES = {}


def _fleches():
    """Les petits chevrons des listes déroulantes (dessinés une fois, en PNG : marche partout)."""
    if not _FLECHES:
        import os
        import tempfile
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
        d = os.path.join(tempfile.gettempdir(), "viki-fleches-%s" % (os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "w")))
        os.makedirs(d, exist_ok=True)
        for nom, pts in (("bas", ((4, 8), (10, 14), (16, 8))), ("haut", ((4, 12), (10, 6), (16, 12))),
                         ("bas_n", ((4, 8), (10, 14), (16, 8))), ("haut_n", ((4, 12), (10, 6), (16, 12)))):
            f = os.path.join(d, nom + ".png")
            pm = QPixmap(20, 20)
            pm.fill(Qt.GlobalColor.transparent)
            pa = QPainter(pm)
            pa.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(60, 60, 67, 200) if nom.endswith("_n") else QColor(235, 235, 245, 200), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pa.setPen(pen)
            pa.drawPolyline([QPointF(*p) for p in pts])
            pa.end()
            pm.save(f, "PNG")
            _FLECHES[nom] = f.replace("\\", "/")
    sombre = est_sombre()
    acc = "#0a84ff" if _cur == "pomme" else color("#d0457a")
    rep = {"@BAS@": _FLECHES["bas" if sombre else "bas_n"], "@HAUT@": _FLECHES["haut" if sombre else "haut_n"],
           "@A@": "255,255,255" if sombre else "0,0,0", "@T2@": "235,235,245" if sombre else "60,60,67",
           "@TXT@": "#f5f5f7" if sombre else color("#3d2733"), "@ACC@": acc,
           "@POP@": "#2a2b33" if _cur == "pomme" else color("#ffffff")}
    out = POMME_CSS
    for k, v in rep.items():
        out = out.replace(k, v)
    if not sombre:                       # fonds clairs : des voiles un peu plus marqués
        out = re.sub(r"rgba\(0,0,0,(\d+)\)", lambda m: "rgba(0,0,0,%d)" % min(255, int(int(m.group(1)) * 0.7)), out)
    return out


def est_sombre():
    try:
        return _cur == "pomme" or bool(THEMES.get(_cur, (0, 0, 0, False))[3])
    except Exception:
        return True


def _fenetre_pomme(w):
    """Les boutons, champs et listes arrondis du style « épuré » sur une fenêtre de Viki.
    Pas sur les menus (le clic droit reste tel quel), ni sur ce qui flotte sur le bureau (elle, ses bulles…)."""
    try:
        if not w.isWindow() or w.property("sans_theme") or _dans_menu(w):
            return
        from PyQt6.QtCore import Qt
        if w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) and not (
                habit is not None and id(w) in habit._H):
            return
        s = w.styleSheet() or ""
        if _cur != "rose" and w.property("theme_fait") != _cur:   # ses couleurs, dans le même calcul que nos blocs
            w.setProperty("theme_fait", _cur)
            s = css(s)
        s = _RX_POMME.sub("", s)
        if habit is not None and id(w) in habit._H and "/*habit*/" not in s:
            s = s + habit.regle(w)              # fenêtre arrondie : le fond transparent, dans le même calcul
        if _cur != "contraste":                 # à la fin : les mêmes boutons partout (les #noms précis gardent les leurs)
            h = _RX_H.search(s)
            s = (s[:h.start()] + _fleches() + s[h.start():]) if h else s + "\n" + _fleches()
        if s != (w.styleSheet() or ""):
            w.setStyleSheet(s)                  # un seul recalcul du style pour toute la fenêtre
        if _cur != "contraste":                 # les petits boutons carrés (icônes) : pas de marge, sinon l'icône disparaît
            from PyQt6.QtWidgets import QPushButton
            for b in w.findChildren(QPushButton):
                if b.maximumWidth() <= 48 and "padding" not in (b.styleSheet() or ""):
                    b.setStyleSheet((b.styleSheet() or "") + " QPushButton { padding: 0px; }")
    except Exception:
        pass


try:
    import habit
except Exception:                     # habit.py absent : fenêtres avec le cadre du bureau
    habit = None


class _Filter(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if habit is not None and habit.ACTIF and habit.concerne(obj, t):
            if habit.evenement(obj, ev, sombre=est_sombre(), fond=fond_fenetre()):
                return True
        if (t == QEvent.Type.Polish or t == QEvent.Type.Show) and isinstance(obj, QWidget):
            if t == QEvent.Type.Show and obj.isWindow():
                apply_tree(obj)
                _fenetre_pomme(obj)
                if habit is not None and habit.ACTIF:
                    habit.montrer(obj)
            else:
                apply(obj)
        return False


def fond_fenetre():
    return "#1e1f26" if _cur == "pomme" else color("#fbf6f9")


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
        if _cur == "pomme":
            for role, hexc in ((P.Window, "#1e1f26"), (P.Base, "#26272f"), (P.AlternateBase, "#2c2d35"),
                               (P.Button, "#30313a"), (P.Highlight, "#0a84ff"), (P.Link, "#409cff"),
                               (P.ToolTipBase, "#2a2b33"), (P.Mid, "#3a3b45"), (P.Midlight, "#34353e")):
                pal.setColor(role, QColor(hexc))
            for role in (P.WindowText, P.Text, P.ButtonText, P.ToolTipText):
                pal.setColor(role, QColor("#f5f5f7"))
            pal.setColor(P.PlaceholderText, QColor("#8e8e98"))
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
    if habit is not None and habit.ACTIF:
        habit.installer(_fenetre_pomme)         # fenêtres arrondies : tout est préparé AVANT l'affichage
    if _filter is None:
        _filter = _Filter(app)
        app.installEventFilter(_filter)
    return _cur
