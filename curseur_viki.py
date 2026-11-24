"""🖱️ Le mode curseur : le pointeur de la souris devient celui de Viki (rose, avec un petit cœur), et il sert
aussi à appeler ses fonctions : Meta+Alt+Espace ouvre une roue autour du pointeur (« C'est quoi ça ? », copier ou
traduire le texte à cet endroit, la couleur sous le pointeur, « Montre-moi… »).

Le thème de curseur est un dossier « Viki » dans ~/.local/share/icons (fichiers Xcursor dessinés ici même),
appliqué par les réglages du bureau après ton accord ; « Remettre mon curseur » remet l'ancien.
"""
import json
import sys
import math
import os
import shutil
import struct
import subprocess
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

NOM = "Viki"
DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
ICONES = DATA / "icons"
DOSSIER = ICONES / NOM
ETAT = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "viki" / "curseur_avant.json"
TAILLES = (24, 32, 48, 64)
ROSE = QColor(255, 79, 139)
AVATAR = {"img": None}                                  # le visage de Viki (QImage carré), posé à côté du pointeur
ROSE_F = QColor(192, 40, 98)

# nom du fichier -> (dessin, alias)
FORMES = {
    "default": ("fleche", ["left_ptr", "arrow", "top_left_arrow", "left_arrow", "context-menu", "copy", "alias"]),
    "pointer": ("main", ["hand2", "hand1", "pointing_hand", "hand", "e29285e634086352946a0e7090d73106",
                         "9d800788f1b08800ae810202380a0822"]),
    "text": ("texte", ["xterm", "ibeam", "vertical-text"]),
    "wait": ("attente", ["watch"]),
    "progress": ("fleche_attente", ["left_ptr_watch", "half-busy", "3ecb610c1bf2410f44200f48c40d3599",
                                    "08e8e1c95fe2fc01f976f1e063a24ccd"]),
    "help": ("aide", ["question_arrow", "whats_this", "d9ce0ab605698f320427677b458ad60b",
                      "5c6cd98b3f3ebcb1f9c7f1c204630408"]),
    "crosshair": ("viseur", ["cross", "tcross", "cell"]),
}


# ------------------------------------------------------------------ dessiner les pointeurs
def _fleche(p, s, avatar=True, petite=False):
    k = s * (0.62 if petite or (avatar and AVATAR["img"] is not None) else 0.95) / 20
    pts = [(0, 0), (0, 16.5), (4.2, 12.6), (7.2, 19.2), (10, 18), (7.1, 11.6), (12.6, 11.6)]
    poly = QPolygonF([QPointF(1.2 + x * k, 1.2 + y * k) for x, y in pts])
    p.setPen(QPen(QColor("white"), max(1.2, s / 20), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(ROSE)
    p.drawPolygon(poly)
    if avatar:
        _avatar(p, s)


def _avatar(p, s):
    """Le petit visage de Viki, en rond, en bas à droite du pointeur."""
    img = AVATAR["img"]
    if img is None:
        return
    r = s * 0.25
    c = QPointF(s - r - max(1.0, s / 24), s - r - max(1.0, s / 24))
    path = QPainterPath()
    path.addEllipse(c, r, r)
    p.save()
    p.setClipPath(path)
    p.drawImage(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), img)
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("white"), max(1.0, s / 26)))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(ROSE, max(0.8, s / 40)))
    p.drawEllipse(c, r + max(1.0, s / 26) * 0.7, r + max(1.0, s / 26) * 0.7)


def _coeur(p, c, r):
    path = QPainterPath()
    path.moveTo(c.x(), c.y() + r * 0.9)
    path.cubicTo(c.x() - r * 1.6, c.y() - r * 0.2, c.x() - r * 0.6, c.y() - r * 1.3, c.x(), c.y() - r * 0.45)
    path.cubicTo(c.x() + r * 0.6, c.y() - r * 1.3, c.x() + r * 1.6, c.y() - r * 0.2, c.x(), c.y() + r * 0.9)
    p.setPen(QPen(QColor("white"), max(1.0, r / 4)))
    p.setBrush(ROSE_F)
    p.drawPath(path)


