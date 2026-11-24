"""Demandes « naturelles » de Viki : l'actu des sites suivis, la musique (YouTube), la création d'images.
Internet seulement quand tu le demandes. Aucune clé obligatoire."""
import base64
import datetime
import difflib
import email.utils
import json
import os
import random
import re
import shutil
import subprocess
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
      "Accept-Language": "fr,en;q=0.7", "Cookie": "SOCS=CAI; CONSENT=YES+1"}
KEY_FILE = None                           # fixé par compagnon.py : clé Pollinations facultative (chmod 600)


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def _get(url, headers=None, data=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


_POLI = r"(?:s'?il (?:te|vous) pla[iî]t|stp|svp|merci|please|viki|hey|eh|allez|vas[- ]y|bon|alors|ok|okay)"
_FILL = {"moi", "nous", "un", "une", "des", "du", "de", "la", "le", "les", "l", "d", "peu", "petit", "petite", "bon",
         "bonne", "truc", "trucs", "quelque", "chose", "s'il", "te", "plait", "stp", "svp", "merci", "en", "sur", "a",
         "au", "aux", "et", "pour", "que", "qui", "ca", "y", "il", "stp.", "maintenant", "là", "la,", "vite", "juste",
         "stp,", "please", "un peu", "genre", "style", "type", "comme", "tu", "peux", "veux", "voudrais", "aimerais",
         "je", "j", "on", "me", "m", "est", "ce", "qu", "quoi", "dis", "viki"}


def _clean(t):
    t = re.sub(r"\b" + _POLI + r"\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.!?:;-")


# ================================================================== ACTU
_NEWS_WORD = r"(?:actus?|actualites?|infos?|informations|nouvelles|news|gros titres|titres du jour|journal du jour)"
_NEWS_RE = re.compile(
    r"\b(?:donne|dis|raconte|lis|fais|balance|envoie|resume|montre|sors|file|annonce)\w*(?:[- ](?:moi|nous))?\b.*\b" + _NEWS_WORD + r"\b"
    r"|\b(?:c'?est quoi|quelles? sont|quoi comme|y'? ?a quoi (?:comme|dans)|il y a quoi (?:comme|dans)|"
    r"qu'?est[- ]ce qu'?il y a (?:comme|dans)|tu as|t'?as|des|les dernieres?|un point sur) (?:l'|les |l |la |des |de l'|d')?" + _NEWS_WORD + r"\b"
    r"|\bquoi de (?:neuf|nouveau|beau)\b.*\b(?:monde|aujourd'?hui|actu|en |dans |cote |niveau |sur )"
    r"|\b(?:qu'?est[- ]ce qu'?il se passe|il se passe quoi|que se passe[- ]t[- ]il|ca dit quoi) (?:dans le monde|aujourd'?hui|"
    r"en |dans |cote |niveau |sur )"
    r"|^(?:l'|les |des )?" + _NEWS_WORD + r"(?: .{0,45})?$"
    r"|\bje veux (?:l'|les |des )?" + _NEWS_WORD + r"\b|\b(?:tiens|mets)[- ]moi au courant\b")
_NEWS_STOP = {"actu", "actus", "actualite", "actualites", "info", "infos", "informations", "nouvelles", "news", "jour",
              "aujourd'hui", "aujourdhui", "monde", "dernieres", "derniere", "titres", "gros", "journal", "matin", "soir",
              "moment", "neuf", "nouveau", "passe", "quoi", "donne", "dis", "raconte", "lis", "fais", "site", "sites",
              "mes", "liens", "lien", "suivis", "menu", "point", "resume", "courant", "dit", "ca", "se", "cote", "niveau"}


def parse_news(ta):
    """« donne-moi l'actu », « quoi de neuf en tech ? », « les infos sur l'espace » -> {"sujet": "..."} ou None."""
    t = _clean(ta)
    if not _NEWS_RE.search(t) or re.search(r"^(?:ouvre|affiche)\b|\b(?:regle|parametre|ajoute|suis|supprime|retire)\b", t):
        return None
    def topic(s):
        words = [re.sub(r"^(?:l'|d'|qu')", "", w) for w in re.findall(r"[a-z0-9'.+-]+", s)]
        return " ".join(w for w in words if w and w not in _FILL and w not in _NEWS_STOP and len(w) > 1)
    sujet = ""
    last = None
    for last in re.finditer(r"\b" + _NEWS_WORD + r"\b", t):
        pass
    if last:
        sujet = topic(t[last.end():])
    if not sujet:
        m = re.search(r"\b(?:sur|en|concernant|a propos (?:de|du|des|d')|au sujet (?:de|du|des|d')|cote|niveau|chez|"
                      r"dans(?: le| la| les| l')?)\s*(.+)$", t if not last else t[:last.start()])
        if m:
            sujet = topic(m.group(1))
    return {"sujet": sujet}


def _date(d):
    if not d:
        return 0.0
    try:
        return email.utils.parsedate_to_datetime(d).timestamp()
    except Exception:
        try:
            return datetime.datetime.fromisoformat(d.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0


TOPIC_SYN = {"tech": "tech|techno|informatique|numerique|logiciel|ia|ordinateur|smartphone|app",
             "informatique": "informatique|tech|logiciel|ordinateur|linux|windows|code|cyber",
             "ia": r"\bia\b|intelligence artificielle|\bai\b|chatgpt|claude|gemini|llm|openai|anthropic|mistral",
             "science": "science|scientifi|recherche|chercheur|etude|physique|biologie|espace|nasa",
             "espace": "espace|spatial|nasa|esa|fusee|spacex|planete|lune|mars|satellite|astronom",
             "jeux": "jeu video|jeux video|gaming|playstation|xbox|nintendo|steam|switch",
             "sport": "sport|foot|football|rugby|tennis|basket|ligue|match|jo |olymp",
             "cinema": "cinema|film|serie|netflix|acteur|actrice|bande-annonce",
             "manga": "manga|anime|shonen|crunchyroll|chapitre",
             "linux": "linux|kde|gnome|arch|ubuntu|debian|fedora|kernel|noyau",
             "securite": "securite|cyber|piratage|hack|faille|malware|ransomware|fuite de donnees"}


def headlines(sites, site_items, sujet="", n=6):
    """Derniers titres des sites suivis (les plus récents d'abord), filtrés par sujet ou par nom de site.
    -> (liste [(site, article)], "sites" | "site:<nom>" | "aucun")."""
    srcs = [s for s in sites if s.get("suivre", True)]
    if not srcs:
        return [], "aucun"
    q = _sa(sujet).strip()
    named = [s for s in srcs if q and (q in _sa(s.get("nom", "")) or q.replace(" ", "") in _sa(s.get("site", "")))]
    pool = named or srcs

    def fetch(s):
        try:
            return [(s.get("nom", "?"), x) for x in site_items(s, 15)]
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        allx = [x for part in ex.map(fetch, pool) for x in part]
    if named:
        allx.sort(key=lambda sx: -_date(sx[1].get("date")))
        return allx[:n], "site:" + named[0].get("nom", "")
    if q:
        words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in q.split()]
        pats = [TOPIC_SYN.get(w, re.escape(w)) for w in words]
        hit = [sx for sx in allx if all(re.search(p, _sa(sx[1]["titre"] + " " + sx[0])) for p in pats)]
        if not hit:
            hit = [sx for sx in allx if any(re.search(p, _sa(sx[1]["titre"] + " " + sx[0])) for p in pats)]
        hit.sort(key=lambda sx: -_date(sx[1].get("date")))
        return hit[:n], "sites"
    # sans sujet : on alterne les sites pour ne pas n'en lire qu'un
    by = {}
    for site, x in sorted(allx, key=lambda sx: -_date(sx[1].get("date"))):
        by.setdefault(site, []).append((site, x))
    out = []
    while len(out) < n and any(by.values()):
        for site in list(by):
            if by[site]:
                out.append(by[site].pop(0))
    return out[:n], "sites"


# ================================================================== MUSIQUE
_MUSIC_OBJ = r"(?:musiques?|chansons?|morceaux?|sons?|playlists?|titres?|zik|zic|zique|tubes?|albums?|ambiance)"
_MUSIC_VERB = (r"(?:mets?|met|mes(?=[- ]moi| de | du | un | une )|lance|joue|balance|envoie|passe|fais[- ](?:moi )?(?:peter|ecouter|tourner)|"
               r"fais peter|demarre|diffuse|trouve|cherche)")
_MUSIC_RE = re.compile(
    r"\b" + _MUSIC_VERB + r"(?:[- ](?:moi|nous))?\b.*\b" + _MUSIC_OBJ + r"\b"
    r"|\b(?:j'?(?:ai envie|aimerais|veux|voudrais)|je (?:veux|voudrais)|on (?:peut|pourrait)|tu (?:peux|pourrais|veux bien)|"
    r"envie) (?:d'|de |bien )?(?:ecouter|entendre|mettre|me mettre|lancer|jouer)\b"
    r"|^(?:un peu de |de la |une? |du )?" + _MUSIC_OBJ + r"\b(?! (?:suivante?|precedente?))"
    r"|\b(?:mets?|met|mes(?=[- ]moi)|joue|lance|balance|passe)(?:[- ](?:moi|nous))? (?:du|de la|de l'|des|un peu de|le dernier|la derniere|"
    r"quelque chose d[e']|un truc)\b"
    r"|\b(?:ecoute|ecouter|ecoutons)\b.*\b(?:chaine|youtube)\b|\b(?:ma|ta|la) chaine\b.*\b(?:musique|youtube|son)\b"
    r"|\b(?:mets?|lance|ouvre|joue)(?:[- ]moi)?\b.*\b(?:ma|ta) chaine\b"
    r"|\b(?:mets?|met|lance|joue|ecoute|ecouter|passe)\b.*\b(?:sur|avec|dans) (?:spotify|deezer|youtube music|yt music)\b")
_MUSIC_STOP = _FILL | {"musique", "musiques", "chanson", "chansons", "morceau", "morceaux", "son", "sons", "playlist",
                       "titre", "titres", "zik", "zic", "zique", "ambiance", "youtube", "mets", "met", "lance", "joue",
                       "balance", "envoie", "passe", "fais", "peter", "ecouter", "ecoute", "entendre", "mettre", "lancer",
                       "jouer", "envie", "ai", "aimerais", "voudrais", "veux", "pourrais", "peux", "bien", "demarre",
                       "diffuse", "trouve", "cherche", "tourner", "mes", "pourrait", "peut", "pourrait-on", "ecoutons", "quelque", "truc", "ma", "ta", "chaine", "sa", "mon", "ton",
                       "avec", "dessus", "depuis", "dans", "via", "album", "albums", "tube", "tubes", "fond", "volume"}
_FOCUS = r"concentr|travaill|cod(?:er|e\b|ing)|bosser|reviser|etudi|focus|\bdev\b|programm"


def parse_music(ta):
    """« mets-moi de la musique », « j'ai envie d'écouter du lofi », « joue le dernier son de ma chaîne »
    -> {"q": "lofi", "chaine": bool, "focus": bool, "dernier": bool} ou None."""
    t = _clean(ta)
    if not _MUSIC_RE.search(t):
        return None
    if re.search(r"\b(?:pause|stop|arrete|coupe|suivante?|precedente?|volume|baisse|monte|remets la musique|"
                 r"reprends la musique)\b|^(?:mets|lance|remets|reprends) la musique$", t):
        return None
    if re.search(r"\b(?:image|dessin|photo|logo|affiche|illustration|fond d'?ecran|fichier|dossier|pdf|video de|film|minuteur|rappel|alarme|note|"
                 r"mode |reglage|parametre|lumiere|ecran)\b", t):
        return None
    service = ""
    m_s = re.search(r"\b(?:sur|avec|dans|via) (spotify|deezer|youtube music|yt music)\b", t)
    if m_s:                                         # « mets Daft Punk sur Spotify »
        service = {"youtube music": "ytmusic", "yt music": "ytmusic"}.get(m_s.group(1), m_s.group(1))
        t = (t[:m_s.start()] + " " + t[m_s.end():]).strip()
    chaine = bool(re.search(r"\b(?:ma|ta|notre|la) chaine\b|\bkorhyu\b", t))
    focus = bool(re.search(_FOCUS, t))
    dernier = bool(re.search(r"\b(?:dernier|derniere|nouveau|nouvelle|recent)\b", t))
    words = [re.sub(r"^(?:l'|d'|qu'|j'|m'|t'|n'|s')", "", w) for w in re.findall(r"[a-z0-9'&.+-]+", t)]
    words = [w for w in words if w and w not in _MUSIC_STOP and len(w) > 1]
    q = " ".join(words)
    q = re.sub(r"\b(?:dernier|derniere|nouveau|nouvelle|recent|sortie?)\b", " ", q) if chaine or dernier and not q.strip() else q
    if focus:
        q = re.sub(r"\b(?:me |se )?(?:" + _FOCUS + r")\w*", " ", q)
    return {"q": re.sub(r"\s+", " ", q).strip(), "chaine": chaine, "focus": focus, "dernier": dernier,
            "service": service}


def channel_id(url):
    """Lien d'une chaîne YouTube (@nom, /channel/UC…) -> identifiant UC…"""
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    if m:
        return m.group(1)
    page = _get(url).decode("utf-8", "replace")
    for pat in (r'"channelId":"(UC[\w-]{22})"', r'channel_id=(UC[\w-]{22})', r'"externalId":"(UC[\w-]{22})"',
                r'/channel/(UC[\w-]{22})'):
        m = re.search(pat, page)
        if m:
            return m.group(1)
    raise RuntimeError("identifiant de chaîne introuvable")


def channel_videos(cid):
    """Les 15 dernières vidéos d'une chaîne (flux public, sans clé) -> [{"titre", "lien", "id"}]."""
    import xml.etree.ElementTree as ET
    A, Y = "{http://www.w3.org/2005/Atom}", "{http://www.youtube.com/xml/schemas/2015}"
    root = ET.fromstring(_get("https://www.youtube.com/feeds/videos.xml?channel_id=" + cid))
    out = []
    for e in root.findall(A + "entry"):
        vid = e.findtext(Y + "videoId") or ""
        if vid:
            out.append({"titre": (e.findtext(A + "title") or "").strip(), "id": vid,
                        "lien": "https://www.youtube.com/watch?v=" + vid})
    return out


def pick_video(videos, q="", dernier=False):
    if not videos:
        return None
    if dernier and not q:
        return videos[0]
    if not q:
        return random.choice(videos)
    words = [w for w in _sa(q).split() if len(w) > 1]
    best, score = None, 0.0
    for v in videos:
        t = _sa(v["titre"])
        toks = re.findall(r"[a-z0-9]+", t)
        sc = sum(1.0 if w in t else 0.6 if difflib.get_close_matches(w, toks, n=1, cutoff=0.8) else 0 for w in words)
        if sc > score:
            best, score = v, sc
    return best if score >= max(1.0, len(words) * 0.5) else None


def youtube_search(q, n=1):
    """Premiers résultats YouTube -> [{"titre", "lien", "id"}]. yt-dlp si présent, sinon la page de résultats."""
    exe = shutil.which("yt-dlp")
    if exe:
        try:
            r = subprocess.run([exe, f"ytsearch{n}:{q}", "--flat-playlist", "--print", "%(id)s\t%(title)s", "--no-warnings"],
                               capture_output=True, text=True, timeout=25)
            out = [{"id": a, "titre": b, "lien": "https://www.youtube.com/watch?v=" + a}
                   for a, _, b in (l.partition("\t") for l in r.stdout.splitlines()) if re.fullmatch(r"[\w-]{11}", a)]
            if out:
                return out
        except Exception:
            pass
    page = _get("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)).decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([\w-]{11})".{0,1200}?"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
                         page, re.S):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            try:
                title = json.loads('"' + m.group(2) + '"')
            except Exception:
                title = m.group(2)
            out.append({"id": m.group(1), "titre": title, "lien": "https://www.youtube.com/watch?v=" + m.group(1)})
        if len(out) >= n:
            break
    return out


def search_url(q, channel_url=""):
    if channel_url and ("/@" in channel_url or "/channel/" in channel_url):
        return channel_url.rstrip("/") + "/search?query=" + urllib.parse.quote_plus(q)
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)


