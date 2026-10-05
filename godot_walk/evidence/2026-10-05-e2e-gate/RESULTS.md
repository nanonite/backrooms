# Results — end-to-end acceptance gate (#91)

All results measured 2026-10-05 (UTC) on the host in `ENVIRONMENT.md`.
Logs are under `logs/`; screenshots under `screenshots/`.

## Tolerances, set before scoring

These are the tolerances the pipeline's own contracts define; #91 scores against
them rather than inventing new ones.

| Domain | Quantity | Tolerance | Source |
|---|---|---|---|
| Alignment | PLY→Godot effective mapping | equals manifest; GDGS −180° Z correction fired 0× | `verify_alignment.gd`, `alignment_manifest.json` |
| Alignment | Floor→ceiling clear height | 2.40 m declared (chosen scale; raw 0.46798 ± 0.00937 units) | `alignment_manifest.json` |
| Alignment | Reconstruction camera eye height | 1.153 m mean; cameras inside room | `alignment_manifest.json` |
| Alignment | Rendered splat AABB | matches manifest `full_min`/`full_max` to 4 decimals | `verify_alignment.gd` |
| Alignment | Metric scale | `chosen`, not measured (synthetic footage) | `scale_reference.kind` |
| Collision | Walkway covers camera path | ≥ 90 % navigable at 1.00 m | `traversability.py` |
| Collision | Floor support under camera path | 100 % | `traversability.py` |
| Collision | Walls block | ≥ 80 % of splat-obstructed columns solid | `traversability.py` |
| Collision | Openings preserved | ≥ 90 % precision | `traversability.py` |
| Collision | Mesh watertight / normals | 0 boundary edges; normals face walkable | `traversability.py` |
| Physics | Capsule | r = 0.30 m, h = 1.20 m | `player.tscn` |
| Physics | Required clearance | 1.25 m (capsule + 0.05 m) | `traversal_manifest.json` |
| Physics | Position / step / block-stop | 0.18 m / 0.20 m / 0.12 m | `traversal_manifest.json` |
| Physics | Floor support per leg | ≥ 95 % of ticks | `traversal_manifest.json` |
| Physics | Spawn drop | ≤ 1.00 m | `traversal_manifest.json` |
| Physics | SafetyNet | **zero** contacts and never stood on | `traversal_manifest.json` |
| Performance | Walking frame rate | 60 fps target at 1280x720 (vsync-capped) | `HARDWARE_BUDGET.md` |
| Resumability | Stage C nondeterminism | splat count ±5 %, camera positions ±0.01 m | `README.md` §Nondeterminism |
| Resumability | Stages A/B/D/E/F | byte-identical | `README.md` §Nondeterminism |

## Results table

