#!/usr/bin/env python3
"""Qualité visuelle du compagnon : netteté par IA (Real-ESRGAN, local, carte graphique via Vulkan)
et expressions du visage à partir d'images (joie, tristesse, surprise…)."""
import json
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QRadialGradient

import os
APP_DIR = Path(__file__).resolve().parent
import sys as _sys
if _sys.platform == "win32" and getattr(_sys, "frozen", False):
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Compagnon"
else:
    DATA_DIR = (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "compagnon"
                if (os.environ.get("APPIMAGE") or os.environ.get("COMPAGNON_PORTABLE")) else APP_DIR)
EXPRESSIONS = {"joie": "Joie (grand sourire)", "triste": "Tristesse", "boude": "Boude / fâchée",
               "surprise": "Surprise", "timide": "Timide (rougit)"}


# ================================================================ netteté (Real-ESRGAN)
def find_upscaler():
    for cand in (DATA_DIR / "tools" / "realesrgan" / "realesrgan-ncnn-vulkan.exe",
                 DATA_DIR / "tools" / "realesrgan" / "realesrgan-ncnn-vulkan",
                 APP_DIR / "tools" / "realesrgan" / "realesrgan-ncnn-vulkan"):
        if cand.exists():
            return str(cand)
    return shutil.which("realesrgan-ncnn-vulkan")


def upscale_file(src, dst, factor=2):
    """Agrandit une image avec le modèle anime (x4) puis la ramène à `factor` : traits nets, sans flou."""
    exe = find_upscaler()
    if not exe:
        raise RuntimeError("Real-ESRGAN n'est pas installé (bash installer_nettete.sh).")
    tmp = str(dst) + ".x4.png"
    models = Path(exe).parent / "models"
    cmd = [exe, "-i", str(src), "-o", tmp, "-n", "realesrgan-x4plus-anime", "-s", "4", "-t", "256"]
    if models.exists():
        cmd += ["-m", str(models)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not Path(tmp).exists():
        raise RuntimeError("Real-ESRGAN a échoué : " + (r.stderr or r.stdout)[-300:])
    big = QImage(tmp)
    orig = QImage(str(src))
    w, h = orig.width() * factor, orig.height() * factor
    out = big.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if not big.hasAlphaChannel() and orig.hasAlphaChannel():     # ancienne version : on remet la transparence
        a = orig.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32)
        out = out.convertToFormat(QImage.Format.Format_ARGB32)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, a)
        p.end()
    out.save(str(dst))
    Path(tmp).unlink(missing_ok=True)
    return factor


def _scale_calib(d, f):
    """Multiplie les coordonnées d'un character.json / tenue.json par f."""
    for e in d.get("eyes", []):
        for k in ("x", "y", "w", "h"):
            if k in e:
                e[k] = round(e[k] * f)
    m = d.get("mouth")
    if m:
        for k in ("x", "y", "w", "max_open"):
            if k in m:
                m[k] = round(m[k] * f)
    sk = d.get("skin_sample")
    if sk:
        sk["x"], sk["y"] = round(sk["x"] * f), round(sk["y"] * f)
    for z in d.get("zones", []) or []:
        for k in ("cx", "cy", "r", "x", "y", "w", "h"):
            if k in z:
                z[k] = round(z[k] * f)
    if d.get("scale"):
        d["scale"] = round(d["scale"] / f, 4)
    return d


def upscale_character(cdir, make_hitmask, progress=None):
    """Rend tout un personnage (image de base, tenues, expressions) 2 fois plus net.
    Une copie de l'original est gardée dans original/ (pour annuler)."""
    cdir = Path(cdir)
    data = json.loads((cdir / "character.json").read_text())
    if data.get("nettete"):
        raise RuntimeError("Ce personnage est déjà en haute qualité.")
    backup = cdir / "original"
    if not backup.exists():
        backup.mkdir()
        for p in cdir.rglob("*"):
            if p.is_file() and backup not in p.parents:
                dst = backup / p.relative_to(cdir)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
    jobs = [(cdir / "character.json", cdir)]
    for tj in sorted((cdir / "tenues").glob("*/tenue.json")) if (cdir / "tenues").exists() else []:
        jobs.append((tj, tj.parent))
    for i, (jf, d) in enumerate(jobs):
        cal = json.loads(jf.read_text())
        img = d / cal.get("image", "character.png")
        if progress:
            progress(f"Netteté : image {i + 1} sur {len(jobs)}…")
        f = upscale_file(img, img, 2)
        hm = make_hitmask(QImage(str(img)))
        hm.save(str(d / cal.get("hitmask", "hitmask.png")))
        cal = _scale_calib(cal, f)
        if jf.name == "character.json":
            cal["nettete"] = True
            for emo, rel in (cal.get("expressions") or {}).items():
                pp = d / rel
                if pp.exists():
                    q = QImage(str(pp))
                    q.scaled(q.width() * f, q.height() * f, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation).save(str(pp))
        jf.write_text(json.dumps(cal, indent=2, ensure_ascii=False))
    return len(jobs)


def undo_upscale(cdir):
    cdir = Path(cdir)
    backup = cdir / "original"
    if not backup.exists():
        return False
    for p in backup.rglob("*"):
        if p.is_file():
            dst = cdir / p.relative_to(backup)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    shutil.rmtree(backup)
    return True


