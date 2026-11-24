"""Le look « à la Apple » des grandes fenêtres (Réglages, Atelier d'images, Studio musique) :
pictogrammes blancs sur petites tuiles de couleur (comme les Réglages du Mac), groupes arrondis séparés par
de fins traits, onglets en commande segmentée. Actif quand les ronds sont en style Verre, Clair ou Graphite."""
from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

# couleurs des tuiles (fixes, comme sur macOS : elles ne suivent pas le thème)
TUILES = {
    "Accueil": "#8e8e93", "Personnage": "#0a84ff", "Au quotidien": "#ff9f0a", "Actions rapides": "#bf5af2",
    "Comportement": "#30b0c7", "Voix": "#ff375f", "Discussion": "#ff2d55", "Langues": "#0a84ff",
    "Apparence": "#5e5ce6", "Micro et écoute": "#ff453a", "Assistant": "#ac8e68", "Développeur": "#636366",
    "Gestion du PC": "#30d158", "Invitées": "#ff6482", "Performances": "#ffd60a", "Accessibilité": "#0a84ff",
    "Sauvegarde et aide": "#64d2ff",
}
_cache = {}


def actif(C, cfg):
    """Vrai si le style Apple est choisi (ronds en Verre, Clair ou Graphite)."""
    try:
        return cfg.get("ronds_theme", "verre") in getattr(C, "RONDS_STYLES", {})
    except Exception:
        return False


def _famille(C):
    try:
        return C.icon_family()
    except Exception:
        return ""


def code_de(emoji):
    try:
        import menu_style
        return menu_style.EMOJI_ICONES.get(emoji) or menu_style.EMOJI_ICONES.get(emoji.replace("️", ""))
    except Exception:
        return None


def tuile(C, emoji, couleur, px=24):
    """Petite tuile arrondie de couleur avec un pictogramme blanc (ou l'emoji si on n'a pas de pictogramme)."""
    k = (emoji, couleur, px)
    if k in _cache:
        return _cache[k]
    dpr = 2
    pm = QPixmap(px * dpr, px * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), px * 0.24, px * 0.24)
    p.fillPath(path, QColor(couleur))
    code, fam = code_de(emoji), _famille(C)
    r = QRectF(0, 0, px, px)
    if code and fam:
        f = QFont(fam)
        f.setPixelSize(int(px * 0.68))
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, chr(code))
    else:
        f = QFont()
        f.setPixelSize(int(px * 0.6))
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, emoji)
    p.end()
    _cache[k] = pm
    return pm


def sans_emoji(t):
    """« 🎵 Créer » -> (« 🎵 », « Créer »)."""
    t = (t or "").strip()
    if t and not t[0].isalnum():
        e, _, rest = t.partition(" ")
        if len(e) <= 4 and rest:
            return e, rest.strip()
    return "", t


def pictos_onglets(C, tabs, couleurs=("#0a84ff", "#8e8e93", "#30b0c7", "#ff9f0a")):
    """Onglets : l'emoji devient une petite tuile, le texte reste."""
    tabs.setIconSize(QSize(18, 18))
    for i in range(tabs.count()):
        e, txt = sans_emoji(tabs.tabText(i))
        if e:
            tabs.setTabIcon(i, QIcon(tuile(C, e, couleurs[i % len(couleurs)], 18)))
            tabs.setTabText(i, txt)


