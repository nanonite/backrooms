# #135 Source Support Grid Prototype

## Result

The CPU-only prototype proves the grid and hole-preserving patch logic, but the
available source data do not support a connected route. It creates one
experimental quad (2 triangles), and only 69 of 192 registered camera samples
(35.9%) have an observed supported grid sample within 0.30 m. The nearest
sample distance is 0.441 m at the median, 1.229 m at q90, 1.559 m at q95, and
1.790 m at the maximum. These are proximity checks, not player traversal.

No reviewed floor masks or dense registered source floor mesh were found. The prototype
uses only the existing #100 `corridor.ply`: a Gaussian is a candidate sample
when its short covariance axis is within 30 degrees of world vertical and its
centre is within 5 cm of the #100 declared floor plane. This is a geometric
heuristic, not a semantic floor label. It does not fill gaps or infer a floor
from camera bounds.

## Method And Frame

The grid uses 5 cm cells, with median candidate height per occupied cell.
Empty cells are `NaN` and remain unsupported. Samples are limited to the
registered-camera XZ bounds plus 0.30 m. Neighbour checks reject both cells at
a discontinuity above 0.20 m or a local slope above 15 degrees. A patch quad
is emitted only when all four adjacent samples remain supported. No smoothing,
gap closing, or exterior fill is used.

The source is mapped only through the #100 `corridor_splat` contract. Its
`5.128383849` m per Nerfstudio unit is a chosen synthetic-scene convention, not
a surveyed metric measurement. All 192 camera centres mapped through the
available COLMAP/dataparser inputs have minima and maxima matching the #100
contract to within `1e-6` m. The Hunyuan frame-141 candidate scale
`1.558285848` is recorded for context only; no Hunyuan transform or geometry
enters this prototype, and #134 still has `registration_accepted=false`.

## Measurements

| Measure | Result |
|---|---:|
| #100 Gaussian centres | 182,569 |
| Floor-oriented candidates in camera window | 15,214 |
| Selected samples in floor band | 2,087 |
| Selected floor residual, abs q50 / q90 / q95 | 0.0247 / 0.0448 / 0.0475 m |
| Grid | 206 x 117 = 24,102 cells at 0.05 m |
| Observed cells before geometry filter | 1,660 |
| Unknown cells left unknown | 22,442 |
| Observed cells rejected by slope filter | 930 |
| Supported samples after filter | 730 |
| Connected patch output | 4 vertices, 2 triangles |
| Camera samples within 0.30 m of support | 69 / 192 (35.9%) |
| Latest build time / process peak RSS | 2.20 s / about 127 MB |
| Grid archive / evidence OBJ | 13,249 B / 272 B |

The OBJ is a diagnostic evidence artifact only. It is not a `collision.glb`,
not imported by the design harness, and not approved for physics or walkability.
The grid archive, report, and patch all remain under this evidence directory.
An initial prototype run recorded a 930,975,744-byte process peak; two later
runs recorded about 127 MB. Keep the first value as the conservative memory
observation until a more instrumented benchmark explains the variance.

## Verification And Limits

Run from the Track A worktree:

```sh
pytest -q godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/test_source_support.py
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/build_source_support.py
```

The 8 focused tests cover a flat patch, a supported gentle slope, rejected
steep slope, rejected step, masked gap, large hole, wrong scale, and wrong
axis. Unknown cells remain unknown and generated faces are upward-facing. The
camera-centre proximity metric does not test interpolated route coverage.

No Avian 0.6, Tnua 0.31, or integration 0.11 runtime test was added. The real
candidate has no useful connected route, and a synthetic controller run would
not validate its source coverage. There was no reason to add physics
dependencies or launch a render/GPU scene. `#135` remains open: the 90% route
coverage and actual positive/negative traversal gates are not demonstrated. A next pass
needs reviewed floor masks or denser registered source geometry, then a new
support grid and headless Avian/Tnua traversal tests. Collision and metric
approval remain separate from #134's unaccepted Hunyuan registration.
