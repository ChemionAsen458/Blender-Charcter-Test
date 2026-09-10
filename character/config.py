"""Central configuration for the anime character generator.

Everything that describes *what the character looks like* lives here:
proportions, colour palette, mesh resolutions and object/material naming.
The generator modules read from this file so the whole model can be
re-proportioned without touching geometry code.

Units are Blender metres.  The character stands on Z = 0 facing -Y (Blender convention).
"""

# --------------------------------------------------------------------------
# Identity / naming
# --------------------------------------------------------------------------

CHARACTER_NAME = "Kaito"

PREFIX = "CHR"          # meshes            -> CHR-Body
RIG_NAME = "RIG-Kaito"  # armature object
MAT_PREFIX = "MAT"      # materials         -> MAT-Skin
SET_PREFIX = "SET"      # scene furniture   -> SET-ShadowCatcher

OBJ = {
    "body":   f"{PREFIX}-Body",
    "eye_l":  f"{PREFIX}-Eye-L",
    "eye_r":  f"{PREFIX}-Eye-R",
    "brow_l": f"{PREFIX}-Brow-L",
    "brow_r": f"{PREFIX}-Brow-R",
    "mouth":  f"{PREFIX}-Mouth",
    "cavity": f"{PREFIX}-MouthCavity",
    "hair":   f"{PREFIX}-Hair",
    "shirt":  f"{PREFIX}-Shirt",
    "pants":  f"{PREFIX}-Pants",
    "shoes":  f"{PREFIX}-Shoes",
    "gloves": f"{PREFIX}-Gloves",
    "contact_shadow": f"{PREFIX}-ContactShadow",
}

MAT = {
    "skin":   f"{MAT_PREFIX}-Skin",
    "hair":   f"{MAT_PREFIX}-Hair",
    "eyes":   f"{MAT_PREFIX}-Eyes",
    "mouth":  f"{MAT_PREFIX}-Mouth",
    "shirt":  f"{MAT_PREFIX}-Shirt",
    "pants":  f"{MAT_PREFIX}-Pants",
    "shoes":  f"{MAT_PREFIX}-Shoes",
    "gloves": f"{MAT_PREFIX}-Gloves",
    "contact_shadow": f"{MAT_PREFIX}-ContactShadow",
}

# Texture template stem -> the material that consumes it.
TEXTURE_SETS = ("skin", "hair", "eyes", "shirt", "pants", "shoes", "gloves")

TEXTURE_SIZE = 2048
TEXTURE_DIR = "textures/generated"

# --------------------------------------------------------------------------
# Mesh resolution
# --------------------------------------------------------------------------

TORSO_SEGMENTS = 32     # verts around the torso / head loft
LIMB_SEGMENTS = 14      # verts around arm & leg tubes
FINGER_SEGMENTS = 8
LEG_SEGMENTS = TORSO_SEGMENTS // 2 + 2   # forced by the crotch fork
SUBSURF_VIEWPORT = 1
SUBSURF_RENDER = 2

# --------------------------------------------------------------------------
# Proportions
# --------------------------------------------------------------------------
# ~7.0 heads tall: a slim, athletic teenage build matching the reference
# turnaround.  HEIGHT is the sole-to-crown measurement.

HEIGHT = 1.72
CHIN_Z = 1.475
CROWN_Z = 1.720
HEAD_HEIGHT = CROWN_Z - CHIN_Z          # 0.245  -> 7.02 heads

# Named heights used by geometry *and* by the rig, so bones land on the
# same landmarks the mesh was built from.
Z = {
    "sole": 0.000,
    "ankle": 0.085,
    "calf": 0.300,
    "knee": 0.452,
    "thigh": 0.650,
    "crotch": 0.815,
    "hip": 0.900,
    "waist": 0.980,
    "ribs": 1.075,
    "chest": 1.180,
    "upper_chest": 1.290,
    "shoulder": 1.355,
    "trap": 1.395,
    "neck_base": 1.418,
    "chin": CHIN_Z,
    "mouth": 1.522,
    "nose": 1.548,
    "eye": 1.586,
    "brow": 1.614,
    "hairline": 1.660,
    "crown": CROWN_Z,
}

