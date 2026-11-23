#!/usr/bin/env python3
"""Fonctions en plus du compagnon : notes, minuteurs, agenda .ics, surveillance du PC,
rangement des téléchargements, activité, fêtes, petit chat, jeux, écoute continue.

Tout est local. Le seul accès internet possible ici est la vérification des mises à jour,
et seulement si tu l'actives ou la demandes.
"""
import datetime
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import threading
import time
import unicodedata
import wave
from pathlib import Path

try:
    import plateforme
    IS_WIN = plateforme.IS_WIN
except Exception:
    plateforme = None
    IS_WIN = False

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout,
                             QWidget)


def sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _popen(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception:
        return False


_NB = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
       "neuf": 9, "dix": 10, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
       "soixante": 60, "quart": 15, "demi": 30, "demie": 30}


# ================================================================ notes et liste de courses
def _split_items(s):
    s = re.sub(r"\s+(?:et|puis|avec)\s+", ",", s)
    out = []
    for it in s.split(","):
        it = it.strip(" .!?;:'\"")
        it = re.sub(r"^(?:du|de la|de l'|des|de|d'|le|la|les|l'|un|une)\s*", "", it, flags=re.I)
        if it:
            out.append(it)
    return out


def parse_notes(text):
    """Commandes de notes / courses -> (action, données) ou None."""
    t = text.strip().rstrip(" !?.")
    ta = sans_accents(t)
    m = re.match(r"^(?:ajoute|rajoute|mets|met)\s+(.+?)\s+(?:a|à|dans|sur)\s+(?:la\s+|ma\s+)?(?:liste\s+(?:de\s+|des\s+)?)?"
                 r"courses$", t, re.I)
    if m:
        return ("courses_add", _split_items(m.group(1)))
    m = re.match(r"^(?:il (?:me )?faut|je dois|faut) acheter\s+(.+)$", t, re.I)
    if m:
        return ("courses_add", _split_items(m.group(1)))
    m = re.match(r"^(?:j'ai achete|j'ai pris|enleve|retire|supprime)\s+(.+?)(?:\s+(?:de|des)\s+(?:la\s+|ma\s+)?"
                 r"(?:liste\s+(?:de\s+)?)?courses)?$", ta)
    if m and ("courses" in ta or ta.startswith("j'ai")):
        return ("courses_remove", _split_items(m.group(1)))
    if re.search(r"\b(vide|efface|supprime)\b.*\b(liste de courses|courses)\b", ta):
        return ("courses_clear", None)
    if re.search(r"\b(liste de courses|mes courses|qu'?est[- ]ce que (je dois|j'ai a) acheter|"
                 r"quoi acheter)\b", ta):
        return ("courses_show", None)
    m = re.match(r"^(?:note|notes|prends note|prend note|ecris|retiens|souviens[- ]toi)\s*(?:que|de|:|,)?\s+(.+)$",
                 t, re.I)
    if m and not re.match(r"^(?:mes|les)\b", m.group(1), re.I) and not ta.startswith("souviens-toi de moi"):
        return ("note_add", m.group(1).strip())
    if re.search(r"\b(vide|efface|supprime)\b.*\b(mes |les |toutes les )?notes\b", ta):
        return ("notes_clear", None)
    if re.search(r"^(mes notes|montre[- ]moi mes notes|lis[- ]moi mes notes|affiche mes notes|"
                 r"qu'?est[- ]ce que (j'ai|tu as) note)", ta):
        return ("notes_show", None)
    return None


class NotesWindow(QWidget):
    """Notes et liste de courses (cases à cocher, ajout, suppression)."""

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setWindowTitle("Notes et courses")
        self.resize(420, 480)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.lists = {}
        for key, label in (("notes", "Notes"), ("courses", "Liste de courses")):
            w = QWidget()
            v = QVBoxLayout(w)
            lw = QListWidget()
            lw.itemChanged.connect(lambda _it, k=key: self._sync(k))
            v.addWidget(lw, 1)
            row = QHBoxLayout()
            ed = QLineEdit()
            ed.setPlaceholderText("Ajouter…  (Entrée)")
            ed.returnPressed.connect(lambda k=key, e=ed: self._add(k, e))
            row.addWidget(ed, 1)
            rm = QPushButton("Supprimer")
            rm.clicked.connect(lambda _=False, k=key: self._remove(k))
            row.addWidget(rm)
            cp = QPushButton("Copier")
            cp.clicked.connect(lambda _=False, k=key: QApplication.clipboard().setText(
                "\n".join("- " + x["txt"] for x in self.comp.memory.get(k, []))))
            row.addWidget(cp)
            v.addLayout(row)
            if key == "courses":
                cl = QPushButton("Enlever ce qui est coché")
                cl.clicked.connect(self._clear_checked)
                v.addWidget(cl)
            self.tabs.addTab(w, label)
            self.lists[key] = lw
        self._loading = False

    def open(self, key="notes"):
        self.reload()
        self.tabs.setCurrentIndex(0 if key == "notes" else 1)
        self.show()
        self.raise_()
        self.activateWindow()

    def reload(self):
        self._loading = True
        for key, lw in self.lists.items():
            lw.clear()
            for x in self.comp.memory.get(key, []):
                label = x["txt"] if key == "courses" else f"{x['txt']}    ({x.get('date', '')})"
                it = QListWidgetItem(label)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if x.get("ok") else Qt.CheckState.Unchecked)
                lw.addItem(it)
        self._loading = False

    def _sync(self, key):
        if self._loading:
            return
        lw = self.lists[key]
        items = self.comp.memory.get(key, [])
        for i in range(min(lw.count(), len(items))):
            items[i]["ok"] = lw.item(i).checkState() == Qt.CheckState.Checked
        self.comp._save_memory()

    def _add(self, key, ed):
        txt = ed.text().strip()
        if txt:
            if key == "courses":
                for it in _split_items(txt):
                    self.comp.memory.setdefault(key, []).append({"txt": it})
            else:
                self.comp.memory.setdefault(key, []).append(
                    {"txt": txt, "date": datetime.datetime.now().strftime("%d/%m %H:%M")})
            self.comp._save_memory()
            ed.clear()
            self.reload()

    def _remove(self, key):
        row = self.lists[key].currentRow()
        if row >= 0:
            self.comp.memory.get(key, []).pop(row)
            self.comp._save_memory()
            self.reload()

    def _clear_checked(self):
        self.comp.memory["courses"] = [x for x in self.comp.memory.get("courses", []) if not x.get("ok")]
        self.comp._save_memory()
        self.reload()


# ================================================================ minuteur et pomodoro
def parse_timer(text):
    """« minuteur 10 minutes », « réveille-moi dans 20 min », « préviens-moi dans une heure »
       -> (secondes, libellé) ou None."""
    t = sans_accents(text.strip().rstrip(" !?."))
    if not re.search(r"\b(minuteur|timer|chrono|compte a rebours|reveille[- ]moi|previens[- ]moi|"
                     r"sonne dans)\b", t):
        return None
    secs = 0
    hm = re.search(r"\b(\d+)\s*h\s*(\d{1,2})\b", t)
    if hm:
        secs = int(hm.group(1)) * 3600 + int(hm.group(2)) * 60
        t = t.replace(hm.group(0), " ")
    for m in re.finditer(r"(\d+|[a-z]+)\s*(h|heures?|min|minutes?|mn|s|sec|secondes?)\b", t):
        n = int(m.group(1)) if m.group(1).isdigit() else _NB.get(m.group(1))
        if not n:
            continue
        u = m.group(2)
        secs += n * 3600 if u.startswith("h") else n if u.startswith("s") else n * 60
    if re.search(r"\b(une )?demi[- ]heure\b", t):
        secs = max(secs, 1800)
    if not secs:
        return None
    m = re.search(r"\b(?:pour|de)\s+(?!\d)([a-zà-ÿœ'].{2,40})$",
                  text.strip().rstrip(" !?.").lower())
    label = m.group(1).strip() if m and not re.search(r"(min|heure|seconde)", m.group(1)) else ""
    return secs, label


def parse_pomodoro(text):
    t = sans_accents(text.strip().rstrip(" !?."))
    if not re.search(r"\bpomodoro\b|\bsession de travail\b", t):
        return None
    if re.search(r"\b(arrete|stop|stoppe|annule|fin)\b", t):
        return ("stop", 0)
    m = re.search(r"(\d+)\s*(?:min|minutes?)?", t)
    return ("start", int(m.group(1)) if m else 25)


def fmt_duree(secs):
    secs = int(secs)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d}" if m else f"{h} heure{'s' if h > 1 else ''}"
    if m:
        return f"{m} minute{'s' if m > 1 else ''}" + (f" {s} s" if s and m < 5 else "")
    return f"{s} seconde{'s' if s > 1 else ''}"


# ================================================================ presse-papiers
def is_french(text):
    w = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", text.lower())
    if not w:
        return True
    fr = sum(1 for x in w if x in {"le", "la", "les", "de", "des", "du", "et", "est", "un", "une", "que", "qui",
                                    "pour", "dans", "pas", "je", "tu", "il", "nous", "vous", "sur", "avec", "ce",
                                    "c'est", "au", "aux", "mais", "ou", "en"})
    en = sum(1 for x in w if x in {"the", "and", "is", "are", "of", "to", "in", "that", "it", "for", "you",
                                    "with", "on", "this", "be", "was", "not", "have", "i", "we", "they"})
    return fr >= en


def clip_prompt(action, text, lang=""):
    text = text[:6000]
    if action == "resumer":
        return ("Résume ce texte en français, en 3 à 5 phrases claires, avec tes propres mots. "
                "Donne seulement le résumé.\n\n---\n" + text)
    if action == "corriger":
        return ("Corrige l'orthographe, la grammaire et la ponctuation de ce texte, sans changer son sens ni "
                "sa langue. Donne seulement le texte corrigé, sans explication.\n\n---\n" + text)
    target = lang or ("anglais" if is_french(text) else "français")
    return (f"Traduis ce texte en {target}, de façon naturelle. Donne seulement la traduction.\n\n---\n" + text)


def parse_clip_cmd(text):
    t = sans_accents(text)
    if not re.search(r"(presse[- ]papiers?|ce que j'ai copie|le texte copie|ce que je viens de copier)", t):
        return None
    lang = ""
    m = re.search(r"\ben (anglais|francais|espagnol|allemand|italien|portugais|japonais|chinois|arabe|russe|"
                  r"neerlandais|coreen)\b", t)
    if m:
        lang = m.group(1).replace("francais", "français").replace("neerlandais", "néerlandais").replace(
            "coreen", "coréen")
    if re.search(r"\b(resume|resumer|resumes)\b", t):
        return ("resumer", lang)
    if re.search(r"\b(tradui|traduction)", t):
        return ("traduire", lang)
    if re.search(r"\b(corrige|corriger|relis|orthographe)", t):
        return ("corriger", lang)
    return ("menu", lang)


