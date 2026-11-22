"""🍽️ La cuisine de Viki : une fenêtre à côté d'elle avec la recette en images (ingrédients, étapes illustrées,
minuteurs), le planning des repas de la semaine et la liste de courses qui en découle.
Tout reste sur le PC : les recettes sont dans ce fichier et dans quotidien.py, le planning dans la config."""
import random
import re
import unicodedata

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout,
                             QWidget)

try:
    from i18n import tr
except Exception:
    def tr(t):
        return t

# ------------------------------------------------------------------ recettes en plus (même forme que quotidien.REPAS)
# (nom, minutes, budget par personne, ingrédients pour 1 personne, étapes, pourquoi c'est bien)
REPAS_PLUS = [
    ("Curry de pois chiches", 25, "≈ 1,5 €", ["1 boîte de pois chiches", "1 oignon", "200 g de tomates concassées",
                                             "1 c. à café de curry", "un peu de lait de coco", "riz"],
     ["Fais cuire le riz 12 min dans l'eau bouillante salée.",
      "Coupe l'oignon et fais-le revenir 3 min dans un peu d'huile avec le curry.",
      "Ajoute les pois chiches égouttés, les tomates et le lait de coco.",
      "Laisse mijoter 10 min à feu doux, puis sers avec le riz."],
     "Plein de fibres et de protéines végétales, très peu cher."),
    ("Poêlée de poulet et légumes", 20, "≈ 2,5 €", ["150 g de blanc de poulet", "1 courgette", "1 poivron",
                                                   "1 oignon", "sauce soja ou herbes", "riz ou pâtes"],
     ["Coupe le poulet en dés et les légumes en morceaux.",
      "Fais dorer le poulet 5 min dans une poêle avec un peu d'huile.",
      "Ajoute les légumes et laisse cuire 10 min en remuant.",
      "Assaisonne avec la sauce soja ou les herbes et sers."],
     "Des protéines et des légumes en un seul plat."),
    ("Pâtes carbonara", 15, "≈ 1,8 €", ["100 g de spaghettis", "75 g de lardons", "1 œuf",
                                        "parmesan râpé", "poivre"],
     ["Fais cuire les pâtes 10 min dans l'eau bouillante salée.",
      "Pendant ce temps, fais dorer les lardons à la poêle, sans matière grasse.",
      "Bats l'œuf avec le parmesan et beaucoup de poivre dans un bol.",
      "Hors du feu, mélange les pâtes égouttées, les lardons et l'œuf : la chaleur fait la sauce."],
     "Rapide, réconfortant, et presque rien à acheter."),
    ("Galettes de courgettes", 25, "≈ 1,2 €", ["1 courgette", "1 œuf", "3 c. à soupe de farine",
                                               "un peu de fromage râpé", "salade verte"],
     ["Râpe la courgette et presse-la dans un torchon pour enlever l'eau.",
      "Mélange-la avec l'œuf, la farine, le fromage, du sel et du poivre.",
      "Fais cuire des petits tas dans une poêle huilée, 3 min de chaque côté.",
      "Sers chaud avec la salade."],
     "Une façon gourmande de manger des légumes."),
    ("Risotto aux champignons", 30, "≈ 2 €", ["80 g de riz rond", "150 g de champignons", "1 oignon",
                                              "1 cube de bouillon", "un peu de parmesan"],
     ["Fais chauffer 50 cl d'eau avec le cube de bouillon.",
      "Fais revenir l'oignon et les champignons coupés 5 min dans une casserole.",
      "Ajoute le riz, remue 1 min, puis verse le bouillon louche par louche en remuant.",
      "Après environ 18 min, le riz est crémeux : ajoute le parmesan et sers."],
     "Un plat de restaurant fait avec trois fois rien."),
    ("Tortilla espagnole", 35, "≈ 1,3 €", ["2 pommes de terre", "3 œufs", "1 oignon", "salade verte"],
     ["Coupe les pommes de terre en fines rondelles et l'oignon en lamelles.",
      "Fais-les cuire 15 min à feu doux dans une poêle avec de l'huile, en remuant.",
      "Bats les œufs, ajoute les pommes de terre et l'oignon, verse le tout dans la poêle.",
      "Laisse cuire 8 min à feu doux, retourne sur une assiette et remets 3 min de l'autre côté."],
     "Se mange chaude ou froide, parfaite pour le lendemain."),
    ("Velouté de potiron", 30, "≈ 1 €", ["300 g de potiron ou de courge", "1 pomme de terre", "1 oignon",
                                         "1 cube de bouillon", "un peu de crème"],
     ["Épluche et coupe le potiron, la pomme de terre et l'oignon en morceaux.",
      "Mets-les dans une casserole, couvre d'eau et ajoute le cube de bouillon.",
      "Laisse cuire 20 min jusqu'à ce que ce soit tendre.",
      "Mixe avec un peu de crème, sale et poivre."],
     "Doux, plein de vitamines, et il se congèle très bien."),
    ("Hachis parmentier", 45, "≈ 2 €", ["150 g de bœuf haché", "3 pommes de terre", "1 oignon",
                                        "un peu de lait et de beurre", "fromage râpé"],
     ["Fais cuire les pommes de terre épluchées 20 min dans l'eau salée.",
      "Pendant ce temps, fais revenir l'oignon et la viande hachée 8 min à la poêle.",
      "Écrase les pommes de terre avec le lait et le beurre pour faire une purée.",
      "Mets la viande dans un plat, couvre de purée et de fromage, puis passe 15 min au four à 200 °C."],
     "Le classique réconfortant, et les restes se réchauffent très bien."),
    ("Nouilles sautées aux légumes", 15, "≈ 1,5 €", ["1 portion de nouilles", "légumes surgelés (mélange wok)",
                                                     "1 œuf", "sauce soja"],
     ["Fais cuire les nouilles 4 min dans l'eau bouillante, puis égoutte-les.",
      "Fais sauter les légumes 5 min dans une poêle bien chaude avec un peu d'huile.",
      "Pousse les légumes sur le côté et fais cuire l'œuf brouillé au milieu.",
      "Ajoute les nouilles et la sauce soja, mélange 2 min et sers."],
     "Prêt en 15 minutes, comme au resto asiatique."),
    ("Lentilles vertes aux carottes", 35, "≈ 1 €", ["80 g de lentilles vertes", "2 carottes", "1 oignon",
                                                   "1 feuille de laurier", "un filet de vinaigre"],
     ["Rince les lentilles et coupe les carottes en rondelles et l'oignon en morceaux.",
      "Mets le tout dans une casserole avec le laurier, couvre bien d'eau.",
      "Laisse cuire 25 min à petit feu, sans saler au début.",
      "Égoutte, sale, poivre et ajoute un filet de vinaigre."],
     "Des protéines végétales et du fer pour presque rien."),
    ("Taboulé", 15, "≈ 1,2 €", ["60 g de semoule", "1 tomate", "1/2 concombre", "1/2 citron",
                                "menthe ou persil", "huile d'olive"],
     ["Verse la semoule dans un bol avec un peu de sel et couvre-la d'eau bouillante.",
      "Laisse gonfler 5 min sous une assiette, puis égraine à la fourchette.",
      "Coupe la tomate et le concombre en petits dés, hache les herbes.",
      "Mélange tout avec le jus de citron et l'huile d'olive, et mets au frais si tu as le temps."],
     "Frais, léger et parfait à emporter."),
    ("Pizza sur tortilla", 15, "≈ 1,5 €", ["1 tortilla", "3 c. à soupe de coulis de tomate", "1/2 mozzarella",
                                           "quelques champignons ou un peu de jambon", "origan"],
     ["Préchauffe le four à 220 °C.",
      "Étale le coulis sur la tortilla, ajoute la mozzarella en morceaux et la garniture.",
      "Saupoudre d'origan et fais cuire 8 min au four, jusqu'à ce que le fromage fonde.",
      "Coupe en parts et sers avec une salade."],
     "Une pizza maison sans pâte à préparer."),
    ("Poisson, purée et haricots verts", 25, "≈ 2,5 €", ["1 filet de poisson blanc", "2 pommes de terre",
                                                         "1 poignée de haricots verts", "un peu de lait", "citron"],
     ["Fais cuire les pommes de terre épluchées 20 min dans l'eau salée.",
      "Fais cuire les haricots verts 8 min à la vapeur ou dans l'eau bouillante.",
      "Fais cuire le poisson 4 min de chaque côté à la poêle avec un peu d'huile.",
      "Écrase les pommes de terre avec le lait, et sers avec un filet de citron."],
     "Du poisson au moins une fois par semaine, c'est bon pour la santé."),
    ("Shakshuka", 20, "≈ 1,3 €", ["1 boîte de tomates concassées", "2 œufs", "1 oignon", "1 poivron",
                                  "cumin, paprika", "pain"],
     ["Fais revenir l'oignon et le poivron coupés 5 min dans une poêle avec un peu d'huile.",
      "Ajoute les tomates et les épices, laisse mijoter 8 min.",
      "Creuse deux trous et casse les œufs dedans.",
      "Couvre et laisse cuire 5 min : le blanc doit être pris. Sers avec du pain."],
     "Un plat du Maghreb et du Moyen-Orient, plein de saveurs."),
    ("Ratatouille et semoule", 35, "≈ 1,8 €", ["1 courgette", "1/2 aubergine", "1 poivron", "1 oignon",
                                               "1 boîte de tomates concassées", "semoule"],
     ["Coupe tous les légumes en dés.",
      "Fais revenir l'oignon et le poivron 5 min, puis ajoute l'aubergine et la courgette.",
      "Ajoute les tomates, des herbes de Provence, et laisse mijoter 20 min à couvert.",
      "Prépare la semoule (5 min dans l'eau bouillante) et sers ensemble."],
     "Plein de légumes, et encore meilleure réchauffée le lendemain."),
    ("Steak haché et potatoes au four", 35, "≈ 2,5 €", ["1 steak haché", "2 pommes de terre", "paprika",
                                                        "salade verte"],
     ["Préchauffe le four à 210 °C.",
      "Coupe les pommes de terre en quartiers, mélange-les avec un peu d'huile, du sel et du paprika.",
      "Fais-les cuire 30 min au four, en les retournant à mi-cuisson.",
      "Fais cuire le steak 3 min de chaque côté à la poêle et sers avec la salade."],
     "Le petit plaisir de la semaine, fait maison."),
]

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOMENTS = [("midi", "Midi"), ("soir", "Soir")]
_VIANDE = ("poulet", "lardon", "jambon", "boeuf", "bœuf", "steak", "thon", "saumon", "maquereau", "poisson",
           "dinde", "saucisse", "chorizo", "viande")
