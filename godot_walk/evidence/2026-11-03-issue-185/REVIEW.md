# Issue #185 review sheet: poetics metadata for library rooms

Prepared for the operator. Mechanical fields and file paths only. No poetics value is chosen anywhere in this file; every command below has placeholders. Source: `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` §3-§4, `chainlink issue show 185`.

## Field guide (condensed from proposal §3)

| Field | Meaning | Range / type |
|---|---|---|
| `form_role` | Karth's *form* axis. `figure`: a rare, individual landmark (source rooms are described as rare figures). `ground`: repeatable background that fills most cells (generated shape rooms are described as common ground). | `ground` or `figure` |
| `rarity_tier` | How rare the room should read in the maze; the map samples tiers from a biased curve (2d6-like), not uniformly. Issue #185's rough guide: figure ~ tier 2-3, ground ~ tier 0-1. | integer 0-3 |
| `apollonian` | Order: lattice regularity, symmetry, repetition (e.g. repeated fluorescent bays or support rows). | 0-1, scored independently |
| `dionysian` | Noise: debris, occlusion, off-grid obstacles, unresolved gaps. | 0-1, scored independently |
| apollonian vs dionysian | They are not opposites; a room can be high in both. Never sum or combine them into one quality number. | |
| `style_tags` | Keeps rooms on-brief (Karth's *variation*/style axis). Reuse `room_catalog/MATERIAL_LANGUAGE.md` roles where possible. Roles listed there: Wallpaper, Carpet/floor, Ceiling, Column faces, Grid and lamps, Connector trim. | list of unique non-empty strings |
| `surface_salience` | What the player notices first in the room. | free text, required non-empty |
| `unique_details[]` | Details that survive from the direct source frames rather than the Hunyuan panorama (Manovich & Arielli: panoramas lean stereotypical; direct frames carry unique details). Each is `<frame path>::<detail text>`. A `figure` needs at least one. | list of frame-cited strings |
| `reason` | Why the operator chose these values; required by the accept command. | free text |

Other terms used below:

- **sign** (Gerner/Peirce): `index` = seen in a direct-source frame; `icon` = resemblance only (textures, crops, panorama-derived surfaces); `symbol` = authored (sockets, collision, obstacles). Only `symbol` features may be traversable connectors.
- **voids**: observed openings that are not tested connectors; carried forward as non-traversable.
- **translation_chain**: direct frame -> Hunyuan panorama -> authored Godot room; shows where prediction entered.
- **port_slots**: boundary edges where an authored adapter could be added (proposal-only, not tested sockets).
- **unlock rule**: `layout_eligible_derived` becomes true only when metadata is operator-accepted AND at least one tested socket exists.
- `accept-*` commands refuse a `figure` with no `--unique-detail`, apollonian/dionysian outside 0-1, duplicate or empty style tags, and empty salience/reason.

Run commands from the repo root (`/mnt/sharedOs/backrooms-workspace`). Done-when per #185: every room has an accepted decision or an explicit note to leave it pending, then `module_poetics.py validate` and `register_video_sources.py validate` pass.

## Rooms at a glance

| # | module_id | origin | tested doorway | variant_status |
|---|---|---|---|---|
| 1 | `godot_gopro_industrial_hall_south_socket_v1` | source_video | south | operator_accepted_as_part_of_issue168_pair_only |
| 2 | `video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1` | source_video | north | operator_accepted_as_part_of_issue168_pair_only |
| 3 | `godot_later_bay_column_bounded_v1` | authored_kit | east | operator_accepted_as_part_of_issue160_pair_only |
| 4 | `godot_early_pocket_single_west_v1` | authored_kit | west | operator_accepted_as_part_of_issue160_pair_only |
| 5 | `godot_gopro_industrial_hall_frame1097_v1` | source_video | none | operator_accepted_standalone_room |
| 6 | `video_ccf9722164a0bdc8_debris_window_rock_room_v1` | source_video | none | operator_accepted_standalone_room_cataloged_for_issue168_pair |
| 7 | `video_b9161c467ed2d30a_bill_viola_single_room_v1` | source_video | none | operator_accepted_standalone_room_cataloged |
| 8 | `godot_early_pocket_pass_through_v1` | authored_kit | none | provisional_operator_review_pending |
| 9 | `godot_early_pocket_three_way_v1` | authored_kit | none | provisional_operator_review_pending |
| 10 | `godot_source_textured_large_room_v1` | authored_kit | none | operator_accepted_as_authored_room_baseline |
| 11 | `godot_source_textured_large_room_hall_end_v1` | authored_kit | none | provisional_operator_review_pending |

# Group 1: #168 pair

## 1. `godot_gopro_industrial_hall_south_socket_v1`

### Identity

- module_id: `godot_gopro_industrial_hall_south_socket_v1` (kind `authored_room_variant`, origin `source_video`)
- source video: video-ccf9722164a0bdc8 (data/videos or manifest: godot_walk/source_library/sources/video-ccf9722164a0bdc8/source_manifest.json)
- room dir: /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v4-south-socket
- room id (for `--room-id`): `industrial-hall-panorama-v4-south-socket`
- catalog variant_status: `operator_accepted_as_part_of_issue168_pair_only`; catalog_layout_eligible: `False`
- tested doorway: **yes** (south)
- connector pair `issue168_industrial_hall_south__debris_rock_north_v1`: status `operator_accepted_exact_pair`; scope: This exact placement and socket pair only. It does not establish source-video connectivity, arbitrary placement, or general socket interchangeability.
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v4-south-socket/module_poetics_v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 208.0 m2; aspect: 1.230769; ceiling height: 4.78 m
- tested sockets: south; untested sockets: none; port_slot count: 3
- void `source_frame_1097_far_right_gap` (traversable=False), source frame `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
  - draft text: A dark partial gap is visible near the far-right edge; continuation and destination are unknown.
- sign counts: index 1, icon 2, symbol 9 (feature kinds: collision 1, observed_opening 1, obstacle 7, socket 1, surface 2)
- translation chain:
  - `direct_frame`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
  - `hunyuan_panorama`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-005/panorama/panorama.png`
  - `godot_room`: `res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v4-south-socket/room.tscn`

### Evidence to look at

- direct-source frames cited by this room (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- Hunyuan panorama (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-005/panorama/panorama.png`
- existing capture images (7):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/far_boundary.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/roof_grid.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/spawn_toward_windows.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/support_rows.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/from_industrial_hall_to_rock_room.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/from_rock_room_to_industrial_hall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/rock_room_entry_and_banks.png`
- existing contact sheets (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/contact_sheet_v3_final.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/source_to_room_contact_v2.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-issue-167-gopro-pilot/adjacent_seed_frames.jpg`
- other images (textures / source crops / frames) (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/roof_beams.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/support_post.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/window_grid.png`
- reports and records (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/operator_review.json`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/connector_contract.json`
- generated contact sheet (existing images, downscaled): `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-03-issue-185/contact_godot_gopro_industrial_hall_south_socket_v1.jpg` (9 tiles)
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/operator_review.json`
    - operator_feedback: "The operator reviewed the assembled walkthrough and said: “yup looks good to me!”"
    - scope: "Operator accepts this exact two-room assembly, its authored hall-south to rock-room-north doorway, and the tested bidirectional traversal. It does not claim source-video connectivity, calibrated scale, or general socket compatibility."
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/operator_review.json`
    - operator_feedback: "The broad part of the panorama was captured well enough; resolution can be addressed later after building a larger library."
    - scope: "Operator-approved as one bounded playable interpretation of the source hall. The panorama is accepted as a broad layout reference; low-resolution refinement is deferred until a larger room library exists. This does not admit the candidate to the catalog or app..."
- note: The v4 room folder has no review or captures of its own; the notes above are for the two-room assembly and for the v3 hall it is derived from.

### Candidate unique-detail frames (23)

Rule: accepted if the path is repo-relative, starts with godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/, has no symlinks, and is an existing file (module_metadata_accept._frame_ok). Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1090.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1091.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1092.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1093.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1094.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1095.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1096.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1098.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1099.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1100.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/source_ingestion_runner.py accept-module-metadata video-ccf9722164a0bdc8 --room-id industrial-hall-panorama-v4-south-socket \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** Has tested doorway (south): accepting metadata sets layout_eligible_derived=true, so the room can enter generated layouts.

---

## 2. `video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1`

### Identity

- module_id: `video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1` (kind `authored_room_variant`, origin `source_video`)
- source video: video-ccf9722164a0bdc8 (data/videos or manifest: godot_walk/source_library/sources/video-ccf9722164a0bdc8/source_manifest.json)
- room dir: /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v2-north-socket
- room id (for `--room-id`): `debris-window-rock-room-v2-north-socket`
- catalog variant_status: `operator_accepted_as_part_of_issue168_pair_only`; catalog_layout_eligible: `False`
- tested doorway: **yes** (north)
- connector pair `issue168_industrial_hall_south__debris_rock_north_v1`: status `operator_accepted_exact_pair`; scope: This exact placement and socket pair only. It does not establish source-video connectivity, arbitrary placement, or general socket interchangeability.
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v2-north-socket/module_poetics_v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 120.0 m2; aspect: 1.2; ceiling height: 3.92 m
- tested sockets: north; untested sockets: none; port_slot count: 3
- voids: none
- sign counts: index 0, icon 3, symbol 76 (feature kinds: collision 1, obstacle 74, socket 1, surface 3)
- translation chain:
  - `direct_frame`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
  - `hunyuan_panorama`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-006/panorama/panorama.png`
  - `godot_room`: `res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v2-north-socket/room.tscn`

### Evidence to look at

- direct-source frames cited by this room (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- Hunyuan panorama (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-006/panorama/panorama.png`
- existing capture images (8):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/ceiling_beams_and_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/closed_far_boundary.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/spawn_into_rock_field.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/west_rock_bank.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/window_and_pier.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/from_industrial_hall_to_rock_room.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/from_rock_room_to_industrial_hall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/captures-v3/rock_room_entry_and_banks.png`
- existing contact sheets (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/candidate_contact_sheet_final.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/source_context_contact_sheet.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/source_texture_crops.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/source_to_room_contact_v2.jpg`
- other images (textures / source crops / frames) (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/ceiling_beam.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/concrete_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/mixed_debris.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/painted_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/window_band.png`
- reports and records (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-168-two-room/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/operator_review.json`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/operator_review.json`
- generated contact sheet (existing images, downscaled): `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-03-issue-185/contact_video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1.jpg` (10 tiles)
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/operator_review.json`
    - operator_feedback: "The operator reviewed the assembled walkthrough and said: “yup looks good to me!”"
    - scope: "Operator accepts this exact two-room assembly, its authored hall-south to rock-room-north doorway, and the tested bidirectional traversal. It does not claim source-video connectivity, calibrated scale, or general socket compatibility."
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/operator_review.json`
    - operator_feedback: "The operator reviewed the candidate contact sheet and said: “yup looks good to me!”"
    - scope: "Operator accepted the standalone debris/window rock-room design for this exact candidate identity. This accepts the authored rock interpretation and bounded standalone room appearance only. It does not accept catalog admission, any connector/socket variant, so..."
- note: The v2 north-socket room folder has no review or captures of its own; the notes above are for the two-room assembly and for the v1 room it is derived from.

### Candidate unique-detail frames (23)

Rule: accepted if the path is repo-relative, starts with godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/, has no symlinks, and is an existing file (module_metadata_accept._frame_ok). Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1090.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1091.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1092.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1093.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1094.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1095.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1096.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1098.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1099.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1100.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/source_ingestion_runner.py accept-module-metadata video-ccf9722164a0bdc8 --room-id debris-window-rock-room-v2-north-socket \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** Has tested doorway (north): accepting metadata sets layout_eligible_derived=true, so the room can enter generated layouts.

---

# Group 2: kit pair (column bay + single-west pocket)

## 3. `godot_later_bay_column_bounded_v1`

### Identity

- module_id: `godot_later_bay_column_bounded_v1` (kind `authored_bounded_room`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue160_column_connector.tscn`)
- catalog variant_status: `operator_accepted_as_part_of_issue160_pair_only`; catalog_layout_eligible: `None`
- tested doorway: **yes** (east)
- connector pair `column_east__pocket_west_v1`: status `operator_accepted_first_pass_pair`; scope: This pair only; does not approve arbitrary placements or new openings.
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_later_bay_column_bounded_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `polygon`, shape_stage: `None`, rectilinear: `False`, vertices: 6, convexity: 1.0
- symmetry: `C1`; area: 44.605 m2; aspect: 1.161765; ceiling height: 2.4 m
- tested sockets: east; untested sockets: none; port_slot count: 5
- voids: none
- sign counts: index 0, icon 1, symbol 2 (feature kinds: collision 1, socket 1, surface 1)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (19):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/C01_north.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/C01_west.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/C02_front.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/C02_reverse.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/east_socket_closed.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/column/spawn_to_C01.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/column_approach.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/connector_midpoint.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_far.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/seam_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/column_to_connector.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_midpoint.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/doorway_from_later_bay.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/later_bay_approach.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- existing contact sheets (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`
- other images (textures / source crops / frames) (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/assets/psx_extension/textures/hunyuan_round3_column_front.png`
- source images outside godot_walk/ (not accepted by accept-kit) (1):
  - `/mnt/sharedOs/backrooms-workspace/data/scenes/corridor_travel/images/frame_0152.jpg`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/REPORT.md`
- existing operator notes: none found
- note: No operator_review.json exists for this room; the pair decision is in the library index connector pair (shown under identity).

### Candidate unique-detail frames (22)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-22-issue-160/captures/column/C01_north.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/column/C01_west.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/column/C02_front.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/column/C02_reverse.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/column/east_socket_closed.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/column/spawn_to_C01.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/column_approach.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/connector_midpoint.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_far.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_return.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/seam_floor.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/column_to_connector.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_midpoint.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_return.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/doorway_from_later_bay.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/later_bay_approach.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- `godot_walk/evidence/2026-10-22-issue-160/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`
- `godot_walk/assets/psx_extension/textures/hunyuan_round3_column_front.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_later_bay_column_bounded_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** Has tested doorway (east): accepting metadata sets layout_eligible_derived=true, so the room can enter generated layouts.

---

## 4. `godot_early_pocket_single_west_v1`

### Identity

- module_id: `godot_early_pocket_single_west_v1` (kind `authored_room`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue160_pocket_connector.tscn`)
- catalog variant_status: `operator_accepted_as_part_of_issue160_pair_only`; catalog_layout_eligible: `None`
- tested doorway: **yes** (west)
- connector pair `column_east__pocket_west_v1`: status `operator_accepted_first_pass_pair`; scope: This pair only; does not approve arbitrary placements or new openings.
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_early_pocket_single_west_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 82.8 m2; aspect: 2.3; ceiling height: 2.4 m
- tested sockets: west; untested sockets: none; port_slot count: 3
- voids: none
- sign counts: index 0, icon 0, symbol 2 (feature kinds: collision 1, socket 1)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (14):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/pocket/east_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/pocket/entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/pocket/far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/pocket/west_socket_closed.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/column_approach.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/connector_midpoint.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_far.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/captures/assembly/seam_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_midpoint.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_return.png`
- existing contact sheets (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-160/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/REPORT.md`
- existing operator notes: none found
- note: No operator_review.json exists for this room; the pair decision is in the library index connector pair (shown under identity).

### Candidate unique-detail frames (16)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-22-issue-160/captures/pocket/east_wall.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/pocket/entry.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/pocket/far_end.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/pocket/west_socket_closed.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/column_approach.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/connector_midpoint.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_far.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/pocket_return.png`
- `godot_walk/evidence/2026-10-22-issue-160/captures/assembly/seam_floor.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_midpoint.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/connector_return.png`
- `godot_walk/evidence/2026-10-22-issue-160/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_early_pocket_single_west_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** Has tested doorway (west): accepting metadata sets layout_eligible_derived=true, so the room can enter generated layouts.

---

# Group 3: GoPro frame-1097 hall, debris-window v1, Bill Viola

## 5. `godot_gopro_industrial_hall_frame1097_v1`

### Identity

- module_id: `godot_gopro_industrial_hall_frame1097_v1` (kind `authored_bounded_room`, origin `source_video`)
- source video: video-ccf9722164a0bdc8 (data/videos or manifest: godot_walk/source_library/sources/video-ccf9722164a0bdc8/source_manifest.json)
- room dir: /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3
- room id (for `--room-id`): `industrial-hall-panorama-v3`
- catalog variant_status: `operator_accepted_standalone_room`; catalog_layout_eligible: `False`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/module_poetics_v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 208.0 m2; aspect: 1.230769; ceiling height: 4.78 m
- tested sockets: none; untested sockets: none; port_slot count: 4
- void `source_frame_1097_far_right_gap` (traversable=False), source frame `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
  - draft text: A dark partial gap is visible near the far-right edge; continuation and destination are unknown.
- sign counts: index 1, icon 2, symbol 8 (feature kinds: collision 1, observed_opening 1, obstacle 7, surface 2)
- translation chain:
  - `direct_frame`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
  - `hunyuan_panorama`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-005/panorama/panorama.png`
  - `godot_room`: `res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/room.tscn`

### Evidence to look at

- direct-source frames cited by this room (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- Hunyuan panorama (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-005/panorama/panorama.png`
- existing capture images (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/far_boundary.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/roof_grid.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/spawn_toward_windows.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/support_rows.png`
- existing contact sheets (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/contact_sheet_v3_final.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/contact_sheet.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-issue-167-gopro-pilot/adjacent_seed_frames.jpg`
- other images (textures / source crops / frames) (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/roof_beams.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/support_post.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/window_grid.png`
- reports and records (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/operator_review.json`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/CATALOG_ADMISSION.md`
- generated contact sheet (existing images, downscaled): `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-03-issue-185/contact_godot_gopro_industrial_hall_frame1097_v1.jpg` (6 tiles)
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/operator_review.json`
    - operator_feedback: "The broad part of the panorama was captured well enough; resolution can be addressed later after building a larger library."
    - scope: "Operator-approved as one bounded playable interpretation of the source hall. The panorama is accepted as a broad layout reference; low-resolution refinement is deferred until a larger room library exists. This does not admit the candidate to the catalog or app..."

### Candidate unique-detail frames (23)

Rule: accepted if the path is repo-relative, starts with godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/, has no symlinks, and is an existing file (module_metadata_accept._frame_ok). Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1090.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1091.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1092.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1093.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1094.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1095.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1096.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1098.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1099.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1100.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/source_ingestion_runner.py accept-module-metadata video-ccf9722164a0bdc8 --room-id industrial-hall-panorama-v3 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested.

---

## 6. `video_ccf9722164a0bdc8_debris_window_rock_room_v1`

### Identity

- module_id: `video_ccf9722164a0bdc8_debris_window_rock_room_v1` (kind `authored_bounded_room`, origin `source_video`)
- source video: video-ccf9722164a0bdc8 (data/videos or manifest: godot_walk/source_library/sources/video-ccf9722164a0bdc8/source_manifest.json)
- room dir: /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1
- room id (for `--room-id`): `debris-window-rock-room-v1`
- catalog variant_status: `operator_accepted_standalone_room_cataloged_for_issue168_pair`; catalog_layout_eligible: `False`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/module_poetics_v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 120.0 m2; aspect: 1.2; ceiling height: 3.92 m
- tested sockets: none; untested sockets: none; port_slot count: 4
- voids: none
- sign counts: index 0, icon 3, symbol 75 (feature kinds: collision 1, obstacle 74, surface 3)
- translation chain:
  - `direct_frame`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
  - `hunyuan_panorama`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-006/panorama/panorama.png`
  - `godot_room`: `res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/room.tscn`

### Evidence to look at

- direct-source frames cited by this room (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- Hunyuan panorama (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-006/panorama/panorama.png`
- existing capture images (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/ceiling_beams_and_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/closed_far_boundary.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/spawn_into_rock_field.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/west_rock_bank.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/captures-final/window_and_pier.png`
- existing contact sheets (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/candidate_contact_sheet_final.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/source_context_contact_sheet.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/source_texture_crops.png`
- other images (textures / source crops / frames) (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/ceiling_beam.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/concrete_floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/mixed_debris.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/painted_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/window_band.png`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-01-issue-168-room-candidate/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/operator_review.json`
- generated contact sheet (existing images, downscaled): `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-03-issue-185/contact_video_ccf9722164a0bdc8_debris_window_rock_room_v1.jpg` (7 tiles)
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/operator_review.json`
    - operator_feedback: "The operator reviewed the candidate contact sheet and said: “yup looks good to me!”"
    - scope: "Operator accepted the standalone debris/window rock-room design for this exact candidate identity. This accepts the authored rock interpretation and bounded standalone room appearance only. It does not accept catalog admission, any connector/socket variant, so..."

### Candidate unique-detail frames (23)

Rule: accepted if the path is repo-relative, starts with godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/, has no symlinks, and is an existing file (module_metadata_accept._frame_ok). Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-room-references/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4336.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4486.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4636.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4786.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-zone-context/frame_4936.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1090.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1091.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1092.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1093.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1094.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1095.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1096.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1097.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1098.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1099.png`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/frame_1100.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/source_ingestion_runner.py accept-module-metadata video-ccf9722164a0bdc8 --room-id debris-window-rock-room-v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested.

---

## 7. `video_b9161c467ed2d30a_bill_viola_single_room_v1`

### Identity

- module_id: `video_b9161c467ed2d30a_bill_viola_single_room_v1` (kind `authored_bounded_room`, origin `source_video`)
- source video: video-b9161c467ed2d30a (data/videos or manifest: godot_walk/source_library/sources/video-b9161c467ed2d30a/source_manifest.json)
- room dir: /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1
- room id (for `--room-id`): `bill-viola-single-room-v1`
- catalog variant_status: `operator_accepted_standalone_room_cataloged`; catalog_layout_eligible: `False`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/module_poetics_v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D4`; area: 64.0 m2; aspect: 1.0; ceiling height: 2.8 m
- tested sockets: none; untested sockets: none; port_slot count: 4
- voids: none
- sign counts: index 0, icon 5, symbol 2 (feature kinds: collision 1, obstacle 1, surface 5)
- translation chain:
  - `direct_frame`: `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_0820.png`; `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_4642.png`; `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2730.png`; `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2731.png`; `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2732.png`
  - `godot_room`: `res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/room.tscn`

### Evidence to look at

- direct-source frames cited by this room (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_0820.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_4642.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2730.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2731.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2732.png`
- Hunyuan panorama (1):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/hunyuan/attempt-001/panorama/panorama.png`
- existing capture images (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-v4/left_oblique.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-v4/look_back_at_closed_boundary.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-v4/right_oblique.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-v4/spawn_toward_dresser.png`
- existing contact sheets (3):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/candidate-contact.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room_comparison_v2.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room_comparison_v1.jpg`
- other images (textures / source crops / frames) (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/dark_carpet.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/dresser_front.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/plain_wall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/television_screen.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/vase_and_flowers.png`
- reports and records (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/OPERATOR_APPROVAL.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/operator_decision_001.json`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/CATALOG_ADMISSION.md`
- generated contact sheet (existing images, downscaled): `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-03-issue-185/contact_video_b9161c467ed2d30a_bill_viola_single_room_v1.jpg` (10 tiles)
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/operator_decision_001.json`
    - operator_feedback: "hell yea! it looks really nice, approved!"
    - limitations: "["No panorama approval; Hunyuan attempt 001 remains a source mismatch.", "No catalog admission, scale calibration, registration acceptance, or connector approval."]"
- note: Existing record (operator_decision_001.json limitations / OPERATOR_APPROVAL.md): the Hunyuan attempt-001 panorama is recorded as a source mismatch and was not used as the room basis.

### Candidate unique-detail frames (5)

Rule: accepted if the path is repo-relative, starts with godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/, has no symlinks, and is an existing file (module_metadata_accept._frame_ok). Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_0820.png`
- `godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-room-context-001/frame_4642.png`
- `godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2730.png`
- `godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2731.png`
- `godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/issue169-seed-91s/frame_2732.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/source_ingestion_runner.py accept-module-metadata video-b9161c467ed2d30a --room-id bill-viola-single-room-v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested.

---

# Group 4: pocket pass-through / three-way, large room + hall-end variant

## 8. `godot_early_pocket_pass_through_v1`

### Identity

- module_id: `godot_early_pocket_pass_through_v1` (kind `authored_room_variant`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue149_pocket_pass_through.tscn`)
- catalog variant_status: `provisional_operator_review_pending`; catalog_layout_eligible: `None`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_early_pocket_pass_through_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 82.8 m2; aspect: 2.3; ceiling height: 2.4 m
- tested sockets: none; untested sockets: east, west; port_slot count: 2
- voids: none
- sign counts: index 0, icon 0, symbol 3 (feature kinds: collision 1, socket 2)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (12):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_dead_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_opening.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_return_to_trunk.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_pass_through.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_start_connector.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_terminal_dead_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_column_to_pocket.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_pocket_far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_pocket_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- existing contact sheets (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/REPORT.md`
- existing operator notes: none found
- note: No operator_review.json exists for this room. The #149 captures are seeded-layout views, not isolated room captures.

### Candidate unique-detail frames (14)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_dead_end.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_opening.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_return_to_trunk.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_pass_through.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_start_connector.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_terminal_dead_end.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_column_to_pocket.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_pocket_far_end.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/issue160-regression/accepted_pair_pocket_return.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- `godot_walk/evidence/2026-10-22-issue-149/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_early_pocket_pass_through_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested. Untested sockets on the draft: east, west.

---

## 9. `godot_early_pocket_three_way_v1`

### Identity

- module_id: `godot_early_pocket_three_way_v1` (kind `authored_room_variant`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue149_pocket_three_way.tscn`)
- catalog variant_status: `provisional_operator_review_pending`; catalog_layout_eligible: `None`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_early_pocket_three_way_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `box`, shape_stage: `0`, rectilinear: `True`, vertices: 4, convexity: 1.0
- symmetry: `D2`; area: 82.8 m2; aspect: 2.3; ceiling height: 2.4 m
- tested sockets: none; untested sockets: east, north, west; port_slot count: 1
- voids: none
- sign counts: index 0, icon 0, symbol 4 (feature kinds: collision 1, socket 3)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (9):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_dead_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_opening.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_return_to_trunk.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_pass_through.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_start_connector.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_terminal_dead_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- existing contact sheets (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-22-issue-149/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-21-issue-148/early-pocket/REPORT.md`
- existing operator notes: none found
- note: No operator_review.json exists for this room. The #149 captures are seeded-layout views, not isolated room captures.

### Candidate unique-detail frames (11)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_dead_end.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_opening.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_branch_return_to_trunk.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_pass_through.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_start_connector.png`
- `godot_walk/evidence/2026-10-22-issue-149/captures/seed-149/seed_terminal_dead_end.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_entry.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_far_end.png`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/pocket_return.png`
- `godot_walk/evidence/2026-10-22-issue-149/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_early_pocket_three_way_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested. Untested sockets on the draft: east, north, west.

---

## 10. `godot_source_textured_large_room_v1`

### Identity

- module_id: `godot_source_textured_large_room_v1` (kind `authored_bounded_room`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue164_room_large_baseline.tscn`)
- catalog variant_status: `operator_accepted_as_authored_room_baseline`; catalog_layout_eligible: `None`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_source_textured_large_room_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `rectilinear_polygon`, shape_stage: `1`, rectilinear: `True`, vertices: 8, convexity: 0.851964
- symmetry: `D1`; area: 141.0 m2; aspect: 1.9; ceiling height: 3.2 m
- tested sockets: none; untested sockets: hall_end; port_slot count: 7
- void `source_frame_0013_visible_passage` (traversable=False), source frame `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
  - draft text: A room-to-passage opening is visible in the seed frame; the footage does not establish where it leads.
- sign counts: index 1, icon 0, symbol 3 (feature kinds: collision 1, observed_opening 1, obstacle 1, socket 1)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (9):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/column_south.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/column_west.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/open_passage.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/room_corner.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/spawn_column.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/large_room_column_and_hall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/large_room_hall_entry.png`
- existing contact sheets (4):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/candidate_contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_candidates_contact.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures_contact.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/contact_sheet.jpg`
- other images (textures / source crops / frames) (7):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/ceiling.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/column_face.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/wallpaper.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0049.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0085.png`
- reports and records (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/operator_review.json`
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/operator_review.json`
    - operator_statement: "looks pretty good to me, we can run with that, i approve"
    - decision: "accepted_as_authored_room_baseline"

### Candidate unique-detail frames (20)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-24-issue-163/captures_final/column_south.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/column_west.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_end.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_return.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/open_passage.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/room_corner.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/spawn_column.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/large_room_column_and_hall.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/large_room_hall_entry.png`
- `godot_walk/evidence/2026-10-24-issue-163/candidate_contact_sheet.jpg`
- `godot_walk/evidence/2026-10-24-issue-163/source_candidates_contact.jpg`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures_contact.jpg`
- `godot_walk/evidence/2026-10-24-issue-164/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/ceiling.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/column_face.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/floor.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/wallpaper.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0049.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0085.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_source_textured_large_room_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested. Untested sockets on the draft: hall_end.

---

## 11. `godot_source_textured_large_room_hall_end_v1`

### Identity

- module_id: `godot_source_textured_large_room_hall_end_v1` (kind `authored_room_variant`, origin `authored_kit`)
- source video: none (authored kit room)
- room dir: none (kit room; scene `res://scenes/issue164_room_large_connector.tscn`)
- catalog variant_status: `provisional_operator_review_pending`; catalog_layout_eligible: `None`
- tested doorway: **no**
- draft: `/mnt/sharedOs/backrooms-workspace/godot_walk/room_catalog/module_poetics/godot_source_textured_large_room_hall_end_v1-v1.json` (metadata_status `draft_mechanical`)

### Mechanical fields (module_poetics_v1 draft)

- primitive: `rectilinear_polygon`, shape_stage: `1`, rectilinear: `True`, vertices: 8, convexity: 0.851046
- symmetry: `D1`; area: 141.18 m2; aspect: 1.906; ceiling height: 4.47099 m
- tested sockets: none; untested sockets: hall_end; port_slot count: 7
- void `source_frame_0013_visible_passage` (traversable=False), source frame `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
  - draft text: The room-to-hall opening is source-visible; the new hallway-end socket is authored and provisional.
- sign counts: index 1, icon 0, symbol 3 (feature kinds: collision 1, observed_opening 1, obstacle 1, socket 1)
- translation chain: empty in the draft (authored kit room)

### Evidence to look at

- direct-source frames: none (kit room, no source video)
- existing capture images (13):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/column_south.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/column_west.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_end.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_return.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/open_passage.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/room_corner.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/captures_final/spawn_column.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/large_room_column_and_hall.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/large_room_hall_entry.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/new_room_to_pocket.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/captures/pocket_to_new_room.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-four-room-transfer/captures_final/connection_corridor_to_large_room.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-four-room-transfer/captures_final/connection_large_room_to_corridor.png`
- existing contact sheets (2):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/candidate_contact_sheet.jpg`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/contact_sheet.jpg`
- other images (textures / source crops / frames) (7):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/ceiling.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/column_face.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/floor.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/source_textures/wallpaper.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0049.png`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0085.png`
- reports and records (5):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/operator_review.json`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-four-room-transfer/REPORT.md`
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-four-room-transfer/operator_review.json`
- existing operator notes (quoted from files):
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-163/operator_review.json`
    - operator_statement: "looks pretty good to me, we can run with that, i approve"
    - decision: "accepted_as_authored_room_baseline"
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-24-issue-164/operator_review.json`
    - operator_feedback: "excellent yes it feels coherent , walkable , its the basis of what we want a workflow to produce for any input video"
    - scope: "Accepts the exact seed-164 three-room layout and pocket-to-third-room connection as a workflow prototype. Does not establish source-video connectivity, calibrated scale, or suitability of this connector for other videos."
  - `/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-10-26-four-room-transfer/operator_review.json`
    - operator_feedback: "The current four-room state looks very good; the connection and layout look right."
    - scope: "Accepts this exact seed-166 four-room layout and authored R002.west_back to R003.west connection. Does not admit either candidate module to the shared catalog, approve metric scale or source registration, establish source-video connectivity, or generalize the ..."
    - decision: "accepted"
- note: The #163 and #164 reviews cover the baseline room and a layout using the hall-end connector; check whether they apply to this variant.

### Candidate unique-detail frames (22)

Rule: kit rooms have no source video; accept-kit accepts any existing repo-relative file under godot_walk/ (KIT_EVIDENCE_PREFIX). Listed here: this room's existing evidence images under godot_walk/. Paths are repo-relative, as the flag requires. Listed without description.

- `godot_walk/evidence/2026-10-24-issue-163/captures_final/column_south.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/column_west.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_end.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/hallway_return.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/open_passage.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/room_corner.png`
- `godot_walk/evidence/2026-10-24-issue-163/captures_final/spawn_column.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/large_room_column_and_hall.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/large_room_hall_entry.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/new_room_to_pocket.png`
- `godot_walk/evidence/2026-10-24-issue-164/captures/pocket_to_new_room.png`
- `godot_walk/evidence/2026-10-26-four-room-transfer/captures_final/connection_corridor_to_large_room.png`
- `godot_walk/evidence/2026-10-26-four-room-transfer/captures_final/connection_large_room_to_corridor.png`
- `godot_walk/evidence/2026-10-24-issue-163/candidate_contact_sheet.jpg`
- `godot_walk/evidence/2026-10-24-issue-164/contact_sheet.jpg`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/ceiling.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/column_face.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/floor.png`
- `godot_walk/evidence/2026-10-24-issue-163/source_textures/wallpaper.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0013.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0049.png`
- `godot_walk/evidence/2026-10-24-issue-163/room_large_frame_0085.png`

### Command template (fill every placeholder)

```bash
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id godot_source_textured_large_room_hall_end_v1 \
  --form-role <ground|figure> --rarity-tier <0-3> --apollonian <0-1> --dionysian <0-1> \
  --style-tag <tag> [--style-tag <tag> ...] \
  --surface-salience "<what the player notices first>" \
  --unique-detail "<frame path>::<detail>" [--unique-detail "<frame path>::<detail>" ...] \
  --reason "<reason>"
```

**Unlock:** No tested doorway: accepting records the decision, but layout_eligible_derived stays false and the room stays out of layout until a doorway variant is authored and tested. Untested sockets on the draft: hall_end.

---