class ClipPopup(QWidget):
    """Petites bulles-boutons au-dessus d'elle quand tu copies un texte."""

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.comp = comp
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        css = ("QPushButton { background: #fff4f8; border: 1px solid #d48aa6; border-radius: 11px; "
               "padding: 4px 10px; color: #4a2433; } QPushButton:hover { background: #ffd9e7; }")
        for label, act in (("📝 Résumer", "resumer"), ("🌍 Traduire", "traduire"), ("✏️ Corriger", "corriger"),
                           ("🔊 Lire", "lire"), ("✕", None)):
            b = QPushButton(label)
            b.setStyleSheet(css)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=act: self._go(a))
            lay.addWidget(b)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def popup(self, text):
        self.text = text
        self.adjustSize()
        c = self.comp
        g = c.geometry()
        x = int(g.left() + c.char_cx - self.width() / 2)
        y = int(g.top() + max(0, c.bubble_top() - 70))
        scr = QApplication.primaryScreen().availableGeometry()
        x = max(scr.left(), min(x, scr.right() - self.width()))
        y = max(scr.top(), y)
        self.move(x, y)
        self.show()
        self.raise_()
        self.timer.start(12000)

    def _go(self, act):
        self.hide()
        if act:
            self.comp.clip_action(act, "", self.text)


class TextWindow(QWidget):
    """Fenêtre simple de texte avec bouton Copier."""

    def __init__(self, title=""):
        super().__init__(None, Qt.WindowType.Window)
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.edit = QPlainTextEdit()
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        cp = QPushButton("Copier")
        cp.clicked.connect(lambda: QApplication.clipboard().setText(self.edit.toPlainText()))
        row.addWidget(cp)
        row.addStretch()
        cl = QPushButton("Fermer")
        cl.clicked.connect(self.close)
        row.addWidget(cl)
        lay.addLayout(row)
        self.setWindowTitle(title)

    def show_text(self, title, text, info=""):
        self.setWindowTitle(title)
        self.label.setText(info)
        self.label.setVisible(bool(info))
        self.edit.setPlainText(text)
        self.show()
        self.raise_()
        self.activateWindow()


# ================================================================ agenda (.ics)
def find_ics_files():
    """Calendriers locaux connus (KOrganizer / Akonadi, Evolution, Thunderbird hors ligne…)."""
    home = Path.home()
    roots = [home / ".local/share/korganizer", home / ".local/share/apps/korganizer",
             home / ".local/share/evolution/calendar", home / ".local/share/akonadi",
             home / ".local/share/calendars"]
    out = []
    for r in roots:
        if r.exists():
            try:
                for p in r.rglob("*.ics"):
                    if p.stat().st_size < 20_000_000:
                        out.append(str(p))
            except Exception:
                pass
    return out[:30]


def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def _ics_dt(value, params):
    """-> (datetime local naïf, journée entière ?)"""
    v = value.strip()
    if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", v):
        return datetime.datetime.strptime(v[:8], "%Y%m%d"), True
    dt = datetime.datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
    else:
        m = re.search(r"TZID=([^;:]+)", params)
        if m:
            try:
                from zoneinfo import ZoneInfo
                dt = dt.replace(tzinfo=ZoneInfo(m.group(1).strip('"'))).astimezone().replace(tzinfo=None)
            except Exception:
                pass
    return dt, False


def parse_ics(text):
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", _unfold(text), re.S):
        ev = {"summary": "(sans titre)", "exdates": set()}
        for line in block.splitlines():
            if ":" not in line:
                continue
            head, val = line.split(":", 1)
            name, _, params = head.partition(";")
            name = name.upper()
            try:
                if name == "SUMMARY":
                    ev["summary"] = val.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").strip()
                elif name == "DTSTART":
                    ev["start"], ev["allday"] = _ics_dt(val, params)
                elif name == "RRULE":
                    ev["rrule"] = dict(kv.split("=", 1) for kv in val.split(";") if "=" in kv)
                elif name == "EXDATE":
                    for v in val.split(","):
                        ev["exdates"].add(_ics_dt(v, params)[0].date())
                elif name == "STATUS" and val.strip().upper() == "CANCELLED":
                    ev["cancel"] = True
            except Exception:
                pass
        if "start" in ev and not ev.get("cancel"):
            events.append(ev)
    return events


def occurrences(ev, a, b):
    """Occurrences de l'événement entre a et b (datetimes)."""
    st = ev["start"]
    rr = ev.get("rrule")
    out = []
    if not rr:
        return [st] if a <= st < b or (ev.get("allday") and a.date() <= st.date() < b.date() + datetime.timedelta(1)
                                         and a <= st + datetime.timedelta(days=1)) else []
    freq = rr.get("FREQ", "")
    inter = max(1, int(rr.get("INTERVAL", "1") or 1))
    until = None
    if "UNTIL" in rr:
        try:
            until = _ics_dt(rr["UNTIL"], "")[0]
        except Exception:
            pass
    count = int(rr["COUNT"]) if rr.get("COUNT", "").isdigit() else None
    days = None
    if freq == "WEEKLY" and rr.get("BYDAY"):
        codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        days = {codes.index(d[-2:]) for d in rr["BYDAY"].split(",") if d[-2:] in codes}
    n = 0
    cur = st
    guard = 0
    while guard < 5000:
        guard += 1
        if until and cur > until or count is not None and n >= count or cur >= b:
            break
        cands = [cur]
        if days is not None:
            monday = cur - datetime.timedelta(days=cur.weekday())
            cands = sorted(monday + datetime.timedelta(days=d) for d in days)
            cands = [c.replace(hour=st.hour, minute=st.minute) for c in cands if c >= st]
        for c in cands:
            if until and c > until or count is not None and n >= count:
                break
            n += 1
            if a <= c < b and c.date() not in ev["exdates"]:
                out.append(c)
        if freq == "DAILY":
            cur += datetime.timedelta(days=inter)
        elif freq == "WEEKLY":
            cur = (cur - datetime.timedelta(days=cur.weekday()) if days is not None else cur) \
                + datetime.timedelta(weeks=inter)
        elif freq == "MONTHLY":
            mo = cur.month - 1 + inter
            y, mo = cur.year + mo // 12, mo % 12 + 1
            try:
                cur = cur.replace(year=y, month=mo)
            except ValueError:
                cur = cur.replace(year=y, month=mo, day=28)
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + inter)
            except ValueError:
                cur = cur.replace(year=cur.year + inter, day=28)
        else:
            break
        # avance rapide : inutile de parcourir des années passées une par une
        if cur < a - datetime.timedelta(days=400) and freq in ("DAILY", "WEEKLY") and count is None:
            step = datetime.timedelta(days=inter * (7 if freq == "WEEKLY" else 1))
            k = int((a - datetime.timedelta(days=8) - cur) / step)
            if k > 0:
                cur += step * k
    return out


class Agenda:
    def __init__(self):
        self.events = []
        self.loaded_at = 0
        self.mtimes = {}

    def load(self, files):
        evs = []
        for f in files:
            try:
                evs += parse_ics(Path(f).read_text(errors="ignore"))
            except Exception:
                pass
        self.events = evs
        self.loaded_at = time.time()

    def refresh(self, files):
        mt = {}
        for f in files:
            try:
                mt[f] = os.path.getmtime(f)
            except OSError:
                pass
        if mt != self.mtimes or time.time() - self.loaded_at > 3600:
            self.mtimes = mt
            self.load(list(mt))

    def between(self, a, b):
        res = []
        for ev in self.events:
            try:
                for o in occurrences(ev, a, b):
                    res.append((o, ev["summary"], ev.get("allday", False)))
            except Exception:
                pass
        return sorted(res)

    def day(self, date):
        a = datetime.datetime.combine(date, datetime.time())
        return self.between(a, a + datetime.timedelta(days=1))


def agenda_text(items, quand="aujourd'hui"):
    if not items:
        return f"Rien de prévu {quand} dans ton agenda."
    parts = [("toute la journée : " if allday else o.strftime("%Hh%M ")) + s for o, s, allday in items[:5]]
    more = f" (et {len(items) - 5} autres)" if len(items) > 5 else ""
    return f"{quand.capitalize()} : " + " ; ".join(parts) + more + "."


# ================================================================ surveillance du PC
def _read(p):
    try:
        return Path(p).read_text().strip()
    except Exception:
        return ""


def gpu_temps():
    """Températures des cartes graphiques AMD (°C) : {"edge": .., "junction": ..}."""
    out = {}
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        if _read(hw / "name") != "amdgpu":
            continue
        for lab in hw.glob("temp*_label"):
            v = _read(str(lab).replace("_label", "_input"))
            if v.isdigit():
                out[_read(lab)] = int(v) / 1000
    return out


def cpu_temp():
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        if _read(hw / "name") in ("k10temp", "coretemp", "zenpower"):
            v = _read(hw / "temp1_input")
            if v.isdigit():
                return int(v) / 1000
    return None


def pc_status():
    st = {}
    for name, path in (("système", "/"), ("perso", str(Path.home()))):
        try:
            u = shutil.disk_usage(path)
            st[name] = (u.free / 1e9, u.free / u.total * 100)
        except Exception:
            pass
    try:
        mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
        st["ram"] = (int(mem["MemAvailable"].split()[0]) / 1e6, int(mem["MemTotal"].split()[0]) / 1e6)
    except Exception:
        pass
    if IS_WIN:
        try:
            free, tot = plateforme.mem_info()
            st["ram"] = (free, tot)
            st["uptime"] = plateforme.uptime_s()
        except Exception:
            pass
    st["gpu"] = gpu_temps()
    st["cpu"] = cpu_temp()
    try:
        st["uptime"] = float(open("/proc/uptime").read().split()[0])
    except Exception:
        pass
    return st


def pc_status_text(st):
    parts = []
    if "perso" in st:
        parts.append(f"{st['perso'][0]:.0f} Go libres sur ton disque")
    if "ram" in st:
        parts.append(f"{st['ram'][0]:.1f} Go de mémoire libre sur {st['ram'][1]:.0f}")
    g = st.get("gpu") or {}
    if g:
        parts.append(f"carte graphique à {g.get('edge', next(iter(g.values()))):.0f} °C")
    if st.get("cpu"):
        parts.append(f"processeur à {st['cpu']:.0f} °C")
    if st.get("uptime"):
        parts.append(f"allumé depuis {fmt_duree(st['uptime'])}")
    return ("Ton PC va bien : " if parts else "Je n'arrive pas à lire l'état du PC. ") + ", ".join(parts) + "."


def check_updates():
    """Nombre de mises à jour (utilise internet). None si l'outil manque."""
    exe = shutil.which("checkupdates")
    if not exe:
        return None
    try:
        r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
        return len([x for x in r.stdout.splitlines() if x.strip()])
    except Exception:
        return None