RAYONS = [
    ("🥕 Fruits et légumes", ("carotte", "pomme de terre", "pommes de terre", "poireau", "oignon", "ail", "courgette", "poivron",
                              "tomate", "concombre", "salade", "brocoli", "banane", "citron", "champignon",
                              "potiron", "courge", "aubergine", "haricots verts", "menthe", "persil", "herbes")),
    ("🥩 Viande et poisson", ("poulet", "lardon", "jambon", "boeuf", "bœuf", "steak", "poisson", "dinde")),
    ("🥫 Conserves", ("thon", "maquereau", "saumon", "boîte", "boite", "coulis", "concassées", "haricots rouges", "pois chiches", "maïs", "mais",
                      "lait de coco")),
    ("🥛 Frais", ("œuf", "oeuf", "lait", "crème", "creme", "fromage", "beurre", "mozzarella", "parmesan")),
    ("🧊 Surgelés", ("surgelé", "surgele", "petits pois")),
    ("🍞 Boulangerie", ("pain", "tortilla")),
    ("🛒 Épicerie", ()),
]
EMOJI = [("œuf", "🥚"), ("oeuf", "🥚"), ("oignon", "🧅"), ("ail", "🧄"), ("tomate", "🍅"), ("fromage", "🧀"),
         ("parmesan", "🧀"), ("mozzarella", "🧀"), ("pomme de terre", "🥔"), ("pâtes", "🍝"), ("spaghetti", "🍝"),
         ("nouilles", "🍜"), ("riz", "🍚"), ("poulet", "🍗"), ("steak", "🥩"), ("boeuf", "🥩"), ("bœuf", "🥩"),
         ("lardon", "🥓"), ("jambon", "🥓"), ("thon", "🐟"), ("saumon", "🐟"), ("maquereau", "🐟"),
         ("poisson", "🐟"), ("carotte", "🥕"), ("courgette", "🥒"), ("concombre", "🥒"), ("poivron", "🫑"),
         ("aubergine", "🍆"), ("brocoli", "🥦"), ("salade", "🥬"), ("champignon", "🍄"), ("citron", "🍋"),
         ("banane", "🍌"), ("lait de coco", "🥥"), ("lait", "🥛"), ("crème", "🥛"), ("beurre", "🧈"),
         ("pain", "🍞"), ("tortilla", "🫓"), ("farine", "🌾"), ("semoule", "🌾"), ("flocons", "🌾"),
         ("lentilles", "🫘"), ("pois chiches", "🫘"), ("haricots", "🫘"), ("petits pois", "🫛"),
         ("maïs", "🌽"), ("potiron", "🎃"), ("courge", "🎃"), ("poireau", "🥬"), ("menthe", "🌿"),
         ("persil", "🌿"), ("herbes", "🌿"), ("origan", "🌿"), ("laurier", "🌿"), ("curry", "🌶️"),
         ("cumin", "🌶️"), ("paprika", "🌶️"), ("soja", "🥢"), ("huile", "🫒"), ("vinaigre", "🫗"),
         ("bouillon", "🍲"), ("cannelle", "🌰")]


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def recettes():
    """Toutes les recettes (celles de quotidien.py + celles d'ici), sans le petit-déjeuner pour les repas."""
    try:
        import quotidien
        base = list(quotidien.REPAS)
    except Exception:
        base = []
    noms = {r[0] for r in base}
    return [r for r in base + [x for x in REPAS_PLUS if x[0] not in noms] if "petit-déj" not in r[0]]


