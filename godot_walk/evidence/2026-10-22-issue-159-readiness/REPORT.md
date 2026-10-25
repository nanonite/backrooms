# #159 — Godot module readiness audit

Operator review on 2026-10-22 accepts both #155 rooms as visually acceptable and walkable. That is **not** generation/stitching acceptance. The accepted C01 four-sided visual box stays unchanged. This audit adds evidence only; both calibration flags remain false.

Review [annotated column views](column_inventory.png), [collision/source map with proposed envelope](current_envelope.png), [eight-view sweep](review_views.png), and the [proposed module/socket contract](module_plan.json). Raw images are in [captures/](captures/); exact poses/FOV/resolution are in [capture_manifest.json](capture_manifest.json) and [close_manifest.json](close_manifest.json).

## Why the apparent room and walking area disagree

The Hunyuan mesh is **visual only**. There is no Hunyuan collision. The player is confined by four **invisible** authored boundary boxes, a planar authored floor, and one invisible column proxy. The visible walls and columns therefore do not reliably indicate where the player can go. The player can both hit an invisible perimeter while seeing further space and pass through source visual surfaces into incoherent/black exterior views. V02/V03/V04 show reachable positions behind visible source walls; V07/V08 look outward into missing source coverage.

All measurements below are uncalibrated Godot units, not established real-world meters:

| Quantity | Live measurement |
| --- | --- |
| Authored floor top | y = -1.27099049 |
| Authored floor/perimeter interior | x [-5.4, 4.5], z [-5.0, 8.8], area 136.62 square units |
| Boundary thickness/height | 0.12 / 2.4 |
| Player capsule | radius 0.3, total height 1.2; eye floor +1.1 |
| Geometric wall-only capsule-center limits | x (-5.1, 4.2), z (-4.7, 8.5); touching contacts excluded |
| Live 0.1-unit capsule-clear grid | 11,338 cells; all spawn-connected; area estimate 113.38 square units |
| Actual sampled center extrema | x [-5.0, 4.1], z [-4.6, 8.4] |
| Source visual vertex bounds | x [-14.8681, 6.7496], y [-1.4217, 1.0485], z [-11.0789, 7.0592] |

The grid uses real capsule queries with 0.02 vertical clearance, floor rays and four-neighbor connectivity. Boundary-touching rejection and grid quantization bias it conservatively. It is an estimate of standing **collision-clear center space**, not visible carpet coverage or a certified room. Source bounds are neither room boundaries nor walkable area. Source mesh bounds extend west/south beyond the authored floor; conversely the north authored floor extends beyond the source visual. No room count or unseen source architecture follows from this.

## Visible upright inventory

IDs are stable for this audit, not a claim to enumerate every source column or every exposed face. Marker positions in the annotated images are projections of estimated world positions onto the original captures. Raw captures remain unannotated. The missing location of the user's particular sighting means C02 is a demonstrated repair candidate, not a claim to identify their exact sighting.

| ID | Evidence and placement | Current readiness decision |
| --- | --- | --- |
| C01 | Accepted authored box x [0.06,0.78], z [0.30,1.80], full floor-to-ceiling height. High confidence in authored bounds. | Keep visual and texture treatment. Reconcile collision independently. |
| C02 | Visible exposed/partial upright in V05, with open/crumpled side clearly shown from opposite reachable views V09/V10. Midheight selected source samples x [-1.000,-0.425], z [4.025,4.825]. Inside current and proposed playable area. | Repair reachable faces and add independently fitted collision in a later reviewed variant. High confidence an exposed upright exists; complete original shape/hidden sides remain unknown. |
| C03 | Further upright visible in V05/V09, selected midheight samples x [4.475,5.550], z [4.450,5.075]. Beyond east collision perimeter, no floor support at estimated center (5,4.7). | Exclude/occlude from playable core. If still visible through openings or from reachable views, visual repair remains required. Moderate confidence in column-like appearance; no claim it is a complete freestanding source column. |

C02's sampled ranges come from an explicitly selected region of world-transformed source vertices at y [-0.1,0.1], quantized to 0.025 units. They bound **observed partial midheight surfaces**, not a recovered solid footprint. C03 uses the same method. Region windows and sample counts are in [column_inventory.json](column_inventory.json); all slice samples are retained in [midheight_visual_slice.json](midheight_visual_slice.json).

Live capsule query at C02's estimated center (-0.7,4.45) finds **no obstruction** and its floor ray hits AuthoredFloor: the visible upright is walk-through geometry today. Both close-view positions are also clear and supported. The C03 center has no authored-floor hit. These distinguish a missing upright collider from the invisible perimeter obstruction.

