"""Vie quotidienne (suite) : budget, humeur, anniversaires des proches, soins (médicaments, plantes, animaux)
avec confirmation, examens et planning de révision, musique. Tout reste dans un fichier sur ton PC.
"""
import datetime
import json
import os
import re
from pathlib import Path

STATE_FILE = None                         # fixé par compagnon.py : ~/.config/viki/vie.json

# ta musique (suggérée de temps en temps ; tu peux changer les liens dans les réglages)
MUSIQUE_CHAINE = "https://www.youtube.com/@korhyu"
MUSIQUE_DEV = "https://youtu.be/qGnJU3-6P24"

CATEGORIES = {"courses": "🛒", "restaurant": "🍔", "transport": "🚌", "loisirs": "🎮", "jeux": "🎮",
              "logement": "🏠", "factures": "🧾", "sante": "🩺", "vetements": "👕", "abonnements": "📺",
              "cadeaux": "🎁", "animaux": "🐾", "autre": "💶"}
CAT_MOTS = {"courses": r"courses?|supermarch|carrefour|leclerc|lidl|aldi|auchan|intermarch|bouffe|nourriture",
            "restaurant": r"resto|restaurant|mcdo|kebab|pizza|burger|cafe|boulangerie|uber ?eats|deliveroo",
            "transport": r"essence|carburant|train|sncf|bus|metro|navigo|taxi|uber|parking|peage",
            "loisirs": r"cine|cinema|concert|sortie|livre|manga|loisir",
            "jeux": r"jeux?|steam|playstation|xbox|nintendo|switch",
            "logement": r"loyer|logement|appart",
            "factures": r"facture|electricite|edf|gaz|internet|box|telephone|forfait|assurance",
            "sante": r"pharmacie|medecin|docteur|sante|mutuelle|dentiste",
            "vetements": r"vetement|habits?|chaussures?|fringues",
            "abonnements": r"netflix|spotify|abonnement|disney|crunchyroll|youtube premium|prime",
            "cadeaux": r"cadeau", "animaux": r"chat|chien|croquettes|veto|veterinaire"}


def _sa(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def load():
    try:
        s = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        s = {}
    for k, v in (("depenses", []), ("budget_mois", 0), ("humeur", {}), ("proches", []), ("soins", []),
                 ("examens", []), ("cours", {})):
        s.setdefault(k, v)
    return s


def save(s):
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


# ================================================================== budget
def parse_expense(text):
    """« j'ai dépensé 12,50 € en courses », « dépense 30 essence », « 8€ kebab » -> (montant, catégorie, libellé)."""
    t = _sa(text)
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur\b)?", t)
    if not m or not re.search(r"\b(depense|depenses|paye|payer|achete|claque|coute|€|euros?)\b|€", t):
        return None
    amount = float(m.group(1).replace(",", "."))
    if amount <= 0 or amount > 100000:
        return None
    rest = (t[:m.start()] + " " + t[m.end():])
    rest = re.sub(r"\b(j'?ai|je|depense\w*|paye\w*|achete\w*|claque|coute|pour|en|de|du|des|un|une|le|la|les|au|aux|"
                  r"euros?|eur|€|aujourd'?hui|hier)\b", " ", rest)
    label = re.sub(r"\s+", " ", rest).strip(" .,!?:") or "dépense"
    cat = next((c for c, pat in CAT_MOTS.items() if re.search(r"\b(?:" + pat + r")", label)), "autre")
    return round(amount, 2), cat, label[:40]


def add_expense(s, amount, cat, label):
    s["depenses"].append({"date": datetime.date.today().isoformat(), "montant": amount, "cat": cat, "libelle": label})
    s["depenses"] = s["depenses"][-2000:]
    save(s)


def month_total(s, month=None):
    month = month or datetime.date.today().strftime("%Y-%m")
    return sum(d["montant"] for d in s["depenses"] if d["date"].startswith(month))


def month_text(s, month=None):
    month = month or datetime.date.today().strftime("%Y-%m")
    ds = [d for d in s["depenses"] if d["date"].startswith(month)]
    if not ds:
        return f"Aucune dépense notée pour {month}. Dis-moi « j'ai dépensé 12 € en courses » et je compte pour toi."
    par = {}
    for d in ds:
        par[d["cat"]] = par.get(d["cat"], 0) + d["montant"]
    tot = sum(par.values())
    lignes = [f"{CATEGORIES.get(k, '💶')} {k} : {v:.2f} €  ({v * 100 / tot:.0f} %)"
              for k, v in sorted(par.items(), key=lambda kv: -kv[1])]
    b = float(s.get("budget_mois") or 0)
    head = f"Dépenses de {month} : {tot:.2f} €" + (f" sur un budget de {b:.0f} € (reste {b - tot:.2f} €)" if b else "")
    last = "\n".join(f"  {d['date'][8:10]}/{d['date'][5:7]} — {d['montant']:.2f} € — {d['libelle']}"
                     for d in ds[-12:])
    return head + "\n\n" + "\n".join(lignes) + "\n\nDernières dépenses :\n" + last


