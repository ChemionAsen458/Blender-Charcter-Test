"""The base skin mesh: torso, head, arms, hands, legs and feet.

Everything is one watertight quad shell.  The torso and head are a single
lofted vertex grid; the arms are bridged into rectangular sockets cut out
of that grid, and the legs grow out of a fork in its bottom ring.  Feet and
hands are swept tubes bridged onto the ankle and wrist rings.

Because the vertex grid is regular, the caller always knows which ring and
column a vertex came from, which is what lets :mod:`character.face_rig`
find eyelid or lip vertices later without any guesswork.
"""

from __future__ import annotations

import math

from . import config as C
from .meshlib import (MeshData, ring_xy, superellipse, tube_rings, lerp,
                      vlerp, smoothstep, patch_boundary, in_patch, vadd,
                      vsub, vmul, vlen, vnorm)

N = C.TORSO_SEGMENTS
NL = C.LIMB_SEGMENTS
NG = C.LEG_SEGMENTS                 # leg ring: half the torso + 2 fork verts
SKIN = C.UV_ATLAS["skin"]


# ---------------------------------------------------------------------------
# torso + head
# ---------------------------------------------------------------------------

def _trunk_rings():
    """Every horizontal cross-section from crotch to crown, bottom-up."""
    rings = []
    for (z, rx, ry, cy, e) in C.TORSO_RINGS:
        rings.append(ring_xy(N, z, rx, ry, cy, e))
    jaw = C.JAW_COLUMN
    for (z, rx, ry, cy, e, neck_blend) in C.HEAD_RINGS:
        ring = ring_xy(N, z, rx, ry, cy, e)
        if neck_blend > 0.0:
            neck = ring_xy(N, z, jaw["rx"], jaw["ry"], jaw["cy"], 2.0)
            for k in range(N):
                a = 2.0 * math.pi * k / N
                # 0 at the face, 1 at the back of the skull
                backness = max(0.0, -math.cos(a)) ** 0.85
                w = neck_blend * backness
                ring[k] = vlerp(ring[k], neck[k], w)
        rings.append(ring)
    return rings


def _face_plane_y(z):
    """Y of the flat anime face plane at height `z` (more negative = forward)."""
    chin, crown = C.CHIN_Z, C.CROWN_Z
    t = (z - chin) / (crown - chin)
    # forehead recedes slightly, the mid-face is the most forward point
    return -0.094 + 0.030 * max(0.0, t - 0.62) ** 1.4 + 0.020 * max(0.0, 0.18 - t)


