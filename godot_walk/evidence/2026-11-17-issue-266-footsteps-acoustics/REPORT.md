# Issue #266 — footsteps and room acoustics for the six accepted video rooms

Worker report, 2026-11-17. Chainlink task 266, workflow chainlink_261pz, attempt 1/2.

## Scope read before authoring

- Issue #266 in `.chainlink/issues.db`: no operator comments are attached to this
  issue, it is not blocked by another issue, and it names no research document
  under `docs/research/`. The related open issue #274 (audio-analysis MCP
  research) is a separate issue and was not worked on here.
- `godot_walk/source_library/README.md`, the six accepted room folders under
  `godot_walk/source_library/sources/*/rooms/`, each room's
  `module_poetics_v1.json` and `room.gd`, `module_acoustics.py`,
  `module_acoustics_v2.py`, `generate_footstep_audio.py`, `footstep_audit.py`,
  `room_acoustic_probe.gd`, `room_reverb_bus.gd`, and the #200/#202/#203/#205/#207/#216
  issue records were read to establish how surfaces, floor tags and reverb are
  built today. The #265 catalog admission commits were inspected; no decisions
  from any other issue were applied.

## What was done

Only NEW files were created. No hash-pinned file, accepted room, shared acoustics
file, `catalog.json`, source ledger, receipt or hash was edited by hand.

New versioned records:

- `godot_walk/room_catalog/footstep_materials_v0.1.0.json` (+ `.sha256`)
- `godot_walk/room_catalog/module_acoustics_v0.3.0.json` (+ `.sha256`)
- `godot_walk/evidence/2026-11-17-issue-266-footsteps-acoustics/gallery_entry_v0.1.0.json`

New code and tests:

- `godot_walk/scripts/issue266_room_audio.py` — deterministic generator/checker.
- `godot_walk/scripts/test_issue266_room_audio.py` — six pytest checks.

### Material decisions (derived from each room's authored walkable floor)

| Module | Floor evidence | Floor class | Footstep tag | Status |
|---|---|---|---|---|
| `video_22909eb734e4d8e2_slot_canyon_courtyard_v1@1` | `sandy_floor.png` | rock/sand | `debris` | existing proxy |
| `video_d857abe7a94da9d1_nested_light_corridor_v1@1` | `reflective_floor.png` | concrete/tile | `tile` | existing tag |
| `video_d92fc1fa764aa3a2_snow_garden_courtyard_v2@1` | `materials.snow` solid floor | snow | none (`default` fallback) | missing layer |
| `video_102caf53423018b7_chevron_corridor_v1@1` | `carpet_floor.png` | carpet | `carpet` | existing tag |
| `video_2671b32f256a4ee7_chevron_corridor_v1@1` | `carpet_floor.png` | carpet | `carpet` | existing tag |
| `video_61b91dbeb9026dc7_chevron_cross_corridor_v1@1` | `carpet_floor.png` | carpet | `carpet` | existing tag |

Each record stores the surface list, the `room.gd` floor evidence with its
SHA-256, the `module_poetics_v1.json` SHA-256 and a written rationale.

### Acoustic decisions

Reverb parameters in `module_acoustics_v0.3.0.json` reuse the #205
`room_acoustic_probe.gd` `map_metrics` formula, evaluated on inputs derived from
the accepted shape metadata (bbox half-extent, ceiling height and an openness
proxy). Courtyards are classified `open_courtyard` (7 m / 8 m ceilings) with a
documented open-sky energy-loss proxy; the four closed corridors are
`enclosed_corridor` (3.6 m / 4.2 m / 4.56 m ceilings). Every entry is marked
`provenance: derived_from_shape_metadata`, not measured.

`module_acoustics_v0.2.0.json` is untouched and remains authoritative for its 11
measured modules; the new v0.3.0 file is an additive overlay for these six rooms.

### What is missing before any new audio