# ================================================================== humeur
HUMEURS = {3: "😊", 2: "😐", 1: "😞"}


def set_mood(s, score, note=""):
    s["humeur"][datetime.date.today().isoformat()] = {"score": int(score), "note": note[:200]}
    save(s)


def parse_mood(text):
    t = _sa(text)
    if re.search(r"\b(super|genial|top|bien|bonne journee|content|heureux|heureuse|ca va bien|tres bien|cool|:\)|😊)",
                 t) and not re.search(r"\bpas (tres )?bien\b", t):
        return 3
    if re.search(r"\b(mal|nul|triste|deprime|fatigue|horrible|mauvaise journee|pas bien|pas top|bof bof|😞|:\()", t):
        return 1
    if re.search(r"\b(bof|moyen|ca va|normal|comme d'habitude|😐|ok)\b", t):
        return 2
    return None


def mood_month_text(s):
    today = datetime.date.today()
    start = today.replace(day=1)
    days = [(start + datetime.timedelta(days=i)) for i in range((today - start).days + 1)]
    cells, scores = [], []
    for d in days:
        h = s["humeur"].get(d.isoformat())
        cells.append(f"{d.day:2d}{HUMEURS.get(h['score'], '·') if h else ' ·'}")
        if h:
            scores.append(h["score"])
    weeks = [" ".join(cells[i:i + 7]) for i in range(0, len(cells), 7)]
    moy = sum(scores) / len(scores) if scores else 0
    resume = ("Ce mois-ci tu as l'air plutôt bien ! 😊" if moy >= 2.5 else
              "Un mois en dents de scie… je suis là si tu veux en parler." if moy >= 1.8 else
              "Le mois a l'air difficile. Parle à quelqu'un de confiance si ça dure, c'est important. 💗"
              if scores else "Pas encore d'humeur notée ce mois-ci.")
    notes = [f"  {k[8:10]}/{k[5:7]} {HUMEURS.get(v['score'], '')} {v['note']}" for k, v in sorted(s["humeur"].items())
             if k.startswith(today.strftime("%Y-%m")) and v.get("note")]
    return ("Ton humeur de " + today.strftime("%m/%Y") + " :\n\n" + "\n".join(weeks) + f"\n\n{resume}" +
            ("\n\nTes mots :\n" + "\n".join(notes[-10:]) if notes else ""))


# ================================================================== anniversaires des proches
def parse_birthday(text):
    """« l'anniversaire de Léa c'est le 12/03 » / « anniversaire de maman le 5 avril »."""
    mois = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
            "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
    t = _sa(text)
    m = re.search(r"anniv\w* (?:de |d')(.+?)(?:,| c'?est| est| le| au)\s+(?:le )?(\d{1,2})(?:[/.-](\d{1,2})| (\w+))", t)
    if not m:
        return None
    jour = int(m.group(2))
    mm = int(m.group(3)) if m.group(3) else mois.get(m.group(4) or "", 0)
    if not (1 <= jour <= 31 and 1 <= mm <= 12):
        return None
    raw = text[m.start(1):m.end(1)].strip() if len(text) == len(t) else m.group(1).strip()
    return raw[:30].strip().capitalize(), f"{jour:02d}/{mm:02d}"


def add_birthday(s, nom, jjmm):
    s["proches"] = [p for p in s["proches"] if _sa(p["nom"]) != _sa(nom)] + [{"nom": nom, "date": jjmm}]
    save(s)


def birthdays_on(s, day):
    k = day.strftime("%d/%m")
    return [p["nom"] for p in s["proches"] if p["date"] == k]


# ================================================================== soins (médicaments, plantes, animaux)
SOIN_TYPES = {"medicament": "💊", "plante": "🪴", "animal": "🐾", "autre": "⏰"}


def add_care(s, nom, kind="autre", heure="", tous_les=1, confirmer=True):
    s["soins"].append({"nom": nom, "type": kind, "heure": heure, "tous_les": max(1, int(tous_les)),
                       "confirmer": bool(confirmer), "dernier": "", "en_attente": ""})
    save(s)


