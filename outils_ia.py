"""🧰 Les outils de son IA : quand tu lui demandes quelque chose avec tes propres mots (« tu peux me rappeler
d'appeler maman demain à 18h ? », « mets un peu de musique », « range mes téléchargements »), son IA choisit
la bonne fonction de Viki et la lance.

Règles :
  - ce qui change quelque chose (ranger, sauvegarder, éteindre…) est TOUJOURS demandé avant (« Je le fais ? ») ;
  - si aucune fonction ne colle, on discute normalement ;
  - rien ne part sur Internet pour ça (sauf si tu as choisi une IA en ligne).
"""
import datetime
import json
import re

# fonctions qui changent quelque chose : on demande d'abord
RISQUE = {"ranger", "sauvegarde", "sauver", "menage", "nettoyer", "veille", "eteindre", "redemarrer", "maj", "mises_a_jour",
          "vider", "corbeille", "supprimer", "tor", "jeu_mode", "nuit_mode", "desinstaller", "installer", "snooze",
          "ports", "dns", "proxy"}
MOTS_RISQUE = re.compile(r"ranger|range|sauvegard|menage|nettoy|supprim|efface|vider|eteind|redemarr|install|"
                         r"desinstall|mise.? a jour|update|veille", re.I)

# outils avec des paramètres (en plus des fonctions des menus)
SPECIAUX = [
    ("rappel", 'créer un rappel ; args : {"texte": "…", "quand": "AAAA-MM-JJ HH:MM"}'),
    ("minuteur", 'lancer un minuteur ; args : {"minutes": 10, "texte": "les pâtes"}'),
    ("musique", 'contrôler la musique en cours ; args : {"commande": "play|pause|next|previous|titre"}'),
    ("ouvrir_appli", 'ouvrir une application installée ; args : {"nom": "firefox"}'),
    ("ouvrir_site", 'ouvrir une adresse web demandée explicitement ; args : {"url": "https://…"}'),
    ("guide", 'montrer quelque chose sur l\'écran (entourer, souligner, expliquer) ; args : {"question": "…"}'),
    ("fichiers", 'répondre d\'après les fichiers/notes de l\'utilisateur ; args : {"question": "…"}'),
    ("trouver_fichier", 'retrouver un fichier par son nom ; args : {"nom": "…"}'),
    ("note", 'noter quelque chose dans ses notes ; args : {"texte": "…"}'),
    ("echeance", 'une chose à faire avant une date (rappels 3 jours avant, la veille, le jour même) ; '
                 'args : {"texte": "payer l\'électricité", "date": "AAAA-MM-JJ"}'),
    ("reviser", 'réviser un sujet (quiz) ou faire une fiche ; args : {"sujet": "…", "mode": "quiz|fiche"}'),
    ("expliquer_commande", 'expliquer une commande de terminal ; args : {"commande": "…"}'),
    ("courses", 'ajouter à la liste de courses ; args : {"articles": ["lait", "œufs"]}'),
]

RX_DEMANDE = re.compile(
    r"^(?:viki,? )?(?:(?:bon|alors|stp|s.il te plait|hey|dis),? )*(?:"
    r"peux[- ]tu|tu peux|pourrais[- ]tu|tu pourrais|est[- ]ce que tu (?:peux|pourrais)|j.aimerais|je voudrais|"
    r"je veux|il faut|aide[- ]moi|rappelle|mets|met|remets|ouvre|lance|joue|range|cherche|trouve|retrouve|montre|"
    r"affiche|cree|fais|fait|prepare|note|ajoute|enleve|supprime|arrete|coupe|baisse|monte|passe|change|active|"
    r"desactive|demarre|programme|planifie|organise|nettoie|sauvegarde|verifie|occupe[- ]toi|"
    r"can you|could you|would you|please|i want|i.d like|remind me|i have to|i need to|i must|set|open|play|start|stop|find|show|add|make|"
    r"turn|check|clean|organi[sz]e)\b", re.I)


RX_SUITE = re.compile(r"^(?:et (?:pour |avec |si |demain|apres|maintenant|l.autre|celui|celle|le |la |les |ca)|pareil|"
                      r"refais|recommence|encore|aussi|idem|la meme|le meme|meme chose|fais[- ]le|ouvre[- ]le|"
                      r"ouvre[- ]la|lance[- ]le|mets[- ]le|ferme[- ]le|annule|plutot|non,? |pas (?:ca|celui)|"
                      r"and (?:for|tomorrow|the other)|same|again|do it)\b", re.I)


def semble_suite(ta):
    """« et demain ? », « refais pareil », « ouvre-le »… : une suite de la demande d'avant."""
    return len(ta.split()) <= 10 and bool(RX_SUITE.search(ta))


def semble_demande(ta):
    """ta : le message en minuscules sans accents. Une demande d'action (et pas une question de culture) ?"""
    if len(ta) > 220 or len(ta.split()) < 2:
        return False
    if re.match(r"^(?:peux[- ]tu|tu peux|pourrais[- ]tu|can you|could you) (?:m.)?(?:expliquer|explain|dire|tell|"
                r"raconter|parler|definir|traduire|resumer)\b", ta):
        return False                                     # « tu peux m'expliquer… » : c'est de la discussion
    return bool(RX_DEMANDE.search(ta))


