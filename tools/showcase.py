#!/usr/bin/env python3
"""Render the sheets that prove the rig works: turnaround, expressions,
and the shadow rig sweeping its own controls.

    python3 -m tools.showcase --blend build/kaito.blend --out build/preview
"""

from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy
from mathutils import Vector

from tools import preview


def _rig():
    from character import config as C
    return bpy.data.objects.get(C.RIG_NAME)


# Custom-property values as the rig was built, captured before the first
# sheet is rendered.  Resetting only the transforms is not enough: every
# look here is a set of *properties*, so without restoring them each frame
# inherits the previous one's grade and the sheet stops being a comparison.
_BASELINE = {}


def _snapshot(rig):
    """Remember every pose-bone custom property at its build-time value."""
    _BASELINE.clear()
    for pb in rig.pose.bones:
        props = {}
        for key in pb.keys():
            if key.startswith("_"):
                continue
            value = pb[key]
            # IDPropertyArray does not survive a plain reference
            props[key] = list(value) if hasattr(value, "__len__") \
                and not isinstance(value, str) else value
        if props:
            _BASELINE[pb.name] = props
    return _BASELINE


def _reset(rig):
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    for name, props in _BASELINE.items():
        pb = rig.pose.bones.get(name)
        if pb is None:
            continue
        for key, value in props.items():
            try:
                pb[key] = value
            except (TypeError, KeyError):
                pass
    rig.update_tag()
    for mat in bpy.data.materials:
        if mat.node_tree is not None:
            mat.node_tree.update_tag()
    bpy.context.evaluated_depsgraph_get().update()


def _apply(rig, pose):
    """pose: {bone: {"loc": (...), "rot": (...)}} or {bone: {prop: value}}."""
    for bone, spec in pose.items():
        pb = rig.pose.bones.get(bone)
        if pb is None:
            continue
        for key, value in spec.items():
            if key == "loc":
                pb.location = value
            elif key == "rot":
                pb.rotation_euler = tuple(math.radians(a) for a in value)
            else:
                pb[key] = value
    rig.update_tag()
    for mat in bpy.data.materials:
        if mat.node_tree is not None:
            mat.node_tree.update_tag()
    bpy.context.evaluated_depsgraph_get().update()


def _meshes(for_framing=True):
    """Renderable meshes.

    `for_framing` drops the set dressing: the six-metre shadow-catcher
    plane would otherwise decide the camera's orthographic scale and
    shrink the character to a speck in the middle of the frame.
    """
    from character import config as C
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.hide_render:
            continue
        if for_framing and (o.name.startswith(C.SET_PREFIX)
                            or o.name == C.OBJ["contact_shadow"]):
            continue
        out.append(o)
    return out


EXPRESSIONS = {
    "neutral": {},
    "blink": {"lid_up.L": {"loc": (0, 0, -0.012)},
              "lid_up.R": {"loc": (0, 0, -0.012)},
              "lid_lo.L": {"loc": (0, 0, 0.010)},
              "lid_lo.R": {"loc": (0, 0, 0.010)}},
    "angry": {"face_props": {"brow_angry_l": 1.0, "brow_angry_r": 1.0,
                             "squint_l": 0.55, "squint_r": 0.55,
                             "mouth_frown": 0.7},
              "brow.L": {"loc": (0, 0, -0.008)},
              "brow.R": {"loc": (0, 0, -0.008)}},
    "surprised": {"brow.L": {"loc": (0, 0, 0.010)},
                  "brow.R": {"loc": (0, 0, 0.010)},
                  "lid_up.L": {"loc": (0, 0, 0.010)},
                  "lid_up.R": {"loc": (0, 0, 0.010)},
                  "mouth": {"loc": (0, 0, -0.010)},
                  "jaw": {"rot": (14, 0, 0)}},
    "smile": {"face_props": {"mouth_smile": 1.0, "squint_l": 0.35,
                             "squint_r": 0.35},
              "mouth_corner.L": {"loc": (0, 0, 0.009)},
              "mouth_corner.R": {"loc": (0, 0, 0.009)},
              "brow.L": {"loc": (0, 0, 0.005)},
              "brow.R": {"loc": (0, 0, 0.005)}},
    "look_left": {"eye_target": {"loc": (0.14, 0.0, 0.02)},
                  "face_props": {"brow_arch_l": 0.4, "brow_arch_r": 0.4}},
}

SHADOW_LOOKS = {
    "default": {},
    "hard_key": {"SHD-ctrl": {"shadow_softness": 0.008,
                              "shadow_threshold": 0.56,
                              "shadow_strength": 1.0}},
    "low_key": {"SHD-key": {"rot": (0, 0, 118)},
                "SHD-ctrl": {"shadow_threshold": 0.72,
                             "shadow_softness": 0.02,
                             "rim_strength": 1.5}},
    "warm_soft": {"SHD-ctrl": {"shadow_softness": 0.22,
                               "shadow_tint_r": 0.92,
                               "shadow_tint_g": 0.72,
                               "shadow_tint_b": 0.66,
                               "shadow_threshold": 0.42}},
    "bang_shadow": {"SHD-face": {"loc": (0, 0, 0.055)},
                    "SHD-ctrl": {"face_shadow_softness": 0.06}},
}

# Per-region grading: the same pose and the same master control, with only
# one region's offsets moved.  Framed on the head and shoulders because
# that is where face-versus-body separation actually reads.
REGION_LOOKS = {
    "uniform": {},
    "face_lifted": {"SUN-face": {"threshold_offset": -0.22,
                                 "softness_offset": 0.05}},
    "hair_hard": {"SUN-hair": {"threshold_offset": 0.18,
                               "softness_offset": -0.035}},
    "body_deep": {"SUN-body": {"threshold_offset": 0.22,
                               "strength_offset": 0.12}},
}

