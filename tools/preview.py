"""Render orthographic turnaround sheets of whatever is in the scene.

Used both as a build artefact (``build/preview_*.png``) and as the
inner loop while tuning proportions: render, look, adjust the numbers in
``character/config.py``, repeat.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector


# Camera *offsets* from the subject, not view directions.  The character
# faces -Y, so the front camera sits at -Y looking back toward +Y.
VIEWS = {
    "front":   (0.0,  -1.0,  0.0),
    "back":    (0.0,   1.0,  0.0),
    "side":    (1.0,   0.0,  0.0),      # the character's left
    "side_r":  (-1.0,  0.0,  0.0),
    "three_q": (-0.68, -0.73, 0.0),
    "top":     (0.0,  -0.15, 1.0),
}


def _look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def setup_render(width=720, height=1200, samples=32, transparent=False,
                 engine="BLENDER_EEVEE_NEXT"):
    scene = bpy.context.scene
    try:
        scene.render.engine = engine
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent
    scene.render.image_settings.file_format = 'PNG'
    ee = getattr(scene, "eevee", None)
    if ee is not None:
        for attr, value in (("taa_render_samples", samples),
                            ("use_gtao", True),
                            ("use_shadows", True),
                            ("use_raytracing", True)):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, value)
                except Exception:
                    pass
    scene.view_settings.view_transform = 'Standard'
    return scene


def ensure_clay_light():
    """Neutral three-point rig used for untextured proportion checks."""
    rigs = []
    for name, rot, energy, size in (
            ("PRV-Key",  (1.05, 0.0, 0.62), 3.2, 8.0),
            ("PRV-Fill", (1.25, 0.0, -2.1), 1.0, 12.0),
            ("PRV-Rim",  (1.45, 0.0, 3.05), 2.2, 6.0)):
        data = bpy.data.lights.new(name, 'SUN')
        data.energy = energy
        data.angle = math.radians(size)
        obj = bpy.data.objects.new(name, data)
        obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)
        rigs.append(obj)
    world = bpy.data.worlds.get("PreviewWorld") or bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.26, 0.27, 0.29, 1.0)
        bg.inputs[1].default_value = 0.85
    bpy.context.scene.world = world
    return rigs


def scene_bounds(objects=None):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    found = False
    for obj in (objects if objects is not None else bpy.context.scene.objects):
        if obj.type != 'MESH' or obj.hide_render:
            continue
        found = True
        for corner in obj.bound_box:
            v = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], v[i]) for i in range(3)))
            hi = Vector((max(hi[i], v[i]) for i in range(3)))
    if not found:
        return Vector((-1, -1, 0)), Vector((1, 1, 2))
    return lo, hi


def render_views(out_dir, views=("front", "side", "three_q"), prefix="preview",
                 width=720, height=1200, margin=1.10, objects=None,
                 focus=None, ortho_scale=None, samples=32):
    """Render orthographic views and return the written file paths."""
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    lo, hi = scene_bounds(objects)
    centre = focus if focus is not None else (lo + hi) * 0.5
    span = max((hi - lo).z, (hi - lo).x, (hi - lo).y)
    if ortho_scale is None:
        ortho_scale = span * margin

    cam_data = bpy.data.cameras.new(prefix + "-Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = ortho_scale
    cam = bpy.data.objects.new(prefix + "-Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    setup_render(width=width, height=height, samples=samples,
                 transparent=scene.render.film_transparent)
    written = []
    for view in views:
        d = Vector(VIEWS[view]).normalized()
        cam.location = centre + d * (span * 3.0 + 2.0)
        _look_at(cam, centre)
        path = os.path.join(out_dir, f"{prefix}_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        written.append(path)
    bpy.data.objects.remove(cam, do_unlink=True)
    return written


def contact_sheet(paths, out_path, pad=8, bg=(38, 40, 44)):
    """Stitch renders side by side so one Read call shows every view."""
    from tools.png import read_png, write_png
    imgs = [read_png(p) for p in paths]
    h = max(im["height"] for im in imgs)
    w = sum(im["width"] for im in imgs) + pad * (len(imgs) + 1)
    out = [bytearray(bytes(bg) * w) for _ in range(h + 2 * pad)]
    x_off = pad
    for im in imgs:
        for y in range(im["height"]):
            row = im["rows"][y]
            dst = out[y + pad]
            for x in range(im["width"]):
                si = x * im["channels"]
                di = (x_off + x) * 3
                dst[di] = row[si]
                dst[di + 1] = row[si + 1]
                dst[di + 2] = row[si + 2]
        x_off += im["width"] + pad
    write_png(out_path, w, h + 2 * pad, out, channels=3)
    return out_path