# ------------------------------------------------------------------ feuilles de style
# Réglages : écrites dans la palette rose d'origine, pour que le thème de Viki les recolore (Nuit, Menthe…)
REGLAGES = """
QWidget#reglages, QWidget#page { background: #f7f2f5; }
QListWidget#menu { background: #f1e9ee; border: none; border-right: 1px solid #e6dae1; padding: 8px 8px;
                   font-size: 13px; outline: 0; }
QListWidget#menu::item { padding: 5px 8px; margin: 0px 2px; border-radius: 7px; color: #3d2733; }
QListWidget#menu::item:hover { background: #e7dbe2; }
QListWidget#menu::item:selected { background: #d0457a; color: white; font-weight: normal; }
QFrame#carte { background: #ffffff; border: 1px solid #ece1e7; border-radius: 11px; }
QFrame#trait { background: #f1e7ec; border: none; min-height: 1px; max-height: 1px; }
QLabel#titrePage { font-size: 26px; font-weight: bold; color: #3d2733; }
QLabel#sousTitre { font-size: 13px; color: #8d7482; }
QLabel#titreCarte { font-size: 12px; font-weight: bold; color: #8d7482; letter-spacing: 0px; }
QLabel#nom { font-size: 13px; color: #3d2733; }
QLabel#aide { font-size: 11.5px; color: #9a8290; }
QPushButton { border-radius: 7px; padding: 6px 14px; }
QPushButton#principal { border-radius: 7px; }
QPushButton#tuile { border-radius: 11px; }
QComboBox, QLineEdit, QSpinBox, QTimeEdit { border-radius: 7px; }
QScrollBar:vertical { width: 10px; background: transparent; border-radius: 5px; margin: 2px; }
QScrollBar::handle:vertical { background: #d9c7d0; border-radius: 4px; min-height: 40px; margin: 1px; }
QScrollBar::handle:vertical:hover { background: #c7aebb; }
QScrollBar:horizontal { height: 10px; background: transparent; border-radius: 5px; margin: 2px; }
QScrollBar::handle:horizontal { background: #d9c7d0; border-radius: 4px; min-width: 40px; margin: 1px; }
"""

# Studios et « Ma liste » : aussi écrits dans la palette rose d'origine (le thème de Viki les recolore), pour que
# texte et fonds restent lisibles quel que soit le thème (Graphite clair, Nuit…), même si le bureau est sombre.
STUDIO = """
QWidget#atelier { font-size: 10.5pt; background: #f7f2f5; color: #3d2733; }
QWidget#atelier QLabel, QWidget#atelier QCheckBox, QWidget#atelier QRadioButton { color: #3d2733;
    background: transparent; }
QWidget#fond, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QTabWidget::pane { border: none; }
QTabWidget::tab-bar { alignment: center; }
QTabBar::tab { background: #ffffff; color: #3d2733; border: 1px solid #e3d3dc; padding: 6px 18px; min-width: 110px;
               margin: 6px 0 10px 0; }
QTabBar::tab:first { border-top-left-radius: 8px; border-bottom-left-radius: 8px; }
QTabBar::tab:last { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QTabBar::tab:!first { border-left: none; }
QTabBar::tab:selected { background: #d0457a; color: white; border-color: #d0457a; font-weight: bold; }
QFrame#carte { border: 1px solid #ece1e7; border-radius: 11px; background: #ffffff; }
QLabel#titre { font-size: 12.5pt; font-weight: bold; }
QLabel#aide { color: #9a8290; }
QPushButton { background: #ffffff; color: #4a3540; border: 1px solid #e3d3dc; border-radius: 7px; padding: 5px 12px; }
QPushButton:hover { background: #fdf0f5; border-color: #d0457a; }
QPushButton:disabled { color: #b8a6b0; }
QPushButton#chip { border-radius: 12px; padding: 5px 13px; }
QPushButton#chip:checked { background: #d0457a; color: white; border: 1px solid #d0457a; font-weight: bold; }
QPushButton#creer { background: #d0457a; color: white; border: none; border-radius: 10px; padding: 11px;
                    font-size: 13pt; font-weight: bold; }
QPushButton#creer:hover { background: #b9386b; }
QTextEdit, QLineEdit, QComboBox, QSpinBox { background: #ffffff; color: #3d2733; border: 1px solid #e3d3dc;
                                            border-radius: 8px; padding: 5px 9px; }
QTextEdit:focus, QLineEdit:focus, QComboBox:hover { border-color: #d0457a; }
QComboBox QAbstractItemView { background: #ffffff; color: #3d2733; selection-background-color: #d0457a;
                              selection-color: white; }
QTextEdit#prompt { border-radius: 11px; padding: 8px; }
QListWidget { border: 1px solid #ece1e7; border-radius: 11px; background: #ffffff; color: #3d2733; padding: 4px;
              outline: 0; }
QListWidget::item { padding: 7px 6px; border-radius: 8px; margin: 1px 0; }
QListWidget::item:hover { background: #fdf0f5; }
QListWidget::item:selected { background: #d0457a; color: white; }
QProgressBar { background: #f6e6ee; border: none; border-radius: 7px; text-align: center; color: #6b4a5a; }
QProgressBar::chunk { background: #d0457a; border-radius: 7px; }
QScrollArea { border: none; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #d9c7d0; border-radius: 4px; min-height: 40px; margin: 1px; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:horizontal { background: #d9c7d0; border-radius: 4px; min-width: 40px; margin: 1px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""