def _shape_head(verts, indices):
    """Turn a generic ovoid into an anime head.

    Applied as a displacement pass over the head rings so the underlying
    grid stays regular: flatten the face, sink the eye sockets, raise the
    brow ridge, add a small nose and lip volume, and taper the jaw.
    """
    eye = C.EYE
    for i in indices:
        x, y, z = verts[i]
        if z < C.HEAD_RINGS[0][0] - 0.02:
            continue

        # how strongly this vert faces forward, 1 at the face centre-line
        rxy = math.hypot(x, y) or 1e-6
        front = max(0.0, -y / rxy)
        side = min(1.0, abs(x) / 0.094)

        # -- flatten the face plane ------------------------------------
        zw = smoothstep(1.470, 1.512, z) * (1.0 - smoothstep(1.648, 1.700, z))
        f = C.FACE_FLATTEN * (front ** 1.6) * zw
        y = lerp(y, _face_plane_y(z), f)

        # -- jaw taper: pull the lower face in and back ----------------
        jaw = 1.0 - smoothstep(1.468, 1.548, z)
        x *= 1.0 - 0.06 * jaw * front
        y += 0.0035 * jaw * front
        # a defined mandible: push the jaw *corner* out while the front of
        # the chin keeps tapering, which is what makes a jawline read
        ax = abs(x)
        corner = smoothstep(0.020, 0.062, ax) * \
            (1.0 - smoothstep(0.062, 0.092, ax))
        jz = 1.0 - smoothstep(0.0, 0.030, abs(z - 1.498))
        x += 0.0060 * jz * corner * (1.0 if x >= 0 else -1.0)
        y -= 0.0030 * jz * corner * front

        # -- eye socket ------------------------------------------------
        # a shallow recess for the eye shells to sit in; the anime eye is
        # a surface decal, so this only has to read as a soft hollow
        dx = (abs(x) - eye["x"]) / 0.050
        dz = (z - eye["z"]) / 0.028
        d = math.hypot(dx, dz)
        socket = (1.0 - smoothstep(0.20, 1.25, d)) * front ** 1.1
        y += 0.0075 * socket
        # a ridge just above the socket reads as the upper lid crease
        crease = (1.0 - smoothstep(0.0, 0.60, abs(d - 1.15))) * front ** 1.4
        y -= 0.0026 * crease

        # -- brow ridge ------------------------------------------------
        brow = (1.0 - smoothstep(0.0, 0.034, abs(z - C.Z["brow"] - 0.004)))
        y -= 0.0052 * brow * front ** 1.3 * (1.0 - 0.35 * side)

        # -- nose: small, anime-scale, but wide enough to survive subsurf
        nz = 1.0 - smoothstep(0.0, 0.026, abs(z - C.Z["nose"]))
        nx = 1.0 - smoothstep(0.0, 0.040, abs(x))
        y -= 0.0190 * nz * (nx ** 1.2) * front
        # the bridge, fading up toward the brow
        bridge_t = smoothstep(C.Z["nose"] - 0.004, C.Z["brow"] + 0.006, z)
        y -= 0.0052 * (1.0 - bridge_t) * bridge_t * 4.0 * (nx ** 1.6) * front
        # nostril wings
        wing = (1.0 - smoothstep(0.014, 0.032, abs(x))) * \
               smoothstep(0.010, 0.030, abs(x))
        y -= 0.0040 * nz * wing * front

        # -- lips ------------------------------------------------------
        mz = 1.0 - smoothstep(0.0, 0.020, abs(z - C.Z["mouth"]))
        mx = 1.0 - smoothstep(0.0, 0.040, abs(x))
        y -= 0.0042 * mz * mx * front
        # the philtrum groove between nose and lip
        pz = 1.0 - smoothstep(0.0, 0.012, abs(z - (C.Z["mouth"] + 0.016)))
        y += 0.0016 * pz * (1.0 - smoothstep(0.0, 0.012, abs(x))) * front
        # chin
        cz = 1.0 - smoothstep(0.0, 0.030, abs(z - (C.CHIN_Z + 0.016)))
        y -= 0.0075 * cz * mx * front
        # and the crease under the lower lip that gives the chin an edge
        lz = 1.0 - smoothstep(0.0, 0.012, abs(z - (C.Z["mouth"] - 0.014)))
        y += 0.0030 * lz * mx * front

        # -- cheekbone -------------------------------------------------
        chz = 1.0 - smoothstep(0.0, 0.030, abs(z - 1.556))
        chx = smoothstep(0.028, 0.062, abs(x)) * \
            (1.0 - smoothstep(0.062, 0.090, abs(x)))
        y -= 0.0018 * chz * chx * front
        x += 0.0014 * chz * chx

        # -- back of the skull: fuller, anime silhouette ---------------
        back = max(0.0, y / rxy)
        y += 0.007 * back * smoothstep(1.560, 1.700, z)

        verts[i] = (x, y, z)


