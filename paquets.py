"""Installer et mettre à jour sur n'importe quel Linux : Arch (et Manjaro, EndeavourOS, CachyOS…), Debian / Ubuntu
(Mint, Pop!_OS, Zorin…), Fedora (Nobara, RHEL, Rocky…), openSUSE, Void, Alpine, Solus, Gentoo, NixOS, et les
systèmes « immuables » (Fedora Silverblue / Kinoite, Bazzite, openSUSE Aeon / MicroOS, SteamOS) où l'on passe
plutôt par Flatpak. Rien n'est lancé ici : on fabrique seulement les commandes, montrées dans un terminal visible."""
import os
import shutil
from pathlib import Path

# id ou id_like de /etc/os-release -> gestionnaire de paquets
_FAMILLES = {
    "pacman": ("arch", "manjaro", "endeavouros", "cachyos", "garuda", "artix", "arcolinux", "archcraft", "rebornos",
               "parabola", "steamos-arch"),
    "apt": ("debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali", "raspbian", "neon", "mx", "deepin",
            "pureos", "devuan", "parrot", "kubuntu", "xubuntu", "lubuntu", "tuxedo"),
    "dnf": ("fedora", "rhel", "centos", "rocky", "almalinux", "nobara", "ultramarine", "mageia", "openmandriva",
            "ol", "amzn"),
    "zypper": ("opensuse", "opensuse-leap", "opensuse-tumbleweed", "suse", "sles", "sled", "opensuse-slowroll"),
    "xbps": ("void",),
    "apk": ("alpine", "postmarketos", "chimera"),
    "eopkg": ("solus",),
    "emerge": ("gentoo", "funtoo", "calculate", "redcore"),
    "nix": ("nixos",),
}
NOMS = {"pacman": "pacman (Arch)", "apt": "apt (Debian / Ubuntu)", "dnf": "dnf (Fedora)", "zypper": "zypper (openSUSE)",
        "xbps": "xbps (Void)", "apk": "apk (Alpine)", "eopkg": "eopkg (Solus)", "emerge": "emerge (Gentoo)",
        "nix": "Nix (NixOS)", "rpm-ostree": "rpm-ostree (Fedora Atomic)", "transactional": "transactional-update "
        "(openSUSE immuable)", "": "Flatpak"}
_CACHE = {}


def dans_flatpak():
    """Viki tourne dans un Flatpak : les commandes du système passent par « flatpak-spawn --host »."""
    return os.path.exists("/.flatpak-info")


def hote(cmd):
    """Préfixe une commande (liste) pour qu'elle tourne sur le vrai système, même depuis un Flatpak."""
    return (["flatpak-spawn", "--host"] + list(cmd)) if dans_flatpak() else list(cmd)


