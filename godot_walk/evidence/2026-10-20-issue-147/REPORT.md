# Chainlink #147: Bounded Later-Bay Candidate

**Status:** standalone candidate built; operator review accepts it as a base for further room-design iteration. It is not admitted to the reusable catalog, is not stitched to the tagged reference zone, and is not a recovered room plan. `registration_accepted=false`; `scale_calibrated=false`.

## Source And Scope

The cataloged #100 video is 1920x1080 at 24 fps, 192 frames, duration 8 seconds, SHA-256 `ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4`. Issue #145 identifies frames 0085-0192 (3.500-7.958 s) as a later repeated-column-bay visual reference. This is a continuous camera sweep, not evidence of a separate room count, exact room extent, or a connection to the tagged zone.

The Hunyuan input is frame 0152 at 6.291667 s, extracted directly from the source video at 1920x1080 with no crop or resize. Its registered JPEG hash is `94b2643eee79583a1b3d4f0151577dc87e4cd37b3639c947edcb5396c15f5b12`; the direct PNG extraction hash is `4846fcf6f510017f02e67f12d9dd71ab2dc1cd0a71bc4750ab1956fb60a4a7ad`. The direct PNG and the original Panogen seed are pixel-identical (ImageMagick absolute-error count 0); the Panogen seed file hash is `fd165eeb0c2d5a14101f2314290feedcc44aeb73148b9d1272fa52d26f819401`.

No model inference was run for #147. This candidate reuses the existing local Track-A Panogen/SceneGen result, whose run manifests are copied here and hash-checked by `module_manifest.json`. Panogen used measured FOV 75.93466 degrees, 1280x640, 50 steps, guidance 30, true CFG 1, seed 42. SceneGen used `indoor`, foreground label `columns`, seed 42, FP8, sequential offload. The pinned HunyuanWorld commit is `57fa9f3a79eae1079c279968cdb9d82c75fa7c86`.

Visual conversion produces 15,383,468 triangles across two non-watertight visual-only layers. Their source PLY hashes are recorded in `hunyuan_conversion.json` and `scenegen_manifest.json`; the combined Bevy GLB hash is `5b3e879c0309448887cd3ceb7b29eaca49476566ac75010f7e5c5253443a23bf`. These visual meshes are never used as collision.

## Authored Candidate

All walkable/collision surfaces are authored and separate from the source-derived visual GLB:

- A planar annular floor with 0.8 m lane width, 16.59 m2 area, 3.3 m centerline radius, and 20.73 m centerline circumference.
- A conservative column obstacle proxy based on visible column bases in frames 0137 and 0141, within the #145 reference range.
- Continuous inner and outer collision boundaries, each 1.4 m high and 0.08 m thick.

The floor has 512 triangles, the column 12, and the two boundary meshes 4096 combined. The collision GLB hash is `1b7a15bed5cd59e3b2812b479e995e34050e891ae828aff55f5d5cb941f3ad6e`. These dimensions are a bounded playable proposal in the uncalibrated #100 convention, not measured room dimensions. No opening is declared a connector.

`candidate_layout.svg` plots only those authored surfaces and the registered frame-0152 camera pose under the same unaccepted convention. The camera marker falls just outside the proposed lane. It is the source camera's reference position, not a point on the playable route or a place the player can stand; the mapping and scale remain unaccepted.

## Mechanical Results

The CPU-only shared-controller suite passed in 28.51 s with 137,976 KiB peak RSS. Outbound progress was 1.0, inbound progress 0.992126, moving support 0.99924, maximum vertical step was 0.001385 m against the 0.2 m gate, and the route recorded zero SafetyNet contacts. The column probe was blocked at 0.2167 progress as intended. All 18 lateral pushes against the inner/outer boundaries passed; maximum offset was 0.11709 m against a 0.12 m limit.

The initial 0.9 m lane failed the lateral-offset gate at about 0.15 m. Its preserved files are `authored_route_collision.glb`, `route_report.json`, and `walkability_report_initial_lane_0.9m.json`; these are not the current candidate. The successful 0.8 m candidate uses `authored_route_collision_v2.glb`, `route_report_v2.json`, and `walkability_report.json`. Three malformed-asset controls (floor, column, or boundaries removed) were rejected by the required-node integrity gate before simulation. The shared wide-hole and open-ledge physics controls also passed in their expected negative outcomes. See `negative_control_summary.json` for the distinction.

## Visual And Runtime Evidence

The CPU visual-query/alignment run did not complete within its 300 s timeout, so no visual-to-collision alignment metric is claimed. The final hash-verified Bevy/Vulkan capture completed 17 views at 960x540 in 37.71 s. Preflight measured 18,219,200 KiB available RAM and 10,710 MiB free VRAM, above the 10 GiB/4096 MiB floors; there were zero active GPU compute processes. Capture peak process RSS was 7,886,484 KiB. `collision_loaded=false` in the capture report is intentional: these are source-visual-only review renders.

The Bevy frame-0152 view is softer than the direct source and shows loss of detail; the panoramic output has visible ceiling arcs. The contact sheets show all sampled headings and the direct-frame-to-panorama-to-Bevy progression. These are observations for operator review, not an automatic visual-quality pass. A timed live-app launch confirmed the visual and collision assets became ready, but reported zero measured frame intervals, so no FPS or manual-walk claim is made.

## Operator Review

Operator review (2026-10-20): the generated Bevy walkthrough is a good-enough room to continue iterating on. The apparent ends of the room are not yet reachable by walking; improving the room ends is a design task for a later iteration. The far side of the column also remains incomplete and should be developed. This review accepts the candidate as an iteration base only; it does not accept its registration, scale, full room extent, or connection to the tagged reference zone. Keep it out of the reusable catalog and do not start stitching until those separate questions are resolved. Room count, unobserved areas, scale, opening/connector status, and connection to the tagged reference zone remain unknown.
