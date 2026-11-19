"""Elle s'habitue à toi avec le temps — tout reste sur ton PC (apprentissage.json).

Ce qu'elle apprend :
  - tes horaires (quand tu es là, quand tu lui parles) ;
  - si ses phrases spontanées te plaisent (tu réponds) ou t'embêtent (« chut », tu ne réagis jamais)
    -> elle parle plus ou moins souvent, et laisse tomber les sujets qui ne marchent pas ;
  - tes consignes : « arrête de… », « j'aime pas quand tu… », « j'aime bien quand tu… » ;
  - la longueur de réponse que tu préfères (« trop long », « développe ») ;
  - ta façon d'écrire (messages courts ou longs) ;
  - tes jeux et activités préférés.
Rien n'est envoyé nulle part. On peut tout voir, retirer une règle ou tout oublier.
"""
import json
import re
import time
from pathlib import Path

def _sa(t):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")


STATE_FILE = None        # fixé par compagnon.py : ~/.config/viki/apprentissage.json
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _new():
    return {"version": 1, "debut": time.time(), "heures": [0] * 24, "jours": [0] * 7,
            "spont": {}, "freq": 1.0, "regles": [], "longueur": "normal",
            "style": {"msgs": 0, "mots": 0.0}, "jeux": {}, "activites": {}, "journal": []}