POSES = {
    "a_pose": {},
    "action": {"root": {"rot": (0, 0, -14)},
               "torso": {"loc": (0.0, 0.02, -0.05), "rot": (4, 0, 8)},
               "hand_ik.L": {"loc": (-0.10, -0.30, 0.36), "rot": (-40, 0, 30)},
               "hand_ik.R": {"loc": (0.06, 0.16, 0.10)},
               "foot_ik.L": {"loc": (0.0, -0.18, 0.0)},
               "foot_ik.R": {"loc": (0.0, 0.16, 0.0), "rot": (18, 0, 0)},
               "chest_ctrl": {"rot": (-6, 0, -10)},
               "head_ctrl": {"rot": (4, 0, 12)},
               "face_props": {"brow_angry_l": 0.8, "brow_angry_r": 0.8},
               "SHD-contact": {"loc": (0.0, -0.04, 0.0)}},
}


def render_turnaround(out_dir, size=(620, 1080), samples=48):
    preview.setup_render(width=size[0], height=size[1], samples=samples)
    paths = preview.render_views(out_dir, views=("front", "side", "back",
                                                 "three_q"),
                                 prefix="turnaround", width=size[0],
                                 height=size[1], objects=_meshes(),
                                 samples=samples)
    return preview.contact_sheet(paths,
                                 os.path.join(out_dir, "turnaround.png"))


def render_expressions(out_dir, rig, size=520, samples=40):
    paths = []
    for name, pose in EXPRESSIONS.items():
        _reset(rig)
        _apply(rig, pose)
        preview.setup_render(width=size, height=size, samples=samples)
        p = preview.render_views(out_dir, views=("front",),
                                 prefix=f"expr_{name}", width=size,
                                 height=size, focus=Vector((0, 0, 1.60)),
                                 ortho_scale=0.32, objects=_meshes(),
                                 samples=samples)
        paths.extend(p)
    _reset(rig)
    return preview.contact_sheet(paths,
                                 os.path.join(out_dir, "expressions.png"))


def render_shadow_looks(out_dir, rig, size=440, samples=40):
    """One three-quarter view per look, framed on the whole figure.

    The point of the sheet is that one control changes the shading
    everywhere at once, so it has to show enough of the character for that
    to be visible.
    """
    paths = []
    for name, pose in SHADOW_LOOKS.items():
        _reset(rig)
        _apply(rig, pose)
        height = int(size * 1.8)
        preview.setup_render(width=size, height=height, samples=samples)
        p = preview.render_views(out_dir, views=("three_q",),
                                 prefix=f"shadow_{name}", width=size,
                                 height=height, focus=Vector((0, 0, 0.90)),
                                 ortho_scale=1.95, objects=_meshes(),
                                 samples=samples)
        paths.extend(p)
    _reset(rig)
    return preview.contact_sheet(paths,
                                 os.path.join(out_dir, "shadow_rig.png"))


def render_regions(out_dir, rig, size=440, samples=40):
    """One frame per region look, framed on the head and shoulders.

    `SHD-ctrl` is untouched across the whole sheet -- only a single region
    control moves between frames, so any difference is that region alone.
    """
    paths = []
    for name, pose in REGION_LOOKS.items():
        _reset(rig)
        _apply(rig, pose)
        height = int(size * 1.15)
        preview.setup_render(width=size, height=height, samples=samples)
        p = preview.render_views(out_dir, views=("three_q",),
                                 prefix=f"region_{name}", width=size,
                                 height=height, focus=Vector((0, 0, 1.50)),
                                 ortho_scale=0.52, objects=_meshes(),
                                 samples=samples)
        paths.extend(p)
    _reset(rig)
    return preview.contact_sheet(paths,
                                 os.path.join(out_dir, "regions.png"))


def render_poses(out_dir, rig, size=(560, 1000), samples=40):
    paths = []
    for name, pose in POSES.items():
        _reset(rig)
        _apply(rig, pose)
        preview.setup_render(width=size[0], height=size[1], samples=samples)
        p = preview.render_views(out_dir, views=("front", "three_q"),
                                 prefix=f"pose_{name}", width=size[0],
                                 height=size[1], objects=_meshes(),
                                 samples=samples)
        paths.extend(p)
    _reset(rig)
    return preview.contact_sheet(paths, os.path.join(out_dir, "poses.png"))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blend", default=os.path.join(HERE, "build",
                                                    "kaito.blend"))
    ap.add_argument("--out", default=os.path.join(HERE, "build", "preview"))
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--only", nargs="*",
                    choices=("turnaround", "expressions", "shadow", "regions",
                             "poses"))
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=args.blend)
    os.makedirs(args.out, exist_ok=True)
    rig = _rig()
    _snapshot(rig)
    want = args.only or ("turnaround", "expressions", "shadow", "regions",
                         "poses")
    written = []
    if "turnaround" in want:
        written.append(render_turnaround(args.out, samples=args.samples))
    if "expressions" in want:
        written.append(render_expressions(args.out, rig, samples=args.samples))
    if "shadow" in want:
        written.append(render_shadow_looks(args.out, rig,
                                           samples=args.samples))
    if "regions" in want:
        written.append(render_regions(args.out, rig, samples=args.samples))
    if "poses" in want:
        written.append(render_poses(args.out, rig, samples=args.samples))
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
