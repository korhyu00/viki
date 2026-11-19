"""Position de la souris sur tout l'écran.

Sous X11, QCursor.pos() suffit. Sous Wayland, Viki tourne via XWayland et ne voit la souris que quand elle
passe sur une fenêtre X11 : son regard se fige. Sur KDE Plasma, on charge un tout petit script KWin qui nous
envoie la position de la souris par D-Bus (rien ne sort du PC). Ailleurs, on garde QCursor.pos().
"""
import os
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, pyqtClassInfo, pyqtSlot
from PyQt6.QtGui import QCursor

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
except Exception:                       # QtDBus absent (Windows…)
    QDBusConnection = QDBusMessage = None

SERVICE = "org.viki.Curseur"
PATH = "/Curseur"
IFACE = "org.viki.Curseur"
SCRIPT = "viki-curseur"

JS = """var last = 0;
function envoie() {
    var t = Date.now();
    if (t - last < 33) return;
    last = t;
    var p = workspace.cursorPos;
    callDBus("%s", "%s", "%s", "pos", Math.round(p.x) + "," + Math.round(p.y));
}
workspace.cursorPosChanged.connect(envoie);
""" % (SERVICE, PATH, IFACE)


@pyqtClassInfo("D-Bus Interface", IFACE)
class _Recv(QObject):
    def __init__(self):
        super().__init__()
        self.p, self.t = None, 0.0

    @pyqtSlot(str)
    def pos(self, txt):
        try:
            x, y = txt.split(",")
            self.p, self.t = QPoint(int(x), int(y)), time.monotonic()
        except ValueError:
            pass


_recv = None
etat = "x11"          # x11 | kde | wayland-sans-relais
raison = ""


def wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE", "") == "wayland"


def kde():
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def _call(bus, path, iface, method, *args):
    m = QDBusMessage.createMethodCall("org.kde.KWin", path, iface, method)
    if args:
        m.setArguments(list(args))
    r = bus.call(m)
    if r.type() == QDBusMessage.MessageType.ErrorMessage:
        raise RuntimeError(r.errorMessage())
    return r.arguments()


def start():
    """À appeler une fois l'application lancée. Renvoie l'état (x11, kde, wayland-sans-relais)."""
    global _recv, etat, raison
    if _recv is not None or not wayland():
        return etat
    etat = "wayland-sans-relais"
    if QDBusConnection is None:
        raison = "QtDBus absent"
        return etat
    if not kde():
        raison = "bureau " + (os.environ.get("XDG_CURRENT_DESKTOP") or "inconnu") + " (seul KDE Plasma est géré)"
        return etat
    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raison = "pas de bus D-Bus de session"
            return etat
        if not bus.registerService(SERVICE):
            raison = "service D-Bus déjà pris (une autre Viki ?) : " + bus.lastError().message()
            return etat
        recv = _Recv()
        if not bus.registerObject(PATH, recv, QDBusConnection.RegisterOption.ExportAllSlots):
            raison = "registerObject a échoué"
            return etat
        js = Path(tempfile.gettempdir()) / f"viki-curseur-{os.getuid()}.js"
        js.write_text(JS, encoding="utf-8")
        try:
            _call(bus, "/Scripting", "org.kde.kwin.Scripting", "unloadScript", SCRIPT)
        except Exception:
            pass
        sid = int(_call(bus, "/Scripting", "org.kde.kwin.Scripting", "loadScript", str(js), SCRIPT)[0])
        if sid < 0:
            raison = f"KWin a refusé le script (id {sid})"
            return etat
        errs = []
        for p in (f"/Scripting/Script{sid}", f"/{sid}"):          # Plasma 6, puis Plasma 5
            try:
                _call(bus, p, "org.kde.kwin.Script", "run")
                break
            except Exception as e:
                errs.append(str(e))
        else:
            raison = "KWin n'a pas lancé le script : " + " / ".join(errs)
            return etat
        _recv, etat, raison = recv, "kde", "script KWin lancé"
    except Exception as e:
        raison = f"erreur : {e}"
    return etat


def stop():
    if _recv is None or QDBusConnection is None:
        return
    try:
        _call(QDBusConnection.sessionBus(), "/Scripting", "org.kde.kwin.Scripting", "unloadScript", SCRIPT)
    except Exception:
        pass


def recu():
    """La position est-elle déjà arrivée de KWin ?"""
    return _recv is not None and _recv.p is not None


def pos():
    """Position de la souris (écran entier)."""
    if _recv is not None and _recv.p is not None:
        return QPoint(_recv.p)
    return QCursor.pos()
