"""Le quotidien : agendas en ligne, lecture de pages web, texte sélectionné, capture d'écran.

Tout reste sur le PC. Internet sert seulement pour ce que tu demandes : télécharger TES agendas en ligne
(adresse iCal secrète que tu colles), ou lire une page dont tu donnes l'adresse.
"""
import hashlib
import html
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) Viki"
CAL_DIR = None                 # dossier des agendas téléchargés (réglé par compagnon.py)


# ================================================================ agendas en ligne
def cal_name(url):
    return "en_ligne_" + hashlib.sha1(url.encode()).hexdigest()[:10] + ".ics"


def norm_cal_url(url):
    """webcal:// -> https:// ; garde le reste."""
    u = (url or "").strip()
    if u.lower().startswith("webcal://"):
        u = "https://" + u[9:]
    return u


def cal_kind(url):
    u = url.lower()
    if "google.com" in u:
        return "Google Agenda"
    if "remote.php/dav" in u or "nextcloud" in u or "export?" in u and "calendars" in u:
        return "Nextcloud"
    if "outlook" in u or "office365" in u or "live.com" in u:
        return "Outlook"
    if "icloud" in u:
        return "iCloud"
    return "Agenda en ligne"


def cal_ok(url):
    u = norm_cal_url(url)
    return bool(re.match(r"https?://\S+$", u))


def fetch_cal(url, dest_dir=None, timeout=20):
    """Télécharge un agenda iCal -> chemin du fichier .ics (ou lève une erreur claire)."""
    d = Path(dest_dir or CAL_DIR)
    d.mkdir(parents=True, exist_ok=True)
    u = norm_cal_url(url)
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(8_000_000)
    if b"BEGIN:VCALENDAR" not in data[:4000]:
        raise ValueError("ce lien n'est pas un agenda iCal (il doit finir souvent par .ics)")
    p = d / cal_name(u)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)
    tmp.replace(p)
    return str(p)


def cal_files(urls, dest_dir=None):
    d = Path(dest_dir or CAL_DIR or ".")
    return [str(d / cal_name(norm_cal_url(u))) for u in urls if (d / cal_name(norm_cal_url(u))).exists()]


CAL_HELP = ("Où trouver l'adresse de ton agenda :\n"
            "• Google Agenda : sur le site, ⚙️ Paramètres → ton agenda → « Adresse secrète au format iCal ».\n"
            "• Nextcloud : Agenda → « … » à côté de l'agenda → « Copier le lien privé » (ou Exporter).\n"
            "• Outlook : Paramètres → Calendrier → Calendriers partagés → Publier → lien ICS.\n"
            "• Thunderbird : il lit déjà ses agendas locaux, je les trouve toute seule.\n"
            "Cette adresse est secrète : je la garde seulement sur ton PC.")


# ================================================================ lire une page web
_DROP = re.compile(r"<(script|style|noscript|nav|header|footer|aside|form|svg|figure|iframe|button)\b.*?</\1>",
                   re.S | re.I)


def page_text(raw, limit=20000):
    """HTML -> (titre, texte principal). Garde les paragraphes et titres, pas les menus."""
    t = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    body = t
    m = re.search(r"<article\b.*?</article>", t, re.S | re.I) or re.search(r"<main\b.*?</main>", t, re.S | re.I)
    if m and len(m.group(0)) > 1500:
        body = m.group(0)
    body = _DROP.sub(" ", body)
    parts = []
    for m in re.finditer(r"<(p|h1|h2|h3|li|blockquote)\b[^>]*>(.*?)</\1>", body, re.S | re.I):
        s = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
        s = re.sub(r"\s+", " ", s).strip()
        if m.group(1).lower() == "li" and len(s) < 60:
            continue
        if len(s) >= 25 or (m.group(1).lower().startswith("h") and len(s) > 3):
            parts.append(s)
    out = []
    for s in parts:                                   # sans doublons
        if s not in out:
            out.append(s)
    text = "\n".join(out)
    return title, text[:limit]


def fetch_page(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        data = r.read(6_000_000)
    if "pdf" in ctype.lower() or data[:5] == b"%PDF-":
        return "pdf", data
    m = re.search(r"charset=([\w\-]+)", ctype)
    try:
        return "html", data.decode(m.group(1) if m else "utf-8", "replace")
    except LookupError:
        return "html", data.decode("utf-8", "replace")


def pdf_bytes_text(data, limit=20000):
    """Texte d'un PDF reçu (pdftotext)."""
    if not shutil.which("pdftotext"):
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        p = f.name
    try:
        r = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True, timeout=60)
        return (r.stdout or "")[:limit]
    except Exception:
        return ""
    finally:
        try:
            os.unlink(p)
        except Exception:
            pass


