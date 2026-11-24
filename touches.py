"""⌨️ Raccourcis clavier globaux : appeler Viki de n'importe où, même quand elle est cachée derrière une fenêtre.
On les inscrit dans les réglages du bureau (c'est la seule façon qui marche aussi sous Wayland) :
KDE Plasma, GNOME (et Ubuntu, Pop!_OS…), Cinnamon, MATE, Budgie et Xfce. Pour les autres (Hyprland, Sway, i3…),
on donne la ligne à copier dans leur fichier de configuration.
Rien n'est touché sans un clic, et « Retirer » remet tout comme avant."""
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

# (id, option de la ligne de commande, nom, touches par défaut au format Qt)
ACTIONS = [
    ("ecrire", "--ecrire", "Lui écrire", "Meta+Alt+V"),
    ("zone", "--zone", "Traduire une zone de l'écran", "Meta+Alt+T"),
    ("salon", "--salon", "Ouvrir le Salon (séries, Netflix, Spotify…)", "Meta+Alt+C"),
    ("parler", "--parler", "Lui parler au micro", "Meta+Alt+M"),
    ("guide", "--guide", "Montre-moi sur l'écran", "Meta+Alt+G"),
    ("curseur", "--curseur", "La roue de Viki autour de la souris", "Meta+Alt+Space"),
]
PREFIXE = "viki-raccourci-"


FLATPAK = os.path.exists("/.flatpak-info")
# un petit script toujours au même endroit, réécrit à chaque lancement de Viki : le clic droit des fichiers,
# le démarrage avec le PC et les raccourcis clavier passent par lui, donc ils marchent encore quand l'AppImage
# est déplacée, renommée (« Viki-x86_64(1).AppImage »…) ou remplacée par une nouvelle version.
STABLE = Path.home() / ".local" / "share" / "viki" / "lancer.sh"


def preparer_lanceur():
    """Écrit (ou met à jour) le script stable. -> son chemin, ou None."""
    try:
        reel = lanceur_reel()
        contenu = ("#!/bin/sh\n# Lance (ou réveille) Viki. Réécrit par Viki à chaque démarrage : ne pas modifier.\n"
                   f"exec {reel} \"$@\"\n")
        STABLE.parent.mkdir(parents=True, exist_ok=True)
        if not STABLE.exists() or STABLE.read_text(encoding="utf-8", errors="ignore") != contenu:
            STABLE.write_text(contenu, encoding="utf-8")
        STABLE.chmod(0o755)
        return STABLE
    except Exception:
        return None


def lanceur():
    """La commande qui lance (ou réveille) Viki, vue depuis le bureau (fichiers de menu, raccourcis…)."""
    if STABLE.exists() and os.access(STABLE, os.X_OK):
        return shlex.quote(str(STABLE))
    return lanceur_reel()


def lanceur_reel():
    if FLATPAK:
        return "flatpak run io.github.korhyu00.Viki"
    if os.environ.get("APPIMAGE"):
        return shlex.quote(os.environ["APPIMAGE"])
    here = Path(__file__).resolve().parent
    run = here / "run.sh"
    return shlex.quote(str(run)) if run.exists() else "python3 " + shlex.quote(str(here / "compagnon.py"))


def bureau():
    d = (os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" + os.environ.get("DESKTOP_SESSION", "")).upper()
    for k, nom in (("KDE", "kde"), ("CINNAMON", "cinnamon"), ("BUDGIE", "gnome"), ("GNOME", "gnome"),
                   ("UNITY", "gnome"), ("POP", "gnome"), ("MATE", "mate"), ("XFCE", "xfce"),
                   ("HYPRLAND", "hyprland"), ("SWAY", "sway"), ("I3", "i3")):
        if k in d:
            return nom
    return ""


def _gtk(combo):
    """« Meta+Alt+V » -> « <Super><Alt>v » (GNOME, Cinnamon, MATE, Xfce)."""
    *mods, key = combo.split("+")
    m = {"Meta": "<Super>", "Alt": "<Alt>", "Ctrl": "<Primary>", "Shift": "<Shift>"}
    return "".join(m.get(x, "") for x in mods) + key.lower()


def _texte(combo):
    return combo.replace("Meta", "Super")


def env_systeme():
    """Pour les outils du bureau : sans les bibliothèques de l'AppImage (sinon kwriteconfig6, qdbus… plantent)."""
    env = dict(os.environ)
    if "COMPAGNON_ORIG_LD" in env:
        if env["COMPAGNON_ORIG_LD"]:
            env["LD_LIBRARY_PATH"] = env["COMPAGNON_ORIG_LD"]
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env_systeme())
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


def _gs_list(val):
    val = (val or "").strip()
    if val.startswith("@as"):
        val = val[3:].strip()
    try:
        return json.loads(val.replace("'", '"')) if val else []
    except Exception:
        return []


# ------------------------------------------------------------------ par bureau
def _gnome(actions, retirer=False):
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
    _c, cur = _run(["gsettings", "get", schema, "custom-keybindings"])
    chemins = [p for p in _gs_list(cur) if PREFIXE not in p]
    if not retirer:
        for aid, opt, nom, combo in actions:
            p = f"{base}{PREFIXE}{aid}/"
            rel = f"{schema}.custom-keybinding:{p}"
            _run(["gsettings", "set", rel, "name", f"Viki — {nom}"])
            _run(["gsettings", "set", rel, "command", f"{lanceur()} {opt}"])
            _run(["gsettings", "set", rel, "binding", _gtk(combo)])
            chemins.append(p)
    code, _o = _run(["gsettings", "set", schema, "custom-keybindings", json.dumps(chemins).replace('"', "'")])
    return code == 0


