"""Petits plus de Viki : historique du presse-papiers (en mémoire vive seulement), snippets de code,
recherche dans les notes, TODO du code, journal de projet, souvenirs, humeur du moment, rituels, mode nuit.
Tout est local. Aucun accès internet."""
import datetime
import difflib
import json
import os
import re
import subprocess
import unicodedata
from collections import deque
from pathlib import Path

STATE_FILE = None                         # fixé par compagnon.py : ~/.config/viki/plus.json


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def load():
    try:
        s = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("snippets", [])
    s.setdefault("souvenirs", [])
    s.setdefault("projets_vus", [])
    return s


def save(s):
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


# ------------------------------------------------------------------ presse-papiers
def clip_kind(t):
    s = t.strip()
    if re.fullmatch(r"https?://\S+|www\.\S+", s):
        return "lien"
    if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", s):
        return "mail"
    if re.fullmatch(r"\+?[\d ().-]{8,20}", s) and sum(c.isdigit() for c in s) >= 8:
        return "numero"
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", s):
        return "couleur"
    if re.fullmatch(r"(~|/|[A-Za-z]:\\)[^\n]*", s) and "\n" not in s and " = " not in s:
        return "chemin"
    if looks_like_error(s):
        return "erreur"
    if re.search(r"[{};]\s*$|^\s*(def |class |import |from \w+ import|function |const |let |var |#include|public |"
                 r"fn |SELECT |sudo |git |npm |pip |cd |ls )|=>|\)\s*\{", s, re.M):
        return "code"
    return "texte"


def looks_secret(t):
    """Mot de passe ou jeton probable : un seul « mot » long qui mélange lettres, chiffres et symboles."""
    s = t.strip()
    if " " in s or "\n" in s or not (8 <= len(s) <= 128) or clip_kind(s) in ("lien", "mail", "chemin", "numero",
                                                                             "couleur"):
        return False
    if re.match(r"(gh[pousr]_|glpat-|sk-|hf_|xox[bap]-|AKIA|eyJ)", s):
        return True
    classes = sum(bool(re.search(p, s)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w]"))
    return classes >= 3 and not re.fullmatch(r"[\w.-]+\.\w{1,5}", s)


KIND_LABEL = {"lien": "🔗 lien", "mail": "✉️ adresse mail", "numero": "📞 numéro", "couleur": "🎨 couleur",
              "chemin": "📁 chemin", "erreur": "🐞 erreur", "code": "💻 code", "texte": "📝 texte"}
KIND_WORDS = {"lien": r"lien|url|adresse web|site|page", "mail": r"mail|e-mail|email|adresse mail",
              "numero": r"numero|telephone|tel", "couleur": r"couleur", "chemin": r"chemin|dossier",
              "erreur": r"erreur|bug", "code": r"code|commande|script", "texte": r"texte|phrase|paragraphe|message"}


class ClipHistory:
    """Les dernières choses copiées. Jamais écrit sur le disque ; les mots de passe probables sont ignorés."""

    def __init__(self, n=40):
        self.items = deque(maxlen=n)          # (heure, type, texte) du plus récent au plus ancien

    def add(self, text):
        if not text or not text.strip() or len(text) > 50000 or looks_secret(text):
            return False
        if self.items and self.items[0][2] == text:
            return False
        for it in list(self.items):
            if it[2] == text:
                self.items.remove(it)
        self.items.appendleft((datetime.datetime.now(), clip_kind(text), text))
        return True

    def find(self, query):
        """« le lien de tout à l'heure », « le code d'avant », « le texte sur python » -> entrée ou None."""
        q = _sa(query)
        items = list(self.items)
        if not items:
            return None
        kind = next((k for k, w in KIND_WORDS.items() if re.search(r"\b(" + w + r")s?\b", q)), None)
        earlier = bool(re.search(r"tout a l'heure|d'avant|avant|precedent|dernier|ancien", q))
        m = re.search(r"\b(?:sur|avec|qui parle de|qui contient|de)\s+([a-z0-9_.-]{3,})\s*$", q)
        word = m.group(1) if m and m.group(1) not in ("tout", "avant", "l'heure", "heure") else None
        pool = [it for it in items if kind is None or it[1] == kind]
        if word:
            hit = [it for it in pool if word in _sa(it[2])]
            pool = hit or pool
        if not pool:
            return None
        if earlier and kind is None and not word and len(pool) > 1:
            return pool[1]                      # « ce que j'avais copié avant » = l'avant-dernier
        return pool[0]

    def clear(self):
        self.items.clear()


def short(t, n=70):
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n - 1] + "…"


