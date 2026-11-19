"""Mises à jour de Viki : regarde sur GitHub s'il existe une version plus récente, la télécharge à côté de
l'AppImage, vérifie son empreinte, puis remplace l'ancienne. Rien ne part sur internet sans ton accord."""
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

VERSION = "0.9.35-beta"
REPO = os.environ.get("VIKI_REPO", "korhyu00/viki")
API = os.environ.get("VIKI_API", "https://api.github.com").rstrip("/")
PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "Viki-x86_64.AppImage"
ASSET_FLATPAK = "viki.flatpak"
FLATPAK_ID = "io.github.korhyu00.Viki"
UA = {"User-Agent": "Viki-compagnon", "Accept": "application/vnd.github+json"}


def _num(v):
    """« v0.9.1-beta » -> (0, 9, 1, 0) ; une bêta compte moins qu'une version finale."""
    v = (v or "").strip().lower().lstrip("v")
    m = re.match(r"(\d+(?:\.\d+)*)(.*)", v)
    if not m:
        return (0,)
    nums = [int(x) for x in m.group(1).split(".")] + [0] * 3
    return tuple(nums[:3]) + (0 if m.group(2).strip("-. ") else 1,)


def plus_recente(tag, actuelle=None):
    return _num(tag) > _num(actuelle or VERSION)


def derniere():
    """-> {"tag", "nom", "notes", "url", "taille", "sha256", "page"} de la dernière Release (demande internet)."""
    req = urllib.request.Request(f"{API}/repos/{REPO}/releases/latest", headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    def fichier(nom):
        a = next((x for x in d.get("assets", []) if x.get("name") == nom), None) or {}
        dig = a.get("digest") or ""
        return {"url": a.get("browser_download_url"), "taille": int(a.get("size") or 0),
                "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""}
    info = {"tag": d.get("tag_name", ""), "nom": d.get("name") or d.get("tag_name", ""),
            "notes": (d.get("body") or "").strip(), "page": d.get("html_url") or PAGE}
    info.update(fichier(ASSET))
    info["flatpak"] = fichier(ASSET_FLATPAK)
    return info


def dans_flatpak():
    return os.path.exists("/.flatpak-info")


def _hote(*cmd):
    import subprocess
    r = subprocess.run(["flatpak-spawn", "--host", *cmd], capture_output=True, text=True, timeout=20)
    return r.stdout if r.returncode == 0 else ""


def flatpak_par_depot():
    """Flatpak installé depuis un dépôt en ligne (le dépôt Viki, ajouté dans Discover/Bazaar…) plutôt que depuis
    le fichier viki.flatpak : on se met alors à jour par ce dépôt, comme toutes les applis du magasin."""
    try:
        origine = _hote("flatpak", "info", "--show-origin", FLATPAK_ID).strip()
        if not origine:
            return False
        for ligne in _hote("flatpak", "remotes", "--columns=name,url").splitlines():
            nom, _, url = ligne.partition("\t")
            if nom.strip() == origine:
                return url.strip().startswith(("http://", "https://"))
    except Exception:
        pass
    return False


def _telecharger(url, part, taille, sha, st):
    """Télécharge url dans part en vérifiant taille et empreinte (st : progression, st["stop"] : annuler)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Viki-compagnon"})
    h, n, t0 = hashlib.sha256(), 0, time.monotonic()
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or taille or 0)
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            h.update(b)
            n += len(b)
            if st.get("stop"):
                f.close()
                part.unlink(missing_ok=True)
                raise RuntimeError("annulé")
            if total:
                st["pct"] = int(100 * n / total)
                dt = time.monotonic() - t0
                reste = (total - n) / (n / dt) if dt > 1 and n else 0
                st["msg"] = f"{n / 2**20:.0f} / {total / 2**20:.0f} Mo" + (f" · encore {int(reste)} s" if reste > 5 else "")
    if taille and n != taille:
        part.unlink(missing_ok=True)
        raise RuntimeError("le téléchargement est incomplet (connexion coupée ?) : réessaie")
    if sha and h.hexdigest() != sha:
        part.unlink(missing_ok=True)
        raise RuntimeError("le fichier reçu ne correspond pas à celui publié (empreinte différente) : je ne l'installe pas")


def telecharger(info, st):
    """Télécharge la nouvelle AppImage à côté de l'actuelle, vérifie taille et empreinte, puis la met à sa place.
    -> chemin de l'AppImage (même nom que l'ancienne). L'ancienne est gardée en « .ancienne » (au cas où)."""
    cur = Path(os.environ["APPIMAGE"])
    if not os.access(cur.parent, os.W_OK):
        raise RuntimeError(f"je n'ai pas le droit d'écrire dans {cur.parent} : déplace-moi dans ton dossier perso")
    part = cur.with_name(cur.name + ".nouvelle")
    _telecharger(info["url"], part, info.get("taille"), info.get("sha256"), st)
    os.chmod(part, 0o755)
    old = cur.with_name(cur.name + ".ancienne")
    try:
        os.replace(cur, old)
    except OSError:
        pass
    os.replace(part, cur)
    return cur


def telecharger_flatpak(info, st):
    """Version Flatpak : télécharge viki.flatpak dans son cache (visible par ton système), vérifié.
    -> chemin du fichier ; il s'installe au redémarrage (commande_flatpak)."""
    fp = info.get("flatpak") or {}
    if not fp.get("url"):
        raise RuntimeError("cette version n'a pas encore de fichier Flatpak sur GitHub")
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "maj"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / ASSET_FLATPAK
    part = d / (ASSET_FLATPAK + ".nouveau")
    _telecharger(fp["url"], part, fp.get("taille"), fp.get("sha256"), st)
    os.replace(part, dest)
    return dest


def commande_flatpak_depot():
    """Mise à jour par le dépôt (comme le ferait le magasin), puis relance."""
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "maj"
    d.mkdir(parents=True, exist_ok=True)
    from shlex import quote
    journal = quote(str(d / "installation.txt"))
    return ["flatpak-spawn", "--host", "sh", "-c",
            f"sleep 2; flatpak update --noninteractive -y {FLATPAK_ID} > {journal} 2>&1; exec flatpak run {FLATPAK_ID}"]


def commande_flatpak(chemin):
    """Commande lancée sur ton système après la fermeture de Viki : installe la nouvelle version puis la relance.
    Si l'installation échoue, l'ancienne version se relance quand même (le journal reste dans maj/installation.txt)."""
    from shlex import quote
    f = quote(str(chemin))
    journal = quote(str(Path(chemin).with_name("installation.txt")))
    return ["flatpak-spawn", "--host", "sh", "-c",
            f"sleep 2; flatpak install --user --reinstall --noninteractive -y {f} > {journal} 2>&1; "
            f"rm -f {f}; exec flatpak run {FLATPAK_ID}"]
