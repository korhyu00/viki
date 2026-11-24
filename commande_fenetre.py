"""💻 La carte « pratique » à côté de Viki (style de la carte du tuto) : tout ce qu'elle donne et qu'on veut
réutiliser a son bouton.
  commande / code : Copier, ⭐ (carnet), Enregistrer sous… (code)
  lien : Ouvrir, Copier · adresse : Carte, Copier · suivi de colis : Suivre, Copier
  date : Me le rappeler · conversion, texte : Copier
Plus le carnet de commandes (les ⭐).

extraire(texte) -> les commandes ; elements(texte) -> tous les éléments [{"type", "texte", …}]."""
import re

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

# premiers mots qui font d'un `bout de texte` une vraie commande
MOTS = set("""sudo su flatpak pacman yay paru apt apt-get dnf zypper rpm-ostree ujust brew snap systemctl journalctl
loginctl ls cd cp mv rm rmdir mkdir touch chmod chown ln cat less head tail grep find locate which whereis echo
printf export source git pip pip3 pipx python python3 node npm npx curl wget ollama kill killall pkill ps top htop
btop df du free lsblk lsusb lspci uname whoami id groups usermod passwd nano vim vi kate tar unzip zip 7z gzip
docker podman distrobox toolbox sh bash zsh fish mount umount ip ping nmcli ss xdg-open kwriteconfig6 kwriteconfig5
qdbus qdbus6 plasma-apply-cursortheme gsettings dconf fc-cache update-grub grub-mkconfig mkinitcpio dracut reboot
shutdown poweroff ffmpeg yt-dlp mpv chsh crontab sed awk sort uniq wc xargs tee env cargo rustup go make cmake
winget choco scoop powershell reg ipconfig""".split())
# pour une ligne écrite sans `…` : seulement des mots qui ne peuvent être que des commandes
SURS = set("""sudo flatpak pacman yay paru apt apt-get dnf zypper rpm-ostree ujust systemctl journalctl git pip pip3
pipx python3 npm npx curl wget ollama chmod chown mkdir rmdir killall pkill lsblk lsusb lspci ffmpeg yt-dlp distrobox
docker podman kwriteconfig6 kwriteconfig5 gsettings qdbus qdbus6 nmcli xdg-open mkinitcpio grub-mkconfig""".split())
_PUCE = re.compile(r"^[ \t]*(?:[-*•>]|\d+[.)])?[ \t]*")
_BLOC = re.compile(r"```[ \t]*([\w+-]*)[ \t]*\n?(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]{3,200})`")
_DOLLAR = re.compile(r"^[ \t]*[$#][ \t]+(\S.{1,300})$", re.M)


def _commande(t):
    t = t.strip()
    if not t:
        return False
    mot = t.split()[0].lstrip("./")
    return mot in MOTS or t.startswith(("./", "~/")) and len(t.split()) >= 1 and "/" in mot


FORTS = {"sudo", "flatpak", "pacman", "systemctl", "yay", "paru", "apt", "apt-get", "dnf", "ujust", "rpm-ostree",
         "journalctl", "ollama", "zypper", "pipx", "distrobox", "kwriteconfig6"}
STOP = set("""dans pour puis et ou ton ta tes le la les un une de du des ça si avec sur en qui que pour te ce cela
il elle je tu nous vous après avant ensuite then in your and to the into it this that or a an with""".split())
_ARG = re.compile(r"^[-\w./:=@+~*'\"%,]+$")


def _au_milieu(texte):
    """« tape sudo pacman -Syu dans ton terminal » -> « sudo pacman -Syu »."""
    out = []
    for ligne in texte.splitlines():
        out += _au_milieu_ligne(ligne)
    return out


LIENS = set("""puis et ensuite après apres tape tapez lance lancez fais faites exécute exécutez execute écris écrivez
utilise utilisez essaie essaye commande avec : then and run type use try with""".split())
_TECH = re.compile(r"^-|[/~.=:0-9+*]")