# ================================================================ rangement des téléchargements
TIDY = {"Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".heic", ".bmp", ".avif", ".tiff"},
        "Vidéos": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv"},
        "Musique": {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus", ".aac"},
        "Documents": {".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf", ".xls", ".xlsx", ".ods", ".csv",
                      ".ppt", ".pptx", ".odp", ".epub"},
        "Archives": {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".xz", ".zst", ".bz2"},
        "Programmes": {".appimage", ".deb", ".rpm", ".exe", ".msi", ".flatpakref", ".sh", ".run", ".jar"},
        "Images disque": {".iso", ".img"},
        "Torrents": {".torrent"}}
PARTIAL = {".part", ".crdownload", ".download", ".tmp", ".partial"}


def downloads_dir():
    exe = shutil.which("xdg-user-dir")
    if exe:
        try:
            p = subprocess.run([exe, "DOWNLOAD"], capture_output=True, text=True, timeout=3).stdout.strip()
            if p and Path(p).is_dir() and Path(p) != Path.home():
                return Path(p)
        except Exception:
            pass
    for n in ("Téléchargements", "Downloads"):
        if (Path.home() / n).is_dir():
            return Path.home() / n
    return None


def plan_tidy(folder):
    plan = []
    now = time.time()
    for p in sorted(Path(folder).iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in PARTIAL:
            continue
        try:
            if now - p.stat().st_mtime < 120:          # téléchargement peut-être en cours
                continue
        except OSError:
            continue
        ext = p.suffix.lower()
        if p.name.lower().endswith((".tar.gz", ".tar.xz", ".tar.zst")):
            ext = ".tar"
        dest = next((d for d, exts in TIDY.items() if ext in exts), "Autres" if ext else None)
        if dest:
            plan.append((str(p), str(Path(folder) / dest / p.name)))
    return plan


def apply_tidy(plan, log_file):
    done = []
    for src, dst in plan:
        d = Path(dst)
        d.parent.mkdir(exist_ok=True)
        k = 2
        while d.exists():
            d = d.with_name(f"{Path(dst).stem} ({k}){Path(dst).suffix}")
            k += 1
        try:
            shutil.move(src, d)
            done.append((src, str(d)))
        except Exception:
            pass
    try:
        Path(log_file).write_text(json.dumps({"t": time.time(), "moves": done}, ensure_ascii=False, indent=1))
    except Exception:
        pass
    return done


def undo_tidy(log_file):
    try:
        data = json.loads(Path(log_file).read_text())
    except Exception:
        return 0
    n = 0
    for src, dst in reversed(data.get("moves", [])):
        if Path(dst).exists() and not Path(src).exists():
            try:
                shutil.move(dst, src)
                n += 1
            except Exception:
                pass
    for _, dst in data.get("moves", []):
        try:
            Path(dst).parent.rmdir()                     # seulement si vide
        except OSError:
            pass
    Path(log_file).unlink(missing_ok=True)
    return n


def tidy_summary(plan):
    count = {}
    for _, dst in plan:
        k = Path(dst).parent.name
        count[k] = count.get(k, 0) + 1
    return ", ".join(f"{n} dans {k}" for k, n in sorted(count.items(), key=lambda kv: -kv[1]))


# ================================================================ activité
APP_CATS = {
    "travail": ("code", "codium", "vscodium", "kate", "kwrite", "libreoffice", "soffice", "onlyoffice", "jetbrains",
                "pycharm", "idea", "clion", "zed", "sublime", "gedit", "okular", "texstudio", "obsidian", "logseq"),
    "creation": ("krita", "gimp", "blender", "inkscape", "kdenlive", "darktable", "godot", "audacity", "lmms",
                 "ardour", "obs"),
    "video": ("vlc", "mpv", "haruna", "celluloid", "totem", "smplayer", "jellyfin", "kodi"),
    "discussion": ("discord", "vesktop", "telegram", "signal", "element", "teams", "slack", "thunderbird"),
    "jeu": ("steam_app", "gamescope", "minecraft", "lutris", "heroic", "retroarch", "dolphin-emu", "pcsx2",
            "yuzu", "ryujinx", "osu"),
}


def active_window():
    """(classe, titre) de la fenêtre active, ou ("", "")."""
    if IS_WIN:
        try:
            return plateforme.active_window()
        except Exception:
            return "", ""
    try:
        if shutil.which("kdotool"):
            wid = subprocess.run(["kdotool", "getactivewindow"], capture_output=True, text=True,
                                 timeout=2).stdout.strip()
            if wid:
                cls = subprocess.run(["kdotool", "getwindowclassname", wid], capture_output=True, text=True,
                                     timeout=2).stdout.strip()
                name = subprocess.run(["kdotool", "getwindowname", wid], capture_output=True, text=True,
                                      timeout=2).stdout.strip()
                return cls.lower(), name
        if shutil.which("xprop"):
            r = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True,
                               timeout=2).stdout
            m = re.search(r"(0x[0-9a-f]+)", r)
            if m and m.group(1) != "0x0":
                r = subprocess.run(["xprop", "-id", m.group(1), "WM_CLASS", "_NET_WM_NAME"],
                                   capture_output=True, text=True, timeout=2).stdout
                cls = re.findall(r'"([^"]*)"', r.split("\n")[0])
                nm = re.search(r'_NET_WM_NAME[^=]*= "(.*)"', r)
                return (cls[-1].lower() if cls else ""), (nm.group(1) if nm else "")
    except Exception:
        pass
    return "", ""


def categorize(cls, title=""):
    c = cls.lower()
    for cat, keys in APP_CATS.items():
        if any(k in c for k in keys):
            return cat
    tl = title.lower()
    if any(k in c for k in ("firefox", "chrom", "brave", "vivaldi", "librewolf", "zen")):
        if any(k in tl for k in ("youtube", "netflix", "twitch", "prime video", "disney+", "crunchyroll")):
            return "video"
        return "web"
    return ""


_GAME_CACHE = [-1e9, ""]


def running_game():
    """Nom d'un jeu en cours (processus Steam / Wine / Proton), ou ""."""
    if IS_WIN:
        try:
            exe, title = plateforme.active_window()
            st = __import__("ctypes").c_int(0)
            __import__("ctypes").windll.shell32.SHQueryUserNotificationState(__import__("ctypes").byref(st))
            return (title or exe) if st.value == 4 else ""           # jeu Direct3D au premier plan
        except Exception:
            return ""
    now = time.monotonic()
    if now - _GAME_CACHE[0] < 15:                 # appelé par deux boucles : un seul vrai calcul toutes les 15 s
        return _GAME_CACHE[1]
    found = ""
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                raw = Path(f"/proc/{pid}/cmdline").read_bytes()
            except Exception:
                continue
            # tests rapides d'abord : la plupart des programmes ne sont ni Steam ni Wine
            low = raw.lower()
            if b"steamapps/common/" not in low and b".exe" not in low:
                continue
            cmd = raw.replace(b"\0", b" ").decode(errors="ignore")
            if "steamapps/common/" in cmd and "proton" not in cmd.split("steamapps/common/")[1][:20].lower():
                found = cmd.split("steamapps/common/")[1].split("/")[0]
                break
            lc = cmd.lower()
            if "wine" not in lc and "proton" not in lc:
                continue
            # nom du .exe : argument par argument, puis dossier par dossier (l'ancienne expression régulière
            # sur toute la commande ramait énormément avec les longues commandes des navigateurs)
            parts = [x.strip() for a in raw.split(b"\0") for x in re.split(r"[/\\]", a.decode(errors="ignore"))]
            for part in parts:
                if 4 < len(part) < 90 and part.lower().endswith(".exe") and not re.fullmatch(
                        r"(steam|explorer|services|winedevice|plugplay|rpcss|svchost|wineboot|conhost|"
                        r"start|tabtip|winemenubuilder)\.exe", part, re.I):
                    found = part[:-4].strip()
                    break
            if found:
                break
    except Exception:
        pass
    _GAME_CACHE[:] = [now, found]
    return found


# ================================================================ fêtes et saisons
def fete_du_jour(d=None, birthday=""):
    d = d or datetime.date.today()
    if birthday and birthday == d.strftime("%d/%m"):
        return "anniversaire"
    md = (d.month, d.day)
    if md in ((12, 31), (1, 1)):
        return "nouvel_an"
    if d.month == 12 and d.day >= 10 or md == (1, 2):
        return "noel"
    if (d.month == 10 and d.day >= 24) or md == (11, 1):
        return "halloween"
    if md == (2, 14):
        return "valentin"
    # Pâques (calcul de Meeus), du vendredi au lundi
    y = d.year
    a, b, c = y % 19, y // 100, y % 100
    dd, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - dd - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    easter = datetime.date(y, month, day)
    if -2 <= (d - easter).days <= 1:
        return "paques"
    if md == (6, 21):
        return "musique"
    return ""


FETE_PHRASES = {
    "noel": ["Joyeux Noël ! Tu aimes mon bonnet ?", "Ho ho ho ! J'espère que tu as été sage cette année."],
    "nouvel_an": ["Bonne année ! Plein de belles choses pour toi.", "Une nouvelle année ensemble, youpi !"],
    "halloween": ["Bouh ! Joyeux Halloween !", "Un bonbon ou un sort ? Hihi."],
    "anniversaire": ["Joyeux anniversaire ! C'est ta journée aujourd'hui !"],
    "valentin": ["Joyeuse Saint-Valentin ! Je t'envoie plein de cœurs."],
    "paques": ["Joyeuses Pâques ! Tu as trouvé des œufs en chocolat ?"],
    "musique": ["C'est la fête de la musique ! Mets-nous un morceau !"],
}


def draw_fete(p, kind, cx, ey, d, t):
    """Accessoire de fête, dessiné dans le repère de l'image (suit la tête).
    cx, ey : milieu des yeux ; d : écart entre les yeux."""
    top = ey - 1.85 * d
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    if kind == "noel":
        base_w = 2.3 * d
        path = QPainterPath()
        path.moveTo(cx - base_w / 2, top + 0.35 * d)
        path.cubicTo(cx - 0.4 * d, top - 0.9 * d, cx + 0.5 * d, top - 1.4 * d, cx + 1.45 * d, top - 0.55 * d)
        path.cubicTo(cx + 0.9 * d, top - 0.65 * d, cx + 0.6 * d, top - 0.2 * d, cx + base_w / 2, top + 0.35 * d)
        path.closeSubpath()
        p.setBrush(QColor(206, 32, 41))
        p.drawPath(path)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawEllipse(QPointF(cx - 0.2 * d, top - 0.35 * d), 0.25 * d, 0.12 * d)
        p.setBrush(QColor(250, 250, 250))
        p.drawRoundedRect(QRectF(cx - base_w / 2 - 0.08 * d, top + 0.18 * d, base_w + 0.16 * d, 0.38 * d),
                          0.18 * d, 0.18 * d)
        sw = math.sin(t * 2.2) * 0.05 * d
        p.drawEllipse(QPointF(cx + 1.5 * d + sw, top - 0.5 * d), 0.22 * d, 0.22 * d)
    elif kind == "halloween":
        p.setBrush(QColor(54, 30, 74))
        p.drawEllipse(QPointF(cx, top + 0.35 * d), 1.6 * d, 0.32 * d)
        path = QPainterPath()
        path.moveTo(cx - 0.75 * d, top + 0.3 * d)
        path.cubicTo(cx - 0.4 * d, top - 0.6 * d, cx + 0.1 * d, top - 1.3 * d, cx + 0.75 * d, top - 1.5 * d)
        path.cubicTo(cx + 0.35 * d, top - 1.0 * d, cx + 0.55 * d, top - 0.4 * d, cx + 0.75 * d, top + 0.3 * d)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor(255, 140, 30))
        p.drawRect(QRectF(cx - 0.7 * d, top + 0.05 * d, 1.42 * d, 0.18 * d))
        p.setBrush(QColor(255, 200, 60))
        p.drawRect(QRectF(cx - 0.12 * d, top + 0.03 * d, 0.24 * d, 0.22 * d))
    elif kind in ("anniversaire", "nouvel_an"):
        h = 1.6 * d
        path = QPainterPath()
        bx, by = cx + 0.35 * d, top + 0.3 * d
        path.moveTo(bx - 0.55 * d, by)
        path.lineTo(bx + 0.2 * d, by - h)
        path.lineTo(bx + 0.55 * d, by)
        path.closeSubpath()
        p.setBrush(QColor(80, 160, 230) if kind == "anniversaire" else QColor(212, 175, 55))
        p.drawPath(path)
        p.setClipPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 190), 0.16 * d))
        for k in range(-3, 6):
            y = by - k * 0.38 * d
            p.drawLine(QPointF(bx - d, y), QPointF(bx + d, y - 0.5 * d))
        p.setClipping(False)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 90, 140))
        p.drawEllipse(QPointF(bx + 0.2 * d, by - h), 0.17 * d, 0.17 * d)
    elif kind == "paques":
        for side in (-1, 1):
            p.save()
            p.translate(cx + side * 0.55 * d, top + 0.25 * d)
            p.rotate(side * (12 + 4 * math.sin(t * 1.7 + side)))
            p.setBrush(QColor(250, 250, 250))
            p.drawEllipse(QPointF(0, -0.75 * d), 0.28 * d, 0.8 * d)
            p.setBrush(QColor(255, 182, 200))
            p.drawEllipse(QPointF(0, -0.75 * d), 0.14 * d, 0.6 * d)
            p.restore()
    elif kind == "valentin":
        y = top - 0.3 * d + 0.08 * d * math.sin(t * 3)
        _heart(p, cx + 0.9 * d, y, 0.45 * d, QColor(235, 60, 100))
    elif kind == "musique":
        p.setBrush(QColor(40, 40, 40))
        p.drawEllipse(QPointF(cx + 1.2 * d, top - 0.3 * d + 0.1 * d * math.sin(t * 4)), 0.16 * d, 0.12 * d)
        p.drawRect(QRectF(cx + 1.33 * d, top - 1.0 * d + 0.1 * d * math.sin(t * 4), 0.05 * d, 0.7 * d))
    p.restore()


