"""Bilan de sécurité du PC, expliqué simplement, avec quoi faire.

Tout se lit sur le PC, sans mot de passe administrateur et sans rien modifier. Seule la recherche de mises à
jour peut utiliser internet (comme le gestionnaire de paquets).
Chaque point : {"niveau": "ok" | "conseil" | "attention" | "danger", "titre", "detail", "faire"}.
"""
import os
import platform
import re
import shutil
import stat
import subprocess
from pathlib import Path

IS_WIN = platform.system() == "Windows"
ICONES = {"ok": "✅", "conseil": "💡", "attention": "⚠️", "danger": "🚨"}
ORDRE = {"danger": 0, "attention": 1, "conseil": 2, "ok": 3}

# ports connus (pour expliquer ce qui écoute)
PORTS = {22: "SSH (accès à distance au terminal)", 80: "serveur web", 443: "serveur web (HTTPS)",
         139: "partage de fichiers Windows (Samba)", 445: "partage de fichiers Windows (Samba)",
         631: "imprimantes (CUPS)", 3389: "bureau à distance", 5900: "bureau à distance (VNC)",
         5353: "découverte réseau (mDNS)", 1714: "KDE Connect", 1716: "KDE Connect", 8080: "serveur web de dev",
         3000: "serveur web de dev", 5000: "serveur web de dev", 5173: "serveur web de dev (Vite)",
         27036: "Steam (jeu en local)", 57621: "Spotify (appareils du réseau)", 11434: "Ollama (IA locale)",
         21: "FTP (non chiffré)", 23: "Telnet (non chiffré)", 3306: "base de données MySQL",
         5432: "base de données PostgreSQL", 6379: "base de données Redis", 27017: "base de données MongoDB"}
RISQUES = {21, 23, 3306, 5432, 6379, 27017, 3389, 5900, 139, 445, 11434}



def _cmd_maj(defaut):
    try:
        import paquets
        return paquets.cmd_mise_a_jour() or defaut
    except Exception:
        return defaut


def _conseil_parefeu():
    """Le conseil pare-feu adapté au système (Arch, Debian/Ubuntu, Fedora, openSUSE, Void, Alpine…)."""
    try:
        import paquets
        pm = paquets.gestionnaire()
    except Exception:
        paquets, pm = None, "pacman"
    if pm in ("dnf", "zypper", "rpm-ostree", "transactional"):
        inst = paquets.texte_installer({"dnf": ["firewalld"], "zypper": ["firewalld"]}) if paquets else ""
        return (f"Active le pare-feu firewalld : {inst + ' puis ' if inst else ''}"
                f"« {paquets.cmd_service('firewalld') if paquets else 'sudo systemctl enable --now firewalld'} ». "
                "Ou utilise le bouton « Installer » de l'onglet Outils.")
    inst = paquets.texte_installer({"pacman": ["ufw"], "apt": ["ufw"], "xbps": ["ufw"], "apk": ["ufw"],
                                    "eopkg": ["ufw"], "emerge": ["net-firewall/ufw"]}) if paquets else "« sudo pacman -S ufw »"
    svc = paquets.cmd_service("ufw") if paquets else "sudo systemctl enable --now ufw"
    return (f"Installe et active un pare-feu simple : {inst} puis « sudo ufw enable » et « {svc} » (sous Ubuntu, "
            "ufw est souvent déjà là : « sudo ufw enable »). Ou le bouton « Installer » de l'onglet Outils. "
            "KDE a aussi un réglage « Pare-feu » dans Configuration du système.")

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def _p(niveau, titre, detail, faire=""):
    return {"niveau": niveau, "titre": titre, "detail": detail, "faire": faire}


# ================================================================== Linux
def _active(unit):
    return _run(["systemctl", "is-active", unit], 5)[1].strip() == "active"


def check_firewall():
    on = [u for u in ("firewalld", "ufw", "nftables", "iptables") if _active(u)]
    if on:
        return _p("ok", "Pare-feu actif", f"Le pare-feu tourne ({', '.join(on)}) : il bloque les connexions non "
                  "voulues qui arrivent de l'extérieur.")
    return _p("attention", "Aucun pare-feu actif",
              "Rien ne filtre les connexions qui arrivent sur ton PC. Derrière une box, le risque est limité, mais "
              "sur un Wi-Fi public (gare, café…), n'importe qui sur le réseau peut essayer de joindre tes services.",
              _conseil_parefeu())


