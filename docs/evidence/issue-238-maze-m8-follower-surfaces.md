# Issue 238 — Maze overlay M8: follower reverb, wear and surface variant

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11 (M8 row), with
sections 5.2-5.5, 6.4, 9.1-9.6 and the operator decisions in section 10.
Dependencies: M1 / #231 (`maze_mutation.py`) and M2 / #232
(`maze_follower.py`) are closed and present on `main`.

Status: implementation and automated checks complete. Operator visual review of
the variant captures, the operator walk and the listen check are pending. A
render or a headless pass is not approval.

## What changed

- `godot_walk/scripts/maze_surface.py` (new) is the headless palette-compatible
  surface layer:
  - `palette_registry` loads the registry named by `map.palette_registry`,
    checks its recorded SHA-256, and refuses an absolute or `..` path.
  - `palette_for_cell`, `surface_record`, `wear_record`, `validate_variants`
    and `escalatable_surfaces` check that the cell's palette exists and that
    every selected variant is offered for that surface. The overlay key is the
    change class `surface_variant` (singular); the map layer remains
    `cell.surface_variants`.
  - Variants only move forward along `clean -> worn -> damaged`; wear is an
    integer in `0..2`.
- `godot_walk/scripts/maze_follower.py` extends the M2 reference:
  - `IMPLEMENTED_CLASSES` is the §5.4 order `reverb`, `lamp_state`,
    `lamp_flicker`, `wear`, `surface_variant`. The class is a keyed draw from
    `sha256("<seed>:<attempt>:<event_index>:follower:gmap-0.13.0:<player>:edit-class")`
    over the classes that both the cadence band allows and have at least one
    eligible hidden target. The draw is uniform; weights remain tuning work.
  - `plan_follower_edit` adds reverb, wear and surface-variant plans to the M2
    lamp plan. `plan_lamp_edit` is unchanged, so the M2 first-edit contract is
    preserved: on seed 279 the first edit is still `c04[2]` on -> flicker.
  - Per-class exclusions follow §5.3/§5.5: the current cell, the spawn, the
    exit, the landmark, the last-edited cell and every visible cell are never
    targets. A library module may take a reverb flip only; it is excluded from
    lamp, wear and variant edits because its scene is hash-pinned.
  - `FollowerController` now records the M8 classes, and its effective-state
    helpers (`reverb_enabled`, `wear`, `surface_variants`) validate the folded
    override. `validation_checks` records the class-specific audit checks,
    including `palette_compatible` for a variant edit.
- `godot_walk/scripts/maze_surface_controller.gd` (new) is the runtime
  equivalent. `tag_room` records the palette, variants and wear the room was
  built with. An override clones only the affected mesh materials, replaces
  the albedo with the registry variant (texture or authored colour), preserves
  the mesh's UV scale, and updates the floor collider's `surface_variant` and
  `surface_wear` metadata. No room is rebuilt and no map file is written.
- `godot_walk/scripts/maze_follower_runtime.gd` follows the same class order,
  draw key, target rank and per-class arithmetic. It adds `reverb`, `wear` and
  `surface_variant`; the existing lamp arithmetic is untouched. It ignores a
  cell with no instanced room, and it continues to read the live M6 passage map.
- `godot_walk/scripts/generative_map_assembly.gd` tags generated rooms with
  their surface state and adds the narrow runtime points `set_room_wear`,
  `set_cell_surface_variants`, `apply_cell_surface_override`, `cell_wear` and
  `cell_surface_variants`. Reverb uses the existing `set_room_reverb` from
  #204. Module, landmark and exit cells refuse wear/variant writes.
- `godot_walk/scripts/test_issue232_follower_edit.gd` is generalized to accept
  any implemented first edit class. The seed 279 assertion is unchanged: the
  first live edit is still `lamp_state@c04`, lamp 2, on -> flicker. Seed 1 now
  observes the reverb class its keyed draw selects; that is the intended M8
  extension of the M2 test, not a changed map.
- `godot_walk/scripts/test_maze_follower_edits.py`,
  `godot_walk/scripts/test_maze_surface.py` and
  `godot_walk/scripts/test_issue238_follower_surfaces.gd` (new) cover the M8
  classes, palette compatibility, per-cell isolation, replay and the unchanged
  map.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`project.godot`, `player.gd`, `MATERIAL_LANGUAGE.md` or `PALETTES.md` was
edited. No metadata or layer file was made binary. Every map stays UTF-8 JSON
text.

## Behaviour

The five-seed reference route produces these first three edits (class, cell):

| Seed | Edit 1 | Edit 2 | Edit 3 |
|---|---|---|---|
| 1 | `reverb` `c01` | `lamp_state` `c07` | `reverb` `c06` |
| 2 | `lamp_state` `c05` | `lamp_state` `c06` | `surface_variant` `dp00` |
| 3 | `lamp_state` `c04` | `lamp_state` `c05` | `wear` `c11` |
| 32 | `lamp_state` `c06` | `lamp_state` `c08` | `reverb` `c09` |
| 279 | `lamp_state` `c04` | `lamp_state` `dp00` | `reverb` `c10` |

The Python controller and the live GDScript runtime agree on this table. Across
the five seeds the reference exercises reverb, lamp state, wear and surface
variant; the lamp-flicker class stays covered by the M2 tests. The Godot direct
check also flips a library module's reverb and confirms it sticks, then restores
it; the same module refuses wear and variant writes.

Per class:

- `reverb` flips the room's wet/dry flag through the existing #204 setter.
  It changes metadata, not geometry; the audible tell is the operator's
  listen check. A library module may receive it.
- `wear` adds one level, capped at 2, and updates the floor collider's
  `surface_wear` metadata. It does not rewrite a texture by itself; the visible
  tell in this slice is the variant class.