def _shape_torso(verts, indices):
    """Muscle definition on the trunk.

    Subtle on purpose -- the reference is a slim teenager, and the shirt
    covers most of it -- but enough that the bare mesh does not read as a
    shop mannequin: pectorals, a soft ab grid, the spine groove, the
    shoulder blades and a hint of the trapezius.
    """
    for i in indices:
        x, y, z = verts[i]
        rxy = math.hypot(x, y) or 1e-6
        front = max(0.0, -y / rxy)
        back = max(0.0, y / rxy)
        ax = abs(x)

        # -- pectorals -------------------------------------------------
        pz = 1.0 - smoothstep(0.0, 0.070, abs(z - 1.196))
        px = smoothstep(0.010, 0.055, ax) * (1.0 - smoothstep(0.088, 0.150, ax))
        y -= 0.0130 * pz * px * front ** 1.2
        # the sternum groove between them
        sz = 1.0 - smoothstep(0.0, 0.090, abs(z - 1.190))
        y += 0.0060 * sz * (1.0 - smoothstep(0.0, 0.022, ax)) * front ** 1.4
        # under-pec shadow line
        uz = 1.0 - smoothstep(0.0, 0.020, abs(z - 1.148))
        y += 0.0038 * uz * px * front

        # -- abdomen ---------------------------------------------------
        abz = smoothstep(1.010, 1.140, z) * (1.0 - smoothstep(1.140, 1.170, z))
        y -= 0.0050 * abz * (1.0 - smoothstep(0.0, 0.070, ax)) * front
        # linea alba
        y += 0.0034 * (1.0 - smoothstep(0.0, 0.016, ax)) * front * \
            smoothstep(0.990, 1.040, z) * (1.0 - smoothstep(1.150, 1.200, z))
        # obliques taper into the waist
        oz = smoothstep(0.960, 1.060, z) * (1.0 - smoothstep(1.060, 1.130, z))
        x -= 0.0040 * oz * smoothstep(0.070, 0.120, ax) * (1.0 if x >= 0 else -1.0)

        # -- spine groove ----------------------------------------------
        gz = smoothstep(0.960, 1.060, z) * (1.0 - smoothstep(1.300, 1.390, z))
        y -= 0.0075 * gz * (1.0 - smoothstep(0.0, 0.024, ax)) * back ** 1.3

        # -- shoulder blades -------------------------------------------
        bz = 1.0 - smoothstep(0.0, 0.060, abs(z - 1.262))
        bx = smoothstep(0.024, 0.070, ax) * (1.0 - smoothstep(0.110, 0.165, ax))
        y += 0.0070 * bz * bx * back ** 1.2

        # -- trapezius: fills the neck-to-shoulder slope ---------------
        tz = smoothstep(1.300, 1.392, z)
        y += 0.0060 * tz * back * (1.0 - smoothstep(0.030, 0.120, ax))
        z += 0.0045 * tz * (1.0 - smoothstep(0.020, 0.110, ax)) * back

        # -- gluteal shaping -------------------------------------------
        glz = 1.0 - smoothstep(0.0, 0.055, abs(z - 0.878))
        glx = 1.0 - smoothstep(0.030, 0.130, ax)
        y += 0.0090 * glz * glx * back ** 1.3
        # iliac crest / hip point
        hz = 1.0 - smoothstep(0.0, 0.040, abs(z - 0.930))
        x += 0.0035 * hz * smoothstep(0.080, 0.135, ax) * (1.0 if x >= 0 else -1.0)

        # -- collarbones -----------------------------------------------
        cz = 1.0 - smoothstep(0.0, 0.022, abs(z - 1.318))
        cx = smoothstep(0.018, 0.060, ax) * (1.0 - smoothstep(0.100, 0.160, ax))
        y += 0.0034 * cz * cx * front

        verts[i] = (x, y, z)


