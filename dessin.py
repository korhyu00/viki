"""✏️ Le carnet de dessin de Viki : on dessine ce qu'on veut (calques, symétrie, silhouette guide, image à
décalquer, tablette graphique), on enregistre en PNG ou en .ora (ouvrable dans Krita, GIMP…), et si on veut, le
dessin devient un nouveau personnage (Viki le fait cligner des yeux, parler et respirer).
Tout reste sur le PC. Seul « Devine ! » utilise l'IA qui voit les images, et seulement si on clique."""
import math
import random
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

from PyQt6.QtCore import QBuffer, QByteArray, QPoint, QPointF, QRect, QRectF, QSize, QStandardPaths, Qt, QTimer
from PyQt6.QtGui import (QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut,
                         QTransform)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QScrollArea, QSizePolicy, QColorDialog, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSlider,
                             QTabWidget, QToolButton, QVBoxLayout, QWidget)

try:
    from i18n import tr
except Exception:
    def tr(t):
        return t

TAILLE = 1024
PALETTE = [("#000000", "Noir"), ("#2e1624", "Encre"), ("#9b8a93", "Gris"), ("#ffffff", "Blanc"),
           ("#8a5a3c", "Marron"), ("#f3c9a8", "Peau claire"), ("#c68a5e", "Peau mate"), ("#7a4a2e", "Peau foncée"),
           ("#e0483c", "Rouge"), ("#f59a3c", "Orange"), ("#ffd166", "Jaune"), ("#7cc6a4", "Vert"),
           ("#4a90e2", "Bleu"), ("#8e6bd8", "Violet"), ("#ef5b8f", "Rose"), ("#fde4ef", "Rose pâle")]
ANIMS = [("", "Aucune"), ("balancer", "Se balancer"), ("pivoter", "Pivoter (lever, baisser)"),
         ("onduler", "Onduler (vagues de haut en bas)"), ("ondoyer", "Ondoyer (vagues de gauche à droite)"),
         ("flotter", "Flotter (monter et descendre)"),
         ("rebondir", "Rebondir"), ("glisser", "Glisser (aller-retour)"), ("tourner", "Tourner"),
         ("pulser", "Battre (grossir un peu)"), ("zoomer", "Grandir et rapetisser"),
         ("etirer", "S'étirer (comme de la gelée)"), ("apparaitre", "Apparaître et disparaître"),
         ("clignoter", "Clignoter"), ("trembler", "Trembler")]
TUILES = [("balancer", "🎐", "Se balancer"), ("pivoter", "🎣", "Se lever"), ("onduler", "🌊", "Vagues"),
          ("ondoyer", "🏳️", "Au vent"), ("flotter", "🎈", "Flotter"), ("rebondir", "⚽", "Sauter"),
          ("glisser", "↔️", "Aller-retour"), ("tourner", "🌀", "Tourner"), ("pulser", "💓", "Battre"),
          ("zoomer", "🔍", "Grandir"), ("etirer", "🍮", "Gelée"), ("apparaitre", "👻", "Apparaître"),
          ("clignoter", "✨", "Clignoter"), ("trembler", "🫨", "Trembler"), ("trajet", "🛤️", "Suivre un chemin"),
          ("images", "🎞️", "Image par image"), ("", "⛔", "Ne plus bouger")]
VITESSES = [(1, "Lente"), (2, "Normale"), (3, "Rapide")]
BOUCLE = 4.0                                  # secondes : toutes les animations bouclent sur cette durée
OUTILS = [("crayon", "✏️", "Crayon"), ("feutre", "🖊️", "Feutre"), ("pinceau", "🖌️", "Pinceau"),
          ("gomme", "🧽", "Gomme"), ("remplir", "🪣", "Remplir"), ("ligne", "📏", "Ligne"),
          ("rect", "⬜", "Rectangle"), ("ellipse", "⭕", "Ellipse"), ("texte", "🔤", "Texte"),
          ("pipette", "💧", "Pipette"), ("deplacer", "✋", "Déplacer le calque choisi"),
          ("baguette", "🪄", "Baguette : clique sur un reste de fond pour l'effacer")]
BRAVO = ["Oh, c'est joli !", "J'adore les couleurs !", "Tu dessines bien, tu sais !", "Hihi, ça me plaît beaucoup !",
         "Continue, ça prend forme !"]


def dossier_dessins():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation) or str(Path.home())
    d = Path(base) / "Viki" / "Dessins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vide(w, h):
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _pastille(hexc, px):
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(hexc))
    p.setPen(QPen(QColor("#b9a3ae"), 1))
    p.drawRoundedRect(QRectF(0.5, 0.5, px - 1, px - 1), 6, 6)
    p.end()
    return pm


def boite_calque(img):
    """Le rectangle de ce qui est dessiné sur un calque (None s'il est vide)."""
    import numpy as np
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = src.width(), src.height()
    a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
    ys, xs = np.nonzero(a[:, 3:w * 4:4] > 12)
    if not len(xs):
        return None
    return QRectF(float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1))


PIVOTS = [("bas", "En bas"), ("centre", "Au centre"), ("haut", "En haut"), ("gauche", "À gauche"),
          ("droite", "À droite"), ("clic", "Là où je clique")]
DUREES_TRAJET = [(6.0, "Lente"), (4.0, "Normale"), (2.0, "Rapide")]
CADENCES = [(4, "4 images/s"), (6, "6 images/s"), (8, "8 images/s"), (12, "12 images/s")]


def _pivot(b, ou, an=None):
    if ou == "clic" and an and an.get("px") is not None:
        return QPointF(float(an["px"]), float(an["py"]))
    return {"bas": QPointF(b.center().x(), b.bottom()), "haut": QPointF(b.center().x(), b.top()),
            "gauche": QPointF(b.left(), b.center().y()), "droite": QPointF(b.right(), b.center().y())}.get(
        ou, b.center())


