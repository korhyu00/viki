"""🍿 Mes services : Netflix, Disney+, Spotify… en grandes tuiles, dans une vraie fenêtre à côté de Viki.
Les tuiles ont une couleur et le nom bien lisible. Les icônes officielles des sites ne sont téléchargées que si
tu cliques sur « Récupérer les icônes » (une seule fois, gardées sur ton PC). Tu peux aussi mettre ta propre image."""
import re
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urljoin

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRectF, QPoint, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont, QImage, QCursor, QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea,
                             QMenu, QFileDialog, QApplication, QFrame)

try:
    from i18n import tr
except Exception:                                          # pragma: no cover
    def tr(t):
        return t

COULEURS = {"Netflix": "#8f1d1d", "Disney+": "#16357a", "Prime Video": "#0c5a6e", "Crunchyroll": "#a8510e",
            "ADN": "#1f3f8c", "YouTube": "#9b1c1c", "Twitch": "#5b2ca0", "Max": "#2a2fa0", "Apple TV+": "#2c2c2e",
            "Paramount+": "#1546a0", "Canal+": "#1c1c1e", "Arte": "#9a3d12", "france.tv": "#22489c",
            "Spotify": "#17703b", "Deezer": "#5a2aa0", "YouTube Music": "#8c1c2e", "Apple Music": "#a3263f",
            "SoundCloud": "#a8460e", "Qobuz": "#1d4f73", "Tidal": "#202024"}
W, H = 150, 96

CSS = """
QLabel#grandTitre { font-size: 20px; font-weight: bold; color: #3d2733; }
QLabel#aide { color: #9a8290; font-size: 9pt; }
QLabel#section { font-size: 14px; font-weight: bold; color: #3d2733; padding-top: 6px; background: transparent; }
QPushButton#seg { border-radius: 0; padding: 5px 13px; border-left: none; }
QPushButton#seg[pos="g"] { border-top-left-radius: 8px; border-bottom-left-radius: 8px; border-left: 1px solid #e3d3dc; }
QPushButton#seg[pos="d"] { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QPushButton#seg:checked { background: #d0457a; color: white; border-color: #d0457a; }
QPushButton#tuile { border: none; background: transparent; padding: 0; }
"""


def _slug(nom):
    return re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_")


class _Sig(QObject):
    fini = pyqtSignal(int, int)