def _build_trunk(mesh):
    """Loft the trunk, cut the shoulder sockets and return useful loops."""
    rings = _trunk_rings()
    idx = [mesh.add_verts(r) for r in rings]

    n_torso = len(C.TORSO_RINGS)
    head_indices = [i for r in idx[n_torso - 1:] for i in r]
    torso_indices = [i for r in idx[:n_torso - 1] for i in r]
    _shape_torso(mesh.verts, torso_indices)
    _shape_head(mesh.verts, head_indices)

    sock = C.SHOULDER_SOCKET
    r0, r1 = sock["rows"]
    skip_l = in_patch(r0, r1, sock["cols_l"][0], sock["cols_l"][1], N)
    skip_r = in_patch(r0, r1, sock["cols_r"][0], sock["cols_r"][1], N)

    def skip(i, j):
        return skip_l(i, j) or skip_r(i, j)

    # torso rings share their top ring with the head loft
    seam = N // 2                      # put the UV seam down the spine
    mesh.loft_indices(idx[:n_torso], SKIN["torso"], skip=skip,
                      v_range=(0.02, 0.98), u_shift=seam)
    # the head goes into its own material slot: the face is lit separately
    # from the body, the way the reference rig splits `Skin` from `Skin Body`
    mesh.loft_indices(idx[n_torso - 1:], SKIN["head"], row_offset=n_torso - 1,
                      v_range=(0.02, 0.99), u_shift=seam,
                      mat=C.SKIN_SLOT_FACE)

    # crown cap
    mesh.cap_ring(idx[-1], SKIN["head"], uv_center=(0.5, 0.985),
                  uv_radius=0.012, mat=C.SKIN_SLOT_FACE)

    mesh.mark("head", head_indices)
    mesh.mark("torso", [i for r in idx[:n_torso] for i in r])

    socket_l = patch_boundary(idx, r0, r1, sock["cols_l"][0], sock["cols_l"][1], N)
    socket_r = patch_boundary(idx, r0, r1, sock["cols_r"][0], sock["cols_r"][1], N)
    return idx, socket_l, socket_r


# ---------------------------------------------------------------------------
# arms and hands
# ---------------------------------------------------------------------------

def _mirror_path(path):
    return [(-p[0], p[1], p[2], p[3]) for p in path]


def _arm_rings(side):
    path = C.ARM_PATH if side == "L" else _mirror_path(C.ARM_PATH)
    pts = [(p[0], p[1], p[2]) for p in path]
    radii = [p[3] for p in path]
    # forearms are ovals, not tubes
    squash = [1.00, 0.98, 0.94, 0.92, 0.90, 0.90, 0.92, 0.96]
    return tube_rings(pts, radii, NL, exponent=2.15, squash=squash)


def _build_arm(mesh, socket_loop, side):
    rings = _arm_rings(side)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, SKIN["arm"], v_range=(0.06, 0.97))
    mesh.bridge(socket_loop, idx[0], SKIN["arm"], v_range=(0.0, 0.06))
    mesh.mark("arm." + side, [i for r in idx for i in r])
    return idx[-1]


def _hand_rings(side):
    """Palm cross-sections, from the wrist down to the knuckle row."""
    s = 1.0 if side == "L" else -1.0
    hx = s * (C.WRIST[0] + 0.002)
    hy = C.WRIST[1]
    hw, hd = C.HAND["palm_half_w"], C.HAND["palm_half_d"]
    # (z, half_thickness_x, half_spread_y, squareness)
    profile = [
        (0.870, 0.0295, 0.0310, 2.1),
        (0.849, hd * 1.14, hw * 0.80, 2.4),
        (0.824, hd * 1.02, hw * 0.93, 2.8),
        (0.802, hd * 0.94, hw * 1.00, 3.0),
        (0.786, hd * 0.88, hw * 0.98, 3.0),
    ]
    rings = []
    for (z, rx, ry, e) in profile:
        # the palm cups slightly and drifts forward toward the fingers
        cy = hy - 0.004 * (0.870 - z) / 0.080
        rings.append(ring_xy(NL, z, rx, ry, cy, e, cx=hx))
    return rings


