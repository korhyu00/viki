"""« Quels restos autour de moi ? » : lieux proches (OpenStreetMap), sur une carte, avec leur site web.

Internet seulement quand tu le demandes, et seulement vers OpenStreetMap (libre, sans compte, sans pub) :
  • Nominatim : transformer ton adresse (ou « la gare de Lyon ») en position, une fois
  • Overpass  : les restaurants, cafés… autour de cette position
  • tuiles     : les images de la carte (gardées dans un cache)
"""
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "Viki/1.0 (compagnon de bureau ; https://korhyu.com)"
NOMINATIM = "https://nominatim.openstreetmap.org"
# plusieurs serveurs : le principal est souvent surchargé (« timed out »), on passe vite au suivant
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
# si aucun ne répond : recherche par Nominatim (moins de détails, mais rapide)
NOMI_PHRASES = {"restaurant": ["restaurant", "fast food"], "cafe": ["cafe"], "bar": ["bar", "pub"],
                "boulangerie": ["bakery"], "supermarche": ["supermarket"], "pharmacie": ["pharmacy"],
                "cinema": ["cinema"], "parc": ["park"]}
TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "viki" / "tuiles"

# ce qu'on peut chercher : mot-clé -> (filtres OSM, icône, libellé)
KINDS = {
    "restaurant": ([("amenity", "restaurant"), ("amenity", "fast_food")], "🍽️", "restaurants"),
    "cafe": ([("amenity", "cafe")], "☕", "cafés"),
    "bar": ([("amenity", "bar"), ("amenity", "pub")], "🍺", "bars"),
    "boulangerie": ([("shop", "bakery"), ("shop", "pastry")], "🥐", "boulangeries"),
    "supermarche": ([("shop", "supermarket"), ("shop", "convenience")], "🛒", "magasins d'alimentation"),
    "pharmacie": ([("amenity", "pharmacy")], "💊", "pharmacies"),
    "cinema": ([("amenity", "cinema")], "🎬", "cinémas"),
    "parc": ([("leisure", "park")], "🌳", "parcs"),
}
# « sushi », « pizza »… -> valeur du champ cuisine d'OpenStreetMap
CUISINES = {
    "pizza": "pizza", "pizzeria": "pizza", "italien": "italian", "sushi": "sushi", "japonais": "japanese",
    "ramen": "ramen", "chinois": "chinese", "thai": "thai", "vietnamien": "vietnamese", "coreen": "korean",
    "indien": "indian", "libanais": "lebanese", "kebab": "kebab", "burger": "burger", "hamburger": "burger",
    "mexicain": "mexican", "tacos": "tacos", "creperie": "crepe", "crepe": "crepe", "francais": "french",
    "vegetarien": "vegetarian", "vegan": "vegan", "fruits de mer": "seafood", "poisson": "fish",
    "marocain": "moroccan", "africain": "african", "grec": "greek", "turc": "turkish", "poulet": "chicken",
}
CUISINE_FR = {"pizza": "pizzeria", "italian": "italien", "sushi": "sushi", "japanese": "japonais", "ramen": "ramen",
              "chinese": "chinois", "thai": "thaï", "vietnamese": "vietnamien", "korean": "coréen",
              "indian": "indien", "lebanese": "libanais", "kebab": "kebab", "burger": "burger",
              "mexican": "mexicain", "tacos": "tacos", "crepe": "crêperie", "french": "français",
              "regional": "régional", "vegetarian": "végétarien", "vegan": "vegan", "seafood": "fruits de mer",
              "fish": "poisson", "moroccan": "marocain", "african": "africain", "greek": "grec",
              "turkish": "turc", "chicken": "poulet", "sandwich": "sandwichs", "asian": "asiatique",
              "coffee_shop": "café", "ice_cream": "glacier", "steak_house": "grill", "bagel": "bagels"}
TYPE_FR = {"restaurant": "restaurant", "fast_food": "restauration rapide", "cafe": "café", "bar": "bar",
           "pub": "pub", "bakery": "boulangerie", "pastry": "pâtisserie", "supermarket": "supermarché",
           "convenience": "épicerie", "pharmacy": "pharmacie", "cinema": "cinéma", "park": "parc"}