class ServicesWin(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setObjectName("atelier")
        self.setWindowTitle(tr("🍿 Mes services"))
        self.resize(760, 560)
        self.filtre = ""
        self.sig = _Sig()
        self.sig.fini.connect(self._icones_fini)
        try:
            import pomme
            base = pomme.STUDIO
        except Exception:
            base = ""
        self.setStyleSheet(base + CSS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 12)
        lay.setSpacing(10)
        top = QHBoxLayout()
        t = QLabel(tr("🍿 Mes services"))
        t.setObjectName("grandTitre")
        top.addWidget(t)
        top.addSpacing(12)
        self.segs = []
        filtres = [("Tout", ""), ("Vidéo", "Vidéo"), ("Musique", "Musique")]
        for i, (lab, k) in enumerate(filtres):
            b = QPushButton(tr(lab))
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(k == self.filtre)
            b.setProperty("pos", "g" if i == 0 else "d" if i == len(filtres) - 1 else "m")
            b.clicked.connect(lambda _c=False, k=k: self._filtrer(k))
            top.addWidget(b)
            self.segs.append((k, b))
        top.addStretch()
        self.b_icones = QPushButton(tr("⬇️  Récupérer les icônes"))
        self.b_icones.setToolTip(tr("Télécharge une fois la petite icône de chaque site (gardée sur ton PC)."))
        self.b_icones.clicked.connect(self.recuperer_icones)
        top.addWidget(self.b_icones)
        lay.addLayout(top)
        aide = QLabel(tr("Clic : ouvrir · clic droit : favori, ton image, cacher un service"))
        aide.setObjectName("aide")
        lay.addWidget(aide)
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setFrameShape(QFrame.Shape.NoFrame)
        self.zone.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        lay.addWidget(self.zone, 1)
        self.remplir()

    # ------------------------------------------------------------ données
    def _dossier(self):
        d = Path(self.C.CONFIG_DIR) / "services_icones"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _image(self, nom):
        perso = (self.comp.cfg.get("services_images") or {}).get(nom)
        if perso and Path(perso).exists():
            return perso, True
        f = self._dossier() / (_slug(nom) + ".png")
        return (str(f), False) if f.exists() else ("", False)

    # ------------------------------------------------------------ affichage
    def _filtrer(self, k):
        self.filtre = k
        for kk, b in self.segs:
            b.setChecked(kk == k)
        self.remplir()

    def _avant(self, v):
        """Ce qui vient avant les services (le Salon y met « Reprendre »)."""

    def remplir(self):
        cache = set(self.comp.cfg.get("services_caches", []))
        fav = [n for n in self.comp.cfg.get("services_epingles", []) if n not in cache]
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self._avant(v)
        tous = {x[0]: (x, titre) for titre, l in self.comp.SERVICES for x in l}
        favs = [tous[n][0] for n in fav if n in tous and (not self.filtre or tous[n][1] == self.filtre)]
        sections = ([("⭐", "Mes favoris", favs)] if favs else []) + \
            [("🎬" if t == "Vidéo" else "🎵", t, [x for x in l if x[0] not in fav]) for t, l in self.comp.SERVICES
             if not self.filtre or t == self.filtre]
        for ico, titre, items in sections:
            items = [x for x in items if x[0] not in cache]
            if not items:
                continue
            s = QLabel(ico + "  " + tr(titre))
            s.setObjectName("section")
            v.addWidget(s)
            g = QGridLayout()
            g.setSpacing(12)
            cols = max(1, (self.width() - 60) // (W + 12))
            self._cols = cols
            for i, (nom, url, app) in enumerate(items):
                g.addWidget(self._tuile(nom, url, app), i // cols, i % cols)
            g.setColumnStretch(cols, 1)
            v.addLayout(g)
        if cache:
            b = QPushButton(tr("👁  Réafficher les services cachés ({})").format(len(cache)))
            b.clicked.connect(self._tout_montrer)
            h = QHBoxLayout()
            h.addWidget(b)
            h.addStretch()
            v.addLayout(h)
        v.addStretch()
        old = self.zone.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self.zone.setWidget(page)

    def _vignette(self, nom):
        dpr = 2
        pm = QPixmap(W * dpr, H * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 14, 14)
        p.setClipPath(path)
        p.fillRect(QRectF(0, 0, W, H), QColor(COULEURS.get(nom, "#3a3a3c")))
        img, perso = self._image(nom)
        src = QImage(img) if img else QImage()
        f = QFont()
        f.setBold(True)
        if not src.isNull() and perso:                     # ton image : toute la tuile, nom en bas
            sc = src.scaled(W * dpr, H * dpr, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
            p.drawImage(QRectF(0, 0, W, H), sc, QRectF((sc.width() - W * dpr) / 2, (sc.height() - H * dpr) / 2,
                                                       W * dpr, H * dpr))
            p.fillRect(QRectF(0, H - 30, W, 30), QColor(0, 0, 0, 140))
            f.setPixelSize(13)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(10, H - 30, W - 20, 30), Qt.AlignmentFlag.AlignVCenter, nom)
        elif not src.isNull():                             # icône du site : en haut, nom en dessous
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(QRectF(W / 2 - 26, 14, 52, 52), 12, 12)
            p.drawImage(QRectF(W / 2 - 20, 20, 40, 40), src.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation))
            f.setPixelSize(14)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(6, 70, W - 12, 28), Qt.AlignmentFlag.AlignCenter, nom)
        else:                                              # juste la couleur et le nom, en grand
            f.setPixelSize(20 if len(nom) <= 11 else 16)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(10, 0, W - 20, H), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, nom)
        p.end()
        return pm

    def _tuile(self, nom, url, app):
        b = QPushButton()
        b.setObjectName("tuile")
        b.setIcon(QIcon(self._vignette(nom)))
        b.setIconSize(QSize(W, H))
        b.setFixedSize(W, H)
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setToolTip(tr("Ouvrir {}").format(nom) + (f" ({app})" if app else ""))
        b.clicked.connect(lambda: self.comp.ouvrir_service(nom, url, app))
        b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda pos, bb=b: self._menu(nom, bb.mapToGlobal(pos)))
        return b

    def _menu(self, nom, pos):
        m = QMenu(self)
        m.addAction(tr("🖼️  Mettre mon image…"), lambda: self._mon_image(nom))
        if (self.comp.cfg.get("services_images") or {}).get(nom):
            m.addAction(tr("↩️  Retirer mon image"), lambda: self._retirer_image(nom))
        fav = self.comp.cfg.get("services_epingles", [])
        if nom in fav:
            m.addAction(tr("⭐  Retirer de mes favoris"), lambda: self._epingler(nom, False))
        else:
            m.addAction(tr("⭐  Mettre en favori (en premier)"), lambda: self._epingler(nom, True))
        m.addAction(tr("🙈  Cacher ce service"), lambda: self._cacher(nom))
        self._menu_ref = m
        m.popup(pos)

    def _mon_image(self, nom):
        p, _f = QFileDialog.getOpenFileName(self, tr("Une image pour {}").format(nom), str(Path.home()),
                                            "Images (*.png *.jpg *.jpeg *.webp)")
        if not p:
            return
        im = QImage(p)
        if im.isNull():
            return
        dst = self._dossier() / (_slug(nom) + "_perso.png")
        im.scaled(W * 3, H * 3, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                  Qt.TransformationMode.SmoothTransformation).save(str(dst))
        imgs = dict(self.comp.cfg.get("services_images") or {})
        imgs[nom] = str(dst)
        self.comp.cfg["services_images"] = imgs
        self.C.save_config(self.comp.cfg)
        self.remplir()

    def _retirer_image(self, nom):
        imgs = dict(self.comp.cfg.get("services_images") or {})
        imgs.pop(nom, None)
        self.comp.cfg["services_images"] = imgs
        self.C.save_config(self.comp.cfg)
        self.remplir()

    def _epingler(self, nom, oui):
        fav = [x for x in self.comp.cfg.get("services_epingles", []) if x != nom]
        if oui:
            fav.append(nom)
        self.comp.cfg["services_epingles"] = fav
        self.C.save_config(self.comp.cfg)
        self.remplir()

    def _cacher(self, nom):
        self.comp._service_visible(nom, False)
        self.remplir()

    def _tout_montrer(self):
        self.comp.cfg["services_caches"] = []
        self.C.save_config(self.comp.cfg)
        self.remplir()

    # ------------------------------------------------------------ icônes des sites (sur demande)
    def recuperer_icones(self):
        try:
            from actu_fenetre import demander
            ok = demander(self, "Récupérer les icônes",
                          tr("Je télécharge une seule fois la petite icône de chaque site (Netflix, Spotify…) et je "
                             "la garde sur ton PC. Rien d'autre n'est envoyé. D'accord ?"), oui="Télécharger",
                          non="Annuler", icone="⬇️")
        except Exception:
            ok = True
        if not ok:
            return
        todo = [(nom, url) for _t, l in self.comp.SERVICES for nom, url, _a in l
                if not (self._dossier() / (_slug(nom) + ".png")).exists()]
        self.b_icones.setEnabled(False)
        self.b_icones.setText(tr("⏳ Je télécharge…"))
        dossier = self._dossier()

        def work():
            n = 0
            for nom, url in todo:
                try:
                    data = icone_du_site(url)
                    im = QImage()
                    if data and im.loadFromData(data) and not im.isNull():
                        im.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation).save(str(dossier / (_slug(nom) + ".png")))
                        n += 1
                except Exception:
                    pass
            self.sig.fini.emit(n, len(todo))
        threading.Thread(target=work, daemon=True).start()

    def _icones_fini(self, n, total):
        self.b_icones.setEnabled(True)
        self.b_icones.setText(tr("⬇️  Récupérer les icônes"))
        self.remplir()
        try:
            self.comp.say(tr("C'est fait : {} icône(s) récupérée(s) !").format(n) if n or not total else
                          tr("Je n'ai pas réussi à récupérer les icônes. Es-tu connecté à internet ?"))
        except Exception:
            pass

    # ------------------------------------------------------------ place : à côté d'elle
    def placer(self):
        c = self.comp
        try:
            r = c.body_rect()
            g = c.mapToGlobal(r.topLeft())
            body_l, body_r, body_b = g.x(), g.x() + r.width(), g.y() + r.height()
            scr = (c.screen() or QApplication.primaryScreen()).availableGeometry()
        except Exception:
            return
        w, h = min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 60)
        self.resize(w, h)
        rb = getattr(c, "ronds_bar", None)
        if rb is not None and rb.isVisible():
            body_l = min(body_l, rb.geometry().left())
            body_r = max(body_r, rb.geometry().right())
        gap = 16
        x = body_l - w - gap if body_l - w - gap >= scr.left() else body_r + gap
        x = max(scr.left() + 8, min(x, scr.right() - w - 8))
        y = max(scr.top() + 30, min(body_b - h, scr.bottom() - h - 8))
        self.move(QPoint(int(x), int(y)))

    def resizeEvent(self, e):
        cols = max(1, (self.width() - 60) // (W + 12))
        if cols != getattr(self, "_cols", cols):
            self.remplir()
        self._cols = cols

    def montrer(self):
        self.remplir()
        self.placer()
        self.show()
        self.raise_()
        self.activateWindow()


def icone_du_site(url):
    """La plus grande icône déclarée par la page d'accueil (apple-touch-icon, icon), sinon /favicon.ico."""
    hdr = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Viki"}
    base = "{0.scheme}://{0.netloc}".format(urlparse(url))
    cands = []
    try:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read(300000).decode("utf-8", "ignore")
        for m in re.finditer(r"<link\b[^>]*>", html, re.I):
            tag = m.group(0)
            rel = re.search(r'rel=["\']([^"\']+)', tag, re.I)
            href = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if not rel or not href or "icon" not in rel.group(1).lower():
                continue
            if href.group(1).lower().endswith(".svg"):
                continue
            taille = re.search(r'sizes=["\'](\d+)', tag)
            score = int(taille.group(1)) if taille else (180 if "apple" in rel.group(1).lower() else 32)
            cands.append((score, urljoin(url, href.group(1))))
    except Exception:
        pass
    cands.sort(reverse=True)
    for _s, u in cands + [(0, base + "/apple-touch-icon.png"), (0, base + "/favicon.ico")]:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=8) as r:
                data = r.read(2000000)
            if data and len(data) > 100:
                return data
        except Exception:
            continue
    return None


