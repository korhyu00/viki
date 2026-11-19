"""Ajouter n'importe quelle IA à Viki : on télécharge un fichier, on le glisse, elle reconnaît à quoi il sert
(discuter, traduire, images, musique, voix) et l'installe au bon endroit. Tout reste sur le PC.

Ce qui est reconnu :
  • .gguf             -> une IA qui écrit (cerveau, traduction…) : installée dans Ollama
  • .safetensors      -> modèle d'images (SD 1.5, SDXL, FLUX tout-en-un…) ou de musique (ACE-Step) : moteur d'images
  • .onnx (+ .json)   -> une voix Piper
Les .ckpt / .pt / .bin sont refusés : ces vieux formats peuvent cacher du code qui s'exécute à l'ouverture.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL

LIENS = {
    "cerveau": ("Hugging Face — modèles GGUF", "https://huggingface.co/models?library=gguf&sort=trending"),
    "image": ("Civitai — modèles d'images", "https://civitai.com/models"),
    "image2": ("Hugging Face — modèles d'images", "https://huggingface.co/models?pipeline_tag=text-to-image&sort=trending"),
    "musique": ("ACE-Step (musique)", "https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files"),
    "voix": ("Voix Piper (toutes les langues)", "https://huggingface.co/rhasspy/piper-voices/tree/main"),
}


# ================================================================ lecture des fichiers (sans les charger)
def ram_go():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 2 ** 20)
    except Exception:
        pass
    return 0


def vram_go():
    """Mémoire de la carte graphique en Go (0 si inconnue)."""
    try:
        import gestionpc
        g = gestionpc.gpu() or {}
        return round((g.get("vram_total") or 0) / 2 ** 30)
    except Exception:
        return 0


def verdict(size):
    """(niveau, phrase) : ce fichier de `size` octets tournera-t-il sur ce PC ? niveau : ok / lent / non."""
    go = size / 2 ** 30
    ram, vr = ram_go(), vram_go()
    if vr and go <= vr * 0.85:
        return "ok", f"✅ tient dans ta carte graphique ({vr} Go) : rapide"
    if ram and go <= ram * 0.6:
        return "lent", ("🟠 trop gros pour ta carte graphique" + (f" ({vr} Go)" if vr else "") +
                        f" : il tournera sur la mémoire du PC ({ram} Go), donc lentement")
    if not ram:
        return "lent", "❔ je n'arrive pas à mesurer ton PC"
    return "non", f"❌ trop gros pour ce PC ({ram} Go de mémoire)"


HF_BASE = os.environ.get("VIKI_HF_BASE", "https://huggingface.co").rstrip("/")
_IMG_ARCH = ("flux", "sd1", "sdxl", "sd3", "wan", "hunyuan-video", "ltxv", "lumina2", "hidream", "qwen_image",
             "stable-diffusion", "chroma")
_EMB_ARCH = ("clip", "bert", "nomic-bert", "jina-bert-v2", "t5encoder", "xlm-roberta")


def parse_hf(url):
    """Lien Hugging Face (ou « auteur/modele ») -> (dépôt, fichier ou None). None si ce n'en est pas un."""
    u = (url or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/([\w.\-]+/[\w.\-]+)(?:/(?:blob|resolve)/[^/]+/(.+?))?"
                 r"(?:\?.*)?(?:/tree/.*)?$", u)
    if m:
        return m.group(1), (m.group(2) or None)
    if re.match(r"^[\w.\-]+/[\w.\-]+$", u):
        return u, None
    return None