def par_nom(nom):
    for r in recettes():
        if r[0] == nom:
            return r
    return None


def vegetarien(r):
    t = _sa(" ".join(r[3]))
    return not any(_sa(v) in t for v in _VIANDE)


def emoji_de(ingr):
    t = _sa(ingr)
    for k, e in EMOJI:
        if _sa(k) in t:
            return e
    return "🥄"


def minutes_dans(etape):
    m = re.search(r"(\d+)\s*min\b", etape)
    return int(m.group(1)) if m else 0


def _nombre(s):
    s = s.replace(",", ".")
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b)
    return float(s)


def _fmt(x):
    if abs(x - round(x)) < 0.05:
        return str(int(round(x)))
    if abs(x - 0.5) < 0.05:
        return "1/2"
    return f"{x:.1f}".replace(".", ",")


def mettre_a_l_echelle(ingr, n):
    """« 3 œufs » pour 2 personnes -> « 6 œufs » (seul le nombre du début change)."""
    if n == 1:
        return ingr
    m = re.match(r"^(\d+(?:[.,]\d+)?|\d+/\d+)(\s.*)$", ingr)
    if not m:
        return ingr + f" (×{n})" if not re.match(r"^(un peu|quelques|une? pincée)", ingr) else ingr
    try:
        return _fmt(_nombre(m.group(1)) * n) + m.group(2)
    except Exception:
        return ingr


def nom_article(ingr):
    """« 100 g de pâtes complètes » -> « pâtes complètes » (pour la liste de courses)."""
    x = ingr.strip()
    x = re.sub(r"^\d+\s+ou\s+(?=\d)", "", x)
    x = re.sub(r"^(?:un peu|un filet|quelques|\d+[\d,./]*|une?)\s+", "", x)
    x = re.sub(r"^(?:petite boîte|boîte|boite|poignée|pincée|feuille|gousse|portion|tranches?|bol|"
               r"c\.(?: à café| à soupe)?|kg|ml|cl|g|l)(?=\s|$)\s*", "", x)
    x = re.sub(r"^(?:de |d'|du |des )", "", x)
    x = x.split("(")[0].strip()
    return x


def _cle(a):
    return " ".join(w.rstrip("sx") if len(w) > 3 else w for w in _sa(a).split())


def rayon_de(article):
    t = _sa(article)
    for nom, mots in RAYONS:
        if any(_sa(m) in t for m in mots):
            return nom
    return RAYONS[-1][0]


def prix(r):
    m = re.search(r"(\d+(?:[.,]\d+)?)", r[2])
    return float(m.group(1).replace(",", ".")) if m else 0.0


def remplir_semaine(vege=False, rapide=False, midi=True, eviter=()):
    """Un planning de 7 jours sans répéter un plat (tant que c'est possible)."""
    pool = [r for r in recettes() if (not vege or vegetarien(r)) and (not rapide or r[1] <= 20)] or recettes()
    random.shuffle(pool)
    pool.sort(key=lambda r: r[0] in eviter)
    sem, i = {}, 0
    for j in range(7):
        jour = {}
        for k, _lab in MOMENTS:
            if k == "midi" and not midi:
                continue
            jour[k] = pool[i % len(pool)][0]
            i += 1
        sem[str(j)] = jour
    return sem


