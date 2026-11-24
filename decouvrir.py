"""📖 Pour que tout le monde sache quoi lui dire, sans rien deviner (même un enfant) :
  catalogue(comp)   toutes les phrases d'exemple (celles des astuces + les nouvelles), avec leur icône et leur thème
  chercher(...)     les phrases qui ressemblent à ce qu'on tape (suggestions dans la barre, « tu voulais dire… ? »)
  Livre             la fenêtre « Ce que je sais faire » : on clique une phrase, elle le fait
Chaque phrase : soit elle est faite tout de suite (« dire »), soit elle est mise dans la barre pour qu'on la
complète (« remplir » : une note, un rappel, une image à décrire…)."""
import random
import re
import unicodedata

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

try:
    import astuces
except Exception:                                   # pragma: no cover
    astuces = None


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


CATS = [("parler", "💬", "Parler avec elle"), ("jour", "☀️", "Au quotidien"), ("media", "🎬", "Musique et vidéos"),
        ("creer", "🎨", "Créer"), ("elle", "💜", "Elle"), ("pc", "💻", "PC et travail")]
# exemples des astuces à compléter soi-même (ils contiennent un exemple inventé ou changent quelque chose)
A_REMPLIR = {
    "note que le code du portail est 1234": "note que ", "ajoute du lait à la liste de courses": "ajoute  à la liste de courses",
    "rappelle-moi dans 10 minutes de sortir le linge": "rappelle-moi dans 10 minutes de ",
    "rappelle-moi à 18h30 d'appeler maman": "rappelle-moi à 18h30 de ",
    "je veux regarder One Piece": "je veux regarder ", "One Piece sur ADN": None,
    "mets ma playlist chill avec Firefox": None, "j'en suis à l'épisode 7 de Frieren": None,
    "je me suis arrêté à 23:15 dans Dune": None, "garde ce lien sous le nom One Piece": None,
    "génère une image d'un dragon bleu": "génère une image d'", "dessine-moi un fond d'écran cyberpunk": "dessine-moi ",
    "cherche sur internet la recette des crêpes": "cherche sur internet ", "trouve mon CV": "trouve ",
    "wikipédia Marie Curie": "wikipédia ", "l'actu sur l'espace": "l'actu sur ",
    "quand je dis mode chill, mets ma playlist chill et le mode nuit": "quand je dis ",
    "non, je voulais dire ma playlist chill": None, "oublie la commande mode chill": None,
    "garde ce code sous le nom tri": None, "installe librewolf": None, "mets un dns chiffré": None,
    "sauvegarde chiffrée": None, "enlève tes collants": None, "maigris": None, "grossis un peu": None,
    "coupe-toi les cheveux": None, "j'ai acheté le lait": None, "qu'est-ce que j'avais noté sur le portail ?": None,
    "le pdf que j'ai téléchargé hier": None, "recolle le lien de tout à l'heure": None,
    "désactive le mode batterie": None, "arrête la neige": None, "tu peux reparler": None,
    "chut 30 minutes": None, "minuteur 1 heure": None, "mets le dernier son de ma chaîne": None,
    "mets de la musique de ma liste": None, "traduis la sélection en espagnol": None, "épisode suivant": None,
}
TECH_IDS = {"erreur", "securite", "code", "vieprivee", "agenda_web", "assistant", "commande_perso", "batterie",
            "trad_sel", "lire_page", "ecran"}
