# Bounded #100 PSX Region Investigation

## Decision

The existing #100 splat supports a short, floor-supported walk through its
central/east patch. A separate authored enclosure makes that patch viewable
in every tested direction without large black voids or detached foreground
blobs. **Keep the candidate as a reversible hybrid experiment, not as a
ship-ready replacement for #100.** A convincing final walking space has not
been demonstrated: the tiny playable footprint, prominent low partitions,
soft ceiling reconstruction and visible authored/splat junctions remain.

This result does not recover the room, support the original camera path,
prove native Gaussian 360-degree coverage, or satisfy/close #104. No training,
new video, opacity/scale/component pruning, or Gaussian crop was performed.

## Baseline And Protection

Read AGENTS.md, the working-tree PLAN.md, and the requested October 6, 7 and
12 reports before implementing. The original workspace had modified pipeline
scripts/tests and PLAN.md plus the untracked October 12 report. All work was
performed in `/mnt/sharedOs/bounded-psx-100`, branch
`experiment/bounded-psx-100`, based on `2e18002`.

The actual production #100 scene is `corridor_psx.tscn`. It renders the
previously accepted `corridor_clean.ply` (124,564 Gaussians), not the
182,569-Gaussian raw `corridor.ply` used by the inspection scene. Both were
inspected and copied into the isolated worktree without modification.

| Asset | SHA-256 / contract |
|---|---|
| Raw #100 PLY | `1602f159aa7910a105dd2eff913a8bbccec1cb50cca9f974c9f82dfda297929c` |
| Production #100 PLY | `88a20a95dd4df4dde98203f7fb934d17db93a9cb5d98f9e8c1625d478e9d7af0` |
| Alignment | Existing basis, 5.128383849 m/unit, existing centroid correction |
| Collision | Existing transformed GLB, 10,178 triangles; no mesh changes |
| Spawn / player | Inherited unchanged, including Head offset 0.5 m |

`protected_before.json` and `protected_after.json` match exactly across **293
files**: all original corridor assets, three #100 scenes and the complete
current #104 run directory, including its PLY, input video, model, logs and
state. Original working-tree edits were not incorporated or overwritten.

## Spatial Search

The earlier spawn compass results were clues, not a region definition.
`sample_bounded_region.gd` settled the real production capsule at a 3-by-4
grid over x=-1.80/-0.65/+0.50 m and z=0.50/1.70/2.90/4.10 m. It recorded
actual eye positions, floor contact, capsule overlaps and lateral
depenetration. Two points at z=0.50 moved more than 0.1 m and were excluded;
the remaining **10 positions were each rendered at all eight headings**.

| World x/z (m) | Mean black over eight headings |
|---|---:|
| -1.80 / 0.50 | 6.251% |
| -1.80 / 1.70 | 7.341% |
| -0.65 / 1.70 | 8.464% |
| +0.50 / 1.70 | **3.759%** |
| -1.80 / 2.90 | 10.344% |
| -0.65 / 2.90 | 10.005% |
| +0.50 / 2.90 | 8.813% |
| -1.80 / 4.10 | 18.836% |
| -0.65 / 4.10 | 15.629% |
| +0.50 / 4.10 | 11.154% |

The best sampled native position is **(+0.50, 1.70)**: E/S are 0.001%
black, SE 0.170%, but N is still 11.756%. North/northwest remain weak at
every sampled location, with northward travel generally worsening them.
The contact sheet shows the strongest connected imagery on the east/south
side of the central patch, not a fully enclosed native Gaussian room.

At (-0.65, 1.70), a collision-clear capsule can nevertheless place its eye
inside a splat column, producing obvious streaks. That location is explicitly
excluded by a column guard. Collision clearance alone is not visual clearance.

Chosen route: existing spawn approximately (-0.65,2.90), east to
(0.50,2.90), south to (0.50,1.70), and back. Eye y=-0.0425..-0.0921 m is
derived from the settled production capsule, never shifted into a surface to
improve a view. The world-space eye-slice plot is a density diagnostic;
selection is grounded in the multi-position rendered images and traversal.

## Candidate

`corridor_bounded_psx.tscn` inherits the production scene, resource,
transforms, collision, SafetyNet, spawn, player and compositor. It only adds
`AuthoredBoundaries`. Existing renderer depth testing allows opaque meshes
to occlude splats behind them; renderer/shader addon files were not changed.

The first shell used backstops too close to existing floors/walls and visibly
replaced good imagery. Its contact sheet is retained as `shell_v1_contact.jpg`.
The second moves distant backstops behind the reconstructed surfaces. Low
partitions then contain the player while preserving the east/south sightlines,
and a guard excludes the visually occupied column. The last material revision
uses linear colors that better match the production splat's display colors.
Intermediate full captures remain in the ignored local `shell_v*` directories.

Close full walls: west x=-1.30, north z=3.40 m. Distant visual backstops:
east x=6.00, south z=-3.00, bottom y=-1.70, top y=1.80 m. Backstop floor
and ceiling are **visual only** and cannot substitute for generated support.
Low solid partitions: east x=1.25, south z=1.25, plus the column guard at
z=1.80/x=-0.20. Their tops are below the production eye; the production
controller does not jump.

