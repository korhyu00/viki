"""Les petites aides du quotidien et du dev (tout reste sur le PC) :
  convertir(texte)       « 350 °F », « 5 miles », « 15h à Tokyo »  -> le résultat
  qui_port(n)            quel programme écoute sur un port
  diff_git(dossier)      ce qui a changé (pour écrire un message de commit)
  fichiers_recents()     ce que tu as ouvert hier / aujourd'hui (pour « reprendre où j'en étais »)
  en_appel()             le micro ou la webcam sert à un appel
  Surveille(chemin)      les nouvelles lignes ERROR d'un fichier de log
  TERMINAL / DOSSIER     ce que le petit bout de shell écrit (commande qui échoue, dossier courant)
"""
import datetime
import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

try:
    import touches
    _env = touches.env_systeme
except Exception:                                   # pragma: no cover
    touches = None

    def _env():
        return dict(os.environ)

FLATPAK = os.path.exists("/.flatpak-info")
BASE = Path.home() / ".local" / "share" / "viki"
TERMINAL = BASE / "terminal"          # « code<TAB>commande<TAB>dossier » quand une commande échoue
DOSSIER = BASE / "dossier"            # le dossier où est ton terminal


def hote(cmd, timeout=8):
    """Lance une commande sur ton système (même depuis le Flatpak). -> (code, sortie)."""
    if FLATPAK:
        cmd = ["flatpak-spawn", "--host"] + cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env())
        return r.returncode, (r.stdout or "") + (r.stderr or "" if r.returncode else "")
    except Exception as e:
        return 1, str(e)


# ------------------------------------------------------------------ conversions
_N = r"(-?\d+(?:[.,]\d+)?)"
UNITES = [   # (motif, facteur ou fonction, unité d'arrivée, nom lisible)
    (r"°\s*f|fahrenheit|degr[ée]s? f\b|\bf\b", lambda v: (v - 32) * 5 / 9, "°C", "°F"),
    (r"°\s*c|celsius|degr[ée]s? c\b", lambda v: v * 9 / 5 + 32, "°F", "°C"),
    (r"miles?|mi\b", 1.609344, "km", "mi"),
    (r"km/?h|kmh", 0.621371, "mph", "km/h"),
    (r"mph", 1.609344, "km/h", "mph"),
    (r"km\b|kilom[èe]tres?", 0.621371, "mi", "km"),
    (r"feet|foot|ft\b|pieds?", 0.3048, "m", "ft"),
    (r"inch(?:es)?|in\b|pouces?|\"", 2.54, "cm", "in"),
    (r"yards?|yd\b", 0.9144, "m", "yd"),
    (r"lbs?\b|pounds?|livres?", 0.45359237, "kg", "lb"),
    (r"kg\b|kilos?|kilogrammes?", 2.20462262, "lb", "kg"),
    (r"oz\b|ounces?|onces?", 28.3495231, "g", "oz"),
    (r"fl\.? ?oz", 29.5735, "mL", "fl oz"),
    (r"gallons?|gal\b", 3.78541, "L", "gal"),
    (r"cups?|tasses?", 240, "mL", "cup"),
]
VILLES = {
    "tokyo": "Asia/Tokyo", "japon": "Asia/Tokyo", "japan": "Asia/Tokyo", "seoul": "Asia/Seoul", "séoul": "Asia/Seoul",
    "pekin": "Asia/Shanghai", "pékin": "Asia/Shanghai", "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong", "new york": "America/New_York", "montreal": "America/Toronto",
    "montréal": "America/Toronto", "quebec": "America/Toronto", "québec": "America/Toronto",
    "los angeles": "America/Los_Angeles", "san francisco": "America/Los_Angeles", "londres": "Europe/London",
    "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid",
    "rome": "Europe/Rome", "moscou": "Europe/Moscow", "moscow": "Europe/Moscow", "dubai": "Asia/Dubai",
    "dubaï": "Asia/Dubai", "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "inde": "Asia/Kolkata",
    "sydney": "Australia/Sydney", "sao paulo": "America/Sao_Paulo", "são paulo": "America/Sao_Paulo",
    "mexico": "America/Mexico_City", "chicago": "America/Chicago", "la reunion": "Indian/Reunion",
    "la réunion": "Indian/Reunion", "dakar": "Africa/Dakar", "casablanca": "Africa/Casablanca",
    "est": "America/New_York", "edt": "America/New_York", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "cst": "America/Chicago", "jst": "Asia/Tokyo", "kst": "Asia/Seoul", "utc": "UTC", "gmt": "UTC",
    "cet": "Europe/Paris", "bst": "Europe/London",
}