def find_music(req, chaine_url, dev_url, cid=""):
    """Décide quoi jouer -> {"lien", "titre", "ou": "chaine" | "youtube" | "dev" | "recherche", "cid"}."""
    q = req.get("q", "")
    if req.get("focus") and not q and not req.get("chaine"):
        return {"lien": dev_url, "titre": "", "ou": "dev", "cid": cid}
    vids = []
    if chaine_url and (req.get("chaine") or not q or cid):
        try:
            cid = cid or channel_id(chaine_url)
            vids = channel_videos(cid)
        except Exception:
            vids = []
    if req.get("chaine") or not q:                       # ta chaîne d'abord
        v = pick_video(vids, q, req.get("dernier"))
        if v:
            return {**v, "ou": "chaine", "cid": cid}
        if req.get("chaine") or not q:
            if q and chaine_url:
                return {"lien": search_url(q, chaine_url), "titre": "", "ou": "recherche", "cid": cid}
            if chaine_url and not q:
                return {"lien": chaine_url, "titre": "", "ou": "chaine", "cid": cid}
    else:
        v = pick_video(vids, q)                          # un titre précis de ta chaîne ?
        if v and len(q.split()) >= 1 and _sa(q) in _sa(v["titre"]):
            return {**v, "ou": "chaine", "cid": cid}
    qq = q + (" musique" if q and len(q.split()) < 3 and not re.search(r"music|musique|mix|playlist|song", q) else "")
    try:
        res = youtube_search(qq or "musique", 1)
    except Exception:
        res = []
    if res:
        return {**res[0], "ou": "youtube", "cid": cid}
    return {"lien": search_url(qq or "musique"), "titre": "", "ou": "recherche", "cid": cid}


