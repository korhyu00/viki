"""Mode marionnette : anime la tête, les bras et le buste d'après un rig.json
(pivots, calques, animations), en déformant l'image d'origine du personnage.

Les calques du rig ne sont pas dessinés tels quels : ils servent à savoir quelle partie
de l'image suit quel os. On garde ainsi l'image entière, sans trous ni bords
découpés quand un bras ou la tête tourne.

Format attendu (celui de lilas_puppet) :
  canvas {width, height}, layers {nom: {file, bbox [x0,y0,x1,y1], pivot {x,y}, parent, z_index}},
  animations {nom: {type: sinusoidal, target, property: rotation|scale_y, amplitude, frequency, phase}},
  interactions {mouse_follow: {target, max_angle}}
"""
import json
import math
from pathlib import Path

import numpy as np

COARSE = 4          # les cartes de poids sont calculées en 1/4 de résolution

# Mouvements scriptés (comme les « motions » Live2D) : pour chaque canal, des images clés (temps s, valeur).
# Canaux : head (°), arm_left / arm_right (°, + = vers la droite de l'écran), skirt (°), sway (° du buste).
# Les bras pendent : arm_left > 0 l'écarte du corps, arm_right < 0 aussi.
_W = [(0.0, 0), (0.35, -32), (0.55, -22), (0.75, -36), (0.95, -22), (1.15, -36), (1.35, -24), (1.8, 0)]
MOTIONS = {
    "salut": {"len": 1.8, "arm_right": _W, "head": [(0, 0), (0.4, 5), (1.4, 4), (1.8, 0)],
              "sway": [(0, 0), (0.4, 1.2), (1.4, 1), (1.8, 0)]},
    "main": {"len": 1.6, "arm_right": [(0, 0), (0.3, -28), (0.5, -18), (0.7, -30), (0.9, -18), (1.1, -28), (1.6, 0)],
             "head": [(0, 0), (0.3, 4), (1.2, 4), (1.6, 0)]},
    "etirement": {"len": 2.0, "arm_left": [(0, 0), (0.6, 24), (1.4, 26), (2.0, 0)],
                  "arm_right": [(0, 0), (0.6, -24), (1.4, -26), (2.0, 0)],
                  "head": [(0, 0), (0.6, -5), (1.4, -6), (2.0, 0)], "skirt": [(0, 0), (0.7, 1.5), (2.0, 0)]},
    "regarde": {"len": 1.9, "head": [(0, 0), (0.45, 9), (0.9, 9), (1.35, -9), (1.7, -8), (1.9, 0)],
                "sway": [(0, 0), (0.45, 1.2), (1.35, -1.2), (1.9, 0)]},
    "fredonne": {"len": 2.6, "head": "osc:5:2.2", "sway": "osc:2:1.1", "skirt": "osc:3:2.2",
                 "arm_left": "osc:5:1.1", "arm_right": "osc:5:1.1"},
    "pieds": {"len": 1.8, "head": "osc:6:2.5", "sway": "osc:3:2.5", "skirt": "osc:5:2.5",
              "arm_left": "osc:9:2.5", "arm_right": "osc:-9:2.5"},
    "danse": {"len": 4.0, "head": "osc:7:2", "sway": "osc:3.5:1", "skirt": "osc:6:2",
              "arm_left": "osc:14:2", "arm_right": "osc:14:2"},
    "cheveux": {"len": 1.8, "head": [(0, 0), (0.3, 8), (0.7, -6), (1.1, 5), (1.8, 0)]},
    "joue": {"len": 2.0, "head": [(0, 0), (0.4, -9), (1.5, -8), (2.0, 0)],
             "arm_left": [(0, 0), (0.4, -6), (1.5, -6), (2.0, 0)], "arm_right": [(0, 0), (0.4, 6), (1.5, 6), (2.0, 0)],
             "sway": "osc:1.5:1"},
    "timide": {"len": 2.4, "head": [(0, 0), (0.4, -10), (2.0, -9), (2.4, 0)],
               "arm_left": [(0, 0), (0.4, -7), (2.0, -7), (2.4, 0)], "arm_right": [(0, 0), (0.4, 7), (2.0, 7), (2.4, 0)]},
    "surprise": {"len": 1.4, "arm_left": [(0, 0), (0.15, 18), (0.9, 16), (1.4, 0)],
                 "arm_right": [(0, 0), (0.15, -18), (0.9, -16), (1.4, 0)], "head": [(0, 0), (0.15, -4), (1.4, 0)],
                 "skirt": [(0, 0), (0.2, -3), (0.5, 2), (0.9, -1), (1.4, 0)]},
    "epaule": {"len": 1.0, "arm_left": [(0, 0), (0.12, 12), (1.0, 0)], "arm_right": [(0, 0), (0.12, -12), (1.0, 0)],
               "skirt": [(0, 0), (0.2, -3), (0.5, 2), (1.0, 0)]},
    "reflexion": {"len": 3.0, "head": [(0, 0), (0.5, 11), (2.5, 10), (3.0, 0)],
                  "arm_right": [(0, 0), (0.5, 8), (2.5, 8), (3.0, 0)], "sway": [(0, 0), (0.5, -1), (2.5, -1), (3.0, 0)]},
    "content": {"len": 1.6, "arm_left": [(0, 0), (0.25, 14), (0.5, 6), (0.75, 14), (1.6, 0)],
                "arm_right": [(0, 0), (0.25, -14), (0.5, -6), (0.75, -14), (1.6, 0)], "head": "osc:4:2",
                "skirt": "osc:4:2"},
    "triste": {"len": 2.5, "head": [(0, 0), (0.6, -7), (2.0, -7), (2.5, 0)],
               "arm_left": [(0, 0), (0.6, -3), (2.0, -3), (2.5, 0)], "arm_right": [(0, 0), (0.6, 3), (2.0, 3), (2.5, 0)]},
    "vertige": {"len": 2.8, "head": "osc:9:1.2", "sway": "osc:2.5:1.2"},
    "atterrissage": {"len": 0.7, "arm_left": [(0, 0), (0.1, 10), (0.7, 0)], "arm_right": [(0, 0), (0.1, -10), (0.7, 0)],
                     "skirt": [(0, 0), (0.1, -4), (0.35, 3), (0.7, 0)]},
    "caresse": {"len": 2.0, "head": "osc:3:0.8"},
    "bras": {"len": 1.8, "sway": [(0, 0), (0.4, 2), (1.3, 2), (1.8, 0)], "head": [(0, 0), (0.4, 4), (1.8, 0)]},
    "accessoire": {"len": 1.6, "arm_left": [(0, 0), (0.3, 16), (1.2, 14), (1.6, 0)], "head": [(0, 0), (0.3, 6), (1.6, 0)]},
    "nez": {"len": 0.8, "head": [(0, 0), (0.1, -5), (0.8, 0)]},
    "tete": {"len": 1.5, "head": "osc:3:1.5"},
    # --- nouveaux mouvements
    "victoire": {"len": 2.0, "arm_left": [(0, 0), (0.25, 38), (0.5, 30), (0.75, 40), (1.5, 36), (2.0, 0)],
                 "arm_right": [(0, 0), (0.25, -38), (0.5, -30), (0.75, -40), (1.5, -36), (2.0, 0)],
                 "head": [(0, 0), (0.25, -4), (1.5, -4), (2.0, 0)], "skirt": "osc:4:3", "sway": "osc:1.5:2"},
    "rire": {"len": 1.8, "head": "osc:4:4.5", "sway": "osc:1.6:4.5", "skirt": "osc:2:4.5",
             "arm_left": [(0, 0), (0.3, -5), (1.4, -5), (1.8, 0)], "arm_right": [(0, 0), (0.3, 5), (1.4, 5), (1.8, 0)]},
    "non": {"len": 1.3, "head": "osc:7:2.6"},
    "oui": {"len": 1.2, "head": [(0, 0), (0.2, 4), (0.4, 0), (0.6, 4), (0.8, 0), (1.2, 0)],
            "sway": [(0, 0), (0.2, 0.8), (0.4, 0), (0.6, 0.8), (0.8, 0), (1.2, 0)]},
    "applaudit": {"len": 2.0, "arm_left": "osc:-7:3.5", "arm_right": "osc:7:3.5", "head": [(0, 0), (0.3, 4), (1.6, 4), (2.0, 0)]},
    "fatigue": {"len": 3.0, "head": [(0, 0), (0.8, -8), (1.6, -6), (2.2, -9), (3.0, 0)],
                "arm_left": [(0, 0), (0.8, -4), (2.2, -4), (3.0, 0)], "arm_right": [(0, 0), (0.8, 4), (2.2, 4), (3.0, 0)],
                "sway": [(0, 0), (1.0, -1.2), (2.2, -1.2), (3.0, 0)]},
    "defile": {"len": 3.2, "sway": [(0, 0), (0.6, 2.5), (1.4, -2.5), (2.2, 2.5), (3.2, 0)],
               "skirt": [(0, 0), (0.6, 6), (1.0, -4), (1.4, -6), (1.8, 4), (2.2, 6), (2.6, -3), (3.2, 0)],
               "arm_left": [(0, 0), (0.6, 14), (2.6, 14), (3.2, 0)], "arm_right": [(0, 0), (0.6, -6), (1.4, -14), (2.6, -10), (3.2, 0)],
               "head": [(0, 0), (0.6, 6), (1.4, -6), (2.2, 6), (3.2, 0)]},
    "coucou2": {"len": 2.0, "arm_left": [(0, 0), (0.3, 30), (0.5, 20), (0.7, 32), (0.9, 20), (1.1, 32), (1.5, 26), (2.0, 0)],
                "arm_right": _W[:-1] + [(2.0, 0)], "head": [(0, 0), (0.4, 3), (1.5, 3), (2.0, 0)]},
    "boude": {"len": 2.6, "head": [(0, 0), (0.3, -12), (2.2, -11), (2.6, 0)], "sway": [(0, 0), (0.3, -2), (2.2, -2), (2.6, 0)],
              "arm_left": [(0, 0), (0.3, -10), (2.2, -10), (2.6, 0)], "arm_right": [(0, 0), (0.3, 10), (2.2, 10), (2.6, 0)]},
}
# noms français pour les commandes (« fais coucou », « danse »…)
MOTION_NAMES = {"coucou": "salut", "salut": "salut", "danse": "danse", "etire": "etirement", "timide": "timide",
                "surprise": "surprise", "reflechis": "reflexion", "content": "content", "triste": "triste",
                "regarde": "regarde", "penche": "cheveux", "victoire": "victoire", "ris": "rire", "rigole": "rire",
                "non": "non", "oui": "oui", "applaudis": "applaudit", "fatiguee": "fatigue", "defile": "defile",
                "tourne": "defile", "boude": "boude", "deux mains": "coucou2"}


