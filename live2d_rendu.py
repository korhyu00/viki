"""Personnages Live2D (.model3.json / .model.json) dans la fenêtre du compagnon.

Le modèle est dessiné hors écran (OpenGL) dans une image, que la fenêtre habituelle affiche :
bulle, émotes, marche, perchoir… tout le reste marche comme pour un personnage en image.

Nécessite : pip install live2d-py PyOpenGL
Modèles : faits avec Live2D Cubism Editor, ou achetés / téléchargés en respectant leur licence.
"""
import json
import math
import random
import re
import time
from pathlib import Path

_live2d = _GL = None
_ctx = _surf = None
_err = ""


def available():
    """(True, "") si live2d-py et PyOpenGL sont là, sinon (False, raison)."""
    global _live2d, _GL, _err
    if _live2d:
        return True, ""
    try:
        import live2d as l2d
        from OpenGL import GL
        _live2d, _GL = l2d, GL
        return True, ""
    except Exception as e:
        _err = str(e)
        return False, _err


def verifier_opengl(ctx):
    """Le moteur Live2D a besoin d'OpenGL 2.1 au moins. Sous Windows, sans le pilote de la carte graphique
    (« Microsoft Basic Display Adapter » ou « GDI Generic »), il n'y a qu'OpenGL 1.1 : le moteur plante net."""
    try:
        ver = (_GL.glGetString(_GL.GL_VERSION) or b"").decode("utf-8", "replace")
        ren = (_GL.glGetString(_GL.GL_RENDERER) or b"").decode("utf-8", "replace")
    except Exception:
        ver = ren = ""
    maj, mi = ctx.format().majorVersion(), ctx.format().minorVersion()
    m = re.match(r"\s*(\d+)\.(\d+)", str(ver))
    if m:
        maj, mi = int(m.group(1)), int(m.group(2))
    if "gdi generic" in str(ren).lower() or (maj, mi) < (2, 1):
        raise RuntimeError(f"ta carte graphique n'offre que OpenGL {maj}.{mi} ({ren or 'pilote inconnu'}) : "
                           "il manque sûrement son pilote. Installe le pilote de ta carte graphique (site d'AMD, "
                           "ou Windows Update), puis réessaie.")
    return f"{ver} — {ren}"



def _context():
    """Contexte OpenGL partagé, sans fenêtre visible."""
    global _ctx, _surf
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    if _ctx is None:
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setStencilBufferSize(8)
        ctx = QOpenGLContext()
        ctx.setFormat(fmt)
        if not ctx.create():
            raise RuntimeError("OpenGL indisponible")
        surf = QOffscreenSurface()
        surf.setFormat(ctx.format())
        surf.create()
        if not ctx.makeCurrent(surf):
            raise RuntimeError("OpenGL : impossible d'activer le contexte")
        verifier_opengl(ctx)                             # avant le moteur : un vieux pilote le ferait planter
        _live2d.init()
        _live2d.glInit()
        _ctx, _surf = ctx, surf
    _ctx.makeCurrent(_surf)
    return _ctx


def is_model_json(p):
    """Fichier de description d'un modèle Live2D (Cubism 3+ : *.model3.json ; Cubism 2 : n'importe quel
    .json qui pointe vers un .moc, par exemple « 01.json »)."""
    p = Path(p)
    if p.name.endswith((".model3.json", ".model.json")):
        return True
    if p.suffix.lower() != ".json" or p.stat().st_size > 2_000_000:
        return False
    d = _read_json(p)
    if not isinstance(d, dict):
        return False
    low = {k.lower(): v for k, v in d.items()}
    if ".moc" in str(low.get("model", "")).lower():
        return True
    fr = low.get("filereferences") or {}
    if isinstance(fr, dict):
        fr = {k.lower(): v for k, v in fr.items()}
        return ".moc" in str(fr.get("moc", "")).lower()
    return False


def _read_json(p):
    """JSON tolérant : marque d'encodage (BOM) au début, virgules en trop, caractères bizarres."""
    try:
        txt = Path(p).read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return None
    for attempt in (txt, re.sub(r",\s*([}\]])", r"\1", txt)):
        try:
            return json.loads(attempt)
        except Exception:
            pass
    return None


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tga")
_SKIP_IMG = ("icon", "preview", "thumb", "banner", "cover", "background", "bg_", "screenshot")