URL_RX = re.compile(r"https?://[^\s<>\"']+")


def find_url(*texts):
    for t in texts:
        m = URL_RX.search(t or "")
        if m:
            return m.group(0).rstrip(").,;»")
    return ""


# ================================================================ capture d'écran
def screenshot(path=None):
    """Capture tout l'écran -> chemin d'un PNG, ou "" (on essaie les outils du bureau, sans rien installer)."""
    path = path or os.path.join(tempfile.gettempdir(), f"viki_ecran_{os.getpid()}.png")
    try:
        os.unlink(path)
    except Exception:
        pass
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    cmds = [["spectacle", "-b", "-n", "-f", "-o", path]]
    if wayland:
        cmds += [["grim", path]]
    cmds += [["gnome-screenshot", "-f", path], ["xfce4-screenshooter", "-f", "-s", path],
             ["scrot", "-o", path], ["maim", path], ["import", "-window", "root", path]]
    for c in cmds:
        if not shutil.which(c[0]):
            continue
        try:
            subprocess.run(c, timeout=15, capture_output=True)
        except Exception:
            continue
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
    return ""


SCREEN_PROMPT = ("Voici une capture de l'écran de mon ordinateur. Décris en français, en 3 ou 4 phrases "
                 "simples, ce qu'on y voit : les applications ouvertes, ce que je semble faire, et un détail "
                 "utile s'il y en a un (une erreur, une notification…). Ne lis pas à voix haute les mots de "
                 "passe ou les informations privées que tu pourrais voir.")


def screen_prompt(question=""):
    q = (question or "").strip()
    if q and not re.fullmatch(r"(qu.?est.?ce qu.?il y a|que vois.?tu|tu vois quoi).{0,25}", q, re.I):
        return SCREEN_PROMPT + f"\nMa question : {q}"
    return SCREEN_PROMPT


# ================================================================ commandes
RX_LIRE_PAGE = re.compile(r"\b(lis|lit|lire|li)[- ]?(moi|nous)?\b.{0,20}\b(cette |la |cet |l')?(page|article|site|"
                          r"lien|url)\b", re.I)
RX_LIRE_PDF = re.compile(r"\b(lis|lit|lire)[- ]?(moi)?\b.{0,20}\b(ce |un |le |mon )?(pdf|document|fichier)\b", re.I)
RX_LIRE_SEL = re.compile(r"\b(lis|lit|lire)[- ]?(moi)?\b.{0,15}\b(la |ma |cette )?(s[ée]lection|texte s[ée]lectionn[ée]"
                         r"|ce que j.?ai s[ée]lectionn[ée])", re.I)
RX_TRAD_SEL = re.compile(r"\b(tradu\w*|translate)\b.{0,15}\b(la |ma |cette |the |my )?(s[ée]lection|texte s[ée]lectionn[ée]|ce que j.?ai "
                         r"s[ée]lectionn[ée])", re.I)
RX_ECRAN = re.compile(r"(qu.?est.?ce qu.?il y a|qu.?y a.?t.?il|que vois.?tu|tu vois quoi|regarde|d[ée]cris|"
                      r"analyse|explique).{0,25}\b(sur |à |de )?(mon |l.?)\s*[ée]cran\b", re.I)
RX_CAL = re.compile(r"\b(ajoute|branche|connecte|synchronise|abonne)\w*\b.{0,30}\b(agenda|calendrier)\b.{0,20}"
                    r"(en ligne|google|nextcloud|outlook|icloud|ical)", re.I)


def parse(text):
    """-> (action, extra) ou None."""
    t = (text or "").strip()
    if RX_TRAD_SEL.search(t):
        m = re.search(r"\ben ([a-zéèêàçûî]+)\s*$", t, re.I)
        return "trad_sel", (m.group(1) if m else "")
    if RX_LIRE_SEL.search(t):
        return "lire_sel", ""
    if RX_LIRE_PDF.search(t):
        return "lire_pdf", find_url(t)
    if RX_LIRE_PAGE.search(t) or (re.match(r"^(lis|lit)[- ]?(moi)?\b", t, re.I) and find_url(t)):
        return "lire_page", find_url(t)
    if RX_ECRAN.search(t):
        return "ecran", t
    if RX_CAL.search(t):
        return "agenda_web", find_url(t)
    return None