# ------------------------------------------------------------------ erreurs
def looks_like_error(t):
    return bool(re.search(r"Traceback \(most recent call last\)|^\s*\w*(Error|Exception)\b.*:|\berror(\[\w+\])?:|"
                          r"\bfatal:|\bpanicked at\b|Segmentation fault|command not found|No such file or directory|"
                          r"Permission denied|\bERR!|undefined reference|cannot find (module|symbol)|"
                          r"\bFAILED\b|erreur\s*:|NullPointerException|is not defined|Unhandled", t or "", re.M))


def error_prompt(err):
    return ("Voici un message d'erreur copié depuis mon terminal ou mon programme. Explique-moi en français simple :\n"
            "1) ce que ça veut dire, en une ou deux phrases ;\n2) la cause la plus probable ;\n"
            "3) comment corriger, avec la commande ou la ligne de code exacte si possible.\n"
            "Sois bref et concret. Si plusieurs causes sont possibles, donne les deux plus probables.\n\n"
            "```\n" + err.strip()[-6000:] + "\n```")


# ------------------------------------------------------------------ snippets
LANGS = ((r"^\s*(def |import |from \w+ import|print\()", "python"), (r"^\s*(const |let |function |=>|console\.)", "js"),
         (r"^\s*(#!/bin/(ba)?sh|sudo |echo |cd |ls |git |pacman |apt )", "shell"), (r"^\s*(SELECT|INSERT|UPDATE) ", "sql"),
         (r"^\s*(#include|int main)", "c"), (r"^\s*(fn |let mut |use std)", "rust"), (r"^\s*<\w+[^>]*>", "html"),
         (r"^\s*[.#]?[\w-]+\s*\{", "css"))


def guess_lang(code):
    return next((l for p, l in LANGS if re.search(p, code, re.M | re.I)), "")


def add_snippet(s, name, code):
    name = name.strip(" .:«»\"'") or "sans nom"
    s["snippets"] = [x for x in s["snippets"] if _sa(x["nom"]) != _sa(name)]
    s["snippets"].insert(0, {"nom": name, "code": code, "lang": guess_lang(code),
                             "date": datetime.date.today().isoformat()})
    save(s)
    return name


def find_snippet(s, query):
    q = _sa(query).strip()
    if not s["snippets"] or not q:
        return None
    for x in s["snippets"]:
        if q == _sa(x["nom"]) or q in _sa(x["nom"]):
            return x
    words = [w for w in re.findall(r"[a-z0-9_]+", q) if len(w) > 2]
    best, score = None, 0
    for x in s["snippets"]:
        hay = _sa(x["nom"] + " " + x.get("lang", "") + " " + x["code"][:2000])
        sc = sum(3 if w in _sa(x["nom"]) else 1 for w in words if w in hay)
        if not sc and difflib.get_close_matches(q, [_sa(x["nom"])], n=1, cutoff=0.7):
            sc = 2
        if sc > score:
            best, score = x, sc
    return best


def remove_snippet(s, query):
    x = find_snippet(s, query)
    if x:
        s["snippets"].remove(x)
        save(s)
    return x


def snippets_text(s):
    if not s["snippets"]:
        return ("Aucun snippet pour l'instant.\n\nCopie un bout de code, puis dis :\n"
                "  « garde ce code sous le nom tri rapide »\n\nPour le ressortir : « ressors mon snippet tri rapide ».")
    out = []
    for x in s["snippets"]:
        out.append(f"━━ {x['nom']}" + (f"  ({x['lang']})" if x.get("lang") else "") + f"  ·  {x.get('date', '')}\n"
                   + x["code"].rstrip() + "\n")
    return "\n".join(out)


# ------------------------------------------------------------------ notes
def search_notes(notes, query):
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", _sa(query))
             if len(w) > 2]
    if not words:
        return []
    out = []
    for n in notes:
        t = _sa(n.get("txt", ""))
        sc = sum(1 for w in words if w in t)
        if sc:
            out.append((sc, n))
    return [n for _, n in sorted(out, key=lambda x: -x[0])]


# ------------------------------------------------------------------ dev : TODO et journal
def _git(p, *a, timeout=30):
    try:
        r = subprocess.run(["git", "-C", str(p)] + list(a), capture_output=True, timeout=timeout)
        return r.stdout.decode(errors="ignore") if r.returncode in (0, 1) else ""
    except Exception:
        return ""


def todos(p, limit=200):
    """[(fichier, ligne, texte)] des TODO / FIXME / XXX / HACK du projet (fichiers suivis par git)."""
    out = _git(p, "grep", "-n", "-I", "-E", r"\b(TODO|FIXME|XXX|HACK)\b")
    res = []
    for line in out.splitlines():
        m = re.match(r"^(.+?):(\d+):(.*)$", line)
        if not m or re.search(r"(^|/)(node_modules|vendor|dist|build|\.min\.)", m.group(1)):
            continue
        txt = m.group(3).strip()
        k = re.search(r"\b(TODO|FIXME|XXX|HACK)\b[:\s-]*(.*)", txt)
        res.append((m.group(1), int(m.group(2)), (k.group(1) + " : " + k.group(2).strip()) if k else txt))
        if len(res) >= limit:
            break
    return res


