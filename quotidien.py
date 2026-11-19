"""Le quotidien avec Viki : une chose apprise chaque jour, un peu de sport, des blagues, des idées de repas
pas chers, faciles et équilibrés. Tout est écrit ici (aucun internet) ; l'IA locale peut en ajouter sur demande.
"""
import datetime
import random

# ================================================================== une chose apprise par jour
FAITS = [
    "Le cœur humain bat environ 100 000 fois par jour.",
    "Les pieuvres ont trois cœurs et un sang bleu, grâce à une protéine à base de cuivre.",
    "Le miel ne se périme presque jamais : on en a retrouvé de comestible dans des tombes égyptiennes.",
    "La Tour Eiffel grandit de quelques centimètres en été : le métal se dilate avec la chaleur.",
    "Une journée sur Vénus dure plus longtemps qu'une année vénusienne.",
    "Les bananes sont légèrement radioactives, à cause du potassium qu'elles contiennent (sans aucun danger).",
    "Le plus grand organe du corps humain, c'est la peau.",
    "Les loutres de mer se tiennent par la patte en dormant pour ne pas dériver.",
    "La lumière du Soleil met environ 8 minutes à arriver jusqu'à nous.",
    "Le mot « robot » vient du tchèque « robota », qui veut dire travail forcé.",
    "Les flamants roses sont roses à cause de ce qu'ils mangent : des crevettes et des algues riches en pigments.",
    "Un éclair est environ cinq fois plus chaud que la surface du Soleil.",
    "Le premier programme informatique a été écrit par Ada Lovelace, au XIXe siècle.",
    "Les abeilles communiquent entre elles en dansant : la « danse frétillante » indique où sont les fleurs.",
    "L'eau chaude peut parfois geler plus vite que l'eau froide : on appelle ça l'effet Mpemba.",
    "Les koalas dorment jusqu'à 20 heures par jour.",
    "Le mont Everest grandit encore de quelques millimètres par an.",
    "Le cerveau consomme environ 20 % de l'énergie du corps, alors qu'il ne pèse qu'environ 2 % de notre poids.",
    "Les étoiles de mer n'ont pas de cerveau.",
    "Le son voyage environ quatre fois plus vite dans l'eau que dans l'air.",
    "Les chats passent environ deux tiers de leur vie à dormir.",
    "Le Japon compte plus de 6 800 îles.",
    "Le plus long mot de la langue française couramment cité est « anticonstitutionnellement » (25 lettres).",
    "Les dauphins se donnent des « noms » : chacun a un sifflement qui lui est propre.",
    "La Grande Muraille de Chine ne se voit pas à l'œil nu depuis l'espace, contrairement à la légende.",
    "Une cuillère à café d'étoile à neutrons pèserait des milliards de tonnes.",
    "Les pingouins et les manchots, ce n'est pas pareil : les pingouins peuvent voler, les manchots non.",
    "Le Wi-Fi utilise des ondes radio, comme la radio FM, mais à une fréquence bien plus élevée.",
    "Les empreintes digitales des koalas ressemblent beaucoup à celles des humains.",
    "Il y a plus d'arbres sur Terre que d'étoiles dans la Voie lactée (environ 3 000 milliards d'arbres).",
    "La vitamine D est fabriquée par la peau quand elle reçoit la lumière du soleil.",
    "Le premier site web, créé au CERN en 1991, est toujours en ligne.",
    "Les escargots peuvent dormir pendant plusieurs mois quand il fait trop sec.",
    "Le rire est contagieux : notre cerveau se prépare à rire quand il entend quelqu'un rire.",
    "Les fourmis ne dorment pas comme nous : elles font des centaines de micro-siestes par jour.",
    "La Lune s'éloigne de la Terre d'environ 3,8 cm par an.",
    "Le chocolat est toxique pour les chiens et les chats, à cause de la théobromine.",
    "Le clavier AZERTY vient de la disposition QWERTY, adaptée au français à la fin du XIXe siècle.",
    "Les girafes n'ont que sept vertèbres dans le cou, comme nous.",
    "Le corps humain contient assez de fer pour fabriquer un petit clou.",
    "Les arbres d'une forêt peuvent échanger des nutriments par les champignons de leurs racines.",
    "Les éléphants sont parmi les rares animaux à se reconnaître dans un miroir.",
    "La planète Saturne est si peu dense qu'elle flotterait dans une baignoire géante remplie d'eau.",
    "Le mot « salaire » viendrait du sel, autrefois précieux (l'origine exacte est discutée).",
    "Boire de l'eau aide à se concentrer : même une petite déshydratation fatigue le cerveau.",
    "Le premier jeu vidéo commercial à succès fut Pong, sorti en 1972.",
    "Les papillons goûtent avec leurs pattes.",
    "La Seine traverse Paris, mais elle prend sa source en Bourgogne, sur le plateau de Langres.",
    "Les cheveux poussent d'environ 1 cm par mois.",
    "Un mot de passe long (une phrase de 4 ou 5 mots) est bien plus difficile à deviner qu'un mot court compliqué.",
    "Le sommeil aide à mémoriser : le cerveau trie et range ce qu'on a appris pendant la journée.",
    "Les vaches ont des « meilleures amies » et sont plus calmes en leur présence.",
    "Le diamant et la mine de crayon (graphite) sont faits du même élément : le carbone.",
    "En japonais, « kawaii » signifie « mignon », et « baka » signifie « idiot ».",
    "Le piano a 88 touches : 52 blanches et 36 noires.",
    "Les étoiles qu'on voit la nuit sont presque toutes dans notre propre galaxie.",
    "Marcher 30 minutes par jour suffit à améliorer nettement la santé du cœur.",
    "Les manchots empereurs supportent des températures de -40 °C en se serrant les uns contre les autres.",
    "La musique active le circuit de la récompense du cerveau, comme la nourriture.",
    "Le sable des plages est souvent fait de petits morceaux de roche et de coquillages usés par les vagues.",
    "Une heure de sommeil en moins peut réduire l'attention le lendemain, même si on ne le sent pas.",
    "Les ordinateurs comptent en binaire : avec seulement des 0 et des 1.",
    "Le plus grand animal ayant jamais vécu est la baleine bleue, plus grande que les dinosaures connus.",
    "Une tige de basilic ou de menthe posée dans un verre d'eau fait de nouvelles racines en quelques jours.",
    "L'œil humain peut distinguer environ un million de couleurs.",
    "Le Sahara n'a pas toujours été un désert : il était vert il y a environ 6 000 ans.",
    "Le mot « bug » en informatique vient en partie d'un vrai papillon de nuit coincé dans un ordinateur en 1947.",
    "Les corbeaux savent utiliser des outils et reconnaître des visages humains.",
    "Le hérisson a environ 5 000 piquants.",
    "La Terre ne tourne pas en exactement 24 heures : un jour sidéral dure environ 23 h 56 min.",
    "Sourire, même un peu forcé, peut légèrement améliorer l'humeur.",
    "Les tomates étaient considérées comme décoratives (voire suspectes) en Europe avant d'être mangées.",
    "La mémoire vive (RAM) s'efface quand on éteint l'ordinateur, contrairement au disque.",
    "Le premier manga moderne est souvent associé à Osamu Tezuka, « le dieu du manga ».",
    "Les chouettes ne peuvent pas bouger leurs yeux : elles tournent la tête jusqu'à environ 270 degrés.",
    "Le sel de table est fait de sodium et de chlore, deux éléments dangereux séparément.",
    "Rire 10 minutes, c'est un peu d'exercice : les abdos et le diaphragme travaillent.",
    "Les chiens peuvent comprendre plus de 150 mots pour les plus doués.",
    "L'Antarctique est le plus grand désert du monde : il y tombe très peu de précipitations.",
    "Le bambou peut pousser de plusieurs dizaines de centimètres en une seule journée.",
    "Une sauvegarde n'est vraiment sûre que si elle existe à deux endroits différents.",
]

