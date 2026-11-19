"""La fenêtre « L'actu » : les titres en images à côté de Viki, par catégorie.
Pendant qu'elle lit, l'article en cours s'allume. Clic sur un article : elle le lit ; ↗ : l'ouvrir.
Internet seulement quand tu demandes l'actu (comme avant)."""
import datetime
import email.utils
import re
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl, QPoint, QRect, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont, QDesktopServices, QCursor, QImage
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QScrollArea,
                             QApplication, QButtonGroup, QLayout, QSizeGrip, QSizePolicy, QDialog)

try:
    import i18n
    tr = i18n.tr
except Exception:                                    # pragma: no cover
    def tr(t):
        return t

THUMB_W, THUMB_H = 112, 72
MAX_ITEMS = 8
CACHE_S = 10 * 60
# couleur de la vignette de secours, par catégorie
TEINTES = {"toi": "#7F77DD", "une": "#378ADD", "science": "#1D9E75", "informatique": "#534AB7", "ia": "#7F77DD",
           "jeux": "#D4537E", "manga": "#ED93B1", "cinema": "#BA7517", "espace": "#185FA5", "sante": "#639922",
           "linux": "#5F5E5A", "monde": "#378ADD", "sport": "#D85A30", "musique": "#993556"}

# ce qu'on cherche pour chaque catégorie, dans chaque langue (les titres arrivent dans ta langue)
REQ = {
    "science": {"en": "science discovery", "es": "ciencia descubrimiento", "ru": "наука открытие", "zh": "科学 发现",
                "ja": "科学 発見", "hi": "विज्ञान खोज", "de": "Wissenschaft", "it": "scienza scoperta"},
    "informatique": {"en": "tech software", "es": "tecnología informática", "ru": "технологии IT", "zh": "科技 软件",
                     "ja": "テクノロジー IT", "hi": "टेक्नोलॉजी", "de": "Technik Software", "it": "tecnologia informatica"},
    "ia": {"en": "artificial intelligence", "es": "inteligencia artificial", "ru": "искусственный интеллект",
           "zh": "人工智能", "ja": "人工知能", "hi": "आर्टिफिशियल इंटेलिजेंस", "de": "künstliche Intelligenz",
           "it": "intelligenza artificiale"},
    "jeux": {"en": "video games", "es": "videojuegos", "ru": "видеоигры", "zh": "电子游戏", "ja": "ゲーム",
             "hi": "वीडियो गेम", "de": "Videospiele", "it": "videogiochi"},
    "manga": {"en": "manga anime", "es": "manga anime", "ru": "манга аниме", "zh": "漫画 动画", "ja": "漫画 アニメ",
              "hi": "एनीमे मंगा", "de": "Manga Anime", "it": "manga anime"},
    "cinema": {"en": "movies TV series", "es": "cine series", "ru": "кино сериалы", "zh": "电影 电视剧",
               "ja": "映画 ドラマ", "hi": "फ़िल्म वेब सीरीज़", "de": "Kino Serien", "it": "cinema serie tv"},
    "espace": {"en": "space astronomy", "es": "espacio astronomía", "ru": "космос астрономия", "zh": "太空 天文",
               "ja": "宇宙 天文", "hi": "अंतरिक्ष", "de": "Raumfahrt Astronomie", "it": "spazio astronomia"},
    "sante": {"en": "health", "es": "salud", "ru": "здоровье", "zh": "健康", "ja": "健康", "hi": "स्वास्थ्य",
              "de": "Gesundheit", "it": "salute"},
    "linux": {"en": "Linux", "es": "Linux", "ru": "Linux", "zh": "Linux", "ja": "Linux", "hi": "Linux"},
    "monde": {"en": "world news", "es": "internacional", "ru": "мировые новости", "zh": "国际新闻", "ja": "国際ニュース",
              "hi": "अंतरराष्ट्रीय समाचार", "de": "Weltnachrichten", "it": "esteri"},
    "sport": {"en": "sports", "es": "deportes", "ru": "спорт", "zh": "体育", "ja": "スポーツ", "hi": "खेल",
              "de": "Sport", "it": "sport"},
    "musique": {"en": "music", "es": "música", "ru": "музыка", "zh": "音乐", "ja": "音楽", "hi": "संगीत",
                "de": "Musik", "it": "musica"},
}
# ce qu'elle dit avant le 1er titre
DIT = {
    "fr": {"toi": "Voici les titres de tes sites. ", "une": "Voici les gros titres. ", "cat": "L'actu {}. ",
           "q": "Voici ce que j'ai trouvé sur {}. ", "rien": "Je n'ai rien trouvé là-dessus pour le moment.",
           "err": "Je n'ai pas réussi à récupérer l'actu… Tu es bien connecté à internet ?"},
    "en": {"toi": "Here are the headlines from your sites. ", "une": "Here are the top stories. ",
           "cat": "Here's the latest in {}. ", "q": "Here's what I found about {}. ",
           "rien": "I couldn't find anything about that right now.",
           "err": "I couldn't get the news… Are you connected to the internet?"},
    "es": {"toi": "Aquí tienes los titulares de tus sitios. ", "une": "Estos son los titulares. ",
           "cat": "Las noticias de {}. ", "q": "Esto es lo que encontré sobre {}. ",
           "rien": "No encontré nada sobre eso por ahora.",
           "err": "No pude obtener las noticias… ¿Estás conectado a internet?"},
    "ru": {"toi": "Вот заголовки с твоих сайтов. ", "une": "Вот главные новости. ", "cat": "Новости: {}. ",
           "q": "Вот что я нашла про {}. ", "rien": "Пока ничего не нашла об этом.",
           "err": "Не получилось загрузить новости… Ты подключён к интернету?"},
    "zh": {"toi": "这是你关注的网站的头条。", "une": "这是今天的头条新闻。", "cat": "{}的最新消息。",
           "q": "这是我找到的关于{}的消息。", "rien": "暂时没有找到相关消息。", "err": "我没能获取新闻……你连上网了吗？"},
    "ja": {"toi": "あなたのサイトの見出しです。", "une": "今日の主なニュースです。", "cat": "{}の最新ニュースです。",
           "q": "{}について見つけたニュースです。", "rien": "今のところ見つかりませんでした。",
           "err": "ニュースを取得できませんでした…インターネットにつながっていますか？"},
    "hi": {"toi": "ये रहीं तुम्हारी साइटों की सुर्खियाँ। ", "une": "ये रहीं आज की मुख्य खबरें। ",
           "cat": "{} की ताज़ा खबरें। ", "q": "{} के बारे में मुझे ये मिला। ",
           "rien": "अभी इस बारे में कुछ नहीं मिला।", "err": "खबरें नहीं मिल पाईं… क्या तुम इंटरनेट से जुड़े हो?"},
}


