"""Shirt, pants, shoes and gloves -- each a separate object.

Garments are generated from the *same* profile tables the skin is built
from, grown outward by a per-garment offset.  That guarantees they fit no
matter how the proportions in ``config`` are changed, and it means a
garment's UV grid lines up with the body's, so the texture templates can
place a stripe or a knee pad at an exact spot on the model.

Every garment is an open shell (hem, cuffs and neck holes stay open) and
gets its thickness from a Solidify modifier at assembly time, which is how
real production clothing is built.
"""

from __future__ import annotations

import math

from . import config as C
from . import body as B
from .meshlib import (MeshData, ring_xy, tube_rings, lerp, vlerp, smoothstep,
                      patch_boundary, in_patch, vadd, vsub, vmul, vnorm)

N = C.TORSO_SEGMENTS
NL = C.LIMB_SEGMENTS
NG = C.LEG_SEGMENTS


# ---------------------------------------------------------------------------
# shirt
# ---------------------------------------------------------------------------

SHIRT_ROWS = [0.900, 0.938, 0.975, 1.012, 1.052, 1.092, 1.132, 1.172,
              1.212, 1.252, 1.290, 1.325, 1.355, 1.386]
# which of those rows the sleeve socket is cut from
SHIRT_SOCKET_ROWS = (9, 11)


def build_shirt():
    """A short-sleeved tee: body shell, two sleeves, and a collar band."""
    mesh = MeshData(C.OBJ["shirt"])
    rect = C.UV_ATLAS["shirt"]
    off = C.CLOTH["shirt"]

    rings = []
    for z in SHIRT_ROWS:
        # a little ease across the chest so the shirt drapes rather than
        # shrink-wraps, and more at the hem: an untucked tee has to sit
        # clearly outside the trouser waistband or the waistband pokes through
        ease = off + 0.004 * smoothstep(1.05, 1.20, z) \
            + 0.013 * (1.0 - smoothstep(0.90, 1.05, z))
        rings.append(B.torso_ring(z, ease))
    idx = [mesh.add_verts(r) for r in rings]

    sock = C.SHOULDER_SOCKET
    r0, r1 = SHIRT_SOCKET_ROWS
    skip_l = in_patch(r0, r1, sock["cols_l"][0], sock["cols_l"][1], N)
    skip_r = in_patch(r0, r1, sock["cols_r"][0], sock["cols_r"][1], N)
    mesh.loft_indices(idx, rect["body"], v_range=(0.02, 0.86),
                      skip=lambda i, j: skip_l(i, j) or skip_r(i, j),
                      u_shift=N // 2)

    # collar: draw the top ring in to the neck itself, not the trapezius,
    # otherwise the tee reads as a boat neck
    neck = B.torso_ring(1.430, 0.011)
    prev = idx[-1]
    for (blend, dz, v0, v1) in ((0.62, 0.008, 0.86, 0.93),
                                (0.94, 0.020, 0.93, 1.00)):
        ring = []
        for k in range(N):
            p = vlerp(rings[-1][k], neck[k], blend)
            ring.append((p[0], p[1], p[2] + dz))
        cidx = mesh.add_verts(ring)
        mesh.loft_indices([prev, cidx], rect["collar"], v_range=(v0, v1))
        prev = cidx

    for side in ("L", "R"):
        cols = sock["cols_l"] if side == "L" else sock["cols_r"]
        loop = patch_boundary(idx, r0, r1, cols[0], cols[1], N)
        srings = B.arm_rings(side, C.CLOTH["shirt_sleeve"], 0,
                             C.SHIRT["sleeve_end"] + 1)
        # flare the cuff so the sleeve hangs off the arm
        centre = _ring_centre(srings[-1])
        srings[-1] = [vadd(p, vmul(vsub(p, centre), 0.14))
                      for p in srings[-1]]
        sidx = [mesh.add_verts(r) for r in srings]
        mesh.loft_indices(sidx, rect["sleeve"], v_range=(0.12, 0.94))
        mesh.bridge(loop, sidx[0], rect["sleeve"], v_range=(0.0, 0.12))
        mesh.mark("sleeve." + side, [i for r in sidx for i in r])

    mesh.mark("shirt_body", [i for r in idx for i in r])
    return mesh


def _ring_centre(ring):
    n = len(ring)
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n,
            sum(p[2] for p in ring) / n)


