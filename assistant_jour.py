"""Les petites intelligences du quotidien (sans dépendance, tout en local) :
mails importants, échéances (« je dois payer X avant le 10 »), secrets copiés, commandes dangereuses,
fichier téléchargé (est-il sûr ?), humeur du jour, disposition des fenêtres.
"""
import datetime
import math
import os
import re
import shutil
import stat
import subprocess
import unicodedata
from pathlib import Path


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


# ================================================================== mails importants
IMPORTANT = [
    (r"factur|invoice|echeanc|a payer|paiement|prelevement|impaye|relance|payment due", "une facture ou un paiement"),
    (r"rendez[- ]vous|\brdv\b|convocation|appointment|reservation confirmee|entretien", "un rendez-vous"),
    (r"urgent|important|immediat|asap|action requise|action required", "quelque chose d'urgent"),
    (r"colis|livraison|expedie|delivery|shipped|votre commande", "une livraison"),
    (r"impots|caf\b|ameli|cpam|pole emploi|france travail|urssaf|banque|bank", "un organisme important"),
    (r"(?:^|\W)re ?:|reponse|reply", "une réponse à un de tes messages"),
]
PUB = re.compile(r"newsletter|promo|soldes|offre|unsubscribe|desabonner|noreply|no-reply|% de reduction|black friday",
                 re.I)


def importance(m):
    """m : {"de", "sujet", "corps"?} -> (score 0..3, raison)."""
    t = _sa(f"{m.get('sujet', '')} {m.get('de', '')} {(m.get('corps') or '')[:400]}")
    if PUB.search(t) and not re.search(r"factur|rendez|urgent|colis", t):
        return 0, ""
    for i, (rx, raison) in enumerate(IMPORTANT):
        if re.search(rx, t):
            return (3 if i < 3 else 2), raison
    return 1, ""


# ================================================================== échéances
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
RX_ECHEANCE = re.compile(
    r"^(?:il faut que je|je dois|faut que je|j.ai (?:a|jusqu.au .{1,20} pour)|n.oublie pas que je dois|je dois absolument)\s+"
    r"(.{3,80}?)\s+(?:avant|d.ici|pour|au plus tard)\s+(?:le\s+)?(.{1,25})$", re.I)


def date_de(txt, today=None):
    """« le 10 », « 10/12 », « 12 décembre », « vendredi », « la fin du mois », « demain » -> date ou None."""
    today = today or datetime.date.today()
    t = _sa(txt).strip(" .!?")
    if t == "demain":
        return today + datetime.timedelta(days=1)
    if re.fullmatch(r"(?:la )?fin du mois", t):
        d = (today.replace(day=28) + datetime.timedelta(days=4))
        return d - datetime.timedelta(days=d.day)
    if t in JOURS:
        n = (JOURS[t] - today.weekday()) % 7 or 7
        return today + datetime.timedelta(days=n)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
    mois_donne = True
    if m:
        j, mo = int(m.group(1)), int(m.group(2))
        an = int(m.group(3)) if m.group(3) else today.year
        an += 2000 if an < 100 else 0
    else:
        m = re.fullmatch(r"(\d{1,2})(?:er)?(?: ([a-z]+))?", t)
        if not m:
            return None
        j = int(m.group(1))
        mois_donne = bool(m.group(2))
        mo = MOIS.get(m.group(2), 0) if mois_donne else today.month
        if not mo:
            return None
        an = today.year
    try:
        d = datetime.date(an, mo, j)
    except ValueError:
        return None
    if d < today:
        if mois_donne:                                  # « le 3 mars » passé : l'an prochain
            d = d.replace(year=d.year + 1)
        else:                                           # « le 10 » passé : le mois prochain
            an2, mo2 = (an + 1, 1) if mo == 12 else (an, mo + 1)
            try:
                d = datetime.date(an2, mo2, j)
            except ValueError:
                return None
    return d


def echeance(texte):
    """« je dois payer l'électricité avant le 10 » -> (« payer l'électricité », date) ou None."""
    orig = unicodedata.normalize("NFC", (texte or "").strip().rstrip(" .!?"))
    sa = _sa(orig)
    if len(sa) != len(orig):
        orig = sa
    m = RX_ECHEANCE.match(sa)
    if not m:
        return None
    d = date_de(m.group(2))
    if not d:
        return None
    quoi = re.sub(r"^(?:de |d')", "", orig[m.start(1):m.end(1)]).strip()
    return quoi, d


