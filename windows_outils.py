"""🪟 Les équivalents Windows des outils Linux que Viki utilise (ss, systemctl, resolvectl, flatpak, /proc…).
Tout passe par PowerShell, netstat, winget et le registre : rien à installer. Utilisé seulement sous Windows."""
import base64
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WIN = sys.platform.startswith("win")
CREATE_NO_WINDOW, CREATE_NEW_CONSOLE = 0x08000000, 0x00000010


# ------------------------------------------------------------------ lancer des commandes
def run(cmd, timeout=20):
    """-> (code, texte) ; texte lu en UTF-8, sans jamais planter sur un accent."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or b"") + (r.stderr or b"" if r.returncode else b"")
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                return r.returncode, out.decode(enc)
            except UnicodeDecodeError:
                continue
        return r.returncode, out.decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)


def ps(script, timeout=25):
    """Un script PowerShell (sortie en UTF-8)."""
    pre = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", pre + script],
               timeout)


def ps_json(script, timeout=25):
    code, out = ps(script + " | ConvertTo-Json -Compress -Depth 4", timeout)
    try:
        v = json.loads(out.strip() or "null")
    except Exception:
        return None
    return v if isinstance(v, list) else ([] if v is None else [v])


def _enc(script):
    return base64.b64encode(script.encode("utf-16-le")).decode()


def terminal(lignes, titre="Viki", admin=False):
    """Une fenêtre PowerShell visible qui montre et lance chaque commande (admin : Windows demande la permission).
    -> True si la fenêtre s'est ouverte."""
    corps = [f"Write-Host '── {titre.replace(chr(39), '')} ──' -ForegroundColor Magenta", "Write-Host ''"]
    for l in lignes:
        corps.append(f"Write-Host ('> ' + {json.dumps(l)}) -ForegroundColor DarkGray")
        corps.append(l)
    corps += ["Write-Host ''", "Read-Host 'Entrée pour fermer'"]
    script = "; ".join(corps)
    try:
        if admin:
            lance = (f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
                     f"'-EncodedCommand','{_enc(script)}'")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", lance], creationflags=CREATE_NO_WINDOW)
        else:
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", _enc(script)],
                             creationflags=CREATE_NEW_CONSOLE)
        return True
    except Exception:
        return False


def ouvrir(cible):
    try:
        os.startfile(cible)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ réseau
def ports():
    """Comme « ss -tulnp » : -> [{proto, addr, port, prog, pid}]."""
    code, out = run(["netstat", "-ano"], 15)
    noms = programmes()
    res = []
    for l in out.splitlines():
        c = l.split()
        if len(c) < 4 or c[0] not in ("TCP", "UDP"):
            continue
        if c[0] == "TCP" and (len(c) < 5 or c[2] not in ("0.0.0.0:0", "[::]:0", "*:*")):
            continue                                          # une connexion établie, pas une écoute
        m = re.match(r"^\[?(.*?)\]?:(\d+)$", c[1])
        if not m:
            continue
        pid = int(c[-1]) if c[-1].isdigit() else 0
        res.append({"proto": c[0].lower(), "addr": m.group(1), "port": int(m.group(2)), "pid": pid,
                    "prog": noms.get(pid, "")})
    return res


def programmes():
    """{pid: nom} (tasklist)."""
    code, out = run(["tasklist", "/fo", "csv", "/nh"], 15)
    res = {}
    for l in out.splitlines():
        c = [x.strip('"') for x in l.split('","')]
        if len(c) >= 2 and c[1].strip('"').isdigit():
            res[int(c[1].strip('"'))] = re.sub(r"\.exe$", "", c[0].strip('"'), flags=re.I)
    return res


def arreter(pid, force=False):
    code, out = run(["taskkill", "/PID", str(pid)] + (["/F"] if force else []), 10)
    return code == 0, out.strip()


def passerelle():
    v = ps_json("Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric"
                " | Select-Object -First 1 NextHop")
    return (v[0].get("NextHop") or "") if v else ""


