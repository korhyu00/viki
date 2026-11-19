"""Atelier d'images de Viki : une fenêtre simple pour créer des images.
En ligne (Pollinations, rien à installer), sur ton PC (IA libres via ComfyUI, ou Forge / AUTOMATIC1111 déjà
installé) ou sur le site Perchance. Le catalogue des modèles dit ce qu'il faut comme ordinateur pour chacun."""
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                             QScrollArea, QSpinBox, QTabWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget)

import media

ENGINE_DIR = None            # fixé par compagnon.py : ~/.local/share/viki/comfyui
COMFY_PORTS = (8188, 8000)   # ComfyUI (8188) et ComfyUI Desktop (8000)
FORGE_URL = "http://127.0.0.1:7860"

# ------------------------------------------------------------------ catalogue (chiffres indicatifs)
MODELES = [
    {"id": "sd15", "nom": "Léger et rapide", "tech": "Stable Diffusion 1.5", "fichier": "v1-5-pruned-emaonly.safetensors",
     "url": "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors",
     "page": "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5",
     "desc": "Pour les petits PC. Images correctes en 512 px, très rapide. Le plus facile à faire tourner.",
     "vram": 4, "vram_ok": 6, "ram": 8, "disque": 4.3, "vitesse": "⚡⚡⚡", "licence": "Libre (OpenRAIL-M)"},
    {"id": "sdxl", "nom": "Polyvalent", "tech": "Stable Diffusion XL 1.0", "fichier": "sd_xl_base_1.0.safetensors",
     "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
     "page": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
     "desc": "Le bon choix pour la plupart des PC de jeu. Belles images en 1024 px, tous les styles.",
     "vram": 6, "vram_ok": 8, "ram": 16, "disque": 6.9, "vitesse": "⚡⚡", "licence": "Libre (OpenRAIL++)"},
    {"id": "anime", "nom": "Anime et manga", "tech": "Animagine XL 4.0", "fichier": "animagine-xl-4.0.safetensors",
     "url": "https://huggingface.co/cagliostrolab/animagine-xl-4.0/resolve/main/animagine-xl-4.0.safetensors",
     "page": "https://huggingface.co/cagliostrolab/animagine-xl-4.0",
     "desc": "Spécialiste du style anime. Même ordinateur que « Polyvalent ».",
     "vram": 6, "vram_ok": 8, "ram": 16, "disque": 6.9, "vitesse": "⚡⚡", "licence": "Libre (OpenRAIL++)"},
    {"id": "flux_s", "nom": "Très beau et rapide", "tech": "FLUX.1 schnell (fp8)", "fichier": "flux1-schnell-fp8.safetensors",
     "url": "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors",
     "page": "https://huggingface.co/Comfy-Org/flux1-schnell",
     "desc": "Qualité impressionnante en 4 étapes, comprend bien les phrases longues et écrit du texte lisible.",
     "vram": 12, "vram_ok": 16, "ram": 32, "disque": 17, "vitesse": "⚡⚡", "licence": "Libre (Apache 2.0)"},
    {"id": "flux_d", "nom": "Qualité maximale", "tech": "FLUX.1 dev (fp8)", "fichier": "flux1-dev-fp8.safetensors",
     "url": "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors",
     "page": "https://huggingface.co/Comfy-Org/flux1-dev",
     "desc": "Les plus beaux détails, mais plus lent. Usage personnel seulement (pas commercial).",
     "vram": 12, "vram_ok": 16, "ram": 32, "disque": 17, "vitesse": "⚡", "licence": "Non commercial"},
]

STYLES = [("Aucun", ""), ("🌸 Anime", "anime style, vibrant colors, detailed illustration"),
          ("📷 Photo", "photorealistic, professional photography, natural light, highly detailed"),
          ("🖌️ Peinture", "oil painting, painterly, rich textures"),
          ("💧 Aquarelle", "watercolor painting, soft colors, paper texture"),
          ("👾 Pixel art", "pixel art, 16-bit, retro video game style"),
          ("🧸 3D mignon", "cute 3d render, soft lighting, pastel colors"),
          ("🌃 Cyberpunk", "cyberpunk, neon lights, night city, futuristic"),
          ("🐉 Fantasy", "fantasy art, epic, magical atmosphere, detailed"),
          ("✏️ Croquis", "pencil sketch, black and white, line art")]
FORMATS = [("⬜ Carré", 1, 1), ("📱 Portrait", 2, 3), ("🖼️ Paysage", 3, 2), ("🖥️ Fond d'écran", 16, 9),
           ("📲 Téléphone", 9, 16)]
QUALITES = [("Rapide", 0.6), ("Normale", 1.0), ("Soignée", 1.5)]
IDEES = ["un renard roux dans une forêt enneigée au lever du soleil", "une ville futuriste sous la pluie, néons roses",
         "un chat astronaute qui flotte au-dessus de la Terre", "une bibliothèque magique remplie de livres volants",
         "un petit café cosy un soir d'automne", "une baleine qui nage dans les nuages au coucher du soleil",
         "une cabane dans les arbres éclairée par des lanternes", "un dragon de cristal sur une montagne",
         "une plage tropicale à l'eau turquoise vue d'en haut", "un robot jardinier qui arrose des fleurs"]


# ------------------------------------------------------------------ outils
def clean_env():
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "QT_PLUGIN_PATH"):
        env.pop(k, None)
    if os.environ.get("COMPAGNON_ORIG_LD"):
        env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
    return env


def _http(url, data=None, timeout=10, headers=None):
    h = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers={**h, **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # 127.0.0.1 : jamais via un proxy
    with opener.open(req, timeout=timeout) as r:
        return r.read()


def pc_info():
    """-> {"gpu": nom, "vram": Go (0 si inconnu), "ram": Go, "libre": Go}"""
    info = {"gpu": "", "vram": 0.0, "ram": 0.0, "libre": 0.0}
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            name, mem = r.stdout.strip().splitlines()[0].rsplit(",", 1)
            info["gpu"], info["vram"] = name.strip(), round(float(mem) / 1024, 1)
    except Exception:
        pass
    if not info["vram"]:
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
            try:
                v = int((card / "device/mem_info_vram_total").read_text()) / 1024 ** 3
                if v > info["vram"]:
                    info["vram"] = round(v, 1)
                    info["gpu"] = "Carte AMD" if "0x1002" in (card / "device/vendor").read_text() else "Carte graphique"
            except Exception:
                continue
        if info["vram"] and shutil.which("lspci"):
            try:
                out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout
                m = re.search(r"(?:VGA|Display|3D)[^:]*:\s*(?:Advanced Micro Devices[^\[]*)?\[?([^\]\n]*Radeon[^\]\n]*)", out)
                if m:
                    info["gpu"] = "AMD " + m.group(1).strip()
            except Exception:
                pass
    if not info["vram"] and shutil.which("lspci"):              # Intel Arc (mémoire dédiée)
        try:
            out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"(?:VGA|Display)[^:]*:\s*Intel[^\n]*?(Arc[^\n\]]*|Battlemage[^\n]*|Alchemist[^\n]*)", out)
            if m:
                name = m.group(1).strip()
                known = {"A310": 4, "A380": 6, "A580": 8, "A750": 8, "A770": 16, "B570": 10, "B580": 12}
                info["gpu"] = "Intel " + name
                info["vram"] = float(next((v for k, v in known.items() if k in name), 8))
        except Exception:
            pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                info["ram"] = round(int(line.split()[1]) / 1024 ** 2)
    except Exception:
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            s = MS()
            s.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            info["ram"] = round(s.t / 1024 ** 3)
        except Exception:
            pass
    try:
        base = Path(ENGINE_DIR).parent if ENGINE_DIR else Path.home()
        base.mkdir(parents=True, exist_ok=True)
        info["libre"] = round(shutil.disk_usage(base).free / 1024 ** 3)
    except Exception:
        pass
    return info


def verdict(m, pc):
    if pc.get("ram") and pc["ram"] < m["ram"] / 2:
        return "❌", f"Pas assez de RAM ({pc['ram']} Go, il en faut {m['ram']})."
    if pc.get("ram") and pc["ram"] < m["ram"] and pc.get("vram", 0) >= m["vram"]:
        return "🟡", f"Ça passe, mais {m['ram']} Go de RAM seraient mieux (tu en as {pc['ram']})."
    if not pc["vram"]:
        return "❓", "Carte graphique non détectée : ça peut marcher, mais lentement."
    if pc["vram"] >= m["vram_ok"]:
        return "✅", "Ton PC le fait tourner sans problème."
    if pc["vram"] >= m["vram"]:
        return "🟡", "Ça passe, un peu lentement."
    return "❌", f"Trop lourd pour ta carte ({pc['vram']:g} Go, il en faut {m['vram']})."


def engine_installed():
    return bool(ENGINE_DIR) and (Path(ENGINE_DIR) / ".viki_ok").exists()


def ckpt_dir():
    return Path(ENGINE_DIR) / "models" / "checkpoints"


def find_comfy():
    for p in COMFY_PORTS:
        try:
            _http(f"http://127.0.0.1:{p}/system_stats", timeout=2)
            return f"http://127.0.0.1:{p}"
        except Exception:
            continue
    return ""


def find_forge(url=FORGE_URL):
    try:
        _http(url.rstrip("/") + "/sdapi/v1/options", timeout=2)
        return url.rstrip("/")
    except Exception:
        return ""


_PROC = {"p": None, "env": None, "mode": ""}
LOG_FILE = None              # fixé par compagnon.py : ~/.config/viki/atelier.log
GPU_FILE = None              # cache de la détection de la carte (AMD) : ~/.config/viki/atelier_gpu.json

# architectures AMD prises en charge par PyTorch-ROCm ; les autres empruntent une architecture proche
ROCM_OK = {"gfx900", "gfx906", "gfx908", "gfx90a", "gfx942", "gfx950", "gfx1030", "gfx1100", "gfx1101", "gfx1102",
           "gfx1200", "gfx1201"}


