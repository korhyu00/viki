"""Centre « Vie privée et sécurité » de Viki : bilan, ports ouverts et redirections, outils à installer
(navigateurs, Tor, pare-feu, mots de passe, sauvegardes chiffrées…), DNS chiffré, proxy, sauvegarde chiffrée
d'un dossier. Tout est en option : rien n'est installé ni changé sans un clic de ta part, et chaque commande
système s'affiche dans un terminal (ton mot de passe est demandé là, jamais par Viki)."""
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

try:
    import securite
except Exception:
    securite = None

IS_WIN = os.name == "nt"
WO = None
if IS_WIN:
    try:
        import windows_outils as WO               # 🪟 les équivalents Windows (PowerShell, netstat, winget…)
    except Exception:
        WO = None


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env())
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def _env():
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH"):
        env.pop(k, None)
    if os.environ.get("COMPAGNON_ORIG_LD"):
        env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
    return env


# ------------------------------------------------------------------ gestionnaire de paquets
try:
    import paquets
except Exception:                                          # pragma: no cover
    paquets = None


def pkg_manager():
    if paquets:
        return paquets.gestionnaire()
    for pm in ("pacman", "apt", "dnf", "zypper"):
        if shutil.which(pm if pm != "apt" else "apt-get"):
            return pm
    return ""


def flatpak_ok():
    return bool(shutil.which("flatpak"))


def flatpak_has(app_id):
    if not flatpak_ok() or not app_id:
        return False
    code, out = _run(["flatpak", "info", app_id], 6)
    return code == 0


# ------------------------------------------------------------------ outils proposés
# check : commandes qui prouvent que c'est installé ; flat : appli Flathub ; pkgs : paquets par système
TOOLS = [
    # navigateurs
    dict(id="librewolf", cat="nav", ico="🦊", nom="LibreWolf", flat="io.gitlab.librewolf-community", check=["librewolf"],
         pkgs={}, desc="Firefox réglé pour la vie privée : pas de télémétrie, bloqueur de pubs intégré."),
    dict(id="mullvadb", cat="nav", ico="🛡️", nom="Mullvad Browser", flat="net.mullvad.MullvadBrowser",
         check=["mullvad-browser"], pkgs={}, desc="Le navigateur Tor sans le réseau Tor : très difficile à pister "
                                                   "(empreinte commune à tous), gratuit, sans compte."),
    dict(id="torbrowser", cat="nav", ico="🧅", nom="Navigateur Tor", flat="org.torproject.torbrowser-launcher",
         check=["torbrowser-launcher"], pkgs={"pacman": ["torbrowser-launcher"], "apt": ["torbrowser-launcher"],
                                               "dnf": ["torbrowser-launcher"], "zypper": ["torbrowser-launcher"],
                                               "xbps": ["torbrowser-launcher"]},
         desc="Passe par le réseau Tor : ton adresse IP est cachée aux sites. Plus lent, idéal pour l'anonymat."),
    dict(id="brave", cat="nav", ico="🦁", nom="Brave", flat="com.brave.Browser", check=["brave", "brave-browser"],
         pkgs={}, desc="Basé sur Chromium, bloque pubs et pisteurs d'office. Rapide, compatible avec tout."),
    # réseau
    dict(id="tor", cat="reseau", ico="🧅", nom="Tor (service)", flat="", check=["tor"],
         pkgs={"pacman": ["tor"], "apt": ["tor"], "dnf": ["tor"], "zypper": ["tor"], "xbps": ["tor"], "apk": ["tor"],
               "eopkg": ["tor"], "emerge": ["net-vpn/tor"]},
         post=["sudo systemctl enable --now tor"],
         desc="Le réseau Tor pour tes applis : un proxy SOCKS sur 127.0.0.1:9050 (à mettre dans une appli "
              "qui le permet, comme Telegram ou qBittorrent)."),
    dict(id="ufw", cat="reseau", ico="🧱", nom="Pare-feu (ufw)", flat="", check=["ufw", "firewall-cmd"],
         pkgs={"pacman": ["ufw"], "apt": ["ufw"], "dnf": ["firewalld"], "zypper": ["firewalld"], "xbps": ["ufw"],
               "apk": ["ufw"], "eopkg": ["ufw"], "emerge": ["net-firewall/ufw"]},
         post=["sudo ufw default deny incoming", "sudo ufw default allow outgoing", "sudo ufw allow 1714:1764/tcp",
               "sudo ufw allow 1714:1764/udp", "sudo ufw enable", "sudo systemctl enable --now ufw"],
         post_dnf=["sudo systemctl enable --now firewalld"],
         desc="Bloque les connexions qui arrivent de l'extérieur, laisse sortir les tiennes. KDE Connect reste "
              "autorisé. Le plus important sur un Wi-Fi public."),
    dict(id="opensnitch", cat="reseau", ico="👁️", nom="OpenSnitch", flat="", check=["opensnitch-ui", "opensnitchd"],
         pkgs={"pacman": ["opensnitch"], "apt": ["opensnitch", "python3-opensnitch-ui"], "dnf": ["opensnitch"],
               "zypper": ["opensnitch"]},
         post=["sudo systemctl enable --now opensnitchd"],
         desc="Pare-feu « appli par appli » : il te demande quand un programme veut se connecter à internet."),
    dict(id="upnpc", cat="reseau", ico="📡", nom="miniupnpc (voir les redirections)", flat="", check=["upnpc"],
         pkgs={"pacman": ["miniupnpc"], "apt": ["miniupnpc"], "dnf": ["miniupnpc"], "zypper": ["miniupnpc"],
               "xbps": ["miniupnpc"], "apk": ["miniupnpc"], "emerge": ["net-libs/miniupnpc"]},
         desc="Permet à Viki de te montrer les ports que tes applis ont ouverts sur ta box (UPnP)."),
    # données
    dict(id="keepassxc", cat="donnees", ico="🔑", nom="KeePassXC", flat="org.keepassxc.KeePassXC", check=["keepassxc"],
         pkgs={"pacman": ["keepassxc"], "apt": ["keepassxc"], "dnf": ["keepassxc"], "zypper": ["keepassxc"],
               "xbps": ["keepassxc"], "apk": ["keepassxc"], "eopkg": ["keepassxc"], "emerge": ["app-admin/keepassxc"]},
         desc="Gestionnaire de mots de passe hors ligne : un mot de passe fort et différent partout, un seul à retenir."),
    dict(id="bitwarden", cat="donnees", ico="🔐", nom="Bitwarden", flat="com.bitwarden.desktop", check=["bitwarden"],
         pkgs={}, desc="Gestionnaire de mots de passe synchronisé (PC + téléphone), chiffré de bout en bout. Gratuit."),
    dict(id="pika", cat="donnees", ico="💾", nom="Pika Backup", flat="org.gnome.World.PikaBackup", check=["pika-backup"],
         pkgs={}, desc="Sauvegardes chiffrées très simples (sur disque externe ou serveur), avec planning automatique."),
    dict(id="vorta", cat="donnees", ico="🗄️", nom="Vorta (BorgBackup)", flat="com.borgbase.Vorta", check=["vorta"],
         pkgs={"pacman": ["vorta"], "apt": ["vorta"], "dnf": ["vorta"], "zypper": ["vorta"]},
         desc="Sauvegardes chiffrées et dédupliquées, plus de réglages que Pika."),
    dict(id="cryptomator", cat="donnees", ico="🗝️", nom="Cryptomator", flat="org.cryptomator.Cryptomator",
         check=["cryptomator"], pkgs={}, desc="Un coffre chiffré dans ton cloud (Drive, Dropbox…) : le service ne voit "
                                               "que des fichiers illisibles."),
    dict(id="veracrypt", cat="donnees", ico="📦", nom="VeraCrypt", flat="", check=["veracrypt"],
         pkgs={"pacman": ["veracrypt"], "xbps": ["veracrypt"], "emerge": ["app-crypt/veracrypt"]}, desc="Conteneurs et clés USB chiffrés."),
    dict(id="signal", cat="donnees", ico="💬", nom="Signal", flat="org.signal.Signal", check=["signal-desktop"],
         pkgs={"pacman": ["signal-desktop"]}, desc="Messagerie chiffrée de bout en bout."),
    dict(id="clamav", cat="donnees", ico="🦠", nom="ClamAV (antivirus)", flat="", check=["clamscan"],
         pkgs={"pacman": ["clamav"], "apt": ["clamav"], "dnf": ["clamav"], "zypper": ["clamav"], "xbps": ["clamav"],
               "apk": ["clamav"], "eopkg": ["clamav"], "emerge": ["app-antivirus/clamav"]},
         post=["sudo freshclam"], desc="Antivirus libre : utile pour vérifier des fichiers reçus (surtout pour "
                                       "Windows). Sous Linux, les mises à jour comptent bien plus."),
]
# sous Windows : l'identifiant winget de chaque outil (absent = pas pour Windows : Windows a déjà l'équivalent)
WINGET = {"librewolf": "LibreWolf.LibreWolf", "mullvadb": "MullvadVPN.MullvadBrowser", "torbrowser": "TorProject.TorBrowser",
          "brave": "Brave.Brave", "opensnitch": "Henry++.simplewall", "keepassxc": "KeePassXCTeam.KeePassXC",
          "bitwarden": "Bitwarden.Bitwarden", "cryptomator": "Cryptomator.Cryptomator", "veracrypt": "IDRIX.VeraCrypt",
          "signal": "OpenWhisperSystems.Signal", "gpg4win": "GnuPG.Gpg4win"}
