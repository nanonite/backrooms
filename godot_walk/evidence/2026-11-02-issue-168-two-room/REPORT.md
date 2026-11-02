# Issue 168 — accepted two-room connection

## Review status

The standalone debris/window rock-room design was previously accepted for candidate identity `016fab6e6cc1edff5088bb6da3b81fdf0d8bca5bdabb70b62cb11476cc9f8214`. After reviewing this two-room walkthrough, the operator accepted the exact assembly and doorway for candidate identity `6b83313eb701f9c1a212087ab41b27e85c6ada90f5a5bf1b37b9834533402bff` (“yup looks good to me!”). The decision is recorded in `operator_review.json`; `adaptation_accepted_v1.json` preserves the same candidate identity and binds that decision artifact. The pair and its two socket adapters are admitted in catalog snapshot 0.4.0, scoped to this exact placement. The original accepted rooms, pending candidate, and catalog snapshots 0.2.0 and 0.3.0 remain unchanged. Read-only hashes for the protected source, assets, records, and snapshots are in `protected_inputs.json`.

## What is connected

The accepted industrial hall from #167 and the reviewed debris/window rock room are placed as adjacent rooms. Two new versioned wall adapters open the hall's south wall and the rock room's north wall. The socket centers meet at world `z=6.5`; both floors are at `Y=0`; outward normals oppose. The clear opening is 2.4 by 2.2 authored design units. A shared visual frame and a separately collidable floor-seam plate make the 0.6-unit double-wall depth read as a short doorway passage. Remaining outer walls stay closed. Standalone adapter scenes default to capped sockets and include their own player.

This is authored game geometry. The source samples show the industrial hall at frame_1097 (36.533333 s) and debris/window views around frame_4560 (151.966667 s); the footage does not establish their adjacency, scale, or connectivity. The rock shapes remain an authored interpretation, not a direct observation. The exact source seed, attempt-006 panorama, and original accepted #167/#168 room assets are preserved.

## Verification

Godot 4.6.3 headless checks passed for both standalone adapters and the assembly: safe spawn/reset, supported floors, capped standalone sockets, closed perimeter probes, 25 capsule-clear samples along the full doorway approach, aligned socket centers and opposing normals, header/side collision, continuous seam-floor rays, and render-envelope containment (zero escaped meshes). The player crossed from hall to rock room and back; reset restored the safe spawn. Blocked-connector, missing-floor, and open-boundary negative controls all detected their injected faults. The same suite was rerun after approval; `mechanics/approval_runtime_check.json` is the additional receipt. Its `candidate_status` field is the runner's historical label; acceptance is bound by the separate operator decision and accepted adaptation record.

The guarded Vulkan capture ran at 1152×648 under a 60 FPS cap with VSync disabled. Scene ready/build took 63.16 ms. Across 300 process-frame intervals after 120 warmup frames, mean was 16.664 ms, p95 16.752 ms, p99 16.807 ms. Peak child RSS was 559,747,072 bytes; peak GPU memory was 680,525,824 bytes, an increase of 181,403,648 bytes from the run's start. The guarded run completed in 8.04 seconds. The GPU guard found no competing compute app and recorded its RAM/VRAM headroom before capture. These are bounded capture measurements, not a long gameplay stress test.

`mechanics/traversal.json` and `mechanics/approval_runtime_check.json` are the Godot traversal receipts. `captures-v3/capture_manifest.json` and `capture_resource_run_v3.json` record the matched captures and resource measurements. `adaptation_candidate.json` remains the preserved pre-review record; `adaptation_accepted_v1.json` binds the operator decision to the identical candidate fingerprint and dependency hashes. The read-only adaptation validator passes for the accepted record. The scoped catalog admission is recorded separately in `catalog_admission_decision.json` and catalog snapshot 0.4.0, so the earlier candidate fingerprint and frozen catalog binding are not rewritten. Source manifest v3 records the accepted room and pair while preserving the exact v2 predecessor. Static consistency validation does not replace the runtime evidence above.

## Limitations

- The doorway is a single authored connection. It does not establish a source-video connection or general room-stitching rules.
- Catalog admission is limited to the standalone rock room as used here and this exact tested hall-south/rock-north pair. Both socket adapters are pair-only; neither is eligible for arbitrary layout generation.
- The combined room bounds and socket dimensions are uncalibrated design units. `registration_accepted=false` and `scale_calibrated=false` remain unchanged.
- The candidate uses two existing room designs and two new wall adapters plus one shared connector; it does not demonstrate arbitrary socket matching, branching, or automatic generation.
- Active authoring time was not measured. The connector is a manual adaptation.
- The capture harness has overwrite refusal. Its first attempt stopped before producing images because it did not create the destination directory; that failed guarded receipt is preserved. The successful v3 run creates the directory before capture.

## Operator decision

Accepted for this exact two-room walkthrough and connector pair. The source video does not establish adjacency, calibrated dimensions, or further connectivity. Registration and scale calibration remain false.
