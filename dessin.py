"""✏️ Le carnet de dessin de Viki : on dessine ce qu'on veut (calques, symétrie, silhouette guide, image à
décalquer, tablette graphique), on enregistre en PNG ou en .ora (ouvrable dans Krita, GIMP…), et si on veut, le
dessin devient un nouveau personnage (Viki le fait cligner des yeux, parler et respirer).
Tout reste sur le PC. Seul « Devine ! » utilise l'IA qui voit les images, et seulement si on clique."""
import random
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

from PyQt6.QtCore import QBuffer, QByteArray, QPoint, QPointF, QRect, QRectF, QStandardPaths, Qt
from PyQt6.QtGui import (QColor, QFont, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSlider,
                             QToolButton, QVBoxLayout, QWidget)

try:
    from i18n import tr
except Exception:
    def tr(t):
        return t

TAILLE = 1024
PALETTE = [("#2e1624", "Encre"), ("#ffffff", "Blanc"), ("#9b8a93", "Gris"), ("#ef5b8f", "Rose"),
           ("#fde4ef", "Rose pâle"), ("#e0483c", "Rouge"), ("#f59a3c", "Orange"), ("#ffd166", "Jaune"),
           ("#7cc6a4", "Vert"), ("#4a90e2", "Bleu"), ("#8e6bd8", "Violet"), ("#8a5a3c", "Marron"),
           ("#f3c9a8", "Peau claire"), ("#c68a5e", "Peau mate"), ("#7a4a2e", "Peau foncée"), ("#000000", "Noir")]
OUTILS = [("crayon", "✏️", "Crayon"), ("feutre", "🖊️", "Feutre"), ("pinceau", "🖌️", "Pinceau"),
          ("gomme", "🧽", "Gomme"), ("remplir", "🪣", "Remplir"), ("ligne", "📏", "Ligne"),
          ("rect", "⬜", "Rectangle"), ("ellipse", "⭕", "Ellipse"), ("texte", "🔤", "Texte"),
          ("pipette", "💧", "Pipette")]
BRAVO = ["Oh, c'est joli !", "J'adore les couleurs !", "Tu dessines bien, tu sais !", "Hihi, ça me plaît beaucoup !",
         "Continue, ça prend forme !"]


