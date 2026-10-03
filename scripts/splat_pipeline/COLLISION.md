# Collision geometry from Gaussian splats — measured results

Task #84. Every number below was produced by running the pinned tool on this
host; nothing here is quoted from documentation without a measurement behind it.
The machine-readable form of the same run is
`scripts/splat_pipeline/collision_benchmark.json` (synthetic corridor) and
`scripts/splat_pipeline/collision_benchmark_gdgs_demo.json` (the second input).

```bash
cd scripts/splat_pipeline && npm install @playcanvas/splat-transform@3.9.0
SPLAT_TRANSFORM_NODE_MODULES=$PWD/node_modules python3 generate_collision.py \
    --manifest ../../godot_walk/assets/corridor_splat/alignment_manifest.json \
    --ply ../../exports/corridor_travel_v1/splat.ply \
    --out ../../outputs/collision/corridor_splat \
    --report collision_benchmark.json
```

Exit status: `0` all checks pass, `1` a check failed or the run was not
validatable, `2` the tool is unavailable on this host, `3` an input is missing.

## Verdict

**FAIL on the synthetic `corridor_travel` fixture, on one criterion.**
Nine of ten checks pass. `walkway_covers_camera_path` fails: 153 of the 192
reconstruction camera positions — **79.7 %** — are inside solid collision 1.00 m
above the floor. Floor support is perfect (192/192 have collision floor
directly beneath them) and the mesh is watertight with correct winding, so this
is not a broken mesh; the generated walls sit where somebody walked.

Attribution, measured: the splat's own column classifier finds obstruction-band
surface at **34.9 %** of camera columns, and the collision is solid at
**79.7 %**. 60 columns are obstructed in both, 7 in the splat only, 69 in the
collision only. The collision over-blocks the reconstruction by roughly 2.3×, and
the extra blocking is the exterior fill's dilation closing space the cameras
demonstrated was open. The alignment manifest already records why this capture is
weak — `walls_measured: false`, with no horizontal axis resolving two surfaces
above the 8× density-contrast threshold — so the honest statement is that the
reconstruction does not observe this corridor's walls, and no collision stage can
recover geometry that was never reconstructed.

## Tool benchmark (pinned)

| | |
|---|---|
| package | `@playcanvas/splat-transform@3.9.0` (pin in `splat_transform_cli.PINNED_VERSION`) |
| GPU adapters (`--list-gpus`) | `NVIDIA GeForce RTX 4070 Ti`, `llvmpipe (LLVM 20.1.2, 256 bits)` |
| input | `exports/corridor_travel_v1/splat.ply`, md5 `2f6c2fd5417ffe771ef4147e369d80c5`, 182 569 Gaussians |
| elapsed | **3.3 s** (2.18–3.29 s across repeats) |
| peak CPU / GPU | **519 MiB** CPU / **33 MiB** GPU |
| after `--filter-cluster` | 95 700 Gaussians (302 of 547 coarse blocks kept, 86 900 removed) |
| collision mesh | **10 178 triangles**, 5 091 vertices, 183 896 B |
| voxel output | 184 × 192 × 60 voxels at 0.05 m, tree depth 6, 11 679 nodes, 74 244 B |

### GPU-only, and available here

`.voxel.json` output, `--collision-mesh`, `--filter-cluster` and
`--filter-floaters` all require WebGPU, and `-g cpu` refuses them. This **is not**
blocked on this host: the tool's own `--list-gpus` enumerates the RTX 4070 Ti.

Note the discrepancy with #89, which recorded WebGPU as **FAIL**
(`ModuleNotFoundError: No module named 'wgpu'`). Both are right about different
things. The Python `wgpu` module is absent, so a Python-side probe cannot open an
adapter; `splat-transform` reaches Vulkan through Node's own bindings and finds
one. `splat_transform_cli.probe_adapters` uses the tool's probe, because that is
the one that decides whether collision generation is possible, and it records the
adapters rather than a boolean so the two probes stay distinguishable.

