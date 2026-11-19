"""Personnage animé : un GIF, un WebP animé, un APNG ou une vidéo (MP4, WebM…) devient une suite d'images
transparentes. Tout se fait sur le PC (Qt pour GIF/WebP, ffmpeg pour les vidéos)."""
import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter

EXT_IMG = {".gif", ".webp", ".apng"}
EXT_VID = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}
MAX_FRAMES, MAX_FPS, MAX_H = 150, 15, 640


def is_animated(path):
    """Ce fichier est-il une animation que je sais lire ?"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in EXT_VID or ext == ".apng":
        return True
    if ext in (".gif", ".webp"):
        r = QImageReader(str(p))
        return r.supportsAnimation() and r.imageCount() != 1
    if ext == ".png":                                   # un .png peut être un APNG
        try:
            return b"acTL" in open(p, "rb").read(4096)
        except Exception:
            return False
    return False


def ffmpeg_exe():
    return shutil.which("ffmpeg")


def _env():
    env = dict(os.environ)
    if os.environ.get("APPIMAGE"):
        env["LD_LIBRARY_PATH"] = os.environ.get("COMPAGNON_ORIG_LD", "")
    return env


def _frames_qt(path, st):
    r = QImageReader(str(path))
    r.setDecideFormatFromContent(True)
    n = r.imageCount()
    frames, delays = [], []
    step = max(1, (n + MAX_FRAMES - 1) // MAX_FRAMES) if n > 0 else 1
    i = 0
    while True:
        img = r.read()
        if img.isNull():
            break
        d = r.nextImageDelay() or 80
        if i % step == 0:
            frames.append(img.convertToFormat(QImage.Format.Format_ARGB32))
            delays.append(d * step)
        i += 1
        st["pct"] = min(60, int(60 * i / max(1, n))) if n > 0 else 30
        if st.get("stop"):
            raise RuntimeError("annulé")
        if len(frames) >= MAX_FRAMES or not r.canRead():
            break
    if len(frames) < 2:
        raise RuntimeError("je n'ai trouvé qu'une seule image dans ce fichier : importe-le comme une image normale")
    fps = max(2.0, min(30.0, 1000.0 / (sum(delays) / len(delays))))
    return frames, fps


def _frames_ffmpeg(path, tmp, st, key=None):
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("pour lire une vidéo, il me faut « ffmpeg » (sous Arch : sudo pacman -S ffmpeg)")
    tmp.mkdir(parents=True, exist_ok=True)
    vf = f"fps={MAX_FPS},scale=-2:'min({MAX_H},ih)':flags=lanczos"
    if key:
        vf += f",colorkey=0x{key.lstrip('#')}:0.28:0.08"
    vf += ",format=rgba"
    pre = []
    if Path(path).suffix.lower() == ".webm":            # décodeur qui garde la transparence des WebM
        for codec in ("libvpx-vp9", "libvpx"):
            pre = ["-c:v", codec]
            r = subprocess.run([exe, "-v", "error", "-y", *pre, "-i", str(path), "-vf", vf, "-frames:v",
                                str(MAX_FRAMES), str(tmp / "f%03d.png")], capture_output=True, text=True, env=_env())
            if r.returncode == 0 and any(tmp.glob("f*.png")):
                break
            for f in tmp.glob("f*.png"):
                f.unlink()
            pre = []
    if not any(tmp.glob("f*.png")):
        r = subprocess.run([exe, "-v", "error", "-y", "-i", str(path), "-vf", vf, "-frames:v", str(MAX_FRAMES),
                            str(tmp / "f%03d.png")], capture_output=True, text=True, env=_env())
        if r.returncode != 0:
            raise RuntimeError("ffmpeg n'a pas réussi à lire ce fichier : " + (r.stderr.strip().splitlines() or ["?"])[-1][:160])
    st["pct"] = 60
    files = sorted(tmp.glob("f*.png"))
    if len(files) < 2:
        raise RuntimeError("je n'ai pas trouvé d'animation dans ce fichier")
    frames = [QImage(str(f)).convertToFormat(QImage.Format.Format_ARGB32) for f in files]
    return frames, float(MAX_FPS)


def corner_key(img):
    """Si les 4 coins ont la même couleur unie et opaque, c'est sûrement le fond : renvoie « #rrggbb », sinon None."""
    w, h = img.width(), img.height()
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3), (w // 2, 2)]
    cols = [img.pixelColor(x, y) for x, y in pts]
    if any(c.alpha() < 250 for c in cols):
        return None
    c0 = cols[0]
    if all(abs(c.red() - c0.red()) + abs(c.green() - c0.green()) + abs(c.blue() - c0.blue()) < 36 for c in cols):
        return c0.name()
    return None


def _key_out(frames, key, st):
    """Rend transparente la couleur de fond (GIF/WebP sans transparence). numpy si possible."""
    c = QColor(key)
    try:
        import numpy as np
    except Exception:
        np = None
    out = []
    for i, img in enumerate(frames):
        if np is not None:
            w, h = img.width(), img.height()
            a = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), np.uint8).reshape(
                h, img.bytesPerLine())[:, :w * 4].reshape(h, w, 4).copy()
            d = (np.abs(a[:, :, 2].astype(int) - c.red()) + np.abs(a[:, :, 1].astype(int) - c.green())
                 + np.abs(a[:, :, 0].astype(int) - c.blue()))
            alpha = np.clip((d - 40) * 6, 0, 255).astype(np.uint8)
            a[:, :, 3] = np.minimum(a[:, :, 3], alpha)
            for k in range(3):                               # prémultiplié propre sur les bords
                a[:, :, k] = (a[:, :, k].astype(int) * (a[:, :, 3] > 0)).astype(np.uint8)
            q = QImage(a.tobytes(), w, h, w * 4, QImage.Format.Format_ARGB32).copy()
            out.append(q)
        else:
            out.append(img)
        st["pct"] = 60 + int(15 * (i + 1) / len(frames))
    return out


