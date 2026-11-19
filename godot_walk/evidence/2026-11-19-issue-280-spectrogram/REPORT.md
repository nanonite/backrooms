# Issue #280 — ffmpeg spectrogram image output for the #276 audio capture

Worker report, 2026-11-19. Chainlink task 280, workflow chainlink_bphi8,
attempt 1/2. Host: Godot `4.6.3.stable.official.7d41c59c4`, `DISPLAY=:1`,
system `ffmpeg 6.1.1`, flake `ffmpeg 8.1`, Python 3.12.3, numpy 2.5.3.

**No sound is declared acceptable by an agent.** This change gives an agent two
things it did not have: the #276 numeric measurements **and a picture of the
same sound**. It does **not** let an agent judge whether anything sounds right,
and it does **not** replace operator listening. The operator listens to the real
captures and decides. No material, room, reverb or sound quality is claimed or
inferred here.

## 1. Scope read before authoring

- Issue #280 and its comments (none appended), the related closed #276 issue
  text, the #276 evidence `REPORT.md` in full,
  `godot_walk/scripts/issue276_capture_audio.py`,
  `godot_walk/scripts/issue276_analyze_audio.py`,
  `godot_walk/scripts/test_issue276_analyze_audio.py`, the #276 fixture
  `fixture/audio_probe.gd`, and `devShells.audioAnalysis` in `flake.nix`.
- The guarded render pattern (`exclusive_gpu_job`, `check_capture_headroom`,
  `PeakResourceSampler`) and the frozen-file list.
- `ffmpeg -h filter=showspectrumpic` / `showwavespic` to confirm the available
  filter options before choosing fixed parameters.

## 2. Deliverables

New files:

- `godot_walk/scripts/issue280_spectrogram.py` — fixed-parameter ffmpeg renders
  (`render`, `selftest`, `determinism`), PNG→gray decode and the mechanical
  layout check.
- `godot_walk/scripts/test_issue280_spectrogram.py` — 8 CPU-only tests.
- This `REPORT.md` and `selftest.json` (the machine-check result).

Additive change to the #276 wrapper only:

- `godot_walk/scripts/issue276_capture_audio.py`: `49` lines added, `0` removed
  (`git diff --numstat`). New `--waveform` / `--no-spectrogram` flags; after the
  existing verify step it renders the spectrogram from the normalised WAV,
  writes the PNG beside the measurement JSON, and records the path, SHA-256 and
  size in the receipt. It adds three **new** keys to the measurement JSON
  (`spectrogram_png`, `waveform_png`, `spectrogram_parameters`); a key-set diff
  against the tracked `synthetic-1_measurement.json` shows `removed keys: []`,
  `changed existing keys: []`. No tracked expectation value was edited.

No hash-pinned file was touched (`scripts/player.gd`, `project.godot`, library
room scenes, `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md` all show no
diff). `flake.nix` was **not** changed — `devShells.audioAnalysis` already
provides ffmpeg. `registration_accepted` and `scale_calibrated` remain `false`
everywhere in `catalog.json`. No model call and no download beyond the flake
pin. Captured media and all PNGs stay git-ignored
(`godot_walk/evidence/**/captures/`, `godot_walk/evidence/**/*.png`); only JSON
and this report are tracked.

## 3. Fixed, documented render parameters

| Parameter | Value | Reason |
|---|---|---|
| filter | `showspectrumpic` | ffmpeg-native, no Python imaging dependency |
| size (filter plot area) | `1600x900` | legible at full view, ~66–90 kB PNG |
| actual PNG with legend | `1884x1028` | ffmpeg adds axis/margin area |
| mode / colour | `combined` / `intensity` | one mono plot, magnitude→colour |
| scale / fscale | `log` / `log` | dB amplitude, log frequency axis |
| start / stop | `20 Hz` / `24000 Hz` | 48 kHz Nyquist: shows the #276 full-scale alternating clip near 24 kHz |
| drange / limit | `80 dB` / `0 dBFS` | fixed 0…−80 dB window, comparable captures |
| window | `hann` | showspectrumpic default, made explicit |
| legend | `true` production, `false` for machine checks | axis labels for viewing; no grid for pixel analysis |
| optional waveform | `showwavespic=s=1600x220:scale=lin:split_channels=false` | time-domain envelope strip |

Legend-free check renders are exactly `1600x900`; `image_size()` asserts that,
so the pixel row↔frequency calibration is only applied to images rendered with
those parameters.

## 4. Acceptance 1 — one-command capture also produces the PNG

