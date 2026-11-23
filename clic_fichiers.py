"""🖱️ « Viki » dans le clic droit de tes fichiers (Dolphin, Nautilus / Fichiers, Nemo) : résumer, traduire,
expliquer, lui poser une question, décrire ou convertir une image.

On écrit seulement des petits fichiers de menu dans TON dossier personnel, après un clic sur « Installer »,
et « Retirer » les enlève. Chaque entrée lance : <viki> fichier <action> <fichiers…>
"""
import os
import shlex
import shutil
from pathlib import Path

try:
    from i18n import tr
except Exception:                                   # pragma: no cover
    def tr(t):
        return t

import touches

DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
KDE6 = DATA / "kio" / "servicemenus"
KDE5 = DATA / "kservices5" / "ServiceMenus"
NAUTILUS = DATA / "nautilus" / "scripts" / "Viki"
NEMO = DATA / "nemo" / "actions"

# (action, nom, icône, pour les images seulement ?)
ACTIONS = [
    ("resumer", "Résumer", "view-list-text", False),
    ("traduire", "Traduire", "languages", False),
    ("expliquer", "M'expliquer ce fichier", "help-about", False),
    ("demander", "Lui poser une question…", "dialog-question", False),
    ("surete", "Est-ce que c'est sûr ?", "security-high", None),
    ("decrire", "Décrire l'image", "view-preview", True),
    ("png", "Convertir en PNG", "image-x-generic", True),
    ("jpg", "Convertir en JPG", "image-x-generic", True),
    ("webp", "Convertir en WebP", "image-x-generic", True),
]
TEXTES = ("text/*;application/pdf;application/vnd.openxmlformats-officedocument.wordprocessingml.document;"
          "application/vnd.oasis.opendocument.text;application/epub+zip;application/json;application/xml;"
          "application/x-shellscript;")


def _cmd(action):
    return f"{touches.lanceur()} fichier {action}"


def _kde_fichier(images):
    acts = [a for a in ACTIONS if a[3] == images]
    mime = "all/allfiles;" if images is None else "image/*;" if images else TEXTES
    lignes = ["[Desktop Entry]", "Type=Service", "MimeType=" + mime,
              "Actions=" + ";".join(a[0] for a in acts) + ";", "X-KDE-Submenu=Viki",
              "X-KDE-Submenu[fr]=Viki", "Icon=face-smile", ""]
    for a, nom, ico, _ in acts:
        lignes += [f"[Desktop Action {a}]", f"Name={tr(nom)}", f"Icon={ico}", f"Exec={_cmd(a)} %F", ""]
    return "\n".join(lignes)


def _exe(p, contenu):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenu, encoding="utf-8")
    p.chmod(0o755)


def installer():
    """-> liste des gestionnaires de fichiers où c'est installé."""
    faits = []
    for d in (KDE6, KDE5):
        if d == KDE5 and not (shutil.which("kbuildsycoca5") or d.exists()):
            continue
        _exe(d / "viki-textes.desktop", _kde_fichier(False))
        _exe(d / "viki-images.desktop", _kde_fichier(True))
        _exe(d / "viki-tous.desktop", _kde_fichier(None))
    if shutil.which("dolphin") or shutil.which("konqueror"):
        faits.append("Dolphin")
        for k in ("kbuildsycoca6", "kbuildsycoca5"):
            if shutil.which(k):
                touches._run([k], timeout=30)
                break
    if shutil.which("nautilus") or NAUTILUS.parent.exists():
        for a, nom, _ico, _img in ACTIONS:
            _exe(NAUTILUS / tr(nom).replace("/", "-"),
                 f'#!/bin/sh\nexec {_cmd(a)} "$@"\n')
        faits.append("Fichiers (Nautilus)")
    if shutil.which("nemo") or NEMO.exists():
        for a, nom, _ico, img in ACTIONS:
            ext = "png;jpg;jpeg;webp;gif;bmp;" if img else "any;"
            _exe(NEMO / f"viki-{a}.nemo_action",
                 f"[Nemo Action]\nName=Viki : {tr(nom)}\nExec={_cmd(a)} %F\nSelection=notnone\nExtensions={ext}\n"
                 "Icon-Name=face-smile\n")
        faits.append("Nemo")
    return faits


def retirer():
    for d in (KDE6, KDE5):
        for f in ("viki-textes.desktop", "viki-images.desktop", "viki-tous.desktop"):
            try:
                (d / f).unlink()
            except OSError:
                pass
    shutil.rmtree(NAUTILUS, ignore_errors=True)
    for f in NEMO.glob("viki-*.nemo_action") if NEMO.exists() else []:
        try:
            f.unlink()
        except OSError:
            pass


def installe():
    return (KDE6 / "viki-textes.desktop").exists() or NAUTILUS.exists() or any(NEMO.glob("viki-*.nemo_action")) \
        if NEMO.exists() else (KDE6 / "viki-textes.desktop").exists() or NAUTILUS.exists()
