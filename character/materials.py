"""Cel-shaded (NPR) materials driven by one shared node group.

Every surface routes through ``TOON-Core``: a Diffuse BSDF is converted to
RGB with *Shader to RGB* -- which samples the real scene lighting, so the
key light's direction and its cast shadows still drive the look -- then
posterised into a hard terminator, tinted, and emitted.

Keeping the posterising in a single group is what makes the shadow rig
possible: one set of drivers on the group's inputs retints and re-thresholds
the whole character at once.  See :mod:`character.shadow_rig`.

Shader to RGB is an EEVEE node; the file is saved with EEVEE as the render
engine.  Under Cycles the materials fall back to their flat base colour.
"""

from __future__ import annotations

import os

import bpy

from . import config as C

TOON_GROUP = "TOON-Core"
TOON_NODE = "TOON"          # the group instance's name inside each material

# group input names, also used as the driver targets by the shadow rig
IN_COLOR = "Base Color"
IN_TINT = "Shadow Tint"
IN_THRESHOLD = "Shadow Threshold"
IN_SOFTNESS = "Shadow Softness"
IN_STRENGTH = "Shadow Strength"
IN_RIM = "Rim Strength"
IN_RIM_WIDTH = "Rim Width"
IN_SPEC = "Specular Strength"
IN_SPEC_SIZE = "Specular Size"
IN_EMIT = "Unlit Mix"

SHADOW_INPUTS = (IN_TINT, IN_THRESHOLD, IN_SOFTNESS, IN_STRENGTH,
                 IN_RIM, IN_RIM_WIDTH, IN_SPEC, IN_SPEC_SIZE)


# ---------------------------------------------------------------------------
# node-group construction
# ---------------------------------------------------------------------------

def _new_socket(group, name, kind, default=None, mn=None, mx=None):
    sock = group.interface.new_socket(name=name, in_out='INPUT',
                                      socket_type=kind)
    if default is not None:
        sock.default_value = default
    if mn is not None:
        sock.min_value = mn
    if mx is not None:
        sock.max_value = mx
    return sock


