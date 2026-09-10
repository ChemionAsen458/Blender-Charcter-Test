"""Layered, spiky anime hair.

Two pieces make up the hairstyle:

``scalp``    a shell lofted over an ellipsoid fitted to the skull, which
             supplies volume and stops the skin showing through
``strands``  tapered clumps swept out of that shell -- bangs over the
             forehead, locks framing the face, crown spikes and the layers
             falling down the back

Strands are placed from a seeded generator, so the hair is messy in the way
the reference sheet is messy but identical on every rebuild.
"""

from __future__ import annotations

import math
import random

from . import config as C
from .meshlib import (MeshData, tube_rings, lerp, vadd, vsub, vmul, vnorm,
                      vlen)

HAIR_UV = C.UV_ATLAS["hair"]

# Ellipsoid fitted to the skull: hair roots and the scalp shell ride on it.
SKULL = {"cy": 0.008, "cz": 1.600, "a": 0.092, "b": 0.100, "c": 0.125}

SCALP_COLUMNS = 28
SCALP_ROWS = 9


# ---------------------------------------------------------------------------
# skull surface helpers
# ---------------------------------------------------------------------------

def skull_point(theta, z, offset=0.0):
    """A point on the skull ellipsoid at angle `theta` and height `z`.

    `theta` is 0 at the face and sweeps toward the character's left, the
    same convention the body rings use.
    """
    s = SKULL
    t = (z - s["cz"]) / s["c"]
    rr = math.sqrt(max(0.0, 1.0 - t * t))
    x = s["a"] * rr * math.sin(theta)
    y = s["cy"] - s["b"] * rr * math.cos(theta)
    p = (x, y, z)
    if offset == 0.0:
        return p
    n = skull_normal(theta, z)
    return vadd(p, vmul(n, offset))


def skull_normal(theta, z):
    s = SKULL
    t = (z - s["cz"]) / s["c"]
    rr = math.sqrt(max(0.0, 1.0 - t * t))
    x = s["a"] * rr * math.sin(theta)
    y = -s["b"] * rr * math.cos(theta)
    # gradient of (x/a)^2 + (y/b)^2 + (z/c)^2
    return vnorm((x / (s["a"] ** 2), y / (s["b"] ** 2),
                  (z - s["cz"]) / (s["c"] ** 2)))


def _scalp_bottom_z(theta):
    """How far down the skull the shell reaches, per angle.

    High across the forehead (the bangs cover that), lower at the temples
    and lower still at the nape.
    """
    f = (1.0 - math.cos(theta)) * 0.5          # 0 at the face, 1 at the back
    return 1.658 - 0.112 * (f ** 0.75)


# ---------------------------------------------------------------------------
# scalp shell
# ---------------------------------------------------------------------------

def _build_scalp(mesh):
    off = C.HAIR["shell_offset"]
    z_top = C.CROWN_Z + 0.004
    rings = []
    for i in range(SCALP_ROWS):
        t = i / (SCALP_ROWS - 1)
        ring = []
        for j in range(SCALP_COLUMNS):
            theta = 2.0 * math.pi * j / SCALP_COLUMNS
            z_bot = _scalp_bottom_z(theta)
            z = lerp(z_top, z_bot, t ** 0.85)
            # thicken slightly toward the bottom edge so it does not look
            # like a swim cap
            o = off * (1.0 + 0.55 * t)
            ring.append(skull_point(theta, min(z, C.CROWN_Z + 0.003), o))
        rings.append(ring)
    idx = mesh.add_loft(rings, HAIR_UV["cap"], v_range=(0.97, 0.05))
    mesh.cap_ring(idx[0], HAIR_UV["cap"], flip=True, uv_center=(0.5, 0.99),
                  uv_radius=0.01)
    mesh.mark("scalp", [i for r in idx for i in r])
    return idx


# ---------------------------------------------------------------------------
# strands
# ---------------------------------------------------------------------------

def _strand(mesh, root, direction, bend, length, width, thickness,
            sections=None, twist=0.0, bend_amount=0.85):
    """One tapered hair clump swept from `root`."""
    sections = sections or C.HAIR["strand_sections"]
    d = vnorm(direction)
    b = vnorm(bend) if bend else (0.0, 0.0, 0.0)
    pts, radii, squash = [], [], []
    for i in range(sections + 1):
        t = i / sections
        p = vadd(root, vmul(d, length * t))
        p = vadd(p, vmul(b, length * (t ** 2) * bend_amount))
        pts.append(p)
        # full at the root, knife-edged at the tip
        w = width * ((1.0 - t) ** 0.55 + 0.08)
        radii.append(max(0.0010, w))
        squash.append(lerp(thickness, thickness * 0.80, t))
    rings = tube_rings(pts, radii, 8, exponent=2.8, squash=squash,
                       phase=twist)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, HAIR_UV["strand"], v_range=(0.03, 0.90))
    # collapse the tip to a point so the clump ends in a spike
    tip = mesh.cap_ring(idx[-1], HAIR_UV["strand"], uv_center=(0.5, 0.96),
                        uv_radius=0.02)
    tip_dir = vnorm(vadd(d, vmul(b, bend_amount * 2.0)))
    mesh.verts[tip] = vadd(pts[-1], vmul(tip_dir, length * 0.13))
    mesh.cap_ring(idx[0], HAIR_UV["strand"], flip=True,
                  uv_center=(0.5, 0.02), uv_radius=0.02)
    return idx