def langue_actu(cfg):
    """La langue des titres : celle de l'interface, sinon celle dans laquelle elle parle."""
    try:
        ui = i18n.lang()
    except Exception:
        ui = ""
    if ui and ui != "fr":
        return ui[:2]
    return (cfg.get("langue", "fr") or "fr")[:2]


CSS = """
#cadre { background: #1d1b22; border: 1px solid #3a3644; border-radius: 16px; }
QLabel { color: #ece9f2; background: transparent; }
#titre { font-size: 15px; font-weight: 600; }
#date { color: #9b96a8; font-size: 11px; }
#etat { color: #9b96a8; font-size: 12px; padding: 18px 6px; }
QPushButton#chip { background: #2a2731; color: #d9d5e2; border: 1px solid #3a3644; border-radius: 13px;
                   padding: 4px 11px; font-size: 12px; }
QPushButton#chip:hover { border-color: #6f6a80; }
QPushButton#chip:checked { background: #EEEDFE; color: #26215C; border-color: #EEEDFE; }
QPushButton#btn { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px;
                  padding: 5px 12px; font-size: 12px; }
QPushButton#btn:hover { background: #343040; }
QPushButton#x { background: transparent; color: #9b96a8; border: none; font-size: 15px; padding: 0 4px; }
QPushButton#x:hover { color: #ffffff; }
QPushButton#ouvrir { background: transparent; color: #9b96a8; border: none; font-size: 15px; padding: 2px 4px; }
QPushButton#ouvrir:hover { color: #ffffff; }
#ligne { background: transparent; border-radius: 10px; }
#ligne:hover { background: #26232d; }
#ligne[on="true"] { background: #2f2a4a; }
#art { font-size: 13px; }
#ligne[on="true"] #art { color: #CECBF6; font-weight: 600; }
#meta { color: #8f8a9c; font-size: 11px; }
#ligne[on="true"] #meta { color: #AFA9EC; }
QScrollArea { background: transparent; border: none; }
#fond { background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #4a4556; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { height: 0; }
"""


