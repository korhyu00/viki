"""Traduction de manga / BD / webtoon : elle trouve les bulles, lit le texte, le traduit avec ton IA,
efface l'original et écrit la traduction à sa place.

Pages : images, dossier, .zip / .cbz, .cbr / .rar / .7z / .cb7 (bsdtar, 7z ou unrar), .pdf (pdftoppm).
Lecture du texte, au choix (« auto » prend le meilleur disponible) :
  - manga-ocr : spécialiste du japonais de manga (à installer, ~1 Go, tourne sur le processeur) ;
  - « IA qui voit » : un modèle Ollama avec la vision (ex : qwen3-vl:4b) ou ton IA en ligne si elle voit les images ;
  - Tesseract : s'il est installé avec la bonne langue.
Traduction : ton IA habituelle, page par page (pour garder le contexte entre les bulles).

Pour ton usage personnel : ne partage pas les traductions de scans d'œuvres protégées.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import numpy as np

try:
    import cv2
except Exception:                       # OpenCV absent : la détection des bulles est impossible
    cv2 = None

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif", ".tif", ".tiff"}
ARCH_EXT = {".zip", ".cbz", ".cbr", ".rar", ".7z", ".cb7"}
SOURCES = {"auto": "Langue détectée seule", "ja": "Japonais", "en": "Anglais", "ko": "Coréen", "zh": "Chinois",
           "fr": "Français", "es": "Espagnol"}
CIBLES = ["français", "anglais", "espagnol", "allemand", "italien", "portugais"]
TESS = {"ja": "jpn", "en": "eng", "ko": "kor", "zh": "chi_sim", "fr": "fra", "es": "spa"}
POLICES = ["Wild Words", "CC Wild Words", "Anime Ace 2.0 BB", "Anime Ace", "Komika Axis", "Comic Neue",
           "Comic Sans MS", "Bangers", "Noto Sans", "DejaVu Sans"]


def available():
    return cv2 is not None


def natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


# ================================================================== pages
def is_manga_source(path):
    """Un dossier / une archive qui contient surtout des images ?"""
    p = Path(path)
    try:
        if p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()][:400]
            imgs = [f for f in files if f.suffix.lower() in IMG_EXT]
            return len(imgs) >= 2 and len(imgs) >= 0.6 * len(files)
        if p.suffix.lower() in (".cbz", ".cbr", ".cb7"):
            return True
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
            imgs = [n for n in names if Path(n).suffix.lower() in IMG_EXT]
            return len(imgs) >= 2 and len(imgs) >= 0.7 * len(names)
    except Exception:
        pass
    return False


def extract_pages(src, workdir):
    """-> liste triée des images des pages (copiées / extraites dans workdir si besoin)."""
    srcs = [Path(s) for s in (src if isinstance(src, (list, tuple)) else [src])]
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    pages = []
    for s in srcs:
        ext = s.suffix.lower()
        if s.is_dir():
            pages += sorted((f for f in s.rglob("*") if f.suffix.lower() in IMG_EXT and f.is_file()),
                            key=natural_key)
        elif ext in IMG_EXT:
            pages.append(s)
        elif ext in (".zip", ".cbz"):
            out = work / "pages"
            with zipfile.ZipFile(s) as z:
                for n in z.namelist():
                    if Path(n).suffix.lower() in IMG_EXT and not n.startswith("__MACOSX"):
                        target = out / Path(n).as_posix().replace("..", "_")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(n) as fi, open(target, "wb") as fo:
                            shutil.copyfileobj(fi, fo)
            pages += sorted((f for f in out.rglob("*") if f.suffix.lower() in IMG_EXT), key=natural_key)
        elif ext in (".cbr", ".rar", ".7z", ".cb7"):
            out = work / "pages"
            out.mkdir(parents=True, exist_ok=True)
            tool = None
            for cmd in (["bsdtar", "-xf", str(s), "-C", str(out)], ["7z", "x", "-y", f"-o{out}", str(s)],
                        ["7za", "x", "-y", f"-o{out}", str(s)], ["unrar", "x", "-o+", str(s), str(out) + "/"]):
                if shutil.which(cmd[0]):
                    tool = cmd
                    break
            if not tool:
                raise RuntimeError("pour ouvrir ce fichier, installe « libarchive » (bsdtar) ou « 7zip »")
            r = subprocess.run(tool, capture_output=True, timeout=600)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors="ignore")[-200:] or "extraction impossible")
            pages += sorted((f for f in out.rglob("*") if f.suffix.lower() in IMG_EXT), key=natural_key)
        elif ext == ".pdf":
            if not shutil.which("pdftoppm"):
                raise RuntimeError("il faut « pdftoppm » (paquet poppler) pour les PDF")
            out = work / "pages"
            out.mkdir(parents=True, exist_ok=True)
            subprocess.run(["pdftoppm", "-r", "150", "-png", str(s), str(out / "page")], capture_output=True,
                           timeout=900)
            pages += sorted(out.glob("*.png"), key=natural_key)
    return pages


def imread(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"image illisible : {Path(path).name}")
    return img


def imwrite(path, img):
    ext = Path(path).suffix.lower() or ".png"
    ok, buf = cv2.imencode(ext, img, [cv2.IMWRITE_JPEG_QUALITY, 92] if ext in (".jpg", ".jpeg") else [])
    if not ok:
        raise RuntimeError("enregistrement impossible")
    buf.tofile(str(path))


# ================================================================== bulles
def detect_bubbles(img, rtl=True):
    """Bulles claires contenant du texte -> [{"box": [x,y,w,h], "text_box": [...], "contour": [[x,y],...],
    "fond": [b,g,r]}], dans l'ordre de lecture (droite -> gauche pour le manga)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    page = h * w
    _, white = cv2.threshold(gray, 195, 255, cv2.THRESH_BINARY)
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, hier = cv2.findContours(white, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    if hier is None:
        return out
    for i, c in enumerate(cnts):
        if hier[0][i][3] != -1:
            continue
        area = cv2.contourArea(c)
        if area < page * 0.0012 or area > page * 0.22:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < 24 or bh < 24 or (bw > 0.85 * w and bh > 0.85 * h):
            continue
        hull = cv2.convexHull(c)
        solidity = area / max(1.0, cv2.contourArea(hull))
        if solidity < 0.55:
            continue
        if area / float(bw * bh) > 0.85 and area > page * 0.05:     # une case entière, pas une bulle
            continue
        mask = np.zeros((h, w), np.uint8)
        cv2.drawContours(mask, [c], -1, 255, cv2.FILLED)
        # les « trous » (le texte) font partie de la bulle
        k = max(3, int(min(bw, bh) * 0.04)) | 1
        inner = cv2.erode(mask, np.ones((k, k), np.uint8))
        region = inner > 0
        nreg = int(region.sum())
        if nreg < 300:
            continue
        dark = (gray < 120) & region
        ratio = dark.sum() / nreg
        if ratio < 0.008 or ratio > 0.5:
            continue
        n, _lab, stats, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
        comps = [s for s in stats[1:] if 3 <= s[4] < nreg * 0.25 and s[2] < bw * 0.9 and s[3] < bh * 0.9]
        if len(comps) < 3:
            continue
        tx0 = min(s[0] for s in comps)
        ty0 = min(s[1] for s in comps)
        tx1 = max(s[0] + s[2] for s in comps)
        ty1 = max(s[1] + s[3] for s in comps)
        if area > page * 0.04 and (tx1 - tx0) * (ty1 - ty0) > 0.7 * bw * bh:
            continue                            # « texte » étalé partout : une case dessinée, pas une bulle
        light = gray[region & ~dark]
        fond = img[region & (gray > np.percentile(light, 40) if light.size else region)]
        col = np.median(fond, axis=0).astype(int).tolist() if fond.size else [255, 255, 255]
        out.append({"box": [int(x), int(y), int(bw), int(bh)],
                    "text_box": [int(tx0), int(ty0), int(tx1 - tx0), int(ty1 - ty0)],
                    "contour": c.reshape(-1, 2).tolist(), "fond": col, "manuel": False})
    # ordre de lecture : par bandes horizontales, puis de droite à gauche (manga) ou de gauche à droite
    band = max(40, h // 10)
    out.sort(key=lambda b: (int((b["box"][1] + b["box"][3] / 2) // band),
                            -(b["box"][0] + b["box"][2]) if rtl else b["box"][0]))
    return out


# ================================================================== détection du texte (partout sur la page)
DETECTOR_URL = ("https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/"
                "comictextdetector.pt.onnx")
DETECTOR_FILE = None                    # chemin choisi par Viki (dossier de données de l'utilisateur)
DETECTOR_MB = 95
DET_VERSION = 2                         # pages détectées avec une ancienne méthode : refaites
_net = None
_net_lock = threading.Lock()


def det_tag():
    """Méthode de détection utilisée (si elle change, les pages sont refaites)."""
    return f"{DET_VERSION}{'c' if detector_ready() else 's'}"


def detector_ready():
    try:
        return bool(DETECTOR_FILE) and Path(DETECTOR_FILE).stat().st_size > 80_000_000
    except Exception:
        return False


def download_detector(progress=None):
    """Télécharge le détecteur de texte de manga (comic-text-detector, ~95 Mo, une seule fois)."""
    import urllib.request
    dest = Path(DETECTOR_FILE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    req = urllib.request.Request(DETECTOR_URL, headers={"User-Agent": "Viki"})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or DETECTOR_MB * 1_000_000)
        got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if part.stat().st_size < 80_000_000:
        part.unlink(missing_ok=True)
        raise RuntimeError("téléchargement incomplet")
    part.replace(dest)
    return dest


def _detector():
    global _net
    with _net_lock:
        if _net is None:
            _net = cv2.dnn.readNetFromONNX(str(DETECTOR_FILE))
        return _net


def detect_text_ctd(img):
    """Blocs de texte (bulles, cartouches, texte sur le dessin, onomatopées) + masque des pixels de texte."""
    H, W = img.shape[:2]
    S = 1024
    r = S / max(H, W)
    nh, nw = int(round(H * r)), int(round(W * r))
    lb = np.zeros((S, S, 3), np.uint8)
    lb[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if r < 1 else cv2.INTER_LINEAR)
    net = _detector()
    with _net_lock:
        net.setInput(cv2.dnn.blobFromImage(lb, 1 / 255.0, (S, S), swapRB=True))
        blk, seg = net.forward(["blk", "seg", "det"])[:2]
    p = blk[0]
    conf = p[:, 4] * p[:, 5:].max(1)
    keep = conf > 0.3
    p, conf = p[keep], conf[keep]
    boxes = [[float(cx - w / 2), float(cy - h / 2), float(w), float(h)] for cx, cy, w, h in p[:, :4]]
    blocks = []
    if boxes:
        for i in np.array(cv2.dnn.NMSBoxes(boxes, conf.tolist(), 0.3, 0.35)).flatten():
            x, y, w, h = [v / r for v in boxes[i]]
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1, y1 = min(W, int(x + w + 0.5)), min(H, int(y + h + 0.5))
            if x1 - x0 >= 8 and y1 - y0 >= 8:
                blocks.append([x0, y0, x1 - x0, y1 - y0])
    m = (seg[0, 0, :nh, :nw] > 0.3).astype(np.uint8) * 255
    mask = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)
    # texte vu par le masque mais sans bloc (gros titres, onomatopées…) : on regroupe les pixels proches
    k = max(5, int(min(W, H) * 0.012)) | 1
    grown = cv2.dilate(mask, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    for s in stats[1:]:
        x, y, w, h, _a = [int(v) for v in s]
        if w < 18 or h < 18 or max(w, h) > 0.6 * max(W, H):
            continue
        if any(_overlap([x, y, w, h], b) > 0.3 for b in blocks):
            continue
        sub = mask[y:y + h, x:x + w] > 0
        fill = sub.mean()
        if fill < 0.06 or fill > 0.75 or max(w, h) > 10 * min(w, h) or sub.sum() < 150:
            continue                                  # traits du dessin (fins et allongés), pas du texte
        blocks.append([x, y, w, h, "douteux"])
    return _merge_near(blocks), mask


def _merge_near(blocks):
    """Regroupe les morceaux voisins d'un même texte hors bulle (lettres espacées d'un titre…)."""
    out = [list(b) for b in blocks]
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                if len(a) < 5 or len(b) < 5:            # seulement les morceaux « douteux »
                    continue
                gap_x = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
                gap_y = max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3])
                s = min(max(a[2], a[3]), max(b[2], b[3])) * 0.5
                if gap_x < s and gap_y < s:
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    out[i] = [x0, y0, x1 - x0, y1 - y0, "douteux"]
                    del out[j]
                    changed = True
                    break
            if changed:
                break
    return out


def _overlap(a, b):
    """Part de a recouverte par b."""
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / float(max(1, aw * ah))


def detect_text_classic(img, bubbles):
    """Sans le détecteur : texte sombre hors des bulles (cartouches, panneaux, petits textes) par groupes de
    caractères de taille semblable. Les faux positifs sont écartés ensuite si la lecture ne donne rien."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    dark = (gray < 110).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    chars = np.zeros_like(dark)
    hs = []
    for i, s in enumerate(stats[1:], 1):
        x, y, w, h, a = [int(v) for v in s]
        if not (8 <= h <= 0.07 * H and 3 <= w <= 0.07 * W):
            continue
        if not (0.12 <= a / float(w * h) <= 0.9) or max(w, h) > 6 * min(w, h) and min(w, h) > 3:
            continue
        if any(_overlap([x, y, w, h], b["box"]) > 0.5 for b in bubbles):
            continue
        chars[lab == i] = 1
        hs.append(h)
    if not hs:
        return []
    med = float(np.median(hs))
    k = max(3, int(med * 0.7)) | 1
    grp = cv2.dilate(chars * 255, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(grp, connectivity=8)
    out = []
    for i, s in enumerate(stats[1:], 1):
        x, y, w, h, _a = [int(v) for v in s]
        sub_n = cv2.connectedComponents((chars[y:y + h, x:x + w] > 0).astype(np.uint8))[0] - 1
        if sub_n < 3 or w * h > 0.08 * W * H:
            continue
        out.append([x, y, w, h, "douteux"])
    return out


def _free_zone(img, bl, mask=None):
    """Texte hors bulle : un rectangle, avec la couleur du fond autour du texte."""
    H, W = img.shape[:2]
    x, y, w, h = bl[:4]
    p = max(4, int(min(w, h) * 0.15))
    x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
    crop = img[y0:y1, x0:x1]
    if mask is not None:
        bg = crop[mask[y0:y1, x0:x1] == 0]
    else:
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        bg = crop[g > np.percentile(g, 55)]
    col = np.median(bg, axis=0).astype(int).tolist() if bg.size else [255, 255, 255]
    cont = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return {"box": [x0, y0, x1 - x0, y1 - y0], "text_box": [x, y, w, h], "contour": cont, "fond": col,
            "manuel": False, "libre": True, "douteux": len(bl) > 4}


def detect_all(img, rtl=True):
    """Toutes les zones de texte de la page -> (zones, masque du texte ou None)."""
    bubbles = detect_bubbles(img, rtl)
    H, W = img.shape[:2]
    mask = None
    if detector_ready():
        try:
            blocks, mask = detect_text_ctd(img)
        except Exception:
            blocks, mask = [], None
    else:
        blocks = None
    if blocks is None:                              # méthode simple
        zones = bubbles + [_free_zone(img, bl) for bl in detect_text_classic(img, bubbles)]
    else:
        zones, used = [], {}
        masks = [_mask_of(b, img.shape) for b in bubbles]
        for bl in blocks:
            cx, cy = bl[0] + bl[2] // 2, bl[1] + bl[3] // 2
            j = next((j for j, mk in enumerate(masks) if 0 <= cy < H and 0 <= cx < W and mk[cy, cx]
                      and _overlap(bl, bubbles[j]["box"]) > 0.6), None)
            if j is None:
                zones.append(_free_zone(img, bl, mask))
            elif j in used:                         # plusieurs colonnes dans la même bulle
                z = used[j]
                x0, y0 = min(z["text_box"][0], bl[0]), min(z["text_box"][1], bl[1])
                x1 = max(z["text_box"][0] + z["text_box"][2], bl[0] + bl[2])
                y1 = max(z["text_box"][1] + z["text_box"][3], bl[1] + bl[3])
                z["text_box"] = [x0, y0, x1 - x0, y1 - y0]
            else:
                z = dict(bubbles[j])
                x0, y0 = min(z["text_box"][0], bl[0]), min(z["text_box"][1], bl[1])
                x1 = max(z["text_box"][0] + z["text_box"][2], bl[0] + bl[2])
                y1 = max(z["text_box"][1] + z["text_box"][3], bl[1] + bl[3])
                z["text_box"] = [x0, y0, x1 - x0, y1 - y0]
                used[j] = z
                zones.append(z)
        for j, b in enumerate(bubbles):             # bulle vue par l'ancienne méthode seulement
            if j not in used and b["box"][2] * b["box"][3] < 0.1 * W * H:
                zones.append(b)
    band = max(40, H // 10)
    zones.sort(key=lambda b: (int((b["box"][1] + b["box"][3] / 2) // band),
                              -(b["box"][0] + b["box"][2]) if rtl else b["box"][0]))
    return zones, mask


def useful_text(t):
    """Une zone « douteuse » n'est gardée que si on y a lu du vrai texte."""
    t = (t or "").strip()
    if not t or t == "-":
        return False
    good = len(re.findall(r"[\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", t))
    if good == 1 and _CJK.search(t) and len(t.replace(" ", "")) <= 3:
        return True                                    # « え？ », « 何！ » : une vraie réplique très courte
    return good >= 2 and good / max(1, len(t.replace(" ", ""))) >= 0.6


def manual_zone(img, x, y, w, h):
    """Zone dessinée à la main (bulle non trouvée, texte hors bulle)."""
    H, W = img.shape[:2]
    x, y = max(0, int(x)), max(0, int(y))
    w, h = max(8, min(int(w), W - x)), max(8, min(int(h), H - y))
    crop = img[y:y + h, x:x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    light = crop[gray > np.percentile(gray, 60)]
    col = np.median(light, axis=0).astype(int).tolist() if light.size else [255, 255, 255]
    cont = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return {"box": [x, y, w, h], "text_box": [x, y, w, h], "contour": cont, "fond": col, "manuel": True}


def _mask_of(b, shape):
    m = np.zeros(shape[:2], np.uint8)
    cv2.drawContours(m, [np.array(b["contour"], np.int32).reshape(-1, 1, 2)], -1, 255, cv2.FILLED)
    return m


def crop_text(img, b, pad=6):
    x, y, w, h = b["text_box"]
    H, W = img.shape[:2]
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    return img[y0:y1, x0:x1]


def clean(img, bubbles, tmask=None):
    """Efface le texte d'origine (couleur du fond de la bulle ; inpainting si le fond n'est pas uni).
    tmask : masque des pixels de texte donné par le détecteur (plus précis, marche aussi hors des bulles)."""
    out = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for b in bubbles:
        if b.get("ignore") or not (b.get("traduction") or "").strip():
            continue                            # rien à écrire : on garde l'original plutôt qu'un trou
        m = _mask_of(b, img.shape)
        if b.get("libre"):
            region = m > 0
            x, y, w, h = b["text_box"]
            box = np.zeros_like(region)
            box[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3] = True
            if tmask is not None:
                txt = (tmask > 0) & box
            else:
                fond = np.mean(b["fond"])
                txt = ((gray < fond - 60) | (gray > fond + 60)) & box
            txt = cv2.dilate(txt.astype(np.uint8) * 255, np.ones((7, 7), np.uint8)) > 0
            txt &= region
            sample = img[region & ~txt]
            if sample.size and np.std(sample) < 12:
                out[txt] = b["fond"]
            else:
                out = cv2.inpaint(out, txt.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
            continue
        if not b.get("manuel"):
            k = max(3, int(min(b["box"][2], b["box"][3]) * 0.04)) | 1
            m = cv2.erode(m, np.ones((k, k), np.uint8))
        region = m > 0
        thr = 140 if np.mean(b["fond"]) > 150 else 90
        txt = ((gray < thr) if np.mean(b["fond"]) > 150 else (gray > 255 - thr)) & region
        x, y, w, h = b["text_box"]
        box = np.zeros_like(region)
        box[max(0, y - 4):y + h + 4, max(0, x - 4):x + w + 4] = True
        txt &= box
        if tmask is not None:                   # + ce que le détecteur a vu (texte clair, tramé…)
            txt |= (tmask > 0) & box
        txt = cv2.dilate(txt.astype(np.uint8) * 255, np.ones((5, 5), np.uint8)) > 0
        txt &= region
        sample = img[region & ~txt]
        if sample.size and np.std(sample) < 12:                 # fond uni : on repeint
            out[txt] = b["fond"]
        else:                                                    # trame / dégradé : on reconstruit
            out = cv2.inpaint(out, txt.astype(np.uint8) * 255, 4, cv2.INPAINT_TELEA)
    return out


# ================================================================== écriture de la traduction (Qt)
def pick_font(preferred=""):
    from PyQt6.QtGui import QFontDatabase
    fams = set(QFontDatabase.families())
    for f in ([preferred] if preferred else []) + POLICES:
        if f and f in fams:
            return f
    return ""


def _wrap(fm, text, width):
    # ponctuation française (« ? ! : ; ») jamais seule en début de ligne : espace insécable
    text = re.sub(r"\s+([?!:;»])", "\u00a0\\1", text)
    text = re.sub(r"«\s+", "«\u00a0", text)
    words, lines, cur = [w for w in re.split(r"[ \t\n]+", text) if w], [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if fm.horizontalAdvance(cand) <= width or not cur:
            if fm.horizontalAdvance(wd) > width and not cur:          # mot trop long : on le coupe
                part = ""
                for ch in wd:
                    if fm.horizontalAdvance(part + ch + "-") > width and part:
                        lines.append(part + "-")
                        part = ch
                    else:
                        part += ch
                cur = part
            else:
                cur = cand
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def typeset(bgr, bubbles, font_family="", upper=False):
    """Écrit les traductions dans les bulles -> image BGR."""
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
    h, w = bgr.shape[:2]
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    p = QPainter(qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    fam = pick_font(font_family)
    for b in bubbles:
        txt = (b.get("traduction") or "").strip()
        if not txt or b.get("ignore"):
            continue
        if upper:
            txt = txt.upper()
        x, y, bw, bh = b["box"]
        if b.get("libre"):                     # hors bulle : un peu plus de place, en horizontal
            cx, cy = x + bw / 2, y + bh / 2
            rw = min(w - 4, max(bw, bh * 0.9, 70) * 1.1)
            rh = min(h - 4, max(bh, bw * 0.45, 30) * 1.05)
            rx = min(max(2, cx - rw / 2), w - rw - 2)
            ry = min(max(2, cy - rh / 2), h - rh - 2)
            rect = QRectF(rx, ry, rw, rh)
        elif b.get("manuel"):
            rect = QRectF(x + 2, y + 2, bw - 4, bh - 4)
        else:                                  # rectangle inscrit dans une bulle à peu près ovale
            m = _mask_of(b, bgr.shape)
            M = cv2.moments(m, binaryImage=True)
            cx = M["m10"] / M["m00"] if M["m00"] else x + bw / 2
            cy = M["m01"] / M["m00"] if M["m00"] else y + bh / 2
            rw, rh = bw * 0.74, bh * 0.70
            rect = QRectF(cx - rw / 2, cy - rh / 2, rw, rh)
        best = None
        size = min(42.0, max(10.0, rect.height() / 2.2))
        while size >= 6.0:
            f = QFont(fam) if fam else QFont()
            f.setPixelSize(int(size))
            f.setBold(True)
            if fam in ("", "Noto Sans", "DejaVu Sans"):
                f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
            fm = QFontMetricsF(f)
            lines = _wrap(fm, txt, rect.width())
            lh = fm.height() * 0.98
            if lh * len(lines) <= rect.height() and all(fm.horizontalAdvance(l) <= rect.width() + 1 for l in lines):
                best = (f, lines, lh, fm)
                break
            size -= 1.0
        if not best:                          # même tout petit ça ne rentre pas : on prend toute la bulle
            rect = QRectF(x + 2, y + 2, bw - 4, bh - 4)
            f = QFont(fam) if fam else QFont()
            f.setPixelSize(7)
            f.setBold(True)
            fm = QFontMetricsF(f)
            best = (f, _wrap(fm, txt, rect.width()), fm.height(), fm)
        f, lines, lh, fm = best
        dark_bg = np.mean(b["fond"]) < 110
        ink = QColor(255, 255, 255) if dark_bg else QColor(15, 15, 15)
        halo = QColor(0, 0, 0) if dark_bg else QColor(255, 255, 255)
        top = rect.center().y() - lh * len(lines) / 2
        path = QPainterPath()
        for i, line in enumerate(lines):
            lw = fm.horizontalAdvance(line)
            path.addText(QPointF(rect.center().x() - lw / 2, top + i * lh + fm.ascent()), f, line)
        if b.get("manuel") or b.get("libre"):  # hors bulle : petit contour pour rester lisible
            p.setPen(QPen(halo, max(2.0, f.pixelSize() / 6), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawPath(path)
    p.end()
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


# ================================================================== lecture du texte
MANGA_OCR_SERVER = r'''
import sys, json
from manga_ocr import MangaOcr
m = MangaOcr()
print("PRET", flush=True)
for line in sys.stdin:
    p = line.strip()
    if not p:
        continue
    try:
        print(json.dumps({"ok": True, "texte": m(p)}, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "erreur": repr(e)}), flush=True)
'''


class MangaOcr:
    """manga-ocr dans son propre Python (gardé ouvert pendant la traduction)."""

    def __init__(self, python):
        env = dict(os.environ)
        for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"):
            env.pop(k, None)
        if os.environ.get("COMPAGNON_ORIG_LD"):
            env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
        self.p = subprocess.Popen([python, "-c", MANGA_OCR_SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        line = self.p.stdout.readline()
        if "PRET" not in line:
            raise RuntimeError("manga-ocr n'a pas démarré")
        self.lock = threading.Lock()

    def read(self, png_path):
        with self.lock:
            self.p.stdin.write(str(png_path) + "\n")
            self.p.stdin.flush()
            r = json.loads(self.p.stdout.readline() or "{}")
        return r.get("texte", "") if r.get("ok") else ""

    def close(self):
        try:
            self.p.stdin.close()
            self.p.terminate()
        except Exception:
            pass


def tesseract_langs():
    if not shutil.which("tesseract"):
        return set()
    try:
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
        return {l.strip() for l in r.stdout.splitlines()[1:] if l.strip()}
    except Exception:
        return set()


def tesseract_read(png_path, lang, vertical=False):
    code = TESS.get(lang, "eng")
    langs = tesseract_langs()
    if lang == "ja" and vertical and "jpn_vert" in langs:
        code = "jpn_vert"
    if code not in langs:
        return ""
    r = subprocess.run(["tesseract", str(png_path), "-", "-l", code, "--psm", "5" if vertical else "6"],
                       capture_output=True, text=True, timeout=60)
    t = r.stdout.strip()
    if lang in ("ja", "zh"):
        t = re.sub(r"\s+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def b64png(img):
    ok, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf.tobytes()).decode()


def upscale_for_ocr(crop):
    h, w = crop.shape[:2]
    s = 1.0
    if min(h, w) < 48:
        s = 48 / max(1, min(h, w))
    s = min(4.0, max(s, 2.0 if max(h, w) < 200 else 1.0))
    if s > 1.01:
        crop = cv2.resize(crop, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)
    return crop


def clean_ocr(t):
    t = (t or "").strip().strip("「」『』“”\"")
    t = re.sub(r"[|_~]{2,}", "", t)
    t = re.sub(r"(^|\s)\|(?=\s|')", r"\1I", t)        # Tesseract lit souvent « I » comme « | »
    t = re.sub(r"\s+", " ", t)
    return "" if t.strip() in ("-", "—", "") else t.strip()


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uff66-\uff9f]")
_BAVARD = re.compile(                                 # ce qu'une IA dit quand elle ne lit / traduit pas la bulle
    r"(il n.y a (pas|aucun) (de )?texte|aucun texte|pas de texte (visible|lisible|dans)|texte (illisible|absent|vide)|"
    r"je ne (peux|parviens|suis pas en mesure)[^.!?]{0,40}(lire|traduire|transcrire|voir)|je n.arrive pas [àa] (lire|traduire)|"
    r"d[ée]sol[ée]e?,? (mais )?je (ne|n.)|impossible de (lire|traduire|transcrire)|cette (image|bulle) (ne )?(montre|contient|est)|"
    r"l.image (montre|contient|ne contient|repr[ée]sente)|en tant qu.ia|"
    r"\bno (visible |readable )?text\b|there is no (visible |readable )?text|the (image|bubble|panel) (shows|contains|is|does|depicts)|"
    r"this (image|bubble|panel) (shows|contains|is|does|depicts)|i.?m sorry,? (but )?i|sorry,? (but )?i (can|could|am)|"
    r"i (can.t|cannot|am unable to|could not|don.t see)[^.!?]{0,30}(read|translate|transcribe|see|text)|"
    r"unable to (read|translate|transcribe)|as an ai|cannot translate|"
    r"traceback \(most recent|\bexception:|\berror:|\berreur ?:|http error|timed out|connection refused|"
    r"^n/?a$|^none$|^null$|^undefined$|^\(?vide\)?$|^\(?empty\)?$|^\.\.\.$|^…$)", re.I)


def texte_lu(t, src="ja"):
    """Le texte lu dans une bulle, sans les commentaires d'une IA qui voit (« Il n'y a pas de texte »…)."""
    t = clean_ocr(t)
    t = re.sub(r"^(texte|text|transcription|réponse|answer)\s*:\s*", "", t, flags=re.I).strip().strip('"«»“”')
    if not t or _BAVARD.search(t):
        return ""
    if src in ("ja", "zh", "ko", "auto") and not _CJK.search(t) and len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", t)) >= 3:
        return ""                                      # une phrase en français/anglais : un commentaire, pas la bulle
    return t


def traduction_propre(t, original=""):
    """La traduction rendue par l'IA, nettoyée ; "" si c'est un refus, une erreur ou un commentaire."""
    if not isinstance(t, str):
        return ""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
    t = re.sub(r"^(voici( la)? traduction|traduction|translation|here is the translation|réponse)\s*:?\s*", "", t,
               flags=re.I).strip()
    t = re.sub(r"\s*\((note|n\.?b\.?|nb)\s*:.*\)\s*$", "", t, flags=re.I | re.S).strip()
    t = re.split(r"\n\s*(note|nb|remarque)\s*:", t, flags=re.I)[0].strip()
    t = t.strip().strip('"«»“”').strip()
    if not t or t in ("-", "—", "…", "..."):
        return ""
    if t.startswith(("{", "[")) or re.search(r'"\s*\d+\s*"\s*:', t):
        return ""                                      # un morceau de JSON, pas une phrase
    if _BAVARD.search(t) and not _BAVARD.search(original or ""):
        return ""
    if original and t == original.strip() and _CJK.search(t):
        return ""                                      # pas traduit du tout
    return t


# ================================================================== modèles de traduction (Ollama, sur ton PC)
# (nom, taille, description) — classés du plus léger au plus lourd ; ta carte RX 6600 a 8 Go
MODELES = [
    ("translategemma:4b", "3,3 Go", "spécialiste de la traduction, rapide"),
    ("qwen3:8b", "5,2 Go", "très bon en japonais, garde le contexte"),
    ("translategemma:12b", "8,1 Go", "meilleure traduction, un peu plus lent"),
    ("qwen3:14b", "9,3 Go", "le plus fin pour le japonais, plus lent"),
    ("translategemma:27b", "17 Go", "qualité maximale, très lent (32 Go de RAM conseillés)"),
]
CODES = {"ja": ("Japanese", "ja"), "en": ("English", "en"), "ko": ("Korean", "ko"), "zh": ("Chinese", "zh"),
         "fr": ("French", "fr"), "es": ("Spanish", "es")}
CIBLES_EN = {"français": ("French", "fr"), "anglais": ("English", "en"), "espagnol": ("Spanish", "es"),
             "allemand": ("German", "de"), "italien": ("Italian", "it"), "portugais": ("Portuguese", "pt")}


def is_translator_model(name):
    """Modèle spécialisé (TranslateGemma…) : une bulle à la fois, avec son format de consigne à lui."""
    return bool(name) and "translategemma" in name.lower()


def translategemma_prompt(text, src, dst):
    s_name, s_code = CODES.get("ja" if src == "auto" else src, ("Japanese", "ja"))
    t_name, t_code = CIBLES_EN.get(dst, ("French", "fr"))
    return (f"You are a professional {s_name} ({s_code}) to {t_name} ({t_code}) translator. "
            f"Your goal is to accurately convey the meaning and nuances of the original {s_name} text while "
            f"adhering to {t_name} grammar, vocabulary, and cultural sensitivities.\n"
            f"Produce only the {t_name} translation, without any additional explanations or commentary. "
            f"Please translate the following {s_name} text into {t_name}:\n\n\n{text}")


# ================================================================== traduction (prompt)
def translation_prompt(items, src, dst, contexte=""):
    lang = SOURCES.get(src, "la langue d'origine").lower() if src != "auto" else "la langue d'origine"
    sys_ = (f"Tu es un traducteur professionnel de manga. Tu traduis des bulles de {lang} vers le {dst}. "
            "Traduction naturelle et orale, comme dans une vraie édition, fidèle au sens et au ton (humour, "
            "politesse, insultes adoucies seulement si l'original l'est). Phrases COURTES : elles doivent tenir "
            "dans la bulle. Certains textes sont hors des bulles (cartouches, panneaux, titres) : traduis-les aussi. "
            "Garde les noms propres. Les onomatopées : adapte-les en " + dst + ". "
            "Si une bulle est illisible ou vide, renvoie une chaîne vide pour elle. Ne commente jamais.")
    user = (("Contexte (pages précédentes, résumé) : " + contexte + "\n\n") if contexte else "") + \
        "Bulles de la page, dans l'ordre de lecture :\n" + json.dumps(
            [{"id": i, "texte": t} for i, t in items], ensure_ascii=False) + \
        '\n\nRéponds uniquement en JSON : {"1": "traduction de la bulle 1", "2": "..."}'
    return [{"role": "system", "content": sys_}, {"role": "user", "content": user}]


def vision_prompt(src):
    lang = SOURCES.get(src, "") if src != "auto" else ""
    return ("Transcris exactement le texte de cette bulle de manga" + (f" (en {lang.lower()})" if lang else "") +
            ". Lis dans le bon sens (le japonais vertical se lit de haut en bas, colonnes de droite à gauche). "
            "Réponds uniquement avec le texte, sans traduction ni commentaire. S'il n'y a pas de texte, réponds -")


# ================================================================== projet (traduction d'un tome / chapitre)
PROJECT = "viki-traduction.json"


def out_dir_for(src, dst):
    s = Path(src[0] if isinstance(src, (list, tuple)) else src)
    base = s if s.is_dir() else s.with_suffix("")
    if s.suffix.lower() in IMG_EXT:
        base = s.parent
    return base.parent / f"{base.name} ({dst[:2].upper()})"


def load_project(out_dir):
    try:
        return json.loads((Path(out_dir) / PROJECT).read_text(encoding="utf-8"))
    except Exception:
        return None


def save_project(out_dir, proj):
    p = Path(out_dir) / PROJECT
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def export_cbz(out_dir, name=None):
    out_dir = Path(out_dir)
    proj = load_project(out_dir) or {}
    files = [Path(pg["sortie"]) for pg in proj.get("pages", []) if pg.get("sortie") and Path(pg["sortie"]).exists()]
    if not files:
        files = sorted((f for f in out_dir.iterdir() if f.suffix.lower() in IMG_EXT), key=natural_key)
    target = out_dir.parent / f"{name or out_dir.name}.cbz"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as z:
        for i, f in enumerate(files, 1):
            z.write(f, f"{i:04d}{f.suffix.lower()}")
    return target


class Pipeline:
    """Traduit les pages une par une (dans un fil). Les fonctions de lecture / traduction viennent de Viki."""

    def __init__(self, comp, pages, out_dir, src_lang, dst, engine, font="", upper=False, model=""):
        self.model = model or ""                         # "" = le cerveau habituel de Viki
        self.comp, self.pages, self.out = comp, [str(p) for p in pages], Path(out_dir)
        self.src, self.dst, self.engine, self.font, self.upper = src_lang, dst, engine, font, upper
        self.stop = False
        self.stats, self.note = {}, ""
        self.ocr = None
        self.tmp = Path(tempfile.mkdtemp(prefix="viki-manga-"))
        self.proj = load_project(self.out) or {"pages": [], "source": src_lang, "cible": dst}
        # reprise : on retrouve chaque page par son rang et son nom (le dossier temporaire peut changer)
        old = self.proj["pages"]
        new = []
        for i, p in enumerate(self.pages):
            pg = old[i] if i < len(old) and Path(old[i].get("page", "")).name == Path(p).name else \
                next((o for o in old if Path(o.get("page", "")).name == Path(p).name), None)
            pg = dict(pg) if pg else {}
            pg["page"] = p
            new.append(pg)
        self.proj["pages"] = new
        self.out.mkdir(parents=True, exist_ok=True)

    # --- lecture
    def _reader(self):
        if self.engine == "mangaocr":
            if self.ocr is None:
                self.ocr = MangaOcr(self.comp.manga_ocr_python())
            return lambda path, crop, vert: texte_lu(self.ocr.read(path), self.src)
        if self.engine == "vision":
            return lambda path, crop, vert: texte_lu(self.comp.vision_read(crop, vision_prompt(self.src)), self.src)
        return lambda path, crop, vert: texte_lu(tesseract_read(path, "ja" if self.src == "auto" else self.src, vert),
                                                 self.src)

    def read_bubbles(self, img, bubbles, idx):
        reader = self._reader()
        for j, b in enumerate(bubbles):
            if self.stop:
                return
            if b.get("original") or b.get("ignore"):
                continue
            crop = upscale_for_ocr(crop_text(img, b))
            path = self.tmp / f"p{idx}_b{j}.png"
            cv2.imwrite(str(path), crop)
            tw, th = b["text_box"][2], b["text_box"][3]
            for essai in range(2):                     # une erreur passagère : on réessaie une fois
                try:
                    b["original"] = reader(str(path), crop, th > tw * 1.3)
                    b.pop("erreur", None)
                    break
                except Exception as e:
                    b["original"] = ""
                    b["erreur"] = repr(e)[:160]

    # --- traduction
    def _demande(self, msgs, timeout=300):
        """Une réponse JSON de l'IA (None si elle échoue)."""
        try:
            r = (self.comp.llm_json_model(self.model, msgs) if self.model else
                 self.comp.llm_json(msgs, timeout=timeout))
        except Exception:
            return None
        if isinstance(r, list):                        # certains modèles renvoient une liste
            r = {str(i + 1): t for i, t in enumerate(r)}
        return r if isinstance(r, dict) else None

    @staticmethod
    def _valeur(r, cle):
        t = r.get(cle) if r else None
        if isinstance(t, dict):
            t = t.get("traduction") or t.get("texte") or t.get("translation") or ""
        return t

    def translate(self, bubbles, contexte=""):
        items = [(i + 1, b["original"]) for i, b in enumerate(bubbles) if b.get("original") and not b.get("ignore")]
        if not items:
            return

        def poser(i, t):
            t = traduction_propre(t, bubbles[i - 1].get("original", ""))
            if t:
                bubbles[i - 1]["traduction"] = t
                bubbles[i - 1].pop("non_traduite", None)
            return bool(t)
        if is_translator_model(self.model):              # TranslateGemma : bulle par bulle
            for i, txt in items:
                for essai in range(2):
                    if self.stop:
                        return
                    try:
                        out = self.comp.llm_model(self.model, [{"role": "user", "content":
                                                                translategemma_prompt(txt, self.src, self.dst)}])
                    except Exception:
                        out = ""
                    if poser(i, out):
                        break
        else:
            r = self._demande(translation_prompt(items, self.src, self.dst, contexte))
            for i, _t in items:
                poser(i, self._valeur(r, str(i)))
            # bulles oubliées ou mal traduites : par petits paquets, puis une par une
            for taille in (6, 1):
                manquantes = [(i, t) for i, t in items if not bubbles[i - 1].get("traduction")][:40]
                for k in range(0, len(manquantes), taille):
                    if self.stop:
                        return
                    paquet = manquantes[k:k + taille]
                    r = self._demande(translation_prompt([(n + 1, t) for n, (_i, t) in enumerate(paquet)],
                                                         self.src, self.dst, contexte), timeout=180)
                    for n, (i, _t) in enumerate(paquet):
                        poser(i, self._valeur(r, str(n + 1)))
        for i, _t in items:                              # encore rien : on garde le texte d'origine (pas de trou)
            if not bubbles[i - 1].get("traduction"):
                bubbles[i - 1]["non_traduite"] = True

    def render(self, idx):
        pg = self.proj["pages"][idx]
        img = imread(pg["page"])
        bubbles = pg.get("bulles", [])
        tmask = None
        if pg.get("masque") and Path(pg["masque"]).exists():
            tmask = cv2.imread(pg["masque"], cv2.IMREAD_GRAYSCALE)
            if tmask is not None and tmask.shape != img.shape[:2]:
                tmask = None
        out = typeset(clean(img, bubbles, tmask), bubbles, self.font, self.upper)
        name = Path(pg["page"]).stem + (".jpg" if Path(pg["page"]).suffix.lower() in (".jpg", ".jpeg") else ".png")
        target = self.out / f"{idx + 1:04d}_{name}"
        imwrite(target, out)
        pg["sortie"] = str(target)
        save_project(self.out, self.proj)
        return target

    def prepare(self, idx, force=False):
        """Étape « processeur » : trouver le texte et le lire (peut tourner pendant que l'IA traduit)."""
        pg = self.proj["pages"][idx]
        t0 = time.monotonic()
        img = imread(pg["page"])
        if force or "bulles" not in pg or pg.get("det") != det_tag():
            keep = [b for b in pg.get("bulles", []) if b.get("manuel")]      # zones dessinées à la main
            zones, tmask = detect_all(img, rtl=self.src in ("ja", "auto"))
            pg["bulles"] = zones + keep
            pg["det"] = det_tag()
            pg.pop("masque", None)
            if tmask is not None:
                mdir = self.out / ".masques"
                mdir.mkdir(parents=True, exist_ok=True)
                mp = mdir / f"{idx + 1:04d}.png"
                cv2.imwrite(str(mp), tmask)
                pg["masque"] = str(mp)
        t1 = time.monotonic()
        bubbles = pg["bulles"]
        self.read_bubbles(img, bubbles, idx)
        # zones « douteuses » (vues hors bulle) : gardées seulement si on y a lu du vrai texte
        if not self.stop:
            pg["bulles"] = [b for b in bubbles if not b.get("douteux") or useful_text(b.get("original"))]
        self._time(pg, "détection", t1 - t0)
        self._time(pg, "lecture", time.monotonic() - t1)

    def finish(self, idx, contexte="", force=False):
        """Étape « carte graphique » : traduire puis écrire dans les bulles."""
        pg = self.proj["pages"][idx]
        bubbles = pg.get("bulles", [])
        t0 = time.monotonic()
        if force or any(b.get("original") and not b.get("traduction") for b in bubbles):
            self.translate(bubbles, contexte)
        t1 = time.monotonic()
        out = self.render(idx)
        pg.pop("erreur", None)
        self._time(pg, "traduction", t1 - t0)
        self._time(pg, "écriture", time.monotonic() - t1)
        return out

    def page(self, idx, contexte="", force=False):
        self.prepare(idx, force)
        if self.stop:
            return None
        return self.finish(idx, contexte, force)

    def _time(self, pg, step, sec):
        pg.setdefault("temps", {})[step] = round(sec, 1)
        self.stats[step] = self.stats.get(step, 0.0) + sec

    def summary(self):
        """« détection 12 s · lecture 40 s · traduction 3 min… » : où passe le temps."""
        tot = sum(self.stats.values())
        if tot < 1:
            return ""
        fmt = lambda s: f"{s:.0f} s" if s < 90 else f"{s / 60:.0f} min"
        parts = sorted(self.stats.items(), key=lambda kv: -kv[1])
        return " · ".join(f"{k} {fmt(v)} ({v * 100 / tot:.0f} %)" for k, v in parts if v >= 0.5)

    def check_model(self):
        """Avant tout le tome : on charge le modèle une fois (une erreur s'affiche tout de suite, pas 200 fois)."""
        msgs = [{"role": "user", "content": "Réponds seulement : OK"}]
        if self.model:
            self.comp.llm_model(self.model, msgs, timeout=600)
        elif not self.comp.ia_remote():
            self.comp.llm(msgs, timeout=600)
        fit = getattr(self.comp, "ollama_fit", None)
        if fit and (self.model or not self.comp.ia_remote()):
            self.note = fit(self.model or self.comp.cfg.get("ollama_model", "")) or ""

    def _done(self, i):
        pg = self.proj["pages"][i]
        return bool(pg.get("sortie") and Path(pg["sortie"]).exists() and pg.get("bulles") is not None
                    and pg.get("det") == det_tag())

    def run(self, progress=None, page_done=None, start=0):
        """Tout le tome. Pendant que l'IA traduit une page (carte graphique), la page suivante est déjà
        cherchée et lue (processeur). Avec une « IA qui voit » locale, on lit plusieurs pages d'affilée puis on
        les traduit d'affilée : sinon Ollama changerait de modèle à chaque page (très lent)."""
        contexte = ""
        self.fatal = ""
        n = len(self.pages)
        todo = [i for i in range(start, n)]
        ready = {}                                    # page -> None (prête) ou exception

        def after(i):
            nonlocal contexte
            if page_done:
                page_done(i)
            pg = self.proj["pages"][i]
            lines = [b.get("traduction", "") for b in pg.get("bulles", []) if b.get("traduction")]
            contexte = (contexte + " " + " / ".join(lines))[-700:]

        def finish_one(i):
            pg = self.proj["pages"][i]
            if progress:
                progress(i, n)
            err = ready.get(i)
            if err is None:
                try:
                    self.finish(i, contexte)
                except Exception as e:
                    err = e
            if err is not None:
                pg["erreur"] = repr(err)[:300]
                save_project(self.out, self.proj)
            after(i)

        try:
            try:
                if progress:
                    progress(-1, n)
                self.check_model()
                if self.note and progress:
                    progress(-2, n)
            except Exception as e:
                self.fatal = str(e)
                return
            swap = self.engine == "vision" and not self.comp.ia_remote()
            if swap:                                  # par paquets de pages : 2 changements de modèle par paquet
                CH = 8
                for k in range(0, len(todo), CH):
                    chunk = [i for i in todo[k:k + CH]]
                    for i in chunk:
                        if self.stop:
                            break
                        if self._done(i):
                            continue
                        if progress:
                            progress(i, n)
                        try:
                            self.prepare(i)
                            ready[i] = None
                        except Exception as e:
                            ready[i] = e
                    for i in chunk:
                        if self.stop:
                            break
                        if self._done(i):
                            after(i)
                            continue
                        finish_one(i)
            else:                                     # en parallèle : lecture en avance, traduction derrière
                import queue
                q = queue.Queue(maxsize=2)

                def put(x):
                    while True:
                        try:
                            return q.put(x, timeout=0.5)
                        except queue.Full:
                            if self.stop:
                                return

                def worker():
                    for i in todo:
                        if self.stop:
                            break
                        if not self._done(i):
                            try:
                                self.prepare(i)
                                ready[i] = None
                            except Exception as e:
                                ready[i] = e
                        put(i)
                    put(None)
                th = threading.Thread(target=worker, daemon=True)
                th.start()
                while True:
                    i = q.get()
                    if i is None or self.stop:
                        break
                    if self._done(i) and i not in ready:
                        after(i)
                        continue
                    finish_one(i)
                th.join(timeout=60)
            if progress:
                progress(n, n)
        finally:
            if self.ocr:
                self.ocr.close()
            shutil.rmtree(self.tmp, ignore_errors=True)


# ================================================================== fenêtre
def make_window(comp):
    from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
    from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
                                 QLabel, QListWidget, QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                                 QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

    STYLE = ("QWidget { background: #fffafc; color: #3d2733; font-size: 13px; }"
             "QPushButton { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; padding: 6px 11px; }"
             "QPushButton:hover { background: #fde7ef; } QPushButton:checked { background: #fbd3e4; }"
             "QPushButton#principal { background: #d6457f; color: white; border: none; font-weight: bold; }"
             "QListWidget, QTableWidget, QScrollArea { background: #fff; border: 1px solid #f1dfe8; "
             "border-radius: 10px; } QComboBox { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; "
             "padding: 4px 8px; } QProgressBar { border: 1px solid #f1dfe8; border-radius: 6px; background: #fff; "
             "text-align: center; } QProgressBar::chunk { background: #e889b0; border-radius: 6px; }")

    class Viewer(QLabel):
        zone = pyqtSignal(int, int, int, int)

        def __init__(self):
            super().__init__()
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pix = None
            self.scale = 1.0
            self.drawing = False
            self.p0 = self.p1 = None
            self.boxes = []

        def show_image(self, path, boxes=()):
            self.pix = QPixmap(str(path)) if path else None
            self.boxes = list(boxes)
            self.refit()

        def refit(self):
            if not self.pix or self.pix.isNull():
                self.setText("Ouvre un manga, un dossier d'images, un .cbz ou un PDF.")
                return
            w = max(200, self.parent().width() - 20) if self.parent() else 700
            self.scale = min(1.0, w / self.pix.width())
            self.setFixedSize(QSize(int(self.pix.width() * self.scale), int(self.pix.height() * self.scale)))
            self.update()

        def paintEvent(self, e):
            if not self.pix or self.pix.isNull():
                return super().paintEvent(e)
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(self.rect(), self.pix)
            p.setPen(QPen(QColor(214, 69, 127, 170), 2, Qt.PenStyle.DashLine))
            for i, b in enumerate(self.boxes):
                x, y, w, h = [v * self.scale for v in b["box"]]
                p.drawRect(QRect(int(x), int(y), int(w), int(h)))
                p.drawText(int(x) + 4, int(y) + 14, str(i + 1))
            if self.drawing and self.p0 and self.p1:
                p.setPen(QPen(QColor(214, 69, 127), 2))
                p.drawRect(QRect(self.p0, self.p1).normalized())
            p.end()

        def mousePressEvent(self, e):
            if self.drawing:
                self.p0 = self.p1 = e.position().toPoint()

        def mouseMoveEvent(self, e):
            if self.drawing and self.p0:
                self.p1 = e.position().toPoint()
                self.update()

        def mouseReleaseEvent(self, e):
            if self.drawing and self.p0:
                r = QRect(self.p0, e.position().toPoint()).normalized()
                self.p0 = self.p1 = None
                self.update()
                if r.width() > 8 and r.height() > 8:
                    s = self.scale
                    self.zone.emit(int(r.x() / s), int(r.y() / s), int(r.width() / s), int(r.height() / s))

    class Win(QWidget):
        prog = pyqtSignal(int, int)
        done_page = pyqtSignal(int)
        finished = pyqtSignal(object)
        dl_prog = pyqtSignal(int, int)
        dl_done = pyqtSignal(object)

        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("📖 Traduire un manga — " + comp.char.get("name", "Viki"))
            self.setStyleSheet(STYLE)
            self.resize(1280, 860)
            self.pipe = None
            self.src = None
            self.pages = []
            self.out = None
            self.cur = -1
            self.show_translated = True
            lay = QVBoxLayout(self)
            top = QHBoxLayout()
            ob = QPushButton("📂 Ouvrir…")
            m = QMenu(ob)
            m.addAction("Un fichier (.cbz, .zip, .cbr, .pdf, images)…", self.pick_files)
            m.addAction("Un dossier d'images…", self.pick_dir)
            ob.setMenu(m)
            top.addWidget(ob)
            self.title = QLabel("<i>Aucun manga ouvert</i>")
            top.addWidget(self.title, 1)
            top.addWidget(QLabel("De"))
            self.from_ = QComboBox()
            for k, v in SOURCES.items():
                self.from_.addItem(v, k)
            self.from_.setCurrentIndex(max(0, self.from_.findData(comp.cfg.get("manga_de", "ja"))))
            top.addWidget(self.from_)
            top.addWidget(QLabel("vers"))
            self.to = QComboBox()
            self.to.setProperty("no_i18n", True)        # le texte sert de langue d'arrivée
            self.to.addItems([c.capitalize() for c in CIBLES])
            self.to.setCurrentIndex(max(0, self.to.findText(comp.cfg.get("manga_vers", "Français"))))
            top.addWidget(self.to)
            top.addWidget(QLabel("Lecture"))
            self.eng = QComboBox()
            for lab, k in (("Automatique", "auto"), ("manga-ocr (japonais)", "mangaocr"),
                           ("IA qui voit", "vision"), ("Tesseract", "tesseract")):
                self.eng.addItem(lab, k)
            self.eng.setCurrentIndex(max(0, self.eng.findData(comp.cfg.get("manga_lecteur", "auto"))))
            top.addWidget(self.eng)
            top.addWidget(QLabel("Traduit par"))
            self.mod = QComboBox()
            self.mod.setMinimumWidth(230)
            self.mod.activated.connect(self.model_chosen)
            top.addWidget(self.mod)
            self.fill_models()
            self.upper = QCheckBox("MAJUSCULES")
            self.upper.setChecked(bool(comp.cfg.get("manga_majuscules", False)))
            top.addWidget(self.upper)
            self.go = QPushButton("▶ Traduire tout")
            self.go.setObjectName("principal")
            self.go.clicked.connect(self.start)
            top.addWidget(self.go)
            lay.addLayout(top)
            self.bar = QProgressBar()
            self.bar.hide()
            lay.addWidget(self.bar)
            self.state = QLabel("")
            self.state.setStyleSheet("color: #8d7482;")
            self.state.setWordWrap(True)
            lay.addWidget(self.state)
            sp = QSplitter()
            self.list = QListWidget()
            self.list.setMaximumWidth(190)
            self.list.currentRowChanged.connect(self.show_page)
            sp.addWidget(self.list)
            mid = QWidget()
            ml = QVBoxLayout(mid)
            ml.setContentsMargins(0, 0, 0, 0)
            vbar = QHBoxLayout()
            self.tog = QPushButton("👁 Voir l'original")
            self.tog.clicked.connect(self.toggle)
            vbar.addWidget(self.tog)
            self.zone_btn = QPushButton("➕ Ajouter une zone")
            self.zone_btn.setCheckable(True)
            self.zone_btn.setToolTip("Dessine un rectangle sur une bulle oubliée ou un texte hors bulle")
            self.zone_btn.toggled.connect(self.zone_mode)
            vbar.addWidget(self.zone_btn)
            self.det_btn = QPushButton(f"⬇️ Mieux trouver le texte ({DETECTOR_MB} Mo)")
            self.det_btn.setToolTip("Détecteur de texte de manga (comic-text-detector) : trouve aussi le texte hors "
                                    "des bulles, les bulles sombres, les cartouches et les onomatopées.\n"
                                    "Téléchargé une seule fois depuis GitHub, ensuite il tourne sur ton PC.")
            self.det_btn.clicked.connect(self.get_detector)
            self.det_btn.setVisible(not detector_ready())
            vbar.addWidget(self.det_btn)
            vbar.addStretch(1)
            ml.addLayout(vbar)
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(False)
            self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.view = Viewer()
            self.view.zone.connect(self.add_zone)
            self.scroll.setWidget(self.view)
            ml.addWidget(self.scroll, 1)
            sp.addWidget(mid)
            right = QWidget()
            rl = QVBoxLayout(right)
            rl.setContentsMargins(0, 0, 0, 0)
            self.table = QTableWidget(0, 2)
            self.table.setHorizontalHeaderLabels(["Original", "Traduction (modifiable)"])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.setWordWrap(True)
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            rl.addWidget(self.table, 1)
            for lab, fn in (("✏️ Redessiner la page", self.redraw), ("🔁 Retraduire la page", self.retranslate),
                            ("🙈 Ignorer la bulle choisie", self.ignore_bubble), ("🔊 Lire la page", self.read_page)):
                b = QPushButton(lab)
                b.clicked.connect(fn)
                rl.addWidget(b)
            sp.addWidget(right)
            sp.setSizes([170, 700, 400])
            lay.addWidget(sp, 1)
            bot = QHBoxLayout()
            for lab, fn in (("📂 Ouvrir le dossier traduit", self.open_out), ("📦 Exporter en .cbz", self.cbz)):
                b = QPushButton(lab)
                b.clicked.connect(fn)
                bot.addWidget(b)
            bot.addStretch(1)
            note = QLabel("Pour ton usage personnel : ne partage pas les traductions de scans d'œuvres protégées.")
            note.setStyleSheet("color: #9a8290; font-size: 11px;")
            bot.addWidget(note)
            lay.addLayout(bot)
            self.prog.connect(self.on_prog)
            self.done_page.connect(self.on_page)
            self.finished.connect(self.on_finished)
            self.dl_prog.connect(lambda g, t: self.state.setText(
                f"Téléchargement du détecteur de texte… {g * 100 // max(1, t)} %"))
            self.dl_done.connect(self.detector_done)

        # --- détecteur de texte
        def get_detector(self):
            if not DETECTOR_FILE:
                return
            self.det_btn.setEnabled(False)
            self.state.setText("Téléchargement du détecteur de texte…")

            def work():
                try:
                    self.dl_done.emit(download_detector(self.dl_prog.emit))
                except Exception as e:
                    self.dl_done.emit(e)
            threading.Thread(target=work, daemon=True).start()

        def detector_done(self, res):
            self.det_btn.setEnabled(True)
            if isinstance(res, Exception):
                self.state.setText(f"❌ Téléchargement impossible : {res}")
                return
            self.det_btn.hide()
            self.state.setText("✅ Détecteur installé : je trouve maintenant aussi le texte hors des bulles. "
                               "Clique sur « Traduire tout » : les pages déjà faites seront refaites avec.")
            comp.say("J'ai mes nouvelles lunettes pour lire les mangas : je vois aussi le texte hors des bulles !")
            proj = load_project(self.out) if self.out else None
            if proj:                                    # les pages déjà faites seront refaites avec
                for pg in proj.get("pages", []):
                    pg.pop("det", None)
                save_project(self.out, proj)

        # --- modèle de traduction
        def fill_models(self):
            self.mod.blockSignals(True)
            self.mod.clear()
            self.mod.addItem(f"Son cerveau ({comp.ia_name()})", "")
            have = comp.ollama_list()
            for n in have:
                star = " ⭐" if any(n == m[0] for m in MODELES) else ""
                self.mod.addItem(f"{n}{star}", n)
            missing = [m for m in MODELES if m[0] not in have]
            if missing:
                self.mod.insertSeparator(self.mod.count())
                for n, size, desc in missing:
                    self.mod.addItem(f"⬇️ {n} — {size} — {desc}", "pull:" + n)
            cur = comp.cfg.get("manga_modele", "")
            i = self.mod.findData(cur)
            self.mod.setCurrentIndex(i if i >= 0 else 0)
            self.mod.blockSignals(False)

        def model_chosen(self, _i):
            v = self.mod.currentData() or ""
            if v.startswith("pull:"):
                name = v[5:]
                info = next((m for m in MODELES if m[0] == name), (name, "?", ""))
                if QMessageBox.question(self, "Télécharger un modèle",
                                        f"Télécharger « {name} » ({info[1]}) ? Il reste sur ton PC et sert à "
                                        "traduire les mangas.") != QMessageBox.StandardButton.Yes:
                    return self.fill_models()
                self.state.setText(f"⬇️ Téléchargement de {name}… (tu peux continuer à lire)")
                comp.pull_model(name, then=lambda ok, n=name: (
                    comp.cfg.__setitem__("manga_modele", n) if ok else None, comp.save_cfg(),
                    self.fill_models(), self.state.setText(f"✅ {n} est prêt." if ok else f"❌ Échec : {n}")))
                return self.fill_models()
            comp.cfg["manga_modele"] = v
            comp.save_cfg()

        # --- ouverture
        def pick_files(self):
            files, _ = QFileDialog.getOpenFileNames(
                self, "Manga à traduire", str(Path.home()),
                "Manga (*.cbz *.zip *.cbr *.rar *.7z *.cb7 *.pdf *.jpg *.jpeg *.png *.webp *.avif *.bmp)")
            if files:
                self.load(files if len(files) > 1 else files[0])

        def pick_dir(self):
            d = QFileDialog.getExistingDirectory(self, "Dossier des pages", str(Path.home()))
            if d:
                self.load(d)

        def load(self, src):
            if self.pipe:
                return comp.say("Attends la fin de la traduction en cours (ou arrête-la).")
            self.src = src
            self.state.setText("Ouverture…")
            import hashlib
            first = Path(src[0] if isinstance(src, list) else src)
            try:
                sig = f"{first.resolve()}|{first.stat().st_mtime}|{len(src) if isinstance(src, list) else 1}"
            except Exception:
                sig = str(src)
            work = Path(tempfile.gettempdir()) / f"viki-manga-{hashlib.sha1(sig.encode()).hexdigest()[:12]}"
            try:
                self.pages = extract_pages(src, work)
            except Exception as e:
                return self.state.setText(f"❌ {e}")
            if not self.pages:
                return self.state.setText("❌ Aucune image trouvée là-dedans.")
            self.out = out_dir_for(src, self.to.currentText().lower())
            name = Path(src[0] if isinstance(src, list) else src).name
            self.title.setText(f"<b>{name}</b> — {len(self.pages)} page{'s' if len(self.pages) > 1 else ''}")
            self.list.clear()
            for i, p in enumerate(self.pages, 1):
                self.list.addItem(f"{i}. {Path(p).name[:22]}")
            proj = load_project(self.out)
            done = sum(1 for pg in (proj or {}).get("pages", []) if pg.get("sortie"))
            self.state.setText(f"Déjà traduites : {done} page(s) — clique sur « Traduire tout » pour continuer."
                               if done else "Prêt. Choisis les langues puis « Traduire tout ».")
            self.list.setCurrentRow(0)

        def proj(self):
            pr = load_project(self.out) if self.out else None
            if pr and len(pr.get("pages", [])) == len(self.pages):
                for pg, p in zip(pr["pages"], self.pages):     # chemins des pages de cette session
                    pg["page"] = str(p)
            return pr

        # --- traduction
        def engine(self):
            e = self.eng.currentData()
            src = self.from_.currentData()
            if e == "auto":
                if comp.manga_ocr_python() and src in ("ja", "auto"):
                    return "mangaocr"
                if comp.vision_ready():
                    return "vision"
                if tesseract_read and TESS.get("ja" if src == "auto" else src, "") in tesseract_langs():
                    return "tesseract"
                return None
            if e == "mangaocr" and not comp.manga_ocr_python():
                return None
            if e == "vision" and not comp.vision_ready():
                return None
            return e

        def make_pipe(self):
            eng = self.engine()
            if not eng:
                QMessageBox.information(self, "Lecture du texte", comp.manga_reader_help())
                return None
            for k, v in (("manga_de", self.from_.currentData()), ("manga_vers", self.to.currentText()),
                         ("manga_lecteur", self.eng.currentData()), ("manga_majuscules", self.upper.isChecked())):
                comp.cfg[k] = v
            comp.save_cfg()
            self.out = out_dir_for(self.src, self.to.currentText().lower())
            model = self.mod.currentData() or ""
            if model.startswith("pull:"):
                model = ""
            if not model and not comp.ollama_ok:
                comp.say_from("sans_ia")
                return None
            return Pipeline(comp, self.pages, self.out, self.from_.currentData(), self.to.currentText().lower(),
                            eng, comp.cfg.get("manga_police", ""), self.upper.isChecked(), model)

        def start(self):
            if self.pipe:
                self.pipe.stop = True
                self.go.setText("…arrêt après cette page")
                return
            if not self.pages:
                return self.pick_files()
            self.pipe = self.make_pipe()
            if not self.pipe:
                return
            self.go.setText("⏹ Arrêter")
            self.bar.show()
            self.bar.setRange(0, len(self.pages))
            comp.say(random_line("start"))
            pipe = self.pipe
            threading.Thread(target=lambda: (pipe.run(self.prog.emit, self.done_page.emit),
                                             self.finished.emit(pipe)), daemon=True).start()

        def on_prog(self, i, n):
            import time as _t
            if i == -1:
                self.note_txt = ""
                self.t_run = None
                self.state.setText("Je charge le modèle de traduction (la 1re fois, ça peut prendre une minute)…")
                return
            if i == -2:
                self.note_txt = (self.pipe.note if self.pipe else "") or ""
                self.state.setText("⚠️ " + self.note_txt)
                return
            self.bar.setValue(i)
            eng = {"mangaocr": "manga-ocr", "vision": "IA qui voit", "tesseract": "Tesseract"}.get(
                self.pipe.engine if self.pipe else "", "")
            now = _t.monotonic()
            if self.t_run is None:
                self.t_run, self.i_run = now, i
            eta = ""
            k = i - self.i_run
            if k >= 1 and i < n:
                per = (now - self.t_run) / k
                left = per * (n - i)
                eta = (f" — ≈ {per:.0f} s par page, encore ~{left / 60:.0f} min" if left >= 90 else
                       f" — ≈ {per:.0f} s par page, encore ~{left:.0f} s")
            txt = (f"Page {min(i + 1, n)} / {n} — lecture ({eng}), traduction, mise en bulles…{eta}"
                   if i < n else "Terminé !")
            if getattr(self, "note_txt", ""):
                txt += "\n⚠️ " + self.note_txt
            self.state.setText(txt)

        def on_page(self, i):
            st = getattr(comp, "stat", None)
            if st and self.pipe:
                st("pages_manga")
            if self.cur in (i, -1) or self.list.currentRow() == i - 1:
                self.list.setCurrentRow(i)
            else:
                self.show_page(self.list.currentRow())

        def on_finished(self, pipe):
            self.pipe = None
            self.go.setText("▶ Traduire tout")
            self.bar.hide()
            if getattr(pipe, "fatal", ""):
                self.state.setText("❌ Je n'ai pas pu commencer : " + pipe.fatal)
                comp.say("Je n'arrive pas à utiliser ce modèle pour traduire. Je t'ai mis l'explication dans la "
                         "fenêtre du manga.")
                return
            proj = load_project(pipe.out) or {}
            errs = [pg for pg in proj.get("pages", []) if pg.get("erreur")]
            done = sum(1 for pg in proj.get("pages", []) if pg.get("sortie"))
            spent = pipe.summary()
            tip = ""
            if spent and max(pipe.stats, key=pipe.stats.get) == "traduction":
                tip = (" Astuce : c'est la traduction qui prend le plus de temps → un modèle plus petit qui tient "
                       "dans ta carte graphique (7-8 milliards de paramètres) va bien plus vite.")
            elif spent and max(pipe.stats, key=pipe.stats.get) == "lecture" and pipe.engine == "vision":
                tip = " Astuce : pour le japonais, manga-ocr lit les bulles bien plus vite que l'IA qui voit."
            nt = sum(1 for pg in proj.get("pages", []) for b in pg.get("bulles", []) if b.get("non_traduite"))
            self.state.setText(f"✅ {done} page(s) traduite(s) dans « {pipe.out.name} »."
                               + (f" ⚠️ {len(errs)} page(s) en erreur : {errs[0]['erreur'][:350]}" if errs else "")
                               + (f" · {nt} bulle(s) laissée(s) en version originale (l'IA n'a rien donné de "
                                  f"correct) : corrige-les à droite ou « Retraduire »." if nt else "")
                               + (f"\n⏱ Temps : {spent}." + tip if spent else ""))
            comp.say(f"J'ai fini ! {done} page{'s' if done > 1 else ''} traduite{'s' if done > 1 else ''}. "
                     "Tu peux corriger une bulle à droite si besoin.")
            comp._notify("Manga traduit", f"{done} page(s) — {pipe.out.name}")
            self.show_page(self.list.currentRow())

        # --- affichage / corrections
        def page_data(self, i):
            proj = self.proj()
            if proj and 0 <= i < len(proj.get("pages", [])):
                return proj, proj["pages"][i]
            return proj, None

        def show_page(self, i):
            self.cur = i
            if i < 0 or i >= len(self.pages):
                return
            proj, pg = self.page_data(i)
            translated = pg and pg.get("sortie") and Path(pg["sortie"]).exists()
            path = pg["sortie"] if translated and self.show_translated else str(self.pages[i])
            self.view.show_image(path, (pg or {}).get("bulles", []) if not self.show_translated or not translated
                                 else [])
            self.tog.setText("👁 Voir l'original" if self.show_translated else "👁 Voir la traduction")
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            for b in (pg or {}).get("bulles", []):
                r = self.table.rowCount()
                self.table.insertRow(r)
                a = QTableWidgetItem(b.get("original", "") or ("(erreur)" if b.get("erreur") else ""))
                a.setFlags(a.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t = QTableWidgetItem("🙈 ignorée" if b.get("ignore") else b.get("traduction", ""))
                self.table.setItem(r, 0, a)
                self.table.setItem(r, 1, t)
            self.table.resizeRowsToContents()
            self.table.blockSignals(False)
            if pg and pg.get("erreur"):
                self.state.setText(f"⚠️ Page {i + 1} : {pg['erreur'][:200]}")

        def read_page(self):
            """Elle lit la traduction de la page, bulle par bulle (dans l'ordre de lecture)."""
            proj, pg = self.page_data(self.cur)
            if not pg:
                return
            lines = []
            for b in pg.get("bulles", []):
                t = (b.get("traduction") or "").strip()
                if t and not b.get("ignore"):
                    lines.append(t)
            if not lines:
                return comp.say("Il n'y a rien de traduit sur cette page.")
            comp.read_aloud("\n".join(lines))

        def toggle(self):
            self.show_translated = not self.show_translated
            self.show_page(self.cur)

        def _edit_pipe(self):
            if self.pipe:
                comp.say("Attends la fin de la traduction pour corriger.")
                return None
            p = self.make_pipe()
            return p

        def _collect_edits(self, pg):
            for r, b in enumerate(pg.get("bulles", [])):
                it = self.table.item(r, 1)
                if it and not b.get("ignore"):
                    b["traduction"] = it.text().strip()

        def redraw(self):
            proj, pg = self.page_data(self.cur)
            if not pg:
                return
            pipe = self._edit_pipe()
            if not pipe:
                return
            self._collect_edits(pipe.proj["pages"][self.cur])
            pipe.render(self.cur)
            self.show_translated = True
            self.show_page(self.cur)

        def retranslate(self):
            pipe = self._edit_pipe()
            if not pipe:
                return
            i = self.cur
            self.state.setText(f"Je refais la page {i + 1}…")

            def work():
                pg = pipe.proj["pages"][i]
                for b in pg.get("bulles", []):
                    b.pop("traduction", None)
                pipe.page(i)
            comp._bg(work, lambda r: (self.show_page(i), self.state.setText(
                f"Page {i + 1} refaite." if not isinstance(r, Exception) else f"❌ {r}")))

        def ignore_bubble(self):
            r = self.table.currentRow()
            pipe = self._edit_pipe()
            if r < 0 or not pipe:
                return
            pg = pipe.proj["pages"][self.cur]
            if r < len(pg.get("bulles", [])):
                pg["bulles"][r]["ignore"] = not pg["bulles"][r].get("ignore")
                pipe.render(self.cur)
                self.show_page(self.cur)

        def zone_mode(self, on):
            self.view.drawing = on
            if on:
                self.show_translated = False
                self.show_page(self.cur)
                self.state.setText("Dessine un rectangle autour du texte oublié.")

        def add_zone(self, x, y, w, h):
            self.zone_btn.setChecked(False)
            pipe = self._edit_pipe()
            if not pipe:
                return
            i = self.cur
            pg = pipe.proj["pages"][i]
            img = imread(pg["page"])
            pg.setdefault("bulles", []).append(manual_zone(img, x, y, w, h))
            self.state.setText("Je lis et je traduis cette zone…")

            def work():
                pipe.read_bubbles(img, pg["bulles"], i)
                pipe.translate(pg["bulles"])
                pipe.render(i)
            comp._bg(work, lambda r: (setattr(self, "show_translated", True), self.show_page(i),
                                      self.state.setText("Zone ajoutée." if not isinstance(r, Exception)
                                                         else f"❌ {r}")))

        def open_out(self):
            if self.out and Path(self.out).exists():
                subprocess.Popen(["xdg-open", str(self.out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def cbz(self):
            if not self.out or not Path(self.out).exists():
                return comp.say("Traduis d'abord quelques pages.")
            t = export_cbz(self.out)
            self.state.setText(f"📦 Exporté : {t}")
            comp.say("C'est exporté en .cbz, à côté du dossier traduit !")

        def resizeEvent(self, e):
            super().resizeEvent(e)
            QTimer.singleShot(0, self.view.refit)

        def showEvent(self, e):                      # modèles téléchargés / réglages changés entre-temps
            super().showEvent(e)
            QTimer.singleShot(0, self.fill_models)
            i = self.eng.findData(comp.cfg.get("manga_lecteur", "auto"))
            if i >= 0:
                self.eng.setCurrentIndex(i)

        def closeEvent(self, e):
            if self.pipe:
                self.pipe.stop = True
            super().closeEvent(e)

    def random_line(kind):
        import random
        return random.choice(["C'est parti ! Je lis les bulles et je traduis page par page.",
                              "Je m'y mets ! Ça peut prendre un moment par page."])

    return Win()