def todos_text(p, items):
    if not items:
        return f"Aucun TODO ni FIXME dans {Path(p).name}. Bravo, c'est propre ! ✨"
    fix = [x for x in items if x[2].startswith(("FIXME", "XXX", "HACK"))]
    out = [f"{len(items)} note(s) dans {Path(p).name}" + (f", dont {len(fix)} à corriger (FIXME)" if fix else "") + ".\n"]
    cur = None
    for f, n, t in sorted(items, key=lambda x: (not x[2].startswith("FIXME"), x[0], x[1])):
        if f != cur:
            out.append(f"\n📄 {f}")
            cur = f
        out.append(f"   l.{n:<5} {short(t, 110)}")
    return "\n".join(out)


def day_log(projets, day=None):
    """Ce qui a été fait aujourd'hui dans les projets : {projet: {commits: [...], fichiers, plus, moins, en_cours}}."""
    day = day or datetime.date.today()
    since, until = day.isoformat() + " 00:00", (day + datetime.timedelta(days=1)).isoformat() + " 00:00"
    res = {}
    for p in projets:
        if not Path(p).is_dir():
            continue
        log = _git(p, "log", "--all", "--no-merges", f"--since={since}", f"--until={until}", "--pretty=%s")
        commits = [l.strip() for l in log.splitlines() if l.strip()]
        stat = _git(p, "log", "--all", "--no-merges", f"--since={since}", f"--until={until}", "--pretty=", "--numstat")
        plus = moins = 0
        files = set()
        for l in stat.splitlines():
            a = l.split("\t")
            if len(a) == 3:
                files.add(a[2])
                plus += int(a[0]) if a[0].isdigit() else 0
                moins += int(a[1]) if a[1].isdigit() else 0
        dirty = len([l for l in _git(p, "status", "--porcelain").splitlines() if l.strip()])
        if commits or dirty:
            res[Path(p).name] = {"commits": commits, "fichiers": len(files), "plus": plus, "moins": moins,
                                 "en_cours": dirty}
    return res


def day_log_text(log):
    if not log:
        return "Pas de commit ni de fichier modifié aujourd'hui dans tes projets suivis."
    out = []
    for name, d in log.items():
        n = len(d["commits"])
        out.append(f"📁 {name} — {n} commit{'s' if n > 1 else ''}"
                   + (f", {d['fichiers']} fichier(s), +{d['plus']} / −{d['moins']} lignes" if n else "")
                   + (f", {d['en_cours']} fichier(s) pas encore commité(s)" if d["en_cours"] else ""))
        out += [f"   • {c}" for c in d["commits"][:25]]
    return "\n".join(out)


def day_log_short(log):
    n = sum(len(d["commits"]) for d in log.values())
    lines = sum(d["plus"] for d in log.values())
    names = ", ".join(list(log)[:3])
    if not n:
        return f"Tu as travaillé sur {names} aujourd'hui, sans commit pour l'instant. Pense à sauvegarder ton travail !"
    return (f"Bilan du jour : {n} commit{'s' if n > 1 else ''} sur {names}"
            + (f", environ {lines} lignes ajoutées" if lines else "") + ". Beau travail ! 💪")


def journal_prompt(text):
    return ("Voici mes commits du jour. Résume en 3 phrases maximum, en français, ce que j'ai accompli, "
            "comme une amie fière de moi, sans liste à puces :\n\n" + text[:5000])


# ------------------------------------------------------------------ souvenirs
def add_memory(s, txt, kind="moment", day=None):
    day = (day or datetime.date.today()).isoformat()
    if any(m["txt"] == txt for m in s["souvenirs"]):
        return False
    s["souvenirs"].append({"date": day, "txt": txt, "kind": kind})
    s["souvenirs"] = s["souvenirs"][-400:]
    save(s)
    return True


def _months_ago(day, n):
    y, m = day.year, day.month - n
    while m <= 0:
        m += 12
        y -= 1
    try:
        return day.replace(year=y, month=m)
    except ValueError:
        return None


def anniversaries(s, today=None):
    """Souvenirs d'il y a pile 1 semaine, 1 / 3 / 6 mois, 1 an, 2 ans… -> [(« il y a un mois », souvenir)]."""
    today = today or datetime.date.today()
    marks = [(today - datetime.timedelta(days=7), "Il y a une semaine")]
    for n, lab in ((1, "Il y a un mois"), (3, "Il y a trois mois"), (6, "Il y a six mois"), (12, "Il y a un an"),
                   (24, "Il y a deux ans"), (36, "Il y a trois ans")):
        d = _months_ago(today, n)
        if d:
            marks.append((d, lab))
    out = []
    for d, lab in marks:
        for m in s["souvenirs"]:
            if m["date"] == d.isoformat():
                out.append((lab, m))
    return out