# ================================================================== un peu de sport (doux, sans matériel)
SPORT = [
    ("Étirements du cou", "Penche doucement la tête à droite 15 secondes, puis à gauche. Sans forcer !"),
    ("Épaules", "Fais 10 grands cercles avec les épaules vers l'arrière, puis 10 vers l'avant."),
    ("Debout !", "Lève-toi et marche 2 minutes, même juste dans la pièce. Ton dos te dira merci."),
    ("Squats", "10 squats tranquilles : pieds écartés, on descend comme pour s'asseoir, dos droit."),
    ("Mollets", "Monte sur la pointe des pieds 15 fois, doucement. Ça réveille les jambes."),
    ("Respiration", "Inspire 4 secondes, bloque 4 secondes, souffle 6 secondes. Recommence 5 fois."),
    ("Les poignets", "Tourne les poignets 10 fois dans chaque sens et écarte bien les doigts. Parfait pour les gamers !"),
    ("Le dos", "Debout, bras en l'air, étire-toi vers le plafond 10 secondes, puis penche-toi doucement en avant."),
    ("Les yeux", "Règle 20-20-20 : regarde au loin (à plus de 6 mètres) pendant 20 secondes."),
    ("Pompes contre le mur", "10 pompes contre un mur : facile et bon pour les bras."),
    ("Marche", "Et si on allait marcher 10 minutes dehors ? Un peu d'air frais, ça fait du bien."),
    ("Fentes", "5 fentes avant de chaque côté, doucement. Garde le genou au-dessus du pied."),
    ("Gainage", "Planche sur les avant-bras : 20 secondes. Si c'est dur, pose les genoux."),
    ("Hanches", "Debout, fais 10 cercles avec les hanches dans chaque sens. Ça décoince !"),
    ("Escaliers", "Si tu as des escaliers, monte-les une fois tranquillement. Sinon, 30 secondes de marche sur place."),
    ("Jumping jacks", "20 jumping jacks légers (ou sans sauter si tu as des voisins en dessous)."),
    ("Étirement des bras", "Croise un bras devant toi et tire-le doucement avec l'autre, 15 secondes de chaque côté."),
    ("Équilibre", "Tiens-toi sur un pied 20 secondes, puis sur l'autre. Plus dur les yeux fermés !"),
    ("Danse", "Mets ta musique préférée et bouge pendant une chanson. Je danse avec toi !"),
    ("Le dos assis", "Assis, tourne doucement le buste à droite en t'aidant du dossier, 10 secondes, puis à gauche."),
    ("Verre d'eau", "Va boire un grand verre d'eau : ça compte comme une pause active !"),
]

