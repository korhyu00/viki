"""Galerie des personnages, façon Apple : de grandes vignettes, un clic pour la choisir, clic droit pour le reste."""
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QUrl
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QCursor, QDesktopServices
from PyQt6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

try:
    import pomme
    _BASE = pomme.STUDIO
except Exception:
    _BASE = ""

STYLE = _BASE + """
QLabel#titre { font-size: 22px; font-weight: bold; color: #3d2733; }
QLabel#aide { font-size: 12px; color: #9a8290; }
QLabel#nom { font-size: 13px; font-weight: bold; color: #3d2733; }
QLabel#type { font-size: 11px; color: #9a8290; }
QWidget#atelier QLabel#badge { font-size: 10px; font-weight: bold; color: white; background: #d0457a; border-radius: 8px;
               padding: 2px 8px; }
QFrame#carteP { background: transparent; border: none; }
QPushButton#seg { border-radius: 0; padding: 5px 13px; border-left: none; }
QPushButton#seg[pos="g"] { border-top-left-radius: 8px; border-bottom-left-radius: 8px; border-left: 1px solid #e3d3dc; }
QPushButton#seg[pos="d"] { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QPushButton#seg:checked { background: #d0457a; color: white; border-color: #d0457a; }
QPushButton#plus { background: #d0457a; color: white; border: none; border-radius: 15px; min-width: 30px; max-width: 30px;
                   min-height: 30px; max-height: 30px; padding: 0; font-size: 18px; font-weight: bold; }
QLineEdit#cherche { border-radius: 8px; padding: 5px 9px; }
"""

TYPES = {"live2d": "✨ Live2D", "spine": "🌀 Spine", "marionnette": "🦴 Marionnette", "image": "🖼️ Image"}
FILTRES = [("Tous", ""), ("Images", "image"), ("Live2D", "live2d"), ("Spine", "spine"), ("Marionnettes", "marionnette")]
W, H = 168, 228


def char_type(d, C):
    try:
        info = json.loads((Path(d) / "character.json").read_text())
    except Exception:
        info = {}
    if info.get("type") in ("live2d", "spine"):
        return info["type"]
    m = getattr(C, "marionnette", None)
    if m and m.find_rig(d):
        return "marionnette"
    return "image"


