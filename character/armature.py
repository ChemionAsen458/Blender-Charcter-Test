"""The skeleton: deform bones, IK limbs and animator-facing controls.

Layout follows the usual game/film split.  Deform bones carry the mesh and
are named to match the vertex groups; control bones sit on top, live in
their own bone collections, and never deform anything.  Arms and legs get
two-bone IK with pole targets and an FK/IK blend on a property bone, so the
rig is usable for both posing and animation.

Face and shadow bones are added by :mod:`character.face_rig` and
:mod:`character.shadow_rig`, which are called after this module.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector, Matrix

from . import config as C
from . import blendutil as BU

Z = C.Z

# bone collections
COL_CONTROL = "Controls"
COL_IK = "IK"
COL_FK = "FK"
COL_FACE = "Face"
COL_SHADOW = "Shadow"
COL_DEFORM = "Deform"
COL_MECH = "Mechanism"

PROPS_BONE = "properties"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def mirror(p):
    return (-p[0], p[1], p[2])


def _bone(edit_bones, name, head, tail, parent=None, connect=False,
          roll=0.0, deform=False):
    b = edit_bones.new(name)
    b.head = Vector(head)
    b.tail = Vector(tail)
    b.roll = roll
    b.use_deform = deform
    if parent is not None:
        b.parent = edit_bones[parent] if isinstance(parent, str) else parent
        b.use_connect = connect
    return b


def _finger_chain(edit_bones, prefix, base, direction, total_length, side,
                  parent, splits=(0.44, 0.33, 0.23)):
    """Three phalanges marching along `direction` from `base`."""
    d = Vector(direction).normalized()
    p = Vector(base)
    names = []
    par = parent
    for i, frac in enumerate(splits):
        length = total_length * frac
        tail = p + d * length
        name = f"{prefix}.{i + 1:02d}.{side}"
        _bone(edit_bones, name, p, tail, par, connect=(i > 0), deform=True)
        names.append(name)
        par = name
        p = tail
        # each joint curls a little further forward
        d = (d + Vector((0.0, -0.10, -0.06))).normalized()
    return names


# ---------------------------------------------------------------------------
# skeleton definition
# ---------------------------------------------------------------------------

def _spine_bones(eb):
    _bone(eb, "root", (0, 0, 0), (0, -0.28, 0))
    _bone(eb, "torso", (0, 0.004, Z["hip"]), (0, 0.004, Z["hip"] + 0.13),
          "root")
    _bone(eb, PROPS_BONE, (0, 0.34, Z["hip"]), (0, 0.34, Z["hip"] + 0.08),
          "root")

    _bone(eb, "hips", (0, 0.004, Z["hip"]), (0, 0.004, Z["crotch"]),
          "torso", deform=True)
    _bone(eb, "spine", (0, 0.004, Z["hip"]), (0, -0.002, 1.028),
          "torso", deform=True)
    _bone(eb, "spine.001", (0, -0.002, 1.028), (0, -0.004, Z["chest"]),
          "spine", connect=True, deform=True)
    _bone(eb, "chest", (0, -0.004, Z["chest"]), (0, 0.004, 1.330),
          "spine.001", connect=True, deform=True)
    _bone(eb, "neck", (0, 0.004, 1.330), (0, 0.012, 1.462),
          "chest", connect=True, deform=True)
    _bone(eb, "head", (0, 0.012, 1.462), (0, 0.014, 1.700),
          "neck", connect=True, deform=True)

    # control bones the animator actually grabs
    _bone(eb, "hips_ctrl", (0, 0.004, Z["hip"]), (0, 0.004, Z["hip"] - 0.14),
          "torso")
    _bone(eb, "chest_ctrl", (0, -0.004, Z["chest"]), (0, -0.004, 1.36),
          "torso")
    _bone(eb, "head_ctrl", (0, 0.012, 1.462), (0, 0.012, 1.74), "chest_ctrl")
    _bone(eb, "neck_ctrl", (0, 0.004, 1.330), (0, 0.004, 1.44), "chest_ctrl")


def _arm_bones(eb, side):
    s = 1.0 if side == "L" else -1.0
    ap = C.ARM_PATH
    shoulder_root = (s * 0.028, 0.004, 1.336)
    shoulder_tip = (s * ap[0][0], ap[0][1], ap[0][2])
    elbow = (s * ap[C.ELBOW_INDEX][0], ap[C.ELBOW_INDEX][1],
             ap[C.ELBOW_INDEX][2])
    wrist = (s * C.WRIST[0], C.WRIST[1], C.WRIST[2])
    hand_tip = (s * (C.WRIST[0] + 0.003), C.WRIST[1] - 0.006, 0.788)

    _bone(eb, f"shoulder.{side}", shoulder_root, shoulder_tip, "chest",
          deform=True)
    _bone(eb, f"upper_arm.{side}", shoulder_tip, elbow, f"shoulder.{side}",
          deform=True)
    _bone(eb, f"forearm.{side}", elbow, wrist, f"upper_arm.{side}",
          connect=True, deform=True)
    _bone(eb, f"hand.{side}", wrist, hand_tip, f"forearm.{side}",
          connect=True, deform=True)

    # IK controls
    _bone(eb, f"hand_ik.{side}", wrist, hand_tip, "root")
    _bone(eb, f"elbow_pole.{side}", (s * 0.24, 0.42, 1.06),
          (s * 0.24, 0.42, 1.12), "root")

    hx = s * (C.WRIST[0] + 0.002)
    hy = C.WRIST[1] - 0.004
    for (name, base_u, spread, length, radius) in C.HAND["fingers"]:
        by = hy - base_u * C.HAND["palm_half_w"] * 0.74
        base = (hx + s * 0.001, by, 0.788)
        direction = (s * spread * 3.0, -spread * 6.0, -1.0)
        _finger_chain(eb, name, base, direction, length, side,
                      f"hand.{side}")
    th = C.HAND["thumb"]
    _finger_chain(eb, "thumb", (hx - s * 0.016, hy - 0.030, 0.834),
                  (-s * 0.55, -0.62, -0.90), th["length"], side,
                  f"hand.{side}", splits=(0.42, 0.34, 0.24))


def _leg_bones(eb, side):
    s = 1.0 if side == "L" else -1.0
    lp = C.LEG_PATH
    hip = (s * lp[0][0], lp[0][1], Z["hip"])
    knee = (s * lp[C.KNEE_INDEX][0], lp[C.KNEE_INDEX][1], Z["knee"])
    ankle = (s * lp[-1][0], lp[-1][1], Z["ankle"])
    ball = (s * C.FOOT["x"], -0.098, 0.026)
    toe = (s * C.FOOT["x"], C.FOOT["toe_y"], 0.022)

    _bone(eb, f"thigh.{side}", hip, knee, "hips", deform=True)
    _bone(eb, f"shin.{side}", knee, ankle, f"thigh.{side}", connect=True,
          deform=True)
    _bone(eb, f"foot.{side}", ankle, ball, f"shin.{side}", connect=True,
          deform=True)
    _bone(eb, f"toe.{side}", ball, toe, f"foot.{side}", connect=True,
          deform=True)

    _bone(eb, f"foot_ik.{side}", (s * C.FOOT["x"], 0.010, 0.0),
          (s * C.FOOT["x"], -0.12, 0.0), "root")
    _bone(eb, f"toe_ik.{side}", ball, toe, f"foot_ik.{side}")
    _bone(eb, f"knee_pole.{side}", (s * 0.12, -0.52, Z["knee"]),
          (s * 0.12, -0.52, Z["knee"] + 0.06), "root")


def build_skeleton(collection, name=None):
    """Create the armature object with every deform and control bone."""
    name = name or C.RIG_NAME
    arm = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, arm)
    BU.link(rig, collection)

    BU.set_active(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones
    _spine_bones(eb)
    for side in ("L", "R"):
        _arm_bones(eb, side)
        _leg_bones(eb, side)
    bpy.ops.object.mode_set(mode='OBJECT')

    _make_bone_collections(arm)
    return rig


# ---------------------------------------------------------------------------
# bone collections
# ---------------------------------------------------------------------------

CONTROL_BONES = ("root", "torso", "hips_ctrl", "chest_ctrl", "neck_ctrl",
                 "head_ctrl", PROPS_BONE)


def _make_bone_collections(arm):
    for name in (COL_CONTROL, COL_IK, COL_FK, COL_FACE, COL_SHADOW,
                 COL_MECH, COL_DEFORM):
        if name not in arm.collections_all:
            arm.collections.new(name)

    def assign(coll_name, predicate):
        coll = arm.collections_all[coll_name]
        for b in arm.bones:
            if predicate(b.name):
                coll.assign(b)

    assign(COL_CONTROL, lambda n: n in CONTROL_BONES)
    assign(COL_IK, lambda n: n.startswith(("hand_ik", "foot_ik", "toe_ik",
                                           "elbow_pole", "knee_pole")))
    assign(COL_FK, lambda n: n.startswith(("shoulder", "upper_arm", "forearm",
                                           "hand.", "thigh", "shin", "foot.",
                                           "toe.")))
    assign(COL_DEFORM, lambda n: True)
    for b in arm.bones:
        if not b.use_deform:
            arm.collections_all[COL_DEFORM].unassign(b)
    arm.collections_all[COL_DEFORM].is_visible = False
    arm.collections_all[COL_MECH].is_visible = False


# ---------------------------------------------------------------------------
# widgets
# ---------------------------------------------------------------------------

def _widget(name, points, edges, collection, scale=1.0):
    me = bpy.data.meshes.new(f"WGT-{name}")
    me.from_pydata([(p[0] * scale, p[1] * scale, p[2] * scale)
                    for p in points], edges, [])
    me.update()
    obj = bpy.data.objects.new(f"WGT-{name}", me)
    BU.link(obj, collection)
    obj.hide_render = True
    return obj


def _circle(n=16, r=1.0, axis="Z"):
    pts, edges = [], []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        c, s = math.cos(a) * r, math.sin(a) * r
        pts.append({"Z": (c, s, 0.0), "X": (0.0, c, s),
                    "Y": (c, 0.0, s)}[axis])
        edges.append((i, (i + 1) % n))
    return pts, edges


def _cube(r=1.0):
    pts = [(x * r, y * r, z * r) for x in (-1, 1) for y in (-1, 1)
           for z in (-1, 1)]
    edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7),
             (4, 5), (4, 6), (5, 7), (6, 7)]
    return pts, edges


def _arrow(length=1.0, width=0.35):
    pts = [(0, 0, 0), (0, -length, 0), (-width, -length + width, 0),
           (width, -length + width, 0)]
    edges = [(0, 1), (1, 2), (1, 3)]
    return pts, edges


def _diamond(r=1.0):
    pts = [(0, 0, r), (r, 0, 0), (0, r, 0), (-r, 0, 0), (0, -r, 0), (0, 0, -r)]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4), (5, 1), (5, 2), (5, 3), (5, 4),
             (1, 2), (2, 3), (3, 4), (4, 1)]
    return pts, edges


def build_widgets(collection):
    w = {}
    w["circle"] = _widget("Circle", *_circle(24), collection)
    w["circle_x"] = _widget("CircleX", *_circle(20, axis="X"), collection)
    w["cube"] = _widget("Cube", *_cube(), collection)
    w["arrow"] = _widget("Arrow", *_arrow(), collection)
    w["diamond"] = _widget("Diamond", *_diamond(), collection)
    w["square"] = _widget("Square",
                          [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
                          [(0, 1), (1, 2), (2, 3), (3, 0)], collection)
    return w


WIDGET_ASSIGNMENT = {
    "root": ("circle", 0.55),
    "torso": ("circle", 0.28),
    "hips_ctrl": ("circle", 0.22),
    "chest_ctrl": ("circle", 0.24),
    "neck_ctrl": ("circle_x", 0.09),
    "head_ctrl": ("circle_x", 0.14),
    PROPS_BONE: ("cube", 0.05),
    "hand_ik.L": ("cube", 0.055), "hand_ik.R": ("cube", 0.055),
    "foot_ik.L": ("square", 0.09), "foot_ik.R": ("square", 0.09),
    "toe_ik.L": ("circle_x", 0.05), "toe_ik.R": ("circle_x", 0.05),
    "elbow_pole.L": ("diamond", 0.045), "elbow_pole.R": ("diamond", 0.045),
    "knee_pole.L": ("diamond", 0.05), "knee_pole.R": ("diamond", 0.05),
}


def apply_widgets(rig, widgets):
    for bone_name, (shape, scale) in WIDGET_ASSIGNMENT.items():
        pb = rig.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.custom_shape = widgets[shape]
        pb.custom_shape_scale_xyz = (scale, scale, scale)
        pb.use_custom_shape_bone_size = False


# ---------------------------------------------------------------------------
# constraints
# ---------------------------------------------------------------------------

def _add_props(rig):
    pb = rig.pose.bones[PROPS_BONE]
    for key, value, lo, hi, desc in (
            ("ik_arm_l", 1.0, 0.0, 1.0, "Arm IK/FK blend, left"),
            ("ik_arm_r", 1.0, 0.0, 1.0, "Arm IK/FK blend, right"),
            ("ik_leg_l", 1.0, 0.0, 1.0, "Leg IK/FK blend, left"),
            ("ik_leg_r", 1.0, 0.0, 1.0, "Leg IK/FK blend, right"),
            ("hand_follow_l", 1.0, 0.0, 1.0, "Hand follows its IK control"),
            ("hand_follow_r", 1.0, 0.0, 1.0, "Hand follows its IK control")):
        pb[key] = value
        _ui_range(pb, key, lo, hi, desc)
    return pb


def _ui_range(pb, key, lo, hi, description=""):
    """Set slider limits on a custom property across Blender versions."""
    try:
        ui = pb.id_properties_ui(key)
        ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi,
                  description=description)
    except (AttributeError, TypeError):
        pb["_RNA_UI"] = pb.get("_RNA_UI", {})
        pb["_RNA_UI"][key] = {"min": lo, "max": hi, "soft_min": lo,
                              "soft_max": hi, "description": description}


def _drive_influence(rig, pose_bone, constraint, prop_name, invert=False):
    """Bind a constraint's influence to a property on the props bone."""
    path = f'pose.bones["{pose_bone.name}"].constraints["{constraint.name}"].influence'
    fcurve = rig.driver_add(path)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    var = drv.variables.new()
    var.name = "ik"
    var.type = 'SINGLE_PROP'
    var.targets[0].id = rig
    var.targets[0].data_path = f'pose.bones["{PROPS_BONE}"]["{prop_name}"]'
    drv.expression = f"1.0 - {var.name}" if invert else var.name
    return fcurve


