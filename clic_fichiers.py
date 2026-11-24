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

if os.path.exists("/.flatpak-info"):          # dans le Flatpak, XDG_DATA_HOME est celui de la boîte : on veut celui du bureau
    DATA = Path(os.environ.get("HOST_XDG_DATA_HOME") or Path.home() / ".local" / "share")
else:
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
    if touches.FLATPAK:                              # le Flatpak ne voit pas les programmes du bureau : on demande à l'hôte
        hote = lambda prog: touches._run(["flatpak-spawn", "--host", "sh", "-c", f"command -v {prog}"])[0] == 0
        if hote("dolphin") or hote("konqueror"):
            faits.append("Dolphin")
            for k in ("kbuildsycoca6", "kbuildsycoca5"):
                if hote(k):
                    touches._run(["flatpak-spawn", "--host", k], timeout=30)
                    break
        if hote("nautilus"):
            NAUTILUS.parent.mkdir(parents=True, exist_ok=True)
        if hote("nemo"):
            NEMO.mkdir(parents=True, exist_ok=True)
    elif shutil.which("dolphin") or shutil.which("konqueror"):
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


def a_jour():
    """Les menus déjà installés pointent-ils vers le bon lanceur ?"""
    try:
        return touches.lanceur() in (KDE6 / "viki-textes.desktop").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True


def installe():
    return (KDE6 / "viki-textes.desktop").exists() or NAUTILUS.exists() or any(NEMO.glob("viki-*.nemo_action")) \
        if NEMO.exists() else (KDE6 / "viki-textes.desktop").exists() or NAUTILUS.exists()


# ================================================================== Windows : le clic droit de l'Explorateur
if os.name == "nt":
    import sys
    import winreg

    CLES = [(r"Software\Classes\*\shell\Viki", [a for a in ACTIONS if a[3] is not True]),
            (r"Software\Classes\SystemFileAssociations\image\shell\VikiImage", [a for a in ACTIONS if a[3] is True])]

    def _exe():
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        here = Path(__file__).resolve().parent
        py = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{py}" "{here / "compagnon.py"}"'

    def _effacer(chemin):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin, 0, winreg.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        sous = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    _effacer(chemin + "\\" + sous)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, chemin)
        except OSError:
            pass

    def installer():
        exe = _exe()
        ico = sys.executable if getattr(sys, "frozen", False) else ""
        for cle, acts in CLES:
            _effacer(cle)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cle) as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Viki" if "Image" not in cle else "Viki (image)")
                winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
                if ico:
                    winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, ico)
            for i, (a, nom, _ico, _img) in enumerate(acts):
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{cle}\\shell\\{i:02d}{a}") as k:
                    winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, tr(nom))
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{cle}\\shell\\{i:02d}{a}\\command") as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'{exe} fichier {a} "%1"')
        return ["l'Explorateur de fichiers (Windows 11 : « Afficher d'autres options »)"]

    def retirer():
        for cle, _acts in CLES:
            _effacer(cle)

    def installe():
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLES[0][0]).Close()
            return True
        except OSError:
            return False

    def a_jour():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLES[0][0] + "\\shell\\00resumer\\command") as k:
                return _exe() in winreg.QueryValueEx(k, "")[0]
        except OSError:
            return True
