"""👉 Le guide à l'écran : Viki regarde ton écran, entoure, souligne ou montre avec une flèche, et t'explique.

Elle ne clique jamais à ta place : elle montre, c'est toi qui fais.

Comment elle trouve les choses :
  1. Tesseract (s'il est installé) lit les textes de l'écran avec leur position exacte : chaque ligne reçoit un numéro.
  2. L'IA (qui voit l'image, sinon seulement la liste des textes) répond en JSON : ce qu'il faut expliquer, et quelles
     lignes (ou quelles zones de l'image) entourer, souligner ou montrer.
  3. Un calque transparent, que la souris traverse, dessine les marques par-dessus tout, comme au feutre.
"""
import json
import math
import os
import re
import shutil
import subprocess
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

COTE = 1000                 # l'image envoyée à l'IA : un carré de 1000 px (coordonnées sans ambiguïté)
FORMES = ("cercle", "souligne", "fleche", "cadre")
LANGUES = {"fr": "français", "en": "English", "es": "español", "ru": "русский", "zh": "中文", "ja": "日本語",
           "hi": "हिन्दी"}
TESS = {"fr": "fra", "en": "eng", "es": "spa", "ru": "rus", "zh": "chi_sim", "ja": "jpn", "hi": "hin"}


# ================================================================== lire l'écran
def tesseract_ok():
    return bool(shutil.which("tesseract"))


def _langues_tess(lang):
    try:
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
        dispo = set(r.stdout.split())
    except Exception:
        dispo = set()
    voulu = [TESS.get(lang, "eng"), "eng"]
    out = [x for x in dict.fromkeys(voulu) if x in dispo]
    return "+".join(out) or "eng"


def _tsv(png, langs):
    try:
        r = subprocess.run(["tesseract", str(png), "-", "-l", langs, "--psm", "11", "tsv"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout
    except Exception:
        return ""


def _filtre(a, k, fn):
    """Filtre min / max k×k (séparable) avec numpy."""
    import numpy as np
    r = k // 2
    for ax in (0, 1):
        p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in range(2)], mode="edge")
        n = a.shape[ax]
        a = fn([np.take(p, range(i, i + n), axis=ax) for i in range(k)], axis=0)
    return a


def _texte_clair(img, dest):
    """Image où le texte CLAIR sur fond plus foncé devient noir sur blanc (les cadres épais sont retirés)."""
    try:
        import numpy as np
    except Exception:
        return False
    g = img.convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = g.width(), g.height()
    bpl = g.bytesPerLine()
    a = np.frombuffer(g.constBits().asstring(bpl * h), np.uint8).reshape(h, bpl)[:, :w].astype(np.int32)
    r = 15                                                 # moyenne locale (boîte 31×31) par sommes cumulées
    c = np.pad(a, r + 1, mode="edge").cumsum(0).cumsum(1)
    s = c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]
    moy = s[:h, :w] / float((2 * r + 1) ** 2)
    noir = (a - moy) > 18                                  # True = trait de texte clair
    epais = _filtre(_filtre(noir.astype(np.uint8), 7, np.min), 9, np.max).astype(bool)
    out = np.where(noir & ~epais, 0, 255).astype(np.uint8)
    out = np.ascontiguousarray(out)
    q = QImage(out.data, w, h, w, QImage.Format.Format_Grayscale8)
    return q.save(dest)


