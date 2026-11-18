# Authored data record — issue 269 ground relief and shadows

This fixture is **authored data only**. No source video frame, crop, model output,
GPU inference, download or measurement contributes to its geometry, colour, light
direction or placement. Nothing is registered, catalog-admitted, connected or
calibrated to the source video.

## What is authored

- `relief_spec_v1.json`: four positive drift humps and one shallow swale, each an
  anisotropic Gaussian in the horizontal plane. The continuous surface is sampled
  on a 0.5-unit grid and built as one triangulated mesh. It is deliberately not a
  set of flattened ellipsoids.
- `shadow_spec_v1.json`: four trees and four long static polygons. Each polygon
  starts at its tree's base and extends along one shared direction vector. The
  light azimuth is declared as an assumption, not a measurement.
- `views_v1.json`: five repeatable camera viewpoints used unchanged for both the
  baseline and the variant captures.

## Collision policy (explicit)

Collision **stays flat**; it does not follow the relief. A single static box
collider has its top at `y = 0.0`. The visible relief is bounded to
`|height| <= 0.35` design units, so the maximum visible-to-collision height
difference is **0.35 design units** (approximately 0.31 at the drift peaks and
0.17 in the swale). Traversal therefore happens on a flat plane while the visual
surface undulates within that bound. Height is also baked into vertex colours so
the relief is legible without dynamic lighting.

These are uncalibrated design units. No metric scale, source registration or
physical illumination is implied. `registration_accepted=false` and
`scale_calibrated=false` in every record and in both scenes.

## Provenance of this record

All three JSON specs are new files in this evidence folder. The frozen contract,
accepted snow-garden room and pinned project files were **read only**; their
hashes are checked against the authoritative accepted record and contract freeze
by `scripts/verify_relief_fixture_v1.py`.