`footstep_materials_v0.1.0.json -> missing_layers` lists, before authoring:
- **snow** — no snow tag/stems exist; requires a new versioned generator profile
  with transient/body/texture layers, deterministic variants, an audit tag and
  operator listening. No snow audio was authored.
- **rock/sand** — `debris` is only a granular proxy; a dedicated rock or sand
  layer is a decision for the operator after listening.

The gallery entry lists the six materials in #207 strip-entry style and marks
every audition as `pending_operator_listening`. It is a data entry, not a built
walkable scene.

## Verification (exact commands and results)

| Command | Result |
|---|---|
| `python3 godot_walk/scripts/issue266_room_audio.py generate` | `{"rooms": 6, ..., "audio_authored": false}`; 5 new files created |
| `python3 godot_walk/scripts/issue266_room_audio.py check` | `{"errors": [], "valid": true}` |
| `python3 -m pytest -q godot_walk/scripts` | `1540 passed, 5 skipped, 72 subtests passed in 269.03s` |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"errors": [], "valid": true, "registered_count": 13}` |
| `python3 godot_walk/scripts/template_validate.py` | `{"valid": true, "source_manifests": 42, "module_profiles": 22, "generative_maps": 68, "errors": []}` |
| `python3 godot_walk/scripts/module_acoustics.py check` | `{"errors": [], "valid": true}` |
| `python3 godot_walk/scripts/module_acoustics.py check-v2` | `{"errors": [], "valid": true}` |
| `python3 godot_walk/scripts/generate_footstep_audio.py check` | `{"valid": true, "errors": []}` |
| `godot4 --headless --path godot_walk --script res://scripts/test_issue200_footsteps.gd -- --map=res://room_catalog/generative_maps/gmap-2-gmap-0.5.0.json --rooms=res://room_catalog/shape_rooms/gmap-2-gmap-0.5.0/index.json` | `ISSUE200_FOOTSTEPS: PASS failures=0` (exit 0) |
| `godot4 --headless --audio-driver Dummy --path godot_walk --script res://scripts/test_issue205_acoustics.gd -- --map=res://room_catalog/generative_maps/gmap-279-gmap-0.11.0.json --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.11.0/index.json` | `ISSUE205_ACOUSTICS: PASS failures=0 box_mean=2.206 corridor_mean=4.552 wet=0.550` (exit 0) |
| `git diff --name-only` | empty (no tracked file modified); protected files unchanged |

One honest note on the headless run: an initial `test_issue205_acoustics.gd`
attempt using the per-machine `godot_walk/.walk_target.json` map (`gmap-2`)
reported `FAIL: map has no wet shape room with a simple interior point`. That
map is not a valid fixture for that test; rerunning with the fixture documented
in `godot_walk/evidence/2026-11-09-issue-205/REPORT.md` (`gmap-279`) passed. No
code was changed between the two runs.

No visual captures were rendered: this issue changes records and classifiers,
not geometry or shaders, so there is no visual surface to view.

## Pending the operator

- Listen to the existing footstep layers in the six rooms (or a #207-style
  walkable audition) and decide whether the recorded material assignments sound
  right. This report does **not** claim the sound is right: agents cannot hear.
- Decide whether to author a snow layer and/or a dedicated rock/sand layer after
  reviewing `missing_layers`; none was authored here.
- Review the derived reverb characters and the documented open-sky openness
  extension. No #216 ray-cast probe was run for these rooms because none has an
  accepted `module_profile_v1.json`; these values are derived, not measured.

## Limitations

- Floor classes come from authored floor materials in read-only `room.gd` files
  plus `module_poetics_v1.json`; no new connectivity or socket inference was
  made from the videos.
- `registration_accepted` and `scale_calibrated` were not changed; no ledger
  events, receipts or catalog admission decisions were written.
- Numeric audio checks (loudness/separability) were run against the existing
  footsteps-0.3.0 set to confirm it is intact; they do not judge how a material
  sounds in a specific room.
