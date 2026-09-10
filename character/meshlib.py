"""Pure-python mesh construction helpers.

Nothing in this module imports :mod:`bpy`, which keeps the geometry maths
unit-testable outside Blender.  :func:`to_blender_object` is the single
hand-off point into Blender data.

The whole character is built from three primitives:

``ring``      a closed cross-section (a superellipse)
``loft``      a stack of rings bridged into a quad tube
``fork``      one ring splitting into two (used for the crotch)

Because every vertex is placed by a parametrisation we know, UVs are
assigned analytically instead of being unwrapped -- each region lands in a
known rectangle of the atlas, which is what makes the texture templates in
``tools/generate_textures.py`` line up with the model.
"""

from __future__ import annotations

import math

Vec3 = tuple


# ---------------------------------------------------------------------------
# small vector helpers (kept local so this file has no dependencies)
# ---------------------------------------------------------------------------

def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def vnorm(a):
    n = vlen(a)
    if n < 1e-12:
        return (0.0, 0.0, 1.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def lerp(a, b, t):
    return a + (b - a) * t


def vlerp(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def smoothstep(edge0, edge1, x):
    if edge1 - edge0 < 1e-9:
        return 0.0 if x < edge0 else 1.0
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# cross-sections
# ---------------------------------------------------------------------------

def superellipse(n, rx, ry, exponent=2.0, phase=0.0):
    """`n` points around a superellipse in the XY plane.

    ``exponent`` 2.0 gives a true ellipse; larger values square it off,
    which is what makes a rib-cage read as a torso rather than a tube.
    The character faces -Y (Blender convention), so point 0 sits at the
    front and the ring winds front -> +X (character's left) -> back -> -X.
    With ``n`` = 24 that puts the face at column 0, the left flank at 6,
    the spine at 12 and the right flank at 18.
    """
    pts = []
    e = 2.0 / exponent
    for i in range(n):
        t = phase + 2.0 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        # signed power keeps the curve continuous through the axes
        x = rx * math.copysign(abs(s) ** e, s)
        y = -ry * math.copysign(abs(c) ** e, c)
        pts.append((x, y))
    return pts


def ring_xy(n, z, rx, ry, cy=0.0, exponent=2.0, cx=0.0):
    """A horizontal cross-section at height `z`."""
    return [(cx + x, cy + y, z) for (x, y) in superellipse(n, rx, ry, exponent)]


# ---------------------------------------------------------------------------
# paths and frames
# ---------------------------------------------------------------------------

def parallel_frames(points, up=(0.0, -1.0, 0.0)):
    """Rotation-minimising frames along a polyline.

    Returns a list of ``(tangent, normal, binormal)``.  Parallel transport
    stops limb tubes from corkscrewing where the path bends, which would
    otherwise show up as twisted UVs on the arms and legs.
    """
    n = len(points)
    tangents = []
    for i in range(n):
        if i == 0:
            t = vsub(points[1], points[0])
        elif i == n - 1:
            t = vsub(points[-1], points[-2])
        else:
            t = vsub(points[i + 1], points[i - 1])
        tangents.append(vnorm(t))

    # seed the first frame from `up`, made perpendicular to the tangent
    t0 = tangents[0]
    ref = up
    if abs(vdot(ref, t0)) > 0.99:
        ref = (1.0, 0.0, 0.0)
    nrm = vnorm(vsub(ref, vmul(t0, vdot(ref, t0))))
    frames = []
    for i in range(n):
        t = tangents[i]
        if i > 0:
            # transport the previous normal onto the new tangent
            prev_t = tangents[i - 1]
            axis = vcross(prev_t, t)
            if vlen(axis) > 1e-9:
                axis = vnorm(axis)
                angle = math.acos(max(-1.0, min(1.0, vdot(prev_t, t))))
                nrm = _rotate_about(nrm, axis, angle)
            nrm = vnorm(vsub(nrm, vmul(t, vdot(nrm, t))))
        b = vnorm(vcross(t, nrm))
        frames.append((t, nrm, b))
    return frames


def _rotate_about(v, axis, angle):
    c, s = math.cos(angle), math.sin(angle)
    return vadd(vadd(vmul(v, c), vmul(vcross(axis, v), s)),
                vmul(axis, vdot(axis, v) * (1.0 - c)))


def tube_rings(path, radii, segments, exponent=2.0, squash=None, phase=0.0):
    """Rings swept along `path`, one per path point.

    `squash` optionally scales the binormal axis per ring so a limb can be
    oval rather than round (thighs and forearms both are).
    """
    frames = parallel_frames(path)
    rings = []
    for i, p in enumerate(path):
        _, nrm, b = frames[i]
        r = radii[i]
        sq = 1.0 if squash is None else squash[i]
        prof = superellipse(segments, r, r * sq, exponent, phase)
        ring = []
        for (u, v) in prof:
            # u runs along the normal, v along the binormal
            ring.append(vadd(p, vadd(vmul(nrm, v), vmul(b, u))))
        rings.append(ring)
    return rings


# ---------------------------------------------------------------------------
# UV helper
# ---------------------------------------------------------------------------

def in_rect(rect, u, v):
    """Map a 0-1 parameter pair into an atlas rectangle."""
    u0, v0, u1, v1 = rect
    return (u0 + u * (u1 - u0), v0 + v * (v1 - v0))


# ---------------------------------------------------------------------------
# mesh container
# ---------------------------------------------------------------------------

class MeshData:
    """Verts, faces, per-loop UVs and per-face material slots."""

    def __init__(self, name="mesh"):
        self.name = name
        self.verts: list = []
        self.faces: list = []
        self.uvs: list = []          # one list of (u, v) per face loop
        self.mats: list = []         # material slot index per face
        self.groups: dict = {}       # vertex-group name -> {vert index: weight}
        self.marks: dict = {}        # named vertex-index lists for later use

    # -- building -------------------------------------------------------
    def add_verts(self, verts):
        start = len(self.verts)
        self.verts.extend(tuple(float(c) for c in v) for v in verts)
        return list(range(start, len(self.verts)))

    def add_face(self, idx, uvs=None, mat=0):
        self.faces.append(tuple(idx))
        if uvs is None:
            uvs = [(0.5, 0.5)] * len(idx)
        self.uvs.append([tuple(uv) for uv in uvs])
        self.mats.append(mat)

    def mark(self, key, indices):
        self.marks.setdefault(key, []).extend(indices)

    def weight(self, group, indices, value=1.0):
        g = self.groups.setdefault(group, {})
        for i in indices:
            g[i] = max(g.get(i, 0.0), value)

    # -- combining ------------------------------------------------------
    def merge(self, other, vert_offset_map=None):
        """Append `other` into this mesh, returning the index offset."""
        off = len(self.verts)
        self.verts.extend(other.verts)
        for f, uv, m in zip(other.faces, other.uvs, other.mats):
            self.faces.append(tuple(i + off for i in f))
            self.uvs.append(list(uv))
            self.mats.append(m)
        for g, w in other.groups.items():
            dst = self.groups.setdefault(g, {})
            for i, val in w.items():
                dst[i + off] = max(dst.get(i + off, 0.0), val)
        for k, idx in other.marks.items():
            self.marks.setdefault(k, []).extend(i + off for i in idx)
        if vert_offset_map is not None:
            vert_offset_map.append(off)
        return off

    def mirrored_x(self, uv_shift=None):
        """A mirror copy across X with the winding flipped.

        UVs are copied unchanged so both sides sample the same texture,
        unless `uv_shift` supplies a per-uv transform.
        """
        m = MeshData(self.name + ".mirror")
        m.verts = [(-x, y, z) for (x, y, z) in self.verts]
        for f, uv, mat in zip(self.faces, self.uvs, self.mats):
            m.faces.append(tuple(reversed(f)))
            flipped = list(reversed(uv))
            if uv_shift is not None:
                flipped = [uv_shift(u, v) for (u, v) in flipped]
            m.uvs.append(flipped)
            m.mats.append(mat)
        for g, w in self.groups.items():
            gm = _flip_side_name(g)
            m.groups[gm] = dict(w)
        for k, idx in self.marks.items():
            m.marks[_flip_side_name(k)] = list(idx)
        return m

    # -- primitives -----------------------------------------------------
    def add_loft(self, rings, rect, closed=True, mat=0,
                 u_range=(0.0, 1.0), v_range=(0.0, 1.0), flip=False,
                 v_by_length=True, skip=None):
        """Bridge a stack of rings into quads with analytic UVs.

        `skip(ring_index, column)` may veto individual quads; that is how
        the shoulder sockets are left open for the arms to be bridged into.

        Returns the list of per-ring vertex-index lists so callers can keep
        hold of a boundary loop (for forks and limb sockets).
        """
        idx_rings = [self.add_verts(r) for r in rings]
        self.loft_indices(idx_rings, rect, closed=closed, mat=mat,
                          u_range=u_range, v_range=v_range, flip=flip,
                          v_by_length=v_by_length, skip=skip)
        return idx_rings

    def loft_indices(self, idx_rings, rect, closed=True, mat=0,
                     u_range=(0.0, 1.0), v_range=(0.0, 1.0), flip=False,
                     v_by_length=True, skip=None, row_offset=0, u_shift=0):
        """Face-only loft over vertex rings that already exist.

        Lets one continuous vertex grid -- the torso and head share a
        vertex ring at the neck -- be split across several UV rectangles
        without duplicating or splitting the geometry.

        `u_shift` rotates which column lands at U = 0, which is how the
        texture seam is moved round to the back of the head and torso
        instead of running down the middle of the face.
        """
        rings = [[self.verts[i] for i in r] for r in idx_rings]
        vs = _ring_v_params(rings) if v_by_length else \
            [i / max(1, len(rings) - 1) for i in range(len(rings))]
        n = len(idx_rings[0])
        cols = n if closed else n - 1
        for i in range(len(idx_rings) - 1):
            a, b = idx_rings[i], idx_rings[i + 1]
            v0 = lerp(v_range[0], v_range[1], vs[i])
            v1 = lerp(v_range[0], v_range[1], vs[i + 1])
            for j in range(cols):
                if skip is not None and skip(i + row_offset, j):
                    continue
                k = (j + 1) % n
                col = ((j + u_shift) % n) if closed else j
                u0 = lerp(u_range[0], u_range[1], col / cols)
                u1 = lerp(u_range[0], u_range[1], (col + 1) / cols)
                quad = (a[j], a[k], b[k], b[j])
                uvq = [in_rect(rect, u0, v0), in_rect(rect, u1, v0),
                       in_rect(rect, u1, v1), in_rect(rect, u0, v1)]
                if flip:
                    quad = tuple(reversed(quad))
                    uvq = list(reversed(uvq))
                self.add_face(quad, uvq, mat)
        return idx_rings

    def add_ring_verts(self, ring):
        return self.add_verts(ring)

    def bridge(self, loop_a, loop_b, rect, mat=0, align=True,
               u_range=(0.0, 1.0), v_range=(0.0, 1.0), flip=False,
               positions_a=None, positions_b=None):
        """Bridge two equal-length closed index loops into a quad band."""
        assert len(loop_a) == len(loop_b), "bridge needs equal loop lengths"
        b = list(loop_b)
        if align:
            pa = positions_a or [self.verts[i] for i in loop_a]
            pb = positions_b or [self.verts[i] for i in loop_b]
            b = _align_loop(loop_a, b, pa, pb)
        n = len(loop_a)
        for j in range(n):
            k = (j + 1) % n
            u0 = lerp(u_range[0], u_range[1], j / n)
            u1 = lerp(u_range[0], u_range[1], (j + 1) / n)
            quad = (loop_a[j], loop_a[k], b[k], b[j])
            uvq = [in_rect(rect, u0, v_range[0]), in_rect(rect, u1, v_range[0]),
                   in_rect(rect, u1, v_range[1]), in_rect(rect, u0, v_range[1])]
            if flip:
                quad = tuple(reversed(quad))
                uvq = list(reversed(uvq))
            self.add_face(quad, uvq, mat)
        return b

    def cap_ring(self, loop, rect, mat=0, flip=False, uv_center=(0.5, 0.5),
                 uv_radius=0.45):
        """Close a ring with a fan around a new centre vertex."""
        pts = [self.verts[i] for i in loop]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        c = self.add_verts([(cx, cy, cz)])[0]
        n = len(loop)
        for j in range(n):
            k = (j + 1) % n
            a0 = 2.0 * math.pi * j / n
            a1 = 2.0 * math.pi * k / n
            uv0 = in_rect(rect, uv_center[0] + uv_radius * math.cos(a0),
                          uv_center[1] + uv_radius * math.sin(a0))
            uv1 = in_rect(rect, uv_center[0] + uv_radius * math.cos(a1),
                          uv_center[1] + uv_radius * math.sin(a1))
            uvc = in_rect(rect, uv_center[0], uv_center[1])
            tri = (loop[j], loop[k], c)
            uvt = [uv0, uv1, uvc]
            if flip:
                tri = tuple(reversed(tri))
                uvt = list(reversed(uvt))
            self.add_face(tri, uvt, mat)
        return c

    def add_ngon(self, loop, rect, mat=0, flip=False):
        n = len(loop)
        uvs = []
        for j in range(n):
            a = 2.0 * math.pi * j / n
            uvs.append(in_rect(rect, 0.5 + 0.4 * math.cos(a),
                               0.5 + 0.4 * math.sin(a)))
        face = tuple(loop)
        if flip:
            face = tuple(reversed(face))
            uvs = list(reversed(uvs))
        self.add_face(face, uvs, mat)

    def add_grid(self, rows, rect, mat=0, flip=False,
                 u_range=(0.0, 1.0), v_range=(0.0, 1.0)):
        """An open quad grid from a list of vertex rows (equal length)."""
        idx_rows = [self.add_verts(r) for r in rows]
        nr, nc = len(rows), len(rows[0])
        for i in range(nr - 1):
            for j in range(nc - 1):
                v0 = lerp(v_range[0], v_range[1], i / (nr - 1))
                v1 = lerp(v_range[0], v_range[1], (i + 1) / (nr - 1))
                u0 = lerp(u_range[0], u_range[1], j / (nc - 1))
                u1 = lerp(u_range[0], u_range[1], (j + 1) / (nc - 1))
                quad = (idx_rows[i][j], idx_rows[i][j + 1],
                        idx_rows[i + 1][j + 1], idx_rows[i + 1][j])
                uvq = [in_rect(rect, u0, v0), in_rect(rect, u1, v0),
                       in_rect(rect, u1, v1), in_rect(rect, u0, v1)]
                if flip:
                    quad = tuple(reversed(quad))
                    uvq = list(reversed(uvq))
                self.add_face(quad, uvq, mat)
        return idx_rows

    # -- editing --------------------------------------------------------
    def remap_uv_rect(self, predicate, src_rect, dst_rect):
        """Move whole faces from one atlas rectangle to another.

        Used for the shoe soles: they are lofted as part of the upper, then
        the faces below the sole line are re-pointed at the white sole
        patch of the texture, so one material paints both.
        """
        moved = 0
        for fi, face in enumerate(self.faces):
            pts = [self.verts[i] for i in face]
            if not predicate(pts):
                continue
            self.uvs[fi] = [_rect_remap(uv, src_rect, dst_rect)
                            for uv in self.uvs[fi]]
            moved += 1
        return moved

    def transform(self, fn, indices=None):
        if indices is None:
            self.verts = [fn(v) for v in self.verts]
        else:
            for i in indices:
                self.verts[i] = fn(self.verts[i])

    def bounds(self):
        xs = [v[0] for v in self.verts]
        ys = [v[1] for v in self.verts]
        zs = [v[2] for v in self.verts]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _ring_v_params(rings):
    """Arc-length V so texel density stays even along a long loft."""
    centres = []
    for r in rings:
        n = len(r)
        centres.append((sum(p[0] for p in r) / n,
                        sum(p[1] for p in r) / n,
                        sum(p[2] for p in r) / n))
    acc = [0.0]
    for i in range(1, len(centres)):
        acc.append(acc[-1] + vlen(vsub(centres[i], centres[i - 1])))
    total = acc[-1] or 1.0
    return [a / total for a in acc]


def _align_loop(loop_a, loop_b, pos_a, pos_b):
    """Rotate/reverse `loop_b` so bridging it to `loop_a` does not twist."""
    n = len(loop_a)
    best, best_cost = list(loop_b), float("inf")
    for reverse in (False, True):
        order = list(range(n))
        if reverse:
            order = list(reversed(order))
        for shift in range(n):
            cost = 0.0
            for j in range(n):
                pb = pos_b[order[(j + shift) % n]]
                cost += vlen(vsub(pos_a[j], pb))
                if cost >= best_cost:
                    break
            if cost < best_cost:
                best_cost = cost
                best = [loop_b[order[(j + shift) % n]] for j in range(n)]
    return best


def _flip_side_name(name):
    if name.endswith(".L"):
        return name[:-2] + ".R"
    if name.endswith(".R"):
        return name[:-2] + ".L"
    return name


# ---------------------------------------------------------------------------
# fork: one ring splitting into two (the crotch)
# ---------------------------------------------------------------------------

def fork_ring(mesh, parent_loop, left_ring, right_ring, rect, mat=0,
              front_index=0):
    """Split `parent_loop` (N verts) into two child rings of N/2 + 1.

    The parent's front-centre and back-centre verts become the fork points;
    each half of the parent bridges to one child ring and the remaining
    hexagonal gap between the two children is filled with an n-gon.
    """
    n = len(parent_loop)
    assert n % 2 == 0, "fork needs an even parent ring"
    half = n // 2
    assert len(left_ring) == half + 1, "child ring must be N/2 + 1"
    assert len(right_ring) == half + 1

    front = front_index
    back = (front_index + half) % n

    left_chain = [parent_loop[(front + i) % n] for i in range(half + 1)]
    right_chain = [parent_loop[(back + i) % n] for i in range(half + 1)]

    li = mesh.add_verts(left_ring)
    ri = mesh.add_verts(right_ring)

    def bridge_chain(chain, child, u0, u1):
        m = len(chain)
        for j in range(m - 1):
            ua = lerp(u0, u1, j / (m - 1))
            ub = lerp(u0, u1, (j + 1) / (m - 1))
            mesh.add_face(
                (chain[j], chain[j + 1], child[j + 1], child[j]),
                [in_rect(rect, ua, 1.0), in_rect(rect, ub, 1.0),
                 in_rect(rect, ub, 0.72), in_rect(rect, ua, 0.72)], mat)

    bridge_chain(left_chain, li, 0.0, 0.5)
    bridge_chain(right_chain, ri, 0.5, 1.0)

    # hexagonal crotch gap -> centre vertex + fan, which subdivides cleanly
    hole = [li[0], li[-1], right_chain[0], ri[0], ri[-1], left_chain[0]]
    # de-duplicate consecutive repeats (the fork points are shared)
    dedup = []
    for v in hole:
        if not dedup or dedup[-1] != v:
            dedup.append(v)
    if dedup[0] == dedup[-1]:
        dedup.pop()
    mesh.cap_ring(dedup, rect, mat, flip=True, uv_center=(0.5, 0.62),
                  uv_radius=0.06)
    return li, ri


def patch_boundary(idx_rings, r0, r1, c0, c1, n):
    """Ordered boundary loop of a rectangular hole in a lofted grid.

    The hole covers quads ``(r, c)`` for ``r0 <= r < r1`` and
    ``c0 <= c < c1`` (columns wrap modulo `n`).  The returned loop has
    ``2 * ((r1 - r0) + (c1 - c0))`` vertices, which is the number a limb
    tube must have for a clean, all-quad bridge.
    """
    loop = []
    for c in range(c0, c1 + 1):
        loop.append(idx_rings[r0][c % n])
    for r in range(r0 + 1, r1 + 1):
        loop.append(idx_rings[r][c1 % n])
    for c in range(c1 - 1, c0 - 1, -1):
        loop.append(idx_rings[r1][c % n])
    for r in range(r1 - 1, r0, -1):
        loop.append(idx_rings[r][c0 % n])
    return loop


def in_patch(r0, r1, c0, c1, n):
    """A `skip` predicate for :meth:`MeshData.add_loft`."""
    cols = {c % n for c in range(c0, c1)}

    def _skip(i, j):
        return r0 <= i < r1 and j in cols

    return _skip


def _rect_remap(uv, src, dst):
    su0, sv0, su1, sv1 = src
    du0, dv0, du1, dv1 = dst
    u = (uv[0] - su0) / max(1e-9, su1 - su0)
    v = (uv[1] - sv0) / max(1e-9, sv1 - sv0)
    return (du0 + u * (du1 - du0), dv0 + v * (dv1 - dv0))
