"""Les fenêtres de Viki habillées comme la carte du tuto : sans le cadre du bureau, coins arrondis,
et les mêmes petits boutons ronds en haut à droite (réduire, agrandir, ✕).

Tout passe par le filtre d'événements de themes.py : aucune fenêtre n'a besoin d'être modifiée.
On garde le déplacement (on tire la barre du haut) et le redimensionnement (on tire un bord ou un coin),
y compris sous Wayland (startSystemMove / startSystemResize).
Le menu du clic droit, Viki elle-même, ses bulles et tout ce qui flotte sur le bureau ne sont pas touchés."""
import os
import re

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

ACTIF = os.environ.get("VIKI_CADRE_SYSTEME", "") not in ("1", "oui", "true")
BARRE = 44          # hauteur de la barre du haut
BORD = 6            # zone des bords pour redimensionner
RAYON = 18
_H = {}             # id(fenêtre) -> sa barre
_EXCLUS = ("QFileDialog", "QColorDialog", "QFontDialog", "QPrintDialog", "QMenu", "QComboBoxPrivateContainer")
_TYPES = {QEvent.Type.Paint, QEvent.Type.Resize,
          QEvent.Type.Leave, QEvent.Type.WindowTitleChange, QEvent.Type.WindowStateChange,
          QEvent.Type.StyleChange}
_RX = re.compile(r"/\*habit\*/.*?/\*finhabit\*/", re.S)


def _eligible(w):
    try:
        if not isinstance(w, QWidget) or not w.isWindow() or isinstance(w, QMenu):
            return False
        if w.property("sans_theme") or w.property("sans_habit"):
            return False
        if any(c.__name__ in _EXCLUS for c in type(w).__mro__):
            return False
        f = w.windowFlags()
        typ = w.windowType()
        if typ not in (Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Tool):
            return False
        if f & Qt.WindowType.FramelessWindowHint or w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
            return False                       # déjà sans cadre : elle, ses bulles, les calques…
        if w.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return False                       # déjà affichée : on ne la recrée pas sous les yeux
        if w.layout() is None:
            return False
        if type(w).__name__ in ("Companion",):
            return False
        return True
    except Exception:
        return False


def habiller(w):
    """Appelé quand la fenêtre est préparée, juste avant d'exister à l'écran."""
    if id(w) in _H or not _eligible(w):
        return
    try:
        fixe = w.minimumSize() == w.maximumSize() and w.minimumWidth() > 0
        taille = w.size()
        w.setWindowFlags(w.windowFlags() | Qt.WindowType.FramelessWindowHint)
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        w.setAutoFillBackground(False)
        lay = w.layout()
        m = lay.contentsMargins()
        lay.setContentsMargins(m.left() + BORD, m.top() + BARRE, m.right() + BORD, m.bottom() + BORD)
        dw, dh = 2 * BORD, BARRE + BORD
        if fixe:
            w.setFixedSize(taille.width() + dw, taille.height() + dh)
        elif w.testAttribute(Qt.WidgetAttribute.WA_Resized):
            w.resize(taille.width() + dw, taille.height() + dh)
        if not w.objectName():
            w.setObjectName("vikiFenetre%d" % (len(_H) + 1))
        b = Barre(w)
        b.poignees = [] if fixe else [Poignee(w, e) for e in _COTES]
        _H[id(w)] = b
        w.destroyed.connect(lambda *_a, k=id(w): _H.pop(k, None))
    except Exception:
        pass


def _feuille(w):
    s = w.styleSheet() or ""
    if "/*habit*/" in s:
        return
    w.setStyleSheet(_RX.sub("", s) + "\n/*habit*/ QWidget#%s { background: transparent; border: none; } /*finhabit*/"
                    % w.objectName())


def montrer(w):
    b = _H.get(id(w))
    if b is None:
        return
    try:
        _feuille(w)
        _placer(w, b)
        b.show()
        scr = w.screen().availableGeometry() if w.screen() else None
        if scr is not None and (w.width() > scr.width() or w.height() > scr.height()):
            w.resize(min(w.width(), scr.width()), min(w.height(), scr.height()))
    except Exception:
        pass


