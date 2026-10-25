# Chainlink #156: Bounded Streaming for a Seeded Walkthrough

## Review status

This is a playable bounded-streaming candidate built from the serialized seed-149 graph. It streams the current module and its graph neighbors while keeping the rest of the authored finite layout unloaded. Unloaded connected openings receive solid authored caps. It does not add endless generation or recover connectivity from video.

The previously accepted #160 pair and full-instanced #149 walkthrough remain separate regression references. #156 uses the same provisional seed-149 layout and room variants; streaming mechanics passing does not admit those variants or approve new placements. The operator accepted the door-to-door transition as useful additional functionality and directed that this finite bounded-streaming milestone be closed. Generalized expansion beyond the finite graph is deferred to low-priority #162, after the room workflow and approved library mature. Visual approval of the room set remains separate. `registration_accepted=false`, `scale_calibrated=false`, `generation_ready=false`, and `operator_approved=false` remain unchanged.

## Layout and streaming contract

Seed 149 has 10 placements, 9 authored connections, one three-way branch, and 3 terminal ends including spawn. It uses 4 room designs: one bounded column room, six repeated pass-through pockets, one three-way pocket, and two single-opening terminal pockets. It is a finite tree with no loops, not a varied maze. The serialized layout is bound to catalog snapshot SHA-256 `beb756ff8dcb7a4191b7579baf93881c7149de1d4be2ee636047d9d526f367d1`.

The stream window has graph radius 1 and a hard maximum of 4 resident module instances. Backtracking retains detached instances in a cache capped at 4 module types; active plus cached instances are capped at 8. The contract test observed 2 active instances at spawn, 4 at the branch, and 2 after returning to spawn. The return held 3 cached designs and 5 total instantiated rooms. The full route performance run peaked at 4 active and 5 total instances. Frontier openings were capped at spawn, branch, and terminal views.

The loader only supports the current seed layout and its declared socket family. It does not generate new graph topologies, loops, arbitrary connector types, or infinite worlds. A room being resident is not evidence that its artwork or source-video relationship is approved.

## Mechanical evidence

- The full out-and-back physical route completed 4,357 physics ticks across 290.400 m. Floor support was 100%, SafetyNet contacts were 0, and the maximum measured step was 0.066674 m. All route targets were reached.
- Eight boundary pushes stayed supported, with 0 SafetyNet contacts. The trace reported 35 stale contact references on the streamed route as collision objects were unloaded. These references were skipped by the trace collector; the route and support checks still passed. This is recorded as a streaming instrumentation limitation, not silently treated as a clean zero.
- Negative controls behaved as intended: removing the floor caused a fall to lower collision; opening the boundary allowed an escape/fall; blocking a connector stopped the player while floor support remained.
- #149's full-instanced runtime contract still passes independently, as does the #156 window contract.
- Python layout tests: 8 passed. The bounded layout validator passed (10 modules, 9 connections).

## Runtime and resource measurements

The guarded Vulkan performance run measured 450 frames across 15 window transitions at 1280x720 with VSync disabled. Frame intervals were p50 0.273 ms, p95 1.786 ms, p99 1.897 ms, and maximum 4.565 ms. Scene load-to-ready was 2,108.748 ms. The slowest observed window refresh was 12.360 ms when expanding to the four-room branch. Returning to the spawn window with its room types cached took 0.783 ms. These are measurements from this machine and run, not a cross-hardware guarantee.

The GPU/RAM guard passed before both Vulkan runs and found no compute applications. Capture took 3.569 s, with peak process RSS 2.429 GB and GPU memory increase 582 MB. The performance run took 3.269 s, with peak process RSS 2.429 GB and GPU memory increase 558 MB. Godot's shared resource cache may retain imported resources; the explicit bound here is on room instances and active physics/render objects, not a promise that the engine releases every resource allocation on unload.

## Visual review bundle

- [Review page](index.html) and [contact sheet](contact_sheet.jpg): four matched 1280x720 streamed views, each settled for 30 frames.
- [Layout diagram](layout_seed_149.svg): authored finite graph layout.
- Capture locations, resident IDs, caps, camera poses, and settle count are in [capture_manifest.json](capture_manifest.json).
- Streaming transitions are in [streaming_contract.json](streaming_contract.json) and [streaming_performance.json](streaming_performance.json).
- Route and boundary measurements are in [physics_candidate.json](physics_candidate.json); intended failures are in [negative_controls.json](negative_controls.json).

## Integrity and implementation

[protected_hashes.json](protected_hashes.json) verifies 53 inherited inputs from the #160 provenance manifest and 41 catalog dependencies against their expected hashes. It also records hashes for 10 #100/#149/#160 reference assets, including the tagged corridor scene, collision GLB, alignment manifest, `corridor_clean.ply`, the accepted pair scene, and the #149 layout. The #100 PLY is present and hashed; it was not used to construct this streamed layout. Registration and scale flags remain false.

The #156 implementation is concentrated in `issue156_bounded_streamer.gd`, `issue156_streamed_walkthrough.gd`, `issue156_streamed_walkthrough.tscn`, its contract/negative-control/capture/performance scripts, and `build_issue156_review.py`. Shared #149 infrastructure changes add bounded settings to layout generation/schema/validation and register #156 runtime dependencies in `room_catalog/catalog.json`. `verify_bounded_psx.gd` and `bounded_walk_trace.gd` include streaming-aware handling. The worktree already contains unrelated uncommitted project work, so its overall Git status is not an #156-only patch listing; nothing was staged or committed for this report.

## Operator decision

The operator's door-to-door transition feedback is recorded above. The finite bounded-window candidate and its capped unloaded openings are the accepted #156 milestone; the operator directed closure at this scope. Rendering-style iteration is tracked separately in #161. Continued seeded expansion is tracked in deferred issue #162 and must use a sufficiently varied, operator-approved library. This report does not promote the layout, alter the accepted #160 pair, or change calibration/registration state.