def _images_in(d, deep=False):
    it = d.rglob("*") if deep else d.glob("*")
    return sorted((p for p in it if p.is_file() and p.suffix.lower() in IMG_EXT
                   and not p.name.lower().startswith(_SKIP_IMG)), key=lambda p: p.as_posix().lower())


def _textures_for(moc, root=None):
    """Images d'un .moc sans description : « <nom>.1024/ », « textures/ », à côté, puis tout le paquet."""
    moc = Path(moc)
    stem = moc.name.split(".")[0].lower()
    dirs = [d for d in moc.parent.iterdir() if d.is_dir() and d.name.lower().startswith(stem)]
    dirs += [d for d in moc.parent.iterdir() if d.is_dir() and "tex" in d.name.lower()]
    for d in dirs + [moc.parent]:
        imgs = _images_in(d)
        if imgs:
            return imgs
    for d in [moc.parent] + ([Path(root)] if root else []):     # plus loin : sous-dossiers, tout le paquet
        imgs = _images_in(d, deep=True)
        if imgs:
            named = [p for p in imgs if stem in p.name.lower() or "tex" in p.as_posix().lower()]
            return named or imgs
    return []


def make_model_json(moc, root=None):
    """Crée la description d'un modèle qui n'a que son .moc / .moc3 et ses images. Renvoie son chemin."""
    moc = Path(moc)
    base = moc.parent
    rel = lambda p: Path(__import__("os").path.relpath(p, base)).as_posix()
    tex = _textures_for(moc, root)
    if not tex:
        return None
    stem = moc.name.split(".")[0]
    if moc.suffix.lower() == ".moc3":
        out = base / f"{stem}.model3.json"
        d = {"Version": 3, "FileReferences": {"Moc": rel(moc), "Textures": [rel(t) for t in tex]}}
    else:
        out = base / f"{stem}.model.json"
        d = {"model": rel(moc), "textures": [rel(t) for t in tex]}
    if out.exists():
        return out
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    complete_model_json(out)                                  # physique, mouvements, expressions
    return out


def moc_of(path):
    """Chemin du .moc / .moc3 d'une description de modèle (ou None)."""
    d = _read_json(path)
    if not isinstance(d, dict):
        return None
    low = {k.lower(): v for k, v in d.items()}
    moc = low.get("model")
    fr = low.get("filereferences")
    if not moc and isinstance(fr, dict):
        moc = {k.lower(): v for k, v in fr.items()}.get("moc")
    return (Path(path).parent / moc) if moc else None


def model_ok(path):
    """Le modèle peut être chargé sans risque : son .moc existe, ses images aussi."""
    moc = moc_of(path)
    if not moc or not moc.is_file() or moc.stat().st_size < 64:
        return False
    d = _read_json(path) or {}
    tex = d.get("textures") or ((d.get("FileReferences") or {}).get("Textures")) or []
    return all((Path(path).parent / t).is_file() for t in tex)


def complete_model_json(path):
    """Ajoute à la description du modèle ce qui est dans le dossier mais pas déclaré
    (physique des cheveux, mouvements, expressions). Sans effet si tout est déjà là."""
    path = Path(path)
    d = _read_json(path)
    if not isinstance(d, dict):
        return False
    base = path.parent
    rel = lambda p: p.relative_to(base).as_posix()
    changed = _drop_missing(d, base)
    if "FileReferences" in d:                                  # Cubism 3 et plus
        fr = d["FileReferences"]
        if not fr.get("Physics"):
            p = next(iter(sorted(base.rglob("*.physics3.json"))), None)
            if p:
                fr["Physics"] = rel(p)
                changed = True
        if not fr.get("Motions"):
            mots = sorted(base.rglob("*.motion3.json"))
            if mots:
                groups = {}
                for m in mots:
                    g = "Idle" if "idle" in m.name.lower() else "Tap"
                    groups.setdefault(g, []).append({"File": rel(m)})
                fr["Motions"] = groups
                changed = True
        if not fr.get("Expressions"):
            exps = sorted(base.rglob("*.exp3.json"))
            if exps:
                fr["Expressions"] = [{"Name": e.name.split(".")[0], "File": rel(e)} for e in exps]
                changed = True
    else:                                                      # Cubism 2
        if not d.get("physics"):
            p = next(iter(sorted(list(base.rglob("*.physics")) + list(base.rglob("physics*.json")))), None)
            if p:
                d["physics"] = rel(p)
                changed = True
        if not d.get("motions"):
            mots = sorted(base.rglob("*.mtn"))
            if mots:
                groups = {}
                for m in mots:
                    g = "idle" if "idle" in m.name.lower() else "tap_body"
                    groups.setdefault(g, []).append({"file": rel(m)})
                d["motions"] = groups
                changed = True
        if not d.get("expressions"):
            exps = sorted(base.rglob("*.exp.json"))
            if exps:
                d["expressions"] = [{"name": e.name.split(".")[0], "file": rel(e)} for e in exps]
                changed = True
    if changed:
        try:
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            return False
    return changed


