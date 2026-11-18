# Limitations — issue 269 ground relief and shadows (pre-review)

- **Authored, uncalibrated relief.** The relief is a hand-specified sum of
  anisotropic Gaussian humps in uncalibrated design units, not a measured terrain
  reconstruction. No metric scale and no source registration are implied;
  `registration_accepted` and `scale_calibrated` remain false.
- **Flat collision / visual mismatch.** Collision stays flat while the visible
  relief varies by up to 0.35 design units. The player does not climb the drifts.
  Whether that visual-to-collision mismatch is acceptable for traversal is an
  operator judgement; no feel claim is made by this agent.
- **Static, unlit shadow polygons.** Shadows are dark authored polygons sampled
  onto the relief surface with one assumed light direction. They do not respond
  to dynamic lights, have no softness or penumbra, and are not connected to a
  physical sun. Their direction and length are not measured from the video.
- **Unshaded baked appearance.** Both baseline and variant use unshaded
  materials; relief shading is baked into vertex colours and shadows are dark
  polygons. There is no PSX compositor and no real shadow mapping.
- **Finite plot.** The fixture is a bounded 18 × 18 inspection plot with a safety
  net, not an unbounded open world and not a claim about boundary behaviour.
- **No catalog or integration decision.** No module metadata, socket, admission,
  registration or connectivity decision is made. No accepted room or frozen
  contract was edited.
- **Capture conditions.** Captures use a local Godot Forward+ Vulkan renderer;
  appearance review belongs to the operator comparing the paired PNGs, not to a
  passing structural test.
