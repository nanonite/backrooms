# Chainlink #194 — gmap-0.7.0 landmark rooms

**Status:** implementation and automated checks pass; captures are ready for lead and operator review. Nothing is committed.

## Lead review fixes

`gmap_grow._landmark_port_is_midpoint` now checks the tangent axis: an opening on an X edge must be at the room's Z midpoint; an opening on a Z edge must be at its X midpoint. The earlier predicate checked the normal axis, so only the landmark's entry port survived.

`test_growth_filter_and_validator_agree_on_each_landmark_side` builds an attaching child through the growth placement filter for every permitted side, connects it, and verifies the resulting port with `landmark_errors`. A half-metre tangent offset is rejected by the growth midpoint predicate and the map validator. This negative case calls the growth predicate directly rather than running a whole `grow_step_v61`; the positive case exercises `placements` and `connect`. The per-seed Godot negative control `landmark_port_off_midpoint` separately checks the built room boundary.

The scratch headless sweep initially found a module-joint approach failure on seed 22. `issue183_room_checks.gd` applied the existing module-joint approach exemption through `shape-room-0.6.0` but omitted the new `shape-room-0.7.0` version. Adding the successor version fixed the check; seed 22 then passed, as did all 12 scratch seeds. The capture script retains the lead's parse fix (`var scene: Node = ...`) and now places the review camera at runtime floor-centre height (0.6 m), 3 m inside the landmark and 1.5 m inside its neighbor. Its wide view faces the first opening consistently.

## Landmark placement sweep

The opt-in sweep covered seeds 1–300 at 12 and 20 cells. Each size drew and placed 145 landmarks (48.3% of all maps), with no unplaced landmarks and no invalid maps. The 12-cell result exceeds both the 40%-of-maps placement target and the 50%-of-placed-landmarks two-door target: 88/145 (60.7%) have at least two ports.

| Class | 12 cells: 1 / 2 / 3 / 4 doors | 20 cells: 1 / 2 / 3 / 4 doors | Placed per size |
|---|---:|---:|---:|
| `dodecagon` | 18 / 15 / 9 / 0 | 15 / 14 / 9 / 4 | 42 |
| `hexagon` | 5 / 9 / 0 / 0 | 4 / 10 / 0 / 0 | 14 |
| `octagon_regular` | 17 / 10 / 8 / 0 | 14 / 15 / 5 / 1 | 35 |
| `rotunda16` | 17 / 24 / 11 / 2 | 22 / 19 / 12 / 1 | 54 |
| **Total** | **57 / 58 / 28 / 2** | **55 / 58 / 26 / 6** | **145** |

Unplaced reasons: none. Generation errors: 0 at both sizes. The 12-cell sweep is the requested class-by-door target check. Facet lengths and port eligibility remain the lead-approved contract: octagon 3.31 m, dodecagon 3.22 m, rotunda16 3.18 m, hexagon 4.62 m; the hexagon has two permitted opposing ports.

## Kept artifacts and headless results

Seeds 1–3 are kept. Seeds 23, 60 and 69 show the additional classes with the highest useful port counts found in seeds 1–300. Seed 69 is the four-port rotunda. Every map has `.json`, `.fill.json` and `.svg`; every room set is under `room_catalog/shape_rooms/<map-id>/`.

| Seed | Landmark / open ports | Rooms | Traversal both ways | Flood | Capsule wall stops / samples | Floor missing / samples | Coplanar trim / wall / reveal / diagonal | Palette mismatches | Landmark negative controls |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | none drawn | 12 | 26/26 | 14/14 | 563/563 | 0/42,131 | 0 / 0 / 0 / 0 | 0 | n/a |
| 2 | dodecagon / 3 | 14 | 32/32 | 15/15 | 554/554 | 0/50,290 | 0 / 0 / 0 / 0 | 0 | pass |
| 3 | none drawn | 13 | 28/28 | 14/14 | 522/522 | 0/31,191 | 0 / 0 / 0 / 0 | 0 | n/a |
| 23 | octagon_regular / 3 | 12 | 24/24 | 13/13 | 582/582 | 0/15,557 | 0 / 0 / 0 / 0 | 0 | pass |
| 60 | hexagon / 2 | 13 | 28/28 | 14/14 | 602/602 | 0/35,462 | 0 / 0 / 0 / 0 | 0 | pass |
| 69 | rotunda16 / 4 | 13 | 30/30 | 15/15 | 553/553 | 0/34,807 | 0 / 0 / 0 / 0 | 0 | pass |