# Torso cross-sections: (z, half_width_x, half_depth_y, centre_y, squareness)
# `squareness` feeds a superellipse: 2.0 = ellipse, higher = boxier.
# +centre_y shifts a section backwards, -centre_y forwards.
# Row indices matter: SHOULDER_SOCKET below indexes into this list.
TORSO_RINGS = [
    (Z["crotch"],      0.124, 0.098,  0.000, 2.5),   # 0
    (0.858,            0.143, 0.105,  0.001, 2.5),   # 1
    (Z["hip"],         0.149, 0.107,  0.002, 2.5),   # 2
    (0.940,            0.137, 0.099,  0.001, 2.4),   # 3
    (Z["waist"],       0.127, 0.092,  0.000, 2.3),   # 4
    (1.028,            0.132, 0.096, -0.002, 2.3),   # 5
    (Z["ribs"],        0.140, 0.101, -0.003, 2.4),   # 6
    (1.128,            0.150, 0.107, -0.004, 2.5),   # 7
    (Z["chest"],       0.158, 0.111, -0.004, 2.6),   # 8
    (1.236,            0.166, 0.110, -0.002, 2.6),   # 9
    (Z["upper_chest"], 0.174, 0.107,  0.001, 2.6),   # 10
    (1.325,            0.178, 0.101,  0.004, 2.6),   # 11
    (Z["shoulder"],    0.172, 0.093,  0.006, 2.5),   # 12
    (Z["trap"],        0.122, 0.082,  0.009, 2.3),   # 13
    (Z["neck_base"],   0.068, 0.070,  0.012, 2.0),   # 14
    (1.448,            0.060, 0.063,  0.013, 2.0),   # 15
]

# Rectangular hole cut into the torso loft for each arm, as
# (ring_start, ring_end, column_start, column_end).  The boundary of the
# hole is 2 * ((r1 - r0) + (c1 - c0)) verts, which must equal
# LIMB_SEGMENTS so the deltoid bridges as clean quads.
SHOULDER_SOCKET = {"rows": (10, 12), "cols_l": (6, 11), "cols_r": (21, 26)}

# Head cross-sections: (z, half_width_x, half_depth_y, centre_y, squareness)
# Head cross-sections:
#   (z, half_width_x, half_depth_y, centre_y, squareness, neck_blend)
# `neck_blend` mixes the *back* half of the section toward the neck
# section.  Without it the jaw rings -- which must taper to a narrow chin
# at the front -- would also pinch in at the back, putting a notch between
# the skull and the neck.  With it, the front tapers to a chin while the
# back sweeps into the throat, which is what a real mandible does.
HEAD_RINGS = [
    (1.458,             0.016, 0.032,  0.012, 2.0, 0.95),
    (1.468,             0.028, 0.050,  0.004, 2.1, 0.90),
    (CHIN_Z,            0.038, 0.068, -0.014, 2.3, 0.84),
    (1.490,             0.051, 0.077, -0.013, 2.5, 0.74),
    (1.508,             0.064, 0.084, -0.010, 2.6, 0.60),
    (1.528,             0.075, 0.088, -0.005, 2.6, 0.42),
    (1.550,             0.083, 0.092, -0.002, 2.5, 0.24),
    (1.568,             0.087, 0.094,  0.001, 2.4, 0.10),
    (Z["eye"],          0.089, 0.095,  0.003, 2.3, 0.00),
    (1.604,             0.089, 0.096,  0.005, 2.2, 0.00),
    (Z["brow"] + 0.012, 0.089, 0.096,  0.007, 2.2, 0.00),
    (1.642,             0.087, 0.094,  0.009, 2.1, 0.00),
    (Z["hairline"],     0.084, 0.090,  0.011, 2.1, 0.00),
    (1.682,             0.077, 0.082,  0.013, 2.0, 0.00),
    (1.700,             0.063, 0.067,  0.015, 2.0, 0.00),
    (1.712,             0.044, 0.047,  0.016, 2.0, 0.00),
    (CROWN_Z,           0.020, 0.022,  0.016, 2.0, 0.00),
]

