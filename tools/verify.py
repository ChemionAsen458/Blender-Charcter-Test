#!/usr/bin/env python3
"""Checks that the rig actually works, not just that it built.

Run after ``build.py``:

    python3 -m tools.verify --blend build/kaito.blend

Each check poses the rig or nudges a control and asserts the model
responded: IK moves the foot, the blink slider closes the eye, the shadow
control retints every material, and so on.  Failures are reported with the
measured numbers so they can be diagnosed without opening Blender.
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


class Results:
    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        self.rows.append((name, bool(ok), detail))
        return ok

    @property
    def failed(self):
        return [r for r in self.rows if not r[1]]

    def report(self):
        width = max(len(r[0]) for r in self.rows) if self.rows else 10
        for name, ok, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name:<{width}}  {detail}")
        print(f"\n  {len(self.rows) - len(self.failed)}/{len(self.rows)} "
              f"checks passed")
        return not self.failed


def _deps():
    return bpy.context.evaluated_depsgraph_get()


def _refresh(*ids):
    """Tag datablocks and re-evaluate.

    Assigning a custom property does not tag the depsgraph on its own, so
    drivers reading that property would otherwise report stale values.
    """
    for datablock in ids:
        if datablock is not None:
            datablock.update_tag()
    deps = _deps()
    deps.update()
    return deps


def _eval(datablock):
    return datablock.evaluated_get(_deps())


def _evaluated_verts(obj):
    deps = _deps()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    verts = [obj.matrix_world @ v.co.copy() for v in me.vertices]
    ev.to_mesh_clear()
    return verts


def _centroid(obj):
    verts = _evaluated_verts(obj)
    if not verts:
        return Vector((0, 0, 0))
    total = Vector((0, 0, 0))
    for v in verts:
        total += v
    return total / len(verts)


def _reset(rig):
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    _deps().update()


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_structure(res, rig, objects):
    res.check("rig exists", rig is not None and rig.type == 'ARMATURE',
              f"{len(rig.data.bones) if rig else 0} bones")
    deform = [b.name for b in rig.data.bones if b.use_deform]
    res.check("deform bones", len(deform) >= 40, f"{len(deform)} deform bones")

    expected = ["root", "torso", "spine", "chest", "neck", "head", "jaw",
                "hips", "properties", "face_props", "SHD-ctrl", "SHD-key",
                "SHD-face", "SHD-contact"]
    for side in ("L", "R"):
        expected += [f"thigh.{side}", f"shin.{side}", f"foot.{side}",
                     f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}",
                     f"hand_ik.{side}", f"foot_ik.{side}",
                     f"knee_pole.{side}", f"elbow_pole.{side}",
                     f"eye.{side}", f"brow.{side}", f"lid_up.{side}",
                     f"lid_lo.{side}", f"mouth_corner.{side}",
                     f"thumb.01.{side}", f"index.03.{side}"]
    missing = [b for b in expected if b not in rig.data.bones]
    res.check("expected bones present", not missing,
              "missing: " + ", ".join(missing) if missing else "all present")

    for name in ("CHR-Body", "CHR-Hair", "CHR-Shirt", "CHR-Pants",
                 "CHR-Shoes", "CHR-Gloves", "CHR-Eye-L", "CHR-Eye-R",
                 "CHR-Mouth", "CHR-Brow-L", "CHR-Brow-R"):
        res.check(f"object {name}", name in objects, "")

    separate = all(objects[n].data != objects["CHR-Body"].data
                   for n in ("CHR-Shirt", "CHR-Pants", "CHR-Shoes",
                             "CHR-Gloves") if n in objects)
    res.check("clothing is separate geometry", separate,
              "shirt/pants/shoes/gloves each own their mesh")


def check_weights(res, objects):
    from character import skinning as SKIN
    for name in ("CHR-Body", "CHR-Shirt", "CHR-Pants", "CHR-Shoes",
                 "CHR-Gloves"):
        obj = objects.get(name)
        if obj is None:
            continue
        loose = SKIN.unweighted_vertices(obj)
        res.check(f"weights {name}", not loose,
                  f"{len(loose)} unweighted verts" if loose
                  else f"{len(obj.vertex_groups)} groups, all verts weighted")
        has_mod = any(m.type == 'ARMATURE' for m in obj.modifiers)
        res.check(f"armature modifier {name}", has_mod, "")


def check_rest_pose(res, rig, objects):
    """The rig must not deform anything while it is at rest.

    This is the check that would have caught the leg IK aiming at a
    floor-level control instead of the ankle: every control was at zero,
    yet the mesh was 27 cm out of shape.  Constraints are evaluated even in
    the rest pose, so "all bones at zero" is not the same as "the model is
    where it was modelled".
    """
    _reset(rig)
    deps = _refresh(rig)

    off = []
    for pb in _eval(rig).pose.bones:
        rest = rig.data.bones[pb.name]
        drift = max((pb.head - rest.head_local).length,
                    (pb.tail - rest.tail_local).length)
        if drift > 0.004:
            off.append((drift, pb.name))
    off.sort(reverse=True)
    detail = ", ".join(f"{n} {d * 1000:.0f}mm" for d, n in off[:4]) or         "every bone within 4 mm of rest"
    res.check("rest pose: bones undisturbed", not off, detail)

    for name in ("CHR-Body", "CHR-Shirt", "CHR-Pants", "CHR-Shoes",
                 "CHR-Gloves", "CHR-Hair"):
        obj = objects.get(name)
        if obj is None:
            continue
        arm = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
        if arm is None:
            continue
        posed = _evaluated_verts(obj)
        arm.show_viewport = False
        _refresh(obj)
        plain = _evaluated_verts(obj)
        arm.show_viewport = True
        _refresh(obj)
        if len(posed) != len(plain):
            res.check(f"rest pose: {name}", False, "vertex counts differ")
            continue
        worst = max((a - b).length for a, b in zip(posed, plain))
        res.check(f"rest pose: {name} undeformed", worst < 0.004,
                  f"max drift {worst * 1000:.1f} mm")

    for name in ("CHR-Body", "CHR-Shirt", "CHR-Pants", "CHR-Shoes",
                 "CHR-Gloves"):
        obj = objects.get(name)
        if obj is None:
            continue
        arms = [m for m in obj.modifiers if m.type == 'ARMATURE']
        res.check(f"single armature modifier {name}", len(arms) == 1,
                  f"{len(arms)} armature modifiers")


def check_ik(res, rig, objects):
    body = objects["CHR-Body"]
    _reset(rig)
    for side in ("L", "R"):
        foot = rig.pose.bones[f"foot.{side}"]
        before = (rig.matrix_world @ foot.matrix).translation.copy()
        ctrl = rig.pose.bones[f"foot_ik.{side}"]
        ctrl.location = (0.0, -0.10, 0.16)
        _deps().update()
        after = (rig.matrix_world @ foot.matrix).translation.copy()
        moved = (after - before).length
        res.check(f"leg IK {side}", moved > 0.05,
                  f"foot moved {moved * 100:.1f} cm")
        knee = rig.pose.bones[f"shin.{side}"]
        knee_pos = (rig.matrix_world @ knee.matrix).translation
        res.check(f"knee tracks forward {side}", knee_pos.y < 0.06,
                  f"knee y = {knee_pos.y:+.3f} (should bend forward)")
        _reset(rig)

        hand = rig.pose.bones[f"hand.{side}"]
        before = (rig.matrix_world @ hand.matrix).translation.copy()
        rig.pose.bones[f"hand_ik.{side}"].location = (0.0, -0.18, 0.22)
        _deps().update()
        after = (rig.matrix_world @ hand.matrix).translation.copy()
        moved = (after - before).length
        res.check(f"arm IK {side}", moved > 0.05,
                  f"hand moved {moved * 100:.1f} cm")
        _reset(rig)

    # the body mesh must actually follow the skeleton
    before = _centroid(body)
    rig.pose.bones["torso"].location = (0.0, 0.0, -0.12)
    _deps().update()
    after = _centroid(body)
    res.check("body follows the rig", (after - before).length > 0.02,
              f"centroid moved {(after - before).length * 100:.1f} cm")
    _reset(rig)


def check_fk_ik_blend(res, rig):
    props = rig.pose.bones["properties"]
    for key in ("ik_arm_l", "ik_arm_r", "ik_leg_l", "ik_leg_r"):
        res.check(f"property {key}", key in props.keys(),
                  f"= {props.get(key)}")
    props["ik_leg_l"] = 0.0
    _refresh(rig)
    off = _eval(rig).pose.bones["shin.L"].constraints["IK"].influence
    props["ik_leg_l"] = 1.0
    _refresh(rig)
    on = _eval(rig).pose.bones["shin.L"].constraints["IK"].influence
    res.check("FK/IK blend drives influence", off < 0.01 and on > 0.99,
              f"influence {off:.2f} -> {on:.2f}")


def check_face_rig(res, rig, objects):
    _reset(rig)
    checks = [
        ("blink L", "lid_up.L", (0, 0, -0.012), "CHR-LidUp-L", "blink"),
        ("blink R", "lid_up.R", (0, 0, -0.012), "CHR-LidUp-R", "blink"),
        ("brow up L", "brow.L", (0, 0, 0.014), "CHR-Brow-L", "up"),
        ("brow down R", "brow.R", (0, 0, -0.014), "CHR-Brow-R", "down"),
        ("mouth open", "mouth", (0, 0, -0.012), "CHR-Mouth", "open"),
    ]
    for label, bone, loc, obj_name, key_name in checks:
        obj = objects.get(obj_name)
        if obj is None or obj.data.shape_keys is None:
            res.check(f"face: {label}", False, "missing shape keys")
            continue
        key = obj.data.shape_keys.key_blocks.get(key_name)
        rig.pose.bones[bone].location = loc
        _deps().update()
        value = key.value if key else -1
        res.check(f"face: {label}", value > 0.85,
                  f"shape key '{key_name}' = {value:.2f}")
        _reset(rig)

    # the eyelid must actually move geometry, not just set a number
    lid = objects.get("CHR-LidUp-L")
    before = _centroid(lid)
    rig.pose.bones["lid_up.L"].location = (0, 0, -0.012)
    _deps().update()
    after = _centroid(lid)
    res.check("face: eyelid geometry moves", (after - before).length > 0.002,
              f"lid centroid moved {(after - before).length * 1000:.1f} mm")
    _reset(rig)

    # brow scowl via the shape-key property
    fp = rig.pose.bones["face_props"]
    fp["brow_angry_l"] = 1.0
    _refresh(rig, objects["CHR-Brow-L"].data.shape_keys)
    keys = _eval(objects["CHR-Brow-L"]).data.shape_keys
    key = keys.key_blocks.get("angry") if keys else None
    res.check("face: angry brow property", key and key.value > 0.95,
              f"angry = {key.value:.2f}" if key else "missing")
    fp["brow_angry_l"] = 0.0
    _refresh(rig)

    # eye look
    eye = objects.get("CHR-Eye-L")
    before = _centroid(eye)
    rig.pose.bones["eye_target"].location = (0.12, 0.0, 0.06)
    _deps().update()
    after = _centroid(eye)
    res.check("face: eyes track the target", (after - before).length > 0.001,
              f"eye moved {(after - before).length * 1000:.1f} mm")
    _reset(rig)

    jaw_before = _centroid(objects["CHR-Mouth"])
    rig.pose.bones["jaw"].rotation_euler = (math.radians(20), 0, 0)
    _deps().update()
    jaw_after = _centroid(objects["CHR-Mouth"])
    res.check("face: jaw opens the mouth",
              (jaw_after - jaw_before).length > 0.002,
              f"mouth moved {(jaw_after - jaw_before).length * 1000:.1f} mm")
    _reset(rig)


def check_shadow_rig(res, rig, objects):
    from character import materials as MATS, shadow_rig as SHADOW
    ctrl = rig.pose.bones.get(SHADOW.CTRL)
    res.check("shadow control bone", ctrl is not None, SHADOW.CTRL)
    if ctrl is None:
        return
    names = [p for p, *_ in SHADOW.SHADOW_PROPERTIES]
    missing = [p for p in names if p not in ctrl.keys()]
    res.check("shadow properties", not missing,
              f"{len(names)} properties" if not missing
              else "missing: " + ", ".join(missing))

    toon = MATS.toon_materials()
    res.check("toon materials", len(toon) >= 8, f"{len(toon)} materials")

    # threshold must propagate to every toon material
    ctrl["shadow_threshold"] = 0.80
    _refresh(rig, *toon, *[m.node_tree for m in toon])
    reads = []
    for mat in toon:
        node = MATS.toon_node(_eval(mat))
        idx = next(i for i, s in enumerate(node.inputs)
                   if s.name == MATS.IN_THRESHOLD)
        reads.append(node.inputs[idx].default_value)
    res.check("shadow threshold drives all materials",
              all(abs(v - 0.80) < 1e-3 for v in reads),
              f"min {min(reads):.3f} max {max(reads):.3f}")
    ctrl["shadow_threshold"] = 0.50
    _refresh(rig, *toon, *[m.node_tree for m in toon])

    # tint
    ctrl["shadow_tint_r"] = 0.20
    _refresh(rig, *toon, *[m.node_tree for m in toon])
    node = MATS.toon_node(_eval(toon[0]))
    idx = next(i for i, s in enumerate(node.inputs)
               if s.name == MATS.IN_TINT)
    res.check("shadow tint drives materials",
              abs(node.inputs[idx].default_value[0] - 0.20) < 1e-3,
              f"tint.r = {node.inputs[idx].default_value[0]:.3f}")
    ctrl["shadow_tint_r"] = 0.62
    _refresh(rig, *toon, *[m.node_tree for m in toon])

    # the face-shadow slider must move the band on the skin material
    skin = bpy.data.materials.get("MAT-Skin")
    band = skin.node_tree.nodes.get("FaceShadowBand") if skin else None
    res.check("face shadow band node", band is not None, "MAT-Skin")
    if band is not None:
        _reset(rig)
        _refresh(rig, skin, skin.node_tree)
        low = _eval(skin).node_tree.nodes["FaceShadowBand"] \
            .inputs["From Min"].default_value
        rig.pose.bones[SHADOW.FACE].location = (0, 0, 0.05)
        _refresh(rig, skin, skin.node_tree)
        high = _eval(skin).node_tree.nodes["FaceShadowBand"] \
            .inputs["From Min"].default_value
        res.check("face shadow slider moves the band", high - low > 0.03,
                  f"band {low:.3f} -> {high:.3f}")
        _reset(rig)

    # lights ride their bones
    key_light = bpy.data.objects.get("LGT-Key")
    res.check("key light exists", key_light is not None, "LGT-Key")
    if key_light is not None:
        rides = any(c.type == 'CHILD_OF' and c.subtarget == SHADOW.KEY
                    for c in key_light.constraints)
        res.check("key light rides SHD-key", rides, "")
        deps = _deps()
        before = key_light.evaluated_get(deps).matrix_world.to_quaternion()
        rig.pose.bones[SHADOW.KEY].rotation_euler = (0.0, 0.0, math.radians(60))
        deps.update()
        after = key_light.evaluated_get(deps).matrix_world.to_quaternion()
        angle = before.rotation_difference(after).angle
        res.check("SHD-key rotates the light", angle > 0.2,
                  f"light turned {math.degrees(angle):.0f} deg")
        _reset(rig)
        ctrl["key_energy"] = 7.5
        _refresh(rig, key_light.data)
        energy = _eval(key_light.data).energy
        res.check("key energy driver", abs(energy - 7.5) < 1e-3,
                  f"energy = {energy:.2f}")
        ctrl["key_energy"] = 3.0
        _refresh(rig, key_light.data)

    blob = objects.get("CHR-ContactShadow")
    res.check("contact shadow object", blob is not None, "")
    if blob is not None:
        before = _centroid(blob)
        rig.pose.bones[SHADOW.CONTACT].location = (0.22, 0.0, 0.0)
        _deps().update()
        after = _centroid(blob)
        res.check("contact shadow follows its bone",
                  (after - before).length > 0.05,
                  f"moved {(after - before).length * 100:.1f} cm")
        _reset(rig)


def check_textures(res):
    from character import config as C
    for name in C.TEXTURE_SETS:
        img = bpy.data.images.get(f"{name}.png")
        # size is (0, 0) until the buffer is actually paged in, which does
        # not happen on its own in a background session -- ask for it
        if img is not None and img.size[0] == 0:
            try:
                img.reload()
            except RuntimeError:
                pass
        path = bpy.path.abspath(img.filepath) if img else ""
        ok = img is not None and (img.size[0] > 0 or os.path.exists(path))
        detail = f"{img.size[0]}x{img.size[1]}" if ok and img.size[0] else \
            (os.path.basename(path) if ok else "not loaded")
        res.check(f"texture {name}", ok, detail)
    mats = {"MAT-Skin": "skin.png", "MAT-Hair": "hair.png",
            "MAT-Eyes": "eyes.png", "MAT-Shirt": "shirt.png",
            "MAT-Pants": "pants.png", "MAT-Shoes": "shoes.png",
            "MAT-Gloves": "gloves.png"}
    for mat_name, tex_name in mats.items():
        mat = bpy.data.materials.get(mat_name)
        node = mat.node_tree.nodes.get("BaseTexture") if mat else None
        ok = node is not None and node.image is not None \
            and node.image.name == tex_name
        res.check(f"{mat_name} uses {tex_name}", ok,
                  node.image.name if node and node.image else "missing")


# ---------------------------------------------------------------------------

def run(blend_path=None):
    if blend_path:
        bpy.ops.wm.open_mainfile(filepath=blend_path)
    objects = {o.name: o for o in bpy.data.objects}
    from character import config as C
    rig = bpy.data.objects.get(C.RIG_NAME)
    res = Results()
    check_structure(res, rig, objects)
    check_textures(res)
    check_weights(res, objects)
    check_rest_pose(res, rig, objects)
    check_ik(res, rig, objects)
    check_fk_ik_blend(res, rig)
    check_face_rig(res, rig, objects)
    check_shadow_rig(res, rig, objects)
    return res


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blend", default=os.path.join(HERE, "build",
                                                    "kaito.blend"))
    args = ap.parse_args(argv)
    print(f"verifying {args.blend}\n")
    res = run(args.blend)
    ok = res.report()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