# ---------------------------------------------------------------------------
# pants
# ---------------------------------------------------------------------------

PANTS_ROWS = [0.815, 0.845, 0.878, 0.912, 0.950, 0.995]


def build_pants():
    """Slim trousers: a pelvis shell forking into two legs, plus knee pads."""
    mesh = MeshData(C.OBJ["pants"])
    rect = C.UV_ATLAS["pants"]
    off = C.CLOTH["pants"]

    rings = [B.torso_ring(z, off + 0.003 * smoothstep(0.90, 0.99, z))
             for z in PANTS_ROWS]
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, rect["hip"], v_range=(0.98, 0.05), u_shift=N // 2)

    crotch_pts = B.crotch_points(off)
    crotch = {k: mesh.add_verts([v])[0] for k, v in crotch_pts.items()}
    half = N // 2
    bottom = idx[0]

    cuff = C.PANTS["cuff_index"]
    for side in ("L", "R"):
        if side == "L":
            chain = [bottom[i % N] for i in range(0, half + 1)]
        else:
            chain = [bottom[i % N] for i in range(N, half - 1, -1)]
        fork_loop = chain + [crotch[side]]
        lrings = B.leg_rings(side, C.CLOTH["pants_thigh"])[1:cuff + 1]
        lidx = [mesh.add_verts(r) for r in lrings]
        mesh.loft_indices([fork_loop] + lidx, rect["leg"],
                          v_range=(0.98, 0.06), flip=(side == "R"))
        mesh.mark("pants_leg." + side, [i for r in lidx for i in r])

    mesh.add_face((bottom[0], crotch["L"], bottom[half], crotch["R"]),
                  [(0.50, 0.30), (0.53, 0.27), (0.56, 0.30), (0.53, 0.33)])

    for side in ("L", "R"):
        _knee_pad(mesh, side, rect)
    mesh.mark("pants_hip", [i for r in idx for i in r])
    return mesh


def _knee_pad(mesh, side, rect):
    """The hexagonal plate over each knee, plus its two retaining straps."""
    s = 1.0 if side == "L" else -1.0
    pad = C.PANTS["knee_pad"]
    kx, ky, kz, kr = C.LEG_PATH[C.KNEE_INDEX]
    cx = s * kx
    # hexagonal outline, long axis vertical, matching the reference sheet
    outline = []
    for k in range(6):
        a = math.pi * 2.0 * k / 6.0 + math.pi / 6.0
        outline.append((math.cos(a), math.sin(a)))
    rings = []
    # the 0.97 ring is a support loop: without it Catmull-Clark rounds the
    # hexagonal plate into a disc
    for (scale, depth) in ((1.00, 0.000), (0.97, 0.010), (0.90, 0.018),
                           (0.86, 0.024), (0.52, 0.030)):
        ring = []
        for (ux, uz) in outline:
            px = cx + ux * pad["half_w"] * scale
            pz = pad["z"] + uz * pad["half_h"] * scale
            # ride on the front of the knee
            py = ky - (kr + C.CLOTH["pants_thigh"] + 0.001 + depth)
            py += 0.010 * (ux * ux + uz * uz)
            ring.append((px, py, pz))
        rings.append(ring)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, rect["pad"], v_range=(0.02, 0.74),
                      flip=(side == "R"))
    mesh.cap_ring(idx[-1], rect["pad"], flip=(side == "R"),
                  uv_center=(0.5, 0.88), uv_radius=0.10)
    mesh.mark("knee_pad." + side, [i for r in idx for i in r])

    for dz in (pad["strap_dz"], -pad["strap_dz"]):
        z = pad["z"] + dz
        _strap(mesh, side, z, pad["strap_h"], rect)