def _solve_pole_angle(rig, ik_bone_name, constraint, target_bone,
                      bend_offset, prefer, candidates=None):
    """Pick the pole angle that bends the joint the anatomically right way.

    Solving this on the rest pose does not work: a straight limb is
    indifferent to the pole, so every angle scores the same and the solver
    picks one at random -- which is how you end up with knees that bend
    backwards.  So the limb is deliberately bent first, then scored on how
    far the middle joint travels along `prefer` (forward for a knee,
    backward for an elbow).  Ties are broken by rest-pose fidelity.
    """
    candidates = candidates or [math.radians(a) for a in range(-180, 180, 5)]
    deps = bpy.context.evaluated_depsgraph_get()
    joint = rig.pose.bones[ik_bone_name]
    target = rig.pose.bones[target_bone]
    prefer = Vector(prefer).normalized()

    saved = target.location.copy()
    target.location = Vector(bend_offset)
    deps.update()

    best, best_score = candidates[0], None
    for angle in candidates:
        constraint.pole_angle = angle
        deps.update()
        score = joint.head.dot(prefer)
        if best_score is None or score > best_score:
            best_score, best = score, angle
    constraint.pole_angle = best

    target.location = saved
    deps.update()
    rest_head = rig.data.bones[ik_bone_name].head_local
    rest_error = (joint.head - rest_head).length
    return best, rest_error


