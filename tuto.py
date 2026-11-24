"""📖 Le petit tuto : les fonctions de base, en quelques pages, dans une fenêtre propre posée à côté de Viki.

Il s'ouvre une seule fois (après la première installation) ; on peut le revoir quand on veut
(clic droit → 📖 Découvrir Viki, ou « montre-moi le tuto »). Chaque page a un bouton « Essayer ».
"""
from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

# (pictogramme Tabler, couleur, titre, texte, action du bouton « Essayer » ou "")
PAGES = [
    (0xeabe, "#ff4f8b", "Coucou, moi c'est Viki !",
     "Je vis sur ton bureau et je t'aide pour plein de choses. Tout reste sur ton PC. Voici l'essentiel en quelques pages.", ""),
    (0xef4f, "#0a84ff", "Un clic sur moi",
     "Mes raccourcis apparaissent à côté de moi : m'écrire, aujourd'hui, ta forme, le texte, le mode curseur… "
     "Un autre clic les cache.", "ronds"),
    (0xec42, "#5e5ce6", "Clic droit : tout le reste",
     "Toutes mes fonctions, rangées par thème : parler avec moi, ton quotidien, musique et vidéos, créer, "
     "ton PC, et moi.", "menu"),
    (0xeaed, "#30d158", "Parle-moi avec tes mots",
     "Double-clic sur moi pour m'écrire (ou 🎤 pour me parler). « Rappelle-moi jeudi à 14h… », « Je dois payer "
     "l'électricité avant le 10 », « Traduis ce que j'ai copié »…", "ecrire"),
    (0xea51, "#ffd60a", "Pas besoin de deviner",
     "Commence à écrire un mot (« musique », « rappel », « image »…) : je te propose des phrases à cliquer. Et "
     "« ✨ Ce que je sais faire » (clic droit, ou écris « aide ») montre tout, en grandes fiches.", "livre"),
    (0xedeb, "#ff9f0a", "Je te montre sur l'écran",
     "« Montre-moi où changer le fond d'écran » : j'entoure, je souligne et je pointe où cliquer. C'est toi qui "
     "cliques, toujours.", "guide"),
    (0xf265, "#bf5af2", "Le mode curseur",
     "Mon pointeur avec mon visage, et ma roue autour de la souris (les deux boutons de la souris, ou "
     "Meta+Alt+Espace) : c'est quoi ça, copier ou traduire le texte ici…", "curseur"),
    (0xece9, "#64d2ff", "Je reste discrète",
     "Pendant que tu me demandes quelque chose, je ne parle de rien d'autre. Dans « 🔕 Ce qu'elle me dit », tu "
     "choisis ce que je peux te dire de moi-même.", "muets"),
    (0xea48, "#ff453a", "Un bug ? Dis-le-moi",
     "Je suis faite par une seule personne, sur un vieux PC. Si je bugue, dis « signale un bug » : le rapport est "
     "prêt, sans rien de personnel. Merci ! 💜", "bug"),
]


WIN = __import__("sys").platform.startswith("win")   # Windows : la roue s'ouvre avec Win+Alt+…


class Icone(QWidget):
    def __init__(self, police, parent=None):
        super().__init__(parent)
        self.police, self.code, self.coul = police, 0, QColor("#ff4f8b")
        self.setFixedSize(84, 84)

    def regler(self, code, coul):
        self.code, self.coul = code, QColor(coul)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4, 4, 76, 76)
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)                       # la forme « squircle » des icônes d'app
        haut, bas = QColor(self.coul).lighter(118), QColor(self.coul).darker(112)
        from PyQt6.QtGui import QLinearGradient
        g = QLinearGradient(0, 4, 0, 80)
        g.setColorAt(0, haut)
        g.setColorAt(1, bas)
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(path)
        if self.police and self.code:
            f = QFont(self.police)
            f.setPixelSize(40)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, chr(self.code))
        p.end()


class Points(QWidget):
    def __init__(self, n, parent=None):
        super().__init__(parent)
        self.n, self.i = n, 0
        self.setFixedSize(n * 16, 12)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for k in range(self.n):
            on = k == self.i
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 230 if on else 70))
            p.drawEllipse(QPointF(8 + k * 16, 6), 4 if on else 3, 4 if on else 3)
        p.end()