def check_ports():
    code, out = _run(["ss", "-tulnpH"], 8)
    if code != 0:
        return [_p("conseil", "Ports réseau", "Je n'ai pas pu lister les ports (outil « ss » absent).")]
    expo = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local = parts[0], parts[4]
        m = re.match(r"^(.*):(\d+)$", local)
        if not m:
            continue
        addr, port = m.group(1).strip("[]"), int(m.group(2))
        if addr.startswith("127.") or addr in ("::1", "localhost") or addr.startswith("%lo"):
            continue                                         # seulement ce PC : sans risque
        if proto == "udp" and port in (5353, 68, 546):
            continue
        proc = re.search(r'users:\(\("([^"]+)"', line)
        expo.setdefault(port, (proto, proc.group(1) if proc else ""))
    if not expo:
        return [_p("ok", "Aucun service ouvert sur le réseau", "Rien sur ton PC n'attend de connexion venant "
                   "des autres appareils : c'est le plus sûr.")]
    out_l = []
    lignes = [f"• port {p} ({proto}) — {PORTS.get(p, 'service inconnu')}" + (f", programme : {pr}" if pr else "")
              for p, (proto, pr) in sorted(expo.items())]
    risky = [p for p in expo if p in RISQUES]
    niveau = "attention" if risky else "conseil"
    out_l.append(_p(niveau, f"{len(expo)} service(s) joignable(s) depuis le réseau",
                    "Ces programmes acceptent des connexions des autres appareils (box, Wi-Fi) :\n" + "\n".join(lignes),
                    ("Les ports en ⚠️ (bases de données, partage, bureau à distance, Ollama…) ne devraient pas être "
                     "ouverts au réseau sauf si tu en as besoin : arrête le service, ou règle-le pour écouter "
                     "seulement sur 127.0.0.1. Un pare-feu actif les protège aussi."
                     if risky else "Si tu ne reconnais pas un programme, arrête-le ou demande-moi « pourquoi le "
                     "port … est ouvert ». Un pare-feu actif les protège.")))
    return out_l


def check_ssh():
    if not (_active("sshd") or _active("ssh")):
        return _p("ok", "Pas de serveur SSH", "Personne ne peut ouvrir un terminal sur ton PC à distance.")
    txt = ""
    for f in [Path("/etc/ssh/sshd_config")] + sorted(Path("/etc/ssh/sshd_config.d").glob("*.conf")):
        try:
            txt += "\n" + f.read_text(errors="ignore")
        except Exception:
            pass
    root = re.search(r"^\s*PermitRootLogin\s+yes", txt, re.M | re.I)
    pwd = not re.search(r"^\s*PasswordAuthentication\s+no", txt, re.M | re.I)
    if root:
        return _p("danger", "SSH : connexion root autorisée", "Le serveur SSH tourne et accepte la connexion "
                  "directe en administrateur (root). C'est la première chose que les robots essaient.",
                  "Dans /etc/ssh/sshd_config, mets « PermitRootLogin no », puis « sudo systemctl restart sshd ». "
                  "Si tu n'utilises pas SSH : « sudo systemctl disable --now sshd ».")
    if pwd:
        return _p("attention", "SSH ouvert avec mot de passe", "Un serveur SSH tourne et accepte les mots de passe : "
                  "des robots peuvent essayer d'en deviner.",
                  "Si tu ne t'en sers pas : « sudo systemctl disable --now sshd ». Sinon, utilise une clé SSH et "
                  "mets « PasswordAuthentication no » dans /etc/ssh/sshd_config.")
    return _p("ok", "SSH protégé", "Le serveur SSH tourne mais n'accepte que les clés : bonne configuration.")