### Output frame — measured, not documented

`.voxel.json`, `.voxel.bin` and `.collision.glb` are written in the **PlayCanvas
engine frame**: the source PLY frame rotated 180° about z, `(x, y, z) → (−x, −y, z)`.
Two independent measurements:

1. A one-Gaussian probe PLY written at `(1, 2, 3)` produced `gridBounds` around
   `(-1.2, -2.2, 2.8)`.
2. A 300-Gaussian opaque probe blob at PLY `(1, 2, 3)`: `--seed-pos 1,2,3` is
   reported `unoccupied; resolved to nearest`, while `--seed-pos -1,-2,3` is
   accepted. The tool reads a **single** `--seed-pos` in this frame for
   `--filter-cluster`, `--voxel-external-fill` and `--voxel-carve` alike, so one
   seed value is correct for every stage — but it is *not* the PLY coordinate.

Verified independently at scale: the solid-voxel centroid inside a fixed box is
`(0.232, −0.220, 0.019)` reconstruction units where the splat centroid is
`(−0.211, 0.214, 0.032)` — x and y negated, z unchanged.

The collision mesh carries no `NORMAL` attribute; only `POSITION` and
`indices`. Winding is therefore the only normal information available, and
`traversability._check_mesh_normals` measures it against the voxel field:
**8 324 of 10 178 triangles (81.8 %)** face out of the solid into navigable space.
Measured on floor faces specifically, 90.8 % point up; on ceiling faces, 87.5 %
point down. Both are the side the player is on.

### Determinism

Two runs of the identical command produced **byte-identical** `.voxel.json`,
`.voxel.bin` and `.collision.glb` (md5 recorded in the report). None of these
stages samples, so there is no seed to record and no tolerance to define.

## Settings, and the raw-unit conversion

Every option is in **calibrated metres**, because the input splat is scaled in
place by the contract's `metres_per_unit` before voxelizing.

| setting | value | why |
|---|---|---|
| `--voxel-size` | **0.05 m** | 0.00974966 PLY units; resolves a doorway reveal |
| `--voxel-opacity` | 0.1 | tool default |
| `--filter-cluster` | `0.25, 0.999, 0.1` | 0.25 m, not the tool's 1.0 *world unit* default |
| `--voxel-external-fill` | **1.2 m** | measured threshold, below |
| `--voxel-carve` | `1.25, 0.35` m | player capsule 1.2 × 0.3 + 0.05 m margin |
| `--collision-mesh` | `smooth` | 10 178 triangles; `faces` emits two per exposed voxel face |
| `--seed-pos` | `0.704, −0.326, −0.528` | engine frame, contract spawn + capsule half-height |

**Raw 0.15 is not 0.15 m.** One reconstruction unit on this scene is
**5.1283838 m**. A 5 cm voxel is `0.00974966` raw units; the tool's own defaults,
taken unscaled, would be 5.128× too small — a plausible-looking mesh that blocks
a player three metres wide.

**Bounds.** `gridBounds` `[-2.2, −6.0, −1.4] .. [7.0, 3.6, 1.6]` m in the engine
frame, i.e. 9.2 × 9.6 × 3.0 m, against the contract's observed room of
18.84 × 14.39 × 2.40 m. The generated collision covers **less than half** the
observed footprint in each horizontal axis. That is consistent with the failed
camera-path check and with `walls_measured: false`.

### `--voxel-external-fill` is a cliff, measured

