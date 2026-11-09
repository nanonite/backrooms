# Issue 205 — ray-cast room-acoustics probe and footstep reverb bus

**Status:** implementation and automated verification complete for review. The
operator listen is the pending human step; agents cannot hear audio.

## What changed

### Probe

`godot_walk/scripts/room_acoustic_probe.gd` (new) casts from the listener's
head:

- a horizontal fan of 12 rays around the full circle, so turning on the spot
  does not change the measurement;
- one up ray for ceiling clearance;
- collision layer 1, the same physics world and layer as the footstep floor
  ray. The player's own body RID is excluded.

The query object and direction table are created once. The probe itself has no
per-frame process; `walk_player.gd` samples it at 4 Hz and again on every
footstep and landing.

Measured metrics:

| metric | definition |
|---|---|
| `mean_distance_m` | mean horizontal hit distance; a missed ray counts as the 20 m ray length |
| `max_distance_m` | largest horizontal distance, with the same miss convention |
| `ceiling_height_m` | head height above the floor plus the up-ray distance, capped by the authored ceiling when the ray misses |
| `openness` | fraction of horizontal rays that miss |

Generated shape-room ceilings are rendered but have no collider, so the up ray
would otherwise report a 20 m ceiling in every generated room. `walk_player`
passes the current room's authored `ceiling_height_m` (or the map cell's
`ceiling_range_m`) as a fallback; a real ceiling collider still wins when one
exists. `generative_map_assembly.gd` exposes `room_ceiling_height_at` for this.

### Mapping

`RoomAcousticProbe.map_metrics` is a pure static function. Its current
constants:

| output | mapping |
|---|---|
| `room_size` | `0.10 + 0.78 * mean/10m + 0.12 * ceiling-height factor` |
| `damping` | `0.22 + 0.48 * mean/10m + 0.18 * ceiling-height factor + 0.12 * openness` |
| `wet` | `(0.18 + 0.48 * mean/10m + 0.14 * ceiling-height factor) * (1 - 0.35 * openness)` |
| `predelay_msec` | `clamp(mean / 343 m/s * 1000, 1 ms, 50 ms)` |

The ceiling-height factor runs from 2.2 m to 6.0 m. The mapping is monotonic:
a larger and taller room gives a larger room size, more damping, more wet and a
longer pre-delay. Open space keeps some size but loses wet level.

### Bus and room flag