def _ease(u):
    return u * u * (3 - 2 * u)


def motion_value(spec, d, length):
    """Valeur d'un canal à l'instant d (s) : images clés, ou « osc:amplitude:fréquence »."""
    if isinstance(spec, str) and spec.startswith("osc:"):
        _o, amp, freq = spec.split(":")
        env = min(1.0, d / 0.25) * min(1.0, max(0.0, (length - d) / 0.35))
        return float(amp) * math.sin(2 * math.pi * float(freq) * d) * env
    if not spec:
        return 0.0
    if d <= spec[0][0]:
        return float(spec[0][1])
    for (t0, v0), (t1, v1) in zip(spec, spec[1:]):
        if d <= t1:
            u = (d - t0) / max(1e-6, t1 - t0)
            return v0 + (v1 - v0) * _ease(u)
    return float(spec[-1][1])


def _qimage_alpha(path):
    from PyQt6.QtGui import QImage
    im = QImage(str(path)).convertToFormat(QImage.Format.Format_ARGB32)
    w, h = im.width(), im.height()
    arr = np.frombuffer(im.constBits().asstring(im.sizeInBytes()), np.uint8).reshape(h, im.bytesPerLine())
    return arr[:, :w * 4].reshape(h, w, 4)[:, :, 3].astype(np.float32) / 255.0