class Tuto(QWidget):
    essayer = pyqtSignal(str)
    ferme = pyqtSignal()

    def __init__(self, police=""):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 430)
        self.i = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(10)
        haut = QHBoxLayout()
        self.b_x = QPushButton("✕")
        self.b_x.setFixedSize(28, 28)
        self.b_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_x.setStyleSheet("QPushButton { background: rgba(255,255,255,30); color: #f5f5f7; border: none; "
                               "border-radius: 14px; font-size: 11pt; } QPushButton:hover { background: rgba(255,255,255,60); }")
        self.b_x.clicked.connect(self.close)
        haut.addStretch(1)
        haut.addWidget(self.b_x)
        v.addLayout(haut)
        self.ico = Icone(police)
        v.addWidget(self.ico, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(6)
        self.titre = QLabel()
        self.titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titre.setWordWrap(True)
        self.titre.setStyleSheet("color: #f5f5f7; font-size: 17pt; font-weight: 700;")
        v.addWidget(self.titre)
        self.texte = QLabel()
        self.texte.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.texte.setWordWrap(True)
        self.texte.setStyleSheet("color: rgba(235,235,245,0.75); font-size: 11pt; line-height: 140%;")
        self.texte.setMinimumHeight(96)
        v.addWidget(self.texte, 1)
        self.b_essai = QPushButton()
        self.b_essai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_essai.setStyleSheet("QPushButton { background: rgba(255,255,255,26); color: #f5f5f7; border: 1px solid "
                                   "rgba(255,255,255,50); border-radius: 15px; padding: 6px 16px; font-size: 10.5pt; } "
                                   "QPushButton:hover { background: rgba(255,255,255,48); }")
        self.b_essai.clicked.connect(lambda: self.essayer.emit(PAGES[self.i][4]))
        v.addWidget(self.b_essai, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(4)
        self.points = Points(len(PAGES))
        v.addWidget(self.points, 0, Qt.AlignmentFlag.AlignHCenter)
        bas = QHBoxLayout()
        self.b_prec = QPushButton(tr("Retour"))
        self.b_suiv = QPushButton(tr("Suivant"))
        for b, bleu in ((self.b_prec, False), (self.b_suiv, True)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(34)
            b.setStyleSheet(("QPushButton { background: #0a84ff; color: white; border: none; border-radius: 10px; "
                             "font-size: 11pt; font-weight: 600; padding: 0 18px; } QPushButton:hover { background: #3399ff; }")
                            if bleu else
                            ("QPushButton { background: transparent; color: rgba(235,235,245,0.7); border: none; "
                             "font-size: 11pt; padding: 0 10px; } QPushButton:hover { color: white; }"))
        self.b_prec.clicked.connect(lambda: self.aller(self.i - 1))
        self.b_suiv.clicked.connect(lambda: self.close() if self.i == len(PAGES) - 1 else self.aller(self.i + 1))
        bas.addWidget(self.b_prec)
        bas.addStretch(1)
        bas.addWidget(self.b_suiv)
        v.addLayout(bas)
        for wd in [self] + self.findChildren(QWidget):          # ses couleurs à elle (le thème n'y touche pas)
            wd.setProperty("sans_theme", True)
        self._fondu = QGraphicsOpacityEffect(self.texte)
        self.texte.setGraphicsEffect(self._fondu)
        self.aller(0)

    def aller(self, i):
        self.i = max(0, min(len(PAGES) - 1, i))
        code, coul, titre, texte, act = PAGES[self.i]
        self.ico.regler(code, coul)
        self.titre.setText(tr(titre))
        self.texte.setText(tr(texte).replace("Meta+Alt+", "Win+Alt+") if WIN else tr(texte))
        self.b_essai.setText(tr("Essayer") + " →")
        self.b_essai.setVisible(bool(act))
        self.points.i = self.i
        self.points.update()
        self.b_prec.setVisible(self.i > 0)
        self.b_suiv.setText(tr("C'est parti !") if self.i == len(PAGES) - 1 else tr("Suivant"))
        an = QPropertyAnimation(self._fondu, b"opacity", self)
        an.setDuration(220)
        an.setStartValue(0.0)
        an.setEndValue(1.0)
        an.setEasingCurve(QEasingCurve.Type.OutCubic)
        an.start()
        self._an = an

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.b_suiv.click()
        elif e.key() == Qt.Key.Key_Left and self.i > 0:
            self.aller(self.i - 1)
        elif e.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, e):                            # on peut la déplacer en la tirant
        self._tire = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if getattr(self, "_tire", None) is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._tire)

    def mouseReleaseEvent(self, e):
        self._tire = None

    def closeEvent(self, e):
        self.ferme.emit()
        super().closeEvent(e)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        for k in range(6):                                   # ombre douce
            sh = QPainterPath()
            sh.addRoundedRect(r.adjusted(-k, -k + 2, k, k + 3), 22 + k, 22 + k)
            p.fillPath(sh, QColor(0, 0, 0, 10))
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        p.fillPath(path, QColor(30, 31, 38, 244))
        p.setPen(QPen(QColor(255, 255, 255, 38), 1))
        p.drawPath(path)
        p.end()
