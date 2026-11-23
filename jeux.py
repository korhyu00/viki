"""🎮 Petits jeux avec Viki : puissance 4, pendu et memory. Elle joue (et parfois perd exprès un peu)."""
import random

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

try:
    from i18n import tr, lang
except Exception:
    def tr(t):
        return t

    def lang():
        return "fr"

CSS = """
QWidget#jeu { background: #fffafc; color: #2e1624; }
QWidget#jeu QLabel { color: #2e1624; }
QPushButton { background: white; border: 1px solid #ecd3df; border-radius: 10px; padding: 7px 12px; color: #2e1624; }
QPushButton:hover { background: #fdf0f5; }
QPushButton:disabled { color: #c9b8c1; background: #f6eef2; }
"""


class _Fenetre(QWidget):
    def __init__(self, comp, titre):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setObjectName("jeu")
        self.setStyleSheet(CSS)
        self.setWindowTitle(tr(titre) + " — " + comp.char.get("name", "Viki"))
        self.score = [0, 0, 0]                    # toi, elle, égalités
        self.info = QLabel()
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info.setWordWrap(True)

    def _info(self, extra=""):
        self.info.setText((tr(extra) + "\n" if extra else "") + tr("Toi") + f" {self.score[0]}  ·  " +
                          tr("Égalités") + f" {self.score[2]}  ·  " + self.comp.char.get("name", "Viki") +
                          f" {self.score[1]}")

    def _fin(self, quoi):
        """quoi : « toi », « elle » ou « nul »."""
        k = {"toi": 0, "elle": 1, "nul": 2}[quoi]
        self.score[k] += 1
        self.comp.game_event({"toi": "perdu", "elle": "gagne", "nul": "nul"}[quoi])
        self._info({"toi": "Tu as gagné !", "elle": "Elle a gagné !", "nul": "Égalité !"}[quoi])