def check_updates(online=True):
    if shutil.which("checkupdates") and online:
        code, out = _run(["checkupdates"], 90)
        pk = [l for l in out.splitlines() if re.match(r"^\S+ \S+ -> \S+", l)]
        if code in (0, 2):
            if not pk:
                return _p("ok", "Système à jour", "Aucune mise à jour en attente.")
            imp = [l.split()[0] for l in pk if re.match(r"^(linux|openssl|openssh|sudo|glibc|systemd|firefox|"
                                                       r"chromium|curl|gnupg|polkit|nss|kernel)", l)]
            return _p("attention" if imp or len(pk) > 30 else "conseil", f"{len(pk)} mise(s) à jour en attente",
                      "Les mises à jour corrigent souvent des failles de sécurité." +
                      (f" Importantes pour la sécurité : {', '.join(imp[:8])}." if imp else ""),
                      "Mets à jour : « " + _cmd_maj("sudo pacman -Syu") + " » (ou le bouton Mises à jour de "
                      "Réglages → Gestion du PC), puis redémarre si le noyau a changé.")
    if shutil.which("apt"):
        code, out = _run(["apt", "list", "--upgradable"], 30)
        pk = [l for l in out.splitlines() if "/" in l and "upgradable" in l]
        if pk:
            return _p("conseil", f"{len(pk)} mise(s) à jour en attente", "Les mises à jour corrigent souvent des "
                      "failles de sécurité.", "« sudo apt update && sudo apt upgrade », ou le logiciel Discover.")
        return _p("ok", "Système à jour", "Aucune mise à jour connue en attente.")
    return _p("conseil", "Mises à jour", "Je n'ai pas pu vérifier les mises à jour sur ce système.",
              "Vérifie-les avec Discover ou ton gestionnaire de paquets.")


def check_reboot():
    run = platform.release()
    mods = Path("/usr/lib/modules")
    if mods.is_dir() and not (mods / run).exists() and any(mods.iterdir()):
        return _p("attention", "Redémarrage nécessaire", f"Le noyau a été mis à jour, mais c'est encore l'ancien "
                  f"({run}) qui tourne : les corrections ne s'appliquent qu'après un redémarrage.",
                  "Redémarre le PC quand tu peux.")
    return None


def check_encryption():
    code, out = _run(["lsblk", "-o", "TYPE,MOUNTPOINTS", "-n", "-l"], 5)
    if code != 0:
        code, out = _run(["lsblk", "-o", "TYPE,MOUNTPOINT", "-n", "-l"], 5)
    if "crypt" in out:
        return _p("ok", "Disque chiffré", "Si on te vole le PC, on ne peut pas lire tes fichiers sans ton mot "
                  "de passe.")
    portable = any(Path("/sys/class/power_supply").glob("BAT*"))
    return _p("attention" if portable else "conseil", "Disque non chiffré",
              "Si quelqu'un vole ou emprunte le disque, il peut lire tous tes fichiers, même sans ton mot de passe "
              "de session." + (" C'est surtout important pour un PC portable." if portable else ""),
              "Le chiffrement se choisit à l'installation du système (LUKS). En attendant, garde tes papiers "
              "importants dans un dossier chiffré (ex. l'outil « Coffre-fort » / Plasma Vault de KDE).")


def check_screenlock():
    f = Path.home() / ".config" / "kscreenlockerrc"
    if not os.environ.get("KDE_FULL_SESSION") and not f.exists():
        return None
    txt = f.read_text(errors="ignore") if f.exists() else ""
    if re.search(r"^\s*Autolock\s*=\s*false", txt, re.M | re.I):
        return _p("attention", "Verrouillage automatique coupé", "L'écran ne se verrouille jamais tout seul : si tu "
                  "t'éloignes, n'importe qui peut utiliser ta session.",
                  "Configuration du système → Écran de verrouillage → « Verrouiller automatiquement l'écran ». "
                  "Et pense à Meta+L pour verrouiller en partant.")
    if re.search(r"^\s*LockOnResume\s*=\s*false", txt, re.M | re.I):
        return _p("conseil", "Pas de verrouillage au réveil", "Après une mise en veille, la session se rouvre "
                  "sans mot de passe.", "Écran de verrouillage → coche « Après la sortie de veille ».")
    return _p("ok", "Verrouillage de l'écran actif", "Ta session se verrouille quand tu t'absentes.")


