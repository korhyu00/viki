"""« En cours » et « Aujourd'hui ».

- En cours : une petite carte près de Viki quand une musique ou une vidéo joue (n'importe quel lecteur compatible
  MPRIS : Firefox, Chrome, Spotify, VLC, mpv… sur KDE, GNOME, Xfce, Cinnamon…), avec précédent / pause / suivant.
  Après une série ouverte depuis « Ma liste », elle propose l'épisode suivant.
- Aujourd'hui : des widgets (météo, rappels, PC, ma liste, l'actu, en cours) d'un coup d'œil.
Rien ne sort du PC : MPRIS est le bus local du bureau (D-Bus de session)."""
import datetime
import time
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QCursor, QFont
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QApplication, QSizePolicy)

from actu_fenetre import CSS, Deplacable, tr

MPRIS = "org.mpris.MediaPlayer2."
CHEMIN = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


# ------------------------------------------------------------------ lecteurs du bureau (MPRIS, standard freedesktop)
class Mpris:
    """Lit les lecteurs multimédia du bureau. Marche sur tous les bureaux Linux (standard freedesktop)."""

    def __init__(self):
        self.ok = False
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage
            self._C, self._M = QDBusConnection, QDBusMessage
            self.bus = QDBusConnection.sessionBus()
            self.ok = self.bus.isConnected()
        except Exception:
            self.ok = False

    def _appel(self, svc, iface, meth, args=(), attente=600):
        m = self._M.createMethodCall(svc, CHEMIN, iface, meth)
        if args:
            m.setArguments(list(args))
        from PyQt6.QtDBus import QDBus
        r = self.bus.call(m, QDBus.CallMode.Block, attente)
        if r.type() == self._M.MessageType.ErrorMessage:
            raise RuntimeError(r.errorMessage())
        return r.arguments()

    def lecteurs(self):
        if not self.ok:
            return []
        try:
            r = self.bus.interface().registeredServiceNames()
            noms = r.value() if hasattr(r, "value") else r
        except Exception:
            return []
        return [n for n in noms if str(n).startswith(MPRIS)]

    @staticmethod
    def _val(v):
        """QDBusVariant / QVariant -> valeur Python."""
        for f in ("variant", "value"):
            if hasattr(v, f) and not isinstance(v, (str, bytes, int, float, list, dict)):
                try:
                    v = getattr(v, f)()
                except Exception:
                    pass
        return v

    def etat(self, svc):
        """{"svc", "nom", "statut", "titre", "artiste", "image", "duree", "position"}"""
        a = self._appel(svc, "org.freedesktop.DBus.Properties", "GetAll", [PLAYER])
        props = {k: self._val(v) for k, v in (a[0] if a else {}).items()}
        md = props.get("Metadata") or {}
        md = {k: self._val(v) for k, v in dict(md).items()} if isinstance(md, dict) else {}
        art = md.get("xesam:artist") or ""
        if isinstance(art, (list, tuple)):
            art = ", ".join(str(x) for x in art)
        nom = svc[len(MPRIS):].split(".")[0]
        return {"svc": svc, "nom": nom.capitalize(), "statut": str(props.get("PlaybackStatus") or ""),
                "titre": str(md.get("xesam:title") or ""), "artiste": str(art), "image": str(md.get("mpris:artUrl") or ""),
                "duree": int(md.get("mpris:length") or 0), "position": int(props.get("Position") or 0),
                "suivant": bool(props.get("CanGoNext", True)), "precedent": bool(props.get("CanGoPrevious", True))}

    def actif(self):
        """Le lecteur qui joue (sinon celui en pause), ou None."""
        vus = []
        for svc in self.lecteurs():
            try:
                e = self.etat(svc)
            except Exception:
                continue
            if e["titre"] or e["statut"] == "Playing":
                vus.append(e)
        vus.sort(key=lambda e: {"Playing": 0, "Paused": 1}.get(e["statut"], 2))
        return vus[0] if vus else None

    def commande(self, svc, meth):
        try:
            self._appel(svc, PLAYER, meth)
            return True
        except Exception:
            return False


