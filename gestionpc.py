"""Gestion du PC : tableau de bord (avec 24 h d'historique), « pourquoi mon PC rame ? », sauvegarde en un clic,
mises à jour (avec les nouvelles d'Arch Linux), santé des disques, ménage intelligent, modes jeu / nuit,
batterie des casques et souris Bluetooth.

Lecture directe de /proc et /sys (pas de dépendance). Rien n'est supprimé sans ton accord, et le ménage
passe par la corbeille.
"""
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

HIST_FILE = None          # fixé par compagnon.py : ~/.local/share/viki/historique_pc.json
HOME = Path.home()


def human(n):
    for u in ("o", "Ko", "Mo", "Go", "To"):
        if abs(n) < 1024 or u == "To":
            return f"{n:.0f} {u}" if u in ("o", "Ko") else f"{n:.1f} {u}"
        n /= 1024


def _read(p):
    try:
        return Path(p).read_text().strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ mesures
def _cpu_times():
    v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v), idle, (v[4] if len(v) > 4 else 0)


def cpu_percent(interval=0.4):
    t1, i1, w1 = _cpu_times()
    time.sleep(interval)
    t2, i2, w2 = _cpu_times()
    dt = max(1, t2 - t1)
    return round(100 * (1 - (i2 - i1) / dt), 1), round(100 * (w2 - w1) / dt, 1)    # (utilisation, attente disque)


def mem():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        m[k] = int(v.split()[0]) * 1024
    tot, av = m["MemTotal"], m.get("MemAvailable", m["MemFree"])
    swap_used = m.get("SwapTotal", 0) - m.get("SwapFree", 0)
    return {"total": tot, "utilise": tot - av, "pct": round(100 * (tot - av) / tot, 1), "swap": swap_used,
            "swap_total": m.get("SwapTotal", 0)}


def gpu():
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dev = card / "device"
        busy = _read(dev / "gpu_busy_percent")
        if busy.isdigit():
            used, tot = _read(dev / "mem_info_vram_used"), _read(dev / "mem_info_vram_total")
            return {"pct": int(busy), "vram": int(used) if used.isdigit() else 0,
                    "vram_total": int(tot) if tot.isdigit() else 0}
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            r = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
            u, mu, mt, t = [x.strip() for x in r.stdout.splitlines()[0].split(",")]
            return {"pct": int(u), "vram": int(mu) * 2 ** 20, "vram_total": int(mt) * 2 ** 20, "temp": float(t)}
        except Exception:
            pass
    return None


def temps():
    out = {}
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        name = _read(hw / "name")
        if name in ("k10temp", "coretemp", "zenpower", "cpu_thermal") and "cpu" not in out:
            v = _read(hw / "temp1_input")
            if v.isdigit():
                out["cpu"] = int(v) / 1000
        elif name == "amdgpu" and "gpu" not in out:
            for lab in hw.glob("temp*_label"):
                if _read(lab) in ("edge", "junction"):
                    v = _read(str(lab).replace("_label", "_input"))
                    if v.isdigit():
                        out["gpu"] = int(v) / 1000
                        break
        elif name == "nvme" and "nvme" not in out:
            v = _read(hw / "temp1_input")
            if v.isdigit():
                out["nvme"] = int(v) / 1000
    return out


def disks():
    out = []
    seen = set()
    for label, p in (("Système", "/"), ("Dossier perso", str(HOME))):
        try:
            st = os.statvfs(p)
            dev = os.stat(p).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            tot, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
            out.append({"nom": label, "chemin": p, "total": tot, "libre": free, "pct": round(100 * (1 - free / tot), 1)})
        except Exception:
            pass
    return out


def sample():
    c, w = cpu_percent(0.3)
    g = gpu() or {}
    t = temps()
    m = mem()
    return {"t": time.time(), "cpu": c, "iowait": w, "ram": m["pct"], "gpu": g.get("pct"),
            "tcpu": t.get("cpu"), "tgpu": t.get("gpu", g.get("temp"))}


