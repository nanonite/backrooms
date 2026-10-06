# Improve synthetic Backrooms PoC visual quality at PSX scale (#100)

Real-GPU, forward/reverse, before/after evidence for a bounded cleanup of the
corridor splat plus an optional PSX presentation pass. Everything here is on the
host in `ENVIRONMENT.md`; exact commands are in `COMMANDS.md`.

## What was wrong, quantified

Measured against the #83 contract before changing anything:

| Quantity | Source `corridor.ply` |
|---|---|
| splats | 182,569 |
| inside the contract's observed room | 78,892 (**43.2%**) |
| outside it | 103,677 (56.8%) |
| opacity of the outside set (median / p90) | **0.995** / 0.99998 |
| largest Gaussian extent | 47.0 raw units = **241 m** |
| rendered full-cloud AABB | **139.47 x 97.01 x 134.52 m** |
| observed room | 18.84 x 2.40 x 14.39 m |

So the haze is not faint: the floaters are essentially opaque, which is why the
**existing compositor `alpha_cutoff` cannot remove them** (tested first, per the
brief). They are removed by *where they are*. The 139 m AABB is an artifact
clue, not a room boundary, and was not used as a crop.

## The cleanup

`scripts/splat_pipeline/clean_splat.py` (pure logic in `splat_cleanup.py`,
unit-tested) writes a filtered derivative and a report. The source PLY is
preserved. Shipped run:

```
margin 0.5 m, max extent 0.30 m, min opacity 0.0 (disabled)
source=182569 kept=124564 removed=58005
removed per stage: bounds=56437, extent=1568, opacity=0
kept AABB: 19.83 x 3.40 x 15.39 m
node_translation_world=(0.2404, 0.0082, 1.5605) m
```

Recorded in `corridor_clean.report.json`: source md5/sha256, output md5/sha256,
deterministic parameters, per-stage removed counts, kept bounds, and the node
translation.

**The centroid trap, handled explicitly.** GDGS subtracts the mean of the loaded
PLY at import, and the contract's node translation is zero because that mean is
the source centroid. Filtering changes the mean, so the presentation node must
add `M*(centroid_filtered - centroid_source)` or the room shifts 1.56 m in Z
while still importing and rendering. `corridor_psx.tscn` carries that
translation and `test_psx_scene.gd` proves the resulting world mapping equals
the source contract. The world is **not** moved: kept splats keep their world
positions; collision, SafetyNet, spawn and player are byte-for-byte the accepted
`corridor.tscn` values, asserted by the same test.

## Before / after (real Vulkan GPU, 1280x720, identical camera poses)

PNGs under `screenshots/{before,after,after_no_psx}/`.

* `player_pov` / `player_pov_reverse` are the #74/#91 room-extreme poses,
  unchanged, so before/after is strictly comparable.
* `spawn_pov` / `spawn_pov_reverse` were added to the harness: the true
  first-person view from the contract's `PlayerSpawn` at eye height.

Honest visible differences:

| View | Before | After |
|---|---|---|
| `player_pov` (room extreme) | room visible but drowned in yellow-green far-field haze; foreground fringing | room readable against a **black** background; far-field haze gone; foreground floaters remain |
| `player_pov_reverse` (room extreme) | almost fully obscured by near-field floaters | still almost fully obscured — see limitation below |
| `spawn_pov` (true player view) | room readable, heavy iridescent floaters right/ceiling | clearly readable room; corridor to the right readable; PSX banding/pixel grid |
| `spawn_pov_reverse` (true player view) | **readable already** — left wall, receding columns, ceiling light strips and patterned floor, under a yellow far-field haze with ceiling/left-edge floaters | still readable; the yellow far-field haze is replaced by black gaps and the left-edge/ceiling floaters remain — a modest gain for this pose |

Only the room-extreme `player_pov` changes from "drowned" to "readable"; the
`spawn_pov` forward view improves from "readable but busy" to "clean", while the
two reverse poses stay limited. The strongest, most defensible claim is the
forward room-extreme view: the far-field haze that covered the room is removed
and the background is black instead of hazy. This is a material reduction, not a
clean plate.

**Limitation, stated plainly.** `player_pov_reverse` (the room-extreme pose)
stands ~4 m beyond the reconstruction camera path (`x -5.45..4.15`; the pose is
at `x≈8.27`), i.e. in a region the capture never observed. No cleanup of a
single clip invents geometry there, so that pose stays floater-dominated. The
`spawn_pov_reverse`, which is where the player actually stands, is readable. The
underlying cause is #91's measured collision coverage of the camera path
(**20.3% < 90%**), which #100 does **not** fix.

## PSX presentation pass (optional, independently switchable)

