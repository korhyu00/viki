"""La forme au quotidien : routines du matin et du soir, pauses santé (eau, yeux, étirements),
planning de la semaine et séances de muscu à la maison (sans matériel). Tout reste sur ton PC."""
import datetime
import random
import re
import time
import unicodedata

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QCursor
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout, QLineEdit,
                             QComboBox, QCheckBox, QScrollArea, QApplication, QSizePolicy)

from actu_fenetre import CSS, Deplacable, tr

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
COULEURS = ["#0a84ff", "#ff9f0a", "#bf5af2", "#30d158", "#ff375f", "#64d2ff", "#ffd60a", "#ac8e68"]

CSS_FORME = CSS + """
QLabel#gros { font-size: 30px; font-weight: 700; }
QLabel#exo { font-size: 22px; font-weight: 700; }
QLabel#desc { font-size: 13px; color: #c9c4d4; }
QLabel#petit { font-size: 11px; color: #9b96a8; }
QLabel#serie { font-size: 12px; color: #ffb340; font-weight: 600; }
QFrame#ligneR { background: #26232d; border: 1px solid #3a3644; border-radius: 10px; }
QFrame#ligneR[fait="true"] { border-color: #30d158; }
QCheckBox { color: #ece9f2; font-size: 13px; spacing: 10px; }
QCheckBox::indicator { width: 20px; height: 20px; border-radius: 10px; border: 2px solid #6f6a80; background: #1d1b22; }
QCheckBox::indicator:checked { background: #30d158; border-color: #30d158; }
QLineEdit, QComboBox { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 8px; padding: 5px 8px; }
QPushButton#gros { background: #7F77DD; color: white; border: none; border-radius: 12px; padding: 10px 18px;
                   font-size: 15px; font-weight: 600; }
QPushButton#gros:hover { background: #8f88e6; }
QPushButton#jour { background: #26232d; border: 1px solid #3a3644; border-radius: 10px; color: #ece9f2;
                   text-align: left; padding: 6px; }
QFrame#col { background: #26232d; border: 1px solid #3a3644; border-radius: 10px; }
QFrame#col[auj="true"] { border-color: #7F77DD; }
QLabel#chip { color: white; border-radius: 6px; padding: 2px 6px; font-size: 11px; }
"""


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def _vider(lay):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif it.layout():
            _vider(it.layout())


class _Fenetre(Deplacable, QWidget):
    """Base : petite fenêtre au style de Viki, près d'elle, qu'on déplace et agrandit."""

    def __init__(self, comp, titre, largeur=420, hauteur=520):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.comp = comp
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(CSS_FORME)
        self.resize(largeur, hauteur)
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        self.lay = QVBoxLayout(cadre)
        self.lay.setContentsMargins(16, 12, 12, 14)
        self.lay.setSpacing(8)
        top = QHBoxLayout()
        self.titre = QLabel(titre)
        self.titre.setObjectName("titre")
        top.addWidget(self.titre)
        top.addStretch()
        self.extra_top = QHBoxLayout()
        top.addLayout(self.extra_top)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.clicked.connect(self.fermer)
        top.addWidget(x)
        self.lay.addLayout(top)

    def fermer(self):
        self.hide()

    def montrer(self):
        self.remplir()
        if not self.isVisible():
            try:
                from aujourdhui import _pres_de_viki
                p = _pres_de_viki(self.comp, self.width(), self.height())
                if p is not None:
                    self.move(p)
            except Exception:
                pass
        self.show()
        self.raise_()

    def remplir(self):
        pass


# ================================================================== 1. routines
ROUTINES_DEFAUT = {
    "matin": {"heure": "08:00", "items": ["Boire un grand verre d'eau", "Prendre mes médicaments", "5 minutes d'étirements",
                                          "Ouvrir la fenêtre, un peu d'air frais", "Préparer mon sac"]},
    "soir": {"heure": "22:00", "items": ["Préparer mes affaires pour demain", "Ranger mon bureau",
                                         "Lâcher les écrans 30 minutes avant de dormir", "Me brosser les dents"]},
}


def routines(cfg):
    r = cfg.get("routines")
    if not isinstance(r, dict):
        r = cfg["routines"] = {k: dict(v, items=list(v["items"])) for k, v in ROUTINES_DEFAUT.items()}
    return r


def fait_du_jour(cfg, quand, jour=None):
    jour = jour or datetime.date.today().isoformat()
    return set((cfg.get("routines_fait") or {}).get(jour, {}).get(quand, []))


def serie(cfg, quand):
    """Nombre de jours de suite où la routine a été faite (au moins aux 3/4)."""
    n, d = 0, datetime.date.today()
    items = len(routines(cfg)[quand]["items"]) or 1
    fait = cfg.get("routines_fait") or {}
    if len(fait.get(d.isoformat(), {}).get(quand, [])) < items * 0.75:
        d -= datetime.timedelta(days=1)                       # aujourd'hui pas encore fini : on compte jusqu'à hier
    while len(fait.get(d.isoformat(), {}).get(quand, [])) >= items * 0.75:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


