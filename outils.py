"""Outils du compagnon : nettoyage du système, rangement de dossiers, idées d'activités.

Règle d'or : rien n'est supprimé ni déplacé sans que l'utilisateur ait vu la liste et cliqué.
Les rangements s'annulent ; les commandes qui demandent le mot de passe administrateur
sont seulement affichées (à copier dans un terminal), jamais lancées en cachette.
"""
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

IS_WIN = sys.platform.startswith("win")
HOME = Path.home()

STYLE = """
QDialog { background: #fbf6f9; }
QLabel#titre { font-size: 18px; font-weight: bold; color: #3d2733; }
QLabel#aide { font-size: 12px; color: #8d7482; }
QFrame#carte { background: white; border: 1px solid #f1dfe8; border-radius: 12px; }
QPushButton { padding: 6px 14px; border-radius: 9px; border: 1px solid #e3c3d2; background: white; }
QPushButton:hover { background: #fdf0f5; }
QPushButton#principal { background: #d0457a; color: white; border: none; font-weight: bold; }
QPushButton#principal:disabled { background: #e6a9c0; }
QCheckBox { font-size: 13px; color: #3d2733; }
"""


def human(n):
    for u in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or u == "To":
            return f"{n:.0f} {u}" if u in ("o", "Ko") else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024


def dir_size(p, limit_s=8.0):
    """Taille d'un dossier (on s'arrête au bout de quelques secondes pour ne pas bloquer)."""
    total, t0 = 0, time.monotonic()
    try:
        for root, dirs, files in os.walk(p, onerror=lambda e: None):
            for f in files:
                try:
                    st = os.lstat(os.path.join(root, f))
                    total += st.st_size
                except OSError:
                    pass
            if time.monotonic() - t0 > limit_s:
                break
    except Exception:
        pass
    return total


def _rm_content(folder, older_than_days=0, keep=()):
    """Vide un dossier (sans le supprimer lui-même). Renvoie l'espace libéré."""
    freed = 0
    limit = time.time() - older_than_days * 86400
    folder = Path(folder)
    if not folder.is_dir():
        return 0
    for p in list(folder.iterdir()):
        if p.name in keep:
            continue
        try:
            if older_than_days and p.lstat().st_mtime > limit:
                continue
            if p.is_dir() and not p.is_symlink():
                s = dir_size(p, 30)
                shutil.rmtree(p, ignore_errors=True)
                freed += s if not p.exists() else 0
            else:
                s = p.lstat().st_size
                p.unlink()
                freed += s
        except Exception:
            pass
    return freed


# ================================================================ nettoyage
# Dossiers du cache qu'on ne touche pas : modèles d'IA (re-téléchargement de plusieurs Go),
# le compagnon lui-même, et ce qui sert aux sessions ouvertes.
CACHE_KEEP = {"huggingface", "compagnon", "torch", "whisper", "ollama", "pip-voix", "ms-playwright",
              "kioskmode", "ksycoca6_fr_FR", "plasmashell", "kwin", "sessions"}