def _arrondie(pm, w, h, r=10):
    out = QPixmap(w * 2, h * 2)
    out.setDevicePixelRatio(2)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.setClipPath(path)
    if pm is not None and not pm.isNull():
        sc = pm.scaled(w * 2, h * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(QRectF(0, 0, w, h), sc, QRectF((sc.width() - w * 2) / 2, (sc.height() - h * 2) / 2, w * 2, h * 2))
    else:
        p.fillRect(QRectF(0, 0, w, h), QColor("#8a2d4a"))
        f = QFont()
        f.setPixelSize(int(h * 0.42))
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return out


def _mmss(us):
    s = max(0, int(us // 1_000_000))
    return f"{s // 60}:{s % 60:02d}"


CSS_EN_PLUS = """
QPushButton#ctl { background: transparent; border: none; color: #ece9f2; font-size: 17px; padding: 2px 6px; }
QPushButton#ctl:hover { color: #ffffff; background: #2f2a3a; border-radius: 8px; }
QLabel#piste { font-size: 13px; font-weight: 600; }
QLabel#qui { color: #9b96a8; font-size: 11px; }
QFrame#barre { background: #3a3644; border-radius: 2px; min-height: 4px; max-height: 4px; }
QFrame#plein { background: #ece9f2; border-radius: 2px; min-height: 4px; max-height: 4px; }
QFrame#tuileW { background: #26232d; border: 1px solid #3a3644; border-radius: 13px; }
QFrame#tuileW:hover { border-color: #6f6a80; }
QLabel#wTitre { color: #9b96a8; font-size: 11px; }
QLabel#wGros { font-size: 22px; font-weight: 600; }
QLabel#wTexte { font-size: 12.5px; }
QLabel#wPetit { color: #9b96a8; font-size: 11px; }
QPushButton#coin { background: #d0457a; color: white; border: none; border-radius: 9px; padding: 3px 9px;
                   font-size: 11px; font-weight: 600; }
QPushButton#coin:hover { background: #b8386a; }
"""


def _pres_de_viki(comp, w, h, cote_oppose=False):
    """Une position à côté d'elle, sans couvrir ses ronds."""
    try:
        r = comp.body_rect()
        g = comp.mapToGlobal(r.topLeft())
        L, R, B = g.x(), g.x() + r.width(), g.y() + r.height()
        scr = (comp.screen() or QApplication.primaryScreen()).availableGeometry()
    except Exception:
        return None
    rb = comp.__dict__.get("ronds_bar")
    if rb is not None and rb.isVisible():
        L, R = min(L, rb.geometry().left()), max(R, rb.geometry().right())
    gap = 16
    gauche_ok = L - w - gap >= scr.left()
    x = (L - w - gap) if (gauche_ok != cote_oppose and gauche_ok) or (cote_oppose and R + gap + w > scr.right()) \
        else R + gap
    if x + w > scr.right():
        x = L - w - gap
    x = max(scr.left() + 8, min(x, scr.right() - w - 8))
    y = max(scr.top() + 8, min(B - h, scr.bottom() - h - 8))
    return QPoint(int(x), int(y))


# ------------------------------------------------------------------ la carte « En cours »
class EnCours(Deplacable, QWidget):
    TAILLE_CLE = "en_cours_taille"

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.comp = comp
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty("sans_theme", True)          # widgets façon Apple : toujours sombres, lisibles
        self.setStyleSheet(CSS + CSS_EN_PLUS)
        self.setFixedWidth(300)
        self.mpris = Mpris()
        self.e = None
        self.cache_img = {}
        self.ignore = ""                 # piste fermée par toi : on ne la remontre pas
        self.serie = None                # (titre de ma liste, quand) : proposer l'épisode suivant
        self.deplacee = False
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(6)
        # musique / vidéo
        self.zone_media = QWidget()
        self.zone_media.setObjectName("fond")
        zm = QVBoxLayout(self.zone_media)
        zm.setContentsMargins(0, 0, 0, 0)
        zm.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.cover = QLabel()
        self.cover.setFixedSize(52, 52)
        top.addWidget(self.cover)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.piste = QLabel("")
        self.piste.setObjectName("piste")
        self.piste.setProperty("no_i18n", True)
        col.addWidget(self.piste)
        self.qui = QLabel("")
        self.qui.setObjectName("qui")
        self.qui.setProperty("no_i18n", True)
        col.addWidget(self.qui)
        top.addLayout(col, 1)
        cache = QPushButton("👁")
        cache.setObjectName("x")
        cache.setToolTip(tr("Cacher cette carte"))
        cache.clicked.connect(lambda: self._menu_cacher(cache))
        top.addWidget(cache, 0, Qt.AlignmentFlag.AlignTop)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setToolTip(tr("Cacher (jusqu'au prochain morceau)"))
        x.clicked.connect(self.fermer_media)
        top.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        zm.addLayout(top)
        self.barre = QFrame()
        self.barre.setObjectName("barre")
        self.plein = QFrame(self.barre)
        self.plein.setObjectName("plein")
        zm.addWidget(self.barre)
        ctl = QHBoxLayout()
        ctl.addStretch()
        self.b_prev = QPushButton("⏮")
        self.b_play = QPushButton("⏸")
        self.b_next = QPushButton("⏭")
        for b, meth in ((self.b_prev, "Previous"), (self.b_play, "PlayPause"), (self.b_next, "Next")):
            b.setObjectName("ctl")
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, m=meth: self._cmd(m))
            ctl.addWidget(b)
            ctl.addSpacing(6)
        ctl.addStretch()
        zm.addLayout(ctl)
        lay.addWidget(self.zone_media)
        # série de « Ma liste »
        self.zone_serie = QFrame()
        self.zone_serie.setObjectName("tuileW")
        zs = QHBoxLayout(self.zone_serie)
        zs.setContentsMargins(10, 8, 8, 8)
        self.l_serie = QLabel("")
        self.l_serie.setObjectName("wTexte")
        self.l_serie.setWordWrap(True)
        self.l_serie.setProperty("no_i18n", True)
        zs.addWidget(self.l_serie, 1)
        self.b_suite = QPushButton("▶ " + tr("Épisode suivant"))
        self.b_suite.setObjectName("btn")
        self.b_suite.clicked.connect(self._episode_suivant)
        zs.addWidget(self.b_suite)
        xs = QPushButton("✕")
        xs.setObjectName("x")
        xs.clicked.connect(self.fermer_serie)
        zs.addWidget(xs, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.zone_serie)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2000)

    # ---------- données
    def tick(self):
        c = self.comp
        if not c.cfg.get("en_cours", True) or not c.isVisible() or time.time() < float(c.cfg.get("en_cours_pause") or 0):
            return self.hide()
        e = None
        if self.mpris.ok:
            try:
                e = self.mpris.actif()
            except Exception:
                e = None
        cle = (e or {}).get("svc", "") + "|" + (e or {}).get("titre", "")
        if e and cle == self.ignore:
            e = None
        if e and e["statut"] not in ("Playing", "Paused"):
            e = None
        self.e = e
        serie_ok = self.serie and time.time() - self.serie[1] < 4 * 3600
        self.zone_media.setVisible(bool(e))
        self.zone_serie.setVisible(bool(serie_ok))
        if e:
            self.piste.setText(self._court(e["titre"] or e["nom"], 34))
            self.qui.setText(" · ".join(x for x in (self._court(e["artiste"], 26), e["nom"]) if x) +
                             (f"  ·  {_mmss(e['position'])} / {_mmss(e['duree'])}" if e["duree"] else ""))
            self.b_play.setText("⏸" if e["statut"] == "Playing" else "▶")
            self.b_prev.setEnabled(e["precedent"])
            self.b_next.setEnabled(e["suivant"])
            self.barre.setVisible(bool(e["duree"]))
            if e["duree"]:
                k = max(0.0, min(1.0, e["position"] / e["duree"]))
                QTimer.singleShot(0, lambda k=k: self.plein.setGeometry(0, 0, int(self.barre.width() * k), 4))
            self._pochette(e["image"])
        if serie_ok:
            it = self.serie[0]
            self.l_serie.setText(f"{it['nom']} · {tr('épisode')} {it.get('ep') or 1}\n" + tr("Tu as fini ?"))
        if (e or serie_ok) and not self.isVisible():
            self.adjustSize()
            if not self.deplacee:
                p = _pres_de_viki(c, self.width(), self.sizeHint().height(), cote_oppose=True)
                if p is not None:
                    self.move(p)
            self.show()
        elif not (e or serie_ok) and self.isVisible():
            self.hide()
        else:
            self.adjustSize()

    @staticmethod
    def _court(t, n):
        t = str(t or "")
        return t if len(t) <= n else t[:n - 1] + "…"

    def _pochette(self, url):
        pm = self.cache_img.get(url)
        if pm is None:
            pm = QPixmap()
            if url.startswith("file://"):
                pm.load(unquote(urlparse(url).path))
            elif url.startswith(("http://", "https://")) and self.comp.cfg.get("en_cours_images", True):
                self.cache_img[url] = QPixmap()              # pas deux fois
                try:
                    import suivi

                    def work():
                        return suivi.fetch_image(url, limit=3_000_000)

                    def then(data):
                        if isinstance(data, (bytes, bytearray)):
                            p2 = QPixmap()
                            p2.loadFromData(data)
                            self.cache_img[url] = p2
                            if self.e and self.e["image"] == url:
                                self.cover.setPixmap(_arrondie(p2, 52, 52))
                    self.comp._bg(work, then)
                except Exception:
                    pass
            self.cache_img[url] = pm
        self.cover.setPixmap(_arrondie(pm, 52, 52))

    # ---------- cacher
    def _menu_cacher(self, btn):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("🙈  " + tr("Cacher pour ce morceau"), self.fermer_media)
        m.addAction("⏰  " + tr("Cacher pendant 1 heure"), lambda: self._pause(3600))
        m.addAction("🌙  " + tr("Cacher jusqu'à demain"), lambda: self._pause(
            (datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(6)) -
             datetime.datetime.now()).total_seconds()))
        m.addSeparator()
        m.addAction("🚫  " + tr("Ne plus jamais l'afficher"), self._jamais)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _pause(self, sec):
        self.comp.cfg["en_cours_pause"] = time.time() + sec
        self.comp.save_cfg()
        self.hide()

    def _jamais(self):
        self.comp.cfg["en_cours"] = False
        self.comp.save_cfg()
        self.hide()
        self.comp.say("D'accord, je ne l'affiche plus. Tu peux la remettre dans Réglages → Au quotidien.")

    # ---------- actions
    def _cmd(self, meth):
        if self.e:
            self.mpris.commande(self.e["svc"], meth)
            QTimer.singleShot(300, self.tick)

    def fermer_media(self):
        if self.e:
            self.ignore = self.e["svc"] + "|" + self.e["titre"]
        self.tick()

    def fermer_serie(self):
        self.serie = None
        self.tick()

    def serie_ouverte(self, it):
        """Appelé quand une série de « Ma liste » est ouverte."""
        if it.get("type") == "serie":
            self.serie = (it, time.time())
            QTimer.singleShot(500, self.tick)

    def _episode_suivant(self):
        if self.serie:
            it = self.serie[0]
            self.comp.liste_next(it)
            self.serie = (it, time.time())
            self.tick()

    def _touche(self):
        self.deplacee = True