def check_ssh_keys():
    d = Path.home() / ".ssh"
    if not d.is_dir():
        return None
    bad = []
    try:
        if stat.S_IMODE(d.stat().st_mode) & 0o077:
            bad.append("~/.ssh (dossier)")
        for f in d.iterdir():
            if f.is_file() and not f.name.endswith(".pub") and f.name.startswith("id_"):
                if stat.S_IMODE(f.stat().st_mode) & 0o077:
                    bad.append("~/.ssh/" + f.name)
    except Exception:
        return None
    if bad:
        return _p("attention", "Clés SSH trop ouvertes", "D'autres comptes du PC pourraient lire : " + ", ".join(bad) +
                  ". Une clé privée doit rester secrète.", "Dans un terminal : « chmod 700 ~/.ssh && chmod 600 "
                  "~/.ssh/id_* » puis « chmod 644 ~/.ssh/*.pub ».")
    return _p("ok", "Clés SSH protégées", "Tes clés privées ne sont lisibles que par toi.")


def check_root_accounts():
    try:
        uid0 = [l.split(":")[0] for l in Path("/etc/passwd").read_text().splitlines()
                if l and l.split(":")[2] == "0" and l.split(":")[0] != "root"]
    except Exception:
        return None
    if uid0:
        return _p("danger", "Compte administrateur caché", f"Ces comptes ont les pleins pouvoirs comme root : "
                  f"{', '.join(uid0)}. Ce n'est jamais normal sur un PC perso.",
                  "Ne te connecte plus à des comptes sensibles depuis ce PC et suis le guide « En cas de problème » "
                  "ci-dessous (demande de l'aide à quelqu'un de confiance).")
    return None


def check_autostart():
    items = []
    a = Path.home() / ".config" / "autostart"
    if a.is_dir():
        items += [f.stem for f in a.glob("*.desktop")]
    code, out = _run(["systemctl", "--user", "list-unit-files", "--state=enabled", "--no-legend"], 6)
    if code == 0:
        items += [l.split()[0] for l in out.splitlines() if l.strip() and l.split()[0].endswith(".service")
                  and not l.startswith(("pipewire", "wireplumber", "xdg-user", "p11-kit", "gnome-keyring", "gpg",
                                        "session-migration", "obex", "dbus", "plasma", "kde", "systemd"))]
    code, cr = _run(["crontab", "-l"], 5)
    jobs = [l for l in cr.splitlines() if l.strip() and not l.lstrip().startswith("#") and code == 0]
    if not items and not jobs:
        return _p("ok", "Démarrage automatique", "Aucun programme perso ne se lance tout seul.")
    det = ("Programmes lancés à l'ouverture de ta session : " + ", ".join(sorted(set(items))[:25]) + "." if items
           else "")
    if jobs:
        det += f"\nTâches planifiées (cron) : {len(jobs)} — " + " | ".join(j[:70] for j in jobs[:4])
    return _p("conseil", "À vérifier : ce qui démarre tout seul", det.strip(),
              "Si tu ne reconnais pas un nom, cherche-le avant de le supprimer (Configuration du système → "
              "Démarrage automatique). Les logiciels malveillants aiment se cacher là.")


def check_secureboot():
    code, out = _run(["bootctl", "status"], 6)
    m = re.search(r"Secure Boot:\s*(\w+)", out)
    if not m:
        code, out = _run(["mokutil", "--sb-state"], 5)
        m = re.search(r"SecureBoot (enabled|disabled)", out)
    if not m:
        return None
    if m.group(1).lower() in ("enabled", "yes"):
        return _p("ok", "Secure Boot actif", "Le démarrage vérifie que le système n'a pas été modifié.")
    return _p("conseil", "Secure Boot désactivé", "C'est courant sous Linux (Arch le désactive souvent). Ça protège "
              "contre des attaques rares qui modifient le démarrage.",
              "Pas urgent. Si tu veux l'activer un jour : outil « sbctl » (guide sur le wiki d'Arch).")


