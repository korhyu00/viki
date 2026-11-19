"""Le « cerveau » de Viki : comprendre tes allées et venues, ce que tu fais, ne pas se répéter, apprendre.
Tout reste sur ton PC (cerveau.json, lisible seulement par toi). Chaque partie se coupe dans les réglages.

  - présence : absence réelle (clavier / souris, écran verrouillé, mise en veille), accueil selon le contexte ;
  - routines : à quelle heure tu pars / reviens selon le jour, pour ne pas bavarder quand tu es pressé ;
  - activité : coder, jouer, vidéo, appel (micro ou caméra utilisés)… et le fil de la journée ;
  - fatigue / blocage : même erreur copiée plusieurs fois, longue session sans pause ;
  - anti-répétition : ce qu'elle a dit et quand, pour varier ;
  - souvenirs avec ton accord, corrections, commandes perso, commandes pas comprises.
"""
import datetime
import difflib
import json
import os
import re
import shutil
import statistics
import subprocess
import time
import unicodedata
from pathlib import Path

STATE_FILE = None                 # fixé par compagnon.py : ~/.config/viki/cerveau.json


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def norm(t):
    """Phrase -> clé pour comparer (sans accents, ponctuation, émojis, nombres, prénom)."""
    t = _sa(t)
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^a-z# ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fmt_d(s):
    s = int(s)
    if s < 3600:
        return f"{max(1, s // 60)} minute{'s' if s >= 120 else ''}"
    h, m = s // 3600, s % 3600 // 60
    return f"{h} heure{'s' if h > 1 else ''}" + (f" {m:02d}" if m and h < 5 else "")


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
CAT_TXT = {"travail": "tu travaillais", "code": "tu codais", "creation": "tu créais", "video": "tu regardais une vidéo",
           "web": "tu naviguais sur internet", "discussion": "tu discutais", "jeu": "tu jouais", "appel": "tu étais en appel",
           "musique": "tu écoutais de la musique"}
CAT_NOM = {"travail": "travail", "code": "code", "creation": "création", "video": "vidéos", "web": "internet",
           "discussion": "discussions", "jeu": "jeux", "appel": "appels", "musique": "musique"}
CODE_APPS = ("code", "codium", "vscodium", "jetbrains", "pycharm", "idea", "clion", "zed", "sublime", "kate", "nvim",
             "neovide", "emacs", "konsole", "alacritty", "kitty", "wezterm", "gnome-terminal", "terminal", "godot")