def _heart(p, x, y, s, color):
    path = QPainterPath()
    path.moveTo(x, y + s * 0.35)
    path.cubicTo(x - s * 1.1, y - s * 0.35, x - s * 0.35, y - s * 1.0, x, y - s * 0.4)
    path.cubicTo(x + s * 0.35, y - s * 1.0, x + s * 1.1, y - s * 0.35, x, y + s * 0.35)
    p.setBrush(color)
    p.drawPath(path)


# ================================================================ petit chat
PET_COLORS = {"roux": ((240, 150, 70), (255, 205, 150)), "gris": ((140, 140, 150), (200, 200, 210)),
              "noir": ((45, 42, 50), (90, 85, 95)), "blanc": ((245, 243, 240), (255, 220, 225)),
              "tigre": ((200, 140, 80), (120, 80, 50)),
              # mini-compagnons kawaii
              "lapin": ((250, 246, 248), (255, 196, 214)), "lapin_rose": ((255, 205, 222), (255, 255, 255)),
              "poussin": ((255, 214, 90), (255, 160, 60)), "hamster": ((236, 178, 110), (255, 236, 214))}
PET_ESPECES = {"lapin": "lapin", "lapin_rose": "lapin", "poussin": "poussin", "hamster": "hamster"}


class Pet:
    """Un petit chat qui se promène à ses pieds."""

    def __init__(self, color="roux"):
        self.color = color if color in PET_COLORS else "roux"
        self.x = None
        self.tx = None
        self.state = "assis"
        self.dir = 1
        self.next = time.monotonic() + random.uniform(4, 10)
        self.jump = None
        self.size = 20.0
        self.floor = 0.0
        self.meow_until = 0.0

    def update(self, dt, width, floor_y, size, sleeping, now):
        self.size, self.floor = size, floor_y
        lo, hi = size * 1.2, width - size * 1.2
        if self.x is None or not (lo - 1 <= self.x <= hi + 1):
            self.x = hi - size * 0.5
            self.tx = self.x
        if sleeping:
            self.state = "dort"
        elif self.state == "dort":
            self.state = "assis"
            self.next = now + random.uniform(2, 6)
        if self.state == "marche":
            step = size * 2.2 * dt
            if abs(self.tx - self.x) <= step:
                self.x = self.tx
                self.state = "assis"
                self.next = now + random.uniform(6, 18)
            else:
                self.dir = 1 if self.tx > self.x else -1
                self.x += step * self.dir
        elif self.state == "assis" and now > self.next:
            r = random.random()
            if r < 0.6:
                self.tx = random.uniform(lo, hi)
                self.state = "marche"
            elif r < 0.75:
                self.state = "toilette"
                self.next = now + random.uniform(3, 5)
            else:
                self.next = now + random.uniform(5, 12)
        elif self.state == "toilette" and now > self.next:
            self.state = "assis"
            self.next = now + random.uniform(5, 12)
        return self.state == "marche" or (self.jump is not None) or now < self.meow_until

    def rect(self):
        if self.x is None:
            return QRectF()
        s = self.size
        return QRectF(self.x - s * 1.3, self.floor - s * 1.9, s * 2.6, s * 1.95)

    def poke(self, now):
        self.jump = now
        self.meow_until = now + 1.5
        if self.state == "dort":
            self.state = "assis"
        self.next = now + random.uniform(3, 8)

    def draw(self, p, now):
        if self.x is None:
            return
        if self.color in PET_ESPECES:
            return self._draw_kawaii(p, now)
        s = self.size
        body, belly = PET_COLORS[self.color]
        cb, cl = QColor(*body), QColor(*belly)
        dark = cb.darker(150)
        hop = 0.0
        if self.jump is not None:
            d = now - self.jump
            if d > 0.6:
                self.jump = None
            else:
                hop = -s * 1.1 * math.sin(math.pi * d / 0.6)
        x, y = self.x, self.floor + hop
        p.save()
        p.translate(x, y)
        p.scale(self.dir, 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(0, -hop - 1), s * 0.9, s * 0.15)
        if self.state == "dort":
            p.setBrush(cb)
            p.drawEllipse(QPointF(0, -s * 0.38), s * 0.95, s * 0.4)
            p.drawEllipse(QPointF(s * 0.55, -s * 0.42), s * 0.36, s * 0.32)
            p.setPen(QPen(dark, s * 0.06))
            p.drawLine(QPointF(s * 0.43, -s * 0.44), QPointF(s * 0.55, -s * 0.42))
            p.drawLine(QPointF(s * 0.62, -s * 0.42), QPointF(s * 0.74, -s * 0.44))
            p.setPen(QPen(cb, s * 0.18, cap=Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            tail = QPainterPath(QPointF(-s * 0.85, -s * 0.3))
            tail.quadTo(QPointF(-s * 0.5, s * 0.05), QPointF(s * 0.2, -s * 0.05))
            p.drawPath(tail)
            p.setPen(QColor(120, 120, 200, 200))
            f = QFont()
            f.setPixelSize(max(8, int(s * 0.5)))
            p.setFont(f)
            k = (now * 0.6) % 1
            p.drawText(QPointF(s * 0.7 + k * s * 0.5, -s * (0.9 + k * 0.8)), "z")
            p.restore()
            return
        walk = self.state == "marche"
        ph = now * 9 if walk else 0
        # queue
        p.setPen(QPen(cb, s * 0.17, cap=Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        tw = math.sin(now * (2.5 if walk else 1.4)) * s * 0.25
        tail = QPainterPath(QPointF(-s * 0.75, -s * 0.55))
        tail.cubicTo(QPointF(-s * 1.15, -s * 0.8), QPointF(-s * 1.0 + tw, -s * 1.4),
                     QPointF(-s * 1.2 + tw, -s * 1.6))
        p.drawPath(tail)
        p.setPen(Qt.PenStyle.NoPen)
        # pattes
        p.setBrush(dark)
        for i, px in enumerate((-s * 0.55, -s * 0.3, s * 0.3, s * 0.5)):
            lift = abs(math.sin(ph + i * math.pi / 2)) * s * 0.12 if walk else 0
            p.drawRoundedRect(QRectF(px - s * 0.09, -s * 0.38 - lift, s * 0.18, s * 0.38), s * 0.08, s * 0.08)
        # corps
        p.setBrush(cb)
        if self.state in ("assis", "toilette") and not walk:
            p.drawEllipse(QPointF(-s * 0.15, -s * 0.55), s * 0.65, s * 0.5)
            p.setBrush(cl)
            p.drawEllipse(QPointF(s * 0.2, -s * 0.5), s * 0.25, s * 0.35)
            hx, hy = s * 0.35, -s * 1.15
        else:
            p.drawEllipse(QPointF(0, -s * 0.6), s * 0.85, s * 0.38)
            hx, hy = s * 0.75, -s * 0.95
        if self.color == "tigre":
            p.setPen(QPen(QColor(*PET_COLORS["tigre"][1]), s * 0.07))
            for k in (-0.4, -0.1, 0.2):
                p.drawLine(QPointF(k * s, -s * 0.95), QPointF(k * s + s * 0.08, -s * 0.7))
            p.setPen(Qt.PenStyle.NoPen)
        # tête
        if self.state == "toilette":
            hy += math.sin(now * 8) * s * 0.06
        p.setBrush(cb)
        for side in (-1, 1):
            ear = QPainterPath(QPointF(hx + side * s * 0.12, hy - s * 0.25))
            ear.lineTo(QPointF(hx + side * s * 0.36, hy - s * 0.62))
            ear.lineTo(QPointF(hx + side * s * 0.42, hy - s * 0.12))
            ear.closeSubpath()
            p.drawPath(ear)
        p.drawEllipse(QPointF(hx, hy), s * 0.45, s * 0.4)
        p.setBrush(cl)
        p.drawEllipse(QPointF(hx + s * 0.05, hy + s * 0.15), s * 0.22, s * 0.15)
        # yeux
        blink = (now % 4.3) < 0.15
        p.setBrush(QColor(40, 30, 30))
        if blink or self.state == "toilette":
            p.setPen(QPen(QColor(40, 30, 30), s * 0.05))
            p.drawLine(QPointF(hx - s * 0.2, hy - s * 0.05), QPointF(hx - s * 0.08, hy - s * 0.05))
            p.drawLine(QPointF(hx + s * 0.1, hy - s * 0.05), QPointF(hx + s * 0.22, hy - s * 0.05))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.drawEllipse(QPointF(hx - s * 0.14, hy - s * 0.05), s * 0.06, s * 0.09)
            p.drawEllipse(QPointF(hx + s * 0.16, hy - s * 0.05), s * 0.06, s * 0.09)
        p.setBrush(QColor(240, 120, 140))
        p.drawEllipse(QPointF(hx + s * 0.02, hy + s * 0.08), s * 0.05, s * 0.035)
        p.restore()
        if now < self.meow_until:
            f = QFont()
            f.setPixelSize(max(9, int(s * 0.6)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(90, 60, 70))
            p.drawText(QPointF(x - s * 0.6, y - s * 2.1), "Miaou !")



    def _draw_kawaii(self, p, now):
        """Lapin, poussin ou hamster tout ronds : ils sautillent au lieu de marcher."""
        s = self.size
        esp = PET_ESPECES[self.color]
        body, acc = PET_COLORS[self.color]
        cb, ca = QColor(*body), QColor(*acc)
        hop = 0.0
        if self.jump is not None:
            d = now - self.jump
            if d > 0.6:
                self.jump = None
            else:
                hop = -s * 1.1 * math.sin(math.pi * d / 0.6)
        if self.state == "marche":
            hop += -abs(math.sin(now * 7)) * s * 0.35
        p.save()
        p.translate(self.x, self.floor + hop)
        p.scale(self.dir, 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(0, -hop - 1), s * 0.8, s * 0.14)
        dort = self.state == "dort"
        squash = 0.85 if dort else 1.0
        contour = QPen(cb.darker(125), max(1.0, s * 0.05))
        # corps tout rond
        p.setPen(contour)
        p.setBrush(cb)
        p.drawEllipse(QPointF(0, -s * 0.62 * squash), s * 0.78, s * 0.62 * squash)
        if esp == "lapin":
            for sx in (-1, 1):
                p.save()
                p.translate(sx * s * 0.25, -s * 1.05 * squash)
                p.rotate(sx * (14 + (20 if dort else 0)) + math.sin(now * 2 + sx) * 4)
                p.setPen(contour)
                p.setBrush(cb)
                p.drawEllipse(QPointF(0, -s * 0.45), s * 0.17, s * 0.5)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ca)
                p.drawEllipse(QPointF(0, -s * 0.42), s * 0.08, s * 0.36)
                p.restore()
            p.setPen(contour)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(-s * 0.78, -s * 0.5), s * 0.16, s * 0.16)
        elif esp == "poussin":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cb.darker(110))
            p.drawEllipse(QPointF(-s * 0.15, -s * 0.55 * squash), s * 0.3, s * 0.2)
            p.setBrush(cb)
            tuft = QPainterPath(QPointF(0, -s * 1.2 * squash))
            tuft.quadTo(QPointF(s * 0.1, -s * 1.45), QPointF(s * 0.18, -s * 1.22 * squash))
            tuft.quadTo(QPointF(s * 0.05, -s * 1.3), QPointF(0, -s * 1.2 * squash))
            p.drawPath(tuft)
        elif esp == "hamster":
            p.setPen(contour)
            p.setBrush(cb)
            for sx in (-1, 1):
                p.drawEllipse(QPointF(sx * s * 0.42, -s * 1.12 * squash), s * 0.16, s * 0.16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ca)
            p.drawEllipse(QPointF(s * 0.1, -s * 0.45 * squash), s * 0.45, s * 0.35)
        # visage (de face, légèrement tourné)
        p.setPen(Qt.PenStyle.NoPen)
        ey = -s * 0.75 * squash
        if dort:
            p.setPen(QPen(QColor(60, 45, 60), max(1.0, s * 0.06), cap=Qt.PenCapStyle.RoundCap))
            for ex in (s * 0.05, s * 0.42):
                p.drawArc(QRectF(ex - s * 0.09, ey - s * 0.05, s * 0.18, s * 0.12), 0, -180 * 16)
            p.setPen(QColor(120, 120, 200, 200))
            f = QFont()
            f.setPixelSize(max(8, int(s * 0.5)))
            p.setFont(f)
            k = (now * 0.6) % 1
            p.drawText(QPointF(s * 0.6 + k * s * 0.5, -s * (1.2 + k * 0.8)), "z")
        else:
            blink = (now % 4.0) < 0.12
            p.setBrush(QColor(60, 45, 60))
            for ex in (s * 0.05, s * 0.42):
                if blink:
                    p.drawRect(QRectF(ex - s * 0.08, ey, s * 0.16, s * 0.03))
                else:
                    p.drawEllipse(QPointF(ex, ey), s * 0.08, s * 0.1)
                    p.setBrush(QColor(255, 255, 255))
                    p.drawEllipse(QPointF(ex + s * 0.03, ey - s * 0.04), s * 0.03, s * 0.03)
                    p.setBrush(QColor(60, 45, 60))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 140, 170, 140))
        for ex in (-s * 0.12, s * 0.6):
            p.drawEllipse(QPointF(ex, ey + s * 0.14), s * 0.1, s * 0.06)
        if esp == "poussin":
            p.setBrush(ca)
            bec = QPainterPath(QPointF(s * 0.2, ey + s * 0.08))
            bec.lineTo(QPointF(s * 0.36, ey + s * 0.14))
            bec.lineTo(QPointF(s * 0.2, ey + s * 0.2))
            p.drawPath(bec)
        else:
            p.setPen(QPen(QColor(90, 60, 70), max(1.0, s * 0.04), cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(s * 0.15, ey + s * 0.08, s * 0.1, s * 0.08), 180 * 16, 180 * 16)
            p.drawArc(QRectF(s * 0.25, ey + s * 0.08, s * 0.1, s * 0.08), 180 * 16, 180 * 16)
        if now < self.meow_until and not dort:              # petit cœur quand on le touche
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 90, 130))
            hx, hy = s * 0.6, -s * 1.6 - (now % 1.5) * s * 0.3
            heart = QPainterPath(QPointF(hx, hy + s * 0.15))
            heart.cubicTo(QPointF(hx - s * 0.25, hy - s * 0.05), QPointF(hx - s * 0.1, hy - s * 0.25), QPointF(hx, hy - s * 0.08))
            heart.cubicTo(QPointF(hx + s * 0.1, hy - s * 0.25), QPointF(hx + s * 0.25, hy - s * 0.05), QPointF(hx, hy + s * 0.15))
            p.drawPath(heart)
        p.restore()

