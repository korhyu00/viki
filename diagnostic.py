"""Diagnostic des disques, en mots simples : état (SMART via UDisks, sans mot de passe), place libre,
et test de lecture d'un fichier. Rien ne sort du PC."""
import os
import time
from pathlib import Path

import gestionpc

FS_OK = {"ext4", "ext3", "ext2", "btrfs", "xfs", "f2fs", "ntfs", "ntfs3", "fuseblk", "vfat", "exfat", "zfs", "bcachefs"}


def human(n):
    return gestionpc.human(n)


def volumes():
    """Les partitions montées : [{point, type, total, libre, pct}]."""
    out, seen = [], set()
    try:
        lines = open("/proc/mounts").read().splitlines()
    except Exception:
        return out
    for line in lines:
        p = line.split()
        if len(p) < 3 or p[2] not in FS_OK or p[0] in seen:
            continue
        mp = p[1].replace("\\040", " ")
        if mp.startswith(("/boot", "/snap", "/var/lib/docker", "/run/")) and not mp.startswith("/run/media"):
            continue
        try:
            st = os.statvfs(mp)
            tot, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        except Exception:
            continue
        if tot < (1 << 30):
            continue
        seen.add(p[0])
        out.append({"point": mp, "type": p[2], "total": tot, "libre": free, "pct": round(100 * (1 - free / tot))})
    return out


def juge(d):
    """Un disque de gestionpc.disks_health() -> (niveau, titre, explication, quoi faire). niveau : ok/surveiller/danger/inconnu."""
    det = " ".join(d.get("details", []))
    if not d.get("support"):
        return ("inconnu", "Pas d'information", "Ce disque ne donne pas son état de santé (fréquent pour les clés USB "
                "et certains boîtiers externes).", "Rien à faire. S'il devient lent ou fait des erreurs, remplace-le.")
    if "panne prochaine" in det or "alerte critique" in det:
        return ("danger", "En danger", "Le disque annonce lui-même qu'il va bientôt tomber en panne.",
                "Copie tout de suite tes fichiers importants sur un autre disque, puis remplace celui-ci. "
                "N'y installe plus rien.")
    if "secteur" in det:
        return ("danger" if "rouge" in det else "surveiller", "Abîmé par endroits",
                "Des petites zones du disque ne se lisent plus (« secteurs abîmés »). Les fichiers écrits à ces "
                "endroits peuvent être illisibles : c'est ce qui donne les « erreurs d'entrée/sortie ».",
                "Sauvegarde tes fichiers importants sur un autre disque. Si le nombre de secteurs abîmés augmente "
                "de semaine en semaine, remplace le disque.")
    if "rouge" in det:
        return ("surveiller", "À surveiller", "Un des indicateurs de santé du disque est mauvais.",
                "Fais une sauvegarde de tes fichiers importants et regarde si ça empire.")
    return ("ok", "En bonne santé", "Le disque ne signale aucun problème.", "")


def rapport():
    """Tout le diagnostic. -> {"disques": [...] ou None, "volumes": [...], "heure": ...}"""
    h = gestionpc.disks_health()
    disques = None
    if h is not None:
        disques = []
        for d in h:
            niv, titre, quoi, faire = juge(d)
            disques.append(dict(d, niveau=niv, titre=titre, explication=quoi, faire=faire))
    return {"disques": disques, "volumes": volumes(), "heure": time.strftime("%H:%M:%S")}


def test_fichier(path, st):
    """Lit tout le fichier pour voir si le disque arrive à le rendre. -> (ok, phrase)."""
    p = Path(path)
    size = max(1, p.stat().st_size)
    done, bad, t0 = 0, [], time.monotonic()
    with open(p, "rb", buffering=0) as f:
        while done < size:
            if st.get("stop"):
                return None, "Test annulé."
            try:
                b = f.read(4 << 20)
                if not b:
                    break
                done += len(b)
            except OSError:
                bad.append(done)
                done += 4 << 20
                try:
                    f.seek(done)
                except OSError:
                    break
                if len(bad) > 20:
                    break
            st["pct"] = int(100 * min(done, size) / size)
    if bad:
        return False, (f"❌ Le disque n'arrive pas à lire ce fichier à {len(bad)} endroit{'s' if len(bad) > 1 else ''} "
                       f"(le premier vers {human(bad[0])} sur {human(size)}). Le fichier est abîmé à cause du disque : "
                       "supprime-le et retélécharge-le. S'il était sur ce disque depuis longtemps, c'est le signe que "
                       "le disque fatigue.")
    v = size / max(0.01, time.monotonic() - t0)
    return True, f"✅ Le fichier se lit en entier, sans erreur ({human(size)}, {human(v)}/s)."


COUL = {"ok": "#2e9c55", "surveiller": "#d98a1e", "danger": "#d0403a", "inconnu": "#7a7a86"}
ICO = {"ok": "✅", "surveiller": "🟠", "danger": "🔴", "inconnu": "❔"}


def _T(t):
    try:
        import i18n
        return i18n.tr(t)
    except Exception:
        return t