class RoutineWin(_Fenetre):
    def __init__(self, comp):
        super().__init__(comp, "🌅 " + tr("Ma routine"), 400, 500)
        self.quand = "matin"
        self.edition = False
        seg = QHBoxLayout()
        self.b = {}
        for k, lab in (("matin", "🌅 " + tr("Matin")), ("soir", "🌙 " + tr("Soir"))):
            b = QPushButton(lab)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=k: self.voir(k))
            seg.addWidget(b)
            self.b[k] = b
        seg.addStretch()
        self.l_serie = QLabel("")
        self.l_serie.setObjectName("serie")
        seg.addWidget(self.l_serie)
        self.lay.addLayout(seg)
        self.box = QVBoxLayout()
        self.box.setSpacing(6)
        self.lay.addLayout(self.box)
        self.lay.addStretch()
        bas = QHBoxLayout()
        self.l_heure = QLabel("")
        self.l_heure.setObjectName("petit")
        bas.addWidget(self.l_heure)
        bas.addStretch()
        self.b_edit = QPushButton("✏️ " + tr("Modifier"))
        self.b_edit.setObjectName("btn")
        self.b_edit.clicked.connect(self._basculer_edition)
        bas.addWidget(self.b_edit)
        self.lay.addLayout(bas)

    def voir(self, quand):
        self.quand = quand
        self.remplir()

    def _basculer_edition(self):
        self.edition = not self.edition
        self.remplir()

    def remplir(self):
        cfg = self.comp.cfg
        r = routines(cfg)[self.quand]
        for k, b in self.b.items():
            b.setChecked(k == self.quand)
        _vider(self.box)
        fait = fait_du_jour(cfg, self.quand)
        for i, txt in enumerate(r["items"]):
            f = QFrame()
            f.setObjectName("ligneR")
            f.setProperty("fait", i in fait)
            h = QHBoxLayout(f)
            h.setContentsMargins(10, 6, 8, 6)
            if self.edition:
                e = QLineEdit(txt)
                e.editingFinished.connect(lambda e=e, i=i: self._renommer(i, e.text()))
                h.addWidget(e, 1)
                d = QPushButton("✕")
                d.setObjectName("x")
                d.clicked.connect(lambda _c=False, i=i: self._suppr(i))
                h.addWidget(d)
            else:
                cb = QCheckBox(txt)
                cb.setChecked(i in fait)
                cb.toggled.connect(lambda v, i=i: self._cocher(i, v))
                h.addWidget(cb, 1)
            self.box.addWidget(f)
        if self.edition:
            h = QHBoxLayout()
            e = QLineEdit()
            e.setPlaceholderText(tr("Ajouter une étape…"))
            e.returnPressed.connect(lambda e=e: self._ajouter(e.text()))
            h.addWidget(e, 1)
            b = QPushButton("+")
            b.setObjectName("btn")
            b.clicked.connect(lambda _c=False, e=e: self._ajouter(e.text()))
            h.addWidget(b)
            self.box.addLayout(h)
            h2 = QHBoxLayout()
            h2.addWidget(QLabel(tr("Elle te la propose à :")))
            eh = QLineEdit(r.get("heure", ""))
            eh.setPlaceholderText("08:00")
            eh.setFixedWidth(70)
            eh.editingFinished.connect(lambda eh=eh: self._heure(eh.text()))
            h2.addWidget(eh)
            h2.addStretch()
            self.box.addLayout(h2)
        n = serie(cfg, self.quand)
        self.l_serie.setText(f"🔥 {n} " + (tr("jours") if n > 1 else tr("jour")) if n else "")
        self.l_heure.setText(tr(f"Je te la propose vers {r.get('heure', '')}") if r.get("heure") else "")
        self.b_edit.setText("✔ " + tr("Terminé") if self.edition else "✏️ " + tr("Modifier"))

    def _cocher(self, i, v):
        cfg = self.comp.cfg
        jour = datetime.date.today().isoformat()
        f = cfg.setdefault("routines_fait", {}).setdefault(jour, {}).setdefault(self.quand, [])
        if v and i not in f:
            f.append(i)
        if not v and i in f:
            f.remove(i)
        for k in list(cfg["routines_fait"])[:-40]:          # on garde ~40 jours
            cfg["routines_fait"].pop(k, None)
        self.comp.save_cfg()
        tot = len(routines(cfg)[self.quand]["items"])
        if v and len(f) == tot:
            n = serie(cfg, self.quand)
            self.comp.happy_until = time.monotonic() + 2
            self.comp._spawn("etoile", 5)
            self.comp.say(random.choice(["Bravo, routine terminée ! ✨", "Tout est coché, je suis fière de toi !",
                                         "Et voilà, c'est fait ! Belle journée qui commence."
                                         if self.quand == "matin" else "Tout est prêt, tu peux aller dormir sereinement."])
                          + (f" Ça fait {n} jours de suite 🔥" if n >= 2 else ""))
        self.remplir()

    def _renommer(self, i, txt):
        r = routines(self.comp.cfg)[self.quand]
        if txt.strip() and i < len(r["items"]):
            r["items"][i] = txt.strip()
            self.comp.save_cfg()

    def _suppr(self, i):
        r = routines(self.comp.cfg)[self.quand]
        if i < len(r["items"]):
            r["items"].pop(i)
            self.comp.save_cfg()
        self.remplir()

    def _ajouter(self, txt):
        if txt.strip():
            routines(self.comp.cfg)[self.quand]["items"].append(txt.strip()[:80])
            self.comp.save_cfg()
        self.remplir()

    def _heure(self, txt):
        if re.fullmatch(r"\d{1,2}[:h]\d{2}", txt.strip()):
            h, m = re.split(r"[:h]", txt.strip())
            routines(self.comp.cfg)[self.quand]["heure"] = f"{int(h):02d}:{int(m):02d}"
            self.comp.save_cfg()


# ================================================================== 2. pauses santé
ETIREMENTS = [("Le cou", "Penche doucement la tête à droite… puis à gauche."),
              ("Les épaules", "Fais des grands cercles avec les épaules, vers l'arrière."),
              ("Les bras", "Tends les bras vers le plafond et grandis-toi !"),
              ("Le dos", "Tourne doucement le buste à droite… puis à gauche."),
              ("Les poignets", "Fais tourner les poignets et écarte bien les doigts.")]


