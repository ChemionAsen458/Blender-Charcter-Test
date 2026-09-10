"""Binding meshes to the skeleton.

Blender's automatic weights need a clean manifold cage and still guess
badly around the crotch and fingers, so weights are computed directly here:
distance to each bone's segment, with a smooth left/right mask so the
thighs do not grab each other across the crotch and the fingers stay
independent.

Face parts do not need falloff at all -- an eyeball or an eyebrow moves
rigidly with its own bone -- so they are bound with a single full-weight
group and deformed further by shape keys.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import config as C
from . import blendutil as BU

# Bones whose influence should be confined to one side of the body.  In the
# rest pose no limb crosses the midline, so a smooth sign test is safe.
SIDED_PREFIXES = ("thigh", "shin", "foot", "toe", "shoulder", "upper_arm",
                  "forearm", "hand", "index", "middle", "ring", "pinky",
                  "thumb")

# Per-bone reach in metres.  Small bones need a small reach or they steal
# vertices from their neighbours.
BONE_REACH = {
    "hips": 0.22, "spine": 0.24, "spine.001": 0.24, "chest": 0.26,
    "neck": 0.13, "head": 0.20,
    "shoulder": 0.14, "upper_arm": 0.13, "forearm": 0.11, "hand": 0.07,
    "thigh": 0.17, "shin": 0.15, "foot": 0.11, "toe": 0.08,
}
FINGER_REACH = 0.022
DEFAULT_REACH = 0.12


def _reach(name):
    base = name.rsplit(".", 1)[0] if name.endswith((".L", ".R")) else name
    if base in BONE_REACH:
        return BONE_REACH[base]
    if base.split(".")[0] in ("index", "middle", "ring", "pinky", "thumb"):
        return FINGER_REACH
    return BONE_REACH.get(name, DEFAULT_REACH)


def _side_of(name):
    if name.endswith(".L"):
        return 1.0
    if name.endswith(".R"):
        return -1.0
    return 0.0


def _is_sided(name):
    return name.split(".")[0] in SIDED_PREFIXES


def _point_segment_distance(p, a, b):
    ab = b - a
    denom = ab.dot(ab)
    if denom < 1e-12:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / denom))
    return (p - (a + ab * t)).length


def _smoothstep(e0, e1, x):
    if e1 - e0 < 1e-9:
        return 0.0 if x < e0 else 1.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def collect_bone_segments(rig):
    """(name, head, tail, reach, side) for every deform bone, in rest pose."""
    segs = []
    for bone in rig.data.bones:
        if not bone.use_deform:
            continue
        segs.append((bone.name, bone.head_local.copy(), bone.tail_local.copy(),
                     _reach(bone.name),
                     _side_of(bone.name) if _is_sided(bone.name) else 0.0))
    return segs


def auto_weight(obj, rig, segments=None, max_influences=4, power=3.0,
                side_band=0.030):
    """Envelope-style skinning for the body and the clothing."""
    segments = segments or collect_bone_segments(rig)
    obj.vertex_groups.clear()
    groups = {name: obj.vertex_groups.new(name=name)
              for (name, _, _, _, _) in segments}

    mw = obj.matrix_world
    for v in obj.data.vertices:
        p = mw @ v.co
        scored = []
        for (name, head, tail, reach, side) in segments:
            d = _point_segment_distance(p, head, tail)
            if d > reach * 2.6:
                continue
            w = 1.0 / (d ** power + 1e-7)
            # taper to nothing at the edge of the bone's reach
            w *= 1.0 - _smoothstep(reach, reach * 2.6, d)
            if side > 0.0:
                w *= _smoothstep(-side_band, side_band, p.x)
            elif side < 0.0:
                w *= _smoothstep(-side_band, side_band, -p.x)
            if w > 0.0:
                scored.append((w, name))
        if not scored:
            # fall back to the single closest bone so nothing is left loose
            best = min(segments,
                       key=lambda s: _point_segment_distance(p, s[1], s[2]))
            groups[best[0]].add([v.index], 1.0, 'REPLACE')
            continue
        scored.sort(reverse=True)
        scored = scored[:max_influences]
        total = sum(w for (w, _) in scored)
        for (w, name) in scored:
            groups[name].add([v.index], w / total, 'REPLACE')
    return groups


def rigid_weight(obj, bone_name):
    """Bind every vertex of `obj` fully to one bone."""
    obj.vertex_groups.clear()
    g = obj.vertex_groups.new(name=bone_name)
    g.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')
    return g


def blend_weight(obj, weights):
    """Bind to several bones with fixed weights, e.g. {"head": 1.0}."""
    obj.vertex_groups.clear()
    idx = [v.index for v in obj.data.vertices]
    for name, w in weights.items():
        obj.vertex_groups.new(name=name).add(idx, w, 'REPLACE')


def bind(obj, rig, segments=None, rigid=None):
    if rigid:
        rigid_weight(obj, rigid)
    else:
        auto_weight(obj, rig, segments)
    BU.add_armature_modifier(obj, rig)
    return obj


def weight_report(obj, top=6):
    """Which bones actually influence a mesh -- used by the build's checks."""
    totals = {}
    for v in obj.data.vertices:
        for g in v.groups:
            name = obj.vertex_groups[g.group].name
            totals[name] = totals.get(name, 0.0) + g.weight
    return sorted(totals.items(), key=lambda kv: -kv[1])[:top]


def unweighted_vertices(obj):
    return [v.index for v in obj.data.vertices
            if sum(g.weight for g in v.groups) < 1e-4]