def lignes_ocr(png, lang="fr", maxi=90):
    """Les lignes de texte de l'écran : [{"id", "texte", "box": (x, y, w, h)}] en pixels de la capture.
    On lit l'image normale puis inversée (le texte clair sur bouton foncé)."""
    if not tesseract_ok():
        return []
    langs = _langues_tess(lang)
    out = _lignes(_tsv(png, langs))
    try:
        p2 = str(png) + ".clair.png"
        if _texte_clair(QImage(str(png)), p2):          # 2e lecture : le texte clair sur fond foncé (boutons…)
            for d in _lignes(_tsv(p2, langs), 80):
                x, y, w, h = d["box"]
                if not any(abs(x - e["box"][0]) < 14 and abs(y - e["box"][1]) < 10 for e in out):
                    out.append(d)
            os.unlink(p2)
    except Exception:
        pass
    out.sort(key=lambda d: (d["box"][1] // 12, d["box"][0]))
    out = out[:maxi]
    for i, d in enumerate(out, 1):
        d["id"] = i
    return out


def _lignes(tsv, conf_min=45):
    mots = []
    for ligne in tsv.splitlines()[1:]:
        c = ligne.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            conf = float(c[10])
            x, y, w, h = (int(c[6]), int(c[7]), int(c[8]), int(c[9]))
        except ValueError:
            continue
        if conf < conf_min or h < 6:
            continue
        mots.append({"cle": (c[2], c[3], c[4]), "t": c[11].strip(), "box": (x, y, w, h)})
    groupes = {}
    for m in mots:                                   # on regroupe les mots d'une même ligne (et proches)
        g = groupes.setdefault(m["cle"], [])
        if g and m["box"][0] - (g[-1]["box"][0] + g[-1]["box"][2]) > max(30, 2.5 * m["box"][3]):
            k = m["cle"] + (len([1 for kk in groupes if kk[:3] == m["cle"]]),)
            groupes.setdefault(k, []).append(m)
            continue
        g.append(m)
    out = []
    for g in groupes.values():
        if not g:
            continue
        txt = " ".join(m["t"] for m in g)
        if len(re.sub(r"\W", "", txt)) < 2 or (conf_min > 45 and len(re.findall(r"[^\W\d_]", txt)) < 3):
            continue
        x0 = min(m["box"][0] for m in g)
        y0 = min(m["box"][1] for m in g)
        x1 = max(m["box"][0] + m["box"][2] for m in g)
        y1 = max(m["box"][1] + m["box"][3] for m in g)
        out.append({"texte": txt[:80], "box": (x0, y0, x1 - x0, y1 - y0)})
    return out


def image_carree(img):
    """La capture dans un carré de COTE px (en haut à gauche, fond noir) -> (QImage, échelle capture->carré)."""
    k = COTE / max(img.width(), img.height())
    sc = img.scaled(max(1, int(img.width() * k)), max(1, int(img.height() * k)),
                    Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(COTE, COTE, QImage.Format.Format_RGB32)
    out.fill(QColor(0, 0, 0))
    p = QPainter(out)
    p.drawImage(0, 0, sc)
    p.end()
    return out, k


# ================================================================== demander à l'IA
def consigne(question, lignes, lang="fr", voit=True, historique=(), modele=(), point=None):
    langue = LANGUES.get(lang, "français")
    liste = "\n".join(f"{d['id']}: {d['texte']}" for d in lignes) or "(aucun texte lu)"
    deja = ""
    if historique:
        deja = "\nÉtapes déjà montrées (l'utilisateur les a faites) :\n" + "\n".join(f"- {h}" for h in historique)
    if modele:
        deja += ("\nTutoriel enregistré la dernière fois pour cette demande (suis ces étapes, adapte-toi à l'écran) :\n"
                 + "\n".join(f"{i + 1}. {e}" for i, e in enumerate(modele)))
    if point:
        px, py = point
        proche = min(lignes, key=lambda d: (d["_cx"] - px) ** 2 + (d["_cy"] - py) ** 2, default=None) \
            if lignes and "_cx" in lignes[0] else None
        deja += (f"\nL'utilisateur montre avec sa souris le point ({int(px)}, {int(py)}) du carré 1000×1000"
                 + (f" ; le texte le plus proche est le n°{proche['id']} « {proche['texte']} »" if proche else "")
                 + ". Explique CE QUI EST À CET ENDROIT et entoure-le.")
    vue = ("Tu vois la capture d'écran (carré de 1000×1000, l'écran est en haut à gauche, le noir n'est pas l'écran)."
           if voit else "Tu ne vois pas l'image : tu n'as que la liste des textes lus sur l'écran.")
    return (
        "Tu es Viki, une compagne de bureau qui aide l'utilisateur sur son ordinateur. " + vue + "\n"
        "Voici les textes lus sur l'écran, avec un numéro :\n" + liste + "\n" + deja + "\n"
        f"La demande de l'utilisateur : « {question} »\n\n"
        "Montre-lui sur l'écran : choisis 1 à 4 éléments à marquer. Pour chaque élément, donne de préférence "
        "le numéro du texte (\"id\") ; seulement si l'élément n'a pas de texte (une icône…), donne \"box\": "
        "[x1, y1, x2, y2] en pixels du carré 1000×1000. Formes : \"cercle\" (là où cliquer), \"souligne\" "
        "(un texte important), \"fleche\" (montrer un endroit), \"cadre\" (une zone entière).\n"
        "S'il faut plusieurs étapes, ne montre QUE la prochaine étape ; l'utilisateur dira « suivant » ensuite.\n"
        "Tu ne cliques jamais toi-même. Ne lis jamais de mot de passe ou d'information privée.\n"
        f"Réponds UNIQUEMENT en JSON, textes en {langue} :\n"
        '{"explication": "2 à 4 phrases simples", "marques": [{"id": 12, "forme": "cercle", "note": "3 à 6 mots"}], '
        '"fini": false}\n'
        "« fini » vaut true quand il n'y a plus d'étape après celle-ci.")


def lire_reponse(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"explication": txt[:600], "marques": [], "fini": True}
    try:
        d = json.loads(m.group(0))
    except Exception:
        try:
            d = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
        except Exception:
            return {"explication": re.sub(r"[{}\"]", "", txt)[:600], "marques": [], "fini": True}
    if not isinstance(d, dict):
        return {"explication": "", "marques": [], "fini": True}
    marques = d.get("marques") or []
    return {"explication": str(d.get("explication") or "").strip(),
            "marques": [x for x in marques if isinstance(x, dict)][:6], "fini": bool(d.get("fini", True))}


def placer_marques(rep, lignes, k):
    """Les marques de l'IA -> [{"forme", "note", "rect": (x, y, w, h) en pixels de la capture}]."""
    par_id = {d["id"]: d for d in lignes}
    out = []
    for m in rep.get("marques", []):
        forme = str(m.get("forme") or "cercle").lower()
        forme = forme if forme in FORMES else "cercle"
        rect = None
        try:
            i = int(m.get("id")) if m.get("id") not in (None, "") else None
        except (TypeError, ValueError):
            i = None
        if i is not None and i in par_id:
            rect = par_id[i]["box"]
        elif isinstance(m.get("box"), (list, tuple)) and len(m["box"]) == 4:
            try:
                x1, y1, x2, y2 = (float(v) / k for v in m["box"])
                if x2 > x1 and y2 > y1:
                    rect = (x1, y1, x2 - x1, y2 - y1)
            except (TypeError, ValueError, ZeroDivisionError):
                rect = None
        if rect is None:
            continue
        out.append({"forme": forme, "note": str(m.get("note") or "")[:60], "rect": rect})
    return out


# ================================================================== le calque (dessiné par-dessus tout)
ROSE = QColor(255, 64, 129)


class Calque(QWidget):
    """Plein écran, transparent, la souris passe au travers : seulement les marques au feutre."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.marques, self.t0, self.fin = [], 0.0, 0.0
        self.minuteur = QTimer(self)
        self.minuteur.timeout.connect(self._tic)

    def montrer(self, marques, taille_capture, duree=45.0):
        """marques en pixels de la capture ; taille_capture : (largeur, hauteur) de la capture."""
        ecran = QGuiApplication.primaryScreen()
        virt, prim = ecran.virtualGeometry(), ecran.geometry()
        sx = virt.width() / max(1, taille_capture[0])
        sy = virt.height() / max(1, taille_capture[1])
        ox, oy = virt.x() - prim.x(), virt.y() - prim.y()
        if abs(sx - sy) > 0.05:                       # capture d'un seul écran : l'écran principal
            sx = prim.width() / max(1, taille_capture[0])
            sy = prim.height() / max(1, taille_capture[1])
            ox = oy = 0
        self.marques = [dict(m, r=QRectF(m["rect"][0] * sx + ox, m["rect"][1] * sy + oy, m["rect"][2] * sx,
                                         m["rect"][3] * sy), n=i + 1) for i, m in enumerate(marques)]
        self.setGeometry(prim)
        if os.environ.get("WAYLAND_DISPLAY"):           # Wayland : on ne place pas une fenêtre, on la met plein écran
            self.showFullScreen()
        self.t0 = time.monotonic()
        self.fin = self.t0 + duree
        self.show()
        self.raise_()
        self.minuteur.start(33)
        self.update()

    def effacer(self):
        self.minuteur.stop()
        self.marques = []
        self.hide()

    def actif(self):
        return self.isVisible() and bool(self.marques)

    def _tic(self):
        now = time.monotonic()
        if now > self.fin:
            return self.effacer()
        if now - self.t0 > 0.7 * len(self.marques) + 1.5 and now < self.fin - 1.0:
            self.minuteur.setInterval(200)            # tout est dessiné : on ralentit (juste la pulsation)
        else:
            self.minuteur.setInterval(33)
        self.update()

    # --- dessin au feutre
    @staticmethod
    def _cercle(r, k):
        c = r.center()
        rx, ry = r.width() / 2 + 16, r.height() / 2 + 14
        path = QPainterPath()
        n = 64
        tours = 1.12 * k
        for i in range(n + 1):
            a = -2.2 + 2 * math.pi * tours * i / n
            w = 1 + 0.06 * math.sin(i * 0.7) + 0.05 * i / n          # un peu tremblé, comme à la main
            pt = QPointF(c.x() + rx * w * math.cos(a), c.y() + ry * w * math.sin(a))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        return path

    @staticmethod
    def _vague(r, k):
        path = QPainterPath()
        x0, x1, y = r.left() - 4, r.left() - 4 + (r.width() + 8) * k, r.bottom() + 6
        path.moveTo(x0, y)
        x = x0
        while x < x1:
            x = min(x1, x + 3)
            path.lineTo(x, y + 2.5 * math.sin((x - x0) / 7))
        return path

    def paintEvent(self, ev):
        if not self.marques:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        fondu = min(1.0, max(0.0, (self.fin - now) / 1.0))
        p.setOpacity(fondu)
        for m in self.marques:
            k = min(1.0, max(0.0, (now - self.t0 - 0.7 * (m["n"] - 1)) / 0.6))
            if k <= 0:
                continue
            r = m["r"]
            puls = 0.5 + 0.5 * math.sin(now * 3.2 + m["n"])
            for largeur, alpha in ((12, 50 + int(30 * puls)), (4.5, 240)):     # halo puis trait
                col = QColor(ROSE)
                col.setAlpha(alpha)
                pen = QPen(col, largeur, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                f = m["forme"]
                if f == "cercle":
                    p.drawPath(self._cercle(r, k))
                elif f == "souligne":
                    p.drawPath(self._vague(r, k))
                elif f == "cadre":
                    rr = r.adjusted(-10, -8, 10, 8)
                    path = QPainterPath()
                    path.addRoundedRect(rr, 12, 12)
                    p.setOpacity(fondu * k)
                    p.drawPath(path)
                    p.setOpacity(fondu)
                else:                                                         # flèche
                    bout = QPointF(r.left() - 6, r.center().y())
                    dep = QPointF(bout.x() - 150, bout.y() - 110)
                    if dep.x() < 20:
                        bout = QPointF(r.right() + 6, r.center().y())
                        dep = QPointF(bout.x() + 150, bout.y() - 110)
                    if dep.y() < 20:                                          # trop haut : la flèche vient d'en bas
                        dep = QPointF(dep.x(), bout.y() + 110)
                    q = dep + (bout - dep) * k
                    path = QPainterPath(dep)
                    ctrl = QPointF((dep.x() + q.x()) / 2, min(dep.y(), q.y()) - 30)
                    path.quadTo(ctrl, q)
                    p.drawPath(path)
                    if k >= 1:
                        a = math.atan2(bout.y() - ctrl.y(), bout.x() - ctrl.x())
                        for da in (2.6, -2.6):
                            p.drawLine(bout, QPointF(bout.x() + 22 * math.cos(a + da), bout.y() + 22 * math.sin(a + da)))
            if k >= 1 and m["note"]:                                          # l'étiquette numérotée
                self._etiquette(p, m, fondu)
        p.end()

    def _etiquette(self, p, m, fondu):
        r = m["r"]
        f = QFont()
        f.setPixelSize(15)
        f.setBold(True)
        fm = QFontMetrics(f)
        txt = m["note"]
        w = fm.horizontalAdvance(txt) + 46
        h = 30
        x = min(max(8, r.center().x() - w / 2), self.width() - w - 8)
        y = r.bottom() + 22 if r.bottom() + 22 + h < self.height() - 8 else r.top() - 22 - h
        box = QRectF(x, y, w, h)
        path = QPainterPath()
        path.addRoundedRect(box, 15, 15)
        p.setOpacity(fondu * 0.96)
        p.fillPath(path, QColor(30, 22, 34))
        p.setPen(QPen(ROSE, 2))
        p.drawPath(path)
        p.setBrush(ROSE)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(box.left() + 16, box.center().y()), 10, 10)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(box.left() + 6, box.top(), 20, h), Qt.AlignmentFlag.AlignCenter, str(m["n"]))
        p.drawText(box.adjusted(32, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, txt)
        p.setOpacity(fondu)


# ================================================================== commandes
_UI = r"(?:bouton|option|menu|icone|reglage|parametre|onglet|case|lien|champ|fenetre|barre|touche|curseur|interrupteur)"
RX_GUIDE = re.compile(
    r"^(?:viki,? )?(?:(?:tu peux|peux[- ]tu|stp|s.il te pla[iî]t|est-ce que tu peux) ?,? )*(?:"
    r"(?:montre|indique|guide)[- ]moi (?:ou|comment|sur (?:mon |l.)?ecran|dans cette fenetre|ici)|guide[- ]moi\b|"
    r"entoure|souligne|aide[- ]moi a trouver (?:le |la |l.)" + _UI + r"|"
    r"ou (?:est|sont|se trouve|se trouvent) (?:le |la |les |l.)" + _UI + r"|"
    r"ou (?:je clique|dois[- ]je cliquer|il faut cliquer|cliquer)|"
    r"explique[- ]moi (?:cette fenetre|ce que je vois|mon ecran|l.ecran|ce qu.il y a (?:a|sur) l.ecran|cette page|"
    r"ce menu|ces options|ces boutons)|"
    r"comment (?:je fais|faire|on fait) (?:pour .{3,} )?(?:ici|sur (?:mon |l.)?ecran|dans cette fenetre|avec ca)|"
    r"show me (?:where|how|on (?:my |the )?screen)|where (?:is|are) the " + _UI.replace("bouton", "button") + r"|"
    r"where (?:do i|should i|to) click|circle|highlight|underline|guide me|"
    r"explain (?:this window|my screen|what i see|this page|this menu))\b(.*)$", re.I)
RX_SUITE = re.compile(r"^(?:ok,? |bon,? |voila,? )?(?:suivant|etape suivante|c.est fait|fait|et (?:apres|maintenant)|"
                      r"ensuite|la suite|next|done)\s*[!.?]*$", re.I)
RX_EFFACE = re.compile(r"^(?:efface|enleve|retire|cache|vire)[- ]?(?:moi )?(?:les |tes )?(?:marques|cercles|traits|"
                       r"dessins|fleches|tout)\b|^(?:c.est bon|ok) merci\b|^stop(?:pe)? le guide\b", re.I)
