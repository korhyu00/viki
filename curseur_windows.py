"""🖱️ Le mode curseur sous Windows (le pendant de curseur_viki.py + souris_globale.py sous Linux) :
  activer(avatar) / remettre() / actif()   le pointeur rose de Viki, avec son visage, pour tout Windows
                                          (registre HKCU\\Control Panel\\Cursors : il reste après un redémarrage,
                                          et « remettre » rend exactement les curseurs d'avant)
  Accord(cb)                              gauche + droit en même temps, n'importe où -> cb()
  Raccourci(cb)                           Win+Alt+Espace (ou Ctrl+Alt+Espace si Windows le garde) -> cb()
Tout passe par l'API de Windows (ctypes) : rien à installer."""
import json
import os
import struct
import sys
import threading
import time
from pathlib import Path

WIN = sys.platform.startswith("win")
BASE = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Viki" / "curseur"
ETAT = Path(os.environ.get("APPDATA") or Path.home()) / "Viki" / "curseur_avant.json"
# nom dans le registre -> (dessin de curseur_viki, identifiant OCR_*)
CURSEURS = {"Arrow": ("fleche", 32512), "Hand": ("main", 32649), "IBeam": ("texte", 32513),
            "Wait": ("attente", 32514), "AppStarting": ("fleche_attente", 32650), "Help": ("aide", 32651),
            "Crosshair": ("viseur", 32515)}
RACCOURCI = "Win+Alt+Espace"
_dernier = {"txt": ""}


def _png(img):
    from PyQt6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def ecrire_cur(chemin, images, point):
    """Un fichier .cur (plusieurs tailles, images PNG) ; point = point actif en fraction (x, y)."""
    entrees, donnees = [], []
    for img in images:
        s = img.width()
        donnees.append(_png(img))
        entrees.append((0 if s >= 256 else s, int(point[0] * s), int(point[1] * s)))
    off = 6 + 16 * len(images)
    out = struct.pack("<HHH", 0, 2, len(images))
    for (s, hx, hy), d in zip(entrees, donnees):
        out += struct.pack("<BBBBHHII", s, s, 0, 0, hx, hy, len(d), off)
        off += len(d)
    out += b"".join(donnees)
    Path(chemin).write_bytes(out)


def creer(avatar=None):
    """Dessine les curseurs (avec le visage) dans %LOCALAPPDATA%\\Viki\\curseur. -> {nom registre: chemin}."""
    import curseur_viki as CV
    CV.AVATAR["img"] = avatar
    BASE.mkdir(parents=True, exist_ok=True)
    for f in BASE.glob("*.cur"):                         # un nom neuf à chaque fois : Windows recharge bien
        try:
            f.unlink()
        except OSError:
            pass
    tag = str(int(time.time()))[-6:]
    out = {}
    for nom, (dessin, _ocr) in CURSEURS.items():
        imgs = [CV.image(dessin, s) for s in (32, 48, 64)]
        p = BASE / f"viki-{dessin}-{tag}.cur"
        ecrire_cur(p, imgs, CV.POINTS[dessin])
        out[nom] = str(p)
    return out


def _cle(ecrire=False):
    import winreg
    return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors", 0,
                              winreg.KEY_READ | (winreg.KEY_SET_VALUE if ecrire else 0))


def _recharger():
    import ctypes
    SPI_SETCURSORS = 0x0057
    ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0x01)   # recharge, sans tout prévenir (pas de blocage)


def actif():
    if not WIN:
        return False
    try:
        import winreg
        with _cle() as k:
            v = winreg.QueryValueEx(k, "Arrow")[0]
        return str(BASE).lower() in str(v).lower()
    except OSError:
        return False


def activer(avatar=None):
    """-> (ok, détail)"""
    if not WIN:
        return False, "Windows seulement"
    try:
        import winreg
        fichiers = creer(avatar)
        if not actif():                                   # on garde les curseurs d'avant (une seule fois)
            avant = {}
            with _cle() as k:
                for nom in list(CURSEURS) + [""]:
                    try:
                        avant[nom] = winreg.QueryValueEx(k, nom)[0]
                    except OSError:
                        avant[nom] = None
            ETAT.parent.mkdir(parents=True, exist_ok=True)
            ETAT.write_text(json.dumps(avant), encoding="utf-8")
        with _cle(True) as k:
            for nom, p in fichiers.items():
                winreg.SetValueEx(k, nom, 0, winreg.REG_EXPAND_SZ, p)
        _recharger()
        _dernier["txt"] = "curseurs Viki appliqués (" + str(BASE) + ")"
        return True, ""
    except Exception as e:
        _dernier["txt"] = str(e)
        return False, str(e)[:120]