WIN_NOMS = {"opensnitch": ("simplewall", "Pare-feu « appli par appli » : il te demande quand un programme veut se "
                                         "connecter à internet.")}
WIN_CHERCHE = {"librewolf": ["librewolf"], "mullvadb": ["mullvad browser"], "torbrowser": ["tor browser"],
               "brave": ["brave"], "opensnitch": ["simplewall"], "keepassxc": ["keepassxc"], "bitwarden": ["bitwarden"],
               "cryptomator": ["cryptomator"], "veracrypt": ["veracrypt"], "signal": ["signal"], "gpg4win": ["gpg4win"]}
if IS_WIN:
    TOOLS.append(dict(id="gpg4win", cat="donnees", ico="🔏", nom="Gpg4win (GnuPG)", flat="", check=["gpg"], pkgs={},
                      desc="Le chiffrement GnuPG pour Windows : il sert à la « Sauvegarde chiffrée » de Viki."))
    for _t in TOOLS:
        if _t["id"] in WIN_NOMS:
            _t["nom"], _t["desc"] = WIN_NOMS[_t["id"]]
CATS = [("nav", "🌐 Navigateurs"), ("reseau", "🧱 Réseau, Tor et pare-feu"), ("donnees", "🔐 Mots de passe, "
                                                                                       "sauvegardes, messages")]

EXTENSIONS = [  # (nom, description, firefox, chrome)
    ("uBlock Origin", "Bloque pubs, pisteurs et sites malveillants. Le n°1.",
     "https://addons.mozilla.org/firefox/addon/ublock-origin/",
     "https://chromewebstore.google.com/search/uBlock%20Origin%20Lite"),
    ("Privacy Badger", "Apprend à bloquer les pisteurs invisibles.",
     "https://addons.mozilla.org/firefox/addon/privacy-badger17/",
     "https://chromewebstore.google.com/search/Privacy%20Badger"),
    ("Bitwarden", "Remplit tes mots de passe en sécurité.", "https://addons.mozilla.org/firefox/addon/bitwarden-password-manager/",
     "https://chromewebstore.google.com/search/Bitwarden"),
    ("KeePassXC-Browser", "Relie le navigateur à KeePassXC.", "https://addons.mozilla.org/firefox/addon/keepassxc-browser/",
     "https://chromewebstore.google.com/search/KeePassXC-Browser"),
    ("ClearURLs", "Enlève les pisteurs collés dans les liens.", "https://addons.mozilla.org/firefox/addon/clearurls/",
     "https://chromewebstore.google.com/search/ClearURLs"),
]