def record_history():
    """Toutes les 5 min : une mesure, gardée 24 h."""
    try:
        h = json.loads(Path(HIST_FILE).read_text())
    except Exception:
        h = []
    h.append(sample())
    h = [x for x in h if x["t"] > time.time() - 86400][-300:]
    try:
        Path(HIST_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(HIST_FILE).write_text(json.dumps(h))
    except Exception:
        pass
    return h


def history():
    try:
        return json.loads(Path(HIST_FILE).read_text())
    except Exception:
        return []


# ------------------------------------------------------------------ programmes gourmands
PAGE = os.sysconf("SC_PAGE_SIZE")


def _proc_ticks():
    out = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            raw = (d / "stat").read_text()
            name = raw[raw.index("(") + 1:raw.rindex(")")]
            f = raw[raw.rindex(")") + 2:].split()
            rss = int((d / "statm").read_text().split()[1]) * PAGE
            out[int(d.name)] = (name, int(f[11]) + int(f[12]), rss, d.stat().st_uid)
        except Exception:
            pass
    return out


NOMS = {"firefox": "Firefox", "Isolated Web Co": "Firefox (onglets)", "Web Content": "Firefox (onglets)",
        "chrome": "Chrome", "chromium": "Chromium", "brave": "Brave", "steam": "Steam", "steamwebhelper": "Steam",
        "plasmashell": "Bureau KDE (plasmashell)", "kwin_wayland": "KDE (affichage)", "kwin_x11": "KDE (affichage)",
        "baloo_file": "Recherche de fichiers KDE (Baloo)", "baloo_file_extractor": "Recherche de fichiers KDE (Baloo)",
        "ollama": "Ollama (son IA)", "ollama_llama_server": "Ollama (son IA)", "Discord": "Discord",
        "code": "VS Code", "electron": "Appli Electron", "java": "Java (Minecraft ?)", "python3": "Python",
        "kdeconnectd": "KDE Connect", "packagekitd": "Mises à jour (PackageKit)", "pacman": "pacman"}


def top_processes(interval=1.0, n=8):
    """Programmes regroupés par nom : processeur (%) sur 1 s et mémoire."""
    a = _proc_ticks()
    t0 = time.monotonic()
    time.sleep(interval)
    b = _proc_ticks()
    dt = (time.monotonic() - t0) * os.sysconf("SC_CLK_TCK")
    ncpu = os.cpu_count() or 1
    me = os.getuid()
    groups = {}
    for pid, (name, ticks, rss, uid) in b.items():
        cpu = max(0, ticks - a.get(pid, (name, ticks))[1]) / dt * 100     # en % d'un cœur
        g = groups.setdefault(NOMS.get(name, name), {"nom": NOMS.get(name, name), "cpu": 0.0, "ram": 0, "pids": [],
                                                      "a_moi": True})
        g["cpu"] += cpu
        g["ram"] += rss
        g["pids"].append(pid)
        g["a_moi"] = g["a_moi"] and uid == me
    lst = list(groups.values())
    for g in lst:
        g["coeur"] = round(g["cpu"], 1)               # en % d'un cœur (un programme bloqué = 100 %)
        g["cpu"] = round(g["cpu"] / ncpu, 1)        # en % de tout le processeur
    by_cpu = sorted(lst, key=lambda g: -g["cpu"])[:n]
    by_ram = sorted(lst, key=lambda g: -g["ram"])[:n]
    return by_cpu, by_ram


def why_slow():
    """Diagnostic en une phrase + suspects."""
    c, wait = cpu_percent(0.5)
    m = mem()
    t = temps()
    by_cpu, by_ram = top_processes()
    raisons, suspects = [], []
    if c > 75 and by_cpu and by_cpu[0]["cpu"] > 25:
        raisons.append(f"le processeur est occupé à {c:.0f} %, surtout par {by_cpu[0]['nom']} "
                       f"({by_cpu[0]['cpu']:.0f} %)")
        suspects.append(by_cpu[0])
    elif by_cpu and by_cpu[0]["coeur"] > 85 and (os.cpu_count() or 1) > 2:
        raisons.append(f"{by_cpu[0]['nom']} fait tourner un cœur du processeur à fond ({by_cpu[0]['coeur']:.0f} %)")
        suspects.append(by_cpu[0])
    if m["pct"] > 88:
        top = by_ram[0] if by_ram else None
        raisons.append(f"la mémoire est presque pleine ({m['pct']:.0f} %)"
                       + (f", {top['nom']} en prend {human(top['ram'])}" if top else ""))
        if top and top not in suspects:
            suspects.append(top)
    if m["swap"] > 1.5 * 2 ** 30 and m["pct"] > 75:
        raisons.append(f"il utilise {human(m['swap'])} de swap (le disque remplace la mémoire, c'est lent)")
    if wait > 20:
        raisons.append(f"le disque est très sollicité ({wait:.0f} % d'attente)")
    if (t.get("cpu") or 0) > 92:
        raisons.append(f"le processeur chauffe ({t['cpu']:.0f} °C) et ralentit pour se protéger")
    if (t.get("gpu") or 0) > 95:
        raisons.append(f"la carte graphique chauffe ({t['gpu']:.0f} °C)")
    for d in disks():
        if d["libre"] < 5 * 2 ** 30:
            raisons.append(f"le disque « {d['nom']} » est presque plein ({human(d['libre'])} libres)")
    if not raisons:
        txt = (f"Je ne vois rien d'anormal : processeur à {c:.0f} %, mémoire à {m['pct']:.0f} %. "
               + (f"Ce qui consomme le plus : {by_cpu[0]['nom']}." if by_cpu and by_cpu[0]['cpu'] > 3 else ""))
    else:
        txt = "Ton PC rame parce que " + " ; ".join(raisons) + "."
    return txt, suspects, by_cpu, by_ram


def close_group(g, force=False):
    sig = signal.SIGKILL if force else signal.SIGTERM
    n = 0
    for pid in g["pids"]:
        try:
            os.kill(pid, sig)
            n += 1
        except Exception:
            pass
    return n


# ------------------------------------------------------------------ sauvegarde
def external_drives():
    out = []
    user = os.environ.get("USER") or HOME.name
    for base in (Path("/run/media") / user, Path("/media") / user, Path("/media"), Path("/mnt")):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            try:
                if d.is_dir() and os.path.ismount(d) and os.access(d, os.W_OK):
                    st = os.statvfs(d)
                    out.append({"chemin": str(d), "nom": d.name, "libre": st.f_bavail * st.f_frsize})
            except Exception:
                pass
    return out


def backup(sources, dest, progress=None, stop=None):
    """Copie (sans rien effacer) chaque dossier dans <dest>/Sauvegarde Viki/<nom>. -> (fichiers, erreurs)"""
    root = Path(dest) / "Sauvegarde Viki"
    root.mkdir(parents=True, exist_ok=True)
    rsync = shutil.which("rsync")
    errors = []
    for i, src in enumerate(sources):
        src = Path(src)
        if not src.is_dir():
            continue
        target = root / src.name
        if rsync:
            p = subprocess.Popen([rsync, "-a", "--info=progress2", "--no-inc-recursive",
                                  "--exclude=.cache", "--exclude=node_modules", "--exclude=.venv*",
                                  str(src) + "/", str(target) + "/"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            buf = ""
            while True:
                ch = p.stdout.read(1)
                if not ch:
                    break
                if ch in "\r\n":
                    m = re.search(r"(\d+)%", buf)
                    if m and progress:
                        progress((i + int(m.group(1)) / 100) / len(sources), src.name)
                    buf = ""
                else:
                    buf += ch
                if stop and stop():
                    p.terminate()
                    break
            p.wait()
            if p.returncode not in (0, 24):                    # 24 : fichiers disparus pendant la copie
                errors.append(f"{src.name} : {p.stderr.read()[-200:]}")
        else:
            for f in src.rglob("*"):
                if stop and stop():
                    break
                try:
                    rel = f.relative_to(src)
                    if any(part in (".cache", "node_modules") for part in rel.parts):
                        continue
                    t = target / rel
                    if f.is_dir():
                        t.mkdir(parents=True, exist_ok=True)
                    elif not t.exists() or t.stat().st_mtime < f.stat().st_mtime:
                        t.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, t)
                except Exception as e:
                    errors.append(str(e)[:120])
        if progress:
            progress((i + 1) / len(sources), src.name)
    return errors


# ------------------------------------------------------------------ mises à jour
def distro():
    try:
        import paquets
        return {"pacman": "arch", "apt": "debian", "dnf": "fedora", "zypper": "suse", "xbps": "void",
                "apk": "alpine", "eopkg": "solus", "emerge": "gentoo", "nix": "nixos", "rpm-ostree": "atomic",
                "transactional": "suse-immuable"}.get(paquets.gestionnaire(), "")
    except Exception:
        pass
    if shutil.which("pacman"):
        return "arch"
    if shutil.which("apt"):
        return "debian"
    if shutil.which("dnf"):
        return "fedora"
    return ""


def pending_updates():
    d = distro()
    try:
        if d == "arch" and shutil.which("checkupdates"):
            r = subprocess.run(["checkupdates"], capture_output=True, text=True, timeout=180)
            return [l.strip() for l in r.stdout.splitlines() if l.strip()]
        if d == "debian":
            r = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=60)
            return [l.split("/")[0] for l in r.stdout.splitlines()[1:] if "/" in l]
        if d == "fedora":
            r = subprocess.run(["dnf", "-q", "check-update"], capture_output=True, text=True, timeout=180)
            return [l.split()[0] for l in r.stdout.splitlines() if l.strip() and not l.startswith(" ")]
        if d == "suse":
            r = subprocess.run(["zypper", "-q", "lu"], capture_output=True, text=True, timeout=180)
            return [l.split("|")[2].strip() for l in r.stdout.splitlines() if l.count("|") >= 4
                    and l.split("|")[0].strip() == "v"]
        if d == "void":
            r = subprocess.run(["xbps-install", "-Mun"], capture_output=True, text=True, timeout=180)
            return [l.split()[0] for l in r.stdout.splitlines() if l.strip()]
        if d == "alpine":
            r = subprocess.run(["apk", "version", "-l", "<"], capture_output=True, text=True, timeout=120)
            return [l.split()[0] for l in r.stdout.splitlines()[1:] if l.strip()]
    except Exception:
        pass
    return None


def arch_news(days=60):
    """Nouvelles d'archlinux.org (à lire avant une mise à jour : interventions manuelles)."""
    import html as _h
    req = urllib.request.Request("https://archlinux.org/feeds/news/", headers={"User-Agent": "Viki"})
    try:
        import ia_api
        ctx = ia_api._ssl_ctx()
    except Exception:
        ctx = None
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        x = r.read().decode("utf-8", "ignore")
    out = []
    for item in re.findall(r"(?s)<item>(.*?)</item>", x):
        t = re.search(r"(?s)<title>(.*?)</title>", item)
        l = re.search(r"(?s)<link>(.*?)</link>", item)
        d = re.search(r"(?s)<pubDate>(.*?)</pubDate>", item)
        try:
            dt = datetime.datetime.strptime(d.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S")
        except Exception:
            dt = None
        if dt and (datetime.datetime.now() - dt).days > days:
            continue
        out.append({"titre": _h.unescape(t.group(1).strip()) if t else "", "lien": l.group(1).strip() if l else "",
                    "date": dt.strftime("%d/%m/%Y") if dt else ""})
    return out


def update_command():
    try:
        import paquets
        cmd = paquets.cmd_mise_a_jour()
    except Exception:
        d = distro()
        cmd = {"arch": "sudo pacman -Syu", "debian": "sudo apt update && sudo apt upgrade",
               "fedora": "sudo dnf upgrade"}.get(d)
    if not cmd:
        return None
    return cmd + '; echo; read -p "Mise à jour terminée. Entrée pour fermer…"'


def terminal(cmd):
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"):
        env.pop(k, None)
    if os.environ.get("COMPAGNON_ORIG_LD"):
        env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
    try:
        import paquets
        flat, which = paquets.dans_flatpak(), paquets.which
    except Exception:
        flat, which = False, shutil.which
    # le terminal du bureau d'abord (KDE, GNOME récent, GNOME, Xfce, Cinnamon, MATE, LXQt…), puis les autres
    bur = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    liste = [["konsole", "-e"], ["ptyxis", "--"], ["kgx", "--"], ["gnome-terminal", "--"], ["xfce4-terminal", "-x"],
             ["mate-terminal", "-x"], ["qterminal", "-e"], ["lxterminal", "-e"], ["cosmic-term", "-e"],
             ["tilix", "-e"], ["terminator", "-x"], ["kitty"], ["alacritty", "-e"], ["wezterm", "start", "--"],
             ["foot"], ["x-terminal-emulator", "-e"], ["xterm", "-e"]]
    pref = {"KDE": "konsole", "GNOME": "ptyxis", "XFCE": "xfce4-terminal", "MATE": "mate-terminal",
            "LXQT": "qterminal", "COSMIC": "cosmic-term", "X-CINNAMON": "gnome-terminal"}
    for k, nom in pref.items():
        if k in bur:
            liste.sort(key=lambda t: t[0] != nom)
            break
    for t in liste:
        if which(t[0]):
            argv = t + ["bash", "-c", cmd]
            if flat:                                       # depuis un Flatpak : sur le vrai système
                argv = ["flatpak-spawn", "--host"] + argv
            subprocess.Popen(argv, env=env, start_new_session=True)
            return True
    return False


# ------------------------------------------------------------------ santé des disques (UDisks, sans root)
def disks_health():
    """-> liste de {nom, ok, details} ; None si UDisks n'est pas joignable."""
    exe = shutil.which("busctl")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--system", "--json=short", "call", "org.freedesktop.UDisks2",
                            "/org/freedesktop/UDisks2", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"],
                           capture_output=True, text=True, timeout=15)
        objs = json.loads(r.stdout)["data"][0]
    except Exception:
        return None

    def val(d, k, default=None):
        v = d.get(k)
        return v.get("data", default) if isinstance(v, dict) else default
    out = []
    for path, ifaces in objs.items():
        drv = ifaces.get("org.freedesktop.UDisks2.Drive")
        if not drv or val(drv, "Removable") and not val(drv, "Size"):
            continue
        name = (val(drv, "Vendor", "") + " " + val(drv, "Model", "")).strip() or Path(path).name
        size = val(drv, "Size", 0)
        ata = ifaces.get("org.freedesktop.UDisks2.Drive.Ata")
        nvme = ifaces.get("org.freedesktop.UDisks2.NVMe.Controller")
        d = {"nom": name, "taille": size, "ok": True, "details": [], "support": False}
        if ata and val(ata, "SmartSupported"):
            d["support"] = True
            if val(ata, "SmartFailing"):
                d["ok"] = False
                d["details"].append("le disque annonce une panne prochaine (SMART)")
            bad = val(ata, "SmartNumBadSectors", 0) or 0
            if bad > 0:
                d["ok"] = False
                d["details"].append(f"{bad} secteur{'s' if bad > 1 else ''} abîmé{'s' if bad > 1 else ''}")
            if (val(ata, "SmartNumAttributesFailing", 0) or 0) > 0:
                d["ok"] = False
                d["details"].append("des indicateurs SMART sont dans le rouge")
            k = val(ata, "SmartTemperature", 0) or 0
            if k:
                d["details"].append(f"{k - 273.15:.0f} °C")
            h = (val(ata, "SmartPowerOnSeconds", 0) or 0) / 3600
            if h:
                d["details"].append(f"{h:,.0f} h de fonctionnement".replace(",", " "))
        elif nvme:
            d["support"] = True
            warn = val(nvme, "SmartCriticalWarning", []) or []
            if warn:
                d["ok"] = False
                d["details"].append("alerte critique : " + ", ".join(warn))
            k = val(nvme, "SmartTemperature", 0) or 0
            if k:
                d["details"].append(f"{k - 273.15:.0f} °C")
            h = val(nvme, "SmartPowerOnHours", 0) or 0
            if h:
                d["details"].append(f"{h:,.0f} h de fonctionnement".replace(",", " "))
        out.append(d)
    return out


# ------------------------------------------------------------------ ménage intelligent
VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".ts"}


