#!/usr/bin/env python3
"""Fenêtre de réglages du compagnon : toutes les options au même endroit, rangées par thème."""
import json
import subprocess
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QIcon
try:
    import pomme
except Exception:
    pomme = None
from PyQt6.QtCore import QTime, QTimer
from PyQt6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
                             QTimeEdit,
                             QListWidget, QListWidgetItem, QProgressBar, QPushButton, QScrollArea, QSlider,
                             QStackedWidget, QVBoxLayout, QWidget)

ROSE = "#d0457a"
try:
    import themes as _th
except Exception:                       # themes.py absent : tout reste rose
    _th = None


def _c(hexc):
    """Couleur dessinée à la main, dans le thème choisi."""
    return _th.color(hexc) if _th else hexc

# Familles du menu de gauche (par titre de page). Une page inconnue va dans « Viki ».
FAMILLES = [
    ("ELLE", ("Personnage", "Apparence", "Voix", "Invitées")),
    ("DISCUTER", ("Discussion", "Langues", "Micro et écoute")),
    ("OUTILS", ("Au quotidien", "Actions rapides", "Assistant")),
    ("TON PC", ("Gestion du PC", "Développeur")),
    ("VIKI", ("Comportement", "Accessibilité", "Performances", "Sauvegarde et aide")),
]
SIMPLES = ("Accueil", "Personnage", "Voix", "Discussion", "Au quotidien", "Langues", "Sauvegarde et aide")
STYLES = [("Par familles (menu groupé)", "familles"), ("Accueil à tuiles", "accueil"),
          ("Simple (l'essentiel, « Tout voir » pour le reste)", "simple")]


def famille_de(title):
    for fam, titles in FAMILLES:
        if title in titles:
            return fam
    return "VIKI"


class _Signal(QObject):
    done = pyqtSignal(object, object)          # (rappel, résultat) : retour d'un fil vers l'interface

