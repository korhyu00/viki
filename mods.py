"""Les mods de Viki : des paquets « .vikimod » (un simple zip) que n'importe qui peut créer et partager.

Un mod contient une fiche « mod.json » et, au choix :
  personnages/<dossier>/character.json   des personnages (comme ceux de la galerie)
  voix/*.onnx (+ .onnx.json)             des voix Piper
  repliques.txt                          des petites phrases (une par ligne)
  themes.json                            des thèmes de couleur : [{"id", "nom", "couleur": "#hex", "sombre": false}]
  ronds.json                             des ronds : [{"id", "icone", "nom", "type": "phrase|appli|dossier|lien", "valeur"}]
  main.py                                du code (outils) : def activer(viki) / def desactiver(viki)

Sans code, un mod s'active d'un clic. Avec du code, il s'installe DÉSACTIVÉ : le code peut tout faire sur le PC
(comme les mods de jeux), donc il faut le confirmer après un avertissement. Si le code change (mise à jour du mod),
il faut le reconfirmer.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

DIR = None              # fixé par compagnon.py : ~/.local/share/viki/mods
CATEGORIES = [          # clé, libellé (avec emoji)
    ("personnages", "🎭 Personnages"), ("tenues", "👗 Tenues"), ("themes", "🎨 Thèmes"),
    ("repliques", "💬 Répliques"), ("voix", "🎙️ Voix"), ("ronds", "⭕ Ronds"), ("outils", "🛠️ Outils"),
]
COULEURS = {"personnages": "#4B1528", "tenues": "#72243E", "themes": "#042C53", "repliques": "#085041",
            "voix": "#04342C", "ronds": "#3C3489", "outils": "#412402"}
MAX_ZIP = 3 * 1024 ** 3          # 3 Go décompressés au plus
MAX_REPLIQUES = 400

_charges = {}           # id -> module de code chargé
_commandes = []         # (id, motif compilé, fonction)
_ronds = {}             # "mod:<id>:<rond>" -> {"icone", "nom", "aide", "fn" | "type"+"valeur", "mod"}
_menus = []             # (id, libellé, fonction)
_minuteurs = {}         # id -> [QTimer]
_erreurs = {}           # id -> texte de l'erreur


def _slug(t):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return t[:48] or "mod"


# ------------------------------------------------------------------ lire les mods installés
def fiche(d):
    """La fiche d'un dossier de mod (avec ce qu'il contient vraiment)."""
    d = Path(d)
    try:
        m = json.loads((d / "mod.json").read_text(encoding="utf-8"))
        if not isinstance(m, dict):
            raise ValueError
    except Exception:
        m = {"nom": d.name, "erreur_fiche": True}
    m["id"] = _slug(m.get("id") or d.name)
    m["dossier"] = str(d)
    m["code"] = (d / "main.py").exists()
    contenu = []
    if (d / "personnages").is_dir():
        n = sum(1 for x in (d / "personnages").iterdir() if (x / "character.json").exists())
        if n:
            contenu.append(f"{n} personnage" + ("s" if n > 1 else ""))
    if (d / "voix").is_dir():
        n = len(list((d / "voix").glob("*.onnx")))
        if n:
            contenu.append(f"{n} voix")
    if (d / "repliques.txt").exists():
        n = len(repliques_de(d))
        if n:
            contenu.append(f"{n} réplique" + ("s" if n > 1 else ""))
    n = len(_json_list(d / "themes.json"))
    if n:
        contenu.append(f"{n} thème" + ("s" if n > 1 else ""))
    n = len(_json_list(d / "ronds.json"))
    if n:
        contenu.append(f"{n} rond" + ("s" if n > 1 else ""))
    if m["code"]:
        contenu.append("du code")
    m["contenu"] = contenu
    cat = m.get("categorie")
    if cat not in dict(CATEGORIES):
        cat = ("outils" if m["code"] else "personnages" if (d / "personnages").is_dir() else
               "themes" if (d / "themes.json").exists() else "voix" if (d / "voix").is_dir() else
               "ronds" if (d / "ronds.json").exists() else "repliques")
    m["categorie"] = cat
    ap = d / str(m.get("apercu") or "apercu.png")
    m["apercu_chemin"] = str(ap) if ap.is_file() and ap.resolve().is_relative_to(d.resolve()) else ""
    return m


def _json_list(p):
    try:
        x = json.loads(Path(p).read_text(encoding="utf-8"))
        return [e for e in x if isinstance(e, dict)] if isinstance(x, list) else []
    except Exception:
        return []


def repliques_de(d):
    try:
        lignes = Path(d, "repliques.txt").read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = [l.strip() for l in lignes if l.strip() and not l.strip().startswith("#")]
    return [l[:260] for l in out][:MAX_REPLIQUES]


def installes():
    if not DIR or not Path(DIR).exists():
        return []
    out = []
    for d in sorted(Path(DIR).iterdir()):
        if d.is_dir() and (d / "mod.json").exists():
            out.append(fiche(d))
    return out


def empreinte_code(d):
    """Empreinte de tout le code Python du mod : s'il change, il faut redonner son accord."""
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*.py")):
        h.update(str(p.relative_to(d)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def actif(cfg, mid):
    return bool((cfg.get("mods_actifs") or {}).get(mid))


def code_autorise(cfg, m):
    return (cfg.get("mods_code_ok") or {}).get(m["id"]) == empreinte_code(m["dossier"])


def actifs(cfg):
    return [m for m in installes() if actif(cfg, m["id"]) and (not m["code"] or code_autorise(cfg, m))]


# ------------------------------------------------------------------ ce que les mods actifs ajoutent
def dossiers_personnages(cfg):
    out = []
    for m in actifs(cfg):
        p = Path(m["dossier"]) / "personnages"
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if (x / "character.json").exists())
    return out


def dossiers_voix(cfg):
    return [Path(m["dossier"]) / "voix" for m in actifs(cfg) if (Path(m["dossier"]) / "voix").is_dir()]


def repliques(cfg):
    out = []
    for m in actifs(cfg):
        out += repliques_de(m["dossier"])
    return out


def themes(cfg):
    out = []
    for m in actifs(cfg):
        for t in _json_list(Path(m["dossier"]) / "themes.json"):
            c = str(t.get("couleur") or "")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                out.append({"id": "mod_" + _slug(m["id"] + "-" + str(t.get("id") or t.get("nom") or "theme")),
                            "nom": str(t.get("nom") or m.get("nom") or "Thème")[:40], "couleur": c,
                            "sombre": bool(t.get("sombre"))})
    return out


def ronds(cfg):
    """Les ronds des mods (fichier ronds.json + ceux ajoutés par du code)."""
    out = {k: v for k, v in _ronds.items()}
    for m in actifs(cfg):
        for r in _json_list(Path(m["dossier"]) / "ronds.json"):
            if r.get("type") not in ("phrase", "appli", "dossier", "lien") or not r.get("valeur"):
                continue
            rid = f"mod:{m['id']}:{_slug(str(r.get('id') or r.get('nom') or 'rond'))}"
            out[rid] = {"icone": str(r.get("icone") or "🧩")[:4], "nom": str(r.get("nom") or "Rond")[:24],
                        "aide": str(r.get("aide") or m.get("nom") or "")[:80], "type": r["type"],
                        "valeur": str(r["valeur"]), "mod": m["id"], "dossier": m["dossier"]}
    return out


def menus():
    return list(_menus)


# ------------------------------------------------------------------ installer / créer
class ModInvalide(Exception):
    pass


def _racine(names):
    """Le dossier du zip qui contient mod.json (à la racine ou dans un seul sous-dossier)."""
    if "mod.json" in names:
        return ""
    cands = sorted({n[: -len("mod.json")] for n in names if n.endswith("/mod.json") and n.count("/") == 1})
    if len(cands) == 1:
        return cands[0]
    raise ModInvalide("Ce fichier n'est pas un mod de Viki : il n'y a pas de fiche « mod.json » dedans.")


def lire_paquet(path):
    """Regarde un .vikimod / .zip / dossier SANS l'installer -> (fiche, avertissements)."""
    path = Path(path)
    if path.is_dir():
        if not (path / "mod.json").exists():
            raise ModInvalide("Ce dossier n'a pas de fiche « mod.json ».")
        return fiche(path), []
    tmp = Path(tempfile.mkdtemp(prefix="vikimod_"))
    try:
        _extraire(path, tmp)
        return fiche(tmp), []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _extraire(path, dest):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ModInvalide("Ce fichier est abîmé ou n'est pas un mod (.vikimod ou .zip).")
    with z:
        names = z.namelist()
        racine = _racine(names)
        total = 0
        for info in z.infolist():
            n = info.filename
            if not n.startswith(racine) or n == racine:
                continue
            rel = n[len(racine):]
            parts = Path(rel).parts
            if rel.startswith(("/", "\\")) or ".." in parts or ":" in rel:
                raise ModInvalide("Ce mod contient des chemins suspects : je ne l'installe pas.")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ModInvalide("Ce mod contient des liens symboliques : je ne l'installe pas.")
            total += info.file_size
            if total > MAX_ZIP:
                raise ModInvalide("Ce mod est beaucoup trop gros (plus de 3 Go).")
            out = Path(dest) / rel
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out, "wb") as f:
                shutil.copyfileobj(src, f, 1024 * 1024)