def _dirs(*names):
    return [HOME / n for n in names if (HOME / n).is_dir()]


def scan_smart_clean(stop=None):
    """-> {catégorie: [(chemin, taille, raison)]}"""
    now = time.time()
    res = {"Grosses vidéos jamais regardées": [], "Vieux téléchargements (plus de 6 mois)": [],
           "Photos en double": []}
    for d in _dirs("Vidéos", "Videos", "Téléchargements", "Downloads", "Bureau", "Desktop"):
        for f in d.rglob("*"):
            if stop and stop():
                return res
            try:
                if f.suffix.lower() in VIDEO and f.is_file():
                    st = f.stat()
                    if st.st_size > 500 * 2 ** 20 and now - st.st_mtime > 90 * 86400 and st.st_atime - st.st_mtime < 120:
                        res["Grosses vidéos jamais regardées"].append(
                            (str(f), st.st_size, f"jamais ouverte depuis {int((now - st.st_mtime) / 86400)} jours"))
            except Exception:
                pass
    for d in _dirs("Téléchargements", "Downloads"):
        for f in d.iterdir():
            try:
                st = f.stat()
                if f.is_file() and now - max(st.st_mtime, st.st_atime) > 180 * 86400:
                    res["Vieux téléchargements (plus de 6 mois)"].append(
                        (str(f), st.st_size, f"pas ouvert depuis {int((now - max(st.st_mtime, st.st_atime)) / 86400)} jours"))
            except Exception:
                pass
    try:
        import outils
        for d in _dirs("Images", "Pictures", "Photos"):
            for group in outils.find_duplicates(d) or []:
                files = [Path(x) for x in group]
                files.sort(key=lambda p: (len(str(p)), str(p)))        # on garde le plus « court » (l'original)
                for f in files[1:]:
                    res["Photos en double"].append((str(f), f.stat().st_size, f"copie de {files[0].name}"))
    except Exception:
        pass
    for k in res:
        res[k].sort(key=lambda x: -x[1])
    return res


