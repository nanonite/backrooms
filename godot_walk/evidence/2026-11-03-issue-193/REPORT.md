# Issue 193 — diagonal links on 45-degree walls

## Result

Implemented opt-in `gmap-0.6.0` diagonal links. Earlier generator versions and the CLI default remain unchanged. The v6 post-pass adds a seeded 0–2 link budget, matches disjoint eligible room pairs, applies only rule-checked one-metre leaf nudges, cuts matching 2.5 m chamfers, and inserts a 2 m wide authored passage. Passage geometry has its own continuous mitered wall mesh and collision. Existing doorway/reveal and room-containment checks account for the diagonal ports and the passage floor.

The seed artifacts include the requested base seeds 1–3 and two linked candidates, seeds 36 and 64. Seeds 36 and 64 each contain one diagonal link, a library module, and palette variation. The requested generated example with two links was not found: a search of seeds 1–1000 across supported map sizes (6–20 cells), plus a bounded combination search over seeds 1–300 at 12/16/20 cells (up to eight leaf nudges and 512 explored states), produced no two-link map. The generator and selector retain the two-link budget and selector; a unit test confirms two independent pairs can be selected. This is a remaining artifact-coverage deviation, not a claim that two links were generated.

## Kept-seed runtime evidence

All five kept maps pass the Godot 4.6.3 headless walkability suite. Counts below are from the matching `runtime_seed*_finalverified.json` files in this folder. `rooms` is the number of generated shape-room specs; module count is separate. Coplanar columns are trim, wall, reveal, and diagonal-face conflicts.

| Seed | Shape rooms / modules | Traversal both ways | Flood / expected cells | Push stopped | Floor missing / samples | Joint uncovered / samples | Coplanar trim / wall / reveal / diagonal | Diagonal links / lane sweeps |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12 / 2 | 26/26 | 14/14 | 33/33 | 0/42131 | 0/2935 | 0 / 0 / 0 / 0 | 0 / n/a |
| 2 | 12 / 1 | 24/24 | 13/13 | 21/21 | 0/13208 | 0/1809 | 0 / 0 / 0 / 0 | 0 / n/a |
| 3 | 12 / 2 | 26/26 | 14/14 | 30/30 | 0/45068 | 0/2668 | 0 / 0 / 0 / 0 | 0 / n/a |
| 36 | 13 / 2 | 30/30 | 15/15 | 47/47 | 0/29992 | 0/3752 | 0 / 0 / 0 / 0 | 1 / 12/12 |
| 64 | 21 / 1 | 44/44 | 22/22 | 38/38 | 0/23606 | 0/2951 | 0 / 0 / 0 / 0 | 1 / 12/12 |

Every kept map reports zero void cells reached. The applicable negative controls pass, including removed doorways/floors, open module sockets, removed diagonal doorway/collision, and unmitred passage joints. The new `diagonal_floor_without_declared_link` control applies to seeds 36 and 64: removing diagonal graph edges while retaining passage geometry yields three containment failures (first: `c06: floor present at 10 samples outside the polygon and unconnected`).

The temporary scratch sweep of seeds 4, 5, and 6 also passed. It used generated maps/specs in a temporary directory and retained no scratch artifacts. These maps had 0 diagonal links; they still exercised the existing traversal and zero-coplanar gates.

## Artifacts and review

Each kept seed has a map JSON, fill JSON, SVG, and `shape_rooms/<map-id>/` index/specs. Runtime results are:

- `runtime_seed1_finalverified.json`
- `runtime_seed2_finalverified.json`
- `runtime_seed3_finalverified.json`
- `runtime_seed36_finalverified.json`
- `runtime_seed64_finalverified.json`

