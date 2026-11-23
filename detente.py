"""🌿 Le coin détente de Viki : un petit jeu tranquille, sans stress et sans échec.
🎣 la pêche (une collection à compléter, des bouteilles à la mer), 🌱 le jardin (il pousse en vrai, même quand
Viki est fermée), ✏️ le dessin du jour (un thème par jour, une galerie). On gagne des coquillages 🐚 pour
acheter des graines. Tout reste sur le PC."""
import datetime
import math
import random
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                             QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget)

try:
    from i18n import tr
except Exception:
    def tr(t):
        return t

# ------------------------------------------------------------------ données
# (clé, nom, émoji, rareté 1-3, moment : "tout" / "jour" / "nuit", taille min-max en cm)
POISSONS = [
    ("gardon", "Gardon", "🐟", 1, "tout", (10, 25)), ("perche", "Perche", "🐟", 1, "jour", (15, 35)),
    ("carpe", "Carpe", "🐟", 1, "tout", (30, 70)), ("truite", "Truite", "🐟", 1, "jour", (20, 50)),
    ("sardine", "Sardine", "🐟", 1, "tout", (10, 20)), ("crevette", "Crevette", "🦐", 1, "tout", (3, 10)),
    ("crabe", "Crabe", "🦀", 1, "tout", (5, 20)), ("brochet", "Brochet", "🐟", 2, "jour", (40, 100)),
    ("saumon", "Saumon", "🐟", 2, "tout", (50, 90)), ("clown", "Poisson-clown", "🐠", 2, "jour", (6, 11)),
    ("lune", "Poisson-lune", "🐡", 2, "nuit", (20, 60)), ("calmar", "Calmar", "🦑", 2, "nuit", (20, 60)),
    ("tortue", "Tortue (relâchée !)", "🐢", 2, "tout", (20, 50)), ("pieuvre", "Pieuvre", "🐙", 3, "nuit", (30, 90)),
    ("koi", "Carpe koï dorée", "🎏", 3, "jour", (40, 80)), ("requin", "Petit requin", "🦈", 3, "nuit", (60, 150)),
    ("dauphin", "Dauphin (il dit bonjour !)", "🐬", 3, "jour", (150, 250)),
    ("botte", "Vieille botte", "👢", 1, "tout", (25, 30)), ("bouteille", "Bouteille à la mer", "🍾", 2, "tout", (25, 35)),
]
VALEUR = {1: 2, 2: 6, 3: 20}
MESSAGES = ["Tu fais de ton mieux, et c'est déjà beaucoup.", "Aujourd'hui, prends le temps de respirer.",
            "Quelqu'un pense à toi en ce moment.", "Les petites victoires comptent aussi.",
            "Bois un verre d'eau, ton corps te dira merci.", "Il n'y a pas de bon rythme : il y a le tien.",
            "Une pause, ce n'est pas du temps perdu.", "Tu as le droit d'être fier de toi.",
            "Demain est une nouvelle page.", "Souris : même un petit sourire change la journée."]
# (clé, nom, émoji mûr, minutes pour pousser, prix de la graine, gain à la récolte)
GRAINES = [("salade", "Salade", "🥬", 60, 2, 6), ("carotte", "Carotte", "🥕", 120, 3, 9),
           ("fraise", "Fraise", "🍓", 180, 4, 13), ("tomate", "Tomate", "🍅", 240, 5, 17),
           ("tournesol", "Tournesol", "🌻", 360, 6, 24), ("citrouille", "Citrouille", "🎃", 720, 8, 40)]