# ------------------------------------------------------------------ puissance 4
class Plateau(QWidget):
    L, H = 7, 6

    def __init__(self, jeu):
        super().__init__()
        self.jeu = jeu
        self.setMinimumSize(420, 360)
        self.survol = -1
        self.setMouseTracking(True)

    def _geo(self):
        c = min(self.width() / self.L, self.height() / (self.H + 0.6))
        x0 = (self.width() - c * self.L) / 2
        return c, x0, c * 0.6

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, x0, y0 = self._geo()
        if self.survol >= 0 and not self.jeu.fini:
            p.setBrush(QColor(74, 144, 226, 120))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x0 + self.survol * c + c * 0.15, c * 0.05, c * 0.7, c * 0.5))
        p.setBrush(QColor("#4a6fd8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x0, y0, c * self.L, c * self.H), 16, 16)
        for col in range(self.L):
            for lig in range(self.H):
                v = self.jeu.grille[lig][col]
                coul = {0: "#fffafc", 1: "#f5c518", 2: "#e0483c"}[v]
                p.setBrush(QColor(coul))
                gagne = (lig, col) in self.jeu.ligne
                p.setPen(QPen(QColor("#ffffff"), 4) if gagne else Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(x0 + col * c + c * 0.1, y0 + lig * c + c * 0.1, c * 0.8, c * 0.8))

    def _col(self, x):
        c, x0, _y = self._geo()
        k = int((x - x0) // c)
        return k if 0 <= k < self.L else -1

    def mouseMoveEvent(self, e):
        self.survol = self._col(e.position().x())
        self.update()

    def mousePressEvent(self, e):
        k = self._col(e.position().x())
        if k >= 0:
            self.jeu.jouer(k)


class Puissance4(_Fenetre):
    """Toi en jaune, elle en rouge. Elle réfléchit quelques coups à l'avance (et se trompe parfois)."""

    def __init__(self, comp):
        super().__init__(comp, "Puissance 4")
        self.resize(520, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        self.plateau = Plateau(self)
        lay.addWidget(self.plateau, 1)
        b = QPushButton(tr("Nouvelle partie"))
        b.clicked.connect(self.nouvelle)
        lay.addWidget(b)
        self.niveau = 0.7
        self.toi_commence = True
        self.nouvelle()

    def nouvelle(self):
        self.grille = [[0] * 7 for _ in range(6)]
        self.fini = False
        self.ligne = []
        self.son_tour = not self.toi_commence
        self.toi_commence = not self.toi_commence
        self._info("Clique sur une colonne pour jouer." if not self.son_tour else "Elle commence !")
        self.plateau.update()
        if self.son_tour:
            QTimer.singleShot(500, self._elle)

    @staticmethod
    def _poser(g, col, v):
        for lig in range(5, -1, -1):
            if g[lig][col] == 0:
                g[lig][col] = v
                return lig
        return -1

    @staticmethod
    def _gagnant(g):
        for lig in range(6):
            for col in range(7):
                v = g[lig][col]
                if not v:
                    continue
                for dl, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    cases = [(lig + i * dl, col + i * dc) for i in range(4)]
                    if all(0 <= a < 6 and 0 <= b < 7 and g[a][b] == v for a, b in cases):
                        return v, cases
        if all(g[0][c] for c in range(7)):
            return 3, []
        return 0, []

    def jouer(self, col):
        if self.fini or self.son_tour or self._poser(self.grille, col, 1) < 0:
            return
        self.plateau.update()
        if not self._verif():
            self.son_tour = True
            QTimer.singleShot(450, self._elle)

    def _score(self, g):
        """Évaluation simple : alignements de 2 et 3 avec des cases libres."""
        s = 0
        for lig in range(6):
            for col in range(7):
                for dl, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    cases = [(lig + i * dl, col + i * dc) for i in range(4)]
                    if not all(0 <= a < 6 and 0 <= b < 7 for a, b in cases):
                        continue
                    vals = [g[a][b] for a, b in cases]
                    if 1 in vals and 2 in vals:
                        continue
                    n2, n1 = vals.count(2), vals.count(1)
                    s += {2: 2, 3: 10}.get(n2, 0) - {2: 2, 3: 12}.get(n1, 0)
        s += sum(3 for lig in range(6) if g[lig][3] == 2)
        return s

    def _minimax(self, g, prof, a, b, elle):
        v, _ = self._gagnant(g)
        if v == 2:
            return 10000 + prof, None
        if v == 1:
            return -10000 - prof, None
        if v == 3 or prof == 0:
            return self._score(g), None
        cols = [c for c in (3, 2, 4, 1, 5, 0, 6) if g[0][c] == 0]
        meilleur = None
        if elle:
            best = -10 ** 9
            for c in cols:
                h = [r[:] for r in g]
                self._poser(h, c, 2)
                s, _ = self._minimax(h, prof - 1, a, b, False)
                if s > best:
                    best, meilleur = s, c
                a = max(a, s)
                if a >= b:
                    break
        else:
            best = 10 ** 9
            for c in cols:
                h = [r[:] for r in g]
                self._poser(h, c, 1)
                s, _ = self._minimax(h, prof - 1, a, b, True)
                if s < best:
                    best, meilleur = s, c
                b = min(b, s)
                if a >= b:
                    break
        return best, meilleur

    def _elle(self):
        if self.fini:
            return
        libres = [c for c in range(7) if self.grille[0][c] == 0]
        if random.random() < self.niveau:
            _s, col = self._minimax([r[:] for r in self.grille], 4, -10 ** 9, 10 ** 9, True)
        else:
            col = random.choice(libres)
        if col is None:
            col = random.choice(libres)
        self._poser(self.grille, col, 2)
        self.son_tour = False
        self.plateau.update()
        self._verif()

    def _verif(self):
        v, cases = self._gagnant(self.grille)
        if not v:
            return False
        self.fini = True
        self.ligne = cases
        if v == 1:
            self.niveau = min(0.95, self.niveau + 0.08)
            self._fin("toi")
        elif v == 2:
            self.niveau = max(0.35, self.niveau - 0.1)
            self._fin("elle")
        else:
            self._fin("nul")
        self.plateau.update()
        return True


# ------------------------------------------------------------------ pendu
MOTS = {
    "fr": ["chocolat", "papillon", "montagne", "bibliotheque", "ordinateur", "girafe", "fromage", "voyage", "musique",
           "jardin", "dragon", "etoile", "nuage", "pirate", "cerise", "vacances", "tortue", "chateau", "fusee",
           "crayon", "licorne", "pingouin", "boulangerie", "arcenciel", "telephone", "piscine", "citrouille", "cactus",
           "aventure", "lumiere"],
    "en": ["chocolate", "butterfly", "mountain", "library", "computer", "giraffe", "cheese", "journey", "music",
           "garden", "dragon", "star", "cloud", "pirate", "cherry", "holiday", "turtle", "castle", "rocket", "pencil",
           "unicorn", "penguin", "bakery", "rainbow", "telephone", "pumpkin", "cactus", "adventure", "light",
           "window"],
    "es": ["chocolate", "mariposa", "montana", "biblioteca", "ordenador", "jirafa", "queso", "viaje", "musica",
           "jardin", "dragon", "estrella", "nube", "pirata", "cereza", "vacaciones", "tortuga", "castillo", "cohete",
           "lapiz", "unicornio", "pinguino", "panaderia", "arcoiris", "telefono", "calabaza", "aventura", "ventana"],
    "ru": ["шоколад", "бабочка", "гора", "библиотека", "компьютер", "жираф", "сыр", "путешествие", "музыка", "сад",
           "дракон", "звезда", "облако", "пират", "вишня", "каникулы", "черепаха", "замок", "ракета", "карандаш",
           "единорог", "пингвин", "радуга", "телефон", "тыква", "кактус", "приключение", "окно"],
}
ALPHA = {"fr": "abcdefghijklmnopqrstuvwxyz", "en": "abcdefghijklmnopqrstuvwxyz", "es": "abcdefghijklmnopqrstuvwxyz",
         "ru": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"}


class Pendu(_Fenetre):
    ESSAIS = 7

    def __init__(self, comp):
        super().__init__(comp, "Pendu")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        self.dessin = QLabel()
        self.dessin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dessin.setMinimumHeight(170)
        lay.addWidget(self.dessin)
        self.mot_l = QLabel()
        f = QFont()
        f.setPointSize(26)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
        self.mot_l.setFont(f)
        self.mot_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.mot_l)
        self.g = QGridLayout()
        lay.addLayout(self.g)
        b = QPushButton(tr("Nouveau mot"))
        b.clicked.connect(self.nouvelle)
        lay.addWidget(b)
        self.langue = lang() if lang() in MOTS else "en"
        self.vus = []
        self.boutons = {}
        for i, ch in enumerate(ALPHA[self.langue]):
            bt = QPushButton(ch.upper())
            bt.setFixedSize(38, 34)
            bt.clicked.connect(lambda _=False, c=ch: self.lettre(c))
            self.g.addWidget(bt, i // 11, i % 11)
            self.boutons[ch] = bt
        self.nouvelle()

    def keyPressEvent(self, e):
        t = e.text().lower()
        if t in self.boutons:
            self.lettre(t)

    def nouvelle(self):
        reste = [m for m in MOTS[self.langue] if m not in self.vus] or MOTS[self.langue]
        self.mot = random.choice(reste)
        self.vus.append(self.mot)
        self.trouvees, self.erreurs, self.fini = set(), 0, False
        for b in self.boutons.values():
            b.setEnabled(True)
        self._maj()
        self._info("Devine le mot, lettre par lettre !")

    def _maj(self):
        self.mot_l.setText(" ".join(c.upper() if c in self.trouvees or self.fini else "_" for c in self.mot))
        self.dessin.setPixmap(self._potence())

    def _potence(self):
        from PyQt6.QtGui import QPixmap
        pm = QPixmap(220, 170)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#8a5a3c"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(30, 160, 120, 160)
        p.drawLine(60, 160, 60, 15)
        p.drawLine(60, 15, 140, 15)
        p.drawLine(140, 15, 140, 35)
        p.setPen(QPen(QColor("#2e1624"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        e = self.erreurs
        if e > 0:
            p.drawEllipse(126, 35, 28, 28)
        if e > 1:
            p.drawLine(140, 63, 140, 110)
        if e > 2:
            p.drawLine(140, 75, 120, 95)
        if e > 3:
            p.drawLine(140, 75, 160, 95)
        if e > 4:
            p.drawLine(140, 110, 122, 140)
        if e > 5:
            p.drawLine(140, 110, 158, 140)
        if e > 6:
            p.drawLine(132, 44, 136, 48)
            p.drawLine(136, 44, 132, 48)
            p.drawLine(144, 44, 148, 48)
            p.drawLine(148, 44, 144, 48)
        p.end()
        return pm

    def lettre(self, c):
        if self.fini or not self.boutons[c].isEnabled():
            return
        self.boutons[c].setEnabled(False)
        variantes = {"e": "eéèêë", "a": "aàâ", "i": "iîï", "o": "oôö", "u": "uùûü", "c": "cç", "n": "nñ",
                     "е": "её"}.get(c, c)
        if any(ch in variantes for ch in self.mot):
            self.trouvees |= set(ch for ch in self.mot if ch in variantes)
        else:
            self.erreurs += 1
        if all(ch in self.trouvees for ch in self.mot):
            self.fini = True
            self._fin("toi")
        elif self.erreurs >= self.ESSAIS:
            self.fini = True
            self._fin("elle")
        self._maj()


# ------------------------------------------------------------------ memory
SYMBOLES = ["🐱", "🐶", "🦊", "🐼", "🐸", "🦄", "🐙", "🦋", "🌸", "🍓", "🍩", "🎈", "⭐", "🌙", "🍀", "🎵"]


class Memory(_Fenetre):
    """Retrouve les paires. Elle joue à son tour, avec une mémoire pas parfaite."""

    def __init__(self, comp):
        super().__init__(comp, "Memory")
        self.resize(520, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        self.g = QGridLayout()
        lay.addLayout(self.g, 1)
        b = QPushButton(tr("Nouvelle partie"))
        b.clicked.connect(self.nouvelle)
        lay.addWidget(b)
        self.cartes = []
        for i in range(16):
            bt = QPushButton("")
            bt.setFixedSize(96, 96)
            f = bt.font()
            f.setPointSize(30)
            bt.setFont(f)
            bt.clicked.connect(lambda _=False, k=i: self.retourner(k))
            self.g.addWidget(bt, i // 4, i % 4)
            self.cartes.append(bt)
        self.nouvelle()

    def nouvelle(self):
        sym = random.sample(SYMBOLES, 8) * 2
        random.shuffle(sym)
        self.sym = sym
        self.visibles = set()
        self.trouvees = {}
        self.choix = []
        self.son_tour = False
        self.memoire = {}
        self.points = [0, 0]
        for b in self.cartes:
            b.setText("")
            b.setStyleSheet("background:#e9d7f5;")
        self._tour()

    def _tour(self):
        self.info.setText(tr("Toi") + f" {self.points[0]}  ·  {self.comp.char.get('name', 'Viki')} {self.points[1]}"
                          + "\n" + (tr("À elle de jouer…") if self.son_tour else tr("À toi : retourne deux cartes.")))

    def _montrer(self, k):
        self.cartes[k].setText(self.sym[k])
        self.cartes[k].setStyleSheet("background:#ffffff;")
        if random.random() < 0.75:                         # elle s'en souvient… souvent
            self.memoire[k] = self.sym[k]

    def retourner(self, k, elle=False):
        if (self.son_tour and not elle) or k in self.trouvees or k in self.choix or len(self.choix) >= 2:
            return
        self.choix.append(k)
        self._montrer(k)
        if len(self.choix) == 2:
            QTimer.singleShot(800, self._comparer)

    def _comparer(self):
        a, b = self.choix
        self.choix = []
        qui = 1 if self.son_tour else 0
        if self.sym[a] == self.sym[b]:
            self.trouvees[a] = self.trouvees[b] = qui
            self.points[qui] += 1
            for k in (a, b):
                self.cartes[k].setStyleSheet("background:#fff1a8;" if qui == 0 else "background:#ffd6e4;")
                self.memoire.pop(k, None)
            if len(self.trouvees) == 16:
                p0, p1 = self.points
                return self._fin("toi" if p0 > p1 else "elle" if p1 > p0 else "nul")
        else:
            for k in (a, b):
                self.cartes[k].setText("")
                self.cartes[k].setStyleSheet("background:#e9d7f5;")
            self.son_tour = not self.son_tour
        self._tour()
        if self.son_tour:
            QTimer.singleShot(700, self._elle)

    def _elle(self):
        libres = [k for k in range(16) if k not in self.trouvees]
        if not libres:
            return
        connues = {}
        for k, s in self.memoire.items():
            if k in libres:
                connues.setdefault(s, []).append(k)
        paire = next((v for v in connues.values() if len(v) >= 2), None)
        if paire:
            a = paire[0]
        else:
            inconnues = [k for k in libres if k not in self.memoire] or libres
            a = random.choice(inconnues)
        self.retourner(a, True)

        def deuxieme():
            s = self.sym[a]
            autre = [k for k, v in self.memoire.items() if v == s and k != a and k in libres]
            reste = [k for k in libres if k != a]
            b = autre[0] if autre else random.choice([k for k in reste if k not in self.memoire] or reste)
            self.retourner(b, True)
        QTimer.singleShot(700, deuxieme)
