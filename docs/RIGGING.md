# Rigging guide

![Expressions](images/expressions.png)

101 bones, organised into seven bone collections. Open the Armature tab and
toggle collections to show only what you need: `Controls`, `IK`, `FK`,
`Face`, `Shadow`, `Mechanism`, `Deform` (the last two are hidden by
default).

Rotation mode is XYZ Euler on every bone. Control bones have their
irrelevant channels locked, so you can grab a slider and drag without
worrying about which axis it lives on.

---

## Body

### Controls

| Bone | Use |
| --- | --- |
| `root` | The whole character. Move it, rotate it, scale it — the lights and the contact shadow come along. |
| `torso` | Centre of gravity. Everything above the legs hangs off it. |
| `hips_ctrl` | Rotates the pelvis without moving the chest. |
| `chest_ctrl` | Rotates the ribcage. |
| `neck_ctrl`, `head_ctrl` | Neck and head rotation. |
| `properties` | No transform — it carries the FK/IK sliders. |

### IK

Both arms and both legs are two-bone IK chains.

| Bone | Use |
| --- | --- |
| `hand_ik.L` / `.R` | Hand goal. The hand also copies its rotation. |
| `elbow_pole.L` / `.R` | Elbow direction. Translation only. |
| `foot_ik.L` / `.R` | Foot goal, sitting flat on the floor at Z = 0. The foot copies its rotation, so rotating this control rolls the whole foot. |
| `toe_ik.L` / `.R` | Toe roll, for peeling the foot off the ground. |
| `knee_pole.L` / `.R` | Knee direction. Translation only. |
| `foot_socket.L` / `.R` | Mechanism, hidden by default. See below. |

The foot control lies flat on the floor, but the IK chain has to reach the
**ankle**. Aiming the shin at the control itself drags the ankle 85 mm down
to floor level before anything is even posed, so the chain targets
`foot_socket` instead — a child of the control that duplicates the foot
bone exactly. That also makes the foot's rotation copy identity at rest.

### Pole targets and pole angles

Two-bone IK forces the middle joint into the plane through the root, the
tip and the pole. Two things follow, and both are handled at build time:

* **Pole placement.** `armature.pole_position` projects the modelled elbow
  (or knee) onto the shoulder-to-wrist axis and pushes the pole straight
  out along that offset, so the plane contains the bend *as modelled*. A
  pole placed by eye puts the joint somewhere else the moment IK engages.
* **Pole angle.** `armature._solve_pole_angle` scores every candidate twice:
  once with the limb deliberately bent, to find which half of the circle
  drives the knee forward and the elbow back, and once at rest, to find
  which angle disturbs the modelled pose least. It takes the better-bending
  half, then the smallest rest error. Scoring at rest alone is not enough —
  a straight limb is indifferent to the pole, so every angle ties and the
  solver picks one at random, which is exactly how knees end up bending
  backwards.

Both limbs are modelled with their joints already bowed the right way — the
elbow backwards, the knee forwards — so the IK plane and the mesh agree.
The build prints the outcome:

```
[build]   IK leg.L: pole angle  -86.0 deg, rest error 0.22 mm
```

The rest error is how far the joint drifts from its modelled position with
IK switched on. It should be a fraction of a millimetre.

IK stretching is switched off, so an out-of-reach goal leaves the limb
straight rather than scaling the bones (and, through inherited scale, the
feet).

### FK/IK blending

On the `properties` bone:

| Property | Range |
| --- | --- |
| `ik_arm_l`, `ik_arm_r` | 0 = pure FK, 1 = pure IK |
| `ik_leg_l`, `ik_leg_r` | 0 = pure FK, 1 = pure IK |
| `hand_follow_l`, `hand_follow_r` | Whether the hand copies its IK control's rotation |

These drive the IK constraints' influence, so you can key a hand onto a
prop and back off again. Blending mid-shot needs the FK bones matched to
the IK pose by hand — there is no auto-snap operator.

### Fingers

Five digits per hand, three phalanges each: `index.01.L` … `index.03.L`,
and likewise `middle`, `ring`, `pinky`, `thumb`. They are plain FK, curling
naturally on their local X.

---

## Face

Two mechanisms, deliberately kept apart so nothing double-transforms.

**Rigid parts** — the eyeballs — are weighted to their own bone and simply
rotate. **Deforming parts** — brows, lids, lips — are weighted to `head`,
and their bones are *sliders*: dragging one along a local axis drives a
shape key. Limit Location constraints clamp each slider to the range its
shape keys actually cover, so you cannot drag past the pose that exists.

