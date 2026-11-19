"""Les couleurs de ton fond d'écran -> la couleur de Viki (fenêtres, menus, ronds).
Trouve l'image du fond sur KDE, GNOME (et Ubuntu, Budgie, Pantheon), Cinnamon, MATE et Xfce. Sinon : tu la choisis.
Tout se passe sur ton PC."""
import colorsys
import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


def _chemin(v):
    v = (v or "").strip().strip("'\"")
    if v.startswith("file://"):
        v = unquote(urlparse(v).path)
    p = Path(os.path.expanduser(v)) if v else None
    if p and p.suffix.lower() == ".xml" and p.exists():          # diaporama GNOME : on prend la 1re image
        m = re.search(r"<file>\s*([^<]+?)\s*</file>", p.read_text(errors="ignore"))
        p = Path(m.group(1)) if m else None
    if p and p.is_dir():                                          # dossier (diaporama KDE) : la plus récente
        imgs = sorted((x for x in p.rglob("*") if x.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")),
                      key=lambda x: -x.stat().st_mtime)
        p = imgs[0] if imgs else None
    return p if p and p.is_file() else None


def _gsettings(schema, key):
    if not shutil.which("gsettings"):
        return ""
    try:
        r = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True, timeout=4)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def chemin_fond(cfg=None):
    """Le fichier image du fond d'écran, ou None."""
    perso = (cfg or {}).get("fond_image", "")
    if perso and Path(perso).is_file():
        return Path(perso)
    bureau = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in bureau or os.environ.get("KDE_FULL_SESSION"):
        f = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
        if f.exists():
            try:
                txt = f.read_text(errors="ignore")
                for m in re.finditer(r"\[Wallpaper\]\[org\.kde\.image\]\[General\][^\[]*?^Image=(.+)$", txt, re.M | re.S):
                    p = _chemin(m.group(1))
                    if p:
                        return p
                for m in re.finditer(r"^(?:Image|SlidePaths)=(.+)$", txt, re.M):
                    p = _chemin(m.group(1).split(",")[0])
                    if p:
                        return p
            except Exception:
                pass
    if "CINNAMON" in bureau:
        p = _chemin(_gsettings("org.cinnamon.desktop.background", "picture-uri"))
        if p:
            return p
    if "MATE" in bureau:
        p = _chemin(_gsettings("org.mate.background", "picture-filename"))
        if p:
            return p
    if "XFCE" in bureau and shutil.which("xfconf-query"):
        try:
            r = subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-l"], capture_output=True, text=True,
                               timeout=4)
            for prop in [l for l in r.stdout.splitlines() if l.endswith("last-image")]:
                v = subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-p", prop], capture_output=True,
                                   text=True, timeout=4).stdout
                p = _chemin(v)
                if p:
                    return p
        except Exception:
            pass
    # GNOME et compagnie (et en dernier recours pour les autres)
    sombre = "dark" in _gsettings("org.gnome.desktop.interface", "color-scheme")
    for key in (("picture-uri-dark", "picture-uri") if sombre else ("picture-uri", "picture-uri-dark")):
        p = _chemin(_gsettings("org.gnome.desktop.background", key))
        if p:
            return p
    return None


def couleur_dominante(path):
    """La couleur vive la plus présente de l'image (#rrggbb), assez douce pour des boutons et des menus."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtCore import Qt
    img = QImage(str(path))
    if img.isNull():
        return ""
    img = img.scaled(90, 90, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    bacs = [[0.0, 0.0, 0.0, 0.0] for _ in range(36)]          # poids, r, g, b
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            r, g, b = c.redF(), c.greenF(), c.blueF()
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            if s < 0.22 or v < 0.2 or v > 0.98:
                continue
            w = s * v
            k = int(h * 36) % 36
            bacs[k][0] += w
            bacs[k][1] += r * w
            bacs[k][2] += g * w
            bacs[k][3] += b * w
    best = max(range(36), key=lambda k: bacs[k][0] + 0.6 * (bacs[k - 1][0] + bacs[(k + 1) % 36][0]))
    w, r, g, b = bacs[best]
    if w <= 0.5:                                                 # image presque grise : un bleu doux
        return "#5b7bd5"
    r, g, b = r / w, g / w, b / w
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.45, min(0.6, l))
    s = max(0.55, min(0.85, s * 1.15))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def palette(path, n=4):
    """Quelques couleurs de l'image (pour l'aperçu dans les réglages)."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtCore import Qt
    img = QImage(str(path))
    if img.isNull():
        return []
    img = img.scaled(40, 40, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    vus = {}
    for y in range(0, 40, 2):
        for x in range(0, 40, 2):
            c = img.pixelColor(x, y)
            k = (c.red() // 48, c.green() // 48, c.blue() // 48)
            vus[k] = vus.get(k, 0) + 1
    top = sorted(vus, key=lambda k: -vus[k])[:n]
    return ["#%02x%02x%02x" % (min(255, a * 48 + 24), min(255, b * 48 + 24), min(255, c * 48 + 24)) for a, b, c in top]