`godot_walk/scripts/room_reverb_bus.gd` (new) owns one stock
`AudioEffectReverb` on a dedicated **Footsteps** bus. The bus and effect are
created in code because `project.godot` is frozen; `walk_player.gd` routes all
16 pooled footstep players, including `land`, to it. Ambient sound (#82) will
use a different bus.

- The current room flag is read from the instanced room metadata on every probe
  sample through `generative_map_assembly.room_reverb_at`. A runtime
  `set_room_reverb` mutation is therefore picked up within about 0.25 s; the
  flag is never baked into the player or the bus.
- A dry room forces the wet target to zero. The effect still passes the dry
  signal (`dry = 1.0`, `wet = 0.0`), so the bus adds no audible tail.
- Wet level crossfades over about 0.5 s. Room size, damping and pre-delay ease
  over about 0.3 s. All use exponential easing and snap once the remaining
  difference is below 0.001, so parameters never jump.
- Project-level disable switch:
  `audio/room_acoustics/footstep_reverb_enabled`, default **on**. When off, no
  bus or probe is created and the pooled players stay on Master.

### Room lookup

`generative_map_assembly.gd` also gains `cell_at(world_position)` and
`room_reverb_at(world_position)`. The highest compatible floor wins, then the
smaller envelope, so a threshold cell inside a larger room is preferred. A
missing `reverb_enabled` flag reads as dry, as required.

## Measured values on gmap-279-gmap-0.11.0

Captured by a headless probe walk with the same scene the operator will launch:

| room | flag | mean wall | ceiling | room_size | damping | wet | pre-delay |
|---|---|---:|---:|---:|---:|---:|---:|
| `c00` spawn hall (dry) | dry | 5.34 m | 4.2 m | 0.580 | 0.571 | target 0 | 15.6 ms |
| `c04` wet hall | wet | 6.55 m | 4.6 m | 0.687 | 0.648 | 0.583 | 19.1 ms |
| `c09` wet small room | wet | 2.77 m | 4.7 m | 0.395 | 0.471 | 0.405 | 8.1 ms |
| `c02` wet room | wet | 6.62 m | 4.1 m | 0.676 | 0.628 | 0.568 | 19.3 ms |

The wet hall and wet small room deliberately sound different: the hall has a
larger room, more damping, more wet and a longer pre-delay. The dry spawn
computes the same kind of mapping but its target wet is zero.

## Checks run

### New headless test

```bash
godot4 --headless --audio-driver Dummy --path godot_walk \
  --script res://scripts/test_issue205_acoustics.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.11.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.11.0/index.json
```

Result:

```text
ISSUE205_ACOUSTICS: PASS failures=0 box_mean=2.206 corridor_mean=4.552 wet=0.550
```

The test covers:

- a closed 5 x 3 x 3 m box: zero openness, 3.0 m ceiling, mean 2.206 m;
- an open-ended 20 x 2 x 3 m corridor: openness above 0.1, mean 4.552 m,
  larger mapped room than the box, same 3.0 m ceiling;
- monotonic mapping across 1-10 m mean distances, the `mean / 343` pre-delay
  formula and the 50 ms clamp;
- bus creation with exactly one reverb effect, no first-frame jump, wet target
  reached in a wet room, and exact zero reached in a dry room;
- all 16 footstep players routed to the Footsteps bus;
- the walkthrough scene on the committed map: dry spawn, wet `c09`, the
  geometry-following target, a runtime `set_room_reverb` flip to dry with a
  zero crossfade, and a missing flag reading as dry;
- the project toggle disabling the bus and leaving players on Master.

The same test passes on all four committed gmap-0.11.0 maps (seeds 1, 2, 3 and
279).

### Regression checks

- `test_issue200_footsteps.gd` — PASS (`ISSUE200_FOOTSTEPS: PASS failures=0`).
- `test_issue206_jump.gd` — PASS (`ISSUE206_JUMP: PASS failures=0`, height
  0.936 m).
- `test_issue204_reverb.gd` on gmap-279 — PASS, including the legacy gmap-0.10.0
  dry control.
- `test_issue201_elevation.gd` on gmap-279 — PASS.
- Full Python suite: **663 passed, 5 skipped, 58 subtests passed** in 388.53 s
  (6m28s). No Python files changed.

### Runtime scene

```bash
godot4 --headless --audio-driver Dummy --path godot_walk --quit-after 240 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.11.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.11.0/index.json
```

The scene ran 240 frames with no script errors.

## Pending human step

**Operator listen.** This agent cannot hear audio, and the automated checks do
not assert audible output. Launch the wet/dry candidate:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.11.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.11.0/index.json
```

Walk out of the dry spawn hall (`c00`) into the wet hall (`c04`) and the wet
small room (`c09`), then back. The expected tell is dry carpet at spawn, a
larger ringing tail in the hall, and a smaller, shorter tail in the small room.
The map SVG is
`godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.11.0.svg`.

Operator approval of the reverb character and wet level is still pending, as is
the operator walk of `gmap-279-gmap-0.11.0` itself.

## Out of scope / follow-up

- Wall-material absorption from ray hits is not implemented. The #205 note
  already records this as a possible later research issue.
- Ambient tones (#82) and convolution reverb remain out of scope.
- The feature is a startup project setting; changing it at runtime is not
  required for this issue.

## Files changed by this issue

- `godot_walk/scripts/room_acoustic_probe.gd` (new)
- `godot_walk/scripts/room_reverb_bus.gd` (new)
- `godot_walk/scripts/walk_player.gd`
- `godot_walk/scripts/generative_map_assembly.gd`
- `godot_walk/scripts/test_issue205_acoustics.gd` (new)
- `godot_walk/evidence/2026-11-09-issue-205/REPORT.md` (new)
