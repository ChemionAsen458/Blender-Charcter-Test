# Input textures — drop your maps here

Anything you put in this folder **overrides** the procedurally generated
template of the same name in `textures/generated/`. The build picks them up
automatically; nothing else needs editing.

## Naming

```
textures/input/<piece>_color.png     base colour / albedo  -> Yang-style "Lit" input
textures/input/<piece>_shaded.png    hand-painted shadow pass -> "Shaded" input
textures/input/<piece>_normal.png    tangent-space normal map -> "Normal" input
textures/input/<piece>_shade.png     greyscale terminator bias -> "ShadeMap" input
```

`<piece>` is one of the seven materials:

| `<piece>` | Material | Covers |
| --- | --- | --- |
| `skin`   | `MAT-Skin`   | body, face, hands, feet, ears, eyelids, mouth |
| `hair`   | `MAT-Hair`   | scalp, all hair clumps, eyebrows |
| `eyes`   | `MAT-Eyes`   | both eye shells (iris, sclera, highlights) |
| `shirt`  | `MAT-Shirt`  | the tee |
| `pants`  | `MAT-Pants`  | trousers, knee plates, straps |
| `shoes`  | `MAT-Shoes`  | high-tops, midsoles |
| `gloves` | `MAT-Gloves` | fingerless gloves, knuckle plates |

Only `_color` is required for a piece to look right; every other suffix is
optional and falls back to a derived or neutral default:

* no `_shaded` -> derived from `_color` by the shadow tint in `config.SHADOW`
* no `_normal` -> flat geometry normal, no perturbation
* no `_shade`  -> uniform 0, terminator sits wherever the light puts it

## Format

* **2048 x 2048 PNG**, sRGB for `_color`/`_shaded`, **Non-Colour** for
  `_normal`/`_shade` (the build sets the colour space, you just supply
  the file).
* Tangent-space normal maps, OpenGL convention (+Y up). If yours are
  DirectX (-Y), say so and the build will flip the green channel.
* The UV layout is **not** arbitrary — see below. Paint on top of the
  matching `textures/generated/<piece>_guide.png`, which draws the UV
  wireframe and labels every rectangle.

## Reference images instead of maps

If you would rather hand over concept art / photo reference than finished
maps, drop them here too under any name and note which piece they belong
to; they will be projected into the atlas rather than used directly.