def _strap(mesh, side, z, half_h, rect):
    """A band right around the leg at height `z`."""
    s = 1.0 if side == "L" else -1.0
    rings = []
    for dz in (-half_h, 0.0, half_h):
        ring = _leg_ring_at(side, z + dz, C.CLOTH["pants_thigh"] + 0.0016
                            + 0.0014 * (1.0 - abs(dz) / half_h))
        rings.append(ring)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, rect["strap"], v_range=(0.10, 0.90),
                      flip=(side == "R"))
    mesh.mark("strap." + side, [i for r in idx for i in r])


def _leg_ring_at(side, z, inflate):
    """An even-spaced leg cross-section at an arbitrary height."""
    s = 1.0 if side == "L" else -1.0
    path = C.LEG_PATH
    for i in range(len(path) - 1):
        z0, z1 = path[i][2], path[i + 1][2]
        if z1 <= z <= z0:
            t = (z0 - z) / (z0 - z1)
            x = lerp(path[i][0], path[i + 1][0], t)
            y = lerp(path[i][1], path[i + 1][1], t)
            r = lerp(path[i][3], path[i + 1][3], t) + inflate
            break
    else:
        x, y, r = path[-1][0], path[-1][1], path[-1][3] + inflate
    ring = []
    for k in range(NG):
        a = 2.0 * math.pi * k / NG
        if s < 0:
            a = -a
        ring.append((s * x + r * math.sin(a), y - r * math.cos(a), z))
    return ring


# ---------------------------------------------------------------------------
# shoes
# ---------------------------------------------------------------------------

def build_shoes():
    """High-top trainers.  Faces below the sole line get material slot 1."""
    mesh = MeshData(C.OBJ["shoes"])
    rect = C.UV_ATLAS["shoes"]
    sh = C.SHOE
    for side in ("L", "R"):
        _shoe(mesh, side, rect, sh)
    return mesh


def _shoe(mesh, side, rect, sh):
    s = 1.0 if side == "L" else -1.0
    off = C.CLOTH["shoe"]
    x = s * C.FOOT["x"]

    # collar of the high-top, wrapping the lower shin
    collar = []
    for z in (sh["top_z"], 0.150, 0.122, 0.098):
        collar.append(_leg_ring_at(side, z, off + 0.004
                                   + 0.006 * smoothstep(0.12, 0.175, z)))
    cidx = [mesh.add_verts(r) for r in collar]
    mesh.loft_indices(list(reversed(cidx)), rect["upper"], v_range=(0.99, 0.74),
                      flip=(side == "R"))

    # the foot itself, swept from the ankle to the toe
    path = [
        (x, 0.010, 0.086),
        (x, 0.002, 0.058),
        (x, -0.020, 0.034),
        (x, -0.068, 0.030),
        (x, -0.118, 0.030),
        (x, -0.162, 0.030),
        (x, -0.186, 0.034),
    ]
    radii = [0.040, 0.043, 0.048, 0.050, 0.048, 0.039, 0.022]
    squash = [1.00, 1.12, 1.40, 1.38, 1.26, 1.06, 0.90]
    rings = tube_rings(path, radii, NG, exponent=2.5, squash=squash)
    fidx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(fidx, rect["upper"], v_range=(0.70, 0.06))
    mesh.bridge(cidx[-1], fidx[0], rect["upper"], v_range=(0.74, 0.70),
                flip=(side == "R"))
    mesh.cap_ring(fidx[-1], rect["upper"], uv_center=(0.5, 0.03),
                  uv_radius=0.02)

    # flatten the sole and square the heel
    ids = [i for r in fidx for i in r]
    for i in ids:
        px, py, pz = mesh.verts[i]
        if pz < sh["sole_h"] + 0.016:
            w = 1.0 - smoothstep(0.0, sh["sole_h"] + 0.016, pz)
            pz = lerp(pz, sh["sole_z"], 0.95 * w)
        if py > sh["heel_y"] - 0.02:
            py = min(py, sh["heel_y"])
        mesh.verts[i] = (px, py, pz)
    mesh.mark("shoe." + side, ids + [i for r in cidx for i in r])

    # the white midsole: re-point the lowest faces at the sole patch of the
    # shoe texture so a single material paints upper and sole alike
    sole_top = sh["sole_z"] + sh["sole_h"]
    mesh.remap_uv_rect(
        lambda pts, top=sole_top: sum(p[2] for p in pts) / len(pts) < top,
        rect["upper"], rect["sole"])