def installer(path, cfg):
    """Installe (ou met à jour) un mod -> sa fiche. Un mod avec du code reste désactivé tant qu'on n'a pas dit oui."""
    path = Path(path)
    Path(DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vikimod_", dir=DIR))
    try:
        if path.is_dir():
            if not (path / "mod.json").exists():
                raise ModInvalide("Ce dossier n'a pas de fiche « mod.json ».")
            shutil.copytree(path, tmp / "x", symlinks=False, ignore=shutil.ignore_patterns("__pycache__", ".git"))
            src = tmp / "x"
        else:
            src = tmp / "x"
            src.mkdir()
            _extraire(path, src)
        m = fiche(src)
        dest = Path(DIR) / m["id"]
        ancien = fiche(dest) if dest.exists() else None
        if dest.exists():
            desactiver_code(m["id"])
            shutil.rmtree(dest)
        shutil.move(str(src), str(dest))
        m = fiche(dest)
        acts = cfg.setdefault("mods_actifs", {})
        if ancien is None:
            acts[m["id"]] = True                       # sans code : actif tout de suite ; avec code : il faudra confirmer
        m["mise_a_jour"] = ancien is not None
        m["ancienne_version"] = (ancien or {}).get("version", "")
        return m
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def supprimer(mid, cfg):
    desactiver_code(mid)
    d = Path(DIR) / mid
    if d.exists() and d.resolve().parent == Path(DIR).resolve():
        shutil.rmtree(d)
    for k in ("mods_actifs", "mods_code_ok"):
        (cfg.get(k) or {}).pop(mid, None)


def creer_modele(dossier, nom, auteur, categorie):
    """Prépare un dossier de mod tout fait, avec des exemples et un mode d'emploi."""
    d = Path(dossier) / _slug(nom)
    i = 2
    while d.exists():
        d = Path(dossier) / f"{_slug(nom)}-{i}"
        i += 1
    d.mkdir(parents=True)
    fiche_ = {"id": d.name, "nom": nom, "auteur": auteur or "moi", "version": "1.0",
              "description": "Décris ton mod ici en une phrase.", "categorie": categorie, "apercu": "apercu.png"}
    (d / "mod.json").write_text(json.dumps(fiche_, ensure_ascii=False, indent=2), encoding="utf-8")
    if categorie in ("repliques",):
        (d / "repliques.txt").write_text("# Une phrase par ligne. Les lignes qui commencent par # sont ignorées.\n"
                                         "Tu as pensé à boire de l'eau ?\nJ'adore quand tu travailles en musique.\n",
                                         encoding="utf-8")
    if categorie == "themes":
        (d / "themes.json").write_text(json.dumps([{"id": "mon-theme", "nom": nom, "couleur": "#7f77dd",
                                                    "sombre": True}], ensure_ascii=False, indent=2), encoding="utf-8")
    if categorie == "ronds":
        (d / "ronds.json").write_text(json.dumps([
            {"id": "resume", "icone": "📝", "nom": "Résumer", "type": "phrase",
             "valeur": "Résume ce texte en trois points"},
            {"id": "site", "icone": "🌐", "nom": "Mon site", "type": "lien", "valeur": "https://korhyu.com"}],
            ensure_ascii=False, indent=2), encoding="utf-8")
    if categorie in ("personnages", "tenues"):
        (d / "personnages").mkdir()
        (d / "personnages" / "LISEZ-MOI.txt").write_text(
            "Mets ici un dossier par personnage, comme ceux de ~/.config/compagnon/personnages\n"
            "(un character.json et ses images). Le plus simple : crée ton personnage dans Viki,\n"
            "puis copie son dossier ici.\n", encoding="utf-8")
    if categorie == "voix":
        (d / "voix").mkdir()
        (d / "voix" / "LISEZ-MOI.txt").write_text("Mets ici des voix Piper : le fichier .onnx ET son .onnx.json.\n",
                                                  encoding="utf-8")
    if categorie == "outils":
        (d / "main.py").write_text(EXEMPLE_CODE, encoding="utf-8")
    (d / "LISEZ-MOI.txt").write_text(MODE_EMPLOI, encoding="utf-8")
    return d


def empaqueter(dossier, dest_dir=None):
    """Dossier de mod -> fichier .vikimod prêt à partager."""
    d = Path(dossier)
    m = fiche(d)
    if m.get("erreur_fiche"):
        raise ModInvalide("La fiche mod.json de ce dossier est illisible.")
    out = Path(dest_dir or d.parent) / f"{m['id']}-{_slug(str(m.get('version') or '1'))}.vikimod"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(d.rglob("*")):
            if p.is_symlink() or "__pycache__" in p.parts or ".git" in p.parts or p.suffix == ".vikimod":
                continue
            if p.is_file():
                z.write(p, str(p.relative_to(d)))
    return out


# ------------------------------------------------------------------ le code des mods (avec ton accord)
class API:
    """Ce qu'un mod avec du code reçoit dans activer(viki)."""

    def __init__(self, comp, m):
        self._c, self._m = comp, m
        self.dossier = Path(m["dossier"])
        self.id = m["id"]

    # parler
    def dire(self, texte):
        self._c.say(str(texte))

    def demander_ia(self, question, quand_fini):
        """Pose une question à son IA ; quand_fini(réponse) est appelé ensuite."""
        self._c._bg(lambda: self._c.ask_llm_text(str(question)) if hasattr(self._c, "ask_llm_text") else "",
                    lambda r: quand_fini("" if isinstance(r, Exception) else r))

    # ajouter des choses
    def ajouter_commande(self, motif, fonction):
        """Quand tu lui écris quelque chose qui correspond au motif (expression régulière, sans accents
        ni majuscules), fonction(texte) est appelée."""
        _commandes.append((self.id, re.compile(motif, re.I), fonction))

    def ajouter_rond(self, rid, icone, nom, fonction, aide=""):
        _ronds[f"mod:{self.id}:{_slug(rid)}"] = {"icone": icone, "nom": nom, "aide": aide or self._m.get("nom", ""),
                                                 "fn": fonction, "mod": self.id}

    def ajouter_menu(self, libelle, fonction):
        _menus.append((self.id, str(libelle), fonction))

    def toutes_les(self, minutes, fonction):
        from PyQt6.QtCore import QTimer
        t = QTimer()
        t.timeout.connect(lambda: _sur(self.id, fonction))
        t.start(int(max(0.1, float(minutes)) * 60_000))
        _minuteurs.setdefault(self.id, []).append(t)
        return t

    # ses réglages à lui (gardés entre deux lancements)
    @property
    def reglages(self):
        return self._c.cfg.setdefault("mods_reglages", {}).setdefault(self.id, {})

    def sauver(self):
        self._c.save_cfg()


def _sur(mid, fn, *args):
    try:
        return fn(*args)
    except Exception:
        _erreurs[mid] = traceback.format_exc()[-1500:]
        print(f"Mod {mid} :", _erreurs[mid], file=sys.stderr)


def activer_code(comp, m):
    """Charge main.py et appelle activer(viki). -> "" si tout va bien, sinon le message d'erreur."""
    mid = m["id"]
    if mid in _charges:
        return ""
    _erreurs.pop(mid, None)
    try:
        spec = importlib.util.spec_from_file_location(f"vikimod_{mid.replace('-', '_')}",
                                                      str(Path(m["dossier"]) / "main.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, m["dossier"])
        try:
            spec.loader.exec_module(mod)
        finally:
            if sys.path and sys.path[0] == m["dossier"]:
                sys.path.pop(0)
        if hasattr(mod, "activer"):
            mod.activer(API(comp, m))
        _charges[mid] = mod
        return ""
    except Exception:
        desactiver_code(mid)
        _erreurs[mid] = traceback.format_exc()[-1500:]
        return _erreurs[mid]


def desactiver_code(mid):
    mod = _charges.pop(mid, None)
    if mod is not None and hasattr(mod, "desactiver"):
        _sur(mid, mod.desactiver)
    for t in _minuteurs.pop(mid, []):
        t.stop()
    _commandes[:] = [c for c in _commandes if c[0] != mid]
    _menus[:] = [x for x in _menus if x[0] != mid]
    for k in [k for k, v in _ronds.items() if v.get("mod") == mid]:
        _ronds.pop(k, None)


def demarrer(comp):
    """Au lancement de Viki : charge le code des mods actifs que tu as autorisés."""
    for m in actifs(comp.cfg):
        if m["code"]:
            activer_code(comp, m)


def commande(texte, ta):
    """Une commande ajoutée par un mod correspond ? -> True si elle a été prise en charge."""
    for mid, rx, fn in list(_commandes):
        if rx.search(ta):
            _sur(mid, fn, texte)
            return True
    return False


def erreur(mid):
    return _erreurs.get(mid, "")


EXEMPLE_CODE = '''"""Exemple de mod avec du code. Viki appelle activer(viki) quand le mod est activé."""


def activer(viki):
    # Quand tu lui écris « pile ou face » :
    viki.ajouter_commande(r"\\bpile ou face\\b", lambda texte: viki.dire(__import__("random").choice(["Pile !", "Face !"])))
    # Un rond à mettre à côté d'elle (clic droit sur ses ronds -> Ajouter) :
    viki.ajouter_rond("de", "🎲", "Dé", lambda: viki.dire(f"Tu as fait {__import__('random').randint(1, 6)} !"))
    # Une ligne dans le menu « Mods » :
    viki.ajouter_menu("Dire bonjour", lambda: viki.dire("Bonjour de la part de mon mod !"))


def desactiver(viki=None):
    pass
'''

MODE_EMPLOI = """MON MOD POUR VIKI
=================

1. Remplis mod.json : nom, auteur, version, description (et « apercu » : une image apercu.png
   de ton mod, carrée de préférence).
2. Ajoute ce que tu veux :
     personnages/<dossier>/character.json   des personnages
     voix/*.onnx + *.onnx.json             des voix Piper
     repliques.txt                         des petites phrases (une par ligne)
     themes.json                           des thèmes : [{"id", "nom", "couleur": "#rrggbb", "sombre": false}]
     ronds.json                            des ronds : [{"id", "icone", "nom",
                                             "type": "phrase|appli|dossier|lien", "valeur"}]
     main.py                               du code Python (voir l'exemple) : activer(viki) / desactiver()
3. Pour l'essayer : glisse ce DOSSIER dans la fenêtre « Modèles et mods » de Viki.
4. Pour le partager : dans Viki, « Créer mon mod » -> « Empaqueter un dossier » : ça fait un .vikimod.

Ce que main.py peut utiliser (viki = l'objet reçu dans activer) :
  viki.dire(texte)                              elle le dit
  viki.ajouter_commande(motif, fonction)        quand tu lui écris quelque chose (expression régulière)
  viki.ajouter_rond(id, icone, nom, fonction)   un rond à côté d'elle
  viki.ajouter_menu(libelle, fonction)          une ligne dans le menu « Mods »
  viki.toutes_les(minutes, fonction)            quelque chose de régulier
  viki.reglages / viki.sauver()                 tes réglages, gardés entre deux lancements
  viki.dossier                                  le dossier de ton mod

Règles : pas de contenu sexuel ni violent, pas de personnages protégés (Disney, Nintendo, animés connus…)
si tu le partages, et pas de code qui espionne ou abîme le PC. Les mods avec du code ne se lancent
jamais sans l'accord de la personne qui l'installe.
"""
