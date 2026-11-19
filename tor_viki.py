"""Tor pour la vie privée : installation (dans un terminal visible), démarrage d'un Tor réservé à Viki avec des
réglages prudents, et son état en temps réel. Rien ne démarre tout seul : tout part d'un clic."""
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import gestionpc

SOCKS, CONTROL = 9250, 9251          # (Tor Browser utilise 9150/9151 : pas de conflit)
DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "viki" / "tor"
TORRC = """# Tor de Viki — réglages prudents pour la vie privée (fichier créé par Viki)
SocksPort 127.0.0.1:{socks} IsolateDestAddr IsolateDestPort
ControlPort 127.0.0.1:{control}
CookieAuthentication 1
DataDirectory {data}
ClientOnly 1
ExitRelay 0
SafeSocks 1
SafeLogging 1
AvoidDiskWrites 1
Log notice stdout
"""
EXPLIQUE = (
    ("SocksPort … IsolateDestAddr", "chaque site passe par un chemin différent : plus dur de relier tes visites"),
    ("ClientOnly / ExitRelay 0", "ton PC ne sert jamais de relais pour les autres"),
    ("SafeSocks", "refuse les programmes qui feraient fuiter les noms de sites (fuite DNS)"),
    ("SafeLogging / AvoidDiskWrites", "aucune adresse dans les journaux, le moins de traces possible sur le disque"),
    ("127.0.0.1 seulement", "seul ton PC peut utiliser ce Tor, personne sur ton réseau"),
)


def tor_exe():
    return shutil.which("tor") or next((p for p in ("/usr/sbin/tor", "/usr/bin/tor") if os.path.exists(p)), None)


def browser_exe():
    for n in ("torbrowser-launcher", "tor-browser", "torbrowser"):
        e = shutil.which(n)
        if e:
            return e
    return None


def install_cmd():
    try:
        import paquets
        cmds, _note = paquets.commandes({"pacman": ["tor", "torbrowser-launcher"], "apt": ["tor", "torbrowser-launcher"],
                                         "dnf": ["tor", "torbrowser-launcher"], "zypper": ["tor", "torbrowser-launcher"],
                                         "xbps": ["tor", "torbrowser-launcher"], "apk": ["tor"], "eopkg": ["tor"],
                                         "emerge": ["net-vpn/tor"]})
        if cmds:
            return " && ".join(("sudo apt update && " + c) if c.startswith("sudo apt install") else c for c in cmds)
    except Exception:
        pass
    d = gestionpc.distro()
    cmd = {"arch": "sudo pacman -S --needed tor torbrowser-launcher",
           "debian": "sudo apt update && sudo apt install -y tor torbrowser-launcher",
           "fedora": "sudo dnf install -y tor torbrowser-launcher"}.get(d)
    return cmd


def install():
    """Ouvre un terminal visible avec la commande d'installation. -> (ok, message)"""
    cmd = install_cmd()
    if not cmd:
        return False, ("Je ne connais pas la commande d'installation pour ton système. Installe les paquets « tor » "
                       "et « torbrowser-launcher » avec ton gestionnaire de logiciels.")
    full = (f"echo 'Viki va lancer :  {cmd}'; echo; echo 'Tor (le réseau) + Tor Browser (le navigateur).'; echo; "
            f"{cmd}; echo; echo 'Terminé. Tu peux fermer cette fenêtre.'; read -r _")
    if gestionpc.terminal(full):
        return True, "J'ai ouvert un terminal : tape ton mot de passe pour installer, puis reviens ici."
    return False, f"Je ne trouve pas de terminal. Lance toi-même : {cmd}"


