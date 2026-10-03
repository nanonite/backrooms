# Corridor splat asset (C2 / #74) and its alignment contract

Our REAL corridor Gaussian splat, rendered by `res://scenes/corridor_splat.tscn`
and `res://scenes/corridor.tscn`.

Expected local file for the scenes:

```text
res://assets/corridor_splat/corridor.ply
```

The `.ply` is large (45 MB) and is gitignored (same policy as the GDGS demo
asset). It stays local; this README and `alignment_manifest.json` are tracked.

## The contract: one mapping, applied exactly once

`alignment_manifest.json` is the single source of truth. It records, for this
scene:

- **which axis is up** in the exported frame, and with which sign
- the **handedness** of that frame and of Godot's world
- how many reconstruction units make a **metre**, and *why*
- every transform the GDGS toolchain applies **on its own**, so none is applied
  twice and none is missed
- the resulting PLY -> Godot-world mapping, landmarks, and the collision room
- **where the reconstruction cameras land** in world metres

That last one is the only record not derived from the room itself, so it is what
stops the contract from merely agreeing with itself: the splat node, the collider
and the spawn are all hand-authored in `.tscn` files, while the camera path comes
from the COLMAP model through the nerfstudio dataparser transform. Requiring the
cameras to land inside the room the splat implies closes the loop back to the
reconstruction the splat was actually trained against.

`scripts/splat_alignment.gd` reads it at runtime, `scripts/verify_alignment.gd`
proves both scenes honour it after runtime initialisation, and
`scripts/test_splat_alignment.gd` unit-tests the reader itself.

Regenerate after a re-train, and review the diff:

```bash
python3 scripts/splat_pipeline/measure_splat_frame.py \
    --ply godot_walk/assets/corridor_splat/corridor.ply \
    --colmap-model data/scenes/corridor_travel/sparse/0 \
    --dataparser-transforms outputs/corridor_travel_v1/splatfacto/<run>/dataparser_transforms.json \
    --scene-id corridor_splat \
    --asset-path res://assets/corridor_splat/corridor.ply \
    --source-path exports/corridor_travel_v1/splat.ply \
    --video data/scenes/corridor_travel/video.mp4 \
    --footage-kind synthetic --target-clear-height 2.40 \
    --out godot_walk/assets/corridor_splat/alignment_manifest.json
```

## What the frame actually is

| Property | Value | How it was established |
|---|---|---|
| Source | nerfstudio 1.1.5 export, 182,569 splats, SH degree 3 | PLY header, md5 `2f6c2fd5…` |
| Up axis | **+Z** of the exported frame | mean registered-camera up axis from `data/scenes/corridor_travel/sparse/0` (192 images), mapped through the nerfstudio dataparser transform; 99.99% on one axis |
| Handedness | right-handed | COLMAP and Godot are both right-handed; the mapping is verified det = +1 |
| Corridor axis | Y of the exported frame | measured, not assumed |
| Units | arbitrary reconstruction units | COLMAP/nerfstudio apply a similarity normalisation |
| Metres per unit | **5.128384** | see below |

The PLY header comment says `Vertical Axis: z` and the contract confirms it
numerically. Note the exporter's comment is *not* what the contract relies on —
GDGS ignores comments entirely, and an earlier README claimed Y-up on the
strength of the comment alone. That claim was wrong.

### Why the up axis needed measuring

The old story (`WALKABLE_SPLAT_PLAN.md` §Defect 1) was that `corridor_splat.tscn`
carried a 180° Z rotation and `corridor.tscn` carried identity. That is stale.
Both scenes serialised the same identity transform, and GDGS applied the same
implicit -180° Z correction to both in `_enter_tree`.

That correction is a Z-axis flip. **It leaves the up axis alone**, so it can
never make a z-up splat stand up in Godot's y-up world. That is the whole reason
the "floor axis doesn't match PLY Y" mystery (`LESSONS_LEARNED.md` §5.2) was
never solved: nobody was looking for a Z-to-Y swap, because a Z flip looks
plausible and does nothing about the real problem.