def depuis(date_txt):
    """« il y a 2 h », « il y a 15 min », « hier »… depuis une date RSS ou ISO."""
    d = None
    try:
        d = email.utils.parsedate_to_datetime(date_txt)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat((date_txt or "").replace("Z", "+00:00"))
        except Exception:
            return ""
    if d is None:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    s = (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds()
    if s < 0:
        return ""
    if s < 3600:
        return tr(f"il y a {max(1, int(s // 60))} min")
    if s < 86400:
        return tr(f"il y a {int(s // 3600)} h")
    if s < 2 * 86400:
        return tr("hier")
    return tr(f"il y a {int(s // 86400)} jours")


def vignette(data_or_none, couleur, emoji):
    """Une vignette arrondie : l'image recadrée, ou une tuile de couleur avec l'emoji de la catégorie."""
    dpr = 2
    pm = QPixmap(THUMB_W * dpr, THUMB_H * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, THUMB_W, THUMB_H), 9, 9)
    p.setClipPath(path)
    img = QPixmap()
    if data_or_none and img.loadFromData(data_or_none) and not img.isNull():
        sc = img.scaled(THUMB_W * dpr, THUMB_H * dpr, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
        x, y = (sc.width() - THUMB_W * dpr) // 2, (sc.height() - THUMB_H * dpr) // 2
        p.drawPixmap(QRectF(0, 0, THUMB_W, THUMB_H), sc, QRectF(x, y, THUMB_W * dpr, THUMB_H * dpr))
    else:
        c = QColor(couleur)
        p.fillRect(QRectF(0, 0, THUMB_W, THUMB_H), c.darker(170))
        f = QFont()
        f.setPointSize(22)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(0, 0, THUMB_W, THUMB_H), Qt.AlignmentFlag.AlignCenter, emoji or "📰")
    p.end()
    return pm


class FlowLayout(QLayout):
    """Les pastilles passent à la ligne quand il n'y a plus de place (toutes visibles d'un coup)."""

    def __init__(self, parent=None, esp=6):
        super().__init__(parent)
        self._items, self._esp = [], esp
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, it):
        self._items.append(it)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._place(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._place(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        sz = QSize()
        for it in self._items:
            sz = sz.expandedTo(it.minimumSize())
        return sz

    def _place(self, r, test):
        x, y, ligne = r.x(), r.y(), 0
        for it in self._items:
            h = it.sizeHint()
            if x + h.width() > r.right() + 1 and ligne > 0:
                x, y, ligne = r.x(), y + ligne + self._esp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), h))
            x += h.width() + self._esp
            ligne = max(ligne, h.height())
        return y + ligne - r.y()