def build_toon_group():
    """Create (or fetch) the shared cel-shading node group."""
    existing = bpy.data.node_groups.get(TOON_GROUP)
    if existing is not None:
        return existing

    g = bpy.data.node_groups.new(TOON_GROUP, 'ShaderNodeTree')
    S = C.SHADOW
    _new_socket(g, IN_COLOR, 'NodeSocketColor', (0.8, 0.8, 0.8, 1.0))
    _new_socket(g, IN_TINT, 'NodeSocketColor', (*S["tint"], 1.0))
    _new_socket(g, IN_THRESHOLD, 'NodeSocketFloat', S["threshold"], 0.0, 1.0)
    _new_socket(g, IN_SOFTNESS, 'NodeSocketFloat', S["softness"], 0.0, 1.0)
    _new_socket(g, IN_STRENGTH, 'NodeSocketFloat', S["strength"], 0.0, 1.0)
    _new_socket(g, IN_RIM, 'NodeSocketFloat', S["rim_strength"], 0.0, 4.0)
    _new_socket(g, IN_RIM_WIDTH, 'NodeSocketFloat', S["rim_width"], 0.0, 1.0)
    _new_socket(g, IN_SPEC, 'NodeSocketFloat', S["spec_strength"], 0.0, 4.0)
    _new_socket(g, IN_SPEC_SIZE, 'NodeSocketFloat', 0.14, 0.0, 1.0)
    _new_socket(g, IN_EMIT, 'NodeSocketFloat', 0.0, 0.0, 1.0)
    g.interface.new_socket(name="Shader", in_out='OUTPUT',
                           socket_type='NodeSocketShader')

    nodes, links = g.nodes, g.links
    gin = nodes.new('NodeGroupInput')
    gin.location = (-1100, 0)
    gout = nodes.new('NodeGroupOutput')
    gout.location = (900, 0)

    # -- light term: real lighting, then posterised ---------------------
    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.location = (-900, 260)
    diffuse.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    to_rgb = nodes.new('ShaderNodeShaderToRGB')
    to_rgb.location = (-720, 260)
    links.new(diffuse.outputs['BSDF'], to_rgb.inputs['Shader'])

    lum = nodes.new('ShaderNodeRGBToBW')
    lum.location = (-560, 260)
    links.new(to_rgb.outputs['Color'], lum.inputs['Color'])

    # terminator = smoothstep(threshold - softness, threshold + softness)
    lo = nodes.new('ShaderNodeMath')
    lo.operation = 'SUBTRACT'
    lo.location = (-560, 80)
    hi = nodes.new('ShaderNodeMath')
    hi.operation = 'ADD'
    hi.location = (-560, -80)
    links.new(gin.outputs[IN_THRESHOLD], lo.inputs[0])
    links.new(gin.outputs[IN_SOFTNESS], lo.inputs[1])
    links.new(gin.outputs[IN_THRESHOLD], hi.inputs[0])
    links.new(gin.outputs[IN_SOFTNESS], hi.inputs[1])

    ramp = nodes.new('ShaderNodeMapRange')
    ramp.location = (-360, 160)
    ramp.clamp = True
    ramp.interpolation_type = 'SMOOTHSTEP'
    links.new(lum.outputs['Val'], ramp.inputs['Value'])
    links.new(lo.outputs['Value'], ramp.inputs['From Min'])
    links.new(hi.outputs['Value'], ramp.inputs['From Max'])

    # -- shadow colour ---------------------------------------------------
    shadow_col = nodes.new('ShaderNodeMixRGB')
    shadow_col.blend_type = 'MULTIPLY'
    shadow_col.location = (-360, -140)
    shadow_col.inputs['Fac'].default_value = 1.0
    links.new(gin.outputs[IN_COLOR], shadow_col.inputs['Color1'])
    links.new(gin.outputs[IN_TINT], shadow_col.inputs['Color2'])

    # how far toward the shadow colour the dark side goes
    lit_mask = nodes.new('ShaderNodeMath')
    lit_mask.operation = 'MULTIPLY_ADD'
    lit_mask.location = (-180, 160)
    lit_mask.inputs[1].default_value = 1.0
    links.new(ramp.outputs['Result'], lit_mask.inputs[0])

    inv = nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.location = (-180, 20)
    inv.inputs[0].default_value = 1.0
    links.new(ramp.outputs['Result'], inv.inputs[1])
    strength_mask = nodes.new('ShaderNodeMath')
    strength_mask.operation = 'MULTIPLY'
    strength_mask.location = (-20, 20)
    links.new(inv.outputs['Value'], strength_mask.inputs[0])
    links.new(gin.outputs[IN_STRENGTH], strength_mask.inputs[1])

    base_mix = nodes.new('ShaderNodeMixRGB')
    base_mix.location = (160, 60)
    base_mix.blend_type = 'MIX'
    links.new(strength_mask.outputs['Value'], base_mix.inputs['Fac'])
    links.new(gin.outputs[IN_COLOR], base_mix.inputs['Color1'])
    links.new(shadow_col.outputs['Color'], base_mix.inputs['Color2'])

    # -- rim light -------------------------------------------------------
    fresnel = nodes.new('ShaderNodeLayerWeight')
    fresnel.location = (-360, -360)
    rim_range = nodes.new('ShaderNodeMapRange')
    rim_range.location = (-180, -360)
    rim_range.clamp = True
    rim_range.interpolation_type = 'SMOOTHSTEP'
    rim_range.inputs['From Max'].default_value = 1.0
    links.new(fresnel.outputs['Facing'], rim_range.inputs['Value'])
    rim_from_min = nodes.new('ShaderNodeMath')
    rim_from_min.operation = 'SUBTRACT'
    rim_from_min.location = (-360, -520)
    rim_from_min.inputs[0].default_value = 1.0
    links.new(gin.outputs[IN_RIM_WIDTH], rim_from_min.inputs[1])
    links.new(rim_from_min.outputs['Value'], rim_range.inputs['From Min'])

    rim_amt = nodes.new('ShaderNodeMath')
    rim_amt.operation = 'MULTIPLY'
    rim_amt.location = (-20, -360)
    links.new(rim_range.outputs['Result'], rim_amt.inputs[0])
    links.new(gin.outputs[IN_RIM], rim_amt.inputs[1])
    # rim only where the surface is already lit
    rim_lit = nodes.new('ShaderNodeMath')
    rim_lit.operation = 'MULTIPLY'
    rim_lit.location = (160, -360)
    links.new(rim_amt.outputs['Value'], rim_lit.inputs[0])
    links.new(ramp.outputs['Result'], rim_lit.inputs[1])

    # -- specular blob ---------------------------------------------------
    gloss = nodes.new('ShaderNodeBsdfGlossy')
    gloss.location = (-900, -640)
    gloss.inputs['Roughness'].default_value = 0.30
    gloss_rgb = nodes.new('ShaderNodeShaderToRGB')
    gloss_rgb.location = (-720, -640)
    links.new(gloss.outputs['BSDF'], gloss_rgb.inputs['Shader'])
    gloss_bw = nodes.new('ShaderNodeRGBToBW')
    gloss_bw.location = (-560, -640)
    links.new(gloss_rgb.outputs['Color'], gloss_bw.inputs['Color'])
    # a bright key pushes the glossy term well above 1.0, which would make
    # the "highlight" cover half the model; scale it back into 0-1 first
    gloss_scale = nodes.new('ShaderNodeMath')
    gloss_scale.name = "SpecScale"
    gloss_scale.operation = 'MULTIPLY'
    gloss_scale.location = (-460, -700)
    gloss_scale.inputs[1].default_value = 0.16
    links.new(gloss_bw.outputs['Val'], gloss_scale.inputs[0])

    spec_range = nodes.new('ShaderNodeMapRange')
    spec_range.location = (-300, -640)
    spec_range.clamp = True
    spec_range.interpolation_type = 'SMOOTHSTEP'
    links.new(gloss_scale.outputs['Value'], spec_range.inputs['Value'])
    spec_from_min = nodes.new('ShaderNodeMath')
    spec_from_min.operation = 'SUBTRACT'
    spec_from_min.location = (-560, -820)
    spec_from_min.inputs[0].default_value = 1.0
    links.new(gin.outputs[IN_SPEC_SIZE], spec_from_min.inputs[1])
    links.new(spec_from_min.outputs['Value'], spec_range.inputs['From Min'])
    spec_from_max = nodes.new('ShaderNodeMath')
    spec_from_max.operation = 'ADD'
    spec_from_max.location = (-560, -960)
    spec_from_max.inputs[1].default_value = 0.10
    links.new(spec_from_min.outputs['Value'], spec_from_max.inputs[0])
    links.new(spec_from_max.outputs['Value'], spec_range.inputs['From Max'])
    spec_amt = nodes.new('ShaderNodeMath')
    spec_amt.operation = 'MULTIPLY'
    spec_amt.location = (-180, -640)
    links.new(spec_range.outputs['Result'], spec_amt.inputs[0])
    links.new(gin.outputs[IN_SPEC], spec_amt.inputs[1])

    # -- combine ---------------------------------------------------------
    add_rim = nodes.new('ShaderNodeMixRGB')
    add_rim.blend_type = 'ADD'
    add_rim.location = (360, 0)
    add_rim.inputs['Fac'].default_value = 1.0
    links.new(base_mix.outputs['Color'], add_rim.inputs['Color1'])
    rim_col = nodes.new('ShaderNodeCombineColor')
    rim_col.location = (300, -300)
    for k in range(3):
        links.new(rim_lit.outputs['Value'], rim_col.inputs[k])
    links.new(rim_col.outputs['Color'], add_rim.inputs['Color2'])

    add_spec = nodes.new('ShaderNodeMixRGB')
    add_spec.blend_type = 'ADD'
    add_spec.location = (520, 0)
    add_spec.inputs['Fac'].default_value = 1.0
    links.new(add_rim.outputs['Color'], add_spec.inputs['Color1'])
    spec_col = nodes.new('ShaderNodeCombineColor')
    spec_col.location = (360, -560)
    for k in range(3):
        links.new(spec_amt.outputs['Value'], spec_col.inputs[k])
    links.new(spec_col.outputs['Color'], add_spec.inputs['Color2'])

    # unlit mix: pull the surface back toward flat colour (used by eyes)
    unlit = nodes.new('ShaderNodeMixRGB')
    unlit.blend_type = 'MIX'
    unlit.location = (680, 60)
    links.new(gin.outputs[IN_EMIT], unlit.inputs['Fac'])
    links.new(add_spec.outputs['Color'], unlit.inputs['Color1'])
    links.new(gin.outputs[IN_COLOR], unlit.inputs['Color2'])

    emit = nodes.new('ShaderNodeEmission')
    emit.location = (800, 60)
    links.new(unlit.outputs['Color'], emit.inputs['Color'])
    links.new(emit.outputs['Emission'], gout.inputs['Shader'])
    return g


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------