def _au_milieu_ligne(ligne):
    out = []
    mots = ligne.replace("«", " ").replace("»", " ").replace("“", " ").replace("”", " ").split()
    i = 0
    while i < len(mots):
        m = mots[i].strip(",;")
        prec = mots[i - 1].lower().rstrip(",:") if i else ""
        debut = m in FORTS or ((m in MOTS or m.startswith("./")) and (i == 0 or prec in LIENS
                                                                      or mots[i - 1].endswith(":")))
        if debut:
            j = i + 1
            while j < len(mots) and mots[j].lower() not in STOP and _ARG.match(mots[j].rstrip(".,;!?")):
                fin = mots[j][-1] in ".,;!?" and not mots[j].endswith("..")
                j += 1
                if fin:
                    break
            cmd = " ".join(mots[i:j]).rstrip(".,;!?")
            args = [a.rstrip(".,;!?") for a in mots[i + 1:j]]
            if m in FORTS:
                bon = j - i >= 2 or m != "sudo"
            else:                                      # mot courant (cat, find…) : il faut un vrai argument technique
                bon = any(_TECH.search(a) for a in args) or m.startswith("./")
            if bon and (j - i >= 2 or m.startswith("./") or m in FORTS):
                out.append(cmd)
            i = max(j, i + 1)
        else:
            i += 1
    return out


def _lignes_nues(texte):
    out = []
    for l in texte.splitlines():
        l = _PUCE.sub("", l).strip().rstrip(".")
        if ":" in l and l.split()[0].rstrip(":") not in SURS:        # « Tape ceci : sudo … » -> après les deux-points
            l = l.rsplit(": ", 1)[-1].strip()
        mots = l.split()
        if len(mots) >= 2 and mots[0] in SURS and "`" not in l and len(l) < 300:
            out.append(l)
    return out


def extraire(texte, lignes=False):
    """-> [commande, …] sans doublons, dans l'ordre.
    lignes=True : cherche aussi les commandes écrites sans `…` (réponses de l'IA)."""
    out = []
    texte = texte or ""
    for _lang, corps in _BLOC.findall(texte):
        corps = "\n".join(re.sub(r"^[ \t]*\$[ \t]+", "", l) for l in corps.strip("\n").splitlines()).strip()
        if corps:
            out.append(corps)
    reste = _BLOC.sub(" ", texte)
    for m in _DOLLAR.findall(reste):
        if _commande(m):
            out.append(m.strip())
    for m in _INLINE.findall(reste):
        if _commande(m):
            out.append(m.strip())
    if lignes:
        nu = _INLINE.sub(" ", reste)
        trouve = _lignes_nues(nu)
        out += trouve
        out += [c for c in _au_milieu(nu) if not any(c in t for t in trouve)]
    vus, res = set(), []
    for c in out:
        if c not in vus:
            vus.add(c)
            res.append(c)
    return res[:8]


SHELLS = {"", "bash", "sh", "shell", "zsh", "fish", "console", "terminal", "cmd", "powershell", "ps1"}
EXT = {"python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts", "html": "html",
       "css": "css", "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml", "c": "c", "cpp": "cpp",
       "c++": "cpp", "java": "java", "rust": "rs", "rs": "rs", "go": "go", "php": "php", "ruby": "rb", "sql": "sql",
       "xml": "xml", "lua": "lua", "kotlin": "kt", "swift": "swift", "csharp": "cs", "cs": "cs", "ini": "ini",
       "markdown": "md", "md": "md", "dockerfile": "Dockerfile", "makefile": "Makefile", "gdscript": "gd"}
_URL = re.compile(r"https?://[^\s<>\"'`»)]+")
_ADR = re.compile(r"\b\d{1,4}\s*(?:bis|ter)?,?\s+(?:rue|avenue|boulevard|bd|place|chemin|route|allée|allee|impasse|quai|"
                  r"cours)\s+[^,.\n;:!?]{2,60}(?:,\s*\d{5}\s+[A-Za-zÀ-ÿ' -]{2,40})?", re.I)