# ------------------------------------------------------------------ le panneau « Aujourd'hui »
class Tuile(QFrame):
    def __init__(self, titre, gros="", texte="", petit="", action=None, large=False, bouton=None):
        super().__init__()
        self.setObjectName("tuileW")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(86)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 9, 12, 10)
        v.setSpacing(2)
        for txt, obj in ((titre, "wTitre"), (gros, "wGros"), (texte, "wTexte"), (petit, "wPetit")):
            if txt:
                l = QLabel(txt)
                l.setObjectName(obj)
                l.setWordWrap(True)
                if obj in ("wTexte", "wPetit"):
                    l.setProperty("no_i18n", obj == "wTexte")
                v.addWidget(l)
        v.addStretch()
        self.action = action
        self.large = large
        self.coin = None
        if bouton:                                         # petit bouton qui apparaît au survol (ex. « Changer »)
            self.coin = QPushButton(bouton[0], self)
            self.coin.setObjectName("coin")
            self.coin.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.coin.clicked.connect(bouton[1])
            self.coin.adjustSize()
            self.coin.hide()
        if action:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def resizeEvent(self, e):
        if self.coin is not None:
            self.coin.move(self.width() - self.coin.width() - 8, 6)

    def enterEvent(self, e):
        if self.coin is not None:
            self.coin.show()
            self.coin.raise_()

    def leaveEvent(self, e):
        if self.coin is not None:
            self.coin.hide()

    def mousePressEvent(self, e):
        if self.action and e.button() == Qt.MouseButton.LeftButton:
            self.action()


