# Bounded Backrooms walk assessment (#101)

Real-GPU, production-eye evaluation of the synthetic `corridor_splat` scene as a
bounded PSX-scale walking experience. Continues the partial work it found
(`volume_map.py`, `capture_walk_envelope.gd`, `walk_envelope/` captures) instead
of discarding it, and corrects two defects in that partial work.

## Headline finding: the production camera was inside the ceiling

`player.tscn` carried a legacy `Head` offset of **1.6 m** above the capsule
centre (from the original sandbox controller, G1 #41, never calibrated for this
room). The capsule is 1.2 m tall with its origin at `floor + 0.6 m`, so the
production eye rode at `floor + 2.2 m` -- **5 cm above the generated ceiling
surface** (floor -1.143 m, ceiling 1.007 m at spawn). Every production
viewpoint rendered from inside the ceiling splat, which is what the earlier
`walk_envelope/` captures show (full-screen streak floaters, blocky black
cutouts in `spawn_se`).

Fix (this run): `Head` 1.6 m -> **0.5 m** (eye 0.1 m below the capsule top, a
standard FPS eye; production eye now `floor + 1.1 m` = -0.04 m at spawn, 9 cm
from the capture-camera height of -0.13 m). Capsule, Player origin, spawn,
collision, physics untouched: `verify_scene` (capsule matches disk),
`test_psx_scene` (Player origin identical), `verify_traversal` (both scenes)
all still pass. `capture_walk_envelope.gd` now reads the production `Head`
node instead of a hardcoded `+1.6`, so the capture cannot drift from the game
again.

After the fix, 5 of 8 spawn headings read as Backrooms at 1280x720 (wallpaper
walls, carpet floor, ceiling + light strips, columns). The remaining 3 face the
unreconstructed side and are quantified below -- no legitimate cleanup invents
that geometry (cleanup can only remove splats, which grows black, never
shrinks it).

## Traversable envelope (measured, not claimed)

