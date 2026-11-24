#!/usr/bin/env python3
"""Compatibilité Windows du compagnon.

Le compagnon a été écrit pour Linux : il appelle de petits outils (xdg-open, notify-send, pw-play,
pw-record, playerctl, loginctl…). Sous Windows, ce module intercepte ces appels et fait la même chose
avec les fonctions de Windows (son, micro, touches multimédia, verrouillage, notifications…).
Sous Linux, il ne fait rien.
"""
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

IS_WIN = sys.platform == "win32"
FROZEN = bool(getattr(sys, "frozen", False))
notifier = None                      # fonction(titre, texte) donnée par l'appli (bulle de l'icône)
_PLANTAGE = None
_real_popen = subprocess.Popen
_real_run = subprocess.run
_real_which = shutil.which
CREATE_NO_WINDOW = 0x08000000


# ================================================================ petites fonctions Windows
def _user32():
    return ctypes.windll.user32


def press_key(vk, times=1):
    u = _user32()
    for _ in range(times):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


VK = {"play": 0xB3, "pause": 0xB3, "play-pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
      "vol_up": 0xAF, "vol_down": 0xAE, "mute": 0xAD}


def open_path(target):
    try:
        os.startfile(str(target))
        return True
    except OSError:
        return False


def launch_app(name):
    """« ouvre firefox » : Windows retrouve les applis installées par leur nom (App Paths)."""
    for cand in (name, name + ".exe"):
        try:
            os.startfile(cand)
            return True
        except OSError:
            continue
    return False


def mem_info():
    """(Go libres, Go au total)"""
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1024 ** 3, m.ullTotalPhys / 1024 ** 3


def uptime_s():
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return ctypes.windll.kernel32.GetTickCount64() / 1000.0


def active_window():
    """(nom du programme, titre) de la fenêtre au premier plan."""
    u = _user32()
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return "", ""
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    pid = ctypes.c_ulong()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        size = ctypes.c_ulong(512)
        pbuf = ctypes.create_unicode_buffer(512)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            exe = Path(pbuf.value).stem.lower()
        ctypes.windll.kernel32.CloseHandle(h)
    return exe, buf.value


def active_window_geometry(own_pids=()):
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)]
    u = _user32()
    hwnd = u.GetForegroundWindow()
    if not hwnd or u.IsIconic(hwnd):
        return None
    pid = ctypes.c_ulong()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in own_pids:
        return None
    r = RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def type_text(text):
    """Tape du texte dans la fenêtre active (événements clavier Unicode)."""
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

    class MI(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

    class U(ctypes.Union):
        _fields_ = [("ki", KI), ("mi", MI)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", U)]
    u = _user32()
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            continue
        for flags in (0x0004, 0x0004 | 0x0002):          # KEYEVENTF_UNICODE, puis relâchée
            inp = INPUT(type=1, u=U(ki=KI(0, code, flags, 0, None)))
            u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.004)
    return "windows"


def brightness_set(percent):
    """Écrans de portable seulement (WMI). Renvoie True si ça a marché."""
    ps = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)."
          f"WmiSetBrightness(1,{int(max(0, min(100, percent)))})")
    r = _real_run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                  creationflags=CREATE_NO_WINDOW, timeout=15)
    return r.returncode == 0 and "Exception" not in (r.stderr or "")


def brightness_get():
    ps = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
    r = _real_run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                  creationflags=CREATE_NO_WINDOW, timeout=15)
    try:
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


def downloads_dir():
    p = Path.home() / "Downloads"
    return p if p.is_dir() else None


# ================================================================ son : lecture et micro
class FakeProc:
    """Ressemble à un processus terminé (pour les commandes remplacées)."""

    def __init__(self, out="", code=0):
        self.returncode = code
        self.stdout = out
        self.stderr = ""
        self.args = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def communicate(self, *a, **k):
        return self.stdout, self.stderr

    def kill(self):
        pass

    terminate = kill

    def send_signal(self, sig):
        pass


