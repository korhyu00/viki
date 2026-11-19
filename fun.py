"""La vie du personnage et le confort : saisons à l'écran, jeux, anniversaire de Viki, duos, batterie,
accessibilité. Tout est local.
"""
import datetime
import json
import math
import os
import random
import re
import time
from pathlib import Path

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath
    from PyQt6.QtWidgets import QApplication, QWidget
except Exception:                                   # tests sans interface
    QWidget = object

STATE_FILE = None


# ================================================================ batterie
def power_state(root="/sys/class/power_supply"):
    """-> (sur_batterie, pourcentage ou None). Linux : /sys ; Windows : GetSystemPowerStatus."""
    if os.name == "nt":
        try:
            import ctypes

            class S(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte),
                            ("r", ctypes.c_byte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
            s = S()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
            pct = s.pct if 0 <= s.pct <= 100 else None
            return (s.ac == 0 and pct is not None), pct
        except Exception:
            return False, None
    on_bat, pct, ac_seen, ac_on = False, None, False, False
    try:
        for d in Path(root).iterdir():
            try:
                typ = (d / "type").read_text().strip()
            except Exception:
                typ = "Battery" if d.name.startswith("BAT") else ""
            if typ == "Mains":
                ac_seen = True
                try:
                    ac_on = ac_on or (d / "online").read_text().strip() == "1"
                except Exception:
                    pass
            elif typ == "Battery" and (d / "capacity").exists():
                try:
                    if (d / "scope").read_text().strip() == "Device":       # souris, manette : on ignore
                        continue
                except Exception:
                    pass
                try:
                    pct = int((d / "capacity").read_text().strip())
                    if (d / "status").read_text().strip() == "Discharging":
                        on_bat = True
                except Exception:
                    pass
    except Exception:
        return False, None
    if ac_seen and not ac_on and pct is not None:
        on_bat = True
    if ac_on:
        on_bat = False
    return on_bat, pct


def battery_mode_active(cfg, on_bat):
    m = cfg.get("mode_batterie", "auto")
    return m == "toujours" or (m == "auto" and on_bat)


# ================================================================ saisons et fêtes à l'écran
def season(d=None):
    d = d or datetime.date.today()
    md = (d.month, d.day)
    if (12, 10) <= md or md <= (1, 6):
        return "noel"
    if (10, 24) <= md <= (11, 1):
        return "halloween"
    if md == (2, 14):
        return "valentin"
    if (3, 20) <= md <= (6, 20):
        return "printemps"
    if (9, 22) <= md <= (12, 9):
        return "automne"
    if md <= (3, 19):
        return "hiver"
    return "ete"


SEASON_NAMES = {"noel": "❄️ Neige de Noël", "halloween": "🦇 Halloween", "valentin": "💗 Saint-Valentin",
                "printemps": "🌸 Pétales de printemps", "automne": "🍂 Feuilles d'automne", "hiver": "❄️ Neige d'hiver",
                "ete": "✨ Lucioles d'été", "confettis": "🎉 Confettis"}
# effets à l'écran : par défaut seulement pour les fêtes (Noël, Halloween, Saint-Valentin)
FETES_ECRAN = ("noel", "halloween", "valentin")

SEASON_LINES = {
    "printemps": ["Le printemps est là ! Tout refleurit.", "Ça sent les fleurs aujourd'hui, non ?"],
    "ete": ["C'est l'été ! N'oublie pas de boire de l'eau.", "Il fait beau, tu as prévu une sortie ?"],
    "automne": ["L'automne arrive, les feuilles tombent…", "Saison des plaids et du chocolat chaud !"],
    "hiver": ["Brrr, c'est l'hiver ! Couvre-toi bien.", "Il fait froid dehors, reste au chaud avec moi."],
}


def wanted_effect(cfg, d=None, on_battery=False):
    """Quel effet afficher à l'écran maintenant ? "" = aucun."""
    if on_battery or cfg.get("a11y_mouvement") or not cfg.get("effets_ecran", True):
        return ""
    s = season(d)
    mode = cfg.get("effets_quand", "fetes")           # fetes / saison / jamais
    if mode == "jamais":
        return ""
    if mode == "saison" or s in FETES_ECRAN:
        if s == "hiver" and mode != "saison":
            return ""
        return s
    return ""


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "r", "a", "va", "c", "ph")