From `volume_map.json` (generated collision + #83 contract):

| Quantity | Value |
|---|---|
| walkable cells (collision free grid) | 412 |
| spawn-reachable cells | 255 |
| reachable area | **15.94 m^2** |
| reachable bounds | x -2.94..1.31 (4.25 m), z -1.68..5.07 (6.75 m) |
| spawn (-0.65, 2.89) vs envelope centre (-0.82, 1.69) | +0.17 m x, **+1.19 m z (south of centre)** |
| spawn inside 192-camera path xz range | yes (x -5.45..4.15, z 0.31..5.53) |
| production walk battery | **PASS exit 0 both scenes, zero SafetyNet contacts** |
| route out+back | 6.60 m out / 6.44 m back, 100% floor support, max step 0.067 m |
| camera-path collision coverage (#91, unchanged) | **20.3% < 90% gate** -- the generated walls block most of the filmed path |

Spawn is near the middle in x but ~1.2 m south of centre in z. It was not moved:
`PlayerSpawn` is the #83 contract marker and `verify_alignment`/`verify_scene`
pin it. Relocating spawn to the geometric centre would be a contract change for
a future issue, not this assessment.

## Reachable views (real Vulkan, 1280x720, production eye, PSX scene)

`spawn_headings/spawn_*.png`: 8 compass headings from spawn at the production
eye. Black-void fraction = pixels with all channels < 20/255 (the scene
background is ~(8,9,10); the PSX pass never touches the background):

| Heading | Black voids | Reads as |
|---|---|---|
| se | 0.0% | clean Backrooms corner |
| s | 2.6% | columns, floor, ceiling light, wallpaper |
| sw | 4.1% | columns, floor, ceiling, minor mid-distance gaps |
| e | 6.4% | readable corner + wallpaper, black opening right |
| ne | 8.0% | readable with gaps |
| w | 11.9% | partial: floor/columns/wallpaper + black voids, ceiling streaks |
| nw | 19.3% | floater-dominated with large voids |
| n | 27.4% | mostly black void + near-field floaters |

The geometric view-support score in the same `volume_map.json`
(`visual_enclosure`, 99-100% everywhere, nearest surface median 1.3-2.1 m) is
kept for continuity but **does not predict rendered coverage**: splat centres
inside a heading cone include the floaters themselves. The rendered
black-fraction table above is the ground truth for "visible black voids", and
the PNGs carry the floater judgement no number can.

No background, FOV, or route trickery: background stays the #100 dark value
(voids are counted, not hidden), FOV stays 75, the full 8-heading envelope and
the full #85 route are exercised.

## What was NOT fixed, honestly

1. **North/west views (12-27% black + floaters).** The capture never observed
   that volume (see 20.3% camera-path coverage). No deterministic cleanup of
   this clip invents it. A re-shoot walking the north/west volume is required;
   `corridor_x.mp4` / `room_large.mp4` already pass the capture gate and are
   the candidates, but neither has a splat yet (both e2e attempts ended at
   pose stage / POSE_REFUSED).
2. **Synthetic source status.** `data/scenes/corridor_travel/video.mp4`
   (1920x1080, the `corridor_splat` source) is **REJECTED by the current
   capture gate**: `camera_path_too_short` (0.17 vs >= 0.25 frame widths) +
   `rotation_dominant` warnings. The gate was not tuned to accept it: 0.17
   widths of mostly-pan footage cannot support the walkable volume claimed, so
   `corridor_splat` remains a **historical staged asset**, not a fresh pipeline
   product. Nothing here claims real-video generality.
3. **Adjacent-face enclosure (kept, 0.4% fully enclosed)** measures corridor
   adjacency, not room enclosure, in this open area; it is superseded by the
   rendered table for any visual claim.

## Verification (this tree)

| Check | Result |
|---|---|
| `verify_alignment.gd` | PASS (contract verified across 2 scenes) |
| `test_psx_scene.gd` | OK (mapping + collision/spawn/player identical) |
| `verify_scene.gd` | OK (capsule matches disk, spawn clears floor) |
| `verify_traversal.gd` corridor.tscn | PASS exit 0, zero SafetyNet contacts (log byte-identical) |
| `verify_traversal.gd` corridor_psx.tscn | PASS exit 0, zero SafetyNet contacts (log byte-identical) |
| fps, vsync-capped 1280x720, PSX scene | **60.13 fps** (target 60 met) |
| pytest volume/cleanup/traversal/frame | **141 passed** |
| full pipeline suite | 726 passed / 6 pre-existing failures (same `test_cull_blurry`/`test_train_brush` as #88/#99) |

Untouched: `corridor.tscn`, `corridor_splat.tscn`, `corridor_psx.tscn`,
`alignment_manifest.json`, collision GLB, traversal manifests/logs, #100
evidence. Unrelated dirty files (`.gitignore`, `LESSONS_LEARNED.md`,
`WALKABLE_SPLAT_PLAN.md`, removed `.exo`/`.mcp`/`opencode.json`) left alone.

## Files changed by this run

* `godot_walk/scenes/player.tscn` -- Head 1.6 -> 0.5 m (camera out of ceiling).
* `godot_walk/scripts/capture_walk_envelope.gd` -- eye from production Head node.
* `scripts/splat_pipeline/volume_map.py` -- added view-cone visual-enclosure
  score alongside the adjacent-face score (both reported for source + clean).
* `scripts/splat_pipeline/tests/test_volume_map.py` -- 5 tests for the new score.
* `godot_walk/evidence/2026-10-06-bounded-walk/` -- this evidence (PNGs,
  `volume_map.json`, `heading_black_fraction.json`, REPORT/COMMANDS/ENVIRONMENT).
* `godot_walk/evidence/walk_envelope/spawn_headings/` -- re-captured at the
  corrected production eye (previous captures in that dir were rendered from
  inside the ceiling and are superseded).
