#!/usr/bin/env python3
"""Generate the character's texture templates.

Seven templates, one per material, each painted into the same UV atlas the
model is built with:

    skin  hair  eyes  shirt  pants  shoes  gloves

Every file is written twice: ``<name>.png`` is the paintable texture the
material loads, and ``<name>_guide.png`` overlays the UV wireframe, the
atlas rectangles and their labels so the map can be repainted by hand
without guesswork.

Runs on a bare Python install -- no Pillow, no numpy -- so it works both
standalone and inside Blender's bundled interpreter:

    python3 -m tools.generate_textures --size 2048 --out textures/generated
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from character import config as C
from character import body as BODY
from character import clothing as CLOTH
from character import face as FACE
from character import hair as HAIR
from character.surface import FrontSampler, lens
from tools.canvas import Canvas
from tools.uvprobe import UVProbe

P = C.PALETTE

GUIDE_LINE = (0.10, 0.85, 0.55)
GUIDE_WIRE = (0.15, 0.55, 0.95)
GUIDE_TEXT = (0.95, 0.98, 1.00)


# ---------------------------------------------------------------------------
# a rectangle of the atlas, addressed in 0-1 local coordinates
# ---------------------------------------------------------------------------

class Region:
    def __init__(self, canvas, rect, name=""):
        self.c = canvas
        self.rect = rect
        self.name = name
        self.x0, self.y0, self.x1, self.y1 = canvas.rect_px(rect)
        self.w = self.x1 - self.x0
        self.h = self.y1 - self.y0

    # local (u, v) with v pointing up, like Blender
    def px(self, u, v):
        return (self.x0 + u * self.w, self.y1 - v * self.h)

    def to_local(self, uv):
        u0, v0, u1, v1 = self.rect
        return ((uv[0] - u0) / (u1 - u0), (uv[1] - v0) / (v1 - v0))

    def fill(self, colour):
        self.c.rect(self.x0, self.y0, self.x1, self.y1, colour)

    def box(self, u0, v0, u1, v1, colour, alpha=1.0):
        ax, ay = self.px(u0, v0)
        bx, by = self.px(u1, v1)
        self.c.rect(ax, ay, bx, by, colour, alpha)

    def ellipse(self, u, v, ru, rv, colour, feather=1.6, alpha=1.0, inner=0.0):
        cx, cy = self.px(u, v)
        self.c.ellipse(cx, cy, ru * self.w, rv * self.h, colour,
                       feather=feather, alpha=alpha, inner=inner)

    def bar(self, u, v, length, width, angle, colour, alpha=1.0):
        cx, cy = self.px(u, v)
        # angle is measured in texture space; +ve tilts the bar clockwise
        self.c.bar(cx, cy, length * self.w, width * self.h, angle, colour,
                   alpha)

    def line(self, u0, v0, u1, v1, width, colour, alpha=1.0):
        ax, ay = self.px(u0, v0)
        bx, by = self.px(u1, v1)
        self.c.line(ax, ay, bx, by, width * self.h, colour, alpha)

    def gradient(self, c0, c1, vertical=True, alpha=1.0):
        self.c.linear_gradient((self.x0, self.y0, self.x1, self.y1),
                               c0, c1, vertical, alpha)

    def shade(self, u, v, radius, colour, power=1.6, max_alpha=0.5):
        cx, cy = self.px(u, v)
        self.c.radial_shade((self.x0, self.y0, self.x1, self.y1), (cx, cy),
                            radius * max(self.w, self.h), colour, power,
                            max_alpha)

    def stipple(self, rng, count, colour, r=(1.0, 2.6), alpha=0.55,
                mask=None):
        self.c.stipple((self.x0, self.y0, self.x1, self.y1), rng, count,
                       colour, r[0] * self.w / 1024.0, r[1] * self.w / 1024.0,
                       alpha, mask)

    def label(self, text, colour=GUIDE_TEXT, scale=None):
        scale = scale or max(1, self.c.w // 640)
        self.c.text(self.x0 + 6 * scale, self.y0 + 6 * scale,
                    text, colour, scale=scale)

    def border(self, colour=GUIDE_LINE, width=None):
        width = width or max(1, self.c.w // 900)
        self.c.rect_outline(self.x0, self.y0, self.x1, self.y1, colour, width)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def shade(colour, factor):
    return tuple(max(0.0, min(1.0, colour[i] * factor)) for i in range(3))


# ---------------------------------------------------------------------------
# skin
# ---------------------------------------------------------------------------

def build_skin(size, meshes):
    c = Canvas(size, size, P["skin"])
    atlas = C.UV_ATLAS["skin"]
    rng = random.Random(7301)
    body_md = meshes["body"]
    reg = {k: Region(c, v, k) for k, v in atlas.items()}

    c.fill(P["skin"])
    for name in ("head", "torso", "arm", "leg", "hand", "foot"):
        r = reg[name]
        # a touch of tonal variation so flat colour does not read as plastic
        r.gradient(shade(P["skin"], 1.03), shade(P["skin"], 0.94))

    head = reg["head"]
    probe = UVProbe(body_md, atlas["head"])

    def at(p):
        return head.to_local(probe.uv_at(p))

    # warm the cheeks and the bridge of the nose
    for x in (0.052, -0.052):
        u, v = at((x, -0.076, 1.548))
        head.ellipse(u, v, 0.075, 0.055, P["blush"], alpha=0.28, feather=40.0)
    u, v = at((0.0, -0.112, 1.548))
    head.ellipse(u, v, 0.055, 0.030, P["blush"], alpha=0.18, feather=30.0)

    # under-nose and under-lip shadow
    u, v = at((0.0, -0.104, 1.536))
    head.ellipse(u, v, 0.045, 0.016, shade(P["skin_shadow"], 1.0), alpha=0.22,
                 feather=24.0)

    # eye sockets read better with a faint warm shadow painted in
    for x in (C.EYE["x"], -C.EYE["x"]):
        u, v = at((x, -0.082, C.EYE["z"] + 0.004))
        head.ellipse(u, v, 0.062, 0.042, P["skin_shadow"], alpha=0.20,
                     feather=34.0)

    # jaw and neck occlusion
    u, v = at((0.0, -0.020, 1.462))
    head.ellipse(u, v, 0.30, 0.055, P["skin_shadow"], alpha=0.22, feather=44.0)

    # freckles across the nose and cheeks, as on the reference sheet
    freckle_boxes = []
    for x in (0.058, -0.058, 0.0):
        u, v = at((x, -0.086, 1.552))
        cx, cy = head.px(u, v)
        freckle_boxes.append((cx, cy, head.w * 0.085))
    def freckle_mask(x, y):
        return any(math.hypot(x - fx, y - fy) < fr
                   for (fx, fy, fr) in freckle_boxes)
    head.stipple(rng, 900, P["freckle"], r=(1.1, 2.3), alpha=0.5,
                 mask=freckle_mask)

    # ears
    ear = reg["ear"]
    ear.fill(shade(P["skin"], 0.99))
    ear.gradient(shade(P["skin"], 1.02), shade(P["skin"], 0.90))
    ear.ellipse(0.5, 0.52, 0.26, 0.30, P["skin_shadow"], alpha=0.45,
                feather=size / 90.0)
    ear.ellipse(0.5, 0.46, 0.13, 0.17, P["skin_deep"], alpha=0.40,
                feather=size / 120.0)

    # torso: nipples, navel and a soft centre-line shadow
    torso = reg["torso"]
    tprobe = UVProbe(body_md, atlas["torso"])

    def tat(p):
        return torso.to_local(tprobe.uv_at(p))

    for x in (0.062, -0.062):
        u, v = tat((x, -0.112, 1.176))
        torso.ellipse(u, v, 0.020, 0.016, shade(P["skin_shadow"], 1.05),
                      alpha=0.55, feather=size / 200.0)
    u, v = tat((0.0, -0.098, 1.030))
    torso.ellipse(u, v, 0.013, 0.012, P["skin_deep"], alpha=0.45,
                  feather=size / 260.0)

    # limbs: freckles on the forearms and shoulders
    arm = reg["arm"]
    arm.gradient(shade(P["skin"], 1.02), shade(P["skin"], 0.93))
    arm.stipple(rng, 420, P["freckle"], r=(0.9, 1.9), alpha=0.35)
    reg["leg"].gradient(shade(P["skin"], 1.01), shade(P["skin"], 0.92))

    # hands: nails and knuckle shading
    hand = reg["hand"]
    hand.gradient(shade(P["skin"], 1.02), shade(P["skin"], 0.93))
    hand.box(0.0, 0.86, 1.0, 1.0, shade(P["skin"], 0.90), alpha=0.5)

    foot = reg["foot"]
    foot.gradient(shade(P["skin"], 1.0), shade(P["skin"], 0.90))

    # ---- mouth strip -------------------------------------------------
    m = reg["mouth"]
    m.fill(P["skin"])
    _paint_lens(m, C.MOUTH["height"], C.MOUTH["height"] * 0.85,
                lambda lu, lv, inside, tt: _mouth_pixel(lu, lv, inside, tt))

    # ---- eyelid strips -----------------------------------------------
    for key, upper in (("lid_up", True), ("lid_lo", False)):
        r = reg[key]
        r.fill(P["skin"])
        # V runs from the outer edge (on the face) to the free lash edge
        r.gradient(shade(P["skin"], 0.88), shade(P["skin"], 1.02),
                   vertical=True)
        lash_v0 = 0.80 if upper else 0.74
        r.box(0.0, lash_v0, 1.0, 1.0, mix(P["skin_deep"], P["hair_shadow"],
                                          0.55), alpha=0.85)
        r.box(0.0, 0.94, 1.0, 1.0, P["hair_shadow"], alpha=0.95)
        if upper:
            # thicken the lash line toward the outer corner
            r.bar(0.80, 0.90, 0.42, 0.10, 0.0, P["hair_shadow"], alpha=0.8)
    reg["face"].fill(shade(P["skin"], 0.97))
    return c


def _mouth_pixel(lu, lv, inside, tt):
    """Colour for one texel of the mouth strip.

    `tt` is 0 at the lower lip edge and 1 at the upper lip edge.
    """
    if not inside:
        return None
    if 0.40 < tt < 0.60:
        return mix(P["skin_deep"], P["mouth_inner"], 0.55)
    if tt >= 0.60:
        return mix(P["lip"], P["skin"], (tt - 0.60) / 0.40 * 0.65)
    return mix(P["lip"], P["skin"], (0.40 - tt) / 0.40 * 0.55)


def _paint_lens(region, half_top, half_bot, colour_fn, **kw):
    """Walk a lens-shaped island texel by texel.

    The eye and mouth shells map an almond outline linearly into their
    rectangle, so the texture has to know that outline to paint inside it.
    Importing the same `lens` used to build the mesh keeps them in step.
    """
    span = half_top + half_bot
    for py in range(region.y0, region.y1):
        v = 1.0 - (py + 0.5 - region.y0) / region.h
        for px in range(region.x0, region.x1):
            lu = (px + 0.5 - region.x0) / region.w
            u = lu * 2.0 - 1.0
            lo, hi = lens(u, half_top, half_bot, **kw)
            model_v = (v * span) - half_bot
            inside = lo <= model_v <= hi
            tt = (model_v - lo) / max(1e-6, hi - lo) if inside else 0.0
            col = colour_fn(lu, v, inside, tt)
            if col is not None:
                region.c.blend(px, py, col, 1.0)


# ---------------------------------------------------------------------------
# hair
# ---------------------------------------------------------------------------

def build_hair(size, meshes):
    c = Canvas(size, size, P["hair"])
    atlas = C.UV_ATLAS["hair"]
    rng = random.Random(4412)
    cap = Region(c, atlas["cap"], "cap")
    strand = Region(c, atlas["strand"], "strand")
    brow = Region(c, atlas["brow"], "brow")
    c.fill(P["hair_shadow"])

    # cap: V = 0.05 at the lower edge (roots, in shadow), 0.97 at the crown
    cap.fill(P["hair"])
    cap.gradient(P["hair_light"], P["hair_shadow"])
    # the classic anime highlight band around the crown
    cap.box(0.0, 0.62, 1.0, 0.74, P["hair_light"], alpha=0.55)
    cap.box(0.0, 0.655, 1.0, 0.705, P["hair_rim"], alpha=0.55)
    for i in range(80):
        u = rng.uniform(0.0, 1.0)
        w = rng.uniform(0.004, 0.016)
        cap.box(u, 0.0, u + w, 1.0,
                shade(P["hair"], rng.uniform(0.80, 1.22)), alpha=0.30)

    # strands: V = 0.03 root -> 0.90 tip
    strand.fill(P["hair"])
    strand.gradient(P["hair_light"], P["hair_shadow"])
    strand.box(0.0, 0.0, 1.0, 0.16, P["hair_shadow"], alpha=0.75)
    strand.box(0.0, 0.40, 1.0, 0.56, P["hair_light"], alpha=0.60)
    strand.box(0.0, 0.455, 1.0, 0.515, P["hair_rim"], alpha=0.50)
    strand.box(0.0, 0.90, 1.0, 1.0, shade(P["hair_light"], 1.10), alpha=0.55)
    for i in range(140):
        u = rng.uniform(0.0, 1.0)
        w = rng.uniform(0.003, 0.012)
        strand.box(u, 0.0, u + w, 1.0,
                   shade(P["hair"], rng.uniform(0.72, 1.30)), alpha=0.35)

    # brows: solid, slightly lighter at the tail
    brow.fill(P["hair_shadow"])
    brow.gradient(shade(P["hair"], 1.05), P["hair_shadow"])
    brow.box(0.0, 0.0, 1.0, 0.12, P["hair_shadow"], alpha=0.6)
    brow.box(0.0, 0.88, 1.0, 1.0, P["hair_shadow"], alpha=0.6)
    return c


# ---------------------------------------------------------------------------
# eyes
# ---------------------------------------------------------------------------

def build_eyes(size, meshes):
    c = Canvas(size, size, P["sclera"])
    atlas = C.UV_ATLAS["eyes"]
    iris = Region(c, atlas["iris"], "iris")
    sclera = Region(c, atlas["sclera"], "sclera")
    hl = Region(c, atlas["highlight"], "highlight")
    c.fill((0.06, 0.06, 0.07))

    ht, hb = FACE.EYE_HALF_TOP, FACE.EYE_HALF_BOT
    iris_cu, iris_cv = 0.50, 0.56       # in local rect coords
    iris_r = 0.30
    pupil_r = 0.125

    def eye_pixel(lu, lv, inside, tt):
        if not inside:
            return (0.05, 0.05, 0.06)
        du = (lu - iris_cu) / iris_r
        dv = (lv - iris_cv) / (iris_r * 1.02)
        d = math.hypot(du, dv)
        if d <= 1.0:
            # silver iris: dark rim, bright toward the bottom
            edge = min(1.0, max(0.0, (1.0 - d) / 0.30))
            base = mix(P["eye_rim"], P["eye_silver_dark"], edge)
            lift = max(0.0, (iris_cv - lv) / iris_r) * 0.9 + 0.15
            base = mix(base, P["eye_silver"], min(1.0, lift))
            if d <= pupil_r / iris_r:
                return P["pupil"]
            if d > 0.90:
                return mix(base, P["eye_rim"], (d - 0.90) / 0.10)
            # a few radial striations sell the iris at close range
            ang = math.atan2(dv, du)
            stri = 0.5 + 0.5 * math.sin(ang * 18.0)
            return mix(base, shade(base, 0.82), stri * 0.22 * d)
        # sclera, shaded under the upper lid
        s = mix(P["sclera"], P["sclera_shadow"], max(0.0, (tt - 0.55) / 0.45))
        return s

    _paint_lens(iris, ht, hb, eye_pixel, peak_shift=-0.10)

    # lash line along the top of the lens, and a softer lower rim
    def lash_pixel(lu, lv, inside, tt):
        if not inside:
            return None
        if tt > 0.88:
            return P["eye_rim"]
        if tt > 0.80:
            return mix(P["eye_rim"], P["sclera_shadow"],
                       (tt - 0.80) / 0.08)
        if tt < 0.06:
            return mix(P["eye_rim"], P["sclera"], 0.45)
        return None
    _paint_lens(iris, ht, hb, lash_pixel, peak_shift=-0.10)

    # specular highlights
    iris.ellipse(iris_cu - 0.10, iris_cv + 0.13, 0.085, 0.075,
                 (1.0, 1.0, 1.0), feather=size / 300.0)
    iris.ellipse(iris_cu + 0.11, iris_cv - 0.12, 0.040, 0.035,
                 (0.96, 0.97, 1.0), feather=size / 400.0, alpha=0.8)

    # reference swatches for repainting by hand
    sclera.fill(P["sclera"])
    sclera.gradient(P["sclera"], P["sclera_shadow"])
    hl.fill(P["eye_silver"])
    hl.box(0.0, 0.0, 1.0, 0.34, P["eye_silver_dark"])
    hl.box(0.0, 0.34, 1.0, 0.50, P["eye_rim"])
    hl.ellipse(0.5, 0.76, 0.22, 0.16, (1.0, 1.0, 1.0), feather=size / 300.0)
    return c


# ---------------------------------------------------------------------------
# clothing
# ---------------------------------------------------------------------------

def build_shirt(size, meshes):
    c = Canvas(size, size, P["cloth_black"])
    atlas = C.UV_ATLAS["shirt"]
    md = meshes["shirt"]
    c.fill(P["cloth_black"])
    body = Region(c, atlas["body"], "body")
    sleeve = Region(c, atlas["sleeve"], "sleeve")
    collar = Region(c, atlas["collar"], "collar")

    body.fill(P["cloth_black"])
    body.gradient(shade(P["cloth_black"], 1.35), shade(P["cloth_black"], 0.75))
    # weave: barely-there vertical variation keeps flat black alive
    rng = random.Random(9911)
    for _ in range(60):
        u = rng.uniform(0, 1)
        body.box(u, 0.0, u + rng.uniform(0.002, 0.010), 1.0,
                 shade(P["cloth_black"], rng.uniform(0.85, 1.20)), alpha=0.30)

    probe = UVProbe(md, atlas["body"])

    def bar_at(point, length, width, angle, colour=P["cloth_white"]):
        u, v = body.to_local(probe.uv_at(point))
        body.bar(u, v, length, width, angle, colour)

    # The reference sheet's white flashes: a chevron across the upper
    # chest, a wider one low on the front, and matching marks on the back.
    bar_at((0.118, -0.092, 1.268), 0.108, 0.044, -36.0)
    bar_at((-0.118, -0.092, 1.268), 0.108, 0.044, 36.0)
    bar_at((0.082, -0.106, 0.962), 0.096, 0.040, 54.0)
    bar_at((-0.082, -0.106, 0.962), 0.096, 0.040, -54.0)
    bar_at((0.116, 0.090, 1.276), 0.104, 0.042, 36.0)
    bar_at((-0.116, 0.090, 1.276), 0.104, 0.042, -36.0)
    bar_at((0.112, 0.086, 1.008), 0.090, 0.038, -50.0)
    bar_at((-0.112, 0.086, 1.008), 0.090, 0.038, 50.0)

    # sleeves: one flash near the shoulder seam
    sleeve.fill(P["cloth_black"])
    sleeve.gradient(shade(P["cloth_black"], 1.30), shade(P["cloth_black"], 0.80))
    sleeve.bar(0.30, 0.62, 0.30, 0.16, -22.0, P["cloth_white"])
    sleeve.bar(0.74, 0.62, 0.22, 0.14, 22.0, P["cloth_white"])
    sleeve.box(0.0, 0.0, 1.0, 0.08, shade(P["cloth_black"], 0.7))

    collar.fill(shade(P["cloth_black"], 0.92))
    collar.box(0.0, 0.55, 1.0, 1.0, shade(P["cloth_black"], 1.25))
    return c


def build_pants(size, meshes):
    c = Canvas(size, size, P["cloth_black_lo"])
    atlas = C.UV_ATLAS["pants"]
    c.fill(P["cloth_black_lo"])
    hip = Region(c, atlas["hip"], "hip")
    leg = Region(c, atlas["leg"], "leg")
    pad = Region(c, atlas["pad"], "pad")
    strap = Region(c, atlas["strap"], "strap")
    rng = random.Random(5150)

    for r in (hip, leg):
        r.fill(P["cloth_black_lo"])
        r.gradient(shade(P["cloth_black_lo"], 1.45),
                   shade(P["cloth_black_lo"], 0.80))
        for _ in range(50):
            u = rng.uniform(0, 1)
            r.box(u, 0.0, u + rng.uniform(0.002, 0.009), 1.0,
                  shade(P["cloth_black_lo"], rng.uniform(0.82, 1.25)),
                  alpha=0.28)
    # waistband and a seam down the outside of each leg
    hip.box(0.0, 0.90, 1.0, 1.0, shade(P["cloth_black"], 1.30))
    hip.box(0.0, 0.885, 1.0, 0.905, shade(P["cloth_black_lo"], 0.55))
    for u in (0.25, 0.75):
        leg.box(u - 0.004, 0.0, u + 0.004, 1.0,
                shade(P["cloth_black_lo"], 0.55), alpha=0.8)

    # knee pad: light plate with a bevel and a darker rim
    pad.fill(P["plate_grey"])
    pad.gradient(P["plate_silver"], shade(P["plate_grey"], 0.72))
    pad.box(0.0, 0.0, 1.0, 0.06, shade(P["plate_grey"], 0.45))
    pad.box(0.0, 0.70, 1.0, 1.0, P["plate_silver"])
    pad.box(0.0, 0.66, 1.0, 0.72, shade(P["plate_grey"], 0.60))

    # straps: black webbing with a lighter edge
    strap.fill(P["cloth_black"])
    strap.gradient(shade(P["cloth_black"], 1.30), shade(P["cloth_black"], 0.65))
    strap.box(0.0, 0.44, 1.0, 0.56, shade(P["cloth_black"], 1.55), alpha=0.7)
    return c


def build_shoes(size, meshes):
    c = Canvas(size, size, P["cloth_black"])
    atlas = C.UV_ATLAS["shoes"]
    md = meshes["shoes"]
    c.fill(P["cloth_black"])
    upper = Region(c, atlas["upper"], "upper")
    sole = Region(c, atlas["sole"], "sole")
    detail = Region(c, atlas["detail"], "detail")

    upper.fill(P["cloth_black"])
    upper.gradient(shade(P["cloth_black"], 1.30), shade(P["cloth_black"], 0.72))
    # collar padding at the top of the high-top, and a grey side panel
    upper.box(0.0, 0.93, 1.0, 1.0, shade(P["cloth_black"], 1.6))
    upper.box(0.0, 0.90, 1.0, 0.93, P["plate_grey"], alpha=0.55)

    probe = UVProbe(md, atlas["upper"])
    for side in (1.0, -1.0):
        x = side * C.FOOT["x"]
        # a white flash along the outside of the shoe
        u, v = upper.to_local(probe.uv_at((x + side * 0.03, -0.070, 0.052)))
        upper.bar(u, v, 0.16, 0.05, 8.0, P["cloth_white"])
        u, v = upper.to_local(probe.uv_at((x + side * 0.03, 0.020, 0.090)))
        upper.bar(u, v, 0.10, 0.045, -28.0, P["plate_grey"])

    # laces up the tongue
    for i in range(5):
        v = 0.44 + i * 0.10
        upper.line(0.44, v, 0.56, v + 0.03, 0.012, P["sole_grey"], alpha=0.9)

    sole.fill(P["sole_white"])
    sole.gradient(P["sole_white"], shade(P["sole_white"], 0.82))
    sole.box(0.0, 0.0, 1.0, 0.26, P["sole_grey"])
    sole.box(0.0, 0.74, 1.0, 0.80, P["sole_grey"], alpha=0.6)

    detail.fill(P["cloth_black"])
    detail.box(0.0, 0.0, 0.34, 1.0, P["sole_white"])
    detail.box(0.34, 0.0, 0.62, 1.0, P["plate_grey"])
    return c


def build_gloves(size, meshes):
    c = Canvas(size, size, P["cloth_black"])
    atlas = C.UV_ATLAS["gloves"]
    c.fill(P["cloth_black"])
    hand = Region(c, atlas["hand"], "hand")
    plate = Region(c, atlas["plate"], "plate")
    cuff = Region(c, atlas["cuff"], "cuff")
    detail = Region(c, atlas["detail"], "detail")

    hand.fill(P["cloth_black"])
    hand.gradient(shade(P["cloth_black"], 1.35), shade(P["cloth_black"], 0.70))
    # V = 0.96 at the wrist cuff, 0.08 at the knuckles
    hand.box(0.0, 0.86, 1.0, 1.0, shade(P["cloth_black"], 1.55))
    hand.box(0.0, 0.835, 1.0, 0.865, shade(P["cloth_black"], 0.5))
    hand.box(0.0, 0.0, 1.0, 0.10, shade(P["cloth_black"], 1.4))
    # the four small pale studs above the knuckles
    for i in range(4):
        hand.ellipse(0.30 + i * 0.135, 0.16, 0.028, 0.020, P["cloth_white"],
                     feather=size / 400.0)

    plate.fill(P["plate_silver"])
    plate.gradient(P["plate_silver"], shade(P["plate_grey"], 0.80))
    plate.box(0.0, 0.0, 1.0, 0.10, shade(P["plate_grey"], 0.45))
    plate.box(0.0, 0.72, 1.0, 1.0, (0.94, 0.95, 0.96))

    cuff.fill(shade(P["cloth_black"], 1.2))
    cuff.gradient(shade(P["cloth_black"], 1.5), shade(P["cloth_black"], 0.8))
    detail.fill(P["cloth_black"])
    detail.box(0.0, 0.0, 0.4, 1.0, P["plate_silver"])
    detail.box(0.4, 0.0, 0.68, 1.0, P["cloth_white"])
    return c


# ---------------------------------------------------------------------------
# guide overlay
# ---------------------------------------------------------------------------

def draw_guide(canvas, atlas, meshdatas, label_prefix=""):
    """Overlay the UV wireframe, atlas rectangles and their names."""
    wire = max(1, canvas.w // 2048)
    for md in meshdatas:
        for uvs in md.uvs:
            n = len(uvs)
            for i in range(n):
                a = canvas.uv_to_px(*uvs[i])
                b = canvas.uv_to_px(*uvs[(i + 1) % n])
                canvas.line(a[0], a[1], b[0], b[1], wire, GUIDE_WIRE,
                            alpha=0.55)
    scale = max(1, canvas.w // 700)
    for name, rect in atlas.items():
        r = Region(canvas, rect, name)
        r.border(GUIDE_LINE, width=max(2, canvas.w // 700))
        text = (label_prefix + name).upper()
        canvas.rect(r.x0 + 4 * scale, r.y0 + 4 * scale,
                    r.x0 + 8 * scale + canvas.text_width(text, scale),
                    r.y0 + 16 * scale, (0.0, 0.0, 0.0), alpha=0.65)
        canvas.text(r.x0 + 6 * scale, r.y0 + 6 * scale, text, GUIDE_TEXT,
                    scale=scale)
    return canvas


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

BUILDERS = {
    "skin": build_skin,
    "hair": build_hair,
    "eyes": build_eyes,
    "shirt": build_shirt,
    "pants": build_pants,
    "shoes": build_shoes,
    "gloves": build_gloves,
}


def collect_meshes():
    """Every mesh, so the guide overlays can draw real UV wireframes."""
    body_md = BODY.build()
    sampler = FrontSampler(body_md)
    meshes = {"body": body_md, "hair": HAIR.build()}
    meshes.update(CLOTH.build_all())
    parts = FACE.build_all(sampler)
    meshes["face_parts"] = parts
    return meshes


GUIDE_SOURCES = {
    "skin": lambda m: [m["body"]] + [p[0] for k, p in m["face_parts"].items()
                                     if k.startswith(("lid", "mouth", "cavity"))],
    "hair": lambda m: [m["hair"]] + [p[0] for k, p in m["face_parts"].items()
                                     if k.startswith("brow")],
    "eyes": lambda m: [p[0] for k, p in m["face_parts"].items()
                       if k.startswith("eye")],
    "shirt": lambda m: [m["shirt"]],
    "pants": lambda m: [m["pants"]],
    "shoes": lambda m: [m["shoes"]],
    "gloves": lambda m: [m["gloves"]],
}


def generate(out_dir, size=None, names=None, guides=True, quiet=False):
    size = size or C.TEXTURE_SIZE
    os.makedirs(out_dir, exist_ok=True)
    meshes = collect_meshes()
    written = []
    for name in (names or C.TEXTURE_SETS):
        canvas = BUILDERS[name](size, meshes)
        path = os.path.join(out_dir, f"{name}.png")
        canvas.save(path)
        written.append(path)
        if not quiet:
            print(f"  wrote {path}")
        if guides:
            guide = BUILDERS[name](size, meshes)
            draw_guide(guide, C.UV_ATLAS[name], GUIDE_SOURCES[name](meshes))
            gpath = os.path.join(out_dir, f"{name}_guide.png")
            guide.save(gpath)
            written.append(gpath)
            if not quiet:
                print(f"  wrote {gpath}")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=C.TEXTURE_DIR)
    ap.add_argument("--size", type=int, default=C.TEXTURE_SIZE)
    ap.add_argument("--only", nargs="*", choices=sorted(BUILDERS))
    ap.add_argument("--no-guides", action="store_true")
    args = ap.parse_args(argv)
    print(f"generating {args.size}x{args.size} texture templates -> {args.out}")
    generate(args.out, args.size, args.only, not args.no_guides)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