| fill (m) | stages | navigable volume | clear height | outcome |
|---|---|---|---|---|
| 0.4 | fill **skipped** | 1 187 m³ | 6.80 m | `seed reachable from outside` — total leak; the room holds 650 m³ |
| 0.6 | carve **skipped** | 71.6 m³ | 4.70 m | `seed blocked after dilation, no free cell within 26 voxels` |
| 0.8 | carve **skipped** | 83.5 m³ | 4.70 m | same |
| 1.0 | both ran | 102.1 m³ | 2.50 m | sealed |
| 1.2 | both ran | 106.2 m³ | 2.50 m | sealed — **chosen** |
| 1.6 | both ran | 111.7 m³ | 2.50 m | sealed |
| 3.2 | both ran | 111.7 m³ | 2.50 m | saturated |

1.2 m is the smallest sealed value with margin over the threshold. The tool's own
default of 1.6 is in world units and is two thirds of this room's 2.40 m clear
height. Two further measured facts:

* `--filter-cluster` is **mandatory**, not an optimisation. Without it the floaters
  (reaching 1.36 km) make the mutable grid 30.7 B blocks and the run fails with
  `Voxel mutation requires 30.7B blocks, exceeding the 32-bit mutable-grid limit`.
* `--filter-cluster` resolution is load-bearing: at the tool's default 1.0 m the
  grid is 288 × 624 × 1364 voxels for a 2.4 m room, and at 0.10 m the carve seed
  is buried so the run produces **0 triangles**. 0.25 m works.

## Acceptance checks

Ten checks in `traversability.py`; thresholds are named constants with their
reason inline. Two families: self-consistency (a mesh can satisfy all of it and
still describe a room that was never observed) and agreement with the
reconstruction and the contract.

| check | result | measured |
|---|---|---|
| `stages_applied` | PASS | exterior fill and carve both ran |
| `room_not_filled` | PASS | 106.2 m³ navigable = 16.3 % of the 650 m³ room; clear height 2.50 m vs 2.40 m contracted |
| `floor_supported` | PASS | collision floor under **192/192** camera positions |
| `walkway_covers_camera_path` | **FAIL** | **39/192 (20.3 %)** navigable at 1.00 m; need 90 % |
| `walls_block` | PASS | 383 of 441 splat-obstructed columns solid (**86.8 %** recall) |
| `openings_preserved` | PASS | 757 of 815 navigable columns are splat-open (**92.9 %** precision); 19.1 % of splat-open columns survived |
| `capsule_clearance` | PASS | 0 of 48 capsule surface samples solid at the spawn; 1.800 m clear above it, need 1.250 m |
| `mesh_watertight` | PASS | 0 boundary edges, 0 non-manifold, 15 267 shared by two; 8 degenerate triangles |
| `mesh_normals_face_walkable` | PASS | 8 324/10 178 (81.8 %) face navigable; signed volume +158.7 m³ |
| `within_budget` | PASS | 10 178 ≤ 200 000 triangles; 519 MiB ≤ 4 GiB CPU, 33 MiB ≤ 2 GiB GPU |

The **clear height is 2.50 m against a contracted 2.40 m**. That is not a
defect: the carve re-inflates the navigable region by its own capsule, so a
measured region is the room plus roughly the capsule half-height plus a voxel.
The consequence for #85 is that **the navigable bounds must not be used as the
clear height** — the contract's floor and ceiling are the only statement of it.

## What #85 gets

`collision_benchmark.json` → `expected_geometry`:

* collision node `Transform3D` basis = the contract's **rotation** composed with
  the 180° z engine-frame rotation, with **no scale**; translation **non-zero**
  (`-0.977009, -0.117991, 3.591775` m) because Godot's glTF importer applies no
  centroid subtraction, unlike the GDGS splat builder. Reusing the splat node's
  zero translation would place the collision one room-length away.

  The first record of this field carried `metres_per_unit` (5.128×) in the basis.
  It was wrong: `build_argv` hands the tool a splat the contract has already
  multiplied by `metres_per_unit`, so the engine frame it writes is already metric
  and a second scale puts the generated floor metres away from the room. #85 found
  it because `collision_params.py` held two mappings that disagreed —
  `collision_node_transform` scaled, `engine_frame_to_world` did not — and only
  the point mapping had ever been cross-checked. The report has been re-emitted
  with the corrected basis and a `correction` note; every check, every
  measurement and the verdict are unchanged, and the GLB is byte-identical.

