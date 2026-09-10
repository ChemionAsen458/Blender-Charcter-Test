"""Thin layer between :class:`character.meshlib.MeshData` and Blender."""

from __future__ import annotations

import bpy
import bmesh
from mathutils import Vector

from . import config as C


def purge_scene():
    """Start from a genuinely empty file."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (bpy.data.meshes, bpy.data.objects, bpy.data.materials,
                 bpy.data.armatures, bpy.data.images, bpy.data.actions,
                 bpy.data.node_groups, bpy.data.lights, bpy.data.cameras):
        for item in list(coll):
            coll.remove(item)


def ensure_collection(name, parent=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    target = parent or bpy.context.scene.collection
    if coll.name not in target.children:
        target.children.link(coll)
    return coll


def link(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def to_blender_object(meshdata, name, collection, materials=None,
                      smooth=True, uv_name="UVMap"):
    """Build a real mesh object from a :class:`MeshData`."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(meshdata.verts, [], list(meshdata.faces))
    me.validate(verbose=False)
    me.update()

    uv_layer = me.uv_layers.new(name=uv_name)
    # from_pydata keeps face order, so loops line up with meshdata.uvs
    for poly, uvs in zip(me.polygons, meshdata.uvs):
        if len(uvs) != poly.loop_total:
            continue
        for k, loop_index in enumerate(poly.loop_indices):
            uv_layer.data[loop_index].uv = uvs[k]

    if materials:
        for mat in materials:
            me.materials.append(mat)
        for poly, slot in zip(me.polygons, meshdata.mats):
            poly.material_index = min(slot, max(0, len(materials) - 1))

    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True

    obj = bpy.data.objects.new(name, me)
    link(obj, collection)

    for group, weights in meshdata.groups.items():
        vg = obj.vertex_groups.new(name=group)
        for idx, w in weights.items():
            if 0 <= idx < len(me.vertices):
                vg.add([idx], float(w), 'REPLACE')

    obj["marks"] = {k: list(v) for k, v in meshdata.marks.items()}
    return obj


def add_subsurf(obj, viewport=None, render=None, name="Subdivision"):
    mod = obj.modifiers.new(name, 'SUBSURF')
    mod.levels = C.SUBSURF_VIEWPORT if viewport is None else viewport
    mod.render_levels = C.SUBSURF_RENDER if render is None else render
    mod.use_limit_surface = True
    return mod


def add_mirror(obj, name="Mirror"):
    mod = obj.modifiers.new(name, 'MIRROR')
    mod.use_axis[0] = True
    mod.use_clip = True
    mod.use_mirror_merge = True
    return mod


def add_solidify(obj, thickness, offset=-1.0, name="Solidify"):
    mod = obj.modifiers.new(name, 'SOLIDIFY')
    mod.thickness = thickness
    mod.offset = offset
    mod.use_even_offset = True
    return mod


def add_armature_modifier(obj, rig, name="Armature"):
    mod = obj.modifiers.new(name, 'ARMATURE')
    mod.object = rig
    mod.use_vertex_groups = True
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    return mod


def shade_auto_smooth(obj, angle_degrees=42.0):
    """Blender 4.1+ dropped mesh.auto_smooth_angle for a modifier."""
    me = obj.data
    for poly in me.polygons:
        poly.use_smooth = True
    if hasattr(me, "shade_smooth_by_angle"):
        try:
            me.shade_smooth_by_angle(angle=angle_degrees * 3.14159265 / 180.0)
            return
        except Exception:
            pass
    if hasattr(me, "use_auto_smooth"):
        me.use_auto_smooth = True
        me.auto_smooth_angle = angle_degrees * 3.14159265 / 180.0


def recalc_normals(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    me.update()


def weld(obj, distance=0.0004):
    """Merge coincident verts so lofted seams become watertight."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=distance)
    bm.to_mesh(me)
    bm.free()
    me.update()


def set_active(obj):
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    return obj


def mesh_stats(obj):
    me = obj.data
    return {"verts": len(me.vertices), "faces": len(me.polygons),
            "tris": sum(max(0, len(p.vertices) - 2) for p in me.polygons)}


def bbox_world(obj):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for corner in obj.bound_box:
        v = obj.matrix_world @ Vector(corner)
        lo = Vector((min(lo[i], v[i]) for i in range(3)))
        hi = Vector((max(hi[i], v[i]) for i in range(3)))
    return lo, hi


def relax_verts(obj, predicate, iterations=2, factor=0.5):
    """Laplacian-smooth just the verts a predicate selects.

    Used to soften the ring of geometry where the arms bridge into the
    shoulder sockets, which otherwise reads as a hard crease under the
    subdivision surface.
    """
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    chosen = [v for v in bm.verts if predicate(v.co)]
    for _ in range(iterations):
        moves = []
        for v in chosen:
            linked = [e.other_vert(v) for e in v.link_edges]
            if not linked:
                continue
            ax = sum(o.co.x for o in linked) / len(linked)
            ay = sum(o.co.y for o in linked) / len(linked)
            az = sum(o.co.z for o in linked) / len(linked)
            moves.append((v, (ax, ay, az)))
        for v, target in moves:
            v.co.x += (target[0] - v.co.x) * factor
            v.co.y += (target[1] - v.co.y) * factor
            v.co.z += (target[2] - v.co.z) * factor
    bm.to_mesh(me)
    bm.free()
    me.update()
    return len(chosen)
