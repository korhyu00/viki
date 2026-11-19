"""La fenêtre « Modèles et mods » : tous les modèles d'IA installés, rangés par usage, et les mods.
Même style que la fenêtre de l'actu."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices, QCursor
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QScrollArea, QMenu,
                             QButtonGroup, QSizeGrip, QSizePolicy, QMessageBox, QFileDialog, QInputDialog,
                             QApplication)
from PyQt6.QtCore import QFile

import mods
from actu_fenetre import CSS as CSS_ACTU, FlowLayout, Deplacable, tr, demander, informer

EXT_MODELES = (".gguf", ".safetensors", ".onnx", ".ckpt", ".pt", ".bin")
CATS_MODELES = [("tout", "Tout"), ("cerveau", "🧠 Cerveau"), ("voix", "🎙️ Voix"), ("images", "🎨 Images"),
                ("musique", "🎵 Musique"), ("manga", "📖 Manga"), ("nettete", "✨ Netteté")]
ICONES = {"cerveau": ("🧠", "#3C3489"), "voix": ("🎙️", "#085041"), "images": ("🎨", "#72243E"),
          "musique": ("🎵", "#633806"), "manga": ("📖", "#444441"), "nettete": ("✨", "#0C447C")}
LANGUES_VOIX = {"fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien",
                "ru": "russe", "zh": "chinois", "ja": "japonais", "hi": "hindi", "pt": "portugais"}

CSS = CSS_ACTU + """
QPushButton#onglet { background: #2a2731; color: #d9d5e2; border: 1px solid #3a3644; border-radius: 13px;
                     padding: 4px 13px; font-size: 12px; }
QPushButton#onglet:checked { background: #EEEDFE; color: #26215C; border-color: #EEEDFE; }
#badge_ok { background: #173404; color: #C0DD97; border-radius: 7px; padding: 1px 8px; font-size: 10px; }
#badge_use { background: #26215C; color: #CECBF6; border-radius: 7px; padding: 1px 8px; font-size: 10px; }
#badge_warn { background: #412402; color: #FAC775; border-radius: 7px; padding: 1px 8px; font-size: 10px; }
#badge_off { background: #2c2c2a; color: #b4b2a9; border-radius: 7px; padding: 1px 8px; font-size: 10px; }
#badge_err { background: #501313; color: #F7C1C1; border-radius: 7px; padding: 1px 8px; font-size: 10px; }
QPushButton#petit { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; border-radius: 7px;
                    padding: 4px 10px; font-size: 11px; }