_E = Qt.Edge
_COTES = (_E.LeftEdge, _E.RightEdge, _E.TopEdge, _E.BottomEdge, _E.LeftEdge | _E.TopEdge, _E.RightEdge | _E.TopEdge,
          _E.LeftEdge | _E.BottomEdge, _E.RightEdge | _E.BottomEdge)


class Poignee(QWidget):
    """Une fine zone invisible sur un bord ou un coin : la double flèche n'apparaît que là."""

    def __init__(self, fen, cote):
        super().__init__(fen)
        self.fen, self.cote = fen, cote
        self.setProperty("sans_theme", True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setCursor(_curseur(cote))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not _plein(self.fen) and self.fen.windowHandle() is not None:
            self.fen.windowHandle().startSystemResize(self.cote)


def _placer(w, b):
    W, H, k, c = w.width(), w.height(), BORD, 14
    b.setGeometry(0, 0, W, BARRE)
    b.raise_()
    for g in getattr(b, "poignees", []):
        e = g.cote
        if e == _E.LeftEdge:
            r = (0, c, k, H - 2 * c)
        elif e == _E.RightEdge:
            r = (W - k, c, k, H - 2 * c)
        elif e == _E.TopEdge:
            r = (c, 0, W - 2 * c - 130, 4)            # pas sur les boutons ronds
        elif e == _E.BottomEdge:
            r = (c, H - k, W - 2 * c, k)
        elif e == _E.LeftEdge | _E.TopEdge:
            r = (0, 0, c, c)
        elif e == _E.RightEdge | _E.TopEdge:
            r = (W - c, 0, c, c)
        elif e == _E.LeftEdge | _E.BottomEdge:
            r = (0, H - c, c, c)
        else:
            r = (W - c, H - c, c, c)
        g.setGeometry(*r)
        g.setVisible(not _plein(w))
        g.raise_()


def concerne(obj, t):
    return t in _TYPES and id(obj) in _H


def _bords(w, p):
    e = Qt.Edge(0)
    if p.x() <= BORD:
        e |= Qt.Edge.LeftEdge
    elif p.x() >= w.width() - BORD:
        e |= Qt.Edge.RightEdge
    if p.y() <= 4:
        e |= Qt.Edge.TopEdge
    elif p.y() >= w.height() - BORD:
        e |= Qt.Edge.BottomEdge
    return e


def _curseur(e):
    E = Qt.Edge
    if e in (E.LeftEdge | E.TopEdge, E.RightEdge | E.BottomEdge):
        return Qt.CursorShape.SizeFDiagCursor
    if e in (E.RightEdge | E.TopEdge, E.LeftEdge | E.BottomEdge):
        return Qt.CursorShape.SizeBDiagCursor
    if e in (E.LeftEdge, E.RightEdge):
        return Qt.CursorShape.SizeHorCursor
    if e in (E.TopEdge, E.BottomEdge):
        return Qt.CursorShape.SizeVerCursor
    return None


def _plein(w):
    return bool(w.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))