def tool_installed(t):
    if IS_WIN and WO:
        return WO.est_installe(*WIN_CHERCHE.get(t["id"], [t["nom"]]))
    return any(shutil.which(x) for x in t["check"]) or (t.get("flat") and flatpak_has(t["flat"]))


def install_cmds(t):
    """Commandes à lancer dans le terminal pour installer (et activer) l'outil, ou [] si impossible ici."""
    if IS_WIN:
        return [WO.winget_installer(WINGET[t["id"]])] if WO and t["id"] in WINGET else []
    if paquets:
        return paquets.commandes(t.get("pkgs") or {}, t.get("flat", ""), t.get("post"), t.get("post_dnf"))[0]
    pm = pkg_manager()
    cmds = []
    if t["pkgs"].get(pm):
        p = " ".join(t["pkgs"][pm])
        cmds.append({"pacman": f"sudo pacman -S --needed {p}", "apt": f"sudo apt install -y {p}",
                     "dnf": f"sudo dnf install -y {p}", "zypper": f"sudo zypper install -y {p}"}[pm])
        cmds += t.get("post_dnf" if pm in ("dnf", "zypper") and t.get("post_dnf") else "post", [])
    elif t.get("flat") and (flatpak_ok() or pm):
        if not flatpak_ok():                                   # on installe d'abord Flatpak
            cmds.append({"pacman": "sudo pacman -S --needed flatpak", "apt": "sudo apt install -y flatpak",
                         "dnf": "sudo dnf install -y flatpak", "zypper": "sudo zypper install -y flatpak"}[pm])
        cmds.append("flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo")
        cmds.append(f"flatpak install --user -y flathub {t['flat']}")
    return cmds


# ------------------------------------------------------------------ ports et redirections
PORTS = dict(securite.PORTS) if securite else {}
PORTS.update({53: "DNS (résolution des noms)", 68: "DHCP (adresse réseau)", 1900: "UPnP (découverte de la box)",
              5355: "LLMNR (découverte réseau)", 9050: "Tor (proxy SOCKS)", 9150: "Navigateur Tor", 8188: "ComfyUI "
              "(atelier d'images de Viki)", 7860: "Stable Diffusion (Forge / A1111)", 1714: "KDE Connect",
              1716: "KDE Connect", 51413: "Transmission (torrent)", 6881: "torrent", 8384: "Syncthing (interface)",
              22000: "Syncthing", 3389: "bureau à distance (RDP)", 25565: "serveur Minecraft"})
RISQUES = set(securite.RISQUES) if securite else set()


def listening_ports():
    """-> [{proto, addr, port, prog, pid, expose, nom, risque}]"""
    if IS_WIN and WO:
        res, seen = [], set()
        for p in WO.ports():
            local = p["addr"].startswith("127.") or p["addr"] in ("::1",)
            key = (p["proto"], p["port"], local)
            if key in seen:
                continue
            seen.add(key)
            res.append(dict(p, expose=not local, nom=PORTS.get(p["port"], ""), risque=p["port"] in RISQUES and not local))
        return sorted(res, key=lambda r: (not r["expose"], not r["risque"], r["port"]))
    code, out = _run(["ss", "-tulnpH"], 8)
    res = []
    if code != 0:
        return res
    seen = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        m = re.match(r"^(.*):(\d+)$", parts[4])
        if not m:
            continue
        addr, port = m.group(1).strip("[]"), int(m.group(2))
        local = addr.startswith("127.") or addr in ("::1", "localhost") or "%lo" in addr
        pm = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        prog, pid = (pm.group(1), int(pm.group(2))) if pm else ("", 0)
        key = (parts[0], port, local)
        if key in seen:
            continue
        seen.add(key)
        res.append({"proto": parts[0], "addr": addr, "port": port, "prog": prog, "pid": pid, "expose": not local,
                    "nom": PORTS.get(port, ""), "risque": port in RISQUES and not local})
    return sorted(res, key=lambda r: (not r["expose"], not r["risque"], r["port"]))


def upnp_mappings():
    """Redirections ouvertes sur la box par UPnP -> (ip_externe, [{proto, ext, int_ip, int_port, desc}]) ou None."""
    if IS_WIN and WO:
        return WO.upnp()
    if not shutil.which("upnpc"):
        return None
    code, out = _run(["upnpc", "-l"], 15)
    ext = re.search(r"ExternalIPAddress = ([\d.]+)", out)
    maps = []
    for m in re.finditer(r"^\s*\d+\s+(TCP|UDP)\s+(\d+)->([\d.]+):(\d+)\s+'([^']*)'", out, re.M):
        maps.append({"proto": m.group(1), "ext": int(m.group(2)), "int_ip": m.group(3), "int_port": int(m.group(4)),
                     "desc": m.group(5)})
    if not maps and "No IGD UPnP Device" in out:
        return ("", [])
    return (ext.group(1) if ext else "", maps)


def gateway():
    if IS_WIN and WO:
        return WO.passerelle()
    code, out = _run(["ip", "route", "show", "default"], 4)
    m = re.search(r"default via ([\d.]+)", out)
    return m.group(1) if m else ""


def firewall_state():
    if IS_WIN and WO:
        on, _coupes = WO.pare_feu()
        return on, "Pare-feu Windows"                         # None : je n'ai pas pu vérifier
    for unit, nom in (("ufw", "ufw"), ("firewalld", "firewalld"), ("nftables", "nftables")):
        if _run(["systemctl", "is-active", unit], 4)[1].strip() == "active":
            return True, nom
    return False, ""


