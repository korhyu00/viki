"""Menu court avec recherche, accueil en tuiles et barre de raccourcis à côté du personnage.
Toutes les actions viennent d'un seul registre : actions(comp) -> [{id, ico, nom, cat, fn, mots}]."""
import re
import unicodedata

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget, QWidgetAction, QFrame)

CATS = [("parler", "💬", "Parler avec elle"), ("jour", "☀️", "Mon quotidien"), ("media", "🎬", "Musique et vidéos"),
        ("creer", "🎨", "Créer"), ("pc", "💻", "Travail et PC"), ("elle", "💜", "Elle")]
DEFAUT = ["ecrire", "actu", "liste", "musique", "images", "pomodoro"]


def _sa(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def actions(c):
    """Le registre. Chaque entrée n'apparaît que si la fonction existe dans cette version de Viki."""
    C = __import__("sys").modules[type(c).__module__]
    has = lambda name: callable(getattr(c, name, None))
    A = []

    def add(id_, ico, nom, cat, fn, mots="", ok=True):
        if ok and fn:
            A.append({"id": id_, "ico": ico, "nom": nom, "cat": cat, "fn": fn, "mots": mots})

    # parler
    add("ecrire", "✏️", "Lui écrire", "parler", c.open_input, "ecrire taper message question")
    add("micro", "🎙️", "Lui parler au micro", "parler", c.toggle_mic, "voix micro parler oral")
    add("discuter", "💬", "Discuter avec elle", "parler", getattr(c, "ask_chat", None), "chat discussion conversation ia")
    if hasattr(c, "is_muted") and c.is_muted():
        add("muette", "🔊", "Réactiver sa voix", "parler", lambda: c.set_mute(0),
            "son voix reactiver parler muet silence chut reparler")
    else:
        add("muette", "🔇", "Muette 1 heure", "parler", lambda: c.set_mute(60), "silence muet calme chut")
    add("jouer", "🎮", "Jouer avec elle", "parler", lambda: QTimer.singleShot(0, c.play_menu), "jeu jeux jouer")
    # quotidien
    add("actu", "📰", "Lis-moi l'actu", "jour", lambda: c.tell_news(""), "actualite news infos nouvelles",
        ok=has("tell_news"))
    add("suivis", "🔔", "Actus et suivis", "jour", getattr(c, "open_follow", None), "sites series sorties cine suivi")
    add("apprendre", "💡", "Apprends-moi un truc", "jour", getattr(c, "teach_fact", None), "savoir culture fait")
    add("blague", "😄", "Une blague", "jour", getattr(c, "tell_joke", None), "rire drole humour")
    add("repas", "🍽️", "Idée de repas", "jour", getattr(c, "suggest_meal", None), "manger cuisine recette diner")
    add("cuisine", "📅", "Repas de la semaine", "jour", (lambda: c.open_cuisine(None, 1)) if has("open_cuisine") else None,
        "planning menu semaine courses recettes cuisine")
    add("dessin", "🎨", "Carnet de dessin", "jour", getattr(c, "open_dessin", None),
        "dessin dessiner peindre crayon perso personnage croquis")
    add("autour", "📍", "Restos et lieux autour de moi", "jour",
        (lambda: c.nearby({"kind": "restaurant", "cuisine": None, "near": ""})) if has("nearby") else None,
        "resto restaurant manger cafe bar carte autour proche pres pharmacie boulangerie supermarche plan")
    add("sport", "🏃", "Pause sport", "jour", getattr(c, "suggest_sport", None), "exercice bouger etirement")
    add("notes", "📝", "Mes notes", "jour", lambda: c.open_notes("notes"), "note memo pense-bete", ok=has("open_notes"))
    add("courses", "🛒", "Liste de courses", "jour", lambda: c.open_notes("courses"), "courses acheter magasin",
        ok=has("open_notes"))
    add("journal", "📔", "Mon journal", "jour", getattr(c, "show_journal", None), "journal journee humeur")
    add("copies", "📋", "Ce que j'ai copié", "jour", getattr(c, "open_clip_history", None), "presse-papiers copie coller")
    add("souvenirs", "💜", "Nos souvenirs", "jour", getattr(c, "show_memories", None), "souvenir memoire")
    add("lecture", "📖", "Mode lecture", "jour", (lambda: c.open_reader()) if has("open_reader") and C.lecture else None,
        "livre lire ebook")
    add("mails", "📧", "Mes mails", "jour", (lambda: c.mail_check(read=False)) if getattr(C, "mails", None) else None,
        "mail courrier email")
    # média
    add("liste", "📺", "Ma liste (séries, films…)", "media", getattr(c, "open_liste", None),
        "serie film regarder reprendre episode anime netflix crunchyroll")
    add("musique", "🎵", "Mets de la musique", "media",
        (lambda: c.music_request({"q": "", "chaine": False, "focus": False, "dernier": False}))
        if has("music_request") else None, "musique chanson ecouter youtube son")
    add("routine", "🌅", "Ma routine (matin / soir)", "jour", getattr(c, "open_routine", None),
        "routine matin soir habitudes checklist")
    add("sante", "💧", "Pauses santé (eau, yeux, étirements)", "jour", getattr(c, "open_sante", None),
        "eau boire yeux etirements sante pause")
    add("planning", "🗓️", "Ma semaine (planning)", "jour", getattr(c, "open_planning", None),
        "planning semaine agenda organiser")
    add("muscu", "💪", "Muscu à la maison", "jour", getattr(c, "open_muscu", None),
        "muscu sport seance entrainement workout abdos squats")
    add("services", "🍿", "Netflix, Disney+, Prime Video, Spotify, Deezer…", "media",
        getattr(c, "menu_services", None), "netflix disney prime crunchyroll spotify deezer twitch canal film serie")
    add("service", "🎧", "Où écouter ma musique (YouTube, Spotify, Deezer…)", "media",
        (lambda: c.choisir_service_musique()) if has("choisir_service_musique") else None,
        "spotify deezer youtube music service appli ecouter")
    add("concentration", "🎧", "Musique pour me concentrer", "media", (lambda: c.play_music("dev"))
        if has("play_music") and C.vie else None, "concentration focus travail lofi")
    add("manga", "📚", "Traduire un manga", "media", (lambda: c.open_manga()) if has("open_manga") and C.manga else None,
        "manga traduire scan bd")
    # créer
    add("images", "🖼️", "Atelier d'images", "creer", getattr(c, "image_dialog", None), "image dessin generer photo art")
    add("studio", "🎼", "Studio musique", "creer", getattr(c, "open_music_studio", None),
        "composer chanson creer musique paroles")
    add("pomodoro", "🍅", "Pomodoro 25 min", "pc", lambda: c.start_pomodoro(25, "travail"), "minuteur travail focus timer")
    add("fichier", "📥", "Donne-moi un fichier", "pc", getattr(c, "open_drop_window", None), "fichier glisser deposer")
    add("ranger", "🗂️", "Ranger mes téléchargements", "pc", getattr(c, "tidy_downloads", None), "ranger trier dossier")
    add("vieprivee", "🛡️", "Vie privée et sécurité", "pc", (lambda: c.open_privacy(0)) if hasattr(c, "open_privacy") else None,
        "vie privee securite tor vpn dns proxy navigateur ports pare-feu sauvegarde chiffree anonymat")
    add("ports", "🔌", "Ports ouverts", "pc", (lambda: c.open_privacy(1)) if hasattr(c, "open_privacy") else None,
        "ports ouverts redirection upnp box reseau")
    add("securite", "🛡️", "Vérifier la sécurité du PC", "pc", getattr(c, "security_check", None),
        "securite virus pirate protection")
    add("erreur", "🐞", "Expliquer l'erreur copiée", "pc", getattr(c, "explain_error", None), "erreur bug code debug")
    add("snippets", "💾", "Mes snippets", "pc", getattr(c, "show_snippets", None), "code snippet bout de code")
    add("todo", "📌", "TODO du projet", "pc", getattr(c, "code_todos", None), "todo fixme projet code")
    add("revue", "🔍", "Relire mon code", "pc", getattr(c, "code_review", None), "commit revue diff git")
    add("sauvegarde", "💽", "Sauvegarder tout", "pc", getattr(c, "backup_all", None), "sauvegarde backup")
    # elle
    add("perso", "🎭", "Personnages", "elle", getattr(c, "open_gallery", None), "personnage avatar changer")
    add("apparence", "👗", "Mon apparence", "elle", getattr(c, "open_look", None),
        "apparence look couleur cheveux peau yeux pull jupe collants chaussures vetements tenue habiller style")
    add("sieste", "😴", "Faire une sieste", "elle", getattr(c, "nap", None), "dormir sieste pause")
    add("dis", "🗨️", "Dis-moi quelque chose", "elle", lambda: c.say_from("spontanees"), "parle phrase")
    add("reglages", "⚙️", "Réglages", "elle", c.open_settings, "parametres options configuration")
    add("accueil", "🏠", "Accueil (mes raccourcis)", "elle", lambda: open_home(c), "accueil raccourcis tuiles")
    add("cerveau", "🧠", "Ce qu'elle sait de moi", "elle", (lambda: c.open_brain(0)) if getattr(c, "brain", None) else None,
        "souvenirs memoire habitudes commandes perso journee apprendre")
    add("journee", "📅", "Ma journée", "jour", (lambda: c.open_brain(3)) if getattr(c, "brain", None) else None,
        "journee resume bilan aujourd'hui temps")
    add("astuces", "💡", "Trucs et astuces", "elle", getattr(c, "open_tips", None),
        "aide astuce help mots-cles commandes comment utiliser")
    add("trad_sel", "🌍", "Traduire la sélection", "jour", getattr(c, "translate_selection", None),
        "traduire traduction selection texte langue anglais")
    add("lire_sel", "🔊", "Lire la sélection", "jour", getattr(c, "read_selection", None),
        "lire voix haute selection texte page lecture")
    add("lire_doc", "📄", "Lire un document", "jour", (lambda: c.read_pdf()) if hasattr(c, "read_pdf") else None,
        "lire pdf document voix haute livre")
    add("ecran", "🖥️", "Décris mon écran", "pc", (lambda: c.describe_screen()) if hasattr(c, "describe_screen") else None,
        "ecran capture regarder vision voir analyse")
    add("agenda_web", "🗓️", "Ajouter un agenda en ligne", "jour",
        (lambda: c.add_web_calendar()) if hasattr(c, "add_web_calendar") else None,
        "agenda calendrier google nextcloud outlook ical rendez-vous")
    add("jeux", "🎮", "Mes stats de jeu", "elle", (lambda: c.say(c.game_stats_text())) if getattr(c, "games", None) else None,
        "jeux stats temps de jeu steam gaming")
    add("neige", "❄️", "Faire neiger", "elle", (lambda: c.set_overlay("noel")) if hasattr(c, "set_overlay") else None,
        "neige effet saison noel hiver confettis")
    add("assistant", "🪄", "Assistant de démarrage", "elle", getattr(c, "open_wizard", None),
        "assistant demarrage premiers reglages configuration bienvenue")
    add("zone", "🔲", "Traduire une zone de l'écran", "elle", getattr(c, "translate_zone", None),
        "traduire zone ecran capture jeu texte image ocr lire encadrer")
    add("touches", "⌨️", "Raccourcis clavier", "elle", getattr(c, "show_shortcut_help", None),
        "raccourci clavier touche super global appeler")
    add("salon", "📺", "Salon (séries, Netflix, Spotify…)", "elle", getattr(c, "open_services", None),
        "salon serie film netflix disney prime spotify deezer regarder ce soir reprendre")
    add("bug", "🐞", "Signaler un bug", "elle", getattr(c, "signaler_bug", None),
        "bug probleme erreur signaler rapport github plantage aide")
    return A


def search(acts, q):
    q = _sa(q).strip()
    if not q:
        return []
    stop = {"le", "la", "les", "un", "une", "des", "du", "de", "mon", "ma", "mes", "ton", "ta", "tes", "moi", "truc",
            "chose", "active", "activer", "mets", "met", "lance", "ouvre", "fais", "fait", "affiche", "montre", "pour",
            "avec", "dans", "sur", "et", "en", "au", "aux", "ce", "ces", "cette", "stp", "svp", "veux", "voudrais"}
    words = [w[:-1] if len(w) > 4 and w.endswith("s") else w
             for w in re.findall(r"[a-z0-9]+", q) if len(w) > 1 and w not in stop] or [q]
    out = []
    for a in acts:
        hay = _sa(a["nom"] + " " + a["mots"])
        sc = sum(3 if w in _sa(a["nom"]) else 1 for w in words if w in hay)
        if sc:
            out.append((sc, a))
    return [a for _, a in sorted(out, key=lambda x: -x[0])]


def tr(c, s):
    try:
        import i18n
        return i18n.tr(s)
    except Exception:
        return s


# ------------------------------------------------------------------ A. menu court avec recherche
def short_menu(c, tray=False):
    acts = actions(c)
    m = QMenu()
    m.setMinimumWidth(270)
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(8, 6, 8, 6)
    ed = QLineEdit()
    ed.setPlaceholderText(tr(c, "🔎 Que veux-tu faire ?"))
    ed.setClearButtonEnabled(True)
    lay.addWidget(ed)
    wa = QWidgetAction(m)
    wa.setDefaultWidget(box)
    m.addAction(wa)
    m.addSeparator()
    fixed = []
    if c.cfg.get("ghost") and hasattr(c, "set_ghost"):
        ga = m.addAction("👻  " + tr(c, "Sortir du mode fantôme"), lambda: c.set_ghost(False))
        fg = ga.font()
        fg.setBold(True)
        ga.setFont(fg)
        fixed.append(ga)
    if hasattr(c, "is_muted") and c.is_muted():
        ra = m.addAction("🔊  " + tr(c, "Réactiver sa voix") + f"  (muette {c.mute_label()})", lambda: c.set_mute(0))
        fr = ra.font()
        fr.setBold(True)
        ra.setFont(fr)
        fixed.append(ra)
    a = m.addAction("🏠  " + tr(c, "Accueil (mes raccourcis)"), lambda: open_home(c))
    fixed.append(a)
    if hasattr(c, "open_tips"):
        fixed.append(m.addAction("💡  " + tr(c, "Trucs et astuces"), c.open_tips))
    if hasattr(c, "open_look"):
        fixed.append(m.addAction("👗  " + tr(c, "Mon apparence"), c.open_look))
    if hasattr(c, "nearby"):
        fixed.append(m.addAction("📍  " + tr(c, "Restos et lieux autour de moi"),
                                 lambda: c.nearby({"kind": "restaurant", "cuisine": None, "near": ""})))
    for key, ico, nom in CATS:
        items = [x for x in acts if x["cat"] == key]
        if not items:
            continue
        sm = m.addMenu(f"{ico}  {tr(c, nom)}")
        for x in items:
            sm.addAction(f"{x['ico']}  {tr(c, x['nom'])}", x["fn"])
        fixed.append(sm.menuAction())
    sep = m.addSeparator()
    fixed.append(sep)
    a = m.addAction("⚙️  " + tr(c, "Réglages…"), c.open_settings)
    f = a.font()
    f.setBold(True)
    a.setFont(f)
    if hasattr(c, "open_modeles"):
        mm = m.addAction("🧩  " + tr(c, "Modèles et mods…"), lambda: c.open_modeles())
        mm.setFont(f)
        if hasattr(c, "_menu_mods"):
            c._menu_mods(m)
    fixed.append(a)
    full = m.addMenu("☰  " + tr(c, "Tout le menu (complet)"))
    try:
        c._fill_menu(full, tray=tray)
    except TypeError:
        c._fill_menu(full)
    fixed.append(full.menuAction())
    if tray:
        fixed.append(m.addSeparator())
        fixed.append(m.addAction(tr(c, "Afficher / cacher"), c._toggle_visible))
        fixed.append(m.addAction(tr(c, "Quitter"), c.quit))
    results = []

    def update(text):
        for r in results:
            m.removeAction(r)
        results.clear()
        found = search(acts, text)[:8]
        for x in fixed:
            x.setVisible(not text.strip())
        before = fixed[0]
        for x in found:
            r = QWidgetAction(m)
            r.setText(f"{x['ico']}  {tr(c, x['nom'])}")
            r.triggered.connect(x["fn"])
            m.insertAction(before, r)
            results.append(r)
        if text.strip():
            r = QWidgetAction(m)
            r.setText("💬  " + tr(c, "Le lui demander") + f" : « {text.strip()[:40]} »")
            r.triggered.connect(lambda _=False, t=text.strip(): ask(t))
            m.insertAction(before, r)
            results.append(r)
        m.adjustSize()

    def ask(t):
        m.close()
        QTimer.singleShot(0, lambda: c._local_command(t) or (c.send_chat(t) if c.ollama_ok and
                                                             hasattr(c, "send_chat") else c.say(
                                                                 "Je n'ai pas compris… Essaie avec d'autres mots !")))

    def enter():
        if results:
            m.close()
            results[0].trigger()

    ed.textChanged.connect(update)
    ed.returnPressed.connect(enter)
    m.aboutToShow.connect(lambda: (ed.clear(), QTimer.singleShot(0, ed.setFocus)))
    return m


# ------------------------------------------------------------------ C. accueil en tuiles
CSS = """
QPushButton#tuile { font-size: 12pt; padding: 10px; border-radius: 14px; min-height: 84px;
                    background: palette(button); border: 1px solid palette(mid); }
QPushButton#tuile:hover { border: 2px solid palette(highlight); }
QLabel#titre { font-size: 13pt; font-weight: bold; }
QLabel#aide { color: palette(placeholder-text); }
"""


class Home(QWidget):
    def __init__(self, c):
        super().__init__(None, Qt.WindowType.Window)
        self.c = c
        self.setStyleSheet(CSS)
        self.setWindowTitle("🏠 " + tr(c, "Accueil") + " — " + c.char.get("name", "Viki"))
        self.resize(680, 540)
        self.edit = False
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        t = QLabel(tr(c, "Tes raccourcis"))
        t.setObjectName("titre")
        top.addWidget(t, 1)
        if hasattr(c, "open_tips"):
            bt = QPushButton("💡 " + tr(c, "Trucs et astuces"))
            bt.clicked.connect(c.open_tips)
            top.addWidget(bt)
        self.b_edit = QPushButton("✏️ " + tr(c, "Choisir mes raccourcis"))
        self.b_edit.clicked.connect(self.toggle_edit)
        top.addWidget(self.b_edit)
        lay.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr(c, "🔎 Que veux-tu faire ?"))
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self._enter)
        lay.addWidget(self.search)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        self.box = QWidget()
        self.grid = QGridLayout(self.box)
        self.grid.setSpacing(10)
        sc.setWidget(self.box)
        lay.addWidget(sc, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("aide")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.refresh()

    def pinned(self):
        return self.c.cfg.get("raccourcis") or list(DEFAUT)

    def toggle_edit(self):
        self.edit = not self.edit
        self.b_edit.setText("✅ " + tr(self.c, "Terminé") if self.edit else "✏️ " + tr(self.c, "Choisir mes raccourcis"))
        self.refresh()

    def _clear(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _enter(self):
        q = self.search.text().strip()
        found = search(actions(self.c), q)
        if found:
            self._run(found[0])
        elif q:
            self.c._local_command(q) or self.c.say("Je n'ai pas compris… Essaie avec d'autres mots !")

    def _run(self, a):
        if self.c.cfg.get("accueil_fermer", True):
            self.close()
        QTimer.singleShot(0, a["fn"])

    def refresh(self, *_a):
        self._clear()
        acts = actions(self.c)
        q = self.search.text().strip()
        if self.edit:
            self.hint.setText(tr(self.c, "Coche ceux que tu veux voir ici et dans la barre à côté d'elle "
                                         "(les 8 premiers pour la barre)."))
            pins = self.pinned()
            row = 0
            for key, ico, nom in CATS:
                items = [a for a in acts if a["cat"] == key]
                if not items:
                    continue
                l = QLabel(f"<b>{ico} {tr(self.c, nom)}</b>")
                self.grid.addWidget(l, row, 0, 1, 3)
                row += 1
                for i, a in enumerate(items):
                    cb = QCheckBox(f"{a['ico']} {tr(self.c, a['nom'])}")
                    cb.setChecked(a["id"] in pins)
                    cb.toggled.connect(lambda v, id_=a["id"]: self._pin(id_, v))
                    self.grid.addWidget(cb, row + i // 3, i % 3)
                row += (len(items) + 2) // 3
            return
        self.hint.setText(tr(self.c, "Astuce : tape ce que tu veux faire, puis Entrée. Ou clique sur ✏️ pour choisir "
                                     "tes raccourcis."))
        if q:
            shown = search(acts, q)[:12]
        else:
            by = {a["id"]: a for a in acts}
            shown = [by[i] for i in self.pinned() if i in by]
        for i, a in enumerate(shown):
            b = QPushButton(f"{a['ico']}\n{tr(self.c, a['nom'])}")
            b.setObjectName("tuile")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=a: self._run(a))
            self.grid.addWidget(b, i // 3, i % 3)
        self.grid.setRowStretch(max(1, (len(shown) + 2) // 3), 1)
        if not shown and q:
            b = QPushButton("💬 " + tr(self.c, "Le lui demander") + f" : « {q[:40]} »")
            b.clicked.connect(self._enter)
            self.grid.addWidget(b, 0, 0, 1, 3)

    def _pin(self, id_, on):
        pins = [p for p in self.pinned() if p != id_]
        if on:
            pins.append(id_)
        self.c.cfg["raccourcis"] = pins
        __import__("sys").modules[type(self.c).__module__].save_config(self.c.cfg)
        bar = getattr(self.c, "shortcut_bar", None)
        if bar:
            bar.rebuild()


def open_home(c, edit=False):
    w = getattr(c, "home_win", None)
    if w is None:
        w = c.home_win = Home(c)
    if edit and not w.edit:
        w.toggle_edit()
    w.refresh()
    w.show()
    w.raise_()
    w.activateWindow()
    QTimer.singleShot(0, w.search.setFocus)


# ------------------------------------------------------------------ barre à côté du personnage
class Bar(QWidget):
    def __init__(self, c):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.c = c
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(6)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.follow)
        self.timer.start(250)
        self.rebuild()

    def rebuild(self):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        by = {a["id"]: a for a in actions(self.c)}
        ids = [i for i in (self.c.cfg.get("raccourcis") or DEFAUT) if i in by][:8]
        if hasattr(self.c, "is_muted") and self.c.is_muted() and "muette" not in ids:
            ids = ["muette"] + ids                       # muette : le bouton 🔊 pour la réactiver, en premier
        size = int(self.c.cfg.get("barre_taille", 38))
        for i in ids + ["__plus"]:
            b = QToolButton()
            if i == "__plus":
                b.setText("☰")
                b.setToolTip(tr(self.c, "Accueil et tous les raccourcis"))
                b.clicked.connect(lambda: open_home(self.c))
            else:
                a = by[i]
                b.setText(a["ico"])
                b.setToolTip(tr(self.c, a["nom"]))
                b.clicked.connect(a["fn"])
            b.setFixedSize(QSize(size, size))
            f = b.font()
            f.setPointSizeF(size * 0.36)
            b.setFont(f)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QToolButton {{ background: palette(window); border: 1px solid palette(mid); "
                            f"border-radius: {size // 2}px; }} QToolButton:hover {{ border: 2px solid palette(highlight); }}")
            self.lay.addWidget(b)
        self.adjustSize()
        self.follow()

    def follow(self):
        c = self.c
        want = c.cfg.get("barre_raccourcis") and c.isVisible() and not getattr(c, "fs_hidden", False)
        if getattr(c, "cfg", {}).get("barre_survol"):
            under = c.geometry().adjusted(-60, -20, 60, 20).contains(QCursor.pos()) or \
                self.geometry().adjusted(-20, -20, 20, 20).contains(QCursor.pos())
            if under:
                self._seen = 6
            want = want and getattr(self, "_seen", 0) > 0
            self._seen = max(0, getattr(self, "_seen", 0) - 1)
        if not want:
            if self.isVisible():
                self.hide()
            return
        try:
            body = c.body_rect() if hasattr(c, "body_rect") else None
        except Exception:
            body = None
        g = c.geometry()
        if body is not None:
            left, right, top, bottom = g.x() + body.left(), g.x() + body.right(), g.y() + body.top(), g.y() + body.bottom()
        else:
            left, right, top, bottom = g.x() + g.width() * 0.2, g.x() + g.width() * 0.8, g.y(), g.y() + g.height()
        scr = (c.screen() or QApplication.primaryScreen()).availableGeometry()
        side = c.cfg.get("barre_cote", "auto")
        if side == "auto":
            side = "droite" if right + self.width() + 8 < scr.right() else "gauche"
        x = int(right + 6) if side == "droite" else int(left - self.width() - 6)
        y = int(top + (bottom - top) * 0.22)
        x = max(scr.left(), min(x, scr.right() - self.width()))
        y = max(scr.top(), min(y, scr.bottom() - self.height()))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
        if not self.isVisible():
            self.show()


def update_bar(c):
    bar = getattr(c, "shortcut_bar", None)
    if c.cfg.get("barre_raccourcis"):
        if bar is None:
            c.shortcut_bar = Bar(c)
        else:
            bar.rebuild()
    elif bar is not None:
        bar.hide()
