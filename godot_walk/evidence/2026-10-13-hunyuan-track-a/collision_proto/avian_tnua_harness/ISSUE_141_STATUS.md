# Issue #141 Status

> **2026-10-17 update:** the 17 degree figures below are out of date. The
> shared controller now treats steep ground as a wall, and the slope fixture
> bug is fixed. All 15 blocking scenarios pass and the suite exits 0. See
> [SLOPE_17_DIAGNOSIS.md](SLOPE_17_DIAGNOSIS.md); `walkability_report.json`
> (schema 4) is authoritative.

## Decision

Keep #141 open. The old 17 degree gate was invalid because it required support
on a slope where Tnua 0.31 intentionally clears `standing_on`. The replacement
gate samples Tnua's own ground sensor. It confirms the steep-slope slip
mechanism, but its locked ascent and stability limits fail. The release phase
does return the player to supported flat ground and ends at rest.

The 0.8 m ledge test establishes that the authored route needs edge boundaries
before unconstrained player traversal. This does not add those boundaries to
the #139 asset. #142 remains Route C, both calibration flags remain false, and
nothing from this harness goes to #137.

## Locked 17 Degree Gate Correction

The old 17 degree gate is invalid. It required at least 95% supported ticks on
a surface that exceeds Tnua 0.31's `max_slope`. In this version, `max_slope`
means the steepest ground on which the character can stand without slipping.
When the ground sensor sees a steeper normal, Tnua sets `standing_on` to
`None`, considers the character airborne, and applies a downhill slip vector.
The old support-fraction gate therefore rejected the intended mechanism by
construction. The measured loss of support is not itself a defect, and it is
not a pass condition. A fall still fails.

The replacement gate was locked before implementation and uses these fixed
criteria:

| Gate | Fixed criterion |
|---|---|
| Sensor mechanism, 17 degrees | For every tick when Tnua's ground sensor hits the tagged incline, log its normal angle and require `standing_on == None` and angle `> 16 degrees`. |
| Positive control, 15 degrees | For every incline hit, log its normal angle and require `standing_on != None` and angle `<= 16 degrees`; retain the existing `>= 95%` moving-support requirement. |
| Input and release | Apply forward input for 240 physics ticks (4 seconds), then reverse toward the flat approach until support returns; use zero input for the remaining ticks in the fixed 60-tick recovery budget. |
| No ascent | Capsule bottom must remain at or below 0.25 m above the flat approach. At the declared 0.70 m rest center and 1.20 m capsule height, the bottom starts 0.10 m above the floor; the limit allows 0.15 m of additional rise, less than the 0.30 m capsule radius. |
| No fall | No SafetyNet contact; player-center `min_y >= 0.60 m`, which is the 0.70 m flat rest height minus a fixed 0.10 m margin. |
| Stability | Peak absolute vertical speed during the slope input phase `<= 0.50 m/s` (one quarter of the 2.0 m/s walk speed). Over the last 60 input ticks, maximum positional distance from the window centroid `<= 0.02 m`. |
| Recovery | Reverse until `standing_on` is restored for the tagged flat approach, then zero input for the remainder of the 60-tick budget. No SafetyNet contact. During the final 10 ticks, speed must be `<= 0.10 m/s` and positional excursion from their centroid `<= 0.02 m`. |
| Outcome | Pass label: `controlled_slip_rejection_returned_to_support`. Any failed criterion gets a specific failure outcome; loss of support alone is never success. |

Record each incline-hit tick's sensor normal, angle, `standing_on` state,
position, vertical speed, and phase. Record release and recovery ticks and the
per-tick recovery measurements. Do not add walls or alter the controller to
make the slope pass. Keep the 0.30 m step rejection, hole ray-detection check,
ledge, wall, and #139 loop gates unchanged. The open ledge still requires
authored edge boundaries, which must remain visible in #135.

The first implementation used zero input for the full release phase. That
trial stayed near `[-1.3868, 0.8011, 0]` for the full release second. The
ground sensor saw the flat approach, but Tnua never restored `standing_on`.
Reverse input restored support on the tagged flat approach in 18 ticks, but
holding reverse for all 60 ticks did not end at rest. The locked recovery now
reverses only until support returns, then uses zero input to settle within the
same 60-tick budget. All numeric limits remain unchanged.

## Evidence

Latest run: `walkability_report.json`, schema version 3. It uses the pinned
Bevy 0.18.0, Avian 0.6.1, Tnua 0.31.0, and integration 0.11.0 stack; the
capsule is radius 0.30 m and height 1.20 m; tick rate is 60 Hz; no GPU or
renderer is used.

| Check | Result | Evidence |
|---|---|---|
| Flat, 15 degree ramp, 0.20 m step | Pass | Each reaches at least 95% moving support. |
| 0.30 m step rejection | Pass | Stops at 47.5% progress, stays supported, and has no SafetyNet contact. |
| 0.30 m hole | Pass as a ray-detection check | Tnua bridges it at 99.5% support; rays miss 10 ticks, with 94.8% moving coverage. This is not evidence that the capsule rejects the hole. |
| Wide-hole SafetyNet negative | Pass | Sensor contact at tick 57, position `[-1.2723, -1.2385, 0]`; no min-Y-only inference. |
| Blocking wall and cleared opening | Pass | Wall stops at 45% path progress; opening reaches the end. |
| 0.8 m open ledge | Pass as a boundary decision | Sideways input reaches center z=1.134 m; capsule edge clearance is -1.034 m at SafetyNet contact, tick 38. Authored edge boundaries are required. |
| 15 degree positive control | Pass | 179 ground-sensor hits, all with angle `<=16 degrees` and `standing_on` present; 99.5% moving support. |
| 17 degree sensor mechanism | Pass | 95 ground-sensor hits; measured normal range 16.9978-17.0142 degrees, all with `standing_on` absent. Support loss is the expected Tnua mechanism. |
| 17 degree bounded slip gate | **Fail; issue remains open** | No fall or SafetyNet contact; min-Y is 0.6974 m and progress is 29.2%. Capsule bottom peaks at 0.3316 m above flat (limit 0.25 m), peak vertical speed is 4.226 m/s (limit 0.50), and input-window position radius is 0.0854 m (limit 0.02). Outcome: `slope_ascent_limit_exceeded`; all three failures are listed in the JSON. |
| 17 degree release and recovery | Pass | Reverse input regains support on the tagged flat approach in 18 ticks. Zero input then settles; final 10-tick max speed is 0.00145 m/s and position radius is 0.000044 m. |
| #139 authored loop | Pass, with localized support loss | 100% outbound, 99.2% inbound, 99.3% moving support, 100% floor-ray coverage, 0.0181 m max vertical step, 0.0039 m max route deviation. All eight unsupported samples and five support-loss transitions are in the JSON with positions. |
| Runtime and memory | Recorded | Final suite 27.61 s; peak RSS 79,224 KiB. Per-scenario fields are in the JSON. |

The #139 loop's floor-clearance q90 is 0.1071 m from the capsule bottom. The
0.55 m headroom ray is clear on all 1,149 loop ticks, so the report shows at
least that tested clearance but does not measure the ceiling.

## Remaining Work

The complete CPU-only suite has been rerun. Thirteen of fourteen scenarios pass;
the 17 degree scenario verifies Tnua's rejection mechanism and recovery, but
fails the locked ascent and stability bounds. Do not count lost support as
success, add walls, or relax the thresholds. Keep #141 open. Keep the
authored-loop edge-boundary need visible in #135; do not represent it as a
measured or reconstructed surface.