Seeds 36 and 64 show the new passage in the layout SVG and playable scene. Example launch command for seed 36:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-36-gmap-0.6.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-36-gmap-0.6.0/index.json
```

Rendered output was not visually inspected as part of this headless verification. Human review should check the chamfer-to-passage joins from both sides, reveal trim alignment, floor/ceiling triangulation, and the PSX appearance at the corners. The runtime results establish physics traversal and collision checks, not visual quality.

## Verification

- `python3 -m pytest -q godot_walk/scripts` — **575 passed, 58 subtests passed**.
- `ruff check` and `ruff format --check` on the six new Python modules — passed.
- `python3 -m py_compile` on all modified Python modules — passed.
- Headless `test_issue183_shape_rooms.gd` — passed on seeds 1, 2, 3, 36, and 64; temporary scratch seeds 4, 5, and 6 also passed.
- A clean pre-#193 `HEAD` script snapshot was run against seeds 1–3 for each generator version 0.1.0–0.5.0. All 15 pre-existing headless report fields match exactly, and all runs pass.
- The Python suite verifies byte-identical regeneration for generator versions 0.1.0–0.5.0 and leaves the CLI default unchanged.

Repeat a kept-seed runtime check by replacing `N` with `1`, `2`, `3`, `36`, or `64`:

```bash
godot4 --headless --path godot_walk \
  --script res://scripts/test_issue183_shape_rooms.gd -- \
  --map=res://room_catalog/generative_maps/gmap-N-gmap-0.6.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-N-gmap-0.6.0/index.json \
  --out=res://evidence/2026-11-03-issue-193/runtime_seedN_finalverified.json
```

## Changed files

- Generator and validation: `gmap_build.py`, `gmap_fill.py`, `gmap_module_rules.py`, `gmap_palette.py`, `gmap_rules.py`, `gmap_stage2.py`, `gmap_svg.py`, `gmap_validate.py`, `shape_room_rng.py`, `shape_room_spec.py`, `shape_room_stage2.py`; new `gmap_diagonal.py`, `gmap_diagonal_candidates.py`, `gmap_diagonal_nudge.py`, `gmap_diagonal_rules.py`, `gmap_diagonal_rule_geometry.py`, `test_gmap_diagonal.py`.
- Schemas: `generative_map.schema.json`, `shape_room.schema.json`.
- Godot: `issue183_map_checks.gd`, `issue183_room_checks.gd`, `issue190_diagonal_checks.gd`, `shape_room_builder.gd`, `shape_room_diagonal.gd`, `test_issue183_shape_rooms.gd`; new `issue193_diagonal_link_checks.gd`, `shape_room_diagonal_passage.gd`.
- Generated artifacts: map/fill/SVG and shape-room index/specs for seeds 1, 2, 3, 36, and 64; runtime reports listed above.

No inference, GPU capture, training, or paid API was used. Protected library scenes/scripts/textures, `room_catalog/catalog.json`, `scripts/player.gd`, `project.godot`, and `room_catalog/MATERIAL_LANGUAGE.md` were not changed. No commit was made.

## Rendering fix after operator walk (lead addendum)
On the first walk of seed 36, the operator saw that the diagonal doorways rendered wrong: a mis-rotated lintel, a missing wall above the door, and black showing through. Collision was fine.

**Root cause.** `shape_room_builder.gd` rotated the header, trim and closed-door boxes to the 45-degree face only when a spec carried `diagonal_passage` or `diagonal_link_chamfer`. The chamfer-room specs (c06, c07) carry neither, so those boxes were built unrotated.

**Fix (GDScript only, no data change).**
- The frame's yaw is now always used.
- A `SeamStrip_<port>` under each passage doorway line closes the floor seam, which had shown as black dots.

**Checks added.**
- New `_check_frames` in `issue193_diagonal_link_checks.gd`: the header and trim must exist and be aligned with the face, and the header must span from door height to the ceiling.
- New negative control `diagonal_frame_unaligned`.
- `scripts/capture_diagonal_passage.gd` renders face, up and oblique views of every diagonal doorway, so the result can be checked visually before review.

**Results.**
- Seeds 36 and 64 pass headless with `diagonal_frames=2` and all coplanar counts 0. The lead re-ran both, plus 0.5.0 seed 129.
- 575 pytest tests pass.
- The lead reviewed the renders.
- The operator walked seed 36 after the fix and approved it: "yup it worked! approved".