class Apprentissage:
    def __init__(self, path=None):
        self.path = Path(path or STATE_FILE)
        try:
            self.s = {**_new(), **json.loads(self.path.read_text(encoding="utf-8"))}
        except Exception:
            self.s = _new()
        self.last_spont = None          # (catégorie, instant)
        self._dirty = 0

    # ---------- sauvegarde
    def save(self, force=False):
        self._dirty += 1
        if not force and self._dirty < 5:
            return
        self._dirty = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.s, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def _log(self, txt):
        j = self.s.setdefault("journal", [])
        j.append([time.strftime("%d/%m"), txt])
        self.s["journal"] = j[-30:]

    def reset(self):
        self.s = _new()
        self.save(force=True)

    # ---------- tes habitudes
    def note_message(self, text):
        lt = time.localtime()
        self.s["heures"][lt.tm_hour] += 1
        self.s["jours"][lt.tm_wday] += 1
        st = self.s["style"]
        n = len(text.split())
        st["msgs"] = st.get("msgs", 0) + 1
        st["mots"] = round(st.get("mots", 0.0) * 0.95 + n * 0.05, 2) if st["msgs"] > 1 else float(n)
        if self.last_spont and time.monotonic() - self.last_spont[1] < 120:   # tu as répondu à sa phrase
            self._spont_result(self.last_spont[0], "repondu")
            self.last_spont = None
        self.save()

    def usual_hours(self):
        h = self.s["heures"]
        tot = sum(h)
        if tot < 30:
            return []
        return [i for i in range(24) if h[i] >= max(2, tot / 24 * 1.3)]

    def is_usual_hour(self, hour):
        u = self.usual_hours()
        return not u or hour in u or any(abs(hour - x) <= 1 for x in u)

    # ---------- phrases spontanées
    def note_spont(self, cat):
        d = self.s["spont"].setdefault(cat, {"dit": 0, "repondu": 0, "coupe": 0, "ignore": 0})
        d["dit"] += 1
        if self.last_spont:                       # la précédente n'a eu aucune réaction
            self._spont_result(self.last_spont[0], "ignore")
        self.last_spont = (cat, time.monotonic())
        self.save()

    def _spont_result(self, cat, what):
        d = self.s["spont"].setdefault(cat, {"dit": 0, "repondu": 0, "coupe": 0, "ignore": 0})
        d[what] = d.get(what, 0) + 1
        f = self.s.get("freq", 1.0)
        f *= {"repondu": 1.06, "coupe": 0.8, "ignore": 0.985}.get(what, 1.0)
        self.s["freq"] = round(max(0.35, min(2.0, f)), 3)

    def note_cut(self):
        """« Chut », « tais-toi », muet : sa dernière phrase spontanée t'a dérangé."""
        if self.last_spont and time.monotonic() - self.last_spont[1] < 90:
            self._spont_result(self.last_spont[0], "coupe")
            self._log(f"« {self.last_spont[0]} » t'a dérangé : j'en parlerai moins")
            self.last_spont = None
        else:
            self.s["freq"] = round(max(0.35, self.s.get("freq", 1.0) * 0.9), 3)
        self.save(force=True)

    def freq_factor(self):
        """> 1 : elle parle plus souvent ; < 1 : moins souvent."""
        return float(self.s.get("freq", 1.0))

    def allows(self, cat):
        """Ce sujet de phrase spontanée marche-t-il ? (s'il dérange souvent, elle l'évite)"""
        d = self.s["spont"].get(cat)
        if not d or d["dit"] < 4:
            return True
        bad = d.get("coupe", 0) * 3 + d.get("ignore", 0) * 0.3
        good = d.get("repondu", 0) * 2 + 1
        return bad / (bad + good) < 0.75

    # ---------- tes consignes
    # (type, motif sur le texte sans accents, gabarit de la règle à partir du groupe « x »)
    REGLES = [
        ("evite", r"^(?:j'?\s?aime pas|je n'?\s?aime pas|j'?\s?aime vraiment pas|je deteste)\s+(?:trop\s+)?quand tu\s+(?P<x>.+)", "{x}"),
        ("evite", r"^(?:arrete|arretes|evite|evites|cesse)\s+de\s+(?P<x>.+)", "{x}"),
        ("evite", r"^(?:ne\s+)?(?:me\s+)?(?P<v>dis|parle|demande)\s+plus\s+(?P<x>.+)", "{v} {x}"),
        ("aime", r"^(?:j'?\s?aime|j'?\s?aime bien|j'?\s?adore|c'?est (?:trop )?mignon)\s+quand tu\s+(?P<x>.+)", "{x}"),
        ("aime", r"^continue\s+(?:a|de)\s+(?P<x>.+)", "{x}"),
    ]
    VERBES = {"dis": "dire", "parle": "parler", "demande": "demander"}

    def parse_rule(self, ta, original=""):
        """ta : texte sans accents en minuscules. -> (type, règle) ou None."""
        t = ta.strip().rstrip(" !.?")
        for kind, rx, tpl in self.REGLES:
            m = re.match(rx, t, re.I)
            if not m:
                continue
            x = m.group("x").strip()
            # on reprend la fin du texte original (avec ses accents) quand c'est possible
            orig = (original or "").strip().rstrip(" !.?")
            if orig and len(orig) >= len(x) and _sa(orig[len(orig) - len(x):]).lower() == x.lower():
                x = orig[len(orig) - len(x):]
            if len(x) < 3 or len(x) > 160:
                return None
            if re.fullmatch(r"(me )?(parler|lire|chanter|jouer|bouger|danser|ecouter|m'?ecouter|marcher|dormir)",
                            _sa(x).lower()):
                return None                     # simples ordres (« arrête de lire ») : pas des règles
            v = self.VERBES.get(m.groupdict().get("v") or "", "")
            return kind, tpl.format(x=x, v=v).strip()
        return None

    def add_rule(self, kind, text):
        txt = text.strip()
        for r in self.s["regles"]:
            if r["texte"].lower() == txt.lower():
                r["type"] = kind
                self.save(force=True)
                return
        self.s["regles"].append({"type": kind, "texte": txt, "date": time.strftime("%d/%m/%Y")})
        self.s["regles"] = self.s["regles"][-25:]
        self._log(("à éviter : " if kind == "evite" else "tu aimes : ") + txt)
        self.save(force=True)

    def remove_rule(self, i):
        if 0 <= i < len(self.s["regles"]):
            self.s["regles"].pop(i)
            self.save(force=True)

    # ---------- longueur des réponses
    def note_length_feedback(self, ta):
        if re.search(r"\b(trop long|plus court|fais court|sois (plus )?breve|moins long|t'?es bavarde|"
                     r"en (une|1) phrase)\b", ta):
            self.s["longueur"] = "court" if self.s.get("longueur") != "long" else "normal"
        elif re.search(r"\b(developpe|plus de details|explique (plus|mieux)|plus long|en detail|"
                       r"dis[- ]m'?en plus)\b", ta):
            self.s["longueur"] = "long" if self.s.get("longueur") != "court" else "normal"
        else:
            return False
        self._log(f"longueur des réponses : {self.s['longueur']}")
        self.save(force=True)
        return True

    # ---------- jeux et activités
    def note_game(self, kind):
        self.s["jeux"][kind] = self.s["jeux"].get(kind, 0) + 1
        self.save()

    def favorite_games(self):
        return [k for k, _ in sorted(self.s["jeux"].items(), key=lambda x: -x[1])]

    # ---------- pour l'IA
    def prompt_block(self):
        parts = []
        ev = [r["texte"] for r in self.s["regles"] if r["type"] == "evite"]
        ai = [r["texte"] for r in self.s["regles"] if r["type"] == "aime"]
        if ev:
            parts.append("L'utilisateur t'a demandé d'éviter ceci (ce sont ses mots, adressés à toi) : "
                         + " ; ".join(f"« {x} »" for x in ev[-10:]) + ".")
        if ai:
            parts.append("Il aime quand tu fais ceci (ses mots) : " + " ; ".join(f"« {x} »" for x in ai[-10:]) + ".")
        lg = self.s.get("longueur", "normal")
        if lg == "court":
            parts.append("Il préfère les réponses très courtes : une ou deux phrases maximum.")
        elif lg == "long":
            parts.append("Il aime les réponses plus détaillées : tu peux aller jusqu'à cinq ou six phrases "
                         "quand le sujet s'y prête.")
        st = self.s["style"]
        if st.get("msgs", 0) > 20:
            if st.get("mots", 10) < 6:
                parts.append("Il écrit des messages très courts : reste simple et directe.")
            elif st.get("mots", 10) > 30:
                parts.append("Il écrit des messages longs et posés : prends le temps de bien répondre.")
        return (" " + " ".join(parts) + " ") if parts else " "

    # ---------- résumé lisible
    def summary(self):
        lines = []
        days = int((time.time() - self.s.get("debut", time.time())) / 86400)
        lines.append("J'apprends à te connaître depuis aujourd'hui." if days < 1 else
                     f"J'apprends à te connaître depuis {days} jour{'s' if days > 1 else ''}.")
        u = self.usual_hours()
        if u:
            ranges, start = [], u[0]
            for a, b in zip(u, u[1:] + [None]):
                if b != a + 1:
                    ranges.append(f"{start}h–{a + 1}h" if a != start else f"{start}h–{start + 1}h")
                    start = b
            lines.append("Tu es surtout là : " + ", ".join(ranges) + ".")
        jd = self.s["jours"]
        if sum(jd) >= 20:
            lines.append(f"Ton jour où on parle le plus : le {JOURS[jd.index(max(jd))]}.")
        f = self.freq_factor()
        lines.append("Je parle " + ("plus souvent qu'au début, tu as l'air d'aimer ça" if f > 1.15 else
                                    "moins souvent qu'au début, pour ne pas te déranger" if f < 0.85 else
                                    "à peu près autant qu'au début") + ".")
        lg = self.s.get("longueur", "normal")
        if lg != "normal":
            lines.append("Je fais des réponses " + ("courtes" if lg == "court" else "plus détaillées") + ".")
        tues = [c for c in self.s["spont"] if not self.allows(c)]
        if tues:
            lines.append("Sujets que j'évite (ils t'embêtaient) : " + ", ".join(tues) + ".")
        g = self.favorite_games()
        if g:
            lines.append("Ton jeu préféré avec moi : " + g[0] + ".")
        for r in self.s["regles"][-8:]:
            lines.append(("• Tu m'as demandé d'éviter : « " if r["type"] == "evite" else "• Tu aimes quand : « ")
                         + r["texte"] + " »")
        return lines
