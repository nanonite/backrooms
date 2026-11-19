# Issue #276 — Godot Movie Maker audio capture and an agent-readable analysis step

Worker report, 2026-11-19. Chainlink task 276, workflow chainlink_ru5ey, attempt 1/2.
Host: Godot `4.6.3.stable.official.7d41c59c4`, `DISPLAY=:1`, RTX 4070 Ti,
`godot4` at `/home/goya/.local/bin/godot4`, system `ffmpeg 6.1.1`, Python 3.12.3.

**No sound is declared acceptable by an agent. Numeric measurements do not
replace the operator listening.** This issue only produces recordings and
measurements; the operator decides whether footsteps or room acoustics sound
right. No material, room or reverb quality is claimed or inferred here.

## 1. Scope read before authoring

- Issue #276 and its comments (none appended), related #266 (closed) and #274
  (closed), `docs/research/issue-274-audio-mcp-linux.md` in full, the #266 evidence
  `REPORT.md` and `gallery_entry_v0.1.0.json`, and
  `godot_walk/scripts/issue266_room_audio.py`.
- The #266 runtime path: `walk_player.gd` (pooled `AudioStreamPlayer` footsteps,
  fixed seed used only by this fixture), `room_reverb_bus.gd`
  (`AudioEffectReverb` on the `Footsteps` bus), `room_acoustic_probe.gd`, and
  `maze_follower_audio.gd` (the separate `AudioStreamPlayer3D` follower cues).
- The existing guarded render pattern (`run_capture_guarded.py`,
  `gpu_job_lock.py`, `psx_design_round_resources.py`) and the frozen-file list.

## 2. Deliverables (new files only, plus one additive flake change)

New scripts:

- `godot_walk/scripts/issue276_capture_audio.py` — guarded one-command capture.
- `godot_walk/scripts/issue276_analyze_audio.py` — ffmpeg decode + measurement JSON.
- `godot_walk/scripts/test_issue276_analyze_audio.py` — 8 CPU-only tests.
- `godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/fixture/audio_probe.gd`
  — synthetic tone / clipped / `tone_then_clip` / `spatial3d` signal.
- `.../fixture/walk_capture.gd` and `.../fixture/acoustic_zone.gd` — deterministic
  scripted walk through an accepted #266 room with the real footstep + bus code.

Tracked evidence (JSON): `receipts/*.json` (per run: Godot version, full command,
fps, frame count, duration, SHA-256 of movie/audio/WAV, guard data, verification),
`measurements/*.json`, `expectations/*.json`, `selftest_measurement.json`,
`determinism.json`, `reverb_ab_2.json`, and this report.

Captured media (`.avi`, `.wav`, numbered `.png`, `godot.log`) stays under
`.../captures/`, already git-ignored by `godot_walk/evidence/**/captures/`.

**Flake:** `flake.nix` already existed, so it was **extended additively**: a new
`devShells.audioAnalysis` was added providing `ffmpeg`, `uv`, and
`python3.withPackages [numpy scipy]`. `git diff --numstat flake.nix` is
`34 0` — 34 lines added, **0 removed**. No input, hash, existing devShell or
package was changed. A new standalone flake was not necessary.

No hash-pinned file was touched: `scripts/player.gd`, `project.godot`, library
room scenes, `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md`, accepted
room files and frozen contracts are unchanged. `registration_accepted` and
`scale_calibrated` remain `false`. No model call and no download outside the
pinned flake inputs was made.

## 3. One-command capture and analysis (acceptance 1 and 6)

```
python3 godot_walk/scripts/issue276_capture_audio.py capture --name walk-final-a --mode walk --reverb on
```

The wrapper acquires the shared GPU lock, runs the guard preflight, samples peak
resources, renders through `DISPLAY=:1` with `--rendering-driver vulkan
--fixed-fps 30 --quit-after 120`, converts to 48 kHz mono WAV, writes the
measurement JSON and verifies it against the tracked expectations. Conversion is
part of the command, not a step the agent must remember. Exact output:

```
ISSUE276_MEASURE source=movie.avi duration=4.0s peak=-1.5473dBFS centroid=3319.9225Hz write=created
ISSUE276_MEASURE_JSON /mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/walk-final-a_measurement.json
ISSUE276_VERIFY PASS checks=4 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/walk-final-a_measurement.json
ISSUE276_RECEIPT godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/receipts/walk-final-a_receipt.json pass=True
EXIT=0
```

The room is `nested-light-corridor-v1` (accepted #173). Its #266 floor tag
`tile` is set on the floor collider at runtime, and the real `walk_player.gd`
plays seven material footsteps through the `Footsteps` bus. The fixture prints:

```
AUDIO276_WALK_READY room=nested-light-corridor-v1 tag=tile steps=7 frames=120 seed=20261119 reverb=true
```

## 4. VERIFY claims (a)–(d), answered from command output

### (a) Which `--write-movie` outputs carry audio, and their exact names

Both documented forms carry audio on 4.6.3. **`.avi`** is one file with MJPEG
video *and* a PCM audio stream; **`.png`** writes numbered PNG frames *plus a
sibling `.wav`*.

```
$ ffprobe -v error -show_entries stream=index,codec_name,codec_type,sample_rate,channels,channel_layout,bits_per_sample,duration,nb_frames -show_entries format=duration,size -of default=noprint_wrappers=1 captures/probe-display.avi
index=0
codec_name=mjpeg
codec_type=video
duration=2.000000
nb_frames=60
index=1
codec_name=pcm_s16le
codec_type=audio
sample_rate=48000
channels=2
channel_layout=unknown
bits_per_sample=16
duration=N/A
nb_frames=96000
duration=2.000000
size=1133260
```

```
$ ffprobe -v error -show_entries stream=index,codec_name,codec_type,sample_rate,channels,channel_layout,bits_per_sample,duration -show_entries format=duration,size -of default=noprint_wrappers=1 captures/probe-display-png/probe.wav
index=0
codec_name=pcm_s32le
codec_type=audio
sample_rate=48000
channels=2
channel_layout=unknown
bits_per_sample=32
duration=2.000000
duration=2.000000
size=768044
```

PNG frames are named with an eight-digit zero-padded suffix: `probe00000000.png`
… `probe00000059.png`, plus `probe.wav`. The guarded wrapper's PNG run produced
`movie00000000.png` … `movie00000119.png`, `movie.wav` and `godot.log` (122 files):

```
ISSUE276_MEASURE source=movie.wav duration=4.0s peak=0.0dBFS centroid=439.9668Hz write=created
ISSUE276_VERIFY PASS checks=8 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/synthetic-png-2_measurement.json
ISSUE276_RECEIPT godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/receipts/synthetic-png-2_receipt.json pass=True
EXIT=0
```

The AVI tone measures centroid `439.9667 Hz`; the PNG sibling WAV measures
`439.9668 Hz` — the 0.0001 Hz difference is 16-bit AVI versus 32-bit WAV
quantisation. The AVI movie hash differs from the PNG audio hash by container
format, not by lost audio.

### (b) Dummy audio driver / `--headless` versus real display

**`--headless` does not work.** It forces the dummy *display* driver, and the
movie writer crashes in `texture_2d_get` before writing frames. Exact output
(`--write-movie .../probe-headless.avi`, `--fixed-fps 30 --quit-after 60`):

```
Movie Maker mode enabled, recording movie in 1152×648 @ 30 FPS...
AUDIO276_PROBE_READY mode=tone mix_rate=48000 frames=192000 seconds=4.000
ERROR: Parameter "t" is null.
   at: texture_2d_get (./servers/rendering/dummy/storage/texture_storage.h:106)
handle_crash: Program crashed with signal 11
rc=134
```

The PNG writer additionally refused to start because its output directory did
not exist — the directory must be pre-created:

```
ERROR: Condition "d.is_null()" is true. Returning: FAILED
   at: write_begin (servers/movie_writer/movie_writer_pngwav.cpp:74)
```

**The real display is required.** With `DISPLAY=:1` and `--rendering-driver
vulkan`, both output forms complete (`rc=0`, `60 frames at 30 FPS`). The **`Dummy`
audio driver is fine** when the real display is present; it is the dummy
*display* driver, not the dummy audio driver, that breaks Movie Maker:

```
$ DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --audio-driver Dummy --fixed-fps 30 --quit-after 60 --write-movie .../probe-dummy-audio.avi --script .../audio_probe.gd -- --mode=tone
rc=0
index=1
codec_name=pcm_s16le
codec_type=audio
sample_rate=48000
channels=2
nb_frames=96000
```

The Dummy-audio AVI and the default-driver AVI contain identical recovered tone
samples (peak `0.4883`, RMS `0.345163` in both). The wrapper therefore always
uses the guarded `DISPLAY=:1` path and records the display and driver in the
receipt.

### (c) Is #266 footstep / room-acoustic playback captured as in live play?

**Partially verified; no perceptual equivalence is claimed.** The accepted
room is instantiated read-only, the real `walk_player.gd` plays its pooled
`AudioStreamPlayer` footsteps through the `Footsteps` bus created by
`room_reverb_bus.gd`, and the `#205` probe runs. The mixed output is in the WAV:

```
ISSUE276_MEASURE source=movie.avi duration=4.0s peak=-1.5473dBFS centroid=3319.9225Hz write=created
ISSUE276_VERIFY PASS checks=4 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/walk-reverb-on-2_measurement.json
```

A dedicated `spatial3d` fixture confirms that `AudioStreamPlayer3D` audio is
captured too (that node type is used by the separate #239 follower-cue system,
not by #266 footsteps):

```
ISSUE276_MEASURE source=movie.avi duration=2.0s peak=-9.3169dBFS centroid=439.9991Hz write=created
ISSUE276_VERIFY PASS checks=7 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/spatial3d-1_measurement.json
```

The bus effect is **measurably present**: an on/off A/B of the same walk, with
the runtime acoustic zone enabled, gives (expected) different samples:

```
$ python3 godot_walk/scripts/issue276_analyze_audio.py compare --a .../walk-reverb-on-2_measurement.json --b .../walk-reverb-off-2_measurement.json --output .../reverb_ab_2.json
ISSUE276_DETERMINISM FAIL json_identical=False frames_identical=False peak_delta=0.00326538 rms_delta=0.00986451 centroid_delta=188.0394
EXIT=1
```

That `FAIL` is expected for an A/B: the shared `compare` checker is being used
to prove the configurations differ, not to prove repeatability. The earlier
A/B without the acoustic zone produced identical samples because the probe's
wet target was zero — it was corrected with a runtime-only metadata provider,
not by editing any room file. Honest limit: the level/centroid delta proves the
effect contributed to the captured mix; it does **not** prove the tail sounds
correct. The operator must listen.

### (d) Do two runs of the same scripted walk give the same samples?

**Yes, within a stated tolerance, and in fact bit-identically for audio.**
Final-script runs `walk-final-a` and `walk-final-b` (same room, seed 20261119,
120 frames, reverb on):

```
$ python3 godot_walk/scripts/issue276_analyze_audio.py compare --a .../walk-final-a_measurement.json --b .../walk-final-b_measurement.json --output .../determinism.json
ISSUE276_DETERMINISM PASS json_identical=True frames_identical=True peak_delta=0.0 rms_delta=0.0 centroid_delta=0.0
EXIT=0
```

Both receipts carry the same 48 kHz mono WAV SHA-256:
`a3fff4d8772f37646749ee0659120c9d27aec957ec5fdba24e5614f6f049e770`.
Stated tolerances are recorded in `determinism.json`: duration and peak/RMS
`<= 1e-6`, centroid `<= 1e-3 Hz`, clipping delta `0`. The **AVI container
hashes differ** between runs (MJPEG video metadata), so determinism is claimed
for the audio samples and the derived JSON, not for the whole movie file.

## 5. Synthetic tone / clipped-segment recovery (acceptance 2)

Pure-Python self-test (locally synthesised silence + 440 Hz tone + full-scale
segment + silence, no Godot, no download):

```
$ python3 godot_walk/scripts/issue276_analyze_audio.py selftest --output .../selftest_measurement.json
ISSUE276_SELFTEST PASS tone=440Hz clipping=detected silence=detected
ISSUE276_SELFTEST_JSON .../selftest_measurement.json
```

Godot-captured `tone_then_clip` fixture through the guarded wrapper:

```
ISSUE276_MEASURE source=movie.avi duration=4.0s peak=0.0dBFS centroid=439.9667Hz write=created
ISSUE276_VERIFY PASS checks=8 measurement=/mnt/sharedOs/backrooms-workspace/godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/measurements/synthetic-1_measurement.json
ISSUE276_RECEIPT godot_walk/evidence/2026-11-19-issue-276-movie-maker-audio/receipts/synthetic-1_receipt.json pass=True
EXIT=0
```

Documented tolerances (`expectations/*.json`): tone centroid 440 Hz ±120 Hz,
peak 0.99–1.0, at least 20000 near-full-scale samples, duration 3.9–4.1 s.
The clipped interval is reported at `2.001375 s – 4.0 s`, matching the fixture.
The clip is excluded from the FFT only (peak/RMS/clipping still use raw samples)
so it cannot bias the centroid estimate; this is stated in the measurement JSON.

## 6. Flake build and converter run from the flake (acceptance 5)

```
$ nix build .#devShells.x86_64-linux.audioAnalysis --no-link
this derivation will be built:
  /nix/store/bx6afaz5xb3qxwqvkwfd0j47l6khcxsy-backrooms-audio-analysis.drv
building '/nix/store/bx6afaz5xb3qxwqvkwfd0j47l6khcxsy-backrooms-audio-analysis.drv'...
EXIT=0
```

```
$ nix develop .#audioAnalysis --command python3 godot_walk/scripts/issue276_analyze_audio.py selftest
=== backrooms-audio-analysis dev shell (issue #276) ===
  [x] ffmpeg  ffmpeg version 8.1
  [x] numpy 2.4.4 scipy 1.17.1
ISSUE276_SELFTEST PASS tone=440Hz clipping=detected silence=detected
EXIT=0
```

`nix develop .#audioAnalysis --command python3 ... measure --input .../synthetic-1/movie.avi`
returned `ISSUE276_MEASURE ... centroid=439.9667Hz ...`, `EXIT=0`: the converter
runs from the flake with ffmpeg 8.1 and reproduces the system-ffmpeg result.

## 7. Required verification commands (exact result lines)

```
$ python3 -m pytest -q godot_walk/scripts
1574 passed, 5 skipped, 94 subtests passed in 276.85s (0:04:36)
EXIT=0
```

```
$ python3 godot_walk/scripts/register_video_sources.py validate
{
  "valid": true,
  "registered_count": 13
}
EXIT=0
```

```
$ python3 -m ruff check godot_walk/scripts/issue276_analyze_audio.py godot_walk/scripts/issue276_capture_audio.py godot_walk/scripts/test_issue276_analyze_audio.py
All checks passed!
EXIT=0
```

```
$ git diff --name-only
flake.nix
```

`flake.nix` is the only tracked file changed; it is additive (`34 0` lines).

## 8. Honest statement, limits and pending operator work

- Measurements do **not** replace operator listening. No footstep, room,
  reverb or material sound is declared acceptable, correct or identifiable by
  the agent. The operator listens to the real captures and decides.
- `registration_accepted` and `scale_calibrated` stay `false`. No ledger event,
  receipt of admission, catalog change or frozen hash was written.
- The reverb A/B proves the bus effect reaches the WAV, not that its character
  is right. RT60/decay fields are uncalibrated estimates, not accuracy claims.
  The fixture's `acoustic_zone.gd` is a runtime stand-in, not a measured room.
- Only one accepted room (`nested-light-corridor-v1`, tag `tile`) was walked;
  other #266 rooms, snow and rock/sand layers remain the operator's decisions
  from #266 and were not re-opened here.
- `--headless` Movie Maker capture is unsupported on this host (crash above);
  captures require the guarded `DISPLAY=:1` path. No system-sink routing or MCP
  server was built — that remains #274 territory.
