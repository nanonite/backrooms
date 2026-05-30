## Goal (Step 6 — iterate on capture quality) [POST-MVP, lower priority]
Once the loop is closed end-to-end (Integration Step 5), improve fidelity by
improving the INPUT — reconstruction quality is dominated by capture quality, not by
runtime tweaks.

## Prereqs / Blockers
- Depends on Integration Step 5 (working end-to-end loop). Do NOT start before the
  loop closes — premature capture iteration optimizes a pipeline you can't yet evaluate.

## What to iterate on
- COVERAGE: re-shoot surfaces that smear up close; observe each from ≥2–3 angles.
- PARALLAX: more translation, less rotate-in-place.
- BLUR/EXPOSURE: slower movement, locked exposure, even lighting.
- Capture a known reference distance (meter stick / doorway) IN FRAME to make the
  Back-end Step 4 scale calibration unambiguous.
- SPLAT BUDGET: if runtime FPS/VRAM is tight, cap with Brush `--max-splats` and compare.

## Acceptance criteria
- A second, better capture produces visibly cleaner walk-up surfaces than the first.
- Documented "good capture" checklist appended to `scripts/splat_pipeline/README.md`
  based on what actually worked.

## Escalation conditions
- Diminishing returns on capture → the remaining smear is a renderer/representation
  limit, not a capture limit; note it and stop. Relighting/shadows/NPCs are explicitly
  out of v1 scope (cf. PlayCanvas FPS reference for a later pass).
