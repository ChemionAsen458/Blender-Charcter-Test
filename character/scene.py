"""Scene, camera and render configuration for the finished file."""

from __future__ import annotations

import math

import bpy

from . import config as C
from . import blendutil as BU


def setup_render(engine="BLENDER_EEVEE_NEXT", samples=64):
    """EEVEE, because the cel shading depends on Shader to RGB."""
    scene = bpy.context.scene
    try:
        scene.render.engine = engine
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1440
    scene.render.fps = 24
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    ee = getattr(scene, "eevee", None)
    if ee is not None:
        for attr, value in (("taa_render_samples", samples),
                            ("taa_samples", 16),
                            ("use_shadows", True),
                            ("use_raytracing", True),
                            ("use_gtao", True),
                            ("shadow_ray_count", 2),
                            ("shadow_step_count", 6)):
            if hasattr(ee, attr):
                try:
                    setattr(ee, attr, value)
                except Exception:
                    pass
    return scene


def setup_world(colour=(0.30, 0.32, 0.36), strength=0.42):
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (*colour, 1.0)
        bg.inputs[1].default_value = strength
    bpy.context.scene.world = world
    return world


def add_camera(collection, name="CAM-Turnaround"):
    data = bpy.data.cameras.new(name)
    data.lens = 85.0
    cam = bpy.data.objects.new(name, data)
    cam.location = (0.0, -4.2, 1.05)
    cam.rotation_euler = (math.radians(88.0), 0.0, 0.0)
    BU.link(cam, collection)
    bpy.context.scene.camera = cam
    return cam


def add_shadow_catcher(collection, size=6.0):
    """Ground plane that receives the character's cast shadow."""
    me = bpy.data.meshes.new(f"{C.SET_PREFIX}-ShadowCatcher")
    h = size * 0.5
    me.from_pydata([(-h, -h, 0.0), (h, -h, 0.0), (h, h, 0.0), (-h, h, 0.0)],
                   [], [(0, 1, 2, 3)])
    me.update()
    obj = bpy.data.objects.new(f"{C.SET_PREFIX}-ShadowCatcher", me)
    BU.link(obj, collection)

    mat = bpy.data.materials.new(f"{C.MAT_PREFIX}-ShadowCatcher")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    diff = nt.nodes.new('ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = (0.34, 0.35, 0.38, 1.0)
    diff.location = (-200, 0)
    nt.links.new(diff.outputs['BSDF'], out.inputs['Surface'])
    me.materials.append(mat)
    # `is_shadow_catcher` is a Cycles feature; under EEVEE the plane simply
    # receives the key light's cast shadow like any other surface
    if hasattr(obj, "is_shadow_catcher"):
        obj.is_shadow_catcher = True
    return obj