def log(msg, details=""):
    """Journal des erreurs de l'atelier (gardé petit)."""
    if not LOG_FILE:
        return
    try:
        p = Path(LOG_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8", errors="ignore")[-250000:] if p.exists() else ""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        p.write_text(old + f"\n[{stamp}] {msg}\n" + (details.rstrip() + "\n" if details else ""), encoding="utf-8")
    except Exception:
        pass


def read_log():
    out = ""
    try:
        out = Path(LOG_FILE).read_text(encoding="utf-8", errors="ignore")[-60000:]
    except Exception:
        pass
    eng = ""
    try:
        eng = (Path(ENGINE_DIR) / "viki.log").read_text(encoding="utf-8", errors="ignore")[-20000:]
    except Exception:
        pass
    return out, eng


class ComfyError(RuntimeError):
    def __init__(self, msg, details=""):
        super().__init__(msg)
        self.details = details


def friendly(msg):
    """Message d'erreur technique -> explication simple."""
    m = msg.lower()
    if "invalid device function" in m or "hiperror" in m or "no kernel image" in m:
        return ("Ta carte graphique AMD n'est pas reconnue telle quelle par le moteur. J'ai essayé de corriger "
                "automatiquement ; si ça recommence, ouvre le journal et envoie-le-moi.")
    if "out of memory" in m or "outofmemory" in m or "hip out of memory" in m or "cuda out of memory" in m:
        return "La carte graphique manque de mémoire : prends un modèle plus léger, moins d'images ou la qualité « Rapide »."
    if "connection refused" in m or "urlopen error" in m:
        return "Le moteur ne répond pas. Il s'est peut-être arrêté : ouvre le journal pour voir pourquoi."
    if "not found" in m and "ckpt" in m or "value not in list" in m:
        return "Le modèle choisi est introuvable. Clique sur « Vérifier » dans l'onglet « IA sur mon PC »."
    if "trop long" in m:
        return "C'est beaucoup trop long : ton PC calcule peut-être sur le processeur. Essaie un modèle plus léger."
    return ""


def probe_gpu():
    """Demande à PyTorch (dans l'environnement du moteur) quelles cartes il voit -> [{i, nom, arch, go}]."""
    d = Path(ENGINE_DIR)
    py = d / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        return []
    code = ("import json,torch\nout=[]\n"
            "if torch.cuda.is_available():\n"
            " for i in range(torch.cuda.device_count()):\n"
            "  p=torch.cuda.get_device_properties(i)\n"
            "  out.append({'i':i,'nom':p.name,'arch':getattr(p,'gcnArchName','') or '','go':round(p.total_memory/2**30,1)})\n"
            "print(json.dumps({'hip':bool(getattr(torch.version,'hip',None)),'gpus':out}))")
    env = clean_env()
    for k in ("HSA_OVERRIDE_GFX_VERSION", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"):
        env.pop(k, None)
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=120, env=env, cwd=str(d))
        lines = r.stdout.strip().splitlines()
        if not lines:
            log("Détection par PyTorch impossible (il plante en ouvrant la carte)", r.stderr[-1500:])
            return []
        data = json.loads(lines[-1])
        for g in data["gpus"]:
            g["hip"] = data["hip"]
        return data["gpus"]
    except Exception as e:
        log("Détection de la carte graphique impossible", str(e))
        return []


def kfd_gpus(base="/sys/class/kfd/kfd/topology/nodes"):
    """Cartes AMD vues par le noyau (ROCm), sans lancer PyTorch : /sys/class/kfd/kfd/topology/nodes/*.
    -> [{i (index pour ROCR_VISIBLE_DEVICES), nom, arch, go, hip}]"""
    out = []
    base = Path(base)
    if not base.exists():
        return out
    nodes = sorted((p for p in base.iterdir() if p.name.isdigit()), key=lambda p: int(p.name))
    i = 0
    for n in nodes:
        try:
            props = dict(l.split()[:2] for l in (n / "properties").read_text().splitlines() if len(l.split()) >= 2)
            ver = int(props.get("gfx_target_version", "0"))
            if not ver or int(props.get("simd_count", "0")) == 0:
                continue
            major, minor, step = ver // 10000, ver // 100 % 100, ver % 100
            arch = f"gfx{major}{minor}{step:x}" if major >= 10 else f"gfx{major}{minor:x}{step:x}"
            size = 0
            for mb in (n / "mem_banks").glob("*/properties"):
                try:
                    p2 = dict(l.split()[:2] for l in mb.read_text().splitlines() if len(l.split()) >= 2)
                    size = max(size, int(p2.get("size_in_bytes", "0")))
                except Exception:
                    pass
            nom = ""
            minor_r = props.get("drm_render_minor")
            if minor_r:
                try:
                    nom = (Path(f"/sys/class/drm/renderD{minor_r}/device/product_name").read_text().strip())
                except Exception:
                    pass
            out.append({"i": i, "nom": nom or f"AMD {arch}", "arch": arch, "go": round(size / 2 ** 30, 1),
                        "hip": True, "igpu": size < 3 * 2 ** 30})
            i += 1
        except Exception:
            continue
    return out


def _override_for(arch):
    num = arch[3:]
    if num.startswith("103"):
        return "10.3.0"
    if num.startswith(("110", "115")):
        return "11.0.0"
    if num.startswith("120"):
        return "12.0.1"
    if num.startswith("90"):
        return "9.0.0"
    return "10.3.0"


def gpu_env(force_override=False):
    """Variables d'environnement pour faire tourner le moteur sur la bonne carte AMD."""
    try:
        cache = json.loads(Path(GPU_FILE).read_text())
    except Exception:
        cache = {}
    if not cache.get("gpus"):
        cache["gpus"] = kfd_gpus() or probe_gpu()
        if Path("/dev/kfd").exists() and not os.access("/dev/kfd", os.R_OK | os.W_OK):
            log("Tu n'as pas le droit d'utiliser la carte AMD pour le calcul (/dev/kfd). Dans un terminal : "
                "sudo usermod -aG render,video $USER  puis redémarre la session.")
    env = {}
    gpus = [g for g in cache["gpus"] if g.get("hip")]
    if not gpus:
        return env, cache
    best = max(gpus, key=lambda g: g["go"])             # la carte dédiée (plus de mémoire) plutôt que l'iGPU
    if len(gpus) > 1:
        env["ROCR_VISIBLE_DEVICES"] = str(best["i"])     # cache la puce graphique du processeur au moteur
        env["HIP_VISIBLE_DEVICES"] = "0"
    arch = best["arch"].split(":")[0]
    if cache.get("override"):
        env["HSA_OVERRIDE_GFX_VERSION"] = cache["override"]
    elif force_override or (arch and arch not in ROCM_OK):
        ov = _override_for(arch)
        env["HSA_OVERRIDE_GFX_VERSION"] = ov
        cache["override"] = ov
        log(f"Carte {best['nom']} ({arch}) : je la fais passer pour {ov} (HSA_OVERRIDE_GFX_VERSION).")
    try:
        Path(GPU_FILE).write_text(json.dumps(cache))
    except Exception:
        pass
    return env, cache


def _launch(args, d, env):
    logf = open(d / "viki.log", "w")
    p = subprocess.Popen(args, cwd=str(d), env=env, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    _PROC["p"] = p
    for _ in range(240):
        time.sleep(0.5)
        if p.poll() is not None:
            tail = ""
            try:
                tail = (d / "viki.log").read_text(errors="ignore")[-3000:]
            except Exception:
                pass
            return None, tail
        url = find_comfy()
        if url:
            return url, ""
    raise RuntimeError("le moteur met trop de temps à démarrer")


def start_comfy(vram=0.0, force_override=False):
    """Lance ComfyUI installé par Viki. Si la carte graphique le fait planter, essaie le mode compatibilité,
    puis le processeur (lent mais sûr). Retient ce qui marche."""
    if not force_override:
        url = find_comfy()
        if url:
            return url
    if not engine_installed():
        raise RuntimeError("moteur pas installé")
    stop_comfy()
    d = Path(ENGINE_DIR)
    py = d / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    base = [str(py), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch",
            "--preview-method", "auto"]
    try:
        cache = json.loads(Path(GPU_FILE).read_text())
    except Exception:
        cache = {}
    tries = []
    if vram and cache.get("mode") != "cpu":
        extra, cache = gpu_env(force_override)
        vflag = ["--lowvram"] if vram < 8 else []
        tries.append(("gpu", base + vflag, extra))
        if "HSA_OVERRIDE_GFX_VERSION" not in extra and any(g.get("hip") for g in cache.get("gpus", [])):
            best = max((g for g in cache["gpus"] if g.get("hip")), key=lambda g: g["go"])
            tries.append(("compat", base + vflag, dict(extra, HSA_OVERRIDE_GFX_VERSION=_override_for(best["arch"]))))
    tries.append(("cpu", base + ["--cpu"], {"HIP_VISIBLE_DEVICES": "", "ROCR_VISIBLE_DEVICES": "",
                                            "CUDA_VISIBLE_DEVICES": ""} if vram else {}))
    last = ""
    for mode, args, extra in tries:
        env = clean_env()
        env.update(extra)
        _PROC["env"], _PROC["mode"] = extra, mode
        log(f"Démarrage du moteur ({mode}) : " + " ".join(args[1:]) + (f"  {extra}" if extra else ""))
        url, tail = _launch(args, d, env)
        if url:
            if vram and mode != cache.get("mode"):
                cache["mode"] = mode
                if mode == "compat":
                    cache["override"] = extra.get("HSA_OVERRIDE_GFX_VERSION")
                try:
                    Path(GPU_FILE).write_text(json.dumps(cache))
                except Exception:
                    pass
            if mode == "cpu" and vram:
                log("La carte graphique fait planter le moteur : je calcule sur le processeur (lent). "
                    "Réessaie la carte depuis « IA sur mon PC » → « Réessayer la carte graphique ».")
            return url
        last = tail
        log(f"Le moteur s'est arrêté au démarrage ({mode})", tail)
    raise ComfyError("le moteur s'est arrêté au démarrage", last)


def reset_gpu_cache():
    try:
        Path(GPU_FILE).unlink()
    except Exception:
        pass


def ours():
    p = _PROC.get("p")
    return bool(p and p.poll() is None)


def stop_comfy():
    p = _PROC.get("p")
    if p and p.poll() is None:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    _PROC["p"] = None


# ------------------------------------------------------------------ suivi en direct (websocket ComfyUI)
class Watch:
    """Écoute ws://…/ws?clientId=… : étapes (value / max), nœud en cours, aperçu de l'image."""

    def __init__(self, url, cid):
        self.state = {"value": 0, "max": 0, "node": "", "preview": None, "phase": "attente"}
        self.ok = True
        import socket
        u = urllib.parse.urlparse(url)
        try:
            self.s = socket.create_connection((u.hostname, u.port or 80), timeout=5)
            key = base64.b64encode(os.urandom(16)).decode()
            req = (f"GET /ws?clientId={cid} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
            self.s.sendall(req.encode())
            head = b""
            while b"\r\n\r\n" not in head:
                ch = self.s.recv(1)
                if not ch:
                    raise OSError("fermé")
                head += ch
            if b" 101 " not in head.split(b"\r\n")[0]:
                raise OSError("pas de websocket")
            self.s.settimeout(None)
            threading.Thread(target=self._run, daemon=True).start()
        except Exception:
            self.ok = False

    def _recv(self, n):
        b = b""
        while len(b) < n:
            ch = self.s.recv(n - len(b))
            if not ch:
                raise OSError("fermé")
            b += ch
        return b

    def _run(self):
        buf, op0 = b"", 0
        try:
            while self.ok:
                h = self._recv(2)
                fin, op, ln = h[0] & 0x80, h[0] & 0x0F, h[1] & 0x7F
                if ln == 126:
                    ln = int.from_bytes(self._recv(2), "big")
                elif ln == 127:
                    ln = int.from_bytes(self._recv(8), "big")
                if h[1] & 0x80:
                    self._recv(4)
                data = self._recv(ln)
                if op == 8:
                    break
                if op in (1, 2):
                    buf, op0 = data, op
                elif op == 0:
                    buf += data
                else:
                    continue
                if not fin:
                    continue
                self._handle(op0, buf)
        except Exception:
            pass
        self.ok = False

    def _handle(self, op, data):
        st = self.state
        if op == 2 and len(data) > 8 and int.from_bytes(data[:4], "big") == 1:
            st["preview"] = data[8:]
            return
        try:
            m = json.loads(data)
        except Exception:
            return
        t, d = m.get("type"), m.get("data", {})
        if t == "progress":
            st.update(value=d.get("value", 0), max=d.get("max", 0), phase="calcul")
        elif t == "executing" and d.get("node"):
            st["node"] = str(d.get("node"))
            if st["phase"] == "attente":
                st["phase"] = "chargement"
        elif t == "execution_start":
            st["phase"] = "chargement"

    def close(self):
        self.ok = False
        try:
            self.s.close()
        except Exception:
            pass


def comfy_run(url, graph, stop, prog=None, timeout=1800):
    """Envoie un graphe à ComfyUI, suit l'avancement, renvoie ses sorties."""
    cid = uuid.uuid4().hex
    w = Watch(url, cid)
    try:
        r = json.loads(_http(url + "/prompt", json.dumps({"prompt": graph, "client_id": cid}).encode(), 30))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:4000]
        w.close()
        raise ComfyError("le moteur a refusé la demande : " + body[:200], body)
    if r.get("node_errors"):
        w.close()
        raise ComfyError("le moteur a refusé la demande : " + str(r["node_errors"])[:200], json.dumps(r["node_errors"],
                                                                                                    indent=1))
    pid = r["prompt_id"]
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            if stop():
                try:
                    _http(url + "/interrupt", b"{}", 5)
                except Exception:
                    pass
                raise RuntimeError("annulé")
            for _ in range(4):
                time.sleep(0.25)
                if prog:
                    prog(dict(w.state))
            try:
                hist = json.loads(_http(url + "/history/" + pid, timeout=10))
            except Exception as e:
                if not find_comfy():
                    raise ComfyError("le moteur s'est arrêté pendant le calcul", str(e))
                continue
            if pid in hist:
                stt = hist[pid].get("status", {})
                if stt.get("status_str") == "error":
                    err = next((m[1] for m in stt.get("messages", []) if m[0] == "execution_error"), {})
                    msg = err.get("exception_message", "erreur inconnue").strip()
                    det = (f"Nœud : {err.get('node_type', '?')} ({err.get('node_id', '?')})\n"
                           f"{err.get('exception_type', '')}: {msg}\n" + "".join(err.get("traceback", []))[-4000:])
                    raise ComfyError("erreur du moteur : " + msg.splitlines()[0][:200] if msg else "erreur du moteur", det)
                return hist[pid].get("outputs", {})
        raise RuntimeError("trop long")
    finally:
        w.close()


def comfy_file(url, f):
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                "type": f.get("type", "output")})
    return _http(url + "/view?" + q, timeout=120)