def _cinnamon(actions, retirer=False):
    schema = "org.cinnamon.desktop.keybindings"
    base = "/org/cinnamon/desktop/keybindings/custom-keybindings/"
    _c, cur = _run(["gsettings", "get", schema, "custom-list"])
    noms = [n for n in _gs_list(cur) if not n.startswith(PREFIXE)]
    if not retirer:
        for aid, opt, nom, combo in actions:
            rel = f"{schema}.custom-keybinding:{base}{PREFIXE}{aid}/"
            _run(["gsettings", "set", rel, "name", f"Viki — {nom}"])
            _run(["gsettings", "set", rel, "command", f"{lanceur()} {opt}"])
            _run(["gsettings", "set", rel, "binding", f"['{_gtk(combo)}']"])
            noms.append(PREFIXE + aid)
    code, _o = _run(["gsettings", "set", schema, "custom-list", json.dumps(noms).replace('"', "'")])
    return code == 0


def _mate(actions, retirer=False):
    ok = True
    for aid, opt, nom, combo in actions:
        p = f"/org/mate/desktop/keybindings/{PREFIXE}{aid}/"
        if retirer:
            _run(["dconf", "reset", "-f", p])
            continue
        rel = f"org.mate.control-center.keybinding:{p}"
        for k, v in (("name", f"Viki — {nom}"), ("action", f"{lanceur()} {opt}"), ("binding", _gtk(combo))):
            ok = _run(["gsettings", "set", rel, k, v])[0] == 0 and ok
    return ok


def _xfce(actions, retirer=False):
    ok = True
    for aid, opt, nom, combo in actions:
        prop = f"/commands/custom/{_gtk(combo)}"
        if retirer:
            _run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-r"])
            continue
        ok = _run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-n", "-t", "string", "-s",
                   f"{lanceur()} {opt}"])[0] == 0 and ok
    return ok


def _kde(actions, retirer=False):
    """Plasma : un raccourci de « commande » = un fichier .desktop + son entrée dans kglobalshortcutsrc."""
    apps = Path.home() / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    kw = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    ok = True
    for aid, opt, nom, combo in actions:
        f = apps / f"{PREFIXE}{aid}.desktop"
        if retirer:
            f.unlink(missing_ok=True)
            if kw:
                _run([kw, "--file", "kglobalshortcutsrc", "--group", "services", "--group", f.name, "--key",
                      "_launch", "--delete"])
            continue
        f.write_text("[Desktop Entry]\nType=Application\nName=Viki — " + nom + "\nExec=" + lanceur() + " " + opt +
                     "\nIcon=viki\nNoDisplay=true\nX-KDE-GlobalAccel-CommandShortcut=true\n"
                     "X-KDE-Shortcuts=" + combo + "\n")
        if kw:
            ok = _run([kw, "--file", "kglobalshortcutsrc", "--group", "services", "--group", f.name, "--key",
                       "_launch", combo])[0] == 0 and ok
        else:
            ok = False
    # Plasma relit ses raccourcis (sinon : à la prochaine connexion)
    for q in ("qdbus6", "qdbus", "qdbus-qt6", "qdbus-qt5"):
        if shutil.which(q):
            _run([q, "org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel.reloadConfig"])
            break
    return ok


_BUREAUX = {"gnome": _gnome, "cinnamon": _cinnamon, "mate": _mate, "xfce": _xfce, "kde": _kde}


def lignes_config(b=None):
    """Pour Hyprland, Sway, i3… : les lignes à copier dans leur configuration."""
    b = b or bureau()
    out = []
    for _aid, opt, nom, combo in ACTIONS:
        *mods, key = combo.split("+")
        if b == "hyprland":
            m = " ".join({"Meta": "SUPER", "Alt": "ALT", "Ctrl": "CTRL", "Shift": "SHIFT"}[x] for x in mods)
            out.append(f"bind = {m}, {key}, exec, {lanceur()} {opt}   # Viki — {nom}")
        else:
            m = "+".join({"Meta": "$mod", "Alt": "Mod1", "Ctrl": "Control", "Shift": "Shift"}[x] for x in mods)
            out.append(f"bindsym {m}+{key.lower()} exec {lanceur()} {opt}   # Viki — {nom}")
    return "\n".join(out)


def peut_installer():
    b = bureau()
    if b in ("gnome", "cinnamon", "mate"):
        return bool(shutil.which("gsettings"))
    if b == "xfce":
        return bool(shutil.which("xfconf-query"))
    if b == "kde":
        return True
    return False


def installer(actions=None):
    """-> (ok, message)"""
    b = bureau()
    f = _BUREAUX.get(b)
    if not f or not peut_installer():
        return False, "manuel"
    ok = f(actions or ACTIONS)
    return ok, b


def retirer():
    b = bureau()
    f = _BUREAUX.get(b)
    if f and peut_installer():
        f(ACTIONS, retirer=True)
        return True
    return False


def resume():
    return "\n".join(f"• {_texte(c)} : {n}" for _a, _o, n, c in ACTIONS)