class Overlay(QWidget):
    """Fenêtre transparente plein écran, que la souris traverse : neige, feuilles, pétales, confettis."""

    def __init__(self, kind, count=60, duration=0):
        super().__init__(None)
        self.kind = kind
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        scr = QApplication.primaryScreen()
        self.setGeometry(scr.geometry() if scr else QRectF(0, 0, 1280, 800).toRect())
        self.until = time.monotonic() + duration if duration else 0
        self.parts = [self._new(True) for _ in range(count)]
        self.t0 = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def _new(self, anywhere=False):
        p = Particle()
        w, h = max(1, self.width()), max(1, self.height())
        k = self.kind
        p.x = random.uniform(0, w)
        p.y = random.uniform(-h, h) if anywhere else random.uniform(-60, -10)
        p.ph = random.uniform(0, 6.28)
        p.a, p.va = random.uniform(0, 360), random.uniform(-3, 3)
        if k in ("noel", "hiver"):
            p.r, p.vx, p.vy = random.uniform(1.5, 4.5), random.uniform(-0.3, 0.3), random.uniform(0.6, 1.8)
            p.c = QColor(255, 255, 255, random.randint(150, 235))
        elif k == "automne":
            p.r, p.vx, p.vy = random.uniform(6, 11), random.uniform(-0.6, 0.6), random.uniform(0.9, 1.9)
            p.c = QColor(random.choice(["#d9822b", "#c0562a", "#e3b23c", "#a3472a"]))
        elif k in ("printemps", "valentin"):
            p.r, p.vx, p.vy = random.uniform(4, 8), random.uniform(-0.5, 0.5), random.uniform(0.7, 1.5)
            p.c = QColor(random.choice(["#ffc0d6", "#ffd6e5", "#ff9ec0"] if k == "printemps" else
                                       ["#ff6b9a", "#ff8fb3", "#e8457a"]))
        elif k == "halloween":
            p.r, p.vx, p.vy = random.uniform(7, 12), random.uniform(-1.2, 1.2), random.uniform(-0.4, 0.4)
            p.c = QColor(40, 24, 50, 200)
            if anywhere is False:
                p.y = random.uniform(0, h * 0.6)
                p.x = -20 if random.random() < 0.5 else w + 20
                p.vx = abs(p.vx) + 0.8 if p.x < 0 else -abs(p.vx) - 0.8
        elif k == "ete":
            p.r, p.vx, p.vy = random.uniform(2, 3.5), random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3)
            p.y = random.uniform(h * 0.4, h)
            p.c = QColor(255, 236, 140, 200)
        else:                                                                # confettis
            p.r, p.vx, p.vy = random.uniform(4, 7), random.uniform(-1.5, 1.5), random.uniform(1.5, 3.5)
            p.c = QColor(random.choice(["#ff5c8a", "#ffd23f", "#3bceac", "#5b8def", "#b45bef"]))
        return p

    def _tick(self):
        if self.until and time.monotonic() > self.until and self.kind == "confettis":
            self.timer.stop()
            self.close()
            self.deleteLater()
            return
        w, h = self.width(), self.height()
        t = time.monotonic() - self.t0
        for i, p in enumerate(self.parts):
            p.x += p.vx + math.sin(t * 1.3 + p.ph) * (0.6 if self.kind not in ("confettis", "ete") else 0.2)
            p.y += p.vy
            p.a += p.va
            if self.kind == "ete":
                p.vx += random.uniform(-0.05, 0.05)
                p.vy += random.uniform(-0.05, 0.05)
                p.vx, p.vy = max(-0.5, min(0.5, p.vx)), max(-0.5, min(0.5, p.vy))
            out = p.y > h + 30 or p.x < -40 or p.x > w + 40 or (self.kind == "ete" and p.y < h * 0.3)
            if out:
                if self.kind == "confettis" and self.until:
                    p.y = h + 100
                    p.vy = 0
                    continue
                self.parts[i] = self._new()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        t = time.monotonic() - self.t0
        for q in self.parts:
            p.save()
            p.translate(q.x, q.y)
            p.rotate(q.a)
            if self.kind == "ete":
                c = QColor(q.c)
                c.setAlpha(int(110 + 110 * (0.5 + 0.5 * math.sin(t * 3 + q.ph))))
                p.setBrush(c)
                p.drawEllipse(QPointF(0, 0), q.r, q.r)
            elif self.kind in ("noel", "hiver"):
                p.setBrush(q.c)
                p.drawEllipse(QPointF(0, 0), q.r, q.r)
            elif self.kind == "automne":
                p.setBrush(q.c)
                path = QPainterPath()
                path.moveTo(0, -q.r)
                path.quadTo(q.r * 0.9, 0, 0, q.r)
                path.quadTo(-q.r * 0.9, 0, 0, -q.r)
                p.drawPath(path)
            elif self.kind in ("printemps", "valentin"):
                p.setBrush(q.c)
                if self.kind == "valentin":
                    s = q.r / 6
                    path = QPainterPath()
                    path.moveTo(0, 2 * s)
                    path.cubicTo(-6 * s, -2 * s, -3 * s, -7 * s, 0, -3.5 * s)
                    path.cubicTo(3 * s, -7 * s, 6 * s, -2 * s, 0, 2 * s)
                    p.drawPath(path)
                else:
                    p.drawEllipse(QRectF(-q.r, -q.r * 0.55, q.r * 2, q.r * 1.1))
            elif self.kind == "halloween":
                p.setBrush(q.c)
                flap = math.sin(t * 12 + q.ph) * q.r * 0.5
                path = QPainterPath()
                path.moveTo(0, 0)
                path.quadTo(-q.r, -q.r * 0.3 - flap, -q.r * 1.6, flap * 0.4)
                path.quadTo(-q.r * 0.8, q.r * 0.1, 0, q.r * 0.35)
                path.quadTo(q.r * 0.8, q.r * 0.1, q.r * 1.6, flap * 0.4)
                path.quadTo(q.r, -q.r * 0.3 - flap, 0, 0)
                p.drawPath(path)
                p.rotate(-q.a)
            else:
                p.setBrush(q.c)
                p.drawRect(QRectF(-q.r / 2, -q.r / 4, q.r, q.r / 2))
            p.restore()
        p.end()