SERVICES = {   # où écouter : (nom, recherche, accueil, lien de l'appli)
    "youtube": ("YouTube", "https://www.youtube.com/results?search_query={q}", "https://www.youtube.com", ""),
    "ytmusic": ("YouTube Music", "https://music.youtube.com/search?q={q}", "https://music.youtube.com", ""),
    "spotify": ("Spotify", "https://open.spotify.com/search/{q}", "https://open.spotify.com", "spotify:search:{q}"),
    "deezer": ("Deezer", "https://www.deezer.com/search/{q}", "https://www.deezer.com", "deezer://www.deezer.com/search/{q}"),
}


def service_url(service, q):
    """Le lien de recherche (ou d'accueil) sur le service choisi, et celui de son appli si elle est installée."""
    nom, rech, accueil, appli = SERVICES.get(service, SERVICES["youtube"])
    qq = urllib.parse.quote(q) if service in ("spotify", "deezer") else urllib.parse.quote_plus(q)
    web = rech.format(q=qq) if q else accueil
    app = appli.format(q=qq) if appli and q else ""
    return web, app


def mpv_ok():
    return bool(shutil.which("mpv") and shutil.which("yt-dlp"))


# ================================================================== IMAGES
_IMG_OBJ = (r"(?:images?|illustrations?|dessins?|photos?|fonds? d'?ecran|wallpapers?|logos?|avatars?|portraits?|"
            r"affiches?|posters?|visuels?|tableaux?|peintures?|pochettes?|miniatures?|icones?|stickers?)")