def trash(path):
    """Corbeille (réversible) : gio, sinon la corbeille freedesktop du dossier perso."""
    p = Path(path)
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", str(p)], capture_output=True)
        if r.returncode == 0:
            return True
    for kio in ("kioclient6", "kioclient5", "kioclient"):
        if shutil.which(kio):
            r = subprocess.run([kio, "move", str(p), "trash:/"], capture_output=True)
            if r.returncode == 0:
                return True
    try:
        tr = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share")) / "Trash"
        (tr / "files").mkdir(parents=True, exist_ok=True)
        (tr / "info").mkdir(parents=True, exist_ok=True)
        name = p.name
        i = 1
        while (tr / "files" / name).exists():
            name = f"{p.stem}.{i}{p.suffix}"
            i += 1
        from urllib.parse import quote
        (tr / "info" / (name + ".trashinfo")).write_text(
            f"[Trash Info]\nPath={quote(str(p.resolve()))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        shutil.move(str(p), str(tr / "files" / name))
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ batteries des appareils (UPower)
KINDS = {"headset": "casque", "headphones": "casque", "mouse": "souris", "keyboard": "clavier",
         "gaming_input": "manette", "phone": "téléphone", "tablet": "tablette", "battery_hidpp": "souris/clavier",
         "pen": "stylet", "touchpad": "pavé tactile", "speakers": "enceinte"}


def peripherals():
    exe = shutil.which("upower")
    if not exe:
        return []
    try:
        paths = subprocess.run([exe, "-e"], capture_output=True, text=True, timeout=8).stdout.split()
    except Exception:
        return []
    out = []
    for p in paths:
        base = p.rsplit("/", 1)[-1]
        kind = next((v for k, v in KINDS.items() if base.startswith(k)), None)
        if not kind:
            continue
        try:
            info = subprocess.run([exe, "-i", p], capture_output=True, text=True, timeout=8).stdout
        except Exception:
            continue
        pct = re.search(r"percentage:\s+([\d.]+)%", info)
        model = re.search(r"model:\s+(.+)", info)
        if not pct:
            continue
        out.append({"id": base, "type": kind, "nom": (model.group(1).strip() if model else kind),
                    "pct": float(pct.group(1))})
    return out


# ------------------------------------------------------------------ modes jeu / nuit
def power_profile(set_to=None):
    exe = shutil.which("powerprofilesctl")
    if not exe:
        return None
    try:
        if set_to:
            subprocess.run([exe, "set", set_to], capture_output=True, timeout=8)
        return subprocess.run([exe, "get"], capture_output=True, text=True, timeout=8).stdout.strip() or None
    except Exception:
        return None


# ================================================================== fenêtres
STYLE = ("QWidget { background: #fffafc; color: #3d2733; font-size: 13px; }"
         "QPushButton { background: #fff; border: 1px solid #e7cfdb; border-radius: 9px; padding: 6px 12px; }"
         "QPushButton:hover { background: #fde7ef; }"
         "QPushButton#principal { background: #d6457f; color: white; border: none; font-weight: bold; }"
         "QTreeWidget, QListWidget, QTextBrowser { background: #fff; border: 1px solid #f1dfe8; border-radius: 10px; }"
         "QProgressBar { border: 1px solid #f1dfe8; border-radius: 6px; background: #fff; text-align: center; }"
         "QProgressBar::chunk { background: #e889b0; border-radius: 6px; }")


def _qt():
    from PyQt6 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets


def make_dashboard(comp):
    QtCore, QtGui, QtWidgets = _qt()
    Qt = QtCore.Qt

    class Spark(QtWidgets.QWidget):
        def __init__(self, title, key, unit="%", vmax=100):
            super().__init__()
            self.title, self.key, self.unit, self.vmax = title, key, unit, vmax
            self.now = None
            self.hist = []
            self.setMinimumSize(260, 120)

        def paintEvent(self, e):
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            r = self.rect().adjusted(1, 1, -1, -1)
            p.setPen(QtGui.QPen(QtGui.QColor("#f1dfe8")))
            p.setBrush(QtGui.QColor("#ffffff"))
            p.drawRoundedRect(QtCore.QRectF(r), 12, 12)
            p.setPen(QtGui.QColor("#8d7482"))
            f = p.font()
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.drawText(r.adjusted(14, 10, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.title)
            p.setPen(QtGui.QColor("#3d2733"))
            f.setPointSizeF(18)
            f.setBold(True)
            p.setFont(f)
            txt = "—" if self.now is None else f"{self.now:.0f} {self.unit}"
            p.drawText(r.adjusted(14, 28, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, txt)
            pts = [(x["t"], x.get(self.key)) for x in self.hist if x.get(self.key) is not None]
            if len(pts) >= 2:
                gr = QtCore.QRectF(r.left() + 12, r.top() + 64, r.width() - 24, r.height() - 76)
                t0, t1 = time.time() - 86400, time.time()
                path = QtGui.QPainterPath()
                for i, (t, v) in enumerate(pts):
                    x = gr.left() + (t - t0) / (t1 - t0) * gr.width()
                    y = gr.bottom() - min(1.0, v / self.vmax) * gr.height()
                    path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
                p.setPen(QtGui.QPen(QtGui.QColor("#d6457f"), 1.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                p.setPen(QtGui.QColor("#b7a3ae"))
                f.setPointSizeF(8)
                f.setBold(False)
                p.setFont(f)
                p.drawText(QtCore.QRectF(gr.left(), gr.bottom() - 2, gr.width(), 14),
                           Qt.AlignmentFlag.AlignLeft, "il y a 24 h")
                p.drawText(QtCore.QRectF(gr.left(), gr.bottom() - 2, gr.width(), 14),
                           Qt.AlignmentFlag.AlignRight, "maintenant")
            p.end()

    class Dash(QtWidgets.QWidget):
        sig = QtCore.pyqtSignal(object)

        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("🖥️ Tableau de bord du PC — " + comp.char.get("name", "Viki"))
            self.setStyleSheet(STYLE)
            self.resize(880, 600)
            lay = QtWidgets.QVBoxLayout(self)
            grid = QtWidgets.QGridLayout()
            self.cards = [Spark("Processeur", "cpu"), Spark("Mémoire", "ram"), Spark("Carte graphique", "gpu"),
                          Spark("Température processeur", "tcpu", "°C", 100),
                          Spark("Température carte graphique", "tgpu", "°C", 110)]
            for i, c in enumerate(self.cards):
                grid.addWidget(c, i // 3, i % 3)
            self.disk_box = QtWidgets.QLabel()
            self.disk_box.setWordWrap(True)
            self.disk_box.setStyleSheet("background: #fff; border: 1px solid #f1dfe8; border-radius: 12px; padding: 12px;")
            grid.addWidget(self.disk_box, 1, 2)
            lay.addLayout(grid, 1)
            self.info = QtWidgets.QLabel("")
            self.info.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)
            self.info.setWordWrap(True)
            self.info.setStyleSheet("color: #5c4652; background: #fdf0f5; border-radius: 10px; padding: 10px;")
            lay.addWidget(self.info)
            row = QtWidgets.QHBoxLayout()
            b = QtWidgets.QPushButton("🐢 Pourquoi mon PC rame ?")
            b.setObjectName("principal")
            b.clicked.connect(comp.why_slow)
            row.addWidget(b)
            for lab, fn in (("💽 Santé des disques", comp.disks_health), ("🧹 Ménage intelligent", comp.smart_clean),
                            ("⬆️ Mises à jour", comp.open_updates), ("💾 Sauvegarde", comp.open_backup)):
                bb = QtWidgets.QPushButton(lab)
                bb.clicked.connect(fn)
                row.addWidget(bb)
            row.addStretch(1)
            lay.addLayout(row)
            self.sig.connect(self._show)
            self.t = QtCore.QTimer(self)
            self.t.timeout.connect(self.refresh)
            self.t.start(2500)
            self.refresh()

        def refresh(self):
            if not self.isVisible() and hasattr(self, "_once"):
                return
            self._once = True
            import threading
            threading.Thread(target=lambda: self.sig.emit((sample(), disks(), mem(), gpu(), history())),
                             daemon=True).start()

        def _show(self, data):
            s, dk, m, g, h = data
            for c in self.cards:
                c.now = s.get(c.key)
                c.hist = h + [s]
                c.update()
            self.cards[1].title = f"Mémoire ({human(m['utilise'])} / {human(m['total'])})"
            if g and g.get("vram_total"):
                self.cards[2].title = f"Carte graphique (mémoire {human(g['vram'])} / {human(g['vram_total'])})"
            self.disk_box.setText("<b>Disques</b><br>" + "<br>".join(
                f"{d['nom']} : {human(d['libre'])} libres sur {human(d['total'])} ({d['pct']:.0f} % pris)" for d in dk)
                + (f"<br><br>Swap utilisé : {human(m['swap'])}" if m["swap_total"] else ""))
            try:
                up = float(open("/proc/uptime").read().split()[0])
                self.info.setText(f"Allumé depuis {int(up // 3600)} h {int(up % 3600 // 60):02d}. "
                                  "Les courbes montrent les dernières 24 h (une mesure toutes les 5 minutes, "
                                  "seulement quand Viki est lancée).")
            except Exception:
                pass

    return Dash()


def make_procs_window(comp, txt, by_cpu, by_ram):
    QtCore, QtGui, QtWidgets = _qt()
    Qt = QtCore.Qt
    w = QtWidgets.QWidget(None, Qt.WindowType.Window)
    w.setWindowTitle("🐢 Ce qui consomme — " + comp.char.get("name", "Viki"))
    w.setStyleSheet(STYLE)
    w.resize(640, 520)
    lay = QtWidgets.QVBoxLayout(w)
    lab = QtWidgets.QLabel(txt)
    lab.setWordWrap(True)
    lab.setStyleSheet("background: #fdf0f5; border-radius: 10px; padding: 10px;")
    lay.addWidget(lab)
    tree = QtWidgets.QTreeWidget()
    tree.setHeaderLabels(["Programme", "Processeur", "Mémoire", ""])
    tree.setRootIsDecorated(False)
    seen = {}
    for g in by_cpu + by_ram:
        if g["nom"] in seen or (g["cpu"] < 0.5 and g["ram"] < 150 * 2 ** 20):
            continue
        seen[g["nom"]] = g
        it = QtWidgets.QTreeWidgetItem([g["nom"], f"{g['cpu']:.1f} %", human(g["ram"]), ""])
        tree.addTopLevelItem(it)
        if g["a_moi"]:
            b = QtWidgets.QPushButton("Fermer")
            b.setToolTip("Demande au programme de se fermer (comme cliquer sur la croix)")

            def close(_=False, gg=g, item=it, btn=b):
                if QtWidgets.QMessageBox.question(w, "Fermer", f"Fermer « {gg['nom']} » ? Ce qui n'est pas "
                                                  "enregistré dedans peut être perdu.") \
                        != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                n = close_group(gg)
                btn.setEnabled(False)
                item.setText(3, f"fermé ({n})")
                comp.say(f"J'ai demandé à {gg['nom']} de se fermer.")
            b.clicked.connect(close)
            tree.setItemWidget(it, 3, b)
        else:
            it.setText(3, "système")
    for i in range(3):
        tree.resizeColumnToContents(i)
    tree.setColumnWidth(0, 260)
    lay.addWidget(tree, 1)
    note = QtWidgets.QLabel("« Fermer » ne s'applique qu'à tes propres programmes ; ceux du système sont protégés.")
    note.setStyleSheet("color: #8d7482; font-size: 12px;")
    lay.addWidget(note)
    return w


def make_backup_dialog(comp):
    QtCore, QtGui, QtWidgets = _qt()
    Qt = QtCore.Qt

    class Dlg(QtWidgets.QWidget):
        prog = QtCore.pyqtSignal(float, str)
        fin = QtCore.pyqtSignal(object)

        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("💾 Sauvegarde — " + comp.char.get("name", "Viki"))
            self.setStyleSheet(STYLE)
            self.resize(620, 480)
            self.cfg = comp.cfg.setdefault("sauvegarde", {})
            if not self.cfg.get("sources"):
                self.cfg["sources"] = [str(d) for d in _dirs("Documents", "Images", "Pictures", "Bureau", "Desktop")]
            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(QtWidgets.QLabel("<b>Dossiers à sauvegarder</b>"))
            self.lst = QtWidgets.QListWidget()
            self.lst.addItems(self.cfg["sources"])
            lay.addWidget(self.lst, 1)
            r = QtWidgets.QHBoxLayout()
            for lab, fn in (("➕ Ajouter un dossier…", self.add), ("Retirer", self.rm)):
                b = QtWidgets.QPushButton(lab)
                b.clicked.connect(fn)
                r.addWidget(b)
            r.addStretch(1)
            lay.addLayout(r)
            lay.addWidget(QtWidgets.QLabel("<b>Vers</b>"))
            self.dest = QtWidgets.QComboBox()
            for d in external_drives():
                self.dest.addItem(f"💽 {d['nom']} ({human(d['libre'])} libres)", d["chemin"])
            if self.cfg.get("dest") and self.dest.findData(self.cfg["dest"]) < 0:
                self.dest.addItem(f"📁 {self.cfg['dest']}", self.cfg["dest"])
            self.dest.addItem("Choisir un autre dossier…", "")
            i = self.dest.findData(self.cfg.get("dest", ""))
            self.dest.setCurrentIndex(max(0, i))
            self.dest.activated.connect(self.pick)
            lay.addWidget(self.dest)
            self.rem = QtWidgets.QComboBox()
            for lab, v in (("Me le rappeler chaque semaine", 7), ("Toutes les 2 semaines", 14),
                           ("Chaque mois", 30), ("Ne pas me le rappeler", 0)):
                self.rem.addItem(lab, v)
            self.rem.setCurrentIndex(max(0, self.rem.findData(int(self.cfg.get("jours", 7)))))
            lay.addWidget(self.rem)
            last = self.cfg.get("derniere")
            self.state = QtWidgets.QLabel("Dernière sauvegarde : " + (
                datetime.datetime.fromtimestamp(last).strftime("%d/%m/%Y à %Hh%M") if last else "jamais"))
            lay.addWidget(self.state)
            self.bar = QtWidgets.QProgressBar()
            self.bar.setRange(0, 1000)
            self.bar.hide()
            lay.addWidget(self.bar)
            note = QtWidgets.QLabel("Elle copie dans « Sauvegarde Viki » sur la destination, sans jamais rien "
                                    "effacer ; les fois suivantes, seuls les fichiers nouveaux ou modifiés sont copiés.")
            note.setWordWrap(True)
            note.setStyleSheet("color: #8d7482; font-size: 12px;")
            lay.addWidget(note)
            self.go = QtWidgets.QPushButton("💾 Sauvegarder maintenant")
            self.go.setObjectName("principal")
            self.go.clicked.connect(self.run)
            lay.addWidget(self.go)
            self.prog.connect(lambda f, n: (self.bar.setValue(int(f * 1000)), self.bar.setFormat(f"{n} — {f:.0%}")))
            self.fin.connect(self.done)
            self.stopping = False

        def store(self):
            self.cfg["sources"] = [self.lst.item(i).text() for i in range(self.lst.count())]
            self.cfg["dest"] = self.dest.currentData() or ""
            self.cfg["jours"] = self.rem.currentData()
            comp.save_cfg()

        def add(self):
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier à sauvegarder", str(HOME))
            if d:
                self.lst.addItem(d)
                self.store()

        def rm(self):
            for it in self.lst.selectedItems():
                self.lst.takeItem(self.lst.row(it))
            self.store()

        def pick(self, i):
            if self.dest.itemData(i):
                return self.store()
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Où sauvegarder ?", "/run/media")
            if d:
                self.dest.insertItem(0, f"📁 {d}", d)
                self.dest.setCurrentIndex(0)
            self.store()

        def run(self):
            self.store()
            if not self.cfg["dest"]:
                return comp.say("Branche un disque externe ou choisis un dossier de destination.")
            if not self.cfg["sources"]:
                return comp.say("Ajoute au moins un dossier à sauvegarder.")
            if str(Path(self.cfg["dest"]).resolve()).startswith(str(HOME.resolve()) + "/") is False and \
                    not os.path.ismount(self.cfg["dest"]) and not Path(self.cfg["dest"]).is_dir():
                return comp.say("Je ne trouve pas la destination : le disque est bien branché ?")
            self.go.setEnabled(False)
            self.bar.show()
            comp.say("C'est parti pour la sauvegarde ! Tu peux continuer à utiliser le PC.")
            import threading
            src, dst = list(self.cfg["sources"]), self.cfg["dest"]
            threading.Thread(target=lambda: self.fin.emit(backup(src, dst, self.prog.emit, lambda: self.stopping)),
                             daemon=True).start()

        def done(self, errors):
            self.go.setEnabled(True)
            self.cfg["derniere"] = time.time()
            comp.save_cfg()
            self.state.setText("Dernière sauvegarde : à l'instant" + (f" ({len(errors)} souci(s))" if errors else ""))
            if errors:
                comp.say(f"Sauvegarde terminée, mais avec {len(errors)} souci(s) : {errors[0][:100]}")
            else:
                comp.say("Sauvegarde terminée ! Tes fichiers sont à l'abri.")
            comp._notify("Sauvegarde terminée", "Tes dossiers sont copiés sur " + Path(self.cfg["dest"]).name)

        def closeEvent(self, e):
            self.store()
            super().closeEvent(e)

    return Dlg()


def make_updates_window(comp):
    QtCore, QtGui, QtWidgets = _qt()
    Qt = QtCore.Qt

    class W(QtWidgets.QWidget):
        got = QtCore.pyqtSignal(object)

        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("⬆️ Mises à jour — " + comp.char.get("name", "Viki"))
            self.setStyleSheet(STYLE)
            self.resize(700, 560)
            lay = QtWidgets.QVBoxLayout(self)
            self.news = QtWidgets.QTextBrowser()
            self.news.setOpenExternalLinks(True)
            self.news.setMaximumHeight(200)
            lay.addWidget(QtWidgets.QLabel("<b>📰 Nouvelles d'Arch Linux</b> (à lire avant de mettre à jour : "
                                           "parfois une action manuelle est nécessaire)"))
            lay.addWidget(self.news)
            self.title = QtWidgets.QLabel("<b>Paquets à mettre à jour</b> — je regarde…")
            lay.addWidget(self.title)
            self.pk = QtWidgets.QListWidget()
            lay.addWidget(self.pk, 1)
            row = QtWidgets.QHBoxLayout()
            self.go = QtWidgets.QPushButton("⬆️ Mettre à jour (dans un terminal)")
            self.go.setObjectName("principal")
            self.go.clicked.connect(self.run)
            row.addWidget(self.go)
            rb = QtWidgets.QPushButton("🔄 Actualiser")
            rb.clicked.connect(self.load)
            row.addWidget(rb)
            row.addStretch(1)
            lay.addLayout(row)
            self.got.connect(self.show_data)
            self.load()

        def load(self):
            import threading
            self.title.setText("<b>Paquets à mettre à jour</b> — je regarde… (internet)")

            def work():
                news = None
                if distro() == "arch":
                    try:
                        news = arch_news()
                    except Exception as e:
                        news = e
                return pending_updates(), news
            threading.Thread(target=lambda: self.got.emit(work()), daemon=True).start()

        def show_data(self, data):
            pk, news = data
            if distro() != "arch":
                self.news.setHtml("<i>(seulement pour Arch Linux)</i>")
            elif isinstance(news, Exception):
                self.news.setHtml(f"<i>Je n'ai pas pu lire les nouvelles : {news}</i>")
            elif not news:
                self.news.setHtml("<i>Aucune nouvelle ces deux derniers mois : rien de spécial à faire.</i>")
            else:
                last = comp.cfg.get("maj_derniere", 0)
                items = []
                for n in news:
                    try:
                        recent = datetime.datetime.strptime(n["date"], "%d/%m/%Y").timestamp() > last
                    except Exception:
                        recent = False
                    items.append(f"<p>{'🆕 ' if recent else ''}<b>{n['date']}</b> — "
                                 f"<a href='{n['lien']}'>{n['titre']}</a></p>")
                self.news.setHtml("".join(items))
            self.pk.clear()
            if pk is None:
                self.title.setText("<b>Paquets à mettre à jour</b> — je n'arrive pas à vérifier "
                                   "(installe « pacman-contrib » pour checkupdates).")
            else:
                self.title.setText(f"<b>{len(pk)} paquet{'s' if len(pk) > 1 else ''} à mettre à jour</b>")
                self.pk.addItems(pk[:500])
            self.go.setEnabled(bool(pk) or pk is None)

        def run(self):
            cmd = update_command()
            if not cmd:
                return comp.say("Je ne sais pas mettre à jour cette distribution.")
            if terminal(cmd):
                comp.cfg["maj_derniere"] = time.time()
                comp.save_cfg()
                comp.say("La mise à jour se fait dans le terminal : il va te demander ton mot de passe.")
            else:
                comp.say("Je ne trouve pas de terminal. Lance : " + cmd.split(";")[0])

    return W()


def make_smart_clean(comp):
    QtCore, QtGui, QtWidgets = _qt()
    Qt = QtCore.Qt

    class W(QtWidgets.QWidget):
        got = QtCore.pyqtSignal(object)

        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("🧹 Ménage intelligent — " + comp.char.get("name", "Viki"))
            self.setStyleSheet(STYLE)
            self.resize(760, 560)
            lay = QtWidgets.QVBoxLayout(self)
            self.head = QtWidgets.QLabel("Je cherche… (vidéos jamais regardées, vieux téléchargements, photos en double)")
            self.head.setWordWrap(True)
            self.head.setStyleSheet("background: #fdf0f5; border-radius: 10px; padding: 10px;")
            lay.addWidget(self.head)
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setHeaderLabels(["Fichier", "Taille", "Pourquoi"])
            self.tree.itemDoubleClicked.connect(self.open_item)
            self.tree.itemChanged.connect(self.recount)
            lay.addWidget(self.tree, 1)
            row = QtWidgets.QHBoxLayout()
            self.go = QtWidgets.QPushButton("🗑️ Mettre à la corbeille")
            self.go.setObjectName("principal")
            self.go.clicked.connect(self.run)
            self.go.setEnabled(False)
            row.addWidget(self.go)
            self.sum = QtWidgets.QLabel("")
            row.addWidget(self.sum)
            row.addStretch(1)
            lay.addLayout(row)
            note = QtWidgets.QLabel("Rien n'est coché d'office. Double-clic : ouvrir le fichier. Tout part à la "
                                    "corbeille : tu peux le récupérer.")
            note.setStyleSheet("color: #8d7482; font-size: 12px;")
            lay.addWidget(note)
            self.got.connect(self.fill)
            import threading
            threading.Thread(target=lambda: self.got.emit(scan_smart_clean(lambda: not self.isVisible())),
                             daemon=True).start()

        def fill(self, res):
            self.tree.blockSignals(True)
            total = 0
            for cat, items in res.items():
                if not items:
                    continue
                size = sum(s for _, s, _ in items)
                total += size
                top = QtWidgets.QTreeWidgetItem([f"{cat} ({len(items)})", human(size), ""])
                top.setFlags(top.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
                top.setCheckState(0, Qt.CheckState.Unchecked)
                for path, s, why in items[:400]:
                    it = QtWidgets.QTreeWidgetItem([path.replace(str(HOME), "~"), human(s), why])
                    it.setData(0, Qt.ItemDataRole.UserRole, (path, s))
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.CheckState.Unchecked)
                    top.addChild(it)
                self.tree.addTopLevelItem(top)
            self.tree.blockSignals(False)
            self.tree.setColumnWidth(0, 420)
            if total:
                self.head.setText(f"J'ai trouvé {human(total)} qui pourraient partir. Coche ce que tu veux jeter.")
            else:
                self.head.setText("Rien à jeter : ton PC est bien rangé ! ✨")

        def checked(self):
            out = []
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for j in range(top.childCount()):
                    it = top.child(j)
                    if it.checkState(0) == Qt.CheckState.Checked:
                        out.append((it, *it.data(0, Qt.ItemDataRole.UserRole)))
            return out

        def recount(self, *_):
            c = self.checked()
            self.sum.setText(f"{len(c)} fichier(s), {human(sum(s for _, _, s in c))}" if c else "")
            self.go.setEnabled(bool(c))

        def open_item(self, it, _col):
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if d:
                subprocess.Popen(["xdg-open", d[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def run(self):
            c = self.checked()
            if QtWidgets.QMessageBox.question(self, "Corbeille", f"Mettre {len(c)} fichier(s) à la corbeille "
                                              f"({human(sum(s for _, _, s in c))}) ?") \
                    != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            ok = freed = 0
            for it, path, s in c:
                if trash(path):
                    ok += 1
                    freed += s
                    it.parent().removeChild(it)
            self.recount()
            comp.say(f"C'est fait : {ok} fichier{'s' if ok > 1 else ''} à la corbeille, {human(freed)} de gagnés. "
                     "Vide la corbeille quand tu es sûr.")

    return W()