def scan_cleanup():
    """Liste de ce qu'on peut nettoyer : dict(id, nom, aide, taille, coche, action, admin)."""
    items = []
    if IS_WIN:
        tmp = Path(os.environ.get("TEMP", HOME / "AppData/Local/Temp"))
        items.append({"id": "temp", "nom": "Fichiers temporaires", "taille": dir_size(tmp),
                      "aide": f"{tmp} — plus vieux que 2 jours.", "coche": True,
                      "action": lambda: _rm_content(tmp, 2)})
        items.append({"id": "corbeille", "nom": "Corbeille", "taille": -1, "coche": False,
                      "aide": "Vide la corbeille de Windows (définitif).",
                      "action": lambda: (subprocess.run(["powershell", "-NoProfile", "-Command",
                                                         "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                                                        capture_output=True, timeout=120), 0)[1]})
        local = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local"))
        thumbs = local / "Microsoft/Windows/Explorer"
        items.append({"id": "miniatures", "nom": "Miniatures des images", "coche": False,
                      "taille": sum(f.stat().st_size for f in thumbs.glob("thumbcache_*.db")) if thumbs.is_dir() else 0,
                      "aide": "Windows les recrée tout seul (certaines sont en cours d'utilisation et restent).",
                      "action": lambda: sum(_try_unlink(f) for f in thumbs.glob("thumbcache_*.db"))})
        items.append({"id": "cleanmgr", "nom": "Nettoyage de disque de Windows", "taille": -1, "coche": False,
                      "aide": "Ouvre l'outil de Windows (mises à jour, journaux…).",
                      "action": lambda: (subprocess.Popen(["cleanmgr"]), 0)[1]})
        return items

    trash = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "Trash"
    items.append({"id": "corbeille", "nom": "Corbeille", "taille": dir_size(trash), "coche": False,
                  "aide": "Supprime définitivement ce qui est dans la corbeille.",
                  "action": lambda: _rm_content(trash / "files") + _rm_content(trash / "info")
                  + _rm_content(trash / "expunged")})
    cache = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache"))
    thumbs = cache / "thumbnails"
    items.append({"id": "miniatures", "nom": "Miniatures des images", "taille": dir_size(thumbs), "coche": True,
                  "aide": "Aperçus des photos et vidéos ; ils se recréent tout seuls.",
                  "action": lambda: _rm_content(thumbs)})
    keep = CACHE_KEEP | {"thumbnails"}
    cache_size = 0
    if cache.is_dir():
        for p in cache.iterdir():
            if p.name not in keep:
                cache_size += dir_size(p, 2) if p.is_dir() else p.stat().st_size
    items.append({"id": "cache", "nom": "Cache des applications", "taille": cache_size, "coche": True,
                  "aide": "Navigateurs, applis… (pas les modèles d'IA). Ferme ton navigateur avant.",
                  "action": lambda: _rm_content(cache, 0, keep)})
    tmp_user = 0
    for p in Path("/tmp").glob("*"):
        try:
            if p.owner() == HOME.name and time.time() - p.lstat().st_mtime > 7 * 86400:
                tmp_user += dir_size(p, 1) if p.is_dir() else p.lstat().st_size
        except Exception:
            pass
    items.append({"id": "tmp", "nom": "Fichiers temporaires (plus de 7 jours)", "taille": tmp_user, "coche": True,
                  "aide": "Dans /tmp, seulement les tiens.",
                  "action": lambda: _clean_tmp_user()})
    if shutil.which("flatpak"):
        items.append({"id": "flatpak", "nom": "Bibliothèques Flatpak inutilisées", "taille": -1, "coche": False,
                      "aide": "flatpak uninstall --unused (peut demander ton mot de passe).",
                      "action": lambda: (subprocess.run(["flatpak", "uninstall", "--unused", "-y"],
                                                        capture_output=True, timeout=600), 0)[1]})
    # commandes administrateur : seulement montrées
    admin = []
    if shutil.which("pacman"):
        if shutil.which("paccache"):
            admin.append(("Vieux paquets téléchargés", "sudo paccache -rk1"))
        else:
            admin.append(("Vieux paquets téléchargés", "sudo pacman -Sc"))
        admin.append(("Paquets orphelins (plus utilisés)", "sudo pacman -Rns $(pacman -Qdtq)"))
    elif shutil.which("apt"):
        admin.append(("Paquets inutiles et cache", "sudo apt autoremove --purge && sudo apt clean"))
    elif shutil.which("dnf"):
        admin.append(("Paquets inutiles et cache", "sudo dnf autoremove && sudo dnf clean all"))
    elif shutil.which("zypper"):
        admin.append(("Cache des paquets", "sudo zypper clean --all"))
    elif shutil.which("xbps-remove"):
        admin.append(("Paquets orphelins et cache", "sudo xbps-remove -Oo"))
    elif shutil.which("apk"):
        admin.append(("Cache des paquets", "sudo apk cache clean"))
    elif shutil.which("eopkg"):
        admin.append(("Paquets orphelins et cache", "sudo eopkg remove-orphans && sudo eopkg delete-cache"))
    elif shutil.which("zypper"):
        admin.append(("Cache des paquets", "sudo zypper clean -a"))
    if shutil.which("journalctl"):
        admin.append(("Journaux système de plus de 2 semaines", "sudo journalctl --vacuum-time=2weeks"))
    for nom, cmd in admin:
        items.append({"id": "admin:" + nom, "nom": nom, "taille": -1, "coche": False, "admin": cmd,
                      "aide": "Demande le mot de passe administrateur : copie la commande dans un terminal."})
    return items


def _try_unlink(f):
    try:
        s = f.stat().st_size
        f.unlink()
        return s
    except Exception:
        return 0


def _clean_tmp_user():
    freed = 0
    for p in Path("/tmp").glob("*"):
        try:
            if p.owner() != HOME.name or time.time() - p.lstat().st_mtime < 7 * 86400:
                continue
            if p.name.startswith((".X", "ssh-", "systemd-", "pulse-", "tmux-", "kde", "xauth", "sddm")):
                continue
            if p.is_dir() and not p.is_symlink():
                s = dir_size(p, 5)
                shutil.rmtree(p, ignore_errors=True)
                freed += 0 if p.exists() else s
            elif p.is_file():
                s = p.lstat().st_size
                p.unlink()
                freed += s
        except Exception:
            pass
    return freed


class _Sig(QObject):
    done = pyqtSignal(object, object)


def _run_bg(fn, then, sig):
    import threading
    threading.Thread(target=lambda: sig.done.emit(then, fn()), daemon=True).start()


class CleanDialog(QDialog):
    """Fenêtre « Nettoyer le PC » : on voit tout, on coche, on confirme."""

    def __init__(self, comp):
        super().__init__(None)
        self.comp = comp
        self.setWindowTitle("Nettoyer le PC")
        self.setStyleSheet(STYLE)
        self.resize(620, 560)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, res: fn(res))
        v = QVBoxLayout(self)
        t = QLabel("🧹  Nettoyer le PC")
        t.setObjectName("titre")
        v.addWidget(t)
        self.info = QLabel("Je regarde ce qui prend de la place…")
        self.info.setObjectName("aide")
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.addStretch(1)
        self.area.setWidget(self.inner)
        v.addWidget(self.area, 1)
        row = QHBoxLayout()
        self.go = QPushButton("Nettoyer la sélection")
        self.go.setObjectName("principal")
        self.go.setEnabled(False)
        self.go.clicked.connect(self.clean)
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        row.addStretch(1)
        row.addWidget(close)
        row.addWidget(self.go)
        v.addLayout(row)
        self.checks = []
        _run_bg(scan_cleanup, self.show_items, self.sig)

    def show_items(self, items):
        self.items = items
        total = 0
        for it in items:
            card = QFrame()
            card.setObjectName("carte")
            cl = QVBoxLayout(card)
            if it.get("admin"):
                lab = QLabel("🔒  " + it["nom"])
                lab.setStyleSheet("font-size: 13px; color: #3d2733;")
                cl.addWidget(lab)
                r = QHBoxLayout()
                cmd = QLineEdit(it["admin"])
                cmd.setReadOnly(True)
                cp = QPushButton("Copier")
                cp.clicked.connect(lambda _=False, c=it["admin"]: QApplication.clipboard().setText(c))
                r.addWidget(cmd, 1)
                r.addWidget(cp)
                cl.addLayout(r)
            else:
                taille = "" if it["taille"] < 0 else f"  —  {human(it['taille'])}"
                cb = QCheckBox(it["nom"] + taille)
                cb.setChecked(it["coche"] and it["taille"] != 0)
                cb.setEnabled(it["taille"] != 0)
                self.checks.append((cb, it))
                cl.addWidget(cb)
                if it["taille"] > 0 and it["coche"]:
                    total += it["taille"]
            a = QLabel(it["aide"])
            a.setObjectName("aide")
            a.setWordWrap(True)
            cl.addWidget(a)
            self.lay.insertWidget(self.lay.count() - 1, card)
        self.info.setText(f"Coche ce que tu veux nettoyer. Environ {human(total)} à récupérer avec la sélection "
                          "de base. Tes documents, photos et réglages ne sont jamais touchés.")
        self.go.setEnabled(True)

    def clean(self):
        chosen = [it for cb, it in self.checks if cb.isChecked()]
        if not chosen:
            return
        noms = "\n".join("• " + it["nom"] for it in chosen)
        if QMessageBox.question(self, "Nettoyer", f"Je nettoie :\n{noms}\n\nC'est définitif. On y va ?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.go.setEnabled(False)
        self.info.setText("Nettoyage en cours…")

        def work():
            freed = 0
            for it in chosen:
                try:
                    freed += it["action"]() or 0
                except Exception as e:
                    print("Nettoyage :", it["nom"], e, file=sys.stderr)
            return freed

        def then(freed):
            self.info.setText(f"✅ Fini ! {human(freed)} libérés." if freed else "✅ Fini !")
            self.comp.cleanup_done(freed)
        _run_bg(work, then, self.sig)


# ================================================================ rangement de dossiers
TYPES = {"Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".heic", ".bmp", ".avif", ".tiff", ".raw",
                    ".cr2", ".nef", ".kra", ".xcf", ".psd"},
         "Vidéos": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"},
         "Musique": {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus", ".aac", ".wma", ".mid"},
         "Documents": {".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf", ".epub", ".pages"},
         "Tableurs": {".xls", ".xlsx", ".ods", ".csv", ".numbers"},
         "Présentations": {".ppt", ".pptx", ".odp", ".key"},
         "Archives": {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".xz", ".zst", ".bz2"},
         "Programmes": {".appimage", ".deb", ".rpm", ".exe", ".msi", ".flatpakref", ".run", ".jar", ".apk"},
         "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".c", ".cpp", ".h", ".rs", ".go", ".java",
                  ".sh", ".lua", ".gd", ".yml", ".yaml", ".toml", ".ipynb"},
         "Images disque": {".iso", ".img"},
         "Polices": {".ttf", ".otf", ".woff", ".woff2"},
         "3D": {".blend", ".obj", ".fbx", ".stl", ".glb", ".gltf", ".3mf"},
         "Torrents": {".torrent"}}
PARTIAL = {".part", ".crdownload", ".download", ".tmp", ".partial", ".!qb"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
MODES = [("Par type (Images, Documents, Vidéos…)", "type"),
         ("Par date (2026, 2026-11 novembre…)", "date"),
         ("Par type, puis par année", "type_annee")]
# Dossiers qu'on refuse de ranger : le système et la racine du dossier perso
INTERDITS = [Path("/"), Path("/usr"), Path("/etc"), Path("/bin"), Path("/boot"), Path("/var"), Path("/opt"),
             HOME, HOME / ".config", HOME / ".local", Path("C:/"), Path("C:/Windows")]


def _kind(p):
    ext = p.suffix.lower()
    if p.name.lower().endswith((".tar.gz", ".tar.xz", ".tar.zst", ".tar.bz2")):
        ext = ".tar"
    return next((d for d, e in TYPES.items() if ext in e), "Autres")


def folder_allowed(folder):
    f = Path(folder).resolve()
    if any(f == i.resolve() for i in INTERDITS if i.exists()):
        return False
    return not str(f).startswith(("/usr/", "/etc/", "/bin/", "/boot/", "/proc/", "/sys/", "/dev/"))


def plan_folder(folder, mode="type"):
    """Liste (source, destination). Seulement les fichiers posés directement dans le dossier."""
    folder = Path(folder)
    plan, now = [], time.time()
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.is_symlink() or p.name.startswith(".") or p.suffix.lower() in PARTIAL:
            continue
        if p.name.lower() in ("desktop.ini", "thumbs.db") or p.suffix.lower() == ".desktop":
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if now - mt < 120:                       # en cours d'écriture ou de téléchargement
            continue
        d = datetime.date.fromtimestamp(mt)
        if mode == "date":
            sub = Path(str(d.year)) / f"{d.year}-{d.month:02d} {MOIS[d.month - 1]}"
        elif mode == "type_annee":
            sub = Path(_kind(p)) / str(d.year)
        else:
            sub = Path(_kind(p))
        plan.append((str(p), str(folder / sub / p.name)))
    return plan


def plan_summary(plan):
    count = {}
    for _, dst in plan:
        k = Path(dst).parent.name
        count[k] = count.get(k, 0) + 1
    return ", ".join(f"{n} dans {k}" for k, n in sorted(count.items(), key=lambda kv: -kv[1])[:8])


def apply_plan(plan, log_file):
    done = []
    for src, dst in plan:
        d = Path(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        k = 2
        while d.exists():
            d = d.with_name(f"{Path(dst).stem} ({k}){Path(dst).suffix}")
            k += 1
        try:
            shutil.move(src, d)
            done.append((src, str(d)))
        except Exception:
            pass
    try:
        Path(log_file).write_text(json.dumps({"t": time.time(), "moves": done}, ensure_ascii=False, indent=1))
    except Exception:
        pass
    return done


def find_duplicates(folder, max_files=4000):
    """Doublons exacts (même taille puis même contenu) : liste de groupes de chemins."""
    import hashlib
    by_size = {}
    n = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in files:
            p = Path(root) / f
            try:
                s = p.stat().st_size
            except OSError:
                continue
            if s > 1024:
                by_size.setdefault(s, []).append(p)
            n += 1
            if n > max_files:
                break
    groups = []
    for s, ps in by_size.items():
        if len(ps) < 2:
            continue
        by_hash = {}
        for p in ps:
            try:
                h = hashlib.blake2b(p.read_bytes() if s < 64 << 20 else p.open("rb").read(64 << 20),
                                    digest_size=16).hexdigest()
                by_hash.setdefault(h, []).append(str(p))
            except Exception:
                pass
        groups += [g for g in by_hash.values() if len(g) > 1]
    return groups


class TidyDialog(QDialog):
    """Réorganiser un dossier au choix, avec aperçu et annulation."""

    def __init__(self, comp, folder=None, log_file=None):
        super().__init__(None)
        self.comp, self.log_file = comp, log_file
        self.setWindowTitle("Réorganiser un dossier")
        self.setStyleSheet(STYLE)
        self.resize(640, 560)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, res: fn(res))
        v = QVBoxLayout(self)
        t = QLabel("🗂️  Réorganiser un dossier")
        t.setObjectName("titre")
        v.addWidget(t)
        a = QLabel("Je range les fichiers posés en vrac dans des sous-dossiers. Rien n'est supprimé, "
                   "et tu peux tout remettre comme avant.")
        a.setObjectName("aide")
        a.setWordWrap(True)
        v.addWidget(a)
        r = QHBoxLayout()
        self.path = QLineEdit(str(folder or ""))
        self.path.setPlaceholderText("Choisis un dossier…")
        b = QPushButton("Choisir…")
        b.clicked.connect(self.choose)
        r.addWidget(self.path, 1)
        r.addWidget(b)
        v.addLayout(r)
        quick = QHBoxLayout()
        for lab, sub in (("Téléchargements", "DOWNLOAD"), ("Bureau", "DESKTOP"), ("Documents", "DOCUMENTS"),
                         ("Images", "PICTURES")):
            q = QPushButton(lab)
            q.clicked.connect(lambda _=False, s=sub: self.set_folder(user_dir(s)))
            quick.addWidget(q)
        quick.addStretch(1)
        v.addLayout(quick)
        self.mode = QComboBox()
        for lab, m in MODES:
            self.mode.addItem(lab, m)
        self.mode.currentIndexChanged.connect(self.preview)
        v.addWidget(self.mode)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.dup = QPushButton("Chercher les doublons")
        self.dup.clicked.connect(self.duplicates)
        self.undo = QPushButton("Annuler le dernier rangement")
        self.undo.clicked.connect(self.do_undo)
        self.undo.setVisible(bool(log_file and Path(log_file).exists()))
        self.go = QPushButton("Ranger")
        self.go.setObjectName("principal")
        self.go.setEnabled(False)
        self.go.clicked.connect(self.apply)
        row.addWidget(self.dup)
        row.addWidget(self.undo)
        row.addStretch(1)
        row.addWidget(self.go)
        v.addLayout(row)
        self.plan = []
        if folder:
            self.preview()

    def choose(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier à ranger", self.path.text() or str(HOME))
        if d:
            self.set_folder(d)

    def set_folder(self, d):
        if d:
            self.path.setText(str(d))
            self.preview()

    def preview(self):
        self.list.clear()
        self.plan = []
        f = Path(self.path.text().strip()).expanduser()
        if not f.is_dir():
            self.summary.setText("Choisis un dossier.")
            self.go.setEnabled(False)
            return
        if not folder_allowed(f):
            self.summary.setText("⚠️ Je ne range pas ce dossier-là (dossier système ou racine de ton dossier "
                                 "personnel) : choisis un sous-dossier, par exemple Téléchargements.")
            self.go.setEnabled(False)
            return
        self.plan = plan_folder(f, self.mode.currentData())
        if not self.plan:
            self.summary.setText("✨ Rien à ranger ici : pas de fichiers en vrac.")
        else:
            self.summary.setText(f"<b>{len(self.plan)} fichiers</b> à ranger : {plan_summary(self.plan)}.")
            for s, d in self.plan[:500]:
                self.list.addItem(f"{Path(s).name}   →   {Path(d).parent.relative_to(f)}/")
        self.go.setEnabled(bool(self.plan))

    def apply(self):
        if not self.plan:
            return
        done = apply_plan(self.plan, self.log_file)
        self.undo.setVisible(True)
        self.comp.tidy_done(len(done))
        self.preview()

    def do_undo(self):
        n = undo_plan(self.log_file)
        self.undo.setVisible(False)
        self.comp.say(f"J'ai remis {n} fichier{'s' if n > 1 else ''} à leur place." if n
                      else "Il n'y a rien à annuler.")
        self.preview()

    def duplicates(self):
        f = Path(self.path.text().strip()).expanduser()
        if not f.is_dir():
            return
        self.summary.setText("Je compare les fichiers…")
        self.dup.setEnabled(False)

        def then(groups):
            self.dup.setEnabled(True)
            self.list.clear()
            if not groups:
                self.summary.setText("Aucun doublon trouvé. 👍")
                return
            perdu = sum(Path(g[0]).stat().st_size * (len(g) - 1) for g in groups if Path(g[0]).exists())
            self.summary.setText(f"{len(groups)} fichiers en double ({human(perdu)} en trop). Je ne supprime "
                                 "rien moi-même : double-clique pour ouvrir le dossier et choisis.")
            for g in groups[:200]:
                self.list.addItem("📄 " + Path(g[0]).name + "  ×" + str(len(g)))
                for p in g:
                    self.list.addItem("      " + p)
            try:
                self.list.itemDoubleClicked.disconnect()
            except TypeError:
                pass
            self.list.itemDoubleClicked.connect(
                lambda it: it.text().startswith("      ") and subprocess.Popen(
                    ["xdg-open", str(Path(it.text().strip()).parent)], start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _run_bg(lambda: find_duplicates(f), then, self.sig)


def undo_plan(log_file):
    try:
        data = json.loads(Path(log_file).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return 0
    n = 0
    for src, dst in reversed(data.get("moves", [])):
        if Path(dst).exists() and not Path(src).exists():
            try:
                shutil.move(dst, src)
                n += 1
            except Exception:
                pass
    parents = sorted({Path(d).parent for _, d in data.get("moves", [])}, key=lambda p: -len(p.parts))
    for p in parents:
        for q in (p, p.parent):
            try:
                q.rmdir()                          # seulement s'il est vide
            except OSError:
                pass
    Path(log_file).unlink(missing_ok=True)
    return n


def user_dir(kind):
    if IS_WIN:
        names = {"DOWNLOAD": "Downloads", "DESKTOP": "Desktop", "DOCUMENTS": "Documents", "PICTURES": "Pictures"}
        return HOME / names.get(kind, "")
    exe = shutil.which("xdg-user-dir")
    if exe:
        try:
            p = subprocess.run([exe, kind], capture_output=True, text=True, timeout=3).stdout.strip()
            if p and Path(p).is_dir() and Path(p) != HOME:
                return Path(p)
        except Exception:
            pass
    fr = {"DOWNLOAD": ("Téléchargements", "Downloads"), "DESKTOP": ("Bureau", "Desktop"),
          "DOCUMENTS": ("Documents",), "PICTURES": ("Images", "Pictures")}
    for n in fr.get(kind, ()):
        if (HOME / n).is_dir():
            return HOME / n
    return None


# ================================================================ idées d'activités
# (texte, action possible, moments, conditions) ; action = clé comprise par le compagnon
ACTIVITES = [
    ("On fait une partie de morpion ?", "jeu:morpion", "*", ""),
    ("Je te pose un quiz, pour voir ?", "jeu:quiz", "*", ""),
    ("Une petite devinette pour te réveiller les neurones ?", "jeu:devinette", "*", ""),
    ("Je te raconte une histoire ?", "histoire", "soir,nuit", ""),
    ("Un pomodoro de 25 minutes pour avancer sur un truc, et je te fais signe à la fin ?", "pomodoro",
     "matin,aprem", ""),
    ("Petite pause étirements : lève-toi, bras en l'air, et on s'étire ensemble !", "etirement", "*", ""),
    ("Va boire un grand verre d'eau, je t'attends !", "", "*", ""),
    ("Il fait beau : une petite marche de 15 minutes dehors, ça te dit ?", "", "matin,aprem", "beau"),
    ("Il pleut… parfait pour un film ou une série sous un plaid.", "", "aprem,soir", "pluie"),
    ("Mets ta musique préférée et on danse un peu ?", "danse", "matin,aprem,soir", ""),
    ("Écris trois choses qui t'ont fait plaisir aujourd'hui dans ton journal.", "journal", "soir", ""),
    ("On range un dossier ensemble ? Ton bureau te dira merci.", "ranger", "matin,aprem", ""),
    ("Dessine quelque chose en 10 minutes, même tout simple. Je veux voir !", "minuteur:10", "aprem,soir", ""),
    ("Apprends trois mots d'anglais avec moi ?", "anglais", "*", ""),
    ("Appelle ou écris à quelqu'un que tu n'as pas vu depuis longtemps.", "", "aprem,soir", ""),
    ("Cuisine un petit truc nouveau ce soir ?", "", "aprem,soir", ""),
    ("Fais une liste de courses pour la semaine, je la garde pour toi.", "courses", "matin,aprem", ""),
    ("Ferme les yeux deux minutes et respire lentement avec moi.", "minuteur:2", "*", ""),
    ("Lis quelques pages d'un livre, loin de l'écran.", "", "soir,nuit", ""),
    ("Il est tard… L'activité du moment, c'est dodo !", "", "nuit", ""),
    ("Range ton coin de bureau en 5 minutes chrono ?", "minuteur:5", "matin,aprem", ""),
    ("Une petite séance de jeu vidéo bien méritée ?", "", "aprem,soir", ""),
]


def moment(h=None):
    h = datetime.datetime.now().hour if h is None else h
    return "matin" if 6 <= h < 12 else "aprem" if 12 <= h < 18 else "soir" if 18 <= h < 23 else "nuit"


def suggest(n=3, weather="", hour=None, recent=()):
    m = moment(hour)
    w = (weather or "").lower()
    beau = any(k in w for k in ("soleil", "clair", "beau", "nuage"))
    pluie = any(k in w for k in ("pluie", "averse", "orage", "neige"))
    ok = []
    for txt, act, moments, cond in ACTIVITES:
        if moments != "*" and m not in moments.split(","):
            continue
        if cond == "beau" and not beau or cond == "pluie" and not pluie:
            continue
        if txt in recent:
            continue
        ok.append((txt, act))
    random.shuffle(ok)
    return ok[:n]


class ActivityWindow(QDialog):
    def __init__(self, comp, ideas, ai=False):
        super().__init__(None)
        self.comp = comp
        self.setWindowTitle("Des idées d'activités")
        self.setStyleSheet(STYLE)
        self.resize(520, 380)
        self.v = QVBoxLayout(self)
        t = QLabel("💡  Qu'est-ce qu'on fait ?")
        t.setObjectName("titre")
        self.v.addWidget(t)
        self.box = QVBoxLayout()
        self.v.addLayout(self.box)
        self.v.addStretch(1)
        row = QHBoxLayout()
        more = QPushButton("🔄  D'autres idées")
        more.clicked.connect(lambda: self.fill(comp.activity_ideas()))
        row.addWidget(more)
        if ai:
            perso = QPushButton("✨  Idées pour moi (IA)")
            perso.clicked.connect(comp.activity_ai)
            row.addWidget(perso)
        row.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        row.addWidget(close)
        self.v.addLayout(row)
        self.fill(ideas)

    def fill(self, ideas):
        while self.box.count():
            w = self.box.takeAt(0).widget()
            if w:
                w.deleteLater()
        for txt, act in ideas:
            card = QFrame()
            card.setObjectName("carte")
            h = QHBoxLayout(card)
            lab = QLabel(txt)
            lab.setWordWrap(True)
            lab.setStyleSheet("font-size: 13px; color: #3d2733;")
            h.addWidget(lab, 1)
            if act:
                b = QPushButton("C'est parti !")
                b.setObjectName("principal")
                b.clicked.connect(lambda _=False, a=act: (self.close(), self.comp.do_activity(a)))
                h.addWidget(b)
            else:
                b = QPushButton("👍")
                b.clicked.connect(lambda _=False, t=txt: (self.close(), self.comp.say("Super ! Amuse-toi bien !")))
                h.addWidget(b)
            self.box.addWidget(card)