| # | Check | Fixture / asset | Result | Evidence |
|---|---|---|---|---|
| 1 | Real textured single-room capture available | — | **ABSENT** | `FIXTURES.md` §1 |
| 2 | Difficult low-texture real capture available | — | **ABSENT** | `FIXTURES.md` §1 |
| 3 | Synthetic corridor/column-orbit input available | 7 clips | PRESENT | `FIXTURES.md` §2 |
| 4 | Capture gate — eligible synthetic inputs | `room_large`, `corridor_x`, `dead_end` | ACCEPTED_WITH_WARNINGS | `logs/gate_*.txt` |
| 5 | Capture gate — rejected synthetic inputs | `corridor_straight`, `corridor_corner`, `corridor_t`, `corridor_travel` (column orbit) | **REJECTED** | `logs/gate_*.txt` |
| 6 | One-command pipeline, fresh | `room_large` (50 frames) | **FAIL at Stage B** — `glomap not found`; VGGT fallback crashes on `images/frames.json` | `logs/pipeline_room_large_fresh.log` |
| 7 | One-command pipeline, resumed (VGGT glob worked around) | `room_large` | **FAIL at Stage B** — VGGT `CUDA out of memory` (peak GPU 11 757 MiB) | `logs/pipeline_room_large_resume.log` |
| 8 | One-command pipeline, fresh+resume | `corridor_x` (31 frames) | **FAIL at Stage B** — VGGT `CUDA out of memory` (peak GPU 11 805 MiB) | `logs/pipeline_corridor_x.log` |
| 9 | Documented prerequisite install | GLOMAP 1.2.0 via `nix develop` | **FAIL** — `cmake` configuration incomplete (`FindDependencies.cmake`) | `logs/glomap_install.log` |
| 10 | Calibrated alignment (#83/#74) | existing `corridor_splat` | PASS (contract + rendered AABB reproduce) | `screenshots/`, `../2026-10-05-gdgs-alignment/` |
| 11 | Generated collision (#84) — self-consistency | existing `corridor_splat` | 9 / 10 checks PASS; **`walkway_covers_camera_path` FAIL (20.3 % < 90 %)** | `scripts/splat_pipeline/collision_benchmark.json`, `COLLISION.md` |
| 12 | Production-controller physics (#85) | existing `corridor_splat` | PASS (exit 0) | `logs/verify_traversal.log` |
| 13 | Real-GPU visual inspection | existing `corridor_splat` / `corridor.tscn` | PASS — 4 non-blank PNGs; AABB `pos=(-97.7875,-62.1061,-101.8175) size=(139.4696,97.0061,134.5244)` | `logs/screenshot_corridor.log`, `screenshots/` |
| 14 | Render frame rate, walkable scene (orbit probe; the #85 walk itself is headless) | `corridor.tscn` @1280x720 | **58.94 fps** (182 569 splats; stage VRAM 0.28 GiB, RAM 0.63 GiB) | `logs/render_benchmark_corridor.log` |
| 15 | Resumability / input invalidation | stubbed integration | PASS (4 tests) | `logs/pytest_integration.log` |
| 16 | Downstream verifier unit tests | collision / traversal / splat_frame | PASS (155 tests) | `logs/pytest_collision_traversal_frame.log` |

## #85 walk detail (fresh run, exit 0)

```
spawn: floor -1.1430 m, capsule bottom -1.1430 m, drop -0.0000 m, headroom 2.150 m (need 1.250 m)
route_outbound: 15 legs, 6.60 m, floor support 100.0 %, max step 0.067 m
boundary_out:   15 legs, 6.99 m, floor support 100.0 %, max step 0.072 m
low_clearance:  cell [28, 27], headroom 1.900 m, floor support 100.0 %
boundary_back:  15 legs, 6.88 m, floor support 100.0 %, max step 0.073 m
route_inbound:  15 legs, 6.44 m, floor support 100.0 %, max step 0.067 m
probe column:   ran 1.09 m, stopped 0.067 m from the planned face (tol 0.12 m)
probe wall:     ran 1.40 m, stopped 0.119 m from the planned face (tol 0.12 m)
OK: traversal verified -- route both directions, blocking, openings, corners,
    clearance, spawn and safety net all hold
```

Zero SafetyNet contacts; four deliberately broken negative scenes each fail for
their stated reason (same log).

## Peak resource use (pipeline attempts)

| Run | Elapsed | Peak GPU (MiB) | Peak RAM (MiB) | Outcome |
|---|---|---|---|---|
| `room_large` fresh | 31 s | 7 428 | 30 899 | FAIL Stage B (frames.json) |
| `room_large` resume | 17 s | 11 757 | 29 033 | FAIL Stage B (VGGT OOM) |
| `corridor_x` fresh+resume | 45 s | 11 805 | 33 362 | FAIL Stage B (VGGT OOM) |

Raw 1 Hz samples: `logs/*resources.log`.

## Verdict

- **The primary acceptance (supported textured real fixture) cannot be scored: no
  real capture exists on this host.** The one real-looking asset
  (`gdgs_demo`) has no capture, no poses and no contract.
- **The synthetic fixture does not reach the walk either**: every eligible
  synthetic clip is blocked at Stage B on this host. The default pose path needs
  GLOMAP, which is absent and whose documented install fails; the VGGT fallback
  crashes on the pipeline's own `images/frames.json` manifest and, once worked
  around, exceeds 12 GiB VRAM on 31–50 frames.
- The historical calibrated asset (`corridor_splat`) does pass alignment, the
  production-controller walk and real-GPU rendering (58.94 fps @1280x720), but
  its **collision fails the camera-path coverage check (20.3 % < 90 %)** and its
  source clip is **rejected by the current capture gate**. It is therefore
  evidence for the downstream physics/visual path, not for general
  video-to-walkable reconstruction.

#91 remains **open**; see `REPORT.md` for the precise missing evidence.