class Cerveau:
    def __init__(self, path=None):
        self.path = Path(path or STATE_FILE)
        try:
            self.s = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.s = {}
        for k, v in (("dit", {}), ("sessions", []), ("departs", []), ("retours", []), ("fil", []), ("temps", {}),
                     ("alias", {}), ("rates", []), ("presence_h", [[0] * 24 for _ in range(7)]), ("refuses", [])):
            self.s.setdefault(k, v)
        self.absent_since = None        # time.time() du départ, None si présent
        self.session_start = time.time()
        self.last_wall = time.time()
        self.cat, self.cat_since, self.app, self.title = "", time.time(), "", ""
        self.last_cmd = None            # (texte, instant)
        self.pending_fact = None        # (fait, instant)
        self.err_sig = {}
        self.ignore = {}                # catégorie -> (série d'ignorés, dernier instant)
        self.pause_said = 0.0
        self._dirty = False
        self._saved = 0.0

    # ------------------------------------------------------------ stockage
    def save(self, force=False):
        if not (self._dirty or force) or (not force and time.time() - self._saved < 20):
            return
        try:
            self.s["fil"] = self.s["fil"][-600:]
            self.s["sessions"] = self.s["sessions"][-300:]
            self.s["rates"] = self.s["rates"][-80:]
            cut = time.time() - 30 * 86400
            self.s["dit"] = {k: v for k, v in self.s["dit"].items() if v > cut}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self.path) + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.s, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._saved, self._dirty = time.time(), False
        except Exception:
            pass

    def forget_all(self):
        self.s = {}
        self.__init__(self.path)
        self.save(force=True)

    def log(self, kind, txt):
        """Le fil de la journée : (instant, type, texte)."""
        txt = (txt or "").strip()
        if not txt:
            return
        if self.s["fil"] and self.s["fil"][-1][1] == kind and self.s["fil"][-1][2] == txt:
            return
        self.s["fil"].append([round(time.time()), kind, txt[:120]])
        self._dirty = True

    # ------------------------------------------------------------ anti-répétition
    def recently(self, text, days=3):
        k = norm(text)
        ts = self.s["dit"].get(k)
        return bool(ts and time.time() - ts < days * 86400)

    def said(self, text):
        k = norm(text)
        if len(k) > 6:
            self.s["dit"][k] = round(time.time())
            self._dirty = True

    def pick(self, lines, days=3):
        """Une phrase pas dite récemment (ni presque pareille). Sinon la plus ancienne."""
        import random
        if not lines:
            return ""
        recent = [k for k, v in self.s["dit"].items() if time.time() - v < days * 86400]
        fresh = []
        for l in lines:
            k = norm(l)
            if k in self.s["dit"] and time.time() - self.s["dit"][k] < days * 86400:
                continue
            if any(difflib.SequenceMatcher(None, k, r).ratio() > 0.88 for r in recent[-120:]):
                continue
            fresh.append(l)
        if fresh:
            return random.choice(fresh)
        return min(lines, key=lambda l: self.s["dit"].get(norm(l), 0))

    # ------------------------------------------------------------ présence
    def presence_tick(self, idle, locked):
        """idle = secondes sans clavier/souris. Renvoie ("depart", depuis) | ("retour", absence, avant) | None."""
        now = time.time()
        gap = now - self.last_wall
        self.last_wall = now
        if gap > 180 and self.absent_since is None:          # le PC était en veille
            self.absent_since = now - gap
        ev = None
        if self.absent_since is None and (locked or idle > 5 * 60):
            self.absent_since = now - (idle if not locked else min(idle, 60))
            ev = ("depart", self.absent_since)
        elif self.absent_since is not None and not locked and idle < 30:
            away = now - self.absent_since
            before = self.cat
            self.s["sessions"].append([round(self.session_start), round(self.absent_since)])
            if away > 90 * 60:
                d = datetime.datetime.fromtimestamp(self.absent_since)
                if 5 <= d.hour <= 22:
                    self.s["departs"].append([d.weekday(), d.hour * 60 + d.minute, d.date().isoformat()])
                    self.s["departs"] = self.s["departs"][-120:]
                r = datetime.datetime.fromtimestamp(now)
                self.s["retours"].append([r.weekday(), r.hour * 60 + r.minute, r.date().isoformat()])
                self.s["retours"] = self.s["retours"][-120:]
            self.absent_since = None
            self.session_start = now
            self.pause_said = 0.0
            self.log("presence", f"absent {fmt_d(away)}")
            self._dirty = True
            ev = ("retour", away, before)
        if self.absent_since is None:
            d = datetime.datetime.now()
            self.s["presence_h"][d.weekday()][d.hour] += 1
            self._dirty = True
        return ev

    def present(self):
        return self.absent_since is None

    def session_len(self):
        return time.time() - self.session_start if self.absent_since is None else 0

    # ------------------------------------------------------------ routines
    def usual_departure(self, weekday):
        """Heure habituelle de départ ce jour-là (minutes depuis minuit), si c'est régulier."""
        xs = [m for w, m, _d in self.s["departs"] if w == weekday][-6:]
        days = {d for w, _m, d in self.s["departs"] if w == weekday}
        if len(xs) < 3 or len(days) < 3:
            return None
        med = statistics.median(xs)
        if statistics.pstdev(xs) > 50:
            return None
        return int(med)

    def leaving_soon(self, now=None):
        now = now or datetime.datetime.now()
        dep = self.usual_departure(now.weekday())
        if dep is None:
            return None
        cur = now.hour * 60 + now.minute
        return dep - cur if 0 <= dep - cur <= 45 else None

    def routines_text(self):
        lines = []
        for w in range(7):
            dep = self.usual_departure(w)
            rets = [m for ww, m, _d in self.s["retours"] if ww == w][-6:]
            r = int(statistics.median(rets)) if len(rets) >= 3 and statistics.pstdev(rets) < 60 else None
            if dep is not None or r is not None:
                lines.append(f"{JOURS[w].capitalize()} : " + ", ".join(
                    x for x in ((f"tu pars vers {dep // 60} h {dep % 60:02d}" if dep is not None else ""),
                                (f"tu reviens vers {r // 60} h {r % 60:02d}" if r is not None else "")) if x))
        ph = self.s["presence_h"]
        tot = [sum(ph[w][h] for w in range(7)) for h in range(24)]
        if sum(tot) > 60:
            top = sorted(range(24), key=lambda h: -tot[h])[:4]
            lines.append("Tu es le plus souvent là vers : " + ", ".join(f"{h} h" for h in sorted(top)))
        return "\n".join(lines) or "Je n'ai pas encore assez observé tes habitudes (il me faut quelques semaines)."

    # ------------------------------------------------------------ activité
    def activity(self, cls, title, cat, call=False, music=False):
        """Fenêtre active -> catégorie enrichie. Renvoie la catégorie si elle a changé."""
        c = (cls or "").lower()
        if call:
            cat2 = "appel"
        elif any(k in c for k in CODE_APPS):
            cat2 = "code"
        else:
            cat2 = cat or ("musique" if music else "")
        now = time.time()
        if cat2 != self.cat:
            if self.cat:
                d = now - self.cat_since
                day = datetime.date.today().isoformat()
                t = self.s["temps"].setdefault(day, {})
                t[self.cat] = round(t.get(self.cat, 0) + d / 60, 1)
                for k in sorted(self.s["temps"])[:-35]:
                    del self.s["temps"][k]
            prev, self.cat, self.cat_since = self.cat, cat2, now
            self.app, self.title = c, title or ""
            if cat2:
                pr = project_of(c, title) if cat2 == "code" else ""
                what = f"code ({pr})" if pr else CAT_NOM.get(cat2, cat2)
                self.log("activite", what)
            self._dirty = True
            return cat2 if cat2 != prev else None
        self.app, self.title = c, title or ""
        return None

    def quiet(self):
        """Elle ne bavarde pas : appel, jeu, film."""
        return self.cat in ("appel", "jeu", "video")

    def busy_coding(self):
        return self.cat in ("code", "travail")

    def today_minutes(self, day=None):
        day = day or datetime.date.today().isoformat()
        t = dict(self.s["temps"].get(day, {}))
        if self.cat and day == datetime.date.today().isoformat():
            t[self.cat] = round(t.get(self.cat, 0) + (time.time() - self.cat_since) / 60, 1)
        return t

    def day_text(self, day=None, for_ai=False):
        day = day or datetime.date.today().isoformat()
        t = self.today_minutes(day)
        parts = [f"{CAT_NOM.get(k, k)} {fmt_d(v * 60)}" for k, v in sorted(t.items(), key=lambda kv: -kv[1]) if v >= 5]
        d0 = datetime.datetime.fromisoformat(day).timestamp()
        ev = [e for e in self.s["fil"] if d0 <= e[0] < d0 + 86400]
        acts = list(dict.fromkeys(e[2] for e in ev if e[1] in ("commande", "vu")))[-12:]
        chats = [e[2] for e in ev if e[1] == "discussion"][-5:]
        projets = sorted({re.search(r"\((.+)\)", e[2]).group(1) for e in ev
                          if e[1] == "activite" and re.search(r"\((.+)\)", e[2])})
        if for_ai:
            out = []
            if parts:
                out.append("temps passé : " + ", ".join(parts))
            if projets:
                out.append("projets : " + ", ".join(projets[:4]))
            if acts:
                out.append("ce qu'il t'a demandé : " + " ; ".join(acts[-8:]))
            if chats:
                out.append("sujets de discussion : " + " ; ".join(chats))
            return ". ".join(out)
        lines = []
        if parts:
            lines.append("⏱️ " + ", ".join(parts))
        if projets:
            lines.append("💻 Projets : " + ", ".join(projets))
        if acts:
            lines.append("✨ Tu m'as demandé : " + " · ".join(acts))
        if chats:
            lines.append("💬 On a parlé de : " + " · ".join(chats))
        aw = [e for e in ev if e[1] == "presence"]
        if aw:
            lines.append(f"🚶 Tu t'es absenté {len(aw)} fois.")
        return "\n".join(lines)

    def recent_text(self, minutes=90):
        cut = time.time() - minutes * 60
        ev = [e for e in self.s["fil"] if e[0] >= cut and e[1] in ("activite", "commande", "vu", "discussion")]
        if not ev:
            return ""
        out = []
        for ts, kind, txt in ev[-8:]:
            h = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
            out.append(f"{h} " + {"activite": "tu étais sur", "commande": "tu m'as demandé",
                                  "vu": "tu as ouvert", "discussion": "on a parlé de"}[kind] + f" {txt}")
        return "\n".join(out)

    # ------------------------------------------------------------ fatigue / blocage
    def error_copied(self, text):
        sig = norm(text.strip().splitlines()[-1] if text.strip() else "")[:80]
        now = time.time()
        n, first = self.err_sig.get(sig, (0, now))
        if now - first > 30 * 60:
            n, first = 0, now
        n += 1
        self.err_sig[sig] = (n, first)
        return n

    def needs_pause(self):
        if self.session_len() > 3 * 3600 and time.time() - self.pause_said > 2 * 3600:
            self.pause_said = time.time()
            return True
        return False

    # ------------------------------------------------------------ silence quand on l'ignore
    def spont_said(self, cat):
        """Elle vient de dire une phrase spontanée. Si la précédente est restée sans réponse : on la compte."""
        e = self.ignore.setdefault(cat, {"n": 0, "t": 0.0, "ok": True})
        if not e["ok"]:
            e["n"] = min(8, e["n"] + 1)
        e["t"], e["ok"] = time.time(), False

    def interacted(self):
        now = time.time()
        for e in self.ignore.values():
            if not e["ok"] and now - e["t"] < 180:
                e["n"], e["ok"] = max(0, e["n"] - 1), True

    def spont_ok(self, cat, base=420):
        """Plus tu l'ignores, plus elle attend avant de reparler d'elle-même (x1,7 à chaque fois)."""
        e = self.ignore.get(cat)
        if not e:
            return True
        n = e["n"] + (0 if e["ok"] or time.time() - e["t"] < 180 else 1)
        return time.time() - e["t"] > base * (1.7 ** min(n, 6))

    # ------------------------------------------------------------ alias (corrections et commandes perso)
    def alias_for(self, text):
        return self.s["alias"].get(norm(text))

    def set_alias(self, phrase, cmds, kind="perso"):
        k = norm(phrase)
        if not k or not cmds:
            return False
        self.s["alias"][k] = {"dit": phrase.strip(), "faire": cmds, "type": kind, "date": datetime.date.today().isoformat()}
        self._dirty = True
        self.save(force=True)
        return True

    def del_alias(self, key):
        self.s["alias"].pop(key, None)
        self._dirty = True
        self.save(force=True)

    # ------------------------------------------------------------ commandes pas comprises
    def failed(self, text):
        k = norm(text)
        for r in self.s["rates"]:
            if r["k"] == k:
                r["n"] += 1
                r["date"] = datetime.date.today().isoformat()
                break
        else:
            self.s["rates"].append({"k": k, "dit": text.strip()[:100], "n": 1, "date": datetime.date.today().isoformat()})
        self._dirty = True

    def solved(self, text):
        k = norm(text)
        self.s["rates"] = [r for r in self.s["rates"] if r["k"] != k]
        self._dirty = True