Observed capsule-center boundary extrema: **x=-0.920..+0.870,
z=1.630..3.020 m**. That bounding rectangle is 2.49 m2, with a substantial
column exclusion: approximately **2 m2 of usable micro-space**, not the
15.94 m2 old envelope. The larger shell is a visual backdrop, not a claimed
traversable region. Near-wall eyes remain about 0.30 m outside solid faces.

## Matched Render Evidence

Real GPU: Godot 4.6.3, Vulkan Forward+, RTX 4070 Ti, driver 595.91.07,
DISPLAY=:1, 1280x720. **FOV 75, production eye offset, dark background,
pixel_size=4, color_levels=16, dither_strength=1 are unchanged.**

| Evidence set | Baseline black mean / maximum | Candidate black mean / maximum |
|---|---:|---:|
| Three route positions, eight headings (24 pairs) | 7.526% / 29.255% | 0.000% / 0.000% |
| Eight actual boundary endpoints, eight headings (64 pairs) | 7.065% / 30.932% | 0.000% / 0.000% |
| Four boundary positions, 24 intermediate yaw angles, pitches -60/0/+60 (288 pairs) | 2.761% / see per-frame JSON | 0.000021% / 0.002062% |

Discrete captures settle 200 frames. Sweeps actually turn in 1-degree
increments, then settle 20 frames before sampling each 15-degree interval;
they do not test only favorable compass headings. The same eye coordinates
and rotations are used in both scenes. Pitches cover substantial up/down
views, but do not exhaust the controller's full +/-89-degree range or every
continuous player position. The maximum residual is a tiny boundary seam,
not a large room-sized void.

The unchanged #103 detached-component metric reports **zero candidate
floater pixels** in the 24+64+288 views. Route baseline means are 39.6,
429.9 and 769.8 floater pixels at the three positions; sweep baseline mean
is 117.4 pixels. **This metric cannot detect attached streaks or smears once
authored walls connect the image.** Ceiling texture stretching and irregular
junctions remain visible; zero detached components is not perfect geometry.

Mean changed route pixels: 47.467%. Separate diagnostic captures use the
existing compositor's depth-rejection debug view (PSX disabled only for the
diagnostic, never for scored renders). **54.892% of route pixels reject
splat imagery behind authored geometry**, ranging 28.300..75.240% per view.
This is a lower bound on authored coverage: it excludes hole filling and
partial-alpha blending. The result is substantially authored, rather than a
good Gaussian region magically becoming complete.

All discrete PNGs and logs, per-view metrics, complete sweep contact sheets,
frame manifests and 48 selected full-resolution sweep images are tracked.
All 576 full-resolution sweep PNGs remain locally in the ignored
`sweep_baseline/` and `sweep_candidate/` folders; commands regenerate them.

## Traversal And Runtime

Real production input/controller, actual physics, identical route poses:
baseline and candidate both walk **4.308 m out-and-back**, **100% floor
support**, **zero SafetyNet contacts**, max tick step **0.0687 m**. Generated
collision supplies floor support; no authored floor collision exists.
Eight 240-tick pushes toward all compass directions remain bounded, with
100% floor support, zero SafetyNet contact and maximum step 0.0705 m.

Negative controls work: deleting the east partition lets the player escape
to x=2.75..4.05 m and the verifier fails; deleting generated collision causes
SafetyNet support/contact and the verifier fails despite `is_on_floor=true`.

The draw-signal benchmark rotates at all 11 route/boundary poses, with pitch
variation, at the same resolution. Warmup is at least 200 draws and three
seconds. At an explicit 60-fps cap, both scenes sustain **60.00 fps**; p95
frame intervals are 16.849 ms baseline / 16.872 ms candidate. Uncapped draw
submission rates are 1537 / 1467 per second; these are Godot draw-signal
throughput, **not GPU-timestamp latency**, and are not substituted for the
measured capped runtime result. Benchmark screenshots confirm real imagery.

## Verification And Limits

`verify_alignment.gd`, `test_psx_scene.gd`, `verify_scene.gd`, the matched
route/boundary verifier and both negative controls pass their intended gates.
The pipeline suite in the installed nerfstudio environment: **820 passed,
2 failed** (101.71 s). Both failures are pre-existing Brush stdout
`total_steps` assertions, reproduced independently in the original workspace.
System Python cannot collect mesh tests because it lacks trimesh; the conda
environment was used for the complete suite. No Rust crate exists here.

The candidate is a useful runnable test of the bounded-space hypothesis,
but its flat authored partitions and tiny footprint dominate several views.
Operator review should decide whether this degree of authoring is acceptable.
The experiment provides no basis to require retraining by default: existing
imagery can support a hybrid patch, and visual polish of the junctions has
not been exhausted. It also provides no evidence to approve full coverage,
close #101/#104, or replace protected production assets.

See `COMMANDS.md` for regeneration and launch instructions, `search_contact.jpg`
for region selection, `candidate_contact.jpg` and
`boundary_candidate_contact.jpg` for the actual candidate, and the paired
sweep contact sheets for intermediate angles and pitch limits.
