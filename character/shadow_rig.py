"""The shadow rig.

Cel shading makes shadow a *posed* element, not a by-product of lighting:
where the terminator falls, how hard it is, what colour it goes, where the
fringe's shadow sits on the forehead and how big the contact patch is are
all shot-by-shot decisions.  So they are all bones and properties on the
same armature as the body:

``SHD-key`` / ``SHD-fill`` / ``SHD-rim``
    Direction handles.  A Sun lamp rides on each one, aimed down the bone,
    so pointing the bone points the light -- and therefore moves the cel
    terminator across the whole character.
``SHD-ctrl``
    Custom properties driving *every* toon material at once: terminator
    position, edge softness, shadow depth, shadow tint, rim light and
    specular.
``SHD-face``
    A slider that raises and lowers the hair's shadow across the face.
``SHD-contact``
    Carries the ground contact patch; move, scale and fade it under the
    character.

Because the whole system hangs off ``root``, the lighting travels with the
character, which is what an animator wants for a cel-shaded shot.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import config as C
from . import blendutil as BU
from . import materials as MATS
from .armature import COL_SHADOW, _bone, _ui_range

CTRL = "SHD-ctrl"
KEY = "SHD-key"
FILL = "SHD-fill"
RIM = "SHD-rim"
FACE = "SHD-face"
CONTACT = "SHD-contact"
ROOT = "SHD-root"

# One control per shading region, mirroring the reference rig's three
# per-region shader groups (`BASE_SunBody_Group`, `BASE_SunFace_Group`,
# `BASE_SunHair`) and the `Sunvec` bone collection that steers them.
#
# These do not replace `SHD-ctrl`; they *offset* it.  The master still
# moves the whole character in one gesture, and each region can then be
# pushed away from it -- lift the face's terminator so it reads clean
# while the body keeps its contrast, soften only the hair.
REGION_CTRL = {"body": "SUN-body", "face": "SUN-face", "hair": "SUN-hair"}
COL_SUNVEC = "Sunvec"

# (property, default, min, max, description) -- the offsets each region
# control carries.  Defaults are 0: out of the box every region matches
# the master exactly, so the look is unchanged until something is dialled.
REGION_PROPERTIES = (
    ("threshold_offset", 0.0, -1.0, 1.0,
     "Shift this region's terminator away from the master"),
    ("softness_offset", 0.0, -1.0, 1.0,
     "Soften or harden this region's terminator"),
    ("strength_offset", 0.0, -1.0, 1.0,
     "Deepen or lift this region's shadow"),
    ("rim_offset", 0.0, -4.0, 4.0, "Rim light, relative to the master"),
    ("spec_offset", 0.0, -4.0, 4.0, "Specular, relative to the master"),
)

# region offset property -> the master property it adjusts
REGION_OFFSET_OF = {
    "shadow_threshold": "threshold_offset",
    "shadow_softness": "softness_offset",
    "shadow_strength": "strength_offset",
    "rim_strength": "rim_offset",
    "spec_strength": "spec_offset",
}

FACE_SHADOW_RANGE = 0.060      # metres of slider travel = full sweep

# (property, default, min, max, description)
SHADOW_PROPERTIES = (
    ("shadow_threshold", C.SHADOW["threshold"], 0.0, 1.0,
     "Where the cel terminator sits on the light ramp"),
    ("shadow_softness", C.SHADOW["softness"], 0.0, 0.5,
     "Width of the terminator; 0 is a razor edge"),
    ("shadow_strength", C.SHADOW["strength"], 0.0, 1.0,
     "How far the dark side goes toward the shadow colour"),
    ("shadow_tint_r", C.SHADOW["tint"][0], 0.0, 2.0, "Shadow tint, red"),
    ("shadow_tint_g", C.SHADOW["tint"][1], 0.0, 2.0, "Shadow tint, green"),
    ("shadow_tint_b", C.SHADOW["tint"][2], 0.0, 2.0, "Shadow tint, blue"),
    ("rim_strength", C.SHADOW["rim_strength"], 0.0, 4.0, "Rim light level"),
    ("rim_width", C.SHADOW["rim_width"], 0.0, 1.0, "Rim light width"),
    ("spec_strength", C.SHADOW["spec_strength"], 0.0, 4.0,
     "Specular highlight level"),
    ("face_shadow_softness", C.SHADOW["face_shadow_softness"], 0.005, 0.4,
     "Softness of the shadow the fringe casts on the face"),
    ("contact_opacity", C.SHADOW["contact_opacity"], 0.0, 1.0,
     "Opacity of the ground contact patch"),
    ("key_energy", C.SHADOW["key_light_energy"], 0.0, 20.0,
     "Key light level"),
    ("fill_energy", C.SHADOW["fill_light_energy"], 0.0, 20.0,
     "Fill light level"),
    ("cast_softness", 2.0, 0.0, 45.0,
     "Angular size of the key light: soft or hard cast shadows"),
)

PROP_TO_SOCKET = {
    "shadow_threshold": MATS.IN_THRESHOLD,
    "shadow_softness": MATS.IN_SOFTNESS,
    "shadow_strength": MATS.IN_STRENGTH,
    "rim_strength": MATS.IN_RIM,
    "rim_width": MATS.IN_RIM_WIDTH,
    "spec_strength": MATS.IN_SPEC,
}


# ---------------------------------------------------------------------------
# bones
# ---------------------------------------------------------------------------

def _aim(head, target, length=0.34):
    """A bone starting at `head` and pointing at `target`."""
    d = (Vector(target) - Vector(head)).normalized()
    return tuple(head), tuple(Vector(head) + d * length)


def _ensure_bone(eb, name, head, tail, parent=None):
    """Create a bone, or hand back the one that is already there.

    ``add_shadow_bones`` runs twice -- once early, because constraints and
    skinning need the bones to exist, and again from :func:`build`.  Plain
    ``edit_bones.new()`` would silently make ``SHD-root.001`` and friends
    on the second pass, so every lookup by name has to be guarded.
    """
    existing = eb.get(name)
    if existing is not None:
        return existing
    return _bone(eb, name, head, tail, parent)


def add_shadow_bones(rig):
    BU.set_active(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones

    _ensure_bone(eb, ROOT, (0.0, 0.0, 0.0), (0.0, 0.0, 0.22), "root")
    _ensure_bone(eb, CTRL, (0.42, 0.36, 0.02), (0.42, 0.36, 0.16), ROOT)

    h, t = _aim((0.78, -0.92, 2.06), (0.0, 0.0, 1.28))
    _ensure_bone(eb, KEY, h, t, ROOT)
    h, t = _aim((-0.96, -0.52, 1.52), (0.0, 0.0, 1.16))
    _ensure_bone(eb, FILL, h, t, ROOT)
    h, t = _aim((-0.34, 1.04, 2.02), (0.0, 0.0, 1.32))
    _ensure_bone(eb, RIM, h, t, ROOT)

    # face-shadow slider, parked beside the head
    _ensure_bone(eb, FACE, (0.20, -0.10, C.Z["brow"]),
                 (0.20, -0.10, C.Z["brow"] + 0.05), "head")
    _ensure_bone(eb, CONTACT, (0.0, 0.0, 0.004), (0.0, -0.24, 0.004), ROOT)

    # region controls, parked in a row beside the master
    for i, name in enumerate(REGION_CTRL.values()):
        x = 0.56 + i * 0.10
        _ensure_bone(eb, name, (x, 0.36, 0.02), (x, 0.36, 0.12), ROOT)

    bpy.ops.object.mode_set(mode='OBJECT')

    if COL_SUNVEC not in rig.data.collections_all:
        rig.data.collections.new(COL_SUNVEC)

    coll = rig.data.collections_all[COL_SHADOW]
    for name in (ROOT, CTRL, KEY, FILL, RIM, FACE, CONTACT):
        bone = rig.data.bones.get(name)
        if bone is not None:
            coll.assign(bone)
    sunvec = rig.data.collections_all[COL_SUNVEC]
    for name in REGION_CTRL.values():
        bone = rig.data.bones.get(name)
        if bone is not None:
            sunvec.assign(bone)
    return rig


def add_shadow_properties(rig):
    pb = rig.pose.bones[CTRL]
    for key, value, lo, hi, desc in SHADOW_PROPERTIES:
        pb[key] = value
        _ui_range(pb, key, lo, hi, desc)
    pb.lock_location = (True, True, True)
    pb.lock_rotation = (True, True, True)
    pb.lock_scale = (True, True, True)

    face = rig.pose.bones[FACE]
    lim = face.constraints.new('LIMIT_LOCATION')
    lim.name = "Face Shadow Range"
    lim.owner_space = 'LOCAL'
    for axis in ("x", "y", "z"):
        setattr(lim, f"use_min_{axis}", True)
        setattr(lim, f"use_max_{axis}", True)
        extent = FACE_SHADOW_RANGE if axis == "z" else 0.0
        setattr(lim, f"min_{axis}", -extent)
        setattr(lim, f"max_{axis}", extent)
    lim.use_transform_limit = True
    face.lock_rotation = (True, True, True)
    face.lock_scale = (True, True, True)

    for bone_name in REGION_CTRL.values():
        rb = rig.pose.bones[bone_name]
        for key, value, lo, hi, desc in REGION_PROPERTIES:
            rb[key] = value
            _ui_range(rb, key, lo, hi, desc)
        rb.lock_location = (True, True, True)
        rb.lock_rotation = (True, True, True)
        rb.lock_scale = (True, True, True)
    return pb


# ---------------------------------------------------------------------------
# lights
# ---------------------------------------------------------------------------

def add_lights(rig, collection):
    """Three suns, each flown by its bone."""
    lights = {}
    specs = (("LGT-Key", KEY, C.SHADOW["key_light_energy"], 2.0,
              (1.0, 0.97, 0.92)),
             ("LGT-Fill", FILL, C.SHADOW["fill_light_energy"], 22.0,
              (0.80, 0.86, 1.0)),
             ("LGT-Rim", RIM, 2.4, 6.0, (1.0, 0.95, 0.88)))
    for (name, bone, energy, angle, colour) in specs:
        data = bpy.data.lights.new(name, 'SUN')
        data.energy = energy
        data.angle = math.radians(angle)
        data.color = colour
        obj = bpy.data.objects.new(name, data)
        BU.link(obj, collection)
        # A sun shines down its local -Z.  Rotating the object +90 degrees
        # about X maps that onto the bone's head->tail axis, so the bone
        # reads as an arrow pointing the way the light travels.
        obj.rotation_euler = (math.pi * 0.5, 0.0, 0.0)
        con = obj.constraints.new('CHILD_OF')
        con.name = "Ride Bone"
        con.target = rig
        con.subtarget = bone
        con.set_inverse_pending = False
        lights[name] = obj

    _drive_value(lights["LGT-Key"].data, "energy", rig, "key_energy")
    _drive_value(lights["LGT-Fill"].data, "energy", rig, "fill_energy")
    _drive_value(lights["LGT-Key"].data, "angle", rig, "cast_softness",
                 expression="radians(v)")
    return lights


# ---------------------------------------------------------------------------
# drivers
# ---------------------------------------------------------------------------

def _prop_var(drv, name, rig, bone, prop):
    var = drv.variables.new()
    var.name = name
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = rig
    var.targets[0].data_path = f'pose.bones["{bone}"]["{prop}"]'
    return var


def _add_driver(id_data, data_path, rig, prop, index=-1,
                expression="v", region_bone=None, region_prop=None):
    """Bind any RNA property to a custom property on the shadow control.

    With ``region_bone``/``region_prop`` the driver reads a second value --
    that region's offset -- and adds it, so the master keeps global
    control while the region can be pushed away from it.
    """
    id_data.driver_remove(data_path, index)
    fcurve = id_data.driver_add(data_path, index)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    _prop_var(drv, "v", rig, CTRL, prop)
    if region_bone is not None and region_prop is not None:
        _prop_var(drv, "o", rig, region_bone, region_prop)
        expression = f"({expression}) + o"
    drv.expression = expression
    return fcurve


def _drive_value(id_data, data_path, rig, prop, expression="v"):
    return _add_driver(id_data, data_path, rig, prop, -1, expression)


def _socket_index(node, socket_name):
    for i, sock in enumerate(node.inputs):
        if sock.name == socket_name:
            return i
    return None


def _region_of(mat):
    """Which shading region a material belongs to, or None."""
    for region, keys in C.REGIONS.items():
        if mat.name in (C.MAT[k] for k in keys):
            return region
    return None


def drive_materials(rig, mats=None):
    """Point every toon material at the shadow control bone.

    Materials named in ``config.REGIONS`` additionally pick up their
    region's offset, so body, face and hair can be graded apart.
    """
    mats = mats or MATS.toon_materials()
    wired = 0
    for mat in mats:
        node = MATS.toon_node(mat)
        if node is None:
            continue
        region_bone = REGION_CTRL.get(_region_of(mat))
        for prop, socket_name in PROP_TO_SOCKET.items():
            idx = _socket_index(node, socket_name)
            if idx is None:
                continue
            path = f'nodes["{MATS.TOON_NODE}"].inputs[{idx}].default_value'
            _add_driver(mat.node_tree, path, rig, prop,
                        region_bone=region_bone,
                        region_prop=REGION_OFFSET_OF.get(prop))
            wired += 1
        # shadow tint is a colour, so each channel gets its own driver
        idx = _socket_index(node, MATS.IN_TINT)
        if idx is not None:
            path = f'nodes["{MATS.TOON_NODE}"].inputs[{idx}].default_value'
            for chan, prop in enumerate(("shadow_tint_r", "shadow_tint_g",
                                         "shadow_tint_b")):
                _add_driver(mat.node_tree, path, rig, prop, chan)
                wired += 1
    return wired


def drive_face_shadow(rig, skin_material):
    """Slide the fringe's shadow up and down the face from ``SHD-face``.

    The band's lower edge follows the slider bone; its upper edge is the
    same value plus the softness property, so one slider moves the shadow
    and one number decides how hard its edge is.
    """
    nt = skin_material.node_tree
    band = nt.nodes.get("FaceShadowBand")
    if band is None:
        return 0
    base = C.Z["brow"] - 0.02
    idx_min = _socket_index(band, "From Min")
    idx_max = _socket_index(band, "From Max")

    for idx, expression in ((idx_min, f"{base} + z"),
                            (idx_max, f"{base} + z + soft")):
        path = f'nodes["FaceShadowBand"].inputs[{idx}].default_value'
        nt.driver_remove(path, -1)
        fcurve = nt.driver_add(path, -1)
        drv = fcurve.driver
        drv.type = 'SCRIPTED'
        var = drv.variables.new()
        var.name = "z"
        var.type = 'TRANSFORMS'
        var.targets[0].id = rig
        var.targets[0].bone_target = FACE
        var.targets[0].transform_type = 'LOC_Z'
        var.targets[0].transform_space = 'LOCAL_SPACE'
        if "soft" in expression:
            var2 = drv.variables.new()
            var2.name = "soft"
            var2.type = 'SINGLE_PROP'
            var2.targets[0].id_type = 'OBJECT'
            var2.targets[0].id = rig
            var2.targets[0].data_path = \
                f'pose.bones["{CTRL}"]["face_shadow_softness"]'
        drv.expression = expression

    # the band's tint follows the global shadow tint
    mixer = nt.nodes.get("FaceShadowMix")
    if mixer is not None:
        idx = _socket_index(mixer, "Color2")
        path = f'nodes["FaceShadowMix"].inputs[{idx}].default_value'
        for chan, prop in enumerate(("shadow_tint_r", "shadow_tint_g",
                                     "shadow_tint_b")):
            _add_driver(nt, path, rig, prop, chan)
    return 2


# ---------------------------------------------------------------------------
# contact shadow
# ---------------------------------------------------------------------------

def add_contact_shadow(rig, collection, material, segments=32):
    """A soft blob under the character, carried by ``SHD-contact``."""
    r = C.SHADOW["contact_radius"]
    verts = [(0.0, 0.0, 0.0)]
    faces = []
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        verts.append((math.cos(a) * r, math.sin(a) * r * 1.35, 0.0))
    for i in range(segments):
        faces.append((0, 1 + i, 1 + (i + 1) % segments))
    me = bpy.data.meshes.new(C.OBJ["contact_shadow"])
    me.from_pydata(verts, [], faces)
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(C.OBJ["contact_shadow"], me)
    me.materials.append(material)
    BU.link(obj, collection)
    obj.location = (0.0, -0.02, 0.003)

    con = obj.constraints.new('CHILD_OF')
    con.name = "Ride Bone"
    con.target = rig
    con.subtarget = CONTACT
    con.set_inverse_pending = False

    opacity = material.node_tree.nodes.get("ContactOpacity")
    if opacity is not None:
        idx = 1
        path = f'nodes["ContactOpacity"].inputs[{idx}].default_value'
        _add_driver(material.node_tree, path, rig, "contact_opacity")
    obj.visible_shadow = False
    return obj


# ---------------------------------------------------------------------------
# widgets
# ---------------------------------------------------------------------------

SHADOW_WIDGETS = {
    ROOT: ("circle", 0.30),
    CTRL: ("cube", 0.06),
    KEY: ("arrow", 0.30),
    FILL: ("arrow", 0.24),
    RIM: ("arrow", 0.24),
    FACE: ("cube", 0.018),
    CONTACT: ("circle", 0.24),
}


def apply_shadow_widgets(rig, widgets):
    for bone_name, (shape, scale) in SHADOW_WIDGETS.items():
        pb = rig.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.custom_shape = widgets[shape]
        pb.custom_shape_scale_xyz = (scale, scale, scale)
        pb.use_custom_shape_bone_size = False


def build(rig, collections, mats, widgets=None):
    """Bones, lights, drivers and the contact patch."""
    add_shadow_bones(rig)
    add_shadow_properties(rig)
    lights = add_lights(rig, collections["lights"])
    wired = drive_materials(rig)
    drive_face_shadow(rig, mats["skin"])
    contact = add_contact_shadow(rig, collections["mesh"],
                                 mats["contact_shadow"])
    if widgets:
        apply_shadow_widgets(rig, widgets)
    return {"lights": lights, "drivers": wired, "contact": contact}
