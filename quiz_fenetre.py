"""🎓 Le quiz de révision : une question à la fois, quatre choix, l'explication, et le score à la fin."""
import random

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t


class QuizFenetre(QDialog):
    def __init__(self, comp, sujet, questions):
        super().__init__(None)
        self.comp, self.qs, self.i, self.score = comp, questions, 0, 0
        self.setWindowTitle("🎓 " + sujet[:50])
        self.resize(560, 420)
        v = QVBoxLayout(self)
        self.num = QLabel()
        self.num.setStyleSheet("color: #c05a7a; font-weight: bold;")
        v.addWidget(self.num)
        self.q = QLabel()
        self.q.setWordWrap(True)
        self.q.setStyleSheet("font-size: 13pt; font-weight: bold;")
        v.addWidget(self.q)
        self.boutons = []
        for _ in range(4):
            b = QPushButton()
            b.setStyleSheet("text-align: left; padding: 8px;")
            b.clicked.connect(lambda _c=False, b=b: self.repondre(b))
            v.addWidget(b)
            self.boutons.append(b)
        self.expl = QLabel()
        self.expl.setWordWrap(True)
        v.addWidget(self.expl, 1)
        h = QHBoxLayout()
        h.addStretch(1)
        self.suite = QPushButton(tr("Question suivante ▶"))
        self.suite.clicked.connect(self.suivante)
        h.addWidget(self.suite)
        v.addLayout(h)
        self.montrer()

    def montrer(self):
        q = self.qs[self.i]
        self.num.setText(tr("Question {} / {}").format(self.i + 1, len(self.qs)))
        self.q.setText(str(q["q"]))
        self.expl.setText("")
        self.suite.setEnabled(False)
        for k, b in enumerate(self.boutons):
            if k < len(q["choix"]):
                b.setText(f"{'ABCD'[k]}. {q['choix'][k]}")
                b.setVisible(True)
                b.setEnabled(True)
                b.setStyleSheet("text-align: left; padding: 8px;")
            else:
                b.setVisible(False)

    def repondre(self, b):
        q = self.qs[self.i]
        k = self.boutons.index(b)
        try:
            bonne = int(q.get("bonne", 0))
        except (TypeError, ValueError):
            bonne = 0
        ok = k == bonne
        self.score += ok
        for j, bb in enumerate(self.boutons):
            bb.setEnabled(False)
            if j == bonne:
                bb.setStyleSheet("text-align: left; padding: 8px; background: #2e7d32; color: white;")
            elif j == k:
                bb.setStyleSheet("text-align: left; padding: 8px; background: #c62828; color: white;")
        self.expl.setText(("✅ " if ok else "❌ ") + str(q.get("explication") or ""))
        self.suite.setEnabled(True)
        if self.i == len(self.qs) - 1:
            self.suite.setText(tr("Voir mon score"))

    def suivante(self):
        self.i += 1
        if self.i >= len(self.qs):
            n = len(self.qs)
            self.q.setText(tr("Score : {} / {}").format(self.score, n))
            for b in self.boutons:
                b.setVisible(False)
            self.expl.setText("")
            self.suite.setText(tr("Fermer"))
            self.suite.clicked.disconnect()
            self.suite.clicked.connect(self.close)
            msg = random.choice(["Bravo, c'est parfait ! 🎉", "Excellent travail !"]) if self.score == n else \
                "Pas mal du tout ! On refait les questions ratées une autre fois ?" if self.score >= n / 2 else \
                "Ce n'est pas grave, on révise encore un peu et ça va rentrer ! 💪"
            self.comp.say(msg)
            return
        self.montrer()