C01's existing proxy is x [-1.376856,0.481926], z [-0.861560,1.508522]. It extends well west/south of the accepted visual, while the visual protrudes 0.298074 east and 0.291478 north of the proxy. A capsule can hit empty-looking space and overlap visible box portions. Fixing C01's appearance did not certify its collision. [audit.json](audit.json) records every current collider, all point probes, and source bounds.

## Proposed bounded module and connector plan

Do **not** expand the floor to cover the entire Hunyuan mesh. The map's magenta polygon is a concrete authored design proposal: (-4.4,-1.2), (0,-1.2), (3.5,1.2), (3.5,5.6), (-0.3,5.6), (-4.4,3.7). Its northwest/southeast chamfers avoid obvious source perimeter surfaces while retaining C01/C02 and useful approach space. It is not a recovered floor plan or approved dimension set. Its visible closures, actual camera clearance and artwork must be reviewed before collision is changed. The old spawn is outside this smaller proposal and needs a newly tested interior spawn.

Retain the source GLB unchanged. Build a separate bounded visual derivative with coherent carpet/ceiling and opaque authored closures, excluding west/south source wings, C03, and the current behind-wall area. Review all reachable angles. The source mesh also extends into possible neighboring module placements: closures alone cannot guarantee no protruding Hunyuan geometry inside an adjacent room. A reviewed derivative must constrain its rendered extent to the approved module, with deliberate crop/occlusion decisions at retained surfaces. Do not blindly clip the full source scene or claim distant artwork is another usable room.

Suggested future authored sockets, **PROPOSED / UNTESTED**:

- Column module: east-facing (+X) on the proposed closure at floor-center (3.5,-1.27099049,3.1), width 2.0, height 2.1, approach depth 1.2. This is not today's EastBoundary at x4.5. Clear of the observed C01/C02 footprints; source beyond this plane must be handled by the separate derivative.
- Pocket module: west-facing (-X) at (0,-1.27099049,6.9), same floor/width/height. Its authored west wall is closed today. Room-local axes must be transformed to oppose the column socket when assembled.

Neither socket is an observed video connection, an existing hole, or a tested connector. Both require matching visible openings and collision changes in a later implementation. Same floor height alone does not establish compatibility. No Godot socket or assembled traversal was created by this audit.

Implementation order: (1) review envelope/column inventory; (2) separate coherent bounded visual/collision module with visible barriers and new spawn; (3) preserve C01 visual but independently reconcile its proxy, then repair C02 and fit its collider; (4) create paired sockets and an authored connection; (5) test complete capsule clearance, bidirectional travel, floor seams, boundary pushes, both sides of every reachable upright, backtracking and floor/boundary/connector negative controls; (6) operator review and catalog admission. Only then should generation consume these Godot modules. Every future module gets this same reachable-surface/connector acceptance gate.

## Verification and reproduction

Godot 4.6.3 Vulkan Forward+, existing URSC 1.5 and native PSX post effect unchanged. GPU preflight passed with 10.54 GB free VRAM and 24.26 GB available RAM; [resource_preflight.json](resource_preflight.json). Eight sweep plus two focused captures ran serially with respect to GPU capture jobs; all have exact manifests and 960x540 resolution. No inference or video generation.

```bash
timeout 90 godot4 --headless --path godot_walk --script res://evidence/2026-10-22-issue-159-readiness/audit.gd
python3 -c 'import sys;sys.path.insert(0,"godot_walk/scripts");from psx_design_round_resources import check_capture_headroom;print(check_capture_headroom())'
timeout 90 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://evidence/2026-10-22-issue-159-readiness/capture.gd
python3 godot_walk/evidence/2026-10-22-issue-159-readiness/verify_evidence.py
python3 godot_walk/evidence/2026-10-22-issue-159-readiness/build_review.py
```

All completed successfully. The recorded capture run used eight initial poses plus `-- --close-only` for the two added close views. A full rerun captures all ten into capture_manifest.json; close_manifest.json retains the original supplemental records. `verify_evidence.py` independently floods all 11,338 cells from spawn, verifies all captured eyes are on that connected grid, checks image presence/resolution, verifies false calibration flags, and verifies **all seven previously trusted source/collision hashes**. See [verification.json](verification.json). No runtime code, collision, default scene, source asset, earlier evidence, catalog, engine, Bevy path, or issue status changed; no commit or candidate promotion. Matplotlib in the system environment failed its NumPy ABI import; diagrams use the already available Pillow instead, with no dependency changes.