def _sur_trajet(pts, u):
    """Le point à la fraction u (0..1) de la longueur d'un trajet."""
    import math
    if len(pts) < 2:
        return pts[0]
    long = [0.0]
    for a, b in zip(pts, pts[1:]):
        long.append(long[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    cible = u * long[-1]
    for i in range(1, len(pts)):
        if long[i] >= cible:
            seg = long[i] - long[i - 1] or 1.0
            k = (cible - long[i - 1]) / seg
            return (pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k)
    return pts[-1]


def image_au_temps(c, t):
    """Image par image : l'image du calque à montrer au temps t."""
    fr = c.get("frames")
    if not fr or len(fr) < 2 or t is None:
        return c["img"]
    return fr[int(t * float(c.get("cadence", 6))) % len(fr)]


def uid(c):
    """Identifiant d'un calque (pour qu'une tête suive son corps, par exemple)."""
    if not c.get("uid"):
        c["uid"] = "%08x" % random.getrandbits(32)
    return c["uid"]


def calque_anime(c):
    return bool((c.get("anim") or {}).get("type") or len(c.get("trajet") or []) > 1 or len(c.get("frames") or []) > 1)


def mouvement(c, t):
    """Position d'un calque animé au temps t (secondes) -> (QTransform, opacité).
    Mouvement tout prêt (autour du point d'accroche choisi) + trajet dessiné, l'un et l'autre en boucle."""
    import math
    if t is None:
        return None, 1.0
    an = c.get("anim") or {}
    typ = an.get("type", "")
    pts = c.get("trajet") or []
    if not typ and len(pts) < 2:
        return None, 1.0
    tr_ = QTransform()
    op = 1.0
    if len(pts) > 1:                              # suit le chemin tracé (boucle si fermé, sinon aller-retour)
        d = float(c.get("trajet_duree", 4.0) or 4.0)
        u = (t % d) / d
        ferme = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 40
        if not ferme:
            u = 2 * u if u < 0.5 else 2 - 2 * u
        x, y = _sur_trajet(pts, u)
        tr_.translate(x - pts[0][0], y - pts[0][1])
    if not typ:
        return tr_, op
    b = c.get("_boite")
    if b is None:
        b = c["_boite"] = boite_calque(c["img"])
    if b is None:
        return tr_, op
    k = int(an.get("vitesse", 2) or 2)
    f = max(0.05, float(an.get("force", 40)) / 100.0)
    sens = -1 if an.get("inverse") else 1
    ph = 2 * math.pi * k * (t % BOUCLE) / BOUCLE
    va = 0.5 - 0.5 * math.cos(ph)                 # 0 -> 1 -> 0, en douceur
    pv = _pivot(b, an.get("pivot", "bas" if typ in ("balancer", "etirer", "rebondir") else "centre"), an)

    def autour(fn):
        tr_.translate(pv.x(), pv.y())
        fn()
        tr_.translate(-pv.x(), -pv.y())
    if typ == "balancer":
        autour(lambda: tr_.rotate(sens * math.sin(ph) * 12 * f))
    elif typ == "pivoter":                        # se lève puis redescend (jusqu'à 90°)
        autour(lambda: tr_.rotate(-sens * va * 90 * f))
    elif typ == "flotter":
        tr_.translate(0, math.sin(ph) * 22 * f)
    elif typ == "rebondir":
        tr_.translate(0, -abs(math.sin(ph / 2)) * 60 * f)
    elif typ == "glisser":
        tr_.translate(sens * math.sin(ph) * 70 * f, 0)
    elif typ == "tourner":
        autour(lambda: tr_.rotate(sens * 360.0 * k * (t % BOUCLE) / BOUCLE / 2))
    elif typ == "pulser":
        e = 1 + 0.12 * f * va
        autour(lambda: tr_.scale(e, e))
    elif typ == "zoomer":
        e = 1 + 0.4 * f * va
        autour(lambda: tr_.scale(e, e))
    elif typ == "etirer":
        e = 1 + 0.15 * f * math.sin(ph)
        autour(lambda: tr_.scale(1 / max(0.5, e) ** 0.5, e))
    elif typ == "apparaitre":
        op = 1 - va * min(1.0, f * 1.2)
    elif typ == "clignoter":
        op = 1 - 0.8 * f * (0.5 + 0.5 * math.sin(ph))
    elif typ == "trembler":
        tr_.translate(math.sin(ph * 5) * 3 * f, math.cos(ph * 7) * 3 * f)
    return tr_, max(0.0, op)


def _tableau(img):
    import numpy as np
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()].copy()
    return a                                        # B, G, R, A (non prémultiplié)


def _depuis_tableau(a):
    import numpy as np
    a = np.ascontiguousarray(a.astype(np.uint8))
    h, w = a.shape[:2]
    img = QImage(a.data, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def _fond_local(a, bloc=24):
    """Estimation du papier sous le dessin : la couleur médiane de chaque carré, adoucie."""
    import numpy as np
    h, w = a.shape[:2]
    H, W = (h + bloc - 1) // bloc, (w + bloc - 1) // bloc
    pad = np.pad(a[:, :, :3], ((0, H * bloc - h), (0, W * bloc - w), (0, 0)), mode="edge")
    med = np.median(pad.reshape(H, bloc, W, bloc, 3).transpose(0, 2, 1, 3, 4).reshape(H, W, bloc * bloc, 3), axis=2)
    petit = np.zeros((H, W, 4), np.uint8)
    petit[:, :, :3] = np.clip(med, 0, 255)
    petit[:, :, 3] = 255
    q = _depuis_tableau(petit).scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
    return _tableau(q)[:, :, :3].astype(np.float32)


def _flou_boite(x, r):
    """Flou rapide (boîte, deux passes ≈ gaussien) sur un tableau H×W×C en float."""
    import numpy as np
    for _ in range(2):
        for ax in (0, 1):
            pad = [(0, 0)] * x.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(x, pad, mode="edge"), axis=ax)
            n = x.shape[ax]
            hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
            lo = np.take(c, np.arange(0, n), axis=ax)
            x = (hi - lo) / (2 * r + 1)
    return x


def analyser_qualite(img):
    """Regarde si une image est pixelisée (agrandie sans lissage) ou floue. -> (taille des pixels, flou ?)"""
    import numpy as np
    a = _tableau(img).astype(np.float32)
    if a.shape[0] < 16 or a.shape[1] < 16:
        return 0, False
    if max(a.shape[:2]) > 1400:                       # assez grand : on regarde un morceau du milieu
        h, w = a.shape[:2]
        a = a[h // 2 - 600:h // 2 + 600, w // 2 - 600:w // 2 + 600]
    g = a[:, :, :3].mean(axis=2) * (a[:, :, 3] / 255.0)
    dx = np.abs(np.diff(g, axis=1))
    # pixelisé : entre deux changements de couleur, toujours à peu près le même écart (la taille des « gros pixels »)
    pix = 0
    ch = dx > 12
    ys, xs = np.nonzero(ch)
    if len(xs) > 300:
        same = ys[1:] == ys[:-1]
        ecarts = (xs[1:] - xs[:-1])[same]
        ecarts = ecarts[ecarts < 40]
        if len(ecarts) > 200:
            h_ = np.bincount(ecarts, minlength=42).astype(np.float64)
            tot = h_.sum()
            meilleur, kk = 0.0, 0
            for k in range(2, 33):
                part = (h_[k - 1] + h_[k] + h_[k + 1]) / tot if k > 2 else (h_[k] + h_[k + 1]) / tot
                if part > meilleur:
                    meilleur, kk = part, k
            if meilleur > 0.5 and kk >= 2 and h_[1] / tot < 0.35:
                lo = max(1, kk - 1)
                pix = float((np.arange(lo, kk + 2) * h_[lo:kk + 2]).sum() / max(1.0, h_[lo:kk + 2].sum()))
                pix = round(pix, 2) if pix >= 1.8 else 0
    # flou : les bords les plus marqués s'étalent sur plusieurs pixels
    flou = False
    lo, hi = np.percentile(g, 2), np.percentile(g, 98)
    if hi - lo > 40 and not pix:
        top = np.percentile(dx, 99.5)
        flou = bool(top / (hi - lo) < 0.28)
    return pix, flou


def ameliorer(img, pix=0, flou=False, force=1.0):
    """✨ Corrige une image pixelisée (lisse les marches) et/ou floue (rend les traits plus nets)."""
    import numpy as np
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    if pix >= 1.8:                                   # on revient à la vraie taille, puis on agrandit en lissant
        w, h = img.width(), img.height()
        petit = img.scaled(max(1, int(round(w / pix))), max(1, int(round(h / pix))), Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        img = petit.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        flou = True                                   # un agrandissement lissé gagne à être rendu net
    if flou:
        a = _tableau(img).astype(np.float32)
        al = a[:, :, 3:4] / 255.0
        rgb = a[:, :, :3] * al                        # sans les couleurs cachées sous la transparence
        r = 2 if pix < 3 else min(6, int(pix / 2) + 1)
        b = _flou_boite(rgb, r)
        ba = _flou_boite(al, r)
        net = rgb + (1.2 * force) * (rgb - b)
        a[:, :, :3] = np.where(al > 0.01, net / np.maximum(al, 0.01), a[:, :, :3])
        if pix >= 1.8:                                # bords transparents plus nets aussi
            a[:, :, 3:4] = np.clip(al + 0.8 * force * (al - ba), 0, 1) * 255
        img = _depuis_tableau(np.clip(a, 0, 255))
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def melanger(avant, apres, pts):
    """L'image corrigée seulement dans la zone entourée (bords adoucis)."""
    import numpy as np
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(QPointF(x, y))
    path.closeSubpath()
    masque = _vide(avant.width(), avant.height())
    p = QPainter(masque)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillPath(path, QColor(255, 255, 255))
    p.end()
    m = _flou_boite(_tableau(masque)[:, :, 3:4].astype(np.float32) / 255.0, 2)
    a = _tableau(avant).astype(np.float32)
    b = _tableau(apres).astype(np.float32)
    return _depuis_tableau(np.clip(a * (1 - m) + b * m, 0, 255))


def _inonder(cand, graines):
    """Remplissage : les cases de cand (H×W bool) reliées aux graines (liste d'indices à plat)."""
    import numpy as np
    from collections import deque
    try:                                              # rapide si scipy est là
        from scipy import ndimage
        lab, _n = ndimage.label(cand)
        ids = set(int(lab.flat[g]) for g in graines) - {0}
        return np.isin(lab, list(ids))
    except Exception:
        pass
    h, w = cand.shape
    c = bytearray(cand.astype(np.uint8).tobytes())
    vu = bytearray(h * w)
    q = deque()
    for g in graines:
        if c[g] and not vu[g]:
            vu[g] = 1
            q.append(g)
    pop, push = q.popleft, q.append
    while q:
        i = pop()
        x = i % w
        if x and c[i - 1] and not vu[i - 1]:
            vu[i - 1] = 1
            push(i - 1)
        if x < w - 1 and c[i + 1] and not vu[i + 1]:
            vu[i + 1] = 1
            push(i + 1)
        if i >= w and c[i - w] and not vu[i - w]:
            vu[i - w] = 1
            push(i - w)
        if i < (h - 1) * w and c[i + w] and not vu[i + w]:
            vu[i + w] = 1
            push(i + w)
    return np.frombuffer(bytes(vu), np.uint8).reshape(h, w).astype(bool)


def _a_la_taille(x, w, h):
    """Agrandit (en lissant) un tableau H×W ou H×W×3 en float vers w×h."""
    import numpy as np
    mono = x.ndim == 2
    t = np.zeros(x.shape[:2] + (4,), np.uint8)
    if mono:
        v = np.clip(x * 255, 0, 255)
        t[:, :, 0] = t[:, :, 1] = t[:, :, 2] = v
    else:
        t[:, :, :3] = np.clip(x, 0, 255)
    t[:, :, 3] = 255
    q = _depuis_tableau(t).scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
    r = _tableau(q).astype(np.float32)
    return r[:, :, 0] / 255.0 if mono else r[:, :, :3]


def detourer(img, tol=30.0, trous=True, graine=None):
    """🧽 Enlève le fond d'une image : ce qui touche les bords (ou le point cliqué, graine=(x, y)) et a la
    couleur du fond — même un fond en dégradé ou une photo de papier. Bords adoucis, sans liseré."""
    import numpy as np
    if graine is None:                                # image posée au milieu d'une feuille transparente :
        al0 = _tableau(img)[:, :, 3] > 40             # on travaille sur le rectangle de l'image
        ys, xs = np.nonzero(al0)
        if len(xs) and (xs.min() > 2 or ys.min() > 2 or xs.max() < img.width() - 3 or ys.max() < img.height() - 3):
            r = QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
            if r.width() > 16 and r.height() > 16:
                coupe = img.copy(r)
                morceau = detourer(coupe, tol, trous)
                if morceau is not coupe:
                    out = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).copy()
                    p = QPainter(out)
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                    p.drawImage(r.topLeft(), morceau)
                    p.end()
                    return out
                return img
    a = _tableau(img).astype(np.float32)
    h, w = a.shape[:2]
    rgb = a[:, :, :3]
    k = max(1, int(math.ceil(max(h, w) / 520.0)))
    sw, sh = max(2, w // k), max(2, h // k)
    petit = _tableau(img.convertToFormat(QImage.Format.Format_ARGB32).scaled(
        sw, sh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)).astype(np.float32)
    s, sa = petit[:, :, :3], petit[:, :, 3]
    if graine is None:
        bord = np.concatenate([s[0], s[-1], s[:, 0], s[:, -1]])
        ba = np.concatenate([sa[0], sa[-1], sa[:, 0], sa[:, -1]])
        if (ba < 40).mean() > 0.6:                    # déjà détourée
            return img
        idx = np.arange(sh * sw).reshape(sh, sw)
        graines = list(np.concatenate([idx[0], idx[-1], idx[:, 0], idx[:, -1]]))
        ref = np.median(bord, axis=0)
    else:
        gx, gy = int(graine[0] / k), int(graine[1] / k)
        gx, gy = min(sw - 1, max(0, gx)), min(sh - 1, max(0, gy))
        graines = [gy * sw + gx]
        ref = s[gy, gx].copy()
    champ = np.broadcast_to(ref, s.shape).astype(np.float32)
    masque = np.zeros((sh, sw), bool)
    for _ in range(3):                                # le fond peut changer doucement (dégradé, ombre)
        d = np.abs(s - champ).max(axis=2)
        cand = (d < tol) & (sa > 30)
        masque = _inonder(cand, graines)
        if masque.mean() < 0.01:
            return img
        r = max(2, max(sw, sh) // 10)
        m3 = masque[..., None].astype(np.float32)
        poids = _flou_boite(m3, r)
        somme = _flou_boite(s * m3, r)
        champ = np.where(poids > 0.02, somme / np.maximum(poids, 1e-3), ref).astype(np.float32)
    if trous and graine is None:                      # le fond qui se voit entre un bras et le corps
        d = np.abs(s - champ).max(axis=2)
        reste = (d < tol * 0.6) & ~masque
        if reste.any():
            seuil = 0.004 * sw * sh
            try:
                from scipy import ndimage
                lab, n = ndimage.label(reste)
                tailles = np.bincount(lab.ravel())
                gros = np.nonzero(tailles > seuil)[0]
                masque |= np.isin(lab, [g for g in gros if g != 0])
            except Exception:                         # sans scipy : zone par zone (les poussières d'abord ôtées)
                r2 = reste.copy()
                r2[1:-1, 1:-1] = reste[1:-1, 1:-1] & reste[:-2, 1:-1] & reste[2:, 1:-1] & reste[1:-1, :-2] & \
                    reste[1:-1, 2:]
                for _ in range(150):
                    if r2.sum() < seuil:
                        break
                    i = int(np.argmax(r2.ravel()))
                    zone = _inonder(reste, [i])
                    if zone.sum() > seuil:
                        masque |= zone
                    r2 &= ~zone
    mf = _a_la_taille(_flou_boite(masque[..., None].astype(np.float32), 1)[:, :, 0], w, h)
    champ_f = _a_la_taille(champ, w, h)
    d = np.abs(rgb - champ_f).max(axis=2)
    pres = _a_la_taille(_flou_boite(masque[..., None].astype(np.float32), 2)[:, :, 0], w, h) > 0.01
    al = np.where(pres, np.clip((d - tol * 0.45) / (tol * 0.75), 0.0, 1.0), 1.0)
    al = np.where(mf > 0.97, 0.0, al)
    al = np.minimum(al, 1.0 - np.clip((mf - 0.5) * 2.2, 0, 1) * (d < tol)) if graine is None else al
    out = a.copy()
    a0 = a[:, :, 3] / 255.0
    nouv = np.clip(al, 0, 1) * a0
    demi = (al > 0.02) & (al < 0.98)                  # bords : on retire la couleur du fond mélangée
    pur = (rgb - champ_f * (1 - al[..., None])) / np.maximum(al[..., None], 0.02)
    out[:, :, :3] = np.where(demi[..., None], np.clip(pur, 0, 255), rgb)
    out[:, :, 3] = nouv * 255
    return _depuis_tableau(out)


def separer(img, pts):
    """✂️ Coupe ce qui est entouré par le lasso pts. -> (reste, morceau).
    Sur une image pleine (dessin importé, photo d'un dessin), le papier n'est pas emporté
    et le trou est rebouché avec la couleur du papier tout autour."""
    import numpy as np
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(QPointF(x, y))
    path.closeSubpath()
    masque = _vide(img.width(), img.height())
    p = QPainter(masque)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillPath(path, QColor(255, 255, 255))
    p.end()
    m = _tableau(masque)[:, :, 3].astype(np.float32) / 255.0
    a = _tableau(img).astype(np.float32)
    h, w = m.shape
    morceau = a.copy()
    reste = a.copy()
    plein = (a[:, :, 3] > 200).mean() > 0.5               # une image pleine (dessin importé, photo…)
    if plein:
        fond = _fond_local(a)                             # la couleur du papier, endroit par endroit
        d = np.abs(a[:, :, :3] - fond).max(axis=2)
        garde = np.clip((d - 18.0) / 22.0, 0.0, 1.0)      # ce qui n'est pas du papier = le dessin
        mg = m * garde
        morceau[:, :, 3] = a[:, :, 3] * mg
        reste[:, :, :3] = a[:, :, :3] * (1 - mg[..., None]) + fond * mg[..., None]   # trou rebouché
    else:
        morceau[:, :, 3] *= m
        reste[:, :, 3] *= (1 - m)
    return _depuis_tableau(reste), _depuis_tableau(morceau)


def ecrire_apng(chemin, images, fps):
    """Écrit une image animée APNG (lisible par les navigateurs, Krita, et Viki elle-même)."""
    import struct
    import zlib
    import numpy as np

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    w, h = images[0].width(), images[0].height()
    delai = max(1, int(round(100 / max(1, fps))))
    out = [b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)),
           chunk(b"acTL", struct.pack(">II", len(images), 0))]
    seq = 0
    for i, img in enumerate(images):
        src = img.convertToFormat(QImage.Format.Format_RGBA8888)
        a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
        brut = b"".join(b"\x00" + bytes(a[y, :w * 4]) for y in range(h))
        out.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", seq, w, h, 0, 0, delai, 100, 1, 0)))
        seq += 1
        z = zlib.compress(brut, 6)
        if i == 0:
            out.append(chunk(b"IDAT", z))
        else:
            out.append(chunk(b"fdAT", struct.pack(">I", seq) + z))
            seq += 1
    out.append(chunk(b"IEND", b""))
    Path(chemin).write_bytes(b"".join(out))


def _png(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def _remplissage(img, x, y, couleur, tol=40):
    """Pot de peinture (balayage par lignes, accéléré avec numpy) ; renvoie False si rien à remplir."""
    import numpy as np
    w, h = img.width(), img.height()
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
    a = a[:, :w * 4].reshape(h, w, 4).astype(np.int16)
    ref = a[y, x].copy()
    if ref[3] < 20:
        cible = a[:, :, 3] < 60
    else:
        cible = (np.abs(a - ref).max(axis=2) <= tol) & (a[:, :, 3] > 20)
    rempli = np.zeros((h, w), dtype=bool)
    pile = [(x, y)]
    while pile:
        px, py = pile.pop()
        if rempli[py, px] or not cible[py, px]:
            continue
        lig = cible[py] & ~rempli[py]
        stop_g = np.flatnonzero(~lig[:px])
        g = stop_g[-1] + 1 if stop_g.size else 0
        stop_d = np.flatnonzero(~lig[px:])
        d = px + stop_d[0] - 1 if stop_d.size else w - 1
        rempli[py, g:d + 1] = True
        for ny in (py - 1, py + 1):
            if 0 <= ny < h:
                seg = cible[ny, g:d + 1] & ~rempli[ny, g:d + 1]
                if seg.any():
                    debut = np.flatnonzero(seg & ~np.concatenate(([False], seg[:-1])))
                    pile.extend((g + int(i), ny) for i in debut)
    if not rempli.any():
        return False
    m = rempli.copy()                                    # déborde d'un pixel sous le trait (bords lissés)
    m[1:] |= rempli[:-1]
    m[:-1] |= rempli[1:]
    m[:, 1:] |= rempli[:, :-1]
    m[:, :-1] |= rempli[:, 1:]
    c = QColor(couleur)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    al = c.alpha()
    out[m] = (c.blue() * al // 255, c.green() * al // 255, c.red() * al // 255, al)
    calque = QImage(out.tobytes(), w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
    p = QPainter(img)
    p.drawImage(0, 0, calque)
    p.end()
    return True


def silhouette_guide():
    """Une silhouette très simple (tête, corps, bras, jambes) pour aider à placer un personnage."""
    s = TAILLE / 400.0
    path = QPainterPath()
    path.addEllipse(QRectF(160 * s, 40 * s, 80 * s, 92 * s))
    path.moveTo(200 * s, 132 * s)
    path.lineTo(200 * s, 145 * s)
    path.addRoundedRect(QRectF(150 * s, 145 * s, 100 * s, 120 * s), 30 * s, 30 * s)
    for x0, x1 in ((152, 118), (248, 282)):
        path.moveTo(x0 * s, 160 * s)
        path.lineTo(x1 * s, 255 * s)
    for x in (178, 222):
        path.moveTo(x * s, 262 * s)
        path.lineTo(x * s, 370 * s)
    return path


class Toile(QWidget):
    """La feuille : calques, outils, zoom (Ctrl + molette), déplacement (clic molette ou Espace)."""

    def __init__(self, carnet):
        super().__init__()
        self.carnet = carnet
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking, True)
        self.calques = []
        self.actif = 0
        self.outil = "feutre"
        self.couleur = QColor("#2e1624")
        self.taille = 8
        self.opacite = 1.0
        self.symetrie = False
        self.guide = False
        self.decalque = None
        self.zoom = 1.0
        self.decal = QPointF(0, 0)
        self.annuler_pile, self.refaire_pile = [], []
        self.trait = None
        self.forme = None
        self.pression = 1.0
        self.pan = None
        self.espace = False
        self.modifie = False
        self.nb_traits = 0
        self.anime = False
        self.mode_trajet = False
        self.mode_pivot = False
        self.mode_lasso = False
        self.lasso = None
        self.mode_visage = None
        self.deplace = None
        self.sans_visage = False
        self.trajet_en_cours = None
        self.t0 = time.monotonic()
        self.horloge = QTimer(self)
        self.horloge.setInterval(33)
        self.horloge.timeout.connect(self.update)
        self.nouveau()

    # ---------- document
    def nouveau(self):
        self.calques = [{"nom": tr("Fond"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0},
                        {"nom": tr("Dessin"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0}]
        self.actif = 1
        self.annuler_pile, self.refaire_pile = [], []
        self.modifie = False
        self.update()

    def image_finale(self, avec_fond=True, t=None, seuls=None):
        """L'image de tous les calques visibles ; t (secondes) : avec les animations à cet instant.
        seuls : seulement ces calques (liste)."""
        out = _vide(TAILLE, TAILLE)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for c in self.calques:
            if seuls is not None:
                if any(c is x for x in seuls):
                    self._dessiner_calque(p, c, t)
            elif c["visible"] and (avec_fond or c is not self.calques[0]):
                self._dessiner_calque(p, c, t)
        p.end()
        return out

    def parent(self, c):
        u = c.get("suit")
        if not u:
            return None
        return next((x for x in self.calques if x.get("uid") == u and x is not c), None)

    def enfants(self, c, n=0):
        """Les calques qui suivent c (et ceux qui les suivent…)."""
        if n > 6 or not c.get("uid"):
            return []
        out = []
        for x in self.calques:
            if x.get("suit") == c["uid"] and x is not c:
                out += [x] + self.enfants(x, n + 1)
        return out

    def mouv_total(self, c, t, n=0):
        """Le mouvement du calque + celui du calque qu'il suit (une tête suit son corps)."""
        tr_, op = mouvement(c, t)
        par = self.parent(c)
        if par is not None and n < 6 and t is not None:
            ptr, _o = self.mouv_total(par, t, n + 1)
            if ptr is not None:
                tr_ = (tr_ if tr_ is not None else QTransform()) * ptr
        return tr_, op

    def bouge(self, c, n=0, visage=True):
        par = self.parent(c)
        return calque_anime(c) or (visage and bool((c.get("visage") or {}).get("yeux"))) or \
            (par is not None and n < 6 and self.bouge(par, n + 1, visage))

    def _visage(self, p, c, t):
        """Yeux qui clignent et bouche qui parle, dessinés par-dessus le calque (ils suivent ses mouvements)."""
        import math
        v = c.get("visage") or {}
        yeux = v.get("yeux") or []
        r = float(v.get("r", 14))
        peau = QColor(v.get("peau", "#ffffff"))
        dec = (int(uid(c), 16) % 997) / 997.0 * BOUCLE
        if yeux and v.get("cligne", True):
            tb = (t + dec) % BOUCLE
            if tb < 0.32:
                k = min(1.0, 1.7 * (1 - abs(tb / 0.32 * 2 - 1)))
                for x, y in yeux:
                    rect = QRectF(x - r / 2 - 1, y - r * 0.32 - 1, r + 2, r * 0.64 + 2)
                    path = QPainterPath()
                    path.addEllipse(rect)
                    ly = rect.top() + rect.height() * k
                    p.save()
                    p.setClipPath(path)
                    p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), ly - rect.top()), peau)
                    p.restore()
                    pen = QPen(QColor("#2a1414"), max(1.5, r * 0.12))
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    p.drawLine(QPointF(rect.left() + 1, ly), QPointF(rect.right() - 1, ly))
        b = v.get("bouche")
        if b and v.get("parle"):
            o = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * (t + dec))
            if o > 0.2:
                w, h = r * 0.9 * (0.6 + 0.3 * o), r * 0.6 * o
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#5c1d25"))
                p.drawEllipse(QRectF(b[0] - w / 2, b[1] - h * 0.35, w, h))

    def _dessiner_calque(self, p, c, t):
        tr_, op = self.mouv_total(c, t)
        p.save()
        dec = c.get("_decal")
        if dec:
            p.translate(dec[0], dec[1])
        if tr_ is not None:
            p.setTransform(tr_, True)
        p.setOpacity(c["opacite"] * op)
        img = image_au_temps(c, t)
        an = c.get("anim") or {}
        if t is not None and an.get("type") in ("onduler", "ondoyer"):   # vagues : chaque bande se décale
            import math
            b = c.get("_boite") or boite_calque(c["img"])
            if b is not None:
                f = max(0.05, float(an.get("force", 40)) / 100.0)
                k = int(an.get("vitesse", 2) or 2)
                ph = 2 * math.pi * k * (t % BOUCLE) / BOUCLE * (-1 if an.get("inverse") else 1)
                pas = 3
                if an["type"] == "ondoyer":
                    for y in range(max(0, int(b.top()) - 2), min(TAILLE, int(b.bottom()) + 3), pas):
                        dx = math.sin(y / 60.0 - ph) * 12 * f
                        p.drawImage(QPointF(dx, y), img, QRectF(0, y, TAILLE, pas))
                else:
                    for x in range(max(0, int(b.left()) - 2), min(TAILLE, int(b.right()) + 3), pas):
                        dy = math.sin(x / 70.0 - ph) * 10 * f
                        p.drawImage(QPointF(x, dy), img, QRectF(x, 0, pas, TAILLE))
                if t is not None and c.get("visage") and not self.sans_visage:
                    self._visage(p, c, t)
                p.restore()
                return
        p.drawImage(0, 0, img)
        if t is not None and c.get("visage") and not self.sans_visage:
            self._visage(p, c, t)
        p.restore()

    def animes(self):
        return [c for c in self.calques if c["visible"] and self.bouge(c)]

    def duree_boucle(self):
        d = BOUCLE
        for c in self.animes():
            if len(c.get("frames") or []) > 1:
                d = max(d, len(c["frames"]) / float(c.get("cadence", 6)))
            if len(c.get("trajet") or []) > 1:
                d = max(d, float(c.get("trajet_duree", 4.0)))
        return min(d, 8.0)

    def jouer(self, oui):
        self.anime = bool(oui)
        self.t0 = time.monotonic()
        (self.horloge.start if oui else self.horloge.stop)()
        self.update()

    def _memo(self):
        self.calques[self.actif]["_boite"] = None
        self.annuler_pile.append((self.actif, self.calques[self.actif]["img"].copy()))
        del self.annuler_pile[:-40]
        self.refaire_pile.clear()
        self.modifie = True

    def instantane(self, calques):
        """Pour Ctrl+Z après une grosse opération (détacher, remettre, déplacer…)."""
        snap = ("instantane", list(self.calques), [(c, dict(c, frames=list(c["frames"]) if c.get("frames") else None))
                                                   for c in calques], self.actif)
        self.annuler_pile.clear()
        self.refaire_pile.clear()
        self.annuler_pile.append(snap)
        self.modifie = True

    def annuler(self):
        if not self.annuler_pile:
            return
        if self.annuler_pile[-1][0] == "instantane":
            _k, liste, snaps, actif = self.annuler_pile.pop()
            self.calques = liste
            for c, d in snaps:
                c.clear()
                c.update({k: v for k, v in d.items() if not (k == "frames" and v is None)})
                c["_boite"] = None
            self.actif = min(actif, len(self.calques) - 1)
            self.refaire_pile.clear()
            self.carnet._liste_calques()
            self.update()
            return
        if self.annuler_pile[-1][0] == "detache":         # remettre l'élément détaché dans le dessin
            _k, src, img, morceau = self.annuler_pile.pop()
            if morceau in self.calques:
                self.calques.remove(morceau)
            if src in self.calques:
                src["img"] = img
                src["_boite"] = None
                self.actif = self.calques.index(src)
            self.annuler_pile.clear()
            self.refaire_pile.clear()
            self.carnet._liste_calques()
            self.update()
            return
        i, img = self.annuler_pile.pop()
        if i < len(self.calques):
            self.refaire_pile.append((i, self.calques[i]["img"].copy()))
            self._remettre(i, img)
        self.update()

    def _remettre(self, i, img):
        c = self.calques[i]
        if c.get("frames"):
            c["frames"][c.get("cur", 0)] = img
        c["img"] = img
        c["_boite"] = None

    def refaire(self):
        if not self.refaire_pile:
            return
        i, img = self.refaire_pile.pop()
        if i < len(self.calques):
            self.annuler_pile.append((i, self.calques[i]["img"].copy()))
            self._remettre(i, img)
        self.update()

    # ---------- vue
    def _base(self):
        cote = min(self.width(), self.height()) - 24
        return max(50.0, cote) / TAILLE

    def _echelle(self):
        return self._base() * self.zoom

    def _origine(self):
        e = self._echelle()
        return QPointF((self.width() - TAILLE * e) / 2, (self.height() - TAILLE * e) / 2) + self.decal

    def vers_doc(self, pt):
        o, e = self._origine(), self._echelle()
        return QPointF((pt.x() - o.x()) / e, (pt.y() - o.y()) / e)

    def paintEvent(self, _e):
        p = QPainter(self)
        try:                                                   # autour de la feuille : la couleur du thème
            import themes as _th
            fond = "#16171c" if _th.effective() == "pomme" else _th.color("#f4e9ef")
        except Exception:
            fond = "#f4e9ef"
        p.fillRect(self.rect(), QColor(fond))
        o, e = self._origine(), self._echelle()
        zone = QRectF(o.x(), o.y(), TAILLE * e, TAILLE * e)
        p.fillRect(zone, QColor("#ffffff"))
        p.save()
        p.setClipRect(zone)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#efe9ec"))
        k = 16
        for i in range(int(zone.width() // k) + 1):
            for j in range(int(zone.height() // k) + 1):
                if (i + j) % 2:
                    p.drawRect(QRectF(zone.x() + i * k, zone.y() + j * k, k, k))
        p.restore()
        p.save()
        p.translate(o)
        p.scale(e, e)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, e < 1)
        if self.decalque is not None:
            p.setOpacity(0.35)
            p.drawImage(QRectF(0, 0, TAILLE, TAILLE), self.decalque)
            p.setOpacity(1)
        t = (time.monotonic() - self.t0) if self.anime else None
        for idx, c in enumerate(self.calques):
            if c["visible"]:
                fr = c.get("frames") or []
                if (idx == self.actif and not self.anime and len(fr) > 1 and c.get("cur", 0) > 0
                        and c.get("oignon", True)):                   # pelure d'oignon : l'image d'avant
                    p.setOpacity(0.25 * c["opacite"])
                    p.drawImage(0, 0, fr[c["cur"] - 1])
                self._dessiner_calque(p, c, t)
                if idx == self.actif and self.forme:
                    self._dessiner_forme(p, *self.forme)
        p.setOpacity(1)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.guide:
            p.setPen(QPen(QColor(176, 51, 106, 90), 3 / e, Qt.PenStyle.DashLine))
            p.setBrush(QColor(176, 51, 106, 18))
            p.drawPath(silhouette_guide())
        pts = self.trajet_en_cours or (None if self.anime else self.calques[self.actif].get("trajet"))
        if pts and len(pts) > 1:
            path = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                path.lineTo(QPointF(x, y))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(74, 144, 226, 200), 3 / e, Qt.PenStyle.DashLine))
            p.drawPath(path)
            p.setBrush(QColor(74, 144, 226))
            p.drawEllipse(QPointF(*pts[0]), 7 / e, 7 / e)
        cv = self.calques[self.actif].get("visage") or {}
        pts_v = list(cv.get("yeux") or []) + ([cv["bouche"]] if cv.get("bouche") else [])
        if self.mode_visage is not None:
            pts_v = list(self.mode_visage)
        if pts_v and not self.anime:
            n_yeux = 2 if self.mode_visage is not None else len(cv.get("yeux") or [])
            for i, (x, y) in enumerate(pts_v):
                p.setPen(QPen(QColor("#00b8d9") if i < n_yeux else QColor("#ff3d8b"), 2.5 / e))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x, y), 6 / e, 6 / e)
        if self.lasso and len(self.lasso) > 1:
            path = QPainterPath(QPointF(*self.lasso[0]))
            for x, y in self.lasso[1:]:
                path.lineTo(QPointF(x, y))
            path.closeSubpath()
            p.setBrush(QColor(224, 72, 60, 40))
            p.setPen(QPen(QColor("#e0483c"), 3 / e, Qt.PenStyle.DashLine))
            p.drawPath(path)
        an = self.calques[self.actif].get("anim") or {}
        if an.get("pivot") == "clic" and an.get("px") is not None:
            p.setPen(QPen(QColor("#e0483c"), 2 / e))
            p.setBrush(QColor(255, 255, 255, 200))
            c0 = QPointF(float(an["px"]), float(an["py"]))
            p.drawEllipse(c0, 8 / e, 8 / e)
            p.drawLine(c0 - QPointF(12 / e, 0), c0 + QPointF(12 / e, 0))
            p.drawLine(c0 - QPointF(0, 12 / e), c0 + QPointF(0, 12 / e))
        if self.symetrie:
            p.setPen(QPen(QColor("#e7a3c2"), 2 / e, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(TAILLE / 2, 0), QPointF(TAILLE / 2, TAILLE))
        p.restore()
        p.setPen(QPen(QColor("#ecd3df"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(zone)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            avant = self.vers_doc(ev.position())
            self.zoom = max(0.25, min(6.0, self.zoom * (1.15 if ev.angleDelta().y() > 0 else 1 / 1.15)))
            apres = self.vers_doc(ev.position())
            e = self._echelle()
            self.decal += QPointF((apres.x() - avant.x()) * e, (apres.y() - avant.y()) * e)
            self.update()
        else:
            self.decal += QPointF(ev.angleDelta().x() / 4, ev.angleDelta().y() / 4)
            self.update()

    def recentrer(self):
        self.zoom, self.decal = 1.0, QPointF(0, 0)
        self.update()

    # ---------- pinceaux
    def _pinceau(self, pression=1.0):
        t, c = self.outil, QColor(self.couleur)
        if t == "crayon":
            w = max(1.0, self.taille * 0.35)
        elif t == "pinceau":
            w = max(1.0, self.taille * (0.3 + 0.9 * pression))
            c.setAlphaF(c.alphaF() * 0.45)
        elif t == "gomme":
            w = self.taille * 1.5
        else:
            w = max(1.0, self.taille * (0.6 + 0.4 * pression))
        c.setAlphaF(c.alphaF() * self.opacite)
        return QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    def _miroir(self, pt):
        return QPointF(TAILLE - pt.x(), pt.y())

    def _segment(self, a, b, pression):
        img = self.calques[self.actif]["img"]
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.outil == "gomme":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.setPen(self._pinceau(pression))
        p.drawLine(a, b)
        if self.symetrie:
            p.drawLine(self._miroir(a), self._miroir(b))
        p.end()

    def _dessiner_forme(self, p, a, b):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = self._pinceau()
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for x, y in ((a, b), (self._miroir(a), self._miroir(b))) if self.symetrie else ((a, b),):
            if self.outil == "ligne":
                p.drawLine(x, y)
            elif self.outil == "rect":
                p.drawRect(QRectF(x, y).normalized())
            else:
                p.drawEllipse(QRectF(x, y).normalized())
        p.restore()

    # ---------- souris et tablette
    def _debut(self, pos, pression):
        pt = self.vers_doc(pos)
        if self.mode_pivot:
            self.mode_pivot = False
            self.carnet.pivot_choisi(pt.x(), pt.y())
            return
        if self.mode_lasso:
            self.lasso = [(pt.x(), pt.y())]
            self.update()
            return
        if self.mode_visage is not None:
            self.mode_visage.append((pt.x(), pt.y()))
            self.update()
            self.carnet.visage_point()
            return
        if self.outil == "deplacer":
            c = self.calques[self.actif]
            if self.actif == 0 and len(self.calques) > 1 and boite_calque(c["img"]) is None:
                return
            if self.anime:
                self.carnet.b_jouer.setChecked(False)
            self.deplace = (pt, c)
            c["_decal"] = (0.0, 0.0)
            for x in self.enfants(c):
                x["_decal"] = (0.0, 0.0)
            return
        if self.anime and not self.mode_trajet:
            self.carnet.b_jouer.setChecked(False)
        if self.mode_trajet:
            self.trajet_en_cours = [(pt.x(), pt.y())]
            self.update()
            return
        if not (0 <= pt.x() < TAILLE and 0 <= pt.y() < TAILLE) and self.outil in ("remplir", "pipette", "texte"):
            return
        c = self.calques[self.actif]
        if not c["visible"] and self.outil not in ("pipette",):
            self.carnet.dire("Ce calque est caché : affiche-le pour dessiner dessus.")
            return
        if self.outil == "baguette":
            if 0 <= pt.x() < TAILLE and 0 <= pt.y() < TAILLE:
                self.carnet.baguette(pt.x(), pt.y())
            return
        if self.outil == "pipette":
            fin = self.image_finale()
            x, y = int(pt.x()), int(pt.y())
            if 0 <= x < TAILLE and 0 <= y < TAILLE:
                col = fin.pixelColor(x, y)
                if col.alpha() > 0:
                    col.setAlpha(255)
                    self.carnet.choisir_couleur(col)
            return
        if self.outil == "remplir":
            self._memo()
            try:
                if not _remplissage(c["img"], int(pt.x()), int(pt.y()), self.couleur):
                    self.annuler_pile.pop()
            except Exception:
                self.annuler_pile.pop()
                self.carnet.dire("Je n'ai pas réussi, désolée.")
            self.update()
            return
        if self.outil == "texte":
            txt, ok = QInputDialog.getText(self, tr("Texte"), tr("Ton texte :"))
            if ok and txt.strip():
                self._memo()
                p = QPainter(c["img"])
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                f = QFont()
                f.setPixelSize(max(12, int(self.taille * 4)))
                f.setBold(True)
                p.setFont(f)
                col = QColor(self.couleur)
                col.setAlphaF(self.opacite)
                p.setPen(col)
                p.drawText(pt, txt)
                p.end()
                self.update()
            return
        self._memo()
        if self.outil in ("ligne", "rect", "ellipse"):
            self.forme = (pt, pt)
        else:
            self.trait = pt
            self._segment(pt, pt + QPointF(0.01, 0.01), pression)
        self.update()

    def _suite(self, pos, pression):
        pt = self.vers_doc(pos)
        if self.deplace is not None:
            d = (pt.x() - self.deplace[0].x(), pt.y() - self.deplace[0].y())
            for x in [self.deplace[1]] + self.enfants(self.deplace[1]):
                x["_decal"] = d
            self.update()
            return
        if self.lasso is not None:
            x0, y0 = self.lasso[-1]
            if abs(pt.x() - x0) + abs(pt.y() - y0) > 3:
                self.lasso.append((pt.x(), pt.y()))
                self.update()
            return
        if self.trajet_en_cours is not None:
            x0, y0 = self.trajet_en_cours[-1]
            if abs(pt.x() - x0) + abs(pt.y() - y0) > 4:
                self.trajet_en_cours.append((pt.x(), pt.y()))
                self.update()
            return
        if self.forme:
            self.forme = (self.forme[0], pt)
            self.update()
        elif self.trait is not None:
            self._segment(self.trait, pt, pression)
            self.trait = pt
            self.update()

    def _fin(self):
        if self.deplace is not None:
            c = self.deplace[1]
            self.deplace = None
            dx, dy = c.pop("_decal", (0, 0))
            for x in self.enfants(c):
                x.pop("_decal", None)
            if abs(dx) + abs(dy) > 0.5:
                self.carnet.transformer(c, QTransform.fromTranslate(dx, dy))
            self.update()
            return
        if self.lasso is not None:
            pts, self.lasso = self.lasso, None
            self.mode_lasso = False
            self.unsetCursor()
            self.update()
            self.carnet.detacher(pts)
            return
        if self.trajet_en_cours is not None:
            pts, self.trajet_en_cours = self.trajet_en_cours, None
            self.mode_trajet = False
            if len(pts) > 2:
                self.carnet._histo()
                self.calques[self.actif]["trajet"] = pts
                self.modifie = True
            self.carnet.trajet_fini(len(pts) > 2)
            self.update()
            return
        if self.forme:
            a, b = self.forme
            self.forme = None
            p = QPainter(self.calques[self.actif]["img"])
            self._dessiner_forme(p, a, b)
            p.end()
        self.nb_traits += 1
        self.carnet.trait_fini(self.nb_traits)
        self.trait = None
        self.update()

    def tabletEvent(self, ev):
        t = ev.type()
        self.pression = max(0.05, ev.pressure())
        if t == ev.Type.TabletPress:
            self._debut(ev.position(), self.pression)
        elif t == ev.Type.TabletMove:
            self._suite(ev.position(), self.pression)
        elif t == ev.Type.TabletRelease:
            self._fin()
        ev.accept()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton or (self.espace and ev.button() == Qt.MouseButton.LeftButton):
            self.pan = (ev.position(), QPointF(self.decal))
            return
        if ev.button() == Qt.MouseButton.RightButton:
            self.carnet.outil("pipette" if self.outil != "pipette" else "feutre")
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self._debut(ev.position(), 1.0)

    def mouseMoveEvent(self, ev):
        if self.pan:
            d = ev.position() - self.pan[0]
            self.decal = self.pan[1] + d
            self.update()
            return
        if ev.buttons() & Qt.MouseButton.LeftButton:
            self._suite(ev.position(), 1.0)

    def mouseReleaseEvent(self, ev):
        if self.pan:
            self.pan = None
            return
        if ev.button() == Qt.MouseButton.LeftButton and (self.trait is not None or self.forme or
                                                         self.trajet_en_cours is not None or self.lasso is not None
                                                         or self.deplace is not None):
            self._fin()


class Carnet(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("carnet")
        self.setWindowTitle(tr("✏️ Carnet de dessin") + " — " + comp.char.get("name", "Viki"))
        scr = self.screen().availableGeometry() if self.screen() else None
        self.resize(min(1240, int(scr.width() * 0.9)) if scr else 1180, min(840, int(scr.height() * 0.9)) if scr else 800)
        self.setStyleSheet(CSS)
        self.fichier = None
        self.dernier_bravo = 0.0
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        # barre du haut
        haut = QHBoxLayout()
        for txt, fn in ((tr("📄 Nouveau"), self.nouveau), (tr("📂 Ouvrir…"), self.ouvrir),
                        (tr("💾 Enregistrer"), self.enregistrer), (tr("↩️"), lambda: self.toile.annuler()),
                        (tr("↪️"), lambda: self.toile.refaire()),
                        (tr("🖼️ Image à décalquer…"), self.decalque), (tr("🔍 Recentrer"), lambda: self.toile.recentrer())):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            if txt in ("↩️", "↪️"):
                b.setToolTip(tr("Annuler (Ctrl+Z)") if txt == "↩️" else tr("Refaire (Ctrl+Y)"))
            haut.addWidget(b)
        haut.addStretch(1)
        b = QPushButton(tr("🎬 Animer"))
        b.setToolTip(tr("Faire bouger un perso ou un objet de ton dessin, pas à pas."))
        b.clicked.connect(self._animer)
        haut.addWidget(b)
        b = QPushButton(tr("🔮 Devine !"))
        b.setToolTip(tr("Viki regarde ton dessin et devine ce que c'est (avec l'IA qui voit les images)."))
        b.clicked.connect(self.devine)
        haut.addWidget(b)
        b = QPushButton(tr("🧑‍🎨 Faire de mon dessin un perso"))
        b.setObjectName("main")
        b.clicked.connect(lambda: self.en_perso())
        haut.addWidget(b)
        root.addLayout(haut)
        corps = QHBoxLayout()
        root.addLayout(corps, 1)
        # outils
        col = QVBoxLayout()
        col.setSpacing(4)
        self.b_outils = {}
        for cle, ico, nom in OUTILS:
            tb = QToolButton()
            tb.setText(ico)
            tb.setToolTip(tr(nom))
            tb.setCheckable(True)
            tb.setFixedSize(52, 44)
            f = tb.font()
            f.setPointSize(f.pointSize() + 5)
            tb.setFont(f)
            tb.clicked.connect(lambda _=False, k=cle: self.outil(k))
            col.addWidget(tb)
            self.b_outils[cle] = tb
        col.addStretch(1)
        corps.addLayout(col)
        self.toile = Toile(self)
        corps.addWidget(self.toile, 1)
        # panneau de droite
        droite = QVBoxLayout()
        droite.setSpacing(8)
        panneau = QFrame()
        panneau.setObjectName("panneau")
        panneau.setFixedWidth(320)
        panneau.setLayout(droite)
        corps.addWidget(panneau)
        self.onglets = QTabWidget()
        droite.addWidget(self.onglets, 3)
        ow = QWidget()
        dv = QVBoxLayout(ow)
        dv.setContentsMargins(4, 6, 4, 4)
        dv.setSpacing(8)
        dv.addWidget(self._titre(tr("Couleur")))
        g = QGridLayout()
        g.setSpacing(5)
        for i, (hexc, nom) in enumerate(PALETTE):
            b = QToolButton()
            b.setToolTip(tr(nom))
            b.setFixedSize(28, 28)
            b.setProperty("sans_theme", True)
            b.setIcon(QIcon(_pastille(hexc, 24)))
            b.setIconSize(QSize(24, 24))
            b.setStyleSheet("QToolButton { border: none; background: transparent; padding: 0; }")
            b.clicked.connect(lambda _=False, h=hexc: self.choisir_couleur(QColor(h)))
            g.addWidget(b, i // 8, i % 8)
        dv.addLayout(g)
        h = QHBoxLayout()
        self.apercu = QLabel()
        self.apercu.setFixedSize(34, 34)
        self.apercu.setProperty("sans_theme", True)
        h.addWidget(self.apercu)
        b = QPushButton(tr("🎨 Autre couleur…"))
        b.clicked.connect(self._roue)
        h.addWidget(b, 1)
        dv.addLayout(h)
        self.l_taille = self._titre("")
        dv.addWidget(self.l_taille)
        self.s_taille = QSlider(Qt.Orientation.Horizontal)
        self.s_taille.setRange(1, 80)
        self.s_taille.setValue(8)
        self.s_taille.valueChanged.connect(self._taille)
        dv.addWidget(self.s_taille)
        self.l_opac = self._titre("")
        dv.addWidget(self.l_opac)
        self.s_opac = QSlider(Qt.Orientation.Horizontal)
        self.s_opac.setRange(5, 100)
        self.s_opac.setValue(100)
        self.s_opac.valueChanged.connect(self._opac)
        dv.addWidget(self.s_opac)
        self.c_sym = QCheckBox(tr("Symétrie (parfait pour un visage)"))
        self.c_sym.toggled.connect(lambda v: (setattr(self.toile, "symetrie", v), self.toile.update()))
        dv.addWidget(self.c_sym)
        self.c_guide = QCheckBox(tr("Silhouette guide"))
        self.c_guide.toggled.connect(lambda v: (setattr(self.toile, "guide", v), self.toile.update()))
        dv.addWidget(self.c_guide)
        self.b_net2 = QPushButton(tr("✨ Améliorer l'image (flou, pixels)…"))
        self.b_net2.setToolTip(tr("Pour le calque choisi : rend plus net, ou lisse les gros pixels."))
        self.b_net2.clicked.connect(lambda: self._menu_nettete(self.b_net2))
        dv.addWidget(self.b_net2)
        self.b_retour_net2 = QPushButton(tr("↩️ Retour (enlever la retouche)"))
        self.b_retour_net2.clicked.connect(self.retour_net)
        dv.addWidget(self.b_retour_net2)
        h = QHBoxLayout()
        b = QPushButton(tr("🧽 Enlever le fond"))
        b.setToolTip(tr("Enlève le fond du calque choisi (même en dégradé)."))
        b.clicked.connect(self.enlever_fond)
        h.addWidget(b)
        b = QPushButton(tr("🪄 Baguette"))
        b.setToolTip(tr("Clique ensuite sur un reste de fond pour l'effacer."))
        b.clicked.connect(lambda: self.outil("baguette"))
        h.addWidget(b)
        dv.addLayout(h)
        dv.addStretch(1)
        self.onglets.addTab(self._defilant(ow), tr("🎨 Dessin"))
        self.onglets.addTab(self._defilant(self._onglet_animation()), tr("🎬 Animation"))
        h = QHBoxLayout()
        h.addWidget(self._titre(tr("Calques")), 1)
        for txt, tip, fn in (("🖼️", tr("Ajouter une image ou un perso en calque…"), self.importer_calque),
                             ("＋", tr("Ajouter un calque"), self.ajouter_calque),
                             ("－", tr("Supprimer le calque"), self.supprimer_calque),
                             ("↑", tr("Monter"), lambda: self.deplacer_calque(1)),
                             ("↓", tr("Descendre"), lambda: self.deplacer_calque(-1))):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.setFixedSize(32, 30)
            b.clicked.connect(fn)
            h.addWidget(b)
        droite.addLayout(h)
        self.liste = QListWidget()
        self.liste.setMinimumHeight(80)
        self.liste.itemChanged.connect(self._calque_coche)
        self.liste.currentRowChanged.connect(self._calque_choisi)
        self.liste.itemDoubleClicked.connect(self._renommer)
        droite.addWidget(self.liste, 1)
        self.liste.setMaximumHeight(120)
        self.l_copac = QLabel()
        droite.addWidget(self.l_copac)
        self.s_copac = QSlider(Qt.Orientation.Horizontal)
        self.s_copac.setRange(0, 100)
        self.s_copac.valueChanged.connect(self._calque_opac)
        droite.addWidget(self.s_copac)
        aide = QLabel(tr("Clic droit : pipette · Ctrl + molette : zoom · clic molette ou Espace : déplacer · "
                         "Ctrl+Z / Ctrl+Y : annuler / refaire"))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#9b8a93; font-size:9pt;")
        aide.setVisible(False)
        self.toile.setToolTip(aide.text())
        droite.addWidget(aide)
        for seq, fn in (("Ctrl+Z", lambda: self.toile.annuler()), ("Ctrl+Y", lambda: self.toile.refaire()),
                        ("Ctrl+Shift+Z", lambda: self.toile.refaire()), ("Ctrl+S", self.enregistrer),
                        ("B", lambda: self.outil("pinceau")), ("E", lambda: self.outil("gomme")),
                        ("P", lambda: self.outil("crayon")), ("G", lambda: self.outil("remplir")),
                        ("[", lambda: self.s_taille.setValue(self.s_taille.value() - 2)),
                        ("]", lambda: self.s_taille.setValue(self.s_taille.value() + 2))):
            QShortcut(QKeySequence(seq), self, activated=fn)
        self.outil("feutre")
        self.choisir_couleur(QColor("#2e1624"))
        self._taille(8)
        self._opac(100)
        self._liste_calques()
        self._maj_retour()
        try:
            import i18n
            i18n.translate_widget(self)
        except Exception:
            pass

    # ---------- petits bouts
    def _defilant(self, w):
        """Un onglet qui défile au lieu de s'écraser quand l'écran est petit."""
        sa = QScrollArea()
        self.__dict__.setdefault("_pages", []).append(w)
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w.setMinimumWidth(0)
        return sa

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._hauteurs)
        QTimer.singleShot(300, self._hauteurs)

    def _hauteurs(self):
        for w in getattr(self, "_pages", []):           # jamais écrasé : l'onglet défile
            for lab in w.findChildren(QLabel):
                if lab.wordWrap():                      # hauteur fixe : pas de calcul « hauteur selon largeur »
                    lab.ensurePolished()
                    larg = max(160, w.parentWidget().width() - 16 if w.parentWidget() else 250)
                    hh = lab.fontMetrics().boundingRect(QRect(0, 0, larg, 9999), Qt.TextFlag.TextWordWrap,
                                                        lab.text()).height() + 6
                    sp = lab.sizePolicy()
                    sp.setHeightForWidth(False)
                    lab.setSizePolicy(sp)
                    lab.setMinimumHeight(hh)
            w.layout().invalidate()
            w.setMinimumHeight(w.layout().sizeHint().height())

    def _titre(self, t):
        l = QLabel(t)
        l.setStyleSheet("font-weight:700;")
        return l

    def dire(self, t):
        try:
            self.comp.say(t)
        except Exception:
            pass

    def keyPressEvent(self, e):
        t = self.toile
        if e.key() == Qt.Key.Key_Escape and (t.mode_lasso or t.mode_visage is not None or t.mode_pivot or
                                             t.mode_trajet):
            if t.mode_visage is not None:
                return self.finir_visage()
            t.mode_lasso = t.mode_pivot = t.mode_trajet = False
            t.lasso = t.trajet_en_cours = None
            self._mode_lasso = ""
            t.unsetCursor()
            t.update()
            return self.dire("D'accord, on laisse comme ça.")
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.toile.espace = True
            self.toile.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.toile.espace = False
            self.toile.unsetCursor()
        super().keyReleaseEvent(e)

    def outil(self, k):
        self.toile.outil = k
        for cle, b in self.b_outils.items():
            b.setChecked(cle == k)
        self.toile.setCursor(Qt.CursorShape.CrossCursor if k not in ("pipette",) else Qt.CursorShape.PointingHandCursor)

    def choisir_couleur(self, c):
        self.toile.couleur = QColor(c)
        pm = QPixmap(34, 34)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(c))
        p.setPen(QPen(QColor("#d9c2cd"), 1))
        p.drawRoundedRect(QRectF(1, 1, 32, 32), 8, 8)
        p.end()
        self.apercu.setPixmap(pm)
        if self.toile.outil in ("gomme", "pipette"):
            self.outil("feutre")

    def _roue(self):
        c = QColorDialog.getColor(self.toile.couleur, self, tr("Choisis une couleur"))
        if c.isValid():
            self.choisir_couleur(c)

    def _taille(self, v):
        self.toile.taille = v
        self.l_taille.setText(tr("Taille du trait") + f" : {v} px")

    def _opac(self, v):
        self.toile.opacite = v / 100.0
        self.l_opac.setText(tr("Opacité") + f" : {v} %")

    def trait_fini(self, n):
        if n % 35 == 0 and time.monotonic() - self.dernier_bravo > 150 and random.random() < 0.7:
            self.dernier_bravo = time.monotonic()
            self.dire(random.choice(BRAVO))

    # ---------- calques
    def _liste_calques(self):
        self.liste.blockSignals(True)
        self.liste.clear()
        for c in reversed(self.toile.calques):           # le calque du haut en premier, comme partout
            it = QListWidgetItem(("🎬 " if self.toile.bouge(c) else "") + c["nom"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c["visible"] else Qt.CheckState.Unchecked)
            self.liste.addItem(it)
        self.liste.setCurrentRow(len(self.toile.calques) - 1 - self.toile.actif)
        self.liste.blockSignals(False)
        self._maj_copac()
        self._maj_anim()

    def _index(self, row):
        return len(self.toile.calques) - 1 - row

    def _maj_copac(self):
        c = self.toile.calques[self.toile.actif]
        self.s_copac.blockSignals(True)
        self.s_copac.setValue(int(c["opacite"] * 100))
        self.s_copac.blockSignals(False)
        self.l_copac.setText(tr("Opacité du calque") + f" : {int(c['opacite'] * 100)} %")

    def _calque_choisi(self, row):
        if row >= 0:
            self.toile.actif = self._index(row)
            self.toile.annuler_pile.clear()
            self._maj_copac()
            self._maj_anim()

    def _calque_coche(self, it):
        i = self._index(self.liste.row(it))
        self.toile.calques[i]["visible"] = it.checkState() == Qt.CheckState.Checked
        self.toile.update()

    def _calque_opac(self, v):
        self.toile.calques[self.toile.actif]["opacite"] = v / 100.0
        self.l_copac.setText(tr("Opacité du calque") + f" : {v} %")
        self.toile.update()

    def _renommer(self, it):
        i = self._index(self.liste.row(it))
        nom, ok = QInputDialog.getText(self, tr("Renommer le calque"), tr("Nom :"), text=self.toile.calques[i]["nom"])
        if ok and nom.strip():
            self.toile.calques[i]["nom"] = nom.strip()
            self._liste_calques()

    def ajouter_calque(self):
        t = self.toile
        if len(t.calques) >= 16:
            return self.dire("16 calques, c'est le maximum !")
        t.calques.insert(t.actif + 1, {"nom": tr("Calque") + f" {len(t.calques)}", "img": _vide(TAILLE, TAILLE),
                                       "visible": True, "opacite": 1.0})
        t.actif += 1
        t.annuler_pile.clear()
        self._liste_calques()

    def supprimer_calque(self):
        t = self.toile
        if len(t.calques) <= 1:
            return
        if QMessageBox.question(self, tr("Supprimer le calque"),
                                tr("Supprimer le calque") + f" « {t.calques[t.actif]['nom']} » ?") != \
                QMessageBox.StandardButton.Yes:
            return
        del t.calques[t.actif]
        t.actif = max(0, t.actif - 1)
        t.annuler_pile.clear()
        t.refaire_pile.clear()
        self._liste_calques()
        t.update()

    def deplacer_calque(self, sens):
        t = self.toile
        j = t.actif + sens
        if 0 <= j < len(t.calques):
            t.calques[t.actif], t.calques[j] = t.calques[j], t.calques[t.actif]
            t.actif = j
            t.annuler_pile.clear()
            self._liste_calques()
            t.update()

    # ---------- fichiers
    def _confirmer_perte(self):
        if not self.toile.modifie:
            return True
        r = QMessageBox.question(self, tr("Carnet de dessin"), tr("Enregistrer ton dessin avant ?"),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                 QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        return self.enregistrer() if r == QMessageBox.StandardButton.Yes else True

    def nouveau(self):
        if self._confirmer_perte():
            self.toile.nouveau()
            self.fichier = None
            self._liste_calques()

    def enregistrer(self, demander=False):
        if self.fichier is None or demander:
            nom = time.strftime("dessin-%Y-%m-%d-%H%M")
            p, _ = QFileDialog.getSaveFileName(self, tr("Enregistrer le dessin"), str(dossier_dessins() / f"{nom}.ora"),
                                               tr("Dessin avec calques (*.ora);;Image (*.png)"))
            if not p:
                return False
            self.fichier = Path(p)
        p = self.fichier
        try:
            if p.suffix.lower() == ".png":
                self.toile.image_finale().save(str(p))
            else:
                if p.suffix.lower() != ".ora":
                    p = self.fichier = p.with_suffix(".ora")
                self._ecrire_ora(p)
                self.toile.image_finale().save(str(p.with_suffix(".png")))
        except Exception as e:
            QMessageBox.warning(self, tr("Carnet de dessin"), tr("L'enregistrement n'a pas marché :") + f"\n{e}")
            return False
        self.toile.modifie = False
        self.dire("C'est noté !" if random.random() < 0.5 else "Hihi, ça me plaît beaucoup !")
        return True

    def _ecrire_ora(self, p):
        t = self.toile
        tmp = p.with_suffix(".ora.tmp")
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster", compress_type=zipfile.ZIP_STORED)
            pile = []
            for i, c in reversed(list(enumerate(t.calques))):
                src = f"data/calque{i}.png"
                z.writestr(src, _png(c["img"]), compress_type=zipfile.ZIP_DEFLATED)
                pile.append(f'  <layer name={quoteattr(c["nom"])} src="{src}" x="0" y="0" opacity="{c["opacite"]:.2f}" '
                            f'visibility="{"visible" if c["visible"] else "hidden"}"/>')
            xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<image version="0.0.3" w="{TAILLE}" h="{TAILLE}">\n'
                   '<stack>\n' + "\n".join(pile) + '\n</stack>\n</image>\n')
            z.writestr("stack.xml", xml, compress_type=zipfile.ZIP_DEFLATED)
            infos = {}                                     # l'animation (Viki seulement ; les autres l'ignorent)
            for i, c in enumerate(t.calques):
                d = {k: c[k] for k in ("anim", "trajet", "trajet_duree", "cadence", "oignon", "uid", "suit", "de",
                                       "element", "visage") if c.get(k) is not None}
                fr = c.get("frames") or []
                if len(fr) > 1:
                    d["images"] = []
                    for k, img in enumerate(fr):
                        nom = f"data/calque{i}_image{k}.png"
                        z.writestr(nom, _png(img), compress_type=zipfile.ZIP_DEFLATED)
                        d["images"].append(nom)
                    d["cur"] = c.get("cur", 0)
                if d:
                    infos[str(i)] = d
            if infos:
                import json
                z.writestr("viki-animation.json", json.dumps(infos), compress_type=zipfile.ZIP_DEFLATED)
            fin = t.image_finale()
            z.writestr("mergedimage.png", _png(fin), compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("Thumbnails/thumbnail.png", _png(fin.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation)),
                       compress_type=zipfile.ZIP_DEFLATED)
        tmp.replace(p)

    def ouvrir(self):
        if not self._confirmer_perte():
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("Ouvrir un dessin"), str(dossier_dessins()),
                                           tr("Dessins et images (*.ora *.png *.jpg *.jpeg *.webp)"))
        if not p:
            return
        p = Path(p)
        try:
            calques = self._lire_ora(p) if p.suffix.lower() == ".ora" else None
            if calques is None:
                img = QImage(str(p))
                if img.isNull():
                    raise RuntimeError(tr("image illisible"))
                img, msg_net = self._corriger_import(img)
                if msg_net:
                    QTimer.singleShot(800, lambda m=msg_net: self.dire(m))
                calques = [{"nom": tr("Fond"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0},
                           {"nom": p.stem, "img": self._ajuster(img), "visible": True, "opacite": 1.0}]
        except Exception as e:
            return QMessageBox.warning(self, tr("Carnet de dessin"), tr("Je n'arrive pas à ouvrir ce fichier :") +
                                       f"\n{e}")
        t = self.toile
        t.calques = calques
        self.histo_anim = []
        self.avant_net = []
        orig = self.__dict__.pop("_original_import", None)
        if orig is not None and len(calques) == 2:
            self.avant_net.append((calques[1], self._ajuster(orig), None))
        self._maj_retour()
        t.actif = len(calques) - 1
        t.annuler_pile, t.refaire_pile = [], []
        t.modifie = False
        self.fichier = p if p.suffix.lower() == ".ora" else None
        self._liste_calques()
        t.update()

    def _ajuster(self, img):
        """Une image quelconque, centrée sur la feuille carrée."""
        img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        if img.width() > TAILLE or img.height() > TAILLE:
            img = img.scaled(TAILLE, TAILLE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out = _vide(TAILLE, TAILLE)
        p = QPainter(out)
        p.drawImage((TAILLE - img.width()) // 2, (TAILLE - img.height()) // 2, img)
        p.end()
        return out

    def _lire_ora(self, p):
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(p) as z:
            root = ET.fromstring(z.read("stack.xml"))
            W, H = int(root.get("w", TAILLE)), int(root.get("h", TAILLE))
            calques = []
            for el in root.iter("layer"):
                src = QImage.fromData(z.read(el.get("src")))
                if src.isNull():
                    continue
                feuille = _vide(W, H)
                pa = QPainter(feuille)
                pa.drawImage(int(float(el.get("x", 0))), int(float(el.get("y", 0))), src)
                pa.end()
                calques.append({"nom": el.get("name") or tr("Calque"), "img": self._ajuster(feuille),
                                "visible": el.get("visibility", "visible") != "hidden",
                                "opacite": float(el.get("opacity", 1) or 1)})
                if len(calques) >= 12:
                    break
            if not calques:
                return None
            calques.reverse()                             # stack.xml : le haut en premier
            if "viki-animation.json" in z.namelist():
                import json
                infos = json.loads(z.read("viki-animation.json"))
                for i, d in infos.items():
                    i = int(i)
                    if i >= len(calques):
                        continue
                    c = calques[i]
                    for k in ("anim", "trajet", "trajet_duree", "cadence", "oignon", "uid", "suit", "de", "element",
                              "visage"):
                        if k in d:
                            c[k] = [tuple(x) for x in d[k]] if k == "trajet" else d[k]
                    if d.get("images"):
                        fr = [self._ajuster(QImage.fromData(z.read(n))) for n in d["images"]]
                        c["frames"] = fr
                        c["cur"] = min(int(d.get("cur", 0)), len(fr) - 1)
                        c["img"] = fr[c["cur"]]
        return calques

    def decalque(self):
        t = self.toile
        if t.decalque is not None:
            t.decalque = None
            t.update()
            return self.dire("C'est enlevé.")
        p, _ = QFileDialog.getOpenFileName(self, tr("Image à décalquer"), str(Path.home()),
                                           tr("Images (*.png *.jpg *.jpeg *.webp)"))
        if p:
            img = QImage(p)
            if not img.isNull():
                t.decalque = self._ajuster(img)
                t.update()

    # ---------- animation
    def _onglet_animation(self):
        """L'animation, guidée en 3 étapes (le mode avancé garde tous les réglages)."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(8)
        gros = QFont()
        gros.setPointSizeF(11.5)
        gros.setBold(True)

        def etape(txt):
            lab = QLabel(tr(txt))
            lab.setFont(gros)
            lab.setWordWrap(True)
            v.addWidget(lab)
            return lab
        b = QPushButton(tr("↶ Annuler la dernière animation"))
        b.setMinimumHeight(36)
        b.setToolTip(tr("Revient en arrière d'une étape : mouvement, zone, yeux, déplacement…"))
        b.clicked.connect(self.annuler_anim)
        v.addWidget(b)
        etape("1. Qu'est-ce qui bouge ?")
        self.l_acalque = QLabel()
        self.l_acalque.setWordWrap(True)
        f = self.l_acalque.font()
        f.setPointSizeF(10.5)
        self.l_acalque.setFont(f)
        v.addWidget(self.l_acalque)
        self.b_lasso = QPushButton(tr("✂️ Entourer ce qui bouge"))
        self.b_lasso.setObjectName("main")
        self.b_lasso.setMinimumHeight(40)
        self.b_lasso.setToolTip(tr("Entoure à la souris le perso ou l'objet à animer : il passe sur son propre calque."))
        self.b_lasso.clicked.connect(self._lasso)
        v.addWidget(self.b_lasso)
        b = QPushButton(tr("➕ Ajouter un bout de dessin…"))
        b.setMinimumHeight(34)
        b.setToolTip(tr("Un autre dessin ou une image : tu entoures le bout à garder, puis tu le places."))
        b.clicked.connect(self.ajouter_bout)
        v.addWidget(b)
        # ce qu'on peut faire avec l'élément choisi
        self.w_elem = QFrame()
        self.w_elem.setObjectName("elem")
        self.w_elem.setStyleSheet("QFrame#elem { border: 1px solid #ecd3df; border-radius: 10px; } "
                                  "QFrame#elem QPushButton { padding: 5px 3px; }")
        ge = QGridLayout(self.w_elem)
        ge.setContentsMargins(6, 6, 6, 6)
        ge.setSpacing(5)

        def bouton(txt, tip, fn, r, col, span=1):
            bb = QPushButton(tr(txt))
            bb.setToolTip(tr(tip))
            bb.setMinimumHeight(34)
            bb.clicked.connect(fn)
            ge.addWidget(bb, r, col, 1, span)
            return bb
        bouton("👀 Yeux, bouche", "Clique sur ses yeux et sa bouche : il clignera des yeux et pourra parler.",
               self.commencer_visage, 0, 0)
        bouton("🙂 Sa tête", "Entoure sa tête : elle bougera en plus du reste.", self._tete, 0, 1)
        self.b_sans_bouche = bouton("✔️ Pas de bouche", "", self.finir_visage, 1, 0, 2)
        self.b_sans_bouche.setVisible(False)
        self.b_cligne = bouton("😉 Cligne", "", lambda: self._visage_opt("cligne", self.b_cligne.isChecked()),
                               2, 0)
        self.b_parle = bouton("💬 Parle", "", lambda: self._visage_opt("parle", self.b_parle.isChecked()), 2, 1)
        for bb in (self.b_cligne, self.b_parle):
            bb.setCheckable(True)
        bouton("✋ Déplacer", "Puis fais-le glisser sur le dessin.", lambda: self.outil("deplacer"), 3, 0)
        hh = QHBoxLayout()
        for txt, k in (("➖", 1 / 1.15), ("➕", 1.15)):
            bb = QPushButton(txt)
            bb.setToolTip(tr("Plus petit") if k < 1 else tr("Plus grand"))
            bb.setMinimumHeight(34)
            bb.clicked.connect(lambda _=False, kk=k: self._taille_element(kk))
            hh.addWidget(bb)
        ge.addLayout(hh, 3, 1)
        self.b_net = bouton("✨ Netteté", "Corrige une image floue ou pixelisée (toute l'image ou une zone).",
                            lambda: self._menu_nettete(self.b_net), 5, 0)
        self.b_retour_net = bouton("↩️ Retour", "Enlève la dernière retouche de netteté.", self.retour_net, 5, 1)
        bouton("🧽 Enlever le fond", "Enlève le fond de cet élément (même en dégradé).", self.enlever_fond, 6, 0)
        bouton("🪄 Baguette", "Clique ensuite sur un reste de fond pour l'effacer.", lambda: self.outil("baguette"), 6, 1)
        bouton("↩️ Annuler zone", "Il retourne dans le dessin et ne bouge plus.", self.remettre, 4, 0)
        bouton("🧑‍🎨 En perso", "Seulement lui (et ce qui le suit) devient un perso de Viki.",
               lambda: self.en_perso(seul=self._element()), 4, 1)
        v.addWidget(self.w_elem)
        etape("2. Comment ça bouge ?")
        g = QGridLayout()
        g.setSpacing(6)
        self.tuiles = {}
        for i, (k, ico, nom) in enumerate(TUILES):
            b = QToolButton()
            b.setText(ico + "\n" + tr(nom))
            b.setCheckable(True)
            b.setMinimumSize(110, 52)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setStyleSheet("QToolButton { border: 1px solid #ecd3df; border-radius: 10px; background: white; "
                            "font-size: 10pt; padding: 3px; } QToolButton:checked { border: 3px solid #b0336a; "
                            "background: #fdf0f5; font-weight: 700; }")
            b.clicked.connect(lambda _=False, kk=k: self._tuile(kk))
            g.addWidget(b, i // 2, i % 2)
            self.tuiles[k] = b
        v.addLayout(g)
        self.etape3 = etape("3. Comment ?")
        h = QHBoxLayout()
        self.b_forces = {}
        for val, nom in ((22, "Un peu"), (45, "Moyen"), (80, "Beaucoup")):
            b = QPushButton(tr(nom))
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _=False, vv=val: self.s_force.setValue(vv))
            h.addWidget(b)
            self.b_forces[val] = b
        v.addLayout(h)
        h = QHBoxLayout()
        self.b_vites = {}
        for val, nom in ((1, "🐢 Lent"), (2, "🚶 Normal"), (3, "🐇 Vite")):
            b = QPushButton(tr(nom))
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _=False, vv=val: self.c_vit.setCurrentIndex(self.c_vit.findData(vv)))
            h.addWidget(b)
            self.b_vites[val] = b
        v.addLayout(h)
        self.b_tient = QPushButton(tr("📍 Où ça tient ?"))
        self.b_tient.setMinimumHeight(36)
        self.b_tient.setToolTip(tr("Pour une canne, un bras, une porte : le point qui ne bouge pas (la main, la charnière)."))
        self.b_tient.clicked.connect(lambda: self._choisir_pivot())
        v.addWidget(self.b_tient)
        etape("4. Et après ?")
        b = QPushButton(tr("✂️ Animer autre chose"))
        b.setMinimumHeight(36)
        b.clicked.connect(self._lasso)
        v.addWidget(b)
        b = QPushButton(tr("🎞️ Enregistrer l'animation"))
        b.setMinimumHeight(36)
        b.clicked.connect(self.exporter_anim)
        v.addWidget(b)
        self.c_avance = QCheckBox(tr("⚙️ Mode avancé"))
        v.addWidget(self.c_avance)
        avance = self._anim_avance()
        avance.setVisible(False)
        self.c_avance.toggled.connect(lambda oui: (avance.setVisible(oui), QTimer.singleShot(0, self._hauteurs)))
        v.addWidget(avance)
        v.addStretch(1)
        self._maj_anim()
        return w

    def _animer(self):
        self.onglets.setCurrentIndex(1)
        t = self.toile
        c = self._cal()
        b = boite_calque(c["img"])
        if t.actif == 0 or b is None or b.width() * b.height() > 0.4 * TAILLE * TAILLE:
            self._lasso()
        else:
            self.dire("Choisis comment ça bouge, à droite. Pour animer autre chose, clique sur « ✂️ Animer autre "
                      "chose ».")

    def _tuile(self, k):
        if k == "trajet":
            self.c_avance.setChecked(True)
            self._maj_tuiles()
            return self._tracer()
        if k == "images":
            self.c_avance.setChecked(True)
            self._maj_tuiles()
            return self.dire("Image par image : clique sur « ➕ Copie » et redessine un peu à chaque image, "
                             "comme un dessin animé !")
        c = self._cal()
        if not k:
            self.c_anim.setCurrentIndex(0)
        else:
            if self.toile.actif == 0 and len(self.toile.calques) > 1 and boite_calque(c["img"]) is None:
                return self.dire("Entoure d'abord ce qui doit bouger !")
            self.c_anim.setCurrentIndex(self.c_anim.findData(k))
            if k in ("balancer", "pivoter") and (c.get("anim") or {}).get("pivot") != "clic":
                self.dire("Super ! Clique maintenant sur « 📍 Où ça tient ? », puis sur le point qui ne bouge "
                          "pas (la main qui tient la canne, par exemple).")
            else:
                self.dire(random.choice(["Regarde-le bouger ! Tu peux régler en dessous.",
                                         "C'est parti ! Un peu, moyen ou beaucoup : à toi de voir.",
                                         "Trop bien ! Pour animer autre chose, clique sur « ✂️ Animer autre chose »."]))
        self._maj_tuiles()

    def _maj_tuiles(self):
        if not hasattr(self, "tuiles"):
            return
        c = self._cal()
        typ = (c.get("anim") or {}).get("type", "")
        for k, b in self.tuiles.items():
            b.setChecked(k == typ if k not in ("trajet", "images") else
                         (k == "trajet" and len(c.get("trajet") or []) > 1) or
                         (k == "images" and len(c.get("frames") or []) > 1))
        an = c.get("anim") or {}
        f = int(an.get("force", 40))
        proche = min(self.b_forces, key=lambda x: abs(x - f))
        for val, b in self.b_forces.items():
            b.setChecked(bool(typ) and val == proche)
        for val, b in self.b_vites.items():
            b.setChecked(bool(typ) and val == int(an.get("vitesse", 2) or 2))
        for b in list(self.b_forces.values()) + list(self.b_vites.values()):
            b.setEnabled(bool(typ))
        self.b_tient.setVisible(typ in ("balancer", "pivoter", "tourner", "etirer", "zoomer", "pulser"))
        el = self._element()
        self.w_elem.setVisible(el is not None)
        vis = c.get("visage") or {}
        QTimer.singleShot(0, self._hauteurs)
        for bb, cle, ok in ((self.b_cligne, "cligne", bool(vis.get("yeux"))),
                            (self.b_parle, "parle", bool(vis.get("bouche")))):
            bb.setVisible(ok)
            bb.setChecked(bool(vis.get(cle, cle == "cligne")))
        b = boite_calque(c["img"])
        tout = b is not None and b.width() * b.height() > 0.4 * TAILLE * TAILLE
        if self.toile.actif == 0 and len(self.toile.calques) > 1:
            self.l_acalque.setText(tr("Rien de choisi. Clique sur le bouton, puis entoure le perso ou l'objet."))
        elif tout:
            self.l_acalque.setText(tr("Le calque choisi contient tout le dessin : entoure plutôt une seule chose."))
        else:
            nom = c["nom"] if len(c["nom"]) <= 22 else c["nom"][:21] + "…"
            self.l_acalque.setText(tr("Choisi :") + f" « {nom} »")

    def _anim_avance(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        v.addWidget(self._titre(tr("Mouvement")))
        self.c_anim = QComboBox()
        for k, nom in ANIMS:
            self.c_anim.addItem(tr(nom), k)
        self.c_anim.currentIndexChanged.connect(self._anim_change)
        v.addWidget(self.c_anim)
        def ligne(nom, widget):
            h = QHBoxLayout()
            lab = QLabel(tr(nom))
            lab.setFixedWidth(72)
            h.addWidget(lab)
            if isinstance(widget, QHBoxLayout):
                h.addLayout(widget, 1)
            else:
                h.addWidget(widget, 1)
            v.addLayout(h)
        self.c_vit = QComboBox()
        for k, nom in VITESSES:
            self.c_vit.addItem(tr(nom), k)
        self.c_vit.currentIndexChanged.connect(self._anim_change)
        ligne("Vitesse", self.c_vit)
        self.c_piv = QComboBox()
        for k, nom in PIVOTS:
            self.c_piv.addItem(tr(nom), k)
        self.c_piv.currentIndexChanged.connect(self._anim_change)
        hp = QHBoxLayout()
        hp.addWidget(self.c_piv, 1)
        bp = QPushButton("📍")
        bp.setToolTip(tr("Choisir le point d'accroche en cliquant sur le dessin"))
        bp.setFixedWidth(40)
        bp.clicked.connect(self._choisir_pivot)
        hp.addWidget(bp)
        ligne("Accroche", hp)
        self.s_force = QSlider(Qt.Orientation.Horizontal)
        self.s_force.setRange(5, 100)
        self.s_force.valueChanged.connect(self._anim_change)
        ligne("Force", self.s_force)
        self.c_inverse = QCheckBox(tr("↔ Inverser le sens"))
        self.c_inverse.toggled.connect(self._anim_change)
        v.addWidget(self.c_inverse)
        v.addWidget(self._titre(tr("Trajet")))
        h = QHBoxLayout()
        self.b_trajet = QPushButton(tr("✏️ Tracer"))
        self.b_trajet.setToolTip(tr("Trace le chemin à la souris, en partant de l'élément : il le suivra en boucle."))
        self.b_trajet.clicked.connect(self._tracer)
        h.addWidget(self.b_trajet)
        b = QPushButton(tr("🗑️"))
        b.setToolTip(tr("Effacer le trajet"))
        b.setFixedWidth(40)
        b.clicked.connect(self._effacer_trajet)
        h.addWidget(b)
        self.c_tduree = QComboBox()
        for k, nom in DUREES_TRAJET:
            self.c_tduree.addItem(tr(nom), k)
        self.c_tduree.currentIndexChanged.connect(self._anim_change)
        h.addWidget(self.c_tduree, 1)
        v.addLayout(h)
        v.addWidget(self._titre(tr("Image par image")))
        h = QHBoxLayout()
        for txt, tip, fn in (("◀", tr("Image précédente"), lambda: self._image(-1)),
                             ("▶", tr("Image suivante"), lambda: self._image(1))):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.setFixedWidth(36)
            b.clicked.connect(fn)
            h.addWidget(b)
        self.l_image = QLabel()
        self.l_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.l_image, 1)
        v.addLayout(h)
        h = QHBoxLayout()
        for txt, tip, fn in ((tr("➕ Copie"), tr("Nouvelle image : copie de celle-ci, à modifier"), lambda: self._nouvelle_image(True)),
                             (tr("➕ Vide"), tr("Nouvelle image vide"), lambda: self._nouvelle_image(False)),
                             ("🗑️", tr("Supprimer cette image"), self._suppr_image)):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
        v.addLayout(h)
        h = QHBoxLayout()
        self.c_oignon = QCheckBox(tr("Pelure d'oignon"))
        self.c_oignon.setChecked(True)
        self.c_oignon.toggled.connect(self._anim_change)
        h.addWidget(self.c_oignon)
        self.c_cad = QComboBox()
        for k, nom in CADENCES:
            self.c_cad.addItem(tr(nom), k)
        self.c_cad.setCurrentIndex(1)
        self.c_cad.currentIndexChanged.connect(self._anim_change)
        h.addWidget(self.c_cad)
        v.addLayout(h)
        self.b_jouer = QPushButton(tr("▶ Voir bouger"))
        self.b_jouer.setObjectName("main")
        self.b_jouer.setCheckable(True)
        self.b_jouer.toggled.connect(self._jouer)
        v.addWidget(self.b_jouer)
        b = QPushButton(tr("🎞️ Exporter en image animée…"))
        b.clicked.connect(self.exporter_anim)
        v.addWidget(b)
        astuce = QLabel(tr("Astuce : mets chaque chose qui bouge sur son propre calque. On peut mélanger mouvement, "
                           "trajet et image par image."))
        astuce.setWordWrap(True)
        astuce.setStyleSheet("color:#9b8a93; font-size:9pt;")
        v.addWidget(astuce)
        v.addStretch(1)
        self._maj_anim()
        return w

    def _cal(self):
        return self.toile.calques[self.toile.actif]

    def _maj_anim(self):
        if not hasattr(self, "c_anim"):
            return
        c = self._cal()
        an = c.get("anim") or {}
        self._maj_en_cours = True
        for combo, val in ((self.c_anim, an.get("type", "")), (self.c_vit, an.get("vitesse", 2)),
                           (self.c_piv, an.get("pivot", "bas" if an.get("type") == "balancer" else "centre")),
                           (self.c_tduree, c.get("trajet_duree", 4.0)), (self.c_cad, c.get("cadence", 6))):
            i = combo.findData(val)
            combo.setCurrentIndex(max(0, i))
        self.s_force.setValue(int(an.get("force", 40)))
        self.c_inverse.setChecked(bool(an.get("inverse")))
        self.c_oignon.setChecked(c.get("oignon", True))
        self._maj_en_cours = False
        fr = c.get("frames") or [c["img"]]
        self.l_image.setText(tr("Image") + f" {c.get('cur', 0) + 1} / {len(fr)}")
        self._maj_tuiles()

    def _anim_change(self, *_a):
        if getattr(self, "_maj_en_cours", False):
            return
        self._histo(regrouper=True)
        c = self._cal()
        typ = self.c_anim.currentData() or ""
        if typ:
            ancien = c.get("anim") or {}
            c["anim"] = {"type": typ, "vitesse": self.c_vit.currentData(), "force": self.s_force.value(),
                         "pivot": self.c_piv.currentData(), "inverse": self.c_inverse.isChecked(),
                         "px": ancien.get("px"), "py": ancien.get("py")}
            if c["anim"]["pivot"] == "clic" and (ancien.get("pivot") != "clic" or ancien.get("px") is None) \
                    and not getattr(self, "_maj_en_cours", False):
                self.b_jouer.setChecked(False)
                self.toile.mode_pivot = True
                self.dire("Clique sur le dessin à l'endroit où ça doit tenir (une main, une charnière…).")
        else:
            c.pop("anim", None)
        c["trajet_duree"] = self.c_tduree.currentData()
        c["cadence"] = self.c_cad.currentData()
        c["oignon"] = self.c_oignon.isChecked()
        c["_boite"] = None
        self.toile.modifie = True
        b = boite_calque(c["img"]) if typ else None
        if typ and self.toile.actif == 0 and len(self.toile.calques) > 1:
            self.dire("Ce calque est le fond : tout bougera ensemble. Mets ce qui bouge sur un autre calque !")
        elif b is not None and b.width() * b.height() > 0.4 * TAILLE * TAILLE and not c.get("_averti"):
            c["_averti"] = True
            self.dire("Tout ton dessin est sur ce calque, alors tout bouge ensemble. Clique sur « ✂️ Choisir ce "
                      "qui bouge » et entoure seulement le perso ou l'objet !")
        self._maj_tuiles()
        it = self.liste.item(len(self.toile.calques) - 1 - self.toile.actif)
        if it is not None:
            self.liste.blockSignals(True)
            it.setText(("🎬 " if self.toile.bouge(c) else "") + c["nom"])
            self.liste.blockSignals(False)
        if (typ or len(c.get("trajet") or []) > 1) and not self.b_jouer.isChecked():
            self.b_jouer.setChecked(True)
        self.toile.update()

    def _lasso(self):
        self.b_jouer.setChecked(False)
        t = self.toile
        if not any(boite_calque(c["img"]) is not None for c in t.calques if c["visible"]):
            return self.dire("Il n'y a encore rien de dessiné !")
        self._mode_lasso = ""
        t.mode_lasso, t.mode_trajet, t.mode_pivot = True, False, False
        t.setCursor(Qt.CursorShape.CrossCursor)
        self.dire("Entoure à la souris ce qui doit bouger (un perso, une canne, l'eau…), sans lâcher le bouton.")

    def _calque_sous(self, pts):
        """Le calque visible qui a le plus de dessin dans la zone entourée (le plus haut si égalité)."""
        import numpy as np
        path = QPainterPath(QPointF(*pts[0]))
        for x, y in pts[1:]:
            path.lineTo(QPointF(x, y))
        path.closeSubpath()
        r = path.boundingRect().toAlignedRect().intersected(QRect(0, 0, TAILLE, TAILLE))
        if r.isEmpty():
            return None
        masque = _vide(r.width(), r.height())
        p = QPainter(masque)
        p.translate(-r.x(), -r.y())
        p.fillPath(path, QColor(255, 255, 255))
        p.end()
        m = _tableau(masque)[:, :, 3] > 0
        t = self.toile
        meilleur, score = None, 0
        for i in range(len(t.calques) - 1, -1, -1):
            c = t.calques[i]
            if not c["visible"] or len(c.get("frames") or []) > 1:
                continue
            a = _tableau(c["img"].copy(r))[:, :, 3]
            n = int(((a > 40) & m).sum())
            if n > score * 1.15:                       # le plus haut gagne, sauf s'il y a bien plus ailleurs
                meilleur, score = i, n
        return meilleur if score > 20 else None

    def detacher(self, pts):
        t = self.toile
        mode, self._mode_lasso = getattr(self, "_mode_lasso", ""), ""
        if len(pts) < 6:
            return self.dire("Entoure bien tout le contour, sans lâcher le bouton.")
        if mode.startswith("net:"):
            return self.ameliorer_calque(mode[4:], zone=pts)
        if mode == "garder" or (mode == "tete" and self._element() is not None):
            i = t.actif
        else:
            if len(t.calques) >= 16:
                return self.dire("16 calques, c'est le maximum !")
            i = self._calque_sous(pts)
        if i is None:
            return self.dire("Je ne vois rien à détacher à cet endroit.")
        src = t.calques[i]
        try:
            reste, morceau = separer(src["img"], pts)
        except Exception:
            return self.dire("Je n'ai pas réussi, désolée.")
        if boite_calque(morceau) is None:
            return self.dire("Je ne vois rien à détacher à cet endroit.")
        self._histo()
        t.instantane([src])
        if mode == "garder":                                # un bout de dessin ajouté : on ne garde que ça
            src["img"], src["_boite"] = morceau, None
            src.pop("frames", None)
            self._liste_calques()
            t.update()
            return self.dire("Voilà, j'ai gardé ce bout-là ! Avec ✋ tu peux le déplacer, et ➖ ➕ changer sa taille.")
        src["img"], src["_boite"] = reste, None
        n = sum(1 for c in t.calques if c["nom"].startswith(tr("Élément"))) + 1
        nom = tr("Tête") if mode == "tete" else tr("Élément") + f" {n}"
        nouveau = {"nom": nom, "img": morceau, "visible": True, "opacite": src["opacite"], "element": True,
                   "de": uid(src)}
        if src.get("element"):
            nouveau["suit"] = uid(src)                      # une partie d'un perso suit le perso
        v = src.get("visage")
        if v:                                               # les yeux et la bouche entourés partent avec
            path = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                path.lineTo(QPointF(x, y))
            path.closeSubpath()
            if all(path.contains(QPointF(*e)) for e in v.get("yeux") or []):
                nouveau["visage"] = v
                src.pop("visage", None)
        t.calques.insert(i + 1, nouveau)
        t.actif = i + 1
        if mode == "tete":
            nouveau["anim"] = {"type": "balancer", "vitesse": 1, "force": 35, "pivot": "bas"}
        self._liste_calques()
        self.onglets.setCurrentIndex(1)
        if mode == "tete":
            self.b_jouer.setChecked(True)
            self.dire("Sa tête bouge ! Tu peux choisir un autre mouvement pour elle, à l'étape 2.")
        else:
            self.dire("Bravo ! Maintenant, choisis comment ça bouge (étape 2). Ctrl+Z pour annuler.")
        t.update()

    # ---------- annuler la dernière animation
    def _histo(self, regrouper=False):
        """Garde l'état de l'animation, pour le bouton « Annuler la dernière animation »."""
        t = self.toile
        now = time.monotonic()
        h = self.__dict__.setdefault("histo_anim", [])
        if regrouper and h and getattr(self, "_histo_groupe", False) and now - getattr(self, "_histo_t", 0) < 1.5:
            self._histo_t = now                         # les petits réglages d'affilée comptent pour un
            return
        self._histo_t = now
        self._histo_groupe = regrouper
        h.append((list(t.calques), [(c, dict(c, frames=list(c["frames"]) if c.get("frames") else None,
                                             anim=dict(c["anim"]) if c.get("anim") else None))
                                    for c in t.calques], t.actif))
        del h[:-30]

    def annuler_anim(self):
        h = self.__dict__.get("histo_anim") or []
        if not h:
            return self.dire("Il n'y a plus rien à annuler.")
        t = self.toile
        liste, snaps, actif = h.pop()
        t.calques = liste
        for c, d in snaps:
            c.clear()
            c.update({k: v for k, v in d.items() if v is not None or k not in ("frames", "anim")})
            c["_boite"] = None
        t.actif = min(actif, len(t.calques) - 1)
        t.annuler_pile.clear()
        t.refaire_pile.clear()
        t.modifie = True
        self._liste_calques()
        if not t.animes():
            self.b_jouer.setChecked(False)
        t.update()
        self.dire("C'est annulé !")

    # ---------- fond
    def enlever_fond(self):
        """🧽 Enlève le fond du calque choisi (ce qui touche les bords et a la couleur du fond)."""
        t = self.toile
        c = self._cal()
        if boite_calque(c["img"]) is None:
            return self.dire("Il n'y a rien sur ce calque.")
        try:
            neuf = detourer(c["img"])
        except Exception:
            return self.dire("Je n'ai pas réussi, désolée.")
        if neuf is c["img"]:
            return self.dire("Je ne trouve pas de fond à enlever. Avec 🪄, clique sur un reste de fond pour l'effacer.")
        self._histo()
        t._memo()
        c["img"], c["_boite"] = neuf, None
        if c.get("frames"):
            c["frames"] = list(c["frames"])
            c["frames"][c.get("cur", 0)] = neuf
        t.update()
        self.dire("Le fond est parti ! S'il reste des bouts, prends 🪄 et clique dessus (Ctrl+Z pour annuler).")

    def baguette(self, x, y):
        """🪄 Efface la zone de même couleur autour du clic (un reste de fond, l'intérieur d'un bras…)."""
        t = self.toile
        c = self._cal()
        if c["img"].pixelColor(int(x), int(y)).alpha() < 20:
            return self.dire("Ici c'est déjà transparent. Clique sur un reste de fond.")
        try:
            neuf = detourer(c["img"], tol=26.0, graine=(x, y))
        except Exception:
            return self.dire("Je n'ai pas réussi, désolée.")
        if neuf is c["img"]:
            return
        self._histo()
        t._memo()
        c["img"], c["_boite"] = neuf, None
        if c.get("frames"):
            c["frames"] = list(c["frames"])
            c["frames"][c.get("cur", 0)] = neuf
        t.update()

    def ouvrir_image(self, img, nom=""):
        """Ouvre une image dans le carnet (pour finir son détourage avant d'en faire un perso)."""
        if not self._confirmer_perte():
            return
        t = self.toile
        t.calques = [{"nom": tr("Fond"), "img": _vide(TAILLE, TAILLE), "visible": True, "opacite": 1.0},
                     {"nom": (nom or tr("Mon perso"))[:24], "img": self._ajuster(img), "visible": True,
                      "opacite": 1.0}]
        t.actif = 1
        t.annuler_pile, t.refaire_pile = [], []
        self.histo_anim, self.avant_net = [], []
        self.fichier = None
        t.modifie = True
        self._liste_calques()
        self.onglets.setCurrentIndex(0)
        t.update()
        self.show()
        self.raise_()
        self.dire("Avec 🪄, clique sur les restes de fond pour les effacer (la gomme marche aussi). "
                  "Puis « Faire de mon dessin un perso » !")
        self.outil("baguette")

    # ---------- netteté
    def ameliorer_calque(self, mode="auto", zone=None):
        """✨ Corrige le flou ou les pixels du calque choisi (ou seulement dans la zone entourée)."""
        t = self.toile
        c = self._cal()
        if boite_calque(c["img"]) is None:
            return self.dire("Il n'y a rien à améliorer sur ce calque.")
        pix, flou = analyser_qualite(c["img"])
        if mode == "net":
            pix, flou = 0, True
        elif mode == "pixels":
            pix, flou = pix or 4, True
        elif not pix and not flou:
            return self.dire("Ton image a l'air déjà bien nette ! Tu peux quand même choisir « Plus net ».")
        self._histo()
        t.instantane([c])
        self.__dict__.setdefault("avant_net", []).append((c, c["img"], list(c["frames"]) if c.get("frames") else None))
        del self.avant_net[:-20]

        def corrige(img):
            neuf = ameliorer(img, pix, flou)
            return melanger(img, neuf, zone) if zone else neuf
        if c.get("frames"):
            c["frames"] = [corrige(f) for f in c["frames"]]
            c["img"] = c["frames"][c.get("cur", 0)]
        else:
            c["img"] = corrige(c["img"])
        c["_boite"] = None
        self._maj_retour()
        t.update()
        self.dire("Les pixels sont lissés ! ✨ Pas content ? Clique sur « ↩️ Retour »." if pix else
                  "C'est plus net ! ✨ Pas content ? Clique sur « ↩️ Retour ».")

    def retour_net(self):
        """↩️ Annule la dernière retouche de netteté (même celle faite à l'ouverture)."""
        pile = self.__dict__.get("avant_net") or []
        t = self.toile
        while pile:
            c, img, frames = pile.pop()
            if any(c is x for x in t.calques):
                self._histo()
                c["img"], c["_boite"] = img, None
                if frames is not None:
                    c["frames"] = frames
                self._maj_retour()
                t.update()
                return self.dire("C'est revenu comme avant.")
        self._maj_retour()
        self.dire("Il n'y a pas de retouche à enlever.")

    def _maj_retour(self):
        ok = bool(self.__dict__.get("avant_net"))
        for b in (getattr(self, "b_retour_net", None), getattr(self, "b_retour_net2", None)):
            if b is not None:
                b.setEnabled(ok)

    def _zone_nettete(self, mode):
        """Entourer la zone à corriger, puis on corrige seulement là."""
        t = self.toile
        if boite_calque(self._cal()["img"]) is None:
            return self.dire("Il n'y a rien à améliorer sur ce calque.")
        self.b_jouer.setChecked(False)
        self._mode_lasso = "net:" + mode
        t.mode_lasso, t.mode_trajet, t.mode_pivot = True, False, False
        t.setCursor(Qt.CursorShape.CrossCursor)
        self.dire("Entoure la zone à corriger, sans lâcher le bouton.")

    def _menu_nettete(self, bouton):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addSection(tr("Toute l'image"))
        m.addAction(tr("✨ Automatique"), lambda: self.ameliorer_calque("auto"))
        m.addAction(tr("🔍 Plus net (image floue)"), lambda: self.ameliorer_calque("net"))
        m.addAction(tr("🧱 Lisser les pixels (image pixelisée)"), lambda: self.ameliorer_calque("pixels"))
        m.addSection(tr("Une zone seulement (à entourer)"))
        m.addAction(tr("✂️🔍 Plus net, dans une zone…"), lambda: self._zone_nettete("net"))
        m.addAction(tr("✂️🧱 Lisser les pixels, dans une zone…"), lambda: self._zone_nettete("pixels"))
        m.exec(bouton.mapToGlobal(bouton.rect().bottomLeft()))

    def _corriger_import(self, img):
        """Une image importée trop floue ou pixelisée : on la corrige tout de suite (et on le dit)."""
        try:
            pix, flou = analyser_qualite(img)
        except Exception:
            return img, ""
        self._original_import = img
        if pix:
            return ameliorer(img, pix, True), "Ton image était pixelisée : je l'ai lissée. ✨ (« ↩️ Retour » pour l'original)"
        if flou:
            return ameliorer(img, 0, True), ("Ton image était un peu floue : je l'ai rendue plus nette. ✨ "
                                             "(« ↩️ Retour » pour l'original)")
        self._original_import = None
        return img, ""

    def _element(self):
        """Le calque choisi, s'il s'agit d'un élément à part (pas le fond, pas tout le dessin)."""
        t = self.toile
        c = self._cal()
        if t.actif == 0 and len(t.calques) > 1:
            return None
        b = boite_calque(c["img"])
        if b is None:
            return None
        return c

    def transformer(self, c, m):
        """Déplace / agrandit un calque (et ce qui le suit) : images, trajet, accroche, yeux."""
        t = self.toile
        groupe = [c] + t.enfants(c)
        self._histo()
        t.instantane(groupe)

        def pt(x, y):
            q = m.map(QPointF(x, y))
            return (q.x(), q.y())
        for x in groupe:
            def img2(src):
                out = _vide(TAILLE, TAILLE)
                p = QPainter(out)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                p.setTransform(m)
                p.drawImage(0, 0, src)
                p.end()
                return out
            if x.get("frames"):
                x["frames"] = [img2(f) for f in x["frames"]]
                x["img"] = x["frames"][x.get("cur", 0)]
            else:
                x["img"] = img2(x["img"])
            x["_boite"] = None
            if x.get("trajet"):
                x["trajet"] = [pt(*q) for q in x["trajet"]]
            an = x.get("anim") or {}
            if an.get("px") is not None:
                an["px"], an["py"] = pt(an["px"], an["py"])
            v = x.get("visage")
            if v:
                v = x["visage"] = dict(v)
                v["yeux"] = [pt(*q) for q in v.get("yeux") or []]
                if v.get("bouche"):
                    v["bouche"] = pt(*v["bouche"])
                v["r"] = float(v.get("r", 14)) * math.sqrt(abs(m.determinant()))
        t.update()

    def _taille_element(self, k):
        c = self._element()
        if c is None:
            return self.dire("Choisis d'abord un élément (entoure-le, ou ajoute un bout de dessin).")
        b = boite_calque(c["img"])
        ctr = b.center()
        m = QTransform()
        m.translate(ctr.x(), ctr.y())
        m.scale(k, k)
        m.translate(-ctr.x(), -ctr.y())
        self.transformer(c, m)

    def remettre(self):
        """↩️ Annule une zone animée : l'élément retourne dans le dessin, sans mouvement."""
        t = self.toile
        c = self._element()
        if c is None or not c.get("element"):
            return self.dire("Choisis d'abord une zone animée (un élément), dans la liste des calques.")
        i = t.calques.index(c)
        cible = next((x for x in t.calques if x.get("uid") and x.get("uid") == c.get("de") and x is not c), None)
        if cible is None:
            cible = t.calques[i - 1] if i > 0 else None
        if cible is None:
            return
        self._histo()
        t.instantane([c, cible] + t.enfants(c))
        img = cible["img"].copy()
        p = QPainter(img)
        p.drawImage(0, 0, c["img"])
        p.end()
        if cible.get("frames"):
            cible["frames"] = list(cible["frames"])
            cible["frames"][cible.get("cur", 0)] = img
        cible["img"], cible["_boite"] = img, None
        for x in t.calques:
            if x.get("suit") == c.get("uid"):
                x["suit"] = c.get("suit")
        if c.get("visage") and not cible.get("visage"):
            cible["visage"] = c["visage"]
        t.calques.remove(c)
        t.actif = t.calques.index(cible)
        self._liste_calques()
        t.update()
        self.dire("C'est remis dans le dessin, il ne bouge plus. (Ctrl+Z pour revenir en arrière)")

    def ajouter_bout(self):
        """➕ Un autre bout de dessin (ou une image) : on l'ajoute, on garde ce qu'on veut, on le place."""
        t = self.toile
        if len(t.calques) >= 16:
            return self.dire("16 calques, c'est le maximum !")
        p, _ = QFileDialog.getOpenFileName(self, tr("Ajouter un bout de dessin"), str(dossier_dessins()),
                                           tr("Dessins et images (*.ora *.png *.jpg *.jpeg *.webp)"))
        if not p:
            return
        p = Path(p)
        msg_net = ""
        try:
            if p.suffix.lower() == ".ora":
                img = _vide(TAILLE, TAILLE)
                pa = QPainter(img)
                for c in self._lire_ora(p) or []:
                    if c["visible"]:
                        pa.setOpacity(c["opacite"])
                        pa.drawImage(0, 0, c["img"])
                pa.end()
            else:
                img = QImage(str(p))
                if img.isNull():
                    raise RuntimeError
                img, msg_net = self._corriger_import(img)
                img = self._ajuster(img)
        except Exception:
            return self.dire("Je n'arrive pas à ouvrir ce fichier.")
        self._histo()
        t.instantane([])
        t.calques.append({"nom": p.stem[:24], "img": img, "visible": True, "opacite": 1.0, "element": True})
        orig = self.__dict__.pop("_original_import", None)
        if orig is not None:
            self.__dict__.setdefault("avant_net", []).append((t.calques[-1], self._ajuster(orig), None))
            self._maj_retour()
        t.actif = len(t.calques) - 1
        t.modifie = True
        self._liste_calques()
        self.onglets.setCurrentIndex(1)
        t.update()
        self._mode_lasso = "garder"
        t.mode_lasso, t.mode_trajet, t.mode_pivot = True, False, False
        t.setCursor(Qt.CursorShape.CrossCursor)
        self.dire("Entoure le bout que tu veux garder. (Échap pour tout garder.) Ensuite, ✋ pour le placer.")
        if msg_net:
            QTimer.singleShot(6000, lambda m=msg_net: self.dire(m))

    def importer_calque(self):
        self.ajouter_bout()

    # ---------- yeux et bouche d'un perso du dessin
    def commencer_visage(self):
        c = self._element()
        if c is None:
            return self.dire("Entoure d'abord le perso (étape 1), puis donne-lui des yeux.")
        self.b_jouer.setChecked(False)
        self.toile.mode_visage = []
        self.toile.setCursor(Qt.CursorShape.CrossCursor)
        self.b_sans_bouche.setVisible(True)
        self.dire("Clique sur son œil gauche, puis sur son œil droit, puis sur sa bouche.")
        self.toile.update()

    def visage_point(self):
        n = len(self.toile.mode_visage)
        if n == 1:
            self.dire("Maintenant, l'autre œil !")
        elif n == 2:
            self.dire("Et la bouche ! (Ou « Pas de bouche ».)")
        else:
            self.finir_visage()

    def finir_visage(self):
        t = self.toile
        pts = t.mode_visage or []
        t.mode_visage = None
        t.unsetCursor()
        self.b_sans_bouche.setVisible(False)
        c = self._element()
        if c is None or not pts:
            t.update()
            return
        yeux = pts[:2] if len(pts) >= 2 else pts[:1]
        bouche = pts[2] if len(pts) >= 3 else None
        d = math.hypot(yeux[1][0] - yeux[0][0], yeux[1][1] - yeux[0][1]) if len(yeux) == 2 else 30
        r = max(6.0, min(60.0, d * 0.42))
        self._histo()
        t.instantane([c])
        c["visage"] = {"yeux": yeux, "bouche": bouche, "r": r, "peau": self._peau(yeux, r),
                       "cligne": True, "parle": bool(bouche)}
        self._liste_calques()
        self.b_jouer.setChecked(True)
        t.update()
        self.dire("Regarde, il cligne des yeux et il parle !" if bouche else "Regarde, il cligne des yeux !")

    def _peau(self, yeux, r):
        """La couleur autour des yeux (pour les paupières)."""
        img = self.toile.image_finale()
        vals = []
        for x, y in yeux:
            for k in range(16):
                a = k * math.pi / 8
                for rr in (r * 0.8, r * 1.0):
                    xx, yy = int(x + rr * math.cos(a)), int(y + rr * 0.7 * math.sin(a))
                    if 0 <= xx < TAILLE and 0 <= yy < TAILLE:
                        col = img.pixelColor(xx, yy)
                        if col.alpha() > 200:
                            vals.append(col)
        if not vals:
            return "#ffffff"
        vals.sort(key=lambda q: q.lightness())
        clairs = vals[len(vals) // 2:]
        q = clairs[len(clairs) // 2]
        return q.name()

    def _visage_opt(self, cle, oui):
        c = self._cal()
        if c.get("visage"):
            self._histo()
            c["visage"] = dict(c["visage"], **{cle: oui})
            self.toile.modifie = True
            self.toile.update()

    def _tete(self):
        c = self._element()
        if c is None:
            return self.dire("Entoure d'abord le perso (étape 1), puis sa tête.")
        self._lasso()
        self._mode_lasso = "tete"
        self.dire("Entoure sa tête (pas le cou), sans lâcher le bouton.")

    def _choisir_pivot(self):
        self.b_jouer.setChecked(False)
        self.toile.mode_pivot = True
        self.dire("Clique sur le dessin à l'endroit où ça doit tenir (une main, une charnière…).")

    def pivot_choisi(self, x, y):
        self._histo()
        an = self._cal().setdefault("anim", {"type": self.c_anim.currentData() or "pivoter", "vitesse": 2,
                                             "force": 40})
        an["pivot"], an["px"], an["py"] = "clic", x, y
        i = self.c_piv.findData("clic")
        self._maj_en_cours = True
        self.c_piv.setCurrentIndex(i)
        self._maj_en_cours = False
        self.b_jouer.setChecked(True)

    def _jouer(self, oui):
        self.toile.jouer(oui)
        self.b_jouer.setText(tr("⏸ Arrêter") if oui else tr("▶ Voir bouger"))

    def _tracer(self):
        self.b_jouer.setChecked(False)
        self.toile.mode_trajet = True
        self.toile.setCursor(Qt.CursorShape.CrossCursor)
        self.dire("Trace le chemin avec la souris, en partant de ce que tu veux faire bouger.")

    def trajet_fini(self, ok):
        if ok:
            self.b_jouer.setChecked(True)

    def _effacer_trajet(self):
        self._histo()
        self._cal().pop("trajet", None)
        self.toile.update()

    def _frames(self):
        c = self._cal()
        if not c.get("frames"):
            c["frames"] = [c["img"]]
            c["cur"] = 0
        return c

    def _image(self, sens):
        c = self._frames()
        if len(c["frames"]) < 2:
            return
        self.b_jouer.setChecked(False)
        c["cur"] = (c["cur"] + sens) % len(c["frames"])
        c["img"] = c["frames"][c["cur"]]
        c["_boite"] = None
        self.toile.annuler_pile.clear()
        self.toile.refaire_pile.clear()
        self._maj_anim()
        self.toile.update()

    def _nouvelle_image(self, copie):
        self._histo()
        c = self._frames()
        if len(c["frames"]) >= 48:
            return self.dire("48 images, c'est le maximum !")
        self.b_jouer.setChecked(False)
        img = c["img"].copy() if copie else _vide(TAILLE, TAILLE)
        c["frames"].insert(c["cur"] + 1, img)
        c["cur"] += 1
        c["img"] = img
        c["_boite"] = None
        self.toile.annuler_pile.clear()
        self.toile.modifie = True
        self._maj_anim()
        self.toile.update()

    def _suppr_image(self):
        self._histo()
        c = self._frames()
        if len(c["frames"]) < 2:
            return
        del c["frames"][c["cur"]]
        c["cur"] = max(0, c["cur"] - 1)
        c["img"] = c["frames"][c["cur"]]
        if len(c["frames"]) == 1:
            c.pop("frames")
            c.pop("cur", None)
        self.toile.annuler_pile.clear()
        self._maj_anim()
        self.toile.update()

    def images_animation(self, avec_fond=True, max_cote=640, seuls=None):
        """Les images de l'animation complète (une boucle), recadrées et réduites. -> (images, fps)"""
        t = self.toile
        fps = 12
        n = max(2, min(96, int(round(t.duree_boucle() * fps))))
        brut = [t.image_finale(avec_fond, i / fps, seuls) for i in range(n)]
        boites = [b for b in (self._boite(x) for x in brut) if b is not None]
        if not boites:
            return [], fps
        u = boites[0]
        for b in boites[1:]:
            u = u.united(b)
        u = u.adjusted(-16, -16, 16, 16).intersected(QRect(0, 0, TAILLE, TAILLE))
        out = [x.copy(u) for x in brut]
        self._cadre = (u, min(1.0, max_cote / max(u.width(), u.height())))
        if max(u.width(), u.height()) > max_cote:
            out = [x.scaled(max_cote, max_cote, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation) for x in out]
        return out, fps

    def exporter_anim(self):
        if not self.toile.animes():
            return self.dire("Rien ne bouge encore : choisis un mouvement, un trajet ou plusieurs images.")
        p, _ = QFileDialog.getSaveFileName(self, tr("Exporter en image animée"),
                                           str(dossier_dessins() / time.strftime("anim-%Y-%m-%d-%H%M.png")),
                                           tr("Image animée (*.png)"))
        if not p:
            return
        imgs, fps = self.images_animation(True, 720)
        if not imgs:
            return self.dire("Il n'y a rien de dessiné pour l'instant.")
        try:
            ecrire_apng(p, imgs, fps)
        except Exception as e:
            return QMessageBox.warning(self, tr("Carnet de dessin"), tr("L'enregistrement n'a pas marché :") + f"\n{e}")
        self.dire("C'est enregistré ! Tu peux l'ouvrir dans ton navigateur ou l'envoyer à tes amis.")

    def _perso_anime(self, seuls, contour, pts=None):
        import shutil
        import tempfile
        self.toile.sans_visage = bool(pts)                 # Viki anime elle-même les yeux et la bouche
        try:
            imgs, fps = self.images_animation(True, 640, seuls)
        finally:
            self.toile.sans_visage = False
        if not imgs:
            return self.dire("Il n'y a rien de dessiné pour l'instant.")
        if contour:
            imgs = [contour_blanc(x, 5).convertToFormat(QImage.Format.Format_ARGB32) for x in imgs]
        tmp = Path(tempfile.mkdtemp(prefix="viki-dessin-"))
        (tmp / "anim").mkdir()
        union = _vide(imgs[0].width(), imgs[0].height())
        pu = QPainter(union)
        for i, x in enumerate(imgs):
            x.convertToFormat(QImage.Format.Format_ARGB32).save(str(tmp / "anim" / f"f{i:03d}.png"))
            pu.drawImage(0, 0, x)
        pu.end()
        r = {"n": len(imgs), "fps": fps, "premiere": imgs[0].convertToFormat(QImage.Format.Format_ARGB32),
             "union": union, "fond": None, "visage": True}
        if pts:
            u, k = self._cadre
            r["points"] = [((x - u.x()) * k, (y - u.y()) * k) for x, y in pts]
        self.dire("Montre-moi où sont les yeux et la bouche. Si la tête bouge dans l'animation, choisis "
                  "« pas d'yeux ».")
        nom = self._nom_perso()
        try:
            self.comp._finish_animated(Path(nom + ".png"), tmp, r, None)
        except Exception as e:
            QMessageBox.warning(self, tr("Faire de mon dessin un perso"), str(e))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---------- Viki s'en mêle
    def devine(self):
        fin = self.toile.image_finale()
        if fin.isNull():
            return
        blanc = QImage(fin.size(), QImage.Format.Format_ARGB32)
        blanc.fill(QColor("#ffffff"))
        p = QPainter(blanc)
        p.drawImage(0, 0, fin)
        p.end()
        tmp = Path(getattr(self.comp, "tmpdir", Path("/tmp"))) / "dessin_devine.png"
        blanc.save(str(tmp))
        try:
            self.comp.look_image(tmp, "question",
                                 question="C'est un dessin fait à la main. Devine ce qu'il représente, puis dis un "
                                          "compliment sincère et gentil sur un détail réussi. Deux ou trois phrases.")
        except Exception:
            self.dire("Je n'ai pas réussi à regarder l'image.")

    @staticmethod
    def _plein(c):
        """Un calque « image avec un fond » (presque tout opaque) ?"""
        import numpy as np
        try:
            a = _tableau(c["img"].scaled(128, 128))[:, :, 3]
            return (a > 200).mean() > 0.45
        except Exception:
            return False

    def _detourer_calques(self, calques):
        faits = [c for c in calques if self._plein(c)]
        if not faits:
            return
        self._histo()
        for c in faits:
            try:
                neuf = detourer(c["img"])
            except Exception:
                continue
            c["img"], c["_boite"] = neuf, None
            if c.get("frames"):
                c["frames"] = list(c["frames"])
                c["frames"][c.get("cur", 0)] = neuf
        self.toile.update()

    def _nom_perso(self):
        st = self.fichier.stem if self.fichier else ""
        return (st if st and not st.startswith(("dessin-", "anim-")) else tr("Mon perso"))[:24]

    def _dialogue_perso(self, choix):
        """Une seule fenêtre : ce qu'on met dans le perso, le contour, et où il va. -> (calques, contour, à côté)"""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton
        t = self.toile
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Faire de mon dessin un perso"))
        v = QVBoxLayout(dlg)
        f = QFont()
        f.setPointSizeF(11)
        f.setBold(True)
        lab = QLabel(tr("Qu'est-ce qu'on met dans le perso ?"))
        lab.setFont(f)
        v.addWidget(lab)
        liste = QListWidget()
        for c in reversed(t.calques):
            if boite_calque(c["img"]) is None and not c.get("frames"):
                continue
            it = QListWidgetItem(("🎬 " if t.bouge(c) else "") + c["nom"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if any(c is x for x in choix) else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, t.calques.index(c))
            liste.addItem(it)
        liste.setMinimumHeight(160)
        v.addWidget(liste)
        contour = QCheckBox(tr("Petit contour blanc (il se voit sur tous les fonds d'écran)"))
        contour.setChecked(True)
        v.addWidget(contour)
        fond = QCheckBox(tr("🧽 Enlever le fond des images (papier, photo…)"))
        fond.setChecked(any(self._plein(c) for c in choix))
        v.addWidget(fond)
        lab = QLabel(tr("Où va ton nouveau perso ?"))
        lab.setFont(f)
        v.addWidget(lab)
        nom_viki = self.comp.char.get("name", "Viki")
        place = QRadioButton(tr("🔄 À la place de {} (un seul perso sur le bureau)").replace("{}", nom_viki))
        cote = QRadioButton(tr("👭 À côté de {} (deux persos sur le bureau)").replace("{}", nom_viki))
        (cote if self.comp.cfg.get("dessin_a_cote") else place).setChecked(True)   # le dernier choix
        v.addWidget(place)
        v.addWidget(cote)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        seuls = [t.calques[liste.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(liste.count())
                 if liste.item(i).checkState() == Qt.CheckState.Checked]
        self.comp.cfg["dessin_a_cote"] = cote.isChecked()
        if fond.isChecked():
            self._detourer_calques(seuls)
        return seuls, contour.isChecked(), cote.isChecked()

    def en_perso(self, seul=None):
        if not isinstance(seul, dict):                  # clic sur le bouton : Qt envoie aussi « coché ? » (False)
            seul = None
        t = self.toile
        t.jouer(False)
        self.b_jouer.setChecked(False)
        if seul is not None:
            choix = [seul] + t.enfants(seul)
        else:
            choix = [c for c in t.calques if c["visible"]]
            fond = boite_calque(t.calques[0]["img"])
            if len(t.calques) > 1 and fond is not None and fond.width() > TAILLE * 0.9 and fond.height() > TAILLE * 0.9:
                choix = choix[1:] if choix and choix[0] is t.calques[0] else choix   # un fond plein : un rectangle
        rep = self._dialogue_perso(choix)
        if not rep:
            return
        seuls, contour, a_cote = rep
        if not seuls:
            return self.dire("Coche au moins une chose à mettre dans le perso !")
        fin = t.image_finale(seuls=seuls)
        r = self._boite(fin)
        if r is None:
            return self.dire("Il n'y a rien de dessiné pour l'instant.")
        self.comp._nouveau_a_cote = a_cote
        pts = None
        for c in seuls:                                  # les yeux et la bouche déjà placés dans le carnet
            v = c.get("visage") or {}
            if len(v.get("yeux") or []) == 2:
                pts = [tuple(q) for q in v["yeux"]] + ([tuple(v["bouche"])] if v.get("bouche") else [])
                break
        if t.modifie:
            self.enregistrer()
        if any(t.bouge(c, visage=not pts) for c in seuls):
            return self._perso_anime(seuls, contour, pts)
        marge = 24
        r = r.adjusted(-marge, -marge, marge, marge).intersected(QRect(0, 0, TAILLE, TAILLE))
        img = fin.copy(r)
        if contour:
            img = contour_blanc(img, 6)
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        img.setText("viki_nom", self._nom_perso())
        if pts:
            import json
            img.setText("viki_pts", json.dumps([[x - r.x(), y - r.y()] for x, y in pts]))
            self.dire("Vérifie ses yeux et sa bouche, puis valide !")
        else:
            self.dire("Super ! Montre-moi où sont les yeux et la bouche.")
        try:
            self.comp._finish_new_character(img)
        except Exception as e:
            QMessageBox.warning(self, tr("Faire de mon dessin un perso"), str(e))

    @staticmethod
    def _boite(img):
        """Le rectangle qui contient tout ce qui est dessiné (None si la feuille est vide)."""
        import numpy as np
        src = img.convertToFormat(QImage.Format.Format_ARGB32)
        w, h = src.width(), src.height()
        a = np.frombuffer(src.constBits().asstring(src.sizeInBytes()), dtype=np.uint8).reshape(h, src.bytesPerLine())
        al = a[:, 3:w * 4:4] > 12
        ys, xs = np.nonzero(al)
        if not len(xs):
            return None
        return QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))

    def closeEvent(self, e):
        if not self._confirmer_perte():
            e.ignore()
            return
        super().closeEvent(e)


def contour_blanc(img, r=6):
    """Ajoute un contour blanc autour de ce qui est dessiné (comme un autocollant)."""
    src = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    blanc = src.copy()
    p = QPainter(blanc)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(blanc.rect(), QColor("#ffffff"))
    p.end()
    out = _vide(src.width(), src.height())
    p = QPainter(out)
    import math
    for k in range(16):
        a = k * math.pi / 8
        p.drawImage(QPointF(r * math.cos(a), r * math.sin(a)), blanc)
    p.drawImage(0, 0, src)
    p.end()
    return out


CSS = """
QWidget#carnet { background: #fffafc; color: #2e1624; }
QWidget#carnet QLabel, QWidget#carnet QCheckBox { color: #2e1624; }
QFrame#panneau { background: white; border: 1px solid #f1dfe8; border-radius: 14px; padding: 6px; }
QPushButton { background: white; border: 1px solid #ecd3df; border-radius: 10px; padding: 7px 11px; color: #2e1624; }
QPushButton:hover { background: #fdf0f5; }
QPushButton:checked { background: #fdf0f5; border: 2px solid #b0336a; font-weight: 700; color: #8a2453; }
QPushButton#main { background: #b0336a; color: white; border: none; font-weight: 700; }
QPushButton#main:hover { background: #9a2b5c; }
QToolButton { background: white; border: 1px solid transparent; border-radius: 12px; }
QToolButton:hover { background: #fdf0f5; }
QToolButton:checked { background: #fdf0f5; border: 1px solid #f0bfd4; }
QComboBox { min-height: 26px; padding: 2px 8px; border: 1px solid #ecd3df; border-radius: 8px; background: white; color: #2e1624; }
QListWidget { background: white; border: 1px solid #f1dfe8; border-radius: 10px; color: #2e1624; }
QListWidget::item:selected { background: #fdf0f5; color: #8a2453; }
"""
