# Authored versus source-backed — issue 268 tree prototype

This fixture is an isolated visual experiment, not a reconstruction or an accepted
room. Nothing here is catalog-admitted, registered, scale-calibrated or connected
to any other scene.

## Source-backed

- The three canopy card albedo textures (`branch_canopy.png`, `branch_fine.png`,
  `evergreen_foliage.png`) are byte-for-byte copies of crops already recorded in
  `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/textures/crop_manifest.json`.
  `crop_provenance_v1.json` records the source video SHA-256, frame manifest SHA-256,
  frame ID, frame SHA-256, exact `[x0, y0, x1, y1]` pixel bounds and both the origin
  and copied-file SHA-256 for each crop. The accepted room and its pinned inputs were
  only read, never edited.
- The cards are textured with those crops. The crops are not re-cropped, resized or
  colour-adjusted in this fixture.

## Explicitly authored (not claimed as source evidence)

- Trunk: tapered cylinder, base/top radius, height, and a solid dark bark-like colour.
  No bark crop was used. See `bark_crop_assessment` in `crop_provenance_v1.json`.
- Branches: count, angles, lengths, radii and geometry.
- Canopy: card count, per-card crop choice, radial offset, centre height, azimuth,
  tilt and size; all listed in `card_specs_v1.json`. Layered placement is a hypothesis,
  not a measured tree structure.
- Inspection floor, finite footprint, spawn, lights, materials, camera views, and all
  collision (trunk, floor, safety net).
- The baseline scene reproduces the *current* one-tree representation scheme
  (solid six-sided trunk cylinder + four small branch cylinders + two thin textured
  canopy boxes + separate trunk box collision), not the full accepted room.

## Flags

`registration_accepted = false`, `scale_calibrated = false`, `operator_approved = false`,
`status = candidate_pending_review` in both scenes, both manifests and the report.
A passing validator, clean load or clean capture is not operator approval of
appearance, source fidelity, catalog admission or integration.