def _finger(mesh, base, direction, length, radius, name, side, taper=0.72,
            bend=0.0):
    """A tapered, slightly curled digit capped with a dome."""
    n = C.FINGER_SEGMENTS
    steps = 4
    pts, radii = [], []
    d = vnorm(direction)
    perp = vnorm((0.0, -d[2], d[1])) if abs(d[0]) < 0.9 else (0.0, 0.0, 1.0)
    for i in range(steps + 1):
        t = i / steps
        p = vadd(base, vmul(d, length * t))
        p = vadd(p, vmul(perp, bend * math.sin(math.pi * t) * length))
        pts.append(p)
        radii.append(radius * lerp(1.0, taper, t))
    rings = tube_rings(pts, radii, n, exponent=2.2)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, SKIN["hand"], v_range=(0.05, 0.85))
    mesh.cap_ring(idx[-1], SKIN["hand"], uv_center=(0.5, 0.93), uv_radius=0.04)
    mesh.mark("finger." + side, [i for r in idx for i in r])
    return idx[0]


def _build_hand(mesh, wrist_loop, side):
    s = 1.0 if side == "L" else -1.0
    rings = _hand_rings(side)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, SKIN["hand"], v_range=(0.06, 0.55))
    mesh.bridge(wrist_loop, idx[0], SKIN["hand"], v_range=(0.0, 0.06))
    mesh.cap_ring(idx[-1], SKIN["hand"], flip=True, uv_center=(0.5, 0.60),
                  uv_radius=0.05)
    mesh.mark("hand." + side, [i for r in idx for i in r])

    knuckle_z = 0.788
    hx = s * (C.WRIST[0] + 0.002)
    hy = C.WRIST[1] - 0.004
    for (name, base_u, spread, length, radius) in C.HAND["fingers"]:
        # base_u runs across the palm: -1 = pinky side (+Y), 1 = index (-Y)
        by = hy - base_u * C.HAND["palm_half_w"] * 0.74
        bx = hx + s * 0.001
        direction = (s * spread * 3.0, -spread * 6.0, -1.0)
        _finger(mesh, (bx, by, knuckle_z), direction, length, radius,
                name, side, bend=0.010)

    th = C.HAND["thumb"]
    tb = (hx - s * 0.016, hy - 0.030, 0.834)
    _finger(mesh, tb, (-s * 0.55, -0.62, -0.90), th["length"], th["radius"],
            "thumb", side, taper=0.80, bend=0.006)


# ---------------------------------------------------------------------------
# legs and feet
# ---------------------------------------------------------------------------

def fork_angles():
    """Angles of the crotch fork ring, indexed like the leg rings.

    Indices 0..N/2 come straight off the torso's bottom ring (0 deg at the
    front sweeping 180 deg round the outside to the back); the last vertex
    is the new inner-crotch vert at 270 deg.
    """
    half = N // 2
    ang = [math.pi * i / half for i in range(half + 1)]
    ang.append(1.5 * math.pi)
    return ang


def even_angles():
    return [2.0 * math.pi * i / NG for i in range(NG)]


def leg_rings(side, inflate=0.0, squash_extra=0.0):
    """Leg cross-sections from the crotch fork down to the ankle.

    The first few rings blend the fork's uneven vertex spacing into an
    even one so the thigh does not shear where it leaves the pelvis.
    """
    s = 1.0 if side == "L" else -1.0
    path = C.LEG_PATH
    fork_a, even_a = fork_angles(), even_angles()
    blend_rings = 3
    rings = []
    for pi, (x, y, z, r) in enumerate(path):
        t = min(1.0, pi / blend_rings)
        r = r + inflate
        # thighs are slightly oval, calves more so
        squash = lerp(0.94, 1.0, min(1.0, pi / 4.0)) + squash_extra
        cx, cy = s * x, y
        ring = []
        for k in range(NG):
            a = lerp(fork_a[k], even_a[k], t)
            if s < 0:
                a = -a          # mirror the winding for the right leg
            ring.append((cx + r * math.sin(a) * 1.0,
                         cy - r * math.cos(a) * squash,
                         z))
        rings.append(ring)
    return rings