# ------------------------------------------------------------------ outils
def project_of(cls, title):
    """« main.py - viki - VSCodium » -> « viki »."""
    t = title or ""
    parts = [p.strip() for p in re.split(r" [-—–] ", t) if p.strip()]
    if len(parts) >= 3:
        return parts[-2][:40]
    if len(parts) == 2 and not re.search(r"\.\w{1,5}$", parts[0]):
        return parts[0][:40]
    return ""


def idle_seconds(cursor_idle):
    """Secondes sans clavier ni souris (KDE / GNOME / X11 / Windows). Sinon : depuis le dernier mouvement de souris."""
    if os.name == "nt":
        try:
            import ctypes

            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            li = LII()
            li.cbSize = ctypes.sizeof(LII)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
            return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
        except Exception:
            return cursor_idle
    env = _env()
    for cmd, div in ((["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver",
                       "org.freedesktop.ScreenSaver.GetSessionIdleTime"], 1000.0),
                     (["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor", "--object-path",
                       "/org/gnome/Mutter/IdleMonitor/Core", "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"], 1000.0),
                     (["xprintidle"], 1000.0)):
        if not shutil.which(cmd[0]):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=2, env=env).stdout
            m = re.search(r"(\d+)", out)
            if m:
                v = int(m.group(1)) / div
                if cmd[0] == "qdbus" and v > 10 ** 6:       # certaines versions renvoient des ms, d'autres des s
                    v /= 1000
                return min(v, cursor_idle) if cursor_idle < 30 else v
        except Exception:
            continue
    return cursor_idle


