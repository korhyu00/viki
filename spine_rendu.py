"""Personnages Spine (Esoteric Software) dans la fenêtre du compagnon.

Petit moteur Spine écrit pour le compagnon : lit l'export JSON (Spine 3.8 et 4.x) et l'atlas,
joue les animations (os : rotation, position, échelle, cisaillement ; slots : image, couleur ;
déformations de maillage ; ordre d'affichage) et dessine le tout hors écran en OpenGL.
Les .skel binaires de Spine 4.2/4.3 sont convertis en JSON à l'import (paquet SkelToJson).

Non pris en charge (le reste du modèle s'affiche quand même) : contraintes IK / transform / path,
physique 4.2, découpage (clipping).
"""
import json
import math
import random
import time
from pathlib import Path

import numpy as np

_GL = None
_ctx = _surf = None


def available():
    global _GL
    if _GL:
        return True, ""
    try:
        from OpenGL import GL
        _GL = GL
        return True, ""
    except Exception as e:
        return False, str(e)


def _context():
    global _ctx, _surf
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    if _ctx is None:
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        ctx = QOpenGLContext()
        ctx.setFormat(fmt)
        if not ctx.create():
            raise RuntimeError("OpenGL indisponible")
        surf = QOffscreenSurface()
        surf.setFormat(ctx.format())
        surf.create()
        _ctx, _surf = ctx, surf
    if not _ctx.makeCurrent(_surf):
        raise RuntimeError("OpenGL : impossible d'activer le contexte")
    return _ctx


# ================================================================ fichiers
def is_skeleton_json(p):
    p = Path(p)
    if p.suffix.lower() != ".json" or p.stat().st_size > 60_000_000:
        return False
    try:
        with open(p, "rb") as f:
            head = f.read(4096).decode("utf-8", "ignore")
        if '"bones"' not in head and '"skeleton"' not in head:
            return False
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        return isinstance(d, dict) and "bones" in d and ("slots" in d or "skins" in d)
    except Exception:
        return False


def find_skeletons(folder):
    folder = Path(folder)
    out = [p for p in folder.rglob("*.skel")] + [p for p in folder.rglob("*.json") if is_skeleton_json(p)]
    return sorted(out, key=lambda p: (len(p.parts), p.name))


def find_atlas(skel_path):
    skel_path = Path(skel_path)
    stem = skel_path.name.split(".")[0]
    cands = list(skel_path.parent.glob("*.atlas")) + list(skel_path.parent.glob("*.atlas.txt"))
    cands.sort(key=lambda a: (not a.name.startswith(stem), a.name))
    return cands[0] if cands else None


def skel_to_json(skel, out):
    """Spine 4.2/4.3 binaire -> JSON (paquet SkelToJson)."""
    from SkelToJson import convert_skel_to_json
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        convert_skel_to_json(str(skel), str(out))
    return out


def parse_atlas(path):
    """Atlas libGDX (format Spine 3 et 4) -> (pages, régions)."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pages, regions = [], {}
    page = region = None
    for raw in lines:
        line = raw.strip()
        if not line:
            page_next = True
            region = None
            continue
        if ":" in line and not line.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            k, v = [s.strip() for s in line.split(":", 1)]
            vals = [x.strip() for x in v.split(",")]
            tgt = region if region is not None else page
            if tgt is None:
                continue
            if region is None:                      # propriétés de la page
                if k == "size":
                    page["w"], page["h"] = int(vals[0]), int(vals[1])
                elif k == "pma":
                    page["pma"] = vals[0].lower() == "true"
                continue
            if k == "rotate":
                region["deg"] = 90 if vals[0].lower() == "true" else (int(vals[0]) if vals[0].lstrip("-").isdigit()
                                                                       else 0)
            elif k == "xy":
                region["x"], region["y"] = int(vals[0]), int(vals[1])
            elif k == "size":
                region["w"], region["h"] = int(vals[0]), int(vals[1])
            elif k == "bounds":
                region["x"], region["y"], region["w"], region["h"] = map(int, vals[:4])
            elif k == "orig":
                region["ow"], region["oh"] = int(vals[0]), int(vals[1])
            elif k == "offset":
                region["ox"], region["oy"] = int(vals[0]), int(vals[1])
            elif k == "offsets":
                region["ox"], region["oy"], region["ow"], region["oh"] = map(int, vals[:4])
            continue
        if line.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            page = {"file": line, "w": 0, "h": 0, "pma": False}
            pages.append(page)
            region = None
            continue
        region = {"page": len(pages) - 1, "deg": 0, "x": 0, "y": 0, "w": 0, "h": 0}
        regions[line] = region
    for r in regions.values():
        r.setdefault("ow", r["w"])
        r.setdefault("oh", r["h"])
        r.setdefault("ox", 0)
        r.setdefault("oy", 0)
        pg = pages[r["page"]]
        if not pg["w"]:
            from PyQt6.QtGui import QImageReader
            sz = QImageReader(str(path.parent / pg["file"])).size()
            pg["w"], pg["h"] = sz.width(), sz.height()
        pw, ph = max(1, pg["w"]), max(1, pg["h"])
        r["u"], r["v"] = r["x"] / pw, r["y"] / ph
        if r["deg"] == 90:
            r["u2"], r["v2"] = (r["x"] + r["h"]) / pw, (r["y"] + r["w"]) / ph
        else:
            r["u2"], r["v2"] = (r["x"] + r["w"]) / pw, (r["y"] + r["h"]) / ph
    return pages, regions


def _color(s, default=(1.0, 1.0, 1.0, 1.0)):
    if not s:
        return default
    s = s.strip("#")
    vals = [int(s[i:i + 2], 16) / 255 for i in range(0, min(8, len(s)), 2)]
    while len(vals) < 4:
        vals.append(1.0)
    return tuple(vals)


# ================================================================ courbes
def _bezier_y(t, t0, v0, t1, v1, c1x, c1y, c2x, c2y):
    """Valeur d'une courbe de Bézier (points de contrôle en temps/valeur absolus) au temps t."""
    lo, hi = 0.0, 1.0
    for _ in range(18):
        s = (lo + hi) / 2
        x = ((1 - s) ** 3) * t0 + 3 * ((1 - s) ** 2) * s * c1x + 3 * (1 - s) * s * s * c2x + s ** 3 * t1
        if x < t:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return ((1 - s) ** 3) * v0 + 3 * ((1 - s) ** 2) * s * c1y + 3 * (1 - s) * s * s * c2y + s ** 3 * v1