def eau_du_jour(cfg):
    return int((cfg.get("sante_eau") or {}).get(datetime.date.today().isoformat(), 0))


def boire(cfg, n=1):
    d = cfg.setdefault("sante_eau", {})
    j = datetime.date.today().isoformat()
    d[j] = max(0, int(d.get(j, 0)) + n)
    for k in list(d)[:-30]:
        d.pop(k, None)
    return d[j]


class Anneau(QWidget):
    def __init__(self, taille=110):
        super().__init__()
        self.setFixedSize(taille, taille)
        self.v, self.txt, self.sous, self.col = 0.0, "", "", QColor("#64d2ff")

    @staticmethod
    def _c(hexc):
        """Couleur suivant le thème de Viki (comme les feuilles de style)."""
        try:
            import themes
            return QColor(themes.color(hexc))
        except Exception:
            return QColor(hexc)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(8, 8, self.width() - 16, self.height() - 16)
        fond = self._c("#3a3644")
        p.setPen(QPen(fond, 9))
        p.drawEllipse(r)
        pen = QPen(self.col, 9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, -int(360 * 16 * max(0.0, min(1.0, self.v))))
        p.setPen(self._c("#ece9f2"))
        f = QFont()
        f.setPixelSize(int(self.height() * 0.22))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, self.width(), self.height() * 0.92), Qt.AlignmentFlag.AlignCenter, self.txt)
        if self.sous:
            f.setPixelSize(int(self.height() * 0.1))
            f.setBold(False)
            p.setFont(f)
            p.setPen(self._c("#9b96a8"))
            p.drawText(QRectF(0, self.height() * 0.58, self.width(), self.height() * 0.2),
                       Qt.AlignmentFlag.AlignCenter, self.sous)
        p.end()


class SanteWin(_Fenetre):
    def __init__(self, comp):
        super().__init__(comp, "💧 " + tr("Pauses santé"), 380, 470)
        h = QHBoxLayout()
        self.anneau = Anneau(120)
        h.addWidget(self.anneau)
        col = QVBoxLayout()
        self.l_eau = QLabel("")
        self.l_eau.setObjectName("desc")
        self.l_eau.setWordWrap(True)
        col.addWidget(self.l_eau)
        rb = QHBoxLayout()
        b = QPushButton("💧 " + tr("+1 verre"))
        b.setObjectName("btn")
        b.clicked.connect(lambda: self._boire(1))
        rb.addWidget(b)
        b2 = QPushButton("−")
        b2.setObjectName("btn")
        b2.clicked.connect(lambda: self._boire(-1))
        rb.addWidget(b2)
        rb.addStretch()
        col.addLayout(rb)
        h.addLayout(col, 1)
        self.lay.addLayout(h)
        for ico, lab, fn in (("👀", tr("Pause des yeux (20 secondes)"), lambda: comp.pause_yeux()),
                             ("🙆", tr("Étire-toi avec moi (1 minute)"), lambda: comp.etirements()),
                             ("💪", tr("Une séance de muscu à la maison"), lambda: comp.open_muscu())):
            bb = QPushButton(f"{ico}  {lab}")
            bb.setObjectName("jour")
            bb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            bb.clicked.connect(fn)
            self.lay.addWidget(bb)
        self.l_info = QLabel("")
        self.l_info.setObjectName("petit")
        self.l_info.setWordWrap(True)
        self.lay.addWidget(self.l_info)
        self.lay.addStretch()

    def _boire(self, n):
        v = boire(self.comp.cfg, n)
        self.comp.save_cfg()
        obj = int(self.comp.cfg.get("sante_eau_objectif", 8))
        if n > 0 and v == obj:
            self.comp._spawn("coeur", 4)
            self.comp.say("Objectif d'eau atteint ! Ton corps te dit merci 💧")
        self.remplir()

    def remplir(self):
        cfg = self.comp.cfg
        v, obj = eau_du_jour(cfg), int(cfg.get("sante_eau_objectif", 8))
        self.anneau.v, self.anneau.txt, self.anneau.sous = v / max(1, obj), f"{v}/{obj}", tr("verres d'eau")
        self.anneau.update()
        self.l_eau.setText(tr("Bravo, objectif atteint !") if v >= obj else
                           tr(f"Encore {obj - v} verre(s) aujourd'hui."))
        on = cfg.get("sante_rappels", True)
        self.l_info.setText((tr("Je te rappelle de boire et de reposer tes yeux, doucement (jamais en mode "
                                "concentration ou jeu).") if on else tr("Les rappels santé sont coupés.")) +
                            " " + tr("Réglages → Au quotidien."))


# ================================================================== 3. planning de la semaine
def planning(cfg):
    p = cfg.get("planning")
    if not isinstance(p, list):
        p = cfg["planning"] = []
    return p


def du_jour(cfg, d=None):
    d = d or datetime.date.today()
    out = []
    for e in planning(cfg):
        if e.get("date"):
            if e["date"] == d.isoformat():
                out.append(e)
        elif e.get("jour") == d.weekday():
            out.append(e)
    return sorted(out, key=lambda e: e.get("heure") or "99")


