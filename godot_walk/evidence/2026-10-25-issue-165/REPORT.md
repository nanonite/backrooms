# Chainlink #165 — supervised video-to-PSX room transfer

## Result

The frozen adaptation contract was exercised on the already accepted #163/#164
example and one separate playable candidate sourced from
`data/videos/corridor_corner.mp4`. The new room is a bounded, authored L-shaped
PSX corridor with source-cropped wallpaper, floor, ceiling and column
appearance. The operator accepted this exact candidate as a supervised transfer
example, with wall artifacts noted as acceptable for this version. This does
not approve registration, scale calibration, source connectivity or catalog
admission.

Open the [operator-reviewed page](index_reviewed.html), then use the exact
walkthrough command in [COMMANDS.md](COMMANDS.md). The pre-review contact bundle
is preserved as [index_v2.html](index_v2.html). The interactive candidate is
`godot_walk/scenes/issue165_corridor_corner_transfer.tscn`.

## Reusable contract and fixture records

Contract v1.0.0 was frozen before transfer-frame extraction. Its freeze manifest
hash is `e6ccc0971e368e17a736f294ffdff47107b99c4f3dc9a09a555ef6c5b22d9d77`.
The schema, material language, catalog identity and accepted reference record
are pinned by that manifest. The accepted #163 source-textured room and exact
#164 three-room assembly are documented in
[`room-large-v1.json`](../../room_catalog/adaptations/room-large-v1.json).
That record retains the operator's existing decision; this task did not reopen
it.

The new transfer record is
[`corridor-corner-v2.json`](../../room_catalog/adaptations/corridor-corner-v2.json).
Version 2 keeps the same geometry as v1 and adds capsule checks at every
perimeter wall. Version 1, its original dependency fingerprint and its stage
outputs remain preserved. The contract and schema did not change.

## Source observations and suitability

`corridor_corner.mp4` is 1920×1080, 24 fps, 96 frames and 4 seconds long;
SHA-256 `51abd379f94b8f84799c79927113f37c03014b41b0d5f0d4c23095d3d67587e0`.
It is meaningfully different from accepted `room_large.mp4`, but it is
synthetic and was previously seen during the capture-gate inventory. It is not
a pristine unfamiliar holdout. The CPU-only local-video inventory found no
better unfamiliar fixture; familiar `corridor_travel.mp4` was kept as
regression evidence. Suitability is recorded as
`proceed_with_limitations`.

The source frames were decoded directly at original resolution with no resize
or image edit. Selected one-based frame IDs and timestamps are:

| Frame | Time | Direct observation |
|---|---:|---|
| `0001` | 0.000 s | Wallpaper, carpet-like floor, ceiling grid, box-like column and an open view into a larger partitioned space. |
| `0013` | 0.500 s | Same broad room and column; transient bright ceiling streaks are visible. |
| `0036` | 1.458 s | Column and room context coexist with a long hallway view; ceiling artifacts remain. |
| `0059` | 2.417 s | Hallway-side perspective with a wall turn and the larger space visible beyond; continuity is not established. |
| `0085` | 3.500 s | Long straight corridor with repeated ceiling lights and wallpapered sides. |
| `0096` | 3.958 s | Another corridor perspective; hidden continuation remains outside the clip. |

The original decoded frames, extraction manifest, source-frame contact sheet,
crop bounds and hashes are in `source_frames/`, `source_textures/`, and
`source_reference_contact_sheet_v2.jpg`. The four appearance crops are exact
rectangular pixels from frame `0001`: wallpaper `[100,390,510,650]`, floor
`[120,820,520,1035]`, ceiling `[100,0,520,220]`, and column `[555,300,710,720]`.
They are not Gaussian renders or screenshots of an authored room.

Unresolved source facts include metric scale, camera registration, complete
room boundaries, the exact column footprint and hidden faces, the hallway's
connection to the initial room, and all off-camera continuation. The bright
ceiling streaks and changes in surface appearance are visible in the synthetic
source; their intended meaning is unknown. Source frames are context anchors,
not matched camera poses.

## Adaptation choices

The room is deliberately a game-design proposal rather than a recovered floor
plan. In local uncalibrated design units it has a simple orthogonal footprint
`[(-6,-2),(0,-2),(0,-7),(4,-7),(4,2),(-6,2)]`, floor elevation `y=0`, ceiling
height `3`, and safe player origin `(-5,0.6,0)`. The standard player capsule is
radius `0.3`, height `1.2`; `R` resets to spawn and clears velocity.

Geometry origin, appearance origin, placement basis and collision origin are
recorded independently. Walls, floors, ceilings and all six closed boundaries
are authored. Four floor/ceiling slabs form the L union; a single observed
column receives a complete authored four-sided box and a separate matched
collider. One direct source crop is repeated on the column faces. Its lighting
and pale-base variation produces visible bands, so review that mapping as part
of the new candidate. The source-visible opening remains an observation only;
it is not an open socket in this scene. All perimeter edges are capped and no
connector is claimed or tested.

The existing Godot 4.6.3 controller, `library-psx-ursc-1.5-native-compositor`
profile and current project render settings are used. The conservative rendered
AABB is `min=(-6.08,-0.08,-7.08)`, `max=(4.08,3.08,2.08)`. It encloses all 16
rendered meshes; no background geometry or escaped mesh was found. The
spawn-connected capsule-clear sample is estimated at 44.99 uncalibrated design
units squared. It is not a physical area measurement.

## Mechanical and visual checks

The v2 contract test confirms safe reset, zero velocity after reset, all six
visible perimeter boundaries with separate capsule-blocking colliders, clear
supported approach poses, four clear supported column approaches, a matching
column visual/collider size, and render-envelope containment. Each boundary
approach passed and each wall query blocked the full player capsule. Removing
the column collider made the center capsule query open, as expected for the
obstacle negative control.

The standard bounded route verifier passed its 11 out-and-back waypoints over
25.60 design units. Floor support was 100%, SafetyNet contacts were zero, and
the maximum recorded step was 0.0667 design units. Eight directional boundary
pushes from the spawn-side probe stayed supported and inside the shell. Removing
the east boundary caused escape and the expected gate failure. Removing the
walkable floor caused loss of configured floor support and the expected gate
failure. These negative controls are not treated as candidate failures.

This applies the boundary/column separation raised in #159: visible room limits
and their colliders are both authored and checked, while hidden source surfaces
remain unknown. The relevant workflow suite passed (7 tests), and Godot 4.6.3
accepted the capture script's parse check. The test summary is in
`tests/workflow-test-summary.json`.

Nine Vulkan captures at 1280×720 cover the room entry, turn in both directions,
far leg in both directions and all four column sides. The paired comparison
sheet places each selected source frame next to a candidate view, explicitly
labeled as an unregistered perspective comparison. The review page also links
the source sheet, candidate sheet and authored layout diagram.

## Runtime and resources

The capture reported scene-ready time of 44 ms. The uncapped render sample
covered 14 camera poses and 4,199 frames at 1280×720:

| Measure | Result |
|---|---:|
| Average render rate | 239.86 FPS |
| p95 frame time | 5.254 ms |
| p99 frame time | 5.527 ms |
| Capture-process peak child RSS | 523 MiB |
| Capture GPU-memory increase over desktop baseline | 268 MiB |
| Performance-process peak child RSS | 522 MiB |
| Performance GPU-memory increase over desktop baseline | 235 MiB |

The captures and frame-time run used the existing GPU/RAM guard, policy version
2.1.0. It reported no compute applications, about 9.9 GiB free VRAM and about
16.8 GiB available RAM before capture. These frame results are machine-specific
render measurements, not an operator walkthrough or a 60-FPS cap test.

## Shared tooling changes and limits

Two shared workflow fixes were recorded separately from candidate art:

- Stage receipts are now scoped under their adaptation ID. This prevents
  receipts for the transfer candidate from making the accepted reference record
  appear stale. Earlier unscoped receipts are preserved as historical evidence.
- GPU process checks now resolve the executable behind `nvidia-smi` process
  entries before applying the existing explicit desktop-app allowlist. This
  handles truncated `snapd-desktop-integration` and command-line flags on
  Discord without relaxing the compute-job, Hunyuan, QEMU or unknown-process
  blocks. Policy version 2.1.0 appears in resource reports.

The operator reviewed and accepted the exact v2 candidate as a supervised
transfer example, noting that visible wall artifacts could be cleaned up but
were acceptable as is. The decision is bound to the candidate fingerprint in
[`operator_review.json`](operator_review.json). This accepts the example for
the supervised workflow; it does not admit a reusable room module or approve
scale, registration, source connectivity, stitchability, or unattended
ingestion. `registration_accepted=false` and `scale_calibrated=false` remain.

## Operator review

The operator accepted the bounded L-turn as the supervised transfer example.
They noted wall artifacts could be cleaned up but accepted the current result.
No separate connector, registration, scale, or reusable-module approval was
given.

## Evidence paths

- [operator-reviewed page](index_reviewed.html)
- [pre-review bundle snapshot](index_v2.html)
- [operator decision](operator_review.json)
- [paired source/adaptation sheet](source_vs_adaptation_contact_sheet_v2.jpg)
- [candidate contact sheet](adapted_room_contact_sheet_v2.jpg)
- [authored layout proposal](authored_layout_proposal_v2.svg)
- [v2 adaptation record](../../room_catalog/adaptations/corridor-corner-v2.json)
- [v1 adaptation record, preserved](../../room_catalog/adaptations/corridor-corner-v1.json)
- [commands](COMMANDS.md)