def check_viki_secrets(paths=()):
    loose = []
    for p in paths:
        try:
            p = Path(p)
            if p.exists() and stat.S_IMODE(p.stat().st_mode) & 0o077:
                loose.append(p.name)
        except Exception:
            pass
    if loose:
        return _p("attention", "Clés de Viki trop ouvertes", "Ces fichiers (clés, jetons, mots de passe) sont lisibles "
                  "par d'autres comptes : " + ", ".join(loose) + ".", "Je peux les protéger : dis-moi « protège mes "
                  "clés » (ça fait un chmod 600).")
    return None


# ================================================================== Windows (vérifications de base)
def _ps(cmd, timeout=20):
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], timeout)


def windows_checks():
    out = []
    code, txt = _ps("Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,"
                    "AntivirusSignatureAge | Format-List")
    if "AntivirusEnabled" in txt:
        on = re.search(r"AntivirusEnabled\s*:\s*True", txt) and re.search(r"RealTimeProtectionEnabled\s*:\s*True", txt)
        age = re.search(r"AntivirusSignatureAge\s*:\s*(\d+)", txt)
        old = age and int(age.group(1)) > 7
        out.append(_p("ok" if on and not old else "danger" if not on else "attention", "Antivirus (Defender)",
                      "Protection en temps réel active." if on else "La protection en temps réel est coupée.",
                      "" if on and not old else "Sécurité Windows → Protection contre les virus → active la "
                      "protection en temps réel et lance une mise à jour."))
    code, txt = _ps("Get-NetFirewallProfile | Select-Object Name,Enabled | Format-Table -HideTableHeaders")
    offs = re.findall(r"(\w+)\s+False", txt)
    if txt.strip():
        out.append(_p("attention" if offs else "ok", "Pare-feu Windows",
                      f"Désactivé pour : {', '.join(offs)}." if offs else "Actif sur tous les réseaux.",
                      "Sécurité Windows → Pare-feu et protection du réseau → active-le." if offs else ""))
    code, txt = _ps("(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System')"
                    ".EnableLUA")
    if txt.strip() == "0":
        out.append(_p("attention", "Contrôle de compte (UAC) désactivé", "Les programmes peuvent prendre les "
                      "pleins pouvoirs sans te demander.", "Panneau de configuration → Comptes d'utilisateurs → "
                      "Modifier les paramètres du contrôle de compte → remets le curseur par défaut."))
    code, txt = _ps("(Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server')"
                    ".fDenyTSConnections")
    if txt.strip() == "0":
        out.append(_p("attention", "Bureau à distance activé", "D'autres appareils peuvent essayer de se connecter "
                      "à ton PC.", "Paramètres → Système → Bureau à distance → désactive-le si tu ne t'en sers pas."))
    if not out:
        out.append(_p("conseil", "Vérification limitée", "Je n'ai pas pu interroger Windows (PowerShell)."))
    return out


# ================================================================== tout
def run_all(secret_files=(), online=True):
    if IS_WIN:
        res = windows_checks()
    else:
        res = []
        for f in (check_firewall, check_ssh, lambda: check_updates(online), check_reboot, check_encryption,
                  check_screenlock, check_ssh_keys, check_root_accounts, check_autostart, check_secureboot,
                  lambda: check_viki_secrets(secret_files)):
            try:
                r = f()
            except Exception as e:
                r = _p("conseil", "Vérification impossible", f"{getattr(f, '__name__', 'test')} : {str(e)[:80]}")
            if r:
                res.append(r)
        try:
            res += check_ports()
        except Exception:
            pass
    res.sort(key=lambda p: ORDRE.get(p["niveau"], 9))
    return res