PARCELLES = 6
THEMES = ["un chat qui dort", "ta boisson préférée", "un monstre gentil", "la vue de ta fenêtre", "un robot amoureux",
          "ton plat préféré", "une maison dans un arbre", "un animal avec un chapeau", "la mer", "un dragon minuscule",
          "ton jeu vidéo préféré (à ta façon)", "une plante bizarre", "le ciel ce soir", "une créature des nuages",
          "un objet de ta chambre", "un fantôme timide", "ton humeur du jour", "une fusée", "un dessert géant",
          "un paysage d'hiver", "un poisson extraordinaire", "une ville du futur", "ton animal idéal",
          "un personnage inventé", "un pique-nique", "la pluie", "une étoile filante", "un champignon magique",
          "Viki en vacances", "quelque chose qui te rend heureux"]


def _aujourdhui():
    return datetime.date.today().isoformat()


def theme_du_jour():
    return random.Random("theme" + _aujourdhui()).choice(THEMES)


def est_nuit():
    h = datetime.datetime.now().hour
    return h < 7 or h >= 20


def tirer_poisson():
    """Un poisson au hasard, selon la rareté et le moment de la journée."""
    nuit = est_nuit()
    pool = [p for p in POISSONS if p[4] == "tout" or (p[4] == "nuit") == nuit]
    poids = [{1: 60, 2: 14, 3: 3}[p[3]] for p in pool]
    p = random.choices(pool, poids)[0]
    taille = round(random.uniform(*p[5]), 1)
    return p, taille


# ------------------------------------------------------------------ la scène de pêche
class Lac(QWidget):
    """Le lac, dessiné : ciel selon l'heure, petites vagues, le bouchon qui danse et plonge quand ça mord."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.etat = "attente"            # attente, lance, mord, prise
        self.t0 = time.monotonic()
        self.prise = ""
        self.horloge = QTimer(self)
        self.horloge.setInterval(40)
        self.horloge.timeout.connect(self.update)
        self.horloge.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        t = time.monotonic() - self.t0
        nuit = est_nuit()
        g = QLinearGradient(0, 0, 0, h * 0.45)
        g.setColorAt(0, QColor("#1b2450" if nuit else "#8ecdf5"))
        g.setColorAt(1, QColor("#4a3b7a" if nuit else "#ffe0ef"))
        p.fillRect(QRectF(0, 0, w, h * 0.45), g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fff6c8" if nuit else "#ffd166"))
        p.drawEllipse(QPointF(w * 0.82, h * 0.16), 18, 18)
        if nuit:
            p.setBrush(QColor(255, 255, 255, 180))
            rnd = random.Random(3)
            for _ in range(25):
                p.drawEllipse(QPointF(rnd.random() * w, rnd.random() * h * 0.4), 1.4, 1.4)
        p.setBrush(QColor("#7cc6a4" if not nuit else "#2f5a4a"))
        colline = QPainterPath(QPointF(0, h * 0.45))
        colline.cubicTo(QPointF(w * 0.25, h * 0.32), QPointF(w * 0.5, h * 0.5), QPointF(w, h * 0.38))
        colline.lineTo(QPointF(w, h * 0.46))
        colline.lineTo(QPointF(0, h * 0.46))
        p.drawPath(colline)
        g2 = QLinearGradient(0, h * 0.45, 0, h)
        g2.setColorAt(0, QColor("#4a90e2" if not nuit else "#1f3a6e"))
        g2.setColorAt(1, QColor("#2a5fa8" if not nuit else "#10204a"))
        p.fillRect(QRectF(0, h * 0.45, w, h * 0.55), g2)
        p.setPen(QPen(QColor(255, 255, 255, 70), 2))
        for i in range(7):
            y = h * 0.52 + i * h * 0.065
            x = (t * 18 + i * 60) % (w + 80) - 40
            p.drawLine(QPointF(x, y), QPointF(x + 30, y))
        bx, by = w * 0.55, h * 0.66
        if self.etat in ("lance", "mord"):
            dy = math.sin(t * 2.5) * 3
            if self.etat == "mord":
                dy = 10 + math.sin(t * 25) * 4
            p.setPen(QPen(QColor(255, 255, 255, 140), 1))
            p.drawLine(QPointF(w * 0.08, h * 0.2), QPointF(bx, by + dy - 8))
            p.setPen(QPen(QColor("#2e1624"), 1.5))
            p.setBrush(QColor("#e0483c"))
            p.drawEllipse(QPointF(bx, by + dy - 4), 7, 7)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(bx, by + dy + 4), 7, 5)
            if self.etat == "mord":
                f = QFont()
                f.setPixelSize(34)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#ffd166"))
                p.drawText(QRectF(bx - 40, by - 80, 80, 50), Qt.AlignmentFlag.AlignCenter, "!")
                p.setPen(QPen(QColor(255, 255, 255, 160), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                r = 10 + (t * 40) % 30
                p.drawEllipse(QPointF(bx, by + 8), r * 1.6, r * 0.5)
        elif self.etat == "prise" and self.prise:
            f = QFont()
            f.setPixelSize(64)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            y = by - 40 - min(1.0, t) * 30
            p.drawText(QRectF(bx - 60, y - 40, 120, 90), Qt.AlignmentFlag.AlignCenter, self.prise)


CSS = """
QWidget#detente { background: #fbf7ef; color: #3b2a22; }
QWidget#detente QLabel { color: #3b2a22; }
QTabBar::tab { padding: 8px 16px; margin: 4px 2px; border-radius: 12px; background: #efe5d3; color: #5a4636;
               font-weight: 600; }