def _build_leg(mesh, trunk_idx, side, crotch_verts):
    s = 1.0 if side == "L" else -1.0
    half = N // 2
    bottom = trunk_idx[0]

    # fork ring = the torso's bottom-ring half plus one new inner vert
    if side == "L":
        chain = [bottom[i % N] for i in range(0, half + 1)]
    else:
        chain = [bottom[i % N] for i in range(N, half - 1, -1)]
    inner = crotch_verts[side]
    fork_loop = chain + [inner]
    assert len(fork_loop) == NG, (len(fork_loop), NG)

    rings = leg_rings(side)
    idx = [mesh.add_verts(r) for r in rings[1:]]
    mesh.loft_indices([fork_loop] + idx, SKIN["leg"], v_range=(0.98, 0.10),
                      flip=(side == "R"))
    mesh.mark("leg." + side, [i for r in idx for i in r])
    return idx[-1]


def _build_foot(mesh, ankle_loop, side):
    s = 1.0 if side == "L" else -1.0
    f = C.FOOT
    x = s * f["x"]
    path = [
        (x, 0.006, f["ankle_z"] + 0.004),
        (x, 0.000, 0.052),
        (x, -0.018, 0.030),
        (x, -0.062, 0.026),
        (x, -0.106, 0.025),
        (x, -0.142, 0.023),
    ]
    radii = [0.0375, 0.038, 0.042, 0.044, 0.042, 0.030]
    squash = [1.00, 1.10, 1.35, 1.30, 1.15, 0.95]
    rings = tube_rings(path, radii, NG, exponent=2.3, squash=squash)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, SKIN["foot"], v_range=(0.05, 0.90))
    mesh.bridge(ankle_loop, idx[0], SKIN["foot"], v_range=(0.0, 0.05),
                flip=(side == "R"))
    mesh.cap_ring(idx[-1], SKIN["foot"], uv_center=(0.5, 0.95), uv_radius=0.04)

    # flatten the sole and square off the heel
    foot_ids = [i for r in idx for i in r]
    for i in foot_ids:
        px, py, pz = mesh.verts[i]
        if pz < f["sole_z"] + 0.014 and py < f["heel_y"] + 0.01:
            w = 1.0 - smoothstep(f["sole_z"], f["sole_z"] + 0.014, pz)
            pz = lerp(pz, f["sole_z"], 0.85 * w)
        mesh.verts[i] = (px, py, pz)
    mesh.mark("foot." + side, foot_ids)


# ---------------------------------------------------------------------------
# ears
# ---------------------------------------------------------------------------