def _vignette(path, actif):
    """Le personnage sur une tuile arrondie et douce ; un anneau de couleur si c'est celle qui est sur le bureau."""
    dpr = 2
    pm = QPixmap(W * dpr, H * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    r = QRectF(3, 3, W - 6, H - 6)
    forme = QPainterPath()
    forme.addRoundedRect(r, 16, 16)
    try:
        import themes
        accent = QColor(themes.color("#d0457a"))
    except Exception:
        accent = QColor("#d0457a")
    fond = QColor(accent)
    fond.setAlpha(40)
    p.fillPath(forme, fond if actif else QColor(127, 127, 140, 34))
    src = QPixmap(str(path))
    if not src.isNull():
        sc = src.scaled(int((W - 24) * dpr), int((H - 20) * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        sw, sh = sc.width() / dpr, sc.height() / dpr
        p.setClipPath(forme)
        p.drawPixmap(QRectF((W - sw) / 2, H - 8 - sh, sw, sh), sc, QRectF(0, 0, sc.width(), sc.height()))
        p.setClipping(False)
    if actif:
        from PyQt6.QtGui import QPen
        p.setPen(QPen(accent, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 16, 16)
    p.end()
    return pm


class Galerie(QDialog):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("atelier")
        self.setWindowTitle("🎭 Personnages")
        self.setStyleSheet(STYLE)
        self.resize(900, 680)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        t = QLabel("Personnages")
        t.setObjectName("titre")
        top.addWidget(t)
        top.addSpacing(6)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.grp = QButtonGroup(self)
        self.grp.setExclusive(True)
        for i, (lab, _k) in enumerate(FILTRES):
            b = QPushButton(lab)
            b.setObjectName("seg")
            b.setProperty("pos", "g" if i == 0 else "d" if i == len(FILTRES) - 1 else "m")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.grp.addButton(b, i)
            seg.addWidget(b)
        self.grp.idClicked.connect(lambda _i: self.fill())
        top.addLayout(seg)
        top.addStretch(1)
        self.q = QLineEdit()
        self.q.setObjectName("cherche")
        self.q.setPlaceholderText("🔎 Chercher")
        self.q.setClearButtonEnabled(True)
        self.q.setFixedWidth(190)
        self.q.textChanged.connect(lambda _t: self.fill())
        top.addWidget(self.q)
        plus = QPushButton("+")
        plus.setObjectName("plus")
        plus.setToolTip("Ajouter un personnage")
        plus.clicked.connect(lambda: self._menu_plus(plus))
        top.addWidget(plus)
        v.addLayout(top)
        a = QLabel("Clique sur un personnage pour le mettre sur ton bureau · clic droit : renommer, dossier, supprimer.")
        a.setObjectName("aide")
        a.setWordWrap(True)
        v.addWidget(a)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.area, 1)
        ok, _why = (C.live2d_rendu.available() if getattr(C, "live2d_rendu", None) else (False, "module absent"))
        self.live2d_ok = ok
        self.fill()

    # ---------- menus
    def _menu_plus(self, btn):
        m = QMenu(self)
        if hasattr(self.comp, "creer_kawaii"):
            m.addAction("🎀  Créer un personnage kawaii (IA)…", lambda: (self.close(), self.comp.creer_kawaii()))
        m.addAction("🖼️  Depuis une image…", lambda: (self.close(), self.comp.new_character()))
        if hasattr(self.comp, "new_animated_character"):
            m.addAction("🎞️  Depuis une animation (GIF, vidéo)…", lambda: (self.close(),
                                                                         self.comp.new_animated_character()))
        a = m.addAction("✨  Importer un modèle animé (Live2D ou Spine)…", lambda: (self.comp.import_model(),
                                                                                  self.fill()))
        if not self.live2d_ok:
            a.setToolTip("Il manque live2d-py : pip install live2d-py PyOpenGL")
        m.addSeparator()
        m.addAction("🌐  Trouver des modèles", self.comp.open_live2d_sources)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _menu_perso(self, d, name, own):
        m = QMenu(self)
        m.addAction("✔  Mettre sur mon bureau", lambda: self._choisir(d))
        m.addAction("✏️  Renommer…", lambda: (self.comp.rename_character(d), self.fill()))
        m.addAction("📂  Ouvrir son dossier", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(d))))
        if own:
            m.addSeparator()
            m.addAction("🗑️  Supprimer…", lambda: (self.comp.delete_character(d, name), self.fill()))
        m.exec(QCursor.pos())

    def _choisir(self, d):
        self.comp.switch_character(d)
        self.fill()

    # ---------- grille
    def fill(self):
        try:
            from actu_fenetre import FlowLayout
        except Exception:
            FlowLayout = None
        inner = QWidget()
        inner.setObjectName("fond")
        g = FlowLayout(inner, 16) if FlowLayout else QHBoxLayout(inner)
        cur = Path(self.comp.char_dir).resolve()
        own_root = self.C.CHAR_ROOT.resolve()
        kind = FILTRES[max(0, self.grp.checkedId())][1]
        q = self.q.text().strip().lower()
        n = 0
        for d, name in self.C.list_characters():
            d = Path(d)
            ty = char_type(d, self.C)
            if (kind and ty != kind) or (q and q not in name.lower()):
                continue
            n += 1
            actif = d.resolve() == cur
            own = d.resolve().parent == own_root
            card = QFrame()
            card.setObjectName("carteP")
            card.setFixedWidth(W)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(3)
            img = QLabel()
            img.setFixedSize(W, H)
            try:
                info = json.loads((d / "character.json").read_text())
                img.setPixmap(_vignette(d / info.get("image", "character.png"), actif))
            except Exception:
                img.setPixmap(_vignette(d / "character.png", actif))
            cl.addWidget(img)
            row = QHBoxLayout()
            row.setSpacing(6)
            nm = QLabel(name)
            nm.setObjectName("nom")
            nm.setProperty("no_i18n", True)
            row.addWidget(nm, 1)
            if actif:
                b = QLabel("Sur ton bureau")
                b.setObjectName("badge")
                row.addWidget(b)
            cl.addLayout(row)
            t = QLabel(TYPES[ty])
            t.setObjectName("type")
            cl.addWidget(t)
            card.setToolTip("Clic : la mettre sur ton bureau · Clic droit : renommer, dossier, supprimer")
            card.mousePressEvent = lambda e, dd=d, nn=name, oo=own: (
                self._choisir(dd) if e.button() == Qt.MouseButton.LeftButton else self._menu_perso(dd, nn, oo))
            g.addWidget(card)
        if not n:
            l = QLabel("Aucun personnage ici." if not q else "Aucun résultat.")
            l.setObjectName("aide")
            g.addWidget(l)
        self.area.setWidget(inner)
