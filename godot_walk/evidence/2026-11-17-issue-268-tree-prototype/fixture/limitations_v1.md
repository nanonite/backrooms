# Known limitations — issue 268 tree prototype

Recorded before operator review. These are not resolved by validators or captures.

- **Silhouette:** layered cards can still read as flat or show silhouette gaps from
  above and at close range. The elevated and oblique captures are provided so the
  operator can judge this; no pass is claimed by the agent.
- **Crop edges:** rectangular card edges may remain visible, especially where a bright
  sky background meets a crop's dark border. Flat/unshaded materials were chosen to
  keep baseline and variant comparable, not to hide edges.
- **Repetition:** only three distinct source crops are reused across seven cards, so
  repeated foliage motifs are expected and are not disguised.
- **Trunk appearance:** no usable bark crop was found in the available source frames,
  so the trunk is explicitly authored. Its colour and taper are a design choice, not
  a source measurement or a fidelity claim.
- **Collision:** the trunk collision is an independently authored cylinder sized to
  contain the visual trunk; it is approximate, not source-derived. The canopy cards
  have no collision. The finite floor is an inspection platform, not a physical claim
  about the source scene's ground.
- **Scale and connectivity:** all geometry is in uncalibrated design units. No metric
  scale, registration, source connectivity or terrain continuity is established.
  `registration_accepted` and `scale_calibrated` remain false everywhere.
- **Capture environment:** captures are rendered through the existing guarded capture
  wrapper with the available Vulkan GPU; image quality and faithfulness to the source
  are judged by the operator, not by the agent.
- **Agent judgement:** the agent cannot approve appearance, source fidelity or feel,
  and cannot walk the scene as a player. Any such decision is pending the operator.