# ================================================================== blagues (tout public)
BLAGUES = [
    "Qu'est-ce qu'un crocodile qui surveille la pharmacie ? Un Lacoste garde.",
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tombent dans le bateau.",
    "Que dit une imprimante dans l'eau ? J'ai papier.",
    "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël.",
    "Qu'est-ce qu'un yaourt dans la forêt ? Un yaourt nature.",
    "Pourquoi les poissons détestent l'ordinateur ? Parce qu'ils ont peur du net.",
    "Quel est le comble pour un électricien ? De ne pas être au courant.",
    "Que fait une fraise sur un cheval ? Tagada tagada !",
    "Pourquoi le livre de maths est triste ? Parce qu'il a trop de problèmes.",
    "Qu'est-ce qui est jaune et qui attend ? Jonathan.",
    "Quel est le sport préféré des insectes ? Le cricket.",
    "Comment fait-on aboyer un chat ? On lui donne une tasse de lait, et il la boit.",
    "Que dit un oignon quand il se cogne ? Aïe.",
    "Pourquoi les canards sont toujours à l'heure ? Parce qu'ils sont dans l'étang.",
    "Quel est le comble pour un jardinier ? De raconter des salades.",
    "Qu'est-ce qu'un développeur dit en sortant de la douche ? « Ça marche sur ma machine. »",
    "Pourquoi les programmeurs confondent Halloween et Noël ? Parce que Oct 31 = Dec 25.",
    "Combien de développeurs faut-il pour changer une ampoule ? Aucun, c'est un problème matériel.",
    "Que dit un escargot quand il croise une limace ? « Oh, un nudiste ! »",
    "Pourquoi les vaches ferment-elles les yeux pendant la traite ? Pour faire du lait concentré.",
    "Quel est le fruit préféré des profs d'histoire ? Les dattes.",
    "Qu'est-ce qu'une manette de jeu dit à la console ? « Je te tiens. »",
    "Pourquoi l'ordinateur va chez le médecin ? Il a attrapé un virus.",
    "Que fait un geek quand il a froid ? Il se met dans un coin, parce qu'il y fait 90 degrés.",
    "Quel est le comble pour un pianiste ? De perdre la clé de sol.",
    "Que dit le zéro au huit ? « Jolie ceinture ! »",
    "Pourquoi les fantômes sont de mauvais menteurs ? Parce qu'on voit à travers eux.",
    "Qu'est-ce qui a des dents mais ne mord jamais ? Un peigne.",
    "Pourquoi le citron ne répond jamais ? Parce qu'il est pressé.",
    "Qu'est-ce qui est petit, carré et jaune ? Un petit carré jaune.",
    "Comment appelle-t-on un boomerang qui ne revient pas ? Un bâton.",
    "Que dit un vampire après son dîner ? « C'était sanguinaire ! »",
    "Pourquoi le squelette ne va jamais à la fête ? Parce qu'il n'a personne avec qui y aller.",
    "Qu'est-ce qu'un chameau à trois bosses ? Un chameau qui s'est cogné.",
    "Pourquoi les maths aiment la forêt ? À cause des racines carrées.",
    "Quelle est la boisson préférée des profs de physique ? Le thé… orème.",
    "Que dit une goutte d'eau à une autre ? « On se reverra en mer ! »",
    "Comment appelle-t-on un chien sans pattes ? On ne l'appelle pas, on va le chercher.",
    "Pourquoi le soleil ne va pas à l'école ? Parce qu'il a déjà des millions de degrés.",
    "Quel est l'oiseau le plus heureux ? Le hibou, parce que sa femme est chouette.",
]

