"""« Ma liste » : tes liens de séries, films, musiques et vidéos. Viki les rouvre là où tu t'es arrêté.
Tu donnes tes propres liens (YouTube, Crunchyroll, Netflix, ta chaîne…). Rien n'est envoyé nulle part."""
import datetime
import difflib
import html
import os
import shutil
import subprocess
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

TYPES = {"serie": "📺 Série / animé", "film": "🎬 Film", "musique": "🎵 Musique", "video": "▶️ Vidéo", "autre": "🔗 Autre"}
ICON = {"serie": "📺", "film": "🎬", "musique": "🎵", "video": "▶️", "autre": "🔗"}


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


URL_RE = re.compile(r"https?://\S+|www\.\S+")


def guess_type(url, text=""):
    u, t = url.lower(), _sa(text)
    if re.search(r"\b(serie|animes?|episode|saison)\b", t) or re.search(
            r"crunchyroll|adn|animationdigitalnetwork|netflix\.com/watch|disneyplus|primevideo|max\.com|tv\.apple|"
            r"france\.tv|arte\.tv|6play|m6\.fr|tf1|mycanal|paramountplus|/episode|[?&]ep=|s\d{1,2}e\d{1,3}", u + " " + t):
        return "serie"
    if re.search(r"\b(film|movie)\b", t):
        return "film"
    if re.search(r"\b(musique|chanson|son|playlist|album|morceau)\b", t) or re.search(
            r"music\.youtube|spotify|deezer|soundcloud|bandcamp|list=", u):
        return "musique"
    if re.search(r"youtube\.com|youtu\.be|twitch\.tv|dailymotion|vimeo", u):
        return "video"
    return "autre"


def page_title(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"})
        with urllib.request.urlopen(req, timeout=8) as r:
            page = r.read(300000).decode("utf-8", "replace")
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', page) or \
            re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        if m:
            t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
            t = re.sub(r"\s*[-|–]\s*(YouTube|Crunchyroll|Netflix|ADN|Twitch|Dailymotion|Spotify).*$", "", t)
            return t[:80]
    except Exception:
        pass
    return ""


# ------------------------------------------------------------------ temps et épisodes
def parse_time(t):
    """« 23 minutes », « 1h05 », « 23:15 », « 1 heure 5 », « 45 min 30 » -> secondes, ou None."""
    t = _sa(t)
    m = re.search(r"\b(\d{1,2}):(\d{2}):(\d{2})\b", t)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.search(r"\b(\d{1,3}):(\d{2})\b", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"\b(\d{1,2})\s*(?:h|heures?)\s*(\d{1,2})?\b", t)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2) or 0) * 60
    m = re.search(r"\b(\d{1,3})\s*(?:min|minutes?|mn)\b(?:\s*(?:et\s*)?(\d{1,2})\s*(?:s|sec|secondes?)?\b)?", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    return None


def fmt_time(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


_EP_PAT = re.compile(r"(episode[-_ ]?|[-_/]ep[-_]?|[?&]ep=|[?&]episode=|e)(\d{1,4})(?!.*(?:episode[-_ ]?|[-_/]ep[-_]?|[?&]ep=|"
                     r"[?&]episode=|[sS]\d{1,2}[eE])\d)", re.I)


def has_ep_in_url(url):
    return bool(re.search(r"episode[-_ ]?\d|[-_/]ep[-_]?\d|[?&]ep(?:isode)?=\d|[sS]\d{1,2}[eE]\d", url, re.I))


def ep_from_url(url):
    m = re.search(r"[sS]\d{1,2}[eE](\d{1,4})", url) or re.search(r"episode[-_ ]?(\d{1,4})|[-_/]ep[-_]?(\d{1,4})|"
                                                                  r"[?&]ep(?:isode)?=(\d{1,4})", url, re.I)
    if not m:
        return 0
    return int(next(g for g in m.groups() if g))


def url_for_ep(url, ep):
    """Remplace le numéro d'épisode dans le lien (garde les zéros : e05 -> e06)."""
    def rep(m):
        num = m.group(m.lastindex)
        return m.group(0)[: m.start(m.lastindex) - m.start(0)] + str(ep).zfill(len(num))
    for pat in (r"([sS]\d{1,2}[eE])(\d{1,4})", r"(episode[-_ ]?)(\d{1,4})", r"([-_/]ep[-_]?)(\d{1,4})",
                r"([?&]ep(?:isode)?=)(\d{1,4})"):
        found = list(re.finditer(pat, url, re.I))
        if found:
            m = found[-1]
            return url[: m.start()] + rep(m) + url[m.end():]
    return url


def resume_url(it, url=None):
    url = url or it["url"]
    if it.get("ep") and has_ep_in_url(url):
        url = url_for_ep(url, it["ep"])
    t = int(it.get("temps") or 0)
    if t > 5 and re.search(r"youtube\.com/watch|youtu\.be/|music\.youtube", url):
        url = re.sub(r"[?&]t=\d+s?", "", url)
        url += ("&" if "?" in url else "?") + f"t={t}s"
    elif t > 5 and re.search(r"twitch\.tv/videos|dailymotion\.com/video|vimeo\.com/\d", url):
        url += ("&" if "?" in url else "?") + (f"t={t // 3600}h{t % 3600 // 60}m{t % 60}s" if "twitch" in url
                                              else f"start={t}" if "dailymotion" in url else f"#t={t}s")
    return url



SITES = {"youtube": "YouTube", "youtu.be": "YouTube", "music.youtube": "YouTube Music", "crunchyroll": "Crunchyroll",
         "animationdigitalnetwork": "ADN", "adn.": "ADN", "netflix": "Netflix", "disneyplus": "Disney+",
         "primevideo": "Prime Video", "amazon.": "Prime Video", "max.com": "Max", "tv.apple": "Apple TV+",
         "paramountplus": "Paramount+", "mycanal": "Canal+", "france.tv": "france.tv", "arte.tv": "Arte",
         "twitch": "Twitch", "dailymotion": "Dailymotion", "vimeo": "Vimeo", "spotify": "Spotify",
         "deezer": "Deezer", "soundcloud": "SoundCloud", "bandcamp": "Bandcamp", "apple.com/music": "Apple Music",
         "music.apple": "Apple Music", "qobuz": "Qobuz", "tidal": "Tidal", "plex": "Plex", "jellyfin": "Jellyfin"}


def site_label(url):
    u = url.lower()
    for k, v in SITES.items():
        if k in u:
            return v
    host = urllib.parse.urlparse(url if "://" in url else "https://" + url).netloc
    return re.sub(r"^www\.", "", host) or "lien"


def links(it):
    """Tous les liens d'un titre : le principal puis les autres -> [{url, nom}]."""
    out = [{"url": it["url"], "nom": it.get("site") or site_label(it["url"])}]
    for l in it.get("liens", []):
        if l.get("url") and l["url"] != it["url"]:
            out.append({"url": l["url"], "nom": l.get("nom") or site_label(l["url"])})
    return out


def pick_link(it, where=""):
    """« sur ADN », « sur youtube » -> le lien de ce site ; sinon le principal."""
    w = _sa(where).strip()
    if w:
        for l in links(it):
            if w in _sa(l["nom"]) or w.replace(" ", "") in l["url"].lower():
                return l["url"]
    return it["url"]


def add_link(it, url, nom=""):
    """Ajoute un lien à un titre. Même site : remplace (ex. un nouvel épisode) ; autre site : en plus."""
    lab = nom or site_label(url)
    if site_label(it["url"]) == site_label(url) and not nom:
        it["url"] = url
        return "maj"
    lst = it.setdefault("liens", [])
    for l in lst:
        if l["url"] == url or (not nom and site_label(l["url"]) == site_label(url)):
            l["url"] = url
            return "maj"
    lst.append({"url": url, "nom": lab})
    return "ajout"


def parse_bulk(text):
    """Plusieurs lignes « Nom - lien », « Nom : lien », « lien Nom » ou juste des liens -> [(nom, url)]."""
    out = []
    for line in text.splitlines():
        for m in URL_RE.finditer(line):
            url = m.group(0).rstrip(").,;»\"'")
            rest = (line[:m.start()] + " " + line[m.end():]).strip()
            nom = re.sub(r"^[\s\-–—:|•*\d.)]+|[\s\-–—:|•*]+$", "", rest).strip()
            out.append((nom, url))
    seen, res = set(), []
    for nom, url in out:
        if url not in seen:
            seen.add(url)
            res.append((nom, url))
    return res


# ------------------------------------------------------------------ navigateurs
NAVS = [  # (id, nom, commandes possibles, appli flatpak)
    ("firefox", "Firefox", ["firefox"], "org.mozilla.firefox"),
    ("chrome", "Google Chrome", ["google-chrome-stable", "google-chrome", "chrome"], "com.google.Chrome"),
    ("chromium", "Chromium", ["chromium", "chromium-browser"], "org.chromium.Chromium"),
    ("brave", "Brave", ["brave", "brave-browser"], "com.brave.Browser"),
    ("edge", "Microsoft Edge", ["microsoft-edge-stable", "microsoft-edge"], "com.microsoft.Edge"),
    ("vivaldi", "Vivaldi", ["vivaldi-stable", "vivaldi"], "com.vivaldi.Vivaldi"),
    ("opera", "Opera", ["opera"], "com.opera.Opera"),
    ("librewolf", "LibreWolf", ["librewolf"], "io.gitlab.librewolf-community"),
    ("zen", "Zen", ["zen-browser", "zen"], "app.zen_browser.zen"),
    ("waterfox", "Waterfox", ["waterfox"], "net.waterfox.waterfox"),
    ("floorp", "Floorp", ["floorp"], "one.ablaze.floorp"),
    ("ungoogled", "Ungoogled Chromium", ["ungoogled-chromium"], "io.github.ungoogled_software.ungoogled_chromium"),
    ("falkon", "Falkon", ["falkon"], "org.kde.falkon"),
    ("epiphany", "GNOME Web", ["epiphany"], "org.gnome.Epiphany"),
    ("mpv", "Lecteur mpv (sans navigateur)", ["mpv"], "io.mpv.Mpv"),
]
_NAV_CACHE = {}


def installed_navs():
    """-> [(id, nom)] des navigateurs trouvés sur ce PC (commande ou flatpak)."""
    if "l" in _NAV_CACHE:
        return _NAV_CACHE["l"]
    flat = ""
    if shutil.which("flatpak"):
        try:
            flat = subprocess.run(["flatpak", "list", "--app", "--columns=application"], capture_output=True,
                                  text=True, timeout=5).stdout
        except Exception:
            pass
    out = []
    for nid, nom, cmds, fp in NAVS:
        if any(shutil.which(x) for x in cmds) or (fp and fp in flat):
            out.append((nid, nom))
    _NAV_CACHE["l"] = out
    return out


def nav_name(nid):
    return next((n for i, n, _c, _f in NAVS if i == nid), "")


def find_nav(text):
    """« avec firefox », « sur brave » -> id du navigateur, ou ""."""
    t = _sa(text)
    for nid, nom, cmds, _fp in NAVS:
        keys = {nid, _sa(nom)} | {_sa(nom).split()[-1]} | ({"google chrome"} if nid == "chrome" else set())
        if any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in keys if k):
            return nid
    return ""


def _env():
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "QT_PLUGIN_PATH"):
        env.pop(k, None)
    if os.environ.get("COMPAGNON_ORIG_LD"):
        env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
    return env