```
$ DISPLAY=:1 python3 godot_walk/scripts/issue276_capture_audio.py capture --name spectrogram-280-final --mode synthetic --waveform
ISSUE276_MEASURE source=movie.avi duration=4.0s peak=0.0dBFS centroid=439.9667Hz write=created
ISSUE276_MEASURE_JSON /mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/spectrogram-280-final_measurement.json
ISSUE276_VERIFY PASS checks=8 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/spectrogram-280-final_measurement.json
ISSUE280_SPECTROGRAM godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/spectrogram-280-final_spectrogram.png sha256=1b79c8789430844caa3e7a606a6b94aca074f61c901663bdf5762d2fc73013b7 size=1884x1028 legend=true
ISSUE280_WAVEFORM godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/spectrogram-280-final_waveform.png sha256=7b133f711d47255f5ebc4887910208651c98212a9865eb08c5ad4cdcd95e65ac
ISSUE276_RECEIPT godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/receipts/spectrogram-280-final_receipt.json pass=True
EXIT=0
```

The receipt records `spectrogram_png`, `spectrogram_sha256`,
`spectrogram_size`, `waveform_png`, `waveform_sha256`, `spectrogram_enabled`,
`waveform_enabled` and `verification_pass: true`. The measurement JSON records
the same two relative paths plus `spectrogram_parameters`.

## 5. Acceptance 2 — synthetic tone / clip / silence, seen and measured

```
$ python3 godot_walk/scripts/issue280_spectrogram.py selftest --output godot_walk/evidence/2026-11-19-issue-280-spectrogram/selftest.json
ISSUE280_SELFTEST PASS tone_row=430 clip_row=0 silence=[0.0, 0.0]
EXIT=0
```

The signal is the exact #276 selftest WAV from
`issue276_analyze_audio._synthetic_wav` (0.75 s silence, 1 s 440 Hz tone, 0.5 s
full-scale alternating clip, 0.75 s silence). The mechanical check decodes the
legend-free PNG to grayscale with ffmpeg rawvideo and verifies four named
checks, all `true` in `selftest.json`:

- `tone_at_440hz_row`: peak row 430 equals the pure-440 Hz calibration render's
  peak row 430 (tolerance 8 rows) — this *is* the "energy at the 440 Hz row"
  check, with the row established by an independent known-tone render.
- `clip_near_nyquist`: clip-region peak row 0 (top of the plot, ~24 kHz).
- `clip_broadband`: 130 rows above 15/255 in the clip region.
- `silence_gaps_near_zero`: mean column brightness 0.0 in both silence spans.

`test_mechanical_check_rejects_blank_image` confirms the check fails on an
all-black image, so it is not tautological.

**What I saw when I viewed the images myself.** In the production spectrogram
rendered from that #276 synthetic WAV (`/tmp/issue280-selftest-view.png`, 1884×1028):
the time axis reads 0–3.00 s, the frequency axis 40 Hz at the bottom to 20504 Hz
at the top, and the right-hand colour bar runs 0 to −80 dBFS. The two outer
stretches (0–0.75 s and ~2.25–3.00 s) are solid black — the silence gaps. From
~0.75 s to ~1.80 s there is a narrow pair of bright horizontal bands, with sharp
vertical onset/offset transients; an independent pure-440 Hz render places its
bands at the identical rows, so this pair is the 440 Hz tone (a log-frequency
bin-mapping artifact of ffmpeg, **not** two different tones). From ~1.80 s to
~2.25 s there is a bright red band at the very top and a broad purple block
fading downward — the deliberately clipped, full-scale segment, whose energy is
mostly near Nyquist. In the captured Godot `tone_then_clip` spectrogram the
tone runs 0–2 s and the clip 2–4 s (`audio_probe.gd` defines 2 s + 2 s), with no
silence gap; that is why the silence check is performed on the #276 *selftest*
signal, which does contain the gap. In the waveform PNG the 0–2 s tone is a thin
centred red band and the 2–4 s clip is a solid full-height red block.

## 6. Acceptance 3 — determinism, reported honestly

Same WAV, same ffmpeg version → byte-identical PNG:

```
$ python3 godot_walk/scripts/issue280_spectrogram.py determinism --input .../captures/spectrogram-280-final/audio_48k_mono.wav
ISSUE280_DETERMINISM PASS identical=True sha256=1b79c8789430844caa3e7a606a6b94aca074f61c901663bdf5762d2fc73013b7 size=1884x1028
EXIT=0
```