def liste_de_courses(semaine, personnes=1):
    """-> {rayon: [(article, nombre de repas)]} à partir du planning."""
    compte, ordre = {}, []
    for j in range(7):
        for k, _lab in MOMENTS:
            r = par_nom((semaine.get(str(j)) or {}).get(k, ""))
            if not r:
                continue
            for ingr in r[3]:
                for part in re.split(r"\s*,\s*|\s+ou\s+(?=\d)", nom_article(ingr)):
                    a = nom_article(part)
                    if not a:
                        continue
                    key = _cle(a)
                    if key not in compte:
                        compte[key] = [a, 0]
                        ordre.append(key)
                    compte[key][1] += 1
    out = {}
    for key in ordre:
        a, n = compte[key]
        out.setdefault(rayon_de(a), []).append((a, n))
    return {nom: out[nom] for nom, _m in RAYONS if nom in out}


# ------------------------------------------------------------------ petites illustrations des étapes
def genre_etape(e):
    t = _sa(e)
    for genre, mots in (("four", ("four", "gratin")), ("minuteur", ("laisse", "mijoter", "gonfler", "repos")),
                        ("casserole", ("casserole", "eau bouillante", "bouillon", "cuire les pates", "vapeur",
                                       "dans l'eau")),
                        ("poele", ("poele", "revenir", "dorer", "sauter", "griller", "cuire le")),
                        ("bol", ("melange", "bats", "bol", "mixe", "ecrase", "egraine", "rape")),
                        ("couteau", ("coupe", "epluche", "hache", "emince", "rondelles", "des")),
                        ("assiette", ("sers", "servir", "assiette"))):
        if any(m in t for m in mots):
            return genre
    return "assiette"


