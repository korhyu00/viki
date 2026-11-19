#!/usr/bin/env python3
"""Lieux du compagnon : petits décors animés (chez elle, piscine, parc).

Tout est dessiné par le programme (aucune image externe) ; le ciel suit l'heure
réelle (jour, soir, nuit). Chaque lieu a des objets cliquables, et elle va
elle-même les utiliser de temps en temps.

Les positions sont en coordonnées relatives au décor : u (0 gauche → 1 droite),
v (0 haut → 1 bas).
"""
import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

LIEUX = {"maison": "Chez elle", "chambre": "Dans sa chambre", "cafe": "Au café",
         "parc": "Au parc", "piscine": "À la piscine", "plage": "À la plage", "neige": "À la neige"}
INTERIEUR = {"maison", "chambre", "cafe"}          # la météo se voit par la fenêtre
METEOS = {"soleil": "Soleil", "nuages": "Nuageux", "pluie": "Pluie", "orage": "Orage",
          "neige": "Neige", "brouillard": "Brouillard"}


def period(hour):
    if hour >= 21 or hour < 6:
        return "nuit"
    if hour >= 18:
        return "soir"
    return "jour"


def _sky(p, r, per, seed=1):
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    if per == "nuit":
        g.setColorAt(0, QColor("#0b1636"))
        g.setColorAt(1, QColor("#2b3c70"))
    elif per == "soir":
        g.setColorAt(0, QColor("#5b4b8a"))
        g.setColorAt(0.55, QColor("#ff9a6a"))
        g.setColorAt(1, QColor("#ffd6a0"))
    else:
        g.setColorAt(0, QColor("#7cc8ff"))
        g.setColorAt(1, QColor("#e6f6ff"))
    p.fillRect(r, g)
    if per == "nuit":
        rnd = random.Random(seed)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(r.width() * r.height() / 1400) + 6):
            x, y = r.left() + rnd.random() * r.width(), r.top() + rnd.random() * r.height() * 0.8
            a = rnd.randint(120, 255)
            p.setBrush(QColor(255, 255, 230, a))
            s = rnd.choice((1.0, 1.4, 2.0))
            p.drawEllipse(QPointF(x, y), s, s)


def _sun_moon(p, c, rad, per):
    if per == "nuit":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(250, 245, 215))
        p.drawEllipse(c, rad, rad)
        p.setBrush(QColor(255, 255, 255, 0))
        path = QPainterPath()
        path.addEllipse(c, rad, rad)
        cut = QPainterPath()
        cut.addEllipse(QPointF(c.x() + rad * 0.45, c.y() - rad * 0.2), rad, rad)
        p.setBrush(QColor(20, 30, 70))
        p.drawPath(path.intersected(cut))
    else:
        g = QRadialGradient(c, rad * 2.2)
        col = QColor("#ffd23f") if per == "jour" else QColor("#ff7b47")
        g.setColorAt(0, col)
        g.setColorAt(0.45, QColor(col.red(), col.green(), col.blue(), 120))
        g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, rad * 2.2, rad * 2.2)
        p.setBrush(col)
        p.drawEllipse(c, rad, rad)


def _cloud(p, x, y, s, alpha=230):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, alpha))
    for dx, dy, k in ((0, 0, 1.0), (0.8, -0.35, 0.8), (1.6, 0, 0.9), (0.8, 0.2, 0.9)):
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), s * k, s * k * 0.75)


def _leaf_tree(p, x, ground, h, per):
    trunk = QColor("#7a5232")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(trunk)
    p.drawRoundedRect(QRectF(x - h * 0.06, ground - h * 0.55, h * 0.12, h * 0.55), 4, 4)
    base = QColor("#3e9b4f") if per == "jour" else QColor("#3a7a52") if per == "soir" else QColor("#1f4a3a")
    for dx, dy, k in ((0, -0.72, 0.36), (-0.22, -0.6, 0.28), (0.22, -0.6, 0.28), (0, -0.92, 0.26)):
        p.setBrush(base.lighter(100 + int(dy * -12)))
        p.drawEllipse(QPointF(x + dx * h, ground + dy * h), k * h, k * h * 0.9)