| Bone | Drag | Result |
| --- | --- | --- |
| `eye_target` | anywhere | both eyes follow it |
| `eye_target.L` / `.R` | anywhere | one eye only |
| `lid_up.L` / `.R` | **down** | blink (fully closed at −12 mm) |
| `lid_up.L` / `.R` | **up** | eye widens |
| `lid_lo.L` / `.R` | **up** | lower lid rises |
| `brow.L` / `.R` | **up / down** | eyebrow raises / lowers |
| `brow.L` / `.R` | **toward the nose** | scowl |
| `brow.L` / `.R` | **away from the nose** | worried |
| `mouth` | **down** | mouth opens |
| `mouth` | **sideways** | mouth widens / narrows |
| `mouth_corner.L` / `.R` | **up / down** | smile / frown |
| `jaw` | **rotate X** | jaw opens; the chin deforms and the mouth follows |

`jaw` is a genuine deform bone with a Limit Rotation of −4° to +26°, and it
also feeds the mouth's `open` shape key, so opening the jaw opens the lips
without a second control.

### Face properties

On the `face_props` bone, all 0–1:

`brow_angry_l/r` · `brow_sad_l/r` · `brow_arch_l/r` · `squint_l/r` ·
`mouth_smile` · `mouth_frown` · `mouth_pucker`

These stack additively with the sliders, so you can dial in a permanent
scowl and still animate the brows on top.

### Shape keys per object

The eye shell, the eyelids and the face are three layers a couple of
millimetres apart, and the order matters: the lid's free edge rides
outside the eye's corneal bulge, or a blink would sweep the lid behind the
eye and leave it open. `face.py` asserts that clearance and
`tools/verify.py` re-checks it on the built file.

| Object | Keys |
| --- | --- |
| `CHR-LidUp-L/R`, `CHR-LidLo-L/R` | `blink`, `wide`, `squint` |
| `CHR-Brow-L/R` | `up`, `down`, `angry`, `sad`, `raise` |
| `CHR-Mouth` | `open`, `wide`, `narrow`, `smile`, `frown`, `pucker` |

Every one is generated by re-running the same builder at a different
parameter, so topology is identical by construction rather than by hand.

---

## Shadow rig

![Shadow rig](images/shadow_rig.png)

Cel shading turns shadow into a posed element. All of it lives on bones.
Every frame above is the same model in the same pose; only `SHD-ctrl` and
`SHD-key` differ.

### Light direction

`SHD-key`, `SHD-fill` and `SHD-rim` are arrow-shaped handles. A Sun lamp
rides each one via a Child Of constraint, rotated so the light travels
**down the bone, head to tail**. Point the bone at the character and the
light points there too; rotate it and the cel terminator sweeps across
every surface at once.

They hang off `SHD-root`, which hangs off `root` — so the lighting travels
with the character. That is normally what you want for a cel-shaded shot; if
you want fixed studio lights instead, re-parent `SHD-root` to nothing.

### `SHD-ctrl` — the look

14 properties, each driving every toon material simultaneously:

| Property | Effect |
| --- | --- |
| `shadow_threshold` | Where the terminator sits on the light ramp. Higher = more of the model in shadow. |
| `shadow_softness` | Terminator width. `0.005` is a razor edge, `0.25` is nearly smooth shading. |
| `shadow_strength` | How far the dark side travels toward the shadow colour. |
| `shadow_tint_r/g/b` | Shadow colour multiplier. The default leans cool violet, which is the usual anime choice. |
| `rim_strength`, `rim_width` | Back-light along the silhouette. |
| `spec_strength` | Highlight level. |
| `face_shadow_softness` | Edge hardness of the fringe shadow. |
| `contact_opacity` | Ground patch opacity. |
| `key_energy`, `fill_energy` | Light levels, driven straight onto the lamps. |
| `cast_softness` | Angular size of the key light in degrees — hard sun or overcast. |

### `SUN-body`, `SUN-face`, `SUN-hair` — per-region grading

![Region grading](images/regions.png)

Same pose, same `SHD-ctrl` across all four frames; only one region control
moves. Left to right: uniform, `SUN-face` lifted, `SUN-hair` hardened,
`SUN-body` deepened. Render it yourself with
`python3 -m tools.showcase --only regions`.

`SHD-ctrl` moves the whole character at once, which is the right default
and the wrong final answer: an anime key almost always wants the face
reading cleaner than the body, and the hair harder than either.