def evenement(w, ev, sombre=True, fond="#1e1f26"):
    """Renvoie True si l'événement est entièrement géré ici."""
    t = ev.type()
    b = _H.get(id(w))
    if b is None:
        return False
    try:
        if t == QEvent.Type.Paint:
            p = QPainter(w)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(w.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            rayon = 0 if _plein(w) else RAYON
            chemin = QPainterPath()
            chemin.addRoundedRect(r, rayon, rayon)
            p.fillPath(chemin, QColor(fond))
            p.setPen(QPen(QColor(255, 255, 255, 26) if sombre else QColor(0, 0, 0, 40), 1))
            p.drawPath(chemin)
            p.end()
            return False
        if t == QEvent.Type.Resize:
            _placer(w, b)
        elif t in (QEvent.Type.WindowTitleChange, QEvent.Type.WindowStateChange):
            _placer(w, b)
            b.update()
            w.update()
        elif t == QEvent.Type.StyleChange:
            if "/*habit*/" not in (w.styleSheet() or ""):
                QTimer.singleShot(0, lambda: _feuille(w) if id(w) in _H else None)
    except Exception:
        pass
    return False


class Barre(QWidget):
    """La barre du haut, comme la carte du tuto : juste le petit ✕ rond à droite.
    On la tire pour déplacer la fenêtre, double-clic pour l'agrandir."""

    def __init__(self, fen):
        super().__init__(fen)
        self.fen = fen
        self.setProperty("sans_theme", True)
        self.setMouseTracking(True)
        self.survol = None
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def _ronds(self):
        """[réduire, agrandir, fermer] de gauche à droite, comme le ✕ du tuto."""
        x = self.width() - 14 - 28
        out = {"fermer": QRectF(x, 10, 28, 28)}
        if self._peut_agrandir():
            x -= 36
            out["agrandir"] = QRectF(x, 10, 28, 28)
        x -= 36
        out["reduire"] = QRectF(x, 10, 28, 28)
        return out

    def _sous(self, pos):
        for k, r in self._ronds().items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return k
        return None

    def _peut_agrandir(self):
        return self.fen.maximumSize() != self.fen.minimumSize()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            import themes
            sombre = themes.est_sombre()
        except Exception:
            sombre = True
        trait = QColor(245, 245, 247) if sombre else QColor(60, 60, 67)
        for k, r in self._ronds().items():
            dessus = self.survol == k
            p.setPen(Qt.PenStyle.NoPen)
            if k == "fermer" and dessus:
                p.setBrush(QColor(255, 69, 58, 210))
            elif sombre:
                p.setBrush(QColor(255, 255, 255, 60 if dessus else 30))
            else:
                p.setBrush(QColor(0, 0, 0, 34 if dessus else 16))
            p.drawEllipse(r)
            pen = QPen(QColor("white") if (k == "fermer" and dessus) else trait, 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            c, d = r.center(), 4.2
            if k == "fermer":
                p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
                p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))
            elif k == "reduire":
                p.drawLine(QPointF(c.x() - 4.5, c.y()), QPointF(c.x() + 4.5, c.y()))
            elif _plein(self.fen):                          # remettre en petit : deux carrés
                p.drawRoundedRect(QRectF(c.x() - 4.5, c.y() - 2, 6.5, 6.5), 1.5, 1.5)
                p.drawLine(QPointF(c.x() - 2, c.y() - 4.5), QPointF(c.x() + 4.5, c.y() - 4.5))
                p.drawLine(QPointF(c.x() + 4.5, c.y() - 4.5), QPointF(c.x() + 4.5, c.y() + 2))
            else:
                p.drawRoundedRect(QRectF(c.x() - 4.5, c.y() - 4.5, 9, 9), 2, 2)
        p.end()

    def mouseMoveEvent(self, e):
        s = self._sous(e.position())
        if s != self.survol:
            self.survol = s
            self.setCursor(Qt.CursorShape.PointingHandCursor if s else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _e):
        if self.survol:
            self.survol = None
            self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        k = self._sous(e.position())
        if k == "fermer":
            self.fen.close()
        elif k == "reduire":
            self.fen.showMinimized()
        elif k == "agrandir":
            self._basculer()
        elif e.position().y() <= 4 and self._peut_agrandir() and self.fen.windowHandle() is not None \
                and not _plein(self.fen):
            self.fen.windowHandle().startSystemResize(Qt.Edge.TopEdge)
        elif self.fen.windowHandle() is not None:
            self.fen.windowHandle().startSystemMove()

    def _basculer(self):
        if self.fen.isMaximized():
            self.fen.showNormal()
        else:
            self.fen.showMaximized()

    def mouseDoubleClickEvent(self, e):
        if not self._sous(e.position()) and self._peut_agrandir():
            self._basculer()


_PATCH = []


def installer():
    """Habille chaque fenêtre au moment où on l'affiche (avant que le bureau ne la crée)."""
    if _PATCH:
        return
    from PyQt6.QtWidgets import QDialog
    orig_show, orig_exec, orig_open = QWidget.show, QDialog.exec, QDialog.open

    def show(self):
        if ACTIF:
            habiller(self)
        return orig_show(self)

    def exec_(self):
        if ACTIF:
            habiller(self)
        return orig_exec(self)

    def open_(self):
        if ACTIF:
            habiller(self)
        return orig_open(self)

    QWidget.show, QDialog.exec, QDialog.open = show, exec_, open_
    _PATCH.append((orig_show, orig_exec, orig_open))


def quitter_tout():
    """Pour les tests : combien de fenêtres sont habillées."""
    return len(_H)


_ = QApplication