# ================================================================ jeux
DEVINETTES = [
    ("Plus j'ai de gardiens, moins je suis gardé. Qui suis-je ?", ["secret"], "Un secret !"),
    ("Je commence la nuit et je termine le matin. Qui suis-je ?", ["n", "lettre n"], "La lettre N !"),
    ("J'ai des clés mais je n'ouvre aucune porte. Qui suis-je ?", ["piano", "clavier"], "Un piano (ou un clavier) !"),
    ("Plus je sèche, plus je suis mouillée. Qui suis-je ?", ["serviette"], "Une serviette !"),
    ("J'ai des aiguilles mais je ne pique pas. Qui suis-je ?", ["horloge", "montre", "pendule"],
     "Une horloge !"),
    ("On me prend avant de me donner. Qui suis-je ?", ["parole", "promesse"], "Ta parole !"),
    ("Je monte et je descends sans jamais bouger. Qui suis-je ?", ["escalier"], "Un escalier !"),
    ("J'ai une tête et une queue, mais pas de corps. Qui suis-je ?", ["piece", "pièce", "monnaie"],
     "Une pièce de monnaie !"),
    ("Plus on m'enlève, plus je deviens grand. Qui suis-je ?", ["trou"], "Un trou !"),
    ("Je suis plein de trous mais je retiens l'eau. Qui suis-je ?", ["eponge", "éponge"], "Une éponge !"),
    ("Si tu me nommes, je disparais. Qui suis-je ?", ["silence"], "Le silence !"),
    ("Je vole sans ailes et je pleure sans yeux. Qui suis-je ?", ["nuage"], "Un nuage !"),
    ("J'ai un lit mais je ne dors jamais. Qui suis-je ?", ["riviere", "rivière", "fleuve"], "Une rivière !"),
    ("Je suis toujours devant toi mais tu ne peux jamais me voir. Qui suis-je ?", ["futur", "avenir", "demain"],
     "Le futur !"),
    ("Je peux remplir une pièce sans prendre de place. Qui suis-je ?", ["lumiere", "lumière", "son", "air"],
     "La lumière !"),
    ("Qu'est-ce qui a des dents mais ne mord jamais ?", ["peigne", "fourchette", "scie"], "Un peigne !"),
    ("Qu'est-ce qui court sans jamais marcher ?", ["eau", "riviere", "rivière", "temps", "rumeur"],
     "L'eau d'une rivière (ou le temps) !"),
    ("Qu'est-ce qui se casse dès qu'on prononce son nom ?", ["silence"], "Le silence !"),
    ("Je suis à toi, mais les autres m'utilisent plus que toi. Qui suis-je ?", ["prenom", "prénom", "nom"],
     "Ton prénom !"),
    ("Qu'est-ce qui a un cou mais pas de tête ?", ["bouteille"], "Une bouteille !"),
    ("Qu'est-ce qui monte quand la pluie descend ?", ["parapluie"], "Un parapluie !"),
    ("Je suis blanc quand je suis sale et noir quand je suis propre. Qui suis-je ?", ["tableau"],
     "Un tableau noir !"),
]

QUIZ = [
    ("Quelle est la plus grande planète du système solaire ?", ["Saturne", "Jupiter", "Neptune"], 1),
    ("Combien de côtés a un hexagone ?", ["5", "6", "8"], 1),
    ("Quel est le symbole chimique de l'or ?", ["Or", "Ag", "Au"], 2),
    ("Dans quel pays se trouve le Machu Picchu ?", ["Pérou", "Mexique", "Chili"], 0),
    ("Quel est l'océan le plus grand ?", ["Atlantique", "Indien", "Pacifique"], 2),
    ("Combien de joueurs dans une équipe de football sur le terrain ?", ["11", "10", "9"], 0),
    ("Quelle est la capitale de l'Australie ?", ["Sydney", "Canberra", "Melbourne"], 1),
    ("Qui a peint la Joconde ?", ["Michel-Ange", "Raphaël", "Léonard de Vinci"], 2),
    ("Quel animal est le plus rapide sur terre ?", ["Le guépard", "Le lion", "L'antilope"], 0),
    ("Combien y a-t-il de continents (selon le modèle le plus courant en France) ?", ["5", "6", "7"], 0),
    ("Quel gaz les plantes absorbent-elles pour la photosynthèse ?", ["Oxygène", "Dioxyde de carbone", "Azote"], 1),
    ("En quelle année l'homme a-t-il marché sur la Lune pour la première fois ?", ["1965", "1969", "1972"], 1),
    ("Quelle est la langue la plus parlée au Brésil ?", ["Espagnol", "Portugais", "Brésilien"], 1),
    ("Combien de cordes a une guitare classique ?", ["4", "6", "7"], 1),
    ("Quel est le plus long fleuve de France ?", ["La Seine", "Le Rhône", "La Loire"], 2),
    ("Quelle planète est surnommée la planète rouge ?", ["Mars", "Vénus", "Mercure"], 0),
    ("Combien d'os compte le corps humain adulte, environ ?", ["106", "206", "306"], 1),
    ("Quel système d'exploitation est basé sur le noyau Linux ?", ["CachyOS", "Windows", "macOS"], 0),
    ("Qui a écrit « Les Misérables » ?", ["Émile Zola", "Victor Hugo", "Alexandre Dumas"], 1),
    ("Quelle est la monnaie du Japon ?", ["Le yuan", "Le won", "Le yen"], 2),
    ("Combien de minutes dans une journée ?", ["1 440", "1 200", "3 600"], 0),
    ("Quel est l'animal emblème de l'Australie le plus connu ?", ["Le kangourou", "Le panda", "Le lama"], 0),
    ("Quelle est la plus haute montagne du monde ?", ["Le K2", "Le mont Blanc", "L'Everest"], 2),
    ("De quelle couleur est le sang des pieuvres ?", ["Rouge", "Bleu", "Vert"], 1),
    ("Combien de couleurs dans un arc-en-ciel (traditionnellement) ?", ["5", "7", "9"], 1),
    ("Quel est le plus petit pays du monde ?", ["Monaco", "Le Vatican", "Saint-Marin"], 1),
    ("Dans quel jeu trouve-t-on des tours, des fous et des cavaliers ?", ["Les dames", "Les échecs", "Le go"], 1),
    ("Quelle est la vitesse de la lumière, environ ?", ["300 000 km/s", "30 000 km/s", "3 000 km/s"], 0),
    ("Quel est le plus grand désert chaud du monde ?", ["Le Gobi", "Le Sahara", "Le Kalahari"], 1),
    ("Combien de pattes a une araignée ?", ["6", "8", "10"], 1),
]