def load_texture(name, texture_dir):
    """Load ``<texture_dir>/<name>.png``, generating it if it is missing."""
    path = os.path.join(texture_dir, f"{name}.png")
    if not os.path.exists(path):
        from tools.generate_textures import generate
        generate(texture_dir, names=[name], guides=False, quiet=True)
    img = bpy.data.images.get(f"{name}.png")
    if img is None:
        img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = 'sRGB'
    return img


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------

def _base_material(name, texture_name, texture_dir, unlit=0.0,
                   spec=None, backface_cull=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (500, 0)
    grp = nt.nodes.new('ShaderNodeGroup')
    grp.node_tree = build_toon_group()
    grp.name = TOON_NODE
    grp.label = TOON_NODE
    grp.location = (200, 0)
    nt.links.new(grp.outputs['Shader'], out.inputs['Surface'])

    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.name = "BaseTexture"
    tex.location = (-260, 0)
    tex.image = load_texture(texture_name, texture_dir)
    tex.interpolation = 'Smart'
    uv = nt.nodes.new('ShaderNodeUVMap')
    uv.location = (-480, 0)
    uv.uv_map = "UVMap"
    nt.links.new(uv.outputs['UV'], tex.inputs['Vector'])
    nt.links.new(tex.outputs['Color'], grp.inputs[IN_COLOR])

    grp.inputs[IN_EMIT].default_value = unlit
    if spec is not None:
        grp.inputs[IN_SPEC].default_value = spec
    mat.use_backface_culling = backface_cull
    return mat, nt, grp, tex


def _add_face_shadow(mat, nt, grp, tex):
    """Bang shadow: a height-driven band across the face.

    The band's height and softness are exposed as material custom
    properties so :mod:`character.shadow_rig` can drive them from a bone --
    sliding the shadow the hair casts up and down the forehead is a shot-by
    -shot decision in anime, not something to bake into the texture.
    """
    mat["face_shadow"] = C.SHADOW["face_shadow"]
    mat["face_shadow_softness"] = C.SHADOW["face_shadow_softness"]

    coord = nt.nodes.new('ShaderNodeTexCoord')
    coord.location = (-760, -320)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    sep.location = (-580, -320)
    nt.links.new(coord.outputs['Object'], sep.inputs['Vector'])

    band = nt.nodes.new('ShaderNodeMapRange')
    band.name = "FaceShadowBand"
    band.location = (-400, -320)
    band.clamp = True
    band.interpolation_type = 'SMOOTHSTEP'
    band.inputs['From Min'].default_value = C.Z["brow"] - 0.02
    band.inputs['From Max'].default_value = C.Z["brow"] + 0.06
    nt.links.new(sep.outputs['Z'], band.inputs['Value'])

    darken = nt.nodes.new('ShaderNodeMixRGB')
    darken.name = "FaceShadowMix"
    darken.blend_type = 'MULTIPLY'
    darken.location = (-120, -160)
    darken.inputs['Color2'].default_value = (*C.SHADOW["tint"], 1.0)
    nt.links.new(band.outputs['Result'], darken.inputs['Fac'])
    nt.links.new(tex.outputs['Color'], darken.inputs['Color1'])
    nt.links.new(darken.outputs['Color'], grp.inputs[IN_COLOR])
    return band, darken


def build_all(texture_dir=None):
    """Every material the character needs, keyed by the ``config.MAT`` id."""
    texture_dir = texture_dir or C.TEXTURE_DIR
    build_toon_group()
    mats = {}

    mat, nt, grp, tex = _base_material(C.MAT["skin"], "skin", texture_dir,
                                       spec=0.06)
    grp.inputs[IN_SPEC_SIZE].default_value = 0.10
    _add_face_shadow(mat, nt, grp, tex)
    mats["skin"] = mat

    mat, nt, grp, tex = _base_material(C.MAT["hair"], "hair", texture_dir,
                                       spec=0.34)
    grp.inputs[IN_SPEC_SIZE].default_value = 0.22
    mats["hair"] = mat

    # eyes stay mostly unlit so the iris keeps its painted shading
    mat, nt, grp, tex = _base_material(C.MAT["eyes"], "eyes", texture_dir,
                                       unlit=0.86, spec=0.45)
    grp.inputs[IN_SPEC_SIZE].default_value = 0.07
    mats["eyes"] = mat

    mat, nt, grp, tex = _base_material(C.MAT["mouth"], "skin", texture_dir,
                                       unlit=0.55, spec=0.0)
    mats["mouth"] = mat

    for key, spec in (("shirt", 0.07), ("pants", 0.07), ("shoes", 0.20),
                      ("gloves", 0.14)):
        mat, nt, grp, tex = _base_material(C.MAT[key], key, texture_dir,
                                           spec=spec)
        mats[key] = mat

    mats["contact_shadow"] = _contact_shadow_material()
    return mats


def _contact_shadow_material():
    """Soft transparent blob used for the ground contact shadow."""
    mat = bpy.data.materials.new(C.MAT["contact_shadow"])
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (400, 0)
    trans = nt.nodes.new('ShaderNodeBsdfTransparent')
    trans.location = (100, 120)
    diff = nt.nodes.new('ShaderNodeEmission')
    diff.location = (100, -80)
    diff.inputs['Color'].default_value = (0.03, 0.03, 0.05, 1.0)
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.name = "ContactMix"
    mix.location = (260, 0)
    grad = nt.nodes.new('ShaderNodeTexGradient')
    grad.gradient_type = 'SPHERICAL'
    grad.location = (-300, 0)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    coord.location = (-480, 0)
    nt.links.new(coord.outputs['Object'], grad.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.name = "ContactFalloff"
    ramp.location = (-120, 0)
    ramp.color_ramp.elements[0].position = 0.05
    ramp.color_ramp.elements[1].position = 0.95
    nt.links.new(grad.outputs['Fac'], ramp.inputs['Fac'])
    strength = nt.nodes.new('ShaderNodeMath')
    strength.name = "ContactOpacity"
    strength.operation = 'MULTIPLY'
    strength.location = (60, -260)
    strength.inputs[1].default_value = C.SHADOW["contact_opacity"]
    nt.links.new(ramp.outputs['Color'], strength.inputs[0])
    nt.links.new(strength.outputs['Value'], mix.inputs['Fac'])
    nt.links.new(trans.outputs['BSDF'], mix.inputs[1])
    nt.links.new(diff.outputs['Emission'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    # alpha blending moved from `blend_method` to `surface_render_method`
    # in 4.2; set whichever this build actually has
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'BLENDED'
    elif hasattr(mat, "blend_method"):
        mat.blend_method = 'BLEND'
    mat.use_backface_culling = True
    mat["contact_opacity"] = C.SHADOW["contact_opacity"]
    return mat


def toon_node(mat):
    """The TOON group instance inside a material, or None."""
    if not mat or not mat.node_tree:
        return None
    return mat.node_tree.nodes.get(TOON_NODE)


def toon_materials():
    """Every material carrying a TOON group -- the shadow rig's driver set."""
    return [m for m in bpy.data.materials if toon_node(m) is not None]