# ================================================================ anniversaire de Viki
def viki_birthday(cfg):
    """Date de naissance de Viki = premier lancement (« JJ/MM »)."""
    d = cfg.get("viki_naissance", "")
    return d[8:10] + "/" + d[5:7] if re.match(r"\d{4}-\d{2}-\d{2}", d or "") else ""


def viki_age(cfg, today=None):
    d = cfg.get("viki_naissance", "")
    if not re.match(r"\d{4}-\d{2}-\d{2}", d or ""):
        return 0
    today = today or datetime.date.today()
    return today.year - int(d[:4])


def is_viki_birthday(cfg, today=None):
    today = today or datetime.date.today()
    b = viki_birthday(cfg)
    return bool(b) and b == today.strftime("%d/%m") and viki_age(cfg, today) >= 1


# ================================================================ jeux
MILESTONES = (1, 5, 10, 25, 50, 100, 200, 500, 1000)


def clean_game(name):
    n = re.sub(r"[_\-]+", " ", name or "").strip()
    n = re.sub(r"(?i)\b(win64|win32|shipping|x64|launcher|game)\b", "", n).strip()
    return n[:60] or name


class Games:
    """Temps de jeu par jeu, sessions, paliers. Fichier jeux.json dans la configuration."""

    def __init__(self, path=None):
        self.path = Path(path or STATE_FILE or "jeux.json")
        try:
            self.s = json.loads(self.path.read_text())
        except Exception:
            self.s = {}
        self.s.setdefault("jeux", {})
        self.s.setdefault("semaine", {})
        self.cur, self.start, self.last = "", 0.0, 0.0
        self.dirty = False

    def tick(self, game, dt=20.0, now=None):
        """À appeler régulièrement avec le jeu en cours ("" = aucun). -> liste d'évènements."""
        now = now or time.time()
        ev = []
        game = clean_game(game) if game else ""
        if game and game != self.cur:
            if self.cur:
                ev += self._end(now)
            self.cur, self.start = game, now
            g = self.s["jeux"].setdefault(game, {"s": 0, "n": 0, "first": now, "last": 0})
            g["n"] += 1
            ev.append(("debut", game, g["s"], now - g.get("last", 0) if g.get("last") else 0))
        elif not game and self.cur:
            ev += self._end(now)
        if game:
            g = self.s["jeux"][game]
            h0 = g["s"] / 3600
            g["s"] += dt
            g["last"] = now
            wk = datetime.date.fromtimestamp(now).strftime("%G-%V")
            self.s["semaine"].setdefault(wk, {})
            self.s["semaine"][wk][game] = self.s["semaine"][wk].get(game, 0) + dt
            h1 = g["s"] / 3600
            for m in MILESTONES:
                if h0 < m <= h1:
                    g.setdefault("paliers", []).append(m)
                    self.s.setdefault("a_feter", []).append([game, m])
            sess = now - self.start
            if sess >= 2 * 3600 and not g.get("pause_dite") == int(self.start):
                g["pause_dite"] = int(self.start)
                ev.append(("longue", game, sess))
            self.dirty = True
        return ev

    def _end(self, now):
        game, sess = self.cur, now - self.start
        self.cur = ""
        fetes = [m for gname, m in self.s.pop("a_feter", []) if gname == game]
        self.dirty = True
        if sess < 5 * 60 and not fetes:
            return []
        return [("fin", game, sess, fetes)]

    def week(self, now=None):
        wk = datetime.date.fromtimestamp(now or time.time()).strftime("%G-%V")
        return sorted(self.s["semaine"].get(wk, {}).items(), key=lambda kv: -kv[1])

    def top(self, n=5):
        return sorted(((k, v["s"]) for k, v in self.s["jeux"].items()), key=lambda kv: -kv[1])[:n]

    def save(self):
        if not self.dirty:
            return
        try:
            for wk in sorted(self.s["semaine"])[:-10]:
                del self.s["semaine"][wk]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.s, ensure_ascii=False))
            os.chmod(self.path, 0o600)
            self.dirty = False
        except Exception:
            pass