def parse_care(text):
    """« rappelle-moi de prendre mon médicament tous les jours à 9h », « arrose le basilic tous les 3 jours »,
    « vermifuge le chat tous les 90 jours »."""
    t = _sa(text)
    m = re.search(r"tous les (\d+ )?(jours?|soirs?|matins?|semaines?|mois)", t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    unit = m.group(2)
    days = n * (7 if unit.startswith("semaine") else 30 if unit == "mois" else 1)
    h = re.search(r"\ba (\d{1,2})\s*h\s*(\d{2})?", t)
    heure = f"{int(h.group(1)):02d}:{h.group(2) or '00'}" if h else ("20:00" if "soir" in unit else
                                                                       "09:00" if "matin" in unit else "")
    low = (text or "").lower()
    quoi = re.sub(r"^.*?(?:rappelle[- ]moi (?:de |d['’])?|pense [aà] |n['’]oublie pas (?:de |d['’])?)", "", low)
    quoi = re.sub(r"tous les .*$", "", quoi).strip(" ,.")
    if not quoi:
        return None
    q = _sa(quoi)
    kind = ("medicament" if re.search(r"medic|cachet|pilule|traitement|comprime|vitamine", q) else
            "plante" if re.search(r"arros|plante|basilic|cactus|fleur", q) else
            "animal" if re.search(r"chat|chien|vermifu|litiere|croquette|lapin|hamster|poisson|antipuce", q)
            else "autre")
    return quoi[:60], kind, heure, days


def due_cares(s, now):
    """Soins à faire maintenant -> [index]."""
    out = []
    today = now.date()
    for i, c in enumerate(s["soins"]):
        last = c.get("dernier")
        if last:
            try:
                if (today - datetime.date.fromisoformat(last)).days < c.get("tous_les", 1):
                    continue
            except Exception:
                pass
        if c.get("heure"):
            hh, mm = map(int, c["heure"].split(":"))
            if (now.hour, now.minute) < (hh, mm):
                continue
        elif now.hour < 9:
            continue
        if c.get("en_attente") == today.isoformat():
            continue
        out.append(i)
    return out


def done_care(s, i=None):
    """Marque fait le soin en attente (ou le i-ème)."""
    today = datetime.date.today().isoformat()
    idx = [i] if i is not None else [k for k, c in enumerate(s["soins"]) if c.get("en_attente") == today] or \
        [k for k, c in enumerate(s["soins"]) if c.get("en_attente")]
    names = []
    for k in idx:
        s["soins"][k]["dernier"] = today
        s["soins"][k]["en_attente"] = ""
        names.append(s["soins"][k]["nom"])
    save(s)
    return names


# ================================================================== examens et révisions
def parse_exam(text):
    """« j'ai un examen de maths le 15/12 », « partiel d'histoire le 3 janvier »."""
    mois = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
            "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
    t = _sa(text)
    m = re.search(r"\b(?:examen|exam|partiel|controle|interro|bac|brevet|concours|test)\w* (?:de |d'|en )?(.+?) "
                  r"le (\d{1,2})(?:[/.-](\d{1,2})| (\w+))", t)
    if not m:
        return None
    jour = int(m.group(2))
    mm = int(m.group(3)) if m.group(3) else mois.get(m.group(4) or "", 0)
    if not (1 <= jour <= 31 and 1 <= mm <= 12):
        return None
    today = datetime.date.today()
    try:
        d = datetime.date(today.year, mm, jour)
    except ValueError:
        return None
    if d < today:
        d = d.replace(year=today.year + 1)
    return m.group(1).strip()[:40], d.isoformat()


def add_exam(s, matiere, date):
    s["examens"] = [e for e in s["examens"] if not (_sa(e["matiere"]) == _sa(matiere) and e["date"] == date)]
    s["examens"].append({"matiere": matiere, "date": date})
    save(s)


def exam_plan(e, today=None):
    """Planning simple : de J-14 à J-1, une séance par jour, avec ce qu'on fait."""
    today = today or datetime.date.today()
    d = datetime.date.fromisoformat(e["date"])
    left = (d - today).days
    if left < 0:
        return []
    plan = []
    for k in range(min(left, 14), 0, -1):
        day = d - datetime.timedelta(days=k)
        if day < today:
            continue
        what = ("relire le cours et faire une fiche" if k > 7 else "quiz et exercices" if k > 2 else
                "révision légère des fiches, et dormir tôt")
        plan.append((day.isoformat(), k, what))
    return plan


def exams_today(s, today=None):
    today = today or datetime.date.today()
    out = []
    for e in s["examens"]:
        for day, k, what in exam_plan(e, today):
            if day == today.isoformat():
                out.append((e, k, what))
    s["examens"] = [e for e in s["examens"] if e["date"] >= today.isoformat()]
    return out
