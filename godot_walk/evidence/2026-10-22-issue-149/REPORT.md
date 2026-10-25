# Chainlink #149: Seeded Multi-Room Walkthrough

## Review Status

This is a playable, finite-generation candidate. Mechanical checks pass for seed 149 and the separate #160 regression. The operator has reviewed the walkthrough and confirmed that the stitching concept is sound; seeing the initial column room only once is acceptable for this first pass. New placements, openings, connectors, the branch, and dead ends remain provisional. This review does not promote the candidate or approve arbitrary new topology.

The source footage does not establish the generated adjacencies. The generator authors those connections from registered room modules; it does not recover a floor plan. `registration_accepted=false`, `scale_calibrated=false`, `generation_ready=false`, and `operator_approved=false` remain unchanged.

## What Was Built

`room_catalog/catalog.json` registers the accepted #160 column and pocket modules plus two separate pocket opening variants: pass-through and three-way. Each catalog entry records scene dependencies and hashes, source/authored provenance, visual and collision footprints, socket transforms and dimensions, closures, and approval scope. The catalog snapshot is hash-bound to each serialized layout.

Seed 149 creates a ten-placement tree: one #160 column, six repeated pocket pass-throughs, one three-opening pocket, and two closed-side terminal pockets. It has nine authored links, one north branch, two terminal leaves plus spawn, and no cycles. This is four distinct designs across ten placements; six are repeated instances. The generated walk route traverses the branch and returns to spawn. The result is a long repeated corridor-like layout, not a varied maze.

The exact operator-accepted #160 assembly remains unmodified and is loaded separately by its regression scene. Its accepted scope remains that original column-east to pocket-west pair only. Reusing its column in seed 149 does not imply approval for arbitrary placements or new openings.

The generator supports finite layouts of 10–20 placements, this room/socket family, one three-way branch, two leaves, and no cycles. It rejects loops and layouts outside the configured placement bounds. It does not implement streaming or arbitrary socket types.

## Evidence

- [Contact sheet](contact_sheet.jpg), [layout diagram](layout_seed_149.svg), and [local review page](index.html) contain nine matched 960x540 captures: three exact #160 regression views and six seed-149 candidate views.
- Candidate capture load-to-ready was 2,601 ms; #160 regression load-to-ready was 1,924 ms. These are single-run scene readiness measurements.
- Seed 149: 105/105 route targets reached out and back (290.400 m recorded), floor support fraction 1.0, zero SafetyNet contacts, maximum measured step 0.066674 m, no verifier failures.
- South-branch seed 0: 105/105 route targets reached, floor support fraction 1.0, zero SafetyNet contacts, maximum measured step 0.066674 m, no verifier failures.
- Exact #160 pair regression: 23/23 route targets reached, floor support fraction 1.0, zero SafetyNet contacts, maximum measured step 0.066674 m, no verifier failures.
- The blocked-connector negative control stops the route at the authored blocker (19/105 targets reached). The missing-floor negative produces 4,357 SafetyNet contacts and missing allowed floor support. The exposed-boundary negative records an envelope escape and fails boundary support checks. These are expected failures.
- At 960x540 with the existing Vulkan/URSC rendering path and a 60 FPS cap: 59.886 FPS over 3,659 frames and 61 poses; p95 16.913 ms, p99 22.042 ms. This is not a 1280x720 performance claim.
- Guarded GPU runs recorded peak process RSS of 2.74 GB for captures and 2.43 GB for FPS measurement; peak GPU-memory deltas were 865 MB and 581 MB respectively. The GPU headroom guard passed before both runs. The FPS run took 67.919 s, under its 180 s timeout.
- [Protected hash ledger](protected_hashes.json) re-hashes 53 files from the #160 provenance manifest. All match, including the source footage, #160 bounded visual, and exact assembled walkthrough scene.

## Implementation And Changed Files

- Catalog and serialized contract: `godot_walk/room_catalog/catalog.json`, `godot_walk/room_catalog/layout.schema.json`.
- New candidate/runtime scenes: `godot_walk/scenes/issue149_generated_walkthrough.tscn`, `godot_walk/scenes/issue149_pocket_pass_through.tscn`, `godot_walk/scenes/issue149_pocket_three_way.tscn`.
- Generator, loader, validation, capture, resource guard, hash ledger, and tests: `godot_walk/scripts/issue149_layout_core.py`, `generate_issue149_layout.py`, `validate_issue149_layout.py`, `issue149_generated_walkthrough.gd`, `issue149_pocket_topology.gd`, `capture_issue149.gd`, `run_issue149_gpu.py`, `build_issue149_review.py`, `issue149_protected_hashes.py`, `test_issue149_layout.py`, and `test_issue149_runtime.gd`.
- The shared verifier `godot_walk/scripts/verify_bounded_psx.gd` was extended for generated-scene initialization, repeated-room floor negatives, and blocked-connector negatives.
- Review artifacts and mechanics/resource outputs are under this evidence directory. No #160 scene, source model, collision source, source video, tagged walkthrough, or calibration flag was changed.

## Verification

Python layout tests pass (7 tests); seed 149 and seed 0 serialized layouts validate. Godot runtime contract tests pass for both seeds, including room loading, declared closures, connector thresholds, PSX preset presence, false approval flags, and safe `R` reset. The full route verifier passes for seed 149 and the unchanged #160 pair. Negative controls fail for their intended conditions. The Rust project suite also passes (63 tests); `cargo fmt --check` and `cargo clippy -- -D warnings` pass. GPU capture and capped FPS runs completed inside their timeouts.

The operator review satisfies the walkthrough checkpoint for the stitching proof. It does not admit provisional opening variants, establish source-footage connectivity, calibrate scale/registration, or assert general generation readiness. Keep those states separate in the catalog and runtime metadata.