_IMG_VERB = r"(?:genere|generes|generer|cree|creer|crees|dessine|dessiner|fabrique|imagine|produis|peins|fais|faire|realise)"
_IMG_RE = re.compile(
    r"\b" + _IMG_VERB + r"(?:[- ](?:moi|nous))?\b.{0,40}?\b" + _IMG_OBJ + r"\b"
    r"|^(?:genere|dessine|peins|imagine)(?:[- ](?:moi|nous))?\s+\S"
    r"|\b(?:tu (?:peux|pourrais|sais)|peux[- ]tu|j'?(?:aimerais|ai besoin d'|veux|voudrais)|je (?:veux|voudrais)) .{0,25}\b"
    r"(?:generer|creer|dessiner|faire|une?|d'une?)\b.{0,25}\b" + _IMG_OBJ + r"\b")
BLOCK = re.compile(r"\b(?:nue?s?|nude|naked|nsfw|porn\w*|sexe|sex|sexy|sexuel\w*|erotique|hentai|seins?|topless|lingerie|"
                   r"deshabille\w*|explicit\w*|gore|decapit\w*|loli|shota)\b")


def parse_image(text):
    """« génère-moi une image d'un dragon bleu », « dessine un chat astronaute », « génère cette image : … »
    -> {"prompt": "...", "presse_papiers": bool, "w": .., "h": ..} ou None."""
    raw = text.strip()
    t = _clean(_sa(raw))
    if not _IMG_RE.search(t):
        return None
    if re.search(r"\b(?:trouve|cherche|ouvre|supprime|range|traduis|traduire|redimensionne|convertis|upscale|"
                 r"personnage|marionnette|capture|message|commit|texte|mot de passe|code|resume|quiz|liste|rapport|"
                 r"mail|nom|idee|planning|rappel|note|fiche|script|snippet|histoire|poeme|blague|recette)\b", t) or re.search(r"^(?:fais|faire)\b", t) and not re.search(_IMG_OBJ, t):
        return None
    # le prompt : ce qui suit « : », sinon ce qui suit l'objet (image de / d'un / avec…), sinon ce qui suit le verbe
    low = _sa(raw)
    prompt = ""
    if ":" in raw:
        prompt = raw.split(":", 1)[1]
    else:
        m = re.search(r"\b" + _IMG_OBJ + r"\b\s*(?:(?:de |d'|du |des |avec |qui (?:montre|represente) |representant |montrant |"
                      r"ou (?:on voit|il y a) |sur )?)(.*)$", low)
        if m:
            prompt = raw[len(raw) - len(raw[m.start(1):]):] if len(low) == len(raw) else m.group(1)
        else:
            m = re.search(r"^\W*" + _IMG_VERB + r"(?:[- ](?:moi|nous))?\s+(.*)$", low)
            if m:
                prompt = raw[m.start(1):] if len(low) == len(raw) else m.group(1)
    prompt = re.sub(r"\b" + _POLI + r"\b\W*$", "", prompt.strip(" .!?«»\"'"), flags=re.I).strip(" ,.!?")
    clip = not prompt or bool(re.fullmatch(r"(?:cette|cet|ce|ca|ça|la|le|mon|ce) ?(?:image|prompt|texte|truc)?", _sa(prompt)))
    w, h = 1024, 1024
    if re.search(r"fonds? d'?ecran|wallpaper|paysage|panoram|banniere|miniature|16[:/]9|horizontal", t):
        w, h = 1344, 768
    elif re.search(r"portrait|affiche|poster|vertical|9[:/]16|telephone|personnage en pied|corps entier", t):
        w, h = 768, 1344
    return {"prompt": "" if clip else prompt, "presse_papiers": clip, "w": w, "h": h}