# ------------------------------------------------------------------ DNS
DNS = [  # id, nom, adresses (avec nom TLS), description
    ("quad9", "Quad9 (Suisse)", "9.9.9.9#dns.quad9.net 149.112.112.112#dns.quad9.net 2620:fe::fe#dns.quad9.net",
     "Bloque les sites malveillants, ne garde pas ton adresse IP. Bon choix par défaut."),
    ("mullvad", "Mullvad (Suède)", "194.242.2.2#dns.mullvad.net 2a07:e340::2#dns.mullvad.net",
     "Sans journaux, sans filtrage."),
    ("mullvad_adblock", "Mullvad + bloqueur de pubs", "194.242.2.3#adblock.dns.mullvad.net "
                                                       "2a07:e340::3#adblock.dns.mullvad.net",
     "Comme Mullvad, et bloque pubs et pisteurs pour tout le PC."),
    ("cloudflare", "Cloudflare", "1.1.1.1#cloudflare-dns.com 1.0.0.1#cloudflare-dns.com 2606:4700:4700::1111#cloudflare-dns.com",
     "Très rapide. Journaux effacés sous 24 h."),
    ("adguard", "AdGuard DNS", "94.140.14.14#dns.adguard-dns.com 94.140.15.15#dns.adguard-dns.com",
     "Bloque pubs et pisteurs pour tout le PC."),
]
DNS_FILE = "/etc/systemd/resolved.conf.d/viki-dns.conf"