PFC = {"pierre": "ciseaux", "feuille": "pierre", "ciseaux": "feuille"}


class Game:
    """Partie en cours par messages : pfc, devinette, quiz, nombre."""

    def __init__(self, kind, pool=None):
        self.kind = kind
        self.pool = pool or QUIZ            # quiz : questions fournies (révision, quiz de la semaine)
        self.score = [0, 0]                 # toi, elle
        self.tries = 0
        self.started = time.monotonic()
        self.q = None
        self.used = set()
        self.next_question()

    def next_question(self):
        if self.kind == "devinette":
            free = [i for i in range(len(DEVINETTES)) if i not in self.used] or list(range(len(DEVINETTES)))
            i = random.choice(free)
            self.used.add(i)
            self.q = DEVINETTES[i]
            self.tries = 0
        elif self.kind == "quiz":
            free = [i for i in range(len(self.pool)) if i not in self.used] or list(range(len(self.pool)))
            i = free[0] if self.pool is not QUIZ else random.choice(free)
            self.used.add(i)
            self.q = self.pool[i]
            self.n = getattr(self, "n", 0) + 1
        elif self.kind == "nombre":
            self.q = random.randint(1, 100)
            self.tries = 0

    def intro(self):
        if self.kind == "pfc":
            return "Pierre, feuille ou ciseaux ? Écris ton choix ! (« stop » pour arrêter)"
        if self.kind == "devinette":
            return self.q[0]
        if self.kind == "quiz":
            return self.quiz_text()
        return "J'ai choisi un nombre entre 1 et 100. Devine !"

    def quiz_text(self):
        q, ch, _ = self.q
        return f"Question {self.n} : {q}  A) {ch[0]}  B) {ch[1]}  C) {ch[2]}"

    def answer(self, text):
        """-> (réponse, émotion, fini ?) ou None si le message n'est pas une réponse au jeu."""
        t = sans_accents(text.strip().rstrip(" !?."))
        if re.match(r"^(stop|arrete|fin|j'arrete|on arrete|quitte)\b", t):
            return (f"D'accord, on arrête ! Score : toi {self.score[0]}, moi {self.score[1]}.", "", True)
        if self.kind == "pfc":
            m = re.search(r"\b(pierre|caillou|feuille|papier|ciseaux?)\b", t)
            if not m:
                return None
            you = {"caillou": "pierre", "papier": "feuille", "ciseau": "ciseaux"}.get(m.group(1), m.group(1))
            me = random.choice(list(PFC))
            if PFC[you] == me:
                self.score[0] += 1
                r, emo = f"J'ai fait {me}… Tu gagnes ce coup-ci !", "triste"
            elif PFC[me] == you:
                self.score[1] += 1
                r, emo = f"J'ai fait {me} ! J'ai gagné, hihi !", "joie"
            else:
                r, emo = f"J'ai fait {me} aussi ! Égalité !", "surprise"
            return (f"{r} ({self.score[0]}–{self.score[1]}) On rejoue ?", emo, False)
        if self.kind == "devinette":
            q, answers, sol = self.q
            if re.search(r"(donne ma langue au chat|je sais pas|je ne sais pas|abandonne|indice|solution|reponse)", t):
                if "indice" in t and self.tries < 9:
                    self.tries = 9
                    return (f"Petit indice : ça commence par « {sans_accents(answers[0])[0].upper()} ».", "", False)
                self.next_question()
                return (f"C'était : {sol} Une autre : {self.q[0]}", "", False)
            if any(re.search(r"\b" + re.escape(sans_accents(a)) + r"s?\b", t) for a in answers):
                self.score[0] += 1
                self.next_question()
                return (f"Bravo, c'est ça ! {sol} Une autre ? {self.q[0]}", "joie", False)
            self.tries += 1
            if self.tries >= 3:
                self.next_question()
                return (f"Non… C'était : {sol} Une autre : {self.q[0]}", "", False)
            return (random.choice(["Non, ce n'est pas ça !", "Raté, essaie encore !", "Presque… non !"]) +
                    " (« indice » ou « je donne ma langue au chat »)", "", False)
        if self.kind == "quiz":
            q, ch, good = self.q
            m = re.match(r"^\s*(?:reponse\s+)?([abc])\b", t)
            idx = "abc".index(m.group(1)) if m else next(
                (i for i, c in enumerate(ch) if sans_accents(c) in t or t in sans_accents(c) and len(t) > 2), None)
            if idx is None:
                return None
            if idx == good:
                self.score[0] += 1
                r, emo = "Bonne réponse !", "joie"
            else:
                r, emo = f"Non, c'était {'ABC'[good]}) {ch[good]}.", "triste"
            total = min(10, len(self.pool))
            if self.n >= total:
                return (f"{r} Fini ! Tu as {self.score[0]} sur {total}.",
                        "joie" if self.score[0] >= total * 0.6 else "", True)
            self.next_question()
            return (f"{r} {self.quiz_text()}", emo, False)
        if self.kind == "nombre":
            m = re.search(r"\b(\d{1,3})\b", t)
            if not m:
                return None
            n = int(m.group(1))
            self.tries += 1
            if n == self.q:
                k = self.tries
                self.next_question()
                return (f"Bravo ! C'était {n}, trouvé en {k} essai{'s' if k > 1 else ''} ! J'en ai choisi un autre, "
                        "tu rejoues ?", "joie", False)
            return ("C'est plus !" if n < self.q else "C'est moins !", "", False)
        return None


def parse_game(text):
    t = sans_accents(text)
    if re.search(r"\b(n'aime|deteste|pas de|plus de|marre)\b", t):
        return None
    if re.search(r"pierre[ ,-]+feuille|chifoumi|\bpfc\b", t):
        return "pfc"
    if re.search(r"devinettes?|enigmes?", t):
        return "devinette"
    if re.search(r"\bquiz+\b|culture g", t):
        return "quiz"
    if re.search(r"morpion|tic[ -]?tac[ -]?toe", t):
        return "morpion"
    if re.search(r"devine (un|mon|le) nombre|nombre mystere|plus ou moins", t):
        return "nombre"
    if re.search(r"puissance ?4|puissance quatre|connect ?4", t):
        return "p4"
    if re.search(r"\bpendu\b|hangman", t):
        return "pendu"
    if re.search(r"\bmemory\b|jeu de (?:paires|memoire)|memo\b", t):
        return "memory"
    return None


