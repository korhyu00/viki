"""Actus et suivis : les nouvelles des sujets choisis, et le suivi des mangas, séries, animés, films et sorties ciné.

Internet seulement quand tu l'actives (Réglages → Assistant → Actus et suivis), sans compte :
  - actus : Google Actualités (flux RSS public) ;
  - séries : TVmaze ; animés et mangas (statut, chapitres) : AniList ; nouveaux chapitres de manga : MangaUpdates ;
  - films et sorties ciné : TMDB, avec ta clé gratuite (facultatif ; sinon les actus « sorties cinéma »).
Viki ne donne jamais de lien vers des sites de lecture illégaux : elle te dit seulement qu'un chapitre est sorti.
"""
import datetime
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Viki/1.0 (compagne de bureau)"}
TIMEOUT = 15

# sujet -> recherche Google Actualités
SUJETS = {
    "science": ("🔬 Science", "science découverte"),
    "informatique": ("💻 Informatique", "informatique OR tech OR logiciel"),
    "ia": ("🤖 Intelligence artificielle", "intelligence artificielle"),
    "jeux": ("🎮 Jeux vidéo", "jeux vidéo"),
    "manga": ("📚 Manga et animé", "manga OR anime"),
    "cinema": ("🎬 Cinéma et séries", "cinéma OR série"),
    "espace": ("🚀 Espace", "espace astronomie"),
    "sante": ("🩺 Santé", "santé"),
    "linux": ("🐧 Linux et logiciel libre", "Linux"),
    "monde": ("🌍 Monde", "actualité internationale"),
    "sport": ("⚽ Sport", "sport"),
    "musique": ("🎵 Musique", "musique"),
}
TYPES = {"serie": "📺 Série", "anime": "🌸 Animé", "manga": "📖 Manga", "film": "🎬 Film"}


def _get(url, data=None, headers=None):
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _json(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    hh = {"Content-Type": "application/json", "Accept": "application/json"} if payload is not None else {}
    hh.update(headers or {})
    return json.loads(_get(url, data, hh))


# ================================================================== actus
def news(query, n=6, lang="fr"):
    """Titres récents pour une recherche -> [{"titre", "source", "lien", "date"}]."""
    gl = {"fr": "FR", "en": "US", "es": "ES", "de": "DE", "it": "IT", "ru": "RU", "zh": "CN", "ja": "JP",
          "hi": "IN", "pt": "BR"}.get(lang, "FR")
    if lang == "zh":
        lang = "zh-Hans"
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query + " when:3d") +
           f"&hl={lang}&gl={gl}&ceid={gl}:{lang}")
    root = ET.fromstring(_get(url))
    out = []
    for it in root.iter("item"):
        t = html.unescape(it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and t.endswith(" - " + src):
            t = t[: -len(src) - 3]
        out.append({"titre": t, "source": src, "lien": it.findtext("link") or "",
                    "date": it.findtext("pubDate") or ""})
        if len(out) >= n:
            break
    return out


_BING_LANG = {"fr": ("fr", "FR"), "en": ("en", "US"), "es": ("es", "ES"), "de": ("de", "DE"), "it": ("it", "IT"),
              "ru": ("ru", "RU"), "zh": ("zh-hans", "CN"), "ja": ("ja", "JP"), "hi": ("hi", "IN"), "pt": ("pt", "BR")}
UNE = {"fr": "actualité", "en": "news", "es": "noticias", "de": "nachrichten", "it": "notizie", "ru": "новости",
       "zh": "新闻", "ja": "ニュース", "hi": "समाचार", "pt": "notícias"}


def _age_h(date_txt):
    """Âge d'un article en heures (None si la date est illisible)."""
    import email.utils
    d = None
    try:
        d = email.utils.parsedate_to_datetime(date_txt)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat((date_txt or "").replace("Z", "+00:00"))
        except Exception:
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - d).total_seconds() / 3600


def _vrai_article(t):
    """« Flash Actu », « Appels sur l'actualité », « État et collectivités » : des pages d'émission ou de
    rubrique, pas des articles. Un vrai titre fait au moins 5 mots (2 en chinois/japonais : pas d'espaces)."""
    t = (t or "").strip()
    if not t:
        return False
    if " " not in t:
        return len(t) >= 8
    return len(t.split()) >= 5