def which(outil):
    """Comme shutil.which, mais regarde le vrai système quand on est dans un Flatpak."""
    if not dans_flatpak():
        return shutil.which(outil)
    import subprocess
    try:
        r = subprocess.run(["flatpak-spawn", "--host", "sh", "-c", f"command -v {outil}"], capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def _os_release():
    if "os" in _CACHE:
        return _CACHE["os"]
    d = {}
    for f in (("/run/host/os-release",) if dans_flatpak() else ()) + ("/etc/os-release", "/usr/lib/os-release"):
        try:
            for ligne in Path(f).read_text(errors="ignore").splitlines():
                if "=" in ligne:
                    k, v = ligne.split("=", 1)
                    d[k.strip()] = v.strip().strip('"').strip("'")
            break
        except Exception:
            continue
    _CACHE["os"] = d
    return d


def nom_systeme():
    o = _os_release()
    return o.get("PRETTY_NAME") or o.get("NAME") or "Linux"


def immuable():
    """Système en lecture seule (on n'y installe pas de paquets comme d'habitude)."""
    o = _os_release()
    ids = (o.get("ID", "") + " " + o.get("VARIANT_ID", "") + " " + o.get("ID_LIKE", "")).lower()
    return (os.path.exists("/run/ostree-booted") or "steamos" in ids or "microos" in ids or "aeon" in ids
            or "kalpa" in ids or os.path.exists("/usr/sbin/transactional-update") and
            not os.access("/usr", os.W_OK) and "tumbleweed" not in ids)


def gestionnaire():
    """-> pacman | apt | dnf | zypper | xbps | apk | eopkg | emerge | nix | rpm-ostree | transactional | ''"""
    if "pm" in _CACHE:
        return _CACHE["pm"]
    o = _os_release()
    ids = [o.get("ID", "").lower()] + o.get("ID_LIKE", "").lower().split()
    pm = ""
    if os.path.exists("/run/ostree-booted") and which("rpm-ostree"):
        pm = "rpm-ostree"
    elif "steamos" in ids[0]:
        pm = ""                                               # SteamOS : lecture seule -> Flatpak seulement
    elif immuable() and which("transactional-update"):
        pm = "transactional"
    else:
        for i in ids:
            for p, fam in _FAMILLES.items():
                if i in fam or (p == "zypper" and i.startswith("opensuse")):
                    pm = p
                    break
            if pm:
                break
        if pm and pm != "nix" and not which({"apt": "apt-get", "xbps": "xbps-install"}.get(pm, pm)):
            pm = ""                                           # os-release trompeur : on vérifie l'outil
        if not pm:
            for p, outil in (("pacman", "pacman"), ("apt", "apt-get"), ("dnf", "dnf"), ("zypper", "zypper"),
                             ("xbps", "xbps-install"), ("apk", "apk"), ("eopkg", "eopkg"), ("emerge", "emerge"),
                             ("nix", "nixos-rebuild")):
                if which(outil):
                    pm = p
                    break
    _CACHE["pm"] = pm
    return pm


def init_systeme():
    if which("systemctl") and os.path.isdir("/run/systemd/system"):
        return "systemd"
    if which("rc-service"):
        return "openrc"
    if os.path.isdir("/etc/sv") or which("sv"):
        return "runit"
    return "systemd" if which("systemctl") else ""


def _noms(pkgs, pm):
    """Les noms de paquets pour ce système (les variantes immuables reprennent ceux de leur famille)."""
    if pm in pkgs:
        return pkgs[pm]
    if pm == "rpm-ostree":
        return pkgs.get("dnf")
    if pm == "transactional":
        return pkgs.get("zypper")
    return None


def cmd_installer(noms, pm=None):
    pm = gestionnaire() if pm is None else pm
    p = " ".join(noms)
    return {"pacman": f"sudo pacman -S --needed {p}", "apt": f"sudo apt install -y {p}",
            "dnf": f"sudo dnf install -y {p}", "zypper": f"sudo zypper install -y {p}",
            "xbps": f"sudo xbps-install -Sy {p}", "apk": f"sudo apk add {p}", "eopkg": f"sudo eopkg install -y {p}",
            "emerge": f"sudo emerge --ask=n --noreplace {p}",
            "rpm-ostree": f"sudo rpm-ostree install --idempotent {p}",
            "transactional": f"sudo transactional-update -n pkg install {p}"}.get(pm, "")


def redemarrage_requis(pm=None):
    return (gestionnaire() if pm is None else pm) in ("rpm-ostree", "transactional")


def cmd_service(unite):
    """Activer et démarrer un service, quel que soit le système d'init."""
    init = init_systeme()
    if init == "openrc":
        return f"sudo rc-update add {unite} default && sudo rc-service {unite} start"
    if init == "runit":
        return f"sudo ln -sf /etc/sv/{unite} /var/service/"
    return f"sudo systemctl enable --now {unite}"


def adapter(cmd):
    """Traduit une commande écrite pour systemd (« sudo systemctl enable --now X ») vers l'init du système."""
    pref = "sudo systemctl enable --now "
    if cmd.startswith(pref) and init_systeme() != "systemd":
        return cmd_service(cmd[len(pref):].strip())
    return cmd


def commandes(pkgs, flat="", post=None, post_dnf=None):
    """Commandes pour installer un outil : paquet du système si possible, sinon Flatpak (Flathub).
    -> (liste de commandes, note éventuelle) ; liste vide si impossible ici."""
    pm = gestionnaire()
    noms = _noms(pkgs or {}, pm)
    if noms and pm and pm != "nix" and not (flat and pm in ("rpm-ostree", "transactional")):
        cmds = [cmd_installer(noms, pm)]
        extra = post_dnf if (pm in ("dnf", "zypper", "rpm-ostree", "transactional") and post_dnf) else (post or [])
        note = ""
        if redemarrage_requis(pm):
            note = "Système immuable : l'installation sera active après un redémarrage."
            extra = []                                       # les services s'activeront après le redémarrage
        return cmds + [adapter(c) for c in extra], note
    if flat:
        cmds = []
        if not which("flatpak"):
            if pm in ("", "nix", "rpm-ostree", "transactional"):
                return [], "Installe d'abord Flatpak sur ton système (flathub.org/setup)."
            cmds.append(cmd_installer(["sys-apps/flatpak" if pm == "emerge" else "flatpak"], pm))
        cmds.append("flatpak remote-add --user --if-not-exists flathub "
                    "https://dl.flathub.org/repo/flathub.flatpakrepo")
        cmds.append(f"flatpak install --user -y flathub {flat}")
        return cmds, ""
    if pm == "nix" and noms is None and pkgs:
        nom = next(iter(pkgs.values()))[0]
        return [], f"Sur NixOS, ajoute « {nom} » à ta configuration (environment.systemPackages) puis « sudo nixos-rebuild switch »."
    return [], ""


def texte_installer(pkgs):
    """Pour un conseil écrit : « sudo … install X » adapté au système, ou un texte générique."""
    pm = gestionnaire()
    noms = _noms(pkgs, pm) or pkgs.get("pacman") or next(iter(pkgs.values()), None)
    if not noms:
        return ""
    c = cmd_installer(noms, pm)
    return f"« {c} »" if c else "ton gestionnaire de logiciels (" + " ".join(noms) + ")"


def cmd_mise_a_jour():
    pm = gestionnaire()
    if pm == "pacman":
        for aide in ("paru", "yay"):
            if which(aide):
                return f"{aide} -Syu"
        return "sudo pacman -Syu"
    cmd = {"apt": "sudo apt update && sudo apt upgrade", "dnf": "sudo dnf upgrade --refresh",
           "zypper": "sudo zypper refresh && sudo zypper " + ("dup" if "tumbleweed" in _os_release().get("ID", "")
                                                            else "update"),
           "xbps": "sudo xbps-install -Su", "apk": "sudo apk update && sudo apk upgrade",
           "eopkg": "sudo eopkg upgrade", "emerge": "sudo emerge --sync && sudo emerge -auDN @world",
           "nix": "sudo nixos-rebuild switch --upgrade", "rpm-ostree": "rpm-ostree upgrade",
           "transactional": "sudo transactional-update dup"}.get(pm, "")
    if which("flatpak"):
        cmd = (cmd + " && " if cmd else "") + "flatpak update -y"
    return cmd or None