QPushButton#petit:hover { background: #343040; }
#depot { border: 2px dashed #4a4556; border-radius: 12px; color: #9b96a8; font-size: 12px; padding: 12px; }
#depot[survol="true"] { border-color: #AFA9EC; color: #CECBF6; background: #26232d; }
#ligne { background: transparent; border-radius: 10px; }
"""


def taille_txt(n):
    if not n:
        return ""
    for u, d in (("Go", 1024 ** 3), ("Mo", 1024 ** 2), ("Ko", 1024)):
        if n >= d:
            v = n / d
            return (f"{v:.1f}".replace(".", ",") if v < 10 else f"{v:.0f}") + " " + u
    return f"{n} o"


def taille_dossier(p):
    tot = 0
    try:
        for f in Path(p).rglob("*"):
            if f.is_file() and not f.is_symlink():
                tot += f.stat().st_size
    except Exception:
        pass
    return tot


# ------------------------------------------------------------------ inventaire des modèles
def inventaire(comp, ctx):
    """Tous les modèles installés -> [dict(cat, nom, tech, taille, etat, actions, ref, ...)]."""
    out = []
    cfg = comp.cfg
    # cerveau : Ollama
    ia_api = ctx.get("ia_api")
    remote = bool(ia_api) and ia_api.is_remote()
    ollama_ok = False
    try:
        with urllib.request.urlopen(ctx["ollama"] + "/api/tags", timeout=3) as r:
            tags = json.loads(r.read()).get("models", [])
        ollama_ok = True
    except Exception:
        tags = []
    aj = ctx.get("ajout_ia")
    for m in tags:
        name = m.get("name", "")
        d = m.get("details") or {}
        size = int(m.get("size") or 0)
        verd = ""
        if aj:
            try:
                verd = aj.verdict(size)[1]
            except Exception:
                verd = ""
        used = (not remote) and name == cfg.get("ollama_model")
        tech = " · ".join(x for x in ("Ollama", d.get("parameter_size"), d.get("quantization_level")) if x)
        out.append(dict(cat="cerveau", nom=name.replace(":latest", ""), tech=tech, taille=size, meta=verd,
                        etat="use" if used else "ok", ref=name, kind="ollama",
                        actions=([] if used else ["utiliser"]) + ["supprimer"]))
    if remote:
        try:
            c = ia_api.conf_from()
            out.append(dict(cat="cerveau", nom=c.get("modele", "?"), tech=f"En ligne · {c.get('nom', '')}",
                            taille=0, etat="use", ref="", kind="enligne", actions=["reglages"],
                            meta="Ses réponses viennent d'internet"))
        except Exception:
            pass
    if not tags and not remote:
        out.append(dict(cat="cerveau", nom="Ollama n'est pas lancé" if not ollama_ok else "Aucun cerveau installé",
                        tech="", taille=0, etat="warn", kind="info", ref="", actions=["installer_cerveau"],
                        meta="Sans cerveau, elle ne peut pas discuter librement."))
    # voix Piper
    voix = ctx.get("voix")
    if voix:
        try:
            liste = voix.installed_voices(ctx["voice_dirs"])
        except Exception:
            liste = []
        cur = str(getattr(comp, "voice_model", "") or "")
        for stem, path in liste:
            p = Path(path)
            lg = stem.split("_")[0]
            used = os.path.realpath(path) == os.path.realpath(cur) if cur else False
            parts = stem.split("-")
            nom = (parts[1] if len(parts) > 1 else stem).capitalize()
            mod = "mods" in p.parts and str(p).startswith(str(mods.DIR or "/nulle/part"))
            out.append(dict(cat="voix", nom=f"{nom} ({LANGUES_VOIX.get(lg, lg)})",
                            tech="Piper" + (f" · {parts[-1]}" if len(parts) > 2 else "") + (" · mod" if mod else ""),
                            taille=p.stat().st_size if p.exists() else 0, etat="use" if used else "ok",
                            ref=str(p), stem=stem, kind="piper", meta="",
                            actions=["ecouter"] + ([] if used or lg != "fr" else ["utiliser"]) +
                                    ([] if mod or used else ["supprimer"]) + ["dossier"]))
    # images et musique (moteur intégré / ComfyUI)
    at = ctx.get("atelier")
    dirs = []
    if at and getattr(at, "ENGINE_DIR", None):
        base = Path(at.ENGINE_DIR) / "models"
        dirs = [(base / "checkpoints", "Modèle"), (base / "loras", "LoRA"), (base / "diffusion_models", "Modèle"),
                (base / "unet", "Modèle")]
    for d, genre in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in (".safetensors", ".ckpt", ".pt", ".gguf") or not f.is_file():
                continue
            low = f.name.lower()
            cat = "musique" if ("ace" in low and "step" in low) or "music" in low or "audio" in low else "images"
            used = cat == "images" and genre == "Modèle" and cfg.get("atelier_modele") == f.name
            out.append(dict(cat=cat, nom=_joli(f.stem), tech=genre + " · " + f.suffix[1:], taille=f.stat().st_size,
                            etat="use" if used else "ok", ref=str(f), kind="fichier", meta="",
                            actions=([] if used or cat != "images" or genre != "Modèle" else ["utiliser_image"]) +
                                    ["supprimer", "dossier"]))
        for f in sorted(d.glob("*.part")):
            out.append(dict(cat="images", nom=_joli(f.name[:-5].rsplit(".", 1)[0]), tech="téléchargement",
                            taille=f.stat().st_size, etat="dl", ref=str(f), kind="part", meta="", actions=["dossier"]))
    if aj:
        try:
            dl = Path(aj.downloads_dir())
            for f in sorted(dl.glob("*.part")):
                if f.name[:-5].lower().endswith(EXT_MODELES):
                    out.append(dict(cat="cerveau" if ".gguf" in f.name else "images",
                                    nom=_joli(f.name[:-5].rsplit(".", 1)[0]), tech="téléchargement",
                                    taille=f.stat().st_size, etat="dl", ref=str(f), kind="part", meta="",
                                    actions=["dossier"]))
        except Exception:
            pass
    # manga
    try:
        py = comp.manga_ocr_python() if hasattr(comp, "manga_ocr_python") else None
    except Exception:
        py = None
    if py:
        root = Path(py).parent.parent
        out.append(dict(cat="manga", nom="Manga OCR", tech="Lecture du japonais dans les bulles",
                        taille=taille_dossier(root) if root.exists() else 0, etat="ok", ref=str(root), kind="dossier",
                        meta="", actions=["dossier"]))
    # netteté
    rs = Path(ctx["data_dir"]) / "tools" / "realesrgan"
    if rs.exists():
        out.append(dict(cat="nettete", nom="Real-ESRGAN", tech="Agrandir et rendre plus net",
                        taille=taille_dossier(rs), etat="ok", ref=str(rs), kind="dossier", meta="",
                        actions=["dossier"]))
    return out


def _joli(stem):
    s = stem.replace("_", " ").replace("-", " ")
    return " ".join(w if any(c.isdigit() for c in w) or w.isupper() else w.capitalize() for w in s.split())[:60]


# ------------------------------------------------------------------ une ligne
class Rangee(QFrame):
    def __init__(self, emoji, couleur, titre, badge, badge_obj, meta, boutons, image=""):
        super().__init__()
        self.setObjectName("ligne")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(52, 52)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(image) if image else QPixmap()
        if not pm.isNull():
            ic.setPixmap(pm.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation))
            ic.setStyleSheet("border-radius: 10px;")
        else:
            ic.setText(emoji)
            ic.setStyleSheet(f"background: {couleur}; border-radius: 10px; font-size: 22px;")
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        l1 = QHBoxLayout()
        l1.setSpacing(6)
        t = QLabel(titre)
        t.setObjectName("art")
        t.setProperty("no_i18n", True)
        t.setStyleSheet("font-weight: 600;")
        l1.addWidget(t)
        if badge:
            b = QLabel(badge)
            b.setObjectName(badge_obj)
            l1.addWidget(b)
        l1.addStretch()
        col.addLayout(l1)
        if meta:
            m = QLabel(meta)
            m.setObjectName("meta")
            m.setWordWrap(True)
            m.setProperty("no_i18n", True)
            col.addWidget(m)
        lay.addLayout(col, 1)
        for lab, fn in boutons:
            bt = QPushButton(lab)
            bt.setObjectName("petit")
            bt.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if isinstance(fn, QMenu):
                bt.setMenu(fn)
                bt.setStyleSheet("QPushButton::menu-indicator { width: 0; }")
            else:
                bt.clicked.connect(fn)
            lay.addWidget(bt, 0, Qt.AlignmentFlag.AlignVCenter)


# ------------------------------------------------------------------ la fenêtre
class ModelesMods(Deplacable, QWidget):
    TAILLE_CLE = "modeles_taille"

    def __init__(self, comp, ctx):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.comp, self.ctx = comp, ctx
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setStyleSheet(CSS)
        self.setWindowTitle(tr("Modèles et mods"))
        self.resize(620, 600)
        t = comp.cfg.get(self.TAILLE_CLE)
        if isinstance(t, (list, tuple)) and len(t) == 2:
            self.resize(max(440, int(t[0])), max(380, int(t[1])))
        self.setMinimumSize(440, 380)
        self.onglet, self.filtre = "modeles", "tout"
        self.items, self.gen, self._libre = [], 0, ""

        out = QVBoxLayout(self)
        out.setContentsMargins(0, 0, 0, 0)
        cadre = QFrame()
        cadre.setObjectName("cadre")
        cadre.setMouseTracking(True)
        self.setMouseTracking(True)
        out.addWidget(cadre)
        lay = QVBoxLayout(cadre)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        ti = QLabel("🧩 " + tr("Modèles et mods"))
        ti.setObjectName("titre")
        top.addWidget(ti)
        top.addSpacing(8)
        self.tab_group = QButtonGroup(self)
        self.tab_btn = {}
        for k, lab in (("modeles", "🧠 " + tr("Mes modèles")), ("mods", "🧩 " + tr("Mods"))):
            b = QPushButton(lab)
            b.setObjectName("onglet")
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, k=k: self.montrer(k))
            self.tab_group.addButton(b)
            top.addWidget(b)
            self.tab_btn[k] = b
        top.addStretch()
        self.disque = QLabel("")
        self.disque.setObjectName("date")
        top.addWidget(self.disque)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.clicked.connect(self.close)
        top.addWidget(x)
        lay.addLayout(top)

        self.chips_box = QWidget()
        self.chips_box.setObjectName("fond")
        self.chips = FlowLayout(self.chips_box)
        self.chip_group = QButtonGroup(self)
        lay.addWidget(self.chips_box)

        self.liste_box = QWidget()
        self.liste_box.setObjectName("fond")
        self.liste = QVBoxLayout(self.liste_box)
        self.liste.setContentsMargins(0, 0, 4, 0)
        self.liste.setSpacing(2)
        self.liste.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.liste_box)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().setObjectName("fond")
        lay.addWidget(self.scroll, 1)

        self.depot = QLabel()
        self.depot.setObjectName("depot")
        self.depot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.depot.setWordWrap(True)
        lay.addWidget(self.depot)

        bas = QHBoxLayout()
        self.bas_btns = []
        self.bas = bas
        bas.addStretch()
        grip = QSizeGrip(self)
        bas.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(bas)

    # ------------------------------------------------------------ général
    def montrer(self, onglet="modeles"):
        self.onglet = onglet
        self.tab_btn[onglet].setChecked(True)
        self.filtre = "tout" if onglet == "modeles" else "installes"
        try:
            self._libre = tr(f"{taille_txt(shutil.disk_usage(str(self.ctx['data_dir'])).free)} libres")
        except Exception:
            self._libre = ""
        self.disque.setText(self._libre)
        if onglet == "modeles":
            self.depot.setText("⬇️  " + tr("Glisse un modèle ici (.gguf, .safetensors, .onnx)") + "  ·  " +
                               tr("ou clique pour coller un lien Hugging Face"))
        else:
            self.depot.setText("⬆️  " + tr("Glisse un mod ici (.vikimod, .zip ou un dossier)") + "  ·  " +
                               tr("ou clique pour le choisir"))
        self._boutons_bas()
        self._chips()
        if not self.isVisible():
            self._placer()
        self.show()
        self.raise_()
        self.activateWindow()
        self.charger()

    def _placer(self):
        scr = (self.comp.screen() or QApplication.primaryScreen()).availableGeometry()
        self.resize(min(self.width(), scr.width() - 40), min(self.height(), scr.height() - 40))
        self.move(scr.center().x() - self.width() // 2, scr.center().y() - self.height() // 2)

    def _boutons_bas(self):
        for b in self.bas_btns:
            b.deleteLater()
        self.bas_btns = []
        if self.onglet == "modeles":
            spec = [("➕ " + tr("Ajouter une IA"), lambda: self.comp.open_add_ai()),
                    ("🔄 " + tr("Actualiser"), self.charger)]
        else:
            m = QMenu(self)
            m.addAction("✨  " + tr("Nouveau mod (dossier tout prêt)…"), self.creer_mod)
            m.addAction("📦  " + tr("Empaqueter un dossier en .vikimod…"), self.empaqueter)
            m.addAction("📖  " + tr("Mode d'emploi"), self.mode_emploi)
            spec = [("🛠️ " + tr("Créer mon mod"), m),
                    ("📂 " + tr("Dossier des mods"), lambda: self._ouvrir(mods.DIR)),
                    ("🔄 " + tr("Actualiser"), self.charger)]
        for i, (lab, fn) in enumerate(spec):
            b = QPushButton(lab)
            b.setObjectName("btn")
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if isinstance(fn, QMenu):
                b.setMenu(fn)
            else:
                b.clicked.connect(fn)
            self.bas.insertWidget(i, b)
            self.bas_btns.append(b)

    def _chips(self):
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                self.chip_group.removeButton(w)
                w.deleteLater()
        cats = CATS_MODELES if self.onglet == "modeles" else [("installes", "✅ Installés")] + mods.CATEGORIES
        for k, lab in cats:
            b = QPushButton(tr(lab))
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(k == self.filtre)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _c=False, k=k: self._filtrer(k))
            self.chip_group.addButton(b)
            self.chips.addWidget(b)

    def _filtrer(self, k):
        self.filtre = k
        self._afficher()

    def _vider(self):
        while self.liste.count() > 1:
            w = self.liste.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _etat(self, txt):
        self._vider()
        lab = QLabel(txt)
        lab.setObjectName("etat")
        lab.setWordWrap(True)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.liste.insertWidget(0, lab)

    def charger(self):
        self.gen += 1
        gen = self.gen
        if self.onglet == "mods":
            self.items = mods.installes()
            return self._afficher()
        self._etat("⏳ " + tr("Je fais le tour de ce qui est installé…"))
        self.comp._bg(lambda: inventaire(self.comp, self.ctx),
                      lambda r: gen == self.gen and self._recu(r))

    def _recu(self, r):
        self.items = [] if isinstance(r, Exception) else r
        self._afficher()

    def _afficher(self):
        self._vider()
        if self.onglet == "modeles":
            items = [x for x in self.items if self.filtre == "tout" or x["cat"] == self.filtre]
            if not items:
                return self._etat(tr("Rien d'installé ici pour l'instant.") + "\n" +
                                  tr("Glisse un fichier en bas, ou utilise « Ajouter une IA »."))
            ordre = [k for k, _ in CATS_MODELES]
            items.sort(key=lambda x: (ordre.index(x["cat"]), x["etat"] != "use", x["nom"].lower()))
            tot = sum(x.get("taille") or 0 for x in self.items if x.get("etat") != "dl")
            for x in items:
                self.liste.insertWidget(self.liste.count() - 1, self._rangee_modele(x))
            self.disque.setText(" · ".join(v for v in (tr(f"{taille_txt(tot)} utilisés") if tot else "",
                                                       self._libre) if v))
        else:
            cfg = self.comp.cfg
            items = [m for m in self.items if self.filtre == "installes" or m["categorie"] == self.filtre]
            if not items:
                return self._etat(tr("Aucun mod ici pour l'instant.") + "\n" +
                                  tr("Glisse un fichier .vikimod en bas, ou crée le tien avec « Créer mon mod »."))
            for m in items:
                self.liste.insertWidget(self.liste.count() - 1, self._rangee_mod(m, cfg))

    # ------------------------------------------------------------ modèles
    def _rangee_modele(self, x):
        ico, coul = ICONES.get(x["cat"], ("🧩", "#444441"))
        badge, obj = {"use": (tr("utilisé"), "badge_use"), "ok": (tr("prêt"), "badge_ok"),
                      "dl": (tr("téléchargement en cours"), "badge_warn"),
                      "warn": (tr("à installer"), "badge_warn")}.get(x["etat"], ("", ""))
        meta = " · ".join(v for v in (x.get("tech"), taille_txt(x.get("taille")), x.get("meta")) if v)
        boutons = []
        A = x.get("actions", [])
        if "utiliser" in A or "utiliser_image" in A:
            boutons.append((tr("Utiliser"), lambda: self.utiliser(x)))
        if "ecouter" in A:
            boutons.append(("▶ " + tr("Écouter"), lambda: self.ecouter(x)))
        if "reglages" in A:
            boutons.append((tr("Réglages"), self.comp.open_settings))
        if "installer_cerveau" in A:
            boutons.append((tr("Installer"), self.comp.open_models))
        plus = QMenu(self)
        if "dossier" in A or x.get("kind") in ("fichier", "piper", "part"):
            plus.addAction("📂  " + tr("Ouvrir le dossier"), lambda: self._ouvrir(Path(x["ref"]).parent
                                                                               if Path(x["ref"]).is_file()
                                                                               else x["ref"]))
        if "supprimer" in A:
            plus.addAction("🗑️  " + tr("Supprimer…"), lambda: self.supprimer(x))
        if not plus.isEmpty():
            boutons.append(("⋯", plus))
        return Rangee(ico, coul, x["nom"], badge, obj, meta, boutons)

    def utiliser(self, x):
        c = self.comp
        if x["kind"] == "ollama":
            c.cfg["ollama_model"] = x["ref"]
            if self.ctx.get("ia_api") and self.ctx["ia_api"].is_remote():
                return c.open_settings()
            c.save_cfg()
            c.say(f"D'accord, j'utilise {x['nom']} pour réfléchir maintenant.")
            if hasattr(c, "warm_ollama"):
                QTimer.singleShot(500, c.warm_ollama)
        elif x["kind"] == "piper":
            c._set_piper_voice(x["stem"])
        elif x["kind"] == "fichier":
            c.cfg["atelier_modele"] = Path(x["ref"]).name
            c.save_cfg()
            c.say(f"Pour créer des images, j'utiliserai {x['nom']}.")
        QTimer.singleShot(400, self.charger)

    def ecouter(self, x):
        c = self.comp
        lg = x["stem"].split("_")[0]
        phrase = {"fr": "Bonjour ! Voici ma voix.", "en": "Hello! This is my voice.", "es": "¡Hola! Esta es mi voz.",
                  "de": "Hallo! Das ist meine Stimme.", "it": "Ciao! Questa è la mia voce.",
                  "ru": "Привет! Это мой голос.", "zh": "你好！这是我的声音。", "ja": "こんにちは！これが私の声です。",
                  "hi": "नमस्ते! यह मेरी आवाज़ है।"}.get(lg, "Hello!")
        piper = getattr(c, "piper", None)
        if not piper:
            return c.say("Il me manque Piper pour faire parler cette voix.")

        def work():
            out = Path(tempfile.gettempdir()) / f"viki_essai_{os.getpid()}.wav"
            subprocess.run([piper, "-m", x["ref"], "-f", str(out)], input=phrase.encode(), capture_output=True,
                           timeout=60)
            return out

        def then(out):
            if isinstance(out, Exception) or not Path(out).exists():
                return c.say("Je n'ai pas réussi à faire parler cette voix.")
            try:
                subprocess.Popen(c._play_cmd(str(out)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        c._bg(work, then)

    def supprimer(self, x):
        if x["kind"] == "ollama":
            q = tr("Supprimer le cerveau « {} » ? Il faudra le retélécharger pour le réutiliser.").replace("{}", x["nom"])
        else:
            q = tr("Mettre « {} » à la corbeille ? Tu pourras le récupérer tant que la corbeille n'est pas vidée.") \
                .replace("{}", x["nom"])
        if not demander(self, "Supprimer", q, oui="Supprimer", icone="🗑️", danger=True):
            return
        c = self.comp
        if x["kind"] == "ollama":
            def work():
                req = urllib.request.Request(self.ctx["ollama"] + "/api/delete", method="DELETE",
                                             data=json.dumps({"model": x["ref"]}).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=30).read()
            c._bg(work, lambda r: (c.say("Je n'ai pas réussi à le supprimer.") if isinstance(r, Exception)
                                   else c.say(f"{x['nom']} est supprimé."), self.charger()))
            return
        paths = [Path(x["ref"])]
        if x["kind"] == "piper":
            paths.append(Path(x["ref"] + ".json"))
        ok = True
        for p in paths:
            if p.exists():
                r = QFile.moveToTrash(str(p))
                ok = (r[0] if isinstance(r, tuple) else bool(r)) and ok
        if not ok:
            c.say("Je n'ai pas réussi à tout mettre à la corbeille.")
        self.charger()

    # ------------------------------------------------------------ mods
    def _rangee_mod(self, m, cfg):
        cat = m["categorie"]
        ico = dict(mods.CATEGORIES).get(cat, "🧩 ").split(" ", 1)[0]
        on = mods.actif(cfg, m["id"])
        code_ok = not m["code"] or mods.code_autorise(cfg, m)
        err = mods.erreur(m["id"])
        if err:
            badge, obj = tr("erreur"), "badge_err"
        elif on and code_ok:
            badge, obj = tr("activé"), "badge_ok"
        elif m["code"] and not code_ok:
            badge, obj = tr("contient du code"), "badge_warn"
        else:
            badge, obj = tr("désactivé"), "badge_off"
        meta = " · ".join(v for v in (tr(dict(mods.CATEGORIES).get(cat, "").split(" ", 1)[-1]),
                                      (tr("par {}").replace("{}", str(m.get("auteur"))) if m.get("auteur") else ""),
                                      ("v" + str(m.get("version"))) if m.get("version") else "",
                                      ", ".join(m.get("contenu") or [])) if v)
        if m.get("description"):
            meta += "\n" + str(m["description"])[:160]
        actif_vrai = on and code_ok
        boutons = [((tr("Désactiver") if actif_vrai else tr("Activer") + ("…" if m["code"] and not code_ok else "")),
                    lambda: self.basculer(m))]
        plus = QMenu(self)
        plus.addAction("📂  " + tr("Ouvrir son dossier"), lambda: self._ouvrir(m["dossier"]))
        if m["code"]:
            plus.addAction("📄  " + tr("Voir son code"), lambda: self._ouvrir(Path(m["dossier"]) / "main.py"))
        if err:
            plus.addAction("⚠️  " + tr("Voir l'erreur"), lambda: informer(self, str(m.get("nom", "")), err, "⚠️"))
        plus.addSeparator()
        plus.addAction("🗑️  " + tr("Supprimer…"), lambda: self.supprimer_mod(m))
        boutons.append(("⋯", plus))
        return Rangee(ico, mods.COULEURS.get(cat, "#444441"), str(m.get("nom") or m["id"]), badge, obj, meta,
                      boutons, m.get("apercu_chemin", ""))

    def basculer(self, m):
        cfg = self.comp.cfg
        acts = cfg.setdefault("mods_actifs", {})
        code_ok = not m["code"] or mods.code_autorise(cfg, m)
        if acts.get(m["id"]) and code_ok:
            acts[m["id"]] = False
            mods.desactiver_code(m["id"])
        else:
            if m["code"] and not code_ok and not self.accord_code(m):
                return
            acts[m["id"]] = True
            if m["code"]:
                err = mods.activer_code(self.comp, m)
                if err:
                    acts[m["id"]] = False
                    informer(self, str(m.get("nom")),
                             tr("Ce mod a planté au démarrage, je l'ai désactivé.") + "\n\n" + err[-800:], "⚠️")
        self.comp.save_cfg()
        self.comp.mods_appliquer()
        self.charger()

    def accord_code(self, m):
        txt = (tr("« {} » contient du code.").replace("{}", str(m.get("nom"))) + "\n\n" +
               tr("Ce code pourra tout faire sur ton PC, comme un programme : lire tes fichiers, aller sur internet…") +
               "\n" + tr("N'active que les mods qui viennent de quelqu'un en qui tu as confiance.") + "\n\n" +
               tr("Auteur : {}").replace("{}", str(m.get("auteur") or "?")) + "\n" +
               tr("Tu peux lire son code avant (bouton ⋯ → Voir son code).") + "\n\n" +
               tr("Activer ce mod ?"))
        if not demander(self, "Mod avec du code", txt, oui="Oui, je lui fais confiance", non="Non", icone="⚠️"):
            return False
        self.comp.cfg.setdefault("mods_code_ok", {})[m["id"]] = mods.empreinte_code(m["dossier"])
        return True

    def supprimer_mod(self, m):
        if not demander(self, "Supprimer", tr("Supprimer le mod « {} » ?").replace("{}", str(m.get("nom"))),
                        oui="Supprimer", icone="🗑️", danger=True):
            return
        mods.supprimer(m["id"], self.comp.cfg)
        self.comp.save_cfg()
        self.comp.mods_appliquer()
        self.charger()

    def installer_mod(self, path):
        try:
            m, _w = mods.lire_paquet(path)
        except Exception as e:
            return informer(self, "Mod", str(e), "⚠️")
        existe = (Path(mods.DIR) / m["id"]).exists()
        txt = ((tr("Mettre à jour « {} » ?") if existe else tr("Installer « {} » ?")).replace("{}", str(m.get("nom"))) +
               "\n\n" + " · ".join(v for v in ((tr("par {}").replace("{}", str(m.get("auteur")))
                                                if m.get("auteur") else ""),
                                               ("v" + str(m.get("version"))) if m.get("version") else "") if v) +
               ("\n" + str(m.get("description"))[:200] if m.get("description") else "") +
               "\n\n" + tr("Contenu : {}").replace("{}", ", ".join(m.get("contenu") or ["?"])) +
               ("\n\n⚠️ " + tr("Il contient du code : il restera désactivé tant que tu ne l'auras pas autorisé.")
                if m["code"] else ""))
        if not demander(self, "Installer un mod" if not existe else "Mettre à jour un mod", txt,
                        oui="Mettre à jour" if existe else "Installer", non="Annuler", icone="🧩"):
            return
        self._etat("⏳ " + tr("J'installe le mod…"))
        cfg = self.comp.cfg
        self.comp._bg(lambda: mods.installer(path, cfg), self._installe)

    def _installe(self, m):
        if isinstance(m, Exception):
            informer(self, "Mod", str(m), "⚠️")
            return self.charger()
        self.comp.save_cfg()
        self.comp.mods_appliquer()
        if self.onglet != "mods":
            self.montrer("mods")
        else:
            self.charger()
        nom = m.get("nom") or m["id"]
        if m["code"]:
            self.comp.say(f"J'ai installé « {nom} ». Il contient du code : clique sur « Activer » si tu lui fais "
                          "confiance.")
        else:
            self.comp.say(f"« {nom} » est installé et activé !")

    def creer_mod(self):
        from PyQt6.QtWidgets import QLineEdit, QComboBox
        from actu_fenetre import Boite
        bx = Boite(self, tr("Nouveau mod"), tr("Je te prépare un dossier tout prêt, avec des exemples et un mode "
                                                "d'emploi. Tu n'auras plus qu'à le remplir."),
                   [(tr("Annuler"), False, "non"), (tr("Créer le dossier"), True, "oui")], "✨")
        e_nom = bx.ajouter_champ("Nom de ton mod :", QLineEdit())
        e_nom.setPlaceholderText(tr("Tenues d'hiver"))
        e_aut = bx.ajouter_champ("Ton pseudo (auteur) :", QLineEdit())
        cb = bx.ajouter_champ("Ton mod ajoute surtout :", QComboBox())
        for k, lab in mods.CATEGORIES:
            cb.addItem(tr(lab), k)
        e_nom.setFocus()
        bx.exec()
        nom, auteur, cat = e_nom.text(), e_aut.text(), cb.currentData()
        if not bx.valeur or not nom.strip():
            return
        base = Path.home() / "Documents" / "Mods Viki"
        try:
            d = mods.creer_modele(base, nom.strip(), auteur.strip(), cat)
        except Exception as e:
            return informer(self, "Mod", str(e), "⚠️")
        self._ouvrir(d)
        self.comp.say("Ton dossier de mod est prêt ! Le mode d'emploi est dedans. Quand tu as fini, glisse le "
                      "dossier dans cette fenêtre pour l'essayer.")

    def empaqueter(self):
        d = QFileDialog.getExistingDirectory(self, tr("Le dossier de ton mod"),
                                             str(Path.home() / "Documents" / "Mods Viki"))
        if not d:
            return
        try:
            out = mods.empaqueter(d)
        except Exception as e:
            return informer(self, "Mod", str(e), "⚠️")
        self._ouvrir(out.parent)
        self.comp.say(f"C'est prêt : {out.name}. Tu peux le partager, il suffit de le glisser dans Viki.")

    def mode_emploi(self):
        try:
            self.comp._show_text("📖 " + tr("Créer un mod pour Viki"), mods.MODE_EMPLOI,
                                 tr("Tout ce qu'il faut savoir, en une page."))
        except Exception:
            informer(self, "Mod", mods.MODE_EMPLOI, "📖")

    # ------------------------------------------------------------ glisser-déposer
    def _ouvrir(self, p):
        if not p:
            return
        if str(p) == str(mods.DIR):
            Path(p).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._survol(True)

    def dragLeaveEvent(self, e):
        self._survol(False)

    def _survol(self, on):
        self.depot.setProperty("survol", on)
        self.depot.style().unpolish(self.depot)
        self.depot.style().polish(self.depot)

    def dropEvent(self, e):
        self._survol(False)
        for u in e.mimeData().urls():
            p = Path(u.toLocalFile())
            if not p.exists():
                continue
            low = p.name.lower()
            if low.endswith((".vikimod", ".zip")) or (p.is_dir() and (p / "mod.json").exists()):
                self.installer_mod(p)
            elif low.endswith(EXT_MODELES) or low.endswith(".onnx.json"):
                self.comp.open_add_ai(p)
            else:
                informer(self, "Modèles et mods", tr("Je ne sais pas quoi faire de ce fichier ici.") + "\n" +
                         tr("Modèles : .gguf, .safetensors, .onnx · Mods : .vikimod, .zip ou dossier"), "🤔")
            break

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.depot.geometry().contains(
                self.depot.parentWidget().mapFrom(self, e.position().toPoint())):
            if self.onglet == "mods":
                p, _f = QFileDialog.getOpenFileName(self, tr("Choisir un mod"), str(Path.home() / "Téléchargements"),
                                                    "Mods Viki (*.vikimod *.zip)")
                if p:
                    self.installer_mod(p)
            else:
                self.comp.open_add_ai()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
