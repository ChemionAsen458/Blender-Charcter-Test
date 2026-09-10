"""Eyes, eyelids, eyebrows and mouth -- built as separate riggable shells.

Anime faces are not sculpted the way realistic ones are.  The eye is a
curved decal hugging the skull, the lids are skin-coloured shells that
sweep over it, and the brows and mouth float a millimetre above the face.
That is what makes them animatable: every one of these parts ships with
alternative vertex positions (blink, brow-up, mouth-open ...) that
:mod:`character.face_rig` turns into shape keys and hooks up to bones.

Each builder returns ``(MeshData, shapes)`` where `shapes` maps a shape-key
name to a full replacement vertex list with identical ordering.
"""

from __future__ import annotations

import math

from . import config as C
from .meshlib import MeshData, lerp, vlerp
from .surface import lens

EYE_UV = C.UV_ATLAS["eyes"]
HAIR_UV = C.UV_ATLAS["hair"]
SKIN_UV = C.UV_ATLAS["skin"]

# grid resolution of the lens-shaped shells
NU = 17          # across
NV = 7           # through the vertical span

EYE_HALF_W = 0.0315
EYE_HALF_TOP = 0.0205
EYE_HALF_BOT = 0.0150
EYE_OFFSET = 0.0012          # eye shell sits just proud of the socket
EYE_BULGE = 0.0055           # corneal bulge, so the iris catches light
LID_OFFSET = 0.0026          # lids ride outside the eye shell
LID_REST_OPEN = 0.90         # 1 = fully open, 0 = closed onto the lower lid


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _u_values(n=NU):
    return [-1.0 + 2.0 * i / (n - 1) for i in range(n)]


def _grid_faces(mesh, idx_rows, rect, mat=0, flip=False,
                u_range=(0.0, 1.0), v_range=(0.0, 1.0), uv_rows=None):
    """Quad the grid produced by the lens builders, with explicit UVs."""
    nr, nc = len(idx_rows), len(idx_rows[0])
    for i in range(nr - 1):
        for j in range(nc - 1):
            if uv_rows is not None:
                uv = [uv_rows[i][j], uv_rows[i][j + 1],
                      uv_rows[i + 1][j + 1], uv_rows[i + 1][j]]
            else:
                v0 = lerp(v_range[0], v_range[1], i / (nr - 1))
                v1 = lerp(v_range[0], v_range[1], (i + 1) / (nr - 1))
                u0 = lerp(u_range[0], u_range[1], j / (nc - 1))
                u1 = lerp(u_range[0], u_range[1], (j + 1) / (nc - 1))
                uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            quad = (idx_rows[i][j], idx_rows[i][j + 1],
                    idx_rows[i + 1][j + 1], idx_rows[i + 1][j])
            if flip:
                quad = tuple(reversed(quad))
                uv = list(reversed(uv))
            mesh.add_face(quad, uv, mat)


