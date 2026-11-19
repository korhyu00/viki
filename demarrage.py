"""Assistant du premier lancement, en 3 écrans :
1. Bonjour : ton prénom et ta langue (devinée depuis ton système).
2. Ce que j'ai trouvé : ton système, ton bureau, ta mémoire, ta carte graphique, et les réglages que je te conseille
   (déjà cochés : un clic sur « Suivant » suffit).
3. Ton personnage, et c'est parti.
On peut le relancer quand on veut (Réglages → Accueil, ou « relance l'assistant de démarrage »).
"""
import os
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QLocale
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

CSS = """
QDialog { background: #fbf6f9; }
QLabel#titre { font-size: 22px; font-weight: bold; color: #3d2733; }
QLabel#texte { font-size: 13px; color: #3d2733; }
QLabel#petit { font-size: 12px; color: #9a8290; }
QLabel#cle { font-size: 12px; color: #9a8290; }
QLabel#val { font-size: 13px; color: #3d2733; font-weight: bold; }
QFrame#carte { background: #ffffff; border: 1px solid #efe1e8; border-radius: 14px; }
QPushButton { background: #ffffff; border: 1px solid #e7cfdb; border-radius: 10px; padding: 8px 16px;
              font-size: 13px; color: #3d2733; }
QPushButton:hover { background: #fdf0f5; }
QPushButton#suivant { background: #d0457a; color: white; border: none; font-weight: bold; padding: 9px 22px; }
QPushButton#suivant:hover { background: #b0336a; }
QPushButton#lien { background: transparent; border: none; color: #9a8290; }
QPushButton#lien:hover { color: #d0457a; }
QLineEdit, QComboBox { background: white; border: 1px solid #e7cfdb; border-radius: 8px; padding: 7px;
                       font-size: 14px; }
QCheckBox { font-size: 13px; color: #3d2733; spacing: 8px; padding: 4px; }
QListWidget { background: white; border: 1px solid #efe1e8; border-radius: 14px; padding: 6px; }
"""

ETAPES = ["Bonjour", "Ce que j'ai trouvé", "C'est parti"]
PARLE = (("fr", "Français"), ("en", "English"), ("es", "Español"), ("de", "Deutsch"), ("it", "Italiano"),
         ("pt", "Português"))


def _tr(t):
    try:
        import i18n
        return i18n.tr(t)
    except Exception:
        return t


def _lbl(text, name="texte", wrap=True):
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.TextFormat.RichText)
    return lab


def langue_systeme():
    try:
        return QLocale.system().name()[:2].lower() or "fr"
    except Exception:
        return (os.environ.get("LANG") or "fr")[:2].lower()


def bureau():
    d = os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")
    d = d.split(":")[-1] if ":" in d else d
    noms = {"KDE": "KDE Plasma", "GNOME": "GNOME", "X-Cinnamon": "Cinnamon", "XFCE": "Xfce", "MATE": "MATE",
            "LXQt": "LXQt", "Budgie": "Budgie", "Hyprland": "Hyprland", "sway": "Sway", "COSMIC": "COSMIC"}
    nom = noms.get(d, d or "?")
    s = os.environ.get("XDG_SESSION_TYPE", "")
    return f"{nom} ({'Wayland' if s == 'wayland' else 'X11' if s == 'x11' else s})" if s else nom