STYLE = """
#reglages QLabel, #reglages QCheckBox, #reglages QRadioButton { color: #3d2733; }
QWidget#reglages, QWidget#page { background: #fbf6f9; }
QListWidget#menu { background: #ffffff; border: none; border-right: 1px solid #f1dfe8;
                   padding: 10px 6px; font-size: 14px; outline: 0; }
QListWidget#menu::item { padding: 6px 12px; margin: 1px 4px; border-radius: 10px; color: #4a3540; }
QListWidget#menu::item:hover { background: #fdf0f5; }
QListWidget#menu::item:selected { background: #ffe1ec; color: #b0336a; font-weight: bold; }
QListWidget#menu::item:disabled { background: transparent; padding: 0px; margin: 0px; }
QPushButton#tuile { background: #ffffff; border: 1px solid #f1dfe8; border-radius: 12px; padding: 10px 12px;
    text-align: left; color: #4a3540; }
QPushButton#tuile:hover { background: #fdf0f5; border-color: #eab3cb; }
QFrame#carte { background: #ffffff; border: 1px solid #f1dfe8; border-radius: 14px; }
QLabel#titrePage { font-size: 22px; font-weight: bold; color: #3d2733; }
QLabel#sousTitre { font-size: 13px; color: #8d7482; }
QLabel#titreCarte { font-size: 13px; font-weight: bold; color: #b0336a; letter-spacing: 0.5px; }
QLabel#nom { font-size: 14px; color: #3d2733; }
QLabel#aide { font-size: 12px; color: #9a8290; }
QLabel#info { font-size: 13px; color: #5c4652; background: #fdf0f5; border-radius: 10px; padding: 10px; }
QSpinBox, QTimeEdit { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; padding: 4px 8px;
                      min-height: 22px; color: #3d2733; }
QListWidget#liste { background: #fff; border: 1px solid #f1dfe8; border-radius: 10px; padding: 4px; }
QListWidget#liste::item { padding: 6px 8px; border-radius: 7px; color: #3d2733; }
QListWidget#liste::item:selected { background: #ffe1ec; color: #b0336a; }
QComboBox, QLineEdit { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; padding: 5px 10px;
                       min-height: 22px; color: #3d2733; }
QComboBox:hover, QLineEdit:focus { border-color: #d0457a; }
QComboBox QAbstractItemView { border: 1px solid #e7cfdb; selection-background-color: #ffe1ec;
                              selection-color: #b0336a; background: #fff; color: #3d2733; }
QPushButton { background: #fff; border: 1px solid #e7cfdb; border-radius: 10px; padding: 7px 14px;
              color: #4a3540; }
QPushButton:hover { background: #fdf0f5; border-color: #d0457a; }
QPushButton#principal { background: #d0457a; color: white; border: none; font-weight: bold; }
QPushButton#principal:hover { background: #b9386b; }
QSlider::groove:horizontal { height: 6px; background: #f1dfe8; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #e889ad; border-radius: 3px; }
QSlider::handle:horizontal { background: #d0457a; width: 18px; height: 18px; margin: -6px 0;
                             border-radius: 9px; }
QScrollArea { border: none; background: transparent; }
QProgressBar { background: #f6e6ee; border: none; border-radius: 7px; height: 14px; text-align: center;
               color: #6b4a5a; font-size: 11px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f0a3c1, stop:1 #d0457a);
                      border-radius: 7px; }
QScrollBar:vertical { width: 14px; background: #f6e6ee; border-radius: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: #e889ad; border-radius: 5px; min-height: 40px; margin: 2px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed { background: #d0457a; }
QScrollBar:horizontal { height: 14px; background: #f6e6ee; border-radius: 7px; margin: 2px; }
QScrollBar::handle:horizontal { background: #e889ad; border-radius: 5px; min-width: 40px; margin: 2px; }
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed { background: #d0457a; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class Switch(QAbstractButton):
    """Interrupteur arrondi (oui / non)."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self.anim = QPropertyAnimation(self, b"progress", self)
        self.anim.setDuration(140)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(46, 26)

    def _animate(self, on):
        self.anim.stop()
        self.anim.setStartValue(self._pos)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def get_pos(self):
        return self._pos

    def set_pos(self, v):
        self._pos = v
        self.update()

    progress = pyqtProperty(float, get_pos, set_pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor(_c("#e6d6de")), QColor(_c(ROSE))
        k = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                     int(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * k
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawEllipse(QRectF(x, r.top() + 4, d, d))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class SettingsWindow(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.cfg = comp.cfg
        I = getattr(C, "i18n", None)
        self._t = I.tr if I else (lambda s: s)
        self.setObjectName("reglages")
        self.apple = bool(pomme) and pomme.actif(C, comp.cfg)          # look « Réglages du Mac »
        self.setStyleSheet(STYLE + (pomme.REGLAGES if self.apple else "") + self._arrow_css())
        self.verre = False
        if self.apple and comp.cfg.get("fenetres_verre", True):
            self._verre()
        self.setWindowTitle(f"Réglages — {comp.char.get('name', 'Viki')}")
        try:
            self.setWindowIcon(comp._face_icon())
        except Exception:
            pass
        try:                                   # assez grand pour voir tout le menu sans défiler
            from PyQt6.QtWidgets import QApplication
            av = (comp.screen() or QApplication.primaryScreen()).availableGeometry()
            self.resize(int(min(1180, av.width() * 0.9)), int(min(980, av.height() * 0.93)))
        except Exception:
            self.resize(1100, 900)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        head = QWidget()
        head.setObjectName("tete")
        head.setStyleSheet("QWidget#tete { background: %s; border-right: 1px solid %s; }"
                           % (("#f1e9ee", "#e6dae1") if self.apple else ("#ffffff", "#f1dfe8")))
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 16, 12, 6)
        face = QLabel()
        try:
            face.setPixmap(comp._face_icon().pixmap(46, 46))
        except Exception:
            pass
        face.setStyleSheet("border: none;")
        hl.addWidget(face)
        nm = QLabel(f"<b style='font-size:16px;color:#3d2733'>{comp.char.get('name', 'Viki')}</b>"
                    f"<br><span style='color:#9a8290'>{self._t('Réglages')}</span>")
        nm.setStyleSheet("border: none;")
        hl.addWidget(nm, 1)
        side.addWidget(head)
        sbox = QWidget()
        sbox.setObjectName("cherche")
        sbox.setStyleSheet("QWidget#cherche { background: %s; border-right: 1px solid %s; }"
                           % (("#f1e9ee", "#e6dae1") if self.apple else ("#ffffff", "#f1dfe8")))
        sl = QVBoxLayout(sbox)
        sl.setContentsMargins(10, 4, 10, 4)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎  Chercher un réglage…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._build_menu())
        self.search.returnPressed.connect(self._open_first_result)
        sl.addWidget(self.search)
        side.addWidget(sbox)
        self._pages, self._texts, self._building, self._show_all = [], {}, False, False
        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setFixedWidth(230)
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu.setTextElideMode(Qt.TextElideMode.ElideRight)
        if self.apple:
            self.menu.setIconSize(QSize(22, 22))
            self.search.setPlaceholderText(self._t("Chercher un réglage…"))
        side.addWidget(self.menu, 1)
        foot = QWidget()
        foot.setObjectName("pied")
        foot.setStyleSheet("QWidget#pied { background: %s; border-right: 1px solid %s; }"
                           % (("#f1e9ee", "#e6dae1") if self.apple else ("#ffffff", "#f1dfe8")))
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(12, 8, 12, 14)
        fl.setSpacing(4)
        sout = list(getattr(C, "SOUTIEN", ()))
        if sout:
            cap = QLabel("Soutenir mon travail 💖")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setStyleSheet("border: none; color: #9a8290; font-size: 9pt; padding-top: 2px;")
            fl.addWidget(cap)
            pill = ("QPushButton { background: #fdf0f5; color: #b0336a; border: 1px solid #f6d3e2; "
                    "border-radius: 11px; padding: 4px 8px; font-size: 9pt; } "
                    "QPushButton:hover { background: #fbe0ec; border-color: #eab3cb; }")

            def mk(ico, lab, url):
                b = QPushButton(f"{ico} {lab}")
                b.setToolTip(url)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(pill)
                b.clicked.connect(lambda _=False, u=url: C.open_link(u))
                return b
            don = (getattr(C, "DON_URL", "") or "").strip()
            if don.startswith("https://"):
                bd = mk("☕", "Faire un don", don)
                bd.setStyleSheet(pill.replace("#fdf0f5", "#fff4e0").replace("#b0336a", "#9a5a00")
                                 .replace("#f6d3e2", "#f3d7a6").replace("#fbe0ec", "#ffe8bf"))
                fl.addWidget(bd)
            fl.addWidget(mk(*sout[0]))
            if len(sout) > 1:
                row = QHBoxLayout()
                row.setSpacing(6)
                for s in sout[1:]:
                    row.addWidget(mk(*s))
                fl.addLayout(row)
        fl.addSpacing(8)
        bq = QPushButton("⏻  Quitter Viki")
        bq.setCursor(Qt.CursorShape.PointingHandCursor)
        bq.clicked.connect(lambda: (self.close(), comp.quit()))
        fl.addWidget(bq)
        side.addWidget(foot)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(230)
        root.addWidget(sw)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.menu.currentItemChanged.connect(self._on_item)
        # flèche « il y a d'autres pages plus bas » : sans elle, on rate facilement les dernières pages
        self._fleche = QPushButton("⌄", self.menu)
        self._fleche.setObjectName("flecheBas")
        self._fleche.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fleche.setToolTip(self._t("D'autres pages plus bas"))
        self._fleche.setFixedSize(46, 26)
        self._fleche.setStyleSheet("QPushButton#flecheBas { background: #d0457a; color: white; border: none; "
                                   "border-radius: 13px; font-size: 16px; font-weight: bold; padding: 0 0 4px 0; }"
                                   "QPushButton#flecheBas:hover { background: #b9386b; }")
        self._fleche.clicked.connect(lambda: self.menu.verticalScrollBar().setValue(
            self.menu.verticalScrollBar().value() + max(120, self.menu.viewport().height() - 80)))
        sb = self.menu.verticalScrollBar()
        sb.valueChanged.connect(lambda _v: self._maj_fleche())
        sb.rangeChanged.connect(lambda _a, _b: self._maj_fleche())
        if self.apple:                                   # petit « tic » en survolant le menu, comme le clic droit
            self.menu.setMouseTracking(True)
            self._survol_dernier = None
            self.menu.itemEntered.connect(self._survol)

        self._page_accueil()
        self._page_perso()
        if not C.GUEST:
            self._page_quotidien()
        self._page_actions()
        self._page_comportement()
        self._page_voix()
        self._page_discussion()
        self._page_langues()
        self._page_apparence()
        self._page_micro()
        if C.extras and not C.GUEST:
            self._page_assistant()
            if getattr(C, "dev", None):
                self._page_dev()
            if getattr(C, "gestionpc", None) and not C.IS_WIN:
                self._page_pc()
            self._page_invites()
        if getattr(C, "fun", None):
            self._page_access()
        self._page_perf()
        self._page_sauvegarde()
        self._fill_home()
        self._build_menu()
        self.select_page(0)

    # ------------------------------------------------------------- verre dépoli
    def _verre(self):
        """Fenêtre en verre dépoli : on voit (flouté par KDE) le bureau derrière. Sur GNOME : légère transparence."""
        from PyQt6.QtGui import QColor as _Q
        flou = bool(getattr(self.C, "flou_possible", lambda: False)())
        sheet = self.styleSheet()
        if _th:
            try:
                sheet = _th.css(sheet)
            except Exception:
                pass

        def rgba(hexc, a):
            c = _Q(_th.color(hexc) if _th else hexc)
            return f"rgba({c.red()},{c.green()},{c.blue()},{int(a * 255)})"
        a_page, a_side, a_carte = (0.78, 0.66, 0.82) if flou else (1.0, 1.0, 1.0)   # sans flou : opaque, lisible
        self._rgba_side = rgba("#f1e9ee", a_side)
        sheet += (f"\nQWidget#reglages {{ background: transparent; }}"
                  f"\nQWidget#page {{ background: {rgba('#f7f2f5', a_page)}; }}"
                  f"\nQListWidget#menu {{ background: {self._rgba_side}; }}"
                  f"\nQFrame#carte {{ background: {rgba('#ffffff', a_carte)}; }}"
                  "\nQStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget#qt_scrollarea_viewport "
                  "{ background: transparent; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)
        self.setStyleSheet(sheet)
        self.verre = True

    def showEvent(self, e):
        super().showEvent(e)
        from PyQt6.QtCore import QTimer as _T0
        _T0.singleShot(0, self._maj_fleche)
        if self.verre:
            for nm in ("tete", "cherche", "pied"):
                w = self.findChild(QWidget, nm)
                if w is not None:
                    w.setProperty("sans_theme", True)
                    w.setStyleSheet(f"QWidget#{nm} {{ background: {self._rgba_side}; border: none; }}")
            for sc in self.findChildren(QScrollArea):
                sc.viewport().setAutoFillBackground(False)
            fk = getattr(self.C, "flou_kde", None)
            if fk:
                from PyQt6.QtCore import QTimer as _T
                _T.singleShot(50, lambda: fk(self))

    def _maj_fleche(self):
        f = getattr(self, "_fleche", None)
        if f is None:
            return
        try:
            from PyQt6 import sip as _sip
            if _sip.isdeleted(f) or _sip.isdeleted(self.menu):
                return
        except Exception:
            pass
        sb = self.menu.verticalScrollBar()
        reste = sb.maximum() - sb.value()
        f.setVisible(sb.maximum() > 0 and reste > 8)
        f.move((self.menu.width() - f.width()) // 2, self.menu.height() - f.height() - 8)
        f.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        from PyQt6.QtCore import QTimer as _T
        _T.singleShot(0, self._maj_fleche)

    def _survol(self, it):
        if it is None or it is self._survol_dernier or not (it.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        self._survol_dernier = it
        try:
            self.comp._son_menu()
        except Exception:
            pass

    # ------------------------------------------------------------- navigation
    def _build_menu(self):
        """Remplit le menu de gauche selon le style choisi et la recherche. Chaque élément garde
        l'index de sa page dans la pile (les en-têtes et « Tout voir » n'en ont pas)."""
        cur = self.current_page()
        self._building = True
        self.menu.clear()
        style = self.cfg.get("reglages_style", "familles")
        q = self.search.text().strip().lower()
        simple = style == "simple" and not self._show_all and not q
        scores = {i: self._score(i, q) for i in range(len(self._pages))} if q else {}
        vis = [i for i, p in enumerate(self._pages)
               if (not q or scores[i] > 0) and (not simple or p["title"] in SIMPLES)]
        if q:                                            # les pages les plus pertinentes d'abord
            vis.sort(key=lambda i: -scores[i])

        def add(i):
            p = self._pages[i]
            if self.apple:
                it = QListWidgetItem(QIcon(pomme.tuile(self.C, p["emoji"], pomme.TUILES.get(p["title"], "#8e8e93"), 22)),
                                     "  " + self._t(p["title"]))
            else:
                it = QListWidgetItem(f"{p['emoji']}   {self._t(p['title'])}")
            it.setToolTip(self._t(p["title"]))
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.menu.addItem(it)

        def header(txt):
            it = QListWidgetItem()
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            lab = QLabel((txt[:1] + txt[1:].lower()).replace(" pc", " PC") if self.apple else txt)
            lab.setStyleSheet("color: #a08b97; font-size: 9pt; font-weight: bold; padding: 0px 8px; "
                              "background: transparent;" if self.apple else
                              "color: #b49aa7; font-size: 8pt; font-weight: bold; letter-spacing: 1px; "
                              "padding: 0px 4px; background: transparent;")
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            it.setSizeHint(QSize(200, 34))
            self.menu.addItem(it)
            self.menu.setItemWidget(it, lab)

        if q and vis:                                     # recherche : une liste classée, la meilleure en premier
            header("RÉSULTATS")
            for i in vis:
                add(i)
            self._building = False
            self._select_item(vis[0] if cur not in vis else cur)
            return
        home = [i for i in vis if self._pages[i]["title"] == "Accueil"]
        for i in home:
            add(i)
        order = [fam for fam, _ in FAMILLES]
        grouped = style == "familles" or q
        for fam in order:
            idx = [i for i in vis if i not in home and famille_de(self._pages[i]["title"]) == fam]
            if idx and grouped:
                header(fam)
            for i in idx:
                add(i)
        if q and not vis:
            header("AUCUN RÉSULTAT")
        if simple:
            it = QListWidgetItem("➕   " + self._t("Tout voir"))
            it.setData(Qt.ItemDataRole.UserRole, -1)
            it.setToolTip("Afficher tous les réglages")
            self.menu.addItem(it)
        self._building = False
        self._select_item(cur)

    def _select_item(self, idx):
        for r in range(self.menu.count()):
            it = self.menu.item(r)
            if it.data(Qt.ItemDataRole.UserRole) == idx:
                self._building = True
                self.menu.setCurrentItem(it)
                self._building = False
                return True
        return False

    def _on_item(self, cur, _prev=None):
        if self._building or cur is None:
            return
        d = cur.data(Qt.ItemDataRole.UserRole)
        if d is None:
            return
        if d == -1:                                   # « Tout voir »
            self._show_all = True
            self._build_menu()
            return
        self.stack.setCurrentIndex(d)

    def _open_first_result(self):
        for r in range(self.menu.count()):
            d = self.menu.item(r).data(Qt.ItemDataRole.UserRole)
            if d is not None and d >= 0:
                self.select_page(d)
                return

    # mots courants -> les pages où ils se trouvent (la recherche comprend aussi ces mots-là)
    SYNONYMES = {
        "son": "voix volume", "volume": "voix", "parler": "voix", "parle": "voix", "muet": "muette voix",
        "theme": "apparence couleurs", "couleur": "couleurs apparence", "sombre": "couleurs nuit apparence",
        "clair": "couleurs apparence", "transparent": "verre apparence", "fond": "decor apparence",
        "ronds": "ronds raccourcis apparence", "rond": "ronds raccourcis", "raccourci": "actions rapides ronds",
        "bouton": "ronds actions", "menu": "style du menu clic droit", "clic": "clic droit menu",
        "demarrage": "demarrer avec le pc accueil", "allumage": "demarrer avec le pc", "lancement": "demarrer",
        "maj": "mises a jour accueil", "update": "mises a jour accueil", "version": "mises a jour accueil",
        "mise": "mises a jour accueil", "jour": "mises a jour au quotidien",
        "ia": "discussion intelligence modele", "ai": "discussion", "cerveau": "discussion", "modele": "discussion modele",
        "ollama": "discussion", "chatgpt": "discussion en ligne", "memoire": "discussion souvenirs",
        "langue": "langues", "anglais": "langues", "traduction": "langues traduire",
        "micro": "micro ecoute", "ecoute": "micro", "reconnaissance": "micro",
        "musique": "musique au quotidien", "spotify": "musique", "deezer": "musique", "youtube": "musique chaine",
        "meteo": "meteo au quotidien", "ville": "meteo", "actu": "actus suivis", "news": "actus", "infos": "actus",
        "rappel": "rappels assistant", "agenda": "agenda assistant", "mail": "mails assistant",
        "sauvegarde": "sauvegarde", "backup": "sauvegarde", "export": "sauvegarde",
        "lent": "performances fluidite", "lag": "performances", "saccade": "performances", "perf": "performances", "fps": "fluidite performances",
        "batterie": "batterie performances", "rame": "performances",
        "police": "accessibilite texte plus grand", "ecriture": "accessibilite", "taille": "taille personnage texte",
        "malvoyant": "accessibilite", "daltonien": "contraste accessibilite",
        "personnage": "personnage", "tenue": "tenues personnage", "vetement": "tenues apparence",
        "cheveux": "apparence", "invite": "invitees", "amie": "invitees",
        "securite": "gestion du pc securite", "virus": "securite", "disque": "disques gestion du pc",
        "tor": "gestion du pc vie privee tor", "prive": "vie privee", "code": "developpeur", "github": "developpeur",
        "bavarde": "bavarde phrases comportement", "phrases": "phrases bavarde comportement",
    }

    @staticmethod
    def _sans_accents(t):
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")

    MOTS_VIDES = {"de", "la", "le", "les", "du", "des", "un", "une", "et", "en", "pour", "mon", "ma", "mes", "sa",
                  "ses", "ton", "ta", "tes", "au", "aux", "l", "d", "a", "je", "veux", "comment", "ou", "est", "elle",
                  "qui", "que", "quoi", "the", "of", "to", "my", "how"}

    def _score(self, i, q):
        """Pertinence d'une page : chaque mot doit s'y trouver (ou un synonyme, ou un mot proche).
        Le titre de la page compte plus, puis les synonymes, puis le nombre de fois où le mot apparaît."""
        import difflib
        import re as _re
        if not hasattr(self, "_mots"):
            self._mots = {}
        if i not in self._mots:
            txt = self._sans_accents(self._page_text(i))
            self._mots[i] = (txt, set(_re.findall(r"[a-z0-9]{2,}", txt)))
        txt, mots = self._mots[i]
        titre = self._sans_accents(self._pages[i]["title"] + " " + self._t(self._pages[i]["title"]))
        ws = [w for w in _re.findall(r"[a-z0-9]+", self._sans_accents(q)) if w not in self.MOTS_VIDES]
        if not ws:
            ws = _re.findall(r"[a-z0-9]+", self._sans_accents(q))
        total = 0.0
        for w in ws:
            debut = _re.compile(r"\b" + _re.escape(w))
            syn = (self.SYNONYMES.get(w) or self.SYNONYMES.get(w.rstrip("s")) or "").split()
            sc = 0.0
            if debut.search(titre):
                sc = 6
            elif syn and any(_re.search(r"\b" + _re.escape(x), titre) for x in syn):
                sc = 5
            else:
                n = len(debut.findall(txt))
                if n:
                    sc = 2 + min(2.0, n * 0.35)
                elif len(w) >= 4 and w in txt:
                    sc = 1.5
                elif syn and any(_re.search(r"\b" + _re.escape(x), txt) for x in syn):
                    sc = 1.5
                elif len(w) >= 4 and difflib.get_close_matches(w, mots, n=1, cutoff=0.78):   # fautes de frappe
                    sc = 1
            if not sc:
                return 0.0
            total += sc
        return total

    def _page_text(self, i):
        """Tout le texte d'une page (titres, aides, boutons), pour la recherche."""
        if i not in self._texts:
            import re as _re
            inner = self._pages[i]["inner"]
            parts = [w.text() for w in inner.findChildren(QLabel)]
            parts += [w.text() for w in inner.findChildren(QPushButton)]
            for cb in inner.findChildren(QComboBox):
                parts += [cb.itemText(k) for k in range(cb.count())]
            parts += [self._t(x) for x in parts]           # aussi dans la langue des menus
            self._texts[i] = _re.sub(r"<[^>]+>", " ", " ".join(parts)).lower()
        return self._texts[i]

    def current_page(self):
        return self.stack.currentIndex() if self.stack.count() else 0

    def select_page(self, idx):
        """Ouvre une page par son index (même si le menu la cache : mode simple ou recherche)."""
        if not isinstance(idx, int) or not 0 <= idx < self.stack.count():
            return
        if not self._select_item(idx):
            self._show_all = True
            if self.search.text():
                self.search.blockSignals(True)
                self.search.clear()
                self.search.blockSignals(False)
            self._build_menu()
            self._select_item(idx)
        self.stack.setCurrentIndex(idx)

    def select_by_name(self, name):
        n = name.lower()
        for i, p in enumerate(self._pages):
            if n in p["title"].lower() or n in self._t(p["title"]).lower():
                self.select_page(i)
                return True
        return False

    def _set_style(self, v):
        self.cfg["reglages_style"] = v
        self.C.save_config(self.cfg)
        self._show_all = False
        self._build_menu()

    def _arrow_css(self):
        """Petite flèche rose pour les listes déroulantes (dessinée une fois en PNG)."""
        try:
            from PyQt6.QtGui import QImage, QPainterPath
            th = _th.effective() if _th else "rose"
            path = Path(self.C.CONFIG_DIR) / ("fleche_reglages.png" if th == "rose" else f"fleche_reglages_{th}.png")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                img = QImage(24, 24, QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.transparent)
                p = QPainter(img)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                tri = QPainterPath()
                tri.moveTo(5, 8)
                tri.lineTo(19, 8)
                tri.lineTo(12, 17)
                tri.closeSubpath()
                p.fillPath(tri, QColor(_c(ROSE)))
                p.end()
                img.save(str(path))
            return ("QComboBox::drop-down { border: none; width: 28px; }"
                    f"QComboBox::down-arrow {{ image: url({path.as_posix()}); width: 12px; height: 12px; }}")
        except Exception:
            return ""

    # ------------------------------------------------------------- accueil
    def _page_accueil(self):
        c, C = self.comp, self.C
        self._page("🏠", "Accueil", "Les réglages les plus utilisés, et toutes les pages en un coup d'œil.")
        card = self._card("En un clic")
        self._switch(card, "Voix activée", "Elle lit ses bulles à voix haute.", "voice", default=True)
        self._switch(card, "Bavarde", "Elle dit des petites phrases d'elle-même.", "chatty", default=True)
        btns = [self._button("🔊  Réactiver sa voix", lambda: c.set_mute(0), True) if c.is_muted() else
                self._button("🔇  Muette 1 h", lambda: c.set_mute(60)),
                self._button("🎯  Concentration 25 min", lambda: c.set_focus(25))]
        if getattr(C, "gestionpc", None) and not getattr(C, "IS_WIN", False) and hasattr(c, "set_profile"):
            btns.append(self._button("🎮  Mode jeu", lambda: c.set_profile("jeu")))
        self._buttons(card, *btns)
        self._buttons(card, self._button("🌍  Langue…", lambda: self.select_by_name("Langues")),
                      self._button("🔊  Sa voix…", lambda: self.select_by_name("Voix")),
                      *([self._button("💡  Trucs et astuces", c.open_tips, True)] if getattr(C, "astuces", None) else []))
        if getattr(C, "apparence", None):
            self._buttons(card, self._button("👗  Son apparence (couleurs, coiffure, silhouette)…", c.open_look, True))
        if getattr(C, "demarrage", None):
            self._buttons(card, self._button("🪄  Relancer l'assistant de démarrage", c.open_wizard))
        if hasattr(c, "set_autostart"):
            self.cfg["demarrage_auto"] = c.autostart_enabled()
            self._switch(card, "Démarrer avec le PC", "Elle se lance toute seule quand tu allumes ton ordinateur.",
                         "demarrage_auto", on_change=lambda v: c.set_autostart(v))
        mj = getattr(C, "mise_a_jour", None)
        if mj and hasattr(c, "check_update"):
            card = self._card("Mises à jour de Viki")
            self._info(card, f"Ta version : {mj.VERSION}.")
            self._switch(card, "Regarder une fois par jour s'il y a une nouvelle version",
                         "Elle demande seulement le numéro de la dernière version à GitHub. Rien d'autre ne part.",
                         "maj_auto", default=False)
            self._buttons(card, self._button("🔎  Vérifier maintenant", lambda: c.check_update(), True))
        card = self._card("Affichage des réglages")
        self._combo(card, "Style du menu", "Choisis comment ranger le menu de gauche. La recherche 🔎 marche "
                    "dans tous les styles.", STYLES, self.cfg.get("reglages_style", "familles"),
                    self._set_style, width=300)
        if _th:
            self._combo(card, "Couleurs", "Le thème des fenêtres de Viki.", _th.choices(), _th.current(),
                        lambda v: c.set_theme(v), width=300)
        self._home_lay = self._card("Toutes les pages")
        self._end()

    def _fill_home(self):
        lay = getattr(self, "_home_lay", None)
        if lay is None:
            return
        from PyQt6.QtWidgets import QGridLayout
        for fam, _t in FAMILLES:
            idx = [i for i, p in enumerate(self._pages)
                   if p["title"] != "Accueil" and famille_de(p["title"]) == fam]
            if not idx:
                continue
            h = QLabel(fam)
            h.setStyleSheet("color: #b49aa7; font-size: 8pt; font-weight: bold; letter-spacing: 1px; "
                            "border: none; padding-top: 4px;")
            lay.addWidget(h)
            grid = QGridLayout()
            grid.setSpacing(8)
            for k, i in enumerate(idx):
                p = self._pages[i]
                b = QPushButton(f"{p['emoji']}  {p['title']}")
                b.setObjectName("tuile")
                b.setToolTip(p["subtitle"])
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setMinimumHeight(44)
                b.clicked.connect(lambda _=False, j=i: self.select_page(j))
                grid.addWidget(b, k // 3, k % 3)
            for col in range(3):
                grid.setColumnStretch(col, 1)
            lay.addLayout(grid)

    # ------------------------------------------------------------- briques
    def _page(self, emoji, title, subtitle):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(30, 26, 30, 26)
        lay.setSpacing(14)
        t = QLabel(title)
        t.setObjectName("titrePage")
        if getattr(self, "apple", False):
            hl = QHBoxLayout()
            hl.setSpacing(12)
            ic = QLabel()
            ic.setPixmap(pomme.tuile(self.C, emoji, pomme.TUILES.get(title, "#8e8e93"), 34))
            hl.addWidget(ic)
            hl.addWidget(t, 1)
            lay.addLayout(hl)
        else:
            lay.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("sousTitre")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addSpacing(4)
        scroll.setWidget(inner)
        self.stack.addWidget(scroll)
        self._pages.append({"emoji": emoji, "title": title, "subtitle": subtitle, "inner": inner})
        self._lay = lay
        return lay

    def _end(self):
        self._lay.addStretch(1)

    def _card(self, title=""):
        f = QFrame()
        f.setObjectName("carte")
        v = QVBoxLayout(f)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)
        if title:
            t = QLabel(title if getattr(self, "apple", False) else title.upper())
            t.setObjectName("titreCarte")
            v.addWidget(t)
        if getattr(self, "apple", False):
            v.setSpacing(9)
            v._rangs = 0
        self._lay.addWidget(f)
        return v

    def _row(self, card, name, help_txt, widget):
        if getattr(self, "apple", False) and hasattr(card, "_rangs"):
            if card._rangs:                                  # fin trait entre deux réglages, comme sur Mac
                tr_ = QFrame()
                tr_.setObjectName("trait")
                card.addWidget(tr_)
            card._rangs += 1
        row = QHBoxLayout()
        row.setSpacing(16)
        txt = QVBoxLayout()
        txt.setSpacing(2)
        n = QLabel(name)
        n.setObjectName("nom")
        n.setWordWrap(True)
        txt.addWidget(n)
        if help_txt:
            h = QLabel(help_txt)
            h.setObjectName("aide")
            h.setWordWrap(True)
            txt.addWidget(h)
        row.addLayout(txt, 1)
        if widget is not None:
            row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        card.addLayout(row)
        return widget

    def _switch(self, card, name, help_txt, key, on_change=None, default=False):
        sw = Switch(self.cfg.get(key, self.C.DEFAULT_CONFIG.get(key, default)))

        def changed(v):
            if key in self.comp.toggle_actions:
                self.comp._set_opt(key, v)
            else:
                self.cfg[key] = v
                self.C.save_config(self.cfg)
            if on_change:
                on_change(v)
            self._menus()
        sw.toggled.connect(changed)
        return self._row(card, name, help_txt, sw)

    def _combo(self, card, name, help_txt, items, current, on_change, width=240):
        cb = QComboBox()
        cb.setMinimumWidth(width)
        for label, val in items:
            cb.addItem(label, val)
        idx = next((i for i, (_, v) in enumerate(items) if v == current), -1)
        if idx < 0 and isinstance(current, float):
            idx = min(range(len(items)), key=lambda i: abs(float(items[i][1]) - current))
        cb.setCurrentIndex(max(0, idx))
        cb.currentIndexChanged.connect(lambda i: (on_change(cb.itemData(i)), self._menus()))
        return self._row(card, name, help_txt, cb)

    def _button(self, label, fn, main=False):
        b = QPushButton(label)
        if main:
            b.setObjectName("principal")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def _buttons(self, card, *btns):
        row = QHBoxLayout()
        row.setSpacing(8)
        for b in btns:
            row.addWidget(b)
        row.addStretch(1)
        card.addLayout(row)

    def _info(self, card, text):
        lab = QLabel(text)
        lab.setObjectName("info")
        lab.setWordWrap(True)
        card.addWidget(lab)
        return lab

    def _menus(self):
        try:
            self.comp._rebuild_menus()
        except Exception:
            pass

    def _set(self, key, value):
        self.cfg[key] = value
        self.C.save_config(self.cfg)

    # ------------------------------------------------------------- pages
    def _page_perso(self):
        c, C = self.comp, self.C
        self._page("👤", "Personnage", "Qui est sur ton bureau, sa tenue et sa taille.")
        card = self._card("Personnage")
        chars = C.list_characters()
        cur = str(Path(c.char_dir).resolve())
        self._combo(card, "Personnage affiché", "Change de compagne en un clic.",
                    [(n, str(Path(d).resolve())) for d, n in chars], cur,
                    lambda d: (c.switch_character(d), QTimer.singleShot(0, self._refresh)))
        self._buttons(card, self._button("🎭  Galerie des personnages…", c.open_gallery, True),
                      self._button("➕  Depuis une image ou une animation (GIF, vidéo)…", c.new_character),
                      self._button("➕  Modèle animé (Live2D / Spine)…", lambda: (c.import_model(), self._refresh())))
        self._buttons(card, self._button("Replacer les yeux, la bouche et les zones…", c.recalibrate),
                      self._button("📦  Exporter (pack à partager)…", c.export_pack))
        self._info(card, "Un pack .vikipack contient le personnage, ses tenues, ses phrases, sa voix et son "
                         "extrait de voix. Pour en importer un : glisse-le sur elle.")
        if c.char_base.get("type") == "live2d" and len(c.char_base.get("variantes") or []) > 1:
            card = self._card("Modèle Live2D")
            vs = c.char_base["variantes"]
            self._combo(card, "Version / tenue", "Ce modèle existe en plusieurs versions.",
                        [(Path(v).stem, v) for v in vs], c.char_base.get("live2d"),
                        lambda v: c.set_live2d_variant(v), width=200)
        if c.char_base.get("type") in ("live2d", "spine"):
            card = self._card("Ses mouvements")
            self._switch(card, "Voix et sons du modèle", "Si le modèle a des répliques ou des sons avec ses "
                         "mouvements, elle les joue (avec la bouche qui suit).", "voix_modele", default=True)
            self._switch(card, "…aussi pendant les mouvements au hasard", "Sinon, seulement quand tu cliques "
                         "sur elle ou selon ses émotions.", "voix_modele_hasard", default=True)
            self._switch(card, "Mouvements au hasard", "De temps en temps, elle joue un de ses mouvements "
                         "toute seule (en plus de ceux de ses émotions et de tes clics).", "mouv_hasard",
                         on_change=lambda v: getattr(c, "l2d", None) and setattr(c.l2d[0], "random_moves", v),
                         default=True)
            mots = c.model_motions()
            if mots:
                hint = QLabel(f"{len(mots)} mouvement{'s' if len(mots) > 1 else ''} dans ce modèle. "
                              "Clique pour les essayer :")
                hint.setObjectName("aide")
                card.addWidget(hint)
                row = None
                for k, (lab, key) in enumerate(mots[:60]):
                    if k % 4 == 0:
                        row = QHBoxLayout()
                        row.setSpacing(6)
                        card.addLayout(row)
                    b = self._button("▶ " + lab[:22], lambda _=False, kk=key: c.play_model_motion(kk))
                    row.addWidget(b)
                if row:
                    row.addStretch(1)
            self._buttons(card, self._button("✂️  Recadrer (si elle est coupée)", lambda: (c.refit_model(),
                                                                                         self._refresh())))
        if c.char_base.get("type") == "spine":
            card = self._card("Modèle Spine")
            anims = c.char_base.get("anims") or []
            if anims:
                self._combo(card, "Animation au repos", "Ce qu'elle fait quand elle ne fait rien de spécial. "
                            "(Les animations « happy », « touch »… servent pour ses émotions et les clics.)",
                            [(a, a) for a in anims], c.char_base.get("idle"),
                            lambda v: c.set_spine_option("idle", v), width=220)
            skins = c.char_base.get("skins") or []
            if len(skins) > 1:
                self._combo(card, "Peau / tenue", "", [(s, s) for s in skins], c.char_base.get("skin"),
                            lambda v: c.set_spine_option("skin", v), width=220)
        card = self._card("Tenue")
        quand = dict(C.TENUE_QUAND)
        items = [("Automatique (lieu, heure, météo)", "auto"), ("Tenue de base", "base")] + \
                [(f"{o.get('name', o['_slug'])}  —  {quand.get(o.get('quand'), '')}", o["_slug"])
                 for o in c.list_outfits()]
        self._combo(card, "Tenue", "Les tenues s'ajoutent avec une image du même personnage.", items,
                    self.cfg.get("tenue", "auto"), lambda k: c.change_outfit(k))
        for o in c.list_outfits():                      # quand la porter (soir, musique, mode jeu…)
            self._combo(card, f"Quand porter « {o.get('name', o['_slug'])} »", "", list(map(lambda kv: (kv[1], kv[0]),
                        C.TENUE_QUAND)), o.get("quand", "manuel"),
                        lambda v, sl=o["_slug"]: c.set_outfit_when(sl, v), width=300)
        self._buttons(card, self._button("Ajouter une tenue…", c.add_outfit))
        if getattr(C, "marionnette", None) and c.char_base.get("type") not in ("live2d", "spine"):
            card = self._card("Marionnette")
            rig = c.find_rig()
            if rig:
                self._switch(card, "Mode marionnette",
                             "Sa tête et ses bras bougent vraiment : respiration, tête qui suit ta souris, "
                             "bras qui se balancent, surtout quand elle marche.", "marionnette",
                             on_change=lambda v: (c._build_mesh(), c.update()), default=True)
                self._combo(card, "Force des mouvements", "",
                            [("Discrète", 0.5), ("Normale", 1.0), ("Vivante", 1.5)],
                            float(self.cfg.get("marionnette_force", 1.0)),
                            lambda v: (self._set("marionnette_force", v), setattr(c, "_pup_key", None)))
                if getattr(c, "outfit", None):
                    self._info(card, "En pause : elle porte une autre tenue (la marionnette est faite pour "
                                     "sa tenue de base).")
                self._info(card, f"Marionnette utilisée : {rig}")
            else:
                self._info(card, "Pas encore de marionnette pour ce personnage. Importe le dossier ou le .zip "
                                 "qui contient rig.json et le dossier layers/.")
            self._buttons(card, self._button("Importer une marionnette (.zip ou rig.json)…",
                                             lambda: (c.import_rig(), self._refresh())))
        card = self._card("Taille")
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(40, 220)
        base = c.base_scale()
        sl.setValue(int(round(c.scale / base * 100)))
        sl.setMinimumWidth(240)
        val = QLabel(f"{sl.value()} %")
        val.setMinimumWidth(48)
        sl.valueChanged.connect(lambda v: val.setText(f"{v} %"))
        sl.sliderReleased.connect(lambda: c._set_scale(sl.value() / 100 * base))
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(sl)
        hl.addWidget(val)
        self._row(card, "Taille à l'écran", "Glisse puis relâche.", w)
        if C.extras:
            card = self._card("Votre amitié")
            xp = int(self.cfg.get("amitie_xp", 0))
            lvl, cur, need = C.extras.niveau(xp)
            self._info(card, f"💗  Niveau {lvl} sur 10 : <b>{C.extras.NIVEAUX[lvl - 1]}</b>"
                             + (f"  ·  elle t'appelle « {self.cfg['surnom']} »" if self.cfg.get("surnom") else ""))
            bar = QProgressBar()
            bar.setRange(0, need if lvl < 10 else 1)
            bar.setValue(cur if lvl < 10 else 1)
            bar.setFormat(f"{cur} / {need} points" if lvl < 10 else "Niveau maximum !")
            card.addWidget(bar)
            unl = "\n".join(("✅ " if lvl >= k else "🔒 ") + f"Niveau {k} : {v}"
                             for k, v in sorted(C.extras.NIVEAU_DEBLOQUE.items()))
            lab = QLabel(unl)
            lab.setObjectName("aide")
            card.addWidget(lab)
            hint = QLabel("Tu gagnes des points en lui parlant, en la câlinant, en jouant et chaque jour où tu viens.")
            hint.setObjectName("aide")
            hint.setWordWrap(True)
            card.addWidget(hint)
        if C.visuel:
            card = self._card("Qualité de l'image")
            sharp = bool(c.char_base.get("nettete"))
            tool = C.visuel.find_upscaler()
            self._info(card, ("✨ Ce personnage est en haute définition (netteté IA)." if sharp else
                              "L'image peut être rendue 2× plus nette par une IA locale (Real-ESRGAN, sur ta carte "
                              "graphique) : traits plus propres, plus de flou ni de petits carrés.")
                       + ("" if tool or sharp else "\nL'outil n'est pas encore installé (bouton ci-dessous)."))
            btns = []
            if not tool and not sharp:
                btns.append(self._button("Installer l'outil de netteté (45 Mo)", c.install_upscaler))
            if not sharp:
                b = self._button("✨  Rendre plus net", c.sharpen_character, True)
                b.setEnabled(bool(tool))
                btns.append(b)
            if (Path(c.char_dir) / "original").exists():
                btns.append(self._button("Revenir à l'image d'origine", c.unsharpen_character))
            if btns:
                self._buttons(card, *btns)
            card = self._card("Expressions du visage")
            hint = QLabel("Génère la même image avec une autre expression (même pose, même cadrage, même prompt + "
                          "« smiling », « sad », « surprised »…). Je recale le visage tout seul, et elle change "
                          "vraiment de tête selon son humeur.")
            hint.setObjectName("aide")
            hint.setWordWrap(True)
            card.addWidget(hint)
            have = (c.char_base.get("expressions") or {})
            for emo, label in C.visuel.EXPRESSIONS.items():
                row = QHBoxLayout()
                lab = QLabel(("✅  " if emo in have else "➖  ") + label)
                lab.setObjectName("nom")
                row.addWidget(lab, 1)
                row.addWidget(self._button("Remplacer…" if emo in have else "Ajouter…",
                                           lambda _=False, e=emo: (c.add_expression(e), self.close())))
                if emo in have:
                    row.addWidget(self._button("Retirer", lambda _=False, e=emo: (c.remove_expression(e),
                                                                                 self.close())))
                card.addLayout(row)
        card = self._card("Toi")
        ed = QLineEdit(self.cfg.get("prenom", ""))
        ed.setPlaceholderText("Ton prénom")
        ed.setMinimumWidth(240)
        ed.editingFinished.connect(lambda: self._set("prenom", ed.text().strip()))
        self._row(card, "Ton prénom", "Elle t'appellera comme ça.", ed)
        bd = QLineEdit(self.cfg.get("anniversaire", ""))
        bd.setPlaceholderText("jj/mm")
        bd.setMaximumWidth(120)
        bd.editingFinished.connect(lambda: self._birthday(bd))
        self._row(card, "Ton anniversaire", "Elle te le souhaitera (avec un chapeau de fête).", bd)
        self._buttons(card, self._button("Ce dont elle se souvient…", c.edit_memory),
                      self._button("Nos statistiques…", c.show_stats),
                      self._button("Modifier ses phrases…", c.edit_phrases))
        self._end()

    def _birthday(self, ed):
        import re
        m = re.match(r"^\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*$", ed.text())
        if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
            ed.setText(f"{int(m.group(1)):02d}/{int(m.group(2)):02d}")
            self._set("anniversaire", ed.text())
            if self.C.extras:
                self.comp._update_fete()
        elif not ed.text().strip():
            self._set("anniversaire", "")

    def _refresh(self):
        """Rouvre la fenêtre sur la même page (après un ajout / une suppression), au même endroit."""
        pos = 0
        try:
            pos = self.stack.currentWidget().verticalScrollBar().value()
        except Exception:
            pass
        page, comp = self.current_page(), self.comp
        comp.open_settings(page)

        def restore():
            try:
                comp.settings_win.stack.currentWidget().verticalScrollBar().setValue(pos)
            except Exception:
                pass
        QTimer.singleShot(60, restore)

    def _page_quotidien(self):
        c, C = self.comp, self.C
        self._page("☀️", "Au quotidien", "Ce qu'elle fait avec toi chaque jour : apprendre, bouger, manger, "
                   "le défi, les actus, ton journal.")
        card = self._card("📍 Ma ville (météo)")
        lieu = self.cfg.get("meteo_lieu") or self.cfg.get("meteo_ville") or ""
        self._info(card, ("Ville actuelle : <b>%s</b>" % lieu) if lieu and self.cfg.get("meteo") == "reelle" else
                   "Aucune ville choisie : la météo de ses décors suit la saison. Choisis ta ville pour avoir la "
                   "vraie météo (seul le nom de la ville part en ligne).")

        def _ville():
            c.choisir_ville()
            self.open_page_again() if hasattr(self, "open_page_again") else None
        self._buttons(card, self._button("📍  Choisir ma ville…", _ville, True))
        Q = getattr(C, "quotidien", None)
        if Q:
            card = self._card("En un clic")
            self._buttons(card, self._button("💡  Apprends-moi un truc", lambda: c.teach_fact(), True),
                          self._button("😄  Une blague", c.tell_joke),
                          self._button("🏃  Pause sport", c.suggest_sport),
                          self._button("🍽️  Idée de repas", lambda: c.suggest_meal()))
            self._buttons(card, self._button("🎯  Mon défi", c.defi_status),
                          self._button("❓  Quiz de la semaine", c.week_quiz),
                          self._button("📅  Notre semaine", c.week_digest),
                          self._button("📖  Histoire du soir", lambda: c.tell_story()))
        if getattr(C, "autour", None) and hasattr(c, "nearby"):
            card = self._card("📍 Autour de moi")
            pos = self.cfg.get("position") or {}
            self._info(card, (f"Ta position : <b>{pos.get('saisie') or pos.get('nom')}</b>. " if pos.get("lat") else
                              "Elle ne connaît pas encore ta position : clique sur « Ma position ». ")
                       + "Elle trouve ce qu'il y a autour de toi et le montre sur une carte (OpenStreetMap, seulement "
                         "quand tu le demandes). Tu peux aussi lui dire « une pizzeria pas loin », « un café près de "
                         "la gare »…")
            near = lambda k, cu=None: (lambda: c.nearby({"kind": k, "cuisine": cu, "near": ""}))
            self._buttons(card, self._button("🍽️  Restos", near("restaurant"), True),
                          self._button("☕  Cafés", near("cafe")),
                          self._button("🥐  Boulangeries", near("boulangerie")),
                          self._button("🛒  Courses", near("supermarche")))
            self._buttons(card, self._button("💊  Pharmacies", near("pharmacie")),
                          self._button("🍺  Bars", near("bar")),
                          self._button("🎬  Cinémas", near("cinema")),
                          self._button("🌳  Parcs", near("parc")))
            self._buttons(card, self._button("📌  Ma position…", lambda: c.ask_position(then=self._refresh)))
        if Q:
            card = self._card("Apprendre et s'amuser")
            self._switch(card, "Une chose apprise chaque jour", "Un « le savais-tu ? » par jour. Ou dis-lui "
                         "« apprends-moi quelque chose sur les volcans ».", "q_apprendre", default=True)
            self._switch(card, "Des blagues de temps en temps", "Toutes les heures environ. « Arrête les blagues » "
                         "pour les couper.", "q_blagues", default=True)
            card = self._card("Santé")
            self._combo(card, "Pauses sport", "Une petite idée d'étirement ou d'exercice doux pendant que tu es sur "
                        "le PC (9 h – 21 h, jamais en mode jeu ni en plein écran).",
                        [("Jamais", 0), ("Toutes les 45 min", 45), ("Toutes les heures", 60),
                         ("Toutes les 1 h 30", 90), ("Toutes les 2 h", 120)], int(self.cfg.get("q_sport", 90) or 0),
                        lambda v: self._set("q_sport", v), width=220)
            self._switch(card, "Idées de repas", "Vers midi et vers 19 h : un repas pas cher, facile et équilibré. "
                         "« Idée de repas sans viande », « la recette », « ajoute les ingrédients aux courses ».",
                         "q_repas", default=True)
            self._switch(card, "Ouvrir la recette à l'heure du repas", "La fenêtre cuisine s'ouvre à côté d'elle "
                         "avec la recette en images (ou le repas prévu dans ta semaine).", "repas_fenetre", default=True)
            self._switch(card, "Photos des plats", "Une photo du plat (Wikipédia) dans la recette. Seulement si internet "
                         "est permis (Vie privée) ; les photos sont gardées sur ton PC.", "cuisine_photos", default=True)
            self._switch(card, "Me proposer de jouer de temps en temps", "Une petite partie, la pêche, le jardin ou le "
                         "dessin du jour, toutes les 2 à 4 heures (jamais en concentration).", "q_jeux", default=True)
            self._switch(card, "Défi de la semaine", "Un petit défi santé chaque lundi (eau, marche, sommeil…). "
                         "Dis « défi fait » quand c'est réussi.", "q_defi", default=True)
            self._switch(card, "Me dire d'aller dormir", "Après minuit, si tu es encore sur le PC.", "q_sommeil",
                         default=True)
            self._switch(card, "Météo et conseil du matin", "« Prends un parapluie », « couvre-toi »… (avec la météo "
                         "réelle de ta ville, Apparence → Décor).", "q_meteo_matin", default=True)
        V = getattr(C, "vie", None)
        if V:
            s = V.load()
            card = self._card("Soins et rappels qui reviennent")
            self._info(card, "Médicaments, plantes, animaux… Ajoute-les juste en dessous, ou dis-lui « rappelle-moi de "
                             "prendre mon médicament tous les jours à 9h ». Elle te demande de confirmer "
                             "(« c'est fait ») et relance une fois.")
            for i, x in enumerate(s["soins"]):                 # la liste, avec un bouton pour retirer
                b = self._button("🗑️", lambda _=False, k=i: self._care_remove(k))
                b.setToolTip("Retirer ce rappel")
                self._row(card, f"{V.SOIN_TYPES.get(x['type'], '⏰')}  {x['nom']}",
                          ("chaque jour" if x["tous_les"] == 1 else f"tous les {x['tous_les']} jours")
                          + (f" à {x['heure']}" if x.get("heure") else "")
                          + (" · avec confirmation" if x.get("confirmer") else "")
                          + (f" · fait le {x['dernier'][8:10]}/{x['dernier'][5:7]}" if x.get("dernier") else ""), b)
            # --- ajouter directement ici
            form = QWidget()
            fl = QHBoxLayout(form)
            fl.setContentsMargins(0, 4, 0, 0)
            fl.setSpacing(8)
            nom = QLineEdit()
            nom.setPlaceholderText("Quoi ? (ex : prendre mon médicament, arroser le basilic)")
            typ = QComboBox()
            for k, lab in (("", "🔎 Deviner"), ("medicament", "💊 Médicament"), ("plante", "🪴 Plante"),
                           ("animal", "🐾 Animal"), ("autre", "⏰ Autre")):
                typ.addItem(lab, k)
            typ.setMinimumWidth(140)
            freq = QComboBox()
            for lab, d in (("chaque jour", 1), ("tous les 2 jours", 2), ("tous les 3 jours", 3),
                           ("chaque semaine", 7), ("toutes les 2 semaines", 14), ("chaque mois", 30),
                           ("tous les 3 mois", 90)):
                freq.addItem(lab, d)
            heure = QComboBox()
            heure.addItem("dans la journée", "")
            for h in range(6, 24):
                heure.addItem(f"à {h} h", f"{h:02d}:00")
                heure.addItem(f"à {h} h 30", f"{h:02d}:30")
            freq.setMinimumWidth(150)
            heure.setMinimumWidth(130)
            for w_ in (nom, typ, freq, heure):
                fl.addWidget(w_, 3 if w_ is nom else 0)
            card.addWidget(form)
            conf = Switch(True)
            self._row(card, "Me demander de confirmer (« c'est fait »)", "Et une relance au bout de 30 minutes.", conf)

            def add_care():
                t = nom.text().strip()
                if not t:
                    nom.setFocus()
                    return
                kind = typ.currentData()
                if not kind:                           # « Deviner » : d'après les mots (chat, basilic, cachet…)
                    g = V.parse_care("rappelle-moi de " + t + " tous les jours")
                    kind = g[1] if g else "autre"
                V.add_care(V.load(), t[:60], kind, heure.currentData(), freq.currentData(), conf.isChecked())
                c.say(f"C'est noté : {t}, {freq.currentText()}" + (f" {heure.currentText()}" if heure.currentData()
                                                                   else "") + " !")
                self._refresh()
            nom.returnPressed.connect(add_care)
            self._buttons(card, self._button("➕  Ajouter ce rappel", add_care, True))
            card = self._card("Budget")
            tot, b = V.month_total(s), float(s.get("budget_mois") or 0)
            self._info(card, f"Ce mois-ci : {tot:.2f} € de dépenses notées" + (f" sur {b:.0f} €." if b else ".") +
                       " Dis-lui « j'ai dépensé 12 € en courses », « mon budget est de 300 € par mois », "
                       "« mes dépenses ».")
            self._buttons(card, self._button("💶  Voir le mois", lambda: c._show_text("💶 Budget", V.month_text(
                V.load()), "")))
            card = self._card("Humeur, proches et examens")
            self._info(card, "Humeur : quand tu racontes ta journée le soir, elle note ton humeur 😊 😐 😞 (ou dis "
                             "« je me sens bien »).\nProches : « l'anniversaire de Léa c'est le 12/03 » → elle te "
                             "prévient la veille et t'aide à écrire un message.\nExamens : « j'ai un examen de maths "
                             "le 15/12 » → une petite séance de révision par jour.")
            if s["proches"]:
                self._info(card, "🎂 " + " · ".join(f"{p['nom']} ({p['date']})" for p in s["proches"][:12]))
            self._buttons(card, self._button("😊  Mon humeur du mois", lambda: c._show_text(
                "😊 Humeur", V.mood_month_text(V.load()), "")),
                self._button("📚  Mes révisions", lambda: c._vie_dev_command("mes examens", "mes examens")))
            card = self._card("Musique")
            self._switch(card, "Suggestions de musique", "De temps en temps (au plus une fois par jour), surtout "
                         "quand tu codes ou te concentres : ta chaîne, ou ta musique de concentration.",
                         "musique_suggestions", default=True)
            self._switch(card, "Musique pendant le Pomodoro", "Elle lance ta musique de concentration au début du "
                         "travail, et la met en pause pendant la pause.", "pomo_musique", default=False)
            card2 = self._card("💪 Forme")
            self._switch(card2, "Routines du matin et du soir", "Elle te propose ta petite liste à l'heure choisie "
                         "(tu la modifies dans la fenêtre « Ma routine »).", "routines_on", default=True)
            self._switch(card2, "Rappels santé", "Un verre d'eau de temps en temps et une pause des yeux toutes les 45 "
                         "minutes devant l'écran. Jamais en concentration ni en jeu.", "sante_rappels", default=True)
            self._combo(card2, "Objectif d'eau", "Verres par jour.", [(f"{n} verres", n) for n in (4, 6, 8, 10, 12)],
                        int(self.cfg.get("sante_eau_objectif", 8)), lambda v: self._set("sante_eau_objectif", v),
                        width=140)
            self._buttons(card2, self._button("🌅  Ma routine", lambda: c.open_routine()),
                          self._button("🗓️  Ma semaine", c.open_planning),
                          self._button("💪  Muscu à la maison", c.open_muscu))
            self._switch(card, "Carte « En cours »", "Une petite carte près d'elle quand une musique ou une vidéo "
                         "joue, avec pause et suivant (tous les lecteurs, sur tous les bureaux).", "en_cours",
                         default=True)
            if getattr(C, "media", None) and hasattr(C.media, "SERVICES"):
                self._combo(card, "Où écouter ma musique", "Quand tu lui demandes « mets du lofi » ou « mets Daft Punk ». "
                            "Avec Spotify ou Deezer, elle ouvre ton appli si elle est installée, sinon le site.",
                            [("▶️ YouTube", "youtube"), ("🎵 YouTube Music", "ytmusic"), ("🟢 Spotify", "spotify"),
                             ("💜 Deezer", "deezer")], self.cfg.get("musique_service", "youtube"),
                            lambda v: self._set("musique_service", v), width=220)
            for key, lab, dflt in (("musique_dev", "Musique de concentration (lien)", V.MUSIQUE_DEV),
                                   ("musique_chaine", "Ta chaîne (lien)", V.MUSIQUE_CHAINE)):
                ed = QLineEdit(self.cfg.get(key) or dflt)
                ed.setMinimumWidth(300)
                ed.editingFinished.connect(lambda e=ed, k=key: self._set(k, e.text().strip()))
                self._row(card, lab, "", ed)
            if getattr(C, "media", None):
                self._info(card, "Dis-lui « mets-moi de la musique » : elle choisit un morceau de ta chaîne. Ou précise : "
                                 "« je veux écouter du lofi », « joue le dernier son de ma chaîne », « mets Daft Punk ».")
                ok = C.media.mpv_ok()
                self._switch(card, "Jouer en fond, sans ouvrir le navigateur", "Avec mpv et yt-dlp." if ok else
                             "Installe d'abord mpv et yt-dlp (sudo pacman -S mpv yt-dlp).", "musique_fond", default=False)
            self._buttons(card, self._button("🎧  Écouter maintenant", lambda: c.play_music("dev")))
        if getattr(C, "suivi", None):
            card = self._card("Actus et suivis")
            self._info(card, "Colle le lien de tes sites d'actus préférés et coche ceux qu'elle doit suivre : elle "
                             "te prévient des nouveaux articles. Tu peux aussi suivre des séries, animés, mangas, "
                             "films et les sorties ciné. Dis-lui « donne-moi l'actu » ou « l'actu sur l'espace » : "
                             "elle te lit les derniers titres de tes sites.")
            self._buttons(card, self._button("📰  Ouvrir Actus et suivis…", c.open_follow, True))
            n = sum(1 for s in self.cfg.get("sites", []) if s.get("suivre", True))
            m = len(self.cfg.get("suivis", []))
            if n or m:
                self._info(card, f"Elle suit {n} site{'s' if n > 1 else ''} et {m} série{'s' if m > 1 else ''} / "
                                 f"manga{'s' if m > 1 else ''} / film{'s' if m > 1 else ''}.")
        if getattr(C, "media", None):
            M = C.media
            card = self._card("🎨 Création d'images")
            self._info(card, "Dis-lui « génère une image d'un dragon bleu » ou « dessine-moi un fond d'écran "
                             "cyberpunk ». Tes images sont rangées dans Images → Viki.")
            self._combo(card, "Elle crée les images…", "En ligne : ton texte est envoyé à pollinations.ai (gratuit). "
                        "Sur ton PC : rien ne sort de chez toi, mais il faut une bonne carte graphique.",
                        [("Me demander la première fois", ""), ("☁️ En ligne (Pollinations)", "ligne"),
                         ("🖥️ Sur mon PC (Stable Diffusion)", "local"), ("🌐 Sur le site Perchance", "perchance")],
                        self.cfg.get("image_moteur", ""), lambda v: self._set("image_moteur", v), 280)
            ed = QLineEdit(self.cfg.get("image_local_url") or "http://127.0.0.1:7860")
            ed.setMinimumWidth(260)
            ed.editingFinished.connect(lambda e=ed: self._set("image_local_url", e.text().strip()))
            self._row(card, "Adresse de Stable Diffusion sur ton PC", "Forge, AUTOMATIC1111 ou SD.Next lancé avec --api.", ed)
            ek = QLineEdit(M.api_key())
            ek.setEchoMode(QLineEdit.EchoMode.Password)
            ek.setMinimumWidth(260)
            ek.setPlaceholderText("facultatif")
            ek.editingFinished.connect(lambda e=ek: M.set_api_key(e.text()))
            self._row(card, "Clé Pollinations", "Facultative : pour plus d'images par jour (enter.pollinations.ai).", ek)
            self._switch(card, "Traduire ma description en anglais", "Les générateurs comprennent mieux l'anglais. "
                         "Fait par ton IA de discussion.", "image_traduire", default=True)
            self._buttons(card, self._button("🎨  Ouvrir l'atelier d'images…", c.image_dialog, True),
                          self._button("📂  Mes images", lambda: (c.images_dir().mkdir(parents=True, exist_ok=True),
                                                                   c._open_path(c.images_dir()))),
                          self._button("🖥️  Comment faire sur mon PC ?", lambda: c._show_text(
                              "🖥️ Images sur ton PC", M.LOCAL_HELP, "")))
        if getattr(C, "plus", None):
            card = self._card("📋 Presse-papiers")
            self._switch(card, "Se souvient de tes dernières copies", "« recolle le lien de tout à l'heure ». Gardé en "
                         "mémoire seulement, jamais sur le disque ; les mots de passe probables sont ignorés.",
                         "clip_histo", default=True)
            self._buttons(card, self._button("📋  Voir ce que j'ai copié", c.open_clip_history))
            card = self._card("🌙 Mode nuit automatique")
            self._switch(card, "Mode nuit chaque soir", "Elle parle plus doucement et assombrit ses fenêtres. Tout "
                         "redevient normal le matin.", "mode_nuit", on_change=lambda v: c._night_tick(), default=False)
            hours = [(f"{h} h", h) for h in range(24)]
            self._combo(card, "Commence à", "", hours[18:] + hours[:3], int(self.cfg.get("nuit_debut", 22)),
                        lambda v: (self.cfg.__setitem__("nuit_debut", v), C.save_config(self.cfg), c._night_tick()), 120)
            self._combo(card, "Se termine à", "", hours[4:11], int(self.cfg.get("nuit_fin", 7)),
                        lambda v: (self.cfg.__setitem__("nuit_fin", v), C.save_config(self.cfg), c._night_tick()), 120)
            self._switch(card, "Thème sombre pendant la nuit", "", "nuit_theme", default=True)
            self._switch(card, "Rappel pour reposer tes yeux", "Toutes les 45 minutes pendant la nuit.", "nuit_yeux",
                         default=True)
            card = self._card("💜 Sa vie à elle")
            self._switch(card, "Humeur selon l'heure", "En forme le matin, un creux l'après-midi, fatiguée le soir.",
                         "humeur_journee", default=True)
            self._switch(card, "Petits rituels pendant tes pauses", "Un thé, sa plante, un livre… selon la saison.",
                         "rituels", default=True)
            self._switch(card, "Souvenirs partagés", "« Il y a un mois, tu commençais tel projet. »", "souvenirs",
                         default=True)
            self._buttons(card, self._button("💜  Nos souvenirs", c.show_memories))
        if C.extras:
            card = self._card("Ton journal")
            self._switch(card, "Te demande ta journée le soir", "Et le garde dans ton journal.", "journal",
                         default=True)
            self._switch(card, "Bilan de la semaine", "Le dimanche soir, elle te dit ce que vous avez fait ensemble "
                         "(messages, jeux, lecture, mangas, défi…) et le note dans ton journal. "
                         "Ou dis-lui « notre semaine ».", "bilan_semaine", default=True)
            self._buttons(card, self._button("📔  Lire mon journal", c.show_journal),
                          self._button("✍️  Écrire dans mon journal", lambda: (
                              setattr(c, "journal_until", __import__("time").monotonic() + 600),
                              c.say("Je t'écoute, raconte-moi !"), c.open_input())))
        if getattr(C, "pratique", None):
            card = self._card("📖 Lire, traduire, regarder l'écran")
            self._info(card, "Sélectionne un texte n'importe où, puis dis « traduis la sélection » ou « lis-moi la "
                             "sélection ». Pour une page : copie son adresse et dis « lis-moi cette page ». "
                             "« Qu'est-ce qu'il y a sur mon écran ? » : elle fait une capture et la décrit avec une IA "
                             "qui voit les images (locale, l'image ne quitte pas ton PC). Dictée : « dicte » (micro) "
                             "puis elle tape ce que tu dis dans la fenêtre ouverte.")
            self._buttons(card, self._button("🌍  Traduire la sélection", c.translate_selection),
                          self._button("🔊  Lire la sélection", c.read_selection),
                          self._button("📄  Lire un document…", c.read_pdf),
                          self._button("🖥️  Décris mon écran", c.describe_screen))
            self._buttons(card, self._button("⌨️  Raccourcis clavier…", c.show_shortcut_help))
        if getattr(C, "fun", None):
            card = self._card("🎮 Jeux")
            self._switch(card, "Elle remarque quand tu joues", "Temps de jeu par jeu, félicitations aux paliers "
                         "(10 h, 50 h, 100 h…), petite pause conseillée après 2 h. Steam, Proton, Wine, Lutris, "
                         "Heroic… Les succès Steam demanderaient une clé Steam : pas utilisés.", "jeux_suivi",
                         default=True)
            self._buttons(card, self._button("📊  Mes stats de jeu", lambda: c.say(c.game_stats_text())))
        self._end()

    def _care_remove(self, k):
        V = self.C.vie
        s = V.load()
        if 0 <= k < len(s["soins"]):
            s["soins"].pop(k)
            V.save(s)
        self._refresh()

    def _page_actions(self):
        c, C = self.comp, self.C
        self._page("✨", "Actions rapides", "Tout ce qu'elle peut faire, en un clic.")
        card = self._card("Lui parler")
        self._buttons(card, self._button("✏️  Lui écrire", c.open_input, True),
                      self._button("🎤  Micro", c.toggle_mic),
                      self._button("💬  Discussion", c.ask_chat),
                      self._button("Dis-moi quelque chose", lambda: c.say_from("spontanees")))
        def _place(v):
            self.cfg["barre_place"] = v
            c.save_cfg() if hasattr(c, "save_cfg") else None
            c.reset_input_box()
            c.start_ronds()
            if v != "ronds":
                QTimer.singleShot(50, c.open_input)
        self._combo(card, "Ses raccourcis", "Ronds : toujours à côté d'elle, chacun se déplie au clic (clic droit sur "
                    "un rond pour en ajouter, en retirer ou les déplacer). Colonne / au-dessus : à l'ouverture de la "
                    "barre pour lui écrire.",
                    [("🔵 Ronds à côté d'elle", "ronds"), ("➡️ Colonne à côté d'elle", "droite"),
                     ("⬆️ Barre au-dessus de sa tête", "dessus")],
                    self.cfg.get("barre_place", "ronds"), _place)
        card = self._card("Animations")
        btns = [self._button(lab, lambda _=False, k=key: c._play_anim(k))
                for lab, key in (("Danse", "pieds"), ("Coucou", "salut"), ("Fredonne", "fredonne"),
                                 ("S'étire", "etirement"), ("Clin d'œil", "clin"), ("Bâille", "baille"))]
        self._buttons(card, *btns[:3])
        self._buttons(card, *btns[3:], self._button("😴  Sieste", c.nap))
        if C.extras and not C.GUEST:
            card = self._card("Jouer")
            self._buttons(card, *[self._button(lab, lambda _=False, k=k: c.start_game(k))
                                  for lab, k in (("Pierre-feuille-ciseaux", "pfc"), ("Devinettes", "devinette"),
                                                 ("Quiz", "quiz"))])
            self._buttons(card, *[self._button(lab, lambda _=False, k=k: c.start_game(k))
                                  for lab, k in (("Morpion", "morpion"), ("Devine le nombre", "nombre"))])
            self._buttons(card, *[self._button(lab, lambda _=False, k=k: c.start_game(k))
                                  for lab, k in (("🔴 Puissance 4", "p4"), ("🪢 Pendu", "pendu"), ("🃏 Memory", "memory"))])
            if hasattr(c, "open_detente"):
                self._buttons(card, self._button("🌿  Coin détente (pêche, jardin, dessin du jour)",
                                                 lambda: c.open_detente(), True))
            card = self._card("Vie quotidienne")
            self._buttons(card, self._button("📚  Mode lecture (livres)…", lambda: c.open_reader(), True),
                      self._button("📖  Histoire du soir", lambda: c.tell_story()),
                          self._button("🔊  Lire le presse-papiers", lambda: c.clip_action("lire")),
                          self._button("⌨️  Dictée", c.start_dictation))
            self._buttons(card, self._button("📝  Notes", lambda: c.open_notes("notes")),
                          self._button("🛒  Courses", lambda: c.open_notes("courses")),
                          self._button("📔  Journal", c.show_journal))
        if getattr(C, "outils", None):
            card = self._card("Ton PC et toi")
            self._buttons(card, self._button("💡  Idées d'activités", c.show_activities, True),
                          self._button("🧹  Nettoyer le PC…", c.open_cleaner),
                          self._button("🗂️  Réorganiser un dossier…", c.open_tidy))
        card = self._card("Minuteurs et rappels")
        rs = sorted(self.cfg.get("rappels", []), key=lambda r: r["t"])
        import datetime
        for i, r in enumerate(rs[:8]):
            when = datetime.datetime.fromtimestamp(r["t"])
            row = QHBoxLayout()
            lab = QLabel(f"⏰  {when.strftime('%H:%M' if when.date() == datetime.date.today() else '%d/%m %H:%M')}"
                         f"  —  {r['txt'][:60]}")
            lab.setObjectName("nom")
            row.addWidget(lab, 1)
            row.addWidget(self._button("Supprimer", lambda _=False, k=i: (c._delete_reminder(k), self._refresh())))
            card.addLayout(row)
        self._buttons(card, self._button("➕  Nouveau rappel…", lambda: (c.add_reminder_dialog(), self._refresh())))
        if C.extras and not C.GUEST:
            self._buttons(card, *[self._button(f"⏱ {m} min", lambda _=False, v=m: c.add_timer(v * 60))
                                  for m in (3, 5, 10, 15, 30, 60)])
        pom = [self._button("🍅  Pomodoro 25 min", lambda: c.start_pomodoro(25, "travail")),
               self._button("Pomodoro 50 min", lambda: c.start_pomodoro(50, "travail")),
               self._button("Pause 5 min", lambda: c.start_pomodoro(5, "pause"))]
        if c.pomodoro:
            pom.append(self._button("Arrêter", c.stop_pomodoro))
        self._buttons(card, *pom)
        card = self._card("Objets")
        hint = QLabel("Ajoute des objets (parapluie, ballon, tasse…) : elle les prend, les utilise, et tu peux "
                      "lui donner des ordres comme « prends le parapluie et ouvre-le ».")
        hint.setObjectName("aide")
        hint.setWordWrap(True)
        card.addWidget(hint)
        for slug, o in c.objects_lib().items():
            row = QHBoxLayout()
            lab = QLabel(("✋  " if self.cfg.get("objet_porte") == slug else "•  ") + o["name"])
            lab.setObjectName("nom")
            row.addWidget(lab, 1)
            row.addWidget(self._button("Lui donner", lambda _=False, sl=slug: c.queue([("prendre", sl)])))
            row.addWidget(self._button("Utiliser", lambda _=False, sl=slug: c.queue([("utiliser", sl)])))
            row.addWidget(self._button("Ranger", lambda _=False, sl=slug: c.queue([("ranger", sl)])))
            row.addWidget(self._button("Supprimer", lambda _=False, sl=slug: (c.delete_object(sl), self._refresh())))
            card.addLayout(row)
        self._buttons(card, self._button("➕  Ajouter un objet (image)…", c.add_object))
        self._end()

    def _page_comportement(self):
        c = self.comp
        self._page("💬", "Comportement", "Comment elle vit sur ton bureau.")
        if hasattr(c, "set_autostart"):
            card = self._card("Démarrage")
            self.cfg["demarrage_auto"] = c.autostart_enabled()
            self._switch(card, "Démarrer avec le PC", "Elle se lance toute seule quand tu allumes ton ordinateur "
                         "(tu peux toujours la fermer).", "demarrage_auto", on_change=lambda v: c.set_autostart(v))
        if getattr(self.C, "cerveau", None) and getattr(c, "brain", None):
            card = self._card("🧠 Son intelligence")
            self._info(card, "Elle comprend tes allées et venues et ce que tu fais, varie ce qu'elle dit et apprend de "
                             "toi. Tout reste sur ton PC.")
            for key, name, help_txt in (
                    ("presence_accueil", "T'accueillir selon ton absence", "Rien après 5 minutes, « on reprend ton "
                     "projet ? » après 2 heures, un petit récap le matin."),
                    ("contexte_activite", "S'adapter à ce que tu fais", "Silence pendant un appel, un jeu ou un film ; "
                     "discrète quand tu codes."),
                    ("routines", "Apprendre tes habitudes", "Tes heures de départ selon le jour : elle ne bavarde pas "
                     "quand tu es pressé."),
                    ("fatigue", "Repérer fatigue et blocage", "Longue session sans pause, même erreur copiée plusieurs "
                     "fois."),
                    ("anti_repetition", "Ne pas se répéter", "Elle ne redit pas la même phrase avant quelques jours."),
                    ("phrases_ia", "Varier ses phrases avec l'IA", "Son IA locale reformule ses phrases selon le moment "
                     "(si elle est installée)."),
                    ("souvenirs_auto", "Proposer de retenir ce que tu dis de toi", "Toujours avec ton accord : « Je "
                     "retiens que tu adores le lofi ? »")):
                self._switch(card, name, help_txt, key, default=True)
            self._info(card, "Apprends-lui tes commandes : « quand je dis mode chill, mets ma playlist chill et le mode "
                             "nuit ». Si elle se trompe : « non, je voulais dire … » et elle retient.")
            self._buttons(card, self._button("🧠  Ce qu'elle sait de moi…", lambda: c.open_brain(0), True),
                          self._button("🗣️  Mes commandes", lambda: c.open_brain(1)),
                          self._button("❓  Pas compris", lambda: c.open_brain(2)),
                          self._button("📅  Ma journée", lambda: c.open_brain(3)))
        card = self._card("Son caractère")
        self._switch(card, "Bavarde", "Elle parle d'elle-même de temps en temps.", "chatty")
        self._switch(card, "S'endort quand on la laisse seule", "Elle fait une sieste après un moment sans toi.",
                     "sleepy")
        self._switch(card, "Danse sur la musique", "Quand une musique joue sur ton PC.", "music_dance")
        self._switch(card, "Se promène sur l'écran", "Elle marche un peu toute seule.", "walk")
        if self.C.extras and not self.C.GUEST:
            self._switch(card, "Commente ce que tu fais", "Jeux, travail, heure tardive, musique en boucle.",
                         "activite", default=True)
        if self.C.extras and not self.C.GUEST:
            card = self._card("Concentration et place")
            self._combo(card, "Mode concentration", "Plus aucune bulle, juste un rappel pour boire de l'eau.",
                        [("Désactivé", 0), ("25 minutes", 25), ("50 minutes", 50), ("1 h 30", 90), ("2 heures", 120)],
                        0, lambda v: c.set_focus(v))
            if c.in_focus():
                self._info(card, "🎯 Mode concentration actif.")
            self._switch(card, "S'asseoir sur la fenêtre active", "Elle se pose sur le haut de ta fenêtre et la suit "
                         "(il faut « kdotool » sous Wayland).", "perch", lambda v: c.set_perch(v))
        # --- ses phrases à toi
        card = self._card("Ses phrases (à toi)")
        hint = QLabel("Des phrases qu'elle dira de temps en temps, en plus des siennes. Écris {prenom} pour "
                      "ton prénom.")
        hint.setObjectName("aide")
        hint.setWordWrap(True)
        card.addWidget(hint)
        self.ph_list = QListWidget()
        self.ph_list.setObjectName("liste")
        self.ph_list.setMaximumHeight(150)
        for ph in self.cfg.get("phrases_perso", []):
            self.ph_list.addItem(ph)
        card.addWidget(self.ph_list)
        row = QHBoxLayout()
        self.ph_edit = QLineEdit()
        self.ph_edit.setPlaceholderText("ex : Tu es génial, {prenom} !")
        self.ph_edit.returnPressed.connect(self._add_phrase)
        row.addWidget(self.ph_edit, 1)
        row.addWidget(self._button("Ajouter", self._add_phrase, True))
        row.addWidget(self._button("Supprimer", self._del_phrase))
        card.addLayout(row)
        self._combo(card, "Elle parle d'elle-même…", "", [("Souvent (toutes les 5 min environ)", 5),
                    ("Assez souvent (10 min)", 10), ("Normalement (18 min)", 18), ("Rarement (40 min)", 40)],
                    int(self.cfg.get("freq_phrases", 18)), lambda v: self._set("freq_phrases", v), width=260)
        # --- messages réguliers
        card = self._card("Messages réguliers (rappels qui reviennent)")
        hint = QLabel("Elle te le dit (et une notification apparaît) : toutes les X minutes, ou chaque jour "
                      "à la même heure. Ex : « Bois un verre d'eau ! », « Prends tes médicaments ».")
        hint.setObjectName("aide")
        hint.setWordWrap(True)
        card.addWidget(hint)
        self.msg_list = QListWidget()
        self.msg_list.setObjectName("liste")
        self.msg_list.setMaximumHeight(150)
        card.addWidget(self.msg_list)
        self._fill_msgs()
        row = QHBoxLayout()
        self.msg_edit = QLineEdit()
        self.msg_edit.setPlaceholderText("Le message")
        row.addWidget(self.msg_edit, 1)
        card.addLayout(row)
        row = QHBoxLayout()
        self.msg_type = QComboBox()
        self.msg_type.addItem("Toutes les…", "minutes")
        self.msg_type.addItem("Chaque jour à…", "heure")
        row.addWidget(self.msg_type)
        self.msg_min = QSpinBox()
        self.msg_min.setRange(1, 1440)
        self.msg_min.setValue(60)
        self.msg_min.setSuffix(" min")
        self.msg_min.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        row.addWidget(self.msg_min)
        self.msg_time = QTimeEdit(QTime(9, 0))
        self.msg_time.setDisplayFormat("HH:mm")
        self.msg_time.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self.msg_time.hide()
        row.addWidget(self.msg_time)
        self.msg_type.currentIndexChanged.connect(lambda i: (self.msg_min.setVisible(i == 0),
                                                             self.msg_time.setVisible(i == 1)))
        row.addStretch(1)
        row.addWidget(self._button("Ajouter", self._add_msg, True))
        row.addWidget(self._button("Supprimer", self._del_msg))
        card.addLayout(row)
        card = self._card("Muette")
        muted = c.is_muted()
        self._combo(card, "Son", "Elle continue d'écrire dans ses bulles.",
                    [("🔊 Elle parle", 0), ("🔇 Muette 30 minutes", 30), ("🔇 Muette 1 heure", 60),
                     ("🔇 Muette jusqu'à ce que je la réactive", -1)],
                    (-1 if self.cfg.get("mute_until") == -1 else 30) if muted else 0, lambda v: c.set_mute(v))
        self._switch(card, "En muet, plus de bulles spontanées", "Silence total : elle ne répond que si tu lui "
                     "parles.", "mute_bubbles")
        card = self._card("Fenêtre")
        self._switch(card, "Toujours au premier plan", "Elle reste au-dessus de tes fenêtres.", "on_top",
                     lambda v: c._apply_flags())
        self._switch(card, "Mode fantôme", "À moitié transparente, et les clics la traversent (elle ne gêne jamais). "
                     "Pour en sortir : son icône près de l'horloge, ou « sors du mode fantôme ».", "ghost",
                     lambda v: c.set_ghost(v, told=True))
        self._switch(card, "Se cacher pendant les jeux et vidéos en plein écran", "", "fullscreen_pause",
                     default=True)
        card = self._card("Lui donner des fichiers")
        self._info(card, "Glisse un fichier sur elle (modèle .zip, image, texte, voix…), ou clique sur 📎 dans "
                         "sa barre de texte, ou clic droit → « Donne-moi un fichier ».")
        self._switch(card, "Fenêtre normale (pour lui glisser des fichiers dessus)",
                     "Sous KDE, sa fenêtre passe à côté du gestionnaire de fenêtres pour rester au-dessus : "
                     "le glisser-déposer ne l'atteint pas. Active ceci pour qu'elle les reçoive directement. "
                     "(Expérimental : si elle se cache derrière tes fenêtres, désactive-le.)",
                     "fenetre_geree", on_change=lambda v: c._apply_flags(), default=False)
        self._end()

    # --- phrases et messages
    def _add_phrase(self):
        t = self.ph_edit.text().strip()
        if t:
            self.cfg.setdefault("phrases_perso", []).append(t)
            self.C.save_config(self.cfg)
            self.ph_list.addItem(t)
            self.ph_edit.clear()

    def _del_phrase(self):
        r = self.ph_list.currentRow()
        if r >= 0:
            self.cfg.get("phrases_perso", []).pop(r)
            self.C.save_config(self.cfg)
            self.ph_list.takeItem(r)

    def _fill_msgs(self):
        self.msg_list.clear()
        for m in self.cfg.get("messages_reguliers", []):
            quand = f"Chaque jour à {m.get('heure')}" if m.get("type") == "heure" else \
                f"Toutes les {m.get('minutes')} min"
            self.msg_list.addItem(f"⏰  {quand}  —  {m.get('txt')}")

    def _add_msg(self):
        t = self.msg_edit.text().strip()
        if not t:
            return
        m = {"txt": t, "type": self.msg_type.currentData(), "actif": True}
        if m["type"] == "heure":
            m["heure"] = self.msg_time.time().toString("HH:mm")
        else:
            m["minutes"] = self.msg_min.value()
        self.cfg.setdefault("messages_reguliers", []).append(m)
        self.C.save_config(self.cfg)
        self.msg_edit.clear()
        self._fill_msgs()
        self.comp.say("C'est noté, je te le dirai régulièrement !")

    def _del_msg(self):
        r = self.msg_list.currentRow()
        if r >= 0:
            self.cfg.get("messages_reguliers", []).pop(r)
            self.C.save_config(self.cfg)
            self._fill_msgs()

    def _page_voix(self):
        c, C = self.comp, self.C
        self._page("🔊", "Voix", "Sa façon de parler. Tout est calculé sur ton PC.")
        card = self._card("Voix")
        if not C.voice_files():
            self._info(card, "⚠️ Aucune voix Piper n'est installée : elle parle avec une voix de secours robotique.")
            self._buttons(card, self._button("Télécharger sa voix (Siwis, 60 Mo)", c.install_french_voice, True))
        self._switch(card, "Voix activée", "Sinon elle parle seulement dans ses bulles.", "voice")
        installed = C.natural_voice_installed("naturelle")
        legere = C.natural_voice_installed("legere")
        engines = [("Piper (rapide, robotique léger)", "piper")]
        if legere:
            engines.append(("Légère — Pocket TTS (naturelle et légère)", "legere"))
        if installed:
            engines.append(("Naturelle — Chatterbox (la plus humaine, lourde)", "naturelle"))
        cur = self.cfg.get("voice_engine", "piper")
        self._combo(card, "Moteur de voix",
                    "Légère : presque aussi naturelle que Chatterbox, mais calculée sur le processeur sans le "
                    "faire ramer. Naturelle : la plus humaine, mais lourde.",
                    engines, cur if any(v == cur for _, v in engines) else "piper", lambda v: c._set_engine(v),
                    width=330)
        choices = C.piper_voice_choices()
        if choices:
            cur = next((f"{s}|{sp}" for s, _, sp in choices if s == self.cfg.get("piper_voice", "")
                        and int(self.cfg.get("piper_speaker", -1)) == sp), f"{choices[0][0]}|{choices[0][2]}")
            self._combo(card, "Voix Piper", "", [(lab, f"{s}|{sp}") for s, lab, sp in choices], cur,
                        lambda v: c._set_piper_voice(v.split("|")[0], int(v.split("|")[1])), width=280)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(5, 150)
        sl.setValue(int(float(self.cfg.get("volume", 0.35)) * 100))
        sl.setMinimumWidth(220)
        sl.sliderReleased.connect(lambda: self._set("volume", round(sl.value() / 100, 2)))
        self._row(card, "Volume", "", sl)
        self._buttons(card, self._button("▶  Tester la voix", lambda: c.say(
            f"Coucou ! C'est moi, {c.char.get('name', 'ta compagne')}. Tu m'entends bien ?"), True))
        if getattr(C, "voix", None):
            card = self._card("Sa façon de parler")
            self._info(card, f"Ces réglages sont gardés pour {c.char.get('name', 'elle')} : chaque personnage "
                             "a sa propre voix. (Toutes les voix ; l'expressivité et les pauses : Piper seulement.)")

            def slider(name, help_txt, key, lo, hi, default, fmt):
                s = QSlider(Qt.Orientation.Horizontal)
                s.setRange(lo, hi)
                s.setValue(int(round(float(self.cfg.get(key, default)) * 100)))
                s.setMinimumWidth(200)
                lab = QLabel(fmt(s.value()))
                lab.setMinimumWidth(70)
                lab.setStyleSheet("color: #5c4652; font-size: 13px;")
                s.valueChanged.connect(lambda v: lab.setText(fmt(v)))
                s.sliderReleased.connect(lambda: c.set_voice_param(key, round(s.value() / 100, 2)))
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(s)
                h.addWidget(lab)
                self._row(card, name, help_txt, w)
            slider("Vitesse", "Plus lente ou plus rapide.", "voix_vitesse", 60, 160, 1.0,
                   lambda v: "normale" if v == 100 else f"{v} %")
            slider("Hauteur", "Plus grave ou plus aiguë.", "voix_hauteur", 85, 120, 1.0,
                   lambda v: "normale" if v == 100 else (f"+{v - 100} %" if v > 100 else f"{v - 100} %"))
            slider("Timbre", "De grave et chaude à douce et légère (sans changer la hauteur).", "voix_timbre",
                   -100, 100, 0.0, lambda v: "normal" if v == 0 else (f"grave {-v} %" if v < 0 else f"douce {v} %"))
            self._combo(card, "Bruit de fond", "Retire le souffle et les petits bruits de la voix.",
                        [("Ne rien faire", 0), ("Réduire un peu", 1), ("Réduire fort", 2)],
                        int(self.cfg.get("voix_bruit", 0)), lambda v: c.set_voice_param("voix_bruit", v))
            self._combo(card, "Ambiance", "Un effet de lieu sur sa voix (aucune = voix nette, sans écho).",
                        [(lab, k) for k, (lab, _f) in c.AMBIANCES.items()], self.cfg.get("voix_ambiance", ""),
                        lambda v: c.set_voice_param("voix_ambiance", v))
            self._combo(card, "Expressivité", "Monotone = toujours pareil ; expressive = plus vivante.",
                        [("Monotone", 0.33), ("Calme", 0.5), ("Normale", 0.667), ("Expressive", 0.85),
                         ("Très expressive", 1.0)], float(self.cfg.get("voix_variation", 0.667)),
                        lambda v: c.set_voice_param("voix_variation", v))
            self._combo(card, "Pause entre les phrases", "",
                        [("Aucune", 0.0), ("Courte", 0.2), ("Moyenne", 0.45), ("Longue", 0.8)],
                        float(self.cfg.get("voix_pause", 0.2)), lambda v: c.set_voice_param("voix_pause", v))
            self._buttons(card, self._button("▶  Écouter le résultat", lambda: c.say(
                "Voilà ma voix avec ces réglages. Elle te plaît comme ça ?"), True),
                          self._button("🔧  Diagnostiquer le son", c.sound_diagnostic),
                          self._button("Réinitialiser", lambda: ([c.set_voice_param(k, v) for k, v in (
                              ("voix_vitesse", 1.0), ("voix_hauteur", 1.0), ("voix_variation", 0.667),
                              ("voix_pause", 0.2), ("voix_timbre", 0.0), ("voix_bruit", 0), ("voix_ambiance", ""))],
                                                                         self._refresh())))
            card = self._card("Extraits de voix (référence)")
            nat = C.natural_voice_installed()
            self._info(card, "La voix naturelle imite l'extrait choisi : 10 à 30 secondes, une seule personne qui "
                             "parle calmement, sans musique ni bruit. Utilise ta voix, ou celle de quelqu'un qui "
                             "est d'accord." + ("" if nat else "  (La voix naturelle n'est pas installée sur ce PC : "
                                                              "tes extraits serviront quand elle le sera.)"))
            cur = self.cfg.get("voice_ref", "")
            self._switch(card, "Nettoyer mon extrait", "Retire le bruit et une partie de l'écho de la pièce avant "
                         "qu'elle l'imite (sinon elle imite aussi le souffle et la résonance).", "voix_nettoyer_extrait",
                         lambda v: c._save_char_voice(), default=True)
            refs = c.list_voice_refs()
            if not refs:
                lab = QLabel("Aucun extrait pour l'instant.")
                lab.setObjectName("aide")
                card.addWidget(lab)
            for p in refs:
                row = QHBoxLayout()
                used = str(p) == cur
                lab = QLabel(("✅  " if used else "🎙️  ") + p.stem)
                lab.setObjectName("nom")
                row.addWidget(lab, 1)
                row.addWidget(self._button("▶", lambda _=False, pp=p: c.play_voice_ref(pp)))
                if not used:
                    row.addWidget(self._button("Utiliser", lambda _=False, pp=p: (c.use_voice_ref(pp),
                                                                                  self._refresh())))
                row.addWidget(self._button("Supprimer", lambda _=False, pp=p: (c.delete_voice_ref(pp),
                                                                               self._refresh())))
                card.addLayout(row)
            self._buttons(card, self._button("➕  Ajouter des extraits…", lambda: (c.add_voice_refs(),
                                                                                self._refresh()), True),
                          self._button("🎤  M'enregistrer (20 s)", lambda: c.record_voice_ref(
                              20, done=lambda _p: self._refresh())),
                          self._button("Voix par défaut", lambda: (c._reset_voice_ref(), self._refresh())))
            card = self._card("Plus de voix")
            self._info(card, "Des dizaines de voix gratuites (féminines, masculines, plusieurs accents) dans "
                             "plus de 30 langues. Elles tournent sur ton PC ; internet sert seulement à les télécharger.")
            self._buttons(card, self._button("🗣️  Catalogue des voix…", lambda: c.open_voice_catalog("fr"), True))
        card = self._card("Voix légère (Pocket TTS)")
        if not legere:
            self._info(card, "La solution si la voix naturelle rame : Pocket TTS de Kyutai (laboratoire français), "
                             "un modèle 5 fois plus petit que Chatterbox, fait pour le processeur. Voix française "
                             "« Estelle » fournie, et elle imite aussi tes extraits de voix. Environ 1 Go à "
                             "télécharger, une seule fois.")
            self._buttons(card, self._button("⬇️  Installer la voix légère (terminal)…",
                                             lambda: c.install_natural_voice("legere"), True))
        else:
            self._combo(card, "Qualité", "Le modèle « 24 couches » est meilleur mais environ 2 fois plus lent "
                        "(encore en aperçu chez Kyutai).",
                        [("Rapide (recommandé)", "french"), ("Meilleure (plus lente)", "french_24l")],
                        self.cfg.get("legere_langue", "french"),
                        lambda v: (self._set("legere_langue", v),
                                   self.cfg.get("voice_engine") == "legere" and c._start_natural(restart=True)))
            self._combo(card, "Finesse du son", "Plus d'étapes de calcul = voix plus propre, mais plus lente.",
                        [("Normale (rapide)", 1), ("Fine", 3), ("Très fine (plus lente)", 5)],
                        int(self.cfg.get("legere_finesse", 1)),
                        lambda v: (self._set("legere_finesse", v),
                                   self.cfg.get("voice_engine") == "legere" and c._start_natural(restart=True)))
            self._switch(card, "Calcul allégé (int8)", "Plus léger pour le processeur, mais peut rendre la voix un peu "
                         "métallique ou déformée : coupe-le si c'est le cas.", "legere_int8",
                         lambda v: self.cfg.get("voice_engine") == "legere" and c._start_natural(restart=True),
                         default=True)
            if self.cfg.get("voice_engine") == "legere":
                if c.natural_ready and c.natural_device_name:
                    self._info(card, f"✅ Prête — {c.natural_device_name}")
                else:
                    err = getattr(c, "natural_error", "")
                    self._info(card, ("❌ Elle n'a pas pu se charger : " + err[:160]) if err else
                               "⏳ Chargement (quelques secondes)…")
            self._buttons(card, self._button("Utiliser la voix légère", lambda: c._set_engine("legere"), True),
                          self._button("Journal de la voix…", c.show_voice_log))
            self._clone_box(card)
        if not installed:
            card = self._card("Voix naturelle")
            self._info(card, "Une voix bien plus humaine (Chatterbox), calculée sur ton PC. Elle demande environ "
                             "6 Go et marche mieux avec une bonne carte graphique. Si tu l'as déjà installée "
                             "(dossier .venv-voix), montre-moi juste où elle est.")
            self._buttons(card, self._button("📂  Je l'ai déjà : choisir le dossier…", c.find_natural_voice, True),
                          self._button("⬇️  L'installer (terminal)…", c.install_natural_voice))
        if installed:
            card = self._card("Voix naturelle")
            self._combo(card, "Expressivité", "",
                        [("Calme", 0.3), ("Normale", 0.5), ("Expressive", 0.7), ("Très expressive", 0.9)],
                        float(self.cfg.get("expressivity", 0.5)), lambda v: c._set_expressivity(v))
            self._combo(card, "Mode", "Léger : elle commence à parler dès la 1re phrase, les très longs textes "
                        "passent par Piper, et la mémoire est libérée après 10 min sans parler.",
                        [("Léger (recommandé)", "leger"), ("Complet (toujours chargée)", "complet")],
                        self.cfg.get("natural_mode", "leger"), lambda v: self._set("natural_mode", v))
            self._combo(card, "Calcul sur", "La carte graphique est bien plus rapide.",
                        [("Carte graphique si possible", "auto"), ("Processeur seulement (stable)", "cpu")],
                        self.cfg.get("natural_device", "auto"), lambda v: c._set_natural_device(v))
            if c.natural_ready and c.natural_device_name and self.cfg.get("voice_engine") == "naturelle":
                self._info(card, f"✅ Prête — actuellement sur : {c.natural_device_name}")
            elif self.cfg.get("voice_engine") == "naturelle":
                err = getattr(c, "natural_error", "")  # (seulement pour Chatterbox)
                self._info(card, ("❌ Elle n'a pas pu se charger : " + err[:160] + " — regarde le journal de la voix.")
                           if err else "⏳ Chargement en cours (1 à 3 minutes au démarrage). En attendant, "
                                       "elle parle avec la voix Piper.")
            self._info(card, "Installée dans : " + str(Path(C.natural_python(kind="naturelle")).parents[2]))
            btns = [self._button("Relancer", lambda: c._start_natural(restart=True)),
                    self._button("Imiter une voix (extrait audio)…", c._choose_voice_ref),
                    self._button("Journal de la voix…", c.show_voice_log)]
            if self.cfg.get("voice_ref"):
                btns.append(self._button("Voix par défaut", c._reset_voice_ref))
            self._buttons(card, *btns)
        self._end()

    def _clone_box(self, card):
        """Imitation d'un extrait avec Pocket TTS : modèle « à conditions » chez Kyutai (gratuit)."""
        c, C = self.comp, self.C
        has = bool(C.hf_token())
        t = QLabel("<b>Imiter ton extrait de voix</b>" + (" — ✅ activé" if has else ""))
        t.setStyleSheet("color: #3d2733; margin-top: 6px;")
        card.addWidget(t)
        self._info(card, ("Viki a ton jeton : la voix légère peut imiter l'extrait choisi plus haut. "
                          "Si elle n'y arrive toujours pas, vérifie que tu as bien accepté les conditions (étape 1)."
                          if has else
                          "La voix « Estelle » marche tout de suite. Pour qu'elle imite TON extrait, Kyutai demande "
                          "d'accepter ses conditions d'utilisation (gratuit, une seule fois) :\n"
                          "1. Crée un compte Hugging Face et accepte les conditions sur la page du modèle.\n"
                          "2. Crée un jeton en lecture seule (« Read ») et colle-le ci-dessous.\n"
                          "Les conditions interdisent d'imiter quelqu'un sans son accord : utilise ta voix ou celle "
                          "d'une personne d'accord."))
        tok = QLineEdit(C.hf_token())
        tok.setEchoMode(QLineEdit.EchoMode.Password)
        tok.setPlaceholderText("hf_…")
        tok.setMinimumWidth(260)
        self._row(card, "Jeton Hugging Face", "Rangé dans un fichier que toi seul peux lire.", tok)

        def save():
            C.set_hf_token(tok.text())
            if self.cfg.get("voice_engine") == "legere":
                c._ref_warned = ""
                c._start_natural(restart=True)
                c.say("C'est enregistré ! Je recharge ma voix légère avec l'imitation (le 1er chargement "
                      "télécharge un peu plus).")
            self._refresh()
        self._buttons(card, self._button("1. Accepter les conditions…",
                                         lambda: C.open_link("https://huggingface.co/kyutai/pocket-tts")),
                      self._button("2. Créer un jeton…",
                                   lambda: C.open_link("https://huggingface.co/settings/tokens/new?tokenType=read"
                                                       "&description=Viki")),
                      self._button("Enregistrer", save, True))

    def _page_discussion(self):
        c, C = self.comp, self.C
        self._page("🧠", "Discussion", "Son intelligence (sur ton PC ou en ligne) et sa mémoire.")
        card = self._card("Son cerveau")
        self._card_ia(card)
        card = self._card("Modèle pour traduire, corriger, résumer")
        models = c.ollama_list()
        cur = self.cfg.get("outils_modele", "")
        items = [(f"Son cerveau ({c.ia_name()})", "")] + [(n, n) for n in models]
        if cur and cur not in models:
            items.append((f"{cur} (pas installé)", cur))
        self._combo(card, "Modèle utilisé", "Pour les boutons de la barre (Traduire, Corriger, Résumer…). Un modèle "
                    "spécialisé comme « translategemma » traduit souvent mieux. Les modèles Ollama restent sur ton PC.",
                    items, cur, lambda v: c.set_tools_model(v), width=300)
        self._switch(card, "Bulle « je réfléchis »", "Pendant qu'elle prépare sa réponse (ou cherche un resto) : "
                     "une petite bulle avec le temps écoulé.",
                     "bulle_reflexion", default=True)
        def _ronds(v):
            self.cfg["ressources_ronds"] = v
            c.save_cfg() if hasattr(c, "save_cfg") else None
            c._update_mask()
            c.reset_input_box()
        self._combo(card, "Petits ronds des ressources", "Processeur, mémoire, carte graphique en temps réel, dans le "
                    "rond 📊 à côté d'elle : passe la souris dessus pour voir le détail. Vert : tranquille · orange : "
                    "occupé · rouge : à fond.",
                    [("Toujours", "toujours"), ("Seulement quand elle réfléchit", "reflexion"), ("Jamais", "jamais")],
                    self.cfg.get("ressources_ronds", "toujours"), _ronds)
        h = QHBoxLayout()
        h.addWidget(self._button("👀 Voir la bulle", lambda: c.think_preview()))
        h.addStretch(1)
        card.addLayout(h)
        if getattr(c, "learn", None) is not None or self.cfg.get("apprendre", True) is False:
            self._card_learn(self._card("Ce qu'elle a appris sur toi"))
        card = self._card("Modèle local (Ollama)")
        self._ollama_card = card.parentWidget()
        self._info(card, ("✅ Ollama fonctionne : elle peut discuter, sans internet." if c.ollama_ok
                          and not c.ia_remote() else
                          "Ollama : gratuit, privé, tout reste sur ton PC. Clique sur « Installer / "
                          "choisir un modèle » pour l'installer."))
        live = c.ollama_list() or list(c.ollama_models)          # liste à jour (modèles téléchargés depuis)
        if live:
            self._combo(card, "Modèle utilisé", "Son cerveau pour discuter (et traduire, si tu n'as pas choisi "
                        "de modèle à part ci-dessus).", [(m, m) for m in live],
                        self.cfg.get("ollama_model"), lambda v: c._set_model(v), width=260)
        self._buttons(card, self._button("Installer / choisir un modèle…", c.open_models, True),
                      self._button("Discuter avec elle…", c.ask_chat))
        if hasattr(c, "open_add_ai"):
            self._buttons(card, self._button("🧩  Ajouter une IA téléchargée (glisser un fichier .gguf)…",
                                             lambda: c.open_add_ai(), True))
            self._info(card, "Un modèle trouvé sur Hugging Face ou ailleurs : télécharge son fichier .gguf, puis "
                             "glisse-le dans cette fenêtre. Il apparaît ensuite dans la liste « Modèle utilisé ».")
        card = self._card("Mémoire")
        n = len(c.memory.get("faits", []))
        self._info(card, f"Elle se souvient de {n} chose{'s' if n > 1 else ''} sur toi. Tout reste sur ton PC.")
        self._buttons(card, self._button("Voir / modifier ses souvenirs…", c.edit_memory))
        card = self._card("Internet (seulement quand tu demandes)")
        self._switch(card, "Mode web", "« cherche sur internet … » : elle cherche et te résume.", "web",
                     default=True)
        self._switch(card, "Recherche de fichiers sur ton PC", "« trouve ma facture en pdf » (local).",
                     "file_search", default=True)
        card = self._card("🔎 Où elle cherche tes fichiers")
        self._info(card, "Ton dossier perso, puis tes autres disques montés (/mnt, /media, /run/media…). "
                         "Si elle ne trouve rien, elle regarde aussi les dossiers cachés (.config, .local/share…). "
                         "Exemples : « trouve mon CV », « le pdf téléchargé hier », « mes captures d'écran », "
                         "« trouve les fichiers cachés de mon jeu ».")
        self._switch(card, "Toujours inclure les dossiers cachés", "Plus lent, mais trouve sauvegardes de jeux et "
                     "fichiers de config du premier coup.", "recherche_cachee", default=False)
        self.rd_list = QListWidget()
        self.rd_list.setObjectName("liste")
        self.rd_list.setMaximumHeight(120)
        for d in self.cfg.get("recherche_dossiers", []):
            self.rd_list.addItem(d)
        card.addWidget(self.rd_list)

        def add_dir():
            from PyQt6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(self, "Dossier où chercher aussi", str(Path.home()))
            if d and d not in self.cfg.setdefault("recherche_dossiers", []):
                self.cfg["recherche_dossiers"].append(d)
                self.rd_list.addItem(d)
                self.C.save_config(self.cfg)

        def del_dir():
            it = self.rd_list.currentItem()
            if it and it.text() in self.cfg.get("recherche_dossiers", []):
                self.cfg["recherche_dossiers"].remove(it.text())
                self.rd_list.takeItem(self.rd_list.row(it))
                self.C.save_config(self.cfg)
        self._buttons(card, self._button("➕ Ajouter un dossier…", add_dir, True),
                      self._button("Retirer", del_dir))
        self._end()


    def _page_langues(self):
        c, C = self.comp, self.C
        self._page("🌍", "Langues", "La langue dans laquelle elle te parle, t'écoute et lit.")
        card = self._card("Langue parlée")
        V = getattr(C, "voix", None)
        if V:
            lang = self.cfg.get("langue", "fr")
            self._combo(card, "Elle parle", "Elle te répond, t'écoute au micro et parle avec une voix de cette "
                        "langue.",
                        [(v[0], k) for k, v in V.LANGUES.items()], lang,
                        lambda v: (c.set_language(v, self.cfg.get("langue_mode", "naturel")), self._refresh()),
                        width=260)
            if lang != "fr":
                self._combo(card, "Façon de parler", "",
                            [("Naturellement, dans cette langue", "naturel"),
                             ("Pour pratiquer : elle corrige mes fautes (en français)", "pratique")],
                            self.cfg.get("langue_mode", "naturel"),
                            lambda v: c.set_language(lang, v), width=300)
                inst = V.installed_voices(C.VOICE_DIRS, lang)
                if inst:
                    opts = []
                    for stem, path in inst:
                        sp = V.speakers_of(path)
                        opts += ([(f"{stem} — {n}", f"{stem}|{i}") for i, n in sp] if sp else [(stem, f"{stem}|-1")])
                    p = (self.cfg.get("voix_langue") or {}).get(lang) or {}
                    cur = f"{p.get('voice', inst[0][0])}|{p.get('speaker', -1)}"
                    self._combo(card, f"Sa voix en {V.LANGUES[lang][1]}", "", opts, cur,
                                lambda v: c.set_lang_voice(lang, v.split("|")[0], int(v.split("|")[1])), width=300)
                else:
                    self._info(card, f"Pas encore de voix en {V.LANGUES[lang][1]} : elle écrit dans ses bulles et "
                                     "parle avec une voix de secours. Télécharge une voix ci-dessous.")
                self._buttons(card, self._button(f"🗣️  Voix en {V.LANGUES[lang][1]}…",
                                                 lambda: c.open_voice_catalog(lang), not inst))
            self._info(card, "Astuce : dis-lui « parle-moi en espagnol », « pratiquons l'allemand » ou "
                             "« repasse en français ».")
        else:
            self._info(card, "Module voix.py absent : elle reste en français.")
        card = self._card("Langue des menus")
        I = getattr(C, "i18n", None)
        if I:
            self._combo(card, "Menus et fenêtres", "Les réglages, le clic droit et les fenêtres de Viki. "
                        "Ça ne change pas la langue dans laquelle elle te parle (au-dessus).",
                        [(n, k) for k, n in I.LANGS], self.cfg.get("langue_menus", "fr"),
                        lambda v: c.set_menu_language(v), width=260)
        else:
            self._info(card, "Module i18n.py absent : les menus restent en français.")
        self._end()

    # ------------------------------------------------------------- IA en ligne
    def _card_ia(self, card):
        c, C = self.comp, self.C
        api = C.ia_api
        if not api:
            self._info(card, "Module ia_api.py absent : seulement Ollama (local).")
            return
        self._sig = _Signal()
        self._sig.done.connect(lambda fn, res: fn(res))
        s = api.load_settings()
        prov = QComboBox()
        prov.setMinimumWidth(300)
        prov.setMaxVisibleItems(16)
        from PyQt6.QtGui import QStandardItem
        last = None
        for pid, f in api.FOURNISSEURS.items():
            if f["tarif"] != last:                      # petit titre de groupe, non sélectionnable
                last = f["tarif"]
                prov.addItem(api.TARIFS[last].upper(), None)
                it = prov.model().item(prov.count() - 1)
                it.setEnabled(False)
            prov.addItem("     " + f["court"], pid)
            prov.setItemData(prov.count() - 1, f["info"], Qt.ItemDataRole.ToolTipRole)
        prov.setCurrentIndex(max(0, prov.findData(s.get("fournisseur", "ollama"))))
        self._row(card, "Qui la fait réfléchir ?",
                  "💻 sur ton PC : gratuit et privé.  🆓 gratuit : en ligne, avec des limites par jour.  "
                  "💳 payant : il faut acheter du crédit sur le site.", prov)
        tarif = QLabel("")
        tarif.setObjectName("info")
        tarif.setWordWrap(True)
        card.addWidget(tarif)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        card.addWidget(box)
        warn = QLabel("🌐 Avec une IA en ligne, tes messages (et les textes à traduire, corriger, résumer…) "
                      "sont envoyés à ce service. Sa mémoire de toi reste sur ton PC, mais elle est jointe "
                      "aux messages. La clé est gardée sur ton PC, dans un fichier lisible par toi seul.")
        warn.setObjectName("info")
        warn.setWordWrap(True)
        v.addWidget(warn)
        url = QLineEdit()
        url.setMinimumWidth(280)
        url.setPlaceholderText("http://localhost:1234/v1")
        url_row = QWidget()
        ul = QVBoxLayout(url_row)
        ul.setContentsMargins(0, 0, 0, 0)
        self._row(ul, "Adresse du serveur", "Se termine en général par /v1.", url)
        v.addWidget(url_row)
        key = QLineEdit()
        key.setMinimumWidth(280)
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("colle ta clé ici (sk-…)")
        self._row(v, "Clé API", "Crée-la sur le site du fournisseur (bouton « Obtenir une clé »).", key)
        model = QComboBox()
        model.setEditable(True)
        model.setMinimumWidth(280)
        self._row(v, "Modèle", "Les petits modèles (mini, flash, haiku…) sont rapides et pas chers.", model)
        status = QLabel("")
        status.setObjectName("aide")
        status.setWordWrap(True)
        b_get = self._button("Obtenir une clé…", lambda: None)
        b_list = self._button("Lister les modèles", lambda: None)
        b_test = self._button("Tester", lambda: None, True)
        self._buttons(v, b_test, b_list, b_get)
        v.addWidget(status)

        def pid():
            return prov.currentData()

        def fill():
            p = pid()
            remote = p != "ollama"
            box.setVisible(remote)
            if getattr(self, "_ollama_card", None):
                self._ollama_card.setVisible(not remote)
            f = api.FOURNISSEURS.get(p, {})
            tarif.setText(f"{api.TARIFS[f['tarif']]} — {f['court']} : {f['info']}.")
            if not remote:
                return
            conf = api.conf_from(api.load_settings(), p)
            url_row.setVisible(p == "perso")
            key.setPlaceholderText("facultatif" if p == "perso" else
                                   "facultatif (une clé gratuite donne plus de messages)" if f.get("sans_cle")
                                   else "colle ta clé ici")
            for w, val in ((url, conf["url"]), (key, conf["cle"])):
                w.blockSignals(True)
                w.setText(val)
                w.blockSignals(False)
            model.blockSignals(True)
            model.clear()
            if conf["modele"]:
                model.addItem(conf["modele"])
            model.setCurrentText(conf["modele"])
            model.blockSignals(False)
            b_get.setVisible(bool(api.FOURNISSEURS[p].get("cle_url")))
            status.setText("✅ Prête." if api.ready(conf) and c.ia_remote() and c.ollama_ok else
                           ("Clique sur « Tester » pour vérifier." if api.ready(conf)
                            else "Il manque la clé."))
            if conf.get("anonyme"):
                status.setText(status.text() + "  Sans clé : réponses lentes, et tes messages passent par "
                               "un service public — évite d'y mettre des infos personnelles.")

        def save(*_):
            p = pid()
            if p == "ollama":
                return
            st = api.load_settings()
            d = st.setdefault("api", {}).setdefault(p, {})
            d["cle"] = key.text().strip()
            d["modele"] = model.currentText().strip()
            if p == "perso":
                d["url"] = url.text().strip()
            api.save_settings(st)
            c.recheck_ollama()

        def on_prov(_):
            if pid() is None:                          # titre de groupe : on ne bouge pas
                return
            c.set_ia_provider(pid())
            fill()

        def run(work, then):
            status.setText("…")
            threading.Thread(target=lambda: self._sig.done.emit(then, work()), daemon=True).start()

        def do_test():
            save()
            conf = api.conf_from(api.load_settings(), pid())
            if not api.ready(conf):
                status.setText("⚠️ Colle d'abord ta clé et choisis un modèle.")
                return

            def then(res):
                ok, msg = res
                status.setText(("✅ Ça marche ! Elle utilise maintenant " + conf["nom"] + ".") if ok
                               else "❌ " + msg)
                if ok:
                    c.recheck_ollama()
                    c.say("Me voilà avec un nouveau cerveau ! On discute ?")
            run(lambda: api.test(conf), then)

        def do_list():
            save()
            conf = api.conf_from(api.load_settings(), pid())

            def work():
                try:
                    return api.list_models(conf)
                except Exception as e:
                    return api.explain_error(e)

            def then(res):
                if isinstance(res, str):
                    status.setText("❌ " + res)
                    return
                cur = model.currentText()
                model.blockSignals(True)
                model.clear()
                model.addItems(res)
                model.setCurrentText(cur if cur in res or not res else res[0])
                model.blockSignals(False)
                save()
                status.setText(f"{len(res)} modèles trouvés. Choisis-en un puis « Tester ».")
            run(work, then)

        def do_get():
            u = api.FOURNISSEURS[pid()].get("cle_url")
            if u:
                subprocess.Popen(["xdg-open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)

        for b, fn in ((b_test, do_test), (b_list, do_list), (b_get, do_get)):
            b.clicked.disconnect()
            b.clicked.connect(fn)
        prov.currentIndexChanged.connect(on_prov)
        key.editingFinished.connect(save)
        url.editingFinished.connect(save)
        model.activated.connect(save)
        model.lineEdit().editingFinished.connect(save)
        QTimer.singleShot(0, fill)

    def _card_menus(self):
        c, C = self.comp, self.C
        card = self._card("🧭 Menu et raccourcis")
        items = [("Court : 6 rubriques + recherche (conseillé)", "court"), ("Simple : juste l'essentiel", "simple"),
                 ("Complet : toutes les options", "complet")]
        if not getattr(C, "raccourcis", None):
            items = items[1:]

        def set_style(v):
            self.cfg["menu_clic"] = v
            self.cfg["menu_complet"] = v == "complet"
            C.save_config(self.cfg)
            c._rebuild_menus()
        self._combo(card, "Clic droit sur elle", "Le menu court garde tout : la rubrique « Tout le menu » contient "
                    "toutes les options.", items, c.menu_style(), set_style, 300)
        if getattr(C, "raccourcis", None):
            R = C.raccourcis
            self._switch(card, "Raccourcis à côté d'elle", "Une petite colonne de boutons ronds qui la suit.",
                         "barre_raccourcis", on_change=lambda v: R.update_bar(c), default=False)
            self._combo(card, "Côté", "", [("Automatique", "auto"), ("À droite", "droite"), ("À gauche", "gauche")],
                        self.cfg.get("barre_cote", "auto"), lambda v: (self._set("barre_cote", v), R.update_bar(c)), 160)
            self._combo(card, "Taille des boutons", "", [("Petits", 30), ("Moyens", 38), ("Grands", 48)],
                        int(self.cfg.get("barre_taille", 38)), lambda v: (self._set("barre_taille", v),
                                                                          R.update_bar(c)), 160)
            self._switch(card, "Seulement quand la souris passe sur elle", "Sinon, toujours visibles.", "barre_survol",
                         default=False)
            self._buttons(card, self._button("✏️  Choisir mes raccourcis…", lambda: c.open_home(True), True),
                          self._button("🏠  Ouvrir l'accueil", lambda: c.open_home()))

    def _page_apparence(self):
        c, C = self.comp, self.C
        self._page("🎨", "Apparence", "Couleurs des fenêtres, bulle, effets, décor et petit chat.")
        self._card_menus()
        if getattr(C, "fond_couleurs", None):
            card = self._card("🖼️ Couleurs de mon fond d'écran")
            self._switch(card, "Prendre les couleurs de mon fond d'écran", "Fenêtres, menus et ronds prennent la "
                         "couleur de ton fond, et changent avec lui (KDE, GNOME, Cinnamon, MATE, Xfce).",
                         "couleurs_fond_ui", default=bool(self.cfg.get("couleurs_fond")),
                         on_change=lambda v: c.couleurs_fond(bool(v)))

            def choisir():
                from PyQt6.QtWidgets import QFileDialog
                p, _f = QFileDialog.getOpenFileName(self, "Mon fond d'écran", str(Path.home()),
                                                    "Images (*.png *.jpg *.jpeg *.webp)")
                if p:
                    self.cfg["fond_image"] = p
                    c.couleurs_fond(True)
            self._buttons(card, self._button("🖼️  Choisir l'image moi-même…", choisir))
        if self.apple:
            card = self._card("🪟 Style des fenêtres")
            self._switch(card, "Fenêtres en verre dépoli", "Les réglages laissent voir ton bureau derrière, flouté (sur "
                         "KDE). Sur GNOME et les autres bureaux, où le flou n'existe pas : un fond uni, bien lisible. "
                         "Prend effet à la prochaine ouverture des réglages.", "fenetres_verre", default=True)
        card = self._card("🔤 Police")
        self._switch(card, "Garder la police de mon bureau", "Par défaut, Viki utilise sa propre police (Inter) pour "
                     "avoir des textes nets et de la même taille sur KDE, GNOME, Xfce… Active ceci pour reprendre la "
                     "police de ton bureau. Prend effet au prochain lancement.", "police_systeme_ui",
                     default=self.cfg.get("police") == "systeme",
                     on_change=lambda v: (self.cfg.__setitem__("police", "systeme" if v else "viki"),
                                          self.C.save_config(self.cfg)))
        if getattr(C, "apparence", None):
            card = self._card("👗 Son apparence")
            self._info(card, "Change la couleur de ses cheveux, de sa peau, de ses yeux, de son pull, de sa jupe, de ses "
                             "collants, de ses chaussures et de sa barrette, avec des motifs (rayures, carreaux, pois…) "
                             "et des looks tout prêts. Ou dis-le-lui : « des cheveux roses », « un pull rayé bleu et "
                             "blanc », « look gothique ».")
            self._buttons(card, self._button("👗  Mon apparence…", c.open_look, True))
            self._switch(card, "Contours propres", "Enlève le liseré blanc qui reste parfois autour d'un personnage "
                         "détouré.", "contours_propres", default=True, on_change=lambda v: c.set_look({}, motion=""))
        if getattr(C, "fun", None):
            card = self._card("❄️ Effets de saison à l'écran")
            self._info(card, "Neige à Noël, chauves-souris à Halloween, cœurs à la Saint-Valentin… Ça passe "
                             "par-dessus tes fenêtres mais la souris passe au travers. Coupé en mode batterie, en "
                             "plein écran et avec « moins de mouvement ». Son anniversaire : le jour où tu l'as "
                             "installée 🎂.")
            self._switch(card, "Effets à l'écran", "", "effets_ecran", default=True, on_change=lambda v: c._fun_tick())
            self._combo(card, "Quand ?", "", [("Seulement les jours de fête", "fetes"),
                                              ("Toute l'année, selon la saison", "saison"), ("Jamais", "jamais")],
                        self.cfg.get("effets_quand", "fetes"),
                        lambda v: (self._set("effets_quand", v), c.set_overlay(None)), width=260)
            self._buttons(card, self._button("❄️  Faire neiger", lambda: c.set_overlay("noel")),
                          self._button("🍂  Feuilles", lambda: c.set_overlay("automne")),
                          self._button("🎉  Confettis", lambda: c.confetti(6)),
                          self._button("⏹  Arrêter", lambda: c.set_overlay("")))
        if _th:
            card = self._card("Couleurs des fenêtres")
            self._combo(card, "Thème", "Les réglages et les fenêtres de Viki (manga, lecture, PC…). Les fenêtres déjà "
                        "ouvertes changent quand tu les rouvres.", _th.choices(), _th.current(),
                        lambda v: c.set_theme(v), width=300)
            if _th.current() in ("perso", "perso_sombre"):
                self._buttons(card, self._button("🎨  Choisir ma couleur…", c.pick_theme_color, True))
            elif _th.current() in ("auto", "systeme"):
                self._info(card, "En ce moment : " + {"graphite": "🩶 Graphite (clair)",
                                                       "nuit": "🌌 Nuit (sombre)"}.get(_th.effective(), "")
                           + (". Le soir (20 h – 7 h), elle passe en sombre." if _th.current() == "auto" else
                              ". Ça suit le réglage clair / sombre de ton bureau."))
        card = self._card("Bulle")
        self._combo(card, "Thème", "", [(lab, k) for k, lab in C.BUBBLE_THEME_NAMES.items()],
                    self.cfg.get("bubble_theme", "classique"), lambda v: c._set_bubble(theme=v))
        self._combo(card, "Taille du texte", "",
                    [("Petite", 9.5), ("Normale", 10.5), ("Grande", 12.5), ("Très grande", 14.5)],
                    float(self.cfg.get("bubble_size", 10.5)), lambda v: c._set_bubble(size=v))
        card = self._card("Animation")
        self._switch(card, "Effet 3D", "Elle se tourne un peu vers ta souris.", "relief_3d")
        self._combo(card, "Intensité de la 3D", "", [("Légère", 0.6), ("Normale", 1.0), ("Forte", 1.5)],
                    float(self.cfg.get("relief_force", 1.0)), lambda v: self._set("relief_force", v))
        self._switch(card, "Tête et cheveux animés", "", "head_hair_anim")
        self._switch(card, "Ses yeux suivent la souris", "", "eye_follow")
        if C.extras:
            self._switch(card, "Accessoires de fêtes", "Bonnet de Noël, chapeau d'Halloween…", "fetes",
                         lambda v: c._update_fete(), default=True)
            card = self._card("Petit compagnon")
            self._combo(card, "Qui la suit", "Un petit animal à ses pieds. Clique dessus pour un câlin.",
                        [("Personne", ""), ("🐱 Chat roux", "roux"), ("🐱 Chat gris", "gris"), ("🐱 Chat noir", "noir"),
                         ("🐱 Chat blanc", "blanc"), ("🐱 Chat tigré", "tigre"), ("🐰 Lapin blanc", "lapin"),
                         ("🐰 Lapin rose", "lapin_rose"), ("🐥 Poussin", "poussin"), ("🐹 Hamster", "hamster")],
                        self.cfg.get("pet", ""), lambda v: c.set_pet(v))
        if C.lieux:
            card = self._card("Décor")
            self._combo(card, "Lieu", "", [("Sur le bureau (sans décor)", "")] +
                        [(lab, k) for k, lab in C.lieux.LIEUX.items()], self.cfg.get("lieu", ""),
                        lambda v: c.set_lieu(v))
            self._switch(card, "Change de lieu selon l'heure", "", "lieu_auto", lambda v: c._auto_lieu())
            self._combo(card, "Météo des décors", "La météo réelle utilise internet.",
                        [("Automatique (saison)", "auto")] + [(lab, k) for k, lab in C.lieux.METEOS.items()] +
                        [("Météo réelle de ma ville…", "reelle")], self.cfg.get("meteo", "auto"),
                        lambda v: c.set_weather(v))
        self._end()

    def _page_micro(self):
        c, C = self.comp, self.C
        self._page("🎙", "Micro et écoute", "Lui parler à voix haute. La reconnaissance vocale reste sur ton PC.")
        card = self._card("Micro")
        if c.stt_installed is False:
            self._info(card, "La reconnaissance vocale n'est pas encore installée.")
            self._buttons(card, self._button("Installer la reconnaissance vocale", c.install_stt, True))
        self._buttons(card, self._button("🎤  Lui parler maintenant", c.toggle_mic, True),
                      self._button("🔧  Tester le micro", c.test_mic),
                      self._button("Journal du micro…", c.show_mic_log),
                      self._button("⌨️  Raccourcis clavier…", c.show_shortcut_help))
        self._combo(card, "Oreille (reconnaissance vocale)", "Plus rapide = réponse plus vite, mais comprend un "
                    "peu moins bien.", [("Automatique", "auto"), ("Très rapide (tiny)", "tiny"),
                                        ("Rapide (base, conseillé)", "base"), ("Précise (small, plus lente)", "small")],
                    self.cfg.get("stt_model", "auto"), lambda v: (self._set("stt_model", v), c._restart_stt()),
                    width=260)
        if C.extras and not C.GUEST:
            card = self._card("Écoute continue")
            name = c.char.get("name", "son prénom")
            self._combo(card, "Elle t'écoute…", f"Mode prénom : dis « {name}, quelle heure est-il ? ».",
                        [("Non, seulement quand je clique sur le micro", ""), (f"Quand je dis « {name} »", "nom"),
                         ("Tout le temps (conversation)", "conversation")], self.cfg.get("wake", ""),
                        lambda v: c.set_wake(v), width=300)
        self._end()

    def _page_assistant(self):
        c, C = self.comp, self.C
        self._page("🧰", "Assistant", "Presse-papiers, agenda, mails, PC, rangement et projets de code.")
        card = self._card("Presse-papiers")
        self._switch(card, "Proposer de résumer, traduire ou corriger", "Quand tu copies un long texte "
                     "(il faut Ollama).", "clip_watch", default=True)
        card = self._card("Notifications")
        self._combo(card, "Elle lit tes notifications", "Tout se passe sur ton PC.",
                    [("Non", ""), ("Juste le nom de l'appli", "app"), ("L'appli et le titre", "titre"),
                     ("Tout (avec le début du message)", "tout")], self.cfg.get("notif_lire", "titre"),
                    lambda v: c.set_notif_mode(v), width=260)
        ign = QLineEdit(self.cfg.get("notif_ignore", ""))
        ign.setPlaceholderText("ex : Spotify, Steam")
        ign.setMinimumWidth(260)
        ign.editingFinished.connect(lambda: self._set("notif_ignore", ign.text()))
        self._row(card, "Applis à ignorer", "Séparées par des virgules.", ign)
        card = self._card("Contrôle du PC et lecture")
        self._info(card, "Dis-lui : « monte le son », « baisse la luminosité », « verrouille l'écran », "
                         "« mets le PC en veille », « éteins le PC dans une heure » (« annule l'extinction »), "
                         "« lis-moi ce que j'ai copié », « raconte-moi une histoire », « dictée ».")
        self._buttons(card, self._button("📚  Mode lecture (livres)…", lambda: c.open_reader(), True),
                      self._button("📖  Histoire du soir", lambda: c.tell_story()),
                      self._button("🔊  Lire le presse-papiers", lambda: c.clip_action("lire")),
                      self._button("⌨️  Dictée", c.start_dictation))
        ch = C.piper_voice_choices()
        self._combo(card, "Voix des dialogues (livres)", "Les phrases entre guillemets « … » ou après un tiret — "
                    "sont lues avec une autre voix que le récit.",
                    [("Une seule voix (la sienne)", ""), ("Automatique (une autre voix installée)", "auto")] +
                    [(lab, f"{stem}|{spk}") for stem, lab, spk in ch], self.cfg.get("lecture_dialogues", "auto"),
                    lambda v: self._set("lecture_dialogues", v), width=300)
        # --- mode streamer
        if getattr(C, "streamer", None):
            card = self._card("Mode streamer (Twitch)")
            self._info(card, "Pendant ton live, elle lit le chat de ta chaîne et répond de temps en temps dans sa "
                             "bulle (tes spectateurs la voient à l'écran). Lecture seule, sans compte ni mot de "
                             "passe ; elle n'écrit jamais dans le chat. Utilise internet seulement quand c'est lancé. "
                             "Elle ignore les liens, les commandes « ! » et les bots, et refuse les messages "
                             "insultants. Ou dis-lui « mode streamer ».")
            ed = QLineEdit(self.cfg.get("stream_chaine", ""))
            ed.setPlaceholderText("ta chaîne (pseudo ou lien twitch.tv/…)")
            ed.setMinimumWidth(260)
            ed.editingFinished.connect(lambda: self._set("stream_chaine", C.streamer.channel_of(ed.text())))
            self._row(card, "Chaîne Twitch", "", ed)
            self._combo(card, "Elle répond au plus", "", [("Toutes les 10 s", 10), ("Toutes les 25 s", 25),
                                                          ("Toutes les minutes", 60), ("Toutes les 3 minutes", 180)],
                        int(self.cfg.get("stream_pause", 25)), lambda v: self._set("stream_pause", v), width=220)
            on = bool(getattr(c, "stream", None))
            self._buttons(card, self._button("⏹  Arrêter" if on else "▶  Lancer le mode streamer",
                                             (lambda: (c.stop_streamer(), self._refresh())) if on else
                                             (lambda: (c.start_streamer(ed.text() or None), self._refresh())), not on))
            if hasattr(C.streamer, "parse_event"):
                self._switch(card, "Alertes", "Elle remercie les abonnements, réabonnements, abonnements offerts, "
                             "raids et bits (avec des confettis).", "stream_alertes", default=True)
            self._info(card, "YouTube : son chat demande une clé d'accès Google, pas encore pris en charge.")
        card = self._card("Agenda")
        files = c.agenda_files()
        self.agenda_info = self._info(card, f"{len(files)} calendrier(s) suivi(s)" +
                                      (" : " + ", ".join(Path(f).name for f in files[:4]) if files else
                                       ". Ajoute un fichier .ics (exporté de ton agenda)."))
        self._switch(card, "Trouver mes calendriers automatiquement", "KOrganizer, Evolution…", "agenda_auto",
                     default=True)
        self._combo(card, "Me prévenir avant un rendez-vous", "",
                    [(f"{m} minutes avant", m) for m in (5, 10, 15, 30, 60)], int(self.cfg.get("agenda_avance", 15)),
                    lambda v: self._set("agenda_avance", v))
        if getattr(C, "pratique", None):
            web = self.cfg.get("agendas_web", [])
            self._info(card, "🌐 Agendas en ligne : " + (", ".join(C.pratique.cal_kind(u) for u in web) +
                                                        " (mis à jour toutes les heures)" if web else
                                                        "aucun. Google Agenda, Nextcloud, Outlook, iCloud… : colle "
                                                        "l'adresse iCal secrète, elle reste sur ton PC."))
            self._buttons(card, self._button("🌐  Ajouter un agenda en ligne…", lambda: (c.add_web_calendar(),
                                                                                       self._refresh())),
                          *([self._button("Retirer mes agendas en ligne", lambda: ([c.remove_web_calendar(u) for u in
                                                                                    list(web)], self._refresh()))]
                            if web else []))
        self._buttons(card, self._button("Ajouter un calendrier (.ics)…", self._add_ics),
                      self._button("Retirer mes calendriers ajoutés", self._clear_ics),
                      self._button("Mon agenda aujourd'hui", lambda: c.agenda_say("aujourd'hui")))
        card = self._card("Ton PC")
        st = C.extras.pc_status()
        self._info(card, C.extras.pc_status_text(st))
        self._switch(card, "Surveiller le PC", "Disque presque plein, carte graphique ou processeur trop chauds.",
                     "pc_watch", default=True)
        self._switch(card, "Vérifier les mises à jour toutes les 6 h", "Utilise internet (paquet pacman-contrib).",
                     "updates_check")
        btns = [self._button("Ranger mes téléchargements…", c.tidy_downloads),
                self._button("Nettoyer le PC…", c.open_cleaner),
                self._button("Réorganiser un dossier…", lambda: c.open_tidy()),
                self._button("Y a-t-il des mises à jour ?", lambda: c._extra_command("y a des mises a jour",
                                                                                      "y a des mises a jour"))]
        if (C.CONFIG_DIR / "rangement.json").exists():
            btns.insert(1, self._button("Annuler le dernier rangement", c.undo_tidy))
        self._buttons(card, *btns)
        card = self._card("Notes et journal")
        self._buttons(card, self._button("Mes notes…", lambda: c.open_notes("notes")),
                      self._button("Liste de courses…", lambda: c.open_notes("courses")),
                      self._button("Mon journal…", c.show_journal))
        if getattr(C, "manga", None):
            self._card_manga(self._card("Traduction de manga"))
        if getattr(C, "mails", None):
            self._card_mails(self._card("Mails"))
        if not getattr(C, "dev", None):
            self._card_dev(self._card("Projets de code (développeurs)"))
        self._end()

    # ---------- apprentissage
    def _card_learn(self, card):
        c = self.comp
        self._switch(card, "S'habituer à moi avec le temps", "Elle retient tes horaires, si ses phrases te "
                     "plaisent, tes consignes et la longueur de réponse que tu préfères. Tout reste sur ton PC.",
                     "apprendre", lambda v: self._learn_toggle(v), default=True)
        L = getattr(c, "learn", None)
        if not L:
            return
        self._info(card, "\n".join(x for x in L.summary() if not x.startswith("•")) + "\n\nDis-lui par exemple : « arrête de me parler de la "
                         "météo », « j'aime bien quand tu fais des blagues », « trop long », "
                         "« qu'est-ce que tu as appris sur moi ? »")
        self.rules_box = QVBoxLayout()
        card.addLayout(self.rules_box)
        self._fill_rules()
        self._buttons(card, self._button("Ses souvenirs sur toi…", c.edit_memory),
                      self._button("Oublier mes habitudes", lambda: (L.reset(), self._fill_rules(),
                                                                     c.say("C'est oublié. On repart de zéro !"))))

    def _fill_rules(self):
        L = getattr(self.comp, "learn", None)
        while self.rules_box.count():
            it = self.rules_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
            elif it.layout():
                while it.layout().count():
                    x = it.layout().takeAt(0).widget()
                    if x:
                        x.deleteLater()
        if not L:
            return
        for i, r in enumerate(L.s["regles"]):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(("🚫 À éviter : « " if r["type"] == "evite" else "💗 Tu aimes : « ") + r["texte"] + " »")
            lab.setWordWrap(True)
            lab.setStyleSheet("color: #3d2733;")
            h.addWidget(lab, 1)
            b = QPushButton("Retirer")
            b.clicked.connect(lambda _=False, k=i: (L.remove_rule(k), self._fill_rules()))
            h.addWidget(b)
            self.rules_box.addWidget(row)

    def _learn_toggle(self, v):
        C = self.C
        self.comp.learn = C.apprentissage.Apprentissage() if v and C.apprentissage else None

    # ---------- manga
    def _card_manga(self, card):
        c, C = self.comp, self.C
        M = C.manga
        if not M.available():
            self._info(card, "Il me faut OpenCV pour trouver les bulles : installe le paquet « python-opencv ».")
            return
        mocr = c.manga_ocr_python()
        tl = M.tesseract_langs()
        self._info(card, "Donne-lui un manga (.cbz, .zip, dossier d'images, PDF…) : elle trouve les bulles, lit le "
                         "texte, le traduit avec ton IA et l'écrit à la place de l'original. Tu peux corriger chaque "
                         "bulle ensuite. Pour ton usage personnel.\n\nLecture du texte disponible :\n"
                         + ("✅" if mocr else "❌") + " manga-ocr (le meilleur pour le japonais)\n"
                         + self._vision_line() + "\n"
                         + ("✅" if tl else "❌") + " Tesseract" + (f" ({', '.join(sorted(tl)[:6])})" if tl else ""))
        # --- trouver le texte (bulles + hors bulles)
        if hasattr(M, "detector_ready"):
            if M.detector_ready():
                self._info(card, "✅ Détecteur de texte installé : elle trouve aussi le texte hors des bulles, les "
                                 "bulles sombres, les cartouches et les onomatopées.")
            else:
                self._info(card, "Pour trouver TOUT le texte (hors des bulles, bulles sombres, cartouches, "
                                 f"onomatopées) : télécharge le détecteur de texte ({M.DETECTOR_MB} Mo, une seule "
                                 "fois, depuis GitHub). Ensuite il tourne sur ton PC.")
                self._buttons(card, self._button(f"⬇️ Mieux trouver le texte ({M.DETECTOR_MB} Mo)",
                                                 c.install_text_detector, True))
        # --- quel modèle traduit
        have = c.ollama_list()
        items = [(f"Son cerveau ({c.ia_name()})", "")]
        items += [(n + ("  ⭐" if any(n == m[0] for m in M.MODELES) else ""), n) for n in have]
        items += [(f"⬇️ Télécharger {n} — {size} — {desc}", "pull:" + n) for n, size, desc in M.MODELES if n not in have]
        cur = self.cfg.get("manga_modele", "")
        holder = {}

        def model_changed(v):
            if v.startswith("pull:"):
                name = v[5:]
                cb = holder.get("cb")
                if cb:                                   # on revient sur le choix précédent pendant le téléchargement
                    cb.blockSignals(True)
                    cb.setCurrentIndex(max(0, cb.findData(self.cfg.get("manga_modele", ""))))
                    cb.blockSignals(False)
                c.pull_model(name, then=lambda ok, n=name: ok and (self._set("manga_modele", n),
                                                                  getattr(c, "manga_win", None) and
                                                                  c.manga_win.fill_models()))
                return
            self._set("manga_modele", v)
            mw = getattr(c, "manga_win", None)
            if mw:
                mw.fill_models()
        holder["cb"] = self._combo(card, "Traduit par", "Le modèle qui traduit les bulles. Les modèles Ollama restent "
                                   "sur ton PC ; ⬇️ = à télécharger (une fenêtre montre la progression).",
                                   items, cur if any(v == cur for _, v in items) else "", model_changed, width=380)
        # --- comment lire le texte
        self._combo(card, "Lecture du texte", "« Automatique » prend le meilleur outil installé.",
                    [("Automatique", "auto"), ("manga-ocr (japonais)", "mangaocr"), ("IA qui voit", "vision"),
                     ("Tesseract", "tesseract")], self.cfg.get("manga_lecteur", "auto"),
                    lambda v: self._set("manga_lecteur", v), width=260)
        vm = c.vision_models() if not c.ia_remote() else []
        if vm:
            self._combo(card, "Modèle qui voit", "Pour lire les bulles en mode « IA qui voit ».",
                        [(n, n) for n in vm], self.cfg.get("manga_vision", "") or vm[0],
                        lambda v: self._set("manga_vision", v), width=260)
        btns = [self._button("📖 Traduire un manga…", lambda: c.open_manga(), True)]
        if not mocr:
            btns.append(self._button("⬇️ Installer manga-ocr (≈1 Go)", c.install_manga_ocr))
        btns.append(self._button("⬇️ Modèle qui voit : qwen3-vl:4b (3,3 Go)", lambda: c.pull_vision_model("qwen3-vl:4b")))
        self._buttons(card, *btns)
        from PyQt6.QtGui import QFontDatabase
        fams = sorted(set(QFontDatabase.families()))
        pref = [f for f in M.POLICES if f in fams]
        items = [("Automatique (police BD si installée)", "")] + [(f, f) for f in pref + [f for f in fams if f not in pref]][:60]
        self._combo(card, "Police des bulles", "Astuce : installe une police style BD (ex : « Komika », "
                    "« Bangers », « Anime Ace ») pour un rendu plus manga.", items,
                    self.cfg.get("manga_police", ""), lambda v: self._set("manga_police", v), width=280)

    def _vision_line(self):
        c = self.comp
        if c.ia_remote():
            return "✅ IA qui voit : ton IA en ligne (si elle lit les images)"
        vm = c.vision_models()
        return ("✅ IA qui voit : " + ", ".join(vm[:3])) if vm else "❌ IA qui voit : aucun modèle Ollama qui voit"

    # ---------- mails
    def _card_mails(self, card):
        M = self.C.mails
        s = M.load()
        self._info(card, "Elle relève ta boîte de temps en temps, te prévient des nouveaux mails, et peut te "
                         "les lire ou les résumer (« j'ai des mails ? », « lis mes mails », « résume mes mails »). "
                         "La connexion se fait directement de ton PC à ta messagerie (IMAP) ; le mot de passe est "
                         "rangé dans un fichier que toi seul peux lire. Outlook / Hotmail ne sont pas pris en "
                         "charge (Microsoft n'accepte plus les mots de passe d'application).")
        fo = QComboBox()
        fo.setMinimumWidth(260)
        for k, f in M.FOURNISSEURS.items():
            fo.addItem(f[0], k)
        fo.setCurrentIndex(max(0, fo.findData(s.get("fournisseur", "gmail"))))
        self._row(card, "Messagerie", "", fo)
        help_lab = self._info(card, "")
        adr = QLineEdit(s.get("adresse", ""))
        adr.setPlaceholderText("toi@exemple.fr")
        adr.setMinimumWidth(260)
        self._row(card, "Adresse", "", adr)
        mdp = QLineEdit(s.get("mdp", ""))
        mdp.setEchoMode(QLineEdit.EchoMode.Password)
        mdp.setPlaceholderText("mot de passe d'application")
        mdp.setMinimumWidth(260)
        self._row(card, "Mot de passe d'application", "Pas ton mot de passe habituel : un mot de passe "
                  "spécial créé dans les réglages de sécurité de ton compte.", mdp)
        srv = QLineEdit(s.get("serveur", ""))
        srv.setPlaceholderText("imap.exemple.fr")
        srv.setMinimumWidth(200)
        port = QSpinBox()
        port.setRange(1, 65535)
        port.setValue(int(s.get("port") or 993))
        srv_row = QWidget()
        h = QHBoxLayout(srv_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(srv)
        h.addWidget(port)
        self._row(card, "Serveur IMAP et port", "Seulement pour « Autre ».", srv_row)
        itv = QComboBox()
        for lab, v in (("Toutes les 2 minutes", 2), ("Toutes les 5 minutes", 5), ("Toutes les 15 minutes", 15),
                       ("Toutes les 30 minutes", 30), ("Toutes les heures", 60)):
            itv.addItem(lab, v)
        itv.setCurrentIndex(max(0, itv.findData(int(s.get("intervalle", 5)))))
        self._row(card, "Relever la boîte", "", itv)
        actif = Switch(bool(s.get("actif")))
        self._row(card, "Me prévenir des nouveaux mails", "Elle le dit dans sa bulle (sauf en mode concentration "
                  "ou en plein écran).", actif)
        notif = Switch(bool(s.get("notif", True)))
        self._row(card, "Aussi en notification du bureau", "", notif)
        state = self._info(card, "")

        def cur():
            d = M.load()
            k = fo.currentData()
            d.update(fournisseur=k, adresse=adr.text().strip(), mdp=mdp.text().strip(),
                     serveur=srv.text().strip() if k == "autre" else "",
                     port=port.value() if k == "autre" else M.FOURNISSEURS[k][2],
                     intervalle=itv.currentData(), actif=actif.isChecked(), notif=notif.isChecked())
            return d

        def store(*_):
            d = cur()
            old = M.load()
            if (old.get("adresse"), old.get("fournisseur")) != (d["adresse"], d["fournisseur"]):
                d["vu"] = -1                    # nouvelle boîte : on repart de zéro, sans tout notifier
            M.save(d)

        def prov_changed(*_):
            f = M.FOURNISSEURS[fo.currentData()]
            help_lab.setText("ℹ️ " + f[3])
            srv_row.setEnabled(fo.currentData() == "autre")
        prov_changed()
        fo.currentIndexChanged.connect(lambda *_: (prov_changed(), store()))
        for w in (adr, mdp, srv):
            w.editingFinished.connect(store)
        port.valueChanged.connect(store)
        itv.currentIndexChanged.connect(store)
        actif.toggled.connect(store)
        notif.toggled.connect(store)

        def test():
            store()
            state.setText("Connexion…")
            d = cur()
            self.comp._bg(lambda: M.test(d), lambda r: state.setText(
                ("✅ Connecté : %s mail(s) non lu(s)." % r[1]) if not isinstance(r, Exception) and r[0]
                else "❌ " + (M.explain(r) if isinstance(r, Exception) else str(r[1]))))

        def key_page():
            url = M.FOURNISSEURS[fo.currentData()][4]
            if url:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._buttons(card, self._button("Tester", test, main=True),
                      self._button("📧 Voir mes mails", lambda: (store(), self.comp.mail_check(read=False))),
                      self._button("🔑 Créer un mot de passe d'application", key_page))

    # ---------- développeurs
    def _card_dev(self, card):
        c = self.comp
        self._info(card, "Le matin, elle te fait le point : fichiers pas commités, commits pas poussés. "
                         "Dis-lui aussi « fais le point sur mes projets ». Et « explique cette erreur » "
                         "(ou le bouton 🐞 de la barre) explique la dernière erreur copiée.")
        self.git_list = QLabel()
        self.git_list.setObjectName("info")
        self.git_list.setWordWrap(True)
        card.addWidget(self.git_list)
        self._refresh_git()
        self._switch(card, "Le point du matin", "Une fois par jour, à son premier bonjour.", "git_matin",
                     default=True)

        def add():
            from PyQt6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(self, "Dossier d'un projet Git", str(Path.home()))
            if not d:
                return
            if not (Path(d) / ".git").exists():
                return self.git_list.setText("⚠️ Ce dossier n'est pas un dépôt Git (pas de dossier .git).")
            lst = [p for p in self.cfg.get("projets_git", []) if p != d] + [d]
            self._set("projets_git", lst)
            self._refresh_git()
        self._buttons(card, self._button("➕ Ajouter un projet…", add),
                      self._button("Tout retirer", lambda: (self._set("projets_git", []), self._refresh_git())),
                      self._button("Faire le point maintenant", lambda: c.git_report()))
        self._info(card, "Commande « viki » dans le terminal : viki say \"texte\", viki emote 🎉, "
                         "viki run make (elle te prévient à la fin et propose d'expliquer l'erreur si ça rate), "
                         "viki jouer (à mettre sur un raccourci clavier dans les réglages KDE).")
        self._buttons(card, self._button("Installer la commande « viki »", c.install_cli))

    # ================================================================ page Développeur
    def _page_dev(self):
        c, C = self.comp, self.C
        D = C.dev
        self._page("💻", "Développeur", "Projets, terminal, serveurs, GitHub / GitLab, notes et temps de code.")
        self._card_dev(self._card("Projets de code"))
        if getattr(C, "devplus", None):
            card = self._card("Outils")
            self._info(card, "Sur ton projet en cours (le dernier modifié). Ou dis-lui : « relis mon code », « message "
                             "de commit », « pourquoi la CI a échoué », « mes conteneurs », « vérifie mes "
                             "dépendances », « comment on annule le dernier commit ? », « mode canard ».")
            self._buttons(card, self._button("🔍  Relire avant commit", c.code_review, True),
                          self._button("✍️  Message de commit", c.commit_message),
                          self._button("🧪  Échec de la CI", c.explain_ci))
            self._buttons(card, self._button("🛡️  Dépendances", c.deps_audit),
                          self._button("🐳  Docker", c.open_docker),
                          self._button("📊  Graphique du temps", c.time_chart),
                          self._button("📤  Export CSV", c.export_time))
            self._buttons(card, self._button("🦆  Mode canard", lambda: c._vie_dev_command("mode canard",
                                                                                        "mode canard")),
                          self._button("🎧  Musique pour coder", lambda: c.play_music("dev")))

        if getattr(C, "plus", None):
            card = self._card("Au fil du code")
            self._info(card, "« explique cette erreur » (copie-la d'abord), « garde ce code sous le nom … », « ressors "
                             "mon snippet … », « liste les TODO », « journal du projet ».")
            self._switch(card, "Propose d'expliquer une erreur copiée", "Quand tu copies un message d'erreur, elle te "
                         "le signale.", "clip_erreur", default=True)
            self._switch(card, "Journal de projet le soir", "Elle résume tes commits du jour dans tes projets suivis.",
                         "dev_journal_soir", default=True)
            self._buttons(card, self._button("🐞  Expliquer l'erreur copiée", c.explain_error, True),
                          self._button("💾  Mes snippets", c.show_snippets),
                          self._button("📌  TODO du projet", c.code_todos),
                          self._button("📓  Journal de projet", c.show_project_journal))

        card = self._card("Suivi automatique du terminal")
        self._info(card, "Quand une commande dure longtemps (compilation, tests, téléchargement…), elle te prévient "
                         "à la fin, même si tu as changé de fenêtre — sans taper « viki run ». Ajoute un petit bloc "
                         "à ton ~/.bashrc / ~/.zshrc (retirable d'un clic).")
        self._combo(card, "Me prévenir pour les commandes de plus de", "",
                    [("30 secondes", 30), ("1 minute", 60), ("2 minutes", 120), ("5 minutes", 300)],
                    int(self.cfg.get("terminal_seuil", 60)), lambda v: self._set("terminal_seuil", v))
        self.hook_state = self._info(card, "")

        def hook_refresh():
            self.hook_state.setText("✅ Installé (ouvre un nouveau terminal pour l'activer)." if D.hook_installed()
                                    else "Pas installé.")

        def hook_on():
            c.install_cli()
            files = D.install_hook(int(self.cfg.get("terminal_seuil", 60)))
            hook_refresh()
            c.say("C'est installé ! Ouvre un nouveau terminal : je te préviendrai à la fin des longues commandes."
                  if files else "Je n'ai trouvé ni bash ni zsh ni fish.")

        def hook_off():
            D.uninstall_hook()
            hook_refresh()
            c.say("C'est retiré de ton terminal.")
        hook_refresh()
        self._buttons(card, self._button("Installer", hook_on, True), self._button("Retirer", hook_off))

        card = self._card("Serveurs surveillés")
        self._info(card, "Elle te prévient quand un serveur local s'arrête ou revient (ex : ton serveur web de dev). "
                         "Ou dis-lui : « surveille le port 3000 ».")
        self.ports_box = QVBoxLayout()
        card.addLayout(self.ports_box)
        pn = QSpinBox()
        pn.setRange(1, 65535)
        pn.setValue(3000)
        nm = QLineEdit()
        nm.setPlaceholderText("nom (facultatif) : API, site…")
        roww = QWidget()
        h = QHBoxLayout(roww)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(pn)
        h.addWidget(nm, 1)
        self._row(card, "Port", "", roww)

        def add_port():
            D.add_port(D.load(), pn.value(), nm.text())
            nm.clear()
            self._fill_ports()
        self._buttons(card, self._button("➕ Surveiller ce port", add_port))
        self._fill_ports()

        card = self._card("GitHub / GitLab")
        self._card_forge(card)

        card = self._card("Notes de code")
        self._info(card, "Dis-lui « note de code : corriger le bug du menu » (projet en cours deviné tout seul) ou "
                         "« note de code pour monprojet : … ». Elle te les rappelle au point du matin.")
        self.notes_box = QVBoxLayout()
        card.addLayout(self.notes_box)
        self._fill_notes()

        card = self._card("Temps de code et statistiques")
        s = D.load()
        today, week = D.minutes(s, 1), D.minutes(s, 7)
        self._info(card, ("Aujourd'hui : " + (", ".join(f"{k} {D.fmt_min(v)}" for k, v in today.items()) or "rien") +
                          "\nCette semaine : " + (", ".join(f"{k} {D.fmt_min(v)}" for k, v in week.items()) or "rien") +
                          "\n\nCalculé tout seul : un projet suivi dont des fichiers changent compte comme du "
                          "temps de travail. Le lundi matin, elle te fait le bilan de la semaine (commits, temps)."))
        self._buttons(card, self._button("📊 Bilan de la semaine", c.week_report),
                      self._button("⏱️ Concentration 25 min", lambda: c.set_focus(25)))
        self._end()

    def _fill_ports(self):
        D = self.C.dev
        self._clear(self.ports_box)
        for p in D.load()["ports"]:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            up = D.port_up(p["port"], timeout=0.2)
            lab = QLabel(("🟢 " if up else "🔴 ") + D.port_label(p) + (" — répond" if up else " — arrêté"))
            h.addWidget(lab, 1)
            b = QPushButton("Retirer")
            b.clicked.connect(lambda _=False, pp=p["port"]: (D.remove_port(D.load(), pp), self._fill_ports()))
            h.addWidget(b)
            self.ports_box.addWidget(row)

    def _fill_notes(self):
        D = self.C.dev
        self._clear(self.notes_box)
        s = D.load()
        if not s["notes"]:
            self.notes_box.addWidget(QLabel("Aucune note pour l'instant."))
        for proj, lst in s["notes"].items():
            for i, n in enumerate(lst):
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                lab = QLabel(f"<b>{proj}</b> — {n['texte']} <span style='color:#9a8290'>({n['date']})</span>")
                lab.setWordWrap(True)
                h.addWidget(lab, 1)
                b = QPushButton("Fait ✓")
                b.clicked.connect(lambda _=False, pj=proj, k=i: (D.remove_note(D.load(), pj, k), self._fill_notes()))
                h.addWidget(b)
                self.notes_box.addWidget(row)

    def _clear(self, box):
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _card_forge(self, card):
        D = self.C.dev
        s = D.load()
        f = s["forge"]
        self._info(card, "Elle te prévient : relecture demandée, CI qui échoue, mention, assignation… "
                         "Utilise internet, avec ton propre jeton (rangé dans un fichier que toi seul peux lire). "
                         "GitHub : un jeton « classic » avec le droit notifications. GitLab : un jeton read_api.")
        svc = QComboBox()
        svc.addItem("GitHub", "github")
        svc.addItem("GitLab", "gitlab")
        svc.setCurrentIndex(max(0, svc.findData(f.get("service", "github"))))
        self._row(card, "Service", "", svc)
        url = QLineEdit(f.get("url", "https://gitlab.com"))
        url.setMinimumWidth(260)
        url_row = self._row(card, "Adresse GitLab", "Seulement pour GitLab (ton instance ou gitlab.com).", url)
        tok = QLineEdit(f.get("jeton", ""))
        tok.setEchoMode(QLineEdit.EchoMode.Password)
        tok.setMinimumWidth(260)
        tok.setPlaceholderText("ghp_… ou glpat-…")
        self._row(card, "Jeton d'accès", "", tok)
        itv = QComboBox()
        for lab, v in (("Toutes les 5 minutes", 5), ("Toutes les 10 minutes", 10), ("Toutes les 30 minutes", 30)):
            itv.addItem(lab, v)
        itv.setCurrentIndex(max(0, itv.findData(int(f.get("intervalle", 10)))))
        self._row(card, "Vérifier", "", itv)
        act = Switch(bool(f.get("actif")))
        self._row(card, "Me prévenir", "", act)
        state = self._info(card, "")

        def store(*_):
            s2 = D.load()
            old = s2["forge"]
            new = {"service": svc.currentData(), "url": url.text().strip() or "https://gitlab.com",
                   "jeton": tok.text().strip(), "intervalle": itv.currentData(), "actif": act.isChecked()}
            if (old.get("service"), old.get("jeton"), old.get("url")) != (new["service"], new["jeton"], new["url"]):
                new["vu"] = ""
            else:
                new["vu"] = old.get("vu", "")
            s2["forge"] = new
            D.save(s2)
            url.setEnabled(svc.currentData() == "gitlab")
        for w_ in (url, tok):
            w_.editingFinished.connect(store)
        svc.currentIndexChanged.connect(store)
        itv.currentIndexChanged.connect(store)
        act.toggled.connect(store)
        url.setEnabled(svc.currentData() == "gitlab")

        def test():
            store()
            state.setText("Connexion…")
            ff = D.load()["forge"]
            self.comp._bg(lambda: D.forge_test(ff), lambda r: state.setText(
                f"✅ Connecté en tant que {r[1]}." if not isinstance(r, Exception) and r[0]
                else "❌ " + (str(r) if isinstance(r, Exception) else r[1])))

        def token_page():
            u = ("https://github.com/settings/tokens/new?scopes=notifications&description=Viki"
                 if svc.currentData() == "github" else
                 url.text().rstrip("/") + "/-/user_settings/personal_access_tokens?name=Viki&scopes=read_api")
            self.C.open_link(u)
        self._buttons(card, self._button("Tester", test, True), self._button("🔑 Créer un jeton", token_page))

    # ================================================================ page Gestion du PC
    def _page_pc(self):
        c, C = self.comp, self.C
        G = C.gestionpc
        self._page("🖥️", "Gestion du PC", "Sécurité, surveillance, sauvegardes, mises à jour, disques, ménage et modes.")
        if getattr(C, "vieprivee", None):
            card = self._card("🛡️ Vie privée et sécurité")
            self._info(card, "Bilan, ports ouverts et redirections de ta box, outils à installer (LibreWolf, Tor, pare-feu, "
                             "KeePassXC, sauvegardes chiffrées…), DNS chiffré et proxy. Tout est en option, rien ne "
                             "change sans ton clic.")
            self._buttons(card, self._button("🛡️  Ouvrir le centre vie privée", lambda: c.open_privacy(0), True),
                          self._button("🔌  Ports ouverts", lambda: c.open_privacy(1)),
                          self._button("🧰  Outils", lambda: c.open_privacy(2)),
                          self._button("🌐  DNS chiffré", lambda: c.open_privacy(3)))
            self._switch(card, "Proposer Wikipédia pour mes questions", "« C'est quoi un trou noir ? » → elle propose "
                         "d'ouvrir Wikipédia sur ce sujet.", "wiki_proposer", default=True)
        if getattr(C, "securite", None):
            card = self._card("Sécurité")
            self._info(card, "Elle vérifie le pare-feu, les services ouverts sur le réseau, SSH, les mises à jour, le "
                             "chiffrement du disque, le verrouillage de l'écran, tes clés, ce qui démarre tout seul… "
                             "puis t'explique simplement chaque point et quoi faire. Elle ne modifie rien. "
                             "Ou dis-lui « vérifie la sécurité ».")
            self._buttons(card, self._button("🛡️  Vérifier la sécurité", c.security_check, True),
                          self._button("🆘  En cas de piratage ou de virus", lambda: c._show_text(
                              "🛡️ En cas de problème", C.securite.GUIDE, "Les étapes, dans l'ordre.")))
        card = self._card("Tableau de bord")
        try:
            m = G.mem()
            self._info(card, f"Mémoire : {G.human(m['utilise'])} / {G.human(m['total'])} — "
                             + " · ".join(f"{d['nom']} : {G.human(d['libre'])} libres" for d in G.disks()))
        except Exception:
            pass
        self._buttons(card, self._button("🖥️ Ouvrir le tableau de bord", c.open_dashboard, True),
                      self._button("🐢 Pourquoi mon PC rame ?", c.why_slow))

        card = self._card("Sauvegarde")
        sv = self.cfg.get("sauvegarde") or {}
        last = sv.get("derniere")
        import datetime as _dt
        self._info(card, "Copie tes dossiers importants sur un disque externe en un clic (sans jamais rien effacer), "
                         "et elle te rappelle de le faire.\nDernière sauvegarde : "
                         + (_dt.datetime.fromtimestamp(last).strftime("%d/%m/%Y") if last else "jamais") + ".")
        self._buttons(card, self._button("💾 Sauvegarde…", c.open_backup, True))

        card = self._card("Mises à jour")
        self._info(card, "La liste des paquets à mettre à jour et, sous Arch, les dernières nouvelles d'archlinux.org "
                         "(parfois il faut agir à la main avant de mettre à jour). La mise à jour se lance dans un "
                         "terminal.")
        self._buttons(card, self._button("⬆️ Voir les mises à jour", c.open_updates))

        card = self._card("Santé des disques")
        self._switch(card, "Vérifier chaque jour", "Elle lit les indicateurs SMART (sans mot de passe) et te prévient "
                     "si un disque fatigue.", "disques_check", default=True)
        self._buttons(card, self._button("💽 Vérifier maintenant", c.disks_health))

        card = self._card("Ménage intelligent")
        self._info(card, "Grosses vidéos jamais regardées, téléchargements de plus de 6 mois, photos en double. "
                         "Rien n'est coché d'office, et tout part à la corbeille.")
        self._buttons(card, self._button("🧹 Chercher", c.smart_clean),
                      self._button("Nettoyer le système…", c.open_cleaner))

        card = self._card("Modes")
        self._info(card, "🎮 Mode jeu : profil performances, notifications du bureau coupées, elle se fait discrète.\n"
                         "🌙 Mode nuit : luminosité et son baissés.\nMode normal : tout revient comme avant.\n"
                         "Ou dis-lui : « mode jeu », « mode nuit », « mode normal ».")
        cur = self.cfg.get("profil", "normal")
        self._buttons(card, self._button("🎮 Mode jeu" + (" ✓" if cur == "jeu" else ""), lambda: c.set_profile("jeu")),
                      self._button("🌙 Mode nuit" + (" ✓" if cur == "nuit" else ""), lambda: c.set_profile("nuit")),
                      self._button("Mode normal" + (" ✓" if cur == "normal" else ""),
                                   lambda: c.set_profile("normal")))

        card = self._card("Casques, souris et manettes")
        try:
            per = G.peripherals()
        except Exception:
            per = []
        self._info(card, ("Appareils : " + ", ".join(f"{d['type']} {d['nom']} ({d['pct']:.0f} %)" for d in per))
                   if per else "Aucun appareil sans fil avec batterie détecté pour l'instant.")
        self._switch(card, "Me prévenir quand la batterie est faible", "", "periph_check", default=True)
        self._combo(card, "Seuil", "", [("10 %", 10), ("15 %", 15), ("20 %", 20), ("30 %", 30)],
                    int(self.cfg.get("periph_seuil", 15)), lambda v: self._set("periph_seuil", v))
        self._end()

    def _refresh_git(self):
        lst = self.cfg.get("projets_git", [])
        self.git_list.setText(("Projets suivis : " + ", ".join(Path(p).name for p in lst)) if lst
                              else "Aucun projet suivi pour l'instant.")

    def _add_ics(self):
        self.comp.add_agenda_file()
        self._refresh_agenda()

    def _clear_ics(self):
        self._set("agenda_files", [])
        self._refresh_agenda()

    def _refresh_agenda(self):
        files = self.comp.agenda_files()
        self.agenda_info.setText(f"{len(files)} calendrier(s) suivi(s)" +
                                 (" : " + ", ".join(Path(f).name for f in files[:4]) if files else "."))

    def _page_invites(self):
        self._page("👭", "Invitées", "Fais venir d'autres personnages : elles discutent entre elles.")
        card = self._card("Au démarrage")
        self._switch(card, "Morgane vient avec elle au démarrage", "Ses amies fournies avec le logiciel arrivent "
                     "toutes seules à chaque démarrage.", "amies_auto",
                     lambda v: v and self.comp._default_friend(), default=False)
        self.inv_card = self._card("Personnages")
        self.inv_box = QVBoxLayout()
        self.inv_card.addLayout(self.inv_box)
        self._fill_invites()
        self._end()

    def _fill_invites(self):
        c, C = self.comp, self.C
        while self.inv_box.count():
            it = self.inv_box.takeAt(0)
            lay = it.layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
            elif it.widget():
                it.widget().deleteLater()
        mine = Path(c.cfg["character_dir"]).resolve()
        invited = set(c.cfg.get("invites", []))
        any_char = False
        for d, nm in C.list_characters():
            if Path(d).resolve() == mine:
                continue
            any_char = True
            row = QHBoxLayout()
            lab = QLabel(("💗  " if str(d) in invited else "      ") + nm)
            lab.setObjectName("nom")
            row.addWidget(lab, 1)
            if str(d) in invited:
                b = self._button("Renvoyer", lambda _=False, dd=str(d): (c.dismiss(dd), self._fill_invites()))
            else:
                b = self._button("Inviter", lambda _=False, dd=str(d): (c.invite(dd), self._fill_invites()), True)
            row.addWidget(b)
            self.inv_box.addLayout(row)
        if not any_char:
            lab = QLabel("Ajoute d'abord un autre personnage (page Personnage).")
            lab.setObjectName("aide")
            self.inv_box.addWidget(lab)
        if invited:
            row = QHBoxLayout()
            row.addWidget(self._button("💬  Faites la conversation !", lambda: c.start_duo(), True))
            row.addStretch(1)
            self.inv_box.addLayout(row)

    def _page_perf(self):
        c, C = self.comp, self.C
        self._page("⚡", "Performances", "Fluidité de l'animation et consommation.")
        card = self._card("Fluidité")
        self._combo(card, "Mode", f"Automatique s'adapte à ton PC ({c.hw[0]} cœurs, {c.hw[1]:.0f} Go).",
                    [(f"Automatique (qualité {C.QUALITY_NAMES[c.qlevel]})", "auto"),
                     ("Ultra (60 images/s, très fluide)", "ultra"),
                     ("Maximale (30 images/s)", "fluide"), ("Équilibrée", "equilibre"),
                     ("Économe (PC lent, batterie)", "econome")], self.cfg.get("perf", "auto"),
                    lambda v: (self._set("perf", v), c._build_mesh()), width=280)
        self._info(card, f"Mémoire libre : {C.mem_available_gb():.1f} Go sur {c.hw[1]:.0f} Go.  ·  "
                         "Astuce : le petit chat et l'effet 3D consomment un peu ; désactive-les sur un PC lent.")
        if getattr(C, "fun", None):
            card = self._card("🔋 Mode batterie")
            on, pct = C.fun.power_state()
            self._info(card, ("En ce moment : sur batterie" + (f" ({pct} %)" if pct is not None else "") if on else
                              "En ce moment : branché sur le secteur" if pct is not None else
                              "Pas de batterie détectée (PC fixe).")
                       + ". En mode batterie : animation légère, pas d'effets à l'écran, moins de vérifications "
                         "en fond, pas de reformulation par l'IA.")
            self._combo(card, "Mode batterie", "", [("Automatique (quand je suis sur batterie)", "auto"),
                                                    ("Toujours (PC lent ou silencieux)", "toujours"),
                                                    ("Jamais", "jamais")], self.cfg.get("mode_batterie", "auto"),
                        lambda v: (self._set("mode_batterie", v), c._fun_tick()), width=300)
        self._end()

    def _page_access(self):
        c, C = self.comp, self.C
        self._page("♿", "Accessibilité", "Texte plus grand, contraste élevé, moins de mouvement, tout à voix haute.")
        card = self._card("Lire plus facilement")
        self._combo(card, "Taille du texte", "Fenêtres, menus et bulles (les fenêtres déjà ouvertes changent quand "
                    "tu les rouvres).", [("Normale", 1.0), ("Un peu plus grande", 1.15), ("Grande", 1.3),
                                         ("Très grande", 1.5), ("Énorme", 1.8)],
                    float(self.cfg.get("a11y_texte", 1.0)), lambda v: (self._set("a11y_texte", v),
                                                                      c.apply_accessibility()), width=240)
        self._switch(card, "Contraste élevé", "Noir sur blanc, boutons bleu foncé bien visibles.", "a11y_contraste",
                     on_change=lambda v: c.set_contrast(v))
        self._combo(card, "Durée des bulles", "Le temps pour lire ce qu'elle dit.",
                    [("Normale", 1.0), ("1,5 × plus longue", 1.5), ("2 × plus longue", 2.0), ("3 × plus longue", 3.0)],
                    float(self.cfg.get("a11y_bulle", 1.0)), lambda v: self._set("a11y_bulle", v), width=240)
        card = self._card("Entendre")
        self._switch(card, "Tout lire à voix haute", "Chaque bulle est lue, même si la voix est coupée dans les "
                     "réglages (le mode « muette » reste prioritaire).", "a11y_voix")
        self._info(card, "Pour se faire lire un texte : sélectionne-le puis dis « lis-moi la sélection ». "
                         "Pour une page web : « lis-moi cette page ». Et pour un document : glisse-le sur elle.")
        card = self._card("Bouger moins, naviguer au clavier")
        self._switch(card, "Moins de mouvement", "Pas de particules ni d'effets à l'écran (neige, confettis…).",
                     "a11y_mouvement", on_change=lambda v: c._fun_tick())
        self._switch(card, "Contour visible au clavier", "Un cadre jaune bien visible autour de l'élément choisi "
                     "avec Tab (Tab / Maj+Tab pour avancer et reculer, Espace pour cocher, Entrée pour valider).",
                     "a11y_focus", on_change=lambda v: c.apply_accessibility())
        self._info(card, "Raccourcis clavier globaux : Réglages → Assistant → « Raccourcis clavier » (lui écrire, "
                         "lui parler, traduire ou lire la sélection, décrire l'écran).")
        self._end()

    def _page_sauvegarde(self):
        c, C = self.comp, self.C
        self._page("💾", "Sauvegarde et aide", "Garder ses souvenirs, ses réglages et ses personnages.")
        card = self._card("Sauvegarde")
        self._buttons(card, self._button("Sauvegarder tout…", c.backup_all, True),
                      self._button("Restaurer une sauvegarde…", c.restore_all))
        card = self._card("Où sont mes fichiers ?")
        self._info(card, "Les dossiers où sont rangés les modèles d'IA, tes personnages, les voix… Clique sur "
                         "« Ouvrir » pour les voir dans ton gestionnaire de fichiers.")
        for title, path, why in c.storage_places():
            if not path:
                self._info(card, f"{title} : {why}")
                continue
            ex = Path(path).exists()
            b = self._button("📂  Ouvrir", lambda _=False, p=path: c._open_path(p))
            b.setEnabled(ex)
            self._row(card, title, f"{path}" + ("" if ex else "  (pas encore créé)") + f"\n{why}", b)
        card = self._card("En cas de souci")
        self._info(card, "Un souci ? « Signaler un bug » prépare un rapport utile (version, système, dernières erreurs) "
                         "sans rien de personnel, te le montre, puis ouvre la page GitHub déjà remplie.")
        self._buttons(card, self._button("🐞  Signaler un bug…", c.signaler_bug, True),
                      self._button("Journal des erreurs…", c.show_error_log),
                      self._button("Journal de la voix…", c.show_voice_log))
        if getattr(C, "astuces", None):
            card = self._card("💡 Trucs et astuces")
            self._info(card, "Toutes ses actions avec des exemples, et les mots-clés en anglais, espagnol, russe, "
                             "chinois, japonais et hindi. Dis-lui aussi « aide » ou « que sais-tu faire ? ».")
            self._switch(card, "Une astuce par jour", "Elle te glisse une astuce d'utilisation chaque jour.",
                         "astuce_jour", default=True)
            self._buttons(card, self._button("💡  Ouvrir les trucs et astuces", c.open_tips, True))
        card = self._card("Astuces")
        self._info(card, "• Double-clic sur elle : lui écrire.\n• Clic droit : le menu, avec « Que veux-tu faire ? » en haut.\n"
                         "• Clic molette sur l'icône près de l'horloge : muette / son.\n"
                         "• Écris « chut », « trouve ma facture en pdf », « cherche sur internet … », "
                         "« minuteur 10 minutes », « note que … », « on joue au morpion ».")
        self._end()