def frais(items, n, max_h=72):
    """Garde les vrais articles récents (3 jours), les plus récents d'abord ; les vieux et les rubriques partent."""
    bons, sans_date = [], []
    for x in items:
        if not _vrai_article(x.get("titre")):
            continue
        a = _age_h(x.get("date", ""))
        if a is None:
            sans_date.append(x)
        elif -2 <= a <= max_h:
            bons.append((a, x))
    bons.sort(key=lambda ax: ax[0])
    return ([x for _a, x in bons] + sans_date)[:n]


def news_rich(query, n=8, lang="fr"):
    """Titres AVEC images : Bing Actualités (flux RSS public, miniatures comprises), sinon Google Actualités.
    -> [{"titre", "source", "lien", "date", "image"}]"""
    lang = (lang or "fr")[:2]
    q = query.strip() or UNE.get(lang, "actualité")
    sl, cc = _BING_LANG.get(lang, ("fr", "FR"))
    out = []
    try:
        url = ("https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(q) +
               f"&setlang={sl}&cc={cc}&mkt={sl.split('-')[0]}-{cc}")
        _name, items = _parse_feed(_get(url))
        out = frais([x for x in items if x.get("lien")], n)
    except Exception:
        out = []
    if len(out) < 3:                                 # Bing muet : Google Actualités (sans images)
        try:
            seen = {x["titre"] for x in out}
            out += [dict(x, image="") for x in frais(news(q, n * 2, lang), n) if x["titre"] not in seen]
        except Exception:
            if not out:
                raise
    return out[:n]


NAV = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