Each run passed `test_issue183_shape_rooms.gd`, including closed-door blocking, flood-fill containment, capsule stops, floor samples, and the applicable facet-collision-removed, unmitred-joint and off-midpoint-port controls. Map 2 has 2 diagonal links; maps 3, 60 and 69 have 1 each. Zero coplanar faces and palette mismatches were measured on every kept seed. The final JSON receipts are `runtime_verified_gmap-<seed>.json` in this evidence directory.

## Render captures

GPU-guarded Vulkan captures completed for all 12 landmark doorways (inside and neighboring side) and four wide views: 28 PNGs total. The contact sheets are:

- `captures-operator-review/gmap-2-contact.png` — three-port dodecagon.
- `captures-operator-review/gmap-23-contact.png` — three-port octagon.
- `captures-operator-review/gmap-60-contact.png` — two-port hexagon.
- `captures-operator-review/gmap-69-contact.png` — four-port rotunda.

Raw PNGs are in the matching `captures-operator-review/gmap-<seed>-gmap-0.7.0/` directories. I inspected every inside/neighbor pair and the wide view for each class. The final views show aligned framed openings, a closed wall above each opening, continuous ceilings and floors, mitred facets, and no visible black gaps or floating trim. Source-texture variation remains visible where a landmark meets a neighboring room with a different palette/material; this is an authored material boundary, not a geometric gap. The operator should still walk the room to assess the PSX appearance and whether the repeated central lamp/wall treatment reads well in motion.

The repository guard passed all four capture runs. Across them, peak child RSS was 571,006,976 bytes and the largest measured VRAM delta was 180,355,072 bytes. Preflight reported 11,604,590,592 bytes free VRAM (about 10.8 GiB) and at least 21,567,107,072 bytes available RAM (about 20.1 GiB). No desktop process was stopped or bypassed.

## Verification

- `python3 -m pytest -q godot_walk/scripts` — **600 passed, 2 skipped, 58 subtests passed** in 98.56 s. This includes old-map regeneration parity and the new landmark unit tests.
- `GMAP_LANDMARK_SWEEP=1 python3 -m pytest -s -q godot_walk/scripts/test_gmap_landmarks.py::test_v70_seed_sweep_at_12_and_20_cells` — **1 passed**; 600 maps checked, sweep table above.
- `godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- --map=res://room_catalog/generative_maps/gmap-<seed>-gmap-0.7.0.json --rooms=res://room_catalog/shape_rooms/gmap-<seed>-gmap-0.7.0/index.json --out=res://evidence/2026-11-04-issue-194/runtime_verified_gmap-<seed>.json` — passed on seeds 1, 2, 3, 23, 60 and 69.
- Scratch headless sweep on seeds 4–11, 15, 22, 28 and 90 — all 12 passed after the `shape-room-0.7.0` module-joint check was added.
- `python3 -m compileall -q godot_walk/scripts` — passed.
- Focused `ruff check --ignore RUF100 ...` — passed; `ruff format --check` on the new landmark Python modules/tests — 5 files already formatted. Plain focused Ruff also reports nine pre-existing `RUF100` warnings for legacy `# noqa: E402` directives in `generative_map.py`; that file was not changed to silence unrelated warnings.
- The Vulkan capture command parsed and ran `capture_landmark_rooms.gd` on each kept landmark seed.
- Previous generator outputs remain byte-identical for `gmap-0.1.0` through `gmap-0.6.1`; the full suite covers the 28 committed regression maps. The CLI default remains `gmap-0.2.0`.

## Launch

Best four-port rotunda, seed 69:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-69-gmap-0.7.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-69-gmap-0.7.0/index.json
```

## Human verification

Walk seed 69 and seed 60. Check that the four rotunda doorways feel useful from inside the room, and that the hexagon's two opposing openings read as intended next to its neighboring room. The implementation remains provisional pending review; older generator versions and protected library inputs were not changed.