def rappels_echeance(quoi, d, maintenant=None):
    """Quand la prévenir : 3 jours avant, la veille et le matin même (à 9h), seulement dans le futur."""
    maintenant = maintenant or datetime.datetime.now()
    out = []
    for avant, txt in ((3, f"Dans 3 jours : {quoi}"), (1, f"Demain, dernier délai : {quoi}"), (0, f"Aujourd'hui : {quoi} !")):
        t = datetime.datetime.combine(d - datetime.timedelta(days=avant), datetime.time(9, 0))
        if t > maintenant:
            out.append((t.timestamp(), txt))
    return out


# ================================================================== secrets copiés
RX_SECRET = re.compile(r"^(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{30,}|github_pat_\w{20,}|glpat-[\w-]{16,}|"
                       r"AKIA[0-9A-Z]{16}|xox[abpr]-[\w-]{10,}|AIza[\w-]{30,}|hf_[A-Za-z0-9]{30,}|"
                       r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def ressemble_secret(txt):
    """Une clé d'API, une clé privée, ou un mot de passe (un seul « mot » mélangé, court) ?"""
    t = (txt or "").strip()
    if not t or len(t) > 4000:
        return False
    if RX_SECRET.search(t):
        return True
    if "\n" in t or " " in t or not 10 <= len(t) <= 64:
        return False
    if re.match(r"^(?:https?://|www\.|/|~|[\w.+-]+@[\w-]+\.)", t):
        return False
    classes = sum(bool(re.search(p, t)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w]"))
    if classes < 3:
        return False
    freq = {c: t.count(c) for c in set(t)}
    ent = -sum(n / len(t) * math.log2(n / len(t)) for n in freq.values())
    return ent >= 3.2


# ================================================================== commandes dangereuses
DANGERS = [
    (r"\brm\s+(?:-\w*[rf]\w*\s+)+(?:/|~|\$HOME|/\*|\*)(?:\s|$)", "efface tout (le système ou ton dossier personnel)"),
    (r"\brm\s+-\w*r\w*f|\brm\s+-\w*f\w*r", "supprime des dossiers entiers sans demander (pas de corbeille)"),
    (r"\bdd\b.*\bof=/dev/(?:sd|nvme|hd|mmcblk)", "écrit directement sur un disque : tout ce qu'il contient sera perdu"),
    (r"\bmkfs(?:\.\w+)?\b", "formate une partition : tout ce qu'elle contient sera effacé"),
    (r">\s*/dev/(?:sd|nvme|hd)\w*", "écrase un disque"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "« fork bomb » : bloque l'ordinateur"),
    (r"\bchmod\s+-R\s+0?777\s+/(?:\s|$)", "rend tout le système modifiable par n'importe qui"),
    (r"\bchown\s+-R\s+\S+\s+/(?:\s|$)", "change le propriétaire de tout le système"),
    (r"(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba|z|fi)?sh\b", "exécute un script venu d'Internet sans le lire"),
    (r"\bsudo\s+rm\b", "supprime des fichiers avec les droits administrateur"),
    (r"\b(?:shutdown|poweroff|reboot|halt)\b", "éteint ou redémarre l'ordinateur"),
    (r"\bgit\s+(?:push\s+.*--force|reset\s+--hard|clean\s+-\w*f)", "efface du travail git non sauvegardé"),
    (r"\bpacman\s+-R\w*\s|\bapt(?:-get)?\s+(?:remove|purge)\b|\bdnf\s+remove\b", "désinstalle des logiciels"),
    (r"\bmv\s+\S+\s+/dev/null\b", "fait disparaître un fichier"),
    (r"\bfind\b.*-delete\b", "supprime en masse des fichiers trouvés"),
    (r"\b(?:base64\s+-d|xxd\s+-r)\b.*\|\s*(?:ba)?sh\b", "exécute du code caché"),
]


def dangers(cmd):
    out = []
    for rx, msg in DANGERS:
        if re.search(rx, cmd or "") and msg not in out:
            out.append(msg)
    return out


# ================================================================== un fichier téléchargé est-il sûr ?
SUSPECT = [
    (r"(?:curl|wget)\b[^|\n]*\|\s*(?:ba)?sh", "télécharge et exécute un autre script"),
    (r"/dev/tcp/|\bnc\s+-e\b|\bncat\b.*-e|socat\b.*exec", "ouvre une connexion à distance (porte dérobée possible)"),
    (r"base64\s+-d|frombase64|eval\s*\(\s*(?:atob|base64)|exec\s*\(\s*base64", "contient du code caché (base64)"),
    (r"crontab\b|/etc/cron|systemctl\s+(?:--user\s+)?enable", "s'installe pour se relancer tout seul"),
    (r"\.ssh/(?:id_|authorized_keys)", "touche à tes clés SSH"),
    (r"\.mozilla|\.config/(?:google-chrome|chromium|BraveSoftware)|cookies\.sqlite|Login Data", "lit les données de tes navigateurs"),
    (r"\bsudo\b|pkexec", "demande les droits administrateur"),
    (r"\brm\s+-\w*r\w*f|\bshred\b", "supprime des fichiers"),
    (r"(?:xmrig|minerd|stratum\+tcp|cryptonight)", "ressemble à un mineur de cryptomonnaie"),
    (r"chmod\s+\+x\s+/tmp|/tmp/\.\w+", "cache et lance un programme dans /tmp"),
    (r"LD_PRELOAD|/etc/ld\.so\.preload", "modifie le chargement des programmes (technique de rootkit)"),
    (r"(?:discord|telegram)(?:app)?\.com/api/webhooks|api\.telegram\.org/bot", "envoie des données vers un salon Discord/Telegram"),
]
EXECUTABLES = {".sh", ".bash", ".zsh", ".fish", ".py", ".pl", ".rb", ".js", ".appimage", ".run", ".bin", ".deb",
               ".rpm", ".exe", ".msi", ".bat", ".cmd", ".ps1", ".jar", ".desktop", ".pkg.tar.zst", ".flatpakref"}


def analyse_fichier(path):
    """Analyse SANS l'exécuter. -> {"type", "taille", "executable", "alertes": [...], "texte": extrait lisible|""}"""
    p = Path(path)
    out = {"nom": p.name, "type": "", "taille": 0, "executable": False, "alertes": [], "texte": "", "clamav": ""}
    try:
        st = p.stat()
        out["taille"] = st.st_size
        out["executable"] = bool(st.st_mode & stat.S_IXUSR)
    except OSError:
        return out
    if shutil.which("file"):
        try:
            out["type"] = subprocess.run(["file", "-b", str(p)], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            pass
    ext = "".join(p.suffixes[-2:]).lower() if p.name.lower().endswith(".pkg.tar.zst") else p.suffix.lower()
    if ext in EXECUTABLES or out["executable"]:
        out["alertes"].append("c'est un programme : il peut tout faire sur ton PC si tu le lances")
    nom = p.name.lower()
    if re.search(r"\.(?:pdf|jpg|png|docx?|mp4|txt)\.(?:sh|exe|desktop|appimage|run|bat|js)$", nom):
        out["alertes"].append("double extension trompeuse : il se fait passer pour un document")
    lisible = "text" in out["type"] or ext in (".sh", ".bash", ".py", ".pl", ".rb", ".js", ".desktop", ".ps1", ".bat")
    if lisible and out["taille"] < 2_000_000:
        try:
            t = p.read_text("utf-8", "ignore")
        except Exception:
            t = ""
        out["texte"] = t[:12000]
        for rx, msg in SUSPECT:
            if re.search(rx, t, re.I) and msg not in out["alertes"]:
                out["alertes"].append(msg)
        if ext == ".desktop":
            m = re.search(r"^Exec=(.*)$", t, re.M)
            if m:
                out["alertes"].append("lance cette commande : " + m.group(1)[:120])
    elif out["taille"] < 400_000_000:                  # binaire : on cherche des chaînes suspectes
        try:
            with open(p, "rb") as f:
                data = f.read(8_000_000)
            chaines = " ".join(re.findall(rb"[ -~]{6,}", data)[:20000]).decode("ascii", "ignore")
            for rx, msg in SUSPECT:
                if rx.startswith(r"\bsudo") or rx.startswith(r"\brm"):
                    continue
                if re.search(rx, chaines, re.I) and msg not in out["alertes"]:
                    out["alertes"].append(msg)
        except Exception:
            pass
    if shutil.which("clamscan") and out["taille"] < 200_000_000:
        try:
            r = subprocess.run(["clamscan", "--no-summary", str(p)], capture_output=True, text=True, timeout=180)
            out["clamav"] = "virus trouvé : " + r.stdout.split(":")[-1].strip() if r.returncode == 1 else \
                "rien trouvé" if r.returncode == 0 else ""
        except Exception:
            pass
    return out


def verdict(a, trad=None):
    """-> (niveau 0 ok / 1 prudence / 2 danger, phrase). trad : traduit chaque alerte (langue de l'utilisateur)."""
    trad = trad or (lambda x: x)
    graves = [x for x in a["alertes"] if not x.startswith("c'est un programme") and not x.startswith("lance cette")]
    if a.get("clamav", "").startswith("virus"):
        return 2, "Attention : l'antivirus a trouvé un " + a["clamav"] + ". Ne l'ouvre pas !"
    if len(graves) >= 2 or any("porte dérobée" in x or "mineur" in x or "trompeuse" in x or "navigateurs" in x
                               for x in graves):
        return 2, "Je ne le lancerais pas : " + " ; ".join(trad(x) for x in graves[:3]) + "."
    if graves:
        return 1, "Prudence : " + trad(graves[0]) + ". Lance-le seulement si tu fais confiance à sa source."
    if a["alertes"]:
        return 1, "C'est un programme : rien de suspect dans ce que j'ai pu lire, mais lance-le seulement s'il vient " \
                  "d'une source de confiance."
    return 0, "Rien de suspect : ce n'est pas un programme, il ne peut rien faire tout seul."


# ================================================================== humeur du jour
HUMEURS = {
    "joyeuse": ["Je suis de super bonne humeur aujourd'hui !", "J'ai la pêche ce matin ! ✨"],
    "calme": ["Je me sens toute calme aujourd'hui.", "Journée douce, je trouve."],
    "pensive": ["Je suis un peu dans la lune aujourd'hui…", "Je rêvasse un peu ce matin."],
    "joueuse": ["J'ai envie de m'amuser aujourd'hui !", "Aujourd'hui j'ai envie de jouer !"],
    "fatiguee": ["J'ai un peu de mal à me réveiller…", "Petite fatigue ce matin, mais ça va aller !"],
    "contente_de_toi": ["Hier c'était chouette avec toi, je suis contente !", "On a passé une bonne journée hier, hein ?"],
}
ENVIES = {
    "joyeuse": ["J'ai envie qu'on écoute de la musique !", "Et si on faisait un petit jeu ?"],
    "calme": ["J'ai envie d'une petite pause thé…", "On ouvre la fenêtre ? Enfin… la tienne !"],
    "pensive": ["Tu me racontes un truc intéressant ?", "J'ai envie d'apprendre quelque chose de nouveau."],
    "joueuse": ["Une partie de quelque chose ? Allez !", "Je parie que je te bats à un jeu !"],
    "fatiguee": ["Je ferais bien une petite sieste…", "Un café pour moi aussi ?"],
    "contente_de_toi": ["On refait comme hier ?", "J'aime bien quand on passe du temps ensemble."],
}


def humeur_du_jour(meteo="", messages_hier=0, heure_hier_tard=False, graine=0):
    import random
    r = random.Random(graine)
    poids = {"joyeuse": 3, "calme": 3, "pensive": 2, "joueuse": 2, "fatiguee": 1, "contente_de_toi": 0}
    m = _sa(meteo)
    if any(k in m for k in ("soleil", "clair", "sun")):
        poids["joyeuse"] += 3
    if any(k in m for k in ("pluie", "rain", "nuage", "brouillard", "orage")):
        poids["calme"] += 2
        poids["pensive"] += 2
    if "neige" in m or "snow" in m:
        poids["joueuse"] += 4
    if messages_hier >= 15:
        poids["contente_de_toi"] += 5
    if heure_hier_tard:
        poids["fatiguee"] += 3
    tot = sum(poids.values())
    x = r.uniform(0, tot)
    for k, w in poids.items():
        x -= w
        if x <= 0:
            return k
    return "calme"


# ================================================================== ranger les fenêtres
def grille(n, x, y, w, h, gap=8):
    """n fenêtres côte à côte -> [(x, y, w, h)]."""
    if n <= 0:
        return []
    cols = 1 if n == 1 else 2 if n <= 4 else 3
    rows = math.ceil(n / cols)
    out = []
    for i in range(n):
        r, c = divmod(i, cols)
        nc = cols if r < rows - 1 or n % cols == 0 else n % cols
        cw = (w - gap * (nc + 1)) // nc
        rh = (h - gap * (rows + 1)) // rows
        out.append((x + gap + c * (cw + gap), y + gap + r * (rh + gap), cw, rh))
    return out


def raison_humeur(h, meteo="", ville=""):
    """Son humeur du matin, avec sa raison (sinon rien : pas d'humeur « dans le vide »)."""
    m = _sa(meteo)
    lieu = f" à {ville}" if ville else ""
    if h == "joyeuse" and any(k in m for k in ("soleil", "clair", "sun")):
        return f"Il fait beau{lieu}, ça me met de super bonne humeur !"
    if h in ("calme", "pensive") and any(k in m for k in ("pluie", "rain", "nuage", "brouillard")):
        return "Il fait gris aujourd'hui, je me sens toute calme."
    if h == "joueuse" and ("neige" in m or "snow" in m):
        return "Il neige ! J'ai envie de m'amuser aujourd'hui !"
    if h == "contente_de_toi":
        return "On a passé une super journée hier, je suis encore toute contente !"
    if h == "fatiguee":
        return "On s'est couchés tard hier… j'ai un peu de mal à me réveiller !"
    return ""