# les nouveautés (pas encore dans les astuces) : (id, thème, icône, titre, phrase, mode, technique ?, action)
EXTRA = [
    ("tuto", "elle", "📖", "Le petit tuto", "montre-moi le tuto", "dire", False, None),
    ("meteo", "jour", "🌤️", "La météo", "quel temps fait-il ?", "dire", False, None),
    ("jouer", "parler", "🎮", "Jouer avec elle", "on joue à un jeu ?", "dire", False, None),
    ("muets", "elle", "🔕", "Choisir ce qu'elle me dit", "ce qu'elle me dit", "dire", False, None),
    ("curseur", "elle", "🖱️", "Le mode curseur", "mode curseur", "dire", False, None),
    ("guide", "jour", "👉", "Montre-moi sur l'écran", "montre-moi où changer le fond d'écran", "remplir", False, None),
    ("reprendre", "jour", "↩️", "Reprendre où j'en étais", "reprends où j'en étais", "dire", False, None),
    ("convertir", "jour", "🔁", "Convertir", "convertis 350 °F", "dire", False, None),
    ("rapide", "jour", "✂️", "Mes phrases toutes faites", "ajoute le raccourci ;adr = ", "remplir", False, None),
    ("rapides", "jour", "✂️", "Voir mes phrases toutes faites", "mes phrases toutes faites", "dire", False, None),
    ("dessin", "creer", "✏️", "Carnet de dessin", "Carnet de dessin", "action", False, "dessin"),
    ("studio", "creer", "🎼", "Studio musique", "Studio musique", "action", False, "studio"),
    ("images", "creer", "🖼️", "Atelier d'images", "Atelier d'images", "action", False, "images"),
    ("carnet", "pc", "📒", "Mon carnet de commandes", "mon carnet", "dire", True, None),
    ("commit", "pc", "✍️", "Message de commit", "écris mon commit", "dire", True, None),
    ("port", "pc", "🔌", "Qui utilise un port ?", "qui utilise le port 8080", "remplir", True, None),
    ("log", "pc", "📜", "Surveiller un fichier de log", "surveille le fichier ", "remplir", True, None),
    ("terminal", "pc", "🐚", "Alt+E dans le terminal", "Alt+E dans le terminal", "action", True, "terminal"),
]


VIDES = set("""je j me m moi tu te toi il elle on nous vous le la les l un une des du de d au aux a et ou en dans sur
pour par avec sans que qui quoi est c ce cet cette ces mon ma mes ton ta tes son sa ses ca cela peux veux voudrais
ai as avez avons suis es sommes etes ont vais va vas plus tres bien
fais fait faire stp svp please the a to my me i you""".split())
# des mots en plus, pour trouver même quand on ne dit pas le bon mot
SYNONYMES = {
    "jeux": "stats statistiques temps", "jouer": "jouer jeu jeux ennui ennuie ennuyer amuser morpion devinette", "blague": "rire drole rigoler ennui ennuie marrant",
    "musique": "son sons chanson chansons ecouter morceau ennui ambiance radio", "apprendre": "savoir culture curieux",
    "heure": "temps horloge", "image": "dessin photo illustration fond ecran wallpaper", "minuteur": "timer chrono cuisson",
    "rappel": "oublier oublie penser souvenir alarme reveil", "note": "noter retenir memo", "courses": "acheter magasin",
    "repas": "manger faim cuisine diner dejeuner recette", "neige": "hiver noel fete", "meteo": "temps pluie soleil froid",
    "regarder": "film serie anime episode video", "actu": "news nouvelles informations journal",
    "fichier": "retrouver perdu document", "web": "internet google recherche", "sport": "bouger exercice",
    "mouvements": "danse danser bouger", "apparence": "cheveux tenue habits look", "tuto": "aide comment",
    "chut": "silence taire calme muet", "dessin": "dessiner crayon peindre", "studio": "composer creer chanson",
}


LINUX_SEUL = {"terminal", "commit"}


def catalogue(lang="fr", simple=False):
    """-> [{"id", "cat", "ico", "titre", "phrase", "montre", "mode", "remplir", "action", "mots", "d"}]."""
    out = []
    for a in (astuces.ACTIONS if astuces else []):
        if a["id"] == "aide" or (simple and a["id"] in TECH_IDS):
            continue
        titre = a["t"].get(lang) or a["t"]["fr"]
        kw = (a.get("kw") or {}).get(lang) or []
        for k, ex in enumerate(a["ex"][:3]):
            if ex in A_REMPLIR and A_REMPLIR[ex] is None:
                continue                                    # trop particulier pour être un exemple
            mode = "remplir" if ex in A_REMPLIR else "dire"
            montre = ex if lang == "fr" else (kw[k] if k < len(kw) else tr(ex))
            out.append({"id": a["id"], "cat": a["cat"] if a["cat"] != "astuces" else "jour", "ico": a["ico"],
                        "titre": titre, "phrase": ex, "montre": montre, "mode": mode, "remplir": A_REMPLIR.get(ex),
                        "action": None, "d": a.get("d", ""),
                        "mots": _sa(" ".join([ex, a["t"]["fr"], titre, SYNONYMES.get(a["id"], "")] + kw
                                             + (a.get("kw") or {}).get("en", [])))})
    import sys
    win = sys.platform.startswith("win")
    for id_, cat, ico, titre, phrase, mode, tech, act in EXTRA:
        if (simple and tech) or (win and id_ in LINUX_SEUL):
            continue
        out.append({"id": id_, "cat": cat, "ico": ico, "titre": tr(titre), "phrase": phrase,
                    "montre": tr(phrase) if mode != "action" else tr(titre), "mode": mode,
                    "remplir": phrase if mode == "remplir" else None, "action": act, "d": "",
                    "mots": _sa(" ".join([phrase, titre, tr(titre), tr(phrase), SYNONYMES.get(id_, "")]))})
    return out


