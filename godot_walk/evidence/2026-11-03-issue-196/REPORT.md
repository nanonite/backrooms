# Issue 196 — Growth-time diagonal links

Status: candidate artifacts, CPU/headless verification, and the first GPU capture set are ready for operator review. The first captures were guarded and completed. A corrected oblique recapture remains pending because a later preflight found VLC using the GPU; no process was stopped.

## Implementation

`gmap-0.6.1` is opt-in; the CLI default and generator versions 0.1.0–0.6.0 remain unchanged. Growth attempts a diagonal site with probability 0.35 on its separate named stream while the existing seeded budget has room. Passage clearances are reserved during growth; later cells, voids, and module footprints must stay out. Unused reservations are recorded as released. The #193 post-pass realizes reserved sites first, then incidental eligible pairs. The spanning-tree edges remain cardinal.

To meet the map-level rate targets, generation checks up to 48 deterministic layout variants for a budget-positive attempt. Variant 0 uses the existing layout stream; later variants use a named v0.6.1 layout stream. It returns the first full-budget layout, or the best layout seen if none reaches the budget. The selected `layout_variant` is serialized for exact reproduction. This bounded search is the main deviation from the issue’s per-step description; it retains the per-step 0.35 site chance and the original budget draw.

The existing #193 map-flood and diagonal-link runtime checks were gated to v0.6.0. Their version gates now include v0.6.1 so flood connectivity, doorway frames, and the established negative controls actually run on the new maps.

## Rate sweep

The 300-seed sweep passed both v0.6.1 targets. Counts are `(drawn budget, realized links)`.

| Cells | Used vs budget distribution | Full budget when budget ≥1 | Two links |
|---:|---|---:|---:|
| 12 | (0,0): 100; (1,1): 134; (2,1): 9; (2,2): 57 | 191/200 (95.5%) | 57/300 (19.0%) |
| 20 | (0,0): 100; (1,1): 134; (2,2): 66 | 200/200 (100%) | 66/300 (22.0%) |

## Kept maps

| Seed | Variant | Budget / used | Purpose |
|---:|---:|---:|---|
| 1 | 0 | 0 / 0 | Required seed; no link drawn. |
| 2 | 27 | 2 / 2 | Required two-link example. |
| 3 | 3 | 1 / 1 | Required seed; one link. |
| 8 | 1 | 2 / 1 | Palette-adjacent link example; `c09` is in the `plaster_debris` ring at distance 2 from the figure anchor, and `c08` is the adjacent distance-1 ring cell. One unused budget slot is documented by the generator. |

Each map has its map JSON, fill JSON, layout SVG, and `all_walkable` room index/specs under `room_catalog/`. These are generated candidate artifacts, not catalog admission or operator approval.

Map JSON and room-index SHA-256 values:

| Map | Map JSON | Room index |
|---|---|---|
| `gmap-1-gmap-0.6.1` | `cc89ebb53ffad73d92a34279b9d243af141c0331e7c2c29b179324922642dfac` | `966224395b12fc81a516bb97e879eb922d35b8eb7e8ba96945c711a6dbfeb7a8` |
| `gmap-2-gmap-0.6.1` | `d80d831fbd781c862e461a309f07b4fe678525fa9e69eadbb0d939b768c82693` | `6e9d03b2487c3b6dfffde7c0ae49931495c7b65051aad241103ca2e4868517ab` |
| `gmap-3-gmap-0.6.1` | `2733ae40e3234cd962da6e7ec11e8390fb67007d20bf85e1570fa1a98a610515` | `81f4a69b19f70f7aa08e033b231bb76fee452a5347a3faf8bad2f825a22a7651` |
| `gmap-8-gmap-0.6.1` | `81bb2966d801c71e2121ea0d8ccc01a290cf5cef656e77dcb208ac19995668e7` | `40f7c0e245a5c86939d0ccb25d0adb02bb47f3f2ce6994cebaa1467cb9839917` |

## Headless results

Kept seeds 1, 2, 3, and 8 pass `test_issue183_shape_rooms.gd`. All report zero trim, wall, reveal, and diagonal coplanar conflicts; zero missing floor samples; zero uncovered wall-joint samples; zero unreachable voids; and zero palette mismatches. Applicable negative controls pass. For linked maps, the doorway-removed, passage-collision-removed, floor-without-declared-link, and unaligned-frame controls all fail as expected.

| Seed | Edge traversal both ways | Flood / expected | Chamfer pushes stopped | Floor missing / samples | Joint uncovered / samples | Link lanes / both directions | Passage colliders | Diagonal frames |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 26/26 | 14/14 | 33/33 | 0/42,131 | 0/2,935 | n/a | n/a | n/a |
| 2 | 34/34 | 16/16 | 49/49 | 0/37,989 | 0/3,500 | 24/24 | 12 | 4 |
| 3 | 28/28 | 14/14 | 41/41 | 0/31,191 | 0/3,219 | 12/12 | 6 | 2 |
| 8 | 28/28 | 14/14 | 23/23 | 0/28,541 | 0/1,616 | 12/12 | 6 | 2 |

Scratch seeds 4–6 also pass headless traversal and containment checks; their maps/specs were generated under `/tmp` and removed after the sweep. The scratch results had no coplanar conflicts, no floor/joint gaps, and no palette mismatches. Generator v0.6.0 regression seeds 1, 2, 3, 36, and 64 (seed 64 at 20 cells) pass headless checks after the version-gate extension.

