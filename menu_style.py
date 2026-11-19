"""Les menus de Viki au style des ronds (verre dépoli, clair ou graphite) :
fond arrondi, pictogrammes fins à la place des emojis, sous-menus qui flottent à côté.
Avec les ronds « classiques », les menus gardent leur ancien look."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu

EMOJI_ICONES = {
    "🎮": 0xf1d2,
    "📌": 0xec9c,
    "💡": 0xea51,
    "🧩": 0xeb10,
    "📍": 0xeae8,
    "⚙️": 0xeb20,
    "🔊": 0xeb51,
    "📖": 0xea39,
    "👗": 0xec0a,
    "📺": 0xea8d,
    "🛡️": 0xeb24,
    "🎯": 0xeb35,
    "👻": 0xeb8e,
    "📅": 0xea53,
    "📰": 0xeafd,
    "🎧": 0xeabd,
    "🖥️": 0xea89,
    "💽": 0xea88,
    "😊": 0xeaf7,
    "⭐": 0xeb2e,
    "🎨": 0xeb01,
    "🧠": 0xf59f,
    "🔇": 0xf1c3,
    "😄": 0xeaf4,
    "🏃": 0xec82,
    "🍽️": 0xeeff,
    "📋": 0xea6f,
    "💜": 0xeabe,
    "🎵": 0xeafc,
    "🎼": 0xeec0,
    "📔": 0xeb96,
    "🐞": 0xea48,
    "💾": 0xeb62,
    "🔍": 0xeb1c,
    "🎭": 0xf263,
    "📥": 0xeac4,
    "📧": 0xeae5,
    "🏠": 0xeac1,
    "✅": 0xea5e,
    "🌐": 0xebbe,
    "⏰": 0xea04,
    "🧅": 0xed58,
    "⬆️": 0xea25,
    "⬇️": 0xea16,
    "➖": 0xeaf2,
    "➕": 0xeb0b,
    "🖊️": 0xeb04,
    "🗑️": 0xeb41,
    "👆": 0xee94,
    "🔈": 0xeb4f,
    "↺": 0xeb13,
    "🎲": 0xf08f,
    "🎞️": 0xeafa,
    "📦": 0xeaff,
    "☀️": 0xeb30,
    "❓": 0xeabf,
    "💶": 0xeb85,
    "🌙": 0xeaf8,
    "⌨️": 0xebd6,
    "🪑": 0xef9e,
    "🎙": 0xeaf0,
    "🎙️": 0xeaf0,
    "💻": 0xeb64,
    "📓": 0xeb96,
    "✍️": 0xef08,
    "🧪": 0xebd2,
    "🐳": 0xedca,
    "📊": 0xea59,
    "📤": 0xeb1e,
    "🦆": 0xf9e7,
    "🆘": 0xeadd,
    "✏️": 0xeb04,
    "💬": 0xeaed,
    "🔔": 0xea35,
    "📝": 0xeb6e,
    "🛒": 0xeb25,
    "📚": 0xeff2,
    "🖼️": 0xeb0a,
    "🍅": 0xea70,
    "🗂️": 0xeaae,
    "🔌": 0xebd9,
    "😴": 0xf228,
    "🗨️": 0xeaef,
    "🌍": 0xeb54,
    "📄": 0xeaa2,
    "🗓️": 0xea52,
    "❄️": 0xec0b,
    "🪄": 0xebcb,
    "🎬": 0xeafa,
    "🎤": 0xeaf0,
    "🔁": 0xeb72,
    "📎": 0xeb02,
    "🔒": 0xeae2,
    "🔑": 0xeac7,
    "📁": 0xeaad,
    "📂": 0xfaf7,
    "🧹": 0xeb8b,
    "🌸": 0xeff6,
    "🛋️": 0xefaf,
    "💼": 0xea46,
    "🚪": 0xeba8,
    "👋": 0xec2e,
    "❤️": 0xeabe,
    "🔄": 0xeb13,
    "⏸": 0xed45,
    "▶": 0xed46,
    "🎹": 0xfad3,
    "📷": 0xea54,
    "🧘": 0xf01f,
    "🪟": 0xefe6,
    "🖱️": 0xeaf9,
    "🧭": 0xea79,
    "🎁": 0xeb68,
    "🔕": 0xece9,
    "🗣️": 0xed61,
    "🤖": 0xf00b,
    "🌡️": 0xeb38,
    "☕": 0xef0e,
    "📈": 0xeb43,
    "🔧": 0xeb40,
    "🛠️": 0xebca,
    "🧾": 0xedfd,
    "🏷️": 0x10096,
    "🎉": 0xee46,
    "🙂": 0xeaf7,
    "😺": 0xf65b,
    "🐱": 0xf65b,
    "📮": 0xeead,
    "✨": 0xf6d7,
    "🔥": 0xec2c,
    "🎚️": 0xea03,
    "👁️": 0xea9a,
    "🙈": 0xecf0,
    "🧑": 0xeb4d,
    "👤": 0xeb4d,
    "🗺️": 0xeae9,
    "⚡": 0xea38,
    "🧮": 0xeb80,
    "🌗": 0xec4e,
    "🖨️": 0xeb0e,
    "💤": 0xf228,
    "🏁": 0xeaa6,
    "🛑": 0xec2e,
    "⌛": 0xef93,
    "⏱️": 0xff9b,
    "🕐": 0xea70,
    "📸": 0xea54,
    "🧲": 0xeae3,
    "🧷": 0xeb02
}
_cache = {}
flou_ok = None             # fixé par compagnon.py : le bureau sait-il flouter derrière ? (KDE)
son_survol = None          # fixé par compagnon.py : petit « tic » quand la souris passe d'une ligne à l'autre
_dernier = [None, 0.0]


def _survol(action):
    import time
    if son_survol is None or action is None or action.isSeparator() or not action.isEnabled():
        return
    now = time.monotonic()
    if action is _dernier[0] or now - _dernier[1] < 0.05:
        return
    _dernier[0], _dernier[1] = action, now
    try:
        son_survol()
    except Exception:
        pass


def _couleur(txt):
    txt = txt.strip()
    if txt.startswith("rgba("):
        r, g, b, a = [float(x) for x in txt[5:-1].split(",")]
        return QColor(int(r), int(g), int(b), int(a))
    return QColor(txt)


def feuille(st):
    try:                                          # avec le flou de KDE, le verre peut être plus transparent
        if st.get("nom") == "Verre dépoli" and flou_ok and flou_ok():
            st = dict(st, menu_bg="rgba(34,36,44,190)")
    except Exception:
        pass
    return ("QMenu { background: %s; border: 1px solid %s; border-radius: 14px; padding: 6px; }"
            " QMenu::item { color: %s; font-size: 10pt; padding: 6px 22px 6px 8px; border-radius: 8px; margin: 1px 0; }"
            " QMenu::item:selected { background: %s; color: %s; }"
            " QMenu::item:disabled { color: %s; }"
            " QMenu::icon { padding-left: 8px; }"
            " QMenu::separator { height: 1px; background: %s; margin: 5px 10px; }"
            " QMenu::right-arrow { width: 8px; height: 8px; margin-right: 8px; }"
            " QLineEdit { background: rgba(127,127,127,45); color: %s; border: none; border-radius: 8px;"
            " padding: 6px 9px; font-size: 10pt; }"
            % (st["menu_bg"], st["menu_bord"], st["menu_txt"], st["menu_sel"], st["menu_sel_txt"], st["menu_off"],
               st["menu_sep"], st["menu_txt"]))


# pictogrammes de secours, seulement là où les emoji du système ne s'affichent pas (Bazzite, Fedora récent…)
EMOJI_SECOURS = {
    "🌅": 0xef1c,
    "💧": 0xea97,
    "💪": 0xeff0,
    "🔲": 0xfcc3,
    "🍿": 0xeafa,
    "🔤": 0xebbe,
    "🏋️": 0xeff0,
    "👁": 0xea9a,
}
secours = False


def _picto(code, emoji, coul, fam, px=18):
    k = (code, emoji, coul.name(QColor.NameFormat.HexArgb), fam)
    if k in _cache:
        return _cache[k]
    dpr = 2
    pm = QPixmap(px * dpr, px * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if code and fam:
        f = QFont(fam)
        f.setPixelSize(px)
        p.setFont(f)
        p.setPen(coul)
        p.drawText(QRectF(0, 0, px, px), Qt.AlignmentFlag.AlignCenter, chr(code))
    else:
        f = QFont()
        f.setPixelSize(int(px * 0.82))
        p.setFont(f)
        p.drawText(QRectF(0, 0, px, px), Qt.AlignmentFlag.AlignCenter, emoji)
    p.end()
    _cache[k] = pm
    return pm


def _emoji_de(t):
    """L'emoji du début d'un texte de menu (« ⚙️  Réglages… » -> « ⚙️ »), ou ""."""
    t = t.lstrip()
    if not t or t[0].isalnum() or t[0] in "(«[{\"'-—.":
        return ""
    e = t.split(" ", 1)[0]
    return e if len(e) <= 4 and not any(c.isalnum() for c in e) else ""


def convertir(menu, st, fam):
    """Emojis -> pictogrammes nets (dans la couleur du texte du menu), sous-menus compris."""
    norm, sel, off = _couleur(st["menu_txt"]), _couleur(st["menu_sel_txt"]), _couleur(st["menu_off"])
    for a in menu.actions():
        if a.isSeparator():
            continue
        t = a.text()
        e = _emoji_de(t)
        if e:
            code = EMOJI_ICONES.get(e) or EMOJI_ICONES.get(e.replace("\ufe0f", ""))
            if not code and secours:
                code = EMOJI_SECOURS.get(e) or EMOJI_SECOURS.get(e.replace("\ufe0f", ""))
            ic = QIcon()
            ic.addPixmap(_picto(code, e, norm, fam), QIcon.Mode.Normal)
            ic.addPixmap(_picto(code, e, sel, fam), QIcon.Mode.Active)
            ic.addPixmap(_picto(code, e, sel, fam), QIcon.Mode.Selected)
            ic.addPixmap(_picto(code, e, off, fam), QIcon.Mode.Disabled)
            a.setIcon(ic)
            a.setIconVisibleInMenu(True)
            a.setText(t.lstrip()[len(e):].lstrip())
        sm = a.menu()
        if sm is not None:
            appliquer(sm, st, fam)


def appliquer(menu, st, fam):
    """Donne le style à un menu (et à ses sous-menus quand ils s'ouvrent). st=None : on ne touche à rien."""
    if menu is None or not st:
        return menu
    if menu.property("style_viki") != st["nom"]:
        menu.setProperty("style_viki", st["nom"])
        menu.setProperty("sans_theme", True)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.NoDropShadowWindowHint)
        menu.setStyleSheet(feuille(st))
    menu._viki_st = st
    if not menu.property("style_relie"):
        menu.setProperty("style_relie", True)
        menu.aboutToShow.connect(lambda m=menu: convertir(m, getattr(m, "_viki_st", st), fam))
        menu.hovered.connect(_survol)
    return menu