def _main(p, s):
    """Le pointeur des liens : la flèche un peu penchée, et Viki à côté."""
    p.save()
    p.translate(s * 0.10, s * 0.02)
    p.rotate(-14)
    _fleche(p, s, avatar=False, petite=AVATAR["img"] is not None)
    p.restore()
    _avatar(p, s)


def _texte(p, s):
    k = s / 32
    p.setPen(QPen(QColor("white"), max(3.0, 4 * k), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for pen in (QPen(QColor("white"), 5 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap),
                QPen(ROSE, 2.4 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)):
        p.setPen(pen)
        p.drawLine(QPointF(16 * k, 5 * k), QPointF(16 * k, 27 * k))
        p.drawLine(QPointF(11 * k, 5 * k), QPointF(21 * k, 5 * k))
        p.drawLine(QPointF(11 * k, 27 * k), QPointF(21 * k, 27 * k))


def _attente(p, s, angle=0):
    k = s / 32
    c = QPointF(16 * k, 16 * k)
    p.setPen(QPen(QColor(255, 255, 255, 220), 5 * k))
    p.drawEllipse(c, 10 * k, 10 * k)
    p.setPen(QPen(ROSE, 3.2 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(6 * k, 6 * k, 20 * k, 20 * k), int(-angle * 16), 110 * 16)


def _fleche_attente(p, s, angle=0):
    _fleche(p, s)
    k = s / 32
    p.setPen(QPen(ROSE_F, 2.6 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(17 * k, 1 * k, 12 * k, 12 * k), int(-angle * 16), 120 * 16)


def _aide(p, s):
    _fleche(p, s)
    k = s / 32
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(12 * k))
    p.setFont(f)
    p.setPen(ROSE_F)
    p.drawText(QRectF(17 * k, 0, 14 * k, 14 * k), Qt.AlignmentFlag.AlignCenter, "?")


def _viseur(p, s):
    k = s / 32
    for pen in (QPen(QColor("white"), 4 * k), QPen(ROSE, 2 * k)):
        p.setPen(pen)
        p.drawLine(QPointF(16 * k, 3 * k), QPointF(16 * k, 12 * k))
        p.drawLine(QPointF(16 * k, 20 * k), QPointF(16 * k, 29 * k))
        p.drawLine(QPointF(3 * k, 16 * k), QPointF(12 * k, 16 * k))
        p.drawLine(QPointF(20 * k, 16 * k), QPointF(29 * k, 16 * k))


DESSINS = {"fleche": _fleche, "main": _main, "texte": _texte, "attente": _attente, "fleche_attente": _fleche_attente,
           "aide": _aide, "viseur": _viseur}
POINTS = {"fleche": (0.07, 0.07), "main": (0.34, 0.08), "texte": (0.5, 0.5), "attente": (0.5, 0.5),
          "fleche_attente": (0.07, 0.07), "aide": (0.07, 0.07), "viseur": (0.5, 0.5)}


def image(dessin, s, angle=0):
    img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fn = DESSINS[dessin]
    fn(p, s, angle) if dessin in ("attente", "fleche_attente") else fn(p, s)
    p.end()
    return img


# ------------------------------------------------------------------ le format Xcursor
def xcursor(images):
    """images : [(taille, QImage, xhot, yhot, délai ms)] -> octets d'un fichier Xcursor."""
    n = len(images)
    entete = struct.pack("<4sIII", b"Xcur", 16, 0x10000, n)
    pos = 16 + n * 12
    toc, blocs = b"", b""
    for taille, img, xh, yh, delai in images:
        img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        w, h = img.width(), img.height()
        pixels = bytes(img.constBits().asstring(w * h * 4)) if img.bytesPerLine() == w * 4 else b"".join(
            bytes(img.constScanLine(y).asstring(w * 4)) for y in range(h))
        bloc = struct.pack("<IIIIIIIII", 36, 0xfffd0002, taille, 1, w, h, xh, yh, delai) + pixels
        toc += struct.pack("<III", 0xfffd0002, taille, pos)
        pos += len(bloc)
        blocs += bloc
    return entete + toc + blocs


def dossiers_themes():
    """Où le bureau cherche les curseurs : XCURSOR_PATH s'il existe, sinon ~/.icons et ~/.local/share/icons.
    On installe dans tous les dossiers personnels de la liste (le plus sûr pour être trouvé)."""
    home = Path.home()
    out = []
    for d in (os.environ.get("XCURSOR_PATH") or "").split(":"):
        d = d.strip()
        if not d:
            continue
        d = Path(os.path.expanduser(os.path.expandvars(d)))
        if str(d).startswith(str(home)):
            out.append(d)
    for d in (home / ".icons", ICONES):
        if d not in out:
            out.append(d)
    return out


def creer_theme(nom=NOM):
    """Crée le thème dans ~/.local/share/icons, puis le copie dans les autres dossiers où le bureau cherche."""
    d0 = _creer_theme(nom, ICONES / nom)
    for base in dossiers_themes():
        if base == ICONES:
            continue
        try:
            base.mkdir(parents=True, exist_ok=True)
            dest = base / nom
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(d0, dest, symlinks=True)
        except OSError:
            pass
    return d0


def _creer_theme(nom, dossier):
    cur = dossier / "cursors"
    cur.mkdir(parents=True, exist_ok=True)
    for nom, (dessin, alias) in FORMES.items():
        ims = []
        anime = dessin in ("attente", "fleche_attente")
        for s in TAILLES:
            hx, hy = POINTS[dessin]
            angles = range(0, 360, 30) if anime else (0,)
            for a in angles:
                ims.append((s, image(dessin, s, a), int(hx * s), int(hy * s), 60 if anime else 0))
        (cur / nom).write_bytes(xcursor(ims))
        for a in alias:
            lien = cur / a
            try:
                if lien.exists() or lien.is_symlink():
                    lien.unlink()
                lien.symlink_to(nom)
            except OSError:
                shutil.copy(cur / nom, lien)
    (dossier / "index.theme").write_text(
        f"[Icon Theme]\nName={nom}\nComment=Le curseur de Viki\nInherits=breeze_cursors,Adwaita,default\n",
        encoding="utf-8")
    return dossier


# ------------------------------------------------------------------ l'appliquer / remettre l'ancien
def env_systeme():
    """L'environnement d'origine pour les outils du système (sans les bibliothèques de l'AppImage)."""
    env = dict(os.environ)
    if "COMPAGNON_ORIG_LD" in env:
        if env["COMPAGNON_ORIG_LD"]:
            env["LD_LIBRARY_PATH"] = env["COMPAGNON_ORIG_LD"]
        else:
            env.pop("LD_LIBRARY_PATH", None)
    for k in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "PYTHONHOME", "PYTHONPATH"):
        if env.get("APPDIR") and env.get(k, "").startswith(env["APPDIR"]):
            env.pop(k, None)
    return env


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env_systeme())
        return r.returncode == 0, r.stdout.strip()
    except Exception:
        return False, ""


def bureau():
    d = (os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" + os.environ.get("DESKTOP_SESSION", "")).upper()
    for k, nom in (("KDE", "kde"), ("XFCE", "xfce"), ("CINNAMON", "gnome"), ("GNOME", "gnome"), ("BUDGIE", "gnome"),
                   ("MATE", "mate"), ("UNITY", "gnome"), ("POP", "gnome")):
        if k in d:
            return nom
    return ""


def actuel():
    b = bureau()
    if b == "kde":
        ok, v = _run(["kreadconfig6", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme"]) \
            if shutil.which("kreadconfig6") else _run(["kreadconfig5", "--file", "kcminputrc", "--group", "Mouse",
                                                       "--key", "cursorTheme"])
        return v or "breeze_cursors"
    if b in ("gnome", "mate"):
        sch = "org.mate.peripherals-mouse" if b == "mate" else "org.gnome.desktop.interface"
        key = "theme-name" if b == "mate" else "cursor-theme"
        ok, v = _run(["gsettings", "get", sch, key])
        return v.strip("'") if ok else ""
    if b == "xfce":
        ok, v = _run(["xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeName"])
        return v if ok else ""
    return ""


_dernier_message = {}


def appliquer(nom):
    b = bureau()
    if b == "kde":
        ok = False
        if shutil.which("plasma-apply-cursortheme"):
            try:
                r = subprocess.run(["plasma-apply-cursortheme", nom], capture_output=True, text=True, timeout=20,
                                   env=env_systeme())
                _dernier_message["txt"] = ("plasma-apply-cursortheme : " + (r.stderr or r.stdout).strip())[:300] + \
                    f" — XCURSOR_PATH={os.environ.get('XCURSOR_PATH', '(vide)')} — installé dans " + \
                    ", ".join(str(b) for b in dossiers_themes())
                ok = r.returncode == 0 and "could not" not in (r.stderr + r.stdout).lower()
            except Exception as e:
                _dernier_message["txt"] = str(e)[:200]
        kw = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
        if kw and ok:                                       # écrit + prévient KWin (rechargement en direct)
            _run([kw, "--notify", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme", nom])
        if shutil.which("dbus-send"):
            _run(["dbus-send", "--session", "--type=signal", "/KGlobalSettings", "org.kde.KGlobalSettings.notifyChange",
                  "int32:5", "int32:0"])
        return ok and actuel() == nom
    if b == "gnome":
        return _run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", nom])[0]
    if b == "mate":
        return _run(["gsettings", "set", "org.mate.peripherals-mouse", "theme-name", nom])[0]
    if b == "xfce":
        return _run(["xfconf-query", "-c", "xsettings", "-p", "/Gtk/CursorThemeName", "-s", nom])[0]
    d = Path.home() / ".icons" / "default"                 # autres bureaux : le thème par défaut de X
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.theme").write_text(f"[Icon Theme]\nInherits={nom}\n", encoding="utf-8")
    return True


def activer(avatar=None):
    """Crée le thème (avec le visage de Viki) et l'applique. -> (ok, détail)"""
    import hashlib
    import time as _t
    AVATAR["img"] = avatar
    avant = actuel()
    if avant.startswith(NOM):                              # un essai raté d'avant : le vrai d'avant est dans ETAT
        avant = ""
    nom = f"{NOM}-{hashlib.md5(str(_t.time()).encode()).hexdigest()[:6]}"   # nom neuf : le bureau recharge
    creer_theme(nom)
    if avant and not avant.startswith(NOM):
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps({"avant": avant, "bureau": bureau()}), encoding="utf-8")
    ok = appliquer(nom)
    if not ok and (actuel() or "").startswith(NOM):        # raté : on ne laisse pas un thème introuvable
        try:
            prec = json.loads(ETAT.read_text(encoding="utf-8")).get("avant") or ""
        except Exception:
            prec = ""
        prec = prec if prec and not prec.startswith(NOM) else ("breeze_cursors" if bureau() == "kde" else "Adwaita")
        kw = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
        if kw:
            _run([kw, "--notify", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme", prec])
    for base in dossiers_themes():                          # les anciennes versions (et celle-ci si raté)
        for d in base.glob(NOM + "-*"):
            if d.is_dir() and (d.name != nom or not ok):
                shutil.rmtree(d, ignore_errors=True)
    return ok, (avant if ok else _dernier_message.get("txt", ""))


def remettre():
    try:
        avant = json.loads(ETAT.read_text(encoding="utf-8")).get("avant") or ""
    except Exception:
        avant = ""
    if not avant:
        avant = "breeze_cursors" if bureau() == "kde" else "Adwaita"
    if not bureau():
        try:
            (Path.home() / ".icons" / "default" / "index.theme").unlink()
        except OSError:
            pass
        return True
    return appliquer(avant)


def actif():
    return (actuel() or "").startswith(NOM)


# ------------------------------------------------------------------ la roue autour du pointeur
ACTIONS = [
    ("quoi", "🔍", "C'est quoi ça ?"),
    ("copier", "📋", "Copier le texte ici"),
    ("traduire", "🌐", "Traduire ici"),
    ("couleur", "🎨", "La couleur ici"),
    ("montre", "👉", "Montre-moi…"),
    ("ecrire", "✏️", "Lui écrire"),
    ("zone", "🔲", "Traduire une zone"),
]
GLYPHES = {"quoi": 0xedeb, "copier": 0xea7a, "traduire": 0xebbe, "couleur": 0xeb01, "montre": 0xef4f,
           "ecrire": 0xeaed, "zone": 0xfcc3}       # pictogrammes Tabler (comme ses ronds)


class Roue(QWidget):
    choisi = pyqtSignal(str)

    def __init__(self, centre, police="", survol_son=None, clic_son=None):
        self.police, self.survol_son, self.clic_son = police, survol_son, clic_son
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.R, self.r = 92, 26
        taille = 2 * (self.R + self.r + 70)
        self.resize(taille, taille)
        self.move(int(centre.x() - taille / 2), int(centre.y() - taille / 2))
        self.survol = -1
        self.centre_mode = "retour"        # « retour » : bouton ↩ au centre ; « visage » : son visage, ↩ au survol
        self.k = 0.0
        self.setMouseTracking(True)
        self.t = QTimer(self)
        self.t.timeout.connect(self._anim)
        self.t.start(16)

    def _anim(self):
        self.k = min(1.0, self.k + 0.12)
        self.update()
        if self.k >= 1.0:
            self.t.stop()

    def _pos(self, i):
        a = -math.pi / 2 + 2 * math.pi * i / len(ACTIONS)
        c = QPointF(self.width() / 2, self.height() / 2)
        e = 1 - (1 - self.k) ** 3
        return QPointF(c.x() + self.R * e * math.cos(a), c.y() + self.R * e * math.sin(a))

    def _sous(self, pt):
        c = QPointF(self.width() / 2, self.height() / 2)
        if (pt.x() - c.x()) ** 2 + (pt.y() - c.y()) ** 2 <= 24 ** 2:
            return -2                                          # le bouton retour, au centre
        for i in range(len(ACTIONS)):
            q = self._pos(i)
            if (pt.x() - q.x()) ** 2 + (pt.y() - q.y()) ** 2 <= (self.r + 4) ** 2:
                return i
        return -1

    def mouseMoveEvent(self, e):
        s = self._sous(e.position())
        if s != self.survol:
            self.survol = s
            if s != -1 and self.survol_son:
                try:
                    self.survol_son()
                except Exception:
                    pass
            self.update()

    def mousePressEvent(self, e):
        i = self._sous(e.position())
        self.close()
        if i == -2 and self.clic_son:
            try:
                self.clic_son()
            except Exception:
                pass
        if i >= 0:
            if self.clic_son:
                try:
                    self.clic_son()
                except Exception:
                    pass
            self.choisi.emit(ACTIONS[i][0])

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setOpacity(self.k)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.2))            # un anneau de verre dépoli, comme ses ronds
        p.setBrush(QColor(30, 32, 40, 110))
        p.drawEllipse(c, self.R + self.r + 10, self.R + self.r + 10)
        img = AVATAR["img"]
        sur_c = self.survol == -2
        if self.centre_mode == "visage" and not sur_c and img is not None:   # son visage ; ↩ quand on passe dessus
            path = QPainterPath()
            path.addEllipse(c, 22, 22)
            p.save()
            p.setClipPath(path)
            p.drawImage(QRectF(c.x() - 22, c.y() - 22, 44, 44), img)
            p.restore()
            p.setPen(QPen(QColor("white"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 22, 22)
        else:                                                   # le bouton retour, comme les autres ronds
            rr = 22 + (2 if sur_c else 0)
            p.setPen(QPen(QColor(255, 255, 255, 175 if sur_c else 125), 1.4))
            p.setBrush(QColor(255, 255, 255, 70) if sur_c else QColor(30, 32, 40, 170))
            p.drawEllipse(c, rr, rr)
            box = QRectF(c.x() - 22, c.y() - 22, 44, 44)
            p.setPen(QColor(255, 255, 255))
            if self.police:
                fi = QFont(self.police)
                fi.setPixelSize(20)
                p.setFont(fi)
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, chr(0xeb77))      # flèche retour (Tabler)
            else:
                fi = QFont()
                fi.setPixelSize(18)
                p.setFont(fi)
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, "↩")
        f = QFont()
        for i, (aid, ico, nom) in enumerate(ACTIONS):
            q = self._pos(i)
            on = i == self.survol
            rr = self.r + (2.5 if on else 0)
            p.setPen(QPen(QColor(255, 255, 255, 175 if on else 125), 1.4))
            p.setBrush(QColor(30, 32, 40, 150) if not on else QColor(255, 255, 255, 70))
            p.drawEllipse(q, rr, rr)
            if on:                                        # le reflet du survol
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 40))
                p.drawEllipse(q, rr - 3, rr - 3)
            code = GLYPHES.get(aid)
            box = QRectF(q.x() - self.r, q.y() - self.r, 2 * self.r, 2 * self.r)
            p.setPen(QColor(255, 255, 255))
            if code and self.police:
                fi = QFont(self.police)
                fi.setPixelSize(22)
                p.setFont(fi)
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, chr(code))
            else:
                f.setPixelSize(20)
                p.setFont(f)
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, ico)
        if self.survol != -1:                                  # le nom de l'action, sous le centre
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            txt = tr("Retour") if self.survol == -2 else tr(ACTIONS[self.survol][2])
            box = QRectF(c.x() - 62, c.y() + 30, 124, 26)
            path = QPainterPath()
            path.addRoundedRect(box, 13, 13)
            p.fillPath(path, QColor(34, 36, 44, 225))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawPath(path)
            p.setPen(QColor("#f5f5f7"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, txt)
        p.end()


class Etoile(QWidget):
    """Une petite étoile-cœur qui suit le pointeur, en douceur (option)."""

    def __init__(self, position):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.position = position                               # fonction -> QPoint (la souris, même sous Wayland)
        self.resize(28, 28)
        self.p = QPointF(position())
        self.phase = 0.0
        self.t = QTimer(self)
        self.t.timeout.connect(self._tic)
        self.t.start(33)

    def _tic(self):
        cible = QPointF(self.position()) + QPointF(18, 20)
        d = cible - self.p
        if abs(d.x()) + abs(d.y()) < 0.5:
            self.phase += 0.05
            if self.isVisible():
                self.update()
            return
        self.p += d * 0.22
        self.phase += 0.15
        self.move(int(self.p.x()), int(self.p.y()))
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(0.75 + 0.25 * math.sin(self.phase))
        _coeur(p, QPointF(14, 15), 6.5)
        p.end()


# ------------------------------------------------------------------ Windows : le même mode, avec l'API de Windows
if sys.platform.startswith("win"):
    try:
        import curseur_windows as _W
        activer, remettre, actif = _W.activer, _W.remettre, _W.actif
        _dernier_message = _W._dernier

        def actuel():
            return NOM if _W.actif() else "windows"

        def bureau():
            return "windows"
    except Exception:
        pass