def bilan_rapide():
    """Pour la tuile « Santé du PC » : quelques vérifications rapides et hors ligne.
    -> [(niveau, texte court)] ; niveau : ok | attention | danger."""
    out = []
    for f, court in ((check_firewall, "Pare-feu"), (lambda: check_updates(False), "Mises à jour"),
                     (check_reboot, "Redémarrage")):
        try:
            r = f()
        except Exception:
            r = None
        if r:
            out.append(("ok" if r["niveau"] in ("ok", "conseil") else r["niveau"], f"{court} : {r['titre']}"))
    try:
        import gestionpc
        for d in gestionpc.disks_health() or []:
            if d.get("ok") is False:
                out.append(("danger", f"Disque {d.get('nom', '')} : en mauvais état"))
    except Exception:
        pass
    vus = set()
    for chemin, nom in (("/", "Système"), (os.path.expanduser("~"), "Dossier perso")):
        try:
            dev = os.stat(chemin).st_dev
            if dev in vus:                                 # même disque que le système : une seule ligne
                continue
            vus.add(dev)
            u = shutil.disk_usage(chemin)
            libre = u.free / u.total
            if libre < 0.05:
                out.append(("danger", f"{nom} : presque plein ({u.free / 1e9:.0f} Go libres)"))
            elif libre < 0.12:
                out.append(("attention", f"{nom} : bien rempli ({u.free / 1e9:.0f} Go libres)"))
        except Exception:
            pass
    return out


GUIDE = """EN CAS DE PROBLÈME (piratage, virus, compte volé)

1. Garde ton calme et coupe internet (débranche le câble ou coupe le Wi-Fi) si tu vois des choses bizarres :
   souris qui bouge toute seule, fenêtres qui s'ouvrent, demande de rançon, mots de passe changés.
2. Depuis un AUTRE appareil sûr (ton téléphone), change d'abord le mot de passe de ta boîte mail, puis de tes
   comptes importants (banque, réseaux sociaux, Steam, Google, Discord…). Active la double authentification.
3. Préviens ta banque tout de suite si un paiement a pu être fait.
4. Ne paie jamais de rançon et ne rappelle jamais un « support technique » qui t'a contacté : c'est une arnaque.
5. Fais des captures d'écran de ce que tu vois (messages, adresses) : ça servira.
6. En France : le site cybermalveillance.gouv.fr donne de l'aide gratuite et des prestataires près de chez toi.
   Pour porter plainte : commissariat, gendarmerie, ou la plateforme THESEE en ligne pour les escroqueries.
7. Pour repartir de zéro en sécurité : sauvegarde tes fichiers personnels (pas les programmes), réinstalle le
   système, puis remets tes fichiers après les avoir vérifiés.

LES BONS RÉFLEXES AU QUOTIDIEN
• Un mot de passe différent par site, dans un gestionnaire (KeePassXC, Bitwarden).
• Double authentification partout où c'est possible.
• Mises à jour régulières, et redémarrage après les grosses.
• Méfie-toi des liens et des pièces jointes inattendus, même venant d'amis.
• Ne lance pas de commande copiée sur internet sans comprendre ce qu'elle fait (surtout avec sudo ou curl | sh).
• Une sauvegarde sur un disque externe, débranché la plupart du temps.
"""


def report_text(res):
    n = {k: sum(1 for p in res if p["niveau"] == k) for k in ICONES}
    head = (f"Bilan : {n['danger']} urgent(s), {n['attention']} à corriger, {n['conseil']} conseil(s), "
            f"{n['ok']} point(s) OK.\n\n")
    body = []
    for p in res:
        body.append(f"{ICONES[p['niveau']]} {p['titre']}\n{p['detail']}" +
                    (f"\n➜ Que faire : {p['faire']}" if p.get("faire") else ""))
    return head + "\n\n".join(body) + "\n\n" + "─" * 40 + "\n\n" + GUIDE


def summary(res):
    n_d = sum(1 for p in res if p["niveau"] == "danger")
    n_a = sum(1 for p in res if p["niveau"] == "attention")
    if n_d:
        return f"J'ai trouvé {n_d} problème{'s' if n_d > 1 else ''} urgent{'s' if n_d > 1 else ''} de sécurité ! " \
               "Je t'ai tout expliqué dans la fenêtre, avec quoi faire."
    if n_a:
        return f"Ton PC va plutôt bien, mais il y a {n_a} point{'s' if n_a > 1 else ''} à corriger. " \
               "Je t'explique tout dans la fenêtre."
    return "Bonne nouvelle : je n'ai rien trouvé d'inquiétant ! J'ai mis quelques conseils dans la fenêtre."