class Lieu:
    def __init__(self, kind):
        self.kind = kind
        self.lamp_on = None          # None = automatique selon l'heure
        self.shade = True
        self.ball = {"u": 0.2, "y": 0.0, "vu": 0.0, "vy": 0.0}
        self.birds = True
        self.bird_fly = None
        self.ring_push = 0.0
        self.cat_purr = 0.0
        self.water_splash = 0.0
        self.crab_u, self.crab_v = 0.62, 0.0
        self.crab_run = 0.0
        self.snowman_hat = False
        self.steam_burst = 0.0
        self.weather = "soleil"
        self.flash = 0.0
        self._next_flash = 4.0
        self._bg = None
        self._bg_key = None

    # ---------------------------------------------------------------- objets
    def objects(self):
        if self.kind == "maison":
            return [("fenetre", (0.05, 0.12, 0.31, 0.52)), ("lampe", (0.86, 0.18, 0.97, 0.80)),
                    ("chat", (0.70, 0.56, 0.84, 0.70)), ("plante", (0.02, 0.60, 0.10, 0.84)),
                    ("tasse", (0.16, 0.62, 0.30, 0.78))]
        if self.kind == "chambre":
            return [("lit", (0.58, 0.52, 0.98, 0.86)), ("armoire", (0.02, 0.14, 0.2, 0.82)),
                    ("peluche", (0.62, 0.48, 0.72, 0.62)), ("reveil", (0.24, 0.6, 0.33, 0.72)),
                    ("fenetre", (0.36, 0.1, 0.56, 0.42))]
        if self.kind == "cafe":
            return [("machine", (0.02, 0.28, 0.2, 0.62)), ("gateau", (0.2, 0.5, 0.36, 0.66)),
                    ("tableau", (0.74, 0.1, 0.97, 0.42)), ("tasse", (0.74, 0.66, 0.9, 0.8)),
                    ("fenetre", (0.38, 0.08, 0.64, 0.46))]
        if self.kind == "plage":
            return [("palmier", (0.0, 0.05, 0.2, 0.7)), ("chateau", (0.72, 0.72, 0.9, 0.9)),
                    ("crabe", None), ("coquillage", (0.22, 0.86, 0.3, 0.95)),
                    ("mer", (0.0, 0.5, 1.0, 0.66))]
        if self.kind == "neige":
            return [("bonhomme", (0.76, 0.42, 0.97, 0.88)), ("sapin", (0.0, 0.05, 0.22, 0.8)),
                    ("luge", (0.24, 0.8, 0.4, 0.92)), ("flocons", (0.3, 0.05, 0.7, 0.35))]
        if self.kind == "piscine":
            return [("parasol", (0.03, 0.14, 0.27, 0.62)), ("bouee", (0.76, 0.78, 0.96, 0.96)),
                    ("soleil", (0.80, 0.03, 0.95, 0.22)), ("eau", (0.0, 0.74, 1.0, 1.0))]
        return [("arbre", (0.0, 0.08, 0.24, 0.80)), ("banc", (0.72, 0.62, 0.97, 0.84)),
                ("ballon", None), ("papillon", None), ("fleurs", (0.30, 0.86, 0.70, 1.0))]

    def object_at(self, u, v, t):
        for name, box in self.objects():
            if box is None:
                c = self.dynamic_pos(name, t)
                if c and abs(u - c[0]) < 0.05 and abs(v - c[1]) < 0.06:
                    return name
                continue
            u0, v0, u1, v1 = box
            if u0 <= u <= u1 and v0 <= v <= v1:
                return name
        return None

    def object_center(self, name, t):
        for n, box in self.objects():
            if n == name:
                if box is None:
                    return self.dynamic_pos(name, t)
                return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        return None

    def dynamic_pos(self, name, t):
        if name == "ballon":
            return (self.ball["u"], 0.93 - self.ball["y"])
        if name == "papillon":
            return (0.5 + 0.32 * math.sin(t * 0.37), 0.42 + 0.08 * math.sin(t * 1.3))
        if name == "crabe":
            return (self.crab_u, 0.86)
        return None

    def lamp(self, per):
        return self.lamp_on if self.lamp_on is not None else per != "jour"

    # ---------------------------------------------------------------- interactions
    def interact(self, name, per):
        """Renvoie les effets à jouer : phrase, réaction, particules (u, v)."""
        fx = {"say": "obj_" + name, "happy": 1.2, "parts": []}
        c = self.object_center(name, 0) or (0.5, 0.5)
        if name == "lampe":
            self.lamp_on = not self.lamp(per)
            fx["parts"] = [("etoile", 0.9, 0.3, 2)]
        elif name == "chat":
            self.cat_purr = 3.0
            fx["parts"] = [("coeur", 0.77, 0.55, 3)]
            fx["blush"] = 2.5
        elif name == "plante":
            fx["parts"] = [("goutte", 0.06, 0.6, 4)]
        elif name == "tasse":
            fx["parts"] = [("coeur", 0.23, 0.58, 1)]
        elif name == "fenetre":
            fx["react"] = "regarde"
        elif name == "eau":
            self.water_splash = 1.2
            fx["parts"] = [("goutte", 0.5, 0.78, 7)]
            fx["react"] = "epaule"
        elif name == "bouee":
            self.ring_push = 2.5
            fx["parts"] = [("goutte", 0.86, 0.84, 3)]
        elif name == "parasol":
            self.shade = not self.shade
        elif name == "soleil":
            fx["parts"] = [("etoile", 0.88, 0.12, 2)]
        elif name == "arbre":
            fx["parts"] = [("feuille", 0.12, 0.25, 6)]
            if self.birds:
                self.birds, self.bird_fly = False, 0.0
        elif name == "banc":
            fx["react"] = "assise"
        elif name == "ballon":
            self.ball["vu"] = random.choice((-1, 1)) * random.uniform(0.25, 0.45)
            self.ball["vy"] = random.uniform(0.35, 0.55)
            fx["react"] = "pieds"
        elif name == "papillon":
            fx["parts"] = [("coeur", c[0], c[1], 1)]
        elif name == "fleurs":
            fx["parts"] = [("coeur", 0.5, 0.85, 2)]
        elif name == "lit":
            fx["react"] = "assise"
            fx["yawn"] = True
        elif name == "armoire":
            fx["outfit"] = True                  # le compagnon change de tenue
            fx["parts"] = [("etoile", 0.11, 0.3, 3)]
        elif name == "peluche":
            fx["parts"] = [("coeur", 0.67, 0.5, 3)]
            fx["blush"] = 2.0
        elif name == "reveil":
            fx["say"] = "heure"
        elif name == "machine":
            self.steam_burst = 2.0
            fx["parts"] = [("etoile", 0.1, 0.3, 1)]
        elif name == "gateau":
            fx["parts"] = [("coeur", 0.28, 0.5, 2)]
        elif name == "tableau":
            fx["say"] = "obj_tableau"
        elif name == "mer":
            fx["parts"] = [("goutte", 0.5, 0.58, 6)]
            fx["react"] = "epaule"
        elif name == "chateau":
            fx["parts"] = [("etoile", 0.8, 0.72, 3)]
        elif name == "crabe":
            self.crab_run = 2.0
            fx["react"] = "epaule"
            fx["parts"] = [("exclam", self.crab_u, 0.8, 1)]
        elif name == "coquillage":
            fx["parts"] = [("note", 0.26, 0.85, 2)]
        elif name == "palmier":
            fx["parts"] = [("feuille", 0.1, 0.2, 4)]
        elif name == "bonhomme":
            self.snowman_hat = not self.snowman_hat
            fx["parts"] = [("etoile", 0.87, 0.45, 2)]
        elif name == "sapin":
            fx["parts"] = [("flocon", 0.11, 0.25, 6)]
        elif name == "luge":
            fx["react"] = "pieds"
            fx["slide"] = True
        elif name == "flocons":
            fx["parts"] = [("flocon", 0.5, 0.2, 5)]
        return fx

    def update(self, dt):
        b = self.ball
        if b["y"] > 0 or b["vy"] > 0:
            b["vy"] -= 1.6 * dt
            b["y"] = max(0.0, b["y"] + b["vy"] * dt)
            if b["y"] == 0.0 and b["vy"] < 0:
                b["vy"] = -b["vy"] * 0.45 if abs(b["vy"]) > 0.12 else 0.0
        b["u"] += b["vu"] * dt
        b["vu"] *= 0.985 if b["y"] > 0 else 0.95
        if b["u"] < 0.04 or b["u"] > 0.96:
            b["u"] = min(0.96, max(0.04, b["u"]))
            b["vu"] = -b["vu"] * 0.6
        self.ring_push = max(0.0, self.ring_push - dt)
        self.cat_purr = max(0.0, self.cat_purr - dt)
        self.water_splash = max(0.0, self.water_splash - dt)
        self.steam_burst = max(0.0, self.steam_burst - dt)
        if self.crab_run > 0:                                   # le crabe file de côté
            self.crab_run = max(0.0, self.crab_run - dt)
            self.crab_u += (0.35 if self.crab_u < 0.5 else -0.35) * dt * (1 if self.crab_run > 1 else -1)
        else:
            self.crab_u += 0.02 * math.sin(self.crab_v) * dt
            self.crab_v += dt * 0.7
        self.crab_u = min(0.95, max(0.05, self.crab_u))
        self.flash = max(0.0, self.flash - dt * 3)
        if self.weather == "orage":
            self._next_flash -= dt
            if self._next_flash <= 0:
                self.flash = 1.0
                self._next_flash = random.uniform(5, 14)
        if self.bird_fly is not None:
            self.bird_fly += dt
            if self.bird_fly > 25:                 # les oiseaux reviennent
                self.birds, self.bird_fly = True, None

    # ---------------------------------------------------------------- dessin
    def _static(self, size, per):
        key = (size.width(), size.height(), per, self.lamp(per), self.shade, self.birds)
        if self._bg_key == key:
            return self._bg
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, size.width(), size.height())
        getattr(self, "_bg_" + self.kind)(p, r, per)
        p.end()
        self._bg, self._bg_key = pm, key
        return pm

    def draw_back(self, p, r, t, hour):
        per = period(hour)
        p.drawPixmap(r.topLeft(), self._static(r.size().toSize(), per))
        getattr(self, "_anim_" + self.kind)(p, r, t, per)
        if self.kind in INTERIEUR:                     # météo visible par la fenêtre
            box = self.object_center("fenetre", t)
            if box:
                for n, b in self.objects():
                    if n == "fenetre":
                        wr = QRectF(r.left() + b[0] * r.width(), r.top() + b[1] * r.height(),
                                    (b[2] - b[0]) * r.width(), (b[3] - b[1]) * r.height())
                        p.save()
                        p.setClipRect(wr.adjusted(4, 4, -4, -4))
                        self._weather(p, wr, t, per, light=True)
                        p.restore()
        else:                                          # ciel assombri / brouillard derrière elle
            self._weather(p, r, t, per, layer="back")

    def draw_weather(self, p, r, t, hour):
        """Pluie, neige… devant tout le décor (lieux extérieurs)."""
        if self.kind not in INTERIEUR:
            self._weather(p, r, t, period(hour), layer="front")

    def _weather(self, p, r, t, per, light=False, layer="all"):
        """layer « back » : teinte et brouillard (derrière elle) ;
        « front » : pluie, neige, éclair (devant elle, sans l'assombrir)."""
        w = "neige" if (self.kind == "neige" and self.weather in ("pluie", "orage")) else self.weather
        back, front = layer in ("all", "back"), layer in ("all", "front")
        if back and w in ("nuages", "pluie", "orage", "brouillard"):
            a = {"nuages": 35, "pluie": 70, "orage": 110, "brouillard": 40}[w]
            p.fillRect(r, QColor(70, 80, 95, a))
        if back and w == "brouillard":
            for k in range(3):
                g = QLinearGradient(r.left(), 0, r.right(), 0)
                off = (t * 0.03 + k * 0.33) % 1
                g.setColorAt(0, QColor(235, 238, 242, 0))
                g.setColorAt(off, QColor(235, 238, 242, 120))
                g.setColorAt(1, QColor(235, 238, 242, 0))
                p.fillRect(QRectF(r.left(), r.top() + r.height() * (0.35 + 0.18 * k), r.width(),
                                  r.height() * 0.2), g)
        if front and w in ("pluie", "orage"):
            rnd = random.Random(3)
            p.setPen(QPen(QColor(200, 215, 240, 150), 1.2))
            n = 60 if not light else 25
            for i in range(n):
                x0 = rnd.random() * (r.width() + 60) - 30
                sp = 380 + rnd.random() * 200
                y = (rnd.random() * r.height() + t * sp) % r.height()
                x = (x0 - t * sp * 0.15) % (r.width() + 60) - 30
                p.drawLine(QPointF(r.left() + x, r.top() + y), QPointF(r.left() + x - 4, r.top() + y + 12))
        if front and w == "neige":
            rnd = random.Random(9)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 220))
            n = 70 if not light else 30
            for i in range(n):
                s = 1.2 + rnd.random() * 2.2
                sp = 25 + rnd.random() * 35
                y = (rnd.random() * r.height() + t * sp) % r.height()
                x = (rnd.random() * r.width() + 18 * math.sin(t * 0.8 + i)) % r.width()
                p.drawEllipse(QPointF(r.left() + x, r.top() + y), s, s)
        if front and w == "orage" and self.flash > 0:
            p.fillRect(r, QColor(255, 255, 255, int((150 if layer == "all" else 90) * self.flash)))

    def draw_front(self, p, r, t, hour, cut):
        per = period(hour)
        getattr(self, "_front_" + self.kind)(p, r, t, per, cut)

    # ----- chez elle
    def _bg_maison(self, p, r, per):
        W, H = r.width(), r.height()
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor("#f6e7d6"))
        g.setColorAt(1, QColor("#ead2b8"))
        p.fillRect(r, g)
        p.setPen(QPen(QColor(220, 196, 170), 1))
        for x in range(0, int(W), 26):                       # papier peint rayé
            p.drawLine(QPointF(x, 0), QPointF(x, H * 0.78))
        floor = QRectF(0, H * 0.8, W, H * 0.2)
        p.fillRect(floor, QColor("#b98a5d"))
        p.setPen(QPen(QColor("#9c7047"), 1.2))
        for i in range(1, 5):
            y = floor.top() + floor.height() * i / 5
            p.drawLine(QPointF(0, y), QPointF(W, y))
        p.fillRect(QRectF(0, H * 0.78, W, H * 0.025), QColor("#fbf3ea"))
        # fenêtre
        win = QRectF(W * 0.06, H * 0.13, W * 0.24, H * 0.37)
        p.save()
        p.setClipRect(win)
        _sky(p, win, per, 7)
        _sun_moon(p, QPointF(win.right() - win.width() * 0.28, win.top() + win.height() * 0.3),
                  win.width() * 0.09, per)
        if per != "nuit":
            _cloud(p, win.left() + win.width() * 0.15, win.top() + win.height() * 0.55, win.width() * 0.09)
        p.restore()
        p.setPen(QPen(QColor("#fffaf3"), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(win)
        p.drawLine(QPointF(win.center().x(), win.top()), QPointF(win.center().x(), win.bottom()))
        p.drawLine(QPointF(win.left(), win.center().y()), QPointF(win.right(), win.center().y()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(236, 132, 160, 220))                 # rideaux
        p.drawRoundedRect(QRectF(win.left() - W * 0.03, win.top() - 6, W * 0.04, win.height() + 14), 6, 6)
        p.drawRoundedRect(QRectF(win.right() - W * 0.01, win.top() - 6, W * 0.04, win.height() + 14), 6, 6)
        # canapé
        sofa = QRectF(W * 0.62, H * 0.56, W * 0.34, H * 0.25)
        p.setBrush(QColor("#7b8fd1"))
        p.drawRoundedRect(QRectF(sofa.left(), sofa.top(), sofa.width(), sofa.height() * 0.55), 14, 14)
        p.setBrush(QColor("#6a7dbf"))
        p.drawRoundedRect(QRectF(sofa.left() - 6, sofa.top() + sofa.height() * 0.35, sofa.width() + 12,
                                 sofa.height() * 0.5), 12, 12)
        p.setBrush(QColor("#5a3b28"))
        for x in (sofa.left() + 6, sofa.right() - 12):
            p.drawRect(QRectF(x, sofa.bottom() - sofa.height() * 0.12, 6, sofa.height() * 0.12))
        # petite table + plante
        tb = QRectF(W * 0.15, H * 0.70, W * 0.16, H * 0.1)
        p.setBrush(QColor("#8a5c3b"))
        p.drawRoundedRect(QRectF(tb.left(), tb.top(), tb.width(), 6), 3, 3)
        p.drawRect(QRectF(tb.center().x() - 3, tb.top() + 6, 6, tb.height()))
        p.setBrush(QColor("#c56a3d"))
        p.drawPolygon(QPolygonF_list([(W * 0.025, H * 0.72), (W * 0.095, H * 0.72),
                                      (W * 0.085, H * 0.82), (W * 0.035, H * 0.82)]))
        p.setBrush(QColor("#3f9a52"))
        for dx, dy, s in ((0.06, 0.66, 0.035), (0.04, 0.63, 0.028), (0.08, 0.62, 0.03), (0.06, 0.6, 0.025)):
            p.drawEllipse(QPointF(W * dx, H * dy), W * s, W * s * 1.3)
        # lampe
        lx = W * 0.915
        p.setBrush(QColor("#555"))
        p.drawRect(QRectF(lx - 2, H * 0.3, 4, H * 0.5))
        p.drawEllipse(QPointF(lx, H * 0.8), W * 0.03, 4)
        on = self.lamp(per)
        p.setBrush(QColor("#ffe7a8") if on else QColor("#e9dcc0"))
        shade = QPainterPath()
        shade.moveTo(lx - W * 0.045, H * 0.31)
        shade.lineTo(lx + W * 0.045, H * 0.31)
        shade.lineTo(lx + W * 0.03, H * 0.2)
        shade.lineTo(lx - W * 0.03, H * 0.2)
        shade.closeSubpath()
        p.drawPath(shade)
        if per != "jour":                                       # pénombre (moins forte si lampe)
            p.fillRect(r, QColor(10, 15, 45, 70 if on else 130))
        if on:
            gl = QRadialGradient(QPointF(lx, H * 0.32), W * 0.35)
            gl.setColorAt(0, QColor(255, 220, 140, 120))
            gl.setColorAt(1, QColor(255, 220, 140, 0))
            p.setBrush(gl)
            p.drawEllipse(QPointF(lx, H * 0.32), W * 0.35, W * 0.35)

    def _anim_maison(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        # chat qui dort sur le canapé (la queue bouge, il ronronne si on le caresse)
        cx, cy = W * 0.77, H * 0.63
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f1a95b"))
        p.drawEllipse(QPointF(cx, cy), W * 0.045, H * 0.03)
        p.drawEllipse(QPointF(cx - W * 0.04, cy - H * 0.012), W * 0.022, W * 0.02)
        for ex in (-0.052, -0.032):
            ear = QPainterPath()
            ear.moveTo(cx + W * ex, cy - H * 0.022)
            ear.lineTo(cx + W * (ex + 0.007), cy - H * 0.045)
            ear.lineTo(cx + W * (ex + 0.014), cy - H * 0.022)
            p.drawPath(ear)
        wag = math.sin(t * (6 if self.cat_purr else 1.5)) * 0.4
        tail = QPainterPath(QPointF(cx + W * 0.04, cy))
        tail.quadTo(QPointF(cx + W * 0.07, cy - H * 0.04 * wag), QPointF(cx + W * 0.065, cy - H * 0.04))
        p.setPen(QPen(QColor("#e0964a"), 4, cap=Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(tail)
        p.setPen(QPen(QColor("#6b4423"), 1.2))
        p.drawLine(QPointF(cx - W * 0.047, cy - H * 0.01), QPointF(cx - W * 0.04, cy - H * 0.01))
        # tasse fumante
        tx, ty = W * 0.23, H * 0.685
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fdfdfd"))
        p.drawRoundedRect(QRectF(tx - 7, ty, 14, 12), 3, 3)
        p.setPen(QPen(QColor("#fdfdfd"), 2))
        p.drawArc(QRectF(tx + 4, ty + 2, 8, 7), -90 * 16, 180 * 16)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1.5))
        for k in (-3, 2):
            sp = QPainterPath(QPointF(tx + k, ty - 2))
            ph = t * 2 + k
            sp.cubicTo(QPointF(tx + k + 4 * math.sin(ph), ty - 8), QPointF(tx + k - 4 * math.sin(ph), ty - 13),
                       QPointF(tx + k + 2 * math.sin(ph), ty - 19))
            p.drawPath(sp)
        p.restore()

    def _front_maison(self, p, r, t, per, cut):
        if not cut:
            return
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        p.setPen(Qt.PenStyle.NoPen)                         # petit meuble bas devant elle
        p.setBrush(QColor("#a7764b"))
        p.drawRoundedRect(QRectF(W * 0.3, H * 0.9, W * 0.4, H * 0.11), 6, 6)
        p.setBrush(QColor("#8c6038"))
        p.drawRect(QRectF(W * 0.3, H * 0.9, W * 0.4, 5))
        p.restore()

    # ----- piscine
    def _bg_piscine(self, p, r, per):
        W, H = r.width(), r.height()
        _sky(p, QRectF(0, 0, W, H * 0.62), per, 11)
        _sun_moon(p, QPointF(W * 0.88, H * 0.12), W * 0.035, per)
        p.setPen(Qt.PenStyle.NoPen)
        hedge = QColor("#4f9a5c") if per == "jour" else QColor("#3d6f4f") if per == "soir" else QColor("#1d3b33")
        p.setBrush(hedge)
        for i in range(12):
            p.drawEllipse(QPointF(W * i / 11, H * 0.6), W * 0.07, H * 0.08)
        p.fillRect(QRectF(0, H * 0.6, W, H * 0.16), QColor("#efe3cf"))     # plage carrelée
        p.setPen(QPen(QColor("#dccbb0"), 1))
        for i in range(0, int(W), 22):
            p.drawLine(QPointF(i, H * 0.6), QPointF(i, H * 0.76))
        # transat
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.drawLine(QPointF(W * 0.7, H * 0.72), QPointF(W * 0.83, H * 0.72))
        p.drawLine(QPointF(W * 0.83, H * 0.72), QPointF(W * 0.88, H * 0.62))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#4fb3e6"))
        p.drawRoundedRect(QRectF(W * 0.7, H * 0.69, W * 0.13, 5), 2, 2)
        # parasol
        px = W * 0.14
        p.setBrush(QColor("#ddd"))
        p.drawRect(QRectF(px - 2, H * 0.24, 4, H * 0.5))
        if self.shade:
            top = QPainterPath()
            top.moveTo(px - W * 0.13, H * 0.3)
            top.quadTo(QPointF(px, H * 0.08), QPointF(px + W * 0.13, H * 0.3))
            top.closeSubpath()
            p.setBrush(QColor("#ff6b6b"))
            p.drawPath(top)
            p.setBrush(QColor("#fff3f3"))
            stripe = QPainterPath()
            stripe.moveTo(px - W * 0.045, H * 0.3)
            stripe.quadTo(QPointF(px, H * 0.1), QPointF(px + W * 0.045, H * 0.3))
            stripe.closeSubpath()
            p.drawPath(stripe)
        else:
            p.setBrush(QColor("#ff6b6b"))
            p.drawRoundedRect(QRectF(px - 6, H * 0.12, 12, H * 0.16), 5, 5)
        if per != "jour":
            p.fillRect(r, QColor(10, 15, 50, 60 if per == "soir" else 110))

    def _anim_piscine(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        if per != "nuit":
            for k, sp in ((0, 9), (1, 14)):
                x = (t * sp + k * W * 0.55) % (W + 120) - 60
                _cloud(p, x, H * (0.12 + 0.08 * k), W * 0.035, 200)
        p.restore()

    def _front_piscine(self, p, r, t, per, cut):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        top = H * 0.76
        water = QPainterPath(QPointF(0, top))
        amp = 3 + 4 * self.water_splash
        for i in range(0, 41):
            x = W * i / 40
            water.lineTo(x, top + amp * math.sin(t * 2.2 + i * 0.6))
        water.lineTo(W, H)
        water.lineTo(0, H)
        water.closeSubpath()
        g = QLinearGradient(0, top, 0, H)
        deep = per == "nuit"
        g.setColorAt(0, QColor(80, 200, 235, 200) if not deep else QColor(40, 90, 150, 210))
        g.setColorAt(1, QColor(20, 120, 200, 230) if not deep else QColor(15, 40, 90, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(water)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))           # reflets
        for k in range(6):
            x = (k * W / 6 + t * 12) % W
            y = top + 10 + (k % 3) * (H - top) / 4
            p.drawLine(QPointF(x, y), QPointF(x + 14 + 6 * math.sin(t + k), y))
        # bouée
        bx = W * 0.86 + 6 * math.sin(t * 0.8) + 30 * math.sin(self.ring_push * 2.5) * (self.ring_push / 2.5)
        by = top + 6 + 3 * math.sin(t * 1.7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ff8fb1"))
        p.drawEllipse(QPointF(bx, by), W * 0.06, H * 0.035)
        p.setBrush(QColor(60, 170, 220, 230))
        p.drawEllipse(QPointF(bx, by), W * 0.028, H * 0.015)
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.drawArc(QRectF(bx - W * 0.06, by - H * 0.035, W * 0.12, H * 0.07), 30 * 16, 30 * 16)
        p.drawArc(QRectF(bx - W * 0.06, by - H * 0.035, W * 0.12, H * 0.07), 210 * 16, 30 * 16)
        p.restore()

    # ----- parc
    def _bg_parc(self, p, r, per):
        W, H = r.width(), r.height()
        _sky(p, QRectF(0, 0, W, H * 0.7), per, 23)
        _sun_moon(p, QPointF(W * 0.62, H * 0.12), W * 0.03, per)
        hill = QColor("#7cc576") if per == "jour" else QColor("#5b8f5f") if per == "soir" else QColor("#24463a")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hill.darker(110))
        p.drawEllipse(QPointF(W * 0.25, H * 0.75), W * 0.45, H * 0.22)
        p.setBrush(hill)
        p.drawEllipse(QPointF(W * 0.8, H * 0.78), W * 0.5, H * 0.2)
        grass = QColor("#6bbf5e") if per == "jour" else QColor("#4f8f4f") if per == "soir" else QColor("#1f3d30")
        p.fillRect(QRectF(0, H * 0.78, W, H * 0.22), grass)
        _leaf_tree(p, W * 0.1, H * 0.8, H * 0.72, per)
        _leaf_tree(p, W * 0.97, H * 0.8, H * 0.55, per)
        # banc
        p.setBrush(QColor("#8b5a33"))
        for i in range(3):
            p.drawRoundedRect(QRectF(W * 0.74, H * (0.64 + i * 0.035), W * 0.22, H * 0.022), 3, 3)
        p.setBrush(QColor("#3c3c3c"))
        for x in (0.76, 0.93):
            p.drawRect(QRectF(W * x, H * 0.72, 4, H * 0.1))
        if self.birds:                                           # oiseaux sur l'arbre
            p.setBrush(QColor("#4a4a6a"))
            for bx, by in ((0.06, 0.2), (0.14, 0.25)):
                p.drawEllipse(QPointF(W * bx, H * by), 6, 4.5)
                p.drawEllipse(QPointF(W * bx + 5, H * by - 3), 3, 3)
        if per != "jour":
            p.fillRect(r, QColor(10, 15, 50, 50 if per == "soir" else 100))

    def _anim_parc(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        if per != "nuit":
            for k, sp in ((0, 7), (1, 11)):
                x = (t * sp + k * W * 0.5) % (W + 120) - 60
                _cloud(p, x, H * (0.1 + 0.07 * k), W * 0.03, 210)
        if self.bird_fly is not None and self.bird_fly < 4:      # envol des oiseaux
            p.setPen(QPen(QColor("#3a3a55"), 2))
            for k in range(2):
                x = W * 0.1 + self.bird_fly * W * 0.22 + k * 18
                y = H * 0.22 - self.bird_fly * H * 0.12 + k * 8
                f = 5 * math.sin(t * 14 + k)
                p.drawLine(QPointF(x - 6, y - f), QPointF(x, y))
                p.drawLine(QPointF(x, y), QPointF(x + 6, y - f))
        if per == "nuit":                                        # lucioles
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(7):
                x = W * (0.15 + 0.11 * k) + 14 * math.sin(t * 0.7 + k * 2)
                y = H * (0.55 + 0.05 * math.sin(t * 0.9 + k))
                a = int(140 + 110 * math.sin(t * 3 + k * 1.7))
                gl = QRadialGradient(QPointF(x, y), 7)
                gl.setColorAt(0, QColor(220, 255, 120, max(0, a)))
                gl.setColorAt(1, QColor(220, 255, 120, 0))
                p.setBrush(gl)
                p.drawEllipse(QPointF(x, y), 7, 7)
        else:                                                    # papillon
            c = self.dynamic_pos("papillon", t)
            x, y = W * c[0], H * c[1]
            flap = abs(math.sin(t * 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ff9ad5"))
            p.drawEllipse(QPointF(x - 5 * flap, y), 6 * flap + 1, 5)
            p.drawEllipse(QPointF(x + 5 * flap, y), 6 * flap + 1, 5)
            p.setBrush(QColor("#5a3a5a"))
            p.drawEllipse(QPointF(x, y), 1.5, 4)
        p.restore()

    def _front_parc(self, p, r, t, per, cut):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        # ballon
        b = self.ball
        bx, by = W * b["u"], H * 0.93 - H * b["y"]
        rad = max(8.0, W * 0.025)
        p.setPen(QPen(QColor("#d23"), 1))
        p.setBrush(QColor("#ff5a5a"))
        p.drawEllipse(QPointF(bx, by - rad), rad, rad)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawArc(QRectF(bx - rad, by - 2 * rad, 2 * rad, 2 * rad), int(b["u"] * 4000) % 5760, 90 * 16)
        # fleurs et touffes d'herbe au premier plan
        p.setPen(Qt.PenStyle.NoPen)
        rnd = random.Random(5)
        tuft = QColor("#4fa34a") if per == "jour" else QColor("#2f6a3a")
        n = 26 if cut else 14
        for i in range(n):
            x = W * (i + rnd.random()) / n
            hgt = H * (0.05 + rnd.random() * (0.08 if cut else 0.04))
            sway = 3 * math.sin(t * 1.5 + i)
            p.setBrush(tuft)
            blade = QPainterPath(QPointF(x - 4, H))
            blade.quadTo(QPointF(x + sway, H - hgt * 0.6), QPointF(x + sway, H - hgt))
            blade.quadTo(QPointF(x + sway * 0.5, H - hgt * 0.5), QPointF(x + 4, H))
            p.drawPath(blade)
            if i % 3 == 0:
                col = rnd.choice(("#ffd84d", "#ff8fb8", "#ffffff", "#a8c8ff"))
                p.setBrush(QColor(col))
                p.drawEllipse(QPointF(x + sway, H - hgt), 4, 4)
        p.restore()


    # ----- chambre
    def _bg_chambre(self, p, r, per):
        W, H = r.width(), r.height()
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor("#e9e1f7"))
        g.setColorAt(1, QColor("#d8cdee"))
        p.fillRect(r, g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 70))                   # petits pois au mur
        for i in range(0, int(W), 34):
            for j in range(0, int(H * 0.75), 34):
                p.drawEllipse(QPointF(i + (j // 34 % 2) * 17, j + 10), 3, 3)
        p.fillRect(QRectF(0, H * 0.82, W, H * 0.18), QColor("#c9a27c"))
        p.setBrush(QColor("#f2b8c6"))                           # tapis
        p.drawEllipse(QPointF(W * 0.45, H * 0.92), W * 0.2, H * 0.05)
        win = QRectF(W * 0.37, H * 0.11, W * 0.18, H * 0.3)     # fenêtre
        p.save()
        p.setClipRect(win)
        _sky(p, win, per, 13)
        _sun_moon(p, QPointF(win.center().x() + win.width() * 0.2, win.top() + win.height() * 0.3),
                  win.width() * 0.1, per)
        p.restore()
        p.setPen(QPen(QColor("#fffaf3"), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(win)
        p.drawLine(QPointF(win.center().x(), win.top()), QPointF(win.center().x(), win.bottom()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))                           # cadres décoratifs (formes abstraites)
        for x, col in ((0.62, "#8fd3c7"), (0.73, "#f7c873"), (0.84, "#f39ab4")):
            p.setBrush(QColor("#ffffff"))
            p.drawRect(QRectF(W * x, H * 0.16, W * 0.08, H * 0.13))
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(W * (x + 0.04), H * 0.225), W * 0.022, W * 0.022)
        arm = QRectF(W * 0.03, H * 0.15, W * 0.16, H * 0.67)    # armoire
        p.setBrush(QColor("#b07a52"))
        p.drawRoundedRect(arm, 6, 6)
        p.setPen(QPen(QColor("#8d5d3b"), 2))
        p.drawLine(QPointF(arm.center().x(), arm.top() + 6), QPointF(arm.center().x(), arm.bottom() - 6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f1d18a"))
        for dx in (-6, 4):
            p.drawEllipse(QPointF(arm.center().x() + dx + 1, arm.center().y()), 2.5, 2.5)
        p.setBrush(QColor("#8d5d3b"))                           # table de nuit + réveil
        p.drawRoundedRect(QRectF(W * 0.22, H * 0.7, W * 0.12, H * 0.12), 4, 4)
        p.setBrush(QColor("#ff8a8a"))
        p.drawEllipse(QPointF(W * 0.285, H * 0.665), W * 0.025, W * 0.025)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(W * 0.285, H * 0.665), W * 0.018, W * 0.018)
        bed = QRectF(W * 0.58, H * 0.56, W * 0.4, H * 0.27)     # lit
        p.setBrush(QColor("#8d5d3b"))
        p.drawRoundedRect(QRectF(bed.right() - 10, bed.top() - H * 0.08, 10, bed.height() + H * 0.08), 4, 4)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(bed.left(), bed.top() + H * 0.05, bed.width() - 8, bed.height() * 0.5), 10, 10)
        p.setBrush(QColor("#9bb7f0"))
        p.drawRoundedRect(QRectF(bed.left(), bed.top() + H * 0.1, bed.width() * 0.7, bed.height() * 0.5), 10, 10)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(bed.right() - W * 0.12, bed.top() + H * 0.04, W * 0.1, H * 0.06), 8, 8)
        # peluche (ours générique)
        bx, by = W * 0.67, H * 0.56
        p.setBrush(QColor("#c99063"))
        p.drawEllipse(QPointF(bx, by), W * 0.025, H * 0.035)
        p.drawEllipse(QPointF(bx, by - H * 0.05), W * 0.02, W * 0.02)
        for ex in (-1, 1):
            p.drawEllipse(QPointF(bx + ex * W * 0.016, by - H * 0.07), W * 0.008, W * 0.008)
        p.setBrush(QColor("#3a2a1a"))
        p.drawEllipse(QPointF(bx - 3, by - H * 0.052), 1.4, 1.4)
        p.drawEllipse(QPointF(bx + 3, by - H * 0.052), 1.4, 1.4)
        if per != "jour":
            p.fillRect(r, QColor(20, 15, 60, 80 if per == "soir" else 140))
            gl = QRadialGradient(QPointF(W * 0.285, H * 0.66), W * 0.2)   # veilleuse
            gl.setColorAt(0, QColor(255, 200, 150, 90))
            gl.setColorAt(1, QColor(255, 200, 150, 0))
            p.setBrush(gl)
            p.drawEllipse(QPointF(W * 0.285, H * 0.66), W * 0.2, W * 0.2)

    def _anim_chambre(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        cx, cy, rad = W * 0.285, H * 0.665, W * 0.016            # aiguilles du réveil
        import datetime as _dt
        n = _dt.datetime.now()
        p.setPen(QPen(QColor("#333"), 1.5))
        for frac, ln in (((n.hour % 12 + n.minute / 60) / 12, 0.55), (n.minute / 60, 0.85)):
            a = frac * 2 * math.pi - math.pi / 2
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(a) * rad * ln, cy + math.sin(a) * rad * ln))
        p.restore()

    def _front_chambre(self, p, r, t, per, cut):
        if cut:
            self._front_maison(p, r, t, per, cut)

    # ----- café
    def _bg_cafe(self, p, r, per):
        W, H = r.width(), r.height()
        p.fillRect(r, QColor("#f0e2cf"))
        p.fillRect(QRectF(0, H * 0.55, W, H * 0.45), QColor("#6b4a35"))       # lambris
        p.setPen(QPen(QColor("#5a3c2a"), 1))
        for x in range(0, int(W), 30):
            p.drawLine(QPointF(x, H * 0.55), QPointF(x, H))
        win = QRectF(W * 0.39, H * 0.09, W * 0.24, H * 0.36)                   # vitrine
        p.save()
        p.setClipRect(win)
        _sky(p, win, per, 17)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(120, 120, 140, 160))                                 # immeubles en face
        for i, h in enumerate((0.5, 0.7, 0.4, 0.6)):
            p.drawRect(QRectF(win.left() + i * win.width() / 4, win.bottom() - win.height() * h,
                              win.width() / 4 - 3, win.height() * h))
        p.restore()
        p.setPen(QPen(QColor("#2f2f2f"), 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(win)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d9534f"))                                          # store rayé
        for i in range(8):
            p.setBrush(QColor("#d9534f") if i % 2 == 0 else QColor("#fbeee6"))
            p.drawRect(QRectF(win.left() - 8 + i * (win.width() + 16) / 8, win.top() - 16,
                              (win.width() + 16) / 8, 14))
        p.setBrush(QColor("#a87b55"))                                          # comptoir
        p.drawRect(QRectF(0, H * 0.6, W * 0.38, H * 0.06))
        p.setBrush(QColor("#7e5a3e"))
        p.drawRect(QRectF(0, H * 0.66, W * 0.38, H * 0.34))
        p.setBrush(QColor("#9aa3ad"))                                          # machine à café
        p.drawRoundedRect(QRectF(W * 0.04, H * 0.34, W * 0.13, H * 0.26), 6, 6)
        p.setBrush(QColor("#5d6670"))
        p.drawRect(QRectF(W * 0.07, H * 0.48, W * 0.07, H * 0.04))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(W * 0.09, H * 0.55, W * 0.03, H * 0.05), 2, 2)
        p.setBrush(QColor(255, 255, 255, 180))                                 # vitrine à gâteaux
        p.drawRoundedRect(QRectF(W * 0.2, H * 0.5, W * 0.16, H * 0.1), 6, 6)
        for i, col in enumerate(("#f6a6c1", "#f3d27a", "#a2d39c")):
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(W * (0.23 + i * 0.05), H * 0.57), W * 0.018, H * 0.02)
        p.setBrush(QColor("#2e3b33"))                                          # ardoise du menu
        p.drawRoundedRect(QRectF(W * 0.76, H * 0.12, W * 0.2, H * 0.28), 6, 6)
        p.setPen(QPen(QColor(240, 240, 230, 200), 1.5))
        for i in range(4):
            y = H * (0.18 + i * 0.05)
            p.drawLine(QPointF(W * 0.79, y), QPointF(W * (0.88 + 0.04 * (i % 2)), y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#4b3324"))                                          # petite table
        p.drawEllipse(QPointF(W * 0.82, H * 0.8), W * 0.1, H * 0.03)
        p.drawRect(QRectF(W * 0.815, H * 0.8, W * 0.01, H * 0.2))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(W * 0.8, H * 0.74, W * 0.03, H * 0.05), 2, 2)
        if per != "jour":
            p.fillRect(r, QColor(20, 15, 40, 60 if per == "soir" else 100))
            for x in (0.25, 0.6, 0.85):                                        # suspensions allumées
                gl = QRadialGradient(QPointF(W * x, H * 0.08), W * 0.16)
                gl.setColorAt(0, QColor(255, 210, 140, 110))
                gl.setColorAt(1, QColor(255, 210, 140, 0))
                p.setBrush(gl)
                p.drawEllipse(QPointF(W * x, H * 0.08), W * 0.16, W * 0.16)

    def _anim_cafe(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        strength = 1 + 2 * self.steam_burst
        p.setPen(QPen(QColor(255, 255, 255, 140), 1.6))
        for bx, by in ((W * 0.105, H * 0.54), (W * 0.815, H * 0.73)):
            for k in (-3, 3):
                sp = QPainterPath(QPointF(bx + k, by))
                ph = t * 2 + k
                sp.cubicTo(QPointF(bx + k + 4 * math.sin(ph), by - 8 * strength),
                           QPointF(bx + k - 4 * math.sin(ph), by - 13 * strength),
                           QPointF(bx + k + 2 * math.sin(ph), by - 19 * strength))
                p.drawPath(sp)
        p.restore()

    def _front_cafe(self, p, r, t, per, cut):
        if cut:
            W, H = r.width(), r.height()
            p.save()
            p.translate(r.topLeft())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#8a6244"))
            p.drawRoundedRect(QRectF(W * 0.3, H * 0.9, W * 0.4, H * 0.12), 8, 8)
            p.restore()

    # ----- plage
    def _bg_plage(self, p, r, per):
        W, H = r.width(), r.height()
        _sky(p, QRectF(0, 0, W, H * 0.55), per, 19)
        _sun_moon(p, QPointF(W * 0.55, H * 0.15), W * 0.035, per)
        sea = QLinearGradient(0, H * 0.5, 0, H * 0.68)
        sea.setColorAt(0, QColor("#2f8fd1") if per != "nuit" else QColor("#13305a"))
        sea.setColorAt(1, QColor("#5cc6e8") if per != "nuit" else QColor("#24507e"))
        p.fillRect(QRectF(0, H * 0.5, W, H * 0.18), sea)
        sand = QColor("#f2d8a2") if per == "jour" else QColor("#d9b98a") if per == "soir" else QColor("#8c7a63")
        p.fillRect(QRectF(0, H * 0.66, W, H * 0.34), sand)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#8b5e34"))                                          # palmier
        trunk = QPainterPath(QPointF(W * 0.08, H * 0.86))
        trunk.cubicTo(QPointF(W * 0.06, H * 0.6), QPointF(W * 0.12, H * 0.35), QPointF(W * 0.11, H * 0.2))
        p.setPen(QPen(QColor("#8b5e34"), 10, cap=Qt.PenCapStyle.RoundCap))
        p.drawPath(trunk)
        p.setPen(Qt.PenStyle.NoPen)
        leaf = QColor("#3e9b4f") if per != "nuit" else QColor("#1f4a3a")
        p.setBrush(leaf)
        for ang in (-150, -110, -60, -20, 20):
            path = QPainterPath(QPointF(W * 0.11, H * 0.2))
            a = math.radians(ang)
            ex, ey = W * 0.11 + math.cos(a) * W * 0.12, H * 0.2 + math.sin(a) * H * 0.08 + H * 0.06
            path.quadTo(QPointF((W * 0.11 + ex) / 2, H * 0.12), QPointF(ex, ey))
            path.quadTo(QPointF((W * 0.11 + ex) / 2, H * 0.2), QPointF(W * 0.11, H * 0.2))
            p.drawPath(path)
        p.setBrush(QColor("#d9a95f"))                                          # château de sable
        p.drawRect(QRectF(W * 0.74, H * 0.8, W * 0.15, H * 0.08))
        for i in range(3):
            p.drawRect(QRectF(W * (0.745 + i * 0.05), H * 0.75, W * 0.04, H * 0.06))
        p.setBrush(QColor("#ff6b6b"))
        p.drawPolygon(QPolygonF_list([(W * 0.815, H * 0.67), (W * 0.815, H * 0.71), (W * 0.84, H * 0.69)]))
        p.setBrush(QColor("#ffd9e6"))                                          # coquillage
        p.drawEllipse(QPointF(W * 0.26, H * 0.9), W * 0.02, H * 0.018)
        if per != "jour":
            p.fillRect(r, QColor(10, 15, 50, 50 if per == "soir" else 100))

    def _anim_plage(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        if per != "nuit":
            _cloud(p, (t * 8) % (W + 120) - 60, H * 0.12, W * 0.035, 210)
        p.setPen(QPen(QColor(255, 255, 255, 170), 2))                          # vagues
        for k in range(3):
            y = H * (0.6 + 0.025 * k) + 2 * math.sin(t * 1.5 + k)
            path = QPainterPath(QPointF(0, y))
            for i in range(1, 21):
                x = W * i / 20
                path.lineTo(x, y + 2.5 * math.sin(t * 2 + i * 0.9 + k))
            p.drawPath(path)
        foam = H * 0.66 + 4 * math.sin(t * 0.8)                                # écume sur le sable
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawRect(QRectF(0, foam, W, 3))
        p.restore()

    def _front_plage(self, p, r, t, per, cut):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        cx, cy = W * self.crab_u, H * 0.88                                     # crabe
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e8553b"))
        p.drawEllipse(QPointF(cx, cy), W * 0.022, H * 0.016)
        p.setPen(QPen(QColor("#e8553b"), 2))
        leg = math.sin(t * (18 if self.crab_run else 5)) * 2
        for s in (-1, 1):
            for k in range(3):
                p.drawLine(QPointF(cx + s * W * 0.015, cy + k * 2), QPointF(cx + s * W * 0.03, cy + 4 + k * 2 + leg * s))
            p.drawEllipse(QPointF(cx + s * W * 0.03, cy - H * 0.022), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#111"))
        p.drawEllipse(QPointF(cx - 3, cy - H * 0.018), 1.5, 1.5)
        p.drawEllipse(QPointF(cx + 3, cy - H * 0.018), 1.5, 1.5)
        if cut:                                                                # dune devant elle
            sand = QColor("#ead09a") if per == "jour" else QColor("#c9ab7f") if per == "soir" else QColor("#7d6c57")
            p.setBrush(sand)
            p.drawEllipse(QPointF(W * 0.5, H * 1.02), W * 0.3, H * 0.09)
        p.restore()

    # ----- neige
    def _bg_neige(self, p, r, per):
        W, H = r.width(), r.height()
        g = QLinearGradient(0, 0, 0, H * 0.7)
        if per == "nuit":
            g.setColorAt(0, QColor("#0e1b3a"))
            g.setColorAt(1, QColor("#3a4d7a"))
        else:
            g.setColorAt(0, QColor("#b9cfe6"))
            g.setColorAt(1, QColor("#eef3f8"))
        p.fillRect(QRectF(0, 0, W, H * 0.7), g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d7e3ef") if per != "nuit" else QColor("#6b7da0"))   # montagnes
        p.drawPolygon(QPolygonF_list([(0, H * 0.62), (W * 0.25, H * 0.25), (W * 0.5, H * 0.62)]))
        p.drawPolygon(QPolygonF_list([(W * 0.35, H * 0.62), (W * 0.65, H * 0.18), (W, H * 0.62)]))
        p.setBrush(QColor("#ffffff") if per != "nuit" else QColor("#b8c4dc"))
        p.drawPolygon(QPolygonF_list([(W * 0.2, H * 0.31), (W * 0.25, H * 0.25), (W * 0.3, H * 0.31)]))
        p.drawPolygon(QPolygonF_list([(W * 0.59, H * 0.26), (W * 0.65, H * 0.18), (W * 0.71, H * 0.26)]))
        snow = QColor("#fbfdff") if per != "nuit" else QColor("#c9d3e6")
        p.setBrush(snow)
        p.drawRect(QRectF(0, H * 0.6, W, H * 0.4))
        p.drawEllipse(QPointF(W * 0.3, H * 0.62), W * 0.4, H * 0.07)
        for x, hh in ((0.1, 0.62), (0.2, 0.4)):                                # sapins
            tx = W * x
            green = QColor("#2f6b4a") if per != "nuit" else QColor("#1b3b31")
            for k in range(3):
                p.setBrush(green)
                y0 = H * (0.82 - k * 0.14 * hh / 0.62)
                wdt = W * (0.1 - k * 0.025) * hh / 0.62
                p.drawPolygon(QPolygonF_list([(tx - wdt, y0), (tx, y0 - H * 0.2 * hh / 0.62), (tx + wdt, y0)]))
                p.setBrush(snow)
                p.drawPolygon(QPolygonF_list([(tx - wdt * 0.35, y0 - H * 0.13 * hh / 0.62),
                                              (tx, y0 - H * 0.2 * hh / 0.62),
                                              (tx + wdt * 0.35, y0 - H * 0.13 * hh / 0.62)]))
        p.setBrush(QColor("#c0392b"))                                          # luge
        p.drawRoundedRect(QRectF(W * 0.25, H * 0.84, W * 0.14, H * 0.03), 4, 4)
        p.setPen(QPen(QColor("#555"), 2))
        p.drawLine(QPointF(W * 0.25, H * 0.885), QPointF(W * 0.4, H * 0.885))
        if per == "soir":
            p.fillRect(r, QColor(60, 30, 80, 50))

    def _anim_neige(self, p, r, t, per):
        W, H = r.width(), r.height()
        p.save()
        p.translate(r.topLeft())
        bx, base = W * 0.865, H * 0.86                                          # bonhomme de neige
        p.setPen(Qt.PenStyle.NoPen)
        white = QColor("#ffffff") if per != "nuit" else QColor("#d5ddee")
        p.setPen(QPen(QColor(150, 170, 200, 160), 1.5))           # contour bleuté : visible sur la neige
        p.setBrush(white)
        p.drawEllipse(QPointF(bx, base - H * 0.07), W * 0.06, H * 0.075)
        p.drawEllipse(QPointF(bx, base - H * 0.19), W * 0.045, H * 0.058)
        p.drawEllipse(QPointF(bx, base - H * 0.29), W * 0.033, H * 0.045)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#222"))
        for dy in (-0.17, -0.21):
            p.drawEllipse(QPointF(bx, base + H * dy), 2.2, 2.2)
        p.drawEllipse(QPointF(bx - 5, base - H * 0.3), 1.8, 1.8)
        p.drawEllipse(QPointF(bx + 5, base - H * 0.3), 1.8, 1.8)
        p.setBrush(QColor("#ff8c2a"))
        p.drawPolygon(QPolygonF_list([(bx, base - H * 0.285), (bx + W * 0.03, base - H * 0.278),
                                      (bx, base - H * 0.27)]))
        p.setPen(QPen(QColor("#d64545"), 4))                                   # écharpe qui flotte
        p.drawLine(QPointF(bx - W * 0.03, base - H * 0.245), QPointF(bx + W * 0.03, base - H * 0.245))
        p.drawLine(QPointF(bx + W * 0.025, base - H * 0.245),
                   QPointF(bx + W * 0.045, base - H * 0.2 + 3 * math.sin(t * 2)))
        if self.snowman_hat:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2a2a2a"))
            p.drawRect(QRectF(bx - W * 0.03, base - H * 0.345, W * 0.06, 4))
            p.drawRect(QRectF(bx - W * 0.018, base - H * 0.4, W * 0.036, H * 0.055))
        p.restore()

    def _front_neige(self, p, r, t, per, cut):
        if cut:
            W, H = r.width(), r.height()
            p.save()
            p.translate(r.topLeft())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffffff") if per != "nuit" else QColor("#c9d3e6"))
            p.drawEllipse(QPointF(W * 0.5, H * 1.03), W * 0.32, H * 0.1)
            p.restore()


def QPolygonF_list(points):
    from PyQt6.QtGui import QPolygonF
    return QPolygonF([QPointF(x, y) for x, y in points])