METEO_TXT = {"soleil": "Soleil", "nuages": "Nuageux", "pluie": "Pluie", "neige": "Neige", "orage": "Orage",
             "brouillard": "Brouillard", "nuit": "Nuit claire"}


class Aujourdhui(Deplacable, QWidget):
    TAILLE_CLE = "aujourdhui_taille"

    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.comp, self.C = comp, C
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)          # widgets façon Apple : toujours sombres, lisibles
        self.setStyleSheet(CSS + CSS_EN_PLUS)
        self.setFixedWidth(400)
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        self.lay = QVBoxLayout(cadre)
        self.lay.setContentsMargins(14, 12, 12, 14)
        self.lay.setSpacing(10)
        top = QHBoxLayout()
        self.titre = QLabel("")
        self.titre.setObjectName("titre")
        top.addWidget(self.titre)
        top.addStretch()
        self.b_notifs = QPushButton("🔔")
        self.b_notifs.setObjectName("btn")
        self.b_notifs.setToolTip(tr("Ce que Viki t'a dit"))
        self.b_notifs.clicked.connect(lambda: (self.hide(), self.comp.open_notifs()))
        top.addWidget(self.b_notifs)
        if hasattr(self.comp, "menu_forme"):
            bf = QPushButton("💪")
            bf.setObjectName("btn")
            bf.setToolTip(tr("Forme : routine, santé, semaine, muscu"))
            bf.clicked.connect(lambda: (self.hide(), self.comp.menu_forme()))
            top.addWidget(bf)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.clicked.connect(self.hide)
        top.addWidget(x)
        self.lay.addLayout(top)
        self.grille_box = QWidget()
        self.grille_box.setObjectName("fond")
        self.grille = QGridLayout(self.grille_box)
        self.grille.setContentsMargins(0, 0, 0, 0)
        self.grille.setSpacing(8)
        self.lay.addWidget(self.grille_box)
        self.auto = QTimer(self)
        self.auto.setSingleShot(True)
        self.auto.timeout.connect(lambda: None if self.underMouse() else self.hide())

    def montrer(self):
        self.remplir()
        self.adjustSize()
        p = _pres_de_viki(self.comp, self.width(), self.sizeHint().height())
        if p is not None:
            self.move(p)
        self.show()
        self.raise_()
        self.auto.start(45_000)

    def basculer(self):
        if self.isVisible():
            self.hide()
        else:
            self.montrer()

    def _vider(self):
        while self.grille.count():
            w = self.grille.takeAt(0).widget()
            if w:
                w.deleteLater()

    def remplir(self):
        c, C = self.comp, self.C
        self._vider()
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                "novembre", "décembre"]
        d = datetime.date.today()
        nl = c.notifs_non_lues() if hasattr(c, "notifs_non_lues") else 0
        self.b_notifs.setText(f"🔔 {nl}" if nl else "🔔")
        auj = tr("Aujourd'hui")
        self.titre.setText(f"☀️ {tr(jours[d.weekday()]).capitalize()} {d.day} {tr(mois[d.month - 1])}")
        self.titre.setToolTip(auj)
        tuiles = []
        # météo
        if c.cfg.get("meteo") == "reelle" and c.cfg.get("meteo_ville"):
            t = getattr(c, "temperature", None)
            w = getattr(c, "weather", "") or ""
            tuiles.append(Tuile("📍 " + c.cfg.get("meteo_ville", ""),
                                f"{t:.0f}°" if isinstance(t, (int, float)) else "…",
                                petit=tr(METEO_TXT.get(w, w.capitalize())), action=lambda: c._update_weather(False),
                                bouton=("✏️ " + tr("Changer"), lambda: (c.choisir_ville(), self.remplir()))))
        else:
            tuiles.append(Tuile("🌤️ " + tr("Météo"), texte=tr("Choisis ta ville"),
                                petit="📍 " + tr("Clique ici"),
                                action=lambda: (c.choisir_ville(), self.remplir())))
        # rappels
        rs = sorted([r for r in c.cfg.get("rappels", []) if r.get("t", 0) > time.time()], key=lambda r: r["t"])
        if rs:
            r0 = rs[0]
            quand = datetime.datetime.fromtimestamp(r0["t"])
            tuiles.append(Tuile("⏰ " + tr("Prochain rappel"), quand.strftime("%H:%M") if quand.date() == d else
                                quand.strftime("%d/%m %H:%M"), texte=str(r0.get("txt", ""))[:60],
                                petit=(tr(f"et {len(rs) - 1} autre(s)") if len(rs) > 1 else ""),
                                action=lambda: c.say(c._reminders_text())))
        else:
            tuiles.append(Tuile("⏰ " + tr("Rappels"), texte=tr("Aucun rappel aujourd'hui."),
                                petit=tr("Clique pour en créer un"), action=c.add_reminder_dialog))
        # eau et routine (forme)
        try:
            import forme as _f
        except Exception:
            _f = None
        if _f:
            v, obj = _f.eau_du_jour(c.cfg), int(c.cfg.get("sante_eau_objectif", 8))
            tuiles.append(Tuile("💧 " + tr("Eau"), f"{v}/{obj}", petit=tr("Clique : +1 verre"),
                                action=lambda: (_f.boire(c.cfg, 1), c.save_cfg(), self.remplir())))
            quand = "soir" if datetime.datetime.now().hour >= 16 else "matin"
            r = _f.routines(c.cfg)[quand]
            fait = len(_f.fait_du_jour(c.cfg, quand))
            n = _f.serie(c.cfg, quand)
            tuiles.append(Tuile(("🌅 " if quand == "matin" else "🌙 ") + tr("Routine"), f"{fait}/{len(r['items'])}",
                                petit=(f"🔥 {n} " + tr("jours")) if n > 1 else tr("Clique pour la faire"),
                                action=lambda q=quand: (self.hide(), c.open_routine(q))))
        # PC
        items = c.res_items(getattr(c, "_res", None)) if hasattr(c, "res_items") else []
        if items:
            v, nom, detail = max(items, key=lambda t: t[0])
            tuiles.append(Tuile("📊 " + tr("Ton PC"), f"{v * 100:.0f}%", petit=detail,
                                action=getattr(c, "disks_health", None)))
        else:
            tuiles.append(Tuile("📊 " + tr("Ton PC"), texte=tr("Je mesure…"), action=getattr(c, "disks_health", None)))
        # santé du PC (pare-feu, mises à jour, disques, place libre)
        if hasattr(c, "sante_pc"):
            res = c.sante_pc(apres=lambda: self.isVisible() and self.remplir())
            if res is None:
                tuiles.append(Tuile("🛡️ " + tr("Santé du PC"), texte=tr("Je regarde…"),
                                    action=getattr(c, "security_check", None)))
            else:
                pb = [t for n, t in res if n in ("attention", "danger")]
                grave = any(n == "danger" for n, _t in res)
                t = Tuile("🛡️ " + tr("Santé du PC"), "✅" if not pb else ("🔴 " if grave else "🟠 ") + str(len(pb)),
                          texte=tr("Tout va bien") if not pb else tr("chose(s) à regarder"),
                          petit=tr("Clique : le bilan complet"), action=getattr(c, "security_check", None))
                t.setToolTip("\n".join(pb) if pb else tr("Pare-feu, mises à jour, disques et place libre : OK."))
                tuiles.append(t)
        # ma liste
        it = None
        try:
            import liste
            it = liste._last(c.cfg.get("ma_liste", []))
        except Exception:
            it = None
        if it:
            sous = (f"{tr('épisode')} {it['ep']}" if it.get("ep") else
                    (f"à {liste.fmt_time(it['temps'])}" if it.get("temps") else tr("à reprendre")))
            tuiles.append(Tuile("📺 " + tr("Ma liste"), texte=it["nom"], petit=sous, action=lambda: c.liste_open(it)))
        else:
            tuiles.append(Tuile("📺 " + tr("Ma liste"), texte=tr("Rien à reprendre."), petit=tr("Ouvrir ma liste"),
                                action=getattr(c, "open_liste", None)))
        # en cours (musique) ou l'actu
        enc = c.__dict__.get("en_cours")
        e = enc.e if enc is not None else None
        if e:
            tuiles.append(Tuile("🎵 " + tr("En cours"), texte=(e["titre"] or e["nom"])[:60], petit=e["nom"],
                                action=lambda: enc._cmd("PlayPause"), large=True))
        if _f:
            evs = _f.du_jour(c.cfg)
            tuiles.append(Tuile("🗓️ " + tr("Au programme"),
                                texte=(" · ".join((e.get("heure", "") + " " + e["txt"]).strip() for e in evs[:4])
                                       if evs else tr("Rien de prévu. Dis « ajoute sport jeudi »…")),
                                petit=tr("Clique : ma semaine"), action=lambda: (self.hide(), c.open_planning()),
                                large=True))
        tuiles.append(Tuile("📰 " + tr("L'actu"), texte=tr("Les gros titres du jour, en images."),
                            petit=tr("Clique : je te les lis"), action=lambda: (self.hide(), c.tell_news("")),
                            large=True))
        r = col = 0
        for t in tuiles:
            if t.action is None:
                t.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            if getattr(t, "large", False) or tuiles.index(t) >= 6:
                if col:
                    r, col = r + 1, 0
                self.grille.addWidget(t, r, 0, 1, 2)
                r += 1
                continue
            self.grille.addWidget(t, r, col)
            col += 1
            if col == 2:
                r, col = r + 1, 0

    def _touche(self):
        self.auto.start(45_000)