class Wizard(QDialog):
    """comp : le compagnon ; chars : [(dossier, nom)] ; langs : [(code, nom)] ; pc : dict de atelier.pc_info()."""

    def __init__(self, comp, chars, langs, pc=None, on_done=None):
        super().__init__(None)
        self.comp, self.cfg, self.on_done = comp, comp.cfg, on_done
        self.pc = pc or {}
        self.setWindowTitle(_tr("Bienvenue — premiers réglages"))
        self.setStyleSheet(CSS)
        self.resize(660, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 18, 26, 18)
        self.dots = QLabel()
        self.dots.setObjectName("petit")
        self.dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dots)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.b_skip = QPushButton(_tr("Passer (je règlerai plus tard)"))
        self.b_skip.setObjectName("lien")
        self.b_skip.clicked.connect(self.reject)
        self.b_prev = QPushButton(_tr("← Retour"))
        self.b_prev.clicked.connect(lambda: self.go(-1))
        self.b_next = QPushButton(_tr("Suivant →"))
        self.b_next.setObjectName("suivant")
        self.b_next.setDefault(True)
        self.b_next.clicked.connect(lambda: self.go(1))
        nav.addWidget(self.b_skip)
        nav.addStretch(1)
        nav.addWidget(self.b_prev)
        nav.addWidget(self.b_next)
        lay.addLayout(nav)
        self.name = comp.char.get("name", "Viki") if hasattr(comp, "char") else "Viki"
        self._p_bonjour(langs)
        self._p_trouve()
        self._p_fin(chars)
        self.go(0)

    # ------------------------------------------------------------- pages
    def _page(self, titre, *widgets):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl(_tr(titre), "titre"))
        for x in widgets:
            if isinstance(x, QWidget):
                v.addWidget(x)
            else:
                v.addLayout(x)
        v.addStretch(1)
        self.stack.addWidget(w)
        return w

    def _p_bonjour(self, langs):
        self.e_prenom = QLineEdit(self.cfg.get("prenom", ""))
        self.e_prenom.setPlaceholderText(_tr("Ton prénom ou ton pseudo"))
        sys_lang = langue_systeme()
        self.c_menus = QComboBox()
        for code, nom in langs:
            self.c_menus.addItem(nom, code)
        cur = self.cfg.get("langue_menus") if self.cfg.get("assistant_fait") else None
        i = self.c_menus.findData(cur or sys_lang)
        self.c_menus.setCurrentIndex(max(0, i if i >= 0 else self.c_menus.findData("fr")))
        self.c_parle = QComboBox()
        for code, nom in PARLE:
            self.c_parle.addItem(nom, code)
        cur = self.cfg.get("langue") if self.cfg.get("assistant_fait") else None
        i = self.c_parle.findData(cur or sys_lang)
        self.c_parle.setCurrentIndex(max(0, i if i >= 0 else 0))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.addWidget(_lbl("<b>" + _tr("Langue des menus") + "</b>"), 0, 0)
        g.addWidget(self.c_menus, 0, 1)
        g.addWidget(_lbl("<b>" + _tr("Langue dans laquelle je te parle") + "</b>"), 1, 0)
        g.addWidget(self.c_parle, 1, 1)
        self._page(_tr("Coucou, moi c'est {} ! 👋").format(self.name),
                   _lbl(_tr("Je vis sur ton bureau : je discute, je t'aide (fichiers, agenda, musique, code…), et "
                            "tout reste <b>sur ton PC</b>. On règle l'essentiel en trois écrans ?")),
                   _lbl("<b>" + _tr("Comment je t'appelle ?") + "</b>"), self.e_prenom, g,
                   _lbl(_tr("J'ai deviné ta langue grâce à ton système. Tout se change plus tard (clic droit sur moi)."),
                        "petit"))

    def _p_trouve(self):
        pc = self.pc
        ram, vram, gpu = pc.get("ram", 0), pc.get("vram", 0), pc.get("gpu", "")
        try:
            import paquets
            systeme = paquets.nom_systeme()
            via = paquets.NOMS.get(paquets.gestionnaire(), "")
        except Exception:
            systeme, via = "Linux", ""
        carte = QFrame()
        carte.setObjectName("carte")
        g = QGridLayout(carte)
        g.setContentsMargins(16, 12, 16, 12)
        g.setHorizontalSpacing(16)
        lignes = [("💻", "Système", systeme + (f"  ·  {via}" if via else "")),
                  ("🖥️", "Bureau", bureau()),
                  ("🧠", "Mémoire", f"{ram:g} Go" if ram else _tr("inconnue")),
                  ("🎮", "Carte graphique", (gpu or _tr("non détectée")) + (f" ({vram:g} Go)" if vram else ""))]
        for r, (ico, cle, val) in enumerate(lignes):
            g.addWidget(_lbl(ico + "  " + _tr(cle), "cle"), r, 0)
            g.addWidget(_lbl(val, "val"), r, 1)
        g.setColumnStretch(1, 1)
        # ce que je conseille, déjà coché
        if ram and ram < 8:
            cerveau = _tr("un petit cerveau (≈ 1 à 3 Go) ou une IA en ligne")
        elif ram and ram < 16:
            cerveau = _tr("un cerveau moyen (≈ 4 à 8 Go)")
        else:
            cerveau = _tr("un bon gros cerveau (8 Go et plus)")
        images = (_tr("oui, en local") if vram >= 8 else _tr("en local avec les petits modèles") if vram >= 4
                  else _tr("plutôt en ligne (gratuit)"))
        has_ai = bool(getattr(self.comp, "ollama_models", None)) or (hasattr(self.comp, "ia_remote")
                                                                    and self.comp.ia_remote())
        self.o = {}
        rows = [("voice", _tr("🔊 Qu'elle parle à voix haute"), self.cfg.get("voice", True)),
                ("chatty", _tr("💬 Qu'elle papote de temps en temps"), self.cfg.get("chatty", True) and
                 not (ram and ram < 8)),
                ("ronds_toujours", _tr("🔵 Ses raccourcis toujours visibles à côté d'elle"), True),
                ("astuce_jour", _tr("💡 Une astuce par jour pour découvrir ce qu'elle sait faire"),
                 self.cfg.get("astuce_jour", True)),
                ("ouvrir_ia", _tr("🧠 Choisir son cerveau tout de suite — conseillé ici : {}").format(cerveau),
                 not has_ai)]
        boxes = []
        for k, t, v in rows:
            cb = QCheckBox(t)
            cb.setChecked(bool(v))
            self.o[k] = cb
            boxes.append(cb)
        self.c_theme = QComboBox()
        for lab, k in ((_tr("🌌 Nuit (bleu)"), "nuit"), (_tr("🖥️ Comme mon bureau (clair / sombre)"), "systeme"),
                       (_tr("🌸 Rose"), "rose"), (_tr("🌗 Automatique (clair le jour, sombre le soir)"), "auto")):
            self.c_theme.addItem(lab, k)
        self.c_theme.setCurrentIndex(max(0, self.c_theme.findData(self.cfg.get("theme", "nuit"))))
        h = QHBoxLayout()
        h.addWidget(_lbl("<b>" + _tr("Couleurs des fenêtres") + "</b>"))
        h.addWidget(self.c_theme, 1)
        self._page("Ce que j'ai trouvé 💻", carte,
                   _lbl("<b>" + _tr("Ce que je te conseille") + "</b> — " + _tr("déjà coché pour toi") + "<br>" +
                        _tr("🎨 Images : {}").format(images), "texte"),
                   *boxes, h)

    def _p_fin(self, chars):
        self.l_chars = QListWidget()
        self.l_chars.setViewMode(QListWidget.ViewMode.IconMode)
        self.l_chars.setIconSize(QSize(96, 120))
        self.l_chars.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.l_chars.setMovement(QListWidget.Movement.Static)
        self.l_chars.setSpacing(8)
        self.l_chars.setMinimumHeight(190)
        cur = str(self.cfg.get("character_dir", ""))
        for d, nom in chars:
            it = QListWidgetItem(nom)
            it.setData(Qt.ItemDataRole.UserRole, str(d))
            try:
                import json
                first = json.loads((Path(d) / "character.json").read_text()).get("image", "")
            except Exception:
                first = ""
            for img in (first, "thumb.png", "character.png", "base.png"):
                if img and (Path(d) / img).is_file():
                    pm = QPixmap(str(Path(d) / img))
                    if not pm.isNull():
                        it.setIcon(QIcon(pm.scaled(96, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)))
                    break
            self.l_chars.addItem(it)
            if str(d) == cur or (not cur and self.l_chars.count() == 1):
                self.l_chars.setCurrentItem(it)
        if self.l_chars.currentItem() is None and self.l_chars.count():
            self.l_chars.setCurrentRow(0)
        self.cb_tips = QCheckBox(_tr("Me montrer « Trucs et astuces » (ce que je sais faire, avec des exemples)"))
        self.cb_tips.setChecked(True)
        self._page("Qui vit sur ton bureau ? 🎉",
                   _lbl(_tr("Choisis ton personnage (tu pourras en ajouter d'autres plus tard).")), self.l_chars,
                   _lbl(_tr("Pour me parler : <b>double-clic</b> sur moi. Pour les réglages : <b>clic droit</b>. "
                            "Et dis-moi simplement ce que tu veux : « mets de la musique chill », "
                            "« qu'est-ce que j'ai demain ? »…")),
                   self.cb_tips)

    # ------------------------------------------------------------- navigation
    def go(self, d):
        i = self.stack.currentIndex() + d
        if i >= self.stack.count():
            return self.finish()
        i = max(0, i)
        self.stack.setCurrentIndex(i)
        self.b_prev.setVisible(i > 0)
        self.b_next.setText(_tr("C'est parti ! 🚀" if i == self.stack.count() - 1 else "Suivant →"))
        self.dots.setText("    ".join(("● " if k == i else "○ ") + _tr(n) for k, n in enumerate(ETAPES)))

    def result(self):
        it = self.l_chars.currentItem()
        out = {"prenom": self.e_prenom.text().strip()[:40], "langue_menus": self.c_menus.currentData(),
               "langue": self.c_parle.currentData(), "character_dir": it.data(Qt.ItemDataRole.UserRole) if it else "",
               "menu_clic": self.cfg.get("menu_clic") or "court", "astuces": self.cb_tips.isChecked(),
               "theme": self.c_theme.currentData()}
        for k, cb in self.o.items():
            out[k] = cb.isChecked()
        return out

    def finish(self):
        res = self.result()
        self.accept()
        if self.on_done:
            self.on_done(res)
