# Limitations — issue 270 finite horizon ring

- This is a **visual-only** experiment. The silhouette is an authored
  interpretation, not recovered distant terrain. It carries no source fidelity
  claim and no automatic admission or acceptance follows from it.
- All geometry, colours, sky gradient, ring radius and camera path are
  uncalibrated design units. `registration_accepted=false` and
  `scale_calibrated=false` throughout; no metric or navigable scale is implied.
- The ring is **finite and world-fixed** (radius 36). It has no collision, no
  floor and no route; the bounded camera path is an authored inspection path,
  not traversal. Agents cannot walk or judge feel.
- The sky is an authored procedural gradient rendered at infinity, not the
  source panorama. The baseline keeps the identical sky with the ring disabled,
  so any difference is attributable to the finite ring alone.
- Panel widths (10.0) slightly exceed their arc spacing (~9.42) so the silhouette
  joins overlap. At the `seam_check` view the operator should inspect for seams,
  edge intersections, clipping of panel tips by the sky/ground transition and
  any apparent "wall" reading. These are recorded as observations, not resolved.
- Under translation the finite ring is expected to shift against the static sky;
  under in-place rotation both ring and sky rotate together. Any parallax or
  rotation judgment is for the operator; the mechanical checks only assert
  finite geometry, fixed sky, camera transforms and threshold angular shift.
- Captures are produced only through the existing guarded capture wrapper and
  stay local under the operator `.gitignore` policy for bulky evidence outputs.
  A clean capture is not operator approval.
