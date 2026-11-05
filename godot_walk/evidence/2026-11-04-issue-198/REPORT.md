# Chainlink #198 — gmap-0.8.0 light layer

**Status:** implementation committed as `fde2d07`. #198 is closed. An interactive walkthrough remains pending for review of the darker rotunda and library material transitions.

## Implementation

- Added `gmap-0.8.0` as a version-gated light post-pass over `gmap-0.7.0`. Geometry, ports, links, palette choices and landmark choices stay unchanged. Light data uses the independent `light:gmap-0.8.0` stream. The CLI default remains `gmap-0.2.0`.
- Added map and room schema/validator support. Generated `shape-room-0.8.0` specs carry the light record; older map and room specs are unchanged. The V0.8 cell RNG reuses V0.7 geometry decisions.
- Generated rooms use nearest-filtered per-vertex materials and subdivisions at no more than 1 m. Lamps receive seeded 8 Hz elapsed-time flicker, tier energy and recorded color temperature. Dead lamps have no emission or light. V0.8 ambient energy is 0.2; older maps retain 0.8.
- Library-room materials and `MATERIAL_LANGUAGE.md` remain unchanged. V0.8 runs the existing URSC preset on library module subtrees only, leaving generated per-vertex materials lit. Older maps still use the original whole-assembly preset path.
- To prevent shadowless lights illuminating a neighboring room through a wall, generated rooms within 6.2 m receive distinct culling layers using deterministic spatial coloring. Layer 20 is reserved for library module visuals. Runtime checks assert the masks, nearby-cell separation and module isolation.
- Added `LIGHT_LANGUAGE.md` v0.1.0 and runtime lamp/mesh checks to `test_issue183_shape_rooms.gd`.

### Deviations and compatibility notes

1. The V0.8 spatial light coloring is a small runtime adjustment to the proposed per-cell mask: maps may contain more than 20 room cells, while Godot provides 20 visual layers. Distant rooms may safely share a layer; rooms within the light influence distance may not. This leaves V0.1–0.7 on their existing renderer path.
2. The 600-map sweep exposed a pre-existing shape-spec failure at seed 163: a candidate arm width could form a split/holey raster boundary and abort the width search. `shape_room_stage2.suitable_width` now skips only that nondrawable candidate and tries the next width. Seed 163 now builds 13 room specs; its V0.7/V0.8 map geometry remains equal. Existing successful outputs and kept historical specs remain byte-identical. This changes only the error path that previously failed to produce a room.

## Light distribution

`GMAP_LIGHT_SWEEP=1` validated seeds 1–300 at both requested sizes. No invalid maps or unavailable dark wings occurred. Lamp-state percentages include the deliberate dark-wing dead-lamp override; the base draw remains 80/12/8 before that override.

| Target size | Non-void cells sampled | Lamp states: on / flicker / dead | Cell tiers: normal / bright / dim | Dark wing: placed / not selected / unavailable |
|---|---:|---|---|---|
| 12 | 4,304 | 8,157 (75.67%) / 1,214 (11.26%) / 1,408 (13.06%) | 2,639 (61.32%) / 867 (20.14%) / 798 (18.54%) | 112 / 188 / 0 |
| 20 | 6,718 | 12,630 (77.62%) / 1,812 (11.14%) / 1,829 (11.24%) | 4,347 (64.71%) / 1,230 (18.31%) / 1,141 (16.98%) | 112 / 188 / 0 |

## Headless verification

All kept V0.8 maps passed `test_issue183_shape_rooms.gd`. Counts below are actual versus map-declared lights/boxes; every checked mesh has maximum vertex spacing 1.0 m or less. All checks reported zero failures.

| Seed | Shape rooms | Bidirectional edges | Lights | Lamp boxes | Per-vertex meshes | Nearby isolated pairs | Floor samples missing | Coplanar trim / wall / diagonal | Palette mismatches |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12 | 26/26 | 44/44 | 44/44 | 262 | 38 | 0/42,131 | 0 / 0 / 0 | 0 |
| 2 | 14 | 32/32 | 34/34 | 37/37 | 289 | 36 | 0/50,290 | 0 / 0 / 0 | 0 |
| 3 | 13 | 28/28 | 31/31 | 31/31 | 267 | 38 | 0/31,191 | 0 / 0 / 0 | 0 |
| 11 | 13 | 30/30 | 27/27 | 30/30 | 278 | 33 | 0/46,253 | 0 / 0 / 0 | 0 |
| 69 | 13 | 30/30 | 26/26 | 29/29 | 292 | 36 | 0/34,807 | 0 / 0 / 0 | 0 |

Applicable negative controls passed, including removed door/floor, closed module socket, missing module recess, removed diagonal collision, unmitred joint, malformed diagonal doorway/frame/floor, off-midpoint landmark port and wrong palette. Seed 2 exercised two diagonal links. Seed 69 exercised the four-port rotunda. A V0.7 seed-69 headless regression also passed. `registration_accepted=false` and `scale_calibrated=false` remain unchanged.

Receipts: `runtime_gmap-{1,2,3,11,69}-isolation.json` and `runtime_gmap-69-v7-regression.json` in this directory.

## Rendered captures and inspection

All captures ran under the existing GPU/RAM guard. Preflight passed; no desktop or compute process was stopped and no guard bypass was needed. The capture/profile receipts are in `resource_runs/`.

The referenced PNG captures are Git-ignored by the repository's evidence policy (`godot_walk/evidence/**/*.png`) and are therefore not present in a fresh checkout. The tracked receipts, commands and this report remain; the images stay local unless regenerated.