def chercher(q, cat, n=4):
    """Les phrases les plus proches de ce qu'on tape. -> [(score, item)]."""
    qs = [w for w in re.findall(r"\w+", _sa(q)) if len(w) >= 2 and w not in VIDES]
    if not qs:
        return []
    res = []
    vus = set()
    for it in cat:
        mots = [m for m in re.findall(r"\w+", it["mots"]) if m not in VIDES]
        score = 0.0
        for w in qs:
            if any(m == w for m in mots):
                score += 2
            elif any(m.startswith(w) for m in mots):
                score += 1.4
            elif len(w) >= 4 and any(w[:4] == m[:4] for m in mots if len(m) >= 4):
                score += 0.6
            elif len(w) >= 4 and w in it["mots"]:
                score += 0.5
        if score <= 0:
            continue
        score /= max(1.0, len(qs) ** 0.6)
        if it["phrase"] in vus:
            continue
        vus.add(it["phrase"])
        res.append((score, it))
    res.sort(key=lambda x: -x[0])
    # une seule phrase par fonction, pour varier les propositions
    final, ids = [], set()
    for sc, it in res:
        if it["id"] in ids:
            continue
        ids.add(it["id"])
        final.append((sc, it))
        if len(final) >= n:
            break
    return final


def exemple_au_hasard(cat):
    simples = [it for it in cat if it["mode"] == "dire" and it["action"] is None and len(it["montre"]) < 34]
    return random.choice(simples)["montre"] if simples else ""


# ------------------------------------------------------------------ le livre « Ce que je sais faire »
STYLE = """
QWidget#livre { font-size: 11pt; }
QLabel#gros { font-size: 22pt; font-weight: 800; }
QLabel#sous { font-size: 11.5pt; color: palette(placeholder-text); }
QFrame#fiche { background: rgba(127,127,127,26); border: 1px solid rgba(127,127,127,50); border-radius: 18px; }
QLabel#ico { font-size: 30pt; background: transparent; border: none; }
QLabel#titreFiche { font-size: 13pt; font-weight: 700; background: transparent; border: none; }
QLabel#desc { color: palette(placeholder-text); background: transparent; border: none; }
QLabel#phrase { padding: 8px 14px; border-radius: 14px; font-size: 11.5pt; background: rgba(127,127,127,40);
                border: 1px solid rgba(127,127,127,70); }
QLabel#phrase:hover { background: #0a84ff; color: white; border-color: #0a84ff; }
QPushButton#cat { padding: 7px 16px; border-radius: 15px; font-size: 11pt; }
QPushButton#cat:checked { background: #0a84ff; color: white; border: none; font-weight: 700; }
"""


class Phrase(QLabel):
    """Une phrase à cliquer : comme un bouton, mais le texte passe à la ligne (rien n'est coupé)."""

    def __init__(self, txt, fn):
        super().__init__(txt)
        self.fn = fn
        self.setObjectName("phrase")
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(60)

    def heightForWidth(self, w):
        return super().heightForWidth(w)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.fn()


