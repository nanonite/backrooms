# Issue #60: Stage-M footprint fix

## Verdict

The bad Godot corridor asset came from the Jun 10 Stage-M run that used
`data/scenes/corridor_straight/mesh_raw.ply`. That mesh is a thin slab, so the
previous `blender_cleanup_mesh.py` height-only check accepted a 2m-tall fragment
with a sub-meter footprint.

The local capture/reconstruction data is not generally broken. The older
`mesh_export.obj` and the raw `scene.ply` both have corridor-sized footprints.
I regenerated the Godot visual mesh from `mesh_export.obj` using the fixed
cleanup script.

## Intermediate Measurements

`data/scenes/corridor_straight/mesh_export.obj` before cleanup:

- Vertices: 110,765
- Triangulated faces: 222,744
- Raw bbox dimensions: `2.7161 x 3.0802 x 3.8678`
- Connected components: 175
- Largest component: 104,738 vertices, 211,477 faces, bbox `2.3516 x 2.4970 x 2.9210`
- After removing components below 50 faces: 22 kept components, 109,353 vertices,
  220,553 faces, bbox `2.7161 x 2.4970 x 3.4504`

`data/scenes/corridor_straight/mesh_raw.ply` before cleanup:

- Vertices: 1,283,637
- Faces: 2,576,982
- Blender-imported bbox dimensions: `2.0234 x 0.7309 x 2.9311`
- This is the bad thin-slab source used by the previous Stage-M run.

`data/scenes/corridor_straight/scene.ply` point cloud:

- Vertices: 746,100
- Bbox dimensions: `2.9443 x 3.1626 x 4.0518`
- This has a full footprint, so the capture/point-cloud data is not the stopping
  condition from branch (c).

## Branch Applied

Branch (a) with an input-selection diagnosis: a plausible corridor-footprint mesh
already existed locally as `mesh_export.obj`, while the actual Stage-M input
recorded in `blender_cleanup.log` was `mesh_raw.ply`. The Stage-M script also
needed guards so the bad thin-slab path cannot pass again.

## Changes

`scripts/splat_pipeline/blender_cleanup_mesh.py` now:

- Removes loose components below `--min-component-faces` before scale estimation
  and export.
- Joins the kept components back into one mesh before material/UV/export work.
- Adds `--min-footprint` with a default of `1.5m`.
- Re-imports the exported GLB and validates both height and horizontal footprint.
- Fails if either horizontal extent is below the minimum, which catches the old
  `1.38m x 0.50m` broken asset shape.

`godot_walk/.gitignore` now ignores nested `.exo/` runtime state.

## Regenerated Godot Asset

Regeneration command:

```bash
blender --background \
  --python scripts/splat_pipeline/blender_cleanup_mesh.py -- \
  --scene-dir /home/user/backrooms-workspace/data/scenes/corridor_straight \
  --textures-dir /home/user/backrooms-workspace/data/textures \
  --input-mesh /home/user/backrooms-workspace/data/scenes/corridor_straight/mesh_export.obj \
  --target-tris 500000 \
  --doorway-height 2.0 \
  --min-footprint 1.5
```

Relevant Blender output:

- Removed 144 floating fragments; kept 220,411 faces.
- Cleaned bounds: `X=2.716, Y=3.450, Z=2.497`
- Computed scale factor: `0.8010`
- Exported `scene.glb` size: 13.8 MB
- Re-imported bounds check: `X=2.176, Y=2.764, Z height=2.000`
- Footprint guard passed.

The regenerated files were copied to `godot_walk/assets/corridor_straight/`:

- `scene.glb`: 14,499,428 bytes
- `scene_transform.txt`: `scale: 0.800977`

Direct GLB measurement after copying:

- Vertices: 269,643
- Triangles: 221,881
- GLB dimensions: `2.1756 x 2.0000 x 2.7637`

## Verification

- `python -m py_compile scripts/splat_pipeline/blender_cleanup_mesh.py` passed.
- Synthetic old-bbox guard demo failed as intended:
  `footprint 1.380 x 0.500m is below 1.5m minimum`.
- `cd godot_walk && godot4 --headless --import .` exited 0 and reimported
  `scene.glb` successfully.
- `godot_walk/.exo/` is now ignored by `godot_walk/.gitignore` and no longer
  appears in `git status --short`.

## Human Follow-Up

Re-run `WALKTEST.md` in Godot. The asset now has a corridor-sized footprint, but
visual correctness still requires human inspection in the editor/game view.