def og_image(url, timeout=8):
    """L'image de partage d'une page (og:image / twitter:image), en lisant seulement le début de la page."""
    host = urllib.parse.urlparse(url).netloc
    if not url.startswith("http") or host.endswith(("news.google.com", "bing.com")):
        return ""
    h = {"User-Agent": NAV, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "fr,en;q=0.8"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        page = r.read(800_000).decode("utf-8", "replace")
    for m in re.finditer(r"<meta\b[^>]*>", page, re.I):
        tag = m.group(0)
        if re.search(r"(?:property|name)=[\"'](?:og:image(?::secure_url|:url)?|twitter:image(?::src)?)[\"']", tag, re.I):
            c = re.search(r"content=[\"']([^\"']+)", tag, re.I)
            if c:
                return urllib.parse.urljoin(url, html.unescape(c.group(1)))
    m = re.search(r"<link\b[^>]*rel=[\"']image_src[\"'][^>]*href=[\"']([^\"']+)", page, re.I)
    if m:
        return urllib.parse.urljoin(url, html.unescape(m.group(1)))
    # sinon : la première grande image de l'article
    for m in re.finditer(r"<img\b[^>]*>", page, re.I):
        tag = m.group(0)
        src = re.search(r"(?:data-src|data-lazy-src|src)=[\"']([^\"']+\.(?:jpe?g|png|webp)[^\"']*)", tag, re.I)
        if src and not re.search(r"logo|icon|avatar|sprite|pixel|emoji", src.group(1), re.I):
            return urllib.parse.urljoin(url, html.unescape(src.group(1)))
    return ""


def fetch_image(url, limit=4_000_000, timeout=10, referer=""):
    """Les octets d'une image (4 Mo au plus). referer : la page de l'article (certains sites l'exigent)."""
    h = {"User-Agent": NAV, "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*"}
    if referer:
        h["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("image trop lourde")
    return data


def news_for(sujets, mots=(), n=4):
    """{libellé: [titres]} pour les sujets cochés et les mots-clés perso."""
    res = {}
    for k in sujets:
        if k in SUJETS:
            lab, q = SUJETS[k]
            try:
                res[lab] = news(q, n)
            except Exception as e:
                res[lab] = [{"titre": f"(indisponible : {str(e)[:60]})", "source": "", "lien": "", "date": ""}]
    for m in mots:
        m = m.strip()
        if m:
            try:
                res["🔎 " + m] = news(m, n)
            except Exception as e:
                res["🔎 " + m] = [{"titre": f"(indisponible : {str(e)[:60]})", "source": "", "lien": "", "date": ""}]
    return res


# ================================================================== séries (TVmaze)
def serie_search(name):
    d = _json("https://api.tvmaze.com/singlesearch/shows?q=" + urllib.parse.quote(name))
    return {"id": d["id"], "nom": d["name"], "statut": d.get("status", "")}


def serie_info(sid):
    d = _json(f"https://api.tvmaze.com/shows/{sid}?embed[]=nextepisode&embed[]=previousepisode")
    emb = d.get("_embedded") or {}
    nxt, prv = emb.get("nextepisode"), emb.get("previousepisode")
    fmt = lambda e: f"S{e.get('season', 0):02d}E{e.get('number') or 0:02d}" if e else ""
    return {"nom": d.get("name", ""), "statut": d.get("status", ""),
            "dernier": fmt(prv), "dernier_date": (prv or {}).get("airdate", ""),
            "prochain": fmt(nxt), "prochain_date": (nxt or {}).get("airdate", "")}


# ================================================================== animés et mangas (AniList)
ANI_Q = """query ($s: String, $t: MediaType) { Media(search: $s, type: $t) { id title { romaji english native }
 status episodes chapters volumes nextAiringEpisode { episode airingAt } } }"""
ANI_ID = """query ($i: Int) { Media(id: $i) { id title { romaji english } status episodes chapters
 nextAiringEpisode { episode airingAt } } }"""


def _ani(query, var):
    return _json("https://graphql.anilist.co", {"query": query, "variables": var})["data"]["Media"]


def anime_search(name):
    m = _ani(ANI_Q, {"s": name, "t": "ANIME"})
    return {"id": m["id"], "nom": (m["title"].get("english") or m["title"].get("romaji")), "statut": m["status"]}


def anime_info(aid):
    m = _ani(ANI_ID, {"i": int(aid)})
    nx = m.get("nextAiringEpisode") or {}
    when = datetime.datetime.fromtimestamp(nx["airingAt"]).strftime("%Y-%m-%d %H:%M") if nx else ""
    return {"nom": m["title"].get("english") or m["title"].get("romaji"), "statut": m.get("status", ""),
            "dernier": f"épisode {nx['episode'] - 1}" if nx and nx.get("episode", 1) > 1 else
            (f"{m['episodes']} épisodes" if m.get("episodes") else ""),
            "prochain": f"épisode {nx['episode']}" if nx else "", "prochain_date": when}


# ================================================================== mangas : derniers chapitres (MangaUpdates)
def manga_search(name):
    d = _json("https://api.mangaupdates.com/v1/series/search", {"search": name, "perpage": 5})
    r = (d.get("results") or [])[0]["record"]
    return {"id": r["series_id"], "nom": html.unescape(r.get("title", name)), "statut": ""}


def manga_info(mid):
    d = _json(f"https://api.mangaupdates.com/v1/series/{mid}")
    ch = d.get("latest_chapter")
    return {"nom": html.unescape(d.get("title", "")), "statut": "terminé" if d.get("completed") else "en cours",
            "dernier": f"chapitre {ch}" if ch else "", "prochain": "", "prochain_date": ""}


# ================================================================== films et ciné (TMDB, clé gratuite)
def tmdb(path, key, **params):
    params.update({"api_key": key, "language": "fr-FR"})
    return _json(f"https://api.themoviedb.org/3/{path}?" + urllib.parse.urlencode(params))


def film_search(name, key):
    r = tmdb("search/movie", key, query=name)["results"][0]
    return {"id": r["id"], "nom": r["title"], "statut": r.get("release_date", "")}


def film_info(fid, key):
    d = tmdb(f"movie/{fid}", key, append_to_response="release_dates")
    fr = ""
    for c in (d.get("release_dates") or {}).get("results", []):
        if c.get("iso_3166_1") == "FR":
            dates = sorted(x.get("release_date", "")[:10] for x in c.get("release_dates", []) if x.get("type") == 3)
            fr = dates[0] if dates else ""
    date = fr or d.get("release_date", "")
    today = datetime.date.today().isoformat()
    return {"nom": d.get("title", ""), "statut": d.get("status", ""),
            "dernier": ("sorti le " + date) if date and date <= today else "",
            "prochain": "sortie" if date and date > today else "", "prochain_date": date if date > today else ""}


def cinema(key, kind="now_playing", n=10):
    """Films à l'affiche (now_playing) ou bientôt (upcoming) en France."""
    res = tmdb(f"movie/{kind}", key, region="FR").get("results", [])[:n]
    return [{"titre": r["title"], "date": r.get("release_date", ""), "note": r.get("vote_average", 0),
             "resume": (r.get("overview") or "")[:220]} for r in res]


# ================================================================== suivis
SEARCH = {"serie": serie_search, "anime": anime_search, "manga": manga_search}
INFO = {"serie": serie_info, "anime": anime_info, "manga": manga_info}


def add_follow(kind, name, key=""):
    if kind == "film":
        if not key:
            raise RuntimeError("pour suivre un film, ajoute ta clé TMDB gratuite")
        r = film_search(name, key)
    else:
        r = SEARCH[kind](name)
    r["type"] = kind
    r.update(refresh_one(r, key))
    return r


def refresh_one(item, key=""):
    kind = item["type"]
    info = film_info(item["id"], key) if kind == "film" else INFO[kind](item["id"])
    return {k: v for k, v in info.items() if k != "nom" or v}


def check_all(items, key=""):
    """Met à jour les suivis -> (items, nouveautés en texte)."""
    news_ = []
    today = datetime.date.today().isoformat()
    for it in items:
        try:
            before = it.get("dernier", "")
            info = refresh_one(it, key)
        except Exception as e:
            it["erreur"] = str(e)[:80]
            continue
        it.pop("erreur", None)
        it.update(info)
        if info.get("dernier") and before and info["dernier"] != before:
            label = {"serie": "nouvel épisode", "anime": "nouvel épisode", "manga": "nouveau",
                     "film": "c'est sorti"}[it["type"]]
            news_.append(f"{TYPES[it['type']]} {it['nom']} : {label} — {info['dernier']}")
        pd = (info.get("prochain_date") or "")[:10]
        if pd == today and it.get("annonce") != today:
            it["annonce"] = today
            news_.append(f"{TYPES[it['type']]} {it['nom']} : {info.get('prochain', 'sortie')} aujourd'hui !")
    return items, news_


def describe(it):
    s = f"{TYPES.get(it['type'], '')} {it.get('nom', '?')}"
    if it.get("dernier"):
        s += f" — dernier : {it['dernier']}"
    if it.get("prochain"):
        s += f" — prochain : {it['prochain']}" + (f" le {it['prochain_date']}" if it.get("prochain_date") else "")
    if it.get("erreur"):
        s += f"  (⚠️ {it['erreur']})"
    return s


# ================================================================== sites suivis (liens RSS / Atom)
SITES_IDEES = [
    ("Numerama (tech, science)", "https://www.numerama.com/feed/"),
    ("Korben (informatique)", "https://korben.info/feed"),
    ("LinuxFr.org", "https://linuxfr.org/news.atom"),
    ("Futura (sciences)", "https://www.futura-sciences.com/"),
    ("Frandroid (tech)", "https://www.frandroid.com/feed"),
    ("Jeuxvideo.com (actus)", "https://www.jeuxvideo.com/"),
    ("AlloCiné (actus ciné)", "https://www.allocine.fr/"),
    ("Le Monde (Pixels)", "https://www.lemonde.fr/pixels/rss_full.xml"),
]
ATOM = "{http://www.w3.org/2005/Atom}"


def normalize_url(u):
    u = (u or "").strip()
    if u and not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u


_IMG_EXT = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:[?#]|$)", re.I)


def _clean_link(url):
    """Les liens « clic » de Bing Actualités -> l'adresse de l'article."""
    p = urllib.parse.urlparse(url)
    if p.netloc.endswith("bing.com") and p.path.endswith("/apiclick.aspx"):
        return dict(urllib.parse.parse_qsl(p.query)).get("url") or url
    return url


def _abs_img(u):
    u = html.unescape((u or "").strip())
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/th?"):                     # miniatures de Bing
        u = "https://www.bing.com" + u
    if "bing.com/th?" in u and "&w=" not in u:     # miniature de Bing : on la demande plus grande
        u += "&w=336&h=216&c=7&rs=1"
    return u if u.startswith("http") else ""


def _item_image(it):
    """L'image d'un article de flux : media:content / media:thumbnail, enclosure, News:Image (Bing),
    ou la 1re <img> de la description."""
    for el in it.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        url = el.get("url") or el.get("href") or ""
        if tag in ("content", "thumbnail") and url and (el.get("medium", "") == "image" or
                                                       el.get("type", "").startswith("image") or
                                                       tag == "thumbnail" or _IMG_EXT.search(url)):
            return _abs_img(url)
        if tag in ("enclosure", "link") and url and (el.get("type", "").startswith("image") or
                                                     (tag == "enclosure" and _IMG_EXT.search(url))):
            return _abs_img(url)
        if tag == "image" and el is not it:
            u = _abs_img(el.text or el.findtext("url") or "")
            if u:
                return u
    for tag in ("description", "{http://purl.org/rss/1.0/modules/content/}encoded",
                "{http://www.w3.org/2005/Atom}content", "{http://www.w3.org/2005/Atom}summary"):
        txt = it.findtext(tag) or ""
        m = re.search(r"<img[^>]+src=[\"']([^\"']+)", html.unescape(txt) if "&lt;" in txt else txt, re.I)
        if m:
            u = _abs_img(m.group(1))
            if u:
                return u
    return ""


def _parse_feed(data):
    """RSS 2.0 / Atom -> (titre du site, [{"titre", "lien", "id", "date"}])."""
    root = ET.fromstring(data)
    items = []
    if root.tag == ATOM + "feed":
        site = (root.findtext(ATOM + "title") or "").strip()
        for e in root.findall(ATOM + "entry"):
            link = ""
            for l in e.findall(ATOM + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({"titre": html.unescape((e.findtext(ATOM + "title") or "").strip()), "lien": link,
                          "id": e.findtext(ATOM + "id") or link,
                          "date": e.findtext(ATOM + "updated") or e.findtext(ATOM + "published") or "",
                          "image": _item_image(e), "source": ""})
    else:
        ch = root.find("channel")
        site = ((ch.findtext("title") if ch is not None else "") or "").strip()
        for it in root.iter("item"):
            link = _clean_link((it.findtext("link") or "").strip())
            src = ""
            for el in it:
                if el.tag.rsplit("}", 1)[-1].lower() == "source" and (el.text or "").strip():
                    src = el.text.strip()
            items.append({"titre": html.unescape((it.findtext("title") or "").strip()), "lien": link,
                          "id": (it.findtext("guid") or link).strip(), "date": it.findtext("pubDate") or "",
                          "image": _item_image(it), "source": html.unescape(src)})
    return html.unescape(site), [x for x in items if x["titre"]]


def discover(url):
    """Lien d'un site ou d'un flux -> {"nom", "flux", "site"}. Cherche le flux RSS/Atom tout seul."""
    url = normalize_url(url)
    data = _get(url)
    head = data[:600].lstrip().lower()
    if head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head:
        try:
            name, _items = _parse_feed(data)
            return {"nom": name or urllib.parse.urlparse(url).netloc, "flux": url, "site": url}
        except ET.ParseError:
            pass
    page = data.decode("utf-8", "replace")
    cands = []
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        tag = m.group(0)
        if re.search(r"application/(?:rss|atom)\+xml", tag, re.I):
            h = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if h:
                cands.append(urllib.parse.urljoin(url, html.unescape(h.group(1))))
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    cands += [base + p for p in ("/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml")]
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    for f in cands:
        try:
            name, items = _parse_feed(_get(f))
            if items:
                nom = name or (html.unescape(title.group(1)).strip()[:60] if title else urllib.parse.urlparse(url).netloc)
                return {"nom": nom, "flux": f, "site": url}
        except Exception:
            continue
    raise RuntimeError("je n'ai pas trouvé de flux d'actus (RSS) sur ce site")


def site_items(src, n=10):
    _name, items = _parse_feed(_get(src["flux"]))
    return items[:n]


def check_sites(sources, per_site=2):
    """Nouveaux articles des sites suivis -> (sources mises à jour, [(site, article)])."""
    new = []
    for s in sources:
        if not s.get("suivre", True):
            continue
        try:
            items = site_items(s, 15)
        except Exception as e:
            s["erreur"] = str(e)[:80]
            continue
        s.pop("erreur", None)
        seen = set(s.get("vus", []))
        fresh = [x for x in items if x["id"] not in seen]
        if seen:                                 # la 1re fois, on ne fait que mémoriser
            new += [(s["nom"], x) for x in fresh[:per_site]]
        s["vus"] = ([x["id"] for x in items] + [i for i in s.get("vus", []) if i not in {x["id"] for x in items}])[:80]
    return sources, new