def blocked(prompt):
    return bool(BLOCK.search(_sa(prompt)))


def translate_prompt(prompt):
    return ("Traduis cette description d'image en anglais pour un générateur d'images. Garde tous les détails, "
            "n'ajoute rien, réponds uniquement avec la traduction, sur une seule ligne :\n\n" + prompt)


def api_key():
    try:
        return Path(KEY_FILE).read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def set_api_key(k):
    p = Path(KEY_FILE)
    if not (k or "").strip():
        try:
            p.unlink()
        except Exception:
            pass
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(k.strip())


def _is_image(data):
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def gen_online(prompt, w=1024, h=1024, seed=None, model="flux"):
    """Pollinations (API publique prévue pour ça). Essaie la passerelle actuelle puis l'ancienne adresse."""
    seed = random.randint(1, 10 ** 9) if seed is None else seed
    q = urllib.parse.quote(prompt[:1500], safe="")
    par = urllib.parse.urlencode({"width": w, "height": h, "seed": seed, "model": model, "nologo": "true",
                                  "safe": "true", "private": "true"})
    key = api_key()
    err = None
    for url, hdr in ((f"https://gen.pollinations.ai/image/{q}?{par}", {"Authorization": "Bearer " + key} if key else {}),
                     (f"https://image.pollinations.ai/prompt/{q}?{par}", {})):
        try:
            data = _get(url, hdr, timeout=180)
            if _is_image(data):
                return data
            err = RuntimeError("réponse inattendue du service")
        except Exception as e:
            err = e
    raise RuntimeError(f"le service en ligne n'a pas répondu ({err})")