class Ligne(QFrame):
    def __init__(self, win, i, art, emoji, couleur):
        super().__init__()
        self.win, self.i, self.art = win, i, art
        self.setObjectName("ligne")
        self.setProperty("on", False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)
        self.img = QLabel()
        self.img.setFixedSize(THUMB_W, THUMB_H)
        self.img.setPixmap(vignette(None, couleur, emoji))
        lay.addWidget(self.img, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.t = QLabel(art.get("titre", ""))
        self.t.setObjectName("art")
        self.t.setWordWrap(True)
        self.t.setProperty("no_i18n", True)          # le titre reste dans sa langue
        col.addWidget(self.t)
        meta = " · ".join(x for x in (art.get("source", ""), depuis(art.get("date", ""))) if x)
        self.m = QLabel(meta)
        self.m.setObjectName("meta")
        self.m.setProperty("no_i18n", True)
        col.addWidget(self.m)
        col.addStretch()
        lay.addLayout(col, 1)
        if art.get("lien"):
            o = QPushButton("↗")
            o.setObjectName("ouvrir")
            o.setToolTip(tr("Ouvrir l'article dans le navigateur"))
            o.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            o.clicked.connect(lambda: win.ouvrir(self.i))
            lay.addWidget(o, 0, Qt.AlignmentFlag.AlignTop)

    def set_on(self, on, lecture=False):
        self.setProperty("on", bool(on))
        base = " · ".join(x for x in (self.art.get("source", ""), depuis(self.art.get("date", ""))) if x)
        self.m.setText(base + ("  ·  🔊 " + tr("en lecture") if on and lecture else ""))
        for w in (self, self.t, self.m):
            w.style().unpolish(w)
            w.style().polish(w)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.win.lire_depuis(self.i)

    def mouseDoubleClickEvent(self, e):
        self.win.ouvrir(self.i)


class Deplacable:
    """Fenêtre sans bord qu'on déplace en la tirant et qu'on agrandit par les bords ou les coins.
    (À mettre avant QWidget : class MaFenetre(Deplacable, QWidget).)"""
    TAILLE_CLE = "fenetre_taille"
    _drag = None
    _resize = None

    def _touche(self):
        pass

    # ------------------------------------------------------------ déplacer / agrandir la fenêtre
    BORD = 8

    def _bords(self, pos):
        b, r = self.BORD, self.rect()
        e = Qt.Edge(0)
        if pos.x() <= b:
            e |= Qt.Edge.LeftEdge
        elif pos.x() >= r.width() - b:
            e |= Qt.Edge.RightEdge
        if pos.y() <= b:
            e |= Qt.Edge.TopEdge
        elif pos.y() >= r.height() - b:
            e |= Qt.Edge.BottomEdge
        return e

    def _curseur(self, e):
        C = Qt.CursorShape
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if e in (L | T, R | B):
            return C.SizeFDiagCursor
        if e in (R | T, L | B):
            return C.SizeBDiagCursor
        if e & (L | R):
            return C.SizeHorCursor
        if e & (T | B):
            return C.SizeVerCursor
        return C.ArrowCursor

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self._touche()
        pos = e.position().toPoint()
        bords = self._bords(pos)
        wh = self.windowHandle()
        if bords:
            if not (wh and wh.startSystemResize(bords)):         # Wayland/KDE : c'est le système qui agrandit
                self._resize = (bords, e.globalPosition().toPoint(), self.geometry())
            return
        if not (wh and wh.startSystemMove()):
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        gp = e.globalPosition().toPoint()
        rs = getattr(self, "_resize", None)
        if rs and e.buttons() & Qt.MouseButton.LeftButton:
            bords, p0, g0 = rs
            d = gp - p0
            g = QRect(g0)
            if bords & Qt.Edge.LeftEdge:
                g.setLeft(min(g0.left() + d.x(), g0.right() - self.minimumWidth()))
            if bords & Qt.Edge.RightEdge:
                g.setRight(g0.right() + d.x())
            if bords & Qt.Edge.TopEdge:
                g.setTop(min(g0.top() + d.y(), g0.bottom() - self.minimumHeight()))
            if bords & Qt.Edge.BottomEdge:
                g.setBottom(g0.bottom() + d.y())
            self.setGeometry(g)
            return
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(gp - self._drag)
            return
        self.setCursor(self._curseur(self._bords(e.position().toPoint())))

    def mouseReleaseEvent(self, e):
        self._drag = None
        self._resize = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.isVisible():
            self.comp.cfg[self.TAILLE_CLE] = [self.width(), self.height()]
            if not hasattr(self, "_save_t"):
                self._save_t = QTimer(self)
                self._save_t.setSingleShot(True)
                self._save_t.timeout.connect(lambda: getattr(self.comp, "save_cfg", lambda: None)())
            self._save_t.start(800)



class NewsWindow(Deplacable, QWidget):
    TAILLE_CLE = "actu_taille"
    """comp : le compagnon (say, is_speaking, _bg, cfg…) ; suivi, media : les modules d'actu."""

    def __init__(self, comp, suivi, media):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.comp, self.suivi, self.media = comp, suivi, media
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(CSS)
        self.setWindowTitle(tr("L'actu"))
        self.resize(470, 560)
        self.items, self.lignes = [], []
        self.cat, self.gen, self.cache = "", 0, {}
        self.lang = "fr"
        self.idx, self.playing, self.sid, self.said_at = -1, False, -1, 0.0
        self.fin_at = 0.0
        self.intro = ""
        self._drag = None
        self._resize = None

        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.titre = QLabel("📰 " + tr("L'actu"))
        self.titre.setObjectName("titre")
        top.addWidget(self.titre)
        self.date = QLabel("")
        self.date.setObjectName("date")
        top.addWidget(self.date)
        top.addStretch()
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setToolTip(tr("Fermer"))
        x.clicked.connect(self.fermer)
        top.addWidget(x)
        lay.addLayout(top)

        # catégories : sur plusieurs lignes, toutes visibles
        self.chips_box = QWidget()
        self.chips_box.setObjectName("fond")
        self.chips = FlowLayout(self.chips_box)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        self.chip_btn = {}
        lay.addWidget(self.chips_box)

        # articles
        self.liste_box = QWidget()
        self.liste_box.setObjectName("fond")
        self.liste = QVBoxLayout(self.liste_box)
        self.liste.setContentsMargins(0, 0, 4, 0)
        self.liste.setSpacing(2)
        self.liste.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.liste_box)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().setObjectName("fond")
        lay.addWidget(self.scroll, 1)

        bas = QHBoxLayout()
        self.b_pause = QPushButton("⏸ " + tr("Pause"))
        self.b_pause.setObjectName("btn")
        self.b_pause.clicked.connect(self.pause_reprendre)
        bas.addWidget(self.b_pause)
        self.b_suiv = QPushButton("⏭ " + tr("Suivant"))
        self.b_suiv.setObjectName("btn")
        self.b_suiv.clicked.connect(self.suivant)
        bas.addWidget(self.b_suiv)
        bas.addStretch()
        self.b_ouvrir = QPushButton("↗ " + tr("Ouvrir"))
        self.b_ouvrir.setObjectName("btn")
        self.b_ouvrir.clicked.connect(lambda: self.ouvrir(max(self.idx, 0)))
        bas.addWidget(self.b_ouvrir)
        grip = QSizeGrip(self)
        grip.setToolTip(tr("Agrandir"))
        bas.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(bas)
        self.setMinimumSize(360, 340)
        self.setMouseTracking(True)
        cadre.setMouseTracking(True)
        t = self.comp.cfg.get("actu_taille")
        if isinstance(t, (list, tuple)) and len(t) == 2:
            self.resize(max(360, int(t[0])), max(340, int(t[1])))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(300)

    # ------------------------------------------------------------ catégories
    def categories(self):
        """[(clé, libellé)] : Pour toi (tes sites), À la une, puis les sujets."""
        out = []
        if any(s.get("suivre", True) for s in self.comp.cfg.get("sites", [])):
            out.append(("toi", "⭐ " + tr("Pour toi")))
        out.append(("une", "📰 " + tr("À la une")))
        for k, (lab, _q) in self.suivi.SUJETS.items():
            out.append((k, lab))
        return out

    def _emoji(self, cat):
        lab = dict(self.categories()).get(cat) or ""
        if cat.startswith("q:"):
            return "🔎"
        return lab.split(" ", 1)[0] if lab and not lab[0].isalnum() else "📰"

    def _build_chips(self, extra=None):
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                self.chip_group.removeButton(w)
                w.deleteLater()
        self.chip_btn = {}
        cats = self.categories()
        if extra:
            cats.insert(0, extra)
        for k, lab in cats:
            b = QPushButton(tr(lab))
            if k == "sport":                            # « Sport » veut dire « séance de sport » ailleurs dans Viki
                lg = langue_actu(self.comp.cfg)
                b.setText("⚽ " + {"en": "Sports", "es": "Deportes", "ru": "Спорт", "zh": "体育", "ja": "スポーツ",
                                   "hi": "खेल"}.get(lg, "Sport"))
                b.setProperty("no_i18n", True)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, k=k: self.choisir(k, lire=True))
            self.chip_group.addButton(b)
            self.chips.addWidget(b)
            self.chip_btn[k] = b

    def cat_pour(self, sujet):
        """Le sujet demandé (« sport », « jeux vidéo »…) -> une catégorie, sinon une recherche « q:… »."""
        if not sujet:
            return "toi" if any(s.get("suivre", True) for s in self.comp.cfg.get("sites", [])) else "une"
        import unicodedata

        def sa(t):
            return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
        q = sa(sujet).strip()
        for k, (lab, query) in self.suivi.SUJETS.items():
            mots = [sa(lab.split(" ", 1)[-1]), sa(tr(lab.split(" ", 1)[-1]))] + \
                [sa(w) for w in query.replace(" OR ", "|").split("|")] + [k] + \
                [sa(v) for v in REQ.get(k, {}).values() if len(v) > 2]
            if any(q == m or (len(q) > 3 and (q in m or m in q)) for m in mots):
                return k
        return "q:" + sujet.strip()

    # ------------------------------------------------------------ ouverture
    def montrer(self, sujet="", lire=True):
        cat = self.cat_pour(sujet)
        extra = (cat, "🔎 " + cat[2:]) if cat.startswith("q:") else None
        self._build_chips(extra)
        self.date.setText(datetime.date.today().strftime("%d/%m"))
        self.placer()
        self.show()
        self.raise_()
        self.choisir(cat, lire=lire)

    def placer(self):
        """À côté d'elle : à gauche si la place le permet, sinon à droite ; en bas aligné sur son corps."""
        c = self.comp
        try:
            r = c.body_rect()
            g = c.mapToGlobal(r.topLeft())
            body_l, body_r, body_b = g.x(), g.x() + r.width(), g.y() + r.height()
            scr = (c.screen() or QApplication.primaryScreen()).availableGeometry()
        except Exception:
            return
        w, h = min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 40)
        self.resize(w, h)
        gap = 16
        rb = getattr(c, "ronds_bar", None)
        if rb is not None and rb.isVisible():          # ne pas couvrir ses ronds
            body_l = min(body_l, rb.geometry().left())
            body_r = max(body_r, rb.geometry().right())
        x = body_l - w - gap if body_l - w - gap >= scr.left() else body_r + gap
        x = max(scr.left() + 8, min(x, scr.right() - w - 8))
        y = max(scr.top() + 8, min(body_b - h, scr.bottom() - h - 8))
        self.move(QPoint(int(x), int(y)))

    def choisir(self, cat, lire=True):
        self.stop_lecture()
        self.cat = cat
        b = self.chip_btn.get(cat)
        if b:
            b.setChecked(True)
        self.gen += 1
        gen = self.gen
        self.lang = langue_actu(self.comp.cfg)
        hit = self.cache.get((cat, self.lang))
        if hit and time.monotonic() - hit[0] < CACHE_S:
            return self._remplir(gen, hit[1], lire)
        self._etat("⏳ " + tr("Je cherche les dernières nouvelles…"))
        lang = self.lang = langue_actu(self.comp.cfg)
        sites = [dict(s) for s in self.comp.cfg.get("sites", [])]
        suivi, media = self.suivi, self.media

        def work():
            if cat == "toi":
                arts, _src = media.headlines(sites, suivi.site_items, "", MAX_ITEMS)
                return [dict(a, source=a.get("source") or site) for site, a in arts]
            if cat == "une":
                return suivi.news_rich("", MAX_ITEMS, lang)
            if cat.startswith("q:"):
                q = cat[2:]
                arts, _src = media.headlines(sites, suivi.site_items, q, MAX_ITEMS) if sites else ([], "")
                if arts:
                    return [dict(a, source=a.get("source") or site) for site, a in arts]
                return suivi.news_rich(q, MAX_ITEMS, lang)
            q = REQ.get(cat, {}).get(lang) if lang != "fr" else None
            return suivi.news_rich(q or suivi.SUJETS[cat][1].replace(" OR ", " "), MAX_ITEMS, lang)

        def then(res):
            if gen != self.gen:
                return
            if isinstance(res, Exception) or not res:
                self._etat("😕 " + tr("Je n'ai rien trouvé pour le moment. Tu es bien connecté à internet ?"))
                if lire:
                    self._dire(self._dit("err" if isinstance(res, Exception) else "rien"))
                return
            self.cache[(cat, lang)] = (time.monotonic(), res)
            self._remplir(gen, res, lire)
        self.comp._bg(work, then)

    def _etat(self, txt):
        self._vider()
        lab = QLabel(txt)
        lab.setObjectName("etat")
        lab.setWordWrap(True)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.liste.insertWidget(0, lab)

    def _vider(self):
        self.lignes = []
        while self.liste.count() > 1:
            w = self.liste.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _remplir(self, gen, arts, lire):
        self._vider()
        self.items = list(arts)[:MAX_ITEMS]
        emoji = self._emoji(self.cat)
        coul = TEINTES.get(self.cat, "#7F77DD")
        for i, a in enumerate(self.items):
            ln = Ligne(self, i, a, emoji, coul)
            self.liste.insertWidget(i, ln)
            self.lignes.append(ln)
        self.comp._last_articles = [(a.get("source", ""), a) for a in self.items]
        self._images(gen, emoji, coul)
        if lire:
            lab = dict(self.categories()).get(self.cat, "")
            nom = self.cat[2:] if self.cat.startswith("q:") else tr(lab.split(" ", 1)[-1]) if lab else ""
            k = self.cat if self.cat in ("toi", "une") else "q" if self.cat.startswith("q:") else "cat"
            self.intro = self._dit(k).format(nom.lower() if k == "cat" and self.lang in ("fr", "en", "es", "ru")
                                             else nom)
            self.lire_depuis(0)

    def _images(self, gen, emoji, coul):
        """Les images arrivent une par une, sans bloquer la fenêtre."""
        suivi = self.suivi
        for i, a in enumerate(self.items):
            def work(a=a):
                """L'image du flux, sinon celle de la page de l'article ; on garde la 1re que Qt sait afficher."""
                lien = a.get("lien") or ""
                essais = [a.get("image") or ""]
                notes = []
                for url in essais + ["og"]:
                    etape = "page de l'article" if url == "og" else "image du flux"
                    try:
                        if url == "og":
                            url = suivi.og_image(lien) if lien else ""
                        if not url:
                            notes.append(f"{etape} : rien")
                            continue
                        # i0.wp.com (le cache d'images de WordPress) répond parfois 404 : on essaie l'original
                        m = re.match(r"https?://i\d\.wp\.com/([^?]+)", url)
                        for u in [url] + (["https://" + m.group(1)] if m else []) + \
                                ([url.split("?")[0]] if "?" in url and not m else []):
                            try:
                                try:
                                    data = suivi.fetch_image(u, referer=lien)
                                except TypeError:                 # vieux suivi.py
                                    data = suivi.fetch_image(u)
                                if data and not QImage.fromData(data).isNull():
                                    return data
                                notes.append(f"{etape} : illisible ({len(data or b'')} o) {u[:90]}")
                            except Exception as e:
                                notes.append(f"{etape} : {type(e).__name__} {str(e)[:60]} {u[:90]}")
                    except Exception as e:
                        notes.append(f"{etape} : {type(e).__name__} {str(e)[:80]} {url[:90]}")
                print("Actu, pas d'image pour « " + a.get("titre", "")[:40] + " » : " + " | ".join(notes),
                      file=sys.stderr)
                return None

            def then(data, i=i):
                if gen != self.gen or i >= len(self.lignes) or isinstance(data, Exception) or not data:
                    return
                self.lignes[i].img.setPixmap(vignette(data, coul, emoji))
            self.comp._bg(work, then)

    # ------------------------------------------------------------ lecture
    def _nb_lus(self):
        return max(1, min(len(self.items), int(self.comp.cfg.get("actu_nb", 4) or 4)))

    def _surligner(self):
        for j, ln in enumerate(self.lignes):
            ln.set_on(j == self.idx, self.playing)
        if 0 <= self.idx < len(self.lignes):
            self.scroll.ensureWidgetVisible(self.lignes[self.idx], 0, 30)
        self.b_pause.setText(("⏸ " + tr("Pause")) if self.playing else ("▶ " + tr("Lire")))

    def lire_depuis(self, i):
        if not (0 <= i < len(self.items)):
            return
        self.idx, self.playing, self.fin_at = i, True, 0.0
        a = self.items[i]
        src = a.get("source", "")
        txt = (self.intro or "") + (f"{src} : " if src else "") + a.get("titre", "").rstrip(".") + "."
        self.intro = ""
        if self.lang in ("zh", "ja"):
            txt = txt.replace(" : ", "：", 1)
        elif self.lang != "fr":
            txt = txt.replace(" : ", ": ", 1)
        self._dire(txt)
        self.sid = self.comp.speech_id
        self.said_at = time.monotonic()
        self._surligner()

    def _dit(self, k):
        return DIT.get(getattr(self, "lang", "fr"), DIT["en"]).get(k, DIT["fr"][k])

    def _dire(self, txt):
        """Elle le dit avec la voix de la langue des titres (si tu l'as installée)."""
        lang = getattr(self, "lang", "fr")
        self.comp._tts_lang = None if lang == "fr" else lang
        self.comp.say(txt)

    def _fin_voix(self):
        self.comp._tts_lang = None

    def stop_lecture(self):
        if self.playing and self.comp.speech_id == self.sid:
            c = self.comp
            c.sq = []
            c.speech_id += 1                          # annule la phrase en cours de fabrication
            c.synth_pending = None
            try:
                c._stop_audio()
            except Exception:
                pass
            c.bubble_until = 0
            c.lip_env = []
        self.playing = False
        self._fin_voix()
        self._surligner()

    def pause_reprendre(self):
        if self.playing:
            self.stop_lecture()
        else:
            self.lire_depuis(self.idx if self.idx >= 0 else 0)

    def suivant(self):
        if self.idx + 1 < len(self.items):
            self.stop_lecture()
            self.lire_depuis(self.idx + 1)

    def ouvrir(self, i):
        if 0 <= i < len(self.items) and self.items[i].get("lien"):
            QDesktopServices.openUrl(QUrl(self.items[i]["lien"]))

    def _tick(self):
        if not self.isVisible():
            return
        now = time.monotonic()
        if self.playing:
            if self.comp.speech_id != self.sid:       # tu lui as parlé entre-temps : on s'arrête là
                self.playing = False
                self._fin_voix()
                self._surligner()
                return
            if now - self.said_at < 1.2 or self.comp.is_speaking(now):
                return
            if self.idx + 1 < self._nb_lus():
                return self.lire_depuis(self.idx + 1)
            self.playing = False
            self._fin_voix()
            self.fin_at = now
            self._surligner()
            return
        # fin de lecture : elle se range toute seule au bout de 40 s, sauf si la souris est dessus
        if self.fin_at and now - self.fin_at > 40:
            if self.underMouse():
                self.fin_at = now
            else:
                self.fermer()

    def fermer(self):
        self.stop_lecture()
        self.fin_at = 0.0
        self.gen += 1
        self.hide()

    def _touche(self):
        self.fin_at = 0.0 if not self.playing else self.fin_at

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.fermer()