_SUIVI = re.compile(r"\b(?:[A-Z]{2}\d{9}[A-Z]{2}|\d[A-Z]\d{11})\b")
_MOIS = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
_DATE = re.compile(r"\b(?:le\s+)?(\d{1,2}(?:er)?\s+(?:" + _MOIS + r")(?:\s+\d{4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", re.I)


def _code_bloc(lang, corps):
    """Un bloc ``` : commande (shell) ou code."""
    lang = (lang or "").lower()
    premier = (corps.split() or [""])[0].lstrip("./")
    if lang in SHELLS and (lang or premier in MOTS or corps.startswith(("./", "~/"))):
        return {"type": "commande", "texte": corps}
    return {"type": "code", "texte": corps, "ext": EXT.get(lang, "txt") if lang else "txt"}


def elements(texte, lignes=True, dates=True):
    """Tout ce qui mérite un bouton dans sa réponse, dans l'ordre et sans doublons."""
    texte = texte or ""
    out = []
    for lang, corps in _BLOC.findall(texte):
        corps = "\n".join(re.sub(r"^[ \t]*\$[ \t]+", "", l) for l in corps.strip("\n").splitlines()).strip()
        if corps:
            out.append(_code_bloc(lang, corps))
    reste = _BLOC.sub(" ", texte)
    for c in extraire(reste, lignes=lignes):
        out.append({"type": "commande", "texte": c})
    for u in _URL.findall(reste):
        u = u.rstrip(".,;:!?")
        if not any(u in e["texte"] for e in out):
            out.append({"type": "lien", "texte": u})
    for m in _ADR.finditer(reste):
        out.append({"type": "adresse", "texte": re.sub(r"\s+", " ", m.group(0)).strip()})
    for m in _SUIVI.findall(reste):
        out.append({"type": "suivi", "texte": m})
    if dates:
        try:
            import assistant_jour as _aj
            for m in _DATE.finditer(reste):
                d = _aj.date_de(m.group(1))
                if d:
                    debut = max(0, reste.rfind(".", 0, m.start()) + 1)
                    fin = reste.find(".", m.end())
                    phrase = reste[debut:fin if fin > 0 else len(reste)].strip()
                    out.append({"type": "date", "texte": m.group(1), "date": d.isoformat(), "phrase": phrase[:120]})
        except Exception:
            pass
    vus, res = set(), []
    for e in out:
        k = (e["type"], e["texte"])
        if k not in vus:
            vus.add(k)
            res.append(e)
    return res[:10]


def _mono():
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSizeF(10.5)
    return f


_BTN_BLEU = ("QPushButton { background: #0a84ff; color: white; border: none; border-radius: 10px; font-size: 10pt; "
             "font-weight: 600; padding: 0 12px; } QPushButton:hover { background: #3399ff; }")
_BTN_GRIS = ("QPushButton { background: rgba(255,255,255,26); color: #f5f5f7; border: 1px solid rgba(255,255,255,50); "
             "border-radius: 10px; font-size: 10pt; padding: 0 10px; } QPushButton:hover { background: rgba(255,255,255,48); }")
ICONES = {"commande": "💻", "code": "📄", "lien": "🔗", "adresse": "📍", "suivi": "📦", "date": "📅",
          "conversion": "🔁", "texte": "📋", "fichier": "📄", "dossier": "📁", "action": "👉"}


def _bouton(txt, bleu=False):
    b = QPushButton(txt)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedHeight(30)
    b.setStyleSheet(_BTN_BLEU if bleu else _BTN_GRIS)
    return b


