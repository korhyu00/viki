"""📚 La mémoire de tes fichiers : Viki lit les dossiers que TU choisis (notes, cours, PDF, documents…) et peut
ensuite répondre « d'après ton fichier X ». Tout reste sur ton PC : l'index est un fichier à toi seul (chmod 600),
rien n'est envoyé nulle part (sauf si tu as choisi une IA en ligne : alors seuls les quelques extraits utiles
partent avec ta question).

Recherche par mots (BM25), sans rien à télécharger. L'index se met à jour tout seul (seulement les fichiers changés).
"""
import gzip
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import zipfile
from pathlib import Path

INDEX = None                    # fixé par compagnon.py : ~/.local/share/viki/memoire_fichiers.json.gz
TEXTE = {".txt", ".md", ".markdown", ".org", ".rst", ".csv", ".tsv", ".log", ".tex", ".html", ".htm", ".xml",
         ".json", ".yaml", ".yml", ".ini", ".conf", ".py", ".js", ".ts", ".sh", ".c", ".cpp", ".h", ".rs", ".go",
         ".java", ".kt", ".lua", ".sql", ".srt"}
DOCS = {".pdf", ".docx", ".odt", ".epub"}
IGNORE = {".git", "node_modules", "__pycache__", ".cache", ".venv", "venv", ".local", ".npm", ".cargo", "target",
          "build", "dist", ".mozilla", ".steam", "Steam"}
MAX_FICHIER = 25 * 1024 ** 2
MAX_FICHIERS = 6000
MORCEAU = 900
VIDES = set("""le la les un une des de du d l a au aux et ou en dans sur pour par avec sans ce cet cette ces
mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je tu il elle on nous vous ils elles me te se
qui que quoi dont est sont etait ete etre avoir ai as avait ont pas plus ne ni mais donc car si y
the a an of to in on for with is are was be it this that and or not as at by from""".split())

_verrou = threading.Lock()
_etat = {"index": None, "en_cours": False, "dernier": 0.0, "n": 0}


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def mots(t):
    return [w for w in re.findall(r"[a-z0-9]{2,}", _sa(t)) if w not in VIDES]


# ------------------------------------------------------------------ lire un fichier
def _zip_xml(path, noms):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if any(re.fullmatch(x, n) for x in noms):
                x = z.read(n).decode("utf-8", "ignore")
                x = re.sub(r"</(?:w:p|text:p|text:h|p|h\d|li|div)>", "\n", x)
                out.append(re.sub(r"<[^>]+>", "", x))
    return "\n".join(out)


def lire(path):
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext in TEXTE:
            t = p.read_bytes()[:3_000_000].decode("utf-8", "ignore")
            if ext in (".html", ".htm", ".xml"):
                t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
                t = re.sub(r"<[^>]+>", " ", t)
            return t
        if ext == ".pdf":
            if shutil.which("pdftotext"):
                r = subprocess.run(["pdftotext", "-q", "-layout", str(p), "-"], capture_output=True, timeout=60)
                return r.stdout.decode("utf-8", "ignore")
            return ""
        if ext == ".docx":
            return _zip_xml(p, [r"word/document\.xml"])
        if ext == ".odt":
            return _zip_xml(p, [r"content\.xml"])
        if ext == ".epub":
            return _zip_xml(p, [r".*\.x?html?"])
    except Exception:
        return ""
    return ""


def morceaux(texte):
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte).strip()
    out, i = [], 0
    while i < len(texte) and len(out) < 400:
        bout = texte[i:i + MORCEAU]
        if i + MORCEAU < len(texte):                      # on coupe à une fin de phrase si possible
            j = max(bout.rfind(". "), bout.rfind("\n"))
            if j > MORCEAU * 0.5:
                bout = bout[:j + 1]
        if bout.strip():
            out.append(bout.strip())
        i += max(200, len(bout) - 150)
    return out


# ------------------------------------------------------------------ l'index
def charger():
    if _etat["index"] is not None:
        return _etat["index"]
    idx = {"fichiers": {}, "morceaux": [], "dossiers": [], "date": 0}
    try:
        with gzip.open(INDEX, "rt", encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        pass
    _preparer(idx)
    _etat["index"] = idx
    return idx


def _preparer(idx):
    """Index inversé en mémoire (pas sauvé : recalculé au chargement)."""
    inv, longueurs = {}, []
    for k, m in enumerate(idx["morceaux"]):
        ws = mots(m["t"] + " " + Path(m["f"]).stem.replace("_", " ").replace("-", " "))
        longueurs.append(len(ws))
        vus = {}
        for w in ws:
            vus[w] = vus.get(w, 0) + 1
        for w, n in vus.items():
            inv.setdefault(w, []).append((k, n))
    idx["_inv"], idx["_long"] = inv, longueurs
    idx["_moy"] = (sum(longueurs) / len(longueurs)) if longueurs else 1.0


def _sauver(idx):
    data = {k: v for k, v in idx.items() if not k.startswith("_")}
    Path(INDEX).parent.mkdir(parents=True, exist_ok=True)
    tmp = str(INDEX) + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, INDEX)