NEG = "nsfw, nude, lowres, bad anatomy, bad hands, extra fingers, blurry, watermark, text, signature, jpeg artifacts"


def local_ok(base):
    try:
        _get(base.rstrip("/") + "/sdapi/v1/options", timeout=3)
        return True
    except Exception:
        return False


def gen_local(base, prompt, w=1024, h=1024, steps=25):
    """Stable Diffusion sur ton PC (Forge, AUTOMATIC1111, SD.Next lancés avec --api)."""
    body = json.dumps({"prompt": prompt, "negative_prompt": NEG, "width": w, "height": h, "steps": steps,
                       "cfg_scale": 6, "batch_size": 1}).encode()
    data = _get(base.rstrip("/") + "/sdapi/v1/txt2img", {"Content-Type": "application/json"}, body, timeout=900)
    img = json.loads(data)["images"][0]
    return base64.b64decode(img.split(",", 1)[-1])


def save_image(data, prompt, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ext = ".png" if data[:4] == b"\x89PNG" else ".webp" if data[:4] == b"RIFF" else ".jpg"
    slug = re.sub(r"[^a-z0-9]+", "-", _sa(prompt))[:40].strip("-") or "image"
    p = folder / f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug}{ext}"
    p.write_bytes(data)
    return p


PERCHANCE = "https://perchance.org/ai-text-to-image-generator"
LOCAL_HELP = ("Pour créer des images sur ton PC (carte graphique conseillée : 6 Go de mémoire vidéo ou plus) :\n\n"
              "• Stable Diffusion WebUI Forge — le plus simple et rapide. Lance-le avec l'option --api.\n"
              "• AUTOMATIC1111 ou SD.Next — même principe, option --api.\n\n"
              "Modèles conseillés : SDXL (8 Go), SD 1.5 (4 Go), Flux schnell (12 Go ou plus).\n"
              "Ensuite, dans Réglages → Création d'images, choisis « Sur mon PC » et laisse l'adresse "
              "http://127.0.0.1:7860 (celle par défaut).")