Equal serialised transforms are therefore not evidence of agreement. Only equal
*effective world mapping* is, and that is what the verifier checks.

### The mapping

```
world_x =  5.128384 * frame_x
world_y =  5.128384 * frame_z      <- the up axis
world_z = -5.128384 * frame_y
```

As a Godot node transform (rotation × uniform scale, **zero translation**):

```
Transform3D(0.0, 5.1283836, 0.0, 0.0, 0.0, 5.1283836, 5.1283836, 0.0, 0.0, 0.0, 0.0, 0.0)
```

A pure rotation, so Gaussian orientations, covariances and extents all stay
correct under the renderer's `M3 * covariance * M3^T`. **Nothing is baked** into
the PLY; if you ever do bake a transform, orientations and covariances must move
with the centres.

**The zero translation is load-bearing.** The GDGS resource builder already
subtracts the mean Gaussian centre at import
(`addons/gdgs/importers/builders/gaussian_resource_builder.gd`), so the renderer
works in centroid-relative space. Reapplying the centroid translation on the node
would double-subtract it and shift the room — still imports, still renders, easy
to miss by eye, caught numerically.

## Metric scale

The scale is a **chosen** value, not a measurement, and the manifest says so:

- Floor-to-ceiling separation is measured directly from the splat: two sharp
  density modes at frame Z −0.2287 and +0.2459, i.e. **0.46798 ± 0.00937
  reconstruction units**, re-measured independently across 12 corridor stations.
- The spread (0.00937) is the honest uncertainty: 12 independent slabs, not one
  sheet's thickness.
- The footage is **synthetic** (Veo 3.1 via OpenRouter, `LESSONS_LEARNED.md` §1).
  Generated frames contain no real-world reference, so metres cannot be measured.
  The corridor is instead *declared* to have a **2.40 m** clear height — a normal
  institutional corridor, and close to what the geometry itself suggests.
- **5.128384 m per unit = 2.40 / 0.46798.**

For real footage, `--footage-kind real --measured-reference <metres>` divides a
taped or otherwise known distance by the reconstructed height instead, and the
manifest records `kind: "measured_reference"`.

### Recorded as applied zero times

The GDGS `-180° Z` correction is **neutralised**, not merely absent: scenes give
the splat node an explicit non-identity basis so the addon's identity test cannot
fire. `verify_alignment.gd` asserts both the effective mapping and the absence of
that correction, so a future addon change to the rule fails loudly instead of
silently re-rotating the room.

### Rejected scales

- **0.800977** (`data/scenes/corridor_straight/scene_transform.txt`) — computed as
  2.0 m ÷ the Z extent of the retired COLMAP-dense Poisson mesh. That mesh is a
  different asset from a reconstruction path proven non-viable for these captures
  (`PLAN_pipeline_visual_feedback.md`), and it is not the splat any scene loads.
  Reusing it imports an assumption with no evidence behind it. **Not reused.**
- **1.0** (loading the PLY unscaled) — COLMAP normalises a similarity transform,
  so one reconstruction unit is not one metre.

## Automatic transforms the addon applies

Recorded in full in the manifest's `automatic_transforms`, each with the stage,
the source file, and whether the scene neutralises it:

| Stage | Source | What it does | Applied here |
|---|---|---|---|
| import | `standard_ply_decoder.gd` | stores centres, `exp(scale_N)`, `(rot_1..3, rot_0)` quaternions verbatim — no axis swap, no unit change | once |
| import | `gaussian_resource_builder.gd` | subtracts the mean Gaussian centre; translation only, so covariances stay valid | once (accounted for) |
| node `_enter_tree` | `gaussian_splat_node.gd:_apply_default_orientation_if_needed` | right-multiplies by -180° Z **when the node basis is identity** | **zero times** |
| render | `gaussian_scene_registry.gd` + `gsplat_projection.glsl` | `world = M * centre`, `covariance_world = M3 * cov * M3^T` | once |

