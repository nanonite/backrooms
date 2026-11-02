# Room authoring iterations

These are pre-review design iterations. The operator has directed a rock-heavy room, but has not yet reviewed or accepted the resulting candidate.

| Pass | Evidence | Change and observation |
|---|---|---|
| 1 | `captures/`, `candidate_contact_sheet.jpg`, `capture_resource_run.json` | Closed shell with six side banks of 10 collidable stones and 24 small visual pebbles. The contact sheet showed too much bare floor to read as a rock room. The direct floor crop also projected its perspective clutter across the full surface. The frame-time sample used `--fixed-fps`, which disables real-time synchronization, so it is retained for history but not treated as a runtime rate. |
| 2 | `captures-v2/`, `candidate_contact_sheet_v2.jpg`, `capture_resource_run_v2.json` | Increased the side banks to 12 stones and filled the floor with a seeded 21×16 visual-only gravel field. Rock coverage became clear, but the source floor crop still caused distracting streaks between the stones. |
| 3 | `captures-final/`, `candidate_contact_sheet_final.jpg`, `capture_resource_run_final.json` | Changed the base floor to a flat PSX concrete color and increased position jitter in the small gravel field. The direct source floor crop remains in the bundle for comparison but is not tiled over the room. This is the current candidate. |

The final pass uses `--max-fps 60` with VSync disabled, 120 warmup frames and 300 measured frames. Its view and memory results are in the final capture manifest and guarded resource receipt. The room script seed is fixed at `16802`; the large rock placements and visual-only gravel are reproducible. Active authoring time was not measured.