def _parcourir(dossiers):
    vus = 0
    for d in dossiers:
        d = Path(d).expanduser()
        if not d.is_dir():
            continue
        for racine, sous, fichiers in os.walk(d):
            sous[:] = [s for s in sous if not s.startswith(".") and s not in IGNORE]
            for f in fichiers:
                if f.startswith("."):
                    continue
                p = Path(racine) / f
                if p.suffix.lower() in TEXTE | DOCS:
                    vus += 1
                    if vus > MAX_FICHIERS:
                        return
                    yield p


def indexer(dossiers, progres=None):
    """Met l'index à jour (seulement les fichiers nouveaux ou changés). -> (fichiers, morceaux)"""
    with _verrou:
        if _etat["en_cours"]:
            return None
        _etat["en_cours"] = True
    try:
        idx = charger()
        anciens = idx["fichiers"]
        garder = {}
        par_fichier = {}
        for m in idx["morceaux"]:
            par_fichier.setdefault(m["f"], []).append(m)
        nouveaux = []
        n = 0
        for p in _parcourir(dossiers):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size > MAX_FICHIER:
                continue
            cle = str(p)
            info = anciens.get(cle)
            if info and info.get("mtime") == int(st.st_mtime) and cle in par_fichier:
                garder[cle] = info
                nouveaux += par_fichier[cle]
                continue
            t = lire(p)
            n += 1
            if progres and n % 25 == 0:
                progres(n)
            garder[cle] = {"mtime": int(st.st_mtime), "taille": st.st_size}
            for i, bout in enumerate(morceaux(t)):
                nouveaux.append({"f": cle, "i": i, "t": bout})
        idx = {"fichiers": garder, "morceaux": nouveaux, "dossiers": [str(d) for d in dossiers], "date": time.time()}
        _preparer(idx)
        _sauver(idx)
        _etat["index"] = idx
        _etat["dernier"] = time.time()
        return len(garder), len(nouveaux)
    finally:
        _etat["en_cours"] = False


def oublier():
    _etat["index"] = None
    try:
        os.unlink(INDEX)
    except OSError:
        pass


def chercher(question, n=6):
    """-> [(score, morceau)] les extraits les plus proches de la question (BM25)."""
    idx = charger()
    if not idx["morceaux"]:
        return []
    q = mots(question)
    if not q:
        return []
    N = len(idx["morceaux"])
    scores = {}
    k1, b = 1.4, 0.75
    for w in set(q):
        post = idx["_inv"].get(w)
        if not post:
            continue
        idf = math.log(1 + (N - len(post) + 0.5) / (len(post) + 0.5))
        for k, tf in post:
            L = idx["_long"][k]
            scores[k] = scores.get(k, 0.0) + idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * L / idx["_moy"]))
    meilleurs = sorted(scores.items(), key=lambda x: -x[1])
    out, par_fichier = [], {}
    for k, s in meilleurs:
        m = idx["morceaux"][k]
        if par_fichier.get(m["f"], 0) >= 2:               # pas plus de 2 extraits du même fichier
            continue
        par_fichier[m["f"]] = par_fichier.get(m["f"], 0) + 1
        out.append((s, m))
        if len(out) >= n:
            break
    return out


def chercher_fichier(nom, n=8):
    """Les fichiers dont le NOM ressemble à la demande."""
    idx = charger()
    q = set(mots(nom))
    if not q:
        return []
    res = []
    for f in idx["fichiers"]:
        ws = set(mots(Path(f).stem.replace("_", " ").replace("-", " ")))
        s = len(q & ws)
        if s:
            res.append((s, f))
    res.sort(key=lambda x: (-x[0], len(x[1])))
    return [f for _, f in res[:n]]


