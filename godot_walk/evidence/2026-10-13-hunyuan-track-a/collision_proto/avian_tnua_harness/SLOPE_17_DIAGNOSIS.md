# 17 Degree Slope Gate Diagnosis and Resolution (2026-10-17)

The locked bounds are unchanged: capsule-bottom climb <= 0.25 m, peak
vertical speed <= 0.50 m/s, input-window position radius <= 0.02 m. All
runs used the CPU only.

## Root Cause

Two separate mechanisms cause the failure. Neither one is the air acceleration.

1. **Tnua 0.31 lift/drop cycle.** On ground steeper than `max_slope`, Tnua
   keeps the float spring on while the vertical velocity is positive. When
   that velocity reaches 0, it turns the spring off. The capsule therefore
   lifts toward float height, free-falls about 8.5 cm (sqrt(2 g 0.085) is
   1.29 m/s), lands on its collider, and lifts again. This produced the 1.25
   m/s peak and the 5.4 cm oscillation. The cycle persists on corrected
   geometry and on slopes from 17 to 30 degrees, at every approach speed
   tested.
2. **Fixture bug (fixed).** `spawn_slope` placed the incline at
   `3 tan(a) - 0.1 / cos(a)`. That left a 3.1 cm lip at the 17 degree foot,
   2.0 cm at 15 degrees, and a blocking step at 20 to 25 degrees or more.
   The approach slab also overlapped under the incline, which exposed buried
   end faces: the sensor reported "flat" hits at 74 to 89 degrees. The new
   `slope_layout` puts the incline's low edge exactly at y = 0 where the
   approach floor ends. Unit tests check the lip (< 1 mm), the overlap, and
   the incline angle (within 0.1 degrees).

## Changes in the Worktree

- `player_controller::steep_ground_toggle`: on ground steeper than
  `max_slope`, Tnua runs `SenseOnly` unless the shaped motion leads
  downhill. Tnua still senses the ground and clears `standing_on`, but its
  spring and slip boost are not applied. This removes the lift/drop cycle.
  With the old fixture, all 15 scenarios passed. On the 17 degree gate:
  climb 0.192 m, peak 0.345 m/s, radius 0.000 m, recovery in 16 ticks. The
  13 non-slope scenarios were bit-identical.
- The fixture fix described above. **With corrected geometry, the 17 degree
  gate fails again.** Peak vertical speed is 0.765 m/s, `min_y` is 0.59999
  against a minimum of 0.60, and the character does not end at rest. The
  14 other scenarios pass. The earlier pass depended on the lip lifting the
  capsule before the sensor saw the incline.

## Remaining Conflict: Hover Gap Against the Drop Bound

Tnua floats the capsule 0.10 m above the ground (float height 0.70 m,
capsule half-height 0.60 m). When the ground sensor sees unwalkable ground,
Tnua removes float support, with or without `SenseOnly`. The capsule then
drops up to the hover gap, which can reach sqrt(2 g 0.1) = 1.4 m/s. The
0.50 m/s bound allows a drop of about 1.3 cm.

The table shows the corrected fixture with the SenseOnly change. Speed is
the fraction of the 2 m/s walk speed.

| deg | speed 0.25 | speed 0.5 | speed 1.0 |
|---|---|---|---|
| 17 | 0.918 m/s FAIL | 0.772 FAIL | 0.470 pass |
| 20 | 0.766 FAIL | 0.622 FAIL | 0.459 pass |
| 25 | 0.467 pass | 0.318 pass | 0.474 pass |

Lowering the hover gap globally trades this off against the 0.20 m step.
With a float height of 0.66 m, the slopes pass at all speeds, but
`step_020m` takes 685 ticks instead of 240. At 0.62 m, `step_020m` fails.
No single float height satisfies both.

## Adopted: Steep Ground Acts as a Wall (Operator-Approved 2026-10-17)

`player_controller::steep_ground_command` returns the `TnuaToggle`, the
`SteepGroundHold` latch and the `LockedAxes` for each tick. The caller zeroes
the vertical velocity while the hold is set. The rules:

- The ground is unwalkable when its normal is more than 16 degrees from
  vertical. Tnua then runs SenseOnly unless input leads downhill, and still
  clears `standing_on`.
- A character that reaches unwalkable ground from walkable support keeps
  its height (Y locked). The hold stays on, including while the player steps
  back downhill, until the sensor finds walkable ground or no ground.
- Moving downhill over steep ground that drops away beyond float height
  releases the hold, so the character descends instead of hovering.
- A character that reaches steep ground without prior walkable support (for
  example while falling) is not held.

**Final run (schema 4, `walkability_report.json`).** All 15 blocking
scenarios pass and the suite exits 0. Runtime 19.72 s, peak RSS 80,424 KiB.
On the 17 degree gate: climb 0.100 m (the rest height), peak vertical speed
0.000 m/s, oscillation 0.000 m, `min_y` 0.6986 m, and the release reaches
flat support in 17 ticks and ends at rest. Tnua classified the incline on
every hit (angle above 16 degrees, `standing_on` none, 0 mismatches). The
12 non-slope scenarios match the earlier worker run field for field, apart
from RSS.

**Caveat.** While held, vertical speed and oscillation are 0 because the
controller holds them, not because the physics settles. Climb and recovery
are still measured physically.

**Non-blocking diagnostics** (`steep_rejection_diagnostic_*`) cover 17, 20,
25 and 30 degrees at 25, 50 and 100% approach speed. 10 of 11 pass. At 30
degrees and 25% speed, the incline is first sensed at tick 166. The
character then coasts at 0.5 m/s, with the motor off and height held, until
its capsule touches the incline, and then stays still. The 60-tick
stability window ends at tick 240, so it still includes the end of that
coast and reports 0.039 m. The window was left unchanged.

**Carrying this to Godot.** `CharacterBody3D` is kinematic and has no float
spring, so the Tnua lift/drop cycle cannot occur there. The "steep ground
acts as a wall" behaviour corresponds to `floor_max_angle` (16 degrees),
`floor_block_on_wall`, `floor_stop_on_slope` and `floor_snap_length`. What
carries over is the test design: correct slope geometry (no lip, no buried
faces) and the same no-climb, no-drop, no-jitter checks.
