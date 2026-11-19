"""Son apparence : contours propres et personnalisation (cheveux, peau, yeux, haut, jupe, collants, chaussures).

- Contours propres : beaucoup d'images détourées gardent un liseré blanc (les pixels du bord ont encore la couleur
  de l'ancien fond). On efface les miettes presque invisibles et on donne aux pixels du bord la couleur de
  l'intérieur : plus de halo blanc, quel que soit le fond du bureau.
- Personnalisation : une « carte des parties » (parties.png, une valeur par pixel) dit où sont les cheveux, la peau…
  On change la couleur de chaque partie en gardant les ombres, les reflets et les traits (et des motifs pour les
  vêtements). Tout est calculé sur le PC, et mis en cache.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

CACHE_DIR = None             # réglé par compagnon.py

# valeur dans parties.png -> (clé, nom affiché)
PARTS = {1: ("cheveux", "Cheveux"), 2: ("peau", "Peau"), 3: ("yeux", "Yeux"), 4: ("haut", "Haut"),
         5: ("bas", "Bas (jupe, pantalon…)"), 6: ("collants", "Jambes (collants…)"), 7: ("chaussures", "Chaussures"),
         8: ("barrette", "Accessoire")}
KEY2ID = {k: i for i, (k, _n) in PARTS.items()}
PARTS_KEYS = tuple(k for k, _n in PARTS.values())

# couleurs proposées (nom, couleur)
PALETTES = {
    "cheveux": [("Lilas (d'origine)", ""), ("Rose", "#f59ac0"), ("Blond", "#f1d48a"), ("Roux", "#c8552c"),
                ("Châtain", "#7a4f35"), ("Brun", "#3f2a22"), ("Noir", "#22202a"), ("Blanc", "#eeeef4"),
                ("Argent", "#b8bfcc"), ("Bleu", "#6b9cf0"), ("Turquoise", "#45c4c0"), ("Vert", "#6fbf73"),
                ("Rouge", "#c9313d"), ("Violet", "#7d4fc9")],
    "peau": [("D'origine", ""), ("Très claire", "#fde3d6"), ("Claire", "#f6cdb6"), ("Dorée", "#e9b48e"),
             ("Mate", "#c98d63"), ("Brune", "#9b6440"), ("Foncée", "#6b4029"), ("Très foncée", "#4a2b1c")],
    "yeux": [("Ambre (d'origine)", ""), ("Bleu", "#3f86e0"), ("Vert", "#3da35a"), ("Marron", "#7b4a26"),
             ("Noisette", "#a87632"), ("Gris", "#8a95a3"), ("Violet", "#9056d0"), ("Rouge", "#d23a3a"),
             ("Rose", "#e66aa6"), ("Turquoise", "#2fb8b8")],
    "haut": [("Crème (d'origine)", ""), ("Blanc", "#f5f5f5"), ("Gris", "#9a9ca3"), ("Noir", "#2a2a30"),
             ("Rouge", "#c6343f"), ("Bordeaux", "#7a1f33"), ("Rose", "#f2a3c2"), ("Orange", "#ec8a3c"),
             ("Jaune", "#f2d35b"), ("Vert", "#5aa86a"), ("Sapin", "#2f5d45"), ("Bleu ciel", "#8fc3ef"),
             ("Bleu marine", "#2b3a6b"), ("Lavande", "#b7a6e6"), ("Marron", "#7b5236")],
    "bas": [("Bleu marine (d'origine)", ""), ("Noir", "#24232a"), ("Gris", "#77787f"), ("Rouge", "#b12d38"),
            ("Bordeaux", "#6c1e2c"), ("Vert", "#2f6b4c"), ("Beige", "#cdb592"), ("Blanc", "#eeeeee"),
            ("Rose", "#e891b5"), ("Violet", "#5d3f8f"), ("Jean", "#4a6fa0")],
    "collants": [("Noirs (d'origine)", ""), ("Jambes nues", "peau"), ("Gris", "#6b6b72"), ("Blancs", "#ececf0"),
                 ("Beiges", "#d7b9a0"), ("Bordeaux", "#5f1a28"), ("Bleu nuit", "#1f2747"), ("Roses", "#e6a2bd"),
                 ("Violets", "#4b3570")],
    "chaussures": [("Marron (d'origine)", ""), ("Noires", "#25232a"), ("Blanches", "#eeeeee"), ("Rouges", "#b8303a"),
                   ("Beiges", "#cfb48f"), ("Roses", "#e79ab9"), ("Bleues", "#3d5f9c"), ("Vertes", "#3e7a52")],
    "barrette": [("Dorée (d'origine)", ""), ("Argent", "#c9ccd6"), ("Rose", "#f17aa8"), ("Bleue", "#4f8fe8"),
                 ("Rouge", "#d83a3a"), ("Verte", "#4fb06a"), ("Noire", "#222226")],
}
MOTIFS = [("Uni", ""), ("Rayures", "rayures"), ("Rayures fines", "fines"), ("Carreaux", "carreaux"),
          ("Pois", "pois"), ("Losanges", "losanges")]
MOTIF_PARTS = ("haut", "bas", "collants")

# looks tout prêts (on peut en enregistrer d'autres)
LOOKS = {
    "D'origine": {},
    "Hiver cosy": {"haut": "#7a1f33", "bas": "#24232a", "collants": "", "chaussures": "#25232a"},
    "Noël": {"haut": "#c6343f", "bas": "#f5f5f5", "motif_bas": "carreaux", "bas2": "#2f5d45", "collants": "#ececf0",
             "barrette": "#4fb06a"},
    "Été": {"haut": "#f5f5f5", "bas": "#8fc3ef", "collants": "peau", "chaussures": "#eeeeee"},
    "Gothique": {"cheveux": "#22202a", "haut": "#2a2a30", "bas": "#6c1e2c", "motif_bas": "carreaux",
                 "bas2": "#24232a", "yeux": "#d23a3a", "chaussures": "#25232a"},
    "Marinière": {"haut": "#f5f5f5", "motif_haut": "rayures", "haut2": "#2b3a6b", "bas": "#2b3a6b"},
    "Sakura": {"cheveux": "#f59ac0", "haut": "#f5f5f5", "bas": "#e891b5", "yeux": "#3f86e0", "barrette": "#f17aa8"},
    "Rousse automne": {"cheveux": "#c8552c", "yeux": "#3da35a", "haut": "#ec8a3c", "bas": "#7b5236",
                       "collants": "#5f1a28"},
}


# ================================================================ conversions
def qimage_to_array(qimg):
    """QImage -> tableau h×w×4 (R, G, B, A) en uint8 (copie)."""
    from PyQt6.QtGui import QImage
    im = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = im.width(), im.height()
    buf = im.constBits().asstring(im.sizeInBytes())
    return np.frombuffer(buf, np.uint8).reshape(h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4).copy()


def array_to_qimage(arr):
    from PyQt6.QtGui import QImage
    arr = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _box(a, r):
    """Flou boîte (2 passes), pour des masques doux."""
    if r < 1:
        return a
    for _ in range(2):
        for ax in (0, 1):
            pad = [(r + 1, r) if i == ax else (0, 0) for i in range(a.ndim)]
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax)
            if ax == 0:
                a = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
            else:
                a = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return a


# ================================================================ contours propres
def defringe(arr, cut=0.10):
    """Enlève le liseré blanc : miettes presque transparentes effacées, bord recoloré avec l'intérieur."""
    a = arr[..., 3].astype(np.float32) / 255.0
    rgb = arr[..., :3].astype(np.float32)
    a = np.where(a < cut, 0.0, a)
    a = np.clip((a - cut) / (1.0 - cut), 0.0, 1.0) * (a > 0)
    # miettes isolées : un pixel presque seul dans son voisinage
    dens = _box((a > 0.02).astype(np.float32), 2)
    a = np.where((dens < 0.22) & (a < 0.9), 0.0, a)
    solid = (a > 0.97).astype(np.float32)
    # couleur de l'intérieur, diffusée vers le bord (moyennes pondérées de plus en plus larges)
    out = rgb.copy()
    need = (a > 0) & (a <= 0.97)
    fill = np.zeros_like(rgb)
    got = np.zeros(a.shape, bool)
    for r in (1, 2, 4, 8):
        wsum = _box(solid, r)
        col = np.stack([_box(rgb[..., k] * solid, r) for k in range(3)], -1)
        ok = (wsum > 1e-3) & ~got
        fill[ok] = col[ok] / wsum[ok][:, None]
        got |= ok
        if got[need].all():
            break
    m = need & got
    # on garde un peu de la couleur d'origine quand le pixel est presque opaque
    k = np.clip((a[m] - 0.6) / 0.37, 0, 1)[:, None] * 0.5
    out[m] = fill[m] * (1 - k) + rgb[m] * k
    # première rangée opaque : souvent éclaircie par l'ancien fond -> on l'aligne sur l'intérieur si plus claire
    edge = (a > 0.97) & (_box((a < 0.5).astype(np.float32), 1) > 0.05)
    inner = np.stack([_box(rgb[..., k] * solid, 2) for k in range(3)], -1) / np.maximum(_box(solid, 2), 1e-3)[..., None]
    lighter = edge & (rgb.mean(-1) > inner.mean(-1) + 25)
    out[lighter] = inner[lighter] * 0.8 + rgb[lighter] * 0.2
    res = arr.copy()
    res[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    res[..., 3] = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
    res[res[..., 3] == 0, :3] = 0
    return res


# ================================================================ recoloration
def _rgb_to_hls(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    l = (mx + mn) / 2
    d = mx - mn
    s = np.where(d < 1e-6, 0, d / np.maximum(1e-6, 1 - np.abs(2 * l - 1)))
    dd = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    h = np.where(d < 1e-6, 0, h)
    return h % 1.0, l, np.clip(s, 0, 1)


def _hls_to_rgb(h, l, s):
    c = (1 - np.abs(2 * l - 1)) * s
    hp = (h % 1.0) * 6
    x = c * (1 - np.abs(hp % 2 - 1))
    z = np.zeros_like(h)
    conds = [hp < 1, hp < 2, hp < 3, hp < 4, hp < 5, hp >= 5]
    rs = np.select(conds, [c, x, z, z, x, c])
    gs = np.select(conds, [x, c, c, x, z, z])
    bs = np.select(conds, [z, z, x, c, c, x])
    m = l - c / 2
    return np.stack([rs + m, gs + m, bs + m], -1)


def _stats(h, l, s, w):
    """Teinte (moyenne circulaire), clarté et saturation moyennes d'une partie."""
    ws = max(1e-6, float(w.sum()))
    ang = h * 2 * np.pi
    mh = (np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum()) / (2 * np.pi)) % 1.0
    return mh, float((l * w).sum() / ws), float((s * w).sum() / ws)


def _map_light(l, ml, lt):
    """Clarté : la moyenne de la partie va sur la cible, ombres, reflets et traits gardés (lt : nombre ou tableau)."""
    lt = np.asarray(lt, np.float32)
    up = 1 - (1 - l) * (1 - lt) / max(1e-3, 1 - ml)
    line = np.clip((ml * 0.55 - l) / max(1e-3, ml * 0.55), 0, 1)      # traits bien plus sombres que la moyenne
    up = up * (1 - line * 0.85)
    down = l * lt / max(1e-3, ml)
    return np.where(lt >= ml, up, down)


def _pattern(kind, X, Y, scale=1.0):
    """Motif 0..1 (1 = seconde couleur)."""
    s = 1.0 / max(0.2, scale)
    if kind == "rayures":
        return ((Y * s / 14.0) % 2 < 1).astype(np.float32)
    if kind == "fines":
        return ((Y * s / 6.0) % 3 < 1).astype(np.float32)
    if kind == "carreaux":
        a = ((X * s / 18.0) % 2 < 1)
        b = ((Y * s / 18.0) % 2 < 1)
        lines = (((X * s) % 18.0) < 2.2) | (((Y * s) % 18.0) < 2.2)
        return np.clip((a ^ b) * 0.55 + lines * 0.9, 0, 1).astype(np.float32)
    if kind == "pois":
        gx, gy = (X * s) % 20.0 - 10, (Y * s + (np.floor(X * s / 20.0) % 2) * 10) % 20.0 - 10
        return np.clip(4.5 - np.sqrt(gx * gx + gy * gy), 0, 1).astype(np.float32)
    if kind == "losanges":
        u, v = (X * s + Y * s) / 16.0, (X * s - Y * s) / 16.0
        return (((np.floor(u) + np.floor(v)) % 2) == 0).astype(np.float32)
    return np.zeros_like(X, dtype=np.float32)


def recolor(arr, parts, look, skin_fallback="#f6cdb6"):
    """arr : h×w×4 uint8 ; parts : h×w (valeurs 1..8) ; look : {partie: couleur, motif_x, x2}."""
    if not look:
        return arr
    rgb = arr[..., :3].astype(np.float32) / 255.0
    alpha = arr[..., 3].astype(np.float32) / 255.0
    h, l, s = _rgb_to_hls(rgb)
    out = rgb.copy()
    H, W = parts.shape
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    # couleur de peau à utiliser pour « jambes nues »
    skin_col = look.get("peau") or ""
    if not skin_col:
        mskin = (parts == 2) & (alpha > 0.9) & (l > 0.55)
        if mskin.any():
            c = rgb[mskin].mean(0)
            skin_col = "#%02x%02x%02x" % tuple(int(v * 255) for v in c)
        else:
            skin_col = skin_fallback
    for pid, (key, _name) in PARTS.items():
        col = look.get(key) or ""
        if not col:
            continue
        bare = col == "peau"
        if bare:
            col = skin_col
        m = (parts == pid) | ((parts == 9) if pid == 1 else False)
        if not m.any():
            continue
        w = (m & (alpha > 0.5)).astype(np.float32)
        mh, ml, ms = _stats(h, l, s, w)
        th, tl, ts = _rgb_to_hls(np.array([[hex_rgb(col)]], np.float32))
        th, tl, ts = float(th[0, 0]), float(tl[0, 0]), float(ts[0, 0])
        if bare:                                       # jambes nues : un peu plus mat que le visage
            tl, ts = tl * 0.94, ts * 0.8
        motif = look.get("motif_" + key, "") if key in MOTIF_PARTS else ""
        if motif and look.get(key + "2"):
            p = _pattern(motif, X, Y, float(look.get("motif_taille", 1.0) or 1.0))
            h2, l2, s2 = _rgb_to_hls(np.array([[hex_rgb(look[key + "2"])]], np.float32))
            TH = np.where(p > 0.5, float(h2[0, 0]), th)
            TL = tl * (1 - p) + float(l2[0, 0]) * p
            TS = ts * (1 - p) + float(s2[0, 0]) * p
        else:
            TH, TL, TS = th, tl, ts
        # teinte : la cible, avec un peu de la variation d'origine (reflets plus chauds ou plus froids)
        dh = ((h - mh + 0.5) % 1.0) - 0.5
        nh = (TH + dh * 0.25) % 1.0
        # saturation : relative à la moyenne (les zones grises restent grises)
        TSa = np.asarray(TS, np.float32)
        ns = np.clip(s * (TSa / ms), 0, 1) if ms > 0.05 else np.clip(TSa + (s - ms) * 0.5, 0, 1)
        ns = np.where(TSa < 0.04, s * 0.15, ns)
        nl = _map_light(l, ml, TL)
        new = _hls_to_rgb(nh, np.clip(nl, 0, 1), ns)
        soft = np.clip(_box(m.astype(np.float32), 1) * 1.25, 0, 1)[..., None]   # bords des parties adoucis
        out = out * (1 - soft) + new * soft
    res = arr.copy()
    res[..., :3] = np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
    return res


# ================================================================ chargement
def process(img_path, char_dir, look=None, clean=True, char=None, hit_path=None):
    """Image du personnage prête à afficher : coiffure, couleurs, silhouette, contours propres.
    -> (QImage ou None, Geo ou None, QImage du masque de clic ou None). Mis en cache."""
    from PyQt6.QtGui import QImage
    look = {k: v for k, v in (look or {}).items() if v not in ("", None)}
    char = char or {}
    p = Path(img_path)
    k = float(look.get("silhouette", 1.0) or 1.0)
    if not clean and not look:
        return None, None, None
    try:
        st = p.stat()
        pp = Path(char_dir) / "parties.png"
        key = json.dumps([str(p.resolve()), st.st_mtime, st.st_size, clean, look, char.get("eyes"), char.get("mouth"),
                          pp.stat().st_mtime if pp.exists() else 0, 5], sort_keys=True)
    except Exception:
        return None, None, None
    hsh = hashlib.sha1(key.encode()).hexdigest()[:16]
    cache = Path(CACHE_DIR) / f"{hsh}.png" if CACHE_DIR else None
    q = QImage(str(cache)) if cache and cache.exists() else None
    geo = None
    if q is None or q.isNull():
        q = QImage(str(p))
        if q.isNull():
            return None, None, None
        arr = qimage_to_array(q)
        if look:
            parts = None
            if any(look.get(x) for x in PARTS_KEYS) or look.get("coiffure"):
                parts = parts_for(char_dir, arr.shape[1], arr.shape[0], arr, char)
            if parts is not None and look.get("coiffure"):
                arr = hair_cut(arr, parts, char, look["coiffure"])
            if parts is not None:
                arr = recolor(arr, parts, look)
        if look.get("poitrine"):
            arr = bust(arr, char, look["poitrine"])
        if abs(k - 1) > 1e-3 and face_geometry(char):
            geo = Geo(char, arr.shape[1], arr.shape[0], k)
            arr = warp(arr, geo)
        if clean:
            arr = defringe(arr)
        q = array_to_qimage(arr)
        if cache:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                for old in sorted((f for f in cache.parent.glob("*.png") if not f.name.startswith("parties_")),
                                  key=lambda f: f.stat().st_mtime)[:-30]:
                    old.unlink()                              # on garde les 30 derniers looks
                q.save(str(cache))
            except Exception:
                pass
    else:
        src = QImage(str(p))
        if abs(k - 1) > 1e-3 and face_geometry(char) and not src.isNull():
            geo = Geo(char, src.width(), src.height(), k)
    hit = None
    if geo is not None and hit_path and Path(hit_path).exists():
        hq = QImage(str(hit_path))
        if not hq.isNull() and hq.size() == QImage(str(p)).size():
            hit = array_to_qimage(warp(qimage_to_array(hq), geo))
    return q, geo, hit


def look_key(char_dir):
    try:
        return str(Path(char_dir).resolve())
    except Exception:
        return str(char_dir)


# ================================================================ commandes (« cheveux roses », « pull rouge »…)
COULEURS = {
    "rose": "#f59ac0", "roses": "#f59ac0", "rouge": "#c6343f", "rouges": "#c6343f", "bleu": "#4f7fd8",
    "bleus": "#4f7fd8", "bleue": "#4f7fd8", "bleues": "#4f7fd8", "bleu ciel": "#8fc3ef", "bleu marine": "#2b3a6b",
    "vert": "#4fa065", "verts": "#4fa065", "verte": "#4fa065", "vertes": "#4fa065", "jaune": "#f2d35b",
    "jaunes": "#f2d35b", "orange": "#ec8a3c", "violet": "#7d4fc9", "violets": "#7d4fc9", "violette": "#7d4fc9",
    "violettes": "#7d4fc9", "noir": "#24232a", "noirs": "#24232a", "noire": "#24232a", "noires": "#24232a",
    "blanc": "#f2f2f4", "blancs": "#f2f2f4", "blanche": "#f2f2f4", "blanches": "#f2f2f4", "gris": "#8f9198",
    "grise": "#8f9198", "grises": "#8f9198", "marron": "#7b5236", "marrons": "#7b5236", "beige": "#d3bb98",
    "beiges": "#d3bb98", "bordeaux": "#7a1f33", "turquoise": "#3cbfbb", "lilas": "", "doré": "#e2b04a",
    "dorée": "#e2b04a", "argent": "#c0c6d0", "argenté": "#c0c6d0", "argentés": "#c0c6d0",
    "blond": "#f1d48a", "blonds": "#f1d48a", "blonde": "#f1d48a", "roux": "#c8552c", "rousse": "#c8552c",
    "châtain": "#7a4f35", "chatain": "#7a4f35", "châtains": "#7a4f35", "brun": "#3f2a22", "bruns": "#3f2a22",
    "brune": "#3f2a22", "ambre": "", "noisette": "#a87632", "corail": "#f07a6a", "menthe": "#8fdcbc",
    "lavande": "#b7a6e6", "kaki": "#7a7a45", "sapin": "#2f5d45", "framboise": "#c2325f", "pêche": "#f8b998",
}
MOTS_PARTIES = {
    "cheveux": r"cheveux|coiffure|ch[eè]veux", "peau": r"peau|teint", "yeux": r"yeux|oeil|œil|iris",
    "haut": r"pull|haut|t-?shirt|sweat|chemise|veste|gilet|v[eê]tement du haut",
    "bas": r"jupe|bas\b|short", "collants": r"collants?|bas noirs|leggings?", "chaussures": r"chaussures?|bottes?|bottines?|souliers?|baskets?",
    "barrette": r"barrette|pince|accessoire",
}

PEAU_MOTS = {"tres claire": "#fde3d6", "claire": "#f6cdb6", "doree": "#e9b48e", "bronzee": "#d9a07a",
             "mate": "#c98d63", "brune": "#9b6440", "foncee": "#6b4029", "noire": "#4a2b1c", "tres foncee": "#4a2b1c",
             "pale": "#fde3d6"}
MOTIF_MOTS = {"rayures": "rayures", "raye": "rayures", "rayee": "rayures", "rayes": "rayures", "rayees": "rayures",
              "mariniere": "rayures", "carreaux": "carreaux", "ecossais": "carreaux", "ecossaise": "carreaux",
              "a pois": "pois", "pois": "pois", "losanges": "losanges", "uni": "", "unie": ""}
MOTIF_ADJ = {"rayures": "rayé", "fines": "à fines rayures", "carreaux": "à carreaux", "pois": "à pois",
             "losanges": "à losanges"}
NOMS = {"cheveux": "Cheveux", "peau": "Peau", "yeux": "Yeux", "haut": "Pull", "bas": "Jupe", "collants": "Collants",
        "chaussures": "Chaussures", "barrette": "Barrette"}
IMPLICITE = {"blond": "cheveux", "blonde": "cheveux", "blonds": "cheveux", "roux": "cheveux", "rousse": "cheveux",
             "chatain": "cheveux", "brune": "cheveux", "brun": "cheveux"}


def _sans_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


CUE = (r"^\s*(?:des |un |une |le |la |les )?(?:cheveux|pull|haut|jupe|yeux|peau|collants|chaussures|bottes|barrette)\b|"
       r"\b(?:mets|met|mettre|change|changer|deviens|devenir|teins|teindre|porte|porter|habille|essaie|essaye|"
       r"passe|prends|veux|voudrais|aimerais|peux|fais|tes|ta|ton|toi)\b")
NOT_ME = r"\b(?:mon|ma|mes|j'?ai|je porte|moi j)\b"


def is_request(text):
    """La phrase lui demande-t-elle de changer d'apparence ? (« j'ai mis mon pull rouge » : non)"""
    import re
    t = _sans_accents(text)
    return bool(re.search(CUE, t)) and not re.search(NOT_ME, t)


def parse_look(text):
    """« des cheveux roses », « mets un pull rouge et une jupe noire », « un pull rayé bleu et blanc »,
    « peau mate », « deviens blonde » -> ({partie: couleur…}, phrase) ou None."""
    import re
    t = _sans_accents(text)
    cols = {_sans_accents(k): v for k, v in COULEURS.items()}
    parts = []
    for key, rx in MOTS_PARTIES.items():
        for m in re.finditer(r"\b(?:" + _sans_accents(rx) + r")", t):
            parts.append((m.start(), key))
    words = []
    for w in sorted(cols, key=len, reverse=True):
        for m in re.finditer(r"\b" + re.escape(w) + r"\b", t):
            if not any(a <= m.start() < b for a, b, _w in words):
                words.append((m.start(), m.end(), w))
    motifs = []
    for w, k in MOTIF_MOTS.items():
        for m in re.finditer(r"\b" + re.escape(w) + r"\b", t):
            motifs.append((m.start(), k))
    words.sort()
    parts.sort()
    if not parts:
        imp = [IMPLICITE[w] for _s, _e, w in words if w in IMPLICITE]
        if imp and re.search(r"\b(deviens|devenir|sois|teins|teint|change|mets|passe|aimerais|voudrais|veux)\b", t):
            parts = [(words[0][0] - 1, imp[0])]
        else:
            return None
    changes, desc = {}, []
    for i, (pos, key) in enumerate(parts):
        nxt = parts[i + 1][0] if i + 1 < len(parts) else 10 ** 6
        prv = parts[i - 1][0] if i else -1
        after = [w for w in words if pos < w[0] < nxt]
        before = [w for w in words if prv < w[0] < pos] if not after else []
        mine = after or before[-1:]
        mot = [k for p_, k in motifs if prv < p_ < nxt]
        if key == "peau":
            pm = next((v for w, v in PEAU_MOTS.items() if re.search(r"\b" + w + r"\b", t[pos:nxt])), "")
            if pm:
                changes["peau"] = pm
                desc.append(f"Peau {next(w for w in PEAU_MOTS if re.search(chr(92) + 'b' + w, t[pos:nxt]))}")
                continue
        if not mine and not mot:
            continue
        c1 = cols[mine[0][2]] if mine else None
        if mot and key in MOTIF_PARTS:
            m = mot[0]
            if m == "":
                changes["motif_" + key] = ""
                if c1 is not None:
                    changes[key] = c1
                desc.append(f"{NOMS[key]} uni")
                continue
            c2 = cols[mine[1][2]] if len(mine) > 1 else None
            if c1 and c2:
                changes[key], changes[key + "2"] = c1, c2
            elif c1:
                changes[key + "2"] = c1
                changes.setdefault(key, "#f2f2f4" if hex_rgb(c1)[0] + hex_rgb(c1)[1] + hex_rgb(c1)[2] < 2.0 else "#2a2a30")
            else:
                changes[key + "2"] = "#2b3a6b"
                changes.setdefault(key, "#f2f2f4")
            changes["motif_" + key] = m
            desc.append(f"{NOMS[key]} {MOTIF_ADJ.get(m, m)}"
                        + (f" {mine[0][2]}" if mine else "") + (f" et {mine[1][2]}" if len(mine) > 1 else ""))
            continue
        if c1 is None:
            continue
        changes[key] = c1
        if key in MOTIF_PARTS:
            changes.setdefault("motif_" + key, "")
        desc.append(f"{NOMS[key]} {mine[0][2]}" if c1 else f"{NOMS[key]} d'origine")
    if not changes:
        return None
    return changes, (", ".join(desc) + " !") if desc else "C'est fait !"


# ================================================================ fenêtre « Mon apparence »
def make_window(comp):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                                 QPushButton, QScrollArea, QVBoxLayout, QWidget)

    class Win(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.c = comp
            self.setWindowTitle("👗 Mon apparence — " + comp.char.get("name", "Viki"))
            self.resize(980, 700)
            self.setStyleSheet("QPushButton#sw { border: 2px solid #e7cfdb; border-radius: 13px; min-width: 26px; "
                               "max-width: 26px; min-height: 26px; max-height: 26px; }"
                               "QPushButton#sw:checked { border: 3px solid #d0457a; }"
                               "QLabel#t { font-weight: bold; font-size: 11pt; }"
                               "QPushButton#look { padding: 6px 10px; border-radius: 10px; }")
            root = QHBoxLayout(self)
            left = QVBoxLayout()
            self.prev = QLabel()
            self.prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.prev.setMinimumWidth(300)
            self.prev.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3f55, stop:1 #1d2030);"
                                    " border-radius: 14px;")
            left.addWidget(self.prev, 1)
            self.bg = QComboBox()
            for n, v in (("Fond sombre", "sombre"), ("Fond clair", "clair"), ("Fond coloré", "couleur")):
                self.bg.addItem(n, v)
            self.bg.currentIndexChanged.connect(self._bg)
            left.addWidget(self.bg)
            self.clean = QCheckBox("Contours propres (sans liseré blanc)")
            self.clean.setChecked(comp.cfg.get("contours_propres", True))
            self.clean.toggled.connect(self._clean)
            left.addWidget(self.clean)
            root.addLayout(left, 0)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            inner = QWidget()
            self.lay = QVBoxLayout(inner)
            sc.setWidget(inner)
            root.addWidget(sc, 1)
            self.build()

        # ---------------------------------------------------- contenu
        def build(self):
            lay = self.lay
            while lay.count():
                it = lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                elif it.layout() is not None:
                    self._clear(it.layout())
            c = self.c
            self.look = c.look_get()
            if not c.can_customize():
                lab = QLabel("Ce personnage n'est pas encore calibré (je ne connais pas la place de ses yeux et de sa "
                             "bouche) : je ne peux pas deviner où sont ses cheveux et ses vêtements. Calibre-le "
                             "(Réglages → Personnage), puis reviens ici.\n\nTu peux quand même nettoyer ses contours "
                             "(case à gauche).")
                lab.setWordWrap(True)
                lay.addWidget(lab)
                lay.addStretch(1)
                self.refresh_preview()
                return
            t = QLabel("Looks tout prêts")
            t.setObjectName("t")
            lay.addWidget(t)
            g = QGridLayout()
            names = list(LOOKS) + list(c.cfg.get("looks_perso", {}))
            for i, n in enumerate(names):
                b = QPushButton(("⭐ " if n in c.cfg.get("looks_perso", {}) else "") + n)
                b.setObjectName("look")
                lk = LOOKS.get(n, c.cfg.get("looks_perso", {}).get(n, {}))
                b.clicked.connect(lambda _=False, lk=lk, n=n: c.set_look(dict(lk), replace=True,
                                                                         announce=f"Look « {n} » !"))
                g.addWidget(b, i // 4, i % 4)
            lay.addLayout(g)
            row = QHBoxLayout()
            for txt, fn in (("🎲 Au hasard", self._random), ("💾 Enregistrer ce look…", self._save),
                            ("↩️ Tout d'origine", lambda: c.set_look({}, replace=True, announce="Me revoilà comme au début !"))):
                b = QPushButton(txt)
                b.clicked.connect(fn)
                row.addWidget(b)
            if c.cfg.get("looks_perso"):
                b = QPushButton("🗑️ Supprimer un look…")
                b.clicked.connect(self._delete)
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            t = QLabel("Coiffure et silhouette")
            t.setObjectName("t")
            lay.addWidget(t)
            row = QHBoxLayout()
            row.addWidget(QLabel("Cheveux :"))
            for n, v in COIFFURES:
                b = QPushButton(n)
                b.setCheckable(True)
                b.setChecked(self.look.get("coiffure", "") == v)
                b.clicked.connect(lambda _=False, v=v: self._shape("coiffure", v))
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            row = QHBoxLayout()
            row.addWidget(QLabel("Silhouette :"))
            cur = float(self.look.get("silhouette", 1.0) or 1.0)
            for n, v in SILHOUETTES:
                b = QPushButton(n)
                b.setCheckable(True)
                b.setChecked(abs(cur - v) < 0.02)
                b.clicked.connect(lambda _=False, v=v: self._shape("silhouette", "" if v == 1.0 else v))
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            row = QHBoxLayout()
            row.addWidget(QLabel("Poitrine :"))
            curb = float(self.look.get("poitrine", 0) or 0)
            for n, v in POITRINES:
                b = QPushButton(n)
                b.setCheckable(True)
                b.setChecked(abs(curb - v) < 0.02)
                b.clicked.connect(lambda _=False, v=v: self._shape("poitrine", "" if v == 0 else v))
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            if not (Path(c.char_dir) / "parties.png").exists():
                info = QLabel("Pour ce personnage, je devine toute seule où sont ses cheveux, sa peau et ses vêtements "
                              "(d'après ses couleurs) : le résultat peut être imparfait, surtout si les cheveux et un "
                              "vêtement ont la même couleur.")
                info.setWordWrap(True)
                info.setStyleSheet("color: palette(placeholder-text);")
                lay.addWidget(info)
            for key, (_pid, name) in ((k, (i, n)) for i, (k, n) in PARTS.items()):
                t = QLabel(name)
                t.setObjectName("t")
                lay.addWidget(t)
                row = QHBoxLayout()
                row.setSpacing(5)
                cur = self.look.get(key, "")
                for label, col in PALETTES.get(key, []):
                    b = QPushButton()
                    b.setObjectName("sw")
                    b.setCheckable(True)
                    b.setChecked(col == cur)
                    b.setToolTip(label)
                    b.setProperty("sans_theme", True)          # les vraies couleurs, pas celles du thème
                    if col and col != "peau":
                        b.setStyleSheet(f"background: {col};")
                    elif col == "peau":
                        b.setText("🦵")
                    else:
                        b.setText("↩")
                    b.clicked.connect(lambda _=False, k=key, v=col: self._set(k, v))
                    row.addWidget(b)
                b = QPushButton("🎨")
                b.setToolTip("Autre couleur…")
                b.clicked.connect(lambda _=False, k=key: self._pick(k))
                row.addWidget(b)
                row.addStretch(1)
                lay.addLayout(row)
                if key in MOTIF_PARTS:
                    row = QHBoxLayout()
                    cb = QComboBox()
                    for n, v in MOTIFS:
                        cb.addItem(n, v)
                    cb.setCurrentIndex(max(0, cb.findData(self.look.get("motif_" + key, ""))))
                    cb.currentIndexChanged.connect(lambda _i, k=key, cb=cb: self._motif(k, cb.currentData()))
                    row.addWidget(QLabel("Motif :"))
                    row.addWidget(cb)
                    b2 = QPushButton("Couleur du motif…")
                    c2 = self.look.get(key + "2", "")
                    if c2:
                        b2.setProperty("sans_theme", True)
                        b2.setStyleSheet(f"border-left: 14px solid {c2};")
                    b2.clicked.connect(lambda _=False, k=key: self._pick(k + "2"))
                    row.addWidget(b2)
                    row.addStretch(1)
                    lay.addLayout(row)
            tip = QLabel("Astuce : tu peux aussi me le dire — « des cheveux roses », « un pull rayé bleu et blanc », "
                         "« jupe à carreaux rouge et noire », « enlève tes collants », « look gothique », "
                         "« remets ton look d'origine ».")
            tip.setWordWrap(True)
            tip.setStyleSheet("color: palette(placeholder-text);")
            lay.addWidget(tip)
            lay.addStretch(1)
            self.refresh_preview()

        def _clear(self, l):
            while l.count():
                it = l.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                elif it.layout() is not None:
                    self._clear(it.layout())

        # ---------------------------------------------------- actions
        def _set(self, key, val):
            ch = {key: val}
            if key in MOTIF_PARTS and not val:
                ch["motif_" + key] = ""
            self.c.set_look(ch, motion="defile" if key in ("haut", "bas") else "content")
            QTimer.singleShot(50, self.build)

        def _shape(self, key, val):
            self.c.set_look({key: val}, motion="cheveux" if key == "coiffure" else "" if key == "poitrine" else "defile")
            QTimer.singleShot(50, self.build)

        def _pick(self, key):
            base = self.look.get(key) or "#ffffff"
            col = QColorDialog.getColor(QColor(base if base.startswith("#") else "#ffffff"), self, "Choisis une couleur")
            if col.isValid():
                ch = {key: col.name()}
                if key.endswith("2") and not self.look.get("motif_" + key[:-1]):
                    ch["motif_" + key[:-1]] = "rayures"
                self.c.set_look(ch)
                QTimer.singleShot(50, self.build)

        def _motif(self, key, m):
            ch = {"motif_" + key: m}
            if m and not self.look.get(key + "2"):
                ch[key + "2"] = "#2b3a6b" if (self.look.get(key) or "") != "#2b3a6b" else "#f2f2f4"
            if m and not self.look.get(key):
                ch[key] = "#f2f2f4"
            self.c.set_look(ch, motion="defile")
            QTimer.singleShot(50, self.build)

        def _random(self):
            import random
            lk = {}
            for k in ("cheveux", "yeux", "haut", "bas", "collants", "chaussures"):
                opts = [v for _n, v in PALETTES[k]]
                lk[k] = random.choice(opts)
            lk["coiffure"] = random.choice(["", "", "milongs", "epaules"])
            if random.random() < 0.35:
                k = random.choice(MOTIF_PARTS[:2])
                lk["motif_" + k] = random.choice([v for _n, v in MOTIFS if v])
                lk[k + "2"] = random.choice([v for _n, v in PALETTES["haut"] if v])
            self.c.set_look(lk, replace=True, announce="Surprise ! Alors, ce nouveau look ?")
            QTimer.singleShot(50, self.build)

        def _save(self):
            n, ok = QInputDialog.getText(self, "Enregistrer ce look", "Nom du look :")
            n = (n or "").strip()[:30]
            if ok and n:
                self.c.cfg.setdefault("looks_perso", {})[n] = self.c.look_get()
                self.c.cfg["looks_perso"] = dict(self.c.cfg["looks_perso"])
                self._save_cfg()
                self.c.say(f"Look « {n} » enregistré ! Dis « look {n} » pour le remettre.")
                self.build()

        def _delete(self):
            names = list(self.c.cfg.get("looks_perso", {}))
            n, ok = QInputDialog.getItem(self, "Supprimer un look", "Lequel ?", names, 0, False)
            if ok and n:
                self.c.cfg["looks_perso"].pop(n, None)
                self._save_cfg()
                self.build()

        def _save_cfg(self):
            import sys
            sys.modules[type(self.c).__module__].save_config(self.c.cfg)

        def _clean(self, v):
            self.c.cfg["contours_propres"] = bool(v)
            self._save_cfg()
            self.c.set_look({}, motion="")

        def reload_char(self):
            """Le personnage a changé : nouveau titre, nouvelles parties, nouvel aperçu."""
            self.setWindowTitle("👗 Mon apparence — " + self.c.char.get("name", "Viki"))
            self.clean.blockSignals(True)
            self.clean.setChecked(self.c.cfg.get("contours_propres", True))
            self.clean.blockSignals(False)
            self.prev.clear()
            self.build()
            self.refresh_preview()

        def _bg(self, _i=0):
            v = self.bg.currentData()
            css = {"sombre": "qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3f55, stop:1 #1d2030)",
                   "clair": "qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #e9eef5)",
                   "couleur": "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ff9ec0, stop:1 #7fb8ff)"}[v]
            self.prev.setStyleSheet(f"background: {css}; border-radius: 14px;")

        def refresh_preview(self):
            pm = self.c.src
            if pm is None or pm.isNull():
                return
            h = max(200, self.prev.height() - 20)
            self.prev.setPixmap(pm.scaledToHeight(min(h, 640), Qt.TransformationMode.SmoothTransformation))

        def resizeEvent(self, e):
            super().resizeEvent(e)
            QTimer.singleShot(0, self.refresh_preview)

    _ = QPixmap
    return Win()


# ================================================================ pour n'importe quelle image
def _lab(rgb_u8):
    """RGB uint8 -> Lab (float, L 0..100)."""
    c = rgb_u8.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = c @ M.T / np.array([0.9505, 1.0, 1.089], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _components(mask):
    """Composantes connexes (8-voisins) -> (étiquettes, nombre). cv2 si présent, sinon scipy, sinon rien."""
    try:
        import cv2
        n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
        return lab, n
    except Exception:
        pass
    try:
        from scipy import ndimage
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        return lab, n + 1
    except Exception:
        return mask.astype(np.int32), 2


def _kmeans(x, k, iters=12, seed=1):
    rng = np.random.default_rng(seed)
    c = x[rng.choice(len(x), size=min(k, len(x)), replace=False)].copy()
    for _ in range(iters):
        d = ((x[:, None, :] - c[None, :, :]) ** 2).sum(-1)
        a = d.argmin(1)
        for j in range(len(c)):
            if (a == j).any():
                c[j] = x[a == j].mean(0)
    return c


def face_geometry(char):
    e = char.get("eyes") or []
    m = char.get("mouth") or {}
    if len(e) < 2 or "y" not in m:
        return None
    ex, ey = (e[0]["x"] + e[1]["x"]) / 2, (e[0]["y"] + e[1]["y"]) / 2
    d = max(8.0, ((e[1]["x"] - e[0]["x"]) ** 2 + (e[1]["y"] - e[0]["y"]) ** 2) ** 0.5)
    u = max(d * 0.45, float(m["y"]) - ey)              # yeux -> bouche
    return {"cx": ex, "ey": ey, "d": d, "u": u, "my": float(m["y"]), "chin": float(m["y"]) + 0.9 * u}


def auto_parts(arr, char):
    """Carte des parties devinée pour n'importe quel personnage (calibré : yeux et bouche connus).
    Cheveux = couleur prise au-dessus des yeux et reliée à la tête ; peau = couleur du visage ; vêtements =
    groupes de couleurs rangés de haut en bas (haut, bas, jambes, chaussures)."""
    g = face_geometry(char)
    H, W = arr.shape[:2]
    P = np.zeros((H, W), np.uint8)
    if g is None:
        return P
    al = arr[..., 3] > 128
    lab = _lab(arr[..., :3])
    cx, ey, d, u = g["cx"], g["ey"], g["d"], g["u"]
    Y, X = np.mgrid[0:H, 0:W]

    def sample(points):
        out = []
        for dx, dy in points:
            x, y = int(cx + dx * d), int(ey + dy * d)
            if 0 <= x < W and 0 <= y < H and al[y, x]:
                out.append(lab[y, x])
        return np.array(out) if out else None
    sk = char.get("skin_sample")
    skin = lab[int(sk["y"]), int(sk["x"])][None] if sk and 0 <= sk["y"] < H and 0 <= sk["x"] < W else \
        sample([(0, 0.55), (-0.3, 0.5), (0.3, 0.5), (0, 0.35)])
    if skin is None:
        return P
    skin_c = np.median(skin, 0)
    hs = sample([(0, -1.35), (-0.6, -1.2), (0.6, -1.2), (-1.0, -0.9), (1.0, -0.9), (0, -1.6), (-1.4, -0.4),
                 (1.4, -0.4), (-0.3, -1.5), (0.3, -1.5)])
    if hs is not None:
        hs = hs[(np.linalg.norm(hs - skin_c, axis=1) > 14) & (hs[:, 0] < 90)] if len(hs) > 2 else hs
        if len(hs) > 2:                                   # on écarte les reflets et les échantillons à part
            med = np.median(hs, 0)
            hs = hs[np.linalg.norm(hs - med, axis=1) < 25] if (np.linalg.norm(hs - med, axis=1) < 25).sum() >= 2 else hs
    # --- peau
    dskin = np.linalg.norm(lab - skin_c, axis=-1)
    skin_m = al & (dskin < 16)
    comp, n = _components(skin_m)
    face_zone = (np.abs(X - cx) < 1.6 * d) & (Y > ey - 1.2 * d) & (Y < g["chin"] + 0.5 * u)
    total = max(1, int(al.sum()))
    keep = np.zeros(n, bool)
    for i in range(1, n):
        cm = comp == i
        area = int(cm.sum())
        if area < 30:
            continue
        if (cm & face_zone).any() or area < total * 0.05:
            keep[i] = True
    skin_m = keep[comp] & skin_m
    # peau dans l'ombre (cou, décolleté) : un peu plus loin de la couleur du visage, mais collée à la peau
    dsk2 = np.linalg.norm((lab - skin_c) * np.array([0.5, 1.0, 1.0], np.float32), axis=-1)
    near = al & (dsk2 < 14) & (Y < g["chin"] + 3 * u) & (np.abs(X - cx) < 2.4 * d)
    comp, n = _components(near | skin_m)
    ids = np.unique(comp[skin_m])
    skin_m |= np.isin(comp, ids[ids > 0]) & near
    # --- cheveux : proches d'un des échantillons, reliés à la tête
    hair_m = np.zeros_like(al)
    unsure = False
    if hs is not None and len(hs):
        dh = np.min(np.stack([np.linalg.norm(lab - h, axis=-1) for h in hs]), 0)
        cand = al & (dh < 15) & ~skin_m & (Y < g["my"] + 11 * u)
        # même couleur que le haut (cheveux noirs, pull noir…) ? sous le menton, les cheveux ne peuvent que
        # descendre : on les suit ligne par ligne au lieu de remplir tout le vêtement
        torso = (np.abs(X - cx) < 0.7 * d) & (Y > g["chin"] + 2 * u) & (Y < g["chin"] + 5 * u) & al
        conflict = torso.sum() > 50 and (cand & torso).sum() > 0.45 * torso.sum()
        if conflict:
            y0 = int(min(H - 1, g["chin"] + 0.6 * u))
            comp, n = _components(cand & (Y < y0))
            head_zone = (Y < ey + 0.2 * d) & (np.abs(X - cx) < 2.2 * d)
            ids = np.unique(comp[cand & head_zone & (Y < y0)])
            hair_m = np.isin(comp, ids[ids > 0]) & cand & (Y < y0)
            unsure = True
            for y in range(y0, H):
                prev = hair_m[y - 1]
                sup = prev.copy() if y % 4 else (prev | np.roll(prev, 1) | np.roll(prev, -1))
                row = cand[y] & sup
                if not row.any():
                    break
                hair_m[y] = row
        else:
            comp, n = _components(cand)
            head_zone = (Y < ey + 0.2 * d) & (np.abs(X - cx) < 2.2 * d)
            ids = np.unique(comp[cand & head_zone])
            hair_m = np.isin(comp, ids[ids > 0]) & cand
            unsure = False
    # --- yeux
    eyes_m = np.zeros_like(al)
    for e in char.get("eyes", []):
        ell = ((X - e["x"]) / (e["w"] * 0.62)) ** 2 + ((Y - e["y"]) / (e["h"] * 0.95)) ** 2 < 1
        eyes_m |= ell & al & (lab[..., 0] < 82) & ~skin_m
    # --- vêtements : on descend le long du corps et on coupe là où la couleur change (haut, bas, jambes,
    # chaussures), puis chaque pixel va au vêtement de couleur la plus proche à cette hauteur
    rest = al & ~skin_m & ~hair_m & ~eyes_m & (Y > g["chin"] - 0.2 * u)
    bottom = int(np.where(al.any(1))[0].max()) if al.any() else H
    span = max(1.0, bottom - g["chin"])
    strip = rest & (np.abs(X - cx) < 1.3 * d)
    def dc(a, b):                                      # écart de couleur, l'ombre (clarté) compte moitié
        w = np.array([0.5, 1.0, 1.0], np.float32)
        return float(np.linalg.norm((np.asarray(a) - np.asarray(b)) * w))
    rows = []
    y_start = int(max(0, g["chin"]))
    for y in range(y_start, bottom + 1):
        px = lab[y][strip[y]]
        rows.append((y, np.median(px, 0) if len(px) >= 3 else None))
    segs, cur, n_bad, gap = [], None, 0, 0
    for y, med in rows:
        if med is None:
            gap += 1
            if cur and gap > max(6, u * 0.4):
                segs.append(cur)
                cur = None
            continue
        gap = 0
        if cur is None:
            cur = {"y0": y, "y1": y, "rows": [med]}
            continue
        ref = np.median(np.array(cur["rows"][-80:]), 0)
        if dc(med, ref) > 10:
            n_bad += 1
            if n_bad >= 4:
                segs.append(cur)
                cur = {"y0": y - 3, "y1": y, "rows": [med]}
                n_bad = 0
            continue
        n_bad = 0
        cur["y1"] = y
        cur["rows"].append(med)
    if cur:
        segs.append(cur)
    for sg in segs:
        sg["c"] = np.median(np.array(sg["rows"]), 0)
    # bandes trop fines enlevées, morceaux voisins de même couleur regroupés, col rattaché au haut
    segs = [sg for sg in segs if sg["y1"] - sg["y0"] >= max(4, u * 0.5)]
    merged = []
    for sg in segs:
        if merged and dc(sg["c"], merged[-1]["c"]) < 8:
            m = merged[-1]
            m["y1"] = sg["y1"]
            m["rows"] += sg["rows"]
            m["c"] = np.median(np.array(m["rows"]), 0)
        else:
            merged.append(sg)
    segs = merged
    if len(segs) > 1 and segs[0]["y1"] < g["chin"] + 2 * u:
        segs[1]["y0"] = segs[0]["y0"]
        segs = segs[1:]
    if segs:
        for i, sg in enumerate(segs):
            rel0 = (sg["y0"] - g["chin"]) / span
            relc = ((sg["y0"] + sg["y1"]) / 2 - g["chin"]) / span
            if i == 0:
                sg["part"] = 4
            elif rel0 > 0.8:
                sg["part"] = 7
            elif i == 1 or relc < 0.45:
                sg["part"] = 5
            else:
                sg["part"] = 6
        # deux segments de suite pour la même partie et presque la même couleur : on garde le premier
        ys = np.arange(H)
        best = np.full((H, W), 1e9, np.float32)
        lab_rest = lab
        for sg in segs:
            m = max(2.0 * u, 12)
            yr = (ys >= sg["y0"] - m) & (ys <= sg["y1"] + m)
            dist = np.linalg.norm((lab_rest - sg["c"]) * np.array([0.5, 1.0, 1.0], np.float32), axis=-1)
            # loin de sa hauteur : pénalité
            far = np.where(yr, 0.0, np.minimum(np.abs(ys - sg["y0"]), np.abs(ys - sg["y1"])) / max(1.0, u) * 6)
            dist = dist + far[:, None]
            take = rest & (dist < best)
            P[take] = sg["part"]
            best[take] = dist[take]
    P[skin_m] = 2
    P[hair_m] = 1
    if unsure:            # cheveux de la même couleur qu'un vêtement : sous le menton, « peut-être des cheveux » (9)
        P[hair_m & (Y >= g["chin"] + 0.6 * u)] = 9
    P[eyes_m] = 3
    # trous : on prend la partie voisine la plus proche
    _fill_nearest(P, al)
    return P


def _fill_nearest(P, inside, steps=40):
    """Pixels sans partie (dans la silhouette) : on prend la partie d'un voisin, de proche en proche."""
    for _ in range(steps):
        un = inside & (P == 0)
        if not un.any():
            return
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.roll(np.roll(P, dy, 0), dx, 1)
            take = un & (nb > 0) & (P == 0)
            P[take] = nb[take]


def _read_gray(path, w=None, h=None):
    """PNG en niveaux de gris -> tableau (avec Qt : pas besoin de Pillow)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    q = QImage(str(path))
    if q.isNull():
        return None
    if w and h and (q.width(), q.height()) != (w, h):
        q = q.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    q = q.convertToFormat(QImage.Format.Format_Grayscale8)
    buf = q.constBits().asstring(q.sizeInBytes())
    return np.frombuffer(buf, np.uint8).reshape(q.height(), q.bytesPerLine())[:, :q.width()].copy()


def _write_gray(arr, path):
    from PyQt6.QtGui import QImage
    a = np.ascontiguousarray(arr.astype(np.uint8))
    QImage(a.data, a.shape[1], a.shape[0], a.shape[1], QImage.Format.Format_Grayscale8).copy().save(str(path))


def parts_for(char_dir, w, h, arr=None, char=None):
    """Carte des parties : parties.png du personnage, sinon devinée automatiquement (mise en cache)."""
    p = Path(char_dir) / "parties.png"
    if p.exists():
        return _read_gray(p, w, h)
    if arr is None or char is None:
        return None
    key = hashlib.sha1(json.dumps([str(char_dir), arr.shape, int(arr[..., 3].sum() % 1000003),
                                   char.get("eyes"), char.get("mouth"), 2]).encode()).hexdigest()[:16]
    cache = Path(CACHE_DIR) / f"parties_{key}.png" if CACHE_DIR else None
    if cache and cache.exists():
        r = _read_gray(cache, w, h)
        if r is not None:
            return r
    P = auto_parts(arr, char)
    if cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            _write_gray(P, cache)
        except Exception:
            pass
    return P


def has_parts(char_dir, char=None):
    return (Path(char_dir) / "parties.png").exists() or bool(char and face_geometry(char))


# ================================================================ coiffure (longueur)
COIFFURES = [("Longs (d'origine)", ""), ("Mi-longs", "milongs"), ("Aux épaules", "epaules")]


def hair_cut(arr, parts, char, style):
    """Raccourcit les cheveux : ce qui dépasse dans le vide disparaît, ce qui tombe devant le corps est remplacé
    par le vêtement d'en dessous (reconstitué)."""
    g = face_geometry(char)
    if not style or g is None:
        return arr
    H, W = parts.shape
    base = g["ey"] + g["u"] * {"milongs": 5.4, "epaules": 4.2}.get(style, 5.4)
    rgbf = arr[..., :3].astype(np.float32) / 255
    mx, mn = rgbf.max(-1), rgbf.min(-1)
    hair = parts == 1
    # pixels de la couleur des cheveux restés dans d'autres parties (bords, mèches fines)
    hl = _lab(arr[..., :3])
    if hair.any():
        hc = np.median(hl[hair & (arr[..., 3] > 200)], 0) if (hair & (arr[..., 3] > 200)).any() else None
        if hc is not None:
            hair |= (np.linalg.norm(hl - hc, axis=-1) < 14) & np.isin(parts, (0, 4)) & ((mx - mn) > 0.05)
    body = (parts >= 2) & (parts != 3) & (parts != 8) & (arr[..., 3] > 200) & ~hair
    X = np.arange(W)
    amp = g["u"] * 0.18
    cy = base + amp * np.sin(X / (g["d"] * 0.16)) + amp * 0.6 * np.sin(X / (g["d"] * 0.063) + 1)
    Y = np.arange(H)[:, None]
    below = Y > cy[None, :]
    lo, hi = np.full(H, W), np.full(H, -1)
    for y in range(H):
        xs = np.where(body[y])[0]
        if len(xs):
            lo[y], hi[y] = xs.min(), xs.max()

    def fix(edge, side):                   # bord du corps caché sous les cheveux : on le prolonge en ligne droite
        ok = np.zeros(H, bool)
        for y in range(H):
            e = edge[y]
            if 0 <= e < W:
                xs = range(max(0, e - 4), e) if side < 0 else range(e + 1, min(W, e + 5))
                ok[y] = not any(hair[y, x] for x in xs)
        ys = np.where(ok)[0]
        if len(ys) < 2:
            return edge
        out = edge.astype(float)
        bad = np.where(~ok & (edge >= 0) & (edge < W))[0]
        bad = bad[bad > ys[0]]
        out[bad] = np.interp(bad, ys, edge[ys].astype(float))
        return (np.minimum(edge, out) if side < 0 else np.maximum(edge, out)).astype(int)
    lo2, hi2 = fix(lo, -1), fix(hi, 1)
    span = (X[None, :] >= lo2[:, None]) & (X[None, :] <= hi2[:, None])
    over = hair & below & span
    gone = below & ~span & ~body
    out = arr.copy()
    try:
        import cv2
        rgb = np.ascontiguousarray(arr[..., :3][..., ::-1])
        m = cv2.dilate((((hair | (arr[..., 3] < 200)) & span) * 255).astype(np.uint8), np.ones((3, 3), np.uint8))
        src = arr[..., :3].astype(np.float32)
        det = src - cv2.GaussianBlur(src, (0, 0), 3)
        okd = (body & (parts != 2)).astype(np.float32)
        detail = np.zeros_like(det)
        have = np.zeros(okd.shape, bool)
        for sh in (70, 110, 150, 40, 190):
            sh = int(sh * g["u"] / 44)
            d2, k2 = np.roll(det, -sh, axis=0), np.roll(okd, -sh, axis=0)
            take = ~have & (k2 > 0)
            detail[take] = d2[take]
            have |= take
        inp = np.clip(cv2.inpaint(rgb, m, 5, cv2.INPAINT_NS)[..., ::-1].astype(np.float32) + detail * 0.9, 0, 255)
        o2 = (cv2.dilate((over * 255).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & span
        out[..., :3] = np.where(o2[..., None], inp.astype(np.uint8), out[..., :3])
        a = out[..., 3].astype(np.float32)
        a[o2] = 255
    except Exception:                       # sans OpenCV : on garde les mèches devant le corps
        a = out[..., 3].astype(np.float32)
    a[gone] = 0
    dist = cy[None, :] - Y
    tip = hair & (dist >= 0) & (dist < 6) & ~span
    a[tip] *= np.clip(dist[tip] / 6, 0.25, 1)
    out[..., 3] = a.astype(np.uint8)
    return out


# ================================================================ silhouette (plus fine / plus ronde)
SILHOUETTES = [("Très fine", 0.86), ("Fine", 0.93), ("D'origine", 1.0), ("Ronde", 1.08), ("Très ronde", 1.16)]


POITRINES = [("Plus petite", -0.18), ("Un peu plus petite", -0.09), ("D'origine", 0.0),
             ("Un peu plus grande", 0.09), ("Plus grande", 0.18)]


def bust(arr, char, s):
    """Poitrine un peu plus petite (s < 0) ou plus grande (s > 0), sur le personnage habillé : déformation douce
    autour de deux points placés d'après le visage. Plage volontairement modérée."""
    g = face_geometry(char)
    s = max(-0.18, min(0.18, float(s or 0)))
    if g is None or abs(s) < 1e-3:
        return arr
    try:
        import cv2
    except Exception:
        return arr
    H, W = arr.shape[:2]
    cy, dx, R = g["chin"] + 2.7 * g["u"], 0.5 * g["d"], 0.62 * g["d"]
    y0, y1 = int(max(0, cy - 2.2 * R)), int(min(H, cy + 2.2 * R))
    x0, x1 = int(max(0, g["cx"] - dx - 2.2 * R)), int(min(W, g["cx"] + dx + 2.2 * R))
    if y1 <= y0 or x1 <= x0:
        return arr
    Y, X = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    mx, my = X.copy(), Y.copy()
    for cx in (g["cx"] - dx, g["cx"] + dx):
        rx, ry = (X - cx) / R, (Y - cy) / (R * 0.9)
        r2 = rx * rx + ry * ry
        w = np.exp(-r2 * 1.6) * (r2 < 4)
        mx -= (X - cx) * s * w
        my -= (Y - cy) * s * w
    out = arr.copy()
    out[y0:y1, x0:x1] = cv2.remap(arr, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(0, 0, 0, 0))
    return out


class Geo:
    """Élargit ou affine le corps sous le cou (la tête ne bouge pas). pad : marge ajoutée de chaque côté."""

    def __init__(self, char, w, h, k):
        g = face_geometry(char)
        self.k, self.w0, self.h = float(k), w, h
        self.cx = g["cx"] if g else w / 2
        self.y0 = (g["chin"] + 0.15 * g["u"]) if g else h * 0.2
        self.y1 = self.y0 + (2.2 * g["u"] if g else h * 0.1)
        self.pad = int(np.ceil(max(0.0, self.k - 1) * max(self.cx, w - self.cx))) + (2 if self.k > 1 else 0)
        self.w = w + 2 * self.pad

    def kf(self, y):
        t = np.clip((np.asarray(y, np.float32) - self.y0) / max(1.0, self.y1 - self.y0), 0, 1)
        t = t * t * (3 - 2 * t)
        return 1 + (self.k - 1) * t

    def fwd(self, x, y):
        return self.pad + self.cx + (np.asarray(x, np.float32) - self.cx) * self.kf(y)

    def inv(self, x, y):
        return self.cx + (np.asarray(x, np.float32) - self.pad - self.cx) / self.kf(y)

    def active(self):
        return abs(self.k - 1) > 1e-3


def warp(arr, geo):
    """Applique la silhouette à une image h×w×4 (interpolation horizontale ligne par ligne)."""
    if geo is None or not geo.active():
        return arr
    H = arr.shape[0]
    W1 = geo.w
    out = np.zeros((H, W1, arr.shape[2]), np.uint8)
    xs = np.arange(W1, dtype=np.float32)
    src = arr.astype(np.float32)
    for y in range(H):
        sx = geo.inv(xs, y)
        x0 = np.floor(sx).astype(np.int32)
        f = (sx - x0)[:, None]
        ok = (x0 >= 0) & (x0 < arr.shape[1] - 1)
        x0c = np.clip(x0, 0, arr.shape[1] - 2)
        row = src[y, x0c] * (1 - f) + src[y, x0c + 1] * f
        row[~ok] = 0
        out[y] = np.clip(row + 0.5, 0, 255).astype(np.uint8)
    return out


def shift_char(char, geo):
    """Calibrage (yeux, bouche, zones…) déplacé avec la silhouette."""
    if geo is None or not geo.active():
        return char
    c = dict(char)

    def f(x, y):
        return float(geo.fwd(x, y))
    c["eyes"] = [dict(e, x=f(e["x"], e["y"])) for e in char.get("eyes", [])]
    if char.get("mouth"):
        c["mouth"] = dict(char["mouth"], x=f(char["mouth"]["x"], char["mouth"]["y"]))
    if char.get("skin_sample"):
        s = char["skin_sample"]
        c["skin_sample"] = dict(s, x=int(round(f(s["x"], s["y"]))))
    if char.get("zones"):
        c["zones"] = [dict(z, cx=f(z["cx"], z["cy"])) if "cx" in z else z for z in char["zones"]]
    return c