def _blur(a, r):
    """Flou boîte séparable (2 passes ≈ gaussien), rayon r en cases."""
    if r < 1:
        return a
    for _ in range(2):
        for ax in (0, 1):
            c = np.cumsum(np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in range(2)], mode="edge"), axis=ax)
            if ax == 0:
                a = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
            else:
                a = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return a


def find_rig(char_dir):
    for p in (Path(char_dir) / "marionnette" / "rig.json", Path(char_dir) / "rig.json"):
        if p.exists():
            return p
    return None


class Rig:
    BONES = ("head", "arm_left", "arm_right", "skirt")

    def __init__(self, rig_path, src_w, src_h, geo=None):
        """geo : silhouette modifiée (apparence.Geo) ; src_w est alors la largeur d'origine de l'image."""
        self.path = Path(rig_path)
        d = json.loads(self.path.read_text(encoding="utf-8"))
        self.data = d
        cw = float(d.get("canvas", {}).get("width", src_w)) or src_w
        self.k = src_w / cw                                   # canvas -> pixels de l'image du personnage
        self.w, self.h = src_w, src_h
        L = d.get("layers", {})
        self.pivots = {n: (l["pivot"]["x"] * self.k, l["pivot"]["y"] * self.k) for n, l in L.items()
                       if isinstance(l.get("pivot"), dict)}
        self.root = next((n for n, l in L.items() if not l.get("parent")), "torso")
        self.anims = d.get("animations", {})
        self.follow = d.get("interactions", {}).get("mouse_follow", {})
        # cartes de poids (quelle part de l'image suit chaque os)
        gh, gw = int(src_h / COARSE) + 1, int(src_w / COARSE) + 1
        self.gw, self.gh = gw, gh
        self.weights = {}
        tot = np.zeros((gh, gw), np.float32)
        for name in self.BONES:
            l = L.get(name)
            if not l or name not in self.pivots:
                continue
            m = np.zeros((gh, gw), np.float32)
            try:
                a = _qimage_alpha(self.path.parent / l["file"])
            except Exception:
                continue
            x0, y0 = l["bbox"][0] * self.k, l["bbox"][1] * self.k
            sub = a[::max(1, int(round(COARSE / self.k))), ::max(1, int(round(COARSE / self.k)))]
            gx0, gy0 = int(x0 / COARSE), int(y0 / COARSE)
            hh, ww = min(sub.shape[0], gh - gy0), min(sub.shape[1], gw - gx0)
            if hh > 0 and ww > 0:
                m[gy0:gy0 + hh, gx0:gx0 + ww] = (sub[:hh, :ww] > 0.4)
            m = _blur(m, max(2, int(30 * self.k / COARSE)))      # transition douce (~30 px)
            px, py = self.pivots[name]
            ys = (np.arange(gh) * COARSE)[:, None]
            if name == "head":                                    # sous le cou : on relâche vite
                m *= np.clip(1 - (ys - py) / (45 * self.k), 0, 1)
            else:                                                 # au-dessus de l'épaule : rien
                m *= np.clip(1 - (py - ys) / (40 * self.k), 0, 1)
            self.weights[name] = m
            tot += m
        over = np.maximum(tot, 1.0)
        for n in self.weights:
            self.weights[n] /= over
        if geo is not None and geo.active():                     # corps élargi ou affiné : on suit l'image
            gw1 = int(geo.w / COARSE) + 1
            xs1 = np.arange(gw1, dtype=np.float32) * COARSE
            for n, m in list(self.weights.items()):
                m2 = np.zeros((gh, gw1), np.float32)
                for j in range(gh):
                    sx = geo.inv(xs1, j * COARSE) / COARSE
                    m2[j] = np.interp(sx, np.arange(gw), m[j], left=0.0, right=0.0)
                self.weights[n] = m2
            tot2 = np.zeros((gh, gw1), np.float32)
            for j in range(gh):
                sx = geo.inv(xs1, j * COARSE) / COARSE
                tot2[j] = np.interp(sx, np.arange(gw), tot[j], left=0.0, right=0.0)
            tot = tot2
            self.gw = gw1
            self.w = geo.w
            self.pivots = {n: (float(geo.fwd(x, y)), y) for n, (x, y) in self.pivots.items()}
        # jusqu'où l'image bouge (en dessous : on dessine d'un seul bloc)
        moving = tot > 0.003
        rows = np.where(moving.any(axis=1))[0]
        ry = self.pivots.get(self.root, (0, src_h * 0.47))[1]
        self.moving_bottom = min(src_h, max(ry, (rows.max() + 1) * COARSE if len(rows) else 0) + 24 * self.k)

    def weight_at(self, name, x, y):
        m = self.weights.get(name)
        if m is None:
            return 0.0
        fx, fy = x / COARSE, y / COARSE
        i0, j0 = int(min(max(fx, 0), self.gw - 2)), int(min(max(fy, 0), self.gh - 2))
        u, v = min(max(fx - i0, 0), 1), min(max(fy - j0, 0), 1)
        return float(m[j0, i0] * (1 - u) * (1 - v) + m[j0, i0 + 1] * u * (1 - v)
                     + m[j0 + 1, i0] * (1 - u) * v + m[j0 + 1, i0 + 1] * u * v)

    # ------------------------------------------------------------ pose
    def _sin(self, target, prop, t, mult=1.0):
        val = 0.0
        for a in self.anims.values():
            if a.get("target") == target and a.get("property") == prop and a.get("type", "sinusoidal") == "sinusoidal":
                val += (float(a.get("amplitude", 0)) * mult
                        * math.sin(2 * math.pi * float(a.get("frequency", 0.5)) * t
                                   + math.radians(float(a.get("phase", 0)))))
        return val

    def pose(self, t, gaze_x=0.0, force=1.0, walking=0.0, talking=0.0, motion=None, idle=True):
        """Paramètres de l'instant t : {breath (échelle verticale du buste), head (°), arm_left, arm_right,
        skirt (°), sway (° du buste)}. motion = (nom, secondes écoulées) d'un mouvement scripté."""
        p = self._pose(t, gaze_x, force, walking, talking)
        if idle and force:                                       # vie au repos : buste et jupe qui ondulent
            p["sway"] += 0.7 * force * math.sin(2 * math.pi * 0.11 * t + 0.6)
            p["skirt"] += 0.9 * force * math.sin(2 * math.pi * 0.23 * t + 1.3)
        if walking:
            p["skirt"] += math.sin(walking * 2) * 2.5 * force
        if motion and force:
            m = MOTIONS.get(motion[0])
            if m and 0 <= motion[1] <= m["len"]:
                for ch in ("head", "arm_left", "arm_right", "skirt", "sway"):
                    if ch in m:
                        p[ch] += motion_value(m[ch], motion[1], m["len"]) * min(1.0, force)
        return p

    def _pose(self, t, gaze_x=0.0, force=1.0, walking=0.0, talking=0.0):
        breath = 1.0 + self._sin(self.root, "scale_y", t, 0.5 * force)
        head = self._sin("head", "rotation", t, force)
        head += max(-1.0, min(1.0, gaze_x)) * float(self.follow.get("max_angle", 15)) * 0.45 * force
        head += talking * 1.6 * math.sin(t * 3.1)
        al = self._sin("arm_left", "rotation", t, force)
        ar = self._sin("arm_right", "rotation", t, force)
        if walking:                                              # bras qui balancent en marchant
            s = math.sin(walking) * 5 * force
            al, ar = al + s, ar + s
        return {"breath": breath, "head": head, "arm_left": al, "arm_right": ar,
                "skirt": self._sin("skirt", "rotation", t, force), "sway": self._sin(self.root, "rotation", t, force)}

    # ------------------------------------------------------------ déformation
    def build_grid(self, alpha_fn, cols=22, rows=34):
        """Grille en pixels de l'image d'origine, limitée à la zone qui bouge.
        alpha_fn(x0, y0, x1, y1) -> True si la case contient quelque chose de visible."""
        H = self.moving_bottom
        xs = [self.w * i / cols for i in range(cols + 1)]
        ys = [H * j / rows for j in range(rows + 1)]
        V = [[(x, y, {n: self.weight_at(n, x, y) for n in self.weights},
               max(0.0, min(1.0, (self.pivots.get(self.root, (0, H))[1] - y) / (110 * self.k))))
              for x in xs] for y in ys]
        cells = [(i, j) for j in range(rows) for i in range(cols)
                 if alpha_fn(xs[i], ys[j], xs[i + 1], ys[j + 1])]
        return {"V": V, "cells": cells, "xs": xs, "ys": ys, "bottom": H}

    def deform(self, grid, pose):
        """Nouvelles positions des sommets (pixels d'origine) + décalage et pivot de la tête."""
        rx, ry = self.pivots.get(self.root, (self.w / 2, self.h / 2))
        s = pose["breath"]
        sw = math.radians(pose.get("sway", 0.0))
        cs, ss = math.cos(sw), math.sin(sw)

        def torso(x, y, wb):
            y = y + (ry + (y - ry) * s - y) * wb
            if sw and wb > 0:                                    # le buste se balance autour de la taille
                qx, qy = x - rx, y - ry
                x, y = x + (rx + qx * cs - qy * ss - x) * wb, y + (ry + qx * ss + qy * cs - y) * wb
            return x, y

        rots = {}
        for n in self.weights:
            px, py = self.pivots[n]
            tx, ty = torso(px, py, max(0.0, min(1.0, (ry - py) / (110 * self.k))))
            a = math.radians(pose.get(n, 0.0))
            rots[n] = (tx, ty, math.cos(a), math.sin(a))
        out = []
        for row in grid["V"]:
            r2 = []
            for (x, y, ws, wb) in row:
                nx, ny = torso(x, y, wb)
                dx = dy = 0.0
                for n, w in ws.items():
                    if w <= 0.001:
                        continue
                    tx, ty, ca, sa = rots[n]
                    qx, qy = nx - tx, ny - ty
                    dx += (tx + qx * ca - qy * sa - nx) * w
                    dy += (ty + qx * sa + qy * ca - ny) * w
                r2.append((nx + dx, ny + dy))
            out.append(r2)
        hp = self.pivots.get("head")
        if hp and "head" in rots:
            tx, ty = rots["head"][:2]
            return out, (tx - hp[0], ty - hp[1]), pose.get("head", 0.0), hp
        return out, (0.0, 0.0), 0.0, (0.0, 0.0)