class Carte(QWidget):
    """La carte : un titre, chaque élément dans sa boîte avec ses boutons, et le ✕ rond.
    comp : Viki (pour ouvrir un lien, créer un rappel, le carnet…)."""

    def __init__(self, comp=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.comp = comp
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("sans_theme", True)
        self.setMinimumWidth(380)
        self.setMaximumWidth(600)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 16, 16, 18)
        v.setSpacing(10)
        haut = QHBoxLayout()
        self.titre = QLabel()
        self.titre.setStyleSheet("color: #f5f5f7; font-size: 13pt; font-weight: 700;")
        haut.addWidget(self.titre, 1)
        bx = QPushButton("✕")
        bx.setFixedSize(28, 28)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet("QPushButton { background: rgba(255,255,255,30); color: #f5f5f7; border: none; "
                         "border-radius: 14px; font-size: 11pt; } QPushButton:hover { background: rgba(255,69,58,210); }")
        bx.clicked.connect(self.close)
        haut.addWidget(bx)
        v.addLayout(haut)
        self.aide = QLabel()
        self.aide.setWordWrap(True)
        self.aide.setStyleSheet("color: rgba(235,235,245,0.6); font-size: 9.5pt;")
        v.addWidget(self.aide)
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setFrameShape(QScrollArea.Shape.NoFrame)
        self.zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.zone.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
                                "QScrollBar:vertical { width: 8px; background: transparent; }"
                                "QScrollBar::handle:vertical { background: rgba(255,255,255,60); border-radius: 3px; }"
                                "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }")
        self.liste = QWidget()
        self.lv = QVBoxLayout(self.liste)
        self.lv.setContentsMargins(0, 0, 0, 0)
        self.lv.setSpacing(8)
        self.zone.setWidget(self.liste)
        v.addWidget(self.zone, 1)
        self.items = []

    # --- compatibilité : une simple liste de commandes
    def montrer(self, items, pres_de=None, titre=None, aide=None):
        items = [i if isinstance(i, dict) else {"type": "commande", "texte": i} for i in items]
        self.items = items
        while self.lv.count():
            it = self.lv.takeAt(0)
            wd = it.widget()
            if wd is not None:
                wd.hide()
                wd.deleteLater()
        types = {i["type"] for i in items}
        if titre is None and types == {"action"}:
            titre = tr("Tu voulais dire… ?")
        if titre:
            self.titre.setText(titre)
        elif types <= {"commande"}:
            self.titre.setText(tr("La commande") if len(items) == 1 else tr("Les commandes"))
        elif types <= {"commande", "code"}:
            self.titre.setText(tr("Le code") if len(items) == 1 else tr("Le code et les commandes"))
        else:
            self.titre.setText(tr("Sous la main"))
        if aide is not None:
            self.aide.setText(aide)
        elif types <= {"commande"}:
            self.aide.setText(tr("Copie-la, puis colle-la dans ton terminal (Ctrl+Maj+V).") if len(items) == 1 else
                              tr("Copie-les, puis colle-les dans ton terminal (Ctrl+Maj+V)."))
        else:
            self.aide.setText(tr("Tout ce qu'elle t'a donné, prêt à servir. ☆ : garder une commande dans ton carnet."))
        self.aide.setVisible(bool(self.aide.text()))
        for i in items:
            self.lv.addWidget(self._boite(i))
        self.lv.addStretch(1)
        for wd in [self] + self.findChildren(QWidget):
            wd.setProperty("sans_theme", True)
        lignes = sum(min(10, i["texte"].count("\n") + 1) for i in items)
        self.resize(500, min(620, 100 + lignes * 22 + len(items) * 54))
        if pres_de is not None:
            self._placer(pres_de)
        self.show()
        self.raise_()

    def _placer(self, r):
        """À côté d'elle (à droite si possible, sinon à gauche), dans l'écran."""
        scr = QGuiApplication.screenAt(r.center()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        x = r.right() + 10 if r.right() + 10 + self.width() <= g.right() else r.left() - 10 - self.width()
        y = max(g.top() + 10, min(r.top() + 40, g.bottom() - self.height() - 10))
        self.move(max(g.left() + 10, x), y)

    def _copier(self, b, txt):
        QGuiApplication.clipboard().setText(txt)
        b.setText(tr("Copié") + " ✓")
        QTimer.singleShot(1800, lambda: b.setText(tr("Copier")))

    def _boite(self, it):
        typ, txt = it["type"], it["texte"]
        w = QWidget()
        w.setObjectName("cmd")
        w.setStyleSheet("QWidget#cmd { background: rgba(0,0,0,90); border: 1px solid rgba(255,255,255,30); "
                        "border-radius: 12px; }")
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 9, 9, 9)
        h.setSpacing(8)
        ico = QLabel(ICONES.get(typ, "📋"))
        ico.setStyleSheet("background: transparent; border: none; font-size: 12pt;")
        h.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        montre = txt
        if typ == "date":
            montre = it.get("phrase") or txt
        if typ == "code" and txt.count("\n") > 12:
            montre = "\n".join(txt.splitlines()[:12]) + "\n…"
        t = QLabel(montre)
        if typ in ("commande", "code"):
            t.setFont(_mono())
        t.setWordWrap(True)
        t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        t.setStyleSheet("color: #e6f0ff; background: transparent; border: none;")
        h.addWidget(t, 1)
        col = QVBoxLayout()
        col.setSpacing(5)
        c = self.comp
        if typ == "action":
            ico.setText(it.get("item", {}).get("ico", "👉"))
            t.setText("« " + txt + " »")
            b = _bouton(tr("Vas-y"), True)
            b.clicked.connect(lambda: (self.close(), c.faire_exemple(it["item"])) if c else None)
            col.addWidget(b)
        elif typ == "date":
            b = _bouton(tr("Me le rappeler"), True)
            b.clicked.connect(lambda: (c.rappel_carte(it), b.setText(tr("C'est noté") + " ✓"), b.setEnabled(False))
                              if c else None)
            col.addWidget(b)
        else:
            b = _bouton(tr("Copier"), True)
            b.clicked.connect(lambda: self._copier(b, txt))
            col.addWidget(b)
        if typ == "lien" and c:
            o = _bouton(tr("Ouvrir"))
            o.clicked.connect(lambda: c.ouvrir_lien_carte(txt))
            col.addWidget(o)
        elif typ == "adresse" and c:
            o = _bouton(tr("Carte"))
            o.clicked.connect(lambda: c.ouvrir_lien_carte("https://www.openstreetmap.org/search?query="
                                                          + __import__("urllib.parse").parse.quote(txt)))
            col.addWidget(o)
        elif typ == "suivi" and c:
            o = _bouton(tr("Suivre"))
            o.clicked.connect(lambda: c.ouvrir_lien_carte("https://www.laposte.fr/outils/suivre-vos-envois?code=" + txt))
            col.addWidget(o)
        elif typ in ("fichier", "dossier") and c:
            o = _bouton(tr("Ouvrir"))
            o.clicked.connect(lambda: c.ouvrir_chemin(txt))
            col.addWidget(o)
        if typ == "code":
            e = _bouton(tr("Enregistrer…"))
            e.clicked.connect(lambda: self._enregistrer(txt, it.get("ext", "txt")))
            col.addWidget(e)
        if typ in ("commande", "code") and c:
            deja = c.carnet_a(txt)
            st = _bouton("★" if deja else "☆")
            st.setToolTip(tr("Garder dans mon carnet de commandes"))
            st.setStyleSheet(_BTN_GRIS.replace("color: #f5f5f7", "color: #ffd60a"))

            def etoile():
                st.setText("★" if c.carnet_basculer(txt) else "☆")
            st.clicked.connect(etoile)
            col.addWidget(st)
        col.addStretch(1)
        h.addLayout(col)
        return w

    def _enregistrer(self, txt, ext):
        from PyQt6.QtWidgets import QFileDialog
        import os
        nom = ext if ext in ("Dockerfile", "Makefile") else "code." + ext
        f, _ = QFileDialog.getSaveFileName(self, tr("Enregistrer le code"), os.path.join(os.path.expanduser("~"), nom))
        if f:
            try:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(txt.rstrip("\n") + "\n")
            except OSError:
                pass

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        p.fillPath(path, QColor(30, 31, 38, 246))
        p.setPen(QColor(255, 255, 255, 26))
        p.drawPath(path)
        p.end()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, e):                            # on la déplace en la tirant
        if self.windowHandle() is not None and e.button() == Qt.MouseButton.LeftButton:
            self.windowHandle().startSystemMove()


