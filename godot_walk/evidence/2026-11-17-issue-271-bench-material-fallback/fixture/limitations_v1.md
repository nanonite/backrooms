# Issue 271 — limitations (pre-review, v1)

- This is a visual-only, uncalibrated preview, not acceptance or registration.
  `registration_accepted=false`, `scale_calibrated=false`,
  `operator_approved=false`; no catalog admission, ledger event or hash was
  written by hand.
- The candidate material is an explicitly authored solid colour. It is not a
  source reconstruction and no claim is made that its pixels were observed in
  the source. Whether it reads as plausible stone is an operator judgment.
- The statue plinth keeps the reference's robe crop in BOTH views because the
  reference shares that material between plinth and bench; the fallback is
  deliberately restricted to the bench so the plinth is not silently changed.
  The four bench bollards keep the reference's solid post material in both
  views for the same reason.
- Geometry, collision, floor, walls, trees, drifts, posts and the panorama are
  copied from the accepted room; all counts and placements remain authored and
  uncalibrated. No new source crop was extracted, no frame was resampled and no
  model, GPU inference, download or paid call was used.
- The isolated fixture omits the accepted room's player controller and PSX
  compositor/preset so a plain InspectionCamera can capture fair paired views.
  The panorama is still used as the sky background; lighting is the copied dusk
  key/fill. The absence of PSX post-processing is a capture-only difference and
  must not be read as a scene change.
- Agents cannot judge appearance. A passing validator, clean headless test or
  clean capture is not approval; the operator compares the paired captures and
  decides visual suitability. No integration, socket or scale decision is made.
- Captures are stored under `captures/` and stay local by the operator's
  `.gitignore` policy for bulky evidence outputs; the guard receipt and records
  are committed so the views can be regenerated.
