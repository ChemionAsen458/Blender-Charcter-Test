# How the generator works

The whole character is built from three primitives and one idea.

## The three primitives

**Ring** — a closed cross-section, drawn as a superellipse. The exponent
controls how boxy it is: `2.0` is a true ellipse, `2.6` reads as a ribcage
rather than a tube. `meshlib.superellipse`.

**Loft** — a stack of rings bridged into quads. `MeshData.add_loft`.
Because every vertex comes from a known `(ring, column)` pair, the UV is
computed as it goes: `U` around, `V` along, mapped into a named rectangle
of the atlas. No unwrapping step, no packing, no seams in surprising
places.

**Fork** — one ring splitting into two, which is how the pelvis becomes two
legs. The torso's bottom ring is a 32-vertex loop; each half of it plus one
new inner-crotch vertex forms an 18-vertex leg ring, and the four remaining
edges close as a single crotch quad.

Limbs are lofted along a path with rotation-minimising frames
(`meshlib.parallel_frames`), so an arm that bends does not corkscrew its
UVs. Arms attach through a **socket**: a rectangular patch of the torso
loft is skipped, and its boundary — exactly
`2 × (rows + columns)` vertices, which is why `LIMB_SEGMENTS` is 14 — is
bridged to the arm's first ring, with the rotation chosen by minimising
total edge length so the deltoid does not come out twisted.

## The one idea

**Everything derives from the same tables.** `config.TORSO_RINGS`,
`HEAD_RINGS`, `ARM_PATH` and `LEG_PATH` describe the body. Clothing is not
modelled separately — `clothing.py` calls `body.torso_ring(z, inflate)` and
`body.leg_rings(side, inflate)` and gets the same sections grown outward.
Hair roots ride an ellipsoid fitted to the same skull. Eyes, brows and lips
ask `surface.FrontSampler` where the skin actually ended up and sit a
millimetre off it.

So changing `HEIGHT` or a ring radius re-proportions the character *and*
re-fits the clothes *and* moves the hair *and* keeps the face parts flush,
with no manual repair.

## Build order

`assemble.build()`:

1. **Materials** — `materials.build_all()` creates the shared `TOON-Core`
   node group and one material per surface, loading (or generating) the
   texture templates.
2. **Meshes** — body, then the face parts (which need the body to sample),
   then hair, then clothing.
3. **Shape keys** — each face builder returns alternative vertex sets from
   the *same* function at a different parameter, so topology matches by
   construction. `apply_shape_keys` turns them into real shape keys.
4. **Skeleton** — deform bones, controls, then face and shadow bones,
   *then* constraints (pole angles are solved by evaluating the posed rig,
   so the bones must all exist first).
5. **Skinning** — envelope weights for the body and garments, rigid binding
   for the face parts.
6. **Drivers** — face sliders to shape keys, `SHD-ctrl` to every material.

## Things worth knowing before you edit

**The head needs a neck blend.** A plain elliptical cross-section cannot be
both a tapered chin and a neck. `HEAD_RINGS` carries a sixth column,
`neck_blend`, that mixes the *back* half of each jaw ring toward
`JAW_COLUMN`. Without it the skull and the neck meet in a pinch.

**Facial features must be wider than one vertex.** Catmull–Clark averages a
lone displaced vertex down to roughly a third of its height, so a nose
built from one vertex disappears. `body._shape_head` spreads each feature
over three or more columns.

**Specular needs clamping, not tuning.** A bright key pushes a Glossy
BSDF's value well above 1.0, so thresholding it raw makes the "highlight"
cover half the model. `TOON-Core` scales the glossy term into 0–1 before
the threshold.

**Solve pole angles on a bent limb *and* at rest.** On a straight limb every
pole angle scores identically, so a rest-pose solver picks one at random and
you get knees that bend backwards; scoring only the bend picks the right
hemisphere but not the right angle within it.
`armature._solve_pole_angle` does both — better-bending half first, then
smallest rest drift — and `pole_position` places the pole in the plane of
the modelled bend so a right answer exists at all.

**An IK chain reaches its target's head.** A foot control lying flat on the
floor is not where the ankle is, so aiming the shin at it drags the ankle
85 mm down before anything is posed. `foot_socket` exists for that reason.

**Bone "local space" carries the rest offset.** A Copy Rotation in
LOCAL/LOCAL between two bones with different rest orientations is *not*
identity at rest — it threw the foot 190 mm out. Either match the rest
orientations and copy in world space (what the rig does now), or expect to
debug it.

**Turn off IK stretch.** It defaults on, and a stretched limb propagates
scale into everything parented below it.

**The eyelid has to clear the cornea.** The eye shell bulges forward so the
iris catches light; if the lid's free edge does not ride further out than
that bulge, a blink sweeps the lid *behind* the eye and the eye stays open
with the shape key at 1.0. `face.py` asserts the relationship.

**Heat weighting has a blind spot.** It cannot reach geometry that is not
connected to the rest of the mesh -- free-floating bands like the knee
straps come back with no weights -- so those get filled in by distance
afterwards.

**Custom properties do not tag the depsgraph.** If you write a test that
sets `bone["prop"] = x` and reads a driven value, you will read a stale
number unless you call `update_tag()` and read from `evaluated_get()`. See
`tools/verify._refresh`.

## Extending it

| To add | Do this |
| --- | --- |
| A new garment | Write a builder in `clothing.py` using `B.torso_ring` / `B.leg_rings`, add a UV rectangle to `UV_ATLAS`, a palette entry, a `BUILDERS` entry in `generate_textures.py`, and an `OBJ`/`MAT` name. |
| A new expression | Add a parameter set to the relevant builder in `face.py`, then a driver in `face_rig.add_shape_drivers`. |
| A new shadow control | Add it to `SHADOW_PROPERTIES`, map it to a socket in `PROP_TO_SOCKET`, and add the socket to `TOON-Core`. |
| A different hairstyle | Rewrite the band functions in `hair.py`; `_clump` handles the flow-along-the-skull maths. |

Run `python3 -m tools.verify` after any rig change.