`scripts/psx/psx_post_effect.gd` + `shaders/psx_post.glsl`: coarse pixel grid
(`pixel_size`, default 4) plus ordered-dither colour-depth reduction
(`color_levels`, default 16; `dither_strength` 1.0), applied to the finished
colour buffer. It never touches depth, geometry or collision. Switch it off with
`psx_enabled = false`, `--no-psx` on the command line, or by removing the effect
from the scene's Compositor. The effect is visible in `screenshots/after`
against `screenshots/after_no_psx` (mean per-pixel difference 7.94, 99.2% of
pixels changed, max 255 on the spawn POV).

It is applied **only** in the presentation scene. The geometry/alignment review
scenes (`corridor.tscn`, `corridor_splat.tscn`) load the source asset and carry
no presentation effects.

## Frame rate and resources

| Probe | Source `corridor.tscn` | Cleaned `corridor_psx.tscn` | Cleaned `--no-psx` |
|---|---|---|---|
| vsync-capped fps @1280x720 | 60.17 | 60.14 | 60.14 |
| uncapped fps @1280x720 (one run) | 785.34 | 884.96 | 859.60 |
| peak stage VRAM | 0.29 GiB | 0.35 GiB | — |
| peak stage RAM | 0.75 GiB | 0.52 GiB | — |
| splats | 182,569 | 124,564 | 124,564 |

The 60 fps target is met with headroom; uncapped fps is ~+7–13% for the cleaned
scene and varies run-to-run, so the PSX cost is within that noise. VRAM was
comparable/slightly higher (0.29→0.35 GiB) while RAM fell (0.75→0.52 GiB); the
resource sampler reads whole-process peaks, so treat the VRAM delta as
indicative, not a controlled measurement.

## Verification (all on the shipped tree)

| Check | Result | Log |
|---|---|---|
| #83/#74 `verify_alignment.gd` (both review scenes, source AABB unchanged) | **PASS** | `logs/verify_alignment.log` |
| #85 `verify_traversal.gd` | **PASS**, exit 0, zero SafetyNet contacts on the positive walks; writes the committed `assets/corridor_splat/traversal_run.log` (now records `scene: res://scenes/corridor.tscn`) | `logs/verify_traversal.log` |
| #85 `verify_traversal.gd --scene=corridor_psx.tscn` (presentation scene) | **PASS**, exit 0, identical spawn/route/probe numbers; writes its own `assets/corridor_splat/traversal_run_corridor_psx.log`, so the accepted log is not clobbered | `logs/verify_traversal_psx_scene.log`, `logs/traversal_run_corridor_psx.log` |
| `test_splat_alignment.gd` | 27/27 | `logs/test_splat_alignment.log` |
| `verify_scene.gd` | OK | `logs/verify_scene.log` |
| `test_psx_scene.gd` (new: mapping + collision/safety-net/spawn/player equality) | OK | `logs/test_psx_scene.log` |
| `pytest test_splat_cleanup.py` (new) | 20 passed | `logs/pytest_splat_cleanup.log` |
| full pipeline suite | 726 passed, 6 failed — the same 6 pre-existing `test_cull_blurry`/`test_train_brush` failures #88/#99 recorded | — |

**#85 passing is not proof the coverage gate passed.** #91 separately measured
only **20.3%** collision coverage of the camera path (`walkway_covers_camera_path`
FAIL, need 90%). #100 is a visual-polish task and does not change that; the
collision GLB, spawn, route and physics are untouched.

## Files

* `scripts/splat_pipeline/splat_cleanup.py` — pure filter logic.
* `scripts/splat_pipeline/clean_splat.py` — CLI + PLY subset writer + report.
* `scripts/splat_pipeline/tests/test_splat_cleanup.py` — 20 tests.
* `godot_walk/assets/corridor_splat/CLEANUP.md` — reusable contract.
* `godot_walk/assets/corridor_splat/corridor_clean.report.json` — shipped report.
* `godot_walk/scenes/corridor_psx.tscn` — presentation scene.
* `godot_walk/scripts/psx/psx_post_effect.gd`, `scripts/psx/shaders/psx_post.glsl` — PSX pass.
* `godot_walk/scripts/test_psx_scene.gd` — focused scene check.
* `godot_walk/scripts/screenshot_scene.gd` — added `spawn_pov` cameras (existing poses unchanged).
* `godot_walk/scripts/verify_traversal.gd` — added an optional `--scene=` override (default unchanged) so the same battery runs on the presentation scene; the run log now records its scene and an overridden scene writes its own `traversal_run_<scene>.log` so #85's committed log is never clobbered.
* `godot_walk/assets/corridor_splat/traversal_run.log` — +1 line (`scene: res://scenes/corridor.tscn`); the walk result is unchanged.
* `godot_walk/assets/corridor_splat/traversal_run_corridor_psx.log` — the presentation-scene walk, kept separate.
* `godot_walk/evidence/2026-10-05-psx-cleanup/` — this evidence.

Untouched: `corridor.tscn`, `corridor_splat.tscn`, `alignment_manifest.json`,
the generated collision GLB, `player.tscn`, `player.gd`, `verify_alignment.gd`,
`verify_scene.gd`.