def pare_feu():
    """-> (tout actif ?, profils coupés)"""
    v = ps_json("Get-NetFirewallProfile | Select-Object Name,Enabled")
    if not v:
        return None, []
    coupes = [p.get("Name", "?") for p in v if not p.get("Enabled")]
    return not coupes, coupes


def antivirus():
    """-> {actif, temps_reel, age} ou None"""
    v = ps_json("Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureAge")
    if not v:
        return None
    a = v[0]
    return {"actif": bool(a.get("AntivirusEnabled")), "temps_reel": bool(a.get("RealTimeProtectionEnabled")),
            "age": a.get("AntivirusSignatureAge")}


def upnp():
    """Redirections UPnP de la box (par Windows lui-même) -> (ip, [{proto, ext, int_ip, int_port, desc}]) ou None."""
    v = ps_json("$u = New-Object -ComObject HNetCfg.NATUPnP; $c = $u.StaticPortMappingCollection; "
                "if ($c) { $c | ForEach-Object { [pscustomobject]@{proto=$_.Protocol; ext=$_.ExternalPort; "
                "ip=$_.ExternalIPAddress; int_ip=$_.InternalClient; int_port=$_.InternalPort; desc=$_.Description} } }",
                30)
    if v is None:
        return None
    ip = next((x.get("ip") for x in v if x.get("ip")), "")
    return ip, [{"proto": x.get("proto", ""), "ext": int(x.get("ext") or 0), "int_ip": x.get("int_ip", ""),
                 "int_port": int(x.get("int_port") or 0), "desc": x.get("desc", "")} for x in v]


def upnp_fermer(ext, proto):
    return ps(f"$u = New-Object -ComObject HNetCfg.NATUPnP; $u.StaticPortMappingCollection.Remove({int(ext)}, "
              f"'{proto}')", 20)[0] == 0


# ------------------------------------------------------------------ DNS
DOH = {"quad9": "https://dns.quad9.net/dns-query", "mullvad": "https://dns.mullvad.net/dns-query",
       "mullvad_adblock": "https://adblock.dns.mullvad.net/dns-query",
       "cloudflare": "https://cloudflare-dns.com/dns-query", "adguard": "https://dns.adguard-dns.com/dns-query"}


def dns_etat():
    v = ps_json("Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
                "Select-Object InterfaceAlias,ServerAddresses")
    serveurs = []
    for x in v or []:
        for s in x.get("ServerAddresses") or []:
            if s not in serveurs:
                serveurs.append(s)
    doh = ps_json("Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue | Select-Object ServerAddress")
    chiffres = {x.get("ServerAddress") for x in doh or []}
    ok = bool(serveurs) and all(s in chiffres for s in serveurs)
    return ("Serveurs : " + (", ".join(serveurs) or "ceux de ta box")
            + ("\nChiffré (DNS over HTTPS) : oui" if ok else "\nChiffré : non")), ok


def dns_commandes(ips, modele):
    """Commandes PowerShell (admin) : ces serveurs DNS sur les cartes réseau actives, chiffrés (Windows 11)."""
    liste = ",".join(f"'{i}'" for i in ips)
    cmds = [f"Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {{ Set-DnsClientServerAddress "
            f"-InterfaceIndex $_.ifIndex -ServerAddresses {liste} }}"]
    for i in ips:
        cmds.append(f"try {{ Add-DnsClientDohServerAddress -ServerAddress '{i}' -DohTemplate '{modele}' "
                    "-AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop } catch { "
                    "Write-Host '(DNS chiffré : seulement sous Windows 11, serveur déjà connu ou réglé)' }")
    cmds += ["Clear-DnsClientCache", "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { "
                                     "$_.ServerAddresses } | Format-Table InterfaceAlias,ServerAddresses"]
    return cmds


def dns_retour():
    return ["Get-NetAdapter | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex "
            "-ResetServerAddresses }", "Clear-DnsClientCache",
            "Get-DnsClientServerAddress -AddressFamily IPv4 | Format-Table InterfaceAlias,ServerAddresses"]


# ------------------------------------------------------------------ logiciels
_INSTALLES = {"t": 0, "noms": []}