class WinPlayer(FakeProc):
    """pw-play sous Windows : joue un WAV (volume appliqué en recopiant le fichier)."""

    def __init__(self, path, volume=1.0):
        super().__init__()
        import winsound
        self.winsound = winsound
        self.returncode = None
        src = Path(path)
        play = src
        dur = 1.0
        try:
            with wave.open(str(src), "rb") as w:
                params = w.getparams()
                data = w.readframes(params.nframes)
                dur = params.nframes / float(params.framerate or 16000)
            if params.sampwidth == 2 and abs(volume - 1.0) > 0.01:
                import array
                a = array.array("h", data)
                v = max(0.0, min(1.5, volume))
                for i in range(len(a)):
                    a[i] = max(-32768, min(32767, int(a[i] * v)))
                play = src.with_name(src.stem + "_vol.wav")
                with wave.open(str(play), "wb") as w:
                    w.setparams(params)
                    w.writeframes(a.tobytes())
        except Exception:
            pass
        self.end = time.monotonic() + dur + 0.1
        winsound.PlaySound(str(play), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def poll(self):
        if self.returncode is None and time.monotonic() >= self.end:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        while self.poll() is None:
            time.sleep(0.05)
        return 0

    def kill(self):
        if self.returncode is None:
            self.winsound.PlaySound(None, 0)
            self.returncode = -1

    terminate = kill


def _sd():
    import sounddevice
    return sounddevice


class WinRecorder(FakeProc):
    """pw-record sous Windows. Fichier : enregistre jusqu'à send_signal ; « - » : flux continu sur stdout."""

    def __init__(self, out_path):
        super().__init__()
        self.returncode = None
        self.path = out_path
        self.frames = []
        self.q = queue.Queue()
        self.stream_mode = out_path == "-"
        self.stdout = self if self.stream_mode else None
        self.stderr = None
        self._buf = b""
        self.stderr_text = ""
        self.stream = None
        self.rate, self.ch = 16000, 1
        try:
            sd = _sd()
            dev = sd.query_devices(kind="input")
            native = int(dev.get("default_samplerate") or 48000)
            maxch = max(1, int(dev.get("max_input_channels") or 1))
            tried = []
            # 16 kHz mono si le micro l'accepte, sinon sa fréquence à lui (on convertit ensuite)
            for rate, ch in ((16000, 1), (native, 1), (native, min(2, maxch)), (48000, min(2, maxch)),
                             (44100, min(2, maxch))):
                if (rate, ch) in tried:
                    continue
                tried.append((rate, ch))
                try:
                    sd.check_input_settings(samplerate=rate, channels=ch, dtype="int16")
                    self.stream = sd.RawInputStream(samplerate=rate, channels=ch, dtype="int16",
                                                    blocksize=int(rate * 0.03), callback=self._cb)
                    self.rate, self.ch = rate, ch
                    break
                except Exception as e:
                    self.stderr_text = f"{rate} Hz / {ch} canal(aux) refusé : {e}"
            if self.stream is None:
                raise RuntimeError(self.stderr_text or "aucun réglage accepté")
            self.stream.start()
            self.stderr_text = f"micro : {dev.get('name', '?')} ({self.rate} Hz, {self.ch} canal(aux))"
        except Exception as e:
            self.stream = None
            self.returncode = 1
            self.stderr_text = f"micro indisponible : {e}"

    def _to16k(self, b):
        """Convertit un bloc du micro en 16 kHz mono 16 bits (ce qu'attend la reconnaissance vocale)."""
        if self.rate == 16000 and self.ch == 1:
            return b
        import numpy as np
        a = np.frombuffer(b, dtype="<i2").astype(np.float32)
        if self.ch > 1:
            a = a.reshape(-1, self.ch).mean(axis=1)
        if self.rate != 16000 and len(a):
            n = max(1, int(round(len(a) * 16000 / self.rate)))
            a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
        return np.clip(a, -32768, 32767).astype("<i2").tobytes()

    def _cb(self, data, frames, t, status):
        b = self._to16k(bytes(data))
        if self.stream_mode:
            self.q.put(b)
        else:
            self.frames.append(b)

    # lecture du flux (mode « - »)
    def read(self, n):
        while len(self._buf) < n:
            if self.returncode is not None and self.q.empty():
                break
            try:
                self._buf += self.q.get(timeout=1.0)
            except queue.Empty:
                if self.returncode is not None:
                    break
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _stop(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if not self.stream_mode and self.returncode in (None, 1):
            with wave.open(self.path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"".join(self.frames))
        if self.returncode is None:
            self.returncode = 0

    def send_signal(self, sig):
        self._stop()

    def kill(self):
        self._stop()

    terminate = kill

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


# ================================================================ interception des commandes Linux
HANDLED = {"xdg-open", "notify-send", "dolphin", "loginctl", "systemctl", "playerctl", "spectacle", "pkill",
           "pw-play", "pw-record", "parec", "wpctl"}


def _handle(args, kwargs):
    """Exécute l'équivalent Windows d'une commande Linux. Renvoie un faux processus, ou None."""
    if not args:
        return None
    name = Path(str(args[0])).name
    a = [str(x) for x in args[1:]]
    if name not in HANDLED:
        return None
    if name == "xdg-open":
        open_path(a[-1])
    elif name == "dolphin":
        target = a[-1]
        _real_popen(["explorer", "/select,", target], creationflags=CREATE_NO_WINDOW)
    elif name == "notify-send":
        msg = [x for i, x in enumerate(a) if not x.startswith("-") and (i == 0 or a[i - 1] != "-a")]
        if notifier:
            try:
                notifier(msg[0] if msg else "", " ".join(msg[1:]))
            except Exception:
                pass
    elif name == "loginctl":
        _user32().LockWorkStation()
    elif name == "systemctl":
        if "suspend" in a:
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        elif "poweroff" in a:
            _real_popen(["shutdown", "/s", "/t", "0"], creationflags=CREATE_NO_WINDOW)
        elif "reboot" in a:
            _real_popen(["shutdown", "/r", "/t", "0"], creationflags=CREATE_NO_WINDOW)
    elif name == "playerctl":
        cmd = a[0] if a else ""
        if cmd in VK:
            press_key(VK[cmd])
        return FakeProc("")                       # statut / titre : inconnus sous Windows
    elif name == "spectacle":
        open_path("ms-screenclip:")
    elif name == "wpctl":
        if a[:1] == ["set-mute"]:
            press_key(VK["mute"])
        elif a[:1] == ["set-volume"]:
            val = a[-1]
            n = 0
            try:
                n = int(float(val.rstrip("%+-")))
            except ValueError:
                pass
            if val.endswith("+"):
                press_key(VK["vol_up"], max(1, n // 2))
            elif val.endswith("-"):
                press_key(VK["vol_down"], max(1, n // 2))
            else:                                  # réglage exact : on descend à 0 puis on remonte
                press_key(VK["vol_down"], 50)
                press_key(VK["vol_up"], max(0, n // 2))
        return FakeProc("")
    elif name == "pw-play":
        vol = 1.0
        if "--volume" in a:
            try:
                vol = float(a[a.index("--volume") + 1])
            except Exception:
                pass
        return WinPlayer(a[-1], vol)
    elif name in ("pw-record", "parec"):
        target = a[-1] if name == "pw-record" else "-"
        return WinRecorder(target)
    return FakeProc("")


def _chemin_complet(args):
    """« tesseract … » -> « C:\\Program Files\\Tesseract-OCR\\tesseract.exe … » s'il n'est pas dans le PATH."""
    if IS_WIN and isinstance(args, (list, tuple)) and args and str(args[0]) in CHEMINS_WIN \
            and not _real_which(str(args[0])):
        full = _which(str(args[0]))
        if full:
            return [full] + list(args[1:])
    return args


class _Popen:
    def __new__(cls, args, *a, **kw):
        args = _chemin_complet(args)
        fake = _handle(args if isinstance(args, (list, tuple)) else [args], kw) if IS_WIN else None
        if fake is not None:
            return fake
        if IS_WIN:
            kw.setdefault("creationflags", CREATE_NO_WINDOW)
            kw.pop("preexec_fn", None)
            kw.pop("start_new_session", None)
        return _real_popen(args, *a, **kw)


def _run(args, *a, **kw):
    args = _chemin_complet(args)
    fake = _handle(args if isinstance(args, (list, tuple)) else [args], kw) if IS_WIN else None
    if fake is not None:
        out = fake.stdout if isinstance(fake.stdout, str) else ""
        return subprocess.CompletedProcess(args, 0, out if kw.get("text") else out.encode(), "")
    if IS_WIN:
        kw.setdefault("creationflags", CREATE_NO_WINDOW)
    return _real_run(args, *a, **kw)


# outils installés sous Windows hors du PATH : leurs dossiers habituels
CHEMINS_WIN = {
    "tesseract": [r"%ProgramFiles%\Tesseract-OCR\tesseract.exe", r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"],
    "gpg": [r"%ProgramFiles(x86)%\GnuPG\bin\gpg.exe", r"%ProgramFiles%\GnuPG\bin\gpg.exe"],
    "git": [r"%ProgramFiles%\Git\cmd\git.exe"],
    "mpv": [r"%ProgramFiles%\mpv\mpv.exe", r"%LOCALAPPDATA%\Programs\mpv\mpv.exe"],
    "ffmpeg": [r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"],
    "ollama": [r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"],
}


def _which(name, *a, **kw):
    if IS_WIN and name not in HANDLED:
        r = _real_which(name, *a, **kw)
        if r:
            return r
        for c in CHEMINS_WIN.get(name, []):
            c = os.path.expandvars(c)
            if os.path.isfile(c):
                return c
        return None
    if IS_WIN and name in HANDLED:
        if name in ("pw-record", "parec"):
            try:
                _sd()
            except Exception:
                return None
        return name
    return _real_which(name, *a, **kw)


def install():
    if FROZEN and (sys.stdout is None or sys.stderr is None):
        # .exe sans console : les messages vont dans un fichier (utile en cas de souci)
        try:
            d = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Viki"
            d.mkdir(parents=True, exist_ok=True)
            f = open(d / "console.log", "w", encoding="utf-8", buffering=1)
        except Exception:
            f = open(os.devnull, "w")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
    if IS_WIN:                     # un plantage « natif » (sans message Python) : on note où, pour le corriger
        try:
            import faulthandler
            d = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Viki"
            d.mkdir(parents=True, exist_ok=True)
            global _PLANTAGE
            _PLANTAGE = open(d / "plantage.txt", "a", encoding="utf-8", buffering=1)
            _PLANTAGE.write(f"\n===== lancement {time.strftime('%d/%m %H:%M:%S')}\n")
            faulthandler.enable(file=_PLANTAGE, all_threads=True)
        except Exception:
            pass
    if not IS_WIN:
        return
    subprocess.Popen = _Popen
    subprocess.run = _run
    shutil.which = _which


# ================================================================ reconnaissance vocale dans le même programme
class InProcSTT:
    """Remplace le programme « ecoute.py » sous Windows : même dialogue (chemin WAV -> ligne JSON),
    mais dans un fil du compagnon (pas de second Python à lancer dans le .exe)."""

    def __init__(self, env, script):
        import io
        self.returncode = None
        self._in = queue.Queue()
        self._out = queue.Queue()
        self.stdin = self
        self.stdout = self
        self.env = env
        self.script = script
        threading.Thread(target=self._run, daemon=True).start()

    # côté compagnon
    def write(self, s):
        self._in.put(s)

    def flush(self):
        pass

    def readline(self):
        return self._out.get()

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1
        self._in.put(None)

    def _run(self):
        import json
        ns = {}
        try:
            src = Path(self.script).read_text(encoding="utf-8")
            fn = src[src.index("def load_wav"):src.index("for line in sys.stdin:")]
            exec(fn, ns)
            from faster_whisper import WhisperModel
            size = self.env.get("COMPAGNON_WHISPER", "base")
            root = self.env.get("COMPAGNON_MODELS")
            threads = max(2, min(8, (os.cpu_count() or 4) // 2))
            model = WhisperModel(size, device="cpu", compute_type="int8", download_root=root, cpu_threads=threads)
            self._out.put(json.dumps({"ready": True, "model": size}) + "\n")
        except Exception as e:
            self._out.put(json.dumps({"error": repr(e)}) + "\n")
            self.returncode = 1
            return
        noms = self.env.get("COMPAGNON_NOMS", "").strip()
        while True:
            line = self._in.get()
            if line is None:
                return
            for path in line.splitlines():
                path = path.strip()
                if not path:
                    continue
                try:
                    try:
                        audio = ns["load_wav"](path)
                    except Exception:
                        audio = path
                    opts = dict(language=self.env.get("COMPAGNON_LANGUE", "fr"), vad_filter=True, beam_size=1,
                                condition_on_previous_text=False, without_timestamps=True)
                    try:
                        segs, _ = model.transcribe(audio, hotwords=noms or None, **opts)
                    except TypeError:
                        segs, _ = model.transcribe(audio, initial_prompt=(noms + ".") if noms else None, **opts)
                    text = " ".join(s.text.strip() for s in segs).strip()
                    self._out.put(json.dumps({"text": text}) + "\n")
                except Exception as e:
                    self._out.put(json.dumps({"error": repr(e)}) + "\n")


# ================================================================ reconnaissance vocale : whisper.cpp (Windows)
WCPP_MODELS = {"tiny": "ggml-tiny.bin", "base": "ggml-base.bin", "small": "ggml-small.bin"}
WCPP_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"


def whispercpp_exe(app_dir):
    p = Path(app_dir) / "whispercpp" / "whisper-cli.exe"
    return p if p.exists() else None


class WhisperCppSTT:
    """Oreille Windows basée sur whisper.cpp (whisper-cli.exe) : un petit programme à part,
    très robuste, sans Python. Même dialogue que ecoute.py (chemin WAV -> ligne JSON)."""

    def __init__(self, env, app_dir, models_dir, log=None):
        self.returncode = None
        self._in = queue.Queue()
        self._out = queue.Queue()
        self.stdin = self
        self.stdout = self
        self.env = env
        self.exe = whispercpp_exe(app_dir)
        self.models_dir = Path(models_dir)
        self.log = log
        threading.Thread(target=self._run, daemon=True).start()

    def write(self, s):
        self._in.put(s)

    def flush(self):
        pass

    def readline(self):
        return self._out.get()

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1
        self._in.put(None)

    def _model(self, size):
        import urllib.request
        name = WCPP_MODELS.get(size, "ggml-base.bin")
        path = self.models_dir / name
        if path.exists() and path.stat().st_size > 1_000_000:
            return path
        self.models_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        req = urllib.request.Request(WCPP_URL + name, headers={"User-Agent": "compagnon-bureau"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        tmp.replace(path)
        return path

    def _run(self):
        import json
        try:
            if not self.exe:
                raise RuntimeError("whisper-cli.exe introuvable")
            size = self.env.get("COMPAGNON_WHISPER", "base")
            self.model = self._model(size)
            self._out.put(json.dumps({"ready": True, "model": "whisper.cpp " + size}) + "\n")
        except Exception as e:
            self._out.put(json.dumps({"error": repr(e)}) + "\n")
            self.returncode = 1
            return
        threads = str(max(2, min(8, (os.cpu_count() or 4) // 2)))
        while True:
            line = self._in.get()
            if line is None:
                return
            for path in line.splitlines():
                path = path.strip()
                if not path:
                    continue
                cmd = [str(self.exe), "-m", str(self.model), "-f", path, "-l", self.env.get("COMPAGNON_LANGUE", "fr"),
                       "-t", threads, "-nt", "-np"]
                noms = self.env.get("COMPAGNON_NOMS", "").strip()
                if noms:
                    cmd += ["--prompt", noms + "."]
                try:
                    r = _real_run(cmd, capture_output=True, timeout=180, creationflags=CREATE_NO_WINDOW,
                                  cwd=str(self.exe.parent))
                    text = r.stdout.decode("utf-8", errors="ignore").strip()
                    text = " ".join(t.strip() for t in text.splitlines() if t.strip())
                    if r.returncode != 0 and not text:
                        err = r.stderr.decode("utf-8", errors="ignore")[-300:]
                        self._out.put(json.dumps({"error": f"whisper-cli ({r.returncode}) {err}"}) + "\n")
                    else:
                        self._out.put(json.dumps({"text": text}) + "\n")
                except Exception as e:
                    self._out.put(json.dumps({"error": repr(e)}) + "\n")