def add_constraints(rig):
    """IK chains, pole targets, FK/IK drivers and the foot roll."""
    BU.set_active(rig)
    bpy.ops.object.mode_set(mode='POSE')
    _add_props(rig)
    report = {}

    for side, tag in (("L", "l"), ("R", "r")):
        # -- arm ---------------------------------------------------------
        pb = rig.pose.bones[f"forearm.{side}"]
        ik = pb.constraints.new('IK')
        ik.name = "IK"
        ik.target = rig
        ik.subtarget = f"hand_ik.{side}"
        ik.pole_target = rig
        ik.pole_subtarget = f"elbow_pole.{side}"
        ik.chain_count = 2
        ik.use_tail = True
        # elbows point backwards (+Y)
        angle, err = _solve_pole_angle(
            rig, f"forearm.{side}", ik, f"hand_ik.{side}",
            (0.0, -0.10, 0.26), (0.0, 1.0, 0.0))
        report[f"arm.{side}"] = (math.degrees(angle), err)
        _drive_influence(rig, pb, ik, f"ik_arm_{tag}")

        hand = rig.pose.bones[f"hand.{side}"]
        cr = hand.constraints.new('COPY_ROTATION')
        cr.name = "IK Hand"
        cr.target = rig
        cr.subtarget = f"hand_ik.{side}"
        _drive_influence(rig, hand, cr, f"hand_follow_{tag}")

        # -- leg ---------------------------------------------------------
        pb = rig.pose.bones[f"shin.{side}"]
        ik = pb.constraints.new('IK')
        ik.name = "IK"
        ik.target = rig
        ik.subtarget = f"foot_ik.{side}"
        ik.pole_target = rig
        ik.pole_subtarget = f"knee_pole.{side}"
        ik.chain_count = 2
        ik.use_tail = True
        # knees point forwards (-Y)
        angle, err = _solve_pole_angle(
            rig, f"shin.{side}", ik, f"foot_ik.{side}",
            (0.0, -0.06, 0.20), (0.0, -1.0, 0.0))
        report[f"leg.{side}"] = (math.degrees(angle), err)
        _drive_influence(rig, pb, ik, f"ik_leg_{tag}")

        foot = rig.pose.bones[f"foot.{side}"]
        cr = foot.constraints.new('COPY_ROTATION')
        cr.name = "IK Foot"
        cr.target = rig
        cr.subtarget = f"foot_ik.{side}"
        _drive_influence(rig, foot, cr, f"ik_leg_{tag}")

        toe = rig.pose.bones[f"toe.{side}"]
        cr = toe.constraints.new('COPY_ROTATION')
        cr.name = "Toe Roll"
        cr.target = rig
        cr.subtarget = f"toe_ik.{side}"
        _drive_influence(rig, toe, cr, f"ik_leg_{tag}")

    # torso controls drive the deform spine
    for deform, ctrl in (("hips", "hips_ctrl"), ("chest", "chest_ctrl"),
                         ("neck", "neck_ctrl"), ("head", "head_ctrl")):
        pb = rig.pose.bones[deform]
        cr = pb.constraints.new('COPY_ROTATION')
        cr.name = f"Follow {ctrl}"
        cr.target = rig
        cr.subtarget = ctrl
        cr.mix_mode = 'BEFORE'
        cr.target_space = 'LOCAL'
        cr.owner_space = 'LOCAL'

    _lock_transforms(rig)
    bpy.ops.object.mode_set(mode='OBJECT')
    return report


def _lock_transforms(rig):
    """Poles and pure-rotation controls should not be translated by mistake."""
    for name, pb in rig.pose.bones.items():
        if name.startswith(("elbow_pole", "knee_pole")):
            pb.lock_rotation = (True, True, True)
            pb.lock_scale = (True, True, True)
        elif name in ("chest_ctrl", "neck_ctrl", "head_ctrl", "hips_ctrl"):
            pb.lock_scale = (True, True, True)
        elif name == PROPS_BONE:
            pb.lock_location = (True, True, True)
            pb.lock_rotation = (True, True, True)
            pb.lock_scale = (True, True, True)
        if pb.rotation_mode == 'QUATERNION':
            pb.rotation_mode = 'XYZ'


def deform_bones(rig):
    return [b.name for b in rig.data.bones if b.use_deform]