The reference rig solves this with three shader groups
(`BASE_SunBody_Group`, `BASE_SunFace_Group`, `BASE_SunHair`) fed by three
separate suns, steered from a `Sunvec` bone collection. Blender's own
light-linking would be the obvious way to reproduce that — but **EEVEE
Next ignores light linking** (verified by rendering the same scene with and
without a receiver collection: identical). So the split is made where the
reference makes it too, in the materials.

Three bones in the `Sunvec` collection carry five offsets each:

| Property | Effect |
| --- | --- |
| `threshold_offset` | Move this region's terminator away from the master. |
| `softness_offset` | Soften or harden just this region's edge. |
| `strength_offset` | Deepen or lift just this region's shadow. |
| `rim_offset`, `spec_offset` | Rim and highlight, relative to the master. |

They **offset**, they do not replace: each material's driver reads
`master + offset`, so `SHD-ctrl` still grades everything in one gesture and
the regions keep their relative separation as it moves.

| Region | Materials |
| --- | --- |
| `SUN-body` | `MAT-SkinBody`, `MAT-Shirt`, `MAT-Pants`, `MAT-Shoes`, `MAT-Gloves` |
| `SUN-face` | `MAT-Skin`, `MAT-Mouth`, `MAT-Eyes` |
| `SUN-hair` | `MAT-Hair` |

The skin being two materials is what makes the face row possible, and is
exactly why the reference splits `Skin` from `Skin Body`. `CHR-Body` carries
both in slots 0 and 1; the head loft and the crown cap go into slot 1, the
rest into slot 0, so the split costs no extra geometry.

Everything defaults to `0.0` — out of the box the character looks exactly
as it did before, and the regions only diverge once you dial one.

### `SHD-face` — the bang shadow

Anime characters carry a shadow where the fringe falls across the forehead,
and where it sits is a shot decision. Drag `SHD-face` up and down (±60 mm)
and the band slides up and down the face. It is implemented as a
height-driven band on `MAT-Skin` — `FaceShadowBand` — whose lower edge
follows the bone and whose upper edge is that plus `face_shadow_softness`.

### `SHD-contact` — the ground patch

`CHR-ContactShadow` is a soft radial blob parented to this bone. Move it to
follow the character's weight, scale the bone to grow or shrink the patch,
and fade it with `contact_opacity`. It is separate from the real cast
shadow on `SET-ShadowCatcher`, which comes from the key light.

---

## Skinning

The body and all four garments are bound with **bone heat**. Distance-based
weighting cannot tell that an arm hanging beside the body is not attached to
the lower back — it just sees a bone 13 cm away and hands it a quarter of
the vertex, which drags the whole torso along when the arm moves. Heat
diffuses across the surface instead, so influence has to travel through the
mesh.

Heat has one blind spot: geometry that is not connected to the rest of the
mesh comes back with no weights at all. The trouser knee straps are
free-floating bands, so `skinning.heat_weight` fills just those vertices in
by distance afterwards rather than discarding the good weights everywhere
else. `character/skinning.py` also keeps a full envelope implementation as
a fallback if the heat solver refuses a mesh outright.

The eyeballs are excluded from automatic weighting — they sit *inside* the
skull, so any distance-based scheme hands them a patch of face. They and
the other face shells bind rigidly to a single bone instead.

`tools/verify.py` asserts that no vertex on the body or any garment is left
unweighted, and that each has exactly one armature modifier.

---

## Verifying changes

`python3 -m tools.verify --blend build/kaito.blend` runs 96 checks that
*pose* the rig and measure the response — IK moves the foot 12 cm, the
blink slider closes the eye, `SHD-ctrl` retints all nine toon materials,
`SUN-face` moves the face and leaves the body alone, `SHD-key` turns the
lamp 60°. One more check runs per supplied input map, confirming it
actually reaches the shader. If you change the rig, run it. Failures print
the measured number, so they can be diagnosed without opening Blender.

The checks worth understanding are the **rest-pose** ones. Constraints are
evaluated even when every control is at zero, so "all bones at zero" is not
the same as "the model is where it was modelled". These assert that with
the rig at rest no bone has moved more than 4 mm and no mesh has drifted
more than 4 mm from its unrigged shape. That is the check that catches an
IK chain aimed at the wrong target, a rotation copy whose spaces do not
match at rest, or stretchy IK quietly scaling a limb — all of which look
fine in a bone display and wreck the render.