def _clump(mesh, theta, z, flow, length, width, out=0.28,
           tip_dir=(0.0, 0.0, -1.0), tip_amount=0.60, thickness=0.34,
           twist=0.0):
    """A clump that *lies along* the skull instead of radiating off it.

    `flow` is the direction the hair wants to travel; it is projected onto
    the skull's tangent plane so the root hugs the head, and only `out` of
    the surface normal is mixed back in.  `tip_dir` is an explicit
    world-space pull on the far end -- deriving it from the surface normal
    (the obvious thing) throws the fringe straight off the front of the
    face, because the normal at the top of the skull points forward.
    """
    root = skull_point(theta, z, C.HAIR["shell_offset"] * 0.85)
    n = skull_normal(theta, z)
    f = vnorm(flow)
    dot = sum(f[i] * n[i] for i in range(3))
    tangent = vsub(f, vmul(n, dot))
    if vlen(tangent) < 1e-6:
        tangent = f
    tangent = vnorm(tangent)
    direction = vnorm(vadd(tangent, vmul(n, out)))
    _strand(mesh, root, direction, vnorm(tip_dir), length, width, thickness,
            twist=twist, bend_amount=tip_amount)


def _bangs(mesh, rng):
    """Pointed fringe falling forward over the forehead, down to the brows."""
    for k in range(17):
        u = -1.0 + 2.0 * k / 16.0
        theta = u * math.radians(88.0)
        z = 1.700 - 0.012 * abs(u) + rng.uniform(-0.007, 0.007)
        length = rng.uniform(0.050, 0.074) * (1.0 - 0.10 * abs(u))
        _clump(mesh, theta, z,
               (0.34 * u + rng.uniform(-0.12, 0.12), -0.28, -0.92),
               length, rng.uniform(0.026, 0.042), out=0.16,
               tip_dir=(0.18 * u, 0.34, -0.94),
               tip_amount=rng.uniform(0.80, 1.05), thickness=0.44,
               twist=rng.uniform(-0.35, 0.35))
    # a few longer pieces crossing the brow, as on the reference sheet
    for (u, ln, w) in ((-0.34, 0.086, 0.028), (0.20, 0.090, 0.024),
                       (0.58, 0.078, 0.026)):
        _clump(mesh, u * math.radians(82.0), 1.708,
               (0.44 * u, -0.34, -0.88), ln, w, out=0.10,
               tip_dir=(0.10 * u, 0.40, -0.92), tip_amount=1.05,
               thickness=0.42)


def _side_locks(mesh, rng):
    """Locks framing the face, running down past the temples and ears."""
    for side in (1.0, -1.0):
        for k in range(5):
            theta = side * math.radians(84.0 + 14.0 * k)
            z = 1.674 - 0.014 * k + rng.uniform(-0.006, 0.006)
            _clump(mesh, theta, z,
                   (side * 0.34, rng.uniform(-0.24, 0.14), -0.90),
                   rng.uniform(0.060, 0.090), rng.uniform(0.026, 0.038),
                   out=0.07, tip_dir=(side * 0.22, 0.14, -0.96),
                   tip_amount=rng.uniform(0.45, 0.75), thickness=0.46,
                   twist=rng.uniform(-0.4, 0.4))


def _crown_spikes(mesh, rng):
    """The messy top: clumps flowing off the crown with lifted tips."""
    for k in range(15):
        theta = 2.0 * math.pi * k / 15.0 + rng.uniform(-0.12, 0.12)
        z = rng.uniform(1.700, 1.718)
        st, ct = math.sin(theta), math.cos(theta)
        _clump(mesh, theta, z,
               (st * 0.60 + rng.uniform(-0.16, 0.16),
                -ct * 0.60 + rng.uniform(-0.10, 0.20), -0.70),
               rng.uniform(0.044, 0.072), rng.uniform(0.026, 0.040),
               out=rng.uniform(0.14, 0.26),
               tip_dir=(st * 0.28, -ct * 0.28 + 0.10,
                        rng.uniform(0.55, 0.95)),
               tip_amount=rng.uniform(0.40, 0.65), thickness=0.48,
               twist=rng.uniform(-0.5, 0.5))
    # second band, kept off the forehead so it layers over the back and
    # sides rather than fighting the fringe
    for k in range(14):
        theta = math.radians(66.0) + math.radians(228.0) * (k / 13.0) \
            + rng.uniform(-0.08, 0.08)
        z = rng.uniform(1.668, 1.702)
        st, ct = math.sin(theta), math.cos(theta)
        _clump(mesh, theta, z,
               (st * 0.42 + rng.uniform(-0.14, 0.14),
                -ct * 0.42 + rng.uniform(0.0, 0.24), -0.86),
               rng.uniform(0.056, 0.086), rng.uniform(0.028, 0.042),
               out=0.12,
               tip_dir=(st * 0.20, -ct * 0.20 + 0.18,
                        rng.uniform(-0.30, 0.45)),
               tip_amount=rng.uniform(0.45, 0.75), thickness=0.48,
               twist=rng.uniform(-0.5, 0.5))


def _back_layers(mesh, rng):
    """Layers falling down the back of the head to the nape."""
    for k in range(14):
        theta = math.radians(112.0) + math.radians(136.0) * (k / 13.0)
        z = rng.uniform(1.600, 1.672)
        _clump(mesh, theta, z,
               (rng.uniform(-0.20, 0.20), rng.uniform(0.14, 0.42), -0.88),
               rng.uniform(0.056, 0.090), rng.uniform(0.028, 0.042),
               out=0.07, tip_dir=(0.0, 0.26, -0.96),
               tip_amount=rng.uniform(0.40, 0.70), thickness=0.50,
               twist=rng.uniform(-0.4, 0.4))


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build(seed=20250910):
    mesh = MeshData(C.OBJ["hair"])
    rng = random.Random(seed)
    _build_scalp(mesh)
    _bangs(mesh, rng)
    _side_locks(mesh, rng)
    _crown_spikes(mesh, rng)
    _back_layers(mesh, rng)
    return mesh