- `surface_variant` advances exactly one surface one step inside the cell's
  current palette. The other three surfaces, the palette id, the acoustic tag
  and every other room stay unchanged.

The scope of this slice is the issue's wording: reverb, wear/variant overrides
and palette-compatible validation. It does **not** rewrite `cell.palette` or
swap the cell to another palette. A full palette swap is the separate §5.2
`palette` class (medium cost because the floor material is also the acoustic
tag); it is not implemented here.

## Checks run

Python:

```bash
python3 -m pytest -q godot_walk/scripts/test_maze_follower.py \
  godot_walk/scripts/test_maze_follower_edits.py \
  godot_walk/scripts/test_maze_surface.py \
  godot_walk/scripts/test_maze_mutation.py
```

Result: 50 passed. The focused map layers also passed: 183 passed, 1 skipped
(`test_maze_*`, `test_gmap_reverb`, `test_gmap_surface`, `test_gmap_palette`,
`test_gmap_template_v13`).

Full suite:

```bash
python3 -m pytest -q godot_walk/scripts
```

Result: 1398 passed, 5 skipped, 58 subtests passed in 426.61 seconds.

Lint:

```bash
python3 -m ruff check godot_walk/scripts/maze_follower.py \
  godot_walk/scripts/maze_surface.py \
  godot_walk/scripts/test_maze_follower_edits.py \
  godot_walk/scripts/test_maze_surface.py
```

Result: clean.

Godot headless (Godot 4.6.3.stable.official.7d41c59c4):

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue238_follower_surfaces.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-238/runtime_gmap-${seed}.json
done
```

Result: `ISSUE238_FOLLOWER_SURFACES: PASS` for all five seeds. Each report
records the three live edits, the per-edit changed-cell list (exactly one cell
each), the route, the palette check and the unchanged map hash. Seed 279's
report is tracked at
`godot_walk/evidence/2026-11-13-issue-238/runtime_gmap-279.json`.

The M2 runtime check was rerun for all five seeds and still passes:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue232_follower_edit.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json
done
```

Result: `ISSUE232_FOLLOWER_EDIT: PASS` for all five. Seed 279 still reports
`live_edit=lamp_state@c04`.

Regression checks on the changed assembly:

```bash
godot4 --headless --path godot_walk \
  --script res://scripts/test_issue204_reverb.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json
godot4 --headless --path godot_walk \
  --script res://scripts/test_issue183_shape_rooms.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json
```

Both pass (`ISSUE204_REVERB: PASS`, `ISSUE183_SHAPE_ROOMS: PASS`).

## Per-cell isolation and map hash

The Python suite folds the log before and after every accepted edit and compares
every cell's effective light, reverb, wear and variant record. Exactly the
event's `target.cell_id` changes; every other cell is byte-identical to its base
layer. The same check runs per live edit in the Godot test: the snapshot of all
rooms' layers, collider metadata and surface material paths changes only for the
target cell, and room geometry is unchanged after the direct edits.

The committed maps are never written. Each Godot report has
`map_sha256_before == map_sha256_after`. For seed 279:

```text
sha256 godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json
= 51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c
```

## Captures (local, generated; not committed)

Commands:

```bash
godot4 --path godot_walk \
  --script res://scripts/capture_issue238_follower_surfaces.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-238/captures --cell=c01 --surface=floor

godot4 --path godot_walk \
  --script res://scripts/capture_issue238_follower_surfaces.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-238/captures_wall --cell=c01 --surface=wall
```

Output directories (git-ignored by the evidence capture rule):
`godot_walk/evidence/2026-11-13-issue-238/captures/` and
`godot_walk/evidence/2026-11-13-issue-238/captures_wall/`.

| File | State |
|---|---|
| `before_c01_floor_clean.png` | `c01` floor clean |
| `after_c01_floor_worn.png` | the same floor worn |
| `before_c01_wall_clean.png` | `c01` wall clean |
| `after_c01_wall_worn.png` | the same wall worn |
| `manifest.json` | capture metadata and the surface material paths |

The same camera, room and all other surfaces are unchanged in each pair. The
measured image difference is mean RGB 7.03/5.86/2.27 for the floor pair and
14.87/13.34/4.57 for the wall pair; the worn textures are visibly darker. The
material manifest shows only the target surface's source paths changing from
`floor_source_video.png` / `wallpaper_source_video.png` to the matching
`backrooms_yellow_*_worn.png`. These files are local evidence only; this text
log is the tracked record.

Reverb has no visual tell and is deliberately not captured as a picture. The
headless check flips `reverb_enabled` on exactly one room and restores it; the
existing #204 reverb bus is what the operator must hear. A wear-only edit is
likewise metadata: the headless check verifies the floor collider's
`surface_wear` and no texture rewrite.

## Operator steps pending

1. **PENDING: operator visual review of the variant captures.** Judge whether
   clean -> worn on floor and wall reads as an out-of-sight edit, whether the
   change is noticeable without being garish, and whether the capture framing
   is representative. This run does not claim that review.
2. **PENDING: operator walk.** Confirm the class mix and cadence over a full
   run, that the chosen rooms are ones the player will backtrack through, and
   that a wear-only edit reads as a subtle change rather than a no-op. This run
   does not claim that walk.
3. **PENDING: operator listen.** Confirm the reverb flip is audible in the
   edited room and that the room-tone change is not mistaken for a glitch. No
   audio assertion was made; agents cannot hear the mix.
4. **PENDING: operator confirmation that limiting this slice to
   palette-compatible validation (no full `cell.palette` swap) matches the
   intended M8 boundary.** If a palette swap is wanted, it should be its own
   verified slice because it changes the floor material and acoustic tag.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
