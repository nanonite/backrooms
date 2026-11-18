# Authored data record — issue 270 finite horizon ring

Everything in this experiment is **authored** in uncalibrated design units. No
source video viewpoint was reconstructed, no metric scale was inferred, no model
or GPU inference was run, and nothing was downloaded.

## Geometry placement and authorship

- The finite horizon is a ring of `24` vertical silhouette panels at a fixed
  world radius of `36.0` units around `(0, 0, 0)` in the XZ plane. Panel base is
  `y = 0`, thickness `0.12`, tangential width `10.0`. Each panel faces the ring
  centre.
- Per-panel heights are the explicit `panel_heights` array in
  `horizon_spec_v1.json` (range `1.7`–`4.4` units). The irregular sequence is
  hand-authored to read as a distant tree/terrain line; it is **not** sampled
  from the source frame.
- Panels are unshaded, flat, dark (`0.16, 0.20, 0.24`) and have **no collision**.
  The scene contains no `StaticBody3D`, no `CollisionShape3D`, no floor and no
  player controller. The camera path is inspection-only and bounded
  (`x` in `[-3, 3]`, `y = 1.6`, `z = 0`, looking `-Z`).

## Static sky background

- The backdrop is a Godot `ProceduralSkyMaterial` assigned to a `Sky` and used
  as `Environment.background_mode = BG_SKY`. It is rendered at infinity, so its
  features do **not** move under camera translation. It gives the finite ring a
  fixed backdrop against which parallax is observable.
- The sky gradient is authored, not the source equirectangular panorama. This
  experiment does not claim source fidelity.

## Source reference (context only)

- `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`
  is cited **only** as visual context. It is not modified, not admitted to the
  catalog, not registered, and no geometry is derived from its pixels.

## Flags and status

`registration_accepted=false`, `scale_calibrated=false`, `operator_approved=false`
in both specs, both scenes and the capture manifest. Status is
`candidate_pending_review`. A passing validator or a clean capture is not
approval; the operator decides whether the effect and source interpretation are
acceptable.