def _pen(c, w):
    return QPen(QColor(c), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def dessin_etape(genre, n, px=76):
    """Une petite illustration (vectorielle, rien à télécharger) avec le numéro de l'étape."""
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = px / 76.0
    p.scale(s, s)
    p.setBrush(QColor("#fdf0f5"))
    p.setPen(_pen("#f0bfd4", 2))
    p.drawRoundedRect(QRectF(2, 2, 72, 72), 18, 18)
    ink = _pen("#4a2f3d", 3)
    p.setPen(ink)
    if genre == "poele":
        p.setBrush(QColor("#6f5563"))
        p.drawEllipse(QRectF(14, 32, 36, 20))
        p.drawLine(QPointF(48, 42), QPointF(66, 36))
        p.setBrush(QColor("#ffd166"))
        p.setPen(_pen("#ffffff", 2))
        p.drawEllipse(QRectF(24, 37, 14, 9))
        p.setPen(_pen("#f59a3c", 2.5))
        for x in (24, 32, 40):
            p.drawLine(QPointF(x, 28), QPointF(x - 2, 20))
    elif genre == "casserole":
        p.setBrush(QColor("#9b8a93"))
        p.drawRoundedRect(QRectF(16, 32, 40, 26), 6, 6)
        p.drawLine(QPointF(56, 38), QPointF(68, 38))
        p.drawLine(QPointF(8, 38), QPointF(16, 38))
        p.setPen(_pen("#4a90e2", 2.5))
        for x in (26, 36, 46):
            path = QPainterPath(QPointF(x, 28))
            path.cubicTo(QPointF(x - 4, 22), QPointF(x + 4, 18), QPointF(x, 12))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
    elif genre == "four":
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(14, 14, 48, 48), 6, 6)
        p.setBrush(QColor("#ffd166"))
        p.drawRoundedRect(QRectF(20, 28, 36, 26), 4, 4)
        p.setBrush(QColor("#4a2f3d"))
        for x in (24, 34, 44):
            p.drawEllipse(QRectF(x, 18, 5, 5))
    elif genre == "bol":
        p.setBrush(QColor("#ffffff"))
        path = QPainterPath(QPointF(12, 36))
        path.arcTo(QRectF(12, 18, 52, 40), 180, 180)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(40, 34), QPointF(58, 12))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(32, 26, 12, 10))
    elif genre == "couteau":
        p.setBrush(QColor("#c9b8c1"))
        path = QPainterPath(QPointF(14, 44))
        path.lineTo(QPointF(50, 22))
        path.quadTo(QPointF(56, 30), QPointF(46, 36))
        path.lineTo(QPointF(14, 44))
        p.drawPath(path)
        p.setBrush(QColor("#8a5a3c"))
        p.drawRoundedRect(QRectF(48, 14, 18, 8), 3, 3)
        p.setBrush(QColor("#7cc6a4"))
        for x in (18, 30, 42):
            p.drawEllipse(QRectF(x, 52, 10, 10))
    elif genre == "minuteur":
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(16, 18, 42, 42))
        p.drawLine(QPointF(37, 39), QPointF(37, 26))
        p.drawLine(QPointF(37, 39), QPointF(46, 44))
        p.drawLine(QPointF(32, 12), QPointF(42, 12))
    else:
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(10, 24, 56, 34))
        p.setBrush(QColor("#ef5b8f"))
        p.setPen(_pen("#4a2f3d", 2))
        p.drawEllipse(QRectF(24, 32, 14, 12))
        p.setBrush(QColor("#7cc6a4"))
        p.drawEllipse(QRectF(38, 34, 14, 10))
    p.resetTransform()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#b0336a"))
    r = 13 * s
    p.drawEllipse(QRectF(px - 2 * r - 1, 1, 2 * r, 2 * r))
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(14 * s))
    p.setFont(f)
    p.drawText(QRectF(px - 2 * r - 1, 1, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(n))
    p.end()
    return pm


# ------------------------------------------------------------------ la fenêtre
CSS = """
QWidget#cuisine { background: #fffafc; color: #2e1624; }
QWidget#cuisine QLabel { color: #2e1624; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 8px 16px; margin: 4px 2px; border-radius: 12px; background: #f6e7ee; color: #4a2f3d;
               font-weight: 600; }
QTabBar::tab:selected { background: #b0336a; color: white; }
QFrame#carte { background: white; border: 1px solid #f1dfe8; border-radius: 14px; }
QFrame#pourquoi { background: #fdf0f5; border: none; border-radius: 14px; }
QPushButton { background: white; border: 1px solid #ecd3df; border-radius: 10px; padding: 7px 12px; color: #2e1624; }
QPushButton:hover { background: #fdf0f5; }
QPushButton#main { background: #b0336a; color: white; border: none; font-weight: 700; }
QPushButton#main:hover { background: #9a2b5c; }
QPushButton#case { text-align: left; padding: 10px; min-height: 34px; }
QPushButton#vide { color: #9b8a93; text-align: left; padding: 10px; min-height: 34px; border-style: dashed; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #ecd3df; border-radius: 10px; padding: 6px 8px;
                                 color: #2e1624; }
QScrollArea { border: none; background: transparent; }
QCheckBox { color: #2e1624; }
"""


def _vider(lay):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            _vider(it.layout())


class Cuisine(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("cuisine")
        self.setStyleSheet(CSS)
        self.setWindowTitle(tr("🍽️ Cuisine") + " — " + comp.char.get("name", "Viki"))
        self.resize(560, 760)
        self.d = comp.cfg.setdefault("cuisine", {})
        self.d.setdefault("personnes", 1)
        self.d.setdefault("favoris", [])
        self.recette = None
        self.etape_lue = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._onglet_recette(), tr("🍳 Recette"))
        self.tabs.addTab(self._onglet_semaine(), tr("📅 Ma semaine"))
        self.tabs.addTab(self._onglet_courses(), tr("🛒 Courses"))
        self.tabs.currentChanged.connect(lambda i: self._remplir_courses() if i == 2 else None)

    def _save(self):
        try:
            self.C.save_config(self.comp.cfg)
        except Exception:
            pass

    # ------------------------------------------------------------ onglet recette
    def _onglet_recette(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        h = QHBoxLayout()
        self.choix = QComboBox()
        self.choix.setMinimumWidth(220)
        h.addWidget(self.choix, 1)
        b = QPushButton(tr("🔀 Une autre idée"))
        b.clicked.connect(self.au_hasard)
        h.addWidget(b)
        v.addLayout(h)
        h = QHBoxLayout()
        self.frigo = QLineEdit()
        self.frigo.setPlaceholderText(tr("J'ai dans mon frigo… (ex. : œufs, courgette)"))
        self.frigo.textChanged.connect(self._filtrer)
        h.addWidget(self.frigo, 1)
        self.f_vege = QCheckBox(tr("🌱 Végétarien"))
        self.f_vege.toggled.connect(lambda _b: self._filtrer())
        h.addWidget(self.f_vege)
        self.f_fav = QCheckBox(tr("❤️ Favoris"))
        self.f_fav.toggled.connect(lambda _b: self._filtrer())
        h.addWidget(self.f_fav)
        v.addLayout(h)
        self.choix.activated.connect(lambda _i: self.montrer(self.choix.currentData()))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        self.corps = QWidget()
        self.corps.setObjectName("cuisine")
        self.cl = QVBoxLayout(self.corps)
        self.cl.setContentsMargins(2, 6, 2, 6)
        self.cl.setSpacing(10)
        sc.setWidget(self.corps)
        v.addWidget(sc, 1)
        self._filtrer()
        return w

    def _filtrer(self):
        mots = [m for m in re.split(r"[,;]+|\s+et\s+", _sa(self.frigo.text())) if m.strip()]
        rs = recettes()
        if self.f_vege.isChecked():
            rs = [r for r in rs if vegetarien(r)]
        if self.f_fav.isChecked():
            rs = [r for r in rs if r[0] in self.d.get("favoris", [])]
        if mots:
            def score(r):
                t = _sa(" ".join(r[3]))
                return sum(1 for m in mots if m.strip() and m.strip()[:5] in t)
            rs = sorted([r for r in rs if score(r)], key=lambda r: -score(r))
        cur = self.recette[0] if self.recette else ""
        self.choix.blockSignals(True)
        self.choix.clear()
        for r in rs:
            self.choix.addItem(("❤️ " if r[0] in self.d.get("favoris", []) else "") +
                               ("🌱 " if vegetarien(r) else "") + f"{r[0]} · {r[1]} min", r[0])
        if not rs:
            self.choix.addItem(tr("Aucune recette ne correspond"), "")
        i = self.choix.findData(cur)
        self.choix.setCurrentIndex(max(0, i))
        self.choix.blockSignals(False)
        if mots and rs and (i < 0):
            self.montrer(rs[0][0])

    def au_hasard(self):
        rs = [self.choix.itemData(i) for i in range(self.choix.count()) if self.choix.itemData(i)]
        if self.recette and len(rs) > 1:
            rs = [x for x in rs if x != self.recette[0]]
        if rs:
            self.montrer(random.choice(rs))

    def montrer(self, nom_ou_recette):
        r = par_nom(nom_ou_recette) if isinstance(nom_ou_recette, str) else nom_ou_recette
        if not r:
            return
        self.recette = r
        self.etape_lue = -1
        try:
            self.comp._last_meal = r
        except Exception:
            pass
        i = self.choix.findData(r[0])
        if i >= 0:
            self.choix.setCurrentIndex(i)
        self.tabs.setCurrentIndex(0)
        self._dessiner_recette()

    def _dessiner_recette(self):
        r = self.recette
        _vider(self.cl)
        nom, mins, budget, ingr, etapes, pourquoi = r
        n = int(self.d.get("personnes", 1) or 1)
        t = QLabel(nom)
        f = t.font()
        f.setPointSize(f.pointSize() + 7)
        f.setBold(True)
        t.setFont(f)
        t.setWordWrap(True)
        self.cl.addWidget(t)
        infos = f"⏱ {mins} min   ·   💶 {budget} " + tr("la part") + (f"   ·   🌱 {tr('végétarien')}" if vegetarien(r) else "")
        li = QLabel(infos)
        li.setStyleSheet("color:#6f5563;")
        self.cl.addWidget(li)
        h = QHBoxLayout()
        h.addWidget(QLabel(tr("Pour")))
        sp = QSpinBox()
        sp.setRange(1, 12)
        sp.setValue(n)
        sp.setSuffix(tr(" pers."))
        sp.valueChanged.connect(self._personnes)
        h.addWidget(sp)
        h.addStretch(1)
        fav = r[0] in self.d.get("favoris", [])
        bf = QPushButton(tr("❤️ Favori") if fav else tr("🤍 Favori"))
        bf.clicked.connect(self._favori)
        h.addWidget(bf)
        bs = QPushButton(tr("📅 À ma semaine"))
        bs.clicked.connect(lambda: self._menu_semaine(bs))
        h.addWidget(bs)
        self.cl.addLayout(h)
        # ingrédients en images
        cadre = QFrame()
        cadre.setObjectName("carte")
        g = QGridLayout(cadre)
        g.setContentsMargins(12, 10, 12, 12)
        titre = QLabel(tr("Ingrédients"))
        titre.setStyleSheet("font-weight:700;")
        g.addWidget(titre, 0, 0, 1, 2)
        for k, x in enumerate(ingr):
            e = QLabel(emoji_de(x))
            fe = e.font()
            fe.setPointSize(fe.pointSize() + 9)
            e.setFont(fe)
            e.setFixedWidth(40)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab = QLabel(mettre_a_l_echelle(x, n))
            lab.setWordWrap(True)
            row, col = 1 + k // 2, (k % 2) * 2
            g.addWidget(e, row, col)
            g.addWidget(lab, row, col + 1)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        bc = QPushButton(tr("🛒 Ajouter les ingrédients aux courses"))
        bc.clicked.connect(self._recette_aux_courses)
        g.addWidget(bc, 2 + (len(ingr) - 1) // 2, 0, 1, 4)
        self.cl.addWidget(cadre)
        # étapes illustrées
        h = QHBoxLayout()
        lt = QLabel(tr("Étapes"))
        lt.setStyleSheet("font-weight:700;")
        h.addWidget(lt)
        h.addStretch(1)
        bl = QPushButton(tr("🔊 Me la lire, étape par étape"))
        bl.setObjectName("main")
        bl.clicked.connect(self.lire_suivante)
        self.b_lire = bl
        h.addWidget(bl)
        self.cl.addLayout(h)
        self.cartes = []
        for k, e in enumerate(etapes, 1):
            c = QFrame()
            c.setObjectName("carte")
            hl = QHBoxLayout(c)
            hl.setContentsMargins(10, 10, 10, 10)
            img = QLabel()
            img.setPixmap(dessin_etape(genre_etape(e), k))
            img.setFixedSize(78, 78)
            hl.addWidget(img, 0, Qt.AlignmentFlag.AlignTop)
            vv = QVBoxLayout()
            lab = QLabel(e)
            lab.setWordWrap(True)
            fl = lab.font()
            fl.setPointSize(fl.pointSize() + 1)
            lab.setFont(fl)
            vv.addWidget(lab)
            mn = minutes_dans(e)
            if mn:
                bt = QPushButton(tr("⏱ Minuteur") + f" {mn} min")
                bt.clicked.connect(lambda _=False, m=mn, nm=nom: self._minuteur(m, nm))
                hb = QHBoxLayout()
                hb.addWidget(bt)
                hb.addStretch(1)
                vv.addLayout(hb)
            vv.addStretch(1)
            hl.addLayout(vv, 1)
            self.cl.addWidget(c)
            self.cartes.append(c)
        pq = QFrame()
        pq.setObjectName("pourquoi")
        pl = QVBoxLayout(pq)
        lp = QLabel("💡 " + tr("Pourquoi c'est bien :") + " " + pourquoi)
        lp.setWordWrap(True)
        pl.addWidget(lp)
        self.cl.addWidget(pq)
        note = QLabel(tr("Prix indicatifs. Les quantités sont pour une personne, multipliées par le nombre choisi."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#9b8a93; font-size:9pt;")
        self.cl.addWidget(note)
        self.cl.addStretch(1)
        try:
            import i18n
            i18n.translate_widget(self.corps)
        except Exception:
            pass

    def _personnes(self, n):
        self.d["personnes"] = int(n)
        self._save()
        self._dessiner_recette()

    def _favori(self):
        f = self.d.setdefault("favoris", [])
        nom = self.recette[0]
        if nom in f:
            f.remove(nom)
        else:
            f.append(nom)
            self.comp.say("C'est noté ! 💜")
        self._save()
        self._filtrer()
        self._dessiner_recette()

    def _minuteur(self, m, nom):
        try:
            self.comp.add_timer(m * 60, nom)
        except Exception:
            pass

    def lire_suivante(self):
        """Mode cuisine : elle lit une étape à chaque clic et la met en avant."""
        if not self.recette:
            return
        etapes = self.recette[4]
        self.etape_lue += 1
        if self.etape_lue >= len(etapes):
            self.etape_lue = -1
            self.b_lire.setText(tr("🔊 Me la lire, étape par étape"))
            for c in self.cartes:
                c.setStyleSheet("")
            return self.comp.say("Bon appétit !")
        for k, c in enumerate(self.cartes):
            c.setStyleSheet("QFrame#carte { border: 2px solid #b0336a; background: #fff4f8; }"
                            if k == self.etape_lue else "")
        self.b_lire.setText(tr("▶ Étape suivante") if self.etape_lue < len(etapes) - 1 else tr("✔ Terminé"))
        self.comp.say(f"{self.etape_lue + 1}. {etapes[self.etape_lue]}")

    def _recette_aux_courses(self):
        items = [nom_article(x) for x in self.recette[3]]
        try:
            self.comp._notes_cmd("courses_add", [x for x in items if x])
        except Exception:
            pass

    def _menu_semaine(self, bouton):
        m = QMenu(self)
        for j, jour in enumerate(JOURS):
            sm = m.addMenu(tr(jour))
            for k, lab in MOMENTS:
                sm.addAction(tr(lab), lambda jj=j, kk=k: self._placer_dans_semaine(jj, kk, self.recette[0]))
        m.exec(bouton.mapToGlobal(QPoint(0, bouton.height())))

    def _placer_dans_semaine(self, j, k, nom):
        sem = self.d.setdefault("semaine", {})
        sem.setdefault(str(j), {})[k] = nom
        self._save()
        self._remplir_semaine_ui()
        self.comp.say(f"C'est noté : {tr(JOURS[j]).lower()}, {tr(dict(MOMENTS)[k]).lower()}")

    # ------------------------------------------------------------ onglet semaine
    def _onglet_semaine(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        h = QHBoxLayout()
        b = QPushButton(tr("✨ Remplir ma semaine"))
        b.setObjectName("main")
        b.clicked.connect(self.remplir_auto)
        h.addWidget(b)
        self.o_vege = QCheckBox(tr("🌱 Végétarien"))
        self.o_vege.setChecked(bool(self.d.get("vege")))
        self.o_rapide = QCheckBox(tr("⚡ Rapide"))
        self.o_rapide.setChecked(bool(self.d.get("rapide")))
        self.o_midi = QCheckBox(tr("Midi aussi"))
        self.o_midi.setChecked(self.d.get("midi", True))
        for c in (self.o_vege, self.o_rapide, self.o_midi):
            h.addWidget(c)
        h.addStretch(1)
        v.addLayout(h)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        box = QWidget()
        box.setObjectName("cuisine")
        self.grille = QGridLayout(box)
        self.grille.setHorizontalSpacing(8)
        self.grille.setVerticalSpacing(6)
        sc.setWidget(box)
        v.addWidget(sc, 1)
        self.budget = QLabel()
        self.budget.setWordWrap(True)
        self.budget.setStyleSheet("color:#6f5563;")
        v.addWidget(self.budget)
        h = QHBoxLayout()
        bc = QPushButton(tr("🛒 Faire la liste de courses"))
        bc.setObjectName("main")
        bc.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        h.addWidget(bc)
        bv = QPushButton(tr("🗑️ Vider la semaine"))
        bv.clicked.connect(self._vider_semaine)
        h.addWidget(bv)
        h.addStretch(1)
        v.addLayout(h)
        self._remplir_semaine_ui()
        return w

    def remplir_auto(self):
        self.d.update(vege=self.o_vege.isChecked(), rapide=self.o_rapide.isChecked(), midi=self.o_midi.isChecked())
        self.d["semaine"] = remplir_semaine(self.d["vege"], self.d["rapide"], self.d["midi"])
        self._save()
        self._remplir_semaine_ui()
        self.comp.say("Et voilà ta semaine ! Clique sur un repas pour voir la recette ou le changer.")

    def _vider_semaine(self):
        self.d["semaine"] = {}
        self._save()
        self._remplir_semaine_ui()

    def _remplir_semaine_ui(self):
        if not hasattr(self, "grille"):
            return
        _vider(self.grille)
        sem = self.d.get("semaine") or {}
        for c, (_k, lab) in enumerate(MOMENTS, 1):
            l = QLabel(tr(lab))
            l.setStyleSheet("font-weight:700;")
            self.grille.addWidget(l, 0, c)
        total, nb = 0.0, 0
        for j, jour in enumerate(JOURS):
            l = QLabel(tr(jour))
            l.setStyleSheet("font-weight:600;")
            self.grille.addWidget(l, j + 1, 0)
            for c, (k, _lab) in enumerate(MOMENTS, 1):
                nom = (sem.get(str(j)) or {}).get(k, "")
                r = par_nom(nom)
                b = QPushButton((("🌱 " if vegetarien(r) else "") + r[0]) if r else tr("+ Ajouter"))
                b.setObjectName("case" if r else "vide")
                b.setToolTip(f"{r[0]}\n{r[1]} min · {r[2]}" if r else "")
                b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                b.setMinimumWidth(60)
                b.clicked.connect(lambda _=False, jj=j, kk=k, bb=b: self._menu_case(jj, kk, bb))
                self.grille.addWidget(b, j + 1, c)
                if r:
                    total += prix(r)
                    nb += 1
        self.grille.setColumnStretch(1, 1)
        self.grille.setColumnStretch(2, 1)
        self.grille.setRowStretch(len(JOURS) + 1, 1)
        n = int(self.d.get("personnes", 1) or 1)
        self.budget.setText((tr("Budget estimé :") + f" ≈ {total * n:.0f} € " + tr("pour") + f" {nb} " +
                             tr("repas") + f" ({n} " + tr("pers.") + "). " + tr("Prix indicatifs."))
                            if nb else tr("Ta semaine est vide : clique sur « Remplir ma semaine » ou ajoute des "
                                          "repas un par un."))

    def _menu_case(self, j, k, bouton):
        sem = self.d.setdefault("semaine", {})
        nom = (sem.get(str(j)) or {}).get(k, "")
        m = QMenu(self)
        if nom:
            m.addAction(tr("🍳 Voir la recette"), lambda: self.montrer(nom))
            m.addAction(tr("🔀 Changer au hasard"), lambda: self._changer(j, k))
        else:
            m.addAction(tr("🔀 Une idée au hasard"), lambda: self._changer(j, k))
        sm = m.addMenu(tr("📖 Choisir une recette"))
        for r in sorted(recettes(), key=lambda r: r[0]):
            sm.addAction(("🌱 " if vegetarien(r) else "") + r[0], lambda nm=r[0]: self._placer_dans_semaine(j, k, nm))
        if nom:
            m.addSeparator()
            m.addAction(tr("🗑️ Retirer"), lambda: self._retirer(j, k))
        m.exec(bouton.mapToGlobal(QPoint(0, bouton.height())))

    def _changer(self, j, k):
        sem = self.d.setdefault("semaine", {})
        deja = {n for jour in sem.values() for n in jour.values()}
        pool = [r for r in recettes() if (not self.o_vege.isChecked() or vegetarien(r)) and
                (not self.o_rapide.isChecked() or r[1] <= 20)] or recettes()
        neuf = [r for r in pool if r[0] not in deja] or pool
        sem.setdefault(str(j), {})[k] = random.choice(neuf)[0]
        self._save()
        self._remplir_semaine_ui()

    def _retirer(self, j, k):
        (self.d.get("semaine", {}).get(str(j)) or {}).pop(k, None)
        self._save()
        self._remplir_semaine_ui()

    # ------------------------------------------------------------ onglet courses
    def _onglet_courses(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        info = QLabel(tr("La liste vient de ta semaine de repas. Décoche ce que tu as déjà à la maison."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#6f5563;")
        v.addWidget(info)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        box = QWidget()
        box.setObjectName("cuisine")
        self.cl2 = QVBoxLayout(box)
        self.cl2.setSpacing(4)
        sc.setWidget(box)
        v.addWidget(sc, 1)
        h = QHBoxLayout()
        b = QPushButton(tr("➕ Ajouter à ma liste de courses"))
        b.setObjectName("main")
        b.clicked.connect(self._vers_liste)
        h.addWidget(b)
        b2 = QPushButton(tr("📋 Copier"))
        b2.clicked.connect(self._copier)
        h.addWidget(b2)
        b3 = QPushButton(tr("💾 Enregistrer…"))
        b3.clicked.connect(self._enregistrer)
        h.addWidget(b3)
        h.addStretch(1)
        v.addLayout(h)
        self.cases = []
        return w

    def _remplir_courses(self):
        _vider(self.cl2)
        self.cases = []
        lc = liste_de_courses(self.d.get("semaine") or {}, int(self.d.get("personnes", 1) or 1))
        if not lc:
            l = QLabel(tr("Rien pour l'instant : remplis d'abord ta semaine (onglet « Ma semaine »)."))
            l.setWordWrap(True)
            self.cl2.addWidget(l)
        for rayon, items in lc.items():
            t = QLabel(tr(rayon))
            t.setStyleSheet("font-weight:700; margin-top:8px;")
            self.cl2.addWidget(t)
            for a, n in items:
                c = QCheckBox(a + (f"   · {n} " + tr("repas") if n > 1 else ""))
                c.setChecked(True)
                c.setProperty("article", a)
                self.cl2.addWidget(c)
                self.cases.append(c)
        n = int(self.d.get("personnes", 1) or 1)
        if lc and n > 1:
            l = QLabel(tr("Quantités pour") + f" {n} " + tr("personnes : regarde chaque recette pour le détail."))
            l.setStyleSheet("color:#9b8a93;")
            self.cl2.addWidget(l)
        self.cl2.addStretch(1)

    def _choisis(self):
        return [c.property("article") for c in self.cases if c.isChecked()]

    def _vers_liste(self):
        a = self._choisis()
        if not a:
            return self.comp.say("Ta liste de courses est vide !")
        try:
            self.comp._notes_cmd("courses_add", a)
        except Exception:
            pass

    def _texte(self):
        lc = liste_de_courses(self.d.get("semaine") or {})
        garde = set(self._choisis())
        lignes = [tr("Liste de courses")]
        for rayon, items in lc.items():
            ok = [a for a, _n in items if a in garde]
            if ok:
                lignes += ["", tr(rayon)] + ["☐ " + a for a in ok]
        return "\n".join(lignes)

    def _copier(self):
        QApplication.clipboard().setText(self._texte())
        self.comp.say("C'est copié !")

    def _enregistrer(self):
        from pathlib import Path
        p, _ = QFileDialog.getSaveFileName(self, tr("Enregistrer la liste"), str(Path.home() / "courses.txt"),
                                           "Texte (*.txt)")
        if p:
            Path(p).write_text(self._texte(), encoding="utf-8")

    # ------------------------------------------------------------ place : à côté d'elle
    def placer(self):
        c = self.comp
        try:
            r = c.body_rect()
            g = c.mapToGlobal(r.topLeft())
            body_l, body_r, body_b = g.x(), g.x() + r.width(), g.y() + r.height()
            scr = (c.screen() or QApplication.primaryScreen()).availableGeometry()
        except Exception:
            return
        w, h = min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 60)
        self.resize(w, h)
        rb = getattr(c, "ronds_bar", None)
        if rb is not None and rb.isVisible():
            body_l = min(body_l, rb.geometry().left())
            body_r = max(body_r, rb.geometry().right())
        x = body_l - w - 16 if body_l - w - 16 >= scr.left() else body_r + 16
        x = max(scr.left() + 8, min(x, scr.right() - w - 8))
        y = max(scr.top() + 30, min(body_b - h, scr.bottom() - h - 8))
        self.move(QPoint(int(x), int(y)))

    def ouvrir(self, recette=None, onglet=0):
        if recette is not None:
            self.montrer(recette)
        elif self.recette is None:
            self.au_hasard()
        self.tabs.setCurrentIndex(onglet)
        if onglet == 2:
            self._remplir_courses()
        if not self.isVisible():
            self.placer()
        self.show()
        self.raise_()
        self.activateWindow()