# ================================================================== repas pas chers, faciles, équilibrés
# (nom, minutes, budget indicatif par personne, ingrédients, étapes, pourquoi c'est bien)
REPAS = [
    ("Omelette aux légumes", 15, "≈ 1,5 €", ["3 œufs", "1 poivron ou 1 courgette", "1 oignon", "un peu de fromage râpé"],
     ["Coupe les légumes en petits morceaux et fais-les revenir 5 min dans un peu d'huile.",
      "Bats les œufs avec sel et poivre, verse sur les légumes.", "Laisse cuire à feu doux 4-5 min, ajoute le fromage."],
     "Des protéines, des légumes, et c'est prêt en 15 minutes."),
    ("Pâtes à la sauce tomate et thon", 15, "≈ 1,5 €", ["100 g de pâtes complètes", "1 petite boîte de thon",
                                                         "200 g de coulis de tomate", "1 gousse d'ail, origan"],
     ["Fais cuire les pâtes.", "Fais chauffer le coulis avec l'ail et l'origan, ajoute le thon émietté.",
      "Mélange avec les pâtes."], "Pâtes complètes = énergie qui dure ; le thon apporte des protéines."),
    ("Dahl de lentilles corail", 25, "≈ 1 €", ["100 g de lentilles corail", "1 oignon", "200 ml de lait de coco "
                                                "(ou d'eau)", "1 c. à café de curry", "riz"],
     ["Fais revenir l'oignon avec le curry.", "Ajoute les lentilles rincées et 2 fois leur volume d'eau.",
      "Cuis 15 min, ajoute le lait de coco, sers avec du riz."], "Les lentilles : protéines et fibres, très pas cher."),
    ("Riz sauté aux œufs et petits pois", 15, "≈ 1,2 €", ["1 bol de riz cuit (idéalement de la veille)", "2 œufs",
                                                          "1 poignée de petits pois surgelés", "sauce soja"],
     ["Fais sauter les petits pois 3 min.", "Ajoute le riz, puis les œufs battus en remuant.",
      "Assaisonne avec un peu de sauce soja."], "Parfait pour finir un reste de riz ; complet et rapide."),
    ("Soupe de légumes maison", 30, "≈ 1 €", ["2 carottes", "2 pommes de terre", "1 poireau ou 1 oignon", "1 cube de "
                                                                                                      "bouillon"],
     ["Coupe les légumes en morceaux.", "Couvre d'eau avec le bouillon et cuis 20 min.", "Mixe."],
     "Plein de légumes pour presque rien, et ça se garde 3 jours au frigo."),
    ("Chili sin carne", 30, "≈ 1,5 €", ["1 boîte de haricots rouges", "1 boîte de tomates concassées", "1 oignon",
                                        "maïs", "cumin, paprika", "riz"],
     ["Fais revenir l'oignon avec les épices.", "Ajoute tomates, haricots égouttés et maïs, laisse mijoter 15 min.",
      "Sers avec du riz."], "Haricots + riz = protéines complètes, sans viande."),
    ("Wrap poulet-crudités", 10, "≈ 2 €", ["1 tortilla", "quelques tranches de poulet (ou du thon)", "salade, tomate",
                                           "1 c. de fromage frais"],
     ["Tartine la tortilla de fromage frais.", "Ajoute le poulet et les crudités.", "Roule bien serré."],
     "Sans cuisson, idéal quand tu as la flemme."),
    ("Poêlée de pommes de terre, œuf au plat", 25, "≈ 1,2 €", ["2 pommes de terre", "1 oignon", "1 ou 2 œufs",
                                                               "herbes de Provence"],
     ["Coupe les pommes de terre en dés, fais-les dorer 15-20 min.", "Ajoute l'oignon et les herbes.",
      "Termine avec un œuf au plat par-dessus."], "Simple, rassasiant, et les œufs apportent les protéines."),
    ("Salade de pois chiches", 10, "≈ 1,5 €", ["1 boîte de pois chiches", "1 tomate", "1/2 concombre", "huile d'olive, "
                                                                                                    "citron"],
     ["Rince les pois chiches.", "Coupe les légumes, mélange.", "Assaisonne avec huile, citron, sel, poivre."],
     "Fibres et protéines végétales, parfait l'été."),
    ("Gratin de courgettes", 35, "≈ 1,8 €", ["2 courgettes", "2 œufs", "10 cl de crème ou de lait", "fromage râpé"],
     ["Coupe les courgettes en rondelles, mets-les dans un plat.", "Verse les œufs battus avec la crème.",
      "Ajoute le fromage et enfourne 25 min à 200 °C."], "Plein de légumes, et ça plaît même aux difficiles."),
    ("Croque-monsieur et salade", 15, "≈ 1,5 €", ["4 tranches de pain de mie (complet si possible)", "2 tranches de "
                                                                                                  "jambon", "fromage",
                                                  "salade verte"],
     ["Monte les croques.", "Fais-les dorer à la poêle ou au four 8 min.", "Sers avec une salade."],
     "Avec la salade, ça devient un vrai repas équilibré."),
    ("Riz au curry de légumes", 25, "≈ 1,3 €", ["riz", "légumes surgelés (mélange wok)", "1 c. de curry", "un peu de "
                                                                                                    "lait de coco"],
     ["Lance le riz.", "Fais sauter les légumes avec le curry.", "Ajoute le lait de coco, mijote 5 min."],
     "Les légumes surgelés sont aussi bons pour la santé que les frais, et moins chers."),
    ("Pain perdu salé", 15, "≈ 1 €", ["pain rassis", "2 œufs", "un peu de lait", "fromage râpé", "tomates cerises"],
     ["Trempe le pain dans œufs + lait.", "Fais dorer à la poêle.", "Ajoute fromage et tomates en fin de cuisson."],
     "Anti-gaspi : le pain rassis devient un bon repas."),
    ("Bol de flocons d'avoine (petit-déj')", 5, "≈ 0,6 €", ["50 g de flocons d'avoine", "lait ou boisson végétale",
                                                            "1 banane", "1 pincée de cannelle"],
     ["Fais chauffer les flocons avec le lait 3 min.", "Ajoute la banane écrasée et la cannelle."],
     "Énergie qui dure toute la matinée, pour pas cher."),
    ("Quesadillas aux haricots", 15, "≈ 1,5 €", ["2 tortillas", "1/2 boîte de haricots rouges", "fromage râpé",
                                                 "1/2 poivron"],
     ["Écrase un peu les haricots.", "Garnis une tortilla de haricots, poivron et fromage, couvre avec l'autre.",
      "Fais dorer 3 min de chaque côté."], "Fibres et protéines, et c'est fun à manger."),
    ("Saumon (ou maquereau) en boîte, riz et brocoli", 20, "≈ 2 €",
     ["1 boîte de maquereau ou de saumon", "riz", "brocoli (frais ou surgelé)", "citron"],
     ["Cuis le riz et le brocoli à la vapeur ou à l'eau.", "Ajoute le poisson et un filet de citron."],
     "Le poisson gras en boîte apporte des oméga-3 pour vraiment pas cher."),
]