def _build_ear(mesh, side):
    """A small, stylised ear that reads at silhouette without stealing focus.

    Four rings sweep outward from just inside the skull: a base ring buried
    in the head, a wide bowl, the helix rim, and a small closing ring.  The
    ear tilts back and tapers to a lobe at the bottom, which is most of
    what sells it once the hair covers the top half.
    """
    s = 1.0 if side == "L" else -1.0
    cx, cy, cz = s * 0.0800, 0.016, 1.566
    n = 12
    # (dx outward, half-height, half-width, dy back-shift, lobe pinch)
    specs = [
        (-0.004, 0.0195, 0.0105, 0.000, 0.30),
        ( 0.008, 0.0235, 0.0135, 0.001, 0.34),
        ( 0.016, 0.0225, 0.0120, 0.002, 0.36),
        ( 0.021, 0.0150, 0.0058, 0.003, 0.30),
    ]
    rings = []
    for (dx, h, w, dy, pinch) in specs:
        ring = []
        for k in range(n):
            a = 2.0 * math.pi * k / n
            cos_a, sin_a = math.cos(a), math.sin(a)
            # full and round at the top, pinched into a lobe at the bottom
            taper = 1.0 - pinch * max(0.0, -cos_a) ** 1.3
            ring.append((cx + s * dx - s * 0.005 * max(0.0, -cos_a),
                         cy + dy + w * sin_a * taper,
                         cz + h * cos_a - 0.004 * max(0.0, cos_a)))
        rings.append(ring)
    idx = [mesh.add_verts(r) for r in rings]
    mesh.loft_indices(idx, SKIN["ear"], v_range=(0.10, 0.88),
                      flip=(side == "R"))
    mesh.cap_ring(idx[-1], SKIN["ear"], flip=(side == "R"),
                  uv_center=(0.5, 0.94), uv_radius=0.03)
    mesh.cap_ring(idx[0], SKIN["ear"], flip=(side == "L"),
                  uv_center=(0.5, 0.04), uv_radius=0.03)
    mesh.mark("ear." + side, [i for r in idx for i in r])


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build():
    """Return the complete base body as a :class:`MeshData`."""
    mesh = MeshData(C.OBJ["body"])
    trunk_idx, socket_l, socket_r = _build_trunk(mesh)

    # the two extra verts that close the crotch fork
    z = C.LEG_PATH[0][2] - 0.020
    crotch = {
        "L": mesh.add_verts([(0.013, 0.002, z)])[0],
        "R": mesh.add_verts([(-0.013, 0.002, z)])[0],
    }

    for side, socket in (("L", socket_l), ("R", socket_r)):
        wrist = _build_arm(mesh, socket, side)
        _build_hand(mesh, wrist, side)
        ankle = _build_leg(mesh, trunk_idx, side, crotch)
        _build_foot(mesh, ankle, side)
        _build_ear(mesh, side)

    # crotch quad closing the fork: front-centre, left inner, back-centre,
    # right inner
    bottom = trunk_idx[0]
    mesh.add_face((bottom[0], crotch["L"], bottom[N // 2], crotch["R"]),
                  [(0.50, 0.30), (0.53, 0.27), (0.56, 0.30), (0.53, 0.33)])

    return mesh


# ---------------------------------------------------------------------------
# shared section lookups (clothing rides on the same profiles as the skin)
# ---------------------------------------------------------------------------

def torso_section(z):
    """Interpolate the torso profile to any height: (rx, ry, cy, exponent)."""
    rings = C.TORSO_RINGS
    if z <= rings[0][0]:
        return rings[0][1:]
    if z >= rings[-1][0]:
        return rings[-1][1:]
    for i in range(len(rings) - 1):
        z0, z1 = rings[i][0], rings[i + 1][0]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            return tuple(lerp(rings[i][k + 1], rings[i + 1][k + 1], t)
                         for k in range(4))
    return rings[-1][1:]


def torso_ring(z, inflate=0.0, segments=None):
    """A torso cross-section at `z`, grown outward by `inflate` metres."""
    rx, ry, cy, e = torso_section(z)
    n = segments or N
    return ring_xy(n, z, rx + inflate, ry + inflate, cy, e)


def arm_rings(side, inflate=0.0, first=0, last=None):
    """Arm tube sections, optionally inflated and truncated for a sleeve."""
    path = C.ARM_PATH if side == "L" else _mirror_path(C.ARM_PATH)
    last = len(path) if last is None else last
    seg = path[first:last]
    pts = [(p[0], p[1], p[2]) for p in seg]
    radii = [p[3] + inflate for p in seg]
    squash = [1.00, 0.98, 0.94, 0.92, 0.90, 0.90, 0.92, 0.96][first:last]
    return tube_rings(pts, radii, NL, exponent=2.15, squash=squash)


def crotch_points(inflate=0.0):
    z = C.LEG_PATH[0][2] - 0.020
    d = 0.013 + inflate * 0.4
    return {"L": (d, 0.002, z - inflate * 0.5),
            "R": (-d, 0.002, z - inflate * 0.5)}