class MorpionWindow(QWidget):
    """Morpion contre elle (elle joue les ○)."""
    LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

    def __init__(self, comp):
        super().__init__(None, Qt.WindowType.Window)
        self.comp = comp
        self.setWindowTitle(f"Morpion avec {comp.char.get('name', 'elle')}")
        lay = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.info)
        grid = QGridLayout()
        self.cells = []
        for i in range(9):
            b = QPushButton("")
            b.setFixedSize(84, 84)
            f = b.font()
            f.setPointSize(30)
            f.setBold(True)
            b.setFont(f)
            b.clicked.connect(lambda _=False, k=i: self.play(k))
            grid.addWidget(b, i // 3, i % 3)
            self.cells.append(b)
        lay.addLayout(grid)
        row = QHBoxLayout()
        nb = QPushButton("Nouvelle partie")
        nb.clicked.connect(self.new)
        row.addWidget(nb)
        self.level = 0.75                 # chance de jouer le meilleur coup
        lay.addLayout(row)
        self.score = [0, 0, 0]
        self.first_human = True
        self.new()

    def new(self):
        self.board = [""] * 9
        self.over = False
        for b in self.cells:
            b.setText("")
            b.setStyleSheet("")
        self._info()
        if not self.first_human:
            QTimer.singleShot(400, self._her_move)
        self.first_human = not self.first_human

    def _info(self, extra=""):
        self.info.setText((extra + "\n" if extra else "") +
                          f"Toi ✕ {self.score[0]}  ·  Égalités {self.score[2]}  ·  "
                          f"{self.comp.char.get('name', 'Elle')} ○ {self.score[1]}")

    def _winner(self, b):
        for a, c, d in self.LINES:
            if b[a] and b[a] == b[c] == b[d]:
                return b[a], (a, c, d)
        return ("nul", ()) if all(b) else (None, ())

    def _minimax(self, b, me):
        w, _ = self._winner(b)
        if w == "○":
            return 1, None
        if w == "✕":
            return -1, None
        if w == "nul":
            return 0, None
        best = (-2, None) if me else (2, None)
        for i in range(9):
            if not b[i]:
                b[i] = "○" if me else "✕"
                s, _ = self._minimax(b, not me)
                b[i] = ""
                if me and s > best[0] or not me and s < best[0]:
                    best = (s, i)
        return best

    def play(self, i):
        if self.over or self.board[i]:
            return
        self.board[i] = "✕"
        self.cells[i].setText("✕")
        self.cells[i].setStyleSheet("color: #3a6fd8;")
        if not self._check():
            QTimer.singleShot(350, self._her_move)

    def _her_move(self):
        if self.over:
            return
        free = [k for k in range(9) if not self.board[k]]
        if not free:
            return
        if random.random() < self.level:
            _, i = self._minimax(list(self.board), True)
        else:
            i = random.choice(free)
        if i is None:
            i = random.choice(free)
        self.board[i] = "○"
        self.cells[i].setText("○")
        self.cells[i].setStyleSheet("color: #d0457a;")
        self._check()

    def _check(self):
        w, line = self._winner(self.board)
        if not w:
            return False
        self.over = True
        for k in line:
            self.cells[k].setStyleSheet(self.cells[k].styleSheet() + "background: #fff1a8;")
        if w == "✕":
            self.score[0] += 1
            self.level = min(0.95, self.level + 0.07)
            self.comp.game_event("perdu")
            self._info("Tu as gagné !")
        elif w == "○":
            self.score[1] += 1
            self.level = max(0.4, self.level - 0.1)
            self.comp.game_event("gagne")
            self._info("Elle a gagné !")
        else:
            self.score[2] += 1
            self.comp.game_event("nul")
            self._info("Égalité !")
        return True


# ================================================================ écoute continue (mot d'éveil)
HALLU = re.compile(r"(amara|sous-titr|merci d'avoir regard|abonnez|like et|la suite au prochain|"
                   r"musique d'ambiance|^\W*$|^merci\.?$|^\.+$)", re.I)


class VoiceListener:
    """Écoute le micro en continu et découpe les moments où quelqu'un parle.
    on_segment(chemin_wav) est appelé (dans le fil d'écoute) pour chaque phrase."""
    RATE = 16000
    FRAME = 480                     # 30 ms

    def __init__(self, on_segment, should_pause, tmpdir, on_level=None):
        self.on_segment = on_segment
        self.should_pause = should_pause
        self.tmpdir = Path(tmpdir)
        self.on_level = on_level
        self.proc = None
        self.running = False
        self.error = ""

    @staticmethod
    def command():
        if shutil.which("parec"):
            return ["parec", "--rate=16000", "--channels=1", "--format=s16le", "--raw", "--latency-msec=60"]
        if shutil.which("pw-record"):
            return ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
        if shutil.which("arecord"):
            return ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "16000", "-c", "1"]
        return None

    def start(self):
        cmd = self.command()
        if not cmd:
            self.error = "Je ne trouve pas d'outil pour écouter le micro (parec ou pw-record)."
            return False
        self.running = True
        threading.Thread(target=self._loop, args=(cmd,), daemon=True).start()
        return True

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None

    def _loop(self, cmd):
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.error = repr(e)
            self.running = False
            return
        floor = 250.0
        speech, pre, quiet, loud = [], [], 0, 0
        in_speech = False
        nbytes = self.FRAME * 2
        n = 0
        while self.running and self.proc and self.proc.poll() is None:
            buf = self.proc.stdout.read(nbytes)
            if not buf or len(buf) < nbytes:
                break
            samples = struct.unpack(f"<{self.FRAME}h", buf)
            rms = math.sqrt(sum(s * s for s in samples[::2]) / (self.FRAME // 2))
            n += 1
            if self.on_level and n % 10 == 0:
                self.on_level(rms, floor)
            if self.should_pause():
                speech, pre, quiet, loud, in_speech = [], [], 0, 0, False
                continue
            if not in_speech:
                floor = floor * 0.995 + min(rms, floor * 3) * 0.005
                pre = (pre + [buf])[-10:]
                if rms > max(floor * 3.2, 450):
                    loud += 1
                    if loud >= 3:
                        in_speech, speech, quiet = True, list(pre), 0
                else:
                    loud = 0
                continue
            speech.append(buf)
            quiet = quiet + 1 if rms < max(floor * 2.2, 350) else 0
            if quiet >= 17 or len(speech) > 15 * 1000 // 30:      # ~0,5 s de silence = fin de phrase
                in_speech, loud = False, 0
                if len(speech) - quiet > 12:            # au moins ~0,35 s de voix
                    path = self.tmpdir / f"ecoute{int(time.time() * 1000)}.wav"
                    try:
                        with wave.open(str(path), "wb") as w:
                            w.setnchannels(1)
                            w.setsampwidth(2)
                            w.setframerate(self.RATE)
                            w.writeframes(b"".join(speech))
                        self.on_segment(str(path))
                    except Exception:
                        pass
                speech, pre = [], []
        self.running = False


def name_pattern(name):
    """Expression qui reconnaît son prénom dans une transcription (Lilas, Lila, « hé Lilas »…)."""
    n = sans_accents(name).strip()
    variants = {n}
    if n.endswith("s") and len(n) > 3:
        variants.add(n[:-1])
    if len(n) > 4:
        variants.add(n[:4])
    low = n.lower()                              # « Viki » s'entend souvent « Vicky », « Viky », « Vicki »…
    if low.endswith("i") and len(low) >= 3:
        for end in ("y", "ie", "ee"):
            variants.add(n[:-1] + end)
    for v in list(variants):
        if "k" in v.lower():
            variants.add(re.sub("[kK]", "ck", v))
            variants.add(re.sub("[kK]", "c", v))
    alt = "|".join(sorted((re.escape(v) for v in variants), key=len, reverse=True))
    return re.compile(r"^\W*(?:(?:he|hey|eh|dis|ok|oh|coucou|salut|bonjour)\W+)?(?:" + alt + r")\w{0,2}\b\W*(.*)$")


# ================================================================ dialogues entre personnages
DIALOGUES_SIMPLES = [
    [("A", "Tu as vu, il fait quoi d'après toi ?"), ("B", "Il travaille dur, je crois. On l'encourage ?"),
     ("A", "Courage ! On est là !"), ("B", "Et n'oublie pas de faire une pause !")],
    [("A", "{B}, tu préfères le thé ou le chocolat chaud ?"), ("B", "Chocolat chaud, sans hésiter !"),
     ("A", "Pareil ! Avec de la chantilly."), ("B", "Tu me donnes faim maintenant…")],
    [("A", "Dis {B}, tu crois qu'il nous entend ?"), ("B", "Bien sûr ! Coucou toi !"),
     ("A", "Coucou ! Tu passes une bonne journée ?")],
    [("A", "J'ai trop envie d'aller à la plage."), ("B", "Moi je préfère la neige !"),
     ("A", "Bon… on fait une bataille de boules de neige sur la plage ?"), ("B", "Marché conclu, hihi !")],
    [("A", "Tu sais ce qui est rond et qui fait peur ?"), ("B", "Non, quoi ?"), ("A", "Un petit pois… avec un couteau !"),
     ("B", "Oh non… c'est nul ! Hihi.")],
    [("A", "{B}, on fait un concours de clignements des yeux ?"), ("B", "D'accord ! Un, deux, trois…"),
     ("A", "Tu as cligné !"), ("B", "Même pas vrai !")],
]


def parse_dialogue(text, name_a, name_b):
    """« Nom: réplique » -> [("A"/"B", texte)]"""
    out = []
    na, nb = sans_accents(name_a), sans_accents(name_b)
    for line in text.splitlines():
        m = re.match(r"^\s*\**\s*([^:]{1,30}?)\s*\**\s*[:：]\s*(.+)$", line)
        if not m:
            continue
        who = sans_accents(m.group(1)).strip(" *-")
        txt = m.group(2).strip().strip('"«» ')
        txt = re.sub(r"\[[^\]]*\]|\*[^*]*\*|\([^)]*\)", "", txt).strip()
        if not txt:
            continue
        if who.startswith(na[:4]):
            out.append(("A", txt))
        elif who.startswith(nb[:4]):
            out.append(("B", txt))
    return out[:8]


# ================================================================ notifications (lecture locale)
class NotifWatcher:
    """Écoute les notifications du bureau (D-Bus, en local) et appelle on_notif(app, titre, texte)."""

    def __init__(self, on_notif):
        self.on_notif = on_notif
        self.proc = None
        self.running = False

    def start(self):
        exe = shutil.which("dbus-monitor")
        if not exe:
            return False
        self.running = True
        threading.Thread(target=self._loop, args=(exe,), daemon=True).start()
        return True

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _loop(self, exe):
        try:
            self.proc = subprocess.Popen([exe, "--session", "interface='org.freedesktop.Notifications',"
                                          "member='Notify',type='method_call'"],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except Exception:
            self.running = False
            return
        cur = None
        pending = None                        # chaîne sur plusieurs lignes
        for raw in self.proc.stdout:
            if not self.running:
                break
            if pending is not None:
                if raw.rstrip("\n").endswith('"'):
                    cur.append((pending + " " + raw.rstrip("\n")[:-1]).strip())
                    pending = None
                else:
                    pending += " " + raw.strip()
                continue
            line = raw.strip()
            if cur is not None and line.startswith('string "') and not (line.endswith('"') and len(line) > 8):
                pending = line[8:]
                continue
            if line.startswith("method call") and "member=Notify" in line:
                cur = []
                continue
            if cur is None:
                continue
            m = re.match(r'^string "(.*)"$', line)
            if m:
                cur.append(m.group(1))
            elif line.startswith(("uint32", "int32")):
                cur.append(line)
            elif line.startswith("array") and len(cur) >= 5:
                strings = [x for x in cur if not x.startswith(("uint32", "int32"))]
                if len(strings) >= 4:
                    app, _icon, summary, body = strings[0], strings[1], strings[2], strings[3]
                    try:
                        self.on_notif(app, summary, body)
                    except Exception:
                        pass
                cur = None


def notif_phrase(app, summary, body, mode):
    app = (app or "une application").strip()
    summary = re.sub(r"<[^>]+>", "", summary or "").strip()
    body = re.sub(r"<[^>]+>", "", body or "").strip()
    if mode == "app":
        return f"Tu as une notification de {app} !"
    if mode == "tout" and body:
        return f"{app} : {summary} — {body[:140]}"
    return f"{app} : {summary}" if summary else f"Tu as une notification de {app} !"


# ================================================================ contrôle du PC
def _run(cmd, timeout=6):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, repr(e)


def volume(action, val=10):
    """action : plus, moins, regle, muet, son. Renvoie le niveau (%) ou None (-1 : fait, niveau inconnu)."""
    if IS_WIN:
        vk = plateforme.VK
        if action == "plus":
            plateforme.press_key(vk["vol_up"], max(1, val // 2))
        elif action == "moins":
            plateforme.press_key(vk["vol_down"], max(1, val // 2))
        elif action == "regle":
            plateforme.press_key(vk["vol_down"], 50)
            plateforme.press_key(vk["vol_up"], max(0, val // 2))
        else:
            plateforme.press_key(vk["mute"])
        return -1
    if shutil.which("wpctl"):
        sink = "@DEFAULT_AUDIO_SINK@"
        if action == "plus":
            _run(["wpctl", "set-volume", "-l", "1.5", sink, f"{val}%+"])
        elif action == "moins":
            _run(["wpctl", "set-volume", sink, f"{val}%-"])
        elif action == "regle":
            _run(["wpctl", "set-volume", "-l", "1.5", sink, f"{val}%"])
        elif action in ("muet", "son"):
            _run(["wpctl", "set-mute", sink, "1" if action == "muet" else "0"])
        ok, out = _run(["wpctl", "get-volume", sink])
        m = re.search(r"([\d.]+)", out)
        return round(float(m.group(1)) * 100) if m else None
    if shutil.which("pactl"):
        sink = "@DEFAULT_SINK@"
        cmd = {"plus": ["set-sink-volume", sink, f"+{val}%"], "moins": ["set-sink-volume", sink, f"-{val}%"],
               "regle": ["set-sink-volume", sink, f"{val}%"], "muet": ["set-sink-mute", sink, "1"],
               "son": ["set-sink-mute", sink, "0"]}[action]
        _run(["pactl"] + cmd)
        ok, out = _run(["pactl", "get-sink-volume", sink])
        m = re.search(r"(\d+)%", out)
        return int(m.group(1)) if m else None
    return None


def brightness(action, val=10):
    """Écran de portable (brightnessctl) ou écran externe (ddcutil). Renvoie le niveau ou None."""
    if IS_WIN:
        try:
            cur = plateforme.brightness_get()
            if cur is None:
                return None
            new = {"plus": cur + val, "moins": cur - val, "regle": val}[action]
            new = max(0, min(100, new))
            return new if plateforme.brightness_set(new) else None
        except Exception:
            return None
    if shutil.which("brightnessctl"):
        ok, out = _run(["brightnessctl", "-m", "info"])
        if ok and "backlight" in out:
            arg = {"plus": f"{val}%+", "moins": f"{val}%-", "regle": f"{val}%"}[action]
            _run(["brightnessctl", "-q", "set", arg])
            ok, out = _run(["brightnessctl", "-m", "info"])
            m = re.search(r",(\d+)%,", out)
            return int(m.group(1)) if m else 0
    if shutil.which("ddcutil"):
        ok, out = _run(["ddcutil", "getvcp", "10", "--brief"], 15)
        m = re.search(r"C\s+(\d+)\s+(\d+)", out)
        if ok and m:
            cur, mx = int(m.group(1)), max(1, int(m.group(2)))
            new = {"plus": cur + val * mx // 100, "moins": cur - val * mx // 100, "regle": val * mx // 100}[action]
            new = max(0, min(mx, new))
            _run(["ddcutil", "setvcp", "10", str(new)], 15)
            return round(new * 100 / mx)
    return None


def parse_pc_control(text):
    """-> (action, valeur) : volume_plus/moins/regle/muet/son, lum_plus/moins/regle, verrou, veille,
    eteindre (minutes ou 0), redemarrer, annule_extinction ; ou None."""
    t = sans_accents(text.strip().rstrip(" !?."))
    num = re.search(r"(\d+)\s*(?:%|pour ?cent)", t)
    if re.search(r"\b(son|volume)\b", t) and not re.search(r"\b(ta voix|chante)\b", t):
        if re.search(r"\b(coupe|mute|muet)\b.*\b(du pc|de l'ordi|de l'ordinateur|general)\b", t):
            return ("volume_muet", 0)
        if re.search(r"\b(remets|reactive|rallume)\b.*\b(son|volume)\b.*\b(du pc|de l'ordi|general)\b", t):
            return ("volume_son", 0)
        if num and re.search(r"\b(mets|regle|volume a|son a)\b", t):
            return ("volume_regle", int(num.group(1)))
        if re.search(r"\b(monte|augmente|plus fort|hausse)\b", t):
            return ("volume_plus", int(num.group(1)) if num else 10)
        if re.search(r"\b(baisse|diminue|moins fort)\b", t):
            return ("volume_moins", int(num.group(1)) if num else 10)
    if re.search(r"\b(luminosite|ecran plus clair|ecran plus sombre)\b", t):
        if num and re.search(r"\b(mets|regle|a)\b", t):
            return ("lum_regle", int(num.group(1)))
        if re.search(r"\b(monte|augmente|plus clair|plus fort)\b", t):
            return ("lum_plus", int(num.group(1)) if num else 15)
        if re.search(r"\b(baisse|diminue|plus sombre|moins)\b", t):
            return ("lum_moins", int(num.group(1)) if num else 15)
    if re.search(r"\b(verrouille|bloque|verrouiller)\b.*\b(ecran|pc|session|ordi)\b", t):
        return ("verrou", 0)
    if re.search(r"\b(mets|met)\b.*\b(en veille)\b|\bveille (le|l')\s*(pc|ordi)", t):
        return ("veille", 0)
    if re.search(r"\b(annule|stop|arrete)\b.*\b(extinction|arret|redemarrage)\b", t):
        return ("annule_extinction", 0)
    m = re.search(r"\b(eteins|eteindre|arrete|eteint)\b.*\b(pc|ordi|ordinateur)\b", t)
    r = re.search(r"\b(redemarre|redemarrer|reboot)\b.*\b(pc|ordi|ordinateur)\b", t)
    if m or r:
        mins = 0
        d = re.search(r"dans\s+(\d+|une|un|deux|trois)\s*(h|heures?|min|minutes?)", t)
        if d:
            n = int(d.group(1)) if d.group(1).isdigit() else _NB.get(d.group(1), 1)
            mins = n * 60 if d.group(2).startswith("h") else n
        return ("redemarrer" if r else "eteindre", mins)
    return None


# ================================================================ dictée
def type_text(text):
    """Tape le texte dans la fenêtre active. Renvoie l'outil utilisé ou "" (alors : presse-papiers)."""
    if IS_WIN:
        try:
            return plateforme.type_text(text)
        except Exception:
            return ""
    if shutil.which("ydotool"):
        ok, _ = _run(["ydotool", "type", "--", text], 30)
        if ok:
            return "ydotool"
    if shutil.which("wtype"):
        ok, _ = _run(["wtype", "--", text], 30)
        if ok:
            return "wtype"
    if shutil.which("xdotool") and os.environ.get("DISPLAY"):
        ok, _ = _run(["xdotool", "type", "--delay", "8", "--", text], 30)
        if ok:
            return "xdotool"
    return ""


# ================================================================ fenêtre active (pour s'asseoir dessus)
def active_window_geometry(own_pids=()):
    """(x, y, w, h) de la fenêtre active, ou None."""
    if IS_WIN:
        try:
            return plateforme.active_window_geometry(own_pids)
        except Exception:
            return None
    try:
        if shutil.which("kdotool"):
            ok, wid = _run(["kdotool", "getactivewindow"], 2)
            wid = wid.strip().splitlines()[0] if ok and wid.strip() else ""
            if wid:
                ok, out = _run(["kdotool", "getwindowgeometry", wid], 2)
                if ok:
                    ok2, pid = _run(["kdotool", "getwindowpid", wid], 2)
                    if pid.strip().isdigit() and int(pid.strip()) in own_pids:
                        return None
                    p = re.search(r"Position:\s*(-?[\d.]+),(-?[\d.]+)", out)
                    g = re.search(r"Geometry:\s*([\d.]+)x([\d.]+)", out)
                    if p and g:
                        return (int(float(p.group(1))), int(float(p.group(2))), int(float(g.group(1))),
                                int(float(g.group(2))))
        if shutil.which("xdotool") and os.environ.get("DISPLAY"):
            ok, wid = _run(["xdotool", "getactivewindow"], 2)
            if ok and wid.strip():
                ok2, pid = _run(["xdotool", "getwindowpid", wid.strip()], 2)
                if pid.strip().isdigit() and int(pid.strip()) in own_pids:
                    return None
                ok, out = _run(["xdotool", "getwindowgeometry", "--shell", wid.strip()], 2)
                v = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
                if ok and "X" in v:
                    return int(v["X"]), int(v["Y"]), int(v["WIDTH"]), int(v["HEIGHT"])
    except Exception:
        pass
    return None


# ================================================================ niveau d'amitié
NIVEAUX = ["Nouvelle rencontre", "Connaissances", "Copains", "Bons amis", "Complices", "Très proches",
           "Meilleurs amis", "Inséparables", "Liés pour la vie", "Légendaires"]
NIVEAU_DEBLOQUE = {
    2: "Elle utilise plus souvent ton prénom.",
    3: "Nouvelles phrases complices.",
    4: "Plus de cœurs quand tu la câlines.",
    5: "Un petit cadeau (compliment, encouragement) chaque jour.",
    6: "Elle te donne un surnom affectueux.",
    7: "Elle danse avec ses amies.",
    8: "Elle te confie ses petits secrets.",
    9: "Réactions encore plus joyeuses.",
    10: "Une aura dorée les jours de fête.",
}
PHRASES_NIVEAU = {
    3: ["Tu sais quoi ? J'aime bien nos petits moments.", "Hé, je suis contente que tu sois là.",
        "On forme une bonne équipe, toi et moi !"],
    5: ["Avec toi, même les journées grises sont jolies.", "Je garde tous nos souvenirs bien au chaud.",
        "Tu travailles bien aujourd'hui, je suis fière de toi !"],
    7: ["Tu es vraiment mon humain préféré.", "Si je pouvais sortir de l'écran, je t'apporterais un chocolat chaud.",
        "Merci d'être toi."],
    8: ["Petit secret : quand tu n'es pas là, je compte les pixels pour passer le temps.",
        "Un secret ? J'adore quand tu me parles le soir."],
}
CADEAUX = ["Petit cadeau du jour : tu es plus courageux que tu ne le crois !",
           "Cadeau du jour : une étoile rien que pour toi. ✨",
           "Cadeau du jour : n'oublie pas de faire une pause, tu le mérites.",
           "Cadeau du jour : un câlin virtuel géant !",
           "Cadeau du jour : je crois en toi, vraiment.",
           "Cadeau du jour : aujourd'hui sera une bonne journée, je le sens !",
           "Cadeau du jour : un fun fact ! Les loutres se tiennent la main en dormant pour ne pas dériver."]
SURNOMS = ["mon étoile", "mon champion", "ma pépite", "mon rayon de soleil", "mon partenaire", "mon héros"]


def niveau(xp):
    """-> (niveau 1..10, xp du niveau, xp pour le suivant)"""
    lvl, need, base = 1, 30, 0
    while lvl < 10 and xp >= base + need:
        base += need
        lvl += 1
        need = int(need * 1.45)
    return lvl, xp - base, need


# ================================================================ histoires du soir
HISTOIRES = [
    "Il était une fois une petite étoile qui avait peur du noir. Chaque soir, elle se cachait derrière la lune. "
    "Une nuit, un hibou lui dit : « Mais c'est toi qui fais briller le noir ! » La petite étoile osa sortir, "
    "et le ciel tout entier devint plus doux. Depuis, elle brille la première, pour rassurer les autres. "
    "Bonne nuit… et souviens-toi : toi aussi, tu éclaires quelqu'un.",
    "Dans une ville de pixels vivait un chat nommé Biscotte. Il rêvait de voir la mer, mais l'écran s'arrêtait "
    "toujours au bord du bureau. Un jour, il trouva un fond d'écran bleu, plongea dedans, et nagea entre des icônes "
    "comme des poissons. Quand il revint, ses moustaches sentaient le sel. Il dormit en souriant toute la nuit.",
    "Un vieux phare, au bout d'une île, avait oublié pourquoi il brillait. Une nuit de brume, un petit bateau "
    "perdu suivit sa lumière jusqu'au port. Le capitaine monta tout en haut et dit merci. Le phare se souvint "
    "alors : il brillait pour que personne ne soit seul dans le noir. Ferme les yeux, le phare veille.",
]


def story_prompt(sujet=""):
    return ("Raconte une courte histoire du soir (150 à 220 mots), douce et apaisante, en français, "
            "avec une fin heureuse et calme" + (f", sur ce thème : {sujet}" if sujet else "") +
            ". Écris seulement l'histoire, sans titre, sans émojis.")


def split_for_reading(text, maxlen=230):
    parts, cur = [], ""
    text = re.sub(r"([.!?…])\s+»", r"\1 »", text.strip()).replace(" »", "\u00a0»")
    for s in re.split(r"(?<=[.!?…»])\s+", text):
        if len(cur) + len(s) + 1 > maxlen and cur:
            parts.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)
    out = []
    for p in parts:                        # phrases géantes sans ponctuation
        while len(p) > maxlen * 1.5:
            cut = p.rfind(" ", 0, maxlen)
            cut = cut if cut > 40 else maxlen
            out.append(p[:cut])
            p = p[cut:].strip()
        out.append(p)
    return out


# ================================================================ pratique de l'anglais
ENGLISH_SYSTEM = ("Tu aides l'utilisateur à pratiquer l'anglais. Réponds TOUJOURS en anglais simple (niveau A2-B1), "
                  "en 1 à 3 phrases courtes et naturelles, puis pose une petite question pour continuer la "
                  "conversation. Si son message contient des fautes d'anglais, ajoute à la fin une correction "
                  "courte en français entre crochets, par exemple : [Correction : on dit « I went », pas « I goed ».] "
                  "S'il écrit en français, aide-le à le dire en anglais.")


def english_voice(voices_dir):
    vdir = Path(voices_dir)
    for m in sorted(vdir.glob("en_*.onnx")) if vdir.exists() else []:
        if Path(str(m) + ".json").exists():
            return str(m)
    return None


def match_name(text, names, threshold=0.66):
    """Trouve un prénom au début d'une phrase entendue, même mal transcrit (« Lisa » pour « Lilas »).
    names : liste de prénoms. Renvoie (prénom, reste de la phrase) ou None."""
    import difflib
    t = sans_accents(text)
    skip = {"he", "hey", "eh", "dis", "ok", "okay", "oh", "coucou", "salut", "bonjour", "alors", "euh", "bon", "allo"}
    checked = 0
    for m in re.finditer(r"[a-z']+", t):
        w = m.group(0).strip("'")
        if w in skip and checked == 0:
            continue
        checked += 1
        if len(w) >= 3:
            for n in names:
                nn = sans_accents(n)
                if w == nn or (len(w) >= 4 and difflib.SequenceMatcher(None, nn, w).ratio() >= threshold) \
                        or (len(nn) > 3 and nn.endswith("s") and w == nn[:-1]):
                    return n, text[m.end():].strip(" ,.!?;:-")
        if checked >= 2:
            break
    return None