class Tor:
    def __init__(self):
        self.proc, self.pct, self.etape, self.log = None, 0, "", []
        self.t0 = 0.0
        self._io = (0, 0, 0.0)
        self.debit = (0.0, 0.0)
        self.total = (0, 0)
        self.circuits = 0
        self.ip = None                   # {"ip":…, "tor": bool} après « Vérifier »
        self.erreur = ""

    # ------------------------------------------------ démarrer / arrêter
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        exe = tor_exe()
        if not exe:
            raise RuntimeError("Tor n'est pas installé : clique d'abord sur « Installer Tor ».")
        if self.running():
            return
        DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(DIR, 0o700)
        rc = DIR / "torrc"
        rc.write_text(TORRC.format(socks=SOCKS, control=CONTROL, data=DIR / "data"), encoding="utf-8")
        os.chmod(rc, 0o600)
        env = dict(os.environ)
        for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)
        if os.environ.get("COMPAGNON_ORIG_LD"):
            env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
        self.pct, self.etape, self.log, self.erreur, self.ip = 0, "Démarrage…", [], "", None
        self.t0 = time.monotonic()
        self.proc = subprocess.Popen([exe, "-f", str(rc)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, env=env, start_new_session=True)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except Exception:
                p.kill()
        self.pct, self.etape, self.debit, self.circuits = 0, "", (0.0, 0.0), 0

    ETAPES = (("conn", "Connexion à un premier relais"), ("handshake", "Poignée de main chiffrée"),
              ("onehop", "Premier relais joint"), ("requesting", "Je demande la carte du réseau"),
              ("loading", "Je reçois la carte du réseau"), ("enough_dirinfo", "J'ai la carte du réseau"),
              ("ap_", "Je construis un chemin à 3 relais"), ("circuit_create", "Je construis un chemin à 3 relais"),
              ("done", "Connectée au réseau Tor"))

    def _read(self, p):
        for line in p.stdout:
            line = line.rstrip()
            m = re.search(r"Bootstrapped (\d+)%\s*\(([\w_]+)\)", line)
            if m:
                self.pct = int(m.group(1))
                tag = m.group(2)
                self.etape = next((fr for k, fr in self.ETAPES if tag.startswith(k)), tag)
            msg = re.sub(r"^\w{3} \d+ [\d:.]+ ", "", line)
            if "[warn]" in msg or "[err]" in msg:
                if "Address already in use" in msg or "Could not bind" in msg:
                    self.erreur = ("Un autre Tor utilise déjà mes ports. Ferme l'autre, ou redémarre Viki.")
                elif "clock" in msg.lower():
                    self.erreur = "L'heure de ton PC semble fausse : Tor en a besoin. Règle l'heure, puis relance."
            if "control connection" in msg:              # mes propres mesures : pas la peine de les afficher
                continue
            self.log.append((time.strftime("%H:%M:%S"), msg))
            del self.log[:-200]
        if self.proc is p and not self.erreur and self.pct < 100:
            self.erreur = "Tor s'est arrêté tout seul. Regarde les dernières lignes du journal."

    # ------------------------------------------------ port de contrôle
    def _ctl(self, *cmds):
        cookie = (DIR / "data" / "control_auth_cookie").read_bytes().hex()
        out = []
        with socket.create_connection(("127.0.0.1", CONTROL), timeout=3) as s:
            f = s.makefile("rw", newline="\r\n")
            for c in (f"AUTHENTICATE {cookie}",) + cmds:
                f.write(c + "\r\n")
                f.flush()
                rep = []
                while True:
                    line = f.readline().rstrip("\r\n")
                    if not line:
                        break
                    rep.append(line)
                    if re.match(r"^\d{3} ", line):
                        break
                out.append(rep)
        return out[1:]

    def poll(self):
        """À appeler chaque seconde : débit et nombre de chemins."""
        if not self.running() or self.pct < 5:
            return
        try:
            r, w, c = self._ctl("GETINFO traffic/read", "GETINFO traffic/written", "GETINFO circuit-status")
            rd = int(r[0].split("=")[1])
            wr = int(w[0].split("=")[1])
            now = time.monotonic()
            r0, w0, t0 = self._io
            if t0:
                dt = max(0.2, now - t0)
                self.debit = (max(0, rd - r0) / dt, max(0, wr - w0) / dt)
            self._io, self.total = (rd, wr, now), (rd, wr)
            self.circuits = sum(1 for l in c if " BUILT " in l)
        except Exception:
            pass

    def newnym(self):
        self._ctl("SIGNAL NEWNYM")
        self.ip = None

    # ------------------------------------------------ vérifier la sortie
    def check_ip(self):
        """Demande à torproject.org, À TRAVERS Tor, l'adresse que voient les sites. -> {"ip", "tor"}"""
        host = "check.torproject.org"
        s = socket.create_connection(("127.0.0.1", SOCKS), timeout=15)
        try:
            s.sendall(b"\x05\x01\x00")
            if s.recv(2) != b"\x05\x00":
                raise RuntimeError("Tor a refusé la connexion")
            h = host.encode()
            s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + (443).to_bytes(2, "big"))
            rep = s.recv(10)
            if len(rep) < 2 or rep[1] != 0:
                raise RuntimeError("Tor n'a pas pu joindre le site de vérification (réessaie dans un instant)")
            s.settimeout(30)
            t = ssl.create_default_context().wrap_socket(s, server_hostname=host)
            t.sendall(f"GET /api/ip HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\n"
                      "Connection: close\r\n\r\n".encode())
            data = b""
            while True:
                b = t.recv(4096)
                if not b:
                    break
                data += b
            body = data.split(b"\r\n\r\n", 1)[1].decode(errors="ignore")
            d = json.loads(body[body.index("{"):body.rindex("}") + 1])
            self.ip = {"ip": d.get("IP", "?"), "tor": bool(d.get("IsTor"))}
            return self.ip
        finally:
            try:
                s.close()
            except Exception:
                pass


