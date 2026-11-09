# Chainlink #203 — layered procedural footsteps (footsteps-0.3.0)

**Status:** implementation and automated verification complete for review. Operator
listening is the pending human step; agents cannot hear audio.

## Implementation

### Generator

`godot_walk/scripts/generate_footstep_audio.py` is now `footsteps-0.3.0`. It is
still deterministic, committed and uses no downloaded audio. Every acoustic tag
(`carpet`, `concrete`, `tile`, `plaster`, `metal`, `wood`, `debris`, `default`)
and `land` is baked as separate stems:

| layer role | content |
|---|---|
| `transient_soft` | dark filtered-noise heel strike with a short decay |
| `transient_hard` | brighter filtered-noise heel strike with a short decay |
| `body` | 3–6 decaying modal sines plus a narrow-band noise bed around the same modes |
| `texture` | short noise grains plus a drag/crunch bed, material-dependent |

The wet layer is omitted because no tag needs a squelch or splash; the manifest
records `optional_layers.wet` with that reason.

Stems are mono 22.05 kHz 16-bit WAVs. The longest stem is 0.2925 s, under the
~300 ms budget. The 2 kHz low-pass is raised to 6 kHz.

Layout:

```text
godot_walk/audio/footsteps/<tag>/<layer>/<tag>_<layer>_<variant>.wav
godot_walk/audio/footsteps/land/<layer>/land_<layer>_01.wav
```

Four variants per tag, one landing variant.

### Per-stem provenance

`godot_walk/audio/footsteps/provenance.json` (schema 2) records for every stem:

- `script_version`, `seed_rule`, and the layer's `parameters`;
- the relative `layer_gain`, `onset_ms`, duration, byte count and SHA-256;
- the per-variant mixed RMS/peak for the walk-force audition mix
  (`transient_soft + body + texture`).

The seed rule is `sha256(script_version:tag:variant:layer)`; re-running the
generator reproduces every stem and manifest byte-for-byte.

### Runtime

`godot_walk/scripts/walk_player.gd` is the only runtime script changed. It keeps
`footstep_event(tag, sprinting)`, `landing_event()`, the `default` fallback, the
once-per-collider unknown-floor log and the #200 distance/stride triggers.

- A fixed pool of 16 `AudioStreamPlayer`s is created once in `_ready`: four per
  layer role. A step takes one transient-tier player, one body player and one
  texture player — at most three players per step, no allocation per step.
- The two transient tiers are selected by a dithered gain crossfade: the hard
  tier's probability follows force, so average brightness tracks speed
  continuously while the step stays within the three-player budget.
- Each layer chooses its own variant without an immediate repeat, its own
  ±5% pitch jitter, and its own 0–8 ms onset offset. The offsets are baked into
  the stems (transient 0–1.5 ms, body 2–5 ms, texture 4.5–8 ms) so Godot does not
  need a per-step timer or any per-frame DSP.
- Horizontal speed maps continuously to impact force: 0.5 at walk speed, 0.8 at
  sprint speed, 1.0 for landing. Force scales the three layer gains; the gains
  are normalised so a walk-force step reproduces the baked -19.9 dBFS RMS mix.

### Loudness and playback level

The #202 samples measured -19.9 dBFS RMS at peak 0.72 in the pre-0.2.0
generator, while the v0.2.0 samples were much quieter. The layered stems are
baked to the same **-19.9 dBFS RMS** target with a **±1.5 dB** tolerance from
`footstep_audit.py`.

Playback volumes therefore change from the v0.2.0 `-18 / -14 / -15 dB` structure
to **0.0 dB walking, +1.5 dB sprinting, 0.0 dB landing**. Keeping `-18 dB` on
samples already normalised to -19.9 dBFS would have reproduced the v0.2.0
quietness. Sprint still gets a modest lift, and the force curves add roughly
+1–1.5 dB at sprint and +1–2.5 dB at landing.

## Audit result

Command:

```bash
python3 godot_walk/scripts/footstep_audit.py report \
  --json godot_walk/evidence/2026-11-08-issue-203/audit.json \
  --markdown godot_walk/evidence/2026-11-08-issue-203/matrix.md
```

- **Loudness:** passes; zero variants outside -19.9 ± 1.5 dBFS. The lowest
  variant is -20.87 dBFS (peak-limited to 0.98), still inside tolerance.
- **Separability:** passes every pair; minimum distance **0.838**
  (`concrete`/`debris`) against the **0.60** threshold. The v0.2.0 baseline was
  0.046.

Tag means:

| tag | RMS dBFS | peak dBFS | crest dB | centroid Hz | T60 s | <200 | 200-800 | 800-3000 | >3000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| carpet | -19.90 | -3.30 | 16.60 | 155.0 | 0.100 | 0.87 | 0.10 | 0.03 | 0.00 |
| concrete | -19.90 | -1.16 | 18.75 | 880.5 | 0.083 | 0.00 | 0.70 | 0.29 | 0.01 |
| tile | -20.09 | -1.50 | 18.58 | 3445.3 | 0.055 | 0.00 | 0.00 | 0.25 | 0.75 |
| plaster | -19.90 | -1.18 | 18.72 | 269.4 | 0.056 | 0.44 | 0.53 | 0.03 | 0.00 |
| metal | -19.90 | -1.18 | 18.72 | 2009.9 | 0.266 | 0.00 | 0.08 | 0.72 | 0.20 |
| wood | -19.90 | -2.42 | 17.48 | 590.8 | 0.180 | 0.00 | 0.75 | 0.25 | 0.00 |
| debris | -20.20 | -0.43 | 19.77 | 1401.8 | 0.110 | 0.00 | 0.49 | 0.40 | 0.10 |
| default | -20.14 | -0.73 | 19.41 | 369.0 | 0.123 | 0.19 | 0.75 | 0.05 | 0.00 |
| land | -19.90 | -3.03 | 16.87 | 61.4 | 0.221 | 0.99 | 0.01 | 0.00 | 0.00 |

Pairwise matrix: `matrix.md` (identical to the report's `matrix` object).

## Audition sheet

Command:

```bash
python3 godot_walk/scripts/footstep_audit.py render \
  --out godot_walk/evidence/2026-11-08-issue-203/audition.wav
```

`audition.wav` is 28.63 s, mono 22.05 kHz 16-bit (1,262,778 bytes). Order, three
repeats each, with a 120 ms 880 Hz beep before each tag and 0.6 s gaps:

```text
carpet, concrete, tile, plaster, metal, wood, debris, default, land
```

Each clip is RMS-normalised to -19.9 dBFS (peak-limited at 0.98), so the
comparison is equal-loudness rather than equal-peak. Applied gains are all
~1.000 because the stems already sit on the target.

**Pending operator step:** listen to `audition.wav` and judge material
distinctness, weight and loudness. This agent cannot listen to audio.

### Operator launch command

Seed 6 crosses generated carpet, the industrial-hall concrete library modules and
the debris/window-rock library modules:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-6-gmap-0.9.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-6-gmap-0.9.0/index.json
```

Walk from the spawn through the generated rooms into the library modules and
back; hold Shift to compare sprint footsteps and jump to hear the landing. This
is the requested operator listen, not part of the automated checks. Operator
approval is required before closing the issue.

## Verification

- `python3 godot_walk/scripts/generate_footstep_audio.py check` —
  `{"errors": [], "valid": true}` (132 stems and the manifest reproduce exactly).
- `python3 -m pytest -q godot_walk/scripts/test_footstep_audio.py` — 3 passed:
  determinism/completeness, every stem has the required sibling layers, every
  mix is within the #202 loudness tolerance, loudness constant matches #202.
- `python3 -m pytest -q godot_walk/scripts/test_footstep_audit.py` — 4 passed,
  1 skipped (the v0.2.0 baseline assertion correctly skips on 0.3.0; the new
  v0.3.0 pass assertion covers the committed set).
- `python3 -m pytest -q godot_walk/scripts` — **636 passed, 5 skipped,
  58 subtests passed** in 124.67 s.
- `ruff check` and `ruff format --check` on all four changed Python files pass.
- Headless:

```bash
godot4 --headless --audio-driver Dummy --path godot_walk \
  --script res://scripts/test_issue200_footsteps.gd -- \
  --map=res://room_catalog/generative_maps/gmap-6-gmap-0.9.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-6-gmap-0.9.0/index.json
```

Result:

```text
ISSUE200_FOOTSTEPS: PASS failures=0
```

The test now also asserts the four layer pools with four players each, all
required stream sets (four variants per tag/layer and one landing variant),
exactly three playing players for one step, a fixed node count across walking/
sprinting/landing, and walk/sprint force mapping. It does not assert audio
output.

## Deviations and review points

- The wet layer is omitted as allowed by the issue.
- Onset offsets are baked into the stems rather than scheduled at runtime. This
  gives sample-accurate 0–8 ms offsets with no per-step timer or player
  allocation; the runtime still chooses the offset independently per layer and
  variant.
- The transient brightness crossfade is dithered across steps (probability of
  the hard tier follows force) to respect the three-players-per-step budget.
- Six of 33 mixes are peak-limited to 0.98 and therefore land up to 0.97 dB below
  the exact target; all stay inside the #202 ±1.5 dB tolerance.
- Room reverb, realtime synthesis, physical modelling, neural synthesis and
  ambient tones remain out of scope.

## Files

- `godot_walk/scripts/generate_footstep_audio.py`
- `godot_walk/audio/footsteps/` (132 new stems, 34 old flat samples removed)
- `godot_walk/audio/footsteps/provenance.json`
- `godot_walk/scripts/footstep_audit.py`
- `godot_walk/scripts/test_footstep_audio.py`
- `godot_walk/scripts/test_footstep_audit.py`
- `godot_walk/scripts/walk_player.gd`
- `godot_walk/scripts/test_issue200_footsteps.gd`
- `godot_walk/evidence/2026-11-08-issue-203/REPORT.md`
- `godot_walk/evidence/2026-11-08-issue-203/audit.json`
- `godot_walk/evidence/2026-11-08-issue-203/matrix.md`
- `godot_walk/evidence/2026-11-08-issue-203/audition.wav`