def lire_ajout(texte):
    """« ajoute sport jeudi à 18h », « ménage tous les mercredis », « dentiste vendredi 14h30 »
    -> {"txt", "jour", "heure", "date"|None, "chaque": bool} ou None."""
    t = _sa(texte)
    m = re.search(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain|aujourd'?hui)s?\b", t)
    if not m:
        return None
    mot = m.group(1)
    auj = datetime.date.today()
    if mot == "demain":
        d = auj + datetime.timedelta(days=1)
    elif mot.startswith("aujourd"):
        d = auj
    else:
        j = JOURS.index(mot)
        d = auj + datetime.timedelta(days=(j - auj.weekday()) % 7)
    chaque = bool(re.search(r"\b(?:tous les|chaque|toutes les semaines|le " + mot + r"s?\b)", t)) and mot not in (
        "demain",) and not mot.startswith("aujourd")
    h = re.search(r"\b(?:a |vers |de )?(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b", t)
    heure = f"{int(h.group(1)):02d}:{int(h.group(2) or 0):02d}" if h and int(h.group(1)) < 24 else ""
    # le texte : ce qui reste quand on enlève les mots du planning
    reste = texte
    for pat in (r"(?i)\b(?:ajoute|ajouter|mets?|note|planifie|programme|rajoute)(?:[- ]moi)?\b",
                r"(?i)\b(?:dans|sur|a|à) (?:mon|le|ma) (?:planning|agenda|semaine)\b",
                r"(?i)\b(?:tous les|toutes les|chaque|le|la|ce|cette)\s+(?=" + mot[:3] + ")",
                r"(?i)\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain|aujourd'?hui)s?\b",
                r"(?i)\b(?:à|a|vers|de)?\s*\d{1,2}\s*(?:h|:)\s*\d{0,2}\b", r"(?i)\btoutes les semaines\b"):
        reste = re.sub(pat, " ", reste)
    reste = re.sub(r"\s+", " ", reste).strip(" ,.;:-")
    if not reste:
        return None
    return {"txt": reste[:1].upper() + reste[1:60], "jour": d.weekday(), "heure": heure,
            "date": None if chaque else d.isoformat(), "chaque": chaque}


class PlanningWin(_Fenetre):
    def __init__(self, comp):
        super().__init__(comp, "🗓️ " + tr("Ma semaine"), 760, 430)
        self.setMinimumSize(560, 330)
        self.grille = QGridLayout()
        self.grille.setSpacing(6)
        self.lay.addLayout(self.grille, 1)
        ajout = QHBoxLayout()
        self.e = QLineEdit()
        self.e.setPlaceholderText(tr("« sport jeudi à 18h », « ménage tous les mercredis », « maman samedi »…"))
        self.e.returnPressed.connect(self._ajouter)
        ajout.addWidget(self.e, 1)
        b = QPushButton("+ " + tr("Ajouter"))
        b.setObjectName("btn")
        b.clicked.connect(self._ajouter)
        ajout.addWidget(b)
        self.lay.addLayout(ajout)
        aide = QLabel(tr("Clic sur une activité pour la retirer. Elle te rappelle ta journée le matin, et chaque "
                         "activité un quart d'heure avant."))
        aide.setObjectName("petit")
        aide.setWordWrap(True)
        self.lay.addWidget(aide)

    def _ajouter(self):
        txt = self.e.text().strip()
        if not txt:
            return
        r = lire_ajout(txt)
        if not r:
            return self.comp.say("Dis-moi aussi le jour : « sport jeudi », « ménage tous les mercredis »…")
        r["couleur"] = COULEURS[len(planning(self.comp.cfg)) % len(COULEURS)]
        planning(self.comp.cfg).append(r)
        self.comp.save_cfg()
        self.e.clear()
        self.remplir()

    def _retirer(self, e):
        p = planning(self.comp.cfg)
        if e in p:
            p.remove(e)
            self.comp.save_cfg()
        self.remplir()

    def remplir(self):
        _vider(self.grille)
        auj = datetime.date.today()
        lundi = auj - datetime.timedelta(days=auj.weekday())
        for j in range(7):
            d = lundi + datetime.timedelta(days=j)
            col = QFrame()
            col.setObjectName("col")
            col.setProperty("auj", d == auj)
            v = QVBoxLayout(col)
            v.setContentsMargins(6, 6, 6, 6)
            v.setSpacing(4)
            t = QLabel(f"{tr(JOURS[j]).capitalize()[:3]} {d.day}")
            t.setObjectName("petit" if d != auj else "serie")
            v.addWidget(t)
            for e in du_jour(self.comp.cfg, d):
                c = QPushButton((e["heure"] + " " if e.get("heure") else "") + e["txt"] + (" 🔁" if e.get("chaque") else ""))
                c.setStyleSheet(f"QPushButton {{ background: {e.get('couleur', '#0a84ff')}; color: white; border: none; "
                                f"border-radius: 6px; padding: 3px 5px; font-size: 11px; text-align: left; }}")
                c.setToolTip(tr("Clic : retirer"))
                c.clicked.connect(lambda _c=False, e=e: self._retirer(e))
                v.addWidget(c)
            v.addStretch()
            self.grille.addWidget(col, 0, j)


# ================================================================== 4. muscu à la maison (sans matériel)
EXOS = {  # nom, consigne, icône
    "jumping": ("Jumping jacks", "Écarte bras et jambes en sautillant. Sans sauter si tu as des voisins dessous.", "🤸"),
    "squat": ("Squats", "Pieds largeur d'épaules, descends comme pour t'asseoir, dos droit, genoux au-dessus des pieds.", "🦵"),
    "pompes": ("Pompes", "Mains sous les épaules, corps bien droit. Trop dur ? Pose les genoux.", "💪"),
    "pompes_mur": ("Pompes contre le mur", "Mains sur le mur, corps droit, plie les coudes et repousse.", "💪"),
    "fentes": ("Fentes alternées", "Un grand pas en avant, descends doucement, reviens. Change de jambe.", "🦵"),
    "planche": ("Gainage (planche)", "Sur les avant-bras, corps droit de la tête aux pieds. Respire !", "🧱"),
    "planche_cote": ("Gainage sur le côté", "Sur un avant-bras, hanches levées. Change de côté à la moitié.", "🧱"),
    "crunch": ("Crunchs", "Allongée, genoux pliés, décolle juste les épaules en soufflant.", "🔥"),
    "pont": ("Pont fessier", "Allongée, pieds au sol, monte le bassin, serre les fessiers, redescends.", "🍑"),
    "montees": ("Montées de genoux", "Cours sur place en montant bien les genoux.", "🏃"),
    "dips": ("Dips sur une chaise", "Mains sur le bord d'une chaise solide, plie les coudes et remonte.", "🪑"),
    "superman": ("Superman", "Allongée sur le ventre, lève bras et jambes en même temps, tiens, relâche.", "🦸"),
    "chaise": ("La chaise", "Dos contre le mur, cuisses à l'horizontale. Tiens bon !", "🧱"),
    "mountain": ("Mountain climbers", "En position de pompe, ramène les genoux vers la poitrine, vite.", "⛰️"),
    "etirement": ("Étirements", "Étire doucement les jambes, les bras et le dos. Respire lentement.", "🙆"),
}
PROGRAMMES = {
    "decouverte": ("🌱 Découverte · 8 min", "Pour commencer en douceur.",
                   [("jumping", 30), ("squat", 30), ("pompes_mur", 30), ("pont", 30), ("planche", 20), ("montees", 30),
                    ("crunch", 30), ("etirement", 45)], 20, 1),
    "complet": ("⚡ Corps complet · 15 min", "Un peu de tout, sans matériel.",
                [("jumping", 40), ("squat", 40), ("pompes", 30), ("fentes", 40), ("planche", 30), ("mountain", 30),
                 ("pont", 40), ("crunch", 40)], 20, 2),
    "haut": ("💪 Haut du corps · 12 min", "Bras, épaules, dos.",
             [("pompes", 30), ("dips", 30), ("superman", 30), ("planche", 30), ("pompes_mur", 40), ("planche_cote", 40)],
             25, 2),
    "jambes": ("🦵 Jambes et fessiers · 12 min", "Cuisses, fessiers, mollets.",
               [("squat", 45), ("fentes", 40), ("pont", 45), ("chaise", 30), ("montees", 30)], 20, 2),
    "abdos": ("🔥 Abdos et gainage · 10 min", "Le ventre et le dos.",
              [("crunch", 40), ("planche", 30), ("mountain", 30), ("planche_cote", 40), ("superman", 30)], 20, 2),
}
ENCOURAGE = ["Allez, tu gères !", "Super, continue !", "Encore un peu, je suis avec toi !", "Respire, tu es top !",
             "La moitié, déjà !", "Tu fais ça trop bien !"]


def seance_liste(prog):
    nom, _d, exos, repos, tours = PROGRAMMES[prog]
    out = [("pret", 10)]
    for t in range(tours):
        for i, (k, s) in enumerate(exos):
            if k == "etirement" and t < tours - 1:
                continue
            out.append((k, s))
            if not (t == tours - 1 and i == len(exos) - 1):
                out.append(("repos", repos))
    return out


class MuscuWin(_Fenetre):
    def __init__(self, comp):
        super().__init__(comp, "💪 " + tr("Muscu à la maison"), 470, 580)
        self.prog, self.plan, self.i, self.reste, self.pause, self.debut = None, [], 0, 0, False, 0
        self.zone = QVBoxLayout()
        self.lay.addLayout(self.zone, 1)
        self.t = QTimer(self)
        self.t.timeout.connect(self._tic)

    # --- choisir un programme
    def remplir(self):
        if self.prog:
            return
        _vider(self.zone)
        n = len(self.comp.cfg.get("muscu_log", []))
        l = QLabel(tr("Choisis ta séance. Pas besoin de matériel : juste un peu de place (et une chaise solide pour "
                      "les dips).") + (f"  ·  {n} " + tr("séance(s) déjà faites 💪") if n else ""))
        l.setObjectName("desc")
        l.setWordWrap(True)
        self.zone.addWidget(l)
        for k, (nom, desc, _e, _r, _t) in PROGRAMMES.items():
            b = QPushButton(f"{nom}\n{tr(desc)}")
            b.setObjectName("jour")
            b.setMinimumHeight(52)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, k=k: self.demarrer(k))
            self.zone.addWidget(b)
        a = QLabel(tr("Échauffe-toi, bois de l'eau et écoute ton corps : si ça fait mal (pas juste « dur »), "
                      "arrête-toi."))
        a.setObjectName("petit")
        a.setWordWrap(True)
        self.zone.addWidget(a)
        self.zone.addStretch()

    # --- la séance
    def demarrer(self, prog):
        self.prog, self.plan, self.i, self.pause, self.debut = prog, seance_liste(prog), -1, False, time.time()
        _vider(self.zone)
        self.l_etape = QLabel("")
        self.l_etape.setObjectName("petit")
        self.zone.addWidget(self.l_etape)
        rang = QHBoxLayout()
        rang.addStretch()
        self.sil = Silhouette(190)
        rang.addWidget(self.sil)
        self.anneau = Anneau(140)
        self.anneau.col = QColor("#ff9f0a")
        rang.addWidget(self.anneau, 0, Qt.AlignmentFlag.AlignVCenter)
        rang.addStretch()
        self.zone.addLayout(rang)
        self.l_exo = QLabel("")
        self.l_exo.setObjectName("exo")
        self.l_exo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zone.addWidget(self.l_exo)
        self.l_desc = QLabel("")
        self.l_desc.setObjectName("desc")
        self.l_desc.setWordWrap(True)
        self.l_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zone.addWidget(self.l_desc)
        self.l_suite = QLabel("")
        self.l_suite.setObjectName("petit")
        self.l_suite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zone.addWidget(self.l_suite)
        self.zone.addStretch()
        ctl = QHBoxLayout()
        ctl.addStretch()
        self.b_pause = QPushButton("⏸ " + tr("Pause"))
        self.b_pause.setObjectName("btn")
        self.b_pause.clicked.connect(self._pause)
        ctl.addWidget(self.b_pause)
        b = QPushButton("⏭ " + tr("Passer"))
        b.setObjectName("btn")
        b.clicked.connect(self._suivant)
        ctl.addWidget(b)
        b2 = QPushButton("⏹ " + tr("Arrêter"))
        b2.setObjectName("btn")
        b2.clicked.connect(self.arreter)
        ctl.addWidget(b2)
        ctl.addStretch()
        self.zone.addLayout(ctl)
        self._suivant()
        self.t.start(1000)

    def _nom(self, k):
        return {"pret": tr("Prête ?"), "repos": tr("Repos")}.get(k) or tr(EXOS[k][0])

    def _suivant(self):
        self.i += 1
        if self.i >= len(self.plan):
            return self._fin()
        k, s = self.plan[self.i]
        self.reste, self.duree = s, s
        if getattr(self, "sil", None) is not None:
            self.sil.montrer(k)
        exos = [x for x in self.plan if x[0] not in ("pret", "repos")]
        fait = sum(1 for x in self.plan[:self.i] if x[0] not in ("pret", "repos"))
        self.l_etape.setText(tr(f"Exercice {min(fait + 1, len(exos))} sur {len(exos)}"))
        nxt = next((self._nom(x[0]) for x in self.plan[self.i + 1:] if x[0] not in ("repos",)), "")
        self.l_suite.setText(tr("Ensuite : ") + nxt if nxt else tr("Dernier effort !"))
        if k == "pret":
            self.l_exo.setText("🏁 " + tr("On s'échauffe"))
            self.l_desc.setText(tr("Mets-toi en place, la séance commence dans 10 secondes."))
            self.anneau.col = QColor("#64d2ff")
            self.comp.say(f"C'est parti pour la séance {PROGRAMMES[self.prog][0].split('·')[0][2:].strip()} ! "
                          f"Mets-toi en place.")
        elif k == "repos":
            self.l_exo.setText("😮‍💨 " + tr("Repos"))
            self.l_desc.setText(tr("Respire, bois une gorgée d'eau.") + (f"  {tr('Ensuite : ')}{nxt}" if nxt else ""))
            self.anneau.col = QColor("#30d158")
            self.comp.say(f"Repos ! Ensuite : {nxt}." if nxt else "Repos !")
        else:
            nom, desc, ico = EXOS[k]
            self.l_exo.setText(f"{ico} {tr(nom)}")
            self.l_desc.setText(tr(desc))
            self.anneau.col = QColor("#ff9f0a")
            self.comp.say(f"{nom} ! {s} secondes.")
            self.comp.react = ("regarde", time.monotonic())
        self._maj()

    def _maj(self):
        self.anneau.v = self.reste / max(1, self.duree)
        self.anneau.txt = f"{self.reste}"
        self.anneau.sous = tr("secondes")
        self.anneau.update()

    def _tic(self):
        if self.pause or not self.isVisible() or not self.prog:
            return
        self.reste -= 1
        k = self.plan[self.i][0]
        if self.reste in (3, 2, 1) and k != "repos":
            self.comp.say(str(self.reste))
        elif k not in ("pret", "repos") and self.reste == self.duree // 2 and self.duree >= 30:
            self.comp.say(random.choice(ENCOURAGE))
            self.comp.happy_until = time.monotonic() + 1
        if self.reste <= 0:
            return self._suivant()
        self._maj()

    def _pause(self):
        self.pause = not self.pause
        self.b_pause.setText(("▶ " + tr("Reprendre")) if self.pause else ("⏸ " + tr("Pause")))

    def _fin(self):
        self.t.stop()
        mins = max(1, round((time.time() - self.debut) / 60))
        log = self.comp.cfg.setdefault("muscu_log", [])
        log.append({"date": datetime.date.today().isoformat(), "prog": self.prog, "min": mins})
        del log[:-200]
        self.comp.save_cfg()
        self.comp.happy_until = time.monotonic() + 3
        self.comp._spawn("etoile", 8)
        n = len(log)
        semaine = sum(1 for x in log if (datetime.date.today() - datetime.date.fromisoformat(x["date"])).days < 7)
        self.comp.say(f"Séance terminée, bravo ! {mins} minutes de sport 💪"
                      + (f" C'est ta {semaine}e séance de la semaine !" if semaine > 1 else "")
                      + " Pense à boire et à t'étirer.")
        if hasattr(self.comp, "open_cuisine"):
            QTimer.singleShot(6000, lambda: self.comp.ask_yes(
                "Une idée de repas spécial sport pour bien récupérer ? (oui / non)",
                lambda: self.comp.open_cuisine(None, 0, sportif=True)))
        self.prog = None
        _vider(self.zone)
        l = QLabel(f"🎉 {tr('Bravo !')}\n\n{mins} min · {n} " + tr("séance(s) au total"))
        l.setObjectName("exo")
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zone.addWidget(l)
        b = QPushButton(tr("Choisir une autre séance"))
        b.setObjectName("btn")
        b.clicked.connect(self.remplir)
        self.zone.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        self.zone.addStretch()

    def arreter(self):
        self.t.stop()
        self.prog = None
        self.comp.say("D'accord, on s'arrête là. Chaque minute compte !")
        self.remplir()

    def fermer(self):
        if self.prog:
            self.t.stop()
            self.prog = None
        self.hide()