class Timeline:
    """Images clés d'une ou plusieurs valeurs : [(temps, [valeurs], courbe)]."""

    def __init__(self, keys, names, defaults, v4):
        self.keys = []
        for i, k in enumerate(keys):
            t = float(k.get("time", 0))
            vals = [float(k.get(n, d)) for n, d in zip(names, defaults)]
            self.keys.append([t, vals, k.get("curve"), k])
        self.v4 = v4
        self.n = len(names)

    def value(self, t):
        ks = self.keys
        if not ks:
            return None
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        i = 0
        while i + 1 < len(ks) and ks[i + 1][0] <= t:
            i += 1
        t0, a, curve, raw = ks[i]
        t1, b = ks[i + 1][0], ks[i + 1][1]
        if curve == "stepped":
            return a
        if t1 <= t0:
            return b
        p = (t - t0) / (t1 - t0)
        out = []
        for j in range(self.n):
            if isinstance(curve, list) and self.v4 and len(curve) >= 4 * (j + 1):
                c = curve[4 * j:4 * j + 4]
                out.append(_bezier_y(t, t0, a[j], t1, b[j], c[0], c[1], c[2], c[3]))
            elif (isinstance(curve, (int, float)) or isinstance(curve, list)) and not self.v4:
                c = curve if isinstance(curve, list) else [curve, raw.get("c2", 0), raw.get("c3", 1), raw.get("c4", 1)]
                out.append(_bezier_y(t, t0, a[j], t1, b[j], t0 + c[0] * (t1 - t0), a[j] + c[1] * (b[j] - a[j]),
                                     t0 + c[2] * (t1 - t0), a[j] + c[3] * (b[j] - a[j])))
            else:
                out.append(a[j] + (b[j] - a[j]) * p)
        return out