def catalogue(actions):
    """Les lignes « id : nom (mots) » des fonctions des menus, sans doublons."""
    vus, out = set(), []
    for a in actions:
        if a["id"] in vus:
            continue
        vus.add(a["id"])
        out.append(f"{a['id']} : {a['nom']}" + (f" ({a['mots'][:60]})" if a.get("mots") else ""))
    return out


def consigne(message, actions, langue="français", contexte=""):
    maintenant = datetime.datetime.now().strftime("%A %Y-%m-%d %H:%M")
    spe = "\n".join(f"{k} : {d}" for k, d in SPECIAUX)
    cat = "\n".join(catalogue(actions))
    return (
        "Tu es le « routeur » de Viki, une compagne de bureau. Choisis la fonction de Viki qui fait ce que "
        "l'utilisateur demande, s'il y en a une. Sinon, outil = null (on discutera normalement).\n"
        f"Maintenant : {maintenant}.\n\n"
        "Outils avec paramètres :\n" + spe + "\n\nFonctions des menus (sans paramètre) :\n" + cat + "\n\n"
        + (f"Contexte (pour comprendre les suites : « et demain ? », « refais pareil », « ouvre-le »…) :\n{contexte}\n\n"
           if contexte else "") +
        f"Message : « {message} »\n\n"
        "Réponds UNIQUEMENT en JSON : "
        '{"outil": "id ou null", "args": {}, "dire": "une phrase courte, en ' + langue + ', qui dit ce que tu fais"}\n'
        "Si la demande est une question de culture, un avis, une conversation : outil = null.")


def lire(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    o = d.get("outil")
    if not o or str(o).lower() in ("null", "none", "aucun"):
        return None
    args = d.get("args") if isinstance(d.get("args"), dict) else {}
    return {"outil": str(o).strip(), "args": args, "dire": str(d.get("dire") or "").strip()[:200]}


def risque(outil, args, nom=""):
    if outil in RISQUE:
        return True
    return bool(MOTS_RISQUE.search(outil + " " + nom))


def quand(texte):
    """« AAAA-MM-JJ HH:MM » (ou « HH:MM ») -> horodatage, ou None."""
    texte = (texte or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%H:%M"):
        try:
            d = datetime.datetime.strptime(texte, fmt)
            if fmt == "%H:%M":
                now = datetime.datetime.now()
                d = now.replace(hour=d.hour, minute=d.minute, second=0, microsecond=0)
                if d <= now:
                    d += datetime.timedelta(days=1)
            return d.timestamp()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ le presse-papiers malin
_MOTS = {
    "fr": set("le la les des une est et que qui pas pour dans sur avec mais vous nous je tu il elle ce cette sont".split()),
    "en": set("the and is are you that this with for not have was what your they will from but".split()),
    "es": set("el los las una que por con para pero esta como del muy hay ser tiene".split()),
    "de": set("der die das und ist nicht ich sie mit auf für ein eine sich dem den wir".split()),
    "it": set("il che per una sono della non come anche nel delle questo gli".split()),
    "pt": set("que não uma para com por mais como dos das você está são".split()),
}
RX_ERREUR = re.compile(r"Traceback \(most recent call last\)|^\s*(?:\w+Error|\w+Exception)\b|\berror(?:\[E\d+\])?:|"
                       r"\bfatal:|\bpanicked at\b|Segmentation fault|command not found|No such file or directory|"
                       r"Permission denied|\bFAILED\b|npm ERR!|E: (?:Unable|Impossible)|erreur ?:", re.I | re.M)
RX_ADRESSE = re.compile(r"^\s*\d{1,4}\s*(?:bis|ter)?,?\s+(?:rue|avenue|av\.|boulevard|bd|place|chemin|route|allée|allee|"
                        r"impasse|quai|cours|street|st\.|road|rd\.|avenue|lane|calle|via)\b.{3,80}$", re.I | re.S)


def langue_de(txt):
    ws = re.findall(r"[a-zà-ÿ]+", txt.lower())
    if len(ws) < 6:
        return ""
    sc = {k: sum(1 for w in ws if w in v) for k, v in _MOTS.items()}
    best = max(sc, key=sc.get)
    if sc[best] < 3 or sc[best] < 0.08 * len(ws):
        return ""
    return best


def genre_copie(txt, ma_langue="fr"):
    """« erreur », « adresse », « etranger » ou ""."""
    if len(txt) < 6:
        return ""
    if RX_ERREUR.search(txt) and len(txt) < 6000:
        return "erreur"
    if len(txt) < 140 and txt.count("\n") <= 3 and RX_ADRESSE.search(txt.replace("\n", " ")):
        return "adresse"
    code = sum(c in "{}();=<>[]_$\\/|#" for c in txt) / max(1, len(txt))
    if 30 <= len(txt) <= 6000 and code < 0.03 and not re.search(r"https?://\S+$", txt):
        lg = langue_de(txt)
        if lg and lg != ma_langue:
            return "etranger"
    return ""