# The section the jaw rings blend toward at the back: the top of the neck,
# opened out a little for the angle of the mandible.
JAW_COLUMN = {"rx": 0.066, "ry": 0.072, "cy": 0.016}

# Anime faces are flatter than real ones: front-facing verts between these
# heights are pulled back toward a plane by FACE_FLATTEN.
FACE_FLATTEN = 0.55
FACE_FLATTEN_Z = (1.500, 1.665)

# Arm centre-line: (x, y, z, radius).  Mirrored for the right side.
ARM_PATH = [
    (0.163, -0.004, 1.336, 0.056),   # sits in the shoulder socket
    (0.184, -0.002, 1.288, 0.053),   # deltoid
    (0.194,  0.000, 1.216, 0.047),
    (0.200,  0.002, 1.140, 0.043),
    (0.205,  0.004, 1.062, 0.040),   # elbow
    (0.209,  0.005, 0.984, 0.037),
    (0.213,  0.005, 0.922, 0.033),
    (0.216,  0.004, 0.870, 0.029),   # wrist
]
ELBOW_INDEX = 4
WRIST = (0.216, 0.004, 0.870)

# Leg centre-line: (x, y, z, radius)
LEG_PATH = [
    (0.090, 0.000, 0.905, 0.090),    # buried in the pelvis
    (0.092, 0.002, 0.815, 0.086),
    (0.091, 0.004, Z["thigh"], 0.074),
    (0.089, 0.005, 0.540, 0.065),
    (0.088, 0.007, Z["knee"], 0.062),   # knee
    (0.087, 0.000, 0.380, 0.060),
    (0.086, -0.004, Z["calf"], 0.056),
    (0.085, -0.002, 0.190, 0.046),
    (0.085, 0.002, Z["ankle"], 0.037),  # ankle
]
KNEE_INDEX = 4

# Foot block (before the shoe): heel/toe extents in Y, sole at Z.
FOOT = {
    "heel_y": 0.062,
    "toe_y": -0.158,
    "width": 0.046,      # half width
    "sole_z": 0.010,
    "ankle_z": Z["ankle"],
    "x": 0.085,
}

# Hand: palm block plus five digits.
HAND = {
    "wrist": WRIST,
    "palm_len": 0.082,
    "palm_half_w": 0.046,
    "palm_half_d": 0.022,
    # (name, base_u, spread, length, radius) - base_u is across the palm,
    # -1 = pinky side, +1 = index side
    "fingers": [
        ("index",  0.78, 0.018, 0.064, 0.0136),
        ("middle", 0.26, 0.005, 0.070, 0.0142),
        ("ring",  -0.27, -0.005, 0.064, 0.0132),
        ("pinky", -0.79, -0.018, 0.052, 0.0116),
    ],
    "thumb": {"base_u": 0.92, "length": 0.056, "radius": 0.0155},
}

# --------------------------------------------------------------------------
# Facial feature placement (drives eye sockets, brows, mouth and the rig)
# --------------------------------------------------------------------------

EYE = {
    "x": 0.0385,          # centre of the eyeball
    "z": Z["eye"],
    "y": -0.058,          # eyeballs sit inside the skull; -Y is forward
    "radius": 0.0225,
    "iris_radius": 0.0148,
    "pupil_radius": 0.0062,
    "socket_w": 0.036,    # half width of the modelled socket opening
    "socket_h": 0.019,
}