# ================================================================== défi de la semaine
DEFIS = [
    ("eau", "Boire au moins 6 verres d'eau par jour"),
    ("marche", "Marcher au moins 20 minutes par jour"),
    ("sport", "Faire 3 petites pauses sport par jour"),
    ("lecture", "Lire 15 minutes par jour (livre, manga, BD… loin des réseaux)"),
    ("dodo", "Se coucher avant minuit"),
    ("ecran", "Une heure sans écran avant de dormir"),
    ("legumes", "Manger des légumes ou des fruits à chaque repas"),
    ("rangement", "Ranger 5 minutes par jour (bureau, chambre, fichiers)"),
    ("gratitude", "Écrire 3 choses positives de la journée dans le journal"),
    ("appel", "Prendre des nouvelles d'un proche (message ou appel)"),
]


def defi_de_la_semaine(semaine):
    r = random.Random(f"defi{semaine}")
    return r.choice(DEFIS)


def quiz_prompt(texte, n=5, sujet="ces faits"):
    return [{"role": "system", "content": "Tu crées des quiz courts, justes et clairs, en français."},
            {"role": "user", "content": f"Crée {n} questions à choix multiple sur {sujet}, à partir UNIQUEMENT de ce "
             "texte (rien d'inventé). Trois choix par question, une seule bonne réponse. Réponds seulement en JSON : "
             '{"questions": [{"q": "question", "choix": ["A", "B", "C"], "bonne": 0}]}\n\nTexte :\n' + texte[:6000]}]