def memories_text(s):
    if not s["souvenirs"]:
        return "Nos souvenirs s'écriront ici au fil du temps. Dis « garde ce souvenir : … » pour en ajouter un."
    out = []
    for m in sorted(s["souvenirs"], key=lambda m: m["date"], reverse=True):
        try:
            d = datetime.date.fromisoformat(m["date"]).strftime("%d/%m/%Y")
        except Exception:
            d = m["date"]
        out.append(f"{d}   {m['txt']}")
    return "\n".join(out)


def sync_projects(s, projets):
    """Note la date où chaque projet a été vu pour la première fois. Renvoie les nouveaux."""
    new = [p for p in projets if p not in s["projets_vus"]]
    for p in new:
        s["projets_vus"].append(p)
        add_memory(s, f"tu commençais à travailler sur le projet « {Path(p).name} » avec moi", "projet")
    if new:
        save(s)
    return new


# ------------------------------------------------------------------ humeur du moment, rituels
MOODS = {
    "matin": ["Bonjour le monde ! Je me sens en pleine forme ce matin. ☀️", "J'adore le matin, tout est encore possible !",
              "Bien dormi ? Moi je suis toute fraîche, prête à t'aider !"],
    "midi": ["J'ai un petit creux… Et toi, tu as mangé ? 🍽️", "C'est l'heure de manger, non ? Ne saute pas le repas !"],
    "aprem": ["Petit coup de mou de l'après-midi… Un verre d'eau et ça repart ! 💧",
              "L'après-midi, j'ai toujours un peu envie d'une sieste… Pas toi ?"],
    "soir": ["La journée a été longue… Je suis contente de ce qu'on a fait ensemble. 🌆",
             "Le soir, j'aime bien quand c'est calme comme ça."],
    "nuit": ["Je commence à avoir sommeil… *bâille* 🥱", "Mes yeux se ferment tout seuls… Tu n'es pas fatigué, toi ?"],
}


def mood_slot(hour):
    if 6 <= hour < 10:
        return "matin"
    if 12 <= hour < 14:
        return "midi"
    if 14 <= hour < 17:
        return "aprem"
    if 19 <= hour < 22:
        return "soir"
    if hour >= 22 or hour < 3:
        return "nuit"
    return None


RITUALS = {
    "toujours": [("🍵", "Pendant ta pause, je me fais un petit thé. Tu en veux un aussi ?"),
                 ("🪴", "J'en profite pour arroser ma plante. Elle a bien poussé, regarde !"),
                 ("📖", "Je lis quelques pages de mon livre pendant ta pause."),
                 ("🧘", "Je m'étire un peu… Fais pareil, ça fait du bien au dos !"),
                 ("🎧", "Je mets mon casque et j'écoute un morceau en attendant."),
                 ("✏️", "Je gribouille dans mon carnet pendant que tu souffles.")],
    "hiver": [("☕", "Un chocolat chaud pendant la pause, c'est la saison ! ❄️"),
              ("🧣", "Brr, je remets mon écharpe. Couvre-toi bien toi aussi !")],
    "printemps": [("🌸", "Je regarde les fleurs par la fenêtre, c'est le printemps !")],
    "ete": [("🍦", "Une petite glace pendant la pause ? Il fait chaud !"),
            ("🥤", "Je me sers un grand verre d'eau fraîche. Bois, toi aussi !")],
    "automne": [("🍂", "Je regarde les feuilles tomber… J'adore l'automne."),
                ("🍵", "Une tisane bien chaude, parfaite pour l'automne.")],
}


def season(day=None):
    m = (day or datetime.date.today()).month
    return "hiver" if m in (12, 1, 2) else "printemps" if m in (3, 4, 5) else "ete" if m in (6, 7, 8) else "automne"


def ritual(rnd, day=None):
    pool = RITUALS["toujours"] + RITUALS[season(day)] * 2
    return rnd.choice(pool)


# ------------------------------------------------------------------ mode nuit
def is_night(hour, start=22, end=7):
    start, end = int(start), int(end)
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


EYES = ["Ça fait un moment que tu fixes l'écran… Regarde au loin pendant 20 secondes, tes yeux te diront merci. 👀",
        "Petite pause pour tes yeux ? Cligne plusieurs fois et regarde par la fenêtre un instant.",
        "Il fait nuit et l'écran fatigue les yeux. Baisse un peu la luminosité si tu peux. 🌙"]