def dns_status():
    """-> (texte lisible, chiffré ?)"""
    if IS_WIN and WO:
        return WO.dns_etat()
    if shutil.which("resolvectl"):
        code, out = _run(["resolvectl", "status"], 6)
        if code == 0:
            servers = re.findall(r"(?:Current DNS Server|DNS Servers):\s*(.+)", out)
            dot = "+DNSOverTLS" in out or re.search(r"DNSOverTLS[=:]\s*yes", out) is not None
            mine = Path(DNS_FILE).exists()
            return ("Serveurs : " + ", ".join(dict.fromkeys(s.strip() for s in servers)) if servers else
                    "Serveurs : ceux de ta box") + ("\nChiffré (DNS over TLS) : oui" if dot else
                                                     "\nChiffré : non") + ("\n(Réglé par Viki)" if mine else ""), dot
    try:
        ns = re.findall(r"^nameserver\s+(\S+)", Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace"), re.M)
        return "Serveurs : " + ", ".join(ns), False
    except Exception:
        return "Je n'ai pas pu lire tes réglages DNS.", False


def dns_cmds(dns_id):
    d = next(x for x in DNS if x[0] == dns_id)
    if IS_WIN and WO:
        ips = [a.split("#")[0] for a in d[2].split() if "." in a.split("#")[0]]
        return WO.dns_commandes(ips, WO.DOH.get(dns_id, ""))
    conf = f"[Resolve]\\nDNS={d[2]}\\nDNSOverTLS=yes\\nDomains=~.\\n"
    return ["sudo mkdir -p /etc/systemd/resolved.conf.d",
            f"printf '{conf}' | sudo tee {DNS_FILE} >/dev/null",
            "sudo systemctl enable --now systemd-resolved",
            "sudo ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf",
            "sudo systemctl restart systemd-resolved",
            "resolvectl status | head -20"]


def dns_reset_cmds():
    if IS_WIN and WO:
        return WO.dns_retour()
    return [f"sudo rm -f {DNS_FILE}", "sudo systemctl restart systemd-resolved", "resolvectl status | head -20"]


# ------------------------------------------------------------------ sauvegarde chiffrée
def backup_cmd(folder, dest_dir):
    folder, dest_dir = Path(folder), Path(dest_dir)
    import datetime
    out = dest_dir / f"{folder.name}-{datetime.date.today().isoformat()}.tar.gz.gpg"
    return (f"tar -czf - -C {shlex.quote(str(folder.parent))} {shlex.quote(folder.name)} | "
            f"gpg --symmetric --cipher-algo AES256 -o {shlex.quote(str(out))} && "
            f"echo && echo '✔ Sauvegarde chiffrée : {out}' && "
            f"echo 'Pour la récupérer : gpg -d \"{out.name}\" | tar -xzf -'"), out


# ------------------------------------------------------------------ fenêtre
class _Sig(QObject):
    done = pyqtSignal(object, object)


CSS = """
QFrame#carte { border: 1px solid palette(mid); border-radius: 12px; }
QLabel#titre { font-size: 11.5pt; font-weight: bold; }
QLabel#aide { color: palette(placeholder-text); }
QLabel#cmd { font-family: monospace; background: palette(alternate-base); border-radius: 6px; padding: 4px 6px; }
"""


class PrivacyWindow(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.setStyleSheet(CSS)
        self.setWindowTitle("🛡️ Vie privée et sécurité")
        self.resize(900, 700)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, r: fn(r))
        lay = QVBoxLayout(self)
        info = self._lab("Tout est en option. Rien n'est installé ni modifié sans ton clic : les commandes s'ouvrent "
                         "dans une fenêtre PowerShell, et Windows te demande la permission si besoin (jamais Viki)."
                         if IS_WIN else
                         "Tout est en option. Rien n'est installé ni modifié sans ton clic : les commandes s'ouvrent "
                         "dans un terminal où ton mot de passe est demandé (jamais par Viki).", "aide")
        lay.addWidget(info)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_bilan(), "🛡️ Bilan")
        self.tabs.addTab(self._tab_ports(), "🔌 Ports et redirections")
        self.tabs.addTab(self._tab_outils(), "🧰 Outils à installer")
        self.tabs.addTab(self._tab_dns(), "🌐 DNS et proxy")
        self.tabs.addTab(self._tab_backup(), "💾 Sauvegarde chiffrée")

    # ---------- utilitaires
    def _emit(self, fn, res):
        try:
            self.sig.done.emit(fn, res)
        except RuntimeError:
            pass

    def _bg(self, work, then):
        import threading

        def run():
            try:
                r = work()
            except Exception as e:
                r = e
            self._emit(then, r)
        threading.Thread(target=run, daemon=True).start()

    def _lab(self, txt, obj=""):
        l = QLabel(txt)
        l.setWordWrap(True)
        l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if obj:
            l.setObjectName(obj)
        return l

    def _card(self, lay):
        f = QFrame()
        f.setObjectName("carte")
        v = QVBoxLayout(f)
        lay.addWidget(f)
        return v

    def _scroll(self):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setSpacing(10)
        sc.setWidget(box)
        return sc, lay

    def terminal(self, cmds, titre="Viki", admin=False):
        """Lance les commandes dans un terminal visible (et arrête au premier échec)."""
        if IS_WIN:
            if WO and WO.terminal(cmds, titre, admin=admin):
                return self.comp.say("Je t'ai ouvert une fenêtre PowerShell : tout se passe là"
                                     + (", Windows te demande d'abord la permission." if admin else "."))
            QApplication.clipboard().setText("\n".join(cmds))
            return self.comp.say("Je n'ai pas pu ouvrir PowerShell. Les commandes sont copiées.")
        script = "echo '── " + titre.replace("'", "") + " ──'; echo; " + " && ".join(
            f"echo '$ {c.replace(chr(39), chr(34))}' && {c}" for c in cmds) + \
            "; echo; read -p 'Entrée pour fermer…'"
        g = getattr(self.C, "gestionpc", None)
        if g and g.terminal(script):
            self.comp.say("Je t'ai ouvert un terminal : tout se passe là, avec ton mot de passe si besoin.")
        else:
            QApplication.clipboard().setText("\n".join(cmds))
            self.comp.say("Je n'ai pas trouvé de terminal. Les commandes sont copiées : colle-les dans un terminal.")

    # ---------- bilan
    def _tab_bilan(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        b = QPushButton("🔍 Vérifier mon PC maintenant")
        b.setObjectName("principal")
        b.clicked.connect(self._run_bilan)
        row.addWidget(b)
        b = QPushButton("🆘 En cas de piratage")
        b.clicked.connect(lambda: self.bilan.setPlainText(securite.GUIDE if securite else ""))
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.bilan = QTextEdit()
        self.bilan.setReadOnly(True)
        self.bilan.setPlainText("Clique sur « Vérifier mon PC maintenant » : je regarde le pare-feu, les ports ouverts, "
                                "SSH, les mises à jour, le chiffrement du disque, le verrouillage de l'écran… "
                                "Je ne modifie rien.")
        v.addWidget(self.bilan, 1)
        return w

    def _run_bilan(self):
        if not securite:
            return
        self.bilan.setPlainText("Vérification en cours… (environ une minute)")
        files = self.comp._secret_files() if hasattr(self.comp, "_secret_files") else ()

        def then(res):
            if isinstance(res, Exception):
                return self.bilan.setPlainText(f"Je n'ai pas pu finir : {res}")
            self.bilan.setPlainText(securite.report_text(res))
            self.comp.say(securite.summary(res))
        self._bg(lambda: securite.run_all(files), then)

    # ---------- ports
    def _tab_ports(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        b = QPushButton("🔄 Actualiser")
        b.clicked.connect(self._load_ports)
        row.addWidget(b)
        self.fw = self._lab("")
        row.addWidget(self.fw, 1)
        self.b_fw = QPushButton("🧱 Activer un pare-feu")
        self.b_fw.clicked.connect(lambda: WO.ouvrir("windowsdefender://network") if IS_WIN and WO else
                                  self.install(next(t for t in TOOLS if t["id"] == "ufw")))
        row.addWidget(self.b_fw)
        v.addLayout(row)
        sc, self.p_lay = self._scroll()
        v.addWidget(sc, 1)
        self._load_ports()
        return w

    def _clear(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _load_ports(self):
        self._clear(self.p_lay)
        self.p_lay.addWidget(self._lab("Je regarde…", "aide"))
        self._bg(lambda: (listening_ports(), upnp_mappings(), firewall_state(), gateway()), self._show_ports)

    def _show_ports(self, r):
        self._clear(self.p_lay)
        if isinstance(r, Exception):
            self.p_lay.addWidget(self._lab(f"Erreur : {r}"))
            return
        ports, upnp, (fw_on, fw_name), gw = r
        self.fw.setText(f"✅ Pare-feu actif ({fw_name})" if fw_on else "❔ Je n'ai pas pu vérifier le pare-feu"
                        if fw_on is None else "⚠️ Aucun pare-feu actif")
        self.b_fw.setVisible(fw_on is False)
        expo = [p for p in ports if p["expose"]]
        loc = [p for p in ports if not p["expose"]]
        c = self._card(self.p_lay)
        c.addWidget(self._lab(f"🌍 Ouverts au réseau ({len(expo)})", "titre"))
        c.addWidget(self._lab("Les autres appareils de ton réseau (box, Wi-Fi) peuvent s'y connecter. Derrière une box, "
                              "internet n'y accède pas, sauf redirection (plus bas).", "aide"))
        if not expo:
            c.addWidget(self._lab("✅ Rien : c'est le plus sûr."))
        for p in expo:
            self._port_row(c, p)
        c = self._card(self.p_lay)
        c.addWidget(self._lab(f"🏠 Seulement pour ce PC ({len(loc)})", "titre"))
        c.addWidget(self._lab("Sans risque : seuls les programmes de ton PC peuvent s'y connecter.", "aide"))
        c.addWidget(self._lab("  ·  ".join(f"{p['port']} {p['prog'] or ''}".strip() for p in loc[:40]) or "—"))
        c = self._card(self.p_lay)
        c.addWidget(self._lab("📡 Redirections sur ta box (UPnP)", "titre"))
        c.addWidget(self._lab("Des applis (jeux, torrent, consoles…) peuvent demander à ta box d'ouvrir un port vers "
                              "internet. Celles-ci sont visibles depuis l'extérieur.", "aide"))
        if upnp is None and IS_WIN:
            c.addWidget(self._lab("Je n'ai pas pu interroger ta box (UPnP désactivé sur la box, ou réseau sans box)."))
        elif upnp is None:
            row = QHBoxLayout()
            row.addWidget(self._lab("Pour les voir, il me faut l'outil miniupnpc."), 1)
            b = QPushButton("📥 Installer miniupnpc")
            b.clicked.connect(lambda: self.install(next(t for t in TOOLS if t["id"] == "upnpc")))
            row.addWidget(b)
            c.addLayout(row)
        elif not upnp[1]:
            c.addWidget(self._lab("✅ Aucune redirection automatique (ou UPnP désactivé sur ta box — c'est bien)."))
        else:
            if upnp[0]:
                c.addWidget(self._lab(f"Ton adresse internet : {upnp[0]}"))
            for m in upnp[1]:
                row = QHBoxLayout()
                row.addWidget(self._lab(f"⚠️ {m['proto']} {m['ext']} → {m['int_ip']}:{m['int_port']}  "
                                        f"« {m['desc'] or 'sans nom'} »"), 1)
                b = QPushButton("Fermer")
                b.clicked.connect(lambda _=False, m=m: ((WO.upnp_fermer(m["ext"], m["proto"]) if IS_WIN and WO else
                                                         _run(["upnpc", "-d", str(m["ext"]), m["proto"]], 10)),
                                                        self._load_ports()))
                row.addWidget(b)
                c.addLayout(row)
        c.addWidget(self._lab("Les redirections réglées à la main dans ta box ne se voient que dans son interface.",
                              "aide"))
        if gw:
            b = QPushButton(f"🌐 Ouvrir l'interface de ma box ({gw})")
            b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"http://{gw}")))
            c.addWidget(b)
        self.p_lay.addStretch(1)

    def _port_row(self, c, p):
        row = QHBoxLayout()
        ico = "🚨" if p["risque"] else "🔸"
        row.addWidget(self._lab(f"{ico} {p['proto'].upper()} {p['port']} — {p['nom'] or 'service inconnu'}"
                                + (f"  ·  programme : {p['prog']}" if p["prog"] else "")
                                + ("\n   Ne devrait pas être ouvert au réseau sauf si tu en as besoin." if p["risque"] else "")),
                    1)
        if p["pid"]:
            try:
                mine = True if IS_WIN else Path(f"/proc/{p['pid']}").stat().st_uid == os.getuid()
            except Exception:
                mine = False
            if mine:
                b = QPushButton("Arrêter ce programme")
                b.clicked.connect(lambda _=False, pid=p["pid"], n=p["prog"]: self._kill(pid, n))
                row.addWidget(b)
            else:
                b = QPushButton("Désactiver le service…")
                b.clicked.connect(lambda _=False, n=p["prog"]: self._disable_service(n))
                row.addWidget(b)
        c.addLayout(row)

    def _kill(self, pid, name):
        if IS_WIN and WO:
            ok, msg = WO.arreter(pid)
            self.comp.say(f"J'ai arrêté {name}." if ok else f"Je n'ai pas pu arrêter {name} (c'est peut-être un "
                          "service de Windows : il faut les droits d'administrateur).")
            return self._load_ports()
        try:
            os.kill(pid, 15)
            self.comp.say(f"J'ai arrêté {name}.")
        except Exception as e:
            self.comp.say(f"Je n'ai pas pu arrêter {name} : {e}")
        self._load_ports()

    def _disable_service(self, name):
        unit = {"sshd": "sshd", "cupsd": "cups", "smbd": "smb", "nmbd": "nmb", "rpcbind": "rpcbind",
                "avahi-daemon": "avahi-daemon", "mysqld": "mysqld", "mariadbd": "mariadb", "postgres": "postgresql",
                "redis-server": "redis", "ollama": "ollama", "xrdp": "xrdp"}.get(name, name)
        self.terminal([f"systemctl status {unit} --no-pager | head -5", f"sudo systemctl disable --now {unit}"],
                      f"Désactiver le service {unit}")

    # ---------- outils
    def _tab_outils(self):
        sc, lay = self._scroll()
        if IS_WIN:
            lay.addWidget(self._lab(f"💻 {WO.version_windows() if WO else 'Windows'} · installation par winget (le "
                                    "gestionnaire d'applications de Windows). Clique sur « Installer » : une fenêtre "
                                    "PowerShell s'ouvre et montre la commande. Le pare-feu et l'antivirus sont déjà "
                                    "dans Windows (Sécurité Windows).", "aide"))
        else:
            pm = pkg_manager()
            nom = paquets.nom_systeme() if paquets else "Linux"
            via = (paquets.NOMS.get(pm, pm) if paquets else pm) or ""
            lay.addWidget(self._lab(f"💻 {nom} · installation par {via}{' et Flatpak' if via and pm else ''}"
                                    f"{' (système immuable : Flatpak en priorité)' if paquets and paquets.immuable() else ''}. "
                                    "Clique sur « Installer » : un terminal s'ouvre et montre chaque commande.", "aide"))
        self.tool_btns = {}
        for key, titre in CATS:
            lay.addWidget(self._lab(titre, "titre"))
            for t in [x for x in TOOLS if x["cat"] == key and (not IS_WIN or x["id"] in WINGET)]:
                c = self._card(lay)
                row = QHBoxLayout()
                row.addWidget(self._lab(f"<b>{t['ico']} {t['nom']}</b>"), 1)
                st = QLabel("…")
                row.addWidget(st)
                b = QPushButton("📥 Installer")
                b.clicked.connect(lambda _=False, t=t: self.install(t))
                row.addWidget(b)
                c.addLayout(row)
                c.addWidget(self._lab(t["desc"], "aide"))
                self.tool_btns[t["id"]] = (st, b)
        lay.addWidget(self._lab("🧩 Extensions pour ton navigateur", "titre"))
        for nom, desc, ff, ch in EXTENSIONS:
            c = self._card(lay)
            row = QHBoxLayout()
            row.addWidget(self._lab(f"<b>{nom}</b> — {desc}"), 1)
            for lab, url in (("Firefox / LibreWolf", ff), ("Chrome / Brave", ch)):
                b = QPushButton(lab)
                b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                row.addWidget(b)
            c.addLayout(row)
        lay.addStretch(1)
        self._bg(lambda: {t["id"]: tool_installed(t) for t in TOOLS if t["id"] in self.tool_btns}, self._tools_state)
        return sc

    def _tools_state(self, st):
        if isinstance(st, Exception):
            return
        for tid, ok in st.items():
            lab, b = self.tool_btns[tid]
            t = next(x for x in TOOLS if x["id"] == tid)
            can = bool(install_cmds(t))
            lab.setText("✅ Installé" if ok else ("" if can else "non disponible ici"))
            b.setVisible(not ok and can)

    def install(self, t):
        cmds = install_cmds(t)
        note = paquets.commandes(t.get("pkgs") or {}, t.get("flat", ""), t.get("post"), t.get("post_dnf"))[1] \
            if paquets and not IS_WIN else ""
        if not cmds:
            return self.comp.say(note or f"Je ne sais pas installer {t['nom']} sur ton système. Cherche-le sur "
                                         "flathub.org.")
        self.terminal(cmds, f"Installer {t['nom']}")
        if note:
            self.comp.say(note)

    # ---------- DNS et proxy
    def _tab_dns(self):
        sc, lay = self._scroll()
        c = self._card(lay)
        c.addWidget(self._lab("🌐 DNS chiffré", "titre"))
        c.addWidget(self._lab("Le DNS traduit les noms de sites en adresses. Par défaut, c'est ta box ou ton fournisseur "
                              "qui le fait, en clair : ils voient tous les sites que tu visites. Un DNS chiffré "
                              "(DNS over TLS) les cache.", "aide"))
        self.dns_lab = self._lab("…")
        c.addWidget(self.dns_lab)
        row = QHBoxLayout()
        self.dns_combo = QComboBox()
        for did, nom, _a, desc in DNS:
            self.dns_combo.addItem(nom, did)
        row.addWidget(self.dns_combo, 1)
        b = QPushButton("✅ Utiliser ce DNS chiffré")
        b.setObjectName("principal")
        b.clicked.connect(lambda: self.terminal(dns_cmds(self.dns_combo.currentData()), "DNS chiffré", admin=IS_WIN))
        row.addWidget(b)
        b = QPushButton("↩️ Revenir comme avant")
        b.clicked.connect(lambda: self.terminal(dns_reset_cmds(), "DNS par défaut", admin=IS_WIN))
        row.addWidget(b)
        c.addLayout(row)
        self.dns_desc = self._lab("", "aide")
        c.addWidget(self.dns_desc)
        self.dns_combo.currentIndexChanged.connect(lambda i: self.dns_desc.setText(DNS[i][3]))
        self.dns_desc.setText(DNS[0][3])
        c.addWidget(self._lab("Règle les cartes réseau de Windows (Windows te demande la permission). Le chiffrement "
                              "(DNS over HTTPS) se fait sous Windows 11 ; sous Windows 10, seul le serveur change. "
                              "Si un site ne marche plus, « Revenir comme avant » annule tout." if IS_WIN else
                              "Utilise systemd-resolved (le standard sur Arch, Fedora, Ubuntu). Si un site ne marche "
                              "plus, « Revenir comme avant » annule tout.", "aide"))
        b = QPushButton("🔄 Vérifier mes DNS")
        b.clicked.connect(self._load_dns)
        c.addWidget(b)
        # proxy
        c = self._card(lay)
        c.addWidget(self._lab("🔀 Proxy", "titre"))
        c.addWidget(self._lab("Un proxy fait passer tes connexions par un autre serveur. Pour l'anonymat, préfère le "
                              "navigateur Tor ou Mullvad Browser (onglet « Outils »).", "aide"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Proxy pour les recherches de Viki (actu, musique, images…) :"))
        self.proxy = QLineEdit(self.comp.cfg.get("proxy_viki", ""))
        self.proxy.setPlaceholderText("http://adresse:port  (vide = aucun)")
        row.addWidget(self.proxy, 1)
        b = QPushButton("Enregistrer")
        b.clicked.connect(self._save_proxy)
        row.addWidget(b)
        c.addLayout(row)
        if IS_WIN:
            b = QPushButton("⚙️ Proxy de tout le système (Paramètres de Windows)")
            b.clicked.connect(lambda: WO.ouvrir("ms-settings:network-proxy") if WO else None)
            c.addWidget(b)
        else:
            b = QPushButton("⚙️ Proxy de tout le système (réglages KDE)")
            b.clicked.connect(lambda: subprocess.Popen(["systemsettings", "kcm_proxy"], env=_env(), start_new_session=True)
                              if shutil.which("systemsettings") else self.comp.say("Ouvre les réglages réseau de ton bureau."))
            c.addWidget(b)
            tor_on = _run(["systemctl", "is-active", "tor"], 4)[1].strip() == "active"
            c.addWidget(self._lab("🧅 Service Tor : " + ("actif — proxy SOCKS sur 127.0.0.1:9050" if tor_on else
                                                         "pas actif (onglet « Outils » → Tor)")))
        lay.addStretch(1)
        self._load_dns()
        return sc

    def _load_dns(self):
        self._bg(dns_status, lambda r: self.dns_lab.setText(r[0] if not isinstance(r, Exception) else str(r)))

    def _save_proxy(self):
        v = self.proxy.text().strip()
        if v and not re.match(r"^https?://[\w.\-]+(:\d+)?/?$", v):
            return self.comp.say("Le proxy doit ressembler à http://adresse:port")
        self.comp.cfg["proxy_viki"] = v
        self.C.save_config(self.comp.cfg)
        apply_proxy(v)
        self.comp.say("Proxy enregistré." if v else "Plus de proxy pour mes recherches.")

    # ---------- sauvegarde chiffrée
    def _tab_backup(self):
        sc, lay = self._scroll()
        c = self._card(lay)
        c.addWidget(self._lab("💾 Chiffrer un dossier", "titre"))
        c.addWidget(self._lab("Je crée une archive chiffrée (AES-256, avec GnuPG) du dossier choisi. Sans ton mot de "
                              "passe, personne ne peut l'ouvrir — toi non plus si tu l'oublies !", "aide"))
        row = QHBoxLayout()
        self.src = QLineEdit(str(Path.home() / "Documents"))
        row.addWidget(QLabel("Dossier :"))
        row.addWidget(self.src, 1)
        b = QPushButton("📂")
        b.clicked.connect(lambda: self._pick(self.src))
        row.addWidget(b)
        c.addLayout(row)
        row = QHBoxLayout()
        self.dst = QLineEdit(str(Path.home()))
        row.addWidget(QLabel("Où la ranger :"))
        row.addWidget(self.dst, 1)
        b = QPushButton("📂")
        b.clicked.connect(lambda: self._pick(self.dst))
        row.addWidget(b)
        c.addLayout(row)
        b = QPushButton("🔒 Créer la sauvegarde chiffrée")
        b.setObjectName("principal")
        b.clicked.connect(self._backup)
        c.addWidget(b)
        c.addWidget(self._lab("Astuce : range-la sur un disque externe ou dans ton cloud. Pour un coffre chiffré dans "
                              "ton cloud, installe Cryptomator (onglet « Outils »)." if IS_WIN else
                              "Astuce : range-la sur un disque externe ou dans ton cloud. Pour des sauvegardes "
                              "automatiques et chiffrées, installe Pika Backup ou Vorta (onglet « Outils »).", "aide"))
        c = self._card(lay)
        c.addWidget(self._lab("🔓 Récupérer une sauvegarde", "titre"))
        b = QPushButton("Choisir un fichier .gpg…")
        b.clicked.connect(self._restore)
        c.addWidget(b)
        lay.addStretch(1)
        return sc

    def _pick(self, ed):
        d = QFileDialog.getExistingDirectory(self, "Choisir un dossier", ed.text() or str(Path.home()))
        if d:
            ed.setText(d)

    def _backup(self):
        src, dst = Path(self.src.text().strip()), Path(self.dst.text().strip())
        if not src.is_dir() or not dst.is_dir():
            return self.comp.say("Choisis un dossier à sauvegarder et un dossier où la ranger.")
        if IS_WIN:
            g = WO.gpg() if WO else ""
            if not g:
                return self.comp.ask_yes("Pour chiffrer, il me faut Gpg4win (GnuPG pour Windows, gratuit). Je l'installe "
                                         "avec winget ? (oui / non)",
                                         lambda: self.terminal([WO.winget_installer("GnuPG.Gpg4win")], "Installer Gpg4win"))
            import datetime as _dt
            out = dst / f"{src.name}-{_dt.date.today().isoformat()}.zip.gpg"
            q = lambda x: "'" + str(x).replace("'", "''") + "'"
            tout = q(str(src) + "\\*")
            return self.terminal(["$z = Join-Path $env:TEMP 'viki-sauvegarde.zip'",
                                  f"Compress-Archive -Path {tout} -DestinationPath $z -Force",
                                  f"& {q(g)} --symmetric --cipher-algo AES256 -o {q(out)} $z",
                                  "Remove-Item $z -Force",
                                  f"Write-Host ('Sauvegarde chiffrée : ' + {q(out)}) -ForegroundColor Green"],
                                 "Sauvegarde chiffrée")
        if not shutil.which("gpg"):
            return self.comp.say("Il me faut GnuPG (gpg). Installe-le : " +
                                 (paquets.texte_installer({"pacman": ["gnupg"], "apt": ["gnupg"], "dnf": ["gnupg2"],
                                                           "zypper": ["gpg2"], "xbps": ["gnupg"], "apk": ["gnupg"],
                                                           "eopkg": ["gnupg"], "emerge": ["app-crypt/gnupg"]})
                                  if paquets else "« sudo pacman -S gnupg »") + ".")
        cmd, out = backup_cmd(src, dst)
        self.terminal([cmd], "Sauvegarde chiffrée")

    def _restore(self):
        f, _ = QFileDialog.getOpenFileName(self, "Sauvegarde chiffrée", str(Path.home()), "Sauvegardes (*.gpg)")
        if not f:
            return
        d = QFileDialog.getExistingDirectory(self, "Où la déchiffrer ?", str(Path(f).parent))
        if d and IS_WIN:
            g = WO.gpg() if WO else ""
            if not g:
                return self.comp.say("Il me faut Gpg4win pour la déchiffrer (onglet « Outils »).")
            q = lambda x: "'" + str(x).replace("'", "''") + "'"
            return self.terminal(["$z = Join-Path $env:TEMP 'viki-recup.zip'",
                                  f"& {q(g)} -o $z -d {q(f)}",
                                  f"Expand-Archive -Path $z -DestinationPath {q(d)} -Force",
                                  "Remove-Item $z -Force", f"Write-Host ('Récupérée dans ' + {q(d)}) -ForegroundColor Green"],
                                 "Récupérer une sauvegarde")
        if d:
            self.terminal([f"cd {shlex.quote(d)}", f"gpg -d {shlex.quote(f)} | tar -xzf -",
                           "echo '✔ Récupérée dans ' $(pwd)"], "Récupérer une sauvegarde")


def apply_proxy(v):
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        if v:
            os.environ[k] = v
        elif os.environ.get("VIKI_PROXY_SET"):
            os.environ.pop(k, None)
    if v:
        os.environ["VIKI_PROXY_SET"] = "1"


# ------------------------------------------------------------------ Wikipédia
WIKI_Q = re.compile(r"^(?:c'?est quoi|qu'?est[- ]ce que c'?est(?: que)?|qu'?est[- ]ce qu'?(?:un|une|le|la|les)|"
                    r"qu'?est[- ]ce que|qui (?:est|etait|était|a (?:invente|inventé|cree|créé|ecrit|écrit|decouvert|découvert))|"
                    r"quand (?:a|est|était|etait)|ou (?:se trouve|est situe|est située|est)|où (?:se trouve|est)|"
                    r"comment (?:fonctionne|marche)|explique[- ]moi|parle[- ]moi (?:de|du|des|d')|"
                    r"tu connais|dis[- ]moi (?:ce qu'?est|qui est))\s+(.+?)\s*\??$", re.I)


def wiki_subject(text):
    """« c'est quoi un trou noir ? » -> « trou noir » (ou None si ce n'est pas une question de culture)."""
    m = WIKI_Q.match(text.strip())
    if not m:
        return None
    s = m.group(1).strip(" ?!.")
    s = re.sub(r"^(?:un |une |le |la |les |l'|du |de la |des |d')", "", s, flags=re.I)
    s = re.sub(r"\s+(?:exactement|en fait|stp|svp|s'il te pla[iî]t)$", "", s, flags=re.I)
    if not s or len(s.split()) > 7 or re.search(r"\b(?:tu|toi|moi|je|mon|ma|mes|ton|ta|tes)\b", s, re.I):
        return None
    return s


def wiki_url(subject, lang="fr"):
    import urllib.parse
    return f"https://{lang}.wikipedia.org/w/index.php?search=" + urllib.parse.quote(subject)