# ------------------------------------------------------------------ boîtes de question, au même style
CSS_BOITE = CSS + """
#msg { font-size: 13px; color: #ece9f2; }
#gros { font-size: 30px; }
QPushButton#oui { background: #7F77DD; color: #ffffff; border: 1px solid #7F77DD; border-radius: 8px;
                  padding: 7px 16px; font-size: 13px; font-weight: 600; }
QPushButton#oui:hover { background: #8f88e6; }
QPushButton#danger { background: #c4413f; color: #ffffff; border: 1px solid #c4413f; border-radius: 8px;
                     padding: 7px 16px; font-size: 13px; font-weight: 600; }
QPushButton#non { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px;
                  padding: 7px 16px; font-size: 13px; }
QPushButton#non:hover { background: #343040; }
QLineEdit, QComboBox { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px;
                       padding: 6px 9px; font-size: 13px; }
QLineEdit:focus, QComboBox:focus { border-color: #7F77DD; }
QComboBox QAbstractItemView { background: #2a2731; color: #ece9f2; selection-background-color: #7F77DD; }
QPlainTextEdit, QTextEdit { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px;
                            padding: 6px; font-size: 13px; }
QPlainTextEdit:focus, QTextEdit:focus { border-color: #7F77DD; }
QCheckBox { color: #ece9f2; font-size: 13px; spacing: 8px; }
#champ { color: #9b96a8; font-size: 12px; }
"""


