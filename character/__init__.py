"""Procedural anime character generator for Blender.

Modules:
    config       proportions, palette, naming, UV atlas
    meshlib      dependency-free mesh maths (rings, lofts, forks, UVs)
    blendutil    MeshData -> Blender object plumbing
    body         the base skin mesh
    face         eyes, brows, mouth
    hair         layered spiky hair
    clothing     shirt / pants / shoes / gloves as separate objects
    materials    cel-shaded material system
    armature     full body skeleton with IK
    face_rig     eyebrow / eyelid / mouth controls
    shadow_rig   light-direction, cel-shadow and contact-shadow controls
    scene        camera, lighting and render configuration
"""

__all__ = [
    "config", "meshlib", "blendutil", "body", "face", "hair", "clothing",
    "materials", "armature", "face_rig", "shadow_rig", "scene", "assemble",
]