def motion_sounds(path):
    """Sons / voix attachés aux mouvements : {(groupe, numéro): chemin absolu}."""
    d = _read_json(path)
    if not isinstance(d, dict):
        return {}
    base = Path(path).parent
    out = {}
    groups = (d.get("FileReferences") or {}).get("Motions") or d.get("motions") or {}
    for g, lst in groups.items():
        for i, mo in enumerate(lst or []):
            if not isinstance(mo, dict):
                continue
            snd = mo.get("Sound") or mo.get("sound")
            if snd and (base / snd).exists():
                out[(g, i)] = str(base / snd)
    return out


def _drop_missing(d, base):
    """Retire les mouvements / expressions / sons / physique dont le fichier n'existe pas :
    la bibliothèque Live2D plante si on lui demande de jouer un fichier absent."""
    changed = False
    ok = lambda f: bool(f) and (base / f).is_file()
    fr = d.get("FileReferences")
    if isinstance(fr, dict):
        for g, lst in list((fr.get("Motions") or {}).items()):
            keep = [m for m in lst or [] if isinstance(m, dict) and ok(m.get("File"))]
            for m in keep:
                if m.get("Sound") and not ok(m["Sound"]):
                    m.pop("Sound")
                    changed = True
            if len(keep) != len(lst or []):
                changed = True
            if keep:
                fr["Motions"][g] = keep
            else:
                fr["Motions"].pop(g)
        exps = fr.get("Expressions")
        if exps:
            keep = [e for e in exps if isinstance(e, dict) and ok(e.get("File"))]
            if len(keep) != len(exps):
                fr["Expressions"] = keep
                changed = True
        for k in ("Physics", "Pose", "UserData", "DisplayInfo"):
            if fr.get(k) and not ok(fr[k]):
                fr.pop(k)
                changed = True
    else:
        for g, lst in list((d.get("motions") or {}).items()):
            keep = [m for m in lst or [] if isinstance(m, dict) and ok(m.get("file"))]
            for m in keep:
                if m.get("sound") and not ok(m["sound"]):
                    m.pop("sound")
                    changed = True
            if len(keep) != len(lst or []):
                changed = True
            if keep:
                d["motions"][g] = keep
            else:
                d["motions"].pop(g)
        exps = d.get("expressions")
        if exps:
            keep = [e for e in exps if isinstance(e, dict) and ok(e.get("file"))]
            if len(keep) != len(exps):
                d["expressions"] = keep
                changed = True
        for k in ("physics", "pose"):
            if d.get(k) and not ok(d[k]):
                d.pop(k)
                changed = True
    return changed


AUDIO_EXT = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".opus")
VOICE_KEYS = {"joie": ("fun", "happy", "joy", "smile", "laugh", "glad", "yorokobi"),
              "triste": ("sad", "cry", "kanashi"), "boude": ("angry", "anger", "mad", "ikari", "okori"),
              "surprise": ("surprise", "shock", "odoroki"), "timide": ("shy", "hanikami", "blush", "tere"),
              "salut": ("hello", "hi_", "greet", "morning", "aisatsu", "login", "title"),
              "au revoir": ("bye", "goodbye", "logout", "sayonara")}