# ---------------------------------------------------------------------------
# gloves
# ---------------------------------------------------------------------------

def build_gloves():
    """Fingerless gloves: wrist cuff, hand shell and a knuckle plate."""
    mesh = MeshData(C.OBJ["gloves"])
    rect = C.UV_ATLAS["gloves"]
    for side in ("L", "R"):
        _glove(mesh, side, rect)
    return mesh


def _glove(mesh, side, rect):
    s = 1.0 if side == "L" else -1.0
    g = C.GLOVE
    off = C.CLOTH["glove"]
    hw, hd = C.HAND["palm_half_w"], C.HAND["palm_half_d"]
    hx = s * (C.WRIST[0] + 0.002)
    hy = C.WRIST[1]

    # (z, half_thickness_x, half_spread_y, squareness) -- the palm profile
    # from body.py, grown by the glove offset
    profile = [
        (g["cuff_z"], 0.0320 + off, 0.0320 + off, 2.1),
        (g["cuff_bottom"], 0.0300 + off, 0.0325 + off, 2.2),
        (0.849, hd * 1.14 + off, hw * 0.80 + off, 2.4),
        (0.824, hd * 1.02 + off, hw * 0.93 + off, 2.8),
        (0.802, hd * 0.94 + off, hw * 1.00 + off, 3.0),
        (g["knuckle_z"], hd * 0.90 + off, hw * 0.99 + off, 3.0),
    ]
    rings = []
    for (z, rx, ry, e) in profile:
        cy = hy - 0.004 * (0.870 - z) / 0.080
        rings.append(ring_xy(NL, z, rx, ry, cy, e, cx=hx))
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, rect["hand"], v_range=(0.96, 0.08))
    mesh.mark("glove." + side, [i for r in idx for i in r])

    # knuckle plate on the back of the hand (the outward-facing side)
    _knuckle_plate(mesh, side, rect, hx, hy)


def _knuckle_plate(mesh, side, rect, hx, hy):
    s = 1.0 if side == "L" else -1.0
    hw = C.HAND["palm_half_w"]
    hd = C.HAND["palm_half_d"]
    cz = 0.818
    rings = []
    for (scale, depth) in ((1.00, 0.000), (0.84, 0.008), (0.46, 0.013)):
        ring = []
        for k in range(12):
            a = 2.0 * math.pi * k / 12.0
            uy = math.sin(a)
            uz = math.cos(a)
            # a rounded rectangle rather than an ellipse
            m = 1.0 / max(abs(uy) ** 2.6 + abs(uz) ** 2.6, 1e-6) ** (1 / 2.6)
            uy, uz = uy * m, uz * m
            ring.append((hx + s * (hd * 0.98 + C.CLOTH["glove"] + depth),
                         hy + uy * hw * 0.62 * scale - 0.004,
                         cz + uz * 0.024 * scale))
        rings.append(ring)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, rect["plate"], v_range=(0.05, 0.70),
                      flip=(side == "R"))
    mesh.cap_ring(idx[-1], rect["plate"], flip=(side == "R"),
                  uv_center=(0.5, 0.85), uv_radius=0.10)
    mesh.mark("knuckle." + side, [i for r in idx for i in r])


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_all():
    return {
        "shirt": build_shirt(),
        "pants": build_pants(),
        "shoes": build_shoes(),
        "gloves": build_gloves(),
    }