def consigne(question, extraits, langue="français"):
    blocs = "\n\n".join(f"[{i + 1}] Fichier « {Path(m['f']).name} » :\n{m['t']}" for i, (_, m) in enumerate(extraits))
    return ("Voici des extraits des fichiers de l'utilisateur (sur son PC). Réponds à sa question UNIQUEMENT "
            "d'après ces extraits, en quelques phrases simples, et cite le nom du fichier utilisé (« d'après ton "
            "fichier X… »). Si la réponse n'y est pas, dis-le franchement. Ne recopie pas de mots de passe.\n\n"
            f"{blocs}\n\nQuestion : {question}\nRéponds en {langue}.")


def resume():
    idx = charger()
    return len(idx["fichiers"]), len(idx["morceaux"]), idx.get("date", 0)


RX = re.compile(
    r"\b(?:d.apres|dans|selon|parmi) (?:mes|mon|ma) (?:fichiers?|notes?|documents?|docs?|cours|dossiers?|pdf)\b|"
    r"\b(?:cherche|trouve|retrouve)\b.{0,30}\b(?:dans|parmi) mes (?:fichiers|notes|documents|cours|dossiers)\b|"
    r"\bqu.est[- ]ce que j.avais (?:note|ecrit|mis)\b|\bj.avais (?:note|ecrit) (?:quelque part|ou)\b|"
    r"\b(?:in|from|according to) my (?:files|notes|documents|docs)\b", re.I)
RX_FICHIER = re.compile(r"^(?:ou (?:est|se trouve|j.ai mis|j.ai range) (?:mon|ma|mes|le|la|les) (?:fichier|document|pdf|"
                        r"photo|image|note)s?|(?:trouve|retrouve)[- ]moi (?:le|la|mon|ma) (?:fichier|document|pdf))\s+(.+)$",
                        re.I)


# ------------------------------------------------------------------ la fenêtre : choisir ses dossiers
def Fenetre(comp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QPushButton,
                                 QVBoxLayout)
    try:
        from i18n import tr
    except Exception:
        def tr(t):
            return t

    class _F(QDialog):
        def __init__(self):
            super().__init__(None)
            self.setWindowTitle(tr("📚 Mémoire de mes fichiers"))
            self.resize(560, 440)
            v = QVBoxLayout(self)
            lab = QLabel(tr("Choisis les dossiers que Viki peut lire (notes, cours, PDF, documents…). Ensuite, "
                            "demande-lui « d'après mes notes, … » ou « où est mon fichier … ». Tout reste sur ton PC."))
            lab.setWordWrap(True)
            v.addWidget(lab)
            self.liste = QListWidget()
            v.addWidget(self.liste, 1)
            h = QHBoxLayout()
            for txt, fn in ((tr("➕ Ajouter un dossier…"), self.ajouter), (tr("➖ Retirer"), self.retirer),
                            (tr("🔄 Relire maintenant"), lambda: comp.memoire_indexer(True)),
                            (tr("🗑️ Tout oublier"), self.oublier_tout)):
                b = QPushButton(txt)
                b.clicked.connect(fn)
                h.addWidget(b)
            v.addLayout(h)
            self.etat = QLabel()
            self.etat.setWordWrap(True)
            v.addWidget(self.etat)

        def rafraichir(self):
            self.liste.clear()
            for d in comp.cfg.get("memoire_dossiers") or []:
                self.liste.addItem(d)
            nf, nm, date = resume()
            quand = time.strftime("%d/%m %H:%M", time.localtime(date)) if date else "—"
            self.etat.setText(tr("Fichiers lus : {} · extraits : {} · dernière lecture : {}").format(nf, nm, quand)
                              + ("" if shutil.which("pdftotext") else "\n" + tr("(Pour lire les PDF, installe « poppler » "
                                                                               "qui fournit pdftotext.)")))

        def ajouter(self):
            d = QFileDialog.getExistingDirectory(self, tr("Un dossier à lire"), str(Path.home()))
            if not d:
                return
            ds = comp.cfg.setdefault("memoire_dossiers", [])
            if d not in ds:
                ds.append(d)
                comp.save_cfg()
            self.rafraichir()
            comp.memoire_indexer(True)

        def retirer(self):
            it = self.liste.currentItem()
            if not it:
                return
            ds = comp.cfg.setdefault("memoire_dossiers", [])
            if it.text() in ds:
                ds.remove(it.text())
                comp.save_cfg()
            self.rafraichir()
            comp.memoire_indexer(False) if ds else oublier()
            self.rafraichir()

        def oublier_tout(self):
            comp.cfg["memoire_dossiers"] = []
            comp.save_cfg()
            oublier()
            self.rafraichir()
            comp.say("J'ai tout oublié de tes fichiers.")

    return _F()