def fmt_h(sec):
    sec = int(sec)
    h, m = sec // 3600, (sec % 3600) // 60
    if h and m:
        return f"{h} h {m:02d}"
    if h:
        return f"{h} h"
    return f"{max(1, m)} min"


def game_lines(ev, prenom=""):
    """Évènement de jeu -> phrase (ou "")."""
    p = f" {prenom}" if prenom else ""
    k = ev[0]
    if k == "debut":
        _k, game, total, since = ev
        if total < 60:
            return random.choice([f"Oh, {game} ! C'est nouveau ça. Amuse-toi bien{p} !",
                                  f"Première partie de {game} ? Bonne découverte !"])
        if since > 14 * 86400:
            return f"Tiens, ça faisait longtemps que tu n'avais pas joué à {game} !"
        return random.choice([f"Bonne partie de {game}{p} !", f"C'est parti pour {game} ! Je reste discrète.",
                              f"{game} ? Bon jeu, je te laisse te concentrer."])
    if k == "longue":
        return random.choice([f"Ça fait déjà {fmt_h(ev[2])} que tu joues à {ev[1]}. Petite pause, un verre d'eau ?",
                              f"{fmt_h(ev[2])} de {ev[1]} ! Pense à t'étirer un peu."])
    if k == "fin":
        _k, game, sess, fetes = ev
        if fetes:
            m = max(fetes)
            return random.choice([f"Bravo{p} ! Tu as passé le cap des {m} heure{'s' if m > 1 else ''} sur {game} ! 🎉",
                                  f"{m} heure{'s' if m > 1 else ''} de {game} au total, quel parcours !"])
        if sess > 3600:
            return random.choice([f"Belle session de {fmt_h(sess)} sur {game} ! Alors, ça s'est bien passé ?",
                                  f"Fini {game} ? {fmt_h(sess)} de jeu, tu as gagné ?"])
        return ""
    return ""