def _f(x):
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def convertir(txt, now=None):
    """-> « 350 °F = 176,67 °C » ou "" (texte court seulement)."""
    t = (txt or "").strip()
    if not t or len(t) > 60 or "\n" in t:
        return ""
    tl = t.lower()
    m = re.fullmatch(r"(?:(?:à|a|at)\s+)?(\d{1,2})(?:\s*[h:]\s*(\d{2})?)?\s*(am|pm)?\s*(?:à|a|in|at|heure de|time in)?\s*"
                     r"([a-zéèêëàâîïôöûüç' .-]{2,20})", tl)
    if m and (m.group(4) or "").strip() in VILLES and (m.group(2) or m.group(3) or "h" in tl or ":" in tl):
        try:
            from zoneinfo import ZoneInfo
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3) == "pm" and h < 12:
                h += 12
            if m.group(3) == "am" and h == 12:
                h = 0
            if h > 23 or mi > 59:
                return ""
            zone = ZoneInfo(VILLES[m.group(4).strip()])
            now = now or datetime.datetime.now(zone)
            la_bas = datetime.datetime.combine(now.astimezone(zone).date(), datetime.time(h, mi), zone)
            ici = la_bas.astimezone()
            jour = ici.date() - la_bas.date()
            suff = " (le lendemain)" if jour.days == 1 else " (la veille)" if jour.days == -1 else ""
            lieu = m.group(4).strip()
            lieu = lieu.upper() if len(lieu) <= 4 else lieu.title()
            return f"{h:02d}:{mi:02d} à {lieu} = {ici:%H:%M} chez toi{suff}"
        except Exception:
            return ""
    m = re.fullmatch(_N + r"\s*(.+?)\s*", tl)
    if not m:
        return ""
    v = float(m.group(1).replace(",", "."))
    u = m.group(2).strip()
    for motif, f, vers, nom in UNITES:
        if re.fullmatch(r"(?:" + motif + r")\.?", u):
            r = f(v) if callable(f) else v * f
            return f"{_f(v)} {nom} = {_f(r)} {vers}"
    return ""


# ------------------------------------------------------------------ dev
def _port_proc(n):
    """Sans « ss » : /proc/net/tcp(6) / udp(6) -> inode -> le programme (nos programmes seulement)."""
    inodes = {}
    for proto, fic in (("TCP", "tcp"), ("TCP", "tcp6"), ("UDP", "udp"), ("UDP", "udp6")):
        try:
            for l in open(f"/proc/net/{fic}").read().splitlines()[1:]:
                c = l.split()
                port = int(c[1].rsplit(":", 1)[1], 16)
                if port == int(n) and (proto == "UDP" or c[3] == "0A"):     # 0A = en écoute
                    inodes[c[9]] = proto
        except (OSError, IndexError, ValueError):
            continue
    if not inodes:
        return []
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                lien = os.readlink(f"/proc/{pid}/fd/{fd}")
                if lien.startswith("socket:[") and lien[8:-1] in inodes:
                    nom = open(f"/proc/{pid}/comm").read().strip()
                    out.append((nom, int(pid), inodes[lien[8:-1]]))
        except OSError:
            continue
    return out or [("?", None, p) for p in set(inodes.values())]


def qui_port(n):
    """-> [(programme, pid ou None, proto)], ou None si on ne peut pas regarder."""
    if not (shutil.which("ss") or FLATPAK):
        return _port_proc(n) if os.path.exists("/proc/net/tcp") else None
    out = []
    for proto, opt in (("TCP", "-ltnpH"), ("UDP", "-lunpH")):
        code, txt = hote(["ss", opt, f"sport = :{int(n)}"])
        if code != 0 and not txt:
            continue
        for ligne in txt.splitlines():
            if not ligne.strip():
                continue
            m = re.findall(r'\("([^"]+)",pid=(\d+)', ligne)
            if m:
                out += [(nom, int(pid), proto) for nom, pid in m]
            elif f":{int(n)}" in ligne:
                out.append(("?", None, proto))           # à un autre utilisateur (root) : on ne voit pas qui
    vus, res = set(), []
    for x in out:
        if x not in vus:
            vus.add(x)
            res.append(x)
    return res


def dossier_terminal():
    try:
        d = DOSSIER.read_text(encoding="utf-8", errors="ignore").strip()
        return d if d and os.path.isdir(d) else ""
    except OSError:
        return ""


def diff_git(d):
    """-> (texte du diff, « staged » ou « tout ») ou (message d'erreur, "")."""
    if not d:
        return "", ""
    code, _ = hote(["git", "-C", d, "rev-parse", "--is-inside-work-tree"])
    if code != 0:
        return "pas_git", ""
    _, st = hote(["git", "-C", d, "diff", "--staged", "--stat"])
    quoi = "staged" if st.strip() else "tout"
    args = ["git", "-C", d, "diff"] + (["--staged"] if quoi == "staged" else [])
    _, stat = hote(args + ["--stat"])
    _, diff = hote(args, timeout=15)
    if not diff.strip():
        _, nouv = hote(["git", "-C", d, "status", "--short"])
        if not nouv.strip():
            return "rien", ""
        diff = "Nouveaux fichiers / changements :\n" + nouv
    return (stat.strip() + "\n\n" + diff)[:7000], quoi