# ------------------------------------------------------------------ petite silhouette qui montre le mouvement
_DEBOUT = dict(t=(50, 14), c=(50, 25), b=(50, 52), ce=(42, 37), cm=(40, 51), de=(58, 37), dm=(60, 51),
               cg=(46, 73), cp=(45, 94), dg=(54, 73), dp=(55, 94))


def _p(base=None, **kw):
    d = dict(base or _DEBOUT)
    d.update(kw)
    return d


POSES = {   # exercice : (pose A, pose B, décor)  — repère 0..100, le sol est à y=95
    "pret": (_DEBOUT, _p(t=(50, 13), c=(50, 24)), ""),
    "repos": (_DEBOUT, _p(t=(50, 13), c=(50, 24), ce=(43, 36), de=(57, 36)), ""),
    "jumping": (_DEBOUT, _p(ce=(37, 19), cm=(30, 7), de=(63, 19), dm=(70, 7), cg=(40, 73), cp=(33, 94), dg=(60, 73),
                            dp=(67, 94), t=(50, 11), c=(50, 22), b=(50, 50)), ""),
    "squat": (_p(ce=(44, 40), cm=(40, 40), de=(56, 40), dm=(60, 40)),
              _p(t=(50, 34), c=(50, 45), b=(50, 69), ce=(43, 50), cm=(38, 50), de=(57, 50), dm=(62, 50),
                 cg=(38, 76), cp=(41, 94), dg=(62, 76), dp=(59, 94)), ""),
    "pompes": (dict(t=(18, 57), c=(25, 62), b=(56, 68), ce=(25, 77), cm=(25, 93), de=(27, 77), dm=(27, 93),
                    cg=(72, 74), cp=(88, 91), dg=(72, 75), dp=(88, 92)),
               dict(t=(18, 76), c=(25, 80), b=(56, 82), ce=(35, 84), cm=(25, 93), de=(37, 84), dm=(27, 93),
                    cg=(72, 86), cp=(88, 91), dg=(72, 87), dp=(88, 92)), ""),
    "pompes_mur": (dict(t=(38, 16), c=(40, 27), b=(50, 55), ce=(31, 31), cm=(22, 31), de=(32, 32), dm=(22, 32),
                        cg=(55, 74), cp=(60, 94), dg=(56, 74), dp=(61, 94)),
                   dict(t=(29, 18), c=(32, 29), b=(47, 56), ce=(29, 41), cm=(22, 31), de=(30, 42), dm=(22, 32),
                        cg=(54, 75), cp=(60, 94), dg=(55, 75), dp=(61, 94)), "mur"),
    "fentes": (_DEBOUT, _p(t=(50, 28), c=(50, 39), b=(50, 64), cg=(36, 70), cp=(34, 94), dg=(62, 86), dp=(74, 94),
                           ce=(44, 52), cm=(46, 64), de=(56, 52), dm=(54, 64)), ""),
    "planche": (dict(t=(18, 67), c=(25, 71), b=(56, 74), ce=(25, 89), cm=(38, 91), de=(27, 89), dm=(40, 91),
                     cg=(72, 78), cp=(88, 91), dg=(72, 79), dp=(88, 92)),
                dict(t=(18, 66), c=(25, 70), b=(56, 72), ce=(25, 89), cm=(38, 91), de=(27, 89), dm=(40, 91),
                     cg=(72, 77), cp=(88, 91), dg=(72, 78), dp=(88, 92)), ""),
    "planche_cote": (dict(t=(24, 46), c=(31, 53), b=(55, 70), ce=(30, 88), cm=(42, 92), de=(36, 39), dm=(40, 25),
                          cg=(70, 81), cp=(86, 92), dg=(70, 82), dp=(86, 93)),
                     dict(t=(24, 42), c=(31, 49), b=(55, 64), ce=(30, 88), cm=(42, 92), de=(36, 35), dm=(40, 21),
                          cg=(70, 78), cp=(86, 92), dg=(70, 79), dp=(86, 93)), ""),
    "crunch": (dict(t=(20, 84), c=(27, 86), b=(56, 89), ce=(18, 78), cm=(19, 83), de=(20, 79), dm=(21, 84),
                    cg=(68, 72), cp=(80, 93), dg=(69, 73), dp=(81, 93)),
               dict(t=(29, 70), c=(34, 77), b=(56, 89), ce=(26, 66), cm=(28, 71), de=(27, 67), dm=(29, 72),
                    cg=(68, 72), cp=(80, 93), dg=(69, 73), dp=(81, 93)), ""),
    "pont": (dict(t=(18, 86), c=(26, 87), b=(56, 89), ce=(36, 92), cm=(46, 92), de=(37, 92), dm=(47, 92),
                  cg=(70, 74), cp=(80, 93), dg=(71, 75), dp=(81, 93)),
             dict(t=(18, 86), c=(26, 85), b=(54, 71), ce=(36, 92), cm=(46, 92), de=(37, 92), dm=(47, 92),
                  cg=(70, 70), cp=(80, 93), dg=(71, 71), dp=(81, 93)), ""),
    "montees": (_p(cg=(43, 62), cp=(45, 79), de=(59, 30), dm=(62, 20), ce=(41, 42), cm=(40, 55)),
                _p(dg=(57, 62), dp=(55, 79), ce=(41, 30), cm=(38, 20), de=(59, 42), dm=(60, 55)), ""),
    "dips": (dict(t=(41, 28), c=(41, 38), b=(43, 66), ce=(35, 49), cm=(30, 59), de=(36, 49), dm=(31, 59),
                  cg=(64, 68), cp=(66, 94), dg=(64, 69), dp=(66, 94)),
             dict(t=(41, 40), c=(41, 50), b=(43, 78), ce=(29, 52), cm=(30, 59), de=(30, 53), dm=(31, 59),
                  cg=(64, 74), cp=(66, 94), dg=(64, 75), dp=(66, 94)), "chaise"),
    "superman": (dict(t=(20, 86), c=(27, 88), b=(56, 89), ce=(17, 89), cm=(8, 89), de=(18, 90), dm=(9, 90),
                      cg=(73, 90), cp=(90, 91), dg=(73, 91), dp=(90, 92)),
                 dict(t=(18, 80), c=(26, 84), b=(56, 88), ce=(16, 79), cm=(6, 75), de=(17, 80), dm=(7, 76),
                      cg=(73, 86), cp=(90, 81), dg=(73, 87), dp=(90, 82)), ""),
    "chaise": (dict(t=(27, 30), c=(27, 41), b=(29, 66), ce=(36, 50), cm=(44, 60), de=(37, 51), dm=(45, 61),
                    cg=(49, 66), cp=(49, 94), dg=(50, 67), dp=(50, 94)),
               dict(t=(27, 31), c=(27, 42), b=(29, 67), ce=(36, 51), cm=(44, 61), de=(37, 52), dm=(45, 62),
                    cg=(49, 67), cp=(49, 94), dg=(50, 68), dp=(50, 94)), "mur"),
    "mountain": (dict(t=(18, 58), c=(25, 63), b=(56, 69), ce=(25, 78), cm=(25, 93), de=(27, 78), dm=(27, 93),
                      cg=(40, 79), cp=(52, 91), dg=(72, 76), dp=(88, 92)),
                 dict(t=(18, 58), c=(25, 63), b=(56, 69), ce=(25, 78), cm=(25, 93), de=(27, 78), dm=(27, 93),
                      cg=(72, 76), cp=(88, 92), dg=(40, 79), dp=(52, 91)), ""),
    "etirement": (_p(ce=(40, 18), cm=(38, 5), de=(54, 17), dm=(50, 5), t=(48, 14), c=(49, 25)),
                  _p(ce=(50, 17), cm=(50, 5), de=(62, 18), dm=(64, 5), t=(52, 14), c=(51, 25)), ""),
}


