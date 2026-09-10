"""The face rig: bones that shift the eyebrows, eyelids and mouth.

Two mechanisms, kept deliberately separate so nothing double-transforms:

* **Rigid parts** -- the eyeballs -- are weighted to their own bone and
  simply rotate.  ``eye_target`` aims both of them.
* **Deforming parts** -- brows, eyelids, lips -- are weighted to ``head``
  and their bones act as *sliders*: dragging a slider along one local axis
  drives a shape key.  Pull ``lid_up.L`` down and the eye closes; push
  ``brow.L`` up and the eyebrow lifts.

Slider bones are clamped by Limit Location constraints so the sliders
cannot be dragged past the poses that exist, and everything is grouped into
the ``Face`` bone collection.
"""

from __future__ import annotations

import math

import bpy

from . import config as C
from . import blendutil as BU
from .armature import COL_FACE, COL_MECH, _bone, _ui_range

FACE_PROPS_BONE = "face_props"

# How far a slider travels to reach the full shape, in metres.
BROW_RANGE = 0.014
LID_RANGE = 0.012
MOUTH_RANGE = 0.012
CORNER_RANGE = 0.010


# ---------------------------------------------------------------------------
# bones
# ---------------------------------------------------------------------------

def add_face_bones(rig):
    """Face bones, all children of `head`."""
    BU.set_active(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    eye, brow, mouth = C.EYE, C.BROW, C.MOUTH

    # jaw is a real deform bone: it opens the chin, the lips ride along
    _bone(eb, "jaw", (0.0, 0.048, 1.522), (0.0, -0.048, 1.484), "head",
          deform=True)

    _bone(eb, FACE_PROPS_BONE, (0.0, -0.30, 1.72), (0.0, -0.30, 1.78),
          "head")

    # eye aim: one master target with a child per eye
    _bone(eb, "eye_target", (0.0, -0.34, eye["z"]), (0.0, -0.40, eye["z"]),
          "head")
    for side in ("L", "R"):
        s = 1.0 if side == "L" else -1.0
        _bone(eb, f"eye_target.{side}", (s * eye["x"], -0.34, eye["z"]),
              (s * eye["x"], -0.40, eye["z"]), "eye_target")
        # the eyeball bone starts at the notional eyeball centre and points
        # forward, so rotating it swings the iris across the eye shell
        _bone(eb, f"eye.{side}", (s * eye["x"], -0.052, eye["z"]),
              (s * eye["x"], -0.092, eye["z"]), "head", deform=True)

        _bone(eb, f"brow.{side}", (s * brow["x"], -0.104, brow["z"]),
              (s * brow["x"], -0.104, brow["z"] + 0.022), "head")
        _bone(eb, f"lid_up.{side}", (s * eye["x"], -0.100, eye["z"] + 0.026),
              (s * eye["x"], -0.100, eye["z"] + 0.046), "head")
        _bone(eb, f"lid_lo.{side}", (s * eye["x"], -0.100, eye["z"] - 0.026),
              (s * eye["x"], -0.100, eye["z"] - 0.046), "head")
        _bone(eb, f"mouth_corner.{side}",
              (s * (mouth["width"] + 0.006), -0.098, mouth["z"]),
              (s * (mouth["width"] + 0.024), -0.098, mouth["z"]), "jaw")

    _bone(eb, "mouth", (0.0, -0.104, mouth["z"]),
          (0.0, -0.104, mouth["z"] - 0.020), "jaw")

    bpy.ops.object.mode_set(mode='OBJECT')

    arm = rig.data
    face_coll = arm.collections_all[COL_FACE]
    for b in arm.bones:
        if b.name in ("jaw", "mouth", "eye_target", FACE_PROPS_BONE) or \
                b.name.startswith(("eye.", "eye_target.", "brow.", "lid_up.",
                                   "lid_lo.", "mouth_corner.")):
            face_coll.assign(b)
    return rig


# ---------------------------------------------------------------------------
# constraints and limits
# ---------------------------------------------------------------------------

def add_face_constraints(rig):
    BU.set_active(rig)
    bpy.ops.object.mode_set(mode='POSE')

    for side in ("L", "R"):
        pb = rig.pose.bones[f"eye.{side}"]
        dt = pb.constraints.new('DAMPED_TRACK')
        dt.name = "Look At"
        dt.target = rig
        dt.subtarget = f"eye_target.{side}"
        dt.track_axis = 'TRACK_Y'

        _slider_limits(rig, f"brow.{side}", x=BROW_RANGE, z=BROW_RANGE)
        _slider_limits(rig, f"lid_up.{side}", z=LID_RANGE)
        _slider_limits(rig, f"lid_lo.{side}", z=LID_RANGE)
        _slider_limits(rig, f"mouth_corner.{side}", x=CORNER_RANGE,
                       z=CORNER_RANGE)
    _slider_limits(rig, "mouth", x=MOUTH_RANGE, z=MOUTH_RANGE)

    # a gentle limit so the jaw only swings open
    jaw = rig.pose.bones["jaw"]
    lim = jaw.constraints.new('LIMIT_ROTATION')
    lim.name = "Jaw Range"
    lim.use_limit_x = True
    lim.min_x = math.radians(-4.0)
    lim.max_x = math.radians(26.0)
    lim.owner_space = 'LOCAL'

    bpy.ops.object.mode_set(mode='OBJECT')
    return rig


def _slider_limits(rig, bone_name, x=0.0, y=0.0, z=0.0):
    """Clamp a slider bone to the range its shape keys actually cover."""
    pb = rig.pose.bones.get(bone_name)
    if pb is None:
        return None
    lim = pb.constraints.new('LIMIT_LOCATION')
    lim.name = "Slider Range"
    lim.owner_space = 'LOCAL'
    for axis, extent in (("x", x), ("y", y), ("z", z)):
        setattr(lim, f"use_min_{axis}", True)
        setattr(lim, f"use_max_{axis}", True)
        setattr(lim, f"min_{axis}", -extent)
        setattr(lim, f"max_{axis}", extent)
    lim.use_transform_limit = True
    pb.lock_rotation = (True, True, True)
    pb.lock_scale = (True, True, True)
    return lim


# ---------------------------------------------------------------------------
# custom properties
# ---------------------------------------------------------------------------

FACE_PROPERTIES = (
    ("brow_angry_l", 0.0, "Left brow drives inward and down"),
    ("brow_angry_r", 0.0, "Right brow drives inward and down"),
    ("brow_sad_l", 0.0, "Left brow inner end lifts"),
    ("brow_sad_r", 0.0, "Right brow inner end lifts"),
    ("brow_arch_l", 0.0, "Left brow arches"),
    ("brow_arch_r", 0.0, "Right brow arches"),
    ("squint_l", 0.0, "Left eye narrows"),
    ("squint_r", 0.0, "Right eye narrows"),
    ("mouth_smile", 0.0, "Mouth curves up"),
    ("mouth_frown", 0.0, "Mouth curves down"),
    ("mouth_pucker", 0.0, "Mouth purses"),
)


def add_face_properties(rig):
    pb = rig.pose.bones[FACE_PROPS_BONE]
    for key, value, desc in FACE_PROPERTIES:
        pb[key] = value
        _ui_range(pb, key, 0.0, 1.0, desc)
    pb.lock_location = (True, True, True)
    pb.lock_rotation = (True, True, True)
    pb.lock_scale = (True, True, True)
    return pb


# ---------------------------------------------------------------------------
# drivers
# ---------------------------------------------------------------------------

def _shape_key(obj, name):
    keys = obj.data.shape_keys
    if keys is None:
        return None
    return keys.key_blocks.get(name)


def _drive_shape(rig, obj, shape_name, expression, variables):
    """Bind one shape key to a driver expression over bone transforms/props."""
    key = _shape_key(obj, shape_name)
    if key is None:
        return None
    key.driver_remove("value")
    fcurve = key.driver_add("value")
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    for spec in variables:
        var = drv.variables.new()
        var.name = spec["name"]
        if spec.get("prop"):
            var.type = 'SINGLE_PROP'
            var.targets[0].id = rig
            var.targets[0].data_path = \
                f'pose.bones["{spec["bone"]}"]["{spec["prop"]}"]'
        else:
            var.type = 'TRANSFORMS'
            var.targets[0].id = rig
            var.targets[0].bone_target = spec["bone"]
            var.targets[0].transform_type = spec["transform"]
            var.targets[0].transform_space = 'LOCAL_SPACE'
    drv.expression = expression
    return fcurve


def add_shape_drivers(rig, objects):
    """Wire every face slider and property to its shape key.

    `objects` maps the assembler's part keys to their mesh objects.
    """
    wired = []

    for side in ("L", "R"):
        lo = side.lower()

        # -- eyelids: pull the slider down to blink, up to widen ---------
        for key, bone in ((f"lid_up_{lo}", f"lid_up.{side}"),
                          (f"lid_lo_{lo}", f"lid_lo.{side}")):
            obj = objects.get(key)
            if obj is None:
                continue
            sign = "-" if key.startswith("lid_up") else ""
            wired.append(_drive_shape(
                rig, obj, "blink",
                f"max(0.0, {sign}z / {LID_RANGE}) + squint * 0.0",
                [{"name": "z", "bone": bone, "transform": 'LOC_Z'},
                 {"name": "squint", "bone": FACE_PROPS_BONE,
                  "prop": f"squint_{lo}"}]))
            wired.append(_drive_shape(
                rig, obj, "wide",
                f"max(0.0, {'-' if sign == '' else ''}z / {LID_RANGE})",
                [{"name": "z", "bone": bone, "transform": 'LOC_Z'}]))
            wired.append(_drive_shape(
                rig, obj, "squint", "squint",
                [{"name": "squint", "bone": FACE_PROPS_BONE,
                  "prop": f"squint_{lo}"}]))

        # -- brows -------------------------------------------------------
        obj = objects.get(f"brow_{lo}")
        if obj is not None:
            bone = f"brow.{side}"
            wired.append(_drive_shape(
                rig, obj, "up", f"max(0.0, z / {BROW_RANGE})",
                [{"name": "z", "bone": bone, "transform": 'LOC_Z'}]))
            wired.append(_drive_shape(
                rig, obj, "down", f"max(0.0, -z / {BROW_RANGE})",
                [{"name": "z", "bone": bone, "transform": 'LOC_Z'}]))
            # dragging the slider toward the nose reads as a scowl
            inward = "-x" if side == "L" else "x"
            wired.append(_drive_shape(
                rig, obj, "angry",
                f"max(0.0, {inward} / {BROW_RANGE}) + angry",
                [{"name": "x", "bone": bone, "transform": 'LOC_X'},
                 {"name": "angry", "bone": FACE_PROPS_BONE,
                  "prop": f"brow_angry_{lo}"}]))
            outward = "x" if side == "L" else "-x"
            wired.append(_drive_shape(
                rig, obj, "sad",
                f"max(0.0, {outward} / {BROW_RANGE}) + sad",
                [{"name": "x", "bone": bone, "transform": 'LOC_X'},
                 {"name": "sad", "bone": FACE_PROPS_BONE,
                  "prop": f"brow_sad_{lo}"}]))
            wired.append(_drive_shape(
                rig, obj, "raise", "arch",
                [{"name": "arch", "bone": FACE_PROPS_BONE,
                  "prop": f"brow_arch_{lo}"}]))

    # -- mouth -----------------------------------------------------------
    obj = objects.get("mouth")
    if obj is not None:
        wired.append(_drive_shape(
            rig, obj, "open",
            f"max(0.0, -z / {MOUTH_RANGE}) + max(0.0, jaw / 0.42)",
            [{"name": "z", "bone": "mouth", "transform": 'LOC_Z'},
             {"name": "jaw", "bone": "jaw", "transform": 'ROT_X'}]))
        wired.append(_drive_shape(
            rig, obj, "wide", f"max(0.0, x / {MOUTH_RANGE})",
            [{"name": "x", "bone": "mouth", "transform": 'LOC_X'}]))
        wired.append(_drive_shape(
            rig, obj, "narrow", f"max(0.0, -x / {MOUTH_RANGE})",
            [{"name": "x", "bone": "mouth", "transform": 'LOC_X'}]))
        wired.append(_drive_shape(
            rig, obj, "smile",
            f"max(0.0, (l + r) * 0.5 / {CORNER_RANGE}) + smile",
            [{"name": "l", "bone": "mouth_corner.L", "transform": 'LOC_Z'},
             {"name": "r", "bone": "mouth_corner.R", "transform": 'LOC_Z'},
             {"name": "smile", "bone": FACE_PROPS_BONE,
              "prop": "mouth_smile"}]))
        wired.append(_drive_shape(
            rig, obj, "frown",
            f"max(0.0, -(l + r) * 0.5 / {CORNER_RANGE}) + frown",
            [{"name": "l", "bone": "mouth_corner.L", "transform": 'LOC_Z'},
             {"name": "r", "bone": "mouth_corner.R", "transform": 'LOC_Z'},
             {"name": "frown", "bone": FACE_PROPS_BONE,
              "prop": "mouth_frown"}]))
        wired.append(_drive_shape(
            rig, obj, "pucker", "pucker",
            [{"name": "pucker", "bone": FACE_PROPS_BONE,
              "prop": "mouth_pucker"}]))

    return [w for w in wired if w is not None]


# ---------------------------------------------------------------------------
# widgets
# ---------------------------------------------------------------------------

FACE_WIDGETS = {
    "eye_target": ("square", 0.055),
    "eye_target.L": ("circle_x", 0.018), "eye_target.R": ("circle_x", 0.018),
    "brow.L": ("cube", 0.010), "brow.R": ("cube", 0.010),
    "lid_up.L": ("cube", 0.009), "lid_up.R": ("cube", 0.009),
    "lid_lo.L": ("cube", 0.009), "lid_lo.R": ("cube", 0.009),
    "mouth": ("cube", 0.012),
    "mouth_corner.L": ("cube", 0.008), "mouth_corner.R": ("cube", 0.008),
    "jaw": ("circle_x", 0.05),
    FACE_PROPS_BONE: ("cube", 0.04),
}


def apply_face_widgets(rig, widgets):
    for bone_name, (shape, scale) in FACE_WIDGETS.items():
        pb = rig.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.custom_shape = widgets[shape]
        pb.custom_shape_scale_xyz = (scale, scale, scale)
        pb.use_custom_shape_bone_size = False


def build(rig, objects, widgets=None):
    add_face_bones(rig)
    add_face_properties(rig)
    add_face_constraints(rig)
    drivers = add_shape_drivers(rig, objects)
    if widgets:
        apply_face_widgets(rig, widgets)
    return drivers
