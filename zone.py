"""🔲 Traduire une zone de l'écran : on encadre un morceau d'écran (texte d'un jeu, message d'erreur, image…),
Viki le lit et le traduit, et le résultat s'affiche dans une petite fenêtre juste à côté de la zone.
Marche sur X11 et Wayland (capture par Spectacle, grim, gnome-screenshot… comme « Regarde mon écran »).
L'image reste sur ton PC (elle part seulement vers l'IA que tu as choisie)."""
from PyQt6.QtCore import Qt, QRect, QPoint, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QImage, QFont, QCursor, QGuiApplication
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QApplication, QTextBrowser)

try:
    from i18n import tr
except Exception:                                          # pragma: no cover
    def tr(t):
        return t


class Selecteur(QWidget):
    """Plein écran sur l'écran de la souris : l'écran figé, assombri ; on trace un rectangle. Échap : annuler."""
    choisi = pyqtSignal(QImage, QRect)                      # image découpée, zone en coordonnées écran
    annule = pyqtSignal()

    def __init__(self, capture):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.geo = scr.geometry()
        virt = QGuiApplication.primaryScreen().virtualGeometry()
        # la capture couvre souvent tous les écrans : on garde la partie de celui-ci
        if capture.width() >= virt.width() * 0.9 and capture.width() > 0:
            k = capture.width() / max(1, virt.width())
            part = QRect(int((self.geo.x() - virt.x()) * k), int((self.geo.y() - virt.y()) * k),
                         int(self.geo.width() * k), int(self.geo.height() * k))
            capture = capture.copy(part)
        self.img = capture
        self.k = self.img.width() / max(1, self.geo.width())
        self.a = self.b = None
        self.setGeometry(self.geo)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawImage(QRectF(self.rect()), self.img, QRectF(self.img.rect()))
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self.a and self.b:
            r = QRect(self.a, self.b).normalized()
            p.drawImage(QRectF(r), self.img, QRectF(r.x() * self.k, r.y() * self.k, r.width() * self.k,
                                                     r.height() * self.k))
            p.setPen(QPen(QColor(10, 132, 255), 2))
            p.drawRect(r)
        f = QFont()
        f.setPixelSize(16)
        f.setBold(True)
        p.setFont(f)
        txt = tr("Encadre le texte à traduire · Échap : annuler")
        w = p.fontMetrics().horizontalAdvance(txt) + 36
        bandeau = QRectF((self.width() - w) / 2, 24, w, 40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 22, 30, 225))
        p.drawRoundedRect(bandeau, 20, 20)
        p.setPen(QColor("white"))
        p.drawText(bandeau, Qt.AlignmentFlag.AlignCenter, txt)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            return self._annuler()
        self.a = self.b = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):
        if self.a is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.b = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.a is None:
            return
        r = QRect(self.a, e.position().toPoint()).normalized()
        if r.width() < 12 or r.height() < 8:
            self.a = self.b = None
            return self.update()
        crop = self.img.copy(QRect(int(r.x() * self.k), int(r.y() * self.k), int(r.width() * self.k),
                                   int(r.height() * self.k)))
        self.hide()
        self.choisi.emit(crop, r.translated(self.geo.topLeft()))
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._annuler()

    def _annuler(self):
        self.hide()
        self.annule.emit()
        self.close()


class Resultat(QWidget):
    """La traduction, dans une petite fenêtre posée à côté de la zone encadrée."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)
        self.setStyleSheet("""
QWidget#cadre { background: #1f1d26; border: 1px solid #3a3644; border-radius: 14px; }
QLabel#titre { color: #ece9f2; font-weight: bold; font-size: 13px; }
QTextBrowser { background: transparent; border: none; color: #ece9f2; font-size: 13px; }
QPushButton { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px;
              padding: 4px 10px; font-size: 12px; }
QPushButton:hover { background: #36323f; }
""")
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QWidget()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        v = QVBoxLayout(cadre)
        v.setContentsMargins(14, 10, 14, 10)
        h = QHBoxLayout()
        self.titre = QLabel(tr("🔤 Traduction"))
        self.titre.setObjectName("titre")
        h.addWidget(self.titre, 1)
        self.b_copier = QPushButton(tr("Copier"))
        self.b_copier.clicked.connect(lambda: QApplication.clipboard().setText(self.texte.toPlainText()))
        h.addWidget(self.b_copier)
        self.b_encore = QPushButton(tr("Une autre zone"))
        h.addWidget(self.b_encore)
        x = QPushButton("✕")
        x.clicked.connect(self.close)
        h.addWidget(x)
        v.addLayout(h)
        self.texte = QTextBrowser()
        self.texte.setOpenExternalLinks(False)
        v.addWidget(self.texte, 1)
        self._drag = None

    def montrer(self, zone, texte, titre=None):
        if titre:
            self.titre.setText(titre)
        self.texte.setPlainText(texte)
        doc_h = int(self.texte.document().size().height()) if texte else 40
        w = max(320, min(520, zone.width()))
        h = max(120, min(420, doc_h + 70))
        self.resize(w, h)
        scr = (QGuiApplication.screenAt(zone.center()) or QGuiApplication.primaryScreen()).availableGeometry()
        # à droite de la zone, sinon à gauche, sinon dessous, sinon dessus
        for x, y in ((zone.right() + 12, zone.top()), (zone.left() - w - 12, zone.top()),
                     (zone.left(), zone.bottom() + 12), (zone.left(), zone.top() - h - 12)):
            if scr.left() <= x and x + w <= scr.right() and scr.top() <= y and y + h <= scr.bottom():
                break
        else:
            x, y = scr.right() - w - 12, scr.top() + 12
        x = max(scr.left(), min(x, scr.right() - w))
        y = max(scr.top(), min(y, scr.bottom() - h))
        self.move(QPoint(int(x), int(y)))
        self.show()
        self.raise_()

    def mousePressEvent(self, e):
        self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e):
        self._drag = None