# ------------------------------------------------------------------ reprendre où j'en étais
def fichiers_recents(heures=36, maxi=8):
    """Fichiers ouverts récemment (listes « récents » de GTK et de KDE) qui existent encore. -> [chemin]."""
    vus = {}
    data = Path(os.environ.get("HOST_XDG_DATA_HOME") or Path.home() / ".local" / "share") if FLATPAK else \
        Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    limite = datetime.datetime.now().timestamp() - heures * 3600
    xbel = data / "recently-used.xbel"
    try:
        txt = xbel.read_text(encoding="utf-8", errors="ignore")
        for href, mod in re.findall(r'<bookmark href="(file://[^"]+)"[^>]*?modified="([^"]+)"', txt):
            try:
                t = datetime.datetime.fromisoformat(mod.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            p = urllib.parse.unquote(href[7:])
            if t >= limite:
                vus[p] = max(t, vus.get(p, 0))
    except OSError:
        pass
    for f in (data / "RecentDocuments").glob("*.desktop") if (data / "RecentDocuments").is_dir() else []:
        try:
            t = f.stat().st_mtime
            if t < limite:
                continue
            m = re.search(r"^URL(?:\[[^\]]*\])?=(.+)$", f.read_text(encoding="utf-8", errors="ignore"), re.M)
            if m and m.group(1).startswith(("file://", "/")):
                p = urllib.parse.unquote(m.group(1).replace("file://", "", 1))
                vus[p] = max(t, vus.get(p, 0))
        except OSError:
            pass
    res = [p for p, _t in sorted(vus.items(), key=lambda x: -x[1]) if os.path.exists(p)
           and "/.cache/" not in p and "/tmp/" not in p]
    return res[:maxi]


# ------------------------------------------------------------------ en appel ?
NOS_PROGRAMMES = ("viki", "compagnon", "python", "arecord", "parecord", "pw-record", "sox", "rec", "whisper", "vosk")


def en_appel():
    """Un autre programme se sert du micro (et/ou de la webcam) en ce moment ?"""
    code, txt = hote(["pactl", "list", "source-outputs"], timeout=4)
    if code == 0:
        for bloc in txt.split("Source Output #")[1:]:
            nom = (re.search(r'application\.name = "([^"]*)"', bloc) or [None, ""])[1].lower()
            binaire = (re.search(r'application\.process\.binary = "([^"]*)"', bloc) or [None, ""])[1].lower()
            if "pavucontrol" in nom or "monitor" in bloc.lower() and "peak detect" in bloc.lower():
                continue
            if not any(p in (nom + " " + binaire) for p in NOS_PROGRAMMES):
                return True
    if not FLATPAK:                                    # la webcam (nos propres programmes seulement)
        try:
            moi = os.getuid()
            for pid in os.listdir("/proc"):
                if not pid.isdigit() or int(pid) == os.getpid():
                    continue
                try:
                    if os.stat(f"/proc/{pid}").st_uid != moi:
                        continue
                    for fd in os.listdir(f"/proc/{pid}/fd"):
                        if os.readlink(f"/proc/{pid}/fd/{fd}").startswith("/dev/video"):
                            return True
                except OSError:
                    continue
        except OSError:
            pass
    return False


# ------------------------------------------------------------------ surveiller un log
RX_LOG = re.compile(r"\b(?:ERROR|ERREUR|FATAL|CRITICAL|PANIC|Traceback|Exception|Segmentation fault|failed)\b")


class Surveille:
    """Lit seulement ce qui s'ajoute à la fin du fichier."""

    def __init__(self, chemin):
        self.chemin = os.path.expanduser(chemin)
        try:
            self.pos = os.path.getsize(self.chemin)
        except OSError:
            self.pos = 0

    def nouvelles_erreurs(self):
        try:
            taille = os.path.getsize(self.chemin)
        except OSError:
            return []
        if taille < self.pos:                             # fichier vidé / tourné
            self.pos = 0
        if taille == self.pos:
            return []
        with open(self.chemin, "rb") as f:
            f.seek(self.pos)
            bloc = f.read(min(taille - self.pos, 512 * 1024))
        self.pos = taille
        lignes = bloc.decode("utf-8", "replace").splitlines()
        return [l.strip()[:400] for l in lignes if RX_LOG.search(l)]


# ------------------------------------------------------------------ phrases toutes faites
def texte_rapide(cle, table):
    """« ;adr » -> le texte gardé (ou None)."""
    k = (cle or "").strip().lower()
    if not k.startswith(";"):
        k = ";" + k
    for c, v in (table or {}).items():
        if c.lower() == k:
            return v
    return None