BROW = {
    "x": 0.0400,
    "z": Z["brow"],
    "y": -0.086,
    "length": 0.050,
    "height": 0.0090,
    "thickness": 0.0055,
    "tilt": -0.14,        # radians, inner end lower = the reference's scowl
}

MOUTH = {
    "z": Z["mouth"] - 0.006,
    "y": -0.088,
    "width": 0.0210,      # half width
    "height": 0.0034,     # half height of the neutral lip line
}

# --------------------------------------------------------------------------
# Hair
# --------------------------------------------------------------------------
# The reference has messy, layered, spiky brown hair.  Each strand is a
# tapered shell swept from the scalp: (theta, phi, length, width, lift, twist)
# theta = around the head (0 = front, +ve toward the character's left)
# phi   = up the skull (0 = hairline, 1 = crown)

HAIR = {
    "shell_offset": 0.011,      # scalp cap floats above the skin
    "strand_sections": 5,
    "strand_width_root": 0.030,
    "strand_taper": 0.30,
}

# --------------------------------------------------------------------------
# Clothing offsets (metres above the skin)
# --------------------------------------------------------------------------

CLOTH = {
    "shirt": 0.011,
    "shirt_sleeve": 0.010,
    "pants": 0.009,
    "pants_thigh": 0.008,
    "shoe": 0.014,
    "glove": 0.006,
}

SHIRT = {
    "hem_z": 0.905,           # bottom of the tee
    "collar_z": Z["trap"],
    "sleeve_end": 3,          # index into ARM_PATH where the sleeve stops
}

PANTS = {
    "waist_z": 0.995,
    "cuff_index": 8,          # index into LEG_PATH where the leg opening ends
    "knee_pad": {
        "z": Z["knee"] + 0.014,
        "half_h": 0.064,
        "half_w": 0.056,
        "depth": 0.026,
        "strap_dz": 0.074,
        "strap_h": 0.0075,
    },
}

SHOE = {
    "top_z": 0.175,           # high-top collar
    "sole_z": 0.000,
    "sole_h": 0.030,
    "heel_y": 0.082,
    "toe_y": -0.188,
    "half_w": 0.058,
}

GLOVE = {
    "cuff_z": 0.900,          # wrist band top
    "cuff_bottom": 0.862,
    "knuckle_z": 0.788,
}

# --------------------------------------------------------------------------
# Palette  (linear-ish sRGB tuples, 0-1)
# --------------------------------------------------------------------------

PALETTE = {
    "skin":            (0.788, 0.561, 0.404),
    "skin_shadow":     (0.647, 0.396, 0.271),
    "skin_deep":       (0.522, 0.286, 0.196),
    "blush":           (0.816, 0.478, 0.396),
    "freckle":         (0.560, 0.330, 0.235),
    "lip":             (0.635, 0.353, 0.294),

    "hair":            (0.290, 0.192, 0.153),
    "hair_shadow":     (0.180, 0.114, 0.090),
    "hair_light":      (0.435, 0.294, 0.220),
    "hair_rim":        (0.560, 0.400, 0.300),

    "eye_silver":      (0.776, 0.796, 0.824),
    "eye_silver_dark": (0.494, 0.522, 0.561),
    "eye_rim":         (0.235, 0.251, 0.282),
    "pupil":           (0.086, 0.094, 0.110),
    "sclera":          (0.949, 0.941, 0.929),
    "sclera_shadow":   (0.741, 0.741, 0.749),

    "cloth_black":     (0.102, 0.102, 0.110),
    "cloth_black_hi":  (0.180, 0.180, 0.192),
    "cloth_black_lo":  (0.047, 0.047, 0.055),
    "cloth_white":     (0.929, 0.929, 0.929),
    "cloth_white_lo":  (0.741, 0.745, 0.760),
    "plate_silver":    (0.831, 0.847, 0.867),
    "plate_grey":      (0.616, 0.635, 0.659),
    "sole_white":      (0.910, 0.910, 0.914),
    "sole_grey":       (0.502, 0.514, 0.533),

    "mouth_inner":     (0.290, 0.145, 0.145),
}