def _rect_uv(rect, u, v):
    u0, v0, u1, v1 = rect
    return (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


def mirror_shape(verts):
    return [(-x, y, z) for (x, y, z) in verts]


# ---------------------------------------------------------------------------
# eye
# ---------------------------------------------------------------------------

def _eye_verts(sampler, cx, cz, half_w, half_top, half_bot, offset, bulge):
    verts = []
    for u in _u_values():
        lo, hi = lens(u, half_top, half_bot, peak_shift=-0.10)
        for i in range(NV):
            t = i / (NV - 1)
            v = lerp(lo, hi, t)
            span = (hi - lo) or 1e-6
            # a corneal bulge that peaks at the middle of the eye
            r2 = min(1.0, u * u + (2.0 * (v - (lo + hi) * 0.5) / span) ** 2)
            off = offset + bulge * (1.0 - r2) ** 1.3
            verts.append(sampler.offset_point(cx + u * half_w, cz + v, off))
    return verts


def build_eye(sampler, side="L"):
    """The eye shell: a curved almond decal carrying the silver iris."""
    eye = C.EYE
    cx = eye["x"] if side == "L" else -eye["x"]
    mesh = MeshData(C.OBJ["eye_l" if side == "L" else "eye_r"])
    verts = _eye_verts(sampler, cx, eye["z"], EYE_HALF_W, EYE_HALF_TOP,
                       EYE_HALF_BOT, EYE_OFFSET, EYE_BULGE)
    idx = mesh.add_verts(verts)
    rows = [[idx[j * NV + i] for j in range(NU)] for i in range(NV)]

    uv_rows = []
    for i in range(NV):
        row = []
        for j, u in enumerate(_u_values()):
            lo, hi = lens(u, EYE_HALF_TOP, EYE_HALF_BOT, peak_shift=-0.10)
            v = lerp(lo, hi, i / (NV - 1))
            row.append(_rect_uv(EYE_UV["iris"], (u + 1.0) * 0.5,
                                (v + EYE_HALF_BOT) /
                                (EYE_HALF_TOP + EYE_HALF_BOT)))
        uv_rows.append(row)

    _grid_faces(mesh, rows, EYE_UV["iris"], flip=(side == "R"),
                uv_rows=uv_rows)
    mesh.mark("eye." + side, idx)
    return mesh, {}


# ---------------------------------------------------------------------------
# eyelids
# ---------------------------------------------------------------------------

def _lid_verts(sampler, cx, cz, open_t, upper=True, squeeze=0.0):
    """One eyelid shell at a given openness.

    `open_t` is where the lid's free edge sits in the eye's vertical span:
    1.0 puts the upper lid at the top of the eye, 0.0 closes it onto the
    lower lid.  Generating both the rest and the blink pose through the
    same function guarantees identical topology for the shape key.
    """
    verts = []
    for u in _u_values():
        lo, hi = lens(u, EYE_HALF_TOP, EYE_HALF_BOT, peak_shift=-0.10)
        if upper:
            outer = hi + 0.0105 * (1.0 - 0.35 * abs(u))
            edge = lerp(lo, hi, open_t)
        else:
            outer = lo - 0.0080 * (1.0 - 0.30 * abs(u))
            edge = lerp(lo, hi, open_t)
        for i in range(NV):
            t = i / (NV - 1)
            v = lerp(outer, edge, t)
            # the free edge rides further out so it clears the cornea
            off = LID_OFFSET + 0.0022 * (t ** 2) + squeeze * (t ** 2)
            width = EYE_HALF_W * (1.0 + 0.045 * (1.0 - t))
            verts.append(sampler.offset_point(cx + u * width, cz + v, off))
    return verts


def build_eyelid(sampler, side="L", upper=True):
    eye = C.EYE
    cx = eye["x"] if side == "L" else -eye["x"]
    name = f"{C.PREFIX}-Lid{'Up' if upper else 'Lo'}-{side}"
    mesh = MeshData(name)
    rest_open = LID_REST_OPEN if upper else 0.04
    verts = _lid_verts(sampler, cx, eye["z"], rest_open, upper)
    idx = mesh.add_verts(verts)
    rows = [[idx[j * NV + i] for j in range(NU)] for i in range(NV)]
    _grid_faces(mesh, rows, SKIN_UV["lid_up" if upper else "lid_lo"],
                flip=(side == "R"), u_range=(0.04, 0.96),
                v_range=(0.04, 0.96))
    mesh.mark("lid." + side, idx)

    # closed enough to overlap the other lid slightly, so a blink seals
    closed = 0.10 if upper else 0.16
    shapes = {
        "blink": _lid_verts(sampler, cx, eye["z"], closed, upper),
        "wide": _lid_verts(sampler, cx, eye["z"],
                           1.02 if upper else -0.10, upper),
        "squint": _lid_verts(sampler, cx, eye["z"],
                             0.52 if upper else 0.24, upper, squeeze=0.0004),
    }
    return mesh, shapes


# ---------------------------------------------------------------------------
# eyebrows
# ---------------------------------------------------------------------------

def _brow_verts(sampler, cx, cz, tilt, arch=1.0, dz=0.0, inner_dz=0.0,
                thickness=1.0):
    brow = C.BROW
    hl = brow["length"] * 0.5
    verts = []
    for u in _u_values():
        # u = -1 at the inner (nose) end, +1 at the outer tail
        lo, hi = lens(u, brow["height"] * thickness,
                      brow["height"] * 0.62 * thickness,
                      top_power=0.42, bottom_power=0.50, peak_shift=-0.28)
        # brows taper to a point at the outer tail
        taper = 1.0 - 0.42 * max(0.0, u) ** 2
        lo, hi = lo * taper, hi * taper
        lift = dz + tilt * u * hl + inner_dz * max(0.0, -u) ** 1.4
        arc = arch * brow["height"] * 0.85 * max(0.0, 1.0 - (u - 0.15) ** 2)
        for i in range(NV):
            t = i / (NV - 1)
            v = lerp(lo, hi, t)
            off = brow["thickness"] * (0.35 + 0.65 * (1.0 - abs(2 * t - 1)))
            verts.append(sampler.offset_point(cx + u * hl, cz + v + lift + arc,
                                              off))
    return verts


def build_brow(sampler, side="L"):
    brow = C.BROW
    cx = brow["x"] if side == "L" else -brow["x"]
    mesh = MeshData(C.OBJ["brow_l" if side == "L" else "brow_r"])
    verts = _brow_verts(sampler, cx, brow["z"], brow["tilt"])
    idx = mesh.add_verts(verts)
    rows = [[idx[j * NV + i] for j in range(NU)] for i in range(NV)]
    _grid_faces(mesh, rows, HAIR_UV["brow"], flip=(side == "R"))
    mesh.mark("brow." + side, idx)

    t = brow["tilt"]
    shapes = {
        "up":     _brow_verts(sampler, cx, brow["z"], t, 1.25, dz=0.0125),
        "down":   _brow_verts(sampler, cx, brow["z"], t, 0.72, dz=-0.0080),
        "angry":  _brow_verts(sampler, cx, brow["z"], t - 0.34, 0.60,
                              dz=-0.0035, inner_dz=-0.0085),
        "sad":    _brow_verts(sampler, cx, brow["z"], t + 0.40, 1.05,
                              dz=0.0020, inner_dz=0.0090),
        "raise":  _brow_verts(sampler, cx, brow["z"], t - 0.10, 1.55,
                              dz=0.0060),
    }
    return mesh, shapes


# ---------------------------------------------------------------------------
# mouth
# ---------------------------------------------------------------------------

def _mouth_verts(sampler, half_w, half_top, half_bot, curve=0.0, dz=0.0,
                 corner_dz=0.0, offset=0.0009):
    m = C.MOUTH
    verts = []
    for u in _u_values():
        lo, hi = lens(u, half_top, half_bot, top_power=0.55, bottom_power=0.55)
        # `curve` bows the whole mouth into a smile or a frown
        bow = curve * (1.0 - u * u)
        corner = corner_dz * (u * u)
        for i in range(NV):
            t = i / (NV - 1)
            v = lerp(lo, hi, t)
            # the middle of the lip band pushes out, the rim tucks in
            off = offset + 0.0016 * (1.0 - abs(2 * t - 1))
            verts.append(sampler.offset_point(u * half_w,
                                              m["z"] + v + dz - bow + corner,
                                              off))
    return verts


def build_mouth(sampler):
    m = C.MOUTH
    hw, ht, hb = m["width"], m["height"], m["height"] * 0.85
    mesh = MeshData(C.OBJ["mouth"])
    verts = _mouth_verts(sampler, hw, ht, hb)
    idx = mesh.add_verts(verts)
    rows = [[idx[j * NV + i] for j in range(NU)] for i in range(NV)]
    _grid_faces(mesh, rows, SKIN_UV["mouth"], u_range=(0.03, 0.97),
                v_range=(0.03, 0.97))
    mesh.mark("mouth", idx)

    shapes = {
        "open":    _mouth_verts(sampler, hw * 0.96, ht * 1.25, hb * 3.9),
        "wide":    _mouth_verts(sampler, hw * 1.24, ht * 0.85, hb * 0.85),
        "narrow":  _mouth_verts(sampler, hw * 0.66, ht * 1.35, hb * 1.35),
        "smile":   _mouth_verts(sampler, hw * 1.10, ht * 0.90, hb * 1.15,
                                curve=0.0055, corner_dz=0.0042),
        "frown":   _mouth_verts(sampler, hw * 1.02, ht * 1.05, hb * 0.95,
                                curve=-0.0050, corner_dz=-0.0048),
        "pucker":  _mouth_verts(sampler, hw * 0.55, ht * 1.55, hb * 1.55,
                                offset=0.0038),
    }
    return mesh, shapes


def build_mouth_cavity(sampler):
    """A dark pocket behind the lips so an open mouth is not see-through."""
    m = C.MOUTH
    hw = m["width"] * 1.02
    ht, hb = m["height"] * 1.5, m["height"] * 4.2
    mesh = MeshData(C.OBJ["cavity"])
    verts = []
    for u in _u_values():
        lo, hi = lens(u, ht, hb, top_power=0.55, bottom_power=0.55)
        for i in range(NV):
            t = i / (NV - 1)
            v = lerp(lo, hi, t)
            # recede toward the middle so it reads as a hollow
            depth = -0.0035 - 0.0135 * (1.0 - abs(2 * t - 1)) * (1.0 - u * u)
            verts.append(sampler.offset_point(u * hw, m["z"] + v, depth))
    idx = mesh.add_verts(verts)
    rows = [[idx[j * NV + i] for j in range(NU)] for i in range(NV)]
    _grid_faces(mesh, rows, SKIN_UV["mouth"], u_range=(0.12, 0.88),
                v_range=(0.10, 0.55))
    mesh.mark("cavity", idx)
    return mesh, {}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_all(sampler):
    """Every face part, keyed by a short id used by the assembler."""
    parts = {}
    for side in ("L", "R"):
        parts[f"eye_{side.lower()}"] = build_eye(sampler, side) + ("eyes",)
        parts[f"lid_up_{side.lower()}"] = \
            build_eyelid(sampler, side, True) + ("skin",)
        parts[f"lid_lo_{side.lower()}"] = \
            build_eyelid(sampler, side, False) + ("skin",)
        parts[f"brow_{side.lower()}"] = build_brow(sampler, side) + ("hair",)
    parts["mouth"] = build_mouth(sampler) + ("mouth",)
    parts["cavity"] = build_mouth_cavity(sampler) + ("mouth",)
    return parts