def fiche_prompt(texte):
    return ("Fais une fiche de révision claire de ce cours, en français : les idées principales en points courts, "
            "les définitions importantes, les dates ou formules à retenir, puis 3 questions pour s'entraîner. "
            "Seulement ce qui est dans le texte.\n\n" + texte[:8000])


def _seed_day(salt=""):
    d = datetime.date.today()
    return random.Random(f"{d.isoformat()}{salt}")


def fait_du_jour(vus=()):
    """Une chose apprise par jour, sans répéter avant d'avoir tout vu. -> (index, texte)."""
    reste = [i for i in range(len(FAITS)) if i not in set(vus)] or list(range(len(FAITS)))
    i = _seed_day("fait").choice(reste)
    return i, FAITS[i]


def sport():
    return random.choice(SPORT)


def blague(vues=()):
    reste = [i for i in range(len(BLAGUES)) if i not in set(vues)] or list(range(len(BLAGUES)))
    i = random.choice(reste)
    return i, BLAGUES[i]


def repas(rapide=False):
    pool = [r for r in REPAS if r[1] <= 15] if rapide else REPAS
    return random.choice(pool)


def recette_texte(r):
    nom, mins, budget, ingr, etapes, pourquoi = r
    return (f"{nom}\n⏱ {mins} min · 💶 {budget} par personne (prix indicatif)\n\n"
            "Ingrédients (1 personne) :\n" + "\n".join("• " + x for x in ingr) +
            "\n\nÉtapes :\n" + "\n".join(f"{k}. {e}" for k, e in enumerate(etapes, 1)) +
            f"\n\nPourquoi c'est bien : {pourquoi}")


def ai_fact_prompt(sujet=""):
    return ("Apprends-moi une chose vraie et étonnante" + (f" sur : {sujet}" if sujet else "") +
            ", en 2 ou 3 phrases simples, en français. Uniquement un fait bien établi, que tu es sûre d'être "
            "vrai ; si tu n'es pas sûre, choisis un autre fait. Pas d'introduction.")


def ai_meal_prompt(contraintes=""):
    return ("Propose UN repas pour une personne : pas cher, facile (moins de 30 min), équilibré" +
            (f", avec cette contrainte : {contraintes}" if contraintes else "") +
            ". Donne : le nom, le temps, les ingrédients (liste courte), les étapes (3 à 5), en français, "
            "sans prix exact.")
