# Chainlink #148: Catalog Admission And Authored Connection

**Status:** Three separate catalog modules are recorded. The tagged Hunyuan zone and #150 baseline remain unchanged; a new early-pocket module and an explicitly authored connector adaptation now form a reviewable proposal. The proposed connection passes the bounded walkability checks, but it is not a connection recovered from the footage. Keep #148 open for operator review.

## Decision And Provenance

The #145 inventory's opening candidate C is visible in source frames 0013-0027 (0.5-1.083 s): a broad doorless gap between patterned partition ends, with darker wall/floor visible beyond. The recorded camera does not establish crossing its threshold, the destination, a separate room, or a hallway. These frames are visual inspiration only. No source connectivity, room count, registration, or metric scale is inferred.

The new early-pocket is a **fully authored proposal**, using the #100 uncalibrated convention. It is a closed 6.0 x 13.8 m standalone shell with its own floor and four wall colliders, no column, and simple Backrooms-inspired authored visuals. The separate assembly adaptation places it east of #150 and adds a 3.5 m-long hall with two 2.4 m-wide by 2.4 m-high openings. Those dimensions, placements, walls, sockets, and connector are game-design choices, not source-video facts. The standalone room stays closed at its west wall; only the assembly adaptation opens the sockets.

`registration_accepted=false` and `scale_calibrated=false` remain unchanged for all three catalog entries. The tagged reference remains unconnected. #150's original visual and collision assets are preserved; the assembly uses separate collision and review-visual assets.

## Module And Connection Checks

All route checks use the shared Bevy 0.18 / Avian 0.6 / Tnua 0.31 player profile, run CPU-only, and are recorded in the JSON reports.

| Candidate | Result | Out / return | Moving support | Collision nodes | Suite time / peak RSS |
|---|---:|---:|---:|---:|---:|
| Tagged reference | Pass | 100% / 99.21% | 99.9126% | 4 | 1.819 s / 61,212 KiB |
| #150 standalone baseline | Pass | 100% / 99.51% | 99.9613% | 6 | 1.667 s / 52,616 KiB |
| Early-pocket standalone | Pass | 100% / 99.40% | 99.9526% | 5 | 0.882 s / 52,200 KiB |
| #150 + authored connector + pocket | Pass | 100% / 99.22% | 99.9369% | 7 | 0.927 s / 52,672 KiB |

The connector has a 2.4 m clear opening and 2.4 m authored height; the route crosses a continuous, single-mesh planar floor at the existing convention height. Its maximum sampled vertical step is 0.0032 m, below the 0.2 m gate. The 1,585-tick route is supported on 1,584 moving ticks, has no SafetyNet contacts, and passes the #150 column-block and four exterior-boundary push checks. This verifies the authored collision layout, not physical measurements of the source space.

Two negative controls fail closed: a wall across the connector blocks traversal (9.375% outbound progress); removing the connector floor fails route progress and drops moving support to 79.25%, with a SafetyNet contact. Reports and source GLBs are listed in the catalog and `early-pocket/REPORT.md`.

## Visual And Resource Evidence

The eight-view Vulkan contact sheet shows the existing #150 column, authored threshold, hall, and pocket from both directions. It is a flat-color shell study with patterned wall strips, a grid ceiling, and a brown floor. It does not use the source texture, Hunyuan mesh, or Gaussian splat; it is not a final art pass.

The CPU scene report for the standalone pocket records 7.596 s total, 7.154 s route simulation, 129,932 KiB peak RSS, 2.557 ms mean / 3.480 ms p90 / 8.386 ms max app-update time, 0.0040 s visual load, and 0.0006 s query preparation. The assembled CPU scene records 5.145 s total, 4.693 s route simulation, 130,848 KiB peak RSS, 2.103 / 2.271 / 4.801 ms update times, 0.0040 s visual load, and 0.0013 s query preparation. The four GLB visual triangles are the floor/ceiling mesh layers; patterned shell surfaces are spawned from the authored boxes in the route report. These CPU values are not an FPS benchmark.

The Vulkan capture was guarded by a GPU/RAM preflight and a timeout. It produced eight 960x540 views in 4.646 s with 826,876 KiB peak RSS; zero compute jobs were active at start, with 10,314 MiB free VRAM. Capture report says collision was not loaded for rendering. No inference or training ran.

## Review Files

- [Authored assembly plan](early-pocket/authored_assembly_layout.svg)
- [Eight-view assembled contact sheet](early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg)
- [Early-pocket module report](early-pocket/REPORT.md)
- [Capture report](early-pocket/generated/captures/assembled_connector/bevy_capture_report.json)
- [Issue 148 catalog entries and hashes](../../../splat_walk/room_catalog/catalog.json)
- [Reproduction commands](COMMANDS.md)

## Verification

The catalog validator accepts all three modules. `cargo test` passes 63 tests; `cargo fmt -- --check`, `cargo clippy -- -D warnings`, and `git diff --check` pass. The tagged reference, #150, standalone pocket, and assembled proposal pass their independent CPU route checks; both authored connector negative controls fail closed as expected.

Review the proposed room arrangement and walk it using the command in `early-pocket/REPORT.md`. The connection is authored and tested, while footage connectivity remains unknown. No files outside #148's implementation/evidence, the catalog, and the shared harness compatibility fix were changed by this work. Do not close #148 until the operator has reviewed the assembled walkthrough.
