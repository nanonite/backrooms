# Camera-Path Prior (Non-Collider)

## Result

This is a CPU-only harness proxy. It rasterizes the 192 registered #100
camera-centre XZ samples as an assumed floor path at the #100 declared floor
height. It does not measure a floor, derive room boundaries, test a Hunyuan
transform, or produce a runtime collider. Every cell outside the assumed strip
remains unknown. `#135` remains open; this does not establish source-surface
walkability or unblock collision acceptance.

The 5 cm grid uses three explicit total-width hypotheses. The 0.8 m case is
`0.30 m` capsule radius plus `0.10 m` clearance on each side. These widths are
design assumptions, not reconstructed geometry.

| Total width | Support cells | Cell area | 8-connected components | Camera centres within 5 cm | Segment midpoints within 5 cm |
|---:|---:|---:|---:|---:|---:|
| 0.8 m | 5,056 | 12.6400 m2 | 1 | 192 / 192 | 191 / 191 |
| 1.2 m | 7,735 | 19.3375 m2 | 1 | 192 / 192 | 191 / 191 |
| 1.6 m | 10,521 | 26.3025 m2 | 1 | 192 / 192 | 191 / 191 |

The path length is 15.1684 m under the #100 chosen coordinate convention.
Camera and segment coverage are tautological: support is generated directly
from those same samples. These values measure rasterization tolerance only.
The maximum nearest-cell-centre distance is 0.0344 m. There are no unsupported
segment gaps at 0.30 m in the generated strip. These are not independent
alignment residuals or traversal results.

## Controls

A disk centred at registered frame 97 removes support without infill. Its radius
is half the selected width plus 0.15 m, so it crosses the full strip. All three
hole variants split into two 8-connected components. At a 0.30 m nearest-cell
tolerance, camera coverage falls to 185/192, 181/192, and 175/192 for widths
0.8, 1.2, and 1.6 m. Segment-midpoint coverage falls to 185/191, 179/191, and
175/191. Longest consecutive unsupported midpoint gaps are 0.497, 0.991, and
1.327 m. Both frame-97 local lateral queries at `+/-3 m` miss every strip at
0.30 m. No physics traversal was run.

Two local points 3 m to either side of frame 97 miss all three strips at a
0.30 m tolerance. A whole-path 3 m X translation retains 14.1% to 22.4%
coverage because the route folds back near itself. Swapping X/Z retains 20.3%
to 33.9% for the same reason; this is a partial, not perfect, negative. A
doubled-scale path has 0/192 samples within 0.30 m for all widths. Separately,
the #100 manifest validator rejects a doubled declared scale and a mislabeled
up axis.

## Coordinates And Limits

The cameras are sorted as `frame_0001` through `frame_0192` and mapped through
the recorded #100 `corridor_splat` alignment and Nerfstudio dataparser transform.
Their computed bounds match the #100 manifest within `2.7e-15 m`. Each cell's
height is the declared floor height `-1.27099049` in the chosen #100 scale
convention. That convention is not surveyed metric scale. The provisional
Hunyuan scale `1.558285848` is not used; Hunyuan registration remains
`registration_accepted=false`.

The source-mask experiment still has 0/192 camera centres and 0/191 adjacent
segment midpoints supported within 0.30 m. This camera-path prior fills that
gap only by assuming support under the camera path. It provides no evidence
that a physical floor exists there. It also ignores camera height, capsule
collisions with walls, slopes, steps, openings, and actual source/Hunyuan mesh
surfaces.

No Avian/Tnua test was added. Official pinned references were checked:
[Avian 0.6 docs](https://docs.rs/avian3d/0.6.0/avian3d/),
[Tnua 0.31 docs](https://docs.rs/bevy-tnua/0.31.0/bevy_tnua/), and the
[Tnua Avian 0.11.0 release](https://github.com/idanarye/bevy-tnua/releases/tag/avian-v0.11.0),
which records its Avian 0.6 upgrade. The physics crates are not present in this
worktree's lockfile/cache. More importantly, traversal on this assumed strip
would only test the controller against a support route authored from its own
input, not validate observed geometry. The 192-frame mask and Hunyuan mesh
experiments remain separate and unchanged.

## Artifacts And Verification

- `build_camera_path_prior.py` reproduces the report and grids from the pinned #100 inputs.
- `camera_path_prior_non_collider.npz` stores the three support grids and three hole controls.
- `registered_camera_centres_godot_world.csv` stores the ordered mapped camera centres.
- `CAMERA_PATH_PRIOR_NON_COLLIDER.json` records dimensions, tolerances, controls, hashes, and runtime.
- No OBJ, GLB, `collision.glb`, Bevy runtime asset, or production contract is emitted.

Verification from the Track A worktree:

```sh
PYTHONPATH=godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_prior_non_collider \
  pytest -q godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_prior_non_collider
PYTHONPATH=godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto \
  python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_prior_non_collider/build_camera_path_prior.py
ruff check godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_prior_non_collider
ruff format --check godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_prior_non_collider
```

The focused suite has 7 passing CPU tests. The latest builder run took 0.55 s
and reported 174,469,120 bytes peak RSS; an earlier process run reported
930,975,744 bytes, so retain the larger value as the conservative observation.
No GPU, rendering, Hunyuan inference, or physics simulation was used.