def installes():
    """Noms des logiciels installés (registre « Programmes et fonctionnalités »), en minuscules."""
    if time.monotonic() - _INSTALLES["t"] < 60 and _INSTALLES["noms"]:
        return _INSTALLES["noms"]
    import winreg
    noms = []
    for racine, vue in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY), (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(racine, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0,
                                winreg.KEY_READ | vue) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as s:
                            noms.append(str(winreg.QueryValueEx(s, "DisplayName")[0]).lower())
                    except OSError:
                        continue
        except OSError:
            continue
    _INSTALLES.update(t=time.monotonic(), noms=noms)
    return noms


def est_installe(*mots):
    noms = installes()
    return any(any(m.lower() in n for n in noms) for m in mots)


def winget_ok():
    return run(["winget", "--version"], 10)[0] == 0


def winget_installer(ident):
    return f"winget install -e --id {ident} --accept-source-agreements --accept-package-agreements"


def mises_a_jour():
    """Logiciels à mettre à jour (winget) -> [nom] ou None."""
    code, out = run(["winget", "upgrade", "--include-unknown", "--accept-source-agreements"], 90)
    if code == -1 or not out.strip():                       # winget absent (ou n'a pas répondu)
        return None
    lignes = out.splitlines()
    try:
        i = next(k for k, l in enumerate(lignes) if set(l.strip()) == {"-"})
    except StopIteration:
        return [] if re.search(r"(?:aucun|no) (?:package|paquet|mise|installed|update)", out, re.I) else None
    res = []
    for l in lignes[i + 1:]:
        if not l.strip() or re.match(r"^\d+ (?:mise|upgrade|package|paquet)", l.strip(), re.I):
            continue
        nom = re.split(r"\s{2,}", l.strip())[0]
        if nom:
            res.append(nom)
    return res


def gpg():
    import shutil
    for p in (shutil.which("gpg"), r"C:\Program Files (x86)\GnuPG\bin\gpg.exe", r"C:\Program Files\GnuPG\bin\gpg.exe"):
        if p and os.path.exists(p):
            return p
    return ""


def defender():
    """Le programme de Defender (MpCmdRun.exe) ou ""."""
    base = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    cands = sorted(base.glob("*/MpCmdRun.exe"), reverse=True) if base.is_dir() else []
    cands.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe")
    return next((str(c) for c in cands if c.exists()), "")


def scanner(chemin):
    """Defender sur un fichier -> « rien trouvé », « virus trouvé : … » ou ""."""
    exe = defender()
    if not exe:
        return ""
    code, out = run([exe, "-Scan", "-ScanType", "3", "-File", str(chemin), "-DisableRemediation"], 240)
    if code == 0:
        return "rien trouvé"
    if code == 2:
        m = re.search(r"Threat\s*:\s*(.+)", out) or re.search(r"Menace\s*:\s*(.+)", out)
        return "virus trouvé : " + (m.group(1).strip() if m else "menace détectée")
    return ""


# ------------------------------------------------------------------ appel en cours (micro / webcam)
def en_appel():
    """Une appli se sert du micro ou de la webcam en ce moment (Windows le note dans le registre)."""
    import winreg
    for quoi in ("microphone", "webcam"):
        base = rf"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{quoi}"
        for sous in ("", "NonPackaged"):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + ("\\" + sous if sous else "")) as k:
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        nom = winreg.EnumKey(k, i)
                        if nom == "NonPackaged" or "viki" in nom.lower() or "python" in nom.lower():
                            continue
                        try:
                            with winreg.OpenKey(k, nom) as s:
                                if winreg.QueryValueEx(s, "LastUsedTimeStop")[0] == 0 and \
                                        winreg.QueryValueEx(s, "LastUsedTimeStart")[0] > 0:
                                    return True
                        except OSError:
                            continue
            except OSError:
                continue
    return False