def open_with(url, nid):
    """Ouvre le lien avec ce navigateur. False si introuvable (on ouvrira avec celui par défaut)."""
    for i, _nom, cmds, fp in NAVS:
        if i != nid:
            continue
        exe = next((shutil.which(x) for x in cmds if shutil.which(x)), None)
        args = ([exe] if exe else ["flatpak", "run", fp] if shutil.which("flatpak") else None)
        if not args:
            return False
        if nid == "mpv":
            args += ["--force-window=yes", "--really-quiet"]
        try:
            subprocess.Popen(args + [url], env=_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return True
        except Exception:
            return False
    return False


def link_nav(it, url):
    """Navigateur choisi pour ce lien (sinon celui du titre, sinon "")."""
    if url == it["url"]:
        return it.get("nav", "")
    for l in it.get("liens", []):
        if l["url"] == url:
            return l.get("nav") or it.get("nav", "")
    return it.get("nav", "")


def set_link_nav(it, url, nid):
    if url == it["url"]:
        it["nav"] = nid
        return
    for l in it.get("liens", []):
        if l["url"] == url:
            l["nav"] = nid


# ------------------------------------------------------------------ prononciation (dictée approximative)
def phon(s):
    """Clé « sonore » grossière (français / anglais) : « one pisse » ≈ « one piece », « chil » ≈ « chill »."""
    s = _sa(s)
    for a, b in (("ph", "f"), ("qu", "k"), ("ck", "k"), ("ch", "x"), ("sh", "x"), ("eau", "o"), ("au", "o"),
                 ("ou", "u"), ("oo", "u"), ("ee", "i"), ("ea", "i"), ("ie", "i"), ("y", "i"), ("w", "v"), ("z", "s"),
                 ("ss", "s"), ("ce", "se"), ("ci", "si"), ("c", "k"), ("h", ""), ("ai", "e"), ("ei", "e"),
                 ("er ", "e "), ("ez ", "e "), ("an", "en"), ("em", "en"), ("om", "on"), ("x ", " ")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    s = re.sub(r"[stdpe]\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)

# ------------------------------------------------------------------ recherche dans la liste
GENERIC = {"musique", "musiques", "chanson", "chansons", "son", "sons", "playlist", "playlists", "serie", "series",
           "film", "films", "video", "videos", "anime", "animes", "episode", "truc", "quelque", "chose", "un", "une",
           "le", "la", "les", "de", "du", "des", "ma", "mon", "mes", "moi", "peu"}
_ART = r"^(?:le |la |les |l'|mon |ma |mes |un |une |du |de la |des |de |un peu de |un peu d')+"


def _words(s):
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in GENERIC]


def _norm(w):
    return w[:-1] if len(w) > 3 and w[-1] in "sx" else w


def find(items, query, strict=False):
    """Retrouve un titre de la liste. Un mot générique seul (« musique ») ne suffit jamais.
    strict=True : la phrase doit être presque exactement le nom (pour « One Piece » tout seul)."""
    q = _sa(query).strip(" ?!.,")
    q = re.sub(_ART, "", q).strip()
    if not q or not items:
        return None
    qw = {_norm(w) for w in _words(q)}
    best, best_sc = None, 0.0
    for it in items:
        n = re.sub(_ART, "", _sa(it["nom"])).strip()
        nw = {_norm(w) for w in _words(n)}
        if q == n:
            return it
        ratio = difflib.SequenceMatcher(None, q, n).ratio()
        if strict:
            sc = ratio if ratio >= 0.85 else (0.9 if nw and nw == qw else
                                              0.86 if qw and qw <= nw and len(qw) / len(nw) >= 0.5 else 0)
        else:
            if not qw:                                   # rien que des mots génériques
                continue
            cover_n = len(nw & qw) / len(nw) if nw else 0     # le nom est-il dans la phrase ?
            cover_q = len(nw & qw) / len(qw)                  # la phrase parle-t-elle surtout de ce titre ?
            fuzzy = 0.0
            if cover_n < 1:
                hits = sum(1 for w in nw if any(difflib.SequenceMatcher(None, w, x).ratio() >= 0.8 for x in qw))
                fuzzy = hits / len(nw) if nw else 0
            sc = max(ratio if ratio >= 0.72 else 0, cover_n * 0.6 + cover_q * 0.4 if cover_n >= 0.99 else 0,
                     (fuzzy * 0.6 + cover_q * 0.3) if fuzzy >= 0.99 else 0,
                     0.5 * cover_n + 0.3 * cover_q if cover_n >= 0.5 and cover_q >= 0.5 else 0)
        if not strict and sc < 0.55 and len(n) >= 4:          # dictée approximative : ça « sonne » pareil ?
            pq, pn = phon(q), phon(n)
            if pn and pq and (pn in pq and len(pn) >= 0.5 * len(pq) or
                              difflib.SequenceMatcher(None, pq, pn).ratio() >= 0.8):
                sc = 0.6
        if sc > best_sc:
            best, best_sc = it, sc
    return best if best_sc >= 0.55 else None


def guess(items, query):
    """Le titre le plus proche, même de loin -> (titre, score). Pour demander « tu voulais dire … ? »."""
    q = re.sub(_ART, "", _sa(query).strip(" ?!.,")).strip()
    best, sc = None, 0.0
    for it in items:
        n = re.sub(_ART, "", _sa(it["nom"])).strip()
        r = max(difflib.SequenceMatcher(None, q, n).ratio(), difflib.SequenceMatcher(None, phon(q), phon(n)).ratio())
        if r > sc:
            best, sc = it, r
    return best, sc


# ------------------------------------------------------------------ commandes
_WATCH = (r"(?:je (?:veux|voudrais|vais)|j'ai envie d'|on (?:peut|va)|tu peux|envie d')\s*(?:regarder|voir|ecouter|"
          r"reprendre|continuer|mater|lancer|mettre)|^(?:on )?(?:regarde|regardons|reprends|reprenons|continue|continuons|"
          r"relance|lance|mets?|ouvre|joue|ecoute|ecoutons|mate)(?:[- ](?:moi|nous))?")


def parse(text, items):
    """-> (action, données) ou None. Actions : add, open, next, set_ep, set_time, show, remove."""
    raw = text.strip()
    t = _sa(raw).strip(" ?!.")
    if re.search(r"\b(?:musique|son|chanson|playlist)s? (?:de|dans|depuis) ma liste\b|\bau hasard dans ma liste\b", t):
        return ("random", "musique")
    if re.search(r"^(?:ma liste|mes liens|ma liste (?:de|a) (?:regarder|voir|ecouter)|montre(?:[- ]moi)? ma liste|"
                 r"ouvre ma liste|qu'?est[- ]ce que (?:je regarde|j'ai a regarder))$", t):
        return ("show", None)
    url = URL_RE.search(raw)
    if re.search(r"\b(?:ajoute|garde|enregistre|sauvegarde|retiens|mets?)\b.*\b(?:lien|liste|url)\b", t) or \
            (url and re.search(r"\b(?:ajoute|garde|enregistre)\b", t)):
        if not re.search(r"\b(?:lien|liste|url)\b", t) and not url:
            return None
        if re.search(r"\b(?:courses|snippet|code|notes?)\b", t):
            return None
        m = re.search(r"(?:sous le nom(?: de)?|nomme|appele|qui s'appelle|c'est|pour)\s+[«\"']?(.+?)[»\"']?\s*$", raw, re.I)
        name = m.group(1).strip() if m and not URL_RE.match(m.group(1).strip()) else ""
        name = URL_RE.sub("", name).strip(" .")
        return ("add", {"url": url.group(0) if url else "", "nom": name, "texte": raw})
    m = re.search(r"\b(?:supprime|enleve|retire|efface)\b\s+(.+?)\s+(?:de|dans)\s+ma liste\b", t)
    if m:
        it = find(items, m.group(1))
        return ("remove", it) if it else None
    # épisode
    m = re.search(r"\b(?:j'?en suis|je suis|je me suis arrete|on en est|on s'est arrete|j'ai fini|j'ai vu|j'ai termine|"
                  r"je suis rendu)\b.*?\bep(?:isode)?\s*(\d{1,4})\b(?:.*?\b(?:de|d'|dans|du)\s+(.+))?$", t) or \
        re.search(r"^(.+?)\s*:?\s*(?:j'en suis a l')?ep(?:isode)?\s*(\d{1,4})$", t)
    if m:
        if m.re.pattern.startswith("^(.+?)"):
            name, ep = m.group(1), int(m.group(2))
        else:
            ep, name = int(m.group(1)), m.group(2) or ""
        fini = bool(re.search(r"\b(?:j'ai fini|j'ai vu|j'ai termine)\b", t))
        it = find(items, name) if name else _last(items, "serie")
        return ("set_ep", (it, ep + 1 if fini else ep)) if it else None
    # temps
    if re.search(r"\b(?:je me suis arrete|j'?en suis|on s'est arrete|j'ai arrete|je suis a|on en est|arrete a|pause a|"
                 r"stoppe a)\b", t):
        sec = parse_time(t)
        if sec is not None:
            m = re.search(r"\b(?:de|d'|dans|du)\s+([^0-9].+)$", t)
            it = (find(items, m.group(1)) if m else None) or _last(items)
            return ("set_time", (it, sec)) if it else None
    # épisode suivant
    m = re.search(r"\b(?:episode suivant|prochain episode|ep suivant|la suite)\b(?:\s+(?:de|d'|du)\s+(.+))?", t)
    if m:
        it = (find(items, m.group(1)) if m.group(1) else None) or _last(items, "serie")
        return ("next", it) if it else None
    # « mes / mais / m'est musique chill » (faute de frappe ou dictée) et nom tout seul
    m = re.match(r"^(?:mes|mais|m'est|mai|me|mettre|met moi|mes moi|mais moi)\s+(.+)$", t)
    if m:
        it = find(items, m.group(1)) if not re.match(r"^(?:notes?|courses|snippets?|souvenirs?|images?|rappels?|"
                                                     r"mails?|liens?|copies|todo|projets?)\b", m.group(1)) else None
        if it:
            return ("open", it)
    it = find(items, t, strict=True)
    if it:
        return ("open", it)
    m = re.match(r"^(.+?)\s+(?:sur|avec|via|dans)\s+(.+)$", t)          # « One Piece sur ADN » tout seul
    if m:
        it = find(items, m.group(1), strict=True)
        if it:
            return ("open", (it, m.group(2)))
    # regarder / écouter
    m = re.search("(?:" + _WATCH + r")\s+(?:a |la suite de |la suite d')?(.+)$", t)
    if m:
        what = re.sub(r"\s+(?:la ou (?:je|on) (?:m'|s')?(?:etai[st]|en etai[st]) ?(?:arrete)?.*|stp|svp|s'il te plait|"
                      r"maintenant|ce soir|sur ma liste|de ma liste)$", "", m.group(1)).strip()
        if re.search(r"^(?:ma liste|mes liens)$", what):
            return ("show", None)
        where = ""
        m2 = re.search(r"^(.+?)\s+(?:sur|avec|via|depuis|dans)\s+(.+)$", what)
        if m2 and find(items, m2.group(1)):
            what, where = m2.group(1), m2.group(2)
        it = find(items, what)
        if it:
            return ("open", (it, where)) if where else ("open", it)
        g, sc = guess(items, what)
        if g and sc >= 0.5 and not re.search(r"\b(?:musique|chanson|son|film|serie|video|truc)s?$", what) \
                and len(_words(what)) >= 1:
            return ("guess", (g, what))
    return None


def _last(items, kind=None):
    pool = [i for i in items if kind is None or i.get("type") == kind]
    return max(pool, key=lambda i: i.get("vu", ""), default=None)


def where_txt(it):
    parts = []
    if it.get("saison"):
        parts.append(f"saison {it['saison']}")
    if it.get("ep"):
        parts.append(f"épisode {it['ep']}")
    if it.get("temps"):
        parts.append(f"à {fmt_time(it['temps'])}")
    return ", ".join(parts)


# ------------------------------------------------------------------ images des titres
COULEURS_TYPE = {"serie": "#4a2b6e", "film": "#6b2f2f", "musique": "#8a2d4a", "video": "#24506b", "autre": "#3a4a3a"}
ICONES_TYPE = {"serie": 0xea8d, "film": 0xeafa, "musique": 0xeafc, "video": 0xed46, "autre": 0xeade}


def _yt_id(url):
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else ""


def _get_json(url, data=None):
    import json
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Viki/1.0", "Content-Type": "application/json",
                                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _poster_serie(nom):
    """Affiche officielle : TVmaze (séries), sinon AniList (animés)."""
    try:
        d = _get_json("https://api.tvmaze.com/singlesearch/shows?q=" + urllib.parse.quote(nom))
        im = (d.get("image") or {})
        if im.get("original") or im.get("medium"):
            return im.get("original") or im.get("medium")
    except Exception:
        pass
    try:
        import json
        q = "query ($s: String) { Media(search: $s, type: ANIME) { coverImage { extraLarge large } } }"
        d = _get_json("https://graphql.anilist.co", json.dumps({"query": q, "variables": {"s": nom}}).encode())
        c = ((d.get("data") or {}).get("Media") or {}).get("coverImage") or {}
        return c.get("extraLarge") or c.get("large") or ""
    except Exception:
        return ""


def chercher_image(it, dossier):
    """Trouve une image pour un titre et la garde dans « dossier ». -> nom du fichier, ou ""."""
    import hashlib
    try:
        import suivi
    except Exception:
        suivi = None
    url = (links(it)[0]["url"] if links(it) else it.get("url", "")) or ""
    cand = []
    yid = _yt_id(url)
    if yid:
        cand.append(f"https://i.ytimg.com/vi/{yid}/hqdefault.jpg")
    if it.get("type") == "serie":
        cand.append(lambda: _poster_serie(it["nom"]))
    if suivi and url:
        cand.append(lambda: suivi.og_image(url))
    for c in cand:
        try:
            u = c() if callable(c) else c
        except Exception:
            u = ""
        if not u or not suivi:
            continue
        try:
            data = suivi.fetch_image(u, limit=6_000_000)
        except Exception:
            continue
        if len(data) < 1500:
            continue
        nom = hashlib.sha1(u.encode()).hexdigest()[:16] + ".jpg"
        (dossier / nom).write_bytes(data)
        return nom
    return ""


CSS_LISTE = """
QLabel#grandTitre { font-size: 22px; font-weight: bold; color: #3d2733; }
QLabel#compte { color: #9a8290; font-size: 9.5pt; }
QLabel#section { font-size: 15px; font-weight: bold; padding-top: 10px; color: #3d2733; background: transparent; }
QLabel#nomTV { font-size: 10pt; font-weight: bold; color: #3d2733; }
QLabel#sousTV { font-size: 9pt; color: #9a8290; }
QLabel#vide { color: #9a8290; font-size: 11pt; padding: 60px; }
QPushButton#seg { border-radius: 0; padding: 5px 13px; border-left: none; }
QPushButton#seg[pos="g"] { border-top-left-radius: 8px; border-bottom-left-radius: 8px; border-left: 1px solid #e3d3dc; }
QPushButton#seg[pos="d"] { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QPushButton#seg:checked { background: #d0457a; color: white; border-color: #d0457a; }
QPushButton#rond { border-radius: 15px; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; }
QPushButton#plus { background: #d0457a; color: white; border: none; border-radius: 15px;
                   min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0;
                   font-size: 18px; font-weight: bold; }
QLineEdit#cherche { border-radius: 8px; padding: 5px 9px; }
QFrame#carteTV { background: transparent; border: none; }
"""


# ------------------------------------------------------------------ fenêtre
class _Sig(QObject):
    done = pyqtSignal(object, object)


class ListeWindow(QWidget):
    """« Ma liste » façon Apple TV : une rangée « Reprendre », puis les affiches par catégorie."""
    FILTRES = [("Tout", ""), ("Séries et animés", "serie"), ("Films", "film"), ("Musique", "musique"),
               ("Vidéos", "video"), ("Autres", "autre")]

    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("atelier")
        self.setWindowTitle("📺 Ma liste — séries, films, animés, musique")
        self.resize(980, 760)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, r: fn(r))
        self._cartes, self._en_cours = {}, set()
        try:
            import pomme
            base = pomme.STUDIO
        except Exception:
            base = ""
        self.setStyleSheet(base + CSS_LISTE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        lay.setSpacing(10)
        # --- barre du haut : titre, catégories, recherche, +
        top = QHBoxLayout()
        top.setSpacing(10)
        t = QLabel("Ma liste")
        t.setObjectName("grandTitre")
        top.addWidget(t)
        top.addSpacing(6)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        from PyQt6.QtWidgets import QButtonGroup
        self.f_grp = QButtonGroup(self)
        self.f_grp.setExclusive(True)
        for i, (lab, k) in enumerate(self.FILTRES):
            bt = QPushButton(lab)
            bt.setObjectName("seg")
            bt.setProperty("pos", "g" if i == 0 else "d" if i == len(self.FILTRES) - 1 else "m")
            bt.setCheckable(True)
            bt.setChecked(i == 0)
            bt.setCursor(Qt.CursorShape.PointingHandCursor)
            self.f_grp.addButton(bt, i)
            seg.addWidget(bt)
        self.f_grp.idClicked.connect(lambda _i: self.refresh())
        top.addLayout(seg)
        top.addStretch(1)
        self.q = QLineEdit()
        self.q.setObjectName("cherche")
        self.q.setPlaceholderText("🔎 Chercher")
        self.q.setClearButtonEnabled(True)
        self.q.setFixedWidth(200)
        self.q.textChanged.connect(lambda _t: self.refresh())
        top.addWidget(self.q)
        bh = QPushButton("🔀")
        bh.setObjectName("rond")
        bh.setToolTip("Une musique de ma liste au hasard")
        bh.clicked.connect(self._random_music)
        top.addWidget(bh)
        bp = QPushButton("⋯")
        bp.setObjectName("rond")
        bp.setToolTip("Plus : coller plein de liens, importer, exporter, trier")
        bp.clicked.connect(lambda: self._menu_plus(bp))
        top.addWidget(bp)
        ba = QPushButton("+")
        ba.setObjectName("plus")
        ba.setToolTip("Ajouter un lien")
        ba.clicked.connect(self._dialogue_ajout)
        top.addWidget(ba)
        lay.addLayout(top)
        self.count = QLabel("")
        self.count.setObjectName("compte")
        lay.addWidget(self.count)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.box = QWidget()
        self.box.setObjectName("fond")
        self.rows = QVBoxLayout(self.box)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(4)
        sc.setWidget(self.box)
        lay.addWidget(sc, 1)
        self.tri = comp.cfg.get("liste_tri", "vu")
        self.refresh()

    def _emit(self, fn, res):
        """Renvoie le résultat d'un fil vers l'interface (sans planter si la fenêtre a été fermée entre-temps)."""
        try:
            self.sig.done.emit(fn, res)
        except RuntimeError:
            pass

    def items(self):
        return self.comp.cfg.setdefault("ma_liste", [])

    def _save(self):
        self.C.save_config(self.comp.cfg)

    def _paste(self):
        t = QApplication.clipboard().text().strip()
        found = parse_bulk(t)
        if len(found) > 1:
            return self._bulk(t)
        m = URL_RE.search(t)
        self.e_url.setText(m.group(0) if m else t)

    def _url_changed(self, u):
        u = u.strip()
        if not URL_RE.match(u):
            return
        self.e_type.setCurrentIndex(max(0, self.e_type.findData(guess_type(u))))
        if not self.e_nom.text().strip():
            def done(title):
                if isinstance(title, str) and title and not self.e_nom.text().strip() and self.e_url.text().strip() == u:
                    self.e_nom.setText(title)
            import threading
            threading.Thread(target=lambda: self._emit(done, page_title(u)), daemon=True).start()

    def _add(self):
        u, n = self.e_url.text().strip(), self.e_nom.text().strip()
        if not URL_RE.match(u):
            return self.comp.say("Colle d'abord un lien qui commence par https://")
        if not n:
            return self.comp.say("Donne-lui un nom, pour que tu puisses me le demander.")
        self.comp.liste_add(u, n, self.e_type.currentData())
        nv = self.e_nav.currentData()
        if nv:
            it = next((i for i in self.items() if _sa(i["nom"]) == _sa(n)), None)
            if it:
                set_link_nav(it, u, nv) if any(l["url"] == u for l in links(it)) else None
                self._save()
                self.refresh()
        self.e_url.clear()
        self.e_nom.clear()

    # ---------- ajout en masse
    def _bulk(self, text=None):
        from PyQt6.QtWidgets import QTextEdit
        w = QWidget(self, Qt.WindowType.Window)
        w.setWindowTitle("📋 Ajouter plein de liens")
        w.resize(640, 480)
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Un lien par ligne. Tu peux mettre le nom devant : « One Piece - https://… ».\n"
                           "Sans nom, je prends le titre de la page. Même nom = un lien en plus pour ce titre."))
        ed = QTextEdit()
        ed.setAcceptRichText(False)
        ed.setPlaceholderText("One Piece - https://www.crunchyroll.com/…\nOne Piece - https://animationdigitalnetwork.com/…\n"
                              "Ma playlist chill - https://www.youtube.com/playlist?list=…\nhttps://www.netflix.com/title/…")
        if isinstance(text, str):
            ed.setPlainText(text)
        l.addWidget(ed, 1)
        r = QHBoxLayout()
        ty = QComboBox()
        ty.addItem("🤖 Deviner le type", "")
        for k, v in TYPES.items():
            ty.addItem(v, k)
        r.addWidget(ty)
        st = QLabel("")
        r.addWidget(st, 1)
        b = QPushButton("➕ Tout ajouter")
        b.setObjectName("principal")
        r.addWidget(b)
        l.addLayout(r)

        def go():
            pairs = parse_bulk(ed.toPlainText())
            if not pairs:
                return st.setText("Je ne trouve aucun lien.")
            b.setEnabled(False)
            st.setText(f"J'ajoute {len(pairs)} lien(s)…")
            kind = ty.currentData() or None

            def work():
                from concurrent.futures import ThreadPoolExecutor
                need = [u for n, u in pairs if not n]
                with ThreadPoolExecutor(max_workers=6) as ex:
                    titles = dict(zip(need, ex.map(page_title, need)))
                return [(n or titles.get(u) or site_label(u), u) for n, u in pairs]

            def then(res):
                if isinstance(res, Exception):
                    res = [(n or site_label(u), u) for n, u in pairs]
                n_new, n_link = self.comp.liste_add_many(res, kind)
                w.close()
                self.comp.say(f"C'est ajouté : {n_new} nouveau(x) titre(s)" + (f" et {n_link} lien(s) en plus pour des "
                                                                              f"titres existants" if n_link else "") + " !")
            import threading
            threading.Thread(target=lambda: self._emit(then, self._safe(work)), daemon=True).start()
        b.clicked.connect(go)
        w.show()

    @staticmethod
    def _safe(fn):
        try:
            return fn()
        except Exception as e:
            return e

    def _export(self):
        from PyQt6.QtWidgets import QFileDialog
        import json
        p, _ = QFileDialog.getSaveFileName(self, "Exporter ma liste", str(__import__("pathlib").Path.home() /
                                                                         "ma_liste_viki.json"),
                                           "Liste Viki (*.json);;Texte (*.txt)")
        if not p:
            return
        if p.endswith(".txt"):
            lines = [f"{it['nom']} - {l['url']}" for it in self.items() for l in links(it)]
            open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        else:
            open(p, "w", encoding="utf-8").write(json.dumps(self.items(), ensure_ascii=False, indent=1))
        self.comp.say(f"Ta liste est exportée ({len(self.items())} titres).")

    def _import(self):
        from PyQt6.QtWidgets import QFileDialog
        import json
        p, _ = QFileDialog.getOpenFileName(self, "Importer une liste", str(__import__("pathlib").Path.home()),
                                           "Listes (*.json *.txt *.csv *.html *.md);;Tous (*)")
        if not p:
            return
        txt = open(p, encoding="utf-8", errors="ignore").read()
        if p.endswith(".json"):
            try:
                data = json.loads(txt)
                pairs = []
                for it in data:
                    for l in links(it) if "url" in it else []:
                        pairs.append((it.get("nom", ""), l["url"]))
                n_new, n_link = self.comp.liste_add_many(pairs, None)
                return self.comp.say(f"Importé : {n_new} titre(s), {n_link} lien(s) en plus.")
            except Exception:
                pass
        self._bulk(txt)

    def _random_music(self):
        self.comp.liste_random("musique")

    # ---------- affichage (façon Apple TV)
    def _filtre(self):
        return self.FILTRES[max(0, self.f_grp.checkedId())][1]

    def refresh(self):
        self._cartes = {}
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        allx = self.items()
        kind, q = self._filtre(), _sa(self.q.text()).strip()
        items = [it for it in allx if (not kind or it.get("type") == kind) and
                 (not q or q in _sa(it["nom"]) or any(q in _sa(l["nom"]) or q in l["url"].lower() for l in links(it)))]
        if self.tri == "nom":
            items.sort(key=lambda i: _sa(i["nom"]))
        elif self.tri == "ajout":
            items.sort(key=lambda i: i.get("ajout", ""), reverse=True)
        else:
            items.sort(key=lambda i: i.get("vu", "") or i.get("ajout", ""), reverse=True)
        n_links = sum(len(links(i)) for i in allx)
        self.count.setText(f"{len(allx)} titre(s), {n_links} lien(s)" + (f" · {len(items)} affiché(s)"
                                                                         if len(items) != len(allx) else ""))
        if not items:
            l = QLabel("Ta liste est vide pour l'instant.\nClique sur + pour ajouter un lien (YouTube, Crunchyroll, "
                       "Netflix…)." if not allx else "Aucun résultat.")
            l.setObjectName("vide")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rows.addWidget(l)
            self.rows.addStretch(1)
            return
        if q or kind:                                       # recherche ou catégorie : une grille
            if not q:
                rep = [it for it in items if it.get("vu") or it.get("ep") or it.get("temps")]
                if rep:
                    self._section("Reprendre", rep[:14], large=True)
            self._grille("Résultats" if q else next(l for l, k in self.FILTRES if k == kind), items)
        else:
            rep = sorted([it for it in items if it.get("vu") or it.get("ep") or it.get("temps")],
                         key=lambda i: i.get("vu", ""), reverse=True)
            if rep:
                self._section("Reprendre", rep[:14], large=True)
            for lab, k in self.FILTRES[1:]:
                part = [it for it in items if it.get("type", "autre") == k]
                if part:
                    self._section(lab, part)
        self.rows.addStretch(1)
        self._images_manquantes(items)

    def _forme(self, it, large=False):
        """(largeur, hauteur) de l'image : affiche, carré ou 16:9."""
        if large:
            return 236, 133
        t = it.get("type", "autre")
        if t in ("serie", "film"):
            return 136, 204
        if t == "musique":
            return 158, 158
        return 236, 133

    def _section(self, titre, items, large=False):
        h = QLabel(titre)
        h.setObjectName("section")
        self.rows.addWidget(h)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("fond")
        rl = QHBoxLayout(inner)
        rl.setContentsMargins(0, 0, 0, 6)
        rl.setSpacing(14)
        hmax = 0
        for it in items:
            c = self._carte(it, large)
            hmax = max(hmax, c.sizeHint().height())
            rl.addWidget(c, 0, Qt.AlignmentFlag.AlignTop)
        rl.addStretch(1)
        sc.setWidget(inner)
        sc.setFixedHeight(hmax + 22)
        def molette(e, s=sc):
            """La molette fait défiler la page ; Maj + molette (ou le pavé tactile de côté) fait défiler la rangée."""
            dx, dy = e.angleDelta().x(), e.angleDelta().y()
            if abs(dx) > abs(dy) or e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                s.horizontalScrollBar().setValue(s.horizontalScrollBar().value() - (dx or dy))
                e.accept()
            else:
                e.ignore()                       # remonte jusqu'à la page, qui défile
        sc.wheelEvent = molette
        self.rows.addWidget(sc)

    def _grille(self, titre, items):
        try:
            from actu_fenetre import FlowLayout
        except Exception:
            FlowLayout = None
        h = QLabel(titre)
        h.setObjectName("section")
        self.rows.addWidget(h)
        g = QWidget()
        g.setObjectName("fond")
        fl = FlowLayout(g, 14) if FlowLayout else QHBoxLayout(g)
        for it in items[:400]:
            fl.addWidget(self._carte(it))
        self.rows.addWidget(g)

    def _sous_titre(self, it):
        w = []
        if it.get("type") == "serie" and it.get("ep"):
            w.append(f"Épisode {it['ep']}")
        if it.get("temps"):
            w.append(f"à {fmt_time(it['temps'])}")
        if not w:
            w.append("pas encore commencé" if not it.get("vu") else "déjà ouvert")
        ls = links(it)
        if ls:
            w.append(ls[0]["nom"] + (f" +{len(ls) - 1}" if len(ls) > 1 else ""))
        return " · ".join(w)

    def _carte(self, it, large=False):
        W, H = self._forme(it, large)
        f = QFrame()
        f.setObjectName("carteTV")
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        f.setFixedWidth(W)
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        img = QLabel()
        img.setFixedSize(W, H)
        img.setPixmap(self._vignette(it, W, H, large))
        v.addWidget(img)
        t = QLabel(it["nom"])
        t.setObjectName("nomTV")
        t.setProperty("no_i18n", True)
        t.setWordWrap(True)
        v.addWidget(t)
        st = QLabel(self._sous_titre(it))
        st.setObjectName("sousTV")
        st.setProperty("no_i18n", True)
        st.setWordWrap(True)
        v.addWidget(st)
        f.setToolTip("Clic : ouvrir là où tu t'es arrêté · Clic droit : épisode, liens, navigateur, renommer…")
        f.mousePressEvent = lambda e, i=it, ff=f: (self.comp.liste_open(i) if e.button() == Qt.MouseButton.LeftButton
                                                   else self._menu_titre(i, ff))
        self._cartes.setdefault(id(it), []).append((img, W, H, large))
        return f

    # ---------- images (affiches, miniatures)
    def _dossier_img(self):
        from pathlib import Path
        d = Path(self.C.CONFIG_DIR) / "liste_images"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _vignette(self, it, W, H, large):
        from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont
        from PyQt6.QtCore import QRectF
        dpr = 2
        pm = QPixmap(W * dpr, H * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 11, 11)
        p.setClipPath(path)
        src = QPixmap()
        nom = it.get("img") or ""
        if nom:
            src.load(str(self._dossier_img() / nom))
        if not src.isNull():
            sc = src.scaled(W * dpr, H * dpr, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(QRectF(0, 0, W, H), sc, QRectF((sc.width() - W * dpr) / 2, (sc.height() - H * dpr) / 2,
                                                        W * dpr, H * dpr))
        else:                                              # tuile de couleur : icône + site
            col = QColor(COULEURS_TYPE.get(it.get("type", "autre"), "#3a3a3c"))
            h = (sum(map(ord, it["nom"])) % 40 - 20) / 360.0
            hh, ss, ll, _a = col.getHslF()
            col.setHslF((hh + h) % 1.0, ss, ll)
            p.fillRect(QRectF(0, 0, W, H), col)
            fam = ""
            try:
                fam = self.C.icon_family()
            except Exception:
                pass
            code = ICONES_TYPE.get(it.get("type", "autre"))
            f = QFont(fam) if fam and code else QFont()
            f.setPixelSize(int(min(W, H) * 0.30))
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 215))
            p.drawText(QRectF(0, 0, W, H * 0.86), Qt.AlignmentFlag.AlignCenter,
                       chr(code) if fam and code else ICON.get(it.get("type"), "🔗"))
            ls = links(it)
            if ls:
                f2 = QFont()
                f2.setPixelSize(11)
                f2.setBold(True)
                p.setFont(f2)
                p.setPen(QColor(255, 255, 255, 170))
                p.drawText(QRectF(0, H * 0.70, W, H * 0.25), Qt.AlignmentFlag.AlignCenter, ls[0]["nom"])
        if large:                                          # petit bouton lecture sur « Reprendre »
            p.setClipping(False)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawEllipse(QRectF(10, H - 42, 32, 32))
            p.setBrush(QColor(255, 255, 255, 235))
            from PyQt6.QtGui import QPolygonF
            from PyQt6.QtCore import QPointF
            p.drawPolygon(QPolygonF([QPointF(22, H - 34), QPointF(22, H - 18), QPointF(34, H - 26)]))
        p.end()
        return pm

    def _images_manquantes(self, items):
        """Cherche les affiches / miniatures qui manquent (une seule fois par titre), sans bloquer la fenêtre."""
        if not self.comp.cfg.get("liste_images", True):
            return
        now = time.time()
        todo = [it for it in items if not it.get("img") and id(it) not in self._en_cours
                and now - float(it.get("img_essai") or 0) > 7 * 86400]
        if not todo:
            return
        for it in todo:
            self._en_cours.add(id(it))
        dossier = self._dossier_img()

        def work():
            out = []
            for it in todo[:60]:
                try:
                    out.append((it, chercher_image(it, dossier)))
                except Exception:
                    out.append((it, ""))
                self._emit(self._image_arrivee, out[-1])
            return out
        import threading
        threading.Thread(target=lambda: self._safe(work), daemon=True).start()

    def _image_arrivee(self, res):
        it, nom = res
        self._en_cours.discard(id(it))
        it["img_essai"] = time.time()
        if nom:
            it["img"] = nom
        self._save()
        for img, W, H, large in self._cartes.get(id(it), []):
            try:
                img.setPixmap(self._vignette(it, W, H, large))
            except RuntimeError:
                pass

    # ---------- menus
    def _menu_plus(self, btn):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("📋  Coller plein de liens d'un coup…", self._bulk)
        m.addAction("📥  Importer…", self._import)
        m.addAction("📤  Exporter…", self._export)
        m.addSeparator()
        tri = m.addMenu("🔍  Trier")
        for lab, k in (("Récents d'abord", "vu"), ("A → Z", "nom"), ("Ajoutés récemment", "ajout")):
            tri.addAction(("✓  " if self.tri == k else "     ") + lab, lambda kk=k: self._trier(kk))
        if hasattr(self.comp, "choisir_service_musique"):
            m.addAction("🎧  Où écouter ma musique (YouTube, Spotify, Deezer…)", self.comp.choisir_service_musique)
        on = self.comp.cfg.get("liste_images", True)
        m.addAction(("✓  " if on else "     ") + "Images des titres (affiches, miniatures)", self._basculer_images)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _trier(self, k):
        self.tri = self.comp.cfg["liste_tri"] = k
        self._save()
        self.refresh()

    def _basculer_images(self):
        self.comp.cfg["liste_images"] = not self.comp.cfg.get("liste_images", True)
        self._save()
        self.refresh()

    def _menu_titre(self, it, w):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        m = QMenu(self)
        m.addAction("▶  " + ("Reprendre" if it.get("vu") or it.get("ep") or it.get("temps") else "Ouvrir"),
                    lambda: self.comp.liste_open(it))
        if it.get("type") == "serie":
            m.addAction("⏭  Épisode suivant", lambda: self.comp.liste_next(it))
            m.addAction("📺  Changer d'épisode…", lambda: self._demander_ep(it))
        m.addAction("⏰  Arrêté à…", lambda: self._demander_temps(it))
        ls = links(it)
        if len(ls) > 1:
            sm = m.addMenu("🌐  Ouvrir sur…")
            for l in ls:
                sm.addAction(l["nom"], lambda u=l["url"]: self.comp.liste_open(it, u))
        sm = m.addMenu("🧭  Navigateur")
        self._fill_nav(sm, it, None)
        if len(ls) > 1:
            lm = m.addMenu("🔗  Liens")
            for i, l in enumerate(ls[1:], 1):
                s2 = lm.addMenu(l["nom"])
                s2.addAction("⭐  En faire le lien principal", lambda u=l["url"]: self._make_main(it, u))
                s2.addAction("🗑️  Retirer ce lien", lambda u=l["url"]: self._drop_link(it, u))
        m.addAction("➕  Ajouter un autre site…", lambda: self._add_link_to(it))
        ty = m.addMenu("🏷️  Type")
        for k, lab in TYPES.items():
            ty.addAction(("✓  " if it.get("type") == k else "     ") + lab.split(" ", 1)[1],
                         lambda kk=k: (it.__setitem__("type", kk), self._save(), self.refresh()))
        m.addAction("🖼️  Changer l'image…", lambda: self._choisir_image(it))
        m.addSeparator()
        m.addAction("✏️  Renommer…", lambda: self._rename(it))
        m.addAction("🗑️  Retirer de ma liste", lambda: self.comp.liste_remove(it))
        m.exec(QCursor.pos())

    def _champ(self, titre, texte, valeur="", place=""):
        """Petite question au style de Viki -> texte ou None."""
        try:
            from actu_fenetre import Boite
        except Exception:
            from PyQt6.QtWidgets import QInputDialog
            v, ok = QInputDialog.getText(self, titre, texte, text=valeur)
            return v if ok else None
        b = Boite(self, titre, texte, [("Annuler", False, "non"), ("OK", True, "oui")], "")
        e = QLineEdit(valeur)
        e.setPlaceholderText(place)
        b.ajouter_champ("", e)
        e.setFocus()
        e.returnPressed.connect(lambda: b._fin(True))
        b.exec()
        return e.text() if b.valeur else None

    def _demander_ep(self, it):
        v = self._champ("Épisode", f"Tu en es à quel épisode de « {it['nom']} » ?", str(it.get("ep") or ""), "12")
        if v is not None and v.strip().isdigit():
            it["ep"], it["temps"] = int(v.strip()), 0
            self._save()
            self.refresh()

    def _demander_temps(self, it):
        v = self._champ("Arrêté à", f"Où tu t'es arrêté dans « {it['nom']} » ?",
                        fmt_time(it["temps"]) if it.get("temps") else "", "23:15")
        if v is not None:
            self._set_time(it, v)
            self.refresh()

    def _choisir_image(self, it):
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path
        p, _f = QFileDialog.getOpenFileName(self, "Une image pour ce titre", str(Path.home()),
                                            "Images (*.png *.jpg *.jpeg *.webp)")
        if not p:
            return
        import hashlib
        nom = hashlib.sha1(("perso" + p).encode()).hexdigest()[:16] + Path(p).suffix.lower()
        shutil.copyfile(p, self._dossier_img() / nom)
        it["img"] = nom
        self._save()
        self.refresh()

    def _dialogue_ajout(self):
        """Ajouter un lien : une petite fenêtre au lieu du gros cadre en haut."""
        try:
            from actu_fenetre import Boite
        except Exception:
            Boite = None
        if Boite is None:
            return
        b = Boite(self, "Ajouter à ma liste", "Colle le lien d'une série, d'un film, d'une playlist ou d'une vidéo.",
                  [("Annuler", False, "non"), ("Ajouter", True, "oui")], "➕")
        self.e_url = b.ajouter_champ("Le lien :", QLineEdit())
        self.e_url.setPlaceholderText("https://…")
        clip = URL_RE.search(QApplication.clipboard().text() or "")
        self.e_nom = b.ajouter_champ("Son nom (même nom qu'un titre existant = un site en plus) :", QLineEdit())
        self.e_type = b.ajouter_champ("Type :", QComboBox())
        for k, v in TYPES.items():
            self.e_type.addItem(v, k)
        self.e_nav = b.ajouter_champ("Ouvrir avec :", QComboBox())
        self.e_nav.addItem("🌐 Navigateur par défaut", "")
        for nid, nom in installed_navs():
            self.e_nav.addItem("🌐 " + nom, nid)
        self.e_url.textChanged.connect(self._url_changed)
        if clip:
            self.e_url.setText(clip.group(0))
        self.e_url.setFocus()
        b.exec()
        if b.valeur:
            self._add()

    def _fill_nav(self, m, it, url):
        cur = link_nav(it, url) if url else it.get("nav", "")
        for nid, nom in [("", "Navigateur par défaut")] + installed_navs():
            a = m.addAction(("✓ " if nid == cur else "    ") + nom)
            a.triggered.connect(lambda _=False, n=nid: self._set_nav(it, url, n))

    def _set_nav(self, it, url, nid):
        if url:
            set_link_nav(it, url, nid)
        else:
            it["nav"] = nid
            for l in it.get("liens", []):
                l.pop("nav", None)
        self._save()
        self.refresh()
        self.comp.say(f"« {it['nom']} » s'ouvrira avec {nav_name(nid) or 'ton navigateur par défaut'}.")

    def _nav_menu(self, it, url, btn):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        h = m.addAction("🌐 Ouvrir avec…")
        h.setEnabled(False)
        self._fill_nav(m, it, url)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _link_menu(self, it, url, btn, main=False):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        sm = m.addMenu("🌐 Ouvrir avec")
        self._fill_nav(sm, it, url)
        if not main:
            m.addAction("⭐ En faire le lien principal", lambda: self._make_main(it, url))
            m.addAction("🗑 Retirer ce lien", lambda: self._drop_link(it, url))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _make_main(self, it, url):
        old, old_nav = it["url"], it.get("nav", "")
        new_nav = link_nav(it, url)
        it["liens"] = [l for l in it.get("liens", []) if l["url"] != url] + [{"url": old, "nom": site_label(old),
                                                                                "nav": old_nav}]
        it["url"], it["nav"] = url, new_nav
        self._save()
        self.refresh()

    def _drop_link(self, it, url):
        it["liens"] = [l for l in it.get("liens", []) if l["url"] != url]
        self._save()
        self.refresh()

    def _add_link_to(self, it):
        from PyQt6.QtWidgets import QInputDialog
        clip = URL_RE.search(QApplication.clipboard().text() or "")
        u, ok = QInputDialog.getText(self, "➕ Un autre lien", f"Lien pour « {it['nom']} » (un autre site, une autre "
                                     "saison…) :", text=clip.group(0) if clip else "")
        if ok and URL_RE.match(u.strip()):
            add_link(it, u.strip())
            self._save()
            self.refresh()

    def _rename(self, it):
        from PyQt6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getText(self, "✏️ Renommer", "Nouveau nom :", text=it["nom"])
        if ok and n.strip():
            it["nom"] = n.strip()
            self._save()
            self.refresh()

    def _set_time(self, it, txt):
        s = parse_time(txt) if txt.strip() else 0
        if s is None:
            s = parse_time(txt + " min") if txt.strip().isdigit() else None
        if s is not None:
            it["temps"] = s
            self._save()
