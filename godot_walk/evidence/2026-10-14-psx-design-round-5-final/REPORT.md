# PSX Design Round 5

## Question

Round 4's `source_texture_cleanup` displayed two columns. Its authored source-texture cover was at z=2.55 m, displaced from the column visible along the z=0.2 m far-room route. This loop compares a corrected single-column cover and a lower-ceiling treatment while preserving `door_flush` as the control.

## Candidates

- `door_flush`: unchanged wall and ceiling control.
- `source_floor_single_column`: source-video floor and one visual column cover at x=1.25 m, z=0.2 m; walls and ceiling remain as in `door_flush`.
- `source_floor_ceiling_single_column`: same floor and column, plus a source-video ceiling lowered to y=1.0 m, visible wall meshes fitted to its top, and narrow perimeter trim.

The source textures come from registered raw frame 1 of the #100 video. No Gaussian render, new video, retraining, PLY change, or collision change is involved. The round-4 candidate remains intact for comparison.

## Results

- The aligned source cover reads as one column in the matched far-room view; the previous offset cover is not present in either new candidate.
- The floor-only candidate preserves `door_flush` walls and ceiling while providing the clean source-textured floor.
- The lower-ceiling candidate gives a clearer authored ceiling-wall edge, but the captures still show bright and Gaussian artifacts. Its perimeter trim is visually prominent. Treat it as an experiment, not a ceiling fix or selected design.
- Each candidate completes the 13.067 m route with 100% floor support and zero SafetyNet contacts. Boundary and floor negative controls fail as expected.
- Capped FPS is 60.002 for all candidates. p95/p99 are 16.81/16.95 ms for `source_floor_single_column` and 16.87/17.16 ms for `source_floor_ceiling_single_column`.
- Maximum control repeat noise is 0.02%. ODiff candidate deltas are 3.884% and 9.693%; these are pixel-change diagnostics, not quality scores.
- Protected inputs are unchanged.

## Review

Open `index.html` for matched views and `COMMANDS.md` for live walkthrough commands. Keep #121 open. The operator should judge the single-column alignment, floor, and ceiling-wall intersections before a wall-focused follow-up is chosen. Do not promote either new candidate to the control until reviewed.
