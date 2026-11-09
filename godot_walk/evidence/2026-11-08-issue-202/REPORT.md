# Chainlink #202 — footstep audition harness and material-separability metrics

**Status:** implementation and automated verification complete for review. No runtime
or sample changes. Operator listening is the pending human step; agents cannot hear
audio.

## Implementation

`godot_walk/scripts/footstep_audit.py` is a deterministic numpy/scipy audit and
audition renderer. It reads the committed WAVs and never rewrites them.

Per sample it reports:

- RMS and peak in dBFS;
- spectral centroid (Hann-windowed periodogram);
- energy in four bands: `<200`, `200–800`, `800–3000`, `>3000` Hz, both as
  dBFS and as a fraction of total energy;
- a T60-style decay time fitted to the 5 ms RMS envelope over a 20 dB fall;
- crest factor in dB.

Per tag it averages the variants. Material distance uses
`(log2 centroid, log decay, band-fraction vector)`:

```text
centroid_term = |log2(centroid_a) - log2(centroid_b)|          # octaves
decay_term    = |ln(T60_a) - ln(T60_b)|
band_term     = 0.5 * sum(|band_fraction_a - band_fraction_b|)  # 0..1
distance      = sqrt(centroid_term^2 + decay_term^2 + (2 * band_term)^2)
```

The matrix covers the seven materials plus `default` and `land`.

### Loudness target

`git log --all -- godot_walk/scripts/generate_footstep_audio.py` contains only
`3ef34e5`, which introduced the committed `footsteps-0.2.0`. The pre-0.2.0
`footsteps-0.1.0` generator was an uncommitted #200 working-tree version; it was
recovered from the recorded #200 worker session
(`/home/goya/.codex/sessions/2026/11/05/rollout-2026-11-05T14-45-57-01a1ad3f-207f-7923-a26e-4c2171de7d87.jsonl`)
and re-run to measure its 33 samples. Its 32 tag variants average
**-19.89 dBFS RMS** (33 samples including `land`: **-19.90 dBFS**), with every
peak normalised to 0.72. The target is therefore recorded as
**-19.9 dBFS** with a **±1.5 dB** tolerance.

Recovered pre-0.2.0 per-tag mean RMS:

| tag | mean RMS dBFS |
|---|---:|
| carpet | -19.25 |
| concrete | -20.51 |
| tile | -19.29 |
| plaster | -20.59 |
| metal | -19.11 |
| wood | -19.28 |
| debris | -21.63 |
| default | -19.48 |
| land | -20.10 |

### Separability threshold

The every-pair threshold is **0.60**. It was chosen from the two measured
populations:

- `footsteps-0.2.0` minimum pair distance: **0.046** (`concrete`/`wood`); only
  16 of 36 pairs reach 0.60, so the current set fails separability.
- The deliberately contrasting synthetic reference used by
  `test_footstep_audit.py` (nine log-spaced tonal centres with distinct decays,
  each normalised to the loudness target) has minimum pair distance **0.816**
  and passes every pair.

## Baseline: footsteps-0.2.0

Command:

```bash
python3 godot_walk/scripts/footstep_audit.py report \
  --json godot_walk/evidence/2026-11-08-issue-202/audit.json \
  --markdown godot_walk/evidence/2026-11-08-issue-202/matrix.md
```

Tag means:

| tag | RMS dBFS | peak dBFS | centroid Hz | T60 s | crest dB | <200 | 200–800 | 800–3000 | >3000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| carpet | -19.92 | -6.02 | 190.9 | 0.421 | 13.90 | 0.617 | 0.373 | 0.010 | 0.000 |
| concrete | -20.90 | -6.02 | 281.8 | 0.353 | 14.88 | 0.476 | 0.480 | 0.044 | 0.000 |
| tile | -20.69 | -6.02 | 333.1 | 0.364 | 14.67 | 0.408 | 0.519 | 0.073 | 0.000 |
| plaster | -21.52 | -6.02 | 225.4 | 0.369 | 15.49 | 0.589 | 0.390 | 0.021 | 0.000 |
| metal | -22.00 | -6.02 | 364.4 | 0.377 | 15.98 | 0.375 | 0.536 | 0.089 | 0.000 |
| wood | -21.23 | -6.02 | 286.7 | 0.343 | 15.21 | 0.467 | 0.493 | 0.040 | 0.000 |
| debris | -21.43 | -6.02 | 227.2 | 0.399 | 15.41 | 0.579 | 0.396 | 0.025 | 0.000 |
| default | -20.88 | -6.02 | 249.0 | 0.348 | 14.86 | 0.507 | 0.466 | 0.027 | 0.000 |
| land | -20.05 | -6.02 | 131.4 | 0.562 | 14.03 | 0.765 | 0.231 | 0.004 | 0.000 |