# ------------------------------------------------------------------ centre de notifications
def _il_y_a(t):
    s = max(0, time.time() - float(t or 0))
    if s < 60:
        return tr("à l'instant")
    if s < 3600:
        return tr(f"il y a {int(s // 60)} min")
    if s < 86400:
        return tr(f"il y a {int(s // 3600)} h")
    if s < 2 * 86400:
        return tr("hier")
    return datetime.datetime.fromtimestamp(t).strftime("%d/%m %H:%M")


COULEUR_ICO = {"⏰": "#ff9f0a", "⬇️": "#0a84ff", "🖥️": "#30d158", "📺": "#bf5af2", "🔔": "#ff375f", "💬": "#5e5ce6"}


class Notifs(Deplacable, QWidget):
    """Ce que Viki t'a dit : l'important (gardé) et tout ce qu'elle a dit depuis le lancement."""
    TAILLE_CLE = "notifs_taille"

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.comp = comp
        self.onglet = "important"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)
        self.setStyleSheet(CSS + CSS_EN_PLUS + """
QPushButton#seg { background: #2a2731; color: #d9d5e2; border: 1px solid #3a3644; padding: 4px 12px; font-size: 12px; }
QPushButton#seg:checked { background: #EEEDFE; color: #26215C; border-color: #EEEDFE; }
QPushButton#seg[pos="g"] { border-top-left-radius: 8px; border-bottom-left-radius: 8px; }
QPushButton#seg[pos="d"] { border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-left: none; }
QFrame#notif { background: #26232d; border: 1px solid #3a3644; border-radius: 12px; }
QFrame#notif[nonlu="true"] { border-color: #7F77DD; }
""")
        self.resize(400, 520)
        self.setMinimumSize(340, 300)
        t = comp.cfg.get(self.TAILLE_CLE)
        if isinstance(t, (list, tuple)) and len(t) == 2:
            self.resize(max(340, int(t[0])), max(300, int(t[1])))
        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        out.addWidget(cadre)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        ti = QLabel("🔔 " + tr("Ce que Viki t'a dit"))
        ti.setObjectName("titre")
        top.addWidget(ti)
        top.addStretch()
        x = QPushButton("✕")
        x.setObjectName("x")
        x.clicked.connect(self.hide)
        top.addWidget(x)
        lay.addLayout(top)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.b_imp = QPushButton(tr("Important"))
        self.b_tout = QPushButton(tr("Tout ce qu'elle a dit"))
        for b, k, pos in ((self.b_imp, "important", "g"), (self.b_tout, "tout", "d")):
            b.setObjectName("seg")
            b.setProperty("pos", pos)
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, k=k: self._onglet(k))
            seg.addWidget(b)
        seg.addStretch()
        eff = QPushButton(tr("Tout effacer"))
        eff.setObjectName("btn")
        eff.clicked.connect(self._effacer)
        seg.addWidget(eff)
        lay.addLayout(seg)
        from PyQt6.QtWidgets import QScrollArea
        self.sc = QScrollArea()
        self.sc.setWidgetResizable(True)
        self.sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sc.viewport().setAutoFillBackground(False)
        self.box = QWidget()
        self.box.setObjectName("fond")
        self.liste = QVBoxLayout(self.box)
        self.liste.setContentsMargins(0, 0, 4, 0)
        self.liste.setSpacing(6)
        self.sc.setWidget(self.box)
        lay.addWidget(self.sc, 1)
        from PyQt6.QtWidgets import QSizeGrip
        bas = QHBoxLayout()
        bas.addStretch()
        bas.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(bas)

    def montrer(self):
        self.remplir()
        if not self.isVisible():
            p = _pres_de_viki(self.comp, self.width(), self.height())
            if p is not None:
                self.move(p)
        self.show()
        self.raise_()
        for n in self.comp.cfg.get("notifs", []):        # vues : plus de pastille rouge
            n["lu"] = True
        self.comp.save_cfg()
        rb = self.comp.__dict__.get("ronds_bar")
        if rb is not None:
            rb.update()

    def _onglet(self, k):
        self.onglet = k
        self.remplir()

    def _effacer(self):
        if self.onglet == "important":
            self.comp.cfg["notifs"] = []
            self.comp.save_cfg()
        else:
            self.comp.__dict__["historique"] = []
        self.remplir()

    def remplir(self):
        self.b_imp.setChecked(self.onglet == "important")
        self.b_tout.setChecked(self.onglet == "tout")
        while self.liste.count():
            w = self.liste.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if self.onglet == "important":
            items = [(n["t"], n.get("ico", "🔔"), n["txt"], n.get("action", ""), not n.get("lu"))
                     for n in reversed(self.comp.cfg.get("notifs", []))]
        else:
            items = [(t, "💬", txt, "", False) for t, txt in reversed(self.comp.__dict__.get("historique", []))]
        if not items:
            l = QLabel(tr("Rien pour l'instant. Ce qui est important s'affichera ici : rappels, mises à jour, alertes "
                          "du PC, nouveaux épisodes…") if self.onglet == "important" else
                       tr("Elle n'a encore rien dit depuis son lancement."))
            l.setObjectName("etat")
            l.setWordWrap(True)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.liste.addWidget(l)
        for t, ico, txt, action, nonlu in items[:150]:
            f = QFrame()
            f.setObjectName("notif")
            f.setProperty("nonlu", nonlu)
            h = QHBoxLayout(f)
            h.setContentsMargins(10, 8, 10, 8)
            h.setSpacing(10)
            ic = QLabel(ico)
            ic.setFixedSize(28, 28)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet(f"background: {COULEUR_ICO.get(ico, '#5e5ce6')}; border-radius: 7px; font-size: 14px;")
            h.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            lt = QLabel(txt)
            lt.setObjectName("wTexte")
            lt.setWordWrap(True)
            lt.setProperty("no_i18n", True)
            lt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            col.addWidget(lt)
            lq = QLabel(_il_y_a(t))
            lq.setObjectName("wPetit")
            col.addWidget(lq)
            h.addLayout(col, 1)
            if action:
                lab = {"maj": "Mettre à jour", "rappels": "Voir", "pc": "Voir", "suivis": "Voir",
                       "liste": "Ouvrir", "actu": "Lire"}.get(action, "Voir")
                b = QPushButton(tr(lab))
                b.setObjectName("btn")
                b.clicked.connect(lambda _c=False, a=action: self.comp.notif_action(a))
                h.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            self.liste.addWidget(f)
        self.liste.addStretch(1)
