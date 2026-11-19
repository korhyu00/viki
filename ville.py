"""Choisir sa ville pour la météo : une recherche claire avec des suggestions (Open-Meteo, gratuit, sans compte).
Seul le nom tapé part en ligne, et seulement quand on tape dans ce champ. Pas de GPS, pas de position."""
import json
import threading
import urllib.request
from urllib.parse import quote

from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QLabel

try:
    from i18n import tr, lang as _lang
except Exception:                                          # pragma: no cover
    def tr(t):
        return t

    def _lang():
        return "fr"


def chercher(nom, langue="fr", n=6):
    """-> [{"nom", "lat", "lon", "label"}] (peut lever une exception si pas d'internet)."""
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=%d&language=%s&name=%s"
           % (n, quote(langue or "fr"), quote(nom)))
    with urllib.request.urlopen(url, timeout=8) as r:
        res = json.load(r).get("results") or []
    out = []
    for x in res:
        morceaux = [x.get("name", "")] + [x.get(k) for k in ("admin1", "country") if x.get(k)]
        vus = []
        for m in morceaux:
            if m and m not in vus:
                vus.append(m)
        out.append({"nom": x.get("name", ""), "lat": x.get("latitude"), "lon": x.get("longitude"),
                    "label": ", ".join(vus)})
    return out


class _Sig(QObject):
    fini = pyqtSignal(int, object)


def choisir(parent, cfg):
    """Ouvre la fenêtre ; -> dict choisi (nom, lat, lon, label) ou None."""
    from actu_fenetre import Boite
    actuel = cfg.get("meteo_lieu") or cfg.get("meteo_ville") or ""
    texte = tr("Tape le nom de ta ville, puis choisis-la dans la liste.") + "\n" + \
        tr("Seul ce nom est envoyé à Open-Meteo pour trouver la météo. Pas de GPS, rien d'autre.")
    if actuel:
        texte = tr("Ville actuelle :") + " " + actuel + "\n\n" + texte
    b = Boite(parent, tr("📍 Ta ville pour la météo"), texte,
              [(tr("Annuler"), None, "non"), (tr("Choisir"), "ok", "oui")], "📍")
    champ = QLineEdit()
    champ.setPlaceholderText(tr("Lyon, Montréal, Bruxelles…"))
    champ.setClearButtonEnabled(True)
    liste = QListWidget()
    liste.setMinimumHeight(170)
    liste.setStyleSheet("QListWidget { background: #2a2731; color: #ece9f2; border: 1px solid #3a3644; "
                        "border-radius: 10px; padding: 4px; font-size: 13px; outline: none; }"
                        "QListWidget::item { padding: 7px 8px; border-radius: 7px; }"
                        "QListWidget::item:selected { background: #7F77DD; color: #ffffff; }"
                        "QListWidget::item:hover:!selected { background: #36323f; }")
    etat = QLabel("")
    etat.setObjectName("champ")
    b.ajouter_champ("Ville", champ)
    lay = champ.parentWidget().layout()
    lay.insertWidget(lay.count() - 1, liste)
    lay.insertWidget(lay.count() - 1, etat)
    sig = _Sig(b)
    gen = {"n": 0, "res": []}

    def remplir(n, res):
        if n != gen["n"]:
            return
        liste.clear()
        if isinstance(res, Exception):
            etat.setText(tr("Je n'arrive pas à chercher : es-tu connecté à internet ?"))
            return
        gen["res"] = res
        if not res:
            etat.setText(tr("Aucune ville trouvée. Essaie une autre orthographe."))
            return
        etat.setText("")
        for i, x in enumerate(res):
            it = QListWidgetItem("📍  " + x["label"])
            it.setData(Qt.ItemDataRole.UserRole, i)
            liste.addItem(it)
        liste.setCurrentRow(0)
    sig.fini.connect(remplir)

    def lancer():
        txt = champ.text().strip()
        if len(txt) < 2:
            liste.clear()
            etat.setText("")
            return
        gen["n"] += 1
        n = gen["n"]
        etat.setText(tr("Je cherche…"))
        lg = (_lang() or "fr")[:2]

        def work():
            try:
                r = chercher(txt, lg)
            except Exception as e:
                r = e
            sig.fini.emit(n, r)
        threading.Thread(target=work, daemon=True).start()

    t = QTimer(b)
    t.setSingleShot(True)
    t.setInterval(450)
    t.timeout.connect(lancer)
    champ.textEdited.connect(lambda _t: t.start())
    champ.returnPressed.connect(lambda: liste.count() and b._fin("ok"))
    liste.itemDoubleClicked.connect(lambda _it: b._fin("ok"))
    champ.setFocus()
    b.resize(520, 440)
    b.exec()
    if b.valeur != "ok":
        return None
    it = liste.currentItem()
    if it is None:
        return None
    return gen["res"][it.data(Qt.ItemDataRole.UserRole)]