def html(rap):
    T = _T
    out = []
    ds = rap["disques"]
    if ds is None:
        out.append("<p>❔ " + T("Je n'arrive pas à interroger les disques.") + " <!-- -->" if False else "<p>❔ Je n'arrive pas à interroger les disques : il me faut le service <b>UDisks</b> "
                   "(installé d'office avec KDE et GNOME).</p>")
    elif not ds:
        out.append("<p>Je ne trouve aucun disque.</p>")
    for d in ds or []:
        c = COUL[d["niveau"]]
        infos = " · ".join(T(x) for x in d["details"]) or T("aucun détail")
        out.append(f"<div style='margin:0 0 14px 0'><span style='font-size:13pt'><b>{ICO[d['niveau']]} {d['nom']}</b> "
                   f"({human(d['taille'])})</span><br><b style='color:{c}'>{T(d['titre'])}</b> — {T(d['explication'])}"
                   + (f"<br><b>{T('Que faire :')}</b> {T(d['faire'])}" if d["faire"] else "")
                   + f"<br><span style='color:gray'>{T('Mesures :')} {infos}</span></div>")
    vs = rap["volumes"]
    if vs:
        out.append(T("<p><b>Place sur tes disques</b></p>"))
        for v in vs:
            c = COUL["danger"] if v["pct"] >= 95 else COUL["surveiller"] if v["pct"] >= 85 else COUL["ok"]
            nom = T("Système") if v["point"] == "/" else T("Dossier perso") if v["point"] == str(Path.home()) \
                else Path(v["point"]).name or v["point"]
            mot = T("presque plein !" if v["pct"] >= 95 else "bien rempli" if v["pct"] >= 85 else "ça va")
            out.append(f"<div>💾 <b>{nom}</b> — {human(v['libre'])} {T('libres sur')} {human(v['total'])} · "
                       f"<b style='color:{c}'>{v['pct']} % · {mot}</b></div>")
    out.append("<p style='color:gray'>" + T(f"Mis à jour à {rap['heure']} · rien n'est envoyé sur internet.") + "</p>")
    return "".join(out)


def make_window(comp):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                                 QTextBrowser, QVBoxLayout)

    class Win(QDialog):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Diagnostic des disques")
            self.resize(620, 520)
            L = QVBoxLayout(self)
            t = QLabel("<b style='font-size:14pt'>💽 Diagnostic des disques</b><br>L'état de chaque disque, en clair, "
                       "mis à jour tout seul.")
            t.setWordWrap(True)
            L.addWidget(t)
            self.view = QTextBrowser()
            self.view.setHtml("<p>🔎 Je regarde tes disques…</p>")
            L.addWidget(self.view, 1)
            self.res = QLabel("")
            self.res.setWordWrap(True)
            L.addWidget(self.res)
            self.bar = QProgressBar()
            self.bar.setVisible(False)
            L.addWidget(self.bar)
            h = QHBoxLayout()
            self.b_test = QPushButton("🔬 Tester un fichier…")
            self.b_test.setToolTip("Je lis le fichier en entier pour voir si le disque arrive à le rendre "
                                   "(utile après une « erreur d'entrée/sortie »).")
            self.b_test.clicked.connect(self.test)
            self.b_stop = QPushButton("Arrêter")
            self.b_stop.setVisible(False)
            self.b_stop.clicked.connect(lambda: self.st.__setitem__("stop", True))
            b = QPushButton("Fermer")
            b.clicked.connect(self.close)
            h.addWidget(self.b_test)
            h.addWidget(self.b_stop)
            h.addStretch(1)
            h.addWidget(b)
            L.addLayout(h)
            self.st, self.busy, self.last = {}, False, None
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.tick = QTimer(self)
            self.tick.timeout.connect(lambda: self.bar.setValue(int(self.st.get("pct", 0))))

        def showEvent(self, e):
            super().showEvent(e)
            self.refresh()
            self.timer.start(5000)

        def hideEvent(self, e):
            super().hideEvent(e)
            self.timer.stop()

        def refresh(self):
            if self.busy or not self.isVisible():
                return
            self.busy = True

            def done(r):
                self.busy = False
                if isinstance(r, Exception):
                    return self.view.setHtml(f"<p>❌ {r}</p>")
                self.last = r
                pos = self.view.verticalScrollBar().value()
                self.view.setHtml(html(r))
                self.view.verticalScrollBar().setValue(pos)
            comp._bg(rapport, done)

        def test(self, path=None):
            if not path:
                path, _ = QFileDialog.getOpenFileName(self, "Quel fichier tester ?", str(Path.home()))
            if not path:
                return
            self.st = st = {"pct": 0, "stop": False}
            self.res.setText(f"🔬 Je lis « {Path(path).name} » en entier…")
            self.bar.setValue(0)
            self.bar.setVisible(True)
            self.b_stop.setVisible(True)
            self.b_test.setEnabled(False)
            self.tick.start(200)

            def done(r):
                self.tick.stop()
                self.bar.setVisible(False)
                self.b_stop.setVisible(False)
                self.b_test.setEnabled(True)
                self.res.setText(f"❌ {r}" if isinstance(r, Exception) else r[1])
            comp._bg(lambda: test_fichier(path, st), done)
    return Win()


if os.name == "nt":                                       # Windows : les lecteurs (C:, D:, clés USB…)
    def volumes():
        import shutil
        try:
            import windows_outils as _W
            lettres = _W.lecteurs((2, 3))
        except Exception:
            lettres = ["C:\\"]
        out = []
        for d in lettres:
            try:
                u = shutil.disk_usage(d)
            except Exception:
                continue
            if u.total < (1 << 30):
                continue
            out.append({"point": d, "type": "ntfs", "total": u.total, "libre": u.free,
                        "pct": round(100 * (1 - u.free / u.total))})
        return out