def hf_files(repo):
    """Les fichiers de modèle d'un dépôt : [(chemin, taille)], les .gguf d'abord. Demande internet."""
    req = urllib.request.Request(f"{HF_BASE}/api/models/{repo}/tree/main?recursive=1",
                                 headers={"User-Agent": "Viki-compagnon"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("ce modèle demande un compte Hugging Face (accès restreint) : télécharge-le depuis "
                               "le site, puis glisse le fichier ici")
        if e.code == 404:
            raise RuntimeError("je ne trouve pas ce modèle : vérifie le lien")
        raise RuntimeError(f"Hugging Face a répondu une erreur ({e.code})")
    except Exception as e:
        raise RuntimeError(f"je n'arrive pas à joindre Hugging Face (il faut internet) : {str(e)[:80]}")
    out = []
    for f in data:
        p = f.get("path", "")
        if f.get("type") == "file" and p.lower().endswith((".gguf", ".safetensors")):
            out.append((p, int((f.get("lfs") or {}).get("size") or f.get("size") or 0)))
    out.sort(key=lambda t: (not t[0].lower().endswith(".gguf"), t[1]))
    return out


def downloads_dir():
    for n in ("Téléchargements", "Downloads"):
        d = Path.home() / n
        if d.is_dir():
            return d
    d = Path.home() / "Téléchargements"
    d.mkdir(parents=True, exist_ok=True)
    return d


def hf_download(repo, path, st):
    """Télécharge un fichier du dépôt dans Téléchargements (reprend là où ça s'était arrêté). Renvoie le chemin."""
    dest = downloads_dir() / Path(path).name
    part = Path(str(dest) + ".part")
    have = part.stat().st_size if part.exists() else 0
    url = f"{HF_BASE}/{repo}/resolve/main/{urllib.request.quote(path)}"
    h = {"User-Agent": "Viki-compagnon"}
    if have:
        h["Range"] = f"bytes={have}-"
    st["msg"] = "Je télécharge le modèle…"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:                       # déjà complet
            part.replace(dest)
            return dest
        raise RuntimeError(explain(f"téléchargement refusé ({e.code})"))
    except Exception as e:
        raise RuntimeError(f"le téléchargement n'a pas démarré (il faut internet) : {str(e)[:80]}")
    with r:
        if have and r.status != 206:
            have = 0                                     # le serveur repart de zéro
        total = have + int(r.headers.get("Content-Length") or 0)
        free = shutil.disk_usage(dest.parent).free
        if total and total - have > free - (500 << 20):
            raise RuntimeError(f"pas assez de place dans {dest.parent.name} : il faut {taille_txt(total - have)}, "
                               f"il reste {taille_txt(free)}")
        t0, n0 = time.monotonic(), have
        with open(part, "ab" if have else "wb") as f:
            while True:
                try:
                    b = r.read(1 << 20)
                except Exception as e:
                    raise RuntimeError("la connexion a coupé pendant le téléchargement. Reclique sur Télécharger : "
                                       f"je reprendrai où j'en étais. ({str(e)[:60]})")
                if not b:
                    break
                f.write(b)
                have += len(b)
                if st.get("stop"):
                    raise RuntimeError("annulé")
                if total:
                    st["pct"] = int(100 * have / total)
                dt = time.monotonic() - t0
                if dt > 1:
                    v = (have - n0) / dt
                    reste = (total - have) / v if v > 0 and total else 0
                    st["msg"] = (f"Je télécharge… {taille_txt(have)} / {taille_txt(total)}"
                                 + (f" · encore {int(reste // 60)} min" if reste > 90 else ""))
    if total and have < total:
        raise RuntimeError("le téléchargement s'est arrêté avant la fin. Reclique sur Télécharger : je reprendrai "
                           "où j'en étais.")
    part.replace(dest)
    return dest


def brain_problem(name):
    """« » si ce modèle Ollama peut discuter, sinon la raison (modèle d'images, d'analyse…)."""
    if not name:
        return ""
    arch, caps = "", None
    try:
        req = urllib.request.Request(OLLAMA_URL + "/api/show", data=json.dumps({"model": name}).encode(),
                                     headers={"Content-Type": "application/json"})
        with _DIRECT.open(req, timeout=5) as r:
            d = json.load(r)
        arch = str((d.get("model_info") or {}).get("general.architecture", "")).lower()
        caps = d.get("capabilities")
    except Exception:
        pass
    low = name.lower()
    if arch in _IMG_ARCH or re.search(r"(^|[-_/])(image|flux|sdxl|sd3|sd-?1\.?5|stable-?diffusion|wan|hunyuan|"
                                      r"lumina|hidream|chroma)([-_:.\d]|$)", low):
        return ("c'est un modèle qui fabrique des images : il ne sait pas discuter. Choisis plutôt un modèle de "
                "discussion (par exemple qwen3:8b)")
    if arch in _EMB_ARCH or re.search(r"embed|bge-|nomic|minilm|rerank", low) or (caps and "completion" not in caps):
        return ("c'est un modèle d'analyse (« embeddings ») : il ne sait pas écrire. Choisis plutôt un modèle de "
                "discussion (par exemple qwen3:8b)")
    return ""


def taille_txt(n):
    if n >= 1e9:
        return f"{n / 1e9:.1f} Go".replace(".", ",")
    return f"{max(1, round(n / 1e6))} Mo"


_GG = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def read_gguf(path, want=("general.architecture", "general.name", "general.size_label", "general.basename",
                          "general.type", "general.finetune")):
    """Les infos du début d'un fichier GGUF (architecture, nom…), sans lire le reste."""
    out = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("ce n'est pas un vrai fichier GGUF")
        ver = struct.unpack("<I", f.read(4))[0]
        if ver < 2:
            raise ValueError("GGUF trop ancien")
        _tensors, nkv = struct.unpack("<QQ", f.read(16))

        def s():
            n = struct.unpack("<Q", f.read(8))[0]
            return f.read(n).decode("utf-8", "replace")

        def val(t):
            if t == 8:
                return s()
            if t == 9:
                et, n = struct.unpack("<IQ", f.read(12))
                if et == 8:
                    for _ in range(n):
                        f.seek(struct.unpack("<Q", f.read(8))[0], 1)
                elif et in _GG:
                    f.seek(struct.calcsize(_GG[et]) * n, 1)
                else:
                    raise ValueError("tableau inconnu")
                return None
            fmt = _GG.get(t)
            if not fmt:
                raise ValueError("type inconnu")
            return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]

        for _ in range(min(nkv, 4000)):
            k = s()
            t = struct.unpack("<I", f.read(4))[0]
            v = val(t)
            if k in want:
                out[k] = v
            if k.startswith("tokenizer.") and len(out) >= 2:
                break
    return out


def read_safetensors(path):
    """Noms des tenseurs + métadonnées d'un .safetensors (juste l'en-tête, quelques Ko)."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        if n <= 0 or n > 200_000_000:
            raise ValueError("en-tête illisible")
        head = json.loads(f.read(n))
    meta = head.pop("__metadata__", {}) or {}
    return list(head.keys()), meta


# ================================================================ « à quoi sert ce fichier ? »
def _res(kind, titre, detail, path, **kw):
    r = {"kind": kind, "titre": titre, "detail": detail, "fichier": str(path), "taille": 0, "nom": "", "ok": kind in
         ("cerveau", "image", "musique", "voix")}
    try:
        r["taille"] = Path(path).stat().st_size
    except Exception:
        pass
    r.update(kw)
    return r


def nom_ollama(stem):
    n = stem.lower()
    n = re.sub(r"\.gguf$", "", n)
    n = re.sub(r"[^a-z0-9._-]+", "-", n).strip("-._")
    return (n or "mon-ia")[:60]


def analyze(path):
    p = Path(path)
    if p.is_dir():
        gg = sorted(p.rglob("*.gguf"), key=lambda x: x.stat().st_size, reverse=True)
        gg = [x for x in gg if "mmproj" not in x.name.lower()]
        if gg:
            return analyze(gg[0])
        st = sorted(p.rglob("*.safetensors"), key=lambda x: x.stat().st_size, reverse=True)
        if (p / "model_index.json").exists() or (p / "config.json").exists():
            return _res("format", "Format « dossier Hugging Face » : pas utilisable tel quel",
                        "Ce dossier est le format brut des chercheurs. Sur la page du modèle, cherche plutôt une "
                        "version « GGUF » (pour discuter / traduire) ou un fichier unique .safetensors (pour les "
                        "images).", p)
        if st:
            return analyze(st[0])
        onnx = list(p.rglob("*.onnx"))
        if onnx:
            return _res("voix", "Une voix", "Une voix Piper pour qu'elle te parle.", p)
        return _res("inconnu", "Je ne trouve pas d'IA dans ce dossier", "Il me faut un fichier .gguf, .safetensors "
                    "ou .onnx.", p)
    low = p.name.lower()
    ext = p.suffix.lower()
    if ext == ".zip":
        try:
            import zipfile
            with zipfile.ZipFile(p) as z:
                names = [n.lower() for n in z.namelist()]
            if any(n.endswith(".onnx") for n in names):
                return _res("voix", "Une voix (dans un .zip)", "Une voix Piper pour qu'elle te parle.", p)
        except Exception:
            pass
        return _res("inconnu", "Ce .zip ne contient pas d'IA que je connais",
                    "Décompresse-le et glisse-moi le fichier .gguf, .safetensors ou .onnx qu'il y a dedans.", p)
    if ext == ".onnx" or low.endswith(".onnx.json"):
        return _res("voix", "Une voix", "Une voix Piper : elle parlera avec. Garde le fichier .onnx.json à côté "
                    "du .onnx (les deux vont ensemble).", p)
    if ext in (".ckpt", ".pt", ".pth", ".bin", ".pkl"):
        return _res("refus", "Format refusé pour ta sécurité",
                    f"Les fichiers « {ext} » sont un vieux format qui peut cacher un programme qui s'exécute tout "
                    "seul à l'ouverture. Sur la même page, prends la version « .safetensors » (images, musique) "
                    "ou « .gguf » (discussion) : c'est le même modèle, sans ce risque.", p)
    if ext == ".gguf":
        if re.search(r"-0*\d+-of-0*\d+\.gguf$", low):
            return _res("format", "Modèle coupé en plusieurs morceaux",
                        "Ce fichier n'est qu'un morceau du modèle. Choisis une version plus petite qui tient en un "
                        "seul fichier (par exemple celle qui finit par Q4_K_M.gguf).", p)
        if "mmproj" in low:
            return _res("format", "Complément pour la vue (mmproj)",
                        "Ce fichier n'est pas un modèle à lui seul : il ajoute la vue à un autre modèle. Glisse "
                        "plutôt le fichier principal (le gros .gguf).", p)
        try:
            meta = read_gguf(p)
        except Exception as e:
            return _res("inconnu", "Fichier GGUF illisible", f"Il est peut-être incomplet (téléchargement coupé ?) : "
                        f"{e}.", p)
        arch = str(meta.get("general.architecture", "")).lower()
        name = meta.get("general.basename") or meta.get("general.name") or p.stem
        if arch in ("flux", "sd1", "sdxl", "sd3", "wan", "hunyuan-video", "ltxv", "lumina2", "hidream", "qwen_image",
                    "stable-diffusion", "chroma"):
            return _res("format", "Modèle d'images au format GGUF",
                        "Les images au format GGUF ne sont pas encore prises en charge. Prends la version "
                        "« .safetensors » (de préférence « tout-en-un » / « fp8 »).", p, arch=arch)
        if arch in ("clip", "bert", "nomic-bert", "jina-bert-v2", "t5encoder", "xlm-roberta"):
            return _res("format", "Ce modèle ne sait pas écrire",
                        "C'est un modèle d'analyse (« embeddings ») ou un complément : il ne peut pas discuter. "
                        "Cherche un modèle « Instruct » ou « Chat ».", p, arch=arch)
        r = _res("cerveau", "Une IA qui écrit", "Elle peut lui servir de cerveau pour discuter, ou pour traduire, "
                 "corriger et résumer, ou pour traduire les mangas. Tu choisis ci-dessous.", p,
                 arch=arch, nom=nom_ollama(p.stem), modele=str(name))
        if re.search(r"translat|nllb|madlad|seamless|opus|tower", low + " " + str(name).lower()):
            r["role"] = "traduire"
        return r
    if ext == ".safetensors":
        try:
            keys, meta = read_safetensors(p)
        except Exception as e:
            return _res("inconnu", "Fichier .safetensors illisible", f"Il est peut-être incomplet (téléchargement "
                        f"coupé ?) : {e}.", p)
        kl = [k.lower() for k in keys]
        joined = "\n".join(kl[:20000])
        archm = str(meta.get("modelspec.architecture", "")).lower()
        if "lora" in archm or re.search(r"(^|\n)lora_|\.lora_(up|down|a|b)\b|lora_te|\.alpha\n", joined):
            return _res("format", "Un « LoRA » (petit style à ajouter)",
                        "C'est un complément de style, pas un modèle complet. Viki ne sait pas encore les utiliser : "
                        "prends un modèle complet (« Checkpoint »).", p)
        if re.search(r"lyric|ace_step|music_dcae|speaker_embedder|genre_embedder", joined) or \
                ("ace" in low and "face" not in low):
            return _res("musique", "Un modèle de musique", "Il fera des chansons dans « Créer → Musique ».", p,
                        nom=p.name if re.search(r"ace", low) else "musique-" + p.name)
        has_unet = any(k.startswith(("model.diffusion_model.", "diffusion_model.")) for k in kl[:20000]) or \
            "double_blocks" in joined or "input_blocks" in joined
        has_te = re.search(r"cond_stage_model|conditioner\.embedders|text_encoders|clip_l\.|t5xxl", joined)
        has_vae = re.search(r"first_stage_model|(^|\n)vae\.", joined)
        if has_unet and not (has_te and has_vae):
            return _res("format", "Modèle d'images incomplet",
                        "Ce fichier ne contient que « le cœur » du modèle, sans ses autres morceaux (texte et VAE). "
                        "Sur la page du modèle, prends la version « tout-en-un » (souvent nommée « fp8 » ou "
                        "« checkpoint »).", p)
        if not has_unet:
            if re.search(r"(^|\n)(encoder|decoder)\.", joined) and len(kl) < 400:
                return _res("format", "Un « VAE » (complément)", "C'est un morceau de modèle, pas un modèle "
                            "complet. Prends un « Checkpoint » complet.", p)
            return _res("inconnu", "Je ne reconnais pas ce modèle",
                        "Ce n'est ni un modèle d'images, ni un modèle de musique que je connais.", p)
        if "double_blocks" in joined or "flux" in archm:
            tag, quoi = "flux", "FLUX"
        elif "joint_blocks" in joined or "sd3" in archm:
            tag, quoi = "sd3", "Stable Diffusion 3"
        elif "conditioner.embedders.1" in joined or "xl" in archm:
            tag, quoi = "xl", "Stable Diffusion XL"
        else:
            tag, quoi = "", "Stable Diffusion 1.5"
        new = p.name
        if tag and tag not in low:                         # le nom sert à choisir les bons réglages
            new = f"{p.stem}-{tag}{p.suffix}"
        if "schnell" in low and "schnell" not in new.lower():
            new = f"{Path(new).stem}-schnell{p.suffix}"
        return _res("image", f"Un modèle d'images ({quoi})", "Il apparaîtra dans « Créer → Image ».", p,
                    nom=new, arch=quoi)
    return _res("inconnu", "Ce n'est pas un fichier d'IA que je connais",
                "Il me faut un fichier .gguf (pour écrire), .safetensors (images, musique) ou .onnx (voix).", p)


# ================================================================ installation
def ollama_ok():
    try:
        with _DIRECT.open(OLLAMA_URL + "/api/tags", timeout=3):
            return True
    except Exception:
        return False


def ollama_exe():
    for c in (shutil.which("ollama"), "/usr/local/bin/ollama", "/usr/bin/ollama",
              str(Path.home() / ".local/bin/ollama")):
        if c and Path(c).exists():
            return c
    return ""


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # Ollama est sur ce PC : jamais de proxy


def check_complete(path, st):
    """Le fichier est-il fini de télécharger ? (sinon : « digest mismatch » chez Ollama)."""
    p = Path(path)
    for suf in (".part", ".crdownload", ".download", ".partial", ".opdownload"):
        if Path(str(p) + suf).exists() or p.with_suffix(suf).exists():
            raise RuntimeError("le fichier est encore en train de se télécharger : attends la fin du téléchargement, "
                               "puis réessaie")
    st["msg"] = "Je vérifie que le fichier est complet…"
    a = p.stat().st_size
    time.sleep(1.5)
    if p.stat().st_size != a:
        raise RuntimeError("le fichier grossit encore (téléchargement en cours) : attends qu'il soit fini, puis réessaie")


def _models_dirs():
    out = []
    if os.environ.get("OLLAMA_MODELS"):
        out.append(Path(os.environ["OLLAMA_MODELS"]))
    out += [Path.home() / ".ollama" / "models", Path("/usr/share/ollama/.ollama/models"), Path("/var/lib/ollama")]
    return out


def check_space(path):
    """Assez de place pour la copie qu'Ollama garde ?"""
    need = Path(path).stat().st_size + (300 << 20)
    for d in _models_dirs():
        p = d
        while not p.exists() and p != p.parent:
            p = p.parent
        try:
            free = shutil.disk_usage(p).free
        except Exception:
            continue
        if d.exists() and free < need:
            raise RuntimeError(f"il n'y a pas assez de place sur le disque pour qu'Ollama garde sa copie du modèle "
                               f"(il faut {taille_txt(need)}, il reste {taille_txt(free)} dans {d}) : "
                               "libère de la place, puis réessaie")
        if d.exists():
            return


def check_readable(path):
    """Le fichier se lit-il bien en entier (début et fin) ?"""
    p = Path(path)
    size = p.stat().st_size
    try:
        with open(p, "rb") as f:
            f.read(1 << 20)
            if size > (2 << 20):
                f.seek(size - (1 << 20))
                f.read(1 << 20)
    except OSError as e:
        raise RuntimeError(explain(e))


def explain(err):
    """Transforme une erreur technique en phrase claire."""
    t = str(err)
    low = t.lower()
    if "permission denied" in low or "errno 13" in low:
        return ("je n'ai pas le droit de lire ce fichier : déplace-le dans ton dossier Téléchargements "
                "ou Documents, puis réessaie")
    if "input/output error" in low or "errno 5" in low:
        return ("le disque n'arrive pas à lire ce fichier (erreur de lecture) : le fichier est peut-être abîmé, "
                "ou il est sur une clé / un disque externe qui a un souci. Copie-le sur ton disque principal "
                "ou retélécharge-le, puis réessaie")
    if "no space left" in low or "errno 28" in low:
        return "il n'y a plus de place sur le disque : libère de la place, puis réessaie"
    if "is a directory" in low:
        return "c'est un dossier, pas un fichier : glisse le fichier .gguf lui-même"
    if "file already closed" in low or "connection reset" in low or "broken pipe" in low or "eof" in low:
        return ("Ollama a coupé la réception du fichier en route (souvent : plus de place sur le disque, "
                "ou Ollama qui a redémarré). Vérifie qu'il reste de la place, puis réessaie")
    if "connection refused" in low:
        return "Ollama ne répond pas : lance-le (Réglages → Discussion → Modèle local), puis réessaie"
    return t


def _sha256(path, st, lo=0, hi=40):
    size = max(1, Path(path).stat().st_size)
    h, done = hashlib.sha256(), 0
    with open(path, "rb") as f:
        while True:
            b = f.read(8 << 20)
            if not b:
                break
            h.update(b)
            done += len(b)
            st["pct"] = lo + int((hi - lo) * done / size)
            if st.get("stop"):
                raise RuntimeError("annulé")
    return "sha256:" + h.hexdigest()


def _create_cli(exe, path, name, st):
    mf = Path(os.environ.get("TMPDIR", "/tmp")) / f"viki-modelfile-{os.getpid()}"
    mf.write_text(f"FROM \"{path}\"\n" if " " in str(path) else f"FROM {path}\n", encoding="utf-8")
    st["msg"] = "Ollama range le modèle… (ça peut prendre une minute ou deux)"
    st["pct"] = -1
    env = dict(os.environ)
    env.setdefault("OLLAMA_HOST", OLLAMA_URL)
    env["NO_PROXY"] = env["no_proxy"] = "localhost,127.0.0.1,::1"
    if os.environ.get("APPIMAGE"):                     # pas les bibliothèques de l'AppImage pour Ollama
        env["LD_LIBRARY_PATH"] = os.environ.get("COMPAGNON_ORIG_LD", "")
    pr = subprocess.Popen([exe, "create", name, "-f", str(mf)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, env=env)
    out = []
    for line in pr.stdout:
        out.append(line)
        m = re.search(r"(\d{1,3})%", line)
        if m:
            st["pct"] = int(m.group(1))
        if st.get("stop"):
            pr.kill()
            raise RuntimeError("annulé")
    pr.wait()
    try:
        mf.unlink()
    except Exception:
        pass
    if pr.returncode != 0:
        lines = [l.strip() for l in "".join(out).splitlines() if l.strip()]
        err = [l for l in lines if "error" in l.lower()] or lines or ["erreur d'Ollama"]
        raise RuntimeError(err[-1][:600])
    return name


def _create_api(path, name, st):
    size = path.stat().st_size
    st["msg"] = "Je calcule l'empreinte du fichier (vérification)…"
    dig = _sha256(path, st, 0, 35)
    st["msg"] = "J'envoie le modèle à Ollama…"

    class Prog:
        def __init__(self, f):
            self.f, self.n = f, 0

        def read(self, k=-1):
            b = self.f.read(8 << 20 if k is None or k < 0 else k)
            self.n += len(b)
            st["pct"] = 35 + int(55 * self.n / max(1, size))
            if st.get("stop"):
                raise RuntimeError("annulé")
            return b

    def upload():
        with open(path, "rb") as f:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/blobs/{dig}", data=Prog(f), method="POST",
                                         headers={"Content-Length": str(size), "Content-Type": "application/octet-stream"})
            _DIRECT.open(req, timeout=7200).read()
    try:
        try:
            upload()
        except (urllib.error.URLError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            raise RuntimeError(explain(getattr(e, "reason", e)))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        if "digest" not in body.lower():
            raise RuntimeError(explain(f"Ollama a refusé le fichier ({body[:200] or e})"))
        # l'empreinte ne colle pas : le fichier change-t-il pendant la lecture ?
        st["msg"] = "Je revérifie le fichier…"
        if _sha256(path, st, 35, 45) != dig:
            raise RuntimeError("le fichier change pendant que je le lis (téléchargement pas fini, ou disque qui a un "
                               "souci) : attends la fin du téléchargement, ou copie-le ailleurs, puis réessaie")
        st["msg"] = "J'envoie le modèle à Ollama (2e essai)…"
        try:
            upload()
        except urllib.error.HTTPError as e2:
            raise RuntimeError("Ollama reçoit un fichier différent de celui sur ton disque. Le fichier est sans doute "
                               "abîmé (téléchargement coupé) : retélécharge-le, puis réessaie. "
                               f"(détail : {e2.read().decode(errors='ignore')[:120]})")
    st["msg"] = "Ollama range le modèle…"
    st["pct"] = 92
    last = None
    for body in ({"model": name, "files": {path.name: dig}, "stream": False},
                 {"name": name, "modelfile": f"FROM @{dig}", "stream": False}):
        try:
            req = urllib.request.Request(OLLAMA_URL + "/api/create", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            _DIRECT.open(req, timeout=1800).read()
            st["pct"] = 100
            return name
        except Exception as e:
            last = e
    raise RuntimeError(f"Ollama a refusé le modèle ({last})")


def install_gguf(path, name, st):
    """Ajoute le .gguf à Ollama sous le nom donné. st : état partagé (progression, stop, message).
    D'abord la commande « ollama create » ; si Ollama se plaint de l'empreinte (« digest mismatch »),
    on vérifie le fichier nous-mêmes et on le lui envoie directement."""
    path = Path(path).resolve()
    if path.is_dir():
        raise RuntimeError(explain("is a directory"))
    check_complete(path, st)
    check_readable(path)
    check_space(path)
    exe = ollama_exe()
    first = None
    if exe:
        try:
            return _create_cli(exe, path, name, st)
        except RuntimeError as e:
            if st.get("stop") or str(e) == "annulé":
                raise
            first = e
            st["msg"] = "Ollama a mal reçu le fichier : je vérifie et je réessaie autrement…"
    try:
        return _create_api(path, name, st)
    except RuntimeError as e:
        if str(e) == "annulé" or first is None:
            raise
        raise RuntimeError(explain(e))


def place_file(src, dest_dir, new_name, st):
    """Copie (ou lien instantané si c'est le même disque) avec progression. Renvoie le chemin final."""
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / new_name
    if dst.exists():
        if dst.stat().st_size == src.stat().st_size:
            st["pct"] = 100
            return dst
        dst = dest_dir / f"{Path(new_name).stem}-{int(time.time())}{Path(new_name).suffix}"
    try:
        os.link(src, dst)                     # même disque : instantané, et aucune place en plus
        st["pct"] = 100
        st["lien"] = True
        return dst
    except Exception:
        pass
    size = max(1, src.stat().st_size)
    tmp = dst.with_suffix(dst.suffix + ".part")
    done = 0
    st["msg"] = "Je copie le fichier…"
    with open(src, "rb") as a, open(tmp, "wb") as b:
        while True:
            chunk = a.read(16 << 20)
            if not chunk:
                break
            b.write(chunk)
            done += len(chunk)
            st["pct"] = int(100 * done / size)
            if st.get("stop"):
                b.close()
                tmp.unlink(missing_ok=True)
                raise RuntimeError("annulé")
    tmp.rename(dst)
    return dst


# ================================================================ fenêtre
def make_window(comp):
    from PyQt6.QtCore import Qt, QTimer, QUrl
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                                 QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                                 QWidget)

    ICO = {"cerveau": "🧠", "image": "🎨", "musique": "🎵", "voix": "🗣️", "format": "⚠️", "refus": "⛔", "inconnu": "❓"}

    def lab(txt, obj="", wrap=True):
        lb = QLabel(txt)
        lb.setWordWrap(wrap)
        lb.setTextFormat(Qt.TextFormat.RichText)
        lb.setOpenExternalLinks(True)
        if obj:
            lb.setObjectName(obj)
        return lb

    class Drop(QFrame):
        def __init__(self, win):
            super().__init__()
            self.win = win
            self.setAcceptDrops(True)
            self.setObjectName("drop")
            self.setMinimumHeight(130)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            v = QVBoxLayout(self)
            v.addWidget(lab("<div style='font-size:28pt'>📥</div>"), 0, Qt.AlignmentFlag.AlignHCenter)
            v.addWidget(lab("<b>Glisse ici le fichier de l'IA</b><br>ou clique pour le choisir", "c"), 0,
                        Qt.AlignmentFlag.AlignHCenter)

        def mousePressEvent(self, e):
            f, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier de l'IA", str(Path.home() / "Téléchargements")
                                               if (Path.home() / "Téléchargements").exists() else str(Path.home()),
                                               "Fichiers d'IA (*.gguf *.safetensors *.onnx *.zip *.ckpt *.pt *.bin);;"
                                               "Tous les fichiers (*)")
            if f:
                self.win.load(f)

        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls():
                e.acceptProposedAction()
                self.setProperty("over", True)
                self.style().polish(self)

        def dragLeaveEvent(self, e):
            self.setProperty("over", False)
            self.style().polish(self)

        def dropEvent(self, e):
            self.setProperty("over", False)
            self.style().polish(self)
            urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if urls:
                self.win.load(urls[0])

    class Win(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.c = comp
            self.info = None
            self.st = None
            self.setWindowTitle("🧩 Ajouter une IA")
            self.resize(720, 760)
            self.setAcceptDrops(True)
            # couleurs transparentes : lisible avec le thème clair comme avec le thème sombre
            self.setStyleSheet("QFrame#drop { border: 3px dashed rgba(123,95,255,.75); border-radius: 18px; "
                               "background: rgba(123,95,255,.07); }"
                               "QFrame#drop[over=\"true\"] { background: rgba(123,95,255,.22); border-color: #7b5fff; }"
                               "QFrame#card { border: 1px solid rgba(123,95,255,.35); border-radius: 14px; "
                               "background: rgba(123,95,255,.04); }"
                               "QLabel#t { font-size: 13pt; font-weight: bold; }"
                               "QLabel#h { font-size: 11pt; font-weight: bold; margin-top: 6px; }"
                               "QLabel#c { qproperty-alignment: AlignCenter; }")
            outer = QVBoxLayout(self)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            inner = QWidget()
            L = QVBoxLayout(inner)
            L.setSpacing(10)
            sc.setWidget(inner)
            outer.addWidget(sc)
            L.addWidget(lab("Ajouter une IA", "t"))
            L.addWidget(lab("Tu as trouvé une IA sur internet ? <b>Télécharge son fichier, puis glisse-le ici.</b> Je "
                            "reconnais toute seule à quoi elle sert (discuter, traduire, images, musique, voix) et je "
                            "l'installe au bon endroit. Tout reste sur ton PC.", "aide"))
            self.drop = Drop(self)
            L.addWidget(self.drop)
            # --- ou coller un lien
            L.addWidget(lab("<b>Ou colle le lien du modèle</b> (page Hugging Face) : je te dis lesquels tiennent sur "
                            "ton PC, je télécharge et j'installe. <i>Ça utilise internet, seulement quand tu "
                            "cliques.</i>", "aide"))
            hl = QHBoxLayout()
            self.link = QLineEdit()
            self.link.setPlaceholderText("https://huggingface.co/auteur/modele")
            self.b_link = QPushButton("🔎 Regarder")
            self.b_link.clicked.connect(self.look_link)
            self.link.returnPressed.connect(self.look_link)
            hl.addWidget(self.link, 1)
            hl.addWidget(self.b_link)
            L.addLayout(hl)
            self.hf_list = QListWidget()
            self.hf_list.setVisible(False)
            self.hf_list.setMaximumHeight(170)
            self.hf_list.itemDoubleClicked.connect(lambda _i: self.dl_link())
            L.addWidget(self.hf_list)
            self.b_dl = QPushButton("⬇️ Télécharger et installer celui-ci")
            self.b_dl.setVisible(False)
            self.b_dl.clicked.connect(self.dl_link)
            L.addWidget(self.b_dl)
            self.hf_msg = lab("", "aide")
            L.addWidget(self.hf_msg)
            # --- résultat
            self.card = QFrame()
            self.card.setObjectName("card")
            cv = QVBoxLayout(self.card)
            self.r_title = lab("", "t")
            self.r_detail = lab("", "aide")
            cv.addWidget(self.r_title)
            cv.addWidget(self.r_detail)
            self.roles = QWidget()
            rv = QVBoxLayout(self.roles)
            rv.setContentsMargins(0, 0, 0, 0)
            rv.addWidget(lab("<b>À quoi doit-elle servir ?</b>"))
            self.cb_chat = QCheckBox("💬  Discuter (ce sera son cerveau)")
            self.cb_tools = QCheckBox("🌐  Traduire, corriger et résumer (boutons de la barre)")
            self.cb_manga = QCheckBox("📖  Traduire les mangas et les BD")
            for cb in (self.cb_chat, self.cb_tools, self.cb_manga):
                rv.addWidget(cb)
            row = QHBoxLayout()
            row.addWidget(QLabel("Son nom :"))
            self.name = QLineEdit()
            self.name.setMaxLength(60)
            row.addWidget(self.name, 1)
            rv.addLayout(row)
            cv.addWidget(self.roles)
            row = QHBoxLayout()
            self.b_go = QPushButton("✅  L'installer")
            self.b_go.setMinimumHeight(36)
            self.b_go.clicked.connect(self.install)
            self.b_stop = QPushButton("Annuler")
            self.b_stop.clicked.connect(self.cancel)
            self.b_stop.setVisible(False)
            row.addWidget(self.b_go)
            row.addWidget(self.b_stop)
            row.addStretch(1)
            cv.addLayout(row)
            self.bar = QProgressBar()
            self.bar.setVisible(False)
            cv.addWidget(self.bar)
            self.status = lab("", "aide")
            cv.addWidget(self.status)
            self.card.setVisible(False)
            L.addWidget(self.card)
            # --- aide : où trouver quoi
            ram = ram_go()
            L.addWidget(lab("Où trouver une IA, et quel fichier prendre ?", "h"))
            aide = [
                ("🧠 Pour discuter ou traduire", "cerveau",
                 "Prends un fichier <b>.gguf</b>. Sur la page du modèle (onglet « Files »), choisis celui qui finit par "
                 "<b>Q4_K_M.gguf</b> : c'est le meilleur compromis. "
                 + (f"Ton PC a {ram} Go de mémoire : prends un fichier de <b>moins de {max(1, ram // 2)} Go</b>. "
                    if ram else "Prends un fichier plus petit que la moitié de la mémoire (RAM) de ton PC. ")
                 + "Les noms avec « Instruct » ou « Chat » savent discuter ; « Translate » sont faits pour traduire."),
                ("🎨 Pour les images", "image",
                 "Prends un fichier <b>.safetensors</b> de type « Checkpoint » (modèle complet). Sur Civitai, filtre "
                 "sur « Checkpoint ». SD 1.5 marche partout ; SDXL et FLUX demandent une bonne carte graphique."),
                ("🎵 Pour la musique", "musique",
                 "Prends un modèle <b>ACE-Step</b> en <b>.safetensors</b> (version « all in one » / « aio »)."),
                ("🗣️ Pour sa voix", "voix",
                 "Prends les <b>deux</b> fichiers d'une voix Piper : le <b>.onnx</b> et le <b>.onnx.json</b> "
                 "(glisse le .onnx, garde le .json à côté), ou un .zip qui les contient."),
            ]
            for t, k, txt in aide:
                f = QFrame()
                f.setObjectName("card")
                v = QVBoxLayout(f)
                v.addWidget(lab(f"<b>{t}</b>"))
                v.addWidget(lab(txt, "aide"))
                r = QHBoxLayout()
                for key in (k, k + "2"):
                    if key in LIENS:
                        b = QPushButton("🔗 " + LIENS[key][0])
                        b.clicked.connect(lambda _=False, u=LIENS[key][1]: QDesktopServices.openUrl(QUrl(u)))
                        r.addWidget(b)
                r.addStretch(1)
                v.addLayout(r)
                L.addWidget(f)
            L.addWidget(lab("⛔ Je refuse les fichiers <b>.ckpt</b>, <b>.pt</b> et <b>.bin</b> : ce vieux format peut "
                            "cacher un programme. Il existe presque toujours une version .safetensors ou .gguf. Les "
                            "filtres de Viki (pas d'images choquantes) restent actifs quel que soit le modèle.", "aide"))
            # --- déjà installé
            L.addWidget(lab("Ce qui est déjà installé", "h"))
            self.lst = QListWidget()
            self.lst.setMinimumHeight(170)
            L.addWidget(self.lst)
            row = QHBoxLayout()
            b = QPushButton("🔄 Actualiser")
            b.clicked.connect(self.refresh_list)
            row.addWidget(b)
            self.b_del = QPushButton("🗑️ Supprimer celui-là")
            self.b_del.clicked.connect(self.delete)
            row.addWidget(self.b_del)
            row.addStretch(1)
            L.addLayout(row)
            L.addStretch(1)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.refresh_list()

        # ---------------------------------------------------- glisser sur toute la fenêtre
        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls():
                e.acceptProposedAction()

        def dropEvent(self, e):
            urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if urls:
                self.load(urls[0])

        # ---------------------------------------------------- analyse
        # ---------------------------------------------------- lien Hugging Face
        def look_link(self):
            got = parse_hf(self.link.text())
            if not got:
                return self.hf_msg.setText("❌ Je ne reconnais pas ce lien. Colle l'adresse de la page du modèle, "
                                           "par exemple https://huggingface.co/auteur/modele")
            repo, only = got
            self.hf_msg.setText("🔎 Je regarde ce qu'il y a dans ce modèle…")
            self.hf_list.setVisible(False)
            self.b_dl.setVisible(False)

            def done(res):
                if isinstance(res, Exception):
                    return self.hf_msg.setText(f"❌ {res}")
                files = [f for f in res if not only or f[0] == only] or res
                gg = [f for f in files if f[0].lower().endswith(".gguf")]
                if not files:
                    return self.hf_msg.setText(
                        "❌ Ce modèle n'a pas de fichier que je sais installer d'un clic (.gguf ou .safetensors). "
                        "C'est souvent un modèle « en dossier » pour développeurs : cherche sa version « GGUF » "
                        "(ajoute GGUF à ta recherche sur Hugging Face).")
                self.hf_repo = repo
                self.hf_list.clear()
                best = None
                for k, (p, size) in enumerate(gg or files):
                    niv, phrase = verdict(size) if size else ("lent", "❔ taille inconnue")
                    it = QListWidgetItem(f"{Path(p).name}   ·   {taille_txt(size) if size else '?'}\n      {phrase}")
                    it.setData(Qt.ItemDataRole.UserRole, (p, size, niv))
                    self.hf_list.addItem(it)
                    if niv == "ok":
                        best = k                                  # le plus gros qui reste rapide
                self.hf_list.setCurrentRow(best if best is not None else 0)
                self.hf_list.setVisible(True)
                self.b_dl.setVisible(True)
                self.hf_msg.setText(
                    ("J'ai sélectionné le meilleur qui reste rapide sur ton PC. " if best is not None else
                     "Aucun ne tient dans ta carte graphique : le plus petit sera le moins lent. ")
                    + "Plus le fichier est gros, plus l'IA est fine, mais plus il faut de mémoire.")
            self.c._bg(lambda: hf_files(repo), done)

        def dl_link(self):
            it = self.hf_list.currentItem()
            if it is None:
                return
            if self.st and not self.st.get("fini"):
                return self.hf_msg.setText("Attends la fin de ce qui est en cours.")
            p, size, niv = it.data(Qt.ItemDataRole.UserRole)
            if niv == "non":
                return self.hf_msg.setText("❌ Celui-ci est trop gros pour ton PC : choisis-en un plus petit.")
            self.st = st = {"pct": 0, "msg": "", "stop": False}
            self.card.setVisible(True)
            self.r_title.setText("⬇️ Téléchargement")
            self.r_detail.setText(Path(p).name)
            self.roles.setVisible(False)
            self.b_go.setVisible(False)
            self.b_stop.setVisible(True)
            self.bar.setVisible(True)
            self.b_dl.setEnabled(False)
            repo = self.hf_repo

            def done(res):
                self.timer.stop()
                st["fini"] = True
                self.b_stop.setVisible(False)
                self.bar.setVisible(False)
                self.b_dl.setEnabled(True)
                if isinstance(res, Exception):
                    msg = str(res)
                    return self.status.setText("Téléchargement mis en pause : reclique sur Télécharger pour "
                                               "reprendre." if msg == "annulé" else f"❌ {msg[:400]}")
                self.hf_msg.setText(f"✅ Téléchargé dans {res.parent.name}. Je l'analyse…")
                self.load(str(res))
            self.timer.start(300)
            self.c._bg(lambda: hf_download(repo, p, st), done)

        def load(self, path):
            if self.st and not self.st.get("fini"):
                return self.status.setText("Attends la fin de l'installation en cours.")
            self.card.setVisible(True)
            self.r_title.setText("🔎 Je regarde ce fichier…")
            self.r_detail.setText(Path(path).name)
            self.roles.setVisible(False)
            self.b_go.setVisible(False)
            self.bar.setVisible(False)
            self.status.setText("")
            self.c._bg(lambda: analyze(path), self._analyzed)

        def _analyzed(self, info):
            if isinstance(info, Exception):
                info = _res("inconnu", "Je n'arrive pas à lire ce fichier", str(info)[:200], "")
            self.info = info
            k = info["kind"]
            size = f" · {taille_txt(info['taille'])}" if info.get("taille") else ""
            self.r_title.setText(f"{ICO.get(k, '❓')} {info['titre']}")
            self.r_detail.setText(f"{info['detail']}<br><span style='font-size:9pt'>{Path(info['fichier']).name}{size}"
                                  "</span>")
            self.roles.setVisible(k == "cerveau")
            self.b_go.setVisible(bool(info.get("ok")))
            self.b_go.setEnabled(True)
            self.b_go.setText("✅  L'installer")
            if k == "cerveau":
                self.name.setText(info["nom"])
                role = info.get("role", "")
                self.cb_chat.setChecked(role != "traduire")
                self.cb_tools.setChecked(role == "traduire")
                self.cb_manga.setChecked(role == "traduire")
                ram = ram_go()
                if ram and info["taille"] > ram * 1e9 * 0.75:
                    self.status.setText(f"⚠️ Ce modèle ({taille_txt(info['taille'])}) est gros pour ton PC ({ram} Go "
                                        "de mémoire) : il risque d'être très lent. Une version plus petite (Q4, Q3) "
                                        "serait plus confortable.")
                if not ollama_ok():
                    self.status.setText("ℹ️ Pour les IA qui écrivent, il faut <b>Ollama</b> (gratuit) et il ne répond "
                                        "pas. Clique sur « Installer Ollama », puis reviens ici.")
                    self.b_go.setText("📥  Installer Ollama d'abord")
            elif k in ("image", "musique"):
                if not self._models_root():
                    self.status.setText("ℹ️ Il faut d'abord le <b>moteur d'images</b> de Viki (il sert aussi pour la "
                                        "musique). Clique sur « Installer le moteur », puis reviens ici.")
                    self.b_go.setText("📥  Installer le moteur d'abord")

        def _models_root(self):
            d = self.c.cfg.get("comfy_models_dir")
            if d and Path(d).is_dir():
                return Path(d)
            try:
                import atelier
                if atelier.ENGINE_DIR and atelier.engine_installed():
                    return Path(atelier.ENGINE_DIR) / "models"
            except Exception:
                pass
            return None

        # ---------------------------------------------------- installation
        def install(self):
            info = self.info or {}
            k = info.get("kind")
            if k == "voix":
                self.c.handle_drop([info["fichier"]]) if hasattr(self.c, "handle_drop") else None
                self.status.setText("✅ Voix ajoutée ! Choisis-la dans Réglages → Voix.")
                QTimer.singleShot(1500, self.refresh_list)
                return
            if k == "cerveau" and not ollama_ok():
                return self.c.open_models()
            if k in ("image", "musique") and not self._models_root():
                return self.c.open_studio() if hasattr(self.c, "open_studio") else None
            name = info.get("nom", "")
            if k == "cerveau":
                name = nom_ollama(self.name.text().strip() or info["nom"])
                if not (self.cb_chat.isChecked() or self.cb_tools.isChecked() or self.cb_manga.isChecked()):
                    self.cb_chat.setChecked(True)
            self.st = st = {"pct": 0, "msg": "", "stop": False}
            self.b_go.setEnabled(False)
            self.b_stop.setVisible(True)
            self.bar.setVisible(True)
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.status.setText("C'est parti…")
            src = info["fichier"]
            root = self._models_root()

            def work():
                if k == "cerveau":
                    return ("cerveau", install_gguf(src, name, st))
                dst = place_file(src, root / "checkpoints", name, st)
                return (k, dst)
            self.timer.start(300)
            self.c._bg(work, self._installed)

        def _tick(self):
            st = self.st or {}
            p = st.get("pct", 0)
            if p < 0:
                self.bar.setRange(0, 0)
            else:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(p))
            if st.get("msg"):
                self.status.setText(st["msg"])

        def cancel(self):
            if self.st:
                self.st["stop"] = True

        def _installed(self, res):
            self.timer.stop()
            self.st["fini"] = True
            self.b_stop.setVisible(False)
            self.bar.setRange(0, 100)
            if isinstance(res, Exception):
                self.bar.setVisible(False)
                self.b_go.setEnabled(True)
                msg = str(res)
                self.status.setText("Installation annulée." if msg == "annulé" else f"❌ Ça n'a pas marché : {msg[:600]}")
                return
            self.bar.setValue(100)
            k, val = res
            c = self.c
            if k == "cerveau":
                done = []
                if self.cb_chat.isChecked():
                    c._set_model(val)
                    done.append("discuter")
                if self.cb_tools.isChecked():
                    c.cfg["outils_modele"] = val
                    done.append("traduire / corriger / résumer")
                if self.cb_manga.isChecked():
                    c.cfg["manga_modele"] = val
                    done.append("traduire les mangas")
                c.save_cfg() if hasattr(c, "save_cfg") else None
                try:
                    c.recheck_ollama()
                except Exception:
                    pass
                extra = ""
                if self.cb_chat.isChecked() and getattr(c, "ia_remote", lambda: False)():
                    extra = " (elle utilise en ce moment une IA en ligne : choisis « Sur mon PC » dans Réglages → " \
                            "Discussion pour passer à celle-ci)"
                self.status.setText(f"✅ « {val} » est installée et sert à : {', '.join(done)}.{extra} Tu peux "
                                    "supprimer le fichier téléchargé si tu veux, Ollama en a gardé une copie.")
                c.say(f"J'ai une nouvelle IA : « {val} » !")
            else:
                where = "Créer → Image" if k == "image" else "Créer → Musique"
                lien = (self.st or {}).get("lien")
                self.status.setText(f"✅ Installé ! Choisis « {Path(val).name} » dans {where}."
                                    + ("" if lien else " Tu peux supprimer le fichier téléchargé : j'en ai une copie."))
                for attr in ("studio", "music_studio"):
                    w = getattr(c, attr, None)
                    try:
                        if w is not None:
                            w.refresh_local()
                    except Exception:
                        pass
                c.say("Nouveau modèle installé : on crée quelque chose ?")
            self.b_go.setVisible(False)
            self.refresh_list()

        # ---------------------------------------------------- liste
        def refresh_list(self):
            self.lst.clear()

            def add(txt, data=None):
                it = QListWidgetItem(txt)
                it.setData(Qt.ItemDataRole.UserRole, data)
                if data is None:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.lst.addItem(it)
            models = self.c.ollama_list() if ollama_ok() else []
            add("🧠 IA qui écrivent (Ollama)" + ("" if ollama_ok() else " — Ollama ne répond pas"))
            for m in models:
                add("    " + m, ("ollama", m))
            root = self._models_root()
            ck = sorted((root / "checkpoints").glob("*.safetensors")) if root and (root / "checkpoints").exists() else []
            add("🎨 Modèles d'images")
            for f in ck:
                if not re.search(r"ace|^musique-", f.name, re.I):
                    add(f"    {f.name}  ({taille_txt(f.stat().st_size)})", ("fichier", str(f)))
            add("🎵 Modèles de musique")
            for f in ck:
                if re.search(r"ace|^musique-", f.name, re.I):
                    add(f"    {f.name}  ({taille_txt(f.stat().st_size)})", ("fichier", str(f)))
            try:
                vs = [Path(v).stem for v in self.c.list_voices()] if hasattr(self.c, "list_voices") else []
            except Exception:
                vs = []
            if vs:
                add("🗣️ Voix")
                for v in vs:
                    add("    " + v)

        def delete(self):
            it = self.lst.currentItem()
            d = it.data(Qt.ItemDataRole.UserRole) if it else None
            if not d:
                return self.status.setText("Clique d'abord sur un modèle de la liste.")
            kind, val = d
            nom = val if kind == "ollama" else Path(val).name
            r = QMessageBox.question(self, "Supprimer", f"Supprimer « {nom} » ? Il faudra le retélécharger pour "
                                                        "l'utiliser à nouveau.")
            if r != QMessageBox.StandardButton.Yes:
                return
            try:
                if kind == "ollama":
                    req = urllib.request.Request(OLLAMA_URL + "/api/delete", data=json.dumps({"model": val}).encode(),
                                                 method="DELETE", headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=30).read()
                    for key in ("ollama_model", "outils_modele", "manga_modele"):
                        if self.c.cfg.get(key) == val:
                            self.c.cfg[key] = ""
                    self.c.save_cfg() if hasattr(self.c, "save_cfg") else None
                else:
                    root = self._models_root()
                    p = Path(val).resolve()
                    if not root or root.resolve() not in p.parents:          # sécurité : seulement nos dossiers
                        raise RuntimeError("ce fichier n'est pas dans le dossier des modèles")
                    p.unlink()
                self.status.setText(f"🗑️ « {nom} » est supprimé.")
            except Exception as e:
                self.status.setText(f"❌ Je n'ai pas pu le supprimer : {str(e)[:160]}")
            self.refresh_list()

    _ = threading
    return Win()