def screen_locked():
    if os.name == "nt":
        return False
    env = _env()
    for cmd in (["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver.GetActive"],
                ["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver", "--object-path",
                 "/org/gnome/ScreenSaver", "--method", "org.gnome.ScreenSaver.GetActive"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=2, env=env).stdout.lower()
            if "true" in out:
                return True
            if "false" in out:
                return False
        except Exception:
            continue
    sid = os.environ.get("XDG_SESSION_ID")
    if sid and shutil.which("loginctl"):
        try:
            out = subprocess.run(["loginctl", "show-session", sid, "-p", "LockedHint"], capture_output=True,
                                 text=True, timeout=2).stdout
            return "yes" in out.lower()
        except Exception:
            pass
    return False


def in_call():
    """Micro utilisé par une autre appli (PipeWire / PulseAudio), ou caméra ouverte."""
    if os.name == "nt":
        return False
    if shutil.which("pactl"):
        try:
            out = subprocess.run(["pactl", "list", "source-outputs"], capture_output=True, text=True, timeout=2,
                                 env=_env()).stdout
            apps = re.findall(r'application\.(?:name|process\.binary) = "([^"]+)"', out)
            apps = [a.lower() for a in apps if not re.search(r"viki|python|compagnon|whisper|cava|pavucontrol|"
                                                             r"easyeffects|plasma|kwin|pipewire", a.lower())]
            if apps:
                return True
        except Exception:
            pass
    try:
        uid = os.getuid()
        for p in Path("/proc").iterdir():
            if not p.name.isdigit():
                continue
            try:
                if p.stat().st_uid != uid:
                    continue
                for fd in (p / "fd").iterdir():
                    try:
                        if os.readlink(fd).startswith("/dev/video"):
                            return True
                    except OSError:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return False


def _env():
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH"):
        env.pop(k, None)
    if os.environ.get("COMPAGNON_ORIG_LD"):
        env["LD_LIBRARY_PATH"] = os.environ["COMPAGNON_ORIG_LD"]
    return env


# ------------------------------------------------------------------ souvenirs proposés (avec accord)
FACT_RX = [
    (r"\bje m'?appelle ([a-zà-ÿ'\- ]{2,25})$", "Tu t'appelles {}"),
    (r"\bj'?(?:adore|aime beaucoup|aime trop|kiffe) ((?:le |la |les |l'|faire |jouer |regarder |ecouter |écouter )?[^,.!?]{3,40})",
     "Tu adores {}"),
    (r"\bje (?:deteste|déteste|hais|supporte pas) ([^,.!?]{3,40})", "Tu détestes {}"),
    (r"\bmon (chat|chien|lapin|hamster|frere|frère|pere|père|copain|meilleur ami|fils|mari) s'?appelle ([a-zà-ÿ'\- ]{2,20})",
     "Ton {} s'appelle {}"),
    (r"\bma (chatte|chienne|soeur|sœur|mere|mère|copine|meilleure amie|fille|femme) s'?appelle ([a-zà-ÿ'\- ]{2,20})",
     "Ta {} s'appelle {}"),
    (r"\bje (?:bosse|travaille) ((?:sur|chez|comme|dans) [^,.!?]{3,40})", "Tu travailles {}"),
    (r"\bj'?habite ((?:a|à|en|au|aux|dans) [^,.!?]{2,30})", "Tu habites {}"),
    (r"\bje suis ((?:etudiant|étudiant|etudiante|étudiante|developpeur|développeur|developpeuse|développeuse|"
     r"graphiste|musicien|musicienne|infirmier|infirmière|prof|professeur|lyceen|lycéen|lycéenne|streamer|streameuse)"
     r"(?: en [^,.!?]{2,30})?)", "Tu es {}"),
    (r"\bmon (jeu|film|anime|animé|manga|groupe|artiste|plat|livre|serie|série) (?:prefere|préféré) "
     r"(?:est|c'?est) ([^,.!?]{2,40})", "Ton {} préféré : {}"),
    (r"\bmon anniversaire (?:c'?est|est) le ([0-9]{1,2} [a-zéû]+)", "Ton anniversaire est le {}"),
]


def propose_fact(text):
    t = text.strip()
    tl = t.lower()
    if "?" in t or len(t) > 300 or re.search(r"\b(?:si |peut-etre|peut-être|j'aimerais|je voudrais|pas trop)\b", tl):
        return None
    for rx, tpl in FACT_RX:
        m = re.search(rx, tl)
        if not m:
            continue
        g = [t[m.start(i):m.end(i)].strip() for i in range(1, (m.lastindex or 0) + 1) if m.group(i)]
        if not g:
            continue
        g = [re.sub(r"\s+(?:et|mais|car|parce|quand|aussi|trop|vraiment|depuis)\b.*$", "", x, flags=re.I) for x in g]
        if tpl.count("{}") == 2 and len(g) >= 2:
            return tpl.format(g[0].lower(), g[1].strip().title())
        if "appelles" in tpl:
            return tpl.format(g[0].strip().title())
        return tpl.format(" ".join(g))
    return None


# ------------------------------------------------------------------ fenêtre « Ce qu'elle sait de moi »
def make_window(comp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QPushButton,
                                 QTabWidget, QTextEdit, QVBoxLayout, QWidget)
    B = comp.brain

    class W(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window)
            self.setWindowTitle("🧠 Ce qu'elle sait de moi")
            self.resize(720, 560)
            lay = QVBoxLayout(self)
            info = QLabel("Tout reste sur ton PC. Tu peux tout voir, corriger ou effacer.")
            info.setWordWrap(True)
            lay.addWidget(info)
            self.tabs = QTabWidget()
            lay.addWidget(self.tabs, 1)
            self.f_list = self._list_tab("💜 Souvenirs", self._facts, [("➕ Ajouter…", self._add_fact),
                                                                        ("🗑 Retirer", self._del_fact)])
            self.a_list = self._list_tab("🗣️ Mes commandes", self._aliases, [("➕ Nouvelle commande…", self._add_alias),
                                                                             ("🗑 Retirer", self._del_alias)])
            self.r_list = self._list_tab("❓ Pas compris", self._rates, [("🎓 Lui apprendre…", self._teach),
                                                                         ("🗑 Retirer", self._del_rate)])
            self.h = QTextEdit()
            self.h.setReadOnly(True)
            self.tabs.addTab(self.h, "📅 Habitudes et journée")
            row = QHBoxLayout()
            b = QPushButton("🧹 Tout oublier (sauf mes souvenirs)")
            b.clicked.connect(self._forget)
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            self.refresh()

        def _list_tab(self, name, fill, buttons):
            w = QWidget()
            v = QVBoxLayout(w)
            lst = QListWidget()
            lst.setWordWrap(True)
            v.addWidget(lst, 1)
            r = QHBoxLayout()
            for lab, fn in buttons:
                b = QPushButton(lab)
                b.clicked.connect(fn)
                r.addWidget(b)
            r.addStretch(1)
            v.addLayout(r)
            self.tabs.addTab(w, name)
            lst._fill = fill
            return lst

        def refresh(self):
            for l in (self.f_list, self.a_list, self.r_list):
                l.clear()
                l._fill(l)
            hist = []
            for d in sorted(B.s["temps"])[-7:][::-1]:
                tx = B.day_text(d)
                if tx:
                    hist.append(f"━━ {d}\n{tx}")
            self.h.setPlainText("🔁 Tes habitudes\n" + B.routines_text() + "\n\n" +
                                ("📅 Aujourd'hui\n" + (B.day_text() or "Rien de noté pour l'instant.")) + "\n\n" +
                                "\n\n".join(hist[1:]))

        def _facts(self, l):
            for f in comp.memory.get("faits", []):
                l.addItem(f)

        def _aliases(self, l):
            for k, a in sorted(B.s["alias"].items()):
                it = QListWidgetItem(f"« {a['dit']} »  →  " + " puis ".join(f"« {x} »" for x in a["faire"]) +
                                     ("   (correction)" if a.get("type") == "correction" else ""))
                it.setData(Qt.ItemDataRole.UserRole, k)
                l.addItem(it)

        def _rates(self, l):
            for r in sorted(B.s["rates"], key=lambda r: -r["n"]):
                it = QListWidgetItem(f"« {r['dit']} »  ({r['n']} fois, dernière le {r['date']})")
                it.setData(Qt.ItemDataRole.UserRole, r["dit"])
                l.addItem(it)

        def _add_fact(self):
            t, ok = QInputDialog.getText(self, "💜 Souvenir", "Ce qu'elle doit savoir sur toi :")
            if ok and t.strip():
                comp.memory.setdefault("faits", []).append(t.strip())
                comp._save_memory()
                self.refresh()

        def _del_fact(self):
            it = self.f_list.currentItem()
            if it and it.text() in comp.memory.get("faits", []):
                comp.memory["faits"].remove(it.text())
                comp._save_memory()
                self.refresh()

        def _add_alias(self, phrase=""):
            p, ok = QInputDialog.getText(self, "🗣️ Nouvelle commande", "Quand je dis :", text=phrase or "")
            if not ok or not p.strip():
                return
            d, ok = QInputDialog.getText(self, "🗣️ Nouvelle commande", "Elle fait (plusieurs : sépare par « puis ») :")
            if ok and d.strip():
                B.set_alias(p, [x.strip() for x in re.split(r"\s*(?:,? puis |;)\s*", d) if x.strip()])
                B.solved(p)
                self.refresh()

        def _del_alias(self):
            it = self.a_list.currentItem()
            if it:
                B.del_alias(it.data(Qt.ItemDataRole.UserRole))
                self.refresh()

        def _teach(self):
            it = self.r_list.currentItem()
            if it:
                self._add_alias(it.data(Qt.ItemDataRole.UserRole))

        def _del_rate(self):
            it = self.r_list.currentItem()
            if it:
                B.solved(it.data(Qt.ItemDataRole.UserRole))
                B.save(force=True)
                self.refresh()

        def _forget(self):
            B.forget_all()
            self.refresh()
            comp.say("J'ai tout oublié : tes habitudes, tes commandes et ma mémoire de ce que j'ai dit. "
                     "Tes souvenirs, eux, sont toujours là.")

    return W()
