# Issue 279 — chevron-cross-corridor-v1 two-socket through variant (north/south), untested

Date: 2026-11-19
Issue: #279 (child of #265). Pattern: issue #275,
`godot_walk/evidence/2026-11-18-issue-275-socket-variant/REPORT.md` (including its addendum), and
its variant room `video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/`. The two
later siblings #277 and #278 were read for the current mechanical process; the previous
socket-variant issue (#278) is committed, so this catalog bump is sequential (`0.9.0` → `0.10.0`).
Status: **IMPLEMENTED — pending operator review of socket placement and captures. No blocker.**

## Operator authorisation and scope

Task data authorises ONE new two-socket THROUGH variant of the operator-accepted #177 room
(`video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v1`), built with new files and new versions
only. Sockets: `level_doorway_2m_v1`, clear `2.0 x 2.1`, floor `0.0`, approach clearance `1.2`,
`circulation_role through`, status `untested`; all other walls closed with matching colliders.
The openings are authored proposals, not observed in the source video. `tested_connector_pairs` is
empty, `layout_eligible` is `false`, and `registration_accepted` and `scale_calibrated` stay `false`
everywhere. No map, connector-pair test, `module_profile_v1.json` sidecar, `module_poetics_v2.json`,
`accept-module-metadata` or `decide-integration` was produced. No Hunyuan or any other model call
was made. Captures were rendered only through the guarded capture script. Registration, the
catalog bump and the ledger events use only the existing scripts and runner stages; no event,
receipt or hash was written by hand.

## Socket placement — exact openings and why

The accepted room is an authored rectangle x ∈ [-8, 8], z ∈ [-10, 10], height 4.2, spawn
`(0, 0.6, 8.4)`. Its four interior PARTITIONS (read from `chevron-cross-corridor-v1/room.gd`)
are thin walls, 0.3 m thick in x and 4 m long in z:

| Partition | x range | z range |
|---|---|---|
| `PartitionCollision_00` | [-4.65, -4.35] | [3, 7] |
| `PartitionCollision_01` | [4.35, 4.65] | [0, 4] |
| `PartitionCollision_02` | [-4.65, -4.35] | [-4, 0] |
| `PartitionCollision_03` | [4.35, 4.65] | [-8, -4] |

No partition was added or moved. The partitions leave the central lane x ∈ [-4.35, 4.35] open
along the full z range; they also leave side strips at x < -4.65 and x > 4.65, reached through
partition gaps. A candidate doorway is clear when no partition AABB intersects either its
`2.0 x 2.1` clear volume or its `2.0 x 1.2` inward approach sector at floor level.

### Chosen openings (the two clear ends of the central through-lane)

| Socket | Opening | Outward normal | Clear volume | 1.2 m approach sector | Why this spot |
|---|---|---|---|---|---|
| `north` | x = 0, z = **-10** | (0, 0, -1) | x ∈ [-1, 1], y ∈ [0, 2.1] | x ∈ [-1, 1], z ∈ [-10, -8.8] | Far end of the clear central lane. The nearest partition (`_03`) is at x = 4.5 with z ≥ -8: 3.35 m to the side and 0.8 m beyond the inner edge of the approach sector. |
| `south` | x = 0, z = **+10** | (0, 0, +1) | x ∈ [-1, 1], y ∈ [0, 2.1] | x ∈ [-1, 1], z ∈ [8.8, 10] | Near end of the lane, 0.4 m behind the unchanged safe spawn. The nearest partition (`_00`) is at x = -4.5 with z ≤ 7: 3.35 m to the side and 1.8 m before the inner edge of the approach sector. |

Each end wall is rebuilt as two side returns (x ∈ [-8.15, -1.0] and x ∈ [1.0, 8.15]) plus a
header from y = 2.1 to y = 4.2, each with a matching `StaticBody3D`/`BoxShape3D` collider. West
and east walls stay fully closed with matching colliders. Floor, materials, textures, the four
partitions, ceiling, lights and PSX profile are inherited unchanged. Headless rays confirm the
central lane is unobstructed and real player traversal crosses both openings.

### Clear and blocked candidate positions (as requested)

The issue expects "the arm ends of the cross, up to four". Evaluated as the four perimeter wall
directions, every tested candidate is geometrically clear — there is **no blocked wall position
and therefore no geometry blocker to stop and report**:

| Wall direction | Candidate centres tested | Approach sector | Status |
|---|---|---|---|
| North (z = -10) | x = -6, -4.5, -2, 0, 2, 4.5, 6 | x = c ± 1, z ∈ [-10, -8.8] | **CLEAR** for all centres — every partition stops at z ≥ -8, beyond the sector. |
| South (z = +10) | x = -6, -4.5, -2, 0, 2, 4.5, 6 | x = c ± 1, z ∈ [8.8, 10] | **CLEAR** for all centres — every partition stops at z ≤ 7, before the sector. |
| West (x = -8) | z = -9, -7, -5, -2, 0, 1.5, 5, 8.5 | x ∈ [-8, -6.8], z = c ± 1 | **CLEAR** for all centres — partitions at x ∈ [±4.35, ±4.65] are ≥ 2.15 m from the sector's inner edge. |
| East (x = +8) | z = -9, -7, -5, -2, 0, 1.5, 5, 8.5 | x ∈ [6.8, 8], z = c ± 1 | **CLEAR** for all centres — same lateral clearance. |

- **Clear — chosen:** north (x = 0, z = -10) and south (x = 0, z = +10). These are the two ends
  of the straight central lane, the through-axis used by the #275/#277/#278 pattern.
- **Clear — not chosen:** the west and east wall directions. Their side strips are reachable
  through partition gaps (west: z ∈ [7,10], [0,3], [-10,-4]; east: z ∈ [4,10], [-4,0], [-10,-8]),
  so an opening there would be traversable. They were not selected because they open into side
  strips rather than the main lane and do not give the straight through-corridor of the #275
  pattern. **Operator review of this choice is required** — the "cross"/arm-end phrasing is a
  placement hint, not a verified source-video topology.
- **Blocked candidates:** none. No partition enters any tested doorway or approach sector; the
  only obstruction found at a proposed spot is the visual-only `FarLightPanel` described below.

**Far-light-panel note (operator review required).** The accepted room's `_build_boundaries()`
emits a visual-only `FarLightPanel` at x ∈ [-0.8, 0.8], y ∈ [1.4, 3.4], z ≈ -9.99, which would
cover the centred north doorway. The variant overrides `_build_boundaries()` and deliberately
does not emit that box, so the north opening is visually clear. It has no collider, so traversal
was never blocked. This removes one source-observed terminal surface from the variant only; the
accepted room and its textures are untouched. Appearance is an operator judgement — agents cannot
judge appearance.

## What was done — new files and new versions only

New room folder
`godot_walk/source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/`:

- `room.gd` extends the accepted room's script (accepted file untouched). It overrides
  `_set_candidate_metadata()` and `_build_boundaries()`, opens the two doorways with collider
  returns/headers, omits the far-light panel, and declares both sockets `untested`.
- `room.tscn`, `*.gd.uid`, `test_room.gd`, `capture_room.gd`, `run_capture_guarded.py` — all new.
- `test_room.gd` checks floor support, floor ray, both open doorways below the header, both
  header colliders, both side-wall colliders, the unobstructed central lane, closed west/east
  boundaries, the four inherited partition obstacles, real player traversal through both
  openings, missing-floor/open-boundary negative controls and R reset. As in #278, perimeter
  rays are cast at z = 8.5 (outside every partition z-range) and the player's own collider is
  parked at x = 3 during the doorway ray checks.
- `adaptation_catalog_v1.json` (v3 contract), derived from the operator-accepted base record:
  identity `99bbae061eea29b5a5ecb586ae8caece0bd73613839112ec0e7f3d1b9ba4950a`, bound to the new
  decision by path and SHA-256 `0b267223eaeb78cf160b5fa3df6ef6b141ef1bbaeec6a0852633d6e403d874a7`.
  Its `catalog_snapshot` binding remains the pre-bump `0.9.0` snapshot
  (`0b394553f528517326e3eafa19f81502b320713b0183d80528760fad57453be3`); the new `0.10.0`
  snapshot hash is bound in the admission decision, as in the #275/#277/#278 pattern.
- `catalog_admission_decision.json`: `scope: sockets_declared`, `tested_connector_pairs: []`,
  `layout_eligible: false`, both flags false.
- `module_poetics_v1.json` **draft only** (`draft_mechanical`, poetics empty,
  `untested_sockets: ["north","south"]`, `tested_sockets: []`, `layout_eligible_derived: false`),
  written by the `derive-module-metadata` runner stage. No v2 record and no
  `module_profile_v1.json` sidecar.
- Guarded captures and their manifest/receipt (four 1152×648 PNGs).

Catalog, ledger and library index:

- `catalog.json`: `catalog_version` `0.9.0` → `0.10.0`, exactly ONE appended module entry
  `video_61b91dbeb9026dc7_chevron_cross_corridor_v2_north_south_socket_v1` (two sockets declared,
  `tested_connectors: []`, `layout_eligible: false`, both flags false). A JSON comparison
  confirmed all 17 pre-existing entries and every other top-level field are unchanged.
- New immutable snapshot `catalog_snapshots/godot_psx_room_kit-0.10.0.json`, byte copy of the
  live catalog. SHA-256 `8d125f5108c3962d711ba6cff1da55500c9bffafea62f8aa1c8b2691e370ea94`.
- New library index `library_index/godot_psx_room_kit-0.10.0.json`, built with the existing
  `library_index.py build` stage → module_count 21, pair_count 2, status created. SHA-256
  `d460916c126368c5e19536029387570de2310921225b2fdf98aeda2c0034c613`.
- Registered through the existing path:
  `register_source_room.py video-61b91dbeb9026dc7 --adaptation <new adaptation> --decision <new decision>`
  → `source_manifest-v5.json`, `d58415364755a16caae2225cfac507eb6a8bad749a9bbcd25c80721b7544fa2a`.
- Ledger events through existing runner stages only: `source_ingestion_runner.py
  reconcile-historical video-61b91dbeb9026dc7` → sequence 15 (`historical_decision_reconciled`);
  `source_ingestion_runner.py derive-module-metadata video-61b91dbeb9026dc7 --room-id
  chevron-cross-corridor-v2-north-south-socket` → sequence 16. No event, receipt or hash was
  written by hand. `module_poetics.py derive-all` was not used (it would refuse to overwrite
  frozen drafts).

## Verification commands and exact results

All commands from `/mnt/sharedOs/backrooms-workspace`.

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://…/chevron-cross-corridor-v2-north-south-socket/test_room.gd` | exit 0, `CHEVRON_CROSS_THROUGH_VARIANT_TESTS_PASSED` |
| `python3 -m ruff check …/run_capture_guarded.py` | `All checks passed!`, exit 0 |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}`, exit 0 |
| `python3 godot_walk/scripts/template_validate.py` | `{"valid": true, "source_manifests": 46, "module_profiles": 22, "generative_maps": 68, "errors": []}`, exit 0 |
| `python3 godot_walk/scripts/module_poetics.py validate --index …/godot_psx_room_kit-0.10.0.json` | `draft_count: 21`, overall `valid: false` with 40 errors; **0 errors** for the new variant draft (all errors belong to pre-existing drafts bound to older indices, not edited) |
| `python3 -m pytest -q godot_walk/scripts` | **1574 passed, 5 skipped, 94 subtests passed in 282.45 s (exit 0)** |

Guarded capture command (through `run_capture_guarded.py` only):

```
python3 godot_walk/source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/run_capture_guarded.py \
  --output-dir godot_walk/source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/captures \
  --report godot_walk/source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/capture_room.gd \
  -- --out=res://source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/captures