## Tests and validation

- `python3 -m pytest -q godot_walk/scripts`: **587 passed, 58 subtests passed**. The fixed seed-8 palette-ring fixture test added after that run also passed separately: **1 passed**.
- `ruff check` on changed Python files: passed.
- `python3 -m compileall -q godot_walk/scripts`: passed.
- `generative_map.validate_path` and `shape_room.validate` passed for kept seeds 1, 2, 3, and 8.
- Byte-parity check of the committed v0.6.0 map/fill/SVG/room specs for seeds 1, 2, 3, 36, and 64: passed. Existing suite compatibility checks for v0.1.0–v0.5.0 also passed.
- `git diff --check`: passed. Protected library scenes/scripts/textures, `room_catalog/catalog.json`, `scripts/player.gd`, `project.godot`, and `room_catalog/MATERIAL_LANGUAGE.md` were not changed.

## Captures and review

The GPU/RAM guard passed before the first capture for each linked seed. The tool captured 24 views for seed 2 and 12 each for seeds 3 and 8. Raw PNGs and contact sheets are under:

- `captures/seed2/` and `captures/seed2/contact_sheet.jpg`
- `captures/seed3/` and `captures/seed3/contact_sheet.jpg`
- `captures/seed8/` and `captures/seed8/contact_sheet.jpg`

I inspected all views in the three contact sheets and opened the suspicious oblique PNGs at full resolution. The `face` and `up` views cover each doorway from both adjoining sides. Those views show aligned 45-degree frames, a closed wall above each opening, and a closed passage ceiling; no black gap is visible in those views. The `oblique` views expose black because the capture script placed the camera 1.3 m laterally from the opening center, beyond the 1.0 m half-width of a 2 m doorway. This is an invalid off-aperture camera placement, not evidence that the traversable passage has a hole.

I adjusted `capture_diagonal_passage.gd` to use a 0.6 m lateral offset for its oblique view, which keeps the camera within the opening. The follow-up preflight blocked because VLC (PID 3514202) was using the GPU. I did not stop it or run the corrected captures. The corrected oblique views remain pending.

The first capture command, used for each seed after a passing preflight, was:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 \
  --script res://scripts/capture_diagonal_passage.gd -- \
  --map=res://room_catalog/generative_maps/gmap-N-gmap-0.6.1.json \
  --rooms=res://room_catalog/shape_rooms/gmap-N-gmap-0.6.1/index.json \
  --out=godot_walk/evidence/2026-11-03-issue-196/captures/seedN
```

`gmap-2-gmap-0.6.1.svg` is the current two-link layout diagram; seed 8’s SVG shows the palette-adjacent example. The centered doorway views pass the requested visual checks. Re-run the corrected oblique views once the guard passes to complete the three-angle capture review.

Representative launch command for the two-link walk:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-2-gmap-0.6.1.json \
  --rooms=res://room_catalog/shape_rooms/gmap-2-gmap-0.6.1/index.json
```

Human review remains required for the rendered diagonal doorways and a two-link walkthrough. No commit, promotion, or issue closure has been made.

## Lead addendum (2026-11-04)

The lead verified the work independently:
- **Rate sweep:** reproduced exactly.
- **Byte parity:** all 24 committed 0.1.0–0.6.0 maps rebuild byte-identically.
- **Headless:** kept seeds 1, 2, 3 and 8 PASS.
- **Python suite:** 588 passed before the changes below.

**Captures.** The GPU was free (1.1 of 12 GB in use), so the lead re-rendered all 48 views with the corrected 0.6 m oblique offset. These views replace the first set under `captures/seed{2,3,8}/`. Every doorway shows an aligned 45° frame, a closed lintel and an enclosed passage, and the oblique views show no black. Seed 8 shows the plaster_debris to backrooms_yellow change through the passage.

**Variant search accepted.** At layout_variant 0, only 47/200 (12 cells) and 97/200 (20 cells) budget-positive maps reach their full budget. LEVER_STUDY.md shows the shortfall comes from site availability: growth already enumerates every legal placement, and the set is usually empty. It does not come from gate frequency, retries or later-stage releases.

The lead also measured layout similarity to 0.6.0 at variant 0 (seeds 1–60, 12 cells):
- budget-0 maps are 100% identical;
- budget ≥1 maps are about 13% similar.

The cause is that the root cell uses SITE_CLASSES and site steps shift the layout rng. The bounded re-roll therefore costs little extra similarity. The operator accepted the 48-variant search as built.

**Corner-snap prefilter (lead).** `gmap_diagonal_growth._site_options` now skips placements that have no corner exactly 1 m diagonal from a corner of an eligible cell. Eligibility matches `site_for_rect`. Results:
- the maps for seeds 1–300 at 12 and 20 cells are byte-identical with and without the prefilter;
- generation is 54% faster at 12 cells and 57% faster at 20;
- kept seeds 1, 2, 3 and 8 regenerate unchanged.

**Rate test.** The 300-seed sweep is now skipped by default. Run it with `GMAP_RATE_SWEEP=1 python3 -m pytest -q godot_walk/scripts/test_gmap_diagonal_v61.py -k rate`. The default suite drops from 11 min to 1 min 40 s, with 587 passed and 1 skipped.

**Operator.** The seed-2 two-link walk was approved on 2026-11-04 ("worked out fine, looks good to me").