def _has_alpha(img):
    if not img.hasAlphaChannel():
        return False
    w, h = img.width(), img.height()
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2), (w // 2, 1), (1, h // 2), (w - 2, h // 2)):
        if img.pixelColor(x, y).alpha() < 200:
            return True
    return False


def _union_bbox(frames):
    """Le plus petit cadre qui contient le personnage sur toutes les images."""
    try:
        import numpy as np
    except Exception:
        return None
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for img in frames:
        w, h = img.width(), img.height()
        a = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), np.uint8).reshape(
            h, img.bytesPerLine())[:, :w * 4].reshape(h, w, 4)[:, :, 3]
        ys, xs = np.where(a > 12)
        if len(xs):
            x0, y0, x1, y1 = min(x0, xs.min()), min(y0, ys.min()), max(x1, xs.max()), max(y1, ys.max())
    if x1 < 0:
        return None
    return QRect(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))


def importer(path, outdir, st, key="auto"):
    """Découpe l'animation en images dans outdir (f000.png…). key : « auto », None, ou « #rrggbb » (fond à effacer).
    -> {"n", "fps", "premiere": QImage, "union": QImage (toutes les poses superposées), "fond": couleur effacée ou None}"""
    path, outdir = Path(path), Path(outdir)
    ext = path.suffix.lower()
    st["msg"] = "Je découpe l'animation…"
    tmp = outdir.parent / (outdir.name + "-tmp")
    fond = None
    try:
        if ext in EXT_VID or ext in (".apng", ".png"):
            frames, fps = _frames_ffmpeg(path, tmp, st, key if key not in (None, "auto") else None)
            if key == "auto" and not _has_alpha(frames[0]):
                k = corner_key(frames[0])
                if k:                                        # fond uni détecté : on refait avec ce fond effacé
                    shutil.rmtree(tmp, ignore_errors=True)
                    frames, fps = _frames_ffmpeg(path, tmp, st, k)
                    fond = k
            elif key not in (None, "auto"):
                fond = key
        else:
            frames, fps = _frames_qt(path, st)
            k = key
            if key == "auto":
                k = None if _has_alpha(frames[0]) else corner_key(frames[0])
            if k:
                st["msg"] = "J'efface le fond…"
                frames = _key_out(frames, k, st)
                fond = k
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # taille raisonnable
    if frames[0].height() > MAX_H:
        frames = [f.scaledToHeight(MAX_H, Qt.TransformationMode.SmoothTransformation) for f in frames]
    box = _union_bbox(frames)
    if box is not None and (box.width() < frames[0].width() - 4 or box.height() < frames[0].height() - 4):
        m = 4
        box = box.adjusted(-m, -m, m, m).intersected(frames[0].rect())
        frames = [f.copy(box) for f in frames]
    if st.get("stop"):
        raise RuntimeError("annulé")
    outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.glob("f*.png"):
        f.unlink()
    union = QImage(frames[0].size(), QImage.Format.Format_ARGB32)
    union.fill(Qt.GlobalColor.transparent)
    p = QPainter(union)
    for i, f in enumerate(frames):
        f.save(str(outdir / f"f{i:03d}.png"))
        p.drawImage(0, 0, f)
        st["pct"] = 78 + int(22 * (i + 1) / len(frames))
    p.end()
    return {"n": len(frames), "fps": round(fps, 2), "premiere": frames[0], "union": union, "fond": fond}


def charger(dossier, n):
    """Relit les images d'une animation. -> liste de QImage (vide si un fichier manque)."""
    out = []
    for i in range(int(n)):
        img = QImage(str(Path(dossier) / f"f{i:03d}.png"))
        if img.isNull():
            return []
        out.append(img)
    return out