Commandes = Carte


class Carnet(QWidget):
    """📒 Mon carnet de commandes : les ⭐, avec une recherche, Copier et 🗑."""

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setWindowTitle(tr("📒 Mon carnet de commandes"))
        self.resize(640, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 8, 22, 18)
        v.setSpacing(10)
        t = QLabel(tr("📒 Mon carnet de commandes"))
        t.setStyleSheet("font-size: 17pt; font-weight: 700;")
        v.addWidget(t)
        a = QLabel(tr("Les commandes que tu as gardées avec ☆ dans la carte de Viki. Tu peux aussi en ajouter une."))
        a.setWordWrap(True)
        a.setStyleSheet("color: palette(placeholder-text);")
        v.addWidget(a)
        from PyQt6.QtWidgets import QLineEdit
        haut = QHBoxLayout()
        self.cherche = QLineEdit()
        self.cherche.setPlaceholderText(tr("🔎 Chercher…"))
        self.cherche.textChanged.connect(self.remplir)
        haut.addWidget(self.cherche, 1)
        self.nouv = QLineEdit()
        self.nouv.setPlaceholderText(tr("Nouvelle commande…"))
        self.nouv.returnPressed.connect(self._ajouter)
        haut.addWidget(self.nouv, 1)
        b = QPushButton(tr("Ajouter"))
        b.clicked.connect(self._ajouter)
        haut.addWidget(b)
        v.addLayout(haut)
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setFrameShape(QScrollArea.Shape.NoFrame)
        self.liste = QWidget()
        self.lv = QVBoxLayout(self.liste)
        self.lv.setContentsMargins(0, 0, 0, 0)
        self.lv.setSpacing(6)
        self.zone.setWidget(self.liste)
        v.addWidget(self.zone, 1)
        self.remplir()

    def _ajouter(self):
        t = self.nouv.text().strip()
        if t:
            if not self.comp.carnet_a(t):
                self.comp.carnet_basculer(t)
            self.nouv.clear()
            self.remplir()

    def remplir(self):
        while self.lv.count():
            it = self.lv.takeAt(0)
            wd = it.widget()
            if wd is not None:
                wd.hide()
                wd.deleteLater()
        q = self.cherche.text().strip().lower()
        items = [x for x in reversed(self.comp.cfg.get("carnet_cmd", [])) if not q or q in x["c"].lower()]
        if not items:
            vide = QLabel(tr("Rien ici pour l'instant. Clique sur ☆ à côté d'une commande dans la carte de Viki."))
            vide.setWordWrap(True)
            vide.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lv.addWidget(vide)
        for x in items:
            w = QWidget()
            w.setObjectName("ligneCarnet")
            w.setStyleSheet("QWidget#ligneCarnet { border: 1px solid rgba(128,128,128,70); border-radius: 12px; }")
            h = QHBoxLayout(w)
            h.setContentsMargins(12, 8, 8, 8)
            l = QLabel(x["c"])
            l.setFont(_mono())
            l.setWordWrap(True)
            l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            h.addWidget(l, 1)
            b = QPushButton(tr("Copier"))
            b.setDefault(True)

            def cp(_=False, bb=b, c=x["c"]):
                QGuiApplication.clipboard().setText(c)
                bb.setText(tr("Copié") + " ✓")
                QTimer.singleShot(1500, lambda: bb.setText(tr("Copier")))
            b.clicked.connect(cp)
            h.addWidget(b)
            d = QPushButton("🗑")
            d.setToolTip(tr("Retirer du carnet"))
            d.setFixedSize(40, 28)
            d.clicked.connect(lambda _=False, c=x["c"]: (self.comp.carnet_basculer(c), self.remplir()))
            h.addWidget(d)
            self.lv.addWidget(w)
        self.lv.addStretch(1)


_ = QFont
