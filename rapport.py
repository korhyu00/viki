"""🐞 Signaler un bug : Viki prépare un rapport utile (version, système, bureau, dernières erreurs), en retire tout
ce qui est personnel (ton nom d'utilisateur, tes dossiers, ton adresse mail, tes adresses IP, le nom du PC),
te le montre en entier, puis ouvre la page GitHub déjà remplie. Rien n'est envoyé sans ton clic."""
import getpass
import os
import platform
import re
import socket
import sys
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QLabel, QCheckBox

try:
    from i18n import tr
except Exception:                                          # pragma: no cover
    def tr(t):
        return t

DEPOT = "https://github.com/korhyu00/viki/issues/new"
MAX_URL = 7000                                             # au-delà, les navigateurs / GitHub coupent l'adresse


def anonymiser(txt):
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    home = str(Path.home())
    try:
        hote = socket.gethostname()
    except Exception:
        hote = ""
    if home and home != "/":
        txt = txt.replace(home, "~")
    if user and len(user) > 2:
        txt = re.sub(r"\b" + re.escape(user) + r"\b", "<utilisateur>", txt)
    if hote and len(hote) > 2:
        txt = re.sub(r"\b" + re.escape(hote) + r"\b", "<pc>", txt)
    txt = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<mail>", txt)
    txt = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", lambda m: m.group(0) if m.group(0).startswith(("127.", "0."))
                 else "<ip>", txt)
    txt = re.sub(r"(?i)(api[_-]?key|token|password|mot de passe|secret)\s*[:=]\s*\S+", r"\1=<caché>", txt)
    txt = re.sub(r"\b(sk|ghp|gho|hf|xox[bp])[-_][A-Za-z0-9_-]{10,}", "<clé>", txt)
    return txt


def _queue(path, n):
    try:
        lignes = Path(path).read_text(errors="ignore").splitlines()
        return "\n".join(lignes[-n:])
    except Exception:
        return ""


def infos(C, comp=None):
    """-> texte Markdown (déjà anonymisé)."""
    try:
        import mise_a_jour
        version = mise_a_jour.VERSION
    except Exception:
        version = "?"
    try:
        import paquets
        systeme = f"{paquets.nom_systeme()} ({paquets.gestionnaire() or 'flatpak'})"
    except Exception:
        systeme = platform.platform()
    try:
        from demarrage import bureau
        bur = bureau()
    except Exception:
        bur = os.environ.get("XDG_CURRENT_DESKTOP", "?")
    try:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        qt = f"Qt {QT_VERSION_STR} / PyQt {PYQT_VERSION_STR}"
    except Exception:
        qt = "?"
    scr = QApplication.primaryScreen()
    ecran = f"{scr.size().width()}×{scr.size().height()} @ {scr.devicePixelRatio():g}" if scr else "?"
    cfg = getattr(comp, "cfg", {}) or {}
    lignes = [f"- **Viki** : {version}" + (" (AppImage)" if os.environ.get("APPIMAGE") else ""),
              f"- **Système** : {systeme}", f"- **Bureau** : {bur}", f"- **Noyau** : {platform.release()}",
              f"- **Python** : {sys.version.split()[0]} · {qt}", f"- **Écran** : {ecran}",
              f"- **Langue** : {cfg.get('langue_menus', '?')} · thème {cfg.get('theme', '?')} · "
              f"raccourcis {cfg.get('barre_place', '?')}"]
    try:
        perso = getattr(comp, "char", {}).get("name", "")
        if perso:
            lignes.append(f"- **Personnage** : {perso}")
    except Exception:
        pass
    d = Path(C.CONFIG_DIR)
    blocs = []
    for nom, n in (("erreurs.log", 60), ("plantages.log", 30), ("demarrage.log", 25)):
        q = _queue(d / nom, n)
        if q.strip():
            blocs.append(f"<details><summary>{nom}</summary>\n\n```\n{q}\n```\n</details>")
    return anonymiser("\n".join(lignes) + ("\n\n" + "\n\n".join(blocs) if blocs else ""))


def ouvrir(parent, C, comp=None):
    """La fenêtre : on décrit le souci, on voit tout le rapport, puis « Ouvrir sur GitHub » (ou « Copier »)."""
    from actu_fenetre import Boite
    b = Boite(parent, tr("🐞 Signaler un bug"),
              tr("Explique en quelques mots ce qui s'est passé. Je joins les infos utiles (version, système, "
                 "dernières erreurs) sans rien de personnel : ton nom, tes dossiers, ton mail et tes adresses "
                 "sont retirés. Tu vois tout avant l'envoi."),
              [(tr("Copier le rapport"), "copier", "non"), (tr("Ouvrir sur GitHub"), "github", "oui")], "🐞")
    quoi = QPlainTextEdit()
    quoi.setPlaceholderText(tr("Ex. : quand je passe la souris sur le rond 📊, les ronds changent de côté…"))
    quoi.setFixedHeight(90)
    b.ajouter_champ("Ce qui s'est passé", quoi)
    etapes = QPlainTextEdit()
    etapes.setPlaceholderText(tr("1. J'ouvre…  2. Je clique sur…  3. …"))
    etapes.setFixedHeight(70)
    b.ajouter_champ("Comment le refaire (si tu sais)", etapes)
    detail = QPlainTextEdit(infos(C, comp))
    detail.setReadOnly(True)
    detail.setFixedHeight(150)
    detail.setStyleSheet("QPlainTextEdit { font-family: monospace; font-size: 11px; }")
    b.ajouter_champ("Ce qui sera joint (déjà anonymisé)", detail)
    joindre = QCheckBox(tr("Joindre ces informations"))
    joindre.setChecked(True)
    lay = joindre.parent().layout() if joindre.parent() else detail.parentWidget().layout()
    lay.insertWidget(lay.count() - 1, joindre)
    b.resize(640, 640)
    b.exec()
    if b.valeur not in ("copier", "github"):
        return None
    titre = quoi.toPlainText().strip().splitlines()[0][:80] if quoi.toPlainText().strip() else "Bug"
    corps = (f"### Ce qui s'est passé\n{anonymiser(quoi.toPlainText().strip()) or '(non précisé)'}\n\n"
             f"### Comment le refaire\n{anonymiser(etapes.toPlainText().strip()) or '(inconnu)'}\n\n")
    if joindre.isChecked():
        corps += "### Infos\n" + detail.toPlainText()
    QApplication.clipboard().setText(corps)
    if b.valeur == "copier":
        return "copie"
    url = f"{DEPOT}?labels=bug&title={quote(titre)}&body={quote(corps)}"
    if len(url) > MAX_URL:                                 # trop long : on raccourcit les journaux dans l'adresse
        court = corps[: max(500, len(corps) - (len(url) - MAX_URL) // 3 - 200)] + \
            "\n\n_(" + tr("rapport complet copié : colle-le ici avec Ctrl+V") + ")_"
        url = f"{DEPOT}?labels=bug&title={quote(titre)}&body={quote(court)}"
    QDesktopServices.openUrl(QUrl(url))
    return "github"