# ================================================================ expressions
def _np():
    try:
        import numpy as np
        return np
    except Exception:
        return None


def _to_np(img, np):
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    return arr[:, :img.width()].astype(np.float32)


def _bbox(img):
    """Cadre des pixels visibles (rapide : sur une petite copie)."""
    k = max(1, img.height() // 300)
    small = img.scaled(max(1, img.width() // k), max(1, img.height() // k))
    xs, ys = [], []
    for y in range(small.height()):
        for x in range(small.width()):
            if small.pixelColor(x, y).alpha() > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs) * k, min(ys) * k, (max(xs) + 1) * k, (max(ys) + 1) * k)


def align_expression(base, expr, eyes, mouth):
    """Recale l'image d'expression sur l'image de base et ne garde que le visage (bords fondus).
    Renvoie une image de la taille de la base, transparente hors du visage."""
    bb, be = _bbox(base), _bbox(expr)
    if not bb or not be:
        raise RuntimeError("Image vide après détourage.")
    s = (bb[3] - bb[1]) / max(1, be[3] - be[1])
    if not 0.3 < s < 3.5:
        raise RuntimeError("Le cadrage est trop différent de l'image de base.")
    ew, eh = int(expr.width() * s), int(expr.height() * s)
    ex = expr.scaled(ew, eh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    # recalage grossier : haut de la tête et centre alignés
    ox = (bb[0] + bb[2]) / 2 - (be[0] + be[2]) / 2 * s
    oy = bb[1] - be[1] * s
    cx = (eyes[0]["x"] + eyes[1]["x"]) / 2
    ey = (eyes[0]["y"] + eyes[1]["y"]) / 2
    d = max(12.0, abs(eyes[1]["x"] - eyes[0]["x"]))
    my = mouth["y"]
    np = _np()
    if np is not None:                       # recalage fin sur le visage (contours des cheveux, joues…)
        B = _to_np(base, np)
        E = _to_np(ex, np)
        x0, x1 = int(cx - 1.7 * d), int(cx + 1.7 * d)
        y0, y1 = int(ey - 1.6 * d), int(my + 0.9 * d)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(base.width(), x1), min(base.height(), y1)
        gB = B[y0:y1, x0:x1, :3].mean(2)
        aB = B[y0:y1, x0:x1, 3] > 128
        best = (1e18, 0, 0)
        r = int(max(6, 0.5 * d))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                sx, sy = int(round(x0 - ox - dx)), int(round(y0 - oy - dy))
                if sx < 0 or sy < 0 or sx + (x1 - x0) > E.shape[1] or sy + (y1 - y0) > E.shape[0]:
                    continue
                seg = E[sy:sy + (y1 - y0), sx:sx + (x1 - x0)]
                m = aB & (seg[:, :, 3] > 128)
                n = m.sum()
                if n < 0.3 * aB.sum():
                    continue
                err = float(np.abs(seg[:, :, :3].mean(2) - gB)[m].mean()) + 40.0 * (1 - n / max(1, aB.sum()))
                if err < best[0]:
                    best = (err, dx, dy)
        ox += best[1]
        oy += best[2]
    # visage seul, bords fondus
    patch = QImage(base.size(), QImage.Format.Format_ARGB32_Premultiplied)
    patch.fill(Qt.GlobalColor.transparent)
    p = QPainter(patch)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QPointF(ox, oy), ex)
    p.end()
    mask = QImage(base.size(), QImage.Format.Format_ARGB32_Premultiplied)
    mask.fill(Qt.GlobalColor.transparent)
    fc = QPointF(cx, (ey + my) / 2)
    g = QRadialGradient(QPointF(0, 0), 1.0)
    g.setColorAt(0.0, QColor(0, 0, 0, 255))
    g.setColorAt(0.72, QColor(0, 0, 0, 255))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.translate(fc)
    mp.scale(1.35 * d, 1.5 * d)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(g)
    mp.drawEllipse(QPointF(0, 0), 1.0, 1.0)
    mp.end()
    p = QPainter(patch)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawImage(0, 0, mask)
    p.end()
    return patch


def compose(base, patch):
    out = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(out)
    p.drawImage(0, 0, patch)
    p.end()
    return out


def simple_cutout(img, tol=26):
    """Détourage simple d'une image à fond uni (le fond touchant les bords devient transparent)."""
    np = _np()
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    if np is None:
        return img
    a = _to_np(img, np)
    h, w = a.shape[:2]
    border = np.concatenate([a[0, :, :3], a[-1, :, :3], a[:, 0, :3], a[:, -1, :3]])
    bg = np.median(border, axis=0)
    cand = np.sqrt(((a[:, :, :3] - bg) ** 2).sum(2)) < tol
    m = np.zeros_like(cand)
    m[0, :], m[-1, :], m[:, 0], m[:, -1] = cand[0, :], cand[-1, :], cand[:, 0], cand[:, -1]
    try:                                      # rapide si scipy est là
        from scipy import ndimage
        lab, _n = ndimage.label(cand)
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        m = np.isin(lab, list(edge))
        loops = 0
    except Exception:
        loops = 4000
    for _ in range(loops):                    # remplissage depuis les bords
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        g &= cand
        if (g == m).all():
            break
        m = g
    out = a.copy()
    out[:, :, 3] = np.where(m, 0, out[:, :, 3])
    out = np.ascontiguousarray(out.astype(np.uint8))
    q = QImage(out.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return q.copy()
