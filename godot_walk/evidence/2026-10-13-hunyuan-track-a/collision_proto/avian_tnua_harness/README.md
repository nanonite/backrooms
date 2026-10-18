# Avian and Tnua Walkability Harness

This is the synthetic-first #141 harness. It uses Bevy 0.18.0, Avian 0.6.1,
Tnua 0.31.0, and the Avian integration 0.11.0. It runs without a renderer or
GPU. See [ISSUE_141_STATUS.md](ISSUE_141_STATUS.md) for current acceptance.

Run from the Track A worktree root:

```sh
CARGO_BUILD_JOBS=2 cargo run --manifest-path splat_walk/Cargo.toml --bin walkability_harness
```

The command writes `walkability_report.json` beside this note. The report
includes per-scenario and suite wall time, peak and completion RSS, 60 Hz
controller dimensions, support and collision events, floor clearance and
headroom distances, route progress, and every unsupported #139 loop sample.
`gpu_used` is false. The SafetyNet is a real Avian sensor; it records a tick and
player position but does not stop a fall.

## Current Results

> 2026-10-17: superseded for the slope gate. All 15 blocking scenarios pass,
> and 11 non-blocking steep-slope diagnostics are reported. See
> [SLOPE_17_DIAGNOSIS.md](SLOPE_17_DIAGNOSIS.md) and `walkability_report.json`.

The latest run completed all 14 scenarios in 18.17 seconds. Peak RSS was
79,568 KiB. Thirteen scenario gates pass. The 17 degree slope control still
fails, so #141 remains open.

The 15 degree ramp and 0.20 m step are traversable. The 0.30 m step is rejected
while retaining support. The 0.30 m gap is bridged by the capsule; floor rays
still detect the gap on 10 ticks (94.8% moving ray coverage), while Tnua retains
99.5% moving support. The wide-gap negative control reaches the SafetyNet at
tick 57 and records its position. The blocking wall stops progress, and the
cleared opening remains traversable.

The 0.8 m open ledge test moves sideways with no wall. The capsule crosses the
edge by 1.034 m before the SafetyNet sensor reports contact at tick 38. The
result is explicit: **authored edge boundaries are required before player
traversal**. The #139 route export has no edge barrier in this harness, so this
result does not approve the route for an unconstrained player.

The #139 authored loop completes 100% outbound and 99.2% inbound, with 99.3%
moving Tnua support and 100% moving floor-ray coverage. Maximum per-tick
vertical change is 0.0181 m; maximum horizontal path deviation is 0.0039 m.
Floor clearance from the capsule bottom has q90 0.1071 m. The 0.55 m headroom
ray is clear on all 1,149 ticks; this establishes at least the tested clearance,
not a measured ceiling height. The JSON localizes five support-loss transitions
and all eight unsupported samples by tick and position. The initial sample is
captured while the GLB collision asset is installing.

The 17 degree ramp now starts at a connected lower platform and no longer
passes by falling off the map. It stops at 29.2% route progress and never
contacts the SafetyNet, but Tnua reports support on only 25.8% of movement
ticks. Floor rays hit on all movement ticks. The outcome is
`blocked_without_fall_but_tnua_support_was_not_sustained`; this is not a
controlled, supported rejection. Do not treat the 17 degree surface as safe.
The controller/geometry setup needs further work before this acceptance gate
can pass.

All route and transform results remain experimental. The #139 floor is authored
planar support, not measured terrain; this harness does not accept scale,
registration, or a production collision asset. Do not pass any result to #137.