def voice_pool(root, referenced=()):
    """Voix / sons livrés avec le modèle mais reliés à aucun mouvement (dossier voice/, sound/…)."""
    root = Path(root)
    if not root.is_dir():
        return []
    ref = {str(Path(r).resolve()) for r in referenced}
    files = [p for p in root.rglob("*") if p.suffix.lower() in AUDIO_EXT and p.is_file()
             and str(p.resolve()) not in ref]
    return sorted(files, key=lambda p: p.as_posix().lower())[:3000]


def pick_voice(pool, *hints):
    """Une voix du lot : d'abord celles dont le nom correspond (émotion, nom du mouvement), sinon au hasard."""
    if not pool:
        return None
    for h in hints:
        if not h:
            continue
        keys = VOICE_KEYS.get(h, (h.lower(),))
        match = [p for p in pool if any(k in p.name.lower() for k in keys)]
        if match:
            return random.choice(match)
    return random.choice(pool)


def hit_areas_of(path):
    """Zones cliquables déclarées par le modèle : [(nom, id)]."""
    d = _read_json(path)
    if not isinstance(d, dict):
        return []
    out = [(a.get("Name", ""), a.get("Id", "")) for a in d.get("HitAreas") or []]
    out += [(a.get("name", ""), a.get("id", "")) for a in d.get("hit_areas") or []]
    return [(n, i) for n, i in out if n or i]


def find_models(folder):
    """Tous les modèles d'un dossier (un même personnage a souvent plusieurs tenues : 01.json, 02.json…)."""
    folder = Path(folder)
    out = [p for p in folder.rglob("*.json") if is_model_json(p) and model_ok(p)]   # versions incomplètes : écartées
    if not out:                                   # que des .moc / .moc3 : on crée leur description
        for moc in sorted(list(folder.rglob("*.moc")) + list(folder.rglob("*.moc3"))):
            try:
                made = make_model_json(moc, folder)
            except Exception:
                made = None
            if made:
                out.append(made)
    return sorted(out, key=lambda p: (len(p.parts), p.name))


def find_model(folder):
    found = find_models(folder)
    return found[0] if found else None