# --------------------------------------------------------------------------
# UV atlas layout
# --------------------------------------------------------------------------
# Each body region owns a rectangle of the 0-1 square.  Left/right pairs
# share a rectangle so the texture stays symmetric and half the resolution
# is not wasted.  (u0, v0, u1, v1)

UV_ATLAS = {
    "skin": {
        "head":    (0.505, 0.505, 0.995, 0.995),
        "torso":   (0.010, 0.505, 0.490, 0.995),
        "arm":     (0.010, 0.260, 0.320, 0.490),
        "leg":     (0.340, 0.260, 0.650, 0.490),
        "hand":    (0.010, 0.010, 0.320, 0.245),
        "foot":    (0.340, 0.010, 0.650, 0.245),
        # face detail strip, split so the parts never share texels
        "mouth":   (0.668, 0.010, 0.828, 0.062),
        "lid_lo":  (0.668, 0.072, 0.828, 0.126),
        "lid_up":  (0.668, 0.136, 0.828, 0.210),
        "ear":     (0.842, 0.010, 0.995, 0.210),
        "face":    (0.668, 0.220, 0.995, 0.246),
    },
    "hair": {
        "cap":     (0.010, 0.510, 0.990, 0.990),
        "strand":  (0.010, 0.150, 0.990, 0.490),
        "brow":    (0.010, 0.010, 0.490, 0.130),
    },
    "eyes": {
        "iris":    (0.010, 0.510, 0.490, 0.990),
        "sclera":  (0.510, 0.510, 0.990, 0.990),
        "highlight": (0.010, 0.010, 0.490, 0.490),
    },
    "shirt": {
        "body":    (0.010, 0.330, 0.990, 0.990),
        "sleeve":  (0.010, 0.010, 0.490, 0.310),
        "collar":  (0.510, 0.010, 0.990, 0.310),
    },
    "pants": {
        "hip":     (0.010, 0.660, 0.990, 0.990),
        "leg":     (0.010, 0.180, 0.660, 0.640),
        "pad":     (0.680, 0.180, 0.990, 0.640),
        "strap":   (0.010, 0.010, 0.990, 0.160),
    },
    "shoes": {
        "upper":   (0.010, 0.420, 0.990, 0.990),
        "sole":    (0.010, 0.180, 0.990, 0.400),
        "detail":  (0.010, 0.010, 0.990, 0.160),
    },
    "gloves": {
        "hand":    (0.010, 0.400, 0.990, 0.990),
        "plate":   (0.010, 0.180, 0.660, 0.380),
        "cuff":    (0.680, 0.180, 0.990, 0.380),
        "detail":  (0.010, 0.010, 0.990, 0.160),
    },
}

# --------------------------------------------------------------------------
# Shadow rig defaults (see character/shadow_rig.py)
# --------------------------------------------------------------------------

SHADOW = {
    "threshold": 0.50,       # where the cel terminator sits, 0-1
    "softness": 0.045,       # 0 = razor edge
    "strength": 1.00,        # how far toward the shadow colour we go
    "tint": (0.62, 0.60, 0.78),   # anime shadows lean cool/violet
    "rim_strength": 0.55,
    "rim_width": 0.42,
    "spec_strength": 0.12,
    "face_shadow": 0.0,      # bang shadow height, driven by SHD-FaceShadow
    "face_shadow_softness": 0.10,
    "contact_opacity": 0.55,
    "contact_radius": 0.30,
    "key_light_energy": 3.0,
    "fill_light_energy": 1.1,
    "key_light_angle": (1.05, 0.0, 0.62),    # euler, radians
    "fill_light_angle": (1.30, 0.0, -2.20),
}
