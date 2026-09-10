"""Build the whole character into the current Blender file.

Order matters: meshes first, then materials, then the skeleton (which needs
the meshes to weight), then the face rig (which needs shape keys on the
face parts) and finally the shadow rig (which drives the materials).
"""

from __future__ import annotations

import bpy

from . import config as C
from . import blendutil as BU
from . import body as BODY
from . import clothing as CLOTH
from . import face as FACE
from . import hair as HAIR
from . import materials as MATS
from .surface import FrontSampler

# Solidify thickness per garment, in metres.
CLOTH_THICKNESS = {"shirt": 0.0045, "pants": 0.0045, "shoes": 0.0060,
                   "gloves": 0.0035}

# Face parts and the material each uses.
FACE_SUBSURF = {"eye": 1, "lid": 1, "brow": 1, "mouth": 1, "cavity": 0}


class Character:
    """Handles onto everything the rig modules need."""

    def __init__(self):
        self.collections = {}
        self.objects = {}
        self.materials = {}
        self.shapes = {}        # object name -> {shape key: verts}
        self.meshdata = {}
        self.sampler = None
        self.rig = None

    def mesh_objects(self):
        return [o for o in self.objects.values() if o.type == 'MESH']

    def deformable(self):
        """Everything that should follow the skeleton."""
        return [o for o in self.mesh_objects()
                if o.name != C.OBJ["contact_shadow"]]


def _collections():
    root = BU.ensure_collection(C.CHARACTER_NAME)
    return {
        "root": root,
        "mesh": BU.ensure_collection("Meshes", root),
        "rig": BU.ensure_collection("Rig", root),
        "widgets": BU.ensure_collection("Widgets", root),
        "lights": BU.ensure_collection("Lights", root),
        "set": BU.ensure_collection("Set", root),
    }


def build_meshes(texture_dir=None):
    """Create every mesh object with its material, ready to be rigged."""
    ch = Character()
    ch.collections = _collections()
    coll = ch.collections["mesh"]
    ch.materials = MATS.build_all(texture_dir)

    # -- body ----------------------------------------------------------
    body_md = BODY.build()
    ch.meshdata["body"] = body_md
    body_obj = BU.to_blender_object(body_md, C.OBJ["body"], coll,
                                    [ch.materials["skin"]])
    BU.recalc_normals(body_obj)
    BU.weld(body_obj)
    # soften the ring where the arms bridge into the shoulder sockets
    BU.relax_verts(body_obj,
                   lambda co: 1.20 < co.z < 1.40 and abs(co.x) > 0.12,
                   iterations=2, factor=0.35)
    BU.add_subsurf(body_obj)
    BU.shade_auto_smooth(body_obj)
    ch.objects["body"] = body_obj

    # -- face parts ----------------------------------------------------
    ch.sampler = FrontSampler(body_md)
    for key, (md, shapes, mat_key) in FACE.build_all(ch.sampler).items():
        obj = BU.to_blender_object(md, md.name, coll,
                                   [ch.materials[mat_key]])
        BU.recalc_normals(obj)
        levels = next((v for k, v in FACE_SUBSURF.items()
                       if key.startswith(k)), 1)
        if levels:
            BU.add_subsurf(obj, levels, max(levels, C.SUBSURF_RENDER))
        BU.shade_auto_smooth(obj, 60.0)
        ch.objects[key] = obj
        ch.meshdata[key] = md
        if shapes:
            ch.shapes[obj.name] = shapes

    # -- hair ----------------------------------------------------------
    hair_md = HAIR.build()
    ch.meshdata["hair"] = hair_md
    hair_obj = BU.to_blender_object(hair_md, C.OBJ["hair"], coll,
                                    [ch.materials["hair"]])
    BU.recalc_normals(hair_obj)
    BU.weld(hair_obj)
    BU.add_subsurf(hair_obj, 1, 2)
    BU.shade_auto_smooth(hair_obj, 50.0)
    ch.objects["hair"] = hair_obj

    # -- clothing ------------------------------------------------------
    for key, md in CLOTH.build_all().items():
        obj = BU.to_blender_object(md, C.OBJ[key], coll,
                                   [ch.materials[key]])
        BU.recalc_normals(obj)
        BU.weld(obj)
        BU.add_solidify(obj, CLOTH_THICKNESS[key], offset=1.0)
        BU.add_subsurf(obj, 1, 2)
        BU.shade_auto_smooth(obj, 55.0)
        ch.objects[key] = obj
        ch.meshdata[key] = md

    return ch