Two full guarded captures of the same fixture (`spectrogram-280-a` and
`spectrogram-280-b`) recorded the same spectrogram SHA-256
`1b79c878…07f61c901663bdf5762d2fc73013b7` and waveform SHA-256
`7b133f71…cdcd95e65ac` in their receipts.

**Cross-version claim — NOT byte-identical.** The VERIFY item asked whether
host and flake ffmpeg produce the same image. They do not produce the same
*bytes*:

```
$ python3 issue280_spectrogram.py render --input <WAV> --output /tmp/issue280-host.png     # host ffmpeg 6.1.1
ISSUE280_SPECTROGRAM /tmp/issue280-host.png sha256=1b79c878... size=1884x1028 filter_size=1600x900 legend=true
$ nix develop .#audioAnalysis --command python3 issue280_spectrogram.py render --input <WAV> --output /tmp/issue280-flake.png   # ffmpeg 8.1
ISSUE280_SPECTROGRAM /tmp/issue280-flake.png sha256=32ea34317e8f14ed883470619155a505f4ca5e0dc829f0335c99ad14e9821e8f size=1884x1028 filter_size=1600x900 legend=true
$ sha256sum /tmp/issue280-host.png /tmp/issue280-flake.png
1b79c8789430844caa3e7a606a6b94aca074f61c901663bdf5762d2fc73013b7  /tmp/issue280-host.png
32ea34317e8f14ed883470619155a505f4ca5e0dc829f0335c99ad14e9821e8f  /tmp/issue280-flake.png
$ cmp -s /tmp/issue280-host.png /tmp/issue280-flake.png; echo $?
1
```

However, the **decoded grayscale pixels are identical**:

```
pixels: 1936752 identical_pixels: 1936752 differing_pixels: 0 max_delta: 0 mean_delta: 0.0
```

So the byte difference is PNG container/encoder metadata between libavcodec
versions, not a different picture. Determinism is claimed **within one ffmpeg
version**; for cross-version work compare decoded pixels, not file hashes. The
selftest also passes inside the flake shell (`ISSUE280_SELFTEST PASS
tone_row=430 clip_row=0 silence=[0.0, 0.0]`, `ffmpeg version 8.1`).

## 7. Acceptance 4 — existing #276 tests and expectations still pass

```
$ python3 -m pytest -q godot_walk/scripts
1582 passed, 5 skipped, 94 subtests passed in 278.31s (0:04:38)
EXIT=0
```

Baseline before this task was 1574 passed + 5 skipped; the 8 additional passes
are the new `test_issue280_spectrogram.py` tests. All #276 expectations are
byte-unchanged, and `verify` still reports `ISSUE276_VERIFY PASS checks=8` for
the new capture.

## 8. Required verification commands (exact result lines)

```
$ python3 godot_walk/scripts/issue276_analyze_audio.py selftest
ISSUE276_SELFTEST PASS tone=440Hz clipping=detected silence=detected
EXIT=0

$ python3 godot_walk/scripts/register_video_sources.py validate
{
  "valid": true,
  "registered_count": 13
}
EXIT=0

$ python3 -m ruff check godot_walk/scripts/issue280_spectrogram.py godot_walk/scripts/test_issue280_spectrogram.py godot_walk/scripts/issue276_capture_audio.py
All checks passed!
RUFF_EXIT=0

$ git diff --numstat
49	0	godot_walk/scripts/issue276_capture_audio.py
```

The capture command with `DISPLAY=:1` is quoted in section 4; `--headless`
Movie Maker is still unsupported on this host and was not attempted.

## 9. Acceptance 5/6 — limits, and the explicit agent statement

A spectrogram cannot tell you whether the sound is *good*. From these images an
agent can read where energy sits in time and frequency, onsets and sharp cuts,
broadband versus narrowband content, gross clipping and silence gaps, and a
display-referred dB level. It cannot read phase, exact sample values, precise
frequency beyond the log-bin resolution, room/material identity, reverb
character or naturalness, or whether a footstep "sounds right". The 0…−80 dB
scale is ffmpeg's display scale, not a calibrated measurement. The 440 Hz pair
of bands is a render artifact confirmed by calibration; without that
calibration it would be easy to misread. The Godot `tone_then_clip` fixture has
no silence gap, so the gap check uses the separate #276 selftest signal. The
decay/RT60 fields remain uncalibrated estimates from #276, not accuracy claims.

**Therefore:** this work lets an agent inspect numeric measurements **and a
picture of the sound**. It does not let the agent judge whether the sound is
acceptable, and it does not replace operator listening. No sound is declared
acceptable, correct or identifiable by an agent. The operator must listen to
the real captures and decide whether it is useful.