Loudness fails: **16 of 33 variants** are outside -19.9 ± 1.5 dBFS, from
-23.25 dBFS (`metal_01`) to -17.77 dBFS (`carpet_04`).

Pairwise distance matrix (identical to `matrix.md`):

| tag | carpet | concrete | tile | plaster | metal | wood | debris | default | land |
|---|---|---|---|---|---|---|---|---|---|
| carpet | 0.00 | 0.65 | 0.92 | 0.28 | 1.06 | 0.69 | 0.27 | 0.48 | 0.68 |
| concrete | 0.65 | 0.00 | 0.28 | 0.40 | 0.43 | 0.05 | 0.39 | 0.19 | 1.33 |
| tile | 0.92 | 0.28 | 0.00 | 0.67 | 0.15 | 0.25 | 0.66 | 0.47 | 1.58 |
| plaster | 0.28 | 0.40 | 0.67 | 0.00 | 0.82 | 0.43 | 0.08 | 0.23 | 0.95 |
| metal | 1.06 | 0.43 | 0.15 | 0.82 | 0.00 | 0.40 | 0.80 | 0.61 | 1.71 |
| wood | 0.69 | 0.05 | 0.25 | 0.43 | 0.40 | 0.00 | 0.43 | 0.22 | 1.37 |
| debris | 0.27 | 0.39 | 0.66 | 0.08 | 0.80 | 0.43 | 0.00 | 0.24 | 0.94 |
| default | 0.48 | 0.19 | 0.47 | 0.23 | 0.61 | 0.22 | 0.24 | 0.00 | 1.16 |
| land | 0.68 | 1.33 | 1.58 | 0.95 | 1.71 | 1.37 | 0.94 | 1.16 | 0.00 |

The full per-variant metrics and violations are in `audit.json`.

## Audition sheet

Command:

```bash
python3 godot_walk/scripts/footstep_audit.py render \
  --out godot_walk/evidence/2026-11-08-issue-202/audition.wav
```

`audition.wav` is a 29.22 s, mono 22.05 kHz 16-bit WAV (1,288,628 bytes). It plays
the tags in this fixed order, three times each:

```text
carpet, concrete, tile, plaster, metal, wood, debris, default, land
```

Each tag is introduced by a 120 ms, 880 Hz beep, followed by a 0.6 s gap; every
repetition is separated by a 0.6 s gap. There is no speech. Each clip is
RMS-normalised to -19.9 dBFS (peak-limited at 0.98), so the A/B comparison is at
equal loudness rather than equal peak. Applied gains are recorded in the render
metadata and range from 0.915 to 1.470.

**Pending operator step:** listen to `audition.wav` and judge whether the
materials are now clearly different and loud enough. This agent cannot listen to
audio.

## Verification

- `python3 -m pytest -q godot_walk/scripts/test_footstep_audit.py` — 4 passed:
  metric determinism, v0.2.0 loudness and separability failure, synthetic
  contrast pass, deterministic audition render.
- `python3 -m pytest -q godot_walk/scripts` — full suite passes.
- `ruff check` and `ruff format --check` on both new Python files pass.
- No Godot run was needed, and no runtime file, sample, library scene, catalog or
  protected file was changed.

## Files

- `godot_walk/scripts/footstep_audit.py`
- `godot_walk/scripts/test_footstep_audit.py`
- `godot_walk/evidence/2026-11-08-issue-202/REPORT.md`
- `godot_walk/evidence/2026-11-08-issue-202/audit.json`
- `godot_walk/evidence/2026-11-08-issue-202/matrix.md`
- `godot_walk/evidence/2026-11-08-issue-202/audition.wav`