# ================================================================ squelette
class Skeleton:
    def __init__(self, json_path, atlas_path):
        self.path = str(json_path)
        d = json.loads(Path(json_path).read_text(encoding="utf-8"))
        ver = str((d.get("skeleton") or {}).get("spine", "3.8"))
        self.v4 = not ver.startswith(("2.", "3."))
        self.pages, self.regions = parse_atlas(atlas_path)
        self.atlas_dir = Path(atlas_path).parent
        # os
        self.bones = []
        self.bone_index = {}
        for b in d.get("bones", []):
            self.bone_index[b["name"]] = len(self.bones)
            self.bones.append({
                "name": b["name"], "parent": self.bone_index.get(b.get("parent")),
                "x": b.get("x", 0.0), "y": b.get("y", 0.0), "rot": b.get("rotation", 0.0),
                "sx": b.get("scaleX", 1.0), "sy": b.get("scaleY", 1.0),
                "shx": b.get("shearX", 0.0), "shy": b.get("shearY", 0.0),
                "inherit": b.get("inherit", b.get("transform", "normal"))})
        nb = len(self.bones)
        self.wa, self.wb, self.wc, self.wd = (np.ones(nb), np.zeros(nb), np.zeros(nb), np.ones(nb))
        self.wx, self.wy = np.zeros(nb), np.zeros(nb)
        # slots
        self.slots = []
        for s in d.get("slots", []):
            self.slots.append({"name": s["name"], "bone": self.bone_index.get(s.get("bone"), 0),
                               "color": _color(s.get("color")), "att": s.get("attachment"),
                               "blend": s.get("blend", "normal")})
        self.slot_index = {s["name"]: i for i, s in enumerate(self.slots)}
        # peaux
        skins = d.get("skins", {})
        if isinstance(skins, list):                          # Spine 4
            skins = {s["name"]: s.get("attachments", {}) for s in skins}
        self.skins = {}
        for sk, slots in skins.items():
            self.skins[sk] = {}
            for slot, atts in slots.items():
                for an, a in atts.items():
                    self.skins[sk][(slot, an)] = self._attachment(an, a)
        for sk in self.skins.values():                       # maillages liés
            for key, a in list(sk.items()):
                if a and a.get("type") == "linkedmesh":
                    src = self.skins.get(a.get("skin") or "default", {}).get((key[0], a["parent"])) or \
                          next((s.get((key[0], a["parent"])) for s in self.skins.values()
                                if s.get((key[0], a["parent"]))), None)
                    if src and src.get("type") == "mesh":
                        m = dict(src)
                        m["region"] = a["region"]
                        m["uvs_page"] = self._mesh_uvs(src["uvs"], a["region"]) if a["region"] else None
                        m["deform_from"] = src["key"] if a.get("deform", True) else None
                        m["key"] = a["key"]
                        sk[key] = m
                    else:
                        sk[key] = None
        names = [n for n in self.skins if n != "default"]
        self.skin_names = list(self.skins)
        self.skin = names[0] if names else "default"
        self.animations = d.get("animations", {})
        # événements avec un son (Spine 3.8 et 4.x) : chemin du fichier audio
        audio_dir = Path(json_path).parent / str((d.get("skeleton") or {}).get("audio", "") or "")
        self.event_audio = {}
        for en, ev in (d.get("events") or {}).items():
            a = ev.get("audio") if isinstance(ev, dict) else None
            if a:
                for cand in (audio_dir / a, Path(json_path).parent / a, Path(atlas_path).parent / a):
                    if cand.exists():
                        self.event_audio[en] = str(cand)
                        break
        self.anim_names = list(self.animations)
        self._compiled = {}
        self.textures = {}
        self.reset()

    # ---------- pièces jointes
    def _attachment(self, name, a):
        typ = a.get("type", "region")
        path = a.get("path", a.get("name", name))
        key = path + "#" + name
        if typ in ("region", "regionsequence"):
            r = self.regions.get(path)
            if not r:
                return None
            return {"type": "region", "region": r, "key": key, "color": _color(a.get("color")),
                    "x": a.get("x", 0.0), "y": a.get("y", 0.0), "rot": a.get("rotation", 0.0),
                    "sx": a.get("scaleX", 1.0), "sy": a.get("scaleY", 1.0),
                    "w": a.get("width", r["ow"]), "h": a.get("height", r["oh"])}
        if typ in ("mesh", "skinnedmesh", "weightedmesh"):
            r = self.regions.get(path)
            if not r:
                return None
            uvs = a["uvs"]
            verts = a["vertices"]
            weighted = len(verts) != len(uvs)
            m = {"type": "mesh", "region": r, "key": key, "color": _color(a.get("color")),
                 "uvs": uvs, "tris": np.array(a["triangles"], np.uint32), "weighted": weighted,
                 "n": len(uvs) // 2, "uvs_page": self._mesh_uvs(uvs, r)}
            if weighted:
                vid, bones, vx, vy, w = [], [], [], [], []
                i, v = 0, 0
                while i < len(verts):
                    cnt = int(verts[i])
                    i += 1
                    for _ in range(cnt):
                        vid.append(v)
                        bones.append(int(verts[i]))
                        vx.append(verts[i + 1])
                        vy.append(verts[i + 2])
                        w.append(verts[i + 3])
                        i += 4
                    v += 1
                m.update(vid=np.array(vid), wbones=np.array(bones), vx=np.array(vx, float), vy=np.array(vy, float),
                         w=np.array(w, float))
            else:
                m.update(lx=np.array(verts[0::2], float), ly=np.array(verts[1::2], float))
            return m
        if typ == "linkedmesh":
            return {"type": "linkedmesh", "parent": a.get("parent"), "skin": a.get("skin"),
                    "deform": a.get("deform", True), "region": self.regions.get(path), "key": key}
        if typ == "boundingbox":                             # zone cliquable
            verts = a.get("vertices", [])
            n = int(a.get("vertexCount", len(verts) // 2))
            b = {"type": "bbox", "name": name, "key": key, "n": n, "weighted": len(verts) != n * 2}
            if b["weighted"]:
                vid, bones, vx, vy, w = [], [], [], [], []
                i, v = 0, 0
                while i < len(verts):
                    cnt = int(verts[i])
                    i += 1
                    for _ in range(cnt):
                        vid.append(v)
                        bones.append(int(verts[i]))
                        vx.append(verts[i + 1])
                        vy.append(verts[i + 2])
                        w.append(verts[i + 3])
                        i += 4
                    v += 1
                b.update(vid=np.array(vid), wbones=np.array(bones), vx=np.array(vx, float),
                         vy=np.array(vy, float), w=np.array(w, float))
            else:
                b.update(lx=np.array(verts[0::2], float), ly=np.array(verts[1::2], float))
            return b
        return None                                          # chemins, découpe, points : ignorés

    def _mesh_uvs(self, uvs, r):
        pg = self.pages[r["page"]]
        tw, th = max(1, pg["w"]), max(1, pg["h"])
        uv = np.array(uvs, float).reshape(-1, 2)
        if r["deg"] == 90:
            u = r["u"] - (r["oh"] - r["oy"] - r["h"]) / tw
            v = r["v"] - (r["ow"] - r["ox"] - r["w"]) / th
            width, height = r["oh"] / tw, r["ow"] / th
            return np.stack([u + uv[:, 1] * width, v + (1 - uv[:, 0]) * height], 1).astype(np.float32)
        u = r["u"] - r["ox"] / tw
        v = r["v"] - (r["oh"] - r["oy"] - r["h"]) / th
        width, height = r["ow"] / tw, r["oh"] / th
        return np.stack([u + uv[:, 0] * width, v + uv[:, 1] * height], 1).astype(np.float32)

    def attachment(self, slot_i, name):
        if not name:
            return None
        key = (self.slots[slot_i]["name"], name)
        a = self.skins.get(self.skin, {}).get(key)
        if a is None:
            a = self.skins.get("default", {}).get(key)
        return a

    # ---------- pose
    def reset(self):
        self.pose = [dict(b) for b in self.bones]
        self.slot_att = [s["att"] for s in self.slots]
        self.slot_col = [s["color"] for s in self.slots]
        self.deform = {}
        self.order = list(range(len(self.slots)))

    def _compile(self, name):
        if name in self._compiled:
            return self._compiled[name]
        a = self.animations.get(name, {})
        v4 = self.v4
        bones = []
        for bn, tl in (a.get("bones") or {}).items():
            bi = self.bone_index.get(bn)
            if bi is None:
                continue
            for kind, keys in tl.items():
                kind = kind.lower()
                if kind == "rotate":
                    bones.append((bi, "rot", Timeline(keys, ["value" if v4 else "angle"], [0.0], v4)))
                elif kind in ("translate", "scale", "shear"):
                    d = 1.0 if kind == "scale" else 0.0
                    bones.append((bi, kind, Timeline(keys, ["x", "y"], [d, d], v4)))
                elif kind in ("translatex", "translatey", "scalex", "scaley", "shearx", "sheary"):
                    d = 1.0 if kind.startswith("scale") else 0.0
                    bones.append((bi, kind, Timeline(keys, ["value"], [d], v4)))
        slots = []
        for sn, tl in (a.get("slots") or {}).items():
            si = self.slot_index.get(sn)
            if si is None:
                continue
            for kind, keys in tl.items():
                if kind == "attachment":
                    slots.append((si, "att", [(float(k.get("time", 0)), k.get("name")) for k in keys]))
                elif kind in ("color", "rgba", "rgba2", "rgb", "two"):
                    ks = []
                    for k in keys:
                        c = _color(k.get("color") or k.get("light"))
                        ks.append(dict(k, r=c[0], g=c[1], b=c[2], a=c[3]))
                    slots.append((si, "col", Timeline(ks, ["r", "g", "b", "a"], [1, 1, 1, 1], v4)))
                elif kind == "alpha":
                    slots.append((si, "alpha", Timeline(keys, ["value"], [1.0], v4)))
        deforms = []
        if v4:
            for sk, sl in (a.get("attachments") or {}).items():
                for sn, atts in sl.items():
                    for an, tls in atts.items():
                        if "deform" in tls:
                            deforms.append((sk, sn, an, tls["deform"]))
        else:
            for sk, sl in (a.get("deform") or a.get("ffd") or {}).items():
                for sn, atts in sl.items():
                    for an, keys in atts.items():
                        deforms.append((sk, sn, an, keys))
        dfs = []
        for sk, sn, an, keys in deforms:
            si = self.slot_index.get(sn)
            att = self.skins.get(sk, {}).get((sn, an)) if si is not None else None
            if not att or att.get("type") != "mesh":
                continue
            size = len(att["vx"]) * 2 if att["weighted"] else att["n"] * 2
            ks = []
            for k in keys:
                arr = np.zeros(size)
                vs = k.get("vertices") or []
                off = int(k.get("offset", 0))
                arr[off:off + len(vs)] = vs[:max(0, size - off)]
                ks.append((float(k.get("time", 0)), arr, k.get("curve"), k))
            dfs.append((att["key"], ks))
        order = []
        for k in a.get("drawOrder") or a.get("draworder") or []:
            order.append((float(k.get("time", 0)), k.get("offsets")))
        dur = 0.0
        for _, _, tl in bones:
            dur = max(dur, tl.keys[-1][0] if tl.keys else 0)
        for s in slots:
            dur = max(dur, (s[2][-1][0] if s[1] == "att" else s[2].keys[-1][0]) if (s[2] if s[1] == "att"
                                                                                      else s[2].keys) else 0)
        for _, ks in dfs:
            dur = max(dur, ks[-1][0] if ks else 0)
        for t, _ in order:
            dur = max(dur, t)
        evs = sorted((float(k.get("time", 0)), k.get("name")) for k in a.get("events") or [])
        for et, _ in evs:
            dur = max(dur, et)
        c = {"bones": bones, "slots": slots, "deform": dfs, "order": order, "dur": max(dur, 0.001), "events": evs}
        self._compiled[name] = c
        return c

    def apply(self, name, t, loop=True):
        """Pose du squelette à l'instant t de l'animation (à partir de la pose de repos)."""
        self.reset()
        if not name or name not in self.animations:
            return 0.0
        c = self._compile(name)
        dur = c["dur"]
        tt = (t % dur) if loop else min(t, dur)
        for bi, kind, tl in c["bones"]:
            v = tl.value(tt)
            if v is None:
                continue
            b, s = self.pose[bi], self.bones[bi]
            if kind == "rot":
                b["rot"] = s["rot"] + v[0]
            elif kind == "translate":
                b["x"], b["y"] = s["x"] + v[0], s["y"] + v[1]
            elif kind == "scale":
                b["sx"], b["sy"] = s["sx"] * v[0], s["sy"] * v[1]
            elif kind == "shear":
                b["shx"], b["shy"] = s["shx"] + v[0], s["shy"] + v[1]
            elif kind == "translatex":
                b["x"] = s["x"] + v[0]
            elif kind == "translatey":
                b["y"] = s["y"] + v[0]
            elif kind == "scalex":
                b["sx"] = s["sx"] * v[0]
            elif kind == "scaley":
                b["sy"] = s["sy"] * v[0]
            elif kind == "shearx":
                b["shx"] = s["shx"] + v[0]
            elif kind == "sheary":
                b["shy"] = s["shy"] + v[0]
        for si, kind, data in c["slots"]:
            if kind == "att":
                cur = None
                for kt, nm in data:
                    if kt <= tt:
                        cur = (nm,)
                if cur is not None:
                    self.slot_att[si] = cur[0]
            elif kind == "col":
                v = data.value(tt)
                if v:
                    self.slot_col[si] = tuple(v)
            elif kind == "alpha":
                v = data.value(tt)
                if v:
                    r, g, b_, _ = self.slot_col[si]
                    self.slot_col[si] = (r, g, b_, v[0])
        for key, ks in c["deform"]:
            if not ks:
                continue
            if tt <= ks[0][0]:
                arr = ks[0][1]
            elif tt >= ks[-1][0]:
                arr = ks[-1][1]
            else:
                i = 0
                while i + 1 < len(ks) and ks[i + 1][0] <= tt:
                    i += 1
                t0, a0, curve, raw = ks[i]
                t1, a1 = ks[i + 1][0], ks[i + 1][1]
                if curve == "stepped":
                    p = 0.0
                elif isinstance(curve, list) and self.v4 and len(curve) >= 4:
                    p = _bezier_y(tt, t0, 0, t1, 1, curve[0], curve[1], curve[2], curve[3])
                elif curve is not None and not self.v4:
                    cv = curve if isinstance(curve, list) else [curve, raw.get("c2", 0), raw.get("c3", 1),
                                                                raw.get("c4", 1)]
                    p = _bezier_y(tt, t0, 0, t1, 1, t0 + cv[0] * (t1 - t0), cv[1], t0 + cv[2] * (t1 - t0), cv[3])
                else:
                    p = (tt - t0) / max(1e-6, t1 - t0)
                arr = a0 + (a1 - a0) * p
            self.deform[key] = arr
        if c["order"]:
            cur = None
            for kt, offs in c["order"]:
                if kt <= tt:
                    cur = offs
            if cur:
                self.order = self._draw_order(cur)
        return dur

    def _draw_order(self, offsets):
        n = len(self.slots)
        order = [-1] * n
        unchanged = []
        orig = 0
        for o in offsets:
            si = self.slot_index.get(o.get("slot"))
            if si is None:
                continue
            while orig != si:
                unchanged.append(orig)
                orig += 1
            order[orig + int(o.get("offset", 0))] = orig
            orig += 1
        while orig < n:
            unchanged.append(orig)
            orig += 1
        for i in range(n - 1, -1, -1):
            if order[i] == -1:
                order[i] = unchanged.pop() if unchanged else i
        return order

    def update_world(self, extra_rot=None):
        """Matrices monde des os (mode d'héritage « normal » ; « onlyTranslation » géré)."""
        rad = math.radians
        for i, b in enumerate(self.pose):
            rot = b["rot"] + (extra_rot.get(i, 0.0) if extra_rot else 0.0)
            rx = rad(rot + b["shx"])
            ry = rad(rot + 90 + b["shy"])
            la, lb = math.cos(rx) * b["sx"], math.cos(ry) * b["sy"]
            lc, ld = math.sin(rx) * b["sx"], math.sin(ry) * b["sy"]
            p = b["parent"]
            if p is None:
                self.wa[i], self.wb[i], self.wc[i], self.wd[i] = la, lb, lc, ld
                self.wx[i], self.wy[i] = b["x"], b["y"]
                continue
            pa, pb, pc, pd = self.wa[p], self.wb[p], self.wc[p], self.wd[p]
            self.wx[i] = pa * b["x"] + pb * b["y"] + self.wx[p]
            self.wy[i] = pc * b["x"] + pd * b["y"] + self.wy[p]
            if b["inherit"] == "onlyTranslation":
                self.wa[i], self.wb[i], self.wc[i], self.wd[i] = la, lb, lc, ld
            else:
                self.wa[i], self.wb[i] = pa * la + pb * lc, pa * lb + pb * ld
                self.wc[i], self.wd[i] = pc * la + pd * lc, pc * lb + pd * ld

    def hit(self, x, y):
        """Nom de la zone cliquable (boîte « boundingbox ») sous le point, en coordonnées du squelette."""
        found = None
        for si in self.order:
            att = self.attachment(si, self.slot_att[si])
            if not att or att.get("type") != "bbox":
                continue
            bi = self.slots[si]["bone"]
            if att["weighted"]:
                bo = att["wbones"]
                px = (att["vx"] * self.wa[bo] + att["vy"] * self.wb[bo] + self.wx[bo]) * att["w"]
                py = (att["vx"] * self.wc[bo] + att["vy"] * self.wd[bo] + self.wy[bo]) * att["w"]
                xs, ys = np.bincount(att["vid"], px, att["n"]), np.bincount(att["vid"], py, att["n"])
            else:
                xs = att["lx"] * self.wa[bi] + att["ly"] * self.wb[bi] + self.wx[bi]
                ys = att["lx"] * self.wc[bi] + att["ly"] * self.wd[bi] + self.wy[bi]
            inside = False
            j = len(xs) - 1
            for i in range(len(xs)):                          # point dans le polygone
                if (ys[i] > y) != (ys[j] > y) and x < (xs[j] - xs[i]) * (y - ys[i]) / (ys[j] - ys[i] + 1e-9) + xs[i]:
                    inside = not inside
                j = i
            if inside:
                found = att["name"] or self.slots[si]["name"]      # la plus haute dans l'ordre d'affichage
        return found

    def draw_list(self):
        """[(page, positions Nx2, uvs Nx2, triangles, couleur rgba, mode de fusion)] dans l'ordre d'affichage."""
        out = []
        for si in self.order:
            s = self.slots[si]
            att = self.attachment(si, self.slot_att[si])
            if not att or att.get("type") == "bbox":
                continue
            sc = self.slot_col[si]
            ac = att["color"]
            col = (sc[0] * ac[0], sc[1] * ac[1], sc[2] * ac[2], sc[3] * ac[3])
            if col[3] <= 0.002:
                continue
            bi = s["bone"]
            a, b, c, d, x, y = self.wa[bi], self.wb[bi], self.wc[bi], self.wd[bi], self.wx[bi], self.wy[bi]
            r = att["region"]
            if att["type"] == "region":
                pos, uv = self._region_quad(att, a, b, c, d, x, y)
                tris = np.array([0, 1, 2, 2, 3, 0], np.uint32)
            else:
                dk = att.get("deform_from") or att["key"]
                df = self.deform.get(dk)
                if att["weighted"]:
                    vx, vy = att["vx"], att["vy"]
                    if df is not None and len(df) == 2 * len(vx):
                        vx, vy = vx + df[0::2], vy + df[1::2]
                    bo = att["wbones"]
                    px = (vx * self.wa[bo] + vy * self.wb[bo] + self.wx[bo]) * att["w"]
                    py = (vx * self.wc[bo] + vy * self.wd[bo] + self.wy[bo]) * att["w"]
                    n = att["n"]
                    pos = np.stack([np.bincount(att["vid"], px, n), np.bincount(att["vid"], py, n)], 1)
                else:
                    lx, ly = att["lx"], att["ly"]
                    if df is not None and len(df) == 2 * len(lx):
                        lx, ly = lx + df[0::2], ly + df[1::2]
                    pos = np.stack([lx * a + ly * b + x, lx * c + ly * d + y], 1)
                uv = att.get("uvs_page")
                if uv is None:
                    continue
                tris = att["tris"]
            out.append((r["page"], pos.astype(np.float32), uv, tris, col, s["blend"]))
        return out

    def _region_quad(self, att, a, b, c, d, x, y):
        r = att["region"]
        w, h = att["w"], att["h"]
        rsx = w / max(1, r["ow"]) * att["sx"]
        rsy = h / max(1, r["oh"]) * att["sy"]
        lx = -w / 2 * att["sx"] + r["ox"] * rsx
        ly = -h / 2 * att["sy"] + r["oy"] * rsy
        lx2, ly2 = lx + r["w"] * rsx, ly + r["h"] * rsy
        cs, sn = math.cos(math.radians(att["rot"])), math.sin(math.radians(att["rot"]))
        ax, ay = att["x"], att["y"]
        loc = [(lx * cs - ly * sn + ax, ly * cs + lx * sn + ay),       # bas gauche
               (lx * cs - ly2 * sn + ax, ly2 * cs + lx * sn + ay),     # haut gauche
               (lx2 * cs - ly2 * sn + ax, ly2 * cs + lx2 * sn + ay),   # haut droit
               (lx2 * cs - ly * sn + ax, ly * cs + lx2 * sn + ay)]     # bas droit
        pos = np.array([(px * a + py * b + x, px * c + py * d + y) for px, py in loc], np.float32)
        u, v, u2, v2 = r["u"], r["v"], r["u2"], r["v2"]
        if r["deg"] == 90:
            uv = np.array([(u2, v2), (u, v2), (u, v), (u2, v)], np.float32)
        else:
            uv = np.array([(u, v2), (u, v), (u2, v), (u2, v2)], np.float32)
        return pos, uv


# ================================================================ modèle affiché
ANIM_HINTS = {"idle": ("idle", "wait", "stand", "loop", "breath", "normal", "default"),
              "talk": ("talk", "speak", "say", "voice"),
              "joie": ("happy", "joy", "smile", "laugh", "fun", "win", "victory", "good"),
              "triste": ("sad", "cry", "lose", "down"),
              "boude": ("angry", "mad", "anger"),
              "surprise": ("surprise", "shock", "wow"),
              "timide": ("shy", "blush", "embarrass"),
              "tap": ("touch", "tap", "click", "react", "poke", "action", "special")}


def pick_anim(names, kind):
    keys = ANIM_HINTS.get(kind, ())
    for k in keys:
        for n in names:
            if k in n.lower():
                return n
    return None


class SpineModel:
    """Même interface que live2d_rendu.Live2DModel : resize(), frame(), emote(), tap()."""

    def __init__(self, json_path, atlas_path, idle=None, skin=None):
        ok, why = available()
        if not ok:
            raise RuntimeError("PyOpenGL manquant : " + why)
        self.path = str(json_path)
        self.sk = Skeleton(json_path, atlas_path)
        if skin and skin in self.sk.skins:
            self.sk.skin = skin
        names = self.sk.anim_names
        self.idle = idle if idle in names else (pick_anim(names, "idle") or (names[0] if names else None))
        self.talk = pick_anim(names, "talk")
        self.head = next((i for i, b in enumerate(self.sk.bones)
                          if b["name"].lower() in ("head", "tete", "face", "kao", "atama")), None)
        self.cur, self.cur_t0, self.once = self.idle, time.monotonic(), False
        self.random_moves = True
        self.next_random = time.monotonic() + random.uniform(20, 40)
        self.on_sound = None
        self._ev_name, self._ev_t = None, -1.0
        self.reason = "clic"
        self.look = 0.0
        self.fbo = None
        self.size = (0, 0)
        self.tex = {}
        self.bounds = self._bounds()

    def _bounds(self):
        """Rectangle qui contient le personnage pendant TOUTES ses animations (rien n'est coupé)."""
        mins, maxs = [], []
        anims = ([self.idle] if self.idle else []) + [a for a in self.sk.anim_names if a != self.idle][:30]
        for a in anims or [None]:
            dur = self.sk._compile(a)["dur"] if a else 0
            n = 8 if a == self.idle else 5
            for k in range(n if a else 1):
                self.sk.apply(a, dur * k / max(1, n - 1), loop=False)
                self.sk.update_world()
                for _, pos, _, _, col, _ in self.sk.draw_list():
                    if len(pos):
                        mins.append(pos.min(0))
                        maxs.append(pos.max(0))
        if not mins:
            raise RuntimeError("le modèle ne contient rien à afficher (atlas qui ne correspond pas ?)")
        lo, hi = np.min(mins, 0), np.max(maxs, 0)
        pad = 0.05 * max(hi[0] - lo[0], hi[1] - lo[1])
        return float(lo[0] - pad), float(lo[1] - pad), float(hi[0] + pad), float(hi[1] + pad)

    def aspect(self):
        x0, y0, x1, y1 = self.bounds
        return (x1 - x0) / max(1e-6, y1 - y0)

    def resize(self, w, h):
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject
        w, h = max(16, int(w)), max(16, int(h))
        if (w, h) == self.size:
            return
        _context()
        self.fbo = QOpenGLFramebufferObject(w, h)
        self.size = (w, h)

    def _texture(self, page):
        if page in self.tex:
            return self.tex[page]
        from PyQt6.QtGui import QImage
        GL = _GL
        pg = self.sk.pages[page]
        img = QImage(str(self.sk.atlas_dir / pg["file"])).convertToFormat(QImage.Format.Format_RGBA8888)
        tid = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, img.width(), img.height(), 0, GL.GL_RGBA,
                        GL.GL_UNSIGNED_BYTE, img.constBits().asstring(img.sizeInBytes()))
        self.tex[page] = tid
        return tid

    def play(self, name, once=True, reason="clic"):
        if name:
            self.cur, self.cur_t0, self.once = name, time.monotonic(), once
            self.reason = reason
            self._ev_name, self._ev_t = name, -1.0

    def hit(self, px, py):
        """Zone cliquable sous un point de l'image rendue (pixels)."""
        if not self.size[0]:
            return None
        x0, y0, x1, y1 = self.bounds
        x = x0 + px / self.size[0] * (x1 - x0)
        y = y1 - py / self.size[1] * (y1 - y0)
        return self.sk.hit(x, y)

    def tap_area(self, area):
        a = (area or "").lower()
        anim = next((n for n in self.sk.anim_names if a and a in n.lower()), None)
        self.play(anim or pick_anim(self.sk.anim_names, "tap"))
        self._voice(a, anim or "")

    def close(self):
        try:
            GL = _GL
            _context()
            for tid in self.tex.values():
                GL.glDeleteTextures([tid])
            self.tex = {}
            self.fbo = None
        except Exception:
            pass

    def set_voice_pool(self, root):
        try:
            from live2d_rendu import voice_pool
        except Exception:
            return
        self.voices = voice_pool(root, self.sk.event_audio.values())

    def _voice(self, *hints):
        pool = getattr(self, "voices", [])
        if not pool or not self.on_sound or self.sk.event_audio:
            return
        try:
            from live2d_rendu import pick_voice
            v = pick_voice(pool, *hints)
            if v:
                self.on_sound(str(v), "clic")
        except Exception:
            pass

    def tap(self):
        self.play(pick_anim(self.sk.anim_names, "tap"))
        self._voice(pick_anim(self.sk.anim_names, "tap") or "")

    def emote(self, emo):
        self.play(pick_anim(self.sk.anim_names, emo))
        self._voice(emo)

    def frame(self, look=(0.0, 0.0), mouth=0.0, eyes=None, smile=0.0, body=0.0):
        from PyQt6.QtGui import QImage
        GL = _GL
        _context()
        now = time.monotonic()
        t = now - self.cur_t0
        if self.once:
            dur = self.sk._compile(self.cur)["dur"] if self.cur else 0
            if t >= dur:
                self.cur, self.cur_t0, self.once, t = self.idle, now, False, 0.0
        if self.random_moves and not self.once and now > self.next_random:
            self.next_random = now + random.uniform(25, 60)
            others = [a for a in self.sk.anim_names if a not in (self.idle, self.talk)]
            if others:
                self.play(random.choice(others), reason="hasard")
                t = 0.0
        name = self.cur
        if not self.once and mouth > 0.01 and self.talk:
            name = self.talk
        self.sk.apply(name, t, loop=not self.once)
        if self.on_sound and self.sk.event_audio and name:          # sons des événements de l'animation
            evs = self.sk._compile(name)["events"]
            dur = self.sk._compile(name)["dur"]
            tt = t if self.once else t % dur
            if self._ev_name != name or tt < self._ev_t:
                self._ev_name, self._ev_t = name, -1e-6
            for et, en in evs:
                if self._ev_t < et <= tt and en in self.sk.event_audio:
                    self.on_sound(self.sk.event_audio[en], self.reason if self.once else "repos")
            self._ev_t = tt
        self.look += (look[0] - self.look) * 0.15
        extra = {self.head: -self.look * 8} if self.head is not None else None
        self.sk.update_world(extra)
        w, h = self.size
        self.fbo.bind()
        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        x0, y0, x1, y1 = self.bounds
        GL.glOrtho(x0, x1, y0, y1, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glEnable(GL.GL_BLEND)
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_TEXTURE_COORD_ARRAY)
        for page, pos, uv, tris, col, blend in self.sk.draw_list():
            pma = self.sk.pages[page]["pma"]
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture(page))
            if blend == "additive":
                GL.glBlendFunc(GL.GL_ONE if pma else GL.GL_SRC_ALPHA, GL.GL_ONE)
            elif pma:
                GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
            else:
                GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE,
                                       GL.GL_ONE_MINUS_SRC_ALPHA)
            if pma:
                GL.glColor4f(col[0] * col[3], col[1] * col[3], col[2] * col[3], col[3])
            else:
                GL.glColor4f(*col)
            GL.glVertexPointer(2, GL.GL_FLOAT, 0, np.ascontiguousarray(pos, np.float32))
            GL.glTexCoordPointer(2, GL.GL_FLOAT, 0, np.ascontiguousarray(uv, np.float32))
            idx = np.ascontiguousarray(tris, np.uint32)
            GL.glDrawElements(GL.GL_TRIANGLES, len(idx), GL.GL_UNSIGNED_INT, idx)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glDisableClientState(GL.GL_TEXTURE_COORD_ARRAY)
        img = self.fbo.toImage()
        self.fbo.release()
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def render_preview(json_path, atlas_path, out_png, h=1000, idle=None, skin=None):
    """Aperçu + infos pour character.json (même forme que live2d_rendu.render_preview)."""
    m = SpineModel(json_path, atlas_path, idle, skin)
    w = int(round(h * m.aspect()))
    m.resize(w, h)
    img = m.frame()
    img.save(str(out_png))
    eye_y = h * 0.12
    cx = w / 2
    d = max(14.0, w * 0.09)
    return {"canvas": [w, h], "crop": [0, 0, w, h], "size": [w, h], "idle": m.idle,
            "anims": m.sk.anim_names, "skins": m.sk.skin_names, "skin": m.sk.skin,
            "eyes": [{"x": cx - d / 2, "y": eye_y, "w": d * 0.55, "h": d * 0.3},
                     {"x": cx + d / 2, "y": eye_y, "w": d * 0.55, "h": d * 0.3}],
            "mouth": {"x": cx, "y": eye_y + d * 0.9, "w": d * 0.5, "max_open": d * 0.3}}