def apply_shape_keys(ch):
    """Turn the alternative vertex sets from `face` into real shape keys."""
    created = {}
    for obj_name, shapes in ch.shapes.items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        if obj.data.shape_keys is None:
            obj.shape_key_add(name="Basis", from_mix=False)
        names = []
        for shape_name, verts in shapes.items():
            key = obj.shape_key_add(name=shape_name, from_mix=False)
            for i, co in enumerate(verts):
                if i < len(key.data):
                    key.data[i].co = co
            key.slider_min = 0.0
            key.slider_max = 1.0
            names.append(shape_name)
        created[obj_name] = names
    return created


# ---------------------------------------------------------------------------
# rigging
# ---------------------------------------------------------------------------

# Parts that ride rigidly on one bone rather than being envelope-weighted.
RIGID_BINDING = {
    "hair": "head",
    "eye_l": "eye.L", "eye_r": "eye.R",
    "lid_up_l": "head", "lid_up_r": "head",
    "lid_lo_l": "head", "lid_lo_r": "head",
    "brow_l": "head", "brow_r": "head",
    "mouth": "jaw", "cavity": "jaw",
}

ENVELOPE_BINDING = ("body", "shirt", "pants", "shoes", "gloves")


def build_rig(ch):
    """Skeleton, widgets, skinning, face rig and shadow rig."""
    from . import armature as ARM
    from . import face_rig as FACERIG
    from . import shadow_rig as SHADOWRIG
    from . import skinning as SKIN

    rig = ARM.build_skeleton(ch.collections["rig"])
    ch.rig = rig
    widgets = ARM.build_widgets(ch.collections["widgets"])
    ch.collections["widgets"].hide_render = True

    # face and shadow bones must exist before constraints and skinning
    FACERIG.add_face_bones(rig)
    FACERIG.add_face_properties(rig)
    SHADOWRIG.add_shadow_bones(rig)
    SHADOWRIG.add_shadow_properties(rig)

    ik_report = ARM.add_constraints(rig)
    FACERIG.add_face_constraints(rig)
    ARM.apply_widgets(rig, widgets)
    FACERIG.apply_face_widgets(rig, widgets)
    SHADOWRIG.apply_shadow_widgets(rig, widgets)

    segments = SKIN.collect_bone_segments(rig)
    methods = {}
    for key in ENVELOPE_BINDING:
        obj = ch.objects.get(key)
        if obj is not None:
            methods[key] = SKIN.bind(obj, rig, segments)
    for key, bone in RIGID_BINDING.items():
        obj = ch.objects.get(key)
        if obj is not None:
            methods[key] = SKIN.bind(obj, rig, rigid=bone)

    drivers = FACERIG.add_shape_drivers(rig, ch.objects)
    shadow = SHADOWRIG.build(rig, ch.collections, ch.materials, widgets)
    ch.objects["contact_shadow"] = shadow["contact"]

    return {"ik": ik_report, "shape_drivers": len(drivers),
            "material_drivers": shadow["drivers"],
            "lights": sorted(shadow["lights"]),
            "binding": methods}


def build(texture_dir=None, with_rig=True):
    """Full character: meshes, materials, shape keys and the complete rig."""
    ch = build_meshes(texture_dir)
    apply_shape_keys(ch)
    report = build_rig(ch) if with_rig else {}
    ch.report = report
    return ch