```

Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=5.152`. The Godot
X11 `NO GRAB` mouse warning is non-fatal. `captures/capture_manifest.json`: four 1152×648 PNGs —
`spawn_toward_north_opening`, `north_doorway`, `south_doorway`, `partition_lane`; mean 9.43 ms /
p95 16.72 ms / p99 100.15 ms over 300 samples. All four files exist and are non-empty. **Appearance
and feel judgements are the operator's; agents cannot judge appearance.** No capture image was
interpreted for acceptance.

`video_adaptation_runner.py validate --bundle` on the new adaptation record is not part of the
task's verification set and, like the #275/#277/#278 pattern records, reports a schema difference
in the hand-authored record (`resolved_adaptation/sockets/0: 'kind' is a required property`); it is
noted here as an honest limitation, not claimed as passing.

## Pending operator-only steps (not attempted)

- Approval of the exact north/south socket placement, including whether the "cross"/arm-end
  hint should instead select the clear west/east side strips, and the omitted far-light-panel
  visual noted above.
- Connector-pair test and approval; no partner or rotation is claimed here.
- `accept-module-metadata` (would write `module_poetics_v2.json`), `decide-integration`, and any
  seeded-map placement. No map was generated or committed.

## Honest limitations

- Passing validators, a green headless room test and a clean guarded capture are not approval.
  The sockets remain declared-but-untested and layout-ineligible by design.
- The variant reuses the accepted room's textures by reference; no texture was copied or edited.
- The catalog entry and admission decision deliberately say sockets are untested and
  layout-ineligible. Reverting the `0.10.0` catalog/index/snapshot and registration would be needed
  if the operator rejects the placement; that was not done unprompted.
- No hash-pinned file was touched. `git diff --name-only` for `godot_walk/scripts/player.gd`,
  `godot_walk/project.godot`, `godot_walk/room_catalog/MATERIAL_LANGUAGE.md`,
  `godot_walk/room_catalog/PALETTES.md`, the accepted `chevron-cross-corridor-v1` room and the
  #275/#277/#278 variant rooms is empty.

## Files changed

Modified: `godot_walk/room_catalog/catalog.json`, `godot_walk/source_library/index.json`,
`godot_walk/source_library/sources/video-61b91dbeb9026dc7/events.jsonl`.
Added: `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.10.0.json`,
`godot_walk/room_catalog/library_index/godot_psx_room_kit-0.10.0.json`,
`godot_walk/source_library/sources/video-61b91dbeb9026dc7/source_manifest-v5.json`,
the new `chevron-cross-corridor-v2-north-south-socket/` room folder (scene, scripts, test,
captures, decision, adaptation, poetics draft) and this report.