def _plain(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _get(url, timeout=25, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "fr"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ================================================================ comprendre la demande
KIND_WORDS = (
    (r"r[eé]?s?[st]+[oau]+|restaurent|resteau|restos?|restaus?|restaurants?|manger|bouffer|d[eé]jeuner|d[iî]ner|"
     r"fast.?food|snack|traiteur|grignoter|bouffe|\bon mange\b|\bmange o[uù]|macdo|mcdo|mc ?do|mcdonald|kfc|burger king|subway|quick", "restaurant"),
    (r"caf[eé]s?|salon de th[eé]|coffee|starbucks|petit d[eé]j", "cafe"),
    (r"\bbars?\b|\bpubs?\b|boire (?:un|une) (?:verre|bi[eè]re|coup)|ap[eé]ro|bi[eè]re", "bar"),
    (r"boulang|p[aâ]tiss|\bpain\b|croissant|baguette|viennoiserie", "boulangerie"),
    (r"supermarch|sup[eé]rette|[eé]picerie|faire (?:les|des) courses|\bcourses\b|carrefour|leclerc|lidl|"
     r"intermarch|auchan|monoprix|franprix|casino|aldi", "supermarche"),
    (r"pharmacie|pharma|m[eé]dicament", "pharmacie"),
    (r"cin[eé]ma|\bcin[eé]\b|voir un film", "cinema"),
    (r"\bparcs?\b|jardin|square|se promener|balade", "parc"),
)
PLACE_WORDS = (r"autour|pr[eè]s|proche|[aà] c[oô]t[eé]|dans le coin|pas loin|dans le quartier|aux alentours|"
               r"\bici\b|\bdu coin\b|par ici|alentour|\bvers (?:la|le|l'|les|chez)\b|[aà] proximit[eé]|sur (?:une|la) carte|o[uù] (?:est|sont|"
               r"trouver|manger|aller|acheter|boire)|\bo[uù]\b.*\?")
INTENT_WORDS = (r"\?|\b(?:quels?|quelles?|o[uù]|trouve|trouver|cherche|chercher|montre|affiche|il y a|y a|y'a|ya|"
                r"connais|conseille|conseiller|propose|recommande|donne|liste|envie|faim|soif|je veux|j'veux|"
                r"j'aimerais|je voudrais|on va|on mange|on boit|aller|ouvert|ouverte|un bon|une bonne|des bons|"
                r"meilleurs?|sympa|indique|dis-moi|sais-tu)\b|^(?:des|un|une|les|du) ")


def parse_request(text):
    """« des sushis pas loin de la gare » -> {"kind": "restaurant", "cuisine": "sushi", "near": "la gare"}
    ou None si ce n'est pas une demande de lieu. Accepte beaucoup de façons de le dire (et quelques fautes)."""
    raw = text.strip()
    t = raw.lower()
    tp = _plain(raw)
    kind = cuisine = None
    for k, v in sorted(CUISINES.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + k + r"s?\b", tp):
            kind, cuisine = "restaurant", v
            break
    if re.search(r"macdo|mcdo|mc ?do|mcdonald|burger king|\bquick\b|\bkfc\b", tp):
        kind, cuisine = "restaurant", "burger"
    if not kind:
        for pat, k in KIND_WORDS:
            if re.search(pat, t) or re.search(pat, tp):
                kind = k
                break
    if not kind:
        return None
    place = re.search(PLACE_WORDS, t) or re.search(PLACE_WORDS, tp)
    intent = re.search(INTENT_WORDS, t) or re.search(INTENT_WORDS, tp)
    short = len(re.findall(r"\w+", tp)) <= 4               # « resto ? », « une pizzeria », « pharmacie ouverte »
    if not (place or intent or short):
        return None
    # phrases qui parlent d'un lieu sans en chercher un : « j'étais au resto hier », « le café est froid »
    if re.search(r"\b(?:hier|tout a l'heure|ce matin|j'etais|j'ai mange|on a mange|j'ai bu|est froid|est chaud|"
                 r"je bois|je mange|j'adore|j'aime|aimes?|preferes?|deteste)\b", tp) and not place:
        return None
    near = ""
    m = re.search(r"\b(?:autour|pr[eè]s|proche|[aà] c[oô]t[eé]|pas loin|aux alentours|vers|dans le quartier)\s+"
                  r"(?:de\s+|d'|du\s+|des\s+|)(.+)$", raw, re.I)
    if m:
        cand = m.group(1).strip(" ?!.")
        cand = re.split(r"\s+(?:des|de|du|un|une|les|pour|qui|avec|ou|stp|s'il)\s+(?=\w*(?:resto|restau|caf|bar|pub|"
                        r"pizz|sushi|kebab|burger|boulang|pharma|cin|manger|japon|chinois|italien|indien|te|vous))",
                        cand, flags=re.I)[0]
        cand = re.sub(r"\s+(?:stp|svp|s'il te pla[iî]t|s'il vous pla[iî]t|merci)$", "", cand, flags=re.I).strip(" ,")
        if cand and not re.fullmatch(r"(?:moi|chez moi|ici|la maison|ma maison|mon bureau|nous|chez nous|mon "
                                     r"appart|mon appartement|la|le|l'|ce coin|mon quartier|par ici)", _plain(cand)):
            near = cand
    return {"kind": kind, "cuisine": cuisine, "near": near}


# ================================================================ internet (OpenStreetMap)
def geocode(query):
    """Adresse / lieu -> (lat, lon, nom affiché)."""
    url = f"{NOMINATIM}/search?format=jsonv2&limit=1&addressdetails=0&q=" + urllib.parse.quote(query)
    res = json.loads(_get(url))
    if not res:
        raise LookupError(f"je ne trouve pas « {query} » sur la carte")
    r = res[0]
    return float(r["lat"]), float(r["lon"]), r.get("display_name", query)


def dist_m(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _place(tg, la, lo, lat, lon, typ, osm):
    cu = [CUISINE_FR.get(c.strip(), c.strip().replace("_", " ")) for c in (tg.get("cuisine") or "").split(";")
          if c.strip()]
    addr = " ".join(x for x in (tg.get("addr:housenumber", ""), tg.get("addr:street", "")) if x)
    return {"nom": tg["name"], "lat": float(la), "lon": float(lo), "type": TYPE_FR.get(typ, typ),
            "cuisine": ", ".join(cu[:3]), "adresse": addr, "ville": tg.get("addr:city", ""),
            "horaires": tg.get("opening_hours", ""),
            "site": tg.get("website") or tg.get("contact:website") or tg.get("url") or "",
            "tel": tg.get("phone") or tg.get("contact:phone") or "",
            "vegan": tg.get("diet:vegan", ""), "emporter": tg.get("takeaway", ""), "osm": osm,
            "dist": dist_m(lat, lon, float(la), float(lo))}


def _uniq(out, limit):
    seen, uniq = set(), []
    for o in sorted(out, key=lambda o: o["dist"]):
        k = (o["nom"].lower(), round(o["lat"], 4), round(o["lon"], 4))
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq[:limit]


def _overpass(q):
    """Essaie les serveurs un par un (vite), en commençant par celui qui a marché la dernière fois."""
    last = None
    for ep in list(OVERPASS):
        try:
            data = json.loads(_get(ep, timeout=15, data=urllib.parse.urlencode({"data": q}).encode()))
            if ep != OVERPASS[0]:
                OVERPASS.remove(ep)
                OVERPASS.insert(0, ep)
            return data
        except Exception as e:
            last = e
    raise RuntimeError(f"aucun serveur OpenStreetMap ne répond ({last})")


def search_overpass(lat, lon, kind, cuisine, rad, limit):
    filters = KINDS[kind][0]
    parts = []
    for k, v in filters:
        extra = f'["cuisine"~"{cuisine}",i]' if cuisine else ""
        parts.append(f'nwr["{k}"="{v}"]{extra}["name"](around:{int(rad)},{lat},{lon});')
    data = _overpass(f"[out:json][timeout:12];({''.join(parts)});out center tags {limit * 2};")
    out = []
    for el in data.get("elements", []):
        tg = el.get("tags", {})
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if la is None or not tg.get("name"):
            continue
        typ = next((v for k, v in filters if tg.get(k) == v), "")
        out.append(_place(tg, la, lo, lat, lon, typ,
                          f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}"))
    return _uniq(out, limit)


def search_nominatim(lat, lon, kind, cuisine, rad, limit):
    """Plan B : la recherche de Nominatim dans un carré autour de toi (horaires et sites moins souvent connus)."""
    dlat = rad / 111320.0
    dlon = rad / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    box = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"
    out = []
    for ph in NOMI_PHRASES[kind]:
        q = (cuisine + " " + ph) if cuisine and kind == "restaurant" else ph
        url = (f"{NOMINATIM}/search?format=jsonv2&limit=40&bounded=1&extratags=1&addressdetails=1&viewbox={box}"
               "&q=" + urllib.parse.quote(q))
        try:
            res = json.loads(_get(url, timeout=15))
        except Exception:
            continue
        for r in res:
            et, ad = r.get("extratags") or {}, r.get("address") or {}
            name = r.get("name") or (r.get("display_name", "").split(",")[0])
            if not name:
                continue
            tg = dict(et, name=name)
            tg.setdefault("addr:street", ad.get("road", ""))
            tg.setdefault("addr:housenumber", ad.get("house_number", ""))
            tg.setdefault("addr:city", ad.get("city") or ad.get("town") or ad.get("village") or "")
            out.append(_place(tg, r["lat"], r["lon"], lat, lon, r.get("type", ""),
                              f"https://www.openstreetmap.org/{r.get('osm_type', 'node')}/{r.get('osm_id', '')}"))
        time.sleep(1.0)                             # règle de Nominatim : une demande par seconde
    if cuisine:
        keep = [o for o in out if cuisine in _plain(o["cuisine"] + " " + o["nom"]) or
                CUISINE_FR.get(cuisine, cuisine) in o["cuisine"]]
        out = keep or out
    return _uniq([o for o in out if o["dist"] <= rad * 1.5], limit)


def search(lat, lon, kind="restaurant", cuisine=None, radius=1000, limit=40):
    """Les lieux proches, du plus près au plus loin. Élargit la zone si on en trouve trop peu.
    OpenStreetMap (Overpass) d'abord ; s'il est saturé, Nominatim."""
    best, err = None, None
    for rad in (radius, radius * 2, radius * 4):
        try:
            res = search_overpass(lat, lon, kind, cuisine, rad, limit)
        except Exception as e:
            err = e
            break
        best = (res, rad)
        if len(res) >= 5:
            return best
    if best and best[0]:
        return best
    if err is not None:                             # serveurs saturés : plan B
        for rad in (radius * 1.5, radius * 3):
            res = search_nominatim(lat, lon, kind, cuisine, rad, limit)
            if len(res) >= 3 or rad >= radius * 3:
                if res:
                    return res, rad
        raise RuntimeError("OpenStreetMap est saturé en ce moment, réessaie dans une minute")
    return best or ([], radius)


def horaires_fr(h):
    """« Mo-Sa 11:30-14:30; Su off » -> « lun-sam 11h30-14h30 ; dim fermé »."""
    for en, fr in (("Mo", "lun"), ("Tu", "mar"), ("We", "mer"), ("Th", "jeu"), ("Fr", "ven"), ("Sa", "sam"),
                   ("Su", "dim"), ("PH", "fériés"), ("off", "fermé"), ("closed", "fermé"), ("24/7", "24 h/24")):
        h = re.sub(r"\b" + re.escape(en) + r"\b", fr, h)
    h = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{int(m.group(1))}h{m.group(2) if m.group(2) != '00' else ''}", h)
    return h.replace(";", " ;").replace(",", ", ")


def dist_txt(m):
    return f"{int(round(m / 10.0) * 10)} m" if m < 1000 else f"{m / 1000:.1f} km".replace(".", ",")


def minutes_a_pied(m):
    return max(1, round(m / 75))                 # 4,5 km/h


# ================================================================ carte (tuiles OpenStreetMap)
def deg2tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def tile2deg(x, y, z):
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def make_window(comp):
    from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, QUrl, pyqtSignal
    from PyQt6.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPainterPath, QPen
    from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter,
                                 QVBoxLayout, QWidget)

    class Sig(QObject):
        tile = pyqtSignal(int, int, int, object)

    class MapView(QWidget):
        """Carte OpenStreetMap : glisser pour bouger, molette pour zoomer, clic sur un point."""

        def __init__(self, win):
            super().__init__()
            self.win = win
            self.setMinimumSize(420, 380)
            self.z = 16
            self.clat, self.clon = 48.8566, 2.3522
            self.me = None
            self.places = []
            self.sel = -1
            self.tiles = {}
            self.pending = set()
            self.sig = Sig()
            self.sig.tile.connect(self._got_tile)
            self.pool = ThreadPoolExecutor(4)
            self.drag = None
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        # ---------- coordonnées
        def _px(self, lat, lon):
            cx, cy = deg2tile(self.clat, self.clon, self.z)
            x, y = deg2tile(lat, lon, self.z)
            return QPointF(self.width() / 2 + (x - cx) * 256, self.height() / 2 + (y - cy) * 256)

        def fit(self):
            pts = [(p["lat"], p["lon"]) for p in self.places[:15]] + ([self.me] if self.me else [])
            if not pts:
                return
            la = [p[0] for p in pts]
            lo = [p[1] for p in pts]
            self.clat, self.clon = (min(la) + max(la)) / 2, (min(lo) + max(lo)) / 2
            for z in range(18, 11, -1):
                x0, y0 = deg2tile(max(la), min(lo), z)
                x1, y1 = deg2tile(min(la), max(lo), z)
                if (x1 - x0) * 256 < max(200, self.width() - 80) and (y1 - y0) * 256 < max(200, self.height() - 80):
                    self.z = z
                    break
            self.update()

        def center_on(self, lat, lon):
            self.clat, self.clon = lat, lon
            self.update()

        # ---------- tuiles
        def _tile(self, z, x, y):
            n = 2 ** z
            if y < 0 or y >= n:
                return None
            x %= n
            k = (z, x, y)
            im = self.tiles.get(k)
            if im is not None:
                return im
            f = CACHE / str(z) / str(x) / f"{y}.png"
            if f.exists():
                im = QImage(str(f))
                if not im.isNull():
                    self.tiles[k] = im
                    return im
            if k not in self.pending and len(self.pending) < 64:
                self.pending.add(k)

                def load(k=k, f=f):
                    try:
                        b = _get(TILES.format(z=k[0], x=k[1], y=k[2]), timeout=15)
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(b)
                    except Exception:
                        b = None
                    try:
                        self.sig.tile.emit(k[0], k[1], k[2], b)
                    except RuntimeError:
                        pass
                self.pool.submit(load)
            return None

        def _got_tile(self, z, x, y, b):
            self.pending.discard((z, x, y))
            if b:
                im = QImage()
                im.loadFromData(b)
                if not im.isNull():
                    self.tiles[(z, x, y)] = im
                    if len(self.tiles) > 600:
                        for k in list(self.tiles)[:200]:
                            self.tiles.pop(k, None)
            self.update()

        # ---------- dessin
        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.fillRect(self.rect(), QColor("#e8e4dc"))
            cx, cy = deg2tile(self.clat, self.clon, self.z)
            w, h = self.width(), self.height()
            x0, y0 = int(math.floor(cx - w / 512)) - 1, int(math.floor(cy - h / 512)) - 1
            for tx in range(x0, x0 + int(w / 256) + 3):
                for ty in range(y0, y0 + int(h / 256) + 3):
                    im = self._tile(self.z, tx, ty)
                    if im is not None:
                        p.drawImage(QPointF(w / 2 + (tx - cx) * 256, h / 2 + (ty - cy) * 256), im)
            if self.me:
                c = self._px(*self.me)
                p.setPen(QPen(QColor("white"), 3))
                p.setBrush(QColor("#2f7bff"))
                p.drawEllipse(c, 9, 9)
            f = QFont()
            f.setBold(True)
            f.setPixelSize(12)
            p.setFont(f)
            order = [i for i in range(len(self.places)) if i != self.sel] + ([self.sel] if self.sel >= 0 else [])
            for i in order:
                pl = self.places[i]
                c = self._px(pl["lat"], pl["lon"])
                sel = i == self.sel
                r = 15 if sel else 12
                path = QPainterPath()                      # épingle
                path.addEllipse(QPointF(c.x(), c.y() - r - 6), r, r)
                path.moveTo(c.x() - r * 0.55, c.y() - r - 1)
                path.lineTo(c.x(), c.y())
                path.lineTo(c.x() + r * 0.55, c.y() - r - 1)
                p.setPen(QPen(QColor("white"), 2))
                p.setBrush(QColor("#d0457a" if sel else "#7b5fff"))
                p.drawPath(path)
                p.setPen(QColor("white"))
                p.drawText(QRectF(c.x() - r, c.y() - 2 * r - 6, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter,
                           str(i + 1))
                if sel:
                    t = pl["nom"]
                    tw = p.fontMetrics().horizontalAdvance(t) + 14
                    box = QRectF(c.x() - tw / 2, c.y() - 2 * r - 34, tw, 22)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(255, 255, 255, 235))
                    p.drawRoundedRect(box, 8, 8)
                    p.setPen(QColor("#3d2733"))
                    p.drawText(box, Qt.AlignmentFlag.AlignCenter, t)
            # attribution (obligatoire)
            t = "© les contributeurs d'OpenStreetMap"
            f.setBold(False)
            f.setPixelSize(10)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(t) + 10
            p.fillRect(QRectF(w - tw, h - 16, tw, 16), QColor(255, 255, 255, 200))
            p.setPen(QColor("#333"))
            p.drawText(QRectF(w - tw, h - 16, tw, 16), Qt.AlignmentFlag.AlignCenter, t)
            p.end()

        # ---------- souris
        def _hit(self, pos):
            best, bd = -1, 22.0
            for i, pl in enumerate(self.places):
                c = self._px(pl["lat"], pl["lon"])
                d = math.hypot(pos.x() - c.x(), pos.y() - (c.y() - 18))
                if d < bd:
                    best, bd = i, d
            return best

        def mousePressEvent(self, e):
            i = self._hit(e.position())
            if i >= 0:
                self.win.select(i)
                return
            self.drag = (e.position(), self.clat, self.clon)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        def mouseMoveEvent(self, e):
            if self.drag:
                p0, la, lo = self.drag
                cx, cy = deg2tile(la, lo, self.z)
                d = e.position() - p0
                self.clat, self.clon = tile2deg(cx - d.x() / 256, cy - d.y() / 256, self.z)
                self.update()
            else:
                self.setCursor(Qt.CursorShape.PointingHandCursor if self._hit(e.position()) >= 0
                               else Qt.CursorShape.OpenHandCursor)

        def mouseReleaseEvent(self, e):
            self.drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        def wheelEvent(self, e):
            nz = max(3, min(19, self.z + (1 if e.angleDelta().y() > 0 else -1)))
            if nz != self.z:
                # zoom vers la souris
                pos = e.position()
                cx, cy = deg2tile(self.clat, self.clon, self.z)
                mx = cx + (pos.x() - self.width() / 2) / 256
                my = cy + (pos.y() - self.height() / 2) / 256
                mlat, mlon = tile2deg(mx, my, self.z)
                self.z = nz
                nx, ny = deg2tile(mlat, mlon, nz)
                self.clat, self.clon = tile2deg(nx - (pos.x() - self.width() / 2) / 256,
                                                ny - (pos.y() - self.height() / 2) / 256, nz)
                self.update()

    class Win(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.c = comp
            self.places = []
            self.setWindowTitle("📍 Autour de moi")
            self.resize(1050, 640)
            root = QVBoxLayout(self)
            top = QHBoxLayout()
            self.title = QLabel("📍 Autour de moi")
            self.title.setStyleSheet("font-size: 13pt; font-weight: bold;")
            top.addWidget(self.title, 1)
            self.b_where = QPushButton("📌 Changer de position…")
            self.b_where.clicked.connect(lambda: self.c.ask_position(then=self.c.last_nearby_again))
            top.addWidget(self.b_where)
            root.addLayout(top)
            self.sub = QLabel("")
            self.sub.setWordWrap(True)
            root.addWidget(self.sub)
            sp = QSplitter()
            left = QWidget()
            lv = QVBoxLayout(left)
            lv.setContentsMargins(0, 0, 0, 0)
            self.lst = QListWidget()
            self.lst.currentRowChanged.connect(lambda r: self.select(r, from_list=True))
            lv.addWidget(self.lst, 1)
            self.info = QLabel("")
            self.info.setWordWrap(True)
            self.info.setTextFormat(Qt.TextFormat.RichText)
            self.info.setMinimumHeight(90)
            lv.addWidget(self.info)
            row = QHBoxLayout()
            self.b_site = QPushButton("🌐 Son site")
            self.b_site.clicked.connect(self.open_site)
            self.b_route = QPushButton("🚶 Y aller")
            self.b_route.clicked.connect(self.open_route)
            self.b_osm = QPushButton("🗺️ Plus d'infos")
            self.b_osm.clicked.connect(self.open_osm)
            for b in (self.b_site, self.b_route, self.b_osm):
                b.setEnabled(False)
                row.addWidget(b)
            lv.addLayout(row)
            sp.addWidget(left)
            self.map = MapView(self)
            sp.addWidget(self.map)
            sp.setSizes([380, 670])
            root.addWidget(sp, 1)

        def show_results(self, me, label, places, kind, cuisine, rad):
            ico, lab = KINDS[kind][1], KINDS[kind][2]
            what = (CUISINE_FR.get(cuisine, cuisine) + " — " if cuisine else "") + lab
            self.places = places
            self.title.setText(f"{ico} {what[0].upper() + what[1:]} autour de {label}")
            self.sub.setText(f"{len(places)} trouvé{'s' if len(places) > 1 else ''} à moins de {dist_txt(rad)}. "
                             "Clique sur un lieu (dans la liste ou sur la carte) pour voir son site ou y aller.")
            self.lst.blockSignals(True)
            self.lst.clear()
            for i, pl in enumerate(places):
                det = pl["cuisine"] or pl["type"]
                it = QListWidgetItem(f"{i + 1}. {pl['nom']}\n      {det} · {dist_txt(pl['dist'])} "
                                     f"(~{minutes_a_pied(pl['dist'])} min à pied)" + ("  🌐" if pl["site"] else ""))
                self.lst.addItem(it)
            self.lst.blockSignals(False)
            self.map.me = me
            self.map.places = places
            self.map.sel = -1
            self.map.fit()
            self.info.setText("")
            for b in (self.b_site, self.b_route, self.b_osm):
                b.setEnabled(False)

        def select(self, i, from_list=False):
            if i < 0 or i >= len(self.places):
                return
            pl = self.places[i]
            self.map.sel = i
            if not from_list:
                self.lst.blockSignals(True)
                self.lst.setCurrentRow(i)
                self.lst.blockSignals(False)
            self.map.center_on(pl["lat"], pl["lon"])
            lines = [f"<b>{pl['nom']}</b>", ", ".join(x for x in (pl["cuisine"] or pl["type"], dist_txt(pl["dist"]))
                                                       if x)]
            if pl["adresse"]:
                lines.append("📍 " + pl["adresse"] + (", " + pl["ville"] if pl["ville"] else ""))
            if pl["horaires"]:
                lines.append("🕒 " + horaires_fr(pl["horaires"]))
            if pl["tel"]:
                lines.append("📞 " + pl["tel"])
            extra = [x for x, ok in (("🥗 options vegan", pl["vegan"] in ("yes", "only")),
                                     ("🥡 à emporter", pl["emporter"] in ("yes", "only"))) if ok]
            if extra:
                lines.append(" · ".join(extra))
            self.info.setText("<br>".join(lines))
            self.b_site.setEnabled(True)
            self.b_site.setText("🌐 Son site" if pl["site"] else "🔎 Le chercher sur le web")
            self.b_route.setEnabled(True)
            self.b_osm.setEnabled(True)

        def _cur(self):
            i = self.map.sel
            return self.places[i] if 0 <= i < len(self.places) else None

        def open_site(self):
            pl = self._cur()
            if not pl:
                return
            url = pl["site"]
            if url and not url.startswith("http"):
                url = "https://" + url
            if not url:
                url = "https://duckduckgo.com/?q=" + urllib.parse.quote(f"{pl['nom']} {pl['ville'] or ''} {pl['adresse']}")
            QDesktopServices.openUrl(QUrl(url))

        def open_route(self):
            pl = self._cur()
            if not pl:
                return
            me = self.map.me
            fr = f"{me[0]:.6f}%2C{me[1]:.6f}" if me else ""
            QDesktopServices.openUrl(QUrl("https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot"
                                          f"&route={fr}%3B{pl['lat']:.6f}%2C{pl['lon']:.6f}"))

        def open_osm(self):
            pl = self._cur()
            if pl:
                QDesktopServices.openUrl(QUrl(pl["osm"]))

    _ = (threading, time, QTimer)
    return Win()