# ====================================================================== 📺 le Salon : ta liste + tes services
class _Affiches:
    """Pour réutiliser les affiches de « Ma liste » (même dossier d'images, même dessin)."""

    def __init__(self, C):
        self.C = C

    def _dossier_img(self):
        import liste
        return liste.ListeWindow._dossier_img(self)

    def vignette(self, it, w, h):
        import liste
        return liste.ListeWindow._vignette(self, it, w, h, True)


class SalonWin(ServicesWin):
    """Ce soir, on regarde quoi ? « Reprendre » (ta liste, là où tu t'es arrêté), puis tes services."""

    def __init__(self, comp, C):
        super().__init__(comp, C)
        self.setWindowTitle(tr("📺 Salon"))
        titre = self.findChild(QLabel, "grandTitre")
        if titre is not None:
            titre.setText(tr("📺 Salon"))
        self.resize(800, 640)

    def _avant(self, v):
        import datetime
        try:
            import liste
            items = [it for it in self.comp.liste_items() if it.get("type") in ("serie", "film", "video")]
        except Exception:
            items = []
        rep = sorted([it for it in items if it.get("vu") or it.get("ep") or it.get("temps")],
                     key=lambda i: i.get("vu", ""), reverse=True)[:10]
        h = QHBoxLayout()
        s = QLabel(("🌙  " + tr("Ce soir") if datetime.datetime.now().hour >= 18 else "▶️  " + tr("Reprendre")))
        s.setObjectName("section")
        h.addWidget(s)
        h.addStretch()
        b = QPushButton(tr("📺  Ma liste complète"))
        b.clicked.connect(self.comp.open_liste)
        h.addWidget(b)
        v.addLayout(h)
        if not rep:
            vide = QLabel(tr("Rien à reprendre pour l'instant. Ajoute des séries dans « Ma liste » : elles "
                             "s'afficheront ici, à l'épisode où tu t'es arrêté."))
            vide.setObjectName("aide")
            vide.setWordWrap(True)
            v.addWidget(vide)
            return
        aff = _Affiches(self.C)
        rang = QHBoxLayout()
        rang.setSpacing(12)
        for it in rep:
            carte = QPushButton()
            carte.setObjectName("tuile")
            carte.setFixedSize(176, 124)
            pm = QPixmap(176, 124)
            pm.fill(Qt.GlobalColor.transparent)
            try:
                img = aff.vignette(it, 176, 99)
            except Exception:
                img = None
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if img is not None:
                p.drawPixmap(0, 0, img)
            f = QFont()
            f.setBold(True)
            f.setPixelSize(12)
            p.setFont(f)
            p.setPen(QColor("#ece9f2"))
            sous = (tr("Épisode {}").format(it["ep"]) if it.get("ep") else "")
            p.drawText(QRectF(2, 101, 172, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       (it["nom"] + ("  ·  " + sous if sous else ""))[:34])
            p.end()
            carte.setIcon(QIcon(pm))
            carte.setIconSize(QSize(176, 124))
            carte.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            carte.setToolTip(tr("Clic : reprendre là où tu t'es arrêté"))
            carte.clicked.connect(lambda _c=False, i=it: self.comp.liste_open(i))
            rang.addWidget(carte)
        rang.addStretch()
        boite = QWidget()
        boite.setLayout(rang)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        sc.setWidget(boite)
        sc.setFixedHeight(146)
        v.addWidget(sc)