def dossier_dessins():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation) or str(Path.home())
    d = Path(base) / "Viki" / "Dessins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vide(w, h):
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _png(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def _remplissage(img, x, y, couleur, tol=40):
    """Pot de peinture (balayage par lignes, accéléré avec numpy) ; renvoie False si rien à remplir."""
    import numpy as np
    w, h = img.width(), img.height()
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
    a = a[:, :w * 4].reshape(h, w, 4).astype(np.int16)
    ref = a[y, x].copy()
    if ref[3] < 20:
        cible = a[:, :, 3] < 60
    else:
        cible = (np.abs(a - ref).max(axis=2) <= tol) & (a[:, :, 3] > 20)
    rempli = np.zeros((h, w), dtype=bool)
    pile = [(x, y)]
    while pile:
        px, py = pile.pop()
        if rempli[py, px] or not cible[py, px]:
            continue
        lig = cible[py] & ~rempli[py]
        stop_g = np.flatnonzero(~lig[:px])
        g = stop_g[-1] + 1 if stop_g.size else 0
        stop_d = np.flatnonzero(~lig[px:])
        d = px + stop_d[0] - 1 if stop_d.size else w - 1
        rempli[py, g:d + 1] = True
        for ny in (py - 1, py + 1):
            if 0 <= ny < h:
                seg = cible[ny, g:d + 1] & ~rempli[ny, g:d + 1]
                if seg.any():
                    debut = np.flatnonzero(seg & ~np.concatenate(([False], seg[:-1])))
                    pile.extend((g + int(i), ny) for i in debut)
    if not rempli.any():
        return False
    m = rempli.copy()                                    # déborde d'un pixel sous le trait (bords lissés)
    m[1:] |= rempli[:-1]
    m[:-1] |= rempli[1:]
    m[:, 1:] |= rempli[:, :-1]
    m[:, :-1] |= rempli[:, 1:]
    c = QColor(couleur)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    al = c.alpha()
    out[m] = (c.blue() * al // 255, c.green() * al // 255, c.red() * al // 255, al)
    calque = QImage(out.tobytes(), w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
    p = QPainter(img)
    p.drawImage(0, 0, calque)
    p.end()
    return True


def silhouette_guide():
    """Une silhouette très simple (tête, corps, bras, jambes) pour aider à placer un personnage."""
    s = TAILLE / 400.0
    path = QPainterPath()
    path.addEllipse(QRectF(160 * s, 40 * s, 80 * s, 92 * s))
    path.moveTo(200 * s, 132 * s)
    path.lineTo(200 * s, 145 * s)
    path.addRoundedRect(QRectF(150 * s, 145 * s, 100 * s, 120 * s), 30 * s, 30 * s)
    for x0, x1 in ((152, 118), (248, 282)):
        path.moveTo(x0 * s, 160 * s)
        path.lineTo(x1 * s, 255 * s)
    for x in (178, 222):
        path.moveTo(x * s, 262 * s)
        path.lineTo(x * s, 370 * s)
    return path


class Toile(QWidget):
    """La feuille : calques, outils, zoom (Ctrl + molette), déplacement (clic molette ou Espace)."""

    def __init__(self, carnet):
        super().__init__()
        self.carnet = carnet
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking, True)
        self.calques = []
        self.actif = 0
        self.outil = "feutre"
        self.couleur = QColor("#2e1624")
        self.taille = 8
        self.opacite = 1.0
        self.symetrie = False
        self.guide = False
        self.decalque = None
        self.zoom = 1.0
        self.decal = QPointF(0, 0)
        self.annuler_pile, self.refaire_pile = [], []
        self.trait = None
        self.forme = None
        self.pression = 1.0
        self.pan = None
        self.espace = False
        self.modifie = False
        self.nb_traits = 0
        self.nouveau()

    # ---------- document
    def nouveau(self):
        self.calques = [{"nom": tr("Fond"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0},
                        {"nom": tr("Dessin"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0}]
        self.actif = 1
        self.annuler_pile, self.refaire_pile = [], []
        self.modifie = False
        self.update()

    def image_finale(self, avec_fond=True):
        out = _vide(TAILLE, TAILLE)
        p = QPainter(out)
        for c in self.calques:
            if c["visible"] and (avec_fond or c is not self.calques[0]):
                p.setOpacity(c["opacite"])
                p.drawImage(0, 0, c["img"])
        p.end()
        return out

    def _memo(self):
        self.annuler_pile.append((self.actif, self.calques[self.actif]["img"].copy()))
        del self.annuler_pile[:-40]
        self.refaire_pile.clear()
        self.modifie = True

    def annuler(self):
        if not self.annuler_pile:
            return
        i, img = self.annuler_pile.pop()
        if i < len(self.calques):
            self.refaire_pile.append((i, self.calques[i]["img"].copy()))
            self.calques[i]["img"] = img
        self.update()

    def refaire(self):
        if not self.refaire_pile:
            return
        i, img = self.refaire_pile.pop()
        if i < len(self.calques):
            self.annuler_pile.append((i, self.calques[i]["img"].copy()))
            self.calques[i]["img"] = img
        self.update()

    # ---------- vue
    def _base(self):
        cote = min(self.width(), self.height()) - 24
        return max(50.0, cote) / TAILLE

    def _echelle(self):
        return self._base() * self.zoom

    def _origine(self):
        e = self._echelle()
        return QPointF((self.width() - TAILLE * e) / 2, (self.height() - TAILLE * e) / 2) + self.decal

    def vers_doc(self, pt):
        o, e = self._origine(), self._echelle()
        return QPointF((pt.x() - o.x()) / e, (pt.y() - o.y()) / e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#f4e9ef"))
        o, e = self._origine(), self._echelle()
        zone = QRectF(o.x(), o.y(), TAILLE * e, TAILLE * e)
        p.fillRect(zone, QColor("#ffffff"))
        p.save()
        p.setClipRect(zone)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#efe9ec"))
        k = 16
        for i in range(int(zone.width() // k) + 1):
            for j in range(int(zone.height() // k) + 1):
                if (i + j) % 2:
                    p.drawRect(QRectF(zone.x() + i * k, zone.y() + j * k, k, k))
        p.restore()
        p.save()
        p.translate(o)
        p.scale(e, e)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, e < 1)
        if self.decalque is not None:
            p.setOpacity(0.35)
            p.drawImage(QRectF(0, 0, TAILLE, TAILLE), self.decalque)
            p.setOpacity(1)
        for idx, c in enumerate(self.calques):
            if c["visible"]:
                p.setOpacity(c["opacite"])
                p.drawImage(0, 0, c["img"])
                if idx == self.actif and self.forme:
                    self._dessiner_forme(p, *self.forme)
        p.setOpacity(1)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.guide:
            p.setPen(QPen(QColor(176, 51, 106, 90), 3 / e, Qt.PenStyle.DashLine))
            p.setBrush(QColor(176, 51, 106, 18))
            p.drawPath(silhouette_guide())
        if self.symetrie:
            p.setPen(QPen(QColor("#e7a3c2"), 2 / e, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(TAILLE / 2, 0), QPointF(TAILLE / 2, TAILLE))
        p.restore()
        p.setPen(QPen(QColor("#ecd3df"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(zone)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            avant = self.vers_doc(ev.position())
            self.zoom = max(0.25, min(6.0, self.zoom * (1.15 if ev.angleDelta().y() > 0 else 1 / 1.15)))
            apres = self.vers_doc(ev.position())
            e = self._echelle()
            self.decal += QPointF((apres.x() - avant.x()) * e, (apres.y() - avant.y()) * e)
            self.update()
        else:
            self.decal += QPointF(ev.angleDelta().x() / 4, ev.angleDelta().y() / 4)
            self.update()

    def recentrer(self):
        self.zoom, self.decal = 1.0, QPointF(0, 0)
        self.update()

    # ---------- pinceaux
    def _pinceau(self, pression=1.0):
        t, c = self.outil, QColor(self.couleur)
        if t == "crayon":
            w = max(1.0, self.taille * 0.35)
        elif t == "pinceau":
            w = max(1.0, self.taille * (0.3 + 0.9 * pression))
            c.setAlphaF(c.alphaF() * 0.45)
        elif t == "gomme":
            w = self.taille * 1.5
        else:
            w = max(1.0, self.taille * (0.6 + 0.4 * pression))
        c.setAlphaF(c.alphaF() * self.opacite)
        return QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    def _miroir(self, pt):
        return QPointF(TAILLE - pt.x(), pt.y())

    def _segment(self, a, b, pression):
        img = self.calques[self.actif]["img"]
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.outil == "gomme":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.setPen(self._pinceau(pression))
        p.drawLine(a, b)
        if self.symetrie:
            p.drawLine(self._miroir(a), self._miroir(b))
        p.end()

    def _dessiner_forme(self, p, a, b):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = self._pinceau()
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for x, y in ((a, b), (self._miroir(a), self._miroir(b))) if self.symetrie else ((a, b),):
            if self.outil == "ligne":
                p.drawLine(x, y)
            elif self.outil == "rect":
                p.drawRect(QRectF(x, y).normalized())
            else:
                p.drawEllipse(QRectF(x, y).normalized())
        p.restore()

    # ---------- souris et tablette
    def _debut(self, pos, pression):
        pt = self.vers_doc(pos)
        if not (0 <= pt.x() < TAILLE and 0 <= pt.y() < TAILLE) and self.outil in ("remplir", "pipette", "texte"):
            return
        c = self.calques[self.actif]
        if not c["visible"] and self.outil not in ("pipette",):
            self.carnet.dire("Ce calque est caché : affiche-le pour dessiner dessus.")
            return
        if self.outil == "pipette":
            fin = self.image_finale()
            x, y = int(pt.x()), int(pt.y())
            if 0 <= x < TAILLE and 0 <= y < TAILLE:
                col = fin.pixelColor(x, y)
                if col.alpha() > 0:
                    col.setAlpha(255)
                    self.carnet.choisir_couleur(col)
            return
        if self.outil == "remplir":
            self._memo()
            try:
                if not _remplissage(c["img"], int(pt.x()), int(pt.y()), self.couleur):
                    self.annuler_pile.pop()
            except Exception:
                self.annuler_pile.pop()
                self.carnet.dire("Je n'ai pas réussi, désolée.")
            self.update()
            return
        if self.outil == "texte":
            txt, ok = QInputDialog.getText(self, tr("Texte"), tr("Ton texte :"))
            if ok and txt.strip():
                self._memo()
                p = QPainter(c["img"])
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                f = QFont()
                f.setPixelSize(max(12, int(self.taille * 4)))
                f.setBold(True)
                p.setFont(f)
                col = QColor(self.couleur)
                col.setAlphaF(self.opacite)
                p.setPen(col)
                p.drawText(pt, txt)
                p.end()
                self.update()
            return
        self._memo()
        if self.outil in ("ligne", "rect", "ellipse"):
            self.forme = (pt, pt)
        else:
            self.trait = pt
            self._segment(pt, pt + QPointF(0.01, 0.01), pression)
        self.update()

    def _suite(self, pos, pression):
        pt = self.vers_doc(pos)
        if self.forme:
            self.forme = (self.forme[0], pt)
            self.update()
        elif self.trait is not None:
            self._segment(self.trait, pt, pression)
            self.trait = pt
            self.update()

    def _fin(self):
        if self.forme:
            a, b = self.forme
            self.forme = None
            p = QPainter(self.calques[self.actif]["img"])
            self._dessiner_forme(p, a, b)
            p.end()
        self.nb_traits += 1
        self.carnet.trait_fini(self.nb_traits)
        self.trait = None
        self.update()

    def tabletEvent(self, ev):
        t = ev.type()
        self.pression = max(0.05, ev.pressure())
        if t == ev.Type.TabletPress:
            self._debut(ev.position(), self.pression)
        elif t == ev.Type.TabletMove:
            self._suite(ev.position(), self.pression)
        elif t == ev.Type.TabletRelease:
            self._fin()
        ev.accept()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton or (self.espace and ev.button() == Qt.MouseButton.LeftButton):
            self.pan = (ev.position(), QPointF(self.decal))
            return
        if ev.button() == Qt.MouseButton.RightButton:
            self.carnet.outil("pipette" if self.outil != "pipette" else "feutre")
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self._debut(ev.position(), 1.0)

    def mouseMoveEvent(self, ev):
        if self.pan:
            d = ev.position() - self.pan[0]
            self.decal = self.pan[1] + d
            self.update()
            return
        if ev.buttons() & Qt.MouseButton.LeftButton:
            self._suite(ev.position(), 1.0)

    def mouseReleaseEvent(self, ev):
        if self.pan:
            self.pan = None
            return
        if ev.button() == Qt.MouseButton.LeftButton and (self.trait is not None or self.forme):
            self._fin()


class Carnet(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("carnet")
        self.setWindowTitle(tr("✏️ Carnet de dessin") + " — " + comp.char.get("name", "Viki"))
        scr = self.screen().availableGeometry() if self.screen() else None
        self.resize(min(1240, int(scr.width() * 0.9)) if scr else 1180, min(840, int(scr.height() * 0.9)) if scr else 800)
        self.setStyleSheet(CSS)
        self.fichier = None
        self.dernier_bravo = 0.0
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        # barre du haut
        haut = QHBoxLayout()
        for txt, fn in ((tr("📄 Nouveau"), self.nouveau), (tr("📂 Ouvrir…"), self.ouvrir),
                        (tr("💾 Enregistrer"), self.enregistrer), (tr("↩️"), lambda: self.toile.annuler()),
                        (tr("↪️"), lambda: self.toile.refaire()),
                        (tr("🖼️ Image à décalquer…"), self.decalque), (tr("🔍 Recentrer"), lambda: self.toile.recentrer())):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            if txt in ("↩️", "↪️"):
                b.setToolTip(tr("Annuler (Ctrl+Z)") if txt == "↩️" else tr("Refaire (Ctrl+Y)"))
            haut.addWidget(b)
        haut.addStretch(1)
        b = QPushButton(tr("🔮 Devine !"))
        b.setToolTip(tr("Viki regarde ton dessin et devine ce que c'est (avec l'IA qui voit les images)."))
        b.clicked.connect(self.devine)
        haut.addWidget(b)
        b = QPushButton(tr("🧑‍🎨 Faire de mon dessin un perso"))
        b.setObjectName("main")
        b.clicked.connect(self.en_perso)
        haut.addWidget(b)
        root.addLayout(haut)
        corps = QHBoxLayout()
        root.addLayout(corps, 1)
        # outils
        col = QVBoxLayout()
        col.setSpacing(4)
        self.b_outils = {}
        for cle, ico, nom in OUTILS:
            tb = QToolButton()
            tb.setText(ico)
            tb.setToolTip(tr(nom))
            tb.setCheckable(True)
            tb.setFixedSize(52, 44)
            f = tb.font()
            f.setPointSize(f.pointSize() + 5)
            tb.setFont(f)
            tb.clicked.connect(lambda _=False, k=cle: self.outil(k))
            col.addWidget(tb)
            self.b_outils[cle] = tb
        col.addStretch(1)
        corps.addLayout(col)
        self.toile = Toile(self)
        corps.addWidget(self.toile, 1)
        # panneau de droite
        droite = QVBoxLayout()
        droite.setSpacing(8)
        panneau = QFrame()
        panneau.setObjectName("panneau")
        panneau.setFixedWidth(270)
        panneau.setLayout(droite)
        corps.addWidget(panneau)
        droite.addWidget(self._titre(tr("Couleur")))
        g = QGridLayout()
        g.setSpacing(5)
        for i, (hexc, nom) in enumerate(PALETTE):
            b = QPushButton()
            b.setToolTip(tr(nom))
            b.setFixedSize(26, 26)
            b.setProperty("sans_theme", True)
            b.setStyleSheet(f"QPushButton {{ background: {hexc}; border: 1px solid #d9c2cd; border-radius: 7px; }}")
            b.clicked.connect(lambda _=False, h=hexc: self.choisir_couleur(QColor(h)))
            g.addWidget(b, i // 8, i % 8)
        droite.addLayout(g)
        h = QHBoxLayout()
        self.apercu = QLabel()
        self.apercu.setFixedSize(34, 34)
        self.apercu.setProperty("sans_theme", True)
        h.addWidget(self.apercu)
        b = QPushButton(tr("🎨 Autre couleur…"))
        b.clicked.connect(self._roue)
        h.addWidget(b, 1)
        droite.addLayout(h)
        self.l_taille = self._titre("")
        droite.addWidget(self.l_taille)
        self.s_taille = QSlider(Qt.Orientation.Horizontal)
        self.s_taille.setRange(1, 80)
        self.s_taille.setValue(8)
        self.s_taille.valueChanged.connect(self._taille)
        droite.addWidget(self.s_taille)
        self.l_opac = self._titre("")
        droite.addWidget(self.l_opac)
        self.s_opac = QSlider(Qt.Orientation.Horizontal)
        self.s_opac.setRange(5, 100)
        self.s_opac.setValue(100)
        self.s_opac.valueChanged.connect(self._opac)
        droite.addWidget(self.s_opac)
        self.c_sym = QCheckBox(tr("Symétrie (parfait pour un visage)"))
        self.c_sym.toggled.connect(lambda v: (setattr(self.toile, "symetrie", v), self.toile.update()))
        droite.addWidget(self.c_sym)
        self.c_guide = QCheckBox(tr("Silhouette guide"))
        self.c_guide.toggled.connect(lambda v: (setattr(self.toile, "guide", v), self.toile.update()))
        droite.addWidget(self.c_guide)
        h = QHBoxLayout()
        h.addWidget(self._titre(tr("Calques")), 1)
        for txt, tip, fn in (("＋", tr("Ajouter un calque"), self.ajouter_calque),
                             ("－", tr("Supprimer le calque"), self.supprimer_calque),
                             ("↑", tr("Monter"), lambda: self.deplacer_calque(1)),
                             ("↓", tr("Descendre"), lambda: self.deplacer_calque(-1))):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.setFixedSize(32, 30)
            b.clicked.connect(fn)
            h.addWidget(b)
        droite.addLayout(h)
        self.liste = QListWidget()
        self.liste.itemChanged.connect(self._calque_coche)
        self.liste.currentRowChanged.connect(self._calque_choisi)
        self.liste.itemDoubleClicked.connect(self._renommer)
        droite.addWidget(self.liste, 1)
        self.l_copac = QLabel()
        droite.addWidget(self.l_copac)
        self.s_copac = QSlider(Qt.Orientation.Horizontal)
        self.s_copac.setRange(0, 100)
        self.s_copac.valueChanged.connect(self._calque_opac)
        droite.addWidget(self.s_copac)
        aide = QLabel(tr("Clic droit : pipette · Ctrl + molette : zoom · clic molette ou Espace : déplacer · "
                         "Ctrl+Z / Ctrl+Y : annuler / refaire"))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#9b8a93; font-size:9pt;")
        droite.addWidget(aide)
        for seq, fn in (("Ctrl+Z", lambda: self.toile.annuler()), ("Ctrl+Y", lambda: self.toile.refaire()),
                        ("Ctrl+Shift+Z", lambda: self.toile.refaire()), ("Ctrl+S", self.enregistrer),
                        ("B", lambda: self.outil("pinceau")), ("E", lambda: self.outil("gomme")),
                        ("P", lambda: self.outil("crayon")), ("G", lambda: self.outil("remplir")),
                        ("[", lambda: self.s_taille.setValue(self.s_taille.value() - 2)),
                        ("]", lambda: self.s_taille.setValue(self.s_taille.value() + 2))):
            QShortcut(QKeySequence(seq), self, activated=fn)
        self.outil("feutre")
        self.choisir_couleur(QColor("#2e1624"))
        self._taille(8)
        self._opac(100)
        self._liste_calques()
        try:
            import i18n
            i18n.translate_widget(self)
        except Exception:
            pass

    # ---------- petits bouts
    def _titre(self, t):
        l = QLabel(t)
        l.setStyleSheet("font-weight:700;")
        return l

    def dire(self, t):
        try:
            self.comp.say(t)
        except Exception:
            pass

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.toile.espace = True
            self.toile.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.toile.espace = False
            self.toile.unsetCursor()
        super().keyReleaseEvent(e)

    def outil(self, k):
        self.toile.outil = k
        for cle, b in self.b_outils.items():
            b.setChecked(cle == k)
        self.toile.setCursor(Qt.CursorShape.CrossCursor if k not in ("pipette",) else Qt.CursorShape.PointingHandCursor)

    def choisir_couleur(self, c):
        self.toile.couleur = QColor(c)
        pm = QPixmap(34, 34)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(c))
        p.setPen(QPen(QColor("#d9c2cd"), 1))
        p.drawRoundedRect(QRectF(1, 1, 32, 32), 8, 8)
        p.end()
        self.apercu.setPixmap(pm)
        if self.toile.outil in ("gomme", "pipette"):
            self.outil("feutre")

    def _roue(self):
        c = QColorDialog.getColor(self.toile.couleur, self, tr("Choisis une couleur"))
        if c.isValid():
            self.choisir_couleur(c)

    def _taille(self, v):
        self.toile.taille = v
        self.l_taille.setText(tr("Taille du trait") + f" : {v} px")

    def _opac(self, v):
        self.toile.opacite = v / 100.0
        self.l_opac.setText(tr("Opacité") + f" : {v} %")

    def trait_fini(self, n):
        if n % 35 == 0 and time.monotonic() - self.dernier_bravo > 150 and random.random() < 0.7:
            self.dernier_bravo = time.monotonic()
            self.dire(random.choice(BRAVO))

    # ---------- calques
    def _liste_calques(self):
        self.liste.blockSignals(True)
        self.liste.clear()
        for c in reversed(self.toile.calques):           # le calque du haut en premier, comme partout
            it = QListWidgetItem(c["nom"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c["visible"] else Qt.CheckState.Unchecked)
            self.liste.addItem(it)
        self.liste.setCurrentRow(len(self.toile.calques) - 1 - self.toile.actif)
        self.liste.blockSignals(False)
        self._maj_copac()

    def _index(self, row):
        return len(self.toile.calques) - 1 - row

    def _maj_copac(self):
        c = self.toile.calques[self.toile.actif]
        self.s_copac.blockSignals(True)
        self.s_copac.setValue(int(c["opacite"] * 100))
        self.s_copac.blockSignals(False)
        self.l_copac.setText(tr("Opacité du calque") + f" : {int(c['opacite'] * 100)} %")

    def _calque_choisi(self, row):
        if row >= 0:
            self.toile.actif = self._index(row)
            self._maj_copac()

    def _calque_coche(self, it):
        i = self._index(self.liste.row(it))
        self.toile.calques[i]["visible"] = it.checkState() == Qt.CheckState.Checked
        self.toile.update()

    def _calque_opac(self, v):
        self.toile.calques[self.toile.actif]["opacite"] = v / 100.0
        self.l_copac.setText(tr("Opacité du calque") + f" : {v} %")
        self.toile.update()

    def _renommer(self, it):
        i = self._index(self.liste.row(it))
        nom, ok = QInputDialog.getText(self, tr("Renommer le calque"), tr("Nom :"), text=self.toile.calques[i]["nom"])
        if ok and nom.strip():
            self.toile.calques[i]["nom"] = nom.strip()
            self._liste_calques()

    def ajouter_calque(self):
        t = self.toile
        if len(t.calques) >= 12:
            return self.dire("12 calques, c'est le maximum !")
        t.calques.insert(t.actif + 1, {"nom": tr("Calque") + f" {len(t.calques)}", "img": _vide(TAILLE, TAILLE),
                                       "visible": True, "opacite": 1.0})
        t.actif += 1
        t.annuler_pile.clear()
        self._liste_calques()

    def supprimer_calque(self):
        t = self.toile
        if len(t.calques) <= 1:
            return
        if QMessageBox.question(self, tr("Supprimer le calque"),
                                tr("Supprimer le calque") + f" « {t.calques[t.actif]['nom']} » ?") != \
                QMessageBox.StandardButton.Yes:
            return
        del t.calques[t.actif]
        t.actif = max(0, t.actif - 1)
        t.annuler_pile.clear()
        t.refaire_pile.clear()
        self._liste_calques()
        t.update()

    def deplacer_calque(self, sens):
        t = self.toile
        j = t.actif + sens
        if 0 <= j < len(t.calques):
            t.calques[t.actif], t.calques[j] = t.calques[j], t.calques[t.actif]
            t.actif = j
            t.annuler_pile.clear()
            self._liste_calques()
            t.update()

    # ---------- fichiers
    def _confirmer_perte(self):
        if not self.toile.modifie:
            return True
        r = QMessageBox.question(self, tr("Carnet de dessin"), tr("Enregistrer ton dessin avant ?"),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                 QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        return self.enregistrer() if r == QMessageBox.StandardButton.Yes else True

    def nouveau(self):
        if self._confirmer_perte():
            self.toile.nouveau()
            self.fichier = None
            self._liste_calques()

    def enregistrer(self, demander=False):
        if self.fichier is None or demander:
            nom = time.strftime("dessin-%Y-%m-%d-%H%M")
            p, _ = QFileDialog.getSaveFileName(self, tr("Enregistrer le dessin"), str(dossier_dessins() / f"{nom}.ora"),
                                               tr("Dessin avec calques (*.ora);;Image (*.png)"))
            if not p:
                return False
            self.fichier = Path(p)
        p = self.fichier
        try:
            if p.suffix.lower() == ".png":
                self.toile.image_finale().save(str(p))
            else:
                if p.suffix.lower() != ".ora":
                    p = self.fichier = p.with_suffix(".ora")
                self._ecrire_ora(p)
                self.toile.image_finale().save(str(p.with_suffix(".png")))
        except Exception as e:
            QMessageBox.warning(self, tr("Carnet de dessin"), tr("L'enregistrement n'a pas marché :") + f"\n{e}")
            return False
        self.toile.modifie = False
        self.dire("C'est noté !" if random.random() < 0.5 else "Hihi, ça me plaît beaucoup !")
        return True

    def _ecrire_ora(self, p):
        t = self.toile
        tmp = p.with_suffix(".ora.tmp")
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster", compress_type=zipfile.ZIP_STORED)
            pile = []
            for i, c in reversed(list(enumerate(t.calques))):
                src = f"data/calque{i}.png"
                z.writestr(src, _png(c["img"]), compress_type=zipfile.ZIP_DEFLATED)
                pile.append(f'  <layer name={quoteattr(c["nom"])} src="{src}" x="0" y="0" opacity="{c["opacite"]:.2f}" '
                            f'visibility="{"visible" if c["visible"] else "hidden"}"/>')
            xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<image version="0.0.3" w="{TAILLE}" h="{TAILLE}">\n'
                   '<stack>\n' + "\n".join(pile) + '\n</stack>\n</image>\n')
            z.writestr("stack.xml", xml, compress_type=zipfile.ZIP_DEFLATED)
            fin = t.image_finale()
            z.writestr("mergedimage.png", _png(fin), compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("Thumbnails/thumbnail.png", _png(fin.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation)),
                       compress_type=zipfile.ZIP_DEFLATED)
        tmp.replace(p)

    def ouvrir(self):
        if not self._confirmer_perte():
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("Ouvrir un dessin"), str(dossier_dessins()),
                                           tr("Dessins et images (*.ora *.png *.jpg *.jpeg *.webp)"))
        if not p:
            return
        p = Path(p)
        try:
            calques = self._lire_ora(p) if p.suffix.lower() == ".ora" else None
            if calques is None:
                img = QImage(str(p))
                if img.isNull():
                    raise RuntimeError(tr("image illisible"))
                calques = [{"nom": tr("Fond"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0},
                           {"nom": p.stem, "img": self._ajuster(img), "visible": True, "opacite": 1.0}]
        except Exception as e:
            return QMessageBox.warning(self, tr("Carnet de dessin"), tr("Je n'arrive pas à ouvrir ce fichier :") +
                                       f"\n{e}")
        t = self.toile
        t.calques = calques
        t.actif = len(calques) - 1
        t.annuler_pile, t.refaire_pile = [], []
        t.modifie = False
        self.fichier = p if p.suffix.lower() == ".ora" else None
        self._liste_calques()
        t.update()

    def _ajuster(self, img):
        """Une image quelconque, centrée sur la feuille carrée."""
        img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        if img.width() > TAILLE or img.height() > TAILLE:
            img = img.scaled(TAILLE, TAILLE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out = _vide(TAILLE, TAILLE)
        p = QPainter(out)
        p.drawImage((TAILLE - img.width()) // 2, (TAILLE - img.height()) // 2, img)
        p.end()
        return out

    def _lire_ora(self, p):
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(p) as z:
            root = ET.fromstring(z.read("stack.xml"))
            W, H = int(root.get("w", TAILLE)), int(root.get("h", TAILLE))
            calques = []
            for el in root.iter("layer"):
                src = QImage.fromData(z.read(el.get("src")))
                if src.isNull():
                    continue
                feuille = _vide(W, H)
                pa = QPainter(feuille)
                pa.drawImage(int(float(el.get("x", 0))), int(float(el.get("y", 0))), src)
                pa.end()
                calques.append({"nom": el.get("name") or tr("Calque"), "img": self._ajuster(feuille),
                                "visible": el.get("visibility", "visible") != "hidden",
                                "opacite": float(el.get("opacity", 1) or 1)})
                if len(calques) >= 12:
                    break
        if not calques:
            return None
        calques.reverse()                                 # stack.xml : le haut en premier
        return calques

    def decalque(self):
        t = self.toile
        if t.decalque is not None:
            t.decalque = None
            t.update()
            return self.dire("C'est enlevé.")
        p, _ = QFileDialog.getOpenFileName(self, tr("Image à décalquer"), str(Path.home()),
                                           tr("Images (*.png *.jpg *.jpeg *.webp)"))
        if p:
            img = QImage(p)
            if not img.isNull():
                t.decalque = self._ajuster(img)
                t.update()

    # ---------- Viki s'en mêle
    def devine(self):
        fin = self.toile.image_finale()
        if fin.isNull():
            return
        blanc = QImage(fin.size(), QImage.Format.Format_ARGB32)
        blanc.fill(QColor("#ffffff"))
        p = QPainter(blanc)
        p.drawImage(0, 0, fin)
        p.end()
        tmp = Path(getattr(self.comp, "tmpdir", Path("/tmp"))) / "dessin_devine.png"
        blanc.save(str(tmp))
        try:
            self.comp.look_image(tmp, "question",
                                 question="C'est un dessin fait à la main. Devine ce qu'il représente, puis dis un "
                                          "compliment sincère et gentil sur un détail réussi. Deux ou trois phrases.")
        except Exception:
            self.dire("Je n'ai pas réussi à regarder l'image.")

    def en_perso(self):
        fin = self.toile.image_finale()
        r = self._boite(fin)
        if r is None:
            return self.dire("Il n'y a rien de dessiné pour l'instant.")
        if self.toile.calques[0]["visible"] and not self.toile.calques[0]["img"].isNull():
            fond = self._boite(self.toile.calques[0]["img"])
            if fond is not None and fond.width() > TAILLE * 0.9 and fond.height() > TAILLE * 0.9:
                if QMessageBox.question(self, tr("Faire de mon dessin un perso"),
                                        tr("Le calque « Fond » est rempli : il fera un rectangle autour du perso. "
                                           "Le cacher pour le perso ?")) == QMessageBox.StandardButton.Yes:
                    fin = self.toile.image_finale(avec_fond=False)
                    r = self._boite(fin)
                    if r is None:
                        return self.dire("Il n'y a rien de dessiné pour l'instant.")
        contour = QMessageBox.question(self, tr("Faire de mon dessin un perso"),
                                       tr("Ajouter un petit contour blanc, pour qu'il se voie sur tous les fonds "
                                          "d'écran ?")) == QMessageBox.StandardButton.Yes
        marge = 24
        r = r.adjusted(-marge, -marge, marge, marge).intersected(QRect(0, 0, TAILLE, TAILLE))
        img = fin.copy(r)
        if contour:
            img = contour_blanc(img, 6)
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        if self.toile.modifie:
            self.enregistrer()
        self.dire("Super ! Montre-moi où sont les yeux et la bouche.")
        try:
            self.comp._finish_new_character(img)
        except Exception as e:
            QMessageBox.warning(self, tr("Faire de mon dessin un perso"), str(e))

    @staticmethod
    def _boite(img):
        """Le rectangle qui contient tout ce qui est dessiné (None si la feuille est vide)."""
        import numpy as np
        src = img.convertToFormat(QImage.Format.Format_ARGB32)
        w, h = src.width(), src.height()
        a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
        al = a[:, 3:w * 4:4] > 12
        ys, xs = np.nonzero(al)
        if not len(xs):
            return None
        return QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))

    def closeEvent(self, e):
        if not self._confirmer_perte():
            e.ignore()
            return
        super().closeEvent(e)


def contour_blanc(img, r=6):
    """Ajoute un contour blanc autour de ce qui est dessiné (comme un autocollant)."""
    src = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    blanc = src.copy()
    p = QPainter(blanc)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(blanc.rect(), QColor("#ffffff"))
    p.end()
    out = _vide(src.width(), src.height())
    p = QPainter(out)
    import math
    for k in range(16):
        a = k * math.pi / 8
        p.drawImage(QPointF(r * math.cos(a), r * math.sin(a)), blanc)
    p.drawImage(0, 0, src)
    p.end()
    return out


CSS = """
QWidget#carnet { background: #fffafc; color: #2e1624; }
QWidget#carnet QLabel, QWidget#carnet QCheckBox { color: #2e1624; }
QFrame#panneau { background: white; border: 1px solid #f1dfe8; border-radius: 14px; padding: 6px; }
QPushButton { background: white; border: 1px solid #ecd3df; border-radius: 10px; padding: 7px 11px; color: #2e1624; }
QPushButton:hover { background: #fdf0f5; }
QPushButton#main { background: #b0336a; color: white; border: none; font-weight: 700; }
QPushButton#main:hover { background: #9a2b5c; }
QToolButton { background: white; border: 1px solid transparent; border-radius: 12px; }
QToolButton:hover { background: #fdf0f5; }
QToolButton:checked { background: #fdf0f5; border: 1px solid #f0bfd4; }
QListWidget { background: white; border: 1px solid #f1dfe8; border-radius: 10px; color: #2e1624; }
QListWidget::item:selected { background: #fdf0f5; color: #8a2453; }
"""