# ------------------------------------------------------------------ ressources en temps réel
class Res:
    def __init__(self):
        self.cpu_prev = None

    def _cpu(self):
        try:
            v = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:8]]
            idle, tot = v[3] + v[4], sum(v)
            p = self.cpu_prev
            self.cpu_prev = (idle, tot)
            if p and tot > p[1]:
                return round(100 * (1 - (idle - p[0]) / (tot - p[1])))
        except Exception:
            pass
        return None

    def sample(self):
        r = {"cpu": self._cpu()}
        try:
            mi = {l.split(":")[0]: int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()}
            r["ram"], r["ram_tot"] = round((mi["MemTotal"] - mi["MemAvailable"]) / 2 ** 20, 1), round(mi["MemTotal"] / 2 ** 20)
        except Exception:
            pass
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout
            if out.strip():
                u, mu, mt, tp = [float(x) for x in out.splitlines()[0].split(",")]
                r.update(gpu=round(u), vram=round(mu / 1024, 1), vram_tot=round(mt / 1024, 1), temp=round(tp))
                return r
        except Exception:
            pass
        best = None
        for card in Path("/sys/class/drm").glob("card[0-9]"):
            dev = card / "device"
            try:
                tot = int((dev / "mem_info_vram_total").read_text())
                if best is None or tot > best[1]:
                    best = (dev, tot)
            except Exception:
                continue
        if best:
            dev, tot = best
            try:
                r["gpu"] = int((dev / "gpu_busy_percent").read_text())
            except Exception:
                pass
            try:
                r["vram"], r["vram_tot"] = round(int((dev / "mem_info_vram_used").read_text()) / 2 ** 30, 1), \
                    round(tot / 2 ** 30, 1)
            except Exception:
                pass
            for hw in dev.glob("hwmon/hwmon*"):
                for name in ("temp2_input", "temp1_input"):
                    try:
                        r["temp"] = round(int((hw / name).read_text()) / 1000)
                        break
                    except Exception:
                        continue
                if "temp" in r:
                    break
        return r


def res_text(r):
    parts = []
    if r.get("gpu") is not None:
        parts.append(f"🎮 Carte graphique {r['gpu']} %")
    if r.get("vram") is not None:
        parts.append(f"mémoire vidéo {r['vram']:g} / {r['vram_tot']:g} Go")
    if r.get("temp"):
        parts.append(f"🌡️ {r['temp']} °C")
    if r.get("cpu") is not None:
        parts.append(f"🧠 Processeur {r['cpu']} %")
    if r.get("ram") is not None:
        parts.append(f"RAM {r['ram']:g} / {r['ram_tot']} Go")
    return "  ·  ".join(parts)


def fmt_s(s):
    s = int(max(0, s))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def comfy_models(url):
    d = json.loads(_http(url + "/object_info/CheckpointLoaderSimple"))
    opt = d["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"]
    lst = opt[0] if isinstance(opt[0], list) else (opt[1] or {}).get("options", [])
    return sorted(lst)


def forge_models(url):
    return [m["title"] for m in json.loads(_http(url + "/sdapi/v1/sd-models"))]


def preset(name):
    """Réglages adaptés au modèle (d'après son nom de fichier)."""
    n = name.lower()
    if "schnell" in n:
        return {"steps": 4, "cfg": 1.0, "sampler": "euler", "sched": "simple", "base": 1024, "fixe": True}
    if "flux" in n:
        return {"steps": 20, "cfg": 1.0, "sampler": "euler", "sched": "simple", "base": 1024, "fixe": False}
    if "z_image" in n or "z-image" in n:
        return {"steps": 8, "cfg": 1.0, "sampler": "euler", "sched": "simple", "base": 1024, "fixe": True}
    if re.search(r"turbo|lightning|hyper|lcm", n):
        return {"steps": 6, "cfg": 2.0, "sampler": "euler_ancestral", "sched": "sgm_uniform", "base": 1024, "fixe": True}
    if re.search(r"sd3|3\.5|sd35", n):
        return {"steps": 28, "cfg": 4.5, "sampler": "euler", "sched": "sgm_uniform", "base": 1024, "fixe": False}
    if re.search(r"xl|animagine|illustrious|juggernaut|pony|noob", n):
        return {"steps": 25, "cfg": 6.0, "sampler": "dpmpp_2m", "sched": "karras", "base": 1024, "fixe": False}
    return {"steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "sched": "karras", "base": 512, "fixe": False}


def size_for(rw, rh, base):
    """Format (ex 16:9) -> largeur, hauteur multiples de 64 avec environ base² pixels."""
    area = base * base
    w = (area * rw / rh) ** 0.5
    h = w * rh / rw
    return max(256, int(round(w / 64)) * 64), max(256, int(round(h / 64)) * 64)


def comfy_generate(url, ckpt, prompt, neg, w, h, steps, cfg, seed, sampler, sched, stop, prog=None):
    g = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
         "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
         "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
         "7": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["4", 1]}},
         "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler,
                                                    "scheduler": sched, "denoise": 1.0, "model": ["4", 0],
                                                    "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
         "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
         "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "viki", "images": ["8", 0]}}}
    outs = comfy_run(url, g, stop, prog)
    for out in outs.values():
        for im in out.get("images", []):
            return comfy_file(url, im)
    raise ComfyError("le moteur n'a pas renvoyé d'image", json.dumps(outs)[:2000])


def forge_generate(url, model, prompt, neg, w, h, steps, cfg, seed, sampler, sched):
    import base64
    body = {"prompt": prompt, "negative_prompt": neg, "width": w, "height": h, "steps": steps, "cfg_scale": cfg,
            "seed": seed, "sampler_name": {"euler": "Euler", "euler_ancestral": "Euler a"}.get(sampler, "DPM++ 2M"),
            "scheduler": {"karras": "Karras", "simple": "Simple", "sgm_uniform": "SGM Uniform"}.get(sched, "Automatic"),
            "batch_size": 1}
    if model:
        body["override_settings"] = {"sd_model_checkpoint": model}
    if cfg <= 1.0:
        body["distilled_cfg_scale"] = 3.5
    r = json.loads(_http(url + "/sdapi/v1/txt2img", json.dumps(body).encode(), 1800))
    return base64.b64decode(r["images"][0].split(",", 1)[-1])


def download(url, dest, progress, stop, token=""):
    """Téléchargement reprenable (.part) -> progress(octets, total)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    h = {"User-Agent": "Viki/1.0"}
    if have:
        h["Range"] = f"bytes={have}-"
    if token:
        h["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        if have and r.status != 206:
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        with open(part, "ab" if have else "wb") as f:
            done = have
            while True:
                if stop():
                    raise RuntimeError("annulé")
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                done += len(b)
                progress(done, total)
    if part.stat().st_size < 50 * 1024 * 1024:
        part.unlink()
        raise RuntimeError("fichier incomplet (le site a refusé le téléchargement)")
    part.rename(dest)


# ------------------------------------------------------------------ fenêtre
class _Sig(QObject):
    done = pyqtSignal(object, object)          # (fonction, résultat)


try:
    import pomme
except Exception:
    pomme = None
CSS = """
QWidget#atelier { font-size: 10.5pt; }
QTextEdit#prompt { font-size: 12pt; padding: 6px; border-radius: 10px; }
QPushButton#chip { border-radius: 14px; padding: 5px 12px; }
QPushButton#chip:checked { font-weight: bold; border: 2px solid palette(highlight); }
QPushButton#creer { font-size: 13pt; font-weight: bold; padding: 10px; border-radius: 12px;
                    background: palette(highlight); color: palette(highlighted-text); border: none; }