class Boite(Deplacable, QDialog):
    """Une question claire, dans le même style que les fenêtres de Viki (pas la boîte grise du système)."""

    def __init__(self, parent, titre, texte, boutons, icone="❓"):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)              # toujours sombre et lisible, quel que soit le thème
        self.setStyleSheet(CSS_BOITE)
        self.setWindowTitle(titre)
        self.setModal(True)
        self.valeur = None
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        top = QHBoxLayout()
        t = QLabel(titre)
        t.setObjectName("titre")
        top.addWidget(t)
        top.addStretch()
        x = QPushButton("✕")
        x.setObjectName("x")
        x.clicked.connect(self.reject)
        top.addWidget(x)
        lay.addLayout(top)
        mid = QHBoxLayout()
        mid.setSpacing(14)
        if icone:
            ic = QLabel(icone)
            ic.setObjectName("gros")
            mid.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        msg = QLabel(texte)
        msg.setObjectName("msg")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setMinimumWidth(360)
        mid.addWidget(msg, 1)
        lay.addLayout(mid)
        bas = QHBoxLayout()
        bas.addStretch()
        for lab, val, genre in boutons:
            b = QPushButton(lab)
            b.setObjectName(genre)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, v=val: self._fin(v))
            bas.addWidget(b)
            if genre in ("oui", "danger"):
                b.setDefault(True)
        lay.addLayout(bas)
        self.setMaximumWidth(620)

    def ajouter_champ(self, libelle, w):
        """Ajoute un champ (QLineEdit, QComboBox…) au-dessus des boutons."""
        lay = self.findChild(QFrame, "cadre").layout()
        lab = QLabel(tr(libelle))
        lab.setObjectName("champ")
        lay.insertWidget(lay.count() - 1, lab)
        lay.insertWidget(lay.count() - 1, w)
        return w

    def _fin(self, v):
        self.valeur = v
        self.accept()


def demander(parent, titre, texte, oui="Oui", non="Non", icone="❓", danger=False):
    """Question oui / non -> True ou False."""
    b = Boite(parent, tr(titre), texte, [(tr(non), False, "non"), (tr(oui), True, "danger" if danger else "oui")],
              icone)
    b.exec()
    return bool(b.valeur)


def informer(parent, titre, texte, icone="ℹ️"):
    b = Boite(parent, tr(titre), texte, [(tr("OK"), True, "oui")], icone)
    b.exec()
