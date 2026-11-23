"""🖱️ Les deux boutons de la souris en même temps (gauche + droit) -> la roue de Viki, n'importe où.

Sous Wayland, une appli ne peut pas voir les clics faits dans les autres fenêtres. On lit donc directement les
événements des SOURIS (/dev/input/event*, jamais le clavier), ce qui demande d'être dans le groupe « input ».
Si ce n'est pas le cas, Viki propose la commande (dans un terminal visible, après ton clic).
"""
import os
import re
import select
import struct
import threading
import time

FMT = "llHHi"                      # struct input_event (64 bits) : temps (2 × long), type, code, valeur
TAILLE = struct.calcsize(FMT)
EV_KEY, BTN_LEFT, BTN_RIGHT = 0x01, 0x110, 0x111


def souris():
    """Les fichiers /dev/input/eventN des souris et pavés tactiles (pas les claviers)."""
    out = []
    try:
        blocs = open("/proc/bus/input/devices", encoding="utf-8", errors="ignore").read().split("\n\n")
    except OSError:
        return out
    for b in blocs:
        h = re.search(r"^H: Handlers=(.*)$", b, re.M)
        if not h or "mouse" not in h.group(1):
            continue
        nom = re.search(r'^N: Name="(.*)"$', b, re.M)
        if nom and re.search(r"keyboard|clavier", nom.group(1), re.I):
            continue                                       # jamais un clavier (on ne lit que les boutons de souris)
        m = re.search(r"\bevent(\d+)\b", h.group(1))
        if m:
            out.append(f"/dev/input/event{m.group(1)}")
    return out


def diagnostic():
    """Pour le journal : les souris vues, lisibles ou non, et les groupes."""
    import grp
    import pwd
    devs = souris()
    lis = [d for d in devs if os.access(d, os.R_OK)]
    try:
        actifs = sorted(grp.getgrgid(g).gr_name for g in os.getgroups())
    except Exception:
        actifs = []
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
        compte = sorted(g.gr_name for g in grp.getgrall() if user in g.gr_mem)
    except Exception:
        compte = []
    return {"souris": devs, "lisibles": lis, "groupes_session": actifs, "groupes_compte": compte,
            "reconnexion": "input" in compte and "input" not in actifs}


def accessible():
    """-> (ok, raison) : peut-on lire les souris ?"""
    devs = souris()
    if not devs:
        return False, "aucune souris trouvée"
    for d in devs:
        if os.access(d, os.R_OK):
            return True, ""
    return False, "permission"


class Accord:
    """Surveille les souris ; appelle quand() quand gauche + droit sont enfoncés ensemble."""

    def __init__(self, quand, ecart=0.35):
        self.quand, self.ecart = quand, ecart
        self.stop = False
        self.t = threading.Thread(target=self._boucle, daemon=True)

    def demarrer(self):
        self.t.start()
        return self

    def _boucle(self):
        fds = []
        for d in souris():
            try:
                fds.append(os.open(d, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass
        if not fds:
            return
        bas = {BTN_LEFT: 0.0, BTN_RIGHT: 0.0}
        arme = True
        while not self.stop:
            try:
                prets, _, _ = select.select(fds, [], [], 1.0)
            except (OSError, ValueError):
                break
            for fd in prets:
                try:
                    data = os.read(fd, TAILLE * 64)
                except OSError:
                    continue
                for i in range(0, len(data) - TAILLE + 1, TAILLE):
                    _s, _us, typ, code, val = struct.unpack(FMT, data[i:i + TAILLE])
                    if typ != EV_KEY or code not in bas:
                        continue
                    if val == 1:
                        bas[code] = time.monotonic()
                        autre = bas[BTN_RIGHT if code == BTN_LEFT else BTN_LEFT]
                        if arme and autre and bas[code] - autre <= self.ecart:
                            arme = False
                            try:
                                self.quand()
                            except Exception:
                                pass
                    elif val == 0:
                        bas[code] = 0.0
                        if not bas[BTN_LEFT] and not bas[BTN_RIGHT]:
                            arme = True
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass
