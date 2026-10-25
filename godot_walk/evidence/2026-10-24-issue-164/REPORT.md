# Issue 164 — three-room authored connection prototype

**Status:** mechanically validated and operator accepted for this exact seed-164 assembly. The accepted connection is an input-specific workflow example, not a generic connector or evidence of source-video connectivity. The initial candidate serialization and catalog snapshot are preserved unchanged; [operator_review.json](operator_review.json) records the later decision.

## Review bundle

- [Review page](index.html)
- [Contact sheet](contact_sheet.jpg)
- [Layout diagram](layout_three_room.svg)
- [Reproduction commands](COMMANDS.md)
- [Serialized layout](layout_three_room.json)
- [Catalog snapshot and dependency hashes](catalog_snapshot.json)
- [Physics and resource evidence](mechanics/)
- [Operator review record](operator_review.json)

The first two contact-sheet views show the new doorway looking from the pocket into the third room and back. The other views show the room entrance, hall, and authored column. Captures are 1280×720 using Godot 4.6.3, Vulkan, and the existing PSX profile.

## What changed

The Godot catalog now contains a versioned standalone wrapper for the accepted #163 room and a separate provisional connector adapter. The original #163 scene remains closed at its hallway end and unchanged. The adapter inherits the accepted authored source-textured room, shifts its room children to the library floor elevation, and replaces only the far hallway cap with two textured side returns and a header. The visuals and colliders share the same 2.0×2.1 design-unit opening. No Hunyuan output is loaded or claimed.

The finite seed-164 layout visits three distinct designs in a chain:

| Instance | Design | Placement | Review state |
|---|---|---:|---|
| R000 | Accepted #160 bounded column room | `(0, 0, 0)`, yaw 0° | Accepted as part of the #160 pair |
| R001 | #149 pocket pass-through | `(3.5, 0, -3.8)`, yaw 0° | Existing provisional variant |
| R002 | Accepted #163 source-textured room, connector adapter | `(22.56, 0, 3.1)`, yaw 180° | Baseline accepted; adapter accepted in this layout |

The column-to-pocket pair is the already accepted #160 regression. The pocket-to-third-room connection is new authored geometry; the operator accepted this exact connection as coherent and walkable from both directions. Its 2.0-wide, 2.1-high opening has 1.2 design units of approach clearance and aligns to the pocket socket at floor elevation `-1.27099049`. The third-room standalone baseline remains at its original floor elevation and retains its closed cap. The approval does not generalize the connector to other inputs.

Frame 0013 directly shows the room and a passage, but does not establish where that passage leads. The room placement and the new far-end hallway connection are authored game-layout choices. `registration_accepted=false` and `scale_calibrated=false`; dimensions in the catalog are design-space measurements and are not accepted as real-world scale.

## Traversal and controls

The standalone #160 column, pocket, and #163 room baselines each completed their route out and back with no failed route segment, full floor support, and zero SafetyNet contacts. The assembled route also completed all 33 out-and-back waypoints across both connections:

| Test | Route distance (design units) | Floor support | SafetyNet contacts | Result |
|---|---:|---:|---:|---|
| #160 column standalone | 20.13 | 100% | 0 | Pass |
| Pocket standalone | 53.60 | 100% | 0 | Pass |
| #163 accepted baseline standalone | 35.73 | 100% | 0 | Pass |
| Three-room assembly | 75.60 | 100% | 0 | Pass |

The assembled trace records support from the column floor, third-room floor, and both connector thresholds. Safe spawn/reset and the module/socket contract pass in `test_issue164_runtime.gd`. Focused physics controls pass: the open doorway clears the capsule and a temporary blocker stops it; removing the floor enables a fall path; removing the west boundary permits escape; and the third-room column collider blocks an approach. The original #160/#149 scenes and snapshots were not modified.

## Render and resource measurements

The existing GPU/RAM guard passed before both Vulkan runs. It reported no compute applications, about 9.62 GiB free VRAM before headroom for the captures, and about 15.24 GiB available system RAM.

| Measurement | Capture bundle | Uncapped performance run |
|---|---:|---:|
| Scene ready | 2.575 s | — |
| Process elapsed | 5.175 s | 37.841 s |
| Child peak RSS | 2.423 GB | 2.426 GB |
| GPU memory above desktop baseline | 0.569 GB | 0.597 GB |
| GPU frame rate | — | 239.87 FPS average |
| Frame time | — | p95 4.303 ms; p99 4.351 ms |

The performance run sampled 25 poses and 7,499 rendered frames at 1280×720 on an NVIDIA RTX 4070 Ti with Vulkan. It was uncapped; the observed rate depends on this machine and display configuration. A preliminary short-sample run used the legacy script's `--capped` option, which only reduces frames per pose and does not cap runtime FPS. The uncapped run above is the reported result.

## Integrity and verification

The catalog snapshot records SHA-256 hashes for the module scenes, scripts, source frame, source textures, collision/profile dependencies, and runtime. The layout has its own canonical digest and sidecar. The #163 source frame and manifest hashes are `b75558f5…842ae` and `e8d7d51a…40152`. All 73 protected #149/#160/#163 reference files match their starting hashes; both registration and scale flags remain false.

Passed: twelve Python layout tests (eight #149, four #164); Python schema/hash validation; Godot #149 runtime and #160 room-contract regressions; #164 runtime contract; standalone and assembled route/boundary checks; physics negative controls; Ruff and Python syntax checks. See [COMMANDS.md](COMMANDS.md) for exact commands and output paths.

## Operator review outcome

The operator confirmed that the doorway feels coherent and walkable, and identified this assembly as the target for a workflow that can process other input videos. The layout JSON keeps its original `review_pending` value as generated; the later approval is recorded separately in `operator_review.json`. Registration and scale remain unaccepted.