QPushButton#creer:hover { border: 2px solid palette(highlighted-text); }
QFrame#carte { border: 1px solid palette(mid); border-radius: 12px; }
QLabel#aide { color: palette(placeholder-text); }
QLabel#titre { font-size: 12pt; font-weight: bold; }
"""


class Atelier(QWidget):
    def __init__(self, comp, C):
        super().__init__(None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.cfg = comp.cfg
        self.setObjectName("atelier")
        self.apple = bool(pomme) and pomme.actif(C, comp.cfg)
        self.setStyleSheet(pomme.STUDIO if self.apple else CSS)
        self.setWindowTitle("🎨 Atelier d'images — " + comp.char.get("name", "Viki"))
        scr = self.screen().availableGeometry() if self.screen() else None
        self.resize(min(1180, int(scr.width() * 0.88)) if scr else 1100, min(800, int(scr.height() * 0.88)) if scr else 760)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, res: fn(res))
        self.busy = False
        self.cancel = False
        self.pc = {"gpu": "", "vram": 0.0, "ram": 0, "libre": 0}
        self.local = {"type": "", "url": "", "models": []}
        self.last = None
        self.dl = {}
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._tab_create(), "✨ Créer")
        self.tabs.addTab(self._tab_local(), "🖥️ IA sur mon PC")
        self.tabs.addTab(self._tab_help(), "❓ Aide")
        if self.apple:
            pomme.pictos_onglets(C, self.tabs)
        self._bg(pc_info, self._got_pc)
        self.refresh_local()

    def _emit(self, fn, res):
        """Renvoie le résultat d'un fil vers l'interface (sans planter si la fenêtre a été fermée entre-temps)."""
        try:
            self.sig.done.emit(fn, res)
        except RuntimeError:
            pass

    # ---------- fils
    def _bg(self, work, then):
        def run():
            try:
                res = work()
            except Exception as e:
                res = e
            self._emit(then, res)
        threading.Thread(target=run, daemon=True).start()

    # ---------- onglet Créer
    def _chips(self, items, current, on):
        row = QHBoxLayout()
        row.setSpacing(6)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for i, lab in enumerate(items):
            b = QPushButton(lab)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(i == current)
            grp.addButton(b, i)
            row.addWidget(b)
        row.addStretch(1)
        grp.idClicked.connect(on)
        return row, grp

    def _label(self, txt, obj=""):
        l = QLabel(txt)
        l.setWordWrap(True)
        if obj:
            l.setObjectName(obj)
        return l

    def _tab_create(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        # --- gauche : réglages
        left = QWidget()
        L = QVBoxLayout(left)
        L.setSpacing(8)
        L.addWidget(self._label("1. Décris ton image", "titre"))
        self.prompt = QTextEdit()
        self.prompt.setObjectName("prompt")
        self.prompt.setAcceptRichText(False)
        self.prompt.setPlaceholderText("Ex : un chat astronaute qui flotte au-dessus de la Terre, couleurs douces\n\n"
                                       "Écris en français, je traduis pour l'IA.")
        self.prompt.setMinimumHeight(110)
        self.prompt.setMaximumHeight(150)
        L.addWidget(self.prompt)
        row = QHBoxLayout()
        b = QPushButton("💡 Une idée au hasard")
        b.clicked.connect(lambda: self.prompt.setPlainText(random.choice(IDEES)))
        row.addWidget(b)
        b = QPushButton("📋 Coller")
        b.clicked.connect(lambda: self.prompt.setPlainText(QApplication.clipboard().text()[:1500]))
        row.addWidget(b)
        row.addStretch(1)
        L.addLayout(row)

        L.addWidget(self._label("2. Style", "titre"))
        self.style_i = int(self.cfg.get("atelier_style", 0))
        r, self.g_style = self._chips([s[0] for s in STYLES], self.style_i, lambda i: self._setv("atelier_style", i))
        L.addLayout(self._wrap(r))
        L.addWidget(self._label("3. Format", "titre"))
        r, self.g_fmt = self._chips([f[0] for f in FORMATS], int(self.cfg.get("atelier_format", 0)),
                                    lambda i: self._setv("atelier_format", i))
        L.addLayout(r)
        row = QHBoxLayout()
        row.addWidget(QLabel("Combien d'images :"))
        self.nb = QComboBox()
        for n in (1, 2, 4):
            self.nb.addItem(str(n), n)
        row.addWidget(self.nb)
        row.addSpacing(16)
        row.addWidget(QLabel("Qualité :"))
        self.qual = QComboBox()
        for lab, k in QUALITES:
            self.qual.addItem(lab, k)
        self.qual.setCurrentIndex(1)
        row.addWidget(self.qual)
        row.addStretch(1)
        L.addLayout(row)

        L.addWidget(self._label("4. Où la créer ?", "titre"))
        self.where = QComboBox()
        self.where.addItem("☁️  En ligne — gratuit, rien à installer", "ligne")
        self.where.addItem("🖥️  Sur mon PC — privé, avec une IA libre", "local")
        self.where.addItem("🌐  Sur le site Perchance — j'ouvre la page", "perchance")
        cur = {"ligne": 0, "local": 1, "perchance": 2}.get(self.cfg.get("image_moteur", "ligne"), 0)
        self.where.setCurrentIndex(cur)
        self.where.currentIndexChanged.connect(self._where_changed)
        L.addWidget(self.where)
        self.where_help = self._label("", "aide")
        L.addWidget(self.where_help)
        row = QHBoxLayout()
        self.model_lab = QLabel("Modèle :")
        row.addWidget(self.model_lab)
        self.model = QComboBox()
        self.model.setMinimumWidth(260)
        row.addWidget(self.model, 1)
        self.model.currentIndexChanged.connect(lambda _i: self.where.currentData() == "local" and
                                               self.model.currentData() and
                                               self._setv("atelier_modele", self.model.currentData()))
        self.b_more_models = QPushButton("➕ Ajouter")
        self.b_more_models.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        row.addWidget(self.b_more_models)
        L.addLayout(row)

        # options avancées (repliées)
        self.b_adv = QToolButton()
        self.b_adv.setText("▸ Plus d'options")
        self.b_adv.setCheckable(True)
        self.b_adv.setStyleSheet("QToolButton { border: none; }")
        L.addWidget(self.b_adv)
        self.adv = QWidget()
        A = QGridLayout(self.adv)
        A.setContentsMargins(12, 0, 0, 0)
        A.addWidget(QLabel("À éviter :"), 0, 0)
        self.neg = QLineEdit(self.cfg.get("atelier_eviter", ""))
        self.neg.setPlaceholderText("ex : texte, flou, mains bizarres")
        A.addWidget(self.neg, 0, 1)
        A.addWidget(QLabel("Graine :"), 1, 0)
        rr = QHBoxLayout()
        self.seed = QSpinBox()
        self.seed.setRange(0, 2 ** 31 - 1)
        self.seed.setEnabled(False)
        self.seed_rand = QCheckBox("au hasard")
        self.seed_rand.setChecked(True)
        self.seed_rand.toggled.connect(lambda v: self.seed.setEnabled(not v))
        rr.addWidget(self.seed_rand)
        rr.addWidget(self.seed)
        rr.addStretch(1)
        A.addLayout(rr, 1, 1)
        A.addWidget(self._label("La même graine + la même description = la même image. Pratique pour faire de "
                                "petites variantes.", "aide"), 2, 1)
        self.tr = QCheckBox("Traduire ma description en anglais (les IA comprennent mieux)")
        self.tr.setChecked(bool(self.cfg.get("image_traduire", True)))
        self.tr.toggled.connect(lambda v: self._setv("image_traduire", v))
        A.addWidget(self.tr, 3, 0, 1, 2)
        self.adv.setVisible(False)
        self.b_adv.toggled.connect(lambda v: (self.adv.setVisible(v),
                                              self.b_adv.setText(("▾" if v else "▸") + " Plus d'options")))
        L.addWidget(self.adv)
        L.addStretch(1)
        self.b_go = QPushButton("✨  Créer")
        self.b_go.setObjectName("creer")
        self.b_go.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_go.clicked.connect(self.generate)
        L.addWidget(self.b_go)
        self._progress_panel(L)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(left)
        sc.setMinimumWidth(460)
        lay.addWidget(sc, 5)

        # --- droite : aperçu
        right = QVBoxLayout()
        self.view = QLabel("Ton image apparaîtra ici ✨")
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumSize(420, 380)
        self.view.setStyleSheet("QLabel { border: 2px dashed palette(mid); border-radius: 14px; }")
        right.addWidget(self.view, 1)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setIconSize(QPixmap(84, 84).size())
        self.thumbs.setFixedHeight(112)
        self.thumbs.setFlow(QListWidget.Flow.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.currentItemChanged.connect(lambda it, _p: it and self._show(it.data(Qt.ItemDataRole.UserRole)))
        right.addWidget(self.thumbs)
        row = QHBoxLayout()
        for txt, fn in (("🔁 Encore une", self.generate), ("💾 Enregistrer sous…", self._save_as),
                        ("📋 Copier", self._copy), ("📂 Mes images", self._open_dir)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        right.addLayout(row)
        lay.addLayout(right, 6)
        self._load_recent()
        self._where_changed()
        return w

    def _wrap(self, row):
        """Les puces de style sur deux lignes si besoin."""
        g = QGridLayout()
        g.setSpacing(6)
        items = [row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget()]
        for i, b in enumerate(items):
            g.addWidget(b, i // 5, i % 5)
        return g

    def _setv(self, k, v):
        self.cfg[k] = v
        self.C.save_config(self.cfg)

    def _where_changed(self, *_a):
        e = self.where.currentData()
        self._setv("image_moteur", e)
        local = e == "local"
        for x in (self.model_lab, self.model, self.b_more_models):
            x.setVisible(e != "perchance")
        self.b_more_models.setVisible(local)
        self.nb.setEnabled(e != "perchance")
        self.model.clear()
        if e == "ligne":
            self.where_help.setText("Ta description est envoyée à pollinations.ai, qui calcule l'image sur ses "
                                    "serveurs. Rapide, gratuit, rien à installer.")
            self.model.addItem("Flux — belle qualité", "flux")
            self.model.addItem("Turbo — plus rapide", "turbo")
        elif e == "perchance":
            self.where_help.setText("Je copie ta description et j'ouvre Perchance : colle-la avec Ctrl+V et clique "
                                    "sur Générer.")
        else:
            lc = self.local
            if lc["type"] and lc["models"]:
                self.where_help.setText(("Avec ComfyUI" if lc["type"] == "comfy" else "Avec Forge / AUTOMATIC1111")
                                        + " sur ton PC. Rien ne sort de chez toi.")
                for m in lc["models"]:
                    self.model.addItem(self._nice(m), m)
                i = self.model.findData(self.cfg.get("atelier_modele", ""))
                self.model.setCurrentIndex(max(0, i))
            elif engine_installed() or lc["type"]:
                self.where_help.setText("Le moteur est prêt. Il te faut un modèle : onglet « IA sur mon PC ».")
            else:
                self.where_help.setText("Rien n'est encore installé. Va dans l'onglet « IA sur mon PC » : deux clics "
                                        "et c'est prêt (je te dis aussi si ton PC est assez puissant).")

    def _nice(self, f):
        for m in MODELES:
            if m["fichier"] == f:
                return f"{m['nom']} ({m['tech']})"
        return f

    # ---------- génération
    def set_prompt(self, txt, fmt=None):
        self.prompt.setPlainText(txt)
        if fmt is not None:
            self.g_fmt.button(fmt).setChecked(True)
            self._setv("atelier_format", fmt)

    def generate(self):
        if self.busy:
            self.cancel = True
            self.status.setText("J'arrête…")
            return
        txt = self.prompt.toPlainText().strip()
        if not txt:
            self.status.setText("Écris d'abord ce que tu veux voir (ou clique sur « Une idée au hasard »).")
            self.prompt.setFocus()
            return
        if media.blocked(txt) or media.blocked(self.neg.text()):
            self.status.setText("Ce genre d'image, je ne le fais pas. Essaie autre chose !")
            self.comp.say("Ce genre d'image, je ne le fais pas. Demande-moi autre chose !")
            return
        e = self.where.currentData()
        style = STYLES[max(0, self.g_style.checkedId())][1]
        _lab, rw, rh = FORMATS[max(0, self.g_fmt.checkedId())]
        if e == "perchance":
            QApplication.clipboard().setText(txt + (", " + style if style else ""))
            QDesktopServices.openUrl(QUrl(media.PERCHANCE))
            self.status.setText("Description copiée : colle-la sur Perchance avec Ctrl+V.")
            return
        if e == "local" and not self.model.currentData():
            self.tabs.setCurrentIndex(1)
            self.status.setText("Installe d'abord un modèle dans « IA sur mon PC ».")
            return
        n = int(self.nb.currentData())
        q = float(self.qual.currentData())
        seed0 = random.randint(1, 2 ** 31 - 2) if self.seed_rand.isChecked() else self.seed.value()
        model = self.model.currentData() or "flux"
        neg_user = self.neg.text().strip()
        self._setv("atelier_eviter", neg_user)
        use_ia = self.tr.isChecked() and (self.comp.ollama_ok or self.comp.ia_remote())
        self.busy, self.cancel = True, False
        self.b_go.setText("⏹  Arrêter")
        self._job_start(n, "Image")
        self._amd_retried = False
        self.status.setText("Je prépare mes pinceaux… 🎨")
        self.comp.react = ("regarde", time.monotonic())
        vram = self._calc_vram()
        localinfo = dict(self.local)

        def work():
            p, ng = txt, neg_user
            if use_ia and (re.search(r"[àâéèêëîïôùûç]|\b(?:un|une|des|avec|dans|sur|et|le|la|les|qui)\b", txt.lower())
                           or re.search(r"[^\x00-\x7f]", txt)):
                p = self._translate(txt) or txt
                if ng:
                    ng = self._translate(ng) or ng
            if media.blocked(p):
                raise RuntimeError("bloqué")
            full = p + (", " + style if style else "")
            out = []
            if e == "ligne":
                w, h = size_for(rw, rh, 1024)
                for i in range(n):
                    if self.cancel:
                        break
                    self._job_item(i)
                    self._job_phase("en ligne")
                    self._st("Le service en ligne calcule ton image… (10 à 30 secondes)")
                    data = media.gen_online(full, w, h, seed0 + i, model)
                    out.append(media.save_image(data, txt, self.comp.images_dir()))
                    self._prog(i + 1)
                return out
            # local
            pr = preset(model)
            w, h = size_for(rw, rh, pr["base"])
            steps = pr["steps"] if pr["fixe"] else max(8, int(round(pr["steps"] * q)))
            neg = ", ".join(x for x in (ng, media.NEG) if x)
            if localinfo["type"] == "forge":
                url = localinfo["url"]
            else:
                self._st("Je démarre le moteur d'images… (la première fois, ça peut prendre une minute)")
                url = self._local_url(localinfo, vram)
            for i in range(n):
                if self.cancel:
                    break
                self._job_item(i)
                self._st("Je dessine… 🎨")
                if localinfo["type"] == "forge":
                    data = forge_generate(url, model, full, neg, w, h, steps, pr["cfg"], seed0 + i, pr["sampler"],
                                          pr["sched"])
                else:
                    try:
                        data = comfy_generate(url, model, full, neg, w, h, steps, pr["cfg"], seed0 + i, pr["sampler"],
                                              pr["sched"], lambda: self.cancel, self._job_prog)
                    except Exception as err:
                        url2 = self._retry_amd(err, vram)
                        if not url2:
                            raise
                        url = url2
                        self._job_item(i)
                        data = comfy_generate(url, model, full, neg, w, h, steps, pr["cfg"], seed0 + i, pr["sampler"],
                                              pr["sched"], lambda: self.cancel, self._job_prog)
                out.append(media.save_image(data, txt, self.comp.images_dir()))
                self._prog(i + 1)
            return out

        self.t0 = time.time()
        self._bg(work, lambda res: self._done(res, seed0))

    def _translate(self, txt):
        try:
            tr = self.comp.llm([{"role": "user", "content": media.translate_prompt(txt)}], timeout=60).strip()
            tr = tr.strip("\"'« »").splitlines()[0] if tr else ""
            return tr if 3 < len(tr) < 1500 else ""
        except Exception:
            return ""

    def _st(self, t):
        self._emit(lambda _r: self.status.setText(t), None)

    def _prog(self, i):
        pass

    def _done(self, res, seed):
        self.busy = False
        self.b_go.setText("✨  Créer")
        el = time.time() - self.t0
        self._job_stop()
        if isinstance(res, Exception):
            msg = str(res)
            if msg == "bloqué":
                self.status.setText("Ce genre d'image, je ne le fais pas.")
                return
            if msg == "annulé":
                self.status.setText("C'est arrêté.")
                return
            hint = self._fail(res, self.where.currentData())
            self.status.setText(f"Oups, ça n'a pas marché.\n{hint}\n(Détail : {msg[:140]})")
            self.comp.say("Je n'ai pas réussi à créer l'image… " + hint)
            return
        if not res:
            self.status.setText("Aucune image.")
            return
        for p in res:
            self._add_thumb(p, first=True)
        self.thumbs.setCurrentRow(0)
        self.seed.setValue(seed)
        dt = fmt_s(el)
        self.status.setText(f"Terminé en {dt} ✨ — rangée{'s' if len(res) > 1 else ''} dans Images → Viki. "
                            f"Graine : {seed}")
        self.comp.happy_until = time.monotonic() + 2
        self.comp._spawn("etoile", 4)
        apres = getattr(self, "apres", None)               # ex. : « Créer un personnage kawaii » attend l'image
        if apres:
            self.apres = None
            QTimer.singleShot(400, lambda: apres(str(res[0])))
            return
        self.comp.say(random.choice(["Tadaa ! Elle te plaît ?", "Et voilà ton image ! ✨", "Je suis plutôt fière de "
                                     "celle-là !"]) if len(res) == 1 else f"Voilà {len(res)} images, choisis ta préférée !")

    # ---------- progression, ressources et journal (communs images / musique)
    def _progress_panel(self, L):
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(22)
        L.addWidget(self.bar)
        self.prog_lab = self._label("", "aide")
        self.prog_lab.setVisible(False)
        L.addWidget(self.prog_lab)
        self.res_lab = self._label("", "aide")
        self.res_lab.setVisible(False)
        L.addWidget(self.res_lab)
        row = QHBoxLayout()
        self.status = self._label("", "aide")
        row.addWidget(self.status, 1)
        b = QPushButton("📜 Journal")
        b.setToolTip("Les erreurs et ce que fait le moteur")
        b.clicked.connect(self.show_log)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        L.addLayout(row)
        self.res = Res()
        self.res_timer = QTimer(self)
        self.res_timer.timeout.connect(self._res_tick)

    def _job_start(self, n, what="Image"):
        self.job = {"n": n, "i": 0, "t0": time.time(), "what": what, "ts": None, "v0": 0, "phase": "prépa"}
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.prog_lab.setVisible(True)
        self.res_lab.setVisible(True)
        self.prog_lab.setText("Préparation…")
        self.res.sample()
        self.res_timer.start(1500)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._job_redraw)
        self._tick_timer.start(1000)

    def _job_stop(self):
        self.res_timer.stop()
        if getattr(self, "_tick_timer", None):
            self._tick_timer.stop()
        self.bar.setVisible(False)
        self.prog_lab.setVisible(False)
        self.res_lab.setVisible(False)
        self.job = None

    def _job_item(self, i):
        """Appelé (depuis le fil) quand on commence l'image / le morceau i (0, 1, …)."""
        def f(_r):
            if getattr(self, "job", None):
                self.job.update(i=i, ts=None, v0=0, phase="chargement", value=0, max=0)
                self._job_redraw()
        self._emit(f, None)

    def _job_prog(self, st):
        def f(_r):
            j = getattr(self, "job", None)
            if not j:
                return
            if st.get("max"):
                if j.get("ts") is None or st["value"] < j.get("value", 0):
                    j["ts"], j["v0"] = time.time(), st["value"]
                j.update(value=st["value"], max=st["max"], phase="calcul")
            elif st.get("phase") == "chargement" and j.get("phase") != "calcul":
                j["phase"] = "chargement"
            if st.get("preview") and hasattr(self, "view") and self.view is not None and st["preview"] != j.get("pv"):
                j["pv"] = st["preview"]
                pm = QPixmap()
                if pm.loadFromData(st["preview"]):
                    self.view.setPixmap(pm.scaled(self.view.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
            self._job_redraw()
        self._emit(f, None)

    def _job_redraw(self):
        j = getattr(self, "job", None)
        if not j:
            return
        el = time.time() - j["t0"]
        n, i = j["n"], j["i"]
        head = f"{j['what']} {i + 1} sur {n} · " if n > 1 else ""
        if j.get("phase") == "calcul" and j.get("max"):
            v, mx = j["value"], j["max"]
            frac = (i + v / mx) / n
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * frac))
            self.bar.setFormat(f"{int(100 * frac)} %")
            rest = ""
            if j.get("ts") and v > j["v0"]:
                per = (time.time() - j["ts"]) / (v - j["v0"])
                left = per * (mx - v) + per * mx * (n - i - 1) * 1.05
                rest = f" · encore ~{fmt_s(left + 2)}"
            if v >= mx and j["n"] == i + 1:
                rest = " · finalisation" + (" (conversion en son)…" if j["what"] == "Morceau" else "…")
            self.prog_lab.setText(f"{head}étape {v} / {mx} · {fmt_s(el)} écoulées{rest}")
        else:
            self.bar.setRange(0, 0)
            msg = {"prépa": "Préparation…", "moteur": "Démarrage du moteur…",
                   "en ligne": "Le service en ligne calcule ton image…",
                   "chargement": "Chargement du modèle en mémoire (la 1re fois, c'est plus long)…"}.get(j.get("phase"),
                                                                                                    "Préparation…")
            self.prog_lab.setText(f"{head}{msg} · {fmt_s(el)}")

    def _job_phase(self, ph):
        def f(_r):
            if getattr(self, "job", None):
                self.job["phase"] = ph
                self._job_redraw()
        self._emit(f, None)

    def _res_tick(self):
        if getattr(self, "_res_busy", False):
            return
        self._res_busy = True

        def then(r):
            self._res_busy = False
            if isinstance(r, dict) and getattr(self, "job", None):
                self.res_lab.setText(res_text(r))
        self._bg(self.res.sample, then)

    def _fail(self, e, where="local"):
        """Erreur -> journal + message simple. Renvoie le texte affiché."""
        import traceback
        msg = str(e)
        det = getattr(e, "details", "") or "".join(traceback.format_exception(type(e), e, e.__traceback__))[-3000:]
        log(("Images" if self.__class__ is Atelier else "Musique") + f" ({where}) : {msg}", det)
        nice = friendly(msg + " " + det)
        return nice or ("Le service en ligne ne répond pas, réessaie dans un instant." if where == "ligne" else
                        "Regarde le journal (bouton 📜) : tout y est noté.")

    def show_log(self):
        w = QWidget(None, Qt.WindowType.Window)
        w.setWindowTitle("📜 Journal de l'atelier")
        w.resize(820, 600)
        lay = QVBoxLayout(w)
        info = self._label("Les erreurs de l'atelier, puis ce qu'a écrit le moteur (ComfyUI). Si ça ne marche pas, "
                           "clique sur « Copier » et envoie-le à la personne qui t'aide.", "aide")
        lay.addWidget(info)
        t = QTextEdit()
        t.setReadOnly(True)
        t.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        f = t.font()
        f.setFamily("monospace")
        t.setFont(f)
        lay.addWidget(t, 1)

        def load():
            a, e = read_log()
            gpu = ""
            try:
                gpu = Path(GPU_FILE).read_text()
            except Exception:
                pass
            txt = ("=== Atelier ===\n" + (a.strip() or "(rien pour l'instant)") + "\n\n=== Carte graphique vue par le "
                   "moteur ===\n" + (gpu or "(pas encore détectée)") + f"\nRéglages envoyés : {_PROC.get('env') or '—'}"
                   + "\n\n=== Moteur (fin de viki.log) ===\n" + (e.strip() or "(vide)"))
            t.setPlainText(txt)
            t.verticalScrollBar().setValue(t.verticalScrollBar().maximum())
        load()
        row = QHBoxLayout()
        for txt, fn in (("🔄 Actualiser", load), ("📋 Copier", lambda: (QApplication.clipboard().setText(t.toPlainText()),
                                                                       self.status.setText("Journal copié."))),
                        ("🗑 Effacer", lambda: (Path(LOG_FILE).write_text("") if LOG_FILE else None, load())),
                        ("📂 Dossier", lambda: self.comp._open_path(Path(LOG_FILE).parent) if LOG_FILE else None)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self._log_win = w
        w.show()

    def _calc_vram(self):
        return 0 if self.cfg.get("atelier_cpu") else (self.pc.get("vram", 0) or 4)

    def _local_url(self, info, vram):
        """URL du moteur ; le démarre si besoin."""
        if info.get("type") == "comfy" and info.get("url") and find_comfy():
            return find_comfy()
        self._job_phase("moteur")
        url = start_comfy(vram)
        if vram and _PROC.get("mode") == "cpu":
            self._st("Ta carte graphique fait planter le moteur : je calcule sur le processeur (plus lent). "
                     "Détails dans le journal 📜.")
        return url

    def _retry_amd(self, e, vram):
        """« invalid device function » sur AMD : on relance le moteur en mode compatibilité, une fois."""
        txt = (str(e) + " " + getattr(e, "details", "")).lower()
        if ("invalid device function" in txt or "hiperror" in txt) and not ours():
            log("Erreur AMD avec un ComfyUI lancé hors de Viki : relance-le avec la variable "
                "HSA_OVERRIDE_GFX_VERSION=10.3.0 (RDNA2) ou 11.0.0 (RDNA3), ou ferme-le pour que Viki le lance elle-même.")
            return None
        if vram and engine_installed() and ("invalid device function" in txt or "hiperror" in txt) \
                and not getattr(self, "_amd_retried", False):
            self._amd_retried = True
            log("Erreur de la carte AMD : je relance le moteur en mode compatibilité et je réessaie.",
                getattr(e, "details", "") or str(e))
            self._st("Ta carte AMD a besoin d'un réglage : je relance le moteur et je réessaie…")
            self._job_phase("moteur")
            url = start_comfy(vram, force_override=True)
            self._st("C'est reparti ! 🎨")
            return url
        return None

    # ---------- aperçu
    def _add_thumb(self, path, first=False):
        pm = QPixmap(str(path))
        if pm.isNull():
            return
        it = QListWidgetItem()
        from PyQt6.QtGui import QIcon
        it.setIcon(QIcon(pm.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)))
        it.setData(Qt.ItemDataRole.UserRole, str(path))
        it.setToolTip(Path(path).name)
        if first:
            self.thumbs.insertItem(0, it)
        else:
            self.thumbs.addItem(it)

    def _load_recent(self):
        d = self.comp.images_dir()
        if d.exists():
            for p in sorted((x for x in d.iterdir() if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")),
                            key=lambda x: -x.stat().st_mtime)[:20]:
                self._add_thumb(p)

    def _show(self, path):
        self.last = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.view.setPixmap(pm.scaled(self.view.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.last:
            QTimer.singleShot(0, lambda: self._show(self.last))

    def _save_as(self):
        if not self.last:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'image", str(Path.home() / Path(self.last).name),
                                           "Images (*.png *.jpg *.webp)")
        if p:
            shutil.copy(self.last, p)
            self.status.setText("Enregistrée !")

    def _copy(self):
        if self.last:
            QApplication.clipboard().setPixmap(QPixmap(self.last))
            self.status.setText("Image copiée, tu peux la coller où tu veux.")

    def _open_dir(self):
        d = self.comp.images_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.comp._open_path(d)

    # ---------- onglet IA sur mon PC
    def _card(self, parent_lay):
        f = QFrame()
        f.setObjectName("carte")
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 10, 14, 10)
        parent_lay.addWidget(f)
        return v

    def _tab_local(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        L = QVBoxLayout(inner)
        L.setSpacing(10)
        L.addWidget(self._label("Créer des images sur ton PC, sans internet, avec des IA libres et gratuites. "
                                "Deux étapes : installer le moteur, puis choisir un modèle.", "aide"))
        c = self._card(L)
        c.addWidget(self._label("💻 Ton ordinateur", "titre"))
        self.pc_lab = self._label("J'analyse ton PC…")
        c.addWidget(self.pc_lab)
        c.addWidget(self._label("Le plus important est la mémoire de la carte graphique (VRAM). Les cartes NVIDIA "
                                "marchent le mieux ; les AMD récentes aussi sous Linux.", "aide"))

        c = self._card(L)
        c.addWidget(self._label("Étape 1 — Le moteur (ComfyUI)", "titre"))
        self.eng_lab = self._label("")
        c.addWidget(self.eng_lab)
        row = QHBoxLayout()
        self.b_install = QPushButton("📥 Installer le moteur (environ 5 Go)")
        self.b_install.clicked.connect(self.install_engine)
        row.addWidget(self.b_install)
        b = QPushButton("🔄 Vérifier")
        b.clicked.connect(self.refresh_local)
        row.addWidget(b)
        cpu = QComboBox()
        cpu.addItem("🎮 Calcul sur la carte graphique (rapide)", False)
        cpu.addItem("🧠 Calcul sur le processeur (lent, mais marche partout)", True)
        cpu.setCurrentIndex(1 if self.cfg.get("atelier_cpu") else 0)
        cpu.currentIndexChanged.connect(lambda _i: (self._setv("atelier_cpu", cpu.currentData()), stop_comfy() if ours()
                                                    else None))
        c.addWidget(cpu)
        b = QPushButton("🔁 Réessayer la carte graphique")
        b.setToolTip("Oublie les réglages trouvés pour ta carte et refait la détection au prochain lancement.")
        b.clicked.connect(lambda: (stop_comfy(), reset_gpu_cache(), self.status.setText(
            "C'est noté : je réessaie la carte graphique à la prochaine création.")))
        row.addWidget(b)
        b = QPushButton("📂 Dossier des modèles")
        b.clicked.connect(lambda: (ckpt_dir().mkdir(parents=True, exist_ok=True), self.comp._open_path(ckpt_dir()))
                          if ENGINE_DIR else None)
        row.addWidget(b)
        row.addStretch(1)
        c.addLayout(row)

        L.addWidget(self._label("Étape 2 — Choisis un modèle", "titre"))
        self.cards = {}
        for m in MODELES:
            c = self._card(L)
            top = QHBoxLayout()
            t = self._label(f"<b>{m['nom']}</b> &nbsp;<span style='color:gray'>{m['tech']}</span>")
            t.setTextFormat(Qt.TextFormat.RichText)
            top.addWidget(t, 1)
            ver = QLabel("")
            top.addWidget(ver)
            c.addLayout(top)
            c.addWidget(self._label(m["desc"]))
            c.addWidget(self._label(f"🎮 Carte graphique : {m['vram']} Go minimum, {m['vram_ok']} Go conseillés   ·   "
                                    f"🧠 RAM : {m['ram']} Go   ·   💾 Disque : {m['disque']:g} Go   ·   "
                                    f"Vitesse : {m['vitesse']}   ·   📜 {m['licence']}", "aide"))
            row = QHBoxLayout()
            bd = QPushButton("📥 Télécharger")
            bd.clicked.connect(lambda _=False, mm=m: self.download_model(mm))
            row.addWidget(bd)
            bp = QPushButton("🔗 Page du modèle")
            bp.clicked.connect(lambda _=False, u=m["page"]: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(bp)
            bar = QProgressBar()
            bar.setVisible(False)
            row.addWidget(bar, 1)
            row.addStretch(0)
            c.addLayout(row)
            self.cards[m["id"]] = {"ver": ver, "btn": bd, "bar": bar}
        c = self._card(L)
        c.addWidget(self._label("Tu as déjà un modèle ou une autre IA ?", "titre"))
        if hasattr(self.comp, "open_add_ai"):
            ba = QPushButton("🧩 Ajouter un modèle téléchargé (glisser le fichier)…")
            ba.clicked.connect(lambda: self.comp.open_add_ai())
            c.addWidget(ba)
        c.addWidget(self._label("• Un fichier .safetensors (Civitai, Hugging Face…) : glisse-le dans « Ajouter un "
                                "modèle téléchargé », ou mets-le dans le « Dossier des modèles », puis clique sur "
                                "« Vérifier ».\n"
                                "• Forge ou AUTOMATIC1111 déjà installé : lance-le avec l'option --api, je le "
                                "trouve tout seul.\n• ComfyUI ou ComfyUI Desktop déjà installé : lance-le, je le "
                                "trouve aussi.", "aide"))
        L.addStretch(1)
        sc.setWidget(inner)
        outer.addWidget(sc)
        return w

    def _got_pc(self, pc):
        if isinstance(pc, Exception):
            pc = {"gpu": "", "vram": 0.0, "ram": 0, "libre": 0}
        self.pc = pc
        g = f"{pc['gpu'] or 'Carte graphique'} · <b>{pc['vram']:g} Go</b> de mémoire vidéo" if pc["vram"] else \
            "Carte graphique non détectée (les images seront lentes, ou utilise « En ligne »)"
        self.pc_lab.setText(f"{g}<br>🧠 {pc['ram']} Go de RAM · 💾 {pc['libre']} Go libres sur le disque")
        self.pc_lab.setTextFormat(Qt.TextFormat.RichText)
        self._update_cards()

    def _update_cards(self):
        have = set(self.local.get("models", []))
        for m in MODELES:
            c = self.cards[m["id"]]
            if m["id"] in self.dl:
                continue
            ico, txt = verdict(m, self.pc)
            c["ver"].setText(f"{ico} {txt}")
            if m["fichier"] in have:
                c["btn"].setText("✅ Installé")
                c["btn"].setEnabled(False)
            else:
                c["btn"].setText("📥 Télécharger")
                c["btn"].setEnabled(engine_installed() and not self.dl)

    def refresh_local(self):
        def work():
            info = {"type": "", "url": "", "models": []}
            url = find_comfy()
            if url:
                info.update(type="comfy", url=url, models=comfy_models(url))
                return info
            furl = find_forge(self.cfg.get("image_local_url") or FORGE_URL)
            if furl:
                info.update(type="forge", url=furl, models=forge_models(furl))
                return info
            if engine_installed():
                d = ckpt_dir()
                info.update(type="comfy", models=sorted(p.name for p in d.glob("*.safetensors")) if d.exists() else [])
            return info

        def then(info):
            if isinstance(info, Exception):
                info = {"type": "", "url": "", "models": []}
            self.local = info
            if info["url"]:
                self.eng_lab.setText(("✅ ComfyUI tourne" if info["type"] == "comfy" else "✅ Forge / AUTOMATIC1111 "
                                      "tourne") + f" ({info['url']}) · {len(info['models'])} modèle(s).")
                self.b_install.setText("🔄 Mettre à jour le moteur" if engine_installed() else
                                       "📥 Installer le moteur de Viki (environ 5 Go)")
            elif engine_installed():
                self.eng_lab.setText(f"✅ Installé. Je le démarre tout seul quand tu crées une image. "
                                     f"{len(info['models'])} modèle(s).")
                self.b_install.setText("🔄 Mettre à jour le moteur")
            else:
                self.eng_lab.setText("❌ Pas encore installé. Clique sur le bouton : un terminal s'ouvre et fait tout "
                                     "(10 à 20 minutes selon ta connexion).")
            self._update_cards()
            if self.where.currentData() == "local":
                self._where_changed()
        self._bg(work, then)

    def install_engine(self):
        if os.name == "nt":
            QDesktopServices.openUrl(QUrl("https://www.comfy.org/download"))
            self.comp.say("Sous Windows, installe « ComfyUI Desktop » depuis la page que j'ouvre, puis lance-le : "
                          "je le trouverai toute seule.")
            return
        src = Path(__file__).resolve().parent / "installer_images.sh"
        dst = Path(ENGINE_DIR).parent / src.name
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            dst.chmod(0o755)
        except Exception as e:
            return self.comp.say(f"Je n'ai pas pu préparer l'installation : {str(e)[:80]}")
        cmd = f'bash "{dst}" "{ENGINE_DIR}"; echo; read -p "Entrée pour fermer…"'
        g = getattr(self.C, "gestionpc", None)
        if g and g.terminal(cmd):
            self.comp.say("L'installation se fait dans le terminal. Quand c'est fini, clique sur « Vérifier » !")
        else:
            QApplication.clipboard().setText(f'bash "{dst}" "{ENGINE_DIR}"')
            self.comp.say("Je n'ai pas trouvé de terminal. La commande est copiée : colle-la dans un terminal.")

    def download_model(self, m):
        if not engine_installed():
            return self.comp.say("Installe d'abord le moteur (étape 1).")
        if self.pc.get("libre") and self.pc["libre"] < m["disque"] + 2:
            return self.comp.say(f"Il n'y a pas assez de place sur ton disque ({self.pc['libre']} Go libres).")
        ico, _t = verdict(m, self.pc)
        c = self.cards[m["id"]]
        self.dl[m["id"]] = True
        c["btn"].setText("⏹ Annuler")
        c["btn"].setEnabled(True)
        try:
            c["btn"].clicked.disconnect()
        except Exception:
            pass
        stop = {"v": False}
        c["btn"].clicked.connect(lambda: stop.__setitem__("v", True))
        c["bar"].setVisible(True)
        c["bar"].setRange(0, 1000)
        for k, cc in self.cards.items():
            if k != m["id"]:
                cc["btn"].setEnabled(False)
        tok = ""
        try:
            tok = self.C.hf_token()
        except Exception:
            pass
        last = {"t": 0}

        def prog(done, total):
            if time.time() - last["t"] > 0.3:
                last["t"] = time.time()
                txt = f"{done / 1024 ** 3:.1f} / {total / 1024 ** 3:.1f} Go" if total else f"{done / 1024 ** 3:.1f} Go"
                self._emit(lambda _r: (c["bar"].setValue(int(1000 * done / total) if total else 0),
                                               c["bar"].setFormat(txt), c["bar"].setTextVisible(True)), None)

        def then(res):
            self.dl.pop(m["id"], None)
            c["bar"].setVisible(False)
            try:
                c["btn"].clicked.disconnect()
            except Exception:
                pass
            c["btn"].clicked.connect(lambda _=False, mm=m: self.download_model(mm))
            if isinstance(res, Exception):
                if str(res) != "annulé":
                    self.comp.say(f"Le téléchargement n'a pas marché ({str(res)[:80]}). Je t'ouvre la page du modèle : "
                                  "télécharge le fichier et mets-le dans le dossier des modèles.")
                    QDesktopServices.openUrl(QUrl(m["page"]))
            else:
                self.comp.happy_until = time.monotonic() + 2
                self._model_ready(m)
            self.refresh_local()
        self._bg(lambda: download(m["url"], ckpt_dir() / m["fichier"], prog, lambda: stop["v"], tok), then)

    def _model_ready(self, m):
        self.comp.say(f"Le modèle « {m['nom']} » est installé ! Choisis « Sur mon PC » et crée ta première image. 🎨")
        self.cfg["atelier_modele"] = m["fichier"]
        self.where.setCurrentIndex(1)

    # ---------- onglet Aide
    def _tab_help(self):
        t = QTextEdit()
        t.setReadOnly(True)
        t.setHtml("""
<h3>✨ Bien décrire ton image</h3>
<ul>
<li><b>Dis ce qu'on voit</b> : le sujet, ce qu'il fait, où il est. « un renard roux qui dort sous un arbre en
automne ».</li>
<li><b>Ajoute l'ambiance</b> : la lumière, les couleurs, le moment. « au coucher du soleil, lumière dorée ».</li>
<li><b>Choisis un style</b> avec les boutons : anime, photo, aquarelle…</li>
<li><b>À éviter</b> (dans « Plus d'options ») : ce que tu ne veux pas voir. « texte, flou ».</li>
<li>Pas satisfait ? Clique sur <b>Encore une</b> : chaque image est différente.</li>
</ul>
<h3>📐 Les formats</h3>
<ul><li><b>Carré</b> : avatar, réseaux sociaux.</li><li><b>Portrait</b> : personnage, affiche.</li>
<li><b>Paysage</b> : décor, scène.</li><li><b>Fond d'écran</b> : 16:9, pour ton bureau.</li>
<li><b>Téléphone</b> : 9:16, fond d'écran de mobile.</li></ul>
<h3>☁️ En ligne ou 🖥️ sur ton PC ?</h3>
<ul><li><b>En ligne</b> : rien à installer, marche sur tous les PC. Ta description part sur internet
(pollinations.ai).</li>
<li><b>Sur ton PC</b> : privé et illimité, mais il faut une carte graphique correcte. L'onglet « IA sur mon PC »
te dit quel modèle ton ordinateur peut faire tourner.</li>
<li><b>Perchance</b> : j'ouvre le site et je copie ta description.</li></ul>
<h3>🎮 Quel modèle pour mon PC ?</h3>
<ul><li>Moins de 6 Go de mémoire vidéo : <b>Léger et rapide</b>.</li>
<li>8 à 12 Go : <b>Polyvalent</b> ou <b>Anime et manga</b>.</li>
<li>12 Go et plus avec 32 Go de RAM : <b>Très beau et rapide</b> ou <b>Qualité maximale</b>.</li></ul>
<p>Tu peux aussi me parler : « génère une image d'un dragon bleu », « dessine-moi un fond d'écran cyberpunk ».</p>
<p><i>Je ne crée pas d'images sexuelles ou violentes. Respecte les droits des personnes et des œuvres.</i></p>
""")
        return t

    def closeEvent(self, e):
        self.cancel = True
        super().closeEvent(e)


# ================================================================== MUSIQUE
MUSIQUE_MODELES = [
    {"id": "ace15", "nom": "Chansons complètes (recommandé)", "tech": "ACE-Step 1.5 Turbo",
     "fichier": "ace_step_1.5_turbo_aio.safetensors", "v": 15,
     "url": "https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files/resolve/main/checkpoints/ace_step_1.5_turbo_aio.safetensors",
     "page": "https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files",
     "desc": "Avec voix ou instrumental, tous les styles, jusqu'à plusieurs minutes. Très rapide, même sur une petite carte.",
     "vram": 4, "vram_ok": 8, "ram": 16, "disque": 10, "vitesse": "⚡⚡⚡", "licence": "Libre (MIT)"},
    {"id": "ace1", "nom": "Chansons, version 1", "tech": "ACE-Step v1 3.5B",
     "fichier": "ace_step_v1_3.5b.safetensors", "v": 1,
     "url": "https://huggingface.co/Comfy-Org/ACE-Step_ComfyUI_repackaged/resolve/main/all_in_one/ace_step_v1_3.5b.safetensors",
     "page": "https://huggingface.co/Comfy-Org/ACE-Step_ComfyUI_repackaged",
     "desc": "L'ancienne version : plus lourde et plus lente. Utile seulement si la 1.5 ne marche pas chez toi.",
     "vram": 8, "vram_ok": 12, "ram": 16, "disque": 7.7, "vitesse": "⚡⚡", "licence": "Libre (Apache 2.0)"},
]
GENRES = [("🎧 Lo-fi", "lofi hip hop, chill, mellow, vinyl crackle"), ("🌆 Synthwave", "synthwave, retro 80s, analog synths"),
          ("🎤 Pop", "modern pop, catchy, upbeat"), ("🎸 Rock", "rock, electric guitars, energetic drums"),
          ("⚡ Électro", "electronic, edm, punchy bass, energetic"), ("🎹 Piano calme", "solo piano, calm, emotional"),
          ("🎻 Orchestral", "orchestral, cinematic, epic strings"), ("🎙️ Hip-hop", "hip hop, boom bap, groovy"),
          ("🌌 Ambient", "ambient, atmospheric, dreamy pads"), ("🌸 J-pop", "j-pop, anime opening, bright")]
VOIX = [("🎼 Instrumental", "instrumental"), ("👩 Voix féminine", "female vocals"), ("👨 Voix masculine", "male vocals")]
DUREES = [("30 s", 30), ("1 min", 60), ("2 min", 120), ("3 min", 180)]
ACE_DEMO = "https://huggingface.co/spaces/ACE-Step/Ace-Step-v1.5"
SUNO = "https://suno.com/create"


def _fill(info, cls, given):
    """Entrées d'un nœud ComfyUI : les nôtres + les valeurs par défaut des autres (d'après /object_info)."""
    spec = info.get(cls, {}).get("input", {}).get("required", {})
    out = {}
    for k, v in spec.items():
        if k in given:
            out[k] = given[k]
            continue
        typ = v[0] if v else None
        opts = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
        if isinstance(typ, list):
            out[k] = typ[0] if typ else ""
        elif typ == "COMBO":
            o = opts.get("options") or []
            out[k] = opts.get("default", o[0] if o else "")
        elif "default" in opts:
            out[k] = opts["default"]
    for k, v in given.items():
        out.setdefault(k, v)
    return out


def comfy_music(url, ckpt, tags, lyrics, seconds, seed, stop, prog=None):
    v15 = "1.5" in ckpt or "15" in ckpt.replace("3.5", "")
    enc, lat = ("TextEncodeAceStepAudio1.5", "EmptyAceStep1.5LatentAudio") if v15 else \
        ("TextEncodeAceStepAudio", "EmptyAceStepLatentAudio")
    classes = [enc, lat, "SaveAudioMP3", "SaveAudio", "ModelSamplingAuraFlow", "ConditioningZeroOut"]
    info = {}
    for c in classes:
        try:
            info.update(json.loads(_http(url + "/object_info/" + urllib.parse.quote(c), timeout=10)))
        except Exception:
            pass
    if enc not in info:
        raise RuntimeError("ton ComfyUI est trop ancien pour ce modèle : mets à jour le moteur")
    save = "SaveAudioMP3" if "SaveAudioMP3" in info else "SaveAudio"
    g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
         "2": {"class_type": enc, "inputs": _fill(info, enc, {"clip": ["1", 1], "tags": tags, "lyrics": lyrics or
                                                              "[instrumental]", "duration": seconds, "seed": seed})},
         "3": {"class_type": lat, "inputs": _fill(info, lat, {"seconds": seconds, "batch_size": 1})}}
    model = ["1", 0]
    if v15 and "ModelSamplingAuraFlow" in info:
        g["5"] = {"class_type": "ModelSamplingAuraFlow", "inputs": _fill(info, "ModelSamplingAuraFlow", {"model": model,
                                                                                                         "shift": 3.0})}
        model = ["5", 0]
    if v15 and "ConditioningZeroOut" in info:
        g["6"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
        neg = ["6", 0]
    else:
        g["6"] = {"class_type": enc, "inputs": dict(g["2"]["inputs"], tags="", lyrics="")}
        neg = ["6", 0]
    steps, cfg = (8, 1.0) if v15 else (50, 5.0)
    g["4"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler",
                                                   "scheduler": "simple", "denoise": 1.0, "model": model,
                                                   "positive": ["2", 0], "negative": neg, "latent_image": ["3", 0]}}
    g["7"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}}
    g["8"] = {"class_type": save, "inputs": _fill(info, save, {"audio": ["7", 0], "filename_prefix": "audio/viki"})}
    outs = comfy_run(url, g, stop, prog)
    for out in outs.values():
        for a in out.get("audio", []):
            return comfy_file(url, a), Path(a["filename"]).suffix or ".mp3"
    raise ComfyError("le moteur n'a pas renvoyé de musique", json.dumps(outs)[:2000])


def lyrics_prompt(theme, genre, langue="français"):
    return (f"Écris des paroles de chanson ORIGINALES (inventées par toi, jamais celles d'une chanson existante) en "
            f"{langue}, sur ce thème : {theme or 'la vie de tous les jours'}. Style musical : {genre or 'pop'}. "
            "Structure avec ces balises sur leur propre ligne : [verse], [chorus], [verse], [chorus], [bridge], [chorus]. "
            "Phrases courtes et faciles à chanter, 4 lignes par partie. Réponds uniquement avec les paroles.")


class MusicStudio(Atelier):
    """Studio de musique : même moteur (ComfyUI) que l'atelier d'images."""

    def __init__(self, comp, C):
        QWidget.__init__(self, None, Qt.WindowType.Window)
        self.comp, self.C = comp, C
        self.cfg = comp.cfg
        self.setObjectName("atelier")
        self.apple = bool(pomme) and pomme.actif(C, comp.cfg)
        self.setStyleSheet(pomme.STUDIO if self.apple else CSS)
        self.setWindowTitle("🎵 Studio musique — " + comp.char.get("name", "Viki"))
        scr = self.screen().availableGeometry() if self.screen() else None
        self.resize(min(1100, int(scr.width() * 0.85)) if scr else 1000, min(780, int(scr.height() * 0.88)) if scr else 740)
        self.sig = _Sig()
        self.sig.done.connect(lambda fn, res: fn(res))
        self.busy = self.cancel = False
        self.pc = {"gpu": "", "vram": 0.0, "ram": 0, "libre": 0}
        self.local = {"type": "", "url": "", "models": []}
        self.dl = {}
        self.player = None
        self.last = None
        self.view = None
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._tab_music(), "🎵 Créer")
        self.tabs.addTab(self._tab_music_local(), "🖥️ IA sur mon PC")
        self.tabs.addTab(self._tab_music_help(), "❓ Aide")
        if self.apple:
            pomme.pictos_onglets(C, self.tabs, ("#ff375f", "#8e8e93", "#30b0c7"))
        self._bg(pc_info, self._got_pc)
        self.refresh_local()

    def music_dir(self):
        from PyQt6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation) or str(Path.home())
        return Path(base) / "Viki"

    # ---------- onglet Créer
    def _tab_music(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QWidget()
        L = QVBoxLayout(left)
        L.setSpacing(8)
        L.addWidget(self._label("1. Le style", "titre"))
        self.genre_i = int(self.cfg.get("studio_genre", 0))
        r, self.g_genre = self._chips([g[0] for g in GENRES], self.genre_i, lambda i: self._setv("studio_genre", i))
        L.addLayout(self._wrap(r))
        self.tags = QLineEdit(self.cfg.get("studio_tags", ""))
        self.tags.setPlaceholderText("En plus (facultatif) : ex. « triste, pluie, guitare acoustique, 90 bpm »")
        L.addWidget(self.tags)
        L.addWidget(self._label("2. La voix", "titre"))
        r, self.g_voix = self._chips([v[0] for v in VOIX], int(self.cfg.get("studio_voix", 0)),
                                     lambda i: (self._setv("studio_voix", i), self._voice_changed()))
        L.addLayout(r)
        self.lyr_box = QWidget()
        LB = QVBoxLayout(self.lyr_box)
        LB.setContentsMargins(0, 0, 0, 0)
        LB.addWidget(self._label("3. Les paroles", "titre"))
        row = QHBoxLayout()
        self.theme = QLineEdit()
        self.theme.setPlaceholderText("Le thème : ex. « une nuit d'été en ville »")
        row.addWidget(self.theme, 1)
        b = QPushButton("✍️ Écris-les pour moi")
        b.clicked.connect(self._write_lyrics)
        row.addWidget(b)
        LB.addLayout(row)
        self.lyrics = QTextEdit()
        self.lyrics.setAcceptRichText(False)
        self.lyrics.setPlaceholderText("[verse]\nTes paroles ici…\n\n[chorus]\nLe refrain…\n\n"
                                       "Écris les tiennes, ou clique sur « Écris-les pour moi ».")
        self.lyrics.setMinimumHeight(140)
        LB.addWidget(self.lyrics)
        L.addWidget(self.lyr_box)
        L.addWidget(self._label("4. La durée", "titre"))
        r, self.g_dur = self._chips([d[0] for d in DUREES], int(self.cfg.get("studio_duree", 1)),
                                    lambda i: self._setv("studio_duree", i))
        L.addLayout(r)
        L.addWidget(self._label("5. Où la créer ?", "titre"))
        self.where = QComboBox()
        self.where.addItem("🖥️  Sur mon PC — privé, IA libre (ACE-Step)", "local")
        self.where.addItem("🌐  Démo ACE-Step en ligne — je copie tout et j'ouvre la page", "demo")
        self.where.addItem("🌐  Suno — je copie tout et j'ouvre le site", "suno")
        self.where.setCurrentIndex(max(0, self.where.findData(self.cfg.get("studio_moteur", "local"))))
        self.where.currentIndexChanged.connect(self._where_music)
        L.addWidget(self.where)
        self.where_help = self._label("", "aide")
        L.addWidget(self.where_help)
        row = QHBoxLayout()
        self.model_lab = QLabel("Modèle :")
        row.addWidget(self.model_lab)
        self.model = QComboBox()
        row.addWidget(self.model, 1)
        self.b_more_models = QPushButton("➕ Ajouter")
        self.b_more_models.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        row.addWidget(self.b_more_models)
        L.addLayout(row)
        L.addStretch(1)
        self.b_go = QPushButton("🎵  Créer la musique")
        self.b_go.setObjectName("creer")
        self.b_go.clicked.connect(self.generate_music)
        L.addWidget(self.b_go)
        self._progress_panel(L)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(left)
        sc.setMinimumWidth(480)
        lay.addWidget(sc, 6)
        right = QVBoxLayout()
        right.addWidget(self._label("Mes créations" if getattr(self, "apple", False) else "🎶 Mes créations",
                                    "titre"))
        self.tracks = QListWidget()
        if getattr(self, "apple", False):
            from PyQt6.QtCore import QSize as _QS
            self.tracks.setIconSize(_QS(34, 34))
        self.tracks.itemDoubleClicked.connect(lambda it: self._play(it.data(Qt.ItemDataRole.UserRole)))
        right.addWidget(self.tracks, 1)
        row = QHBoxLayout()
        for txt, fn in (("▶ Écouter", lambda: self.tracks.currentItem() and
                         self._play(self.tracks.currentItem().data(Qt.ItemDataRole.UserRole))),
                        ("⏹ Stop", self._stop), ("📂 Dossier", lambda: (self.music_dir().mkdir(parents=True, exist_ok=True),
                                                                       self.comp._open_path(self.music_dir())))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        right.addLayout(row)
        lay.addLayout(right, 4)
        self._load_tracks()
        self._voice_changed()
        self._where_music()
        return w

    def _voice_changed(self):
        self.lyr_box.setVisible(self.g_voix.checkedId() != 0)

    def _where_music(self, *_a):
        e = self.where.currentData()
        self._setv("studio_moteur", e)
        for x in (self.model_lab, self.model, self.b_more_models):
            x.setVisible(e == "local")
        self.model.clear()
        if e == "suno":
            self.where_help.setText("Je copie le style et les paroles. Sur Suno, colle-les dans « Custom ». "
                                    "Il faut un compte Suno.")
        elif e == "demo":
            self.where_help.setText("La démo officielle d'ACE-Step sur Hugging Face : rien à installer, mais il peut "
                                    "y avoir de l'attente.")
        else:
            mods = [m for m in self.local.get("models", []) if re.search(r"ace|^musique-", m, re.I)]
            if mods:
                self.where_help.setText("Sur ton PC, rien ne sort de chez toi.")
                for m in mods:
                    self.model.addItem(next((x["nom"] + f" ({x['tech']})" for x in MUSIQUE_MODELES if x["fichier"] == m),
                                            m), m)
            elif engine_installed() or self.local["type"]:
                self.where_help.setText("Le moteur est prêt. Il te faut un modèle de musique : onglet « IA sur mon PC ».")
            else:
                self.where_help.setText("Rien n'est encore installé : va dans l'onglet « IA sur mon PC ». C'est le "
                                        "même moteur que pour les images.")

    def _where_changed(self, *_a):          # appelé par refresh_local (classe parente)
        self._where_music()

    def _update_cards(self):
        have = set(self.local.get("models", []))
        for m in MUSIQUE_MODELES:
            c = self.cards[m["id"]]
            if m["id"] in self.dl:
                continue
            ico, txt = verdict(m, self.pc)
            c["ver"].setText(f"{ico} {txt}")
            if m["fichier"] in have:
                c["btn"].setText("✅ Installé")
                c["btn"].setEnabled(False)
            else:
                c["btn"].setText("📥 Télécharger")
                c["btn"].setEnabled(engine_installed() and not self.dl)

    def _tab_music_local(self):
        saved = MODELES[:]
        try:
            MODELES[:] = MUSIQUE_MODELES
            w = self._tab_local()
        finally:
            MODELES[:] = saved
        return w

    def _model_ready(self, m):
        self.comp.say(f"Le modèle « {m['nom']} » est installé ! On compose ta première musique ? 🎶")
        self.where.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)

    def _write_lyrics(self):
        if not (self.comp.ollama_ok or self.comp.ia_remote()):
            return self.status.setText("Pour écrire des paroles, il me faut mon IA de discussion (Réglages → Discussion).")
        self.status.setText("J'écris des paroles… ✍️")
        genre = GENRES[max(0, self.g_genre.checkedId())][0][2:].strip()
        theme = self.theme.text().strip()

        def work():
            return self.comp.llm([{"role": "user", "content": lyrics_prompt(theme, genre)}], timeout=120)

        def then(res):
            if isinstance(res, Exception) or not res:
                return self.status.setText("Je n'ai pas réussi à écrire les paroles.")
            self.lyrics.setPlainText(res.strip())
            self.status.setText("Voilà ! Tu peux les modifier comme tu veux.")
        self._bg(work, then)

    def _style_text(self):
        g = GENRES[max(0, self.g_genre.checkedId())][1]
        v = VOIX[max(0, self.g_voix.checkedId())][1]
        extra = self.tags.text().strip()
        self._setv("studio_tags", extra)
        return ", ".join(x for x in (g, v, extra) if x)

    def generate_music(self):
        if self.busy:
            self.cancel = True
            self.status.setText("J'arrête…")
            return
        tags = self._style_text()
        lyr = self.lyrics.toPlainText().strip() if self.g_voix.checkedId() != 0 else ""
        if media.blocked(tags + " " + lyr):
            return self.status.setText("Je ne fais pas ce genre de contenu. Essaie autre chose !")
        secs = DUREES[max(0, self.g_dur.checkedId())][1]
        e = self.where.currentData()
        if e in ("suno", "demo"):
            QApplication.clipboard().setText(f"Style : {tags}\n\n{lyr}" if lyr else f"Style : {tags}")
            QDesktopServices.openUrl(QUrl(SUNO if e == "suno" else ACE_DEMO))
            return self.status.setText("Copié ! Colle le style et les paroles sur la page qui s'ouvre.")
        model = self.model.currentData()
        if not model:
            self.tabs.setCurrentIndex(1)
            return self.status.setText("Installe d'abord un modèle de musique dans « IA sur mon PC ».")
        self.busy, self.cancel = True, False
        self.b_go.setText("⏹  Arrêter")
        self._job_start(1, "Morceau")
        self._amd_retried = False
        self.status.setText("Je compose… 🎶")
        self.comp.react = ("fredonne", time.monotonic())
        seed = random.randint(1, 2 ** 31 - 2)
        vram, info = self._calc_vram(), dict(self.local)
        name = (self.theme.text().strip() or GENRES[max(0, self.g_genre.checkedId())][0][2:]).strip()

        def work():
            url = self._local_url(info, vram)
            self._job_item(0)
            self._st("Je compose… 🎶")
            try:
                data, ext = comfy_music(url, model, tags, lyr, secs, seed, lambda: self.cancel, self._job_prog)
            except Exception as err:
                url2 = self._retry_amd(err, vram)
                if not url2:
                    raise
                self._job_item(0)
                data, ext = comfy_music(url2, model, tags, lyr, secs, seed, lambda: self.cancel, self._job_prog)
            d = self.music_dir()
            d.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "-", media._sa(name))[:40].strip("-") or "musique"
            p = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}{ext}"
            p.write_bytes(data)
            return p
        self.t0 = time.time()

        def then(res):
            self.busy = False
            self.b_go.setText("🎵  Créer la musique")
            el = time.time() - self.t0
            self._job_stop()
            if isinstance(res, Exception):
                if str(res) == "annulé":
                    return self.status.setText("C'est arrêté.")
                hint = self._fail(res)
                self.status.setText(f"Oups, ça n'a pas marché.\n{hint}\n(Détail : {str(res)[:140]})")
                return self.comp.say("Je n'ai pas réussi à composer… " + hint)
            self._add_track(res, first=True)
            self.tracks.setCurrentRow(0)
            self.status.setText(f"Terminé en {fmt_s(el)} 🎶 — rangée dans Musique → Viki.")
            self.comp.happy_until = time.monotonic() + 2
            self.comp._spawn("note", 5)
            self.comp.say("Ta musique est prête ! Je te la fais écouter. 🎶")
            self._play(str(res))
        self._bg(work, then)

    # ---------- lecture
    def _add_track(self, p, first=False):
        if getattr(self, "apple", False):                 # comme une liste de morceaux : tuile, titre, date
            import datetime as _dt
            from PyQt6.QtGui import QIcon
            try:
                quand = _dt.datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%d/%m/%Y · %H:%M")
            except Exception:
                quand = ""
            it = QListWidgetItem(QIcon(pomme.tuile(self.C, "🎵", "#ff375f", 34)),
                                 Path(p).stem.replace("_", " ") + ("\n" + quand if quand else ""))
        else:
            it = QListWidgetItem("🎵 " + Path(p).stem)
        it.setData(Qt.ItemDataRole.UserRole, str(p))
        if first:
            self.tracks.insertItem(0, it)
        else:
            self.tracks.addItem(it)

    def _load_tracks(self):
        d = self.music_dir()
        if d.exists():
            for p in sorted((x for x in d.iterdir() if x.suffix.lower() in (".mp3", ".flac", ".wav", ".ogg", ".opus")),
                            key=lambda x: -x.stat().st_mtime)[:50]:
                self._add_track(p)

    def _play(self, path):
        self._stop()
        if shutil.which("mpv"):                     # le plus fiable : mpv en arrière-plan
            try:
                self._mpv = subprocess.Popen(["mpv", "--no-video", "--really-quiet", str(path)], env=clean_env(),
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                self.comp.music_playing = True
                return
            except Exception:
                pass
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            if self.player is None:
                self.player = QMediaPlayer(self)
                self.audio = QAudioOutput(self)
                self.audio.setVolume(0.8)
                self.player.setAudioOutput(self.audio)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.comp.music_playing = True
        except Exception:
            self.comp._open_path(path)

    def _stop(self):
        p = getattr(self, "_mpv", None)
        if p and p.poll() is None:
            p.terminate()
        if self.player:
            self.player.stop()
        self.comp.music_playing = False

    def closeEvent(self, e):
        self._stop()
        self.cancel = True
        QWidget.closeEvent(self, e)

    def _tab_music_help(self):
        t = QTextEdit()
        t.setReadOnly(True)
        t.setHtml("""
<h3>🎵 Créer une musique</h3>
<ol><li><b>Choisis un style</b>, et ajoute des précisions si tu veux : l'ambiance, les instruments, le tempo
(« triste, guitare acoustique, 90 bpm »).</li>
<li><b>Instrumental ou avec voix</b>. Avec voix, écris tes paroles ou demande-moi de les écrire.</li>
<li><b>La durée</b>, puis <b>Créer</b>. Ta musique est rangée dans Musique → Viki.</li></ol>
<h3>✍️ Les paroles</h3>
<p>Les balises <b>[verse]</b> (couplet), <b>[chorus]</b> (refrain), <b>[bridge]</b> (pont) aident l'IA à
construire la chanson. Les IA chantent mieux en anglais ; le français marche, un peu moins bien.</p>
<h3>🖥️ Sur mon PC</h3>
<p>C'est le même moteur que pour les images : si tu l'as déjà installé, il suffit de télécharger le modèle
ACE-Step. Il marche même avec une petite carte graphique (4 Go).</p>
<p><i>Crée des musiques originales : ne copie pas les paroles ou la voix d'un artiste existant.</i></p>
""")
        return t