QTabBar::tab:selected { background: #6aa87a; color: white; }
QTabWidget::pane { border: none; }
QPushButton { background: white; border: 1px solid #e3d6bf; border-radius: 10px; padding: 8px 12px; color: #3b2a22; }
QPushButton:hover { background: #f4eddf; }
QPushButton#main { background: #6aa87a; color: white; border: none; font-weight: 700; }
QPushButton#main:hover { background: #5a9669; }
QPushButton:disabled { color: #b8aa96; }
QToolButton#parcelle { background: #c79a6b; border: 2px solid #a87e52; border-radius: 14px; color: #3b2a22; }
QToolButton#parcelle:hover { border-color: #6aa87a; }
QFrame#carte { background: white; border: 1px solid #ece2cf; border-radius: 14px; }
QListWidget { background: white; border: 1px solid #ece2cf; border-radius: 10px; }
"""


class Detente(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("detente")
        self.setStyleSheet(CSS)
        self.setWindowTitle(tr("🌿 Coin détente") + " — " + comp.char.get("name", "Viki"))
        self.resize(640, 640)
        self.d = comp.cfg.setdefault("detente", {})
        self.d.setdefault("coquillages", 10)
        self.d.setdefault("graines", {"salade": 2, "carotte": 1})
        self.d.setdefault("collection", {})
        self.d.setdefault("jardin", [None] * PARCELLES)
        self.d.setdefault("dessins", [])
        self._jour()
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        haut = QHBoxLayout()
        self.l_coq = QLabel()
        f = self.l_coq.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.l_coq.setFont(f)
        haut.addWidget(self.l_coq)
        haut.addStretch(1)
        self.l_jour = QLabel()
        self.l_jour.setStyleSheet("color:#7a6a58;")
        haut.addWidget(self.l_jour)
        root.addLayout(haut)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._onglet_peche(), tr("🎣 À la pêche"))
        self.tabs.addTab(self._onglet_jardin(), tr("🌱 Jardin"))
        self.tabs.addTab(self._onglet_dessin(), tr("✏️ Dessin du jour"))
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(30000)
        self.minuteur.timeout.connect(self._maj_jardin)
        self.minuteur.start()
        self._maj_haut()

    # ---------- commun
    def _save(self):
        try:
            self.C.save_config(self.comp.cfg)
        except Exception:
            pass

    def dire(self, t):
        try:
            self.comp.say(t)
        except Exception:
            pass

    def _jour(self):
        """Les petits objectifs du jour (sans obligation) et la série de jours."""
        j = self.d.get("jour") or {}
        if j.get("date") != _aujourdhui():
            hier = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            serie = (j.get("serie", 0) + 1) if j.get("date") == hier else 1
            self.d["jour"] = {"date": _aujourdhui(), "poissons": 0, "recoltes": 0, "dessin": False, "bonus": False,
                              "serie": serie}

    def _maj_haut(self):
        self._jour()
        j = self.d["jour"]
        self.l_coq.setText(f"🐚 {self.d['coquillages']}")
        ok = lambda b: "✅" if b else "⬜"
        self.l_jour.setText(tr("Aujourd'hui :") + f"  {ok(j['poissons'] >= 3)} 🎣 {min(3, j['poissons'])}/3   "
                            f"{ok(j['recoltes'] >= 1)} 🌱   {ok(j['dessin'])} ✏️   ·   🔥 {j.get('serie', 1)} " +
                            tr("jour(s)"))
        if j["poissons"] >= 3 and j["recoltes"] >= 1 and j["dessin"] and not j["bonus"]:
            j["bonus"] = True
            self.d["coquillages"] += 15
            self.dire("Bravo, tout est fait pour aujourd'hui ! Voilà 15 coquillages en cadeau. 🐚")
            self.l_coq.setText(f"🐚 {self.d['coquillages']}")
        self._save()

    def _gagner(self, n):
        self.d["coquillages"] = int(self.d.get("coquillages", 0)) + int(n)
        self._maj_haut()

    # ---------- pêche
    def _onglet_peche(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        self.lac = Lac()
        v.addWidget(self.lac, 1)
        self.l_peche = QLabel(tr("Clique sur « Lancer » et attends que ça morde…"))
        self.l_peche.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.l_peche.setWordWrap(True)
        v.addWidget(self.l_peche)
        self.b_peche = QPushButton(tr("🎣 Lancer la ligne"))
        self.b_peche.setObjectName("main")
        self.b_peche.setMinimumHeight(44)
        self.b_peche.clicked.connect(self._peche_clic)
        v.addWidget(self.b_peche)
        h = QHBoxLayout()
        self.l_coll = QLabel()
        h.addWidget(self.l_coll, 1)
        b = QPushButton(tr("📖 Ma collection"))
        b.clicked.connect(self._collection)
        h.addWidget(b)
        v.addLayout(h)
        self._maj_coll()
        self.attente = QTimer(self)
        self.attente.setSingleShot(True)
        self.attente.timeout.connect(self._ca_mord)
        self.trop_tard = QTimer(self)
        self.trop_tard.setSingleShot(True)
        self.trop_tard.timeout.connect(self._rate)
        return w

    def _peche_clic(self):
        e = self.lac.etat
        if e in ("attente", "prise"):
            self.lac.etat = "lance"
            self.lac.t0 = time.monotonic()
            self.l_peche.setText(tr("Patience… Clique dès que le bouchon plonge !"))
            self.b_peche.setText(tr("⚡ Ferrer !"))
            self.attente.start(random.randint(2500, 9000))
        elif e == "lance":                                 # trop tôt
            self.attente.stop()
            self.lac.etat = "attente"
            self.l_peche.setText(tr("Oups, trop tôt ! Le poisson a eu peur. Relance quand tu veux."))
            self.b_peche.setText(tr("🎣 Lancer la ligne"))
        elif e == "mord":
            self.trop_tard.stop()
            self._prise()

    def _ca_mord(self):
        self.lac.etat = "mord"
        self.lac.t0 = time.monotonic()
        self.l_peche.setText(tr("Ça mord ! Vite !"))
        self.trop_tard.start(1300)

    def _rate(self):
        self.lac.etat = "attente"
        self.l_peche.setText(tr("Il s'est échappé… Pas grave, il y en a plein d'autres !"))
        self.b_peche.setText(tr("🎣 Lancer la ligne"))

    def _prise(self):
        (cle, nom, emoji, rare, _m, _t), taille = tirer_poisson()
        col = self.d["collection"]
        e = col.setdefault(cle, {"n": 0, "max": 0})
        nouveau = e["n"] == 0
        e["n"] += 1
        e["max"] = max(e["max"], taille)
        self.d["jour"]["poissons"] += 1
        self.lac.etat = "prise"
        self.lac.prise = emoji
        self.lac.t0 = time.monotonic()
        gain = VALEUR[rare]
        txt = f"{emoji} {tr(nom)} — {str(taille).replace('.', ',')} cm   ·   +{gain} 🐚"
        if cle == "bouteille":
            txt += "\n💌 « " + tr(random.choice(MESSAGES)) + " »"
        if nouveau:
            txt += "\n✨ " + tr("Nouveau dans ta collection !")
        self.l_peche.setText(txt)
        self.b_peche.setText(tr("🎣 Relancer"))
        self._gagner(gain)
        self._maj_coll()
        if rare == 3:
            self.dire("Waouh, une prise légendaire ! Je n'en reviens pas !")
        elif nouveau and random.random() < 0.5:
            self.dire("Oh, je n'avais jamais vu celui-là !")

    def _maj_coll(self):
        n = sum(1 for p in POISSONS if self.d["collection"].get(p[0], {}).get("n"))
        self.l_coll.setText(tr("Collection :") + f" {n} / {len(POISSONS)}")

    def _collection(self):
        w = QWidget(self, Qt.WindowType.Window)
        w.setObjectName("detente")
        w.setStyleSheet(CSS)
        w.setWindowTitle(tr("📖 Ma collection"))
        w.resize(420, 520)
        v = QVBoxLayout(w)
        lst = QListWidget()
        for cle, nom, emoji, rare, moment, _t in POISSONS:
            e = self.d["collection"].get(cle)
            etoiles = "★" * rare
            if e and e.get("n"):
                txt = f"{emoji}  {tr(nom)}  {etoiles}   ×{e['n']}   ·   " + tr("record") + \
                      f" {str(e['max']).replace('.', ',')} cm"
            else:
                txt = "❔  ???  " + etoiles + ("   🌙" if moment == "nuit" else "   ☀️" if moment == "jour" else "")
            lst.addItem(QListWidgetItem(txt))
        v.addWidget(lst)
        astuce = QLabel(tr("☀️ = de jour, 🌙 = la nuit (après 20 h). Les ★★★ sont très rares !"))
        astuce.setWordWrap(True)
        v.addWidget(astuce)
        w.show()

    # ---------- jardin
    def _onglet_jardin(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        info = QLabel(tr("Plante, arrose, récolte. Ça pousse en vrai, même quand je suis fermée ! "
                         "Arrosé, ça pousse deux fois plus vite."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#7a6a58;")
        v.addWidget(info)
        g = QGridLayout()
        g.setSpacing(10)
        self.parcelles = []
        for i in range(PARCELLES):
            b = QToolButton()
            b.setObjectName("parcelle")
            b.setMinimumSize(170, 120)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            f = b.font()
            f.setPointSize(f.pointSize() + 1)
            b.setFont(f)
            b.clicked.connect(lambda _=False, k=i: self._parcelle(k))
            g.addWidget(b, i // 3, i % 3)
            self.parcelles.append(b)
        v.addLayout(g)
        v.addWidget(QLabel(tr("Mes graines (clique pour en acheter) :")))
        self.g_graines = QGridLayout()
        self.b_graines = {}
        for i, (cle, nom, emoji, mins, prix, _gain) in enumerate(GRAINES):
            b = QPushButton()
            b.setToolTip(tr(nom) + f" · {mins // 60} h · " + tr("prix") + f" {prix} 🐚")
            b.clicked.connect(lambda _=False, k=cle: self._acheter(k))
            self.g_graines.addWidget(b, i // 3, i % 3)
            self.b_graines[cle] = b
        v.addLayout(self.g_graines)
        self.graine_choisie = "salade"
        v.addStretch(1)
        self._maj_jardin()
        return w

    def _pousse(self, pl):
        """-> fraction 0..1 de la pousse d'une parcelle (arrosée : deux fois plus vite pendant 4 h)."""
        g = next((x for x in GRAINES if x[0] == pl["graine"]), GRAINES[0])
        now = time.time()
        ecoule = now - pl["t"]
        a = pl.get("arrose") or 0
        bonus = max(0.0, min(now, a + 4 * 3600) - max(pl["t"], a)) if a else 0.0
        return min(1.0, (ecoule + bonus) / (g[3] * 60.0))

    def _maj_jardin(self):
        if not hasattr(self, "parcelles"):
            return
        j = self.d["jardin"]
        while len(j) < PARCELLES:
            j.append(None)
        for i, b in enumerate(self.parcelles):
            pl = j[i]
            if not pl:
                b.setText(tr("🟫 Parcelle vide") + "\n" + tr("Clique pour planter"))
                continue
            g = next((x for x in GRAINES if x[0] == pl["graine"]), GRAINES[0])
            f = self._pousse(pl)
            if f >= 1:
                b.setText(f"{g[2]} {g[2]} {g[2]}\n" + tr(g[1]) + "\n" + tr("Prêt ! Clique pour récolter"))
            else:
                reste = int((1 - f) * g[3])
                stade = "🌱" if f < 0.5 else "🌿"
                eau = "💧" if pl.get("arrose") and time.time() - pl["arrose"] < 4 * 3600 else tr("(à arroser)")
                b.setText(f"{stade} {tr(g[1])}\n{int(f * 100)} %  ·  {reste // 60} h {reste % 60:02d}\n{eau}")
        for cle, nom, emoji, _m, prix, _g in GRAINES:
            n = int(self.d["graines"].get(cle, 0))
            b = self.b_graines[cle]
            b.setText(f"{emoji} {tr(nom)} ×{n}   (+1 : {prix} 🐚)")
            b.setStyleSheet("font-weight:700; border:2px solid #6aa87a;" if cle == self.graine_choisie else "")

    def _acheter(self, cle):
        """Un clic sur une graine : je la choisis pour planter, et j'en achète une."""
        self.graine_choisie = cle
        g = next(x for x in GRAINES if x[0] == cle)
        if self.d["coquillages"] >= g[4]:
            self.d["coquillages"] -= g[4]
            self.d["graines"][cle] = int(self.d["graines"].get(cle, 0)) + 1
        else:
            self.dire("Il te manque des coquillages : va pêcher un peu ! 🎣")
        self._save()
        self._maj_haut()
        self._maj_jardin()

    def _parcelle(self, i):
        pl = self.d["jardin"][i]
        if not pl:
            cle = self.graine_choisie
            if int(self.d["graines"].get(cle, 0)) <= 0:
                cle = next((k for k, n in self.d["graines"].items() if n > 0), None)
            if not cle:
                return self.dire("Tu n'as plus de graines : achète-en avec tes coquillages !")
            self.d["graines"][cle] -= 1
            self.d["jardin"][i] = {"graine": cle, "t": time.time(), "arrose": 0}
        elif self._pousse(pl) >= 1:
            g = next((x for x in GRAINES if x[0] == pl["graine"]), GRAINES[0])
            self.d["jardin"][i] = None
            self.d["jour"]["recoltes"] += 1
            self.d.setdefault("recoltes", {})[g[0]] = self.d.get("recoltes", {}).get(g[0], 0) + 1
            self._gagner(g[5])
            if random.random() < 0.4:
                self.dire("Miam, quelle belle récolte !")
        elif not (pl.get("arrose") and time.time() - pl["arrose"] < 4 * 3600):
            pl["arrose"] = time.time()
            if random.random() < 0.3:
                self.dire("Hop, un peu d'eau ! Ça va pousser plus vite. 💧")
        self._save()
        self._maj_jardin()
        self._maj_haut()

    # ---------- dessin du jour
    def _onglet_dessin(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        carte = QFrame()
        carte.setObjectName("carte")
        cv = QVBoxLayout(carte)
        t = QLabel(tr("Le thème d'aujourd'hui :"))
        t.setStyleSheet("color:#7a6a58;")
        cv.addWidget(t)
        self.l_theme = QLabel("✏️ " + tr(theme_du_jour()))
        f = self.l_theme.font()
        f.setPointSize(f.pointSize() + 6)
        f.setBold(True)
        self.l_theme.setFont(f)
        self.l_theme.setWordWrap(True)
        cv.addWidget(self.l_theme)
        h = QHBoxLayout()
        b = QPushButton(tr("📒 Ouvrir le carnet de dessin"))
        b.clicked.connect(self._ouvrir_carnet)
        h.addWidget(b)
        b = QPushButton(tr("✅ J'ai fini, je le montre !"))
        b.setObjectName("main")
        b.clicked.connect(self._montrer_dessin)
        h.addWidget(b)
        cv.addLayout(h)
        v.addWidget(carte)
        v.addWidget(QLabel(tr("Ma galerie des dessins du jour :")))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        box = QWidget()
        box.setObjectName("detente")
        self.galerie = QGridLayout(box)
        self.galerie.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        sc.setWidget(box)
        v.addWidget(sc, 1)
        self._maj_galerie()
        return w

    def _ouvrir_carnet(self):
        try:
            self.comp.open_dessin()
            self.dire("Le thème d'aujourd'hui : " + theme_du_jour() + ". Amuse-toi bien !")
        except Exception:
            pass

    def _montrer_dessin(self):
        carnet = getattr(self.comp, "dessin_win", None)
        if carnet is None:
            return self.dire("Ouvre d'abord le carnet de dessin et dessine le thème du jour !")
        fin = carnet.toile.image_finale()
        r = carnet._boite(fin)
        if r is None:
            return self.dire("Il n'y a rien de dessiné pour l'instant.")
        try:
            import dessin
            d = dessin.dossier_dessins() / "Dessins du jour"
        except Exception:
            d = Path.home() / "Images" / "Viki" / "Dessins du jour"
        d.mkdir(parents=True, exist_ok=True)
        chemin = d / f"{_aujourdhui()}.png"
        fin.copy(r.adjusted(-12, -12, 12, 12)).save(str(chemin))
        lst = self.d["dessins"]
        lst[:] = [x for x in lst if x.get("date") != _aujourdhui()]
        lst.append({"date": _aujourdhui(), "theme": theme_du_jour(), "chemin": str(chemin)})
        premiere = not self.d["jour"]["dessin"]
        self.d["jour"]["dessin"] = True
        if premiere:
            self._gagner(10)
        self._save()
        self._maj_galerie()
        self.dire(random.choice(["Oh, il est trop bien ! Je le range dans ta galerie. 💜",
                                 "J'adore ! Il a sa place dans la galerie.", "Bravo, ça me plaît beaucoup !"]))

    def _maj_galerie(self):
        while self.galerie.count():
            it = self.galerie.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        for i, x in enumerate(reversed(self.d.get("dessins", [])[-60:])):
            lab = QLabel()
            pm = QPixmap(x.get("chemin", ""))
            if pm.isNull():
                continue
            lab.setPixmap(pm.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation))
            lab.setToolTip(f"{x.get('date')} · {tr(x.get('theme', ''))}")
            lab.setFixedSize(150, 150)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setStyleSheet("background:white; border:1px solid #ece2cf; border-radius:10px;")
            self.galerie.addWidget(lab, i // 3, i % 3)

    def ouvrir(self, onglet=None):
        if onglet is not None:
            self.tabs.setCurrentIndex(onglet)
        self._maj_haut()
        self._maj_jardin()
        self.show()
        self.raise_()
        self.activateWindow()
