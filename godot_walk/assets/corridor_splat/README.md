# Corridor splat asset (C2 / #74)

Our REAL corridor Gaussian splat, used by `res://scenes/corridor_splat.tscn` to
measure the splat's true orientation and metric scale on a desktop GPU session.

Expected local file for the scene:

```text
res://assets/corridor_splat/corridor.ply
```

The `.ply` is large (~176 MB) and is gitignored (same policy as the GDGS demo
asset). It stays local; only this README is tracked.

## How to (re)create the local file

Copy the source splat exported by Brush into this directory as `corridor.ply`:

```bash
cp data/scenes/corridor_straight/scene.ply \
   godot_walk/assets/corridor_splat/corridor.ply
```

## How GDGS ingests it

The splat is raw 3DGS binary-little-endian PLY (746,100 splats, SH degree 3,
Y-up, `comment Vertical axis: y`). The GDGS addon `EditorImportPlugin`
(`gaussian.splat.importer`) recognizes the `.ply` extension and routes it to the
`StandardPlyDecoder` automatically on project import — **no manual convert /
compress step is required**. (The demo's `.compressed.ply` only differs in that
it carries `packed_*` properties that trigger the `CompressedPlyDecoder`; raw
3DGS PLYs like ours use the standard decoder.) Godot writes the imported
`Resource` into `.godot/imported/` on first project load.

## Verification

Run the renderer proof from a real desktop GPU session, not headless or xvfb:

```bash
GODOT_BIN=godot4 godot_walk/tools/verify_corridor_splat.sh
```

The script renders three views and the screenshot harness prints `SPLAT_AABB:`
lines to stdout/log giving each splat node's world-space position + size, from
which orientation and metric scale can be read off.