* blocked and open floor-plan column runs at 1.00 m above the floor, 0.25 m
  columns, origin `(-10.069, -4.306)` m, 76 × 58 cells. Expressed as spans rather
  than as boxes because the manifest records `walls_measured: false` — **no wall
  offset can be quoted for this capture**, only which columns block.
* player capsule 0.3 m radius / 1.2 m height; carve capsule 0.35 / 1.25 m.

#85 consumed all of it: see `godot_walk/assets/corridor_splat/TRAVERSAL.md` and
`scripts/splat_pipeline/traversal_plan.py`, which turn the geometry above into a
walkable route, two blocking probes, a spawn on the collision's own floor, and
the tolerances `godot_walk/scripts/verify_traversal.gd` checks them against. The
`walkway_covers_camera_path` FAIL above is carried into the traversal manifest and
printed by the walk test rather than dropped: the walk measures the region this
collision does leave navigable, which is not the same claim as reconstructing the
route the cameras walked.

## Second input — the real-room capture

`godot_walk/assets/gdgs_demo/demo.compressed.ply`, 271 123 Gaussians in PlayCanvas
**compressed** PLY form. Recorded in `collision_benchmark_gdgs_demo.json` with
`--without-contract`, which names the report after the splat rather than after
the borrowed manifest.

The tool **accepts the compressed input** and runs: **2.28 s**, 644 MiB CPU,
48 MiB GPU, 271 000 → 125 000 Gaussians after the cluster filter. It is **not
validated**, for two measured reasons:

1. **No alignment contract exists for this asset.** There is no calibrated frame,
   no camera path and no metric scale, so floor continuity, wall blocking,
   doorway preservation and capsule clearance cannot be scored. That is the
   blocker for the real-capture half of this task's acceptance, and it is #83's
   output for a new capture, not something this stage can substitute for. The
   manifest supplied on the command line is the corridor's; its scale, frame and
   seed say nothing about this splat, which is why the report records them as
   borrowed rather than as this scene's.
2. **The shell does not seal at any setting tried.** With the corridor's
   `--voxel-external-fill 1.2`, the tool reports `seed reachable from outside,
   skipping exterior fill` and `seed outside grid, skipping carve`, and emits
   **355 254 triangles** over 557.9 m³ of navigable space in an 8 × 9 × 8 m grid —
   the whole grid, i.e. a total leak, with **51 non-manifold edges**.
   Sweeping the fill to 2.4 m and 3.2 m does seal it, but the dilation is applied
   on all three axes and the room is only 5.36 × 6.31 × 5.34 m, so the grid is
   consumed and the carve is skipped again: 32 200 triangles. With
   `--voxel-carve` disabled the run produces 9 500 triangles with 0 boundary
   edges, 2 non-manifold edges and a signed volume of 18.1 m³ — a small closed
   shell, still unscored.

   Two navigation stages skipped in one run is the case this stage exists to
   catch: both leave a valid-looking collision file behind, and only the flags
   recorded under `blocking_stage` distinguish "collision generated" from
   "collision generated from nothing".

This is a **bounded, evidence-backed unsupported outcome for that asset**, not a
fallback claim. The synthetic corridor and the demo capture are separate fidelity
classes and the demo is not validated.

## Reproducing and re-checking

```bash
cd scripts/splat_pipeline
npm install @playcanvas/splat-transform@3.9.0
python3 -m pytest tests/test_collision.py -q      # 36 tests, no GPU needed
```

The tests build their fixtures to the published formats, so they cannot tell
whether the pinned tool still accepts the flags `build_argv` emits. That is what
the recorded benchmark is for; a drift between the two is a reason to re-run it,
not to relax a test.