# Limitations — issue 272 lit PSX material fixture (candidate)

This is a disposable **candidate** fixture, not an accepted appearance, a catalog
decision or a production migration. All values are **uncalibrated** design units.

- **Visual-only pending.** A passing validator, clean headless test or clean
  capture is not approval. The **operator** must compare the paired views on a
  suitable renderer; this agent cannot judge appearance. No visual pass is claimed.
- **Fog unchanged.** All four variants keep `FOG_DISABLED` and environment fog
  disabled. Whether fog should ever be enabled with lit materials is a separate,
  later decision and is not tested here.
- **Shadows disabled.** The shared URSC include declares `shadows_disabled`, and
  the key light has shadow maps off. The lit variants respond to light *direction*
  through `diffuse_lambert_wrap` / `vertex_lighting`, but cast no real shadows.
  Whether real shadows are needed is an operator/renderer question, not proven here.
- **`vertex_lighting` is per-vertex.** With low-poly primitives the lit response
  can look faceted; this is a property of the chosen PSX path, not a regression
  fix. Whether it is acceptable is pending operator review.
- **Double lighting / baked albedo.** Existing accepted palettes bake dusk into
  albedo. These neutral authored colours deliberately avoid double lighting; no
  existing source palette was relit, and none was claimed to be faithful.
- **Transparency and double-sided surfaces** are not exercised by these five
  opaque meshes. `CULL_MODE cull_disabled` is retained, but no alpha or two-sided
  case is captured. This remains an open finding.
- **Performance** was not measured. Any runtime cost of the lit path is unverified.
- **No model calls, no downloads, no GPU inference.** The checker texture and all
  colours are authored in code; no external asset or service was used.
- **Scene fidelity not claimed.** The PSX compositor/preset and player controller
  from the accepted room are omitted so a plain InspectionCamera can capture fair
  comparisons; their absence is a capture-only condition, not a scene change.
- **No ledger events or hashes by hand.** The capture guard receipt and the
  pinned-supplement hashes are produced by the existing scripts, never authored.