def make_window(comp):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                                 QVBoxLayout)
    human = gestionpc.human

    class Win(QDialog):
        def __init__(self):
            super().__init__()
            self.tor = Tor()
            self.setWindowTitle("Tor — vie privée")
            self.resize(640, 640)
            L = QVBoxLayout(self)
            t = QLabel("<b style='font-size:14pt'>🧅 Tor — vie privée</b><br>Tor fait passer ta connexion par 3 relais "
                       "chiffrés : les sites ne voient pas ton adresse, et ton fournisseur ne voit pas où tu vas.")
            t.setWordWrap(True)
            L.addWidget(t)
            self.etat = QLabel()
            self.etat.setWordWrap(True)
            self.etat.setStyleSheet("font-size: 12pt;")
            L.addWidget(self.etat)
            self.bar = QProgressBar()
            L.addWidget(self.bar)
            self.vivant = QLabel()
            self.vivant.setWordWrap(True)
            L.addWidget(self.vivant)
            h = QHBoxLayout()
            self.b_inst = QPushButton("⬇️ Installer Tor")
            self.b_inst.clicked.connect(self.install)
            self.b_go = QPushButton("▶ Démarrer Tor")
            self.b_go.clicked.connect(self.toggle)
            self.b_new = QPushButton("🔄 Nouvelle identité")
            self.b_new.setToolTip("Change de chemin : les sites verront une autre adresse.")
            self.b_new.clicked.connect(self.newnym)
            self.b_ip = QPushButton("🔍 Vérifier mon adresse")
            self.b_ip.setToolTip("Demande à torproject.org, à travers Tor, quelle adresse voient les sites.")
            self.b_ip.clicked.connect(self.check)
            self.b_nav = QPushButton("🌐 Ouvrir Tor Browser")
            self.b_nav.clicked.connect(self.browser)
            for b in (self.b_inst, self.b_go, self.b_new, self.b_ip, self.b_nav):
                h.addWidget(b)
            L.addLayout(h)
            self.msg = QLabel()
            self.msg.setWordWrap(True)
            L.addWidget(self.msg)
            L.addWidget(QLabel("<b>Ce que Tor fait en ce moment</b> (en direct)"))
            self.logv = QPlainTextEdit()
            self.logv.setReadOnly(True)
            self.logv.setMaximumBlockCount(300)
            L.addWidget(self.logv, 1)
            info = QLabel(
                "<b>À savoir</b><br>• Pour naviguer, utilise <b>Tor Browser</b> : ton navigateur habituel ne passe "
                "<b>pas</b> par Tor.<br>• Un autre programme peut passer par Tor en réglant son proxy SOCKS5 sur "
                f"<b>127.0.0.1</b>, port <b>{SOCKS}</b>.<br>• Tor cache ton adresse, pas ton identité : si tu te connectes "
                "à ton compte, le site sait que c'est toi.<br>• C'est plus lent qu'une connexion normale, c'est "
                "normal.<br><b>Mes réglages</b> : " + " · ".join(f"{b}" for _a, b in EXPLIQUE) + ".")
            info.setWordWrap(True)
            info.setStyleSheet("color: gray;")
            L.addWidget(info)
            self.nlog = 0
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.refresh()

        def install(self):
            ok, m = install()
            self.msg.setText(("ℹ️ " if ok else "❌ ") + m)

        def toggle(self):
            try:
                if self.tor.running():
                    self.tor.stop()
                    self.msg.setText("Tor est arrêté.")
                else:
                    self.logv.clear()
                    self.nlog = 0
                    self.tor.start()
                    self.msg.setText("")
            except Exception as e:
                self.msg.setText(f"❌ {e}")
            self.refresh()

        def newnym(self):
            try:
                self.tor.newnym()
                self.msg.setText("🔄 Nouveau chemin demandé : les prochaines connexions sortiront ailleurs.")
            except Exception as e:
                self.msg.setText(f"❌ Je n'ai pas pu changer d'identité : {str(e)[:80]}")

        def check(self):
            self.msg.setText("🔍 Je demande à torproject.org, à travers Tor…")
            self.b_ip.setEnabled(False)

            def done(r):
                self.b_ip.setEnabled(True)
                if isinstance(r, Exception):
                    return self.msg.setText(f"❌ {str(r)[:160]}")
                self.msg.setText((f"✅ Les sites voient l'adresse <b>{r['ip']}</b>, qui est bien une sortie Tor : "
                                  "ce n'est pas la tienne.") if r["tor"] else
                                 (f"⚠️ Les sites voient <b>{r['ip']}</b> et ce n'est PAS une sortie Tor. Ne te fie "
                                  "pas à cette connexion."))
            comp._bg(self.tor.check_ip, done)

        def browser(self):
            exe = browser_exe()
            if not exe:
                return self.msg.setText("Tor Browser n'est pas installé : clique sur « Installer Tor ».")
            env = dict(os.environ)
            for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
                env.pop(k, None)
            subprocess.Popen([exe], env=env, start_new_session=True, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.msg.setText("J'ouvre Tor Browser (la première fois, il se télécharge tout seul).")

        def refresh(self):
            t = self.tor
            inst = bool(tor_exe())
            run = t.running()
            self.b_inst.setVisible(not inst or not browser_exe())
            self.b_inst.setText("⬇️ Installer Tor" if not inst else "⬇️ Installer Tor Browser")
            self.b_go.setEnabled(inst)
            self.b_go.setText("■ Arrêter Tor" if run else "▶ Démarrer Tor")
            ok = run and t.pct >= 100
            self.b_new.setEnabled(ok)
            self.b_ip.setEnabled(ok and self.b_ip.isEnabled() or ok)
            if run:
                t.poll()
            self.bar.setVisible(run)
            self.bar.setValue(t.pct)
            if not inst:
                self.etat.setText("⚪ Tor n'est pas installé sur ce PC.")
            elif t.erreur:
                self.etat.setText(f"🔴 {t.erreur}")
            elif not run:
                self.etat.setText("⚪ Tor est arrêté. Rien ne passe par Tor pour l'instant.")
            elif ok:
                self.etat.setText("🟢 <b>Connectée au réseau Tor.</b>")
            else:
                self.etat.setText(f"🟠 Connexion en cours… {t.pct} % — {t.etape}")
            if run:
                d, u = t.debit
                self.vivant.setText(
                    f"⏱ depuis {int((time.monotonic() - t.t0) // 60)} min {int(time.monotonic() - t.t0) % 60:02d} s"
                    f" · 🔗 {t.circuits} chemin{'s' if t.circuits > 1 else ''} prêt{'s' if t.circuits > 1 else ''}"
                    f" · ⬇ {human(d)}/s · ⬆ {human(u)}/s"
                    f" · total ⬇ {human(t.total[0])} ⬆ {human(t.total[1])}"
                    + (f" · sortie : {t.ip['ip']}" if t.ip else ""))
            else:
                self.vivant.setText("")
            for h, m in t.log[self.nlog:]:
                self.logv.appendPlainText(f"{h}  {m}")
            self.nlog = len(t.log)

        def shutdown(self):
            self.timer.stop()
            self.tor.stop()
    return Win()