class Livre(QWidget):
    """Grandes fiches par thème : l'icône, le nom, et les phrases à cliquer."""

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setObjectName("livre")
        self.setWindowTitle(tr("📖 Ce que je sais faire"))
        self.setStyleSheet(STYLE)
        self.resize(980, 760)
        self.cat_choisie = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 10, 26, 20)
        v.setSpacing(12)
        t = QLabel(tr("📖 Ce que je sais faire"))
        t.setObjectName("gros")
        v.addWidget(t)
        s = QLabel(tr("Clique sur une phrase : je le fais tout de suite. Tu peux aussi me l'écrire (double-clic sur moi) "
                      "ou me la dire au micro, avec tes mots à toi."))
        s.setObjectName("sous")
        s.setWordWrap(True)
        v.addWidget(s)
        self.cherche = QLineEdit()
        self.cherche.setPlaceholderText(tr("🔎 Qu'est-ce que tu veux faire ? (musique, rappel, image…)"))
        self.cherche.setMinimumHeight(38)
        self.cherche.textChanged.connect(lambda _t: self._delai.start(180))
        v.addWidget(self.cherche)
        self._delai = QTimer(self)
        self._delai.setSingleShot(True)
        self._delai.timeout.connect(self.remplir)
        cats = QHBoxLayout()
        cats.setSpacing(6)
        self.b_cats = []
        for cid, ico, nom in [("", "✨", "Tout")] + CATS:
            b = QPushButton(f"{ico}  {tr(nom)}")
            b.setObjectName("cat")
            b.setCheckable(True)
            b.setChecked(cid == "")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, c=cid: self.choisir(c))
            cats.addWidget(b)
            self.b_cats.append((cid, b))
        cats.addStretch(1)
        v.addLayout(cats)
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setFrameShape(QFrame.Shape.NoFrame)
        self.zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grille_w = QWidget()
        self.grille = QGridLayout(self.grille_w)
        self.grille.setContentsMargins(0, 0, 6, 0)
        self.grille.setSpacing(12)
        self.zone.setWidget(self.grille_w)
        v.addWidget(self.zone, 1)
        self.remplir()

    def choisir(self, c):
        self.cat_choisie = c
        for cid, b in self.b_cats:
            b.setChecked(cid == c)
        self.remplir()

    def _items(self):
        C = self.comp
        lang = (C.cfg.get("langue", "fr") or "fr")[:2]
        return catalogue(lang, simple=bool(C.cfg.get("mode_simple")))

    def remplir(self):
        while self.grille.count():
            it = self.grille.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        items = self._items()
        q = self.cherche.text().strip()
        if q:
            items = [it for _s, it in chercher(q, items, n=40)]
            ids = []
            for it in items:
                if it["id"] not in ids:
                    ids.append(it["id"])
            tous = self._items()
            groupes = [(i, [x for x in tous if x["id"] == i]) for i in ids]
        else:
            if self.cat_choisie:
                items = [it for it in items if it["cat"] == self.cat_choisie]
            ids = []
            for it in items:
                if it["id"] not in ids:
                    ids.append(it["id"])
            groupes = [(i, [x for x in items if x["id"] == i]) for i in ids]
        if not groupes:
            l = QLabel(tr("Je ne trouve rien pour ça… Essaie un autre mot, ou écris-le-moi simplement !"))
            l.setObjectName("sous")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grille.addWidget(l, 0, 0)
            return
        col = 3 if self.width() > 900 else 2
        for k in range(3):
            self.grille.setColumnStretch(k, 1 if k < col else 0)
        for k, (_i, xs) in enumerate(groupes):
            self.grille.addWidget(self._fiche(xs), k // col, k % col, Qt.AlignmentFlag.AlignTop)
        self.grille.setRowStretch(len(groupes) // col + 1, 1)

    def _fiche(self, xs):
        f = QFrame()
        f.setObjectName("fiche")
        f.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        h = QHBoxLayout()
        ico = QLabel(xs[0]["ico"])
        ico.setObjectName("ico")
        h.addWidget(ico)
        t = QLabel(xs[0]["titre"])
        t.setObjectName("titreFiche")
        t.setWordWrap(True)
        h.addWidget(t, 1)
        v.addLayout(h)
        if xs[0].get("d"):
            d = QLabel(tr(xs[0]["d"]))
            d.setObjectName("desc")
            d.setWordWrap(True)
            v.addWidget(d)
        for it in xs[:3]:
            txt = it["montre"]
            if it["mode"] == "remplir":
                txt = "✏️  « " + txt.rstrip() + " »"
            elif it["mode"] == "dire":
                txt = "« " + txt + " »"
            else:
                txt = "▶  " + tr("Ouvrir")
            b = Phrase(txt, lambda x=it: self.comp.faire_exemple(x))
            b.setToolTip(tr("Je le fais tout de suite") if it["mode"] != "remplir" else
                         tr("Je l'écris dans ma barre : tu n'as plus qu'à compléter"))
            v.addWidget(b)
        return f

    def resizeEvent(self, e):
        super().resizeEvent(e)
        n = 3 if self.width() > 900 else 2
        if getattr(self, "_col", None) != n:
            self._col = n
            QTimer.singleShot(0, self.remplir)


_ = QSize