# ------------------------------------------------------------------ fichiers récents
def fichiers_recents(heures=36, maxi=8):
    d = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
    if not d.is_dir():
        return []
    limite = time.time() - heures * 3600
    lnk = sorted((f for f in d.glob("*.lnk") if f.stat().st_mtime >= limite), key=lambda f: -f.stat().st_mtime)[:30]
    if not lnk:
        return []
    liste = ";".join(str(f).replace("'", "''") for f in lnk)
    code, out = ps("$s = New-Object -ComObject WScript.Shell; '" + liste + "'.Split(';') | ForEach-Object { "
                   "$s.CreateShortcut($_).TargetPath }", 30)
    res = []
    for l in out.splitlines():
        l = l.strip()
        if l and os.path.isfile(l) and l not in res and "\\Temp\\" not in l:
            res.append(l)
    return res[:maxi]


# ------------------------------------------------------------------ PC : mesures
class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _temps_systeme():
    i, k, u = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    v = lambda f: (f.hi << 32) | f.lo
    return v(i), v(k), v(u)


def cpu_pourcent(intervalle=0.4):
    i1, k1, u1 = _temps_systeme()
    time.sleep(intervalle)
    i2, k2, u2 = _temps_systeme()
    tot = (k2 - k1) + (u2 - u1)
    return round(100 * (1 - (i2 - i1) / max(1, tot)), 1)


def memoire():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    tot, av = m.ullTotalPhys, m.ullAvailPhys
    swap_tot = max(0, m.ullTotalPageFile - tot)
    swap = max(0, (m.ullTotalPageFile - m.ullAvailPageFile) - (tot - av))
    return {"total": tot, "utilise": tot - av, "pct": round(100 * (tot - av) / max(1, tot), 1), "swap": swap,
            "swap_total": swap_tot}


def lecteurs(types=(3,)):
    """Lettres de lecteur (3 = disque fixe, 2 = amovible) -> ["C:\\", …]"""
    k32 = ctypes.windll.kernel32
    masque = k32.GetLogicalDrives()
    res = []
    for i in range(26):
        if masque & (1 << i):
            d = f"{chr(65 + i)}:\\"
            if k32.GetDriveTypeW(d) in types:
                res.append(d)
    return res


def processus(intervalle=0.8):
    """[(nom, pid, cpu % d'un cœur, mémoire)] mesurés sur l'intervalle."""
    v = ps_json(f"$a = Get-Process | Select-Object Id,CPU; Start-Sleep -Milliseconds {int(intervalle * 1000)}; "
                "$b = Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64; "
                "$h = @{}; $a | ForEach-Object { $h[$_.Id] = $_.CPU }; $b | ForEach-Object { "
                "[pscustomobject]@{n=$_.ProcessName; p=$_.Id; c=([double]$_.CPU - [double]$h[$_.Id]); "
                "m=$_.WorkingSet64} }", 30)
    res = []
    for x in v or []:
        res.append((x.get("n") or "?", int(x.get("p") or 0), max(0.0, float(x.get("c") or 0)) / intervalle * 100,
                    int(x.get("m") or 0)))
    return res


def sante_disques():
    v = ps_json("Get-PhysicalDisk | Select-Object FriendlyName,HealthStatus,OperationalStatus,MediaType,Size")
    if v is None:
        return None
    res = []
    for d in v:
        sante = str(d.get("HealthStatus", ""))
        ok = sante in ("0", "Healthy", "Sain")
        res.append({"nom": d.get("FriendlyName", "disque"), "ok": ok,
                    "details": ("en bonne santé" if ok else f"état : {sante or 'inconnu'}")})
    return res


def corbeille(chemin):
    """Envoie à la corbeille de Windows (pas de suppression définitive)."""
    class SH(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
    op = SH(None, 3, str(chemin) + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, 0, None, None)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


ENERGIE = {"economie": "a1841308-3541-4fab-bc81-f71556f20b4a", "equilibre": "381b4222-f694-41f0-9685-ff5bb260df2e",
           "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}


def energie(choix=None):
    if choix:
        g = ENERGIE.get(choix)
        return bool(g) and run(["powercfg", "/setactive", g], 10)[0] == 0
    code, out = run(["powercfg", "/getactivescheme"], 10)
    for k, g in ENERGIE.items():
        if g in out.lower():
            return k
    return ""


def version_windows():
    try:
        v = sys.getwindowsversion()
        return "Windows 11" if v.build >= 22000 else "Windows 10" if v.major == 10 else f"Windows {v.major}"
    except Exception:
        return "Windows"