class Silhouette(QWidget):
    """Une petite silhouette qui fait l'exercice en boucle (aller-retour doux entre deux positions)."""

    def __init__(self, taille=190):
        super().__init__()
        self.setFixedSize(taille, taille)
        self.exo = "pret"
        self.t0 = time.monotonic()
        self.tm = QTimer(self)
        self.tm.timeout.connect(self.update)
        self.tm.start(33)
        self.vitesse = 1.0

    def montrer(self, exo):
        self.exo = exo if exo in POSES else "pret"
        self.vitesse = {"planche": 0.5, "planche_cote": 0.4, "chaise": 0.6, "repos": 0.35, "pret": 0.5,
                        "mountain": 1.8, "montees": 1.8, "jumping": 1.6, "etirement": 0.4}.get(self.exo, 0.9)
        self.t0 = time.monotonic()

    @staticmethod
    def _c(hexc):
        try:
            import themes
            return QColor(themes.color(hexc))
        except Exception:
            return QColor(hexc)

    def paintEvent(self, _e):
        import math
        a, b, decor = POSES[self.exo]
        k = 0.5 - 0.5 * math.cos((time.monotonic() - self.t0) * math.pi * self.vitesse)
        S = self.width() / 100.0
        P = {n: QPointF((a[n][0] + (b[n][0] - a[n][0]) * k) * S, (a[n][1] + (b[n][1] - a[n][1]) * k) * S) for n in a}
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fond = self._c("#3a3644")
        p.setPen(QPen(fond, 2.5 * S / 1.9, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(4 * S, 95.5 * S), QPointF(96 * S, 95.5 * S))         # le sol
        if decor == "mur":
            p.drawLine(QPointF(20 * S, 8 * S), QPointF(20 * S, 95 * S))
        if decor == "chaise":
            p.drawLine(QPointF(12 * S, 60 * S), QPointF(32 * S, 60 * S))
            p.drawLine(QPointF(14 * S, 60 * S), QPointF(14 * S, 95 * S))
            p.drawLine(QPointF(30 * S, 60 * S), QPointF(30 * S, 95 * S))
            p.drawLine(QPointF(14 * S, 60 * S), QPointF(14 * S, 34 * S))
        corps = self._c("#ff9f0a")
        loin = QColor(corps)
        loin.setAlpha(140)
        ep = 5.2 * S / 1.9
        # membres du fond (côté droit), puis le corps, puis le devant
        for col, pts in ((loin, (("c", "de"), ("de", "dm"), ("b", "dg"), ("dg", "dp"))),
                         (corps, (("c", "b"),)),
                         (corps, (("c", "ce"), ("ce", "cm"), ("b", "cg"), ("cg", "cp")))):
            p.setPen(QPen(col, ep * (1.25 if pts == (("c", "b"),) else 1), cap=Qt.PenCapStyle.RoundCap,
                          join=Qt.PenJoinStyle.RoundJoin))
            for u, v in pts:
                p.drawLine(P[u], P[v])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(corps)
        p.drawEllipse(P["t"], 7 * S, 7 * S)
        p.end()
