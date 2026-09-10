#!/usr/bin/env python3
"""Build the rigged anime character and save it as a .blend file.

Run it either through Blender:

    blender --background --python build.py -- --out build/kaito.blend

or, if the ``bpy`` module is installed, straight from Python:

    python3 build.py --out build/kaito.blend

Textures are generated into ``textures/generated`` on first run and reused
afterwards; pass ``--regen-textures`` to rebuild them.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def parse_args(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--" in argv:                       # blender --python build.py -- ...
        argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join("build", "kaito.blend"))
    ap.add_argument("--textures", default=None,
                    help="directory holding the texture templates")
    ap.add_argument("--texture-size", type=int, default=None)
    ap.add_argument("--regen-textures", action="store_true")
    ap.add_argument("--no-rig", action="store_true")
    ap.add_argument("--pack", action="store_true",
                    help="pack the textures into the .blend so it is "
                         "self-contained (breaks live repainting)")
    ap.add_argument("--preview", metavar="DIR", default=None,
                    help="also render turnaround previews into DIR")
    ap.add_argument("--quiet", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    import bpy
    from character import assemble, blendutil as BU, config as C, scene
    from tools.generate_textures import generate

    texture_dir = args.textures or os.path.join(HERE, C.TEXTURE_DIR)
    size = args.texture_size or C.TEXTURE_SIZE
    needed = [n for n in C.TEXTURE_SETS
              if not os.path.exists(os.path.join(texture_dir, f"{n}.png"))]
    if args.regen_textures or needed:
        names = None if args.regen_textures else needed
        say(args, f"generating textures ({size}px) -> {texture_dir}")
        generate(texture_dir, size, names, guides=True, quiet=args.quiet)

    say(args, "building character")
    BU.purge_scene()
    scene.setup_render()
    scene.setup_world()
    ch = assemble.build(texture_dir, with_rig=not args.no_rig)
    scene.add_camera(ch.collections["root"])
    scene.add_shadow_catcher(ch.collections["set"])

    report(args, ch)

    out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if args.pack:
        bpy.ops.file.pack_all()
        say(args, "packed textures into the .blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    if not args.pack:
        # image paths are stored relative to the .blend, so a file saved
        # outside the repo cannot find textures/generated any more
        bpy.ops.file.make_paths_absolute()
        bpy.ops.wm.save_mainfile(filepath=out)
    say(args, f"saved {out}")

    if args.preview:
        from tools import preview
        preview.setup_render(width=640, height=1100, samples=32)
        paths = preview.render_views(
            args.preview, views=("front", "side", "back", "three_q"),
            prefix="turnaround", width=640, height=1100,
            objects=ch.mesh_objects())
        preview.contact_sheet(paths,
                              os.path.join(args.preview, "turnaround.png"))
        say(args, f"rendered previews -> {args.preview}")
    return 0


def say(args, message):
    if not args.quiet:
        print(f"[build] {message}")


def report(args, ch):
    from character import blendutil as BU, materials as MATS
    if args.quiet:
        return
    supplied = MATS.supplied_map_report()
    if supplied:
        for piece, slots in sorted(supplied.items()):
            print(f"[build]   input maps: {piece:8s} {', '.join(slots)}")
    else:
        print("[build]   input maps: none supplied, using generated "
              "templates (see textures/input/README.md)")
    total = {"verts": 0, "faces": 0}
    for obj in sorted(ch.mesh_objects(), key=lambda o: o.name):
        stats = BU.mesh_stats(obj)
        total["verts"] += stats["verts"]
        total["faces"] += stats["faces"]
        keys = obj.data.shape_keys
        extra = f"  shape keys: {len(keys.key_blocks) - 1}" if keys else ""
        print(f"[build]   {obj.name:22s} {stats['verts']:6d} verts "
              f"{stats['faces']:6d} faces{extra}")
    print(f"[build]   {'TOTAL':22s} {total['verts']:6d} verts "
          f"{total['faces']:6d} faces")
    if ch.rig is not None:
        bones = ch.rig.data.bones
        deform = sum(1 for b in bones if b.use_deform)
        print(f"[build]   rig: {len(bones)} bones ({deform} deform), "
              f"{len(ch.rig.data.collections_all)} bone collections")
        rep = getattr(ch, "report", {})
        for limb, (angle, err) in sorted(rep.get("ik", {}).items()):
            print(f"[build]   IK {limb}: pole angle {angle:7.1f} deg, "
                  f"rest error {err * 1000:.2f} mm")
        print(f"[build]   drivers: {rep.get('shape_drivers', 0)} shape key, "
              f"{rep.get('material_drivers', 0)} material")
        binding = rep.get("binding", {})
        if binding:
            by_method = {}
            for part, method in binding.items():
                by_method.setdefault(method, []).append(part)
            for method, parts in sorted(by_method.items()):
                print(f"[build]   bound by {method}: {', '.join(sorted(parts))}")


if __name__ == "__main__":
    raise SystemExit(main())