- Seed 1: `captures-vulkan-isolated/seed1/normal_c00.png`, `flicker_c01_01_a.png`, `flicker_c01_01_b.png`, `dark_wing_c05.png`, `library_joint_c07.png`.
- Figure-library joint: `captures-vulkan-isolated/seed3/library_joint_c06.png` (with normal, flicker A/B and dark-wing captures in the same folder).
- Seed 69 rotunda: `captures-vulkan-isolated/seed69-rotunda-v8/` contains p0–p3 inside and neighboring-side views plus `gmap-69-gmap-0.8.0_rotunda16_wide.png` (nine PNGs total).
- Matched V0.7/V0.8 view: `captures-vulkan-isolated/seed69-matched-v7/matched_gmap-69-gmap-0.7.0.png` and `captures-vulkan-isolated/seed69-matched-v8/matched_gmap-69-gmap-0.8.0.png`.
- Pre-change V0.7 reference: `../2026-11-04-issue-194/captures-operator-review/gmap-69-gmap-0.7.0/`.

I inspected every PNG in the final V0.8 capture folders and the matched pair. The four rotunda openings are framed and connected to readable, closed interior surfaces; the floor and ceiling stay continuous, with no visible black holes, z-fighting or floating trim. The dim wing is dark but remains visible. Flicker A/B visibly changes the ceiling lamp; the measured energy changed from 0.900 to 0.072 in the seed-1 capture. I saw no light leaking through the wall surfaces. The library figure doorway is connected and well lit, though its material/floor transition remains visible; the seed-1 column-module joint has a stronger brightness and texture change. Those are reviewable authored-material boundaries rather than openings or light bleed. The existing ceiling source-texture streaks remain visible.

To check the unchanged V0.7 renderer, I compared all nine 960×540 rotunda captures against the pre-change V0.7 issue-194 captures. They have mean absolute pixel differences of 0.034–0.057 on 8-bit RGB values, with maximum channel difference 12; I saw no visible layout or lighting change. This is not bit-identical evidence; minor render/dither variation remains.

## Runtime and resources

The busiest kept map measured was seed 2 at 1280×720 using the rendered `frame_post_draw` path over 3,299 frames and 11 poses:

- p95 frame time: **4.398 ms**; p99: **4.613 ms**; mean measured rate: **240 FPS** uncapped.
- Runtime measurement receipt and image: `fps-run-isolated/fps_issue198_seed2_isolated.json` and `.png`.
- Across guarded capture runs, peak child RSS was **2.43 GB** and peak sampled VRAM was **1.45 GB** (about **0.58 GB** above the sampled starting use). Profile receipt: `resource_runs/issue198_frame_time_seed2_isolated.json`.

## Post-review validator fixes

Validator edge cases found during review are fixed without changing generated outputs or the visual treatment:

- Unknown dark-wing cell IDs now return `dark_wing_unknown_cell` instead of raising `KeyError`.
- A missing or unreadable V0.8 library index now returns `library_index_unavailable`; the existing `stale_index_hash` check still reports missing or hash-mismatched index files.
- Hash-matching but structurally malformed index JSON (for example, `modules: [null]` or empty module entries) also returns `library_index_unavailable` instead of raising `AttributeError`, `KeyError`, or `TypeError`.
- Six focused regressions live in `test_gmap_light.py`.

## Commands

Launch the dark-wing example (seed 11):

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-11-gmap-0.8.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-11-gmap-0.8.0/index.json
```

Launch the four-port rotunda (seed 69):

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-69-gmap-0.8.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-69-gmap-0.8.0/index.json
```

## Verification commands

```bash
python3 -m pytest -q godot_walk/scripts
GMAP_LIGHT_SWEEP=1 python3 -m pytest -s -q godot_walk/scripts/test_gmap_light.py::test_v80_seed_sweep_12_and_20_cells
ruff check godot_walk/scripts/gmap_build.py godot_walk/scripts/gmap_diagonal_rules.py godot_walk/scripts/gmap_module_rules.py godot_walk/scripts/gmap_palette.py godot_walk/scripts/gmap_validate.py godot_walk/scripts/gmap_light.py godot_walk/scripts/shape_room_rng.py godot_walk/scripts/shape_room_spec.py godot_walk/scripts/shape_room_stage2.py godot_walk/scripts/test_gmap_light.py
ruff format --check godot_walk/scripts/gmap_build.py godot_walk/scripts/gmap_diagonal_rules.py godot_walk/scripts/gmap_module_rules.py godot_walk/scripts/gmap_palette.py godot_walk/scripts/gmap_validate.py godot_walk/scripts/gmap_light.py godot_walk/scripts/shape_room_rng.py godot_walk/scripts/shape_room_spec.py godot_walk/scripts/shape_room_stage2.py godot_walk/scripts/test_gmap_light.py
```

Final Python suite after the post-review validator fixes: **612 passed, 3 skipped, 58 subtests passed**. The previously recorded gated sweep: **1 passed in 312.72 s**. Ruff check, Ruff format check and Python compilation passed. Godot 4.6.3 headless runtime checks passed on seeds 1, 2, 3, 11 and 69; rendered capture and frame-time runs passed under the GPU guard. No protected input or library material file was edited.

**Needs operator review:** whether the 0.2 ambient level and resulting darker rotunda are desirable, and whether the visible figure/column module material transitions are acceptable. These still require an interactive walkthrough; no room walk has been performed as part of this implementation.
