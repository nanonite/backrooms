# Capture fixtures — repeatable accepted / rejected clips

`capture_gate.py` decides whether a video can support a walkable splat. That
decision has to be checkable, so it is checked against clips whose properties are
*known by construction* rather than against a recording of what the code used to
print. A test asserting a verdict is only worth having if the fixture really has
the property it exists to exercise — `test_capture_fixtures.py` therefore probes
each clip for its defining property first (a "moving content" fixture whose object
covers 0.1% of the frame would otherwise silently test nothing).

## Regenerating

```bash
python3 scripts/splat_pipeline/fixtures/make_capture_fixtures.py
```

Needs `ffmpeg` and numpy. Writes to `fixtures/clips/`. Deterministic: every
scene is generated from a fixed seed, so the clips are byte-comparable across
runs on the same ffmpeg build. `build_fixture` asserts the frame count and the
first/last frame size against the fixture's declared shape, because the
thresholds in the gate are stated against a resolution and a fixture that
silently changed size would be testing the wrong regime.

## The clips

| Clip | Frames | Size | Expected | Property it exercises |
|------|--------|------|----------|-------------------------|
| `accepted_walkthrough` | 96 | 640×360 | accepted | Static scene, real translation, no cuts |
| `accepted_720p` | 48 | 1280×720 | accepted | 720p is enough to match features and is never a refusal |
| `stationary_camera` | 96 | 640×360 | rejected | The camera never moves: everything else identical |
| `cut_sequence` | 96 | 640×360 | rejected | Hard cuts between unrelated scenes |
| `moving_content` | 96 | 640×360 | warned | An object crosses the frame; still reconstructible |
| `incoherent_geometry` | 96 | 640×360 | rejected | Texture regenerated every frame: no scene persists |
| `long_walkthrough` | 900 | 640×360 | accepted | 9× the length: the bounded-work case |

`accepted_720p` exists specifically to hold the resolution rule honest. "Reject
720p" was the previous behaviour and it was wrong — 720p matches features
reliably and only costs detail at distance — so it needs a fixture that would
catch the rule creeping back, not just a test that describes the intent.

## Recorded command outputs

`command_outputs/` holds the output of each command below, so the numbers in the
gate's docstrings and threshold comments can be checked against a real run rather
than taken on trust. Regenerate them with the same commands.

### Verdicts, one per clip

```bash
for clip in accepted_walkthrough accepted_720p stationary_camera cut_sequence \
            moving_content incoherent_geometry long_walkthrough; do
    python3 scripts/splat_pipeline/capture_gate.py \
        scripts/splat_pipeline/fixtures/clips/$clip.mp4 \
        > scripts/splat_pipeline/fixtures/command_outputs/gate_$clip.txt 2>&1
    echo "$clip exit=$?"
done
```

Observed exit codes and verdicts:

| Clip | Exit | Verdict |
|------|------|---------|
| `accepted_walkthrough` | 0 | ACCEPTED |
| `accepted_720p` | 0 | ACCEPTED |
| `stationary_camera` | 3 | REJECTED |
| `cut_sequence` | 3 | REJECTED |
| `moving_content` | 0 | ACCEPTED_WITH_WARNINGS |
| `incoherent_geometry` | 3 | REJECTED |
| `long_walkthrough` | 0 | ACCEPTED |

`moving_content` exiting 0 is the point of it: a person in shot is a fact about
the capture to weigh, not a refusal. `stationary_camera` is rejected even though
every other measurement of it is as good as the accepted walk, because the only
difference is that the camera never moved.

### The long-clip bounded-work case

```bash
python3 scripts/splat_pipeline/capture_gate.py \
    scripts/splat_pipeline/fixtures/clips/long_walkthrough.mp4 \
    --json /tmp/long.json

python3 scripts/splat_pipeline/sample_frames.py \
    scripts/splat_pipeline/fixtures/clips/long_walkthrough.mp4 /tmp/long.json \
    --out /tmp/long_images
```

The 900-frame clip selects 150 frames — inside the 100–200 small-room
hypothesis — and the candidate pass keeps 180 of 900 at a stride of 5, so 20% of
the clip is scored and the rest is never retained. Extraction then costs exactly
150 ffmpeg invocations, one per kept frame, rather than a decode pass over 900.

Recorded in `command_outputs/gate_long_walkthrough.txt` and
`command_outputs/sample_long_walkthrough.txt`.

### Registration coverage

`model_coverage.py` is exercised against models written by
`tests/build_colmap_model.py`, which emits real `cameras.bin` / `images.bin`
records so the report is checked against the format rather than a mock.

```bash
# 150 of 150 frames registered -> exit 0
#   fixtures/command_outputs/model_coverage_full.txt

# 60 of 150 frames registered -> exit 2, names the 90 unregistered frames
#   fixtures/command_outputs/model_coverage_partial.txt

# two components in sparse/0 and sparse/1 -> exit 0, names the unused one
#   fixtures/command_outputs/model_coverage_two_components.txt
```

The two-component case is why the largest model is not chosen silently: COLMAP
splits a disconnected reconstruction across `sparse/0` and `sparse/1`, and the
model with the most images wins — which is usually right, but the report has to
say that it made that choice and name what it left out.

## Measured basis for the thresholds

The threshold constants in `sampling_budget.py` and `capture_verdict.py` carry
comments citing measured values. Those came from:

* the six 1080p captures in `data/videos/` (adjacent-candidate histogram
  distance 0.024–0.090, hot-block fraction p90 0.003–0.059, median adjacent
  residual 0.034–0.069);
* these fixtures, which bracket the interesting cases rather than the ordinary
  one.

When a threshold changes, the comment above it should change with it, and the
gate outputs in `command_outputs/` should be regenerated so the two agree.