class Live2DModel:
    """Un modèle Live2D rendu hors écran à la taille voulue (pixels physiques)."""

    def __init__(self, model_json, scale=1.0):
        ok, why = available()
        if not ok:
            raise RuntimeError("live2d-py manquant : " + why)
        _context()
        self.path = str(model_json)
        if not model_ok(self.path):                          # la bibliothèque plante si le .moc manque
            raise RuntimeError("fichiers du modèle incomplets (.moc ou images manquants)")
        try:
            complete_model_json(self.path)                   # jamais de fichier absent pour la bibliothèque
        except Exception:
            pass
        self.model = _live2d.Model()
        self.model.LoadModelJson(self.path)
        self.params = set(self.model.GetParamIds())
        try:
            self.groups = self.model.GetMotionGroups() or {}
        except Exception:
            self.groups = {}
        try:
            self.expressions = list(self.model.GetExpressions() or [])
        except Exception:
            self.expressions = []
        self.areas = hit_areas_of(self.path)
        self.idle_group = next((k for k in self.groups if "idle" in k.lower() and self.groups[k]), None)
        # liste de tous les mouvements : (groupe, numéro, nom du fichier)
        self.motions = []
        try:
            for g, lst in (self.model.GetMotions() or {}).items():
                for i, mo in enumerate(lst or []):
                    f = (mo.get("File") or mo.get("file") or "") if isinstance(mo, dict) else str(mo)
                    self.motions.append((g, i, Path(f).name.split(".")[0] or f"{g} {i + 1}"))
        except Exception:
            for g, n in self.groups.items():
                self.motions += [(g, i, f"{g or 'mouvement'} {i + 1}") for i in range(int(n or 0))]
        self.sounds = motion_sounds(self.path)          # (groupe, numéro) -> fichier son
        self.on_sound = None                              # fonction(chemin, raison), donnée par le compagnon
        self.voices = []                                  # voix du paquet reliées à aucun mouvement
        self.last_emo = ""
        self.scale = float(scale or 1.0)
        self.random_moves = True
        self.next_random = time.monotonic() + random.uniform(15, 35)
        for fn in ("SetAutoBreath", "SetAutoBlink"):
            try:
                getattr(self.model, fn)(True)
            except Exception:
                pass
        self.t0 = time.monotonic()
        self.fbo = None
        self.size = (0, 0)
        self.last = time.monotonic()
        self.expr_until = 0.0
        self.look = (0.0, 0.0)

    def close(self):
        """Libère le modèle et ses textures avec le contexte OpenGL actif (sinon : plantage possible)."""
        try:
            _context()
            self.fbo = None
            self.model = None
        except Exception:
            pass

    def resize(self, w, h):
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        w, h = max(16, int(w)), max(16, int(h))
        if (w, h) == self.size:
            return
        _context()
        ff = QOpenGLFramebufferObjectFormat()
        ff.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        self.fbo = QOpenGLFramebufferObject(w, h, ff)
        self.model.Resize(w, h)
        try:
            self.model.SetScale(self.scale)
        except Exception:
            pass
        self.size = (w, h)

    def _set(self, pid, v, weight=1.0):
        if pid in self.params:
            self.model.SetParamById(pid, float(v), weight)

    def _add(self, pid, v):
        """S'ajoute au mouvement en cours au lieu de le remplacer."""
        if pid in self.params and v:
            try:
                self.model.AddParamById(pid, float(v))
            except Exception:
                self.model.SetParamById(pid, float(v), 0.3)

    def set_voice_pool(self, root):
        self.voices = voice_pool(root, self.sounds.values())

    def play_motion(self, group, index, priority=3, reason="clic"):
        if (group, int(index)) not in {(g, i) for g, i, _ in self.motions}:
            return False                                  # mouvement inconnu : on ne prend pas de risque
        try:
            self.model.StartMotion(group, int(index), priority)
            snd = self.sounds.get((group, int(index)))
            if not snd and self.voices and (reason in ("clic", "emotion") or random.random() < 0.35):
                name = next((n for g, i, n in self.motions if g == group and i == int(index)), "")
                v = pick_voice(self.voices, self.last_emo if reason == "emotion" else "", name)
                snd = str(v) if v else None
            if snd and self.on_sound:
                self.on_sound(snd, reason)
            return True
        except Exception:
            try:
                self.model.StartRandomMotion(group, priority)
                return True
            except Exception:
                return False

    def _motion_like(self, keys, idle_ok=False):
        """Mouvement dont le nom de fichier contient un des mots-clés."""
        cands = [(g, i) for g, i, n in self.motions
                 if any(k in n.lower() for k in keys) and (idle_ok or "idl" not in n.lower())]
        return random.choice(cands) if cands else None

    def _idle(self):
        if self.model.IsMotionFinished():
            g = self.idle_group
            if g:
                try:
                    self.model.StartRandomMotion(g, 1)
                except Exception:
                    pass

    def hit(self, x, y):
        """Zone cliquable du modèle sous le point (pixels de l'image rendue) : son nom, ou None."""
        for name, aid in self.areas:
            for key in (name, aid):
                if not key:
                    continue
                try:
                    if self.model.IsAreaHit(key, x, y):
                        return name or aid
                except Exception:
                    break
        if self.areas:                                   # sinon : parties touchées comparées aux ids
            try:
                hits = set(self.model.HitPart(x, y, False)) | set(self.model.HitDrawable(x, y, False))
                for name, aid in self.areas:
                    if aid in hits:
                        return name or aid
            except Exception:
                pass
        return None

    def tap_area(self, area):
        """Mouvement prévu pour cette zone (« tap_head », « flick_head », « TapBody »…), sinon un geste."""
        a = re.sub(r"[^a-z]", "", (area or "").lower())
        if a:
            g = next((k for k in self.groups if self.groups[k] and a in re.sub(r"[^a-z]", "", k.lower())), None)
            if g:
                if self.play_motion(g, random.randrange(max(1, int(self.groups[g] or 1)))):
                    return
        self.tap()

    def tap(self):
        """Petite réaction quand on la touche."""
        g = next((k for k in self.groups if "tap" in k.lower() or "body" in k.lower()), None)
        if g:
            return self.play_motion(g, random.randrange(max(1, int(self.groups[g] or 1))))
        others = [(gg, i) for gg, i, n in self.motions if "idl" not in n.lower() and "idl" not in gg.lower()]
        if others:                                      # sinon : n'importe quel mouvement qui n'est pas « idle »
            self.play_motion(*random.choice(others))

    def emote(self, emo):
        """Émotion du compagnon -> mouvement du modèle qui lui correspond, son expression, sinon un petit geste."""
        keys = {"joie": ("fun", "happy", "joy", "smile", "laugh", "glad", "yorokobi", "warai"),
                "triste": ("sad", "cry", "kanashi"),
                "boude": ("angry", "anger", "mad", "ikari", "okori"),
                "surprise": ("surprise", "shock", "odoroki"),
                "timide": ("shy", "hanikami", "blush", "tere")}.get(emo, ())
        self.last_emo = emo
        mo = self._motion_like(keys) if keys else None
        if mo:
            self.play_motion(*mo, reason="emotion")
        elif self.voices and self.on_sound and emo in VOICE_KEYS:       # pas de mouvement : au moins la voix
            v = pick_voice(self.voices, emo)
            if v:
                self.on_sound(str(v), "emotion")
        if self.expressions:
            want = {"joie": ("smile", "happy", "joy", "fun", "f01", "exp_01"),
                    "triste": ("sad", "cry", "f03", "exp_03"),
                    "boude": ("angry", "mad", "f04", "exp_04"),
                    "surprise": ("surprise", "shock", "f05", "exp_05"),
                    "timide": ("shy", "blush", "hanikami", "f06", "exp_06")}.get(emo, ())
            ex = next((e for e in self.expressions if any(k in e.lower() for k in want)), None)
            if ex is None and emo in ("joie", "surprise", "timide"):
                ex = random.choice(self.expressions)
            if ex:
                try:
                    self.model.SetExpression(ex)
                    self.expr_until = time.monotonic() + 5
                except Exception:
                    pass
        if emo in ("joie", "surprise") and not mo:
            self.tap()

    def frame(self, look=(0.0, 0.0), mouth=0.0, eyes=None, smile=0.0, body=0.0):
        """Dessine l'instant présent. look : -1..1 (x vers la droite, y vers le haut).
        mouth : 0..1. eyes : None (clignements du modèle) ou ouverture forcée 0..1."""
        from PyQt6.QtGui import QImage
        _context()
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - self.last))
        self.last = now
        if self.expr_until and now > self.expr_until:
            self.expr_until = 0.0
            try:
                self.model.ResetExpression()
            except Exception:
                pass
        self._idle()
        if self.random_moves and now > self.next_random:
            self.next_random = now + random.uniform(25, 60)
            if self.model.IsMotionFinished() or self.idle_group:
                cands = [(g, i) for g, i, n in self.motions if "idl" not in n.lower() and "idl" not in g.lower()]
                if cands:
                    self.play_motion(*random.choice(cands), priority=2, reason="hasard")
        lx = self.look[0] + (look[0] - self.look[0]) * min(1.0, dt * 6)
        ly = self.look[1] + (look[1] - self.look[1]) * min(1.0, dt * 6)
        self.look = (lx, ly)
        self.fbo.bind()
        _GL.glViewport(0, 0, self.size[0], self.size[1])
        _live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
        self.model.Update(dt)
        # regard et tête : s'ajoutent aux mouvements du modèle (qui restent donc visibles)
        self._add("ParamAngleX", lx * 18)
        self._add("ParamAngleY", ly * 15)
        self._add("ParamBodyAngleX", lx * 5 + body)
        if not self.idle_group:                           # pas de mouvement de repos : respiration et balancement
            tt = now - self.t0
            br = (math.sin(tt * 2 * math.pi / 3.6) + 1) / 2
            for pid in ("ParamBreath", "PARAM_BREATH"):
                self._set(pid, br)
            for pid in ("ParamBodyAngleZ", "PARAM_BODY_ANGLE_Z"):
                self._set(pid, 2.5 * math.sin(tt * 2 * math.pi / 7.0), 0.7)
            for pid in ("ParamAngleZ", "PARAM_ANGLE_Z"):
                self._set(pid, 3 * math.sin(tt * 2 * math.pi / 5.3) - lx * ly * 10, 0.6)
        self._set("ParamEyeBallX", lx, 0.6)
        self._set("ParamEyeBallY", ly, 0.6)
        if mouth > 0.01:
            self._set("ParamMouthOpenY", min(1.0, mouth))
        if eyes is not None:
            self._set("ParamEyeLOpen", eyes)
            self._set("ParamEyeROpen", eyes)
        if smile:
            self._set("ParamEyeLSmile", smile)
            self._set("ParamEyeRSmile", smile)
            self._set("ParamMouthForm", smile)
        # Cubism 2 : autres noms de paramètres
        if "PARAM_ANGLE_X" in self.params:
            self._add("PARAM_ANGLE_X", lx * 18)
            self._add("PARAM_ANGLE_Y", ly * 15)
            self._set("PARAM_EYE_BALL_X", lx, 0.6)
            self._set("PARAM_EYE_BALL_Y", ly, 0.6)
            self._add("PARAM_BODY_ANGLE_X", lx * 5 + body)
            if mouth > 0.01:
                self._set("PARAM_MOUTH_OPEN_Y", min(1.0, mouth))
            if eyes is not None:
                self._set("PARAM_EYE_L_OPEN", eyes)
                self._set("PARAM_EYE_R_OPEN", eyes)
        self.model.Draw()
        img = self.fbo.toImage()                         # déjà à l'endroit
        self.fbo.release()
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def render_preview(model_json, out_png, w=1000, h=1200):
    """Image d'aperçu (fond transparent, recadrée) + infos pour character.json.
    Si le modèle dépasse du cadre, on le rétrécit jusqu'à ce qu'il tienne en entier."""
    from PyQt6.QtGui import QImage
    import numpy as np
    m = Live2DModel(model_json)
    m.random_moves = False
    m.resize(w, h)
    scale = 0.85                                        # un peu de marge d'office pour ses mouvements
    for _ in range(6):
        try:
            m.model.SetScale(scale)
        except Exception:
            pass
        m.model.StopAllMotions()
        img = None
        for _ in range(3):                              # quelques images : la physique se pose
            img = m.frame()
        a = img.convertToFormat(QImage.Format.Format_ARGB32)
        arr = np.frombuffer(a.constBits().asstring(a.sizeInBytes()), np.uint8).reshape(h, a.bytesPerLine())
        alpha = arr[:, :w * 4].reshape(h, w, 4)[:, :, 3]
        ys, xs = np.where(alpha > 8)
        if len(xs) == 0:
            raise RuntimeError("le modèle ne s'affiche pas (texture manquante ?)")
        edge = max(4, int(0.02 * min(w, h)))
        cut = xs.min() <= edge or ys.min() <= edge or xs.max() >= w - 1 - edge or ys.max() >= h - 1 - edge
        if not cut:
            break
        scale *= 0.75                                   # coupé par le bord : on dézoome
    pad = int(0.06 * max(xs.max() - xs.min(), ys.max() - ys.min()))   # place pour ses mouvements
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    crop = img.copy(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
    crop.save(str(out_png))
    cw, ch = x1 - x0, y1 - y0
    # tête : estimation (le haut de la silhouette, un peu plus bas)
    top = alpha[y0:y0 + max(1, int(ch * 0.25)), x0:x1] > 8
    cols = np.where(top.any(0))[0]
    cx = float(cols.mean()) if len(cols) else cw / 2
    eye_y = min(ch * 0.16, 0.12 * ch + 0.08 * cw)
    d = max(14.0, cw * 0.09)
    return {"canvas": [w, h], "crop": [int(x0), int(y0), int(x1), int(y1)], "size": [int(cw), int(ch)],
            "l2d_scale": round(scale, 4),
            "eyes": [{"x": cx - d / 2, "y": eye_y, "w": d * 0.55, "h": d * 0.3},
                     {"x": cx + d / 2, "y": eye_y, "w": d * 0.55, "h": d * 0.3}],
            "mouth": {"x": cx, "y": eye_y + d * 0.9, "w": d * 0.5, "max_open": d * 0.3}}