# ================================================================ duos plus naturels
DUO_SUJETS = ["ce qu'elles feraient si elles pouvaient sortir de l'écran", "leur goûter préféré", "un rêve bizarre",
              "les chats", "les vacances idéales", "un film qu'elles aimeraient voir", "la meilleure saison",
              "un super-pouvoir qu'elles voudraient", "le bruit du ventilateur du PC", "ranger le bureau",
              "les icônes du bureau qui s'entassent", "une chanson qui reste en tête", "apprendre à cuisiner"]
DUO_CONTEXTE = {"code": "le code que l'utilisateur est en train d'écrire (sans le juger)",
                "jeu": "le jeu vidéo auquel l'utilisateur vient de jouer",
                "video": "la vidéo que l'utilisateur regardait", "musique": "la musique qui passe",
                "web": "les onglets ouverts dans le navigateur, sans entrer dans le détail",
                "bureautique": "le travail de l'utilisateur et l'idée de faire une pause"}


def duo_topic(cfg, cat="", season_key="", fete="", hour=None, recent=()):
    """Choisit un sujet varié, lié au moment présent quand c'est possible."""
    hour = datetime.datetime.now().hour if hour is None else hour
    cands = list(DUO_SUJETS)
    if cat in DUO_CONTEXTE:
        cands += [DUO_CONTEXTE[cat]] * 3
    if fete:
        cands += [f"la fête du jour ({fete})"] * 3
    if season_key:
        cands += [f"la saison ({season_key})"]
    if hour >= 22 or hour < 5:
        cands += ["le fait qu'il est tard et que l'utilisateur devrait dormir"] * 2
    elif hour < 10:
        cands += ["le petit-déjeuner et la journée qui commence"] * 2
    fresh = [c for c in cands if c not in recent] or cands
    return random.choice(fresh)


# ================================================================ accessibilité
A11Y_CSS = """
QPushButton:focus, QToolButton:focus, QCheckBox:focus, QRadioButton:focus, QComboBox:focus, QLineEdit:focus,
QSpinBox:focus, QListWidget:focus, QTextEdit:focus, QPlainTextEdit:focus, QSlider:focus, QTabBar::tab:focus {
    border: 3px solid #ffbf00; }
"""


def apply_a11y(app, cfg, base_font=None):
    """Taille du texte et contour visible du focus clavier, pour toutes les fenêtres."""
    try:
        f = QFont(base_font) if base_font is not None else app.font()
        scale = float(cfg.get("a11y_texte", 1.0) or 1.0)
        size = (base_font.pointSizeF() if base_font is not None else 10.0) * scale
        if size > 0:
            f.setPointSizeF(size)
            app.setFont(f)
        css = (app.styleSheet() or "").replace(A11Y_CSS, "")
        extra = A11Y_CSS if cfg.get("a11y_focus") else ""
        try:
            import themes
            themes.EXTRA_CSS = extra
        except Exception:
            pass
        app.setStyleSheet(css + extra)
    except Exception:
        pass