def remettre():
    if not WIN:
        return False
    try:
        import winreg
        try:
            avant = json.loads(ETAT.read_text(encoding="utf-8"))
        except Exception:
            avant = {}
        with _cle(True) as k:
            for nom in CURSEURS:
                v = avant.get(nom)
                if v is None or str(BASE).lower() in str(v).lower():
                    v = ""                                    # vide = le curseur de Windows par défaut
                winreg.SetValueEx(k, nom, 0, winreg.REG_EXPAND_SZ, v)
        _recharger()
        return True
    except Exception as e:
        _dernier["txt"] = str(e)
        return False


# ------------------------------------------------------------------ souris et clavier, partout
class _Ecoute:
    """Un seul fil Windows : le crochet souris bas niveau (deux boutons) et le raccourci clavier."""

    def __init__(self):
        self.accord_cb = None
        self.raccourci_cb = None
        self.fil = None
        self.tid = 0
        self.g = self.d = 0.0                              # moment où gauche / droit ont été enfoncés (0 = relevé)
        self.dernier = 0.0
        self.raccourci_ok = None
        self.hook = None
        self.erreur = 0

    def demarrer(self):
        if self.fil is None and WIN:
            self.fil = threading.Thread(target=self._boucle, daemon=True)
            self.fil.start()
        return self

    def _boucle(self):
        import ctypes
        from ctypes import wintypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        self.tid = k32.GetCurrentThreadId()
        LRESULT = ctypes.c_ssize_t
        PROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u32.CallNextHookEx.restype = LRESULT
        WM_LBD, WM_LBU, WM_RBD, WM_RBU, WM_HOTKEY = 0x0201, 0x0202, 0x0204, 0x0205, 0x0312

        def crochet(code, wp, lp):
            self.vus = getattr(self, "vus", 0) + 1
            try:
                if code >= 0 and self.accord_cb is not None:
                    now = time.monotonic()
                    if wp == WM_LBD:
                        self.g = now
                    elif wp == WM_RBD:
                        self.d = now
                    elif wp == WM_LBU:
                        self.g = 0.0
                    elif wp == WM_RBU:
                        self.d = 0.0
                    if wp in (WM_LBD, WM_RBD) and self.g and self.d and abs(self.g - self.d) < 0.35 \
                            and now - self.dernier > 0.8:
                        self.dernier = now
                        threading.Thread(target=self.accord_cb, daemon=True).start()
            except Exception:
                pass
            return u32.CallNextHookEx(None, code, wp, lp)
        self._proc = PROC(crochet)                         # garder une référence (sinon Python l'efface)
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, PROC, wintypes.HINSTANCE, wintypes.DWORD]
        u32.SetWindowsHookExW.restype = wintypes.HHOOK
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        self.hook = u32.SetWindowsHookExW(14, self._proc, k32.GetModuleHandleW(None), 0)   # WH_MOUSE_LL
        if not self.hook:                                  # certains Windows veulent un module nul pour ce crochet
            self.hook = u32.SetWindowsHookExW(14, self._proc, None, 0)
        self.erreur = 0 if self.hook else k32.GetLastError()
        global RACCOURCI
        MOD_ALT, MOD_CTRL, MOD_WIN, MOD_NOREPEAT, VK_SPACE = 0x1, 0x2, 0x8, 0x4000, 0x20
        if u32.RegisterHotKey(None, 0x5649, MOD_WIN | MOD_ALT | MOD_NOREPEAT, VK_SPACE):
            self.raccourci_ok, RACCOURCI = True, "Win+Alt+Espace"
        elif u32.RegisterHotKey(None, 0x5649, MOD_CTRL | MOD_ALT | MOD_NOREPEAT, VK_SPACE):
            self.raccourci_ok, RACCOURCI = True, "Ctrl+Alt+Espace"
        else:
            self.raccourci_ok = False
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and self.raccourci_cb is not None:
                threading.Thread(target=self.raccourci_cb, daemon=True).start()
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))


_ECOUTE = _Ecoute()


def raccourci(cb):
    """Win+Alt+Espace -> cb(). -> le raccourci réellement pris."""
    _ECOUTE.raccourci_cb = cb
    _ECOUTE.demarrer()
    for _ in range(40):
        if _ECOUTE.raccourci_ok is not None:
            break
        time.sleep(0.025)
    return RACCOURCI if _ECOUTE.raccourci_ok else ""


# --- la même interface que souris_globale (Linux)
def accessible():
    return (True, "") if WIN else (False, "windows")


def diagnostic():
    return {"souris": "crochet Windows", "lisibles": 1, "groupes_session": "-", "reconnexion": False}


class Accord:
    def __init__(self, cb):
        self.cb = cb
        self._stop = False

    @property
    def stop(self):
        return self._stop

    @stop.setter
    def stop(self, v):
        self._stop = bool(v)
        if v and _ECOUTE.accord_cb is self._appel:
            _ECOUTE.accord_cb = None

    def _appel(self):
        if not self._stop:
            self.cb()

    def demarrer(self):
        _ECOUTE.accord_cb = self._appel
        _ECOUTE.demarrer()
        return self