The node correction is neutralised by giving every splat node this contract's
explicit non-identity basis, so the identity test cannot fire. The verifier
asserts the effective transform equals the manifest, so a future addon change to
that rule fails loudly instead of silently re-rotating the room.

## Verification

Numerical, headless, no GPU needed:

```bash
cd godot_walk && godot4 --headless --script res://scripts/verify_alignment.gd
```

It checks, after runtime initialisation:

1. the manifest is self-consistent, and its up axis maps to Godot +Y with det = +1
2. each scene's **effective** mapping equals the contract
3. GDGS' implicit correction fired in neither scene
4. both scenes agree on the effective mapping
5. landmarks land inside the observed room, floor below ceiling, and the
   floor→ceiling distance equals the declared 2.40 m within tolerance
6. the **rendered splat AABB matches the contract's predicted value numerically**,
   which catches a stale imported `.res` cache or a scene pointing at a different PLY
7. the floor landmark is the lowest point of the observed room and the ceiling the
   highest — the numeric form of "not on its side"
8. the **192 reconstruction cameras** land inside the calibrated room and at a
   walking eye height (1.153 m above the floor)
9. `PlayerSpawn` sits inside the room, 0.5 m above the floor, where the contract says

The reader itself is unit-tested, so the checks above are known to be able to
fail. This is not ceremony: the declared `GDGS_DEFAULT_CORRECTION` shipped with
its z axis as `(1, 0, 0)`, giving determinant 0 and building a matrix no rotation
can equal. That made `gdgs_default_correction_applied()` unsatisfiable, so check 3
above — "the addon did not quietly rotate the room" — was green regardless of
what the addon did. The test now asserts both that the constant is a proper
rotation and that the predicate fires on a basis that really does carry it:

```bash
cd godot_walk && godot4 --headless --script res://scripts/test_splat_alignment.gd
```

The Python half of the contract is covered by
`scripts/splat_pipeline/tests/test_splat_frame.py` (87 tests).

Real-GPU visual evidence (screenshots, non-blank, on the Vulkan/Forward+ path) is
still required, per `LESSONS_LEARNED.md` §5.1 — it is necessary but not
sufficient, and the task explicitly does not accept it alone:

```bash
GODOT_BIN=godot4 godot_walk/tools/verify_corridor_splat.sh
```

Re-run on this change: RTX 4070 Ti, Vulkan 1.4.329, Forward+. The rendered splat
AABB reported by the capture is
`pos=(-97.7875, -62.1061, -101.8175) size=(139.4696, 97.0061, 134.5244)`, which
is the manifest's predicted `full_min`/`full_max` to four decimals — so the thing
on screen is the thing the contract describes, not a differently-scaled or
differently-oriented asset.

The `player_pov` frame shows the corridor upright: floor below, ceiling and its
light band above, walls vertical, which agrees with check 7. The fringing at the
frame edges is far-field floater, not geometry, and the numeric checks above
remain the evidence of record.

## Known limits

- **The walls were not measured.** No horizontal axis shows two surfaces above
  the 8× density-contrast threshold, so the room's horizontal extents are
  *observation bounds* from the camera-path window, not measured wall planes.
  The manifest records this as `capture.walls_measured: false`. Do not treat the
  room's footprint as a measurement.
- **The scale is chosen, not measured** (synthetic footage). Re-decide it when
  real footage lands.
- One clip is one room's viewing volume (`WALKABLE_SPLAT_PLAN.md`); the splat is
  only good near its training trajectory.

## Downstream

`#84` (fit_collider.py) and `#85` consume this contract: they should generate
collision geometry from the manifest's landmarks and bounds rather than from PLY
percentiles, and their output must satisfy the same verifier.