# Hunyuan Collision Design Review

## Decision

Do not turn either open Hunyuan sheet directly into a player collider. Keep the
Hunyuan GLB visual-only. The initial #135 route may be intentionally selected
inside the connected candidate floor footprint and supported by a separate,
explicit planar floor fill authored for Godot, with confirmed obstacles
represented separately. Label that surface authored, not reconstructed. Keep
the original #100 camera path as an optional fidelity branch; its floor is
poorly observed because the camera travels sideways while looking away from
its motion. See
[`collision_proto/CAMERA_PATH_VISIBILITY_DIAGNOSTICS.md`](collision_proto/CAMERA_PATH_VISIBILITY_DIAGNOSTICS.md).

The method comparison and implementation plan requested by #136 are complete.
This does not accept a metric transform, produce a collision asset, or claim
walkability. The #134 scale `1.5582858479` is a convention-derived experiment
value from the chosen #100 2.4 m clear height, not a surveyed scale. Its
camera-anchored floor and ceiling remain about 12 cm above the #100 reference.
Any geometry using that value must stay disposable and explicitly labelled
non-production until #134 registration is resolved.

## Inspected Data

Run-05 SceneGen created a prompted `columns` mask, not a room/object scene graph.
`fg1.json` has two column detections (scores 0.411 and 0.662); their combined
`fg1_mask.png` is 2560 x 1280, with 718,948 nonzero pixels (21.94%). The mask
overlaps 9,471 of the 85,790 points in the floor-band selection below (11.04%;
the mask was nearest-resized to the PLY grid for this count). Those missing
background faces are potential holes, not geometry to fill by default. Layer 0
combines the detections; layer 1 is the residual full-panorama background.
Neither GLB node retains semantic labels or collision metadata.

The binary PLYs are very large depth sheets:

| Layer | Vertices | Triangles | Local bounds (x, y, z) | Evaluator |
|---|---:|---:|---|---|
| 0, combined foreground | 1,603,955 | 3,235,413 | min `[-5.338, -0.970, -0.737]`, max `[1.162, 3.266, 0.877]` | open, non-watertight, winding inconsistent |
| 1, background | 7,372,800 | 14,783,952 | min `[-17.651, -10.391, -0.942]`, max `[2.755, 3.156, 0.948]` | open, non-watertight, winding inconsistent |

Layer 1 is a 3840 x 1920 panorama grid. The run-05 PLY is 568,204,505 bytes.
The GLB conversion applied no scale or repair. In #133, loading the full 344
MiB GLB took 20.8 seconds and peaked at 6.58 GiB process RSS. This is a poor
runtime collision input even before considering its topology.

The source reconstruction has 192 registered cameras and 15,843 sparse 3D
points. A CPU run of `python3 scripts/splat_pipeline/preflight_parallax.py
data/scenes/corridor_travel/sparse/0` passes the minimum parallax gate: 9.57
COLMAP-unit baseline, 45.4% lateral/forward ratio, 89.0% near-field points,
6.20 degree median triangulation angle (below the 10 degree target). This is a
sparse model, not a dense floor mesh or a floor-labelled point set. The
worktree has the #100 source PLY and alignment contract, but no Nerfstudio
training output directory. No source floor masks are supplied.

The existing #100 collision is a useful negative control, not a proposed
replacement asset. Its recorded 5 cm voxel pass made a watertight 10,178-triangle
mesh in 3.3 seconds at 519 MiB peak CPU and 33 MiB GPU. It put floor beneath
192/192 registered cameras, but only 39/192 (20.3%) were navigable at 1 m above
the floor: uncertain exterior fill over-blocked the camera path. Its floor
height and 5.128383849 m/Nerfstudio-unit scale are explicit synthetic-scene
choices. Do not copy that factor onto Hunyuan coordinates or alter the #100
assets for this issue.

## Method A: Registered-Source Floor Footprint

The 192 COLMAP poses and source frames define a useful candidate XZ footprint,
but do not observe the floor under most of the camera path. The registered
camera motion is sideways in the camera frame (median absolute components
0.984, 0.023, 0.175), with view direction 72-88 degrees from travel. The camera
is level within 0.43 degrees and about 1.16 m above the declared plane. The
`v>=930` carpet band intersects the plane about 2.83-3.01 m ahead of each
camera and yields 0/192 camera-path samples in that band. This is not a bad
mask or a misaligned ray origin; see the diagnostics report.

The all-frame projection creates one connected 27.855 m2 candidate XZ region.
The floor height is imposed from the #100 contract, so this is a planar design
footprint, not measured floor geometry. Select a deliberate route inside the
region, likely around the column. An explicitly authored floor fill is
acceptable if it is exported as a separate collision mesh for Godot, carries
exact transform and provenance, and is labelled authored planar support.
Review the column as a separate obstacle. Do not infer walls from camera
bounds: the
#100 contract says wall planes were not measured.

If the original camera path must be traversable, floor samples project into the
lower half in 176/192 cases with the original pinhole check and 182/192 with
COLMAP `SIMPLE_RADIAL` distortion. These are in-frame upper bounds only; they
ignore wall/column occlusion and leave samples 79-88 unseen under the radial
model. Check occlusion-aware path-length coverage before deciding that masks
can support this route. If coverage cannot meet 90%, capture new forward-moving
footage with the camera tilted down about 25-30 degrees. Hand review cannot
recover an unfilmed surface.

**Strengths:** it uses a consistent registered source-to-world transform and
provides a connected, source-informed XZ design footprint. The #100 collider
already demonstrates floor contact at every registered camera, even though
its obstacle volume fails path coverage. An intentionally selected route can
use this region with clearly authored floor support.

**Limits:** no floor labels are provided, sparse COLMAP points alone do not
describe a continuous floor, the source is synthetic, and the 2.4 m height is
chosen. The projected plane does not observe the camera path underfoot and
cannot recover unknown steps or ramps. Independent obstacle evidence is still
required. This is a source-informed design footprint for an explicitly
authored route, not reconstructed collision geometry.

## Method B: Hunyuan Floor-Band Patch

Extract only the run-05 layer-1 depth points in the forward floor band, rather
than repairing the complete panorama shell. Reproducible selection is
`v=[0.56,0.62]` from the top of the 2:1 panorama, and absolute panorama yaw
`<=35` degrees from local `-X` toward `+Y`. The CPU fit has 85,790 points; its
local plane residual q95 is 0.00718 Hunyuan units (about 1.1 cm at the #134
candidate scale). The fit is locally coherent, but under the horizontal #100
reference plane the camera-anchored residual q95 is 12.2 cm. The translation
that aligns the planes instead shifts the registered camera down 12.0 cm.

I also compared these selected points with all 192 registered camera centers,
mapped through the #100 contract and then into the #134 frame-141 transform.
Under the **provisional** 1.5583 scale, the selected floor points occupy world
XZ bounds `[-2.862, -1.444] .. [2.550, 3.357]` m. Camera-path XZ bounds are
`[-5.454, 0.310] .. [4.151, 5.527]` m. Nearest selected floor-point distance
to the 192 camera-center XZ samples has median 2.24 m and maximum 2.87 m; 0/192
are within 0.30 m. This is a point-sample proximity diagnostic, not a physics
test, and depends on the unaccepted #134 transform. It shows this one forward
floor band does not currently provide the source camera-path footprint.

**Strengths:** it is small enough to crop to a local visual zone, and its points
carry a usable local surface shape. At 5 cm over its 5.41 x 4.80 m bounding
rectangle, a regularized grid is about 108 x 96 (10.4k cells, around 21k
triangles before holes); this is small compared with the source mesh.

**Limits:** scale and vertical registration are not accepted; this is one
panorama, not a route; 11.0% of the selected band is masked out; and a single
view has no evidence behind occluders. A heightfield fills a rectangle unless
the support mask is separately respected. A cropped mesh keeps gaps but is
hollow and can be unstable at edges. Do not fill large mask holes, stretch the
patch to the source camera path, or use layer 0 columns as watertight obstacles.

## Comparison And Choice

| Property | A: registered floor footprint + authored route | B: Hunyuan depth-band patch |
|---|---|---|
| Scale | #100's 5.128383849 m/Nerfstudio-unit chosen convention; apply only to that export frame | #134's 1.558285848 declared m/Hunyuan-unit candidate; not surveyed or accepted |
| Route support | Candidate planar footprint is connected (27.855 m2), but original camera path is not observed underfoot; route can be authored separately | Current patch has 0/192 camera centers within 0.30 m of selected floor samples |
| Holes | Keep unobserved cells unknown; any Godot floor fill is explicit authored support | 11.04% mask overlap in band; fill only after independent evidence, otherwise preserve as unsupported |
| Slopes / steps | Plane-only projection cannot represent them; need source depth/confirmed surface and gate by slope/step | Preserve depth heights in a grid; filter unreliable depth discontinuities and reject out-of-threshold cells |
| Obstacles | Project separately reviewed multi-view masks or fit primitives to confirmed source geometry | SceneGen labels are prompts; open layer-0 surfaces are not solid obstacle volumes |
| Decision | Preferred support prototype | Local comparison/zone experiment only after #134 improves |

Reject whole-mesh repair, watertight wrapping, and decimation as primary
collision methods. Closing the open sheets would invent unseen backs and side
surfaces; decimation only changes triangle count. Hunyuan's inconsistent
triangle winding is also incompatible with blindly constructing an Avian
triangle mesh. The pinned Avian 0.6 API documents `Collider::heightfield` as a
rectangular regular XZ grid and `Collider::trimesh` as hollow with no interior;
the implementation should pass a coherent, upward-facing support patch, not
the raw GLB. See [Avian 0.6 Collider API](https://docs.rs/avian3d/0.6.0/avian3d/collision/collider/struct.Collider.html).

## Collision And Traversal Gates

These are proposed #135 gates, reusing existing harness tolerances where they
exist:

- Keep Hunyuan visual and collision nodes separate. Record source hashes,
  transform, scale basis, grid spacing, support mask, and generation version in
  an evidence-side manifest. A convention scale must say `experimental`; it
  must not be copied to production `alignment.toml` or exported as accepted
  `collision.glb`.
- Use 5 cm cells if measured support permits. Unknown is not solid. Close only
  fully enclosed gaps at most 0.10 m across; larger holes remain unsupported
  and fail if they touch the tested route. Test an inserted 0.30 m hole as a
  negative control.
- Start with a maximum supported slope of 15 degrees as a prototype gate. Fail
  or classify steeper cells as obstacles. Reject any adjacent 0.25 m route
  samples with a step over 0.20 m; the 0.20 m step limit is already used by the
  traversal evidence. Do not smooth a real discontinuity away.
- Use the project capsule (radius 0.30 m, height 1.20 m), 60 Hz physics, and
  `bevy-tnua` with the pinned Avian 3D integration. Require at least 95% of
  movement ticks to have floor support, no fall-through or SafetyNet contact,
  no per-tick step over 0.20 m, and a tested route that reaches >=90% of the
  selected supported path. Walk outbound and inbound; ray-check the capsule
  floor gap and headroom.
- Test boundaries with pushes toward every open edge. Add obstacle probes only
  for reviewed obstacles; expect the capsule to stop within the configured
  0.12 m block tolerance. A cleared-opening negative control must let the
  controller through.
- Negative controls: no floor collider must fail by falling to the SafetyNet;
  a >=0.30 m hole under the route must fail support; a rotated or wrong-scale
  transform must fail the alignment checks; a deliberately blocking slab across
  the route must fail the outbound route; removing a required obstacle must
  fail its blocking probe.

The current `splat_walk/` fixture has Bevy 0.18 and the GLB inspection only; it
does not depend on Avian, Tnua, or their integration. The repository's intended
versions are Avian3d 0.6, bevy-tnua 0.31, and bevy-tnua-avian3d 0.11. #135 must
add and pin the compatible plugins in an isolated harness and test the actual
Tnua movement loop; asset import or ray queries alone are not the acceptance.

## Cost And Failure Cases

**A, measured:** the all-192 bottom-band projection runs in 2.57 s at 83.3 MB
peak RSS and produces 11,142 candidate 5 cm cells (27.855 m2). The support is
connected, but it does not cover the original camera path within the required
0.30 m because the camera does not film the floor underfoot. More GPU or RAM
will not fix that coverage gap. A deliberately selected route inside the
candidate footprint can still be tested with authored planar floor support.

**B, estimate:** a 5 cm height grid over the current selected-point bounds is
about 10.4k cells. A patch of about 21k triangles should fit in a few MiB. The
offline reader must inspect a 568 MB PLY; use streaming or memory mapping and
target <1 GiB peak RAM. Expect seconds to tens of seconds for CPU filtering, but
this estimate was not benchmarked. Do not load the 344 MiB full visual GLB as a
physics asset; #133 measured 6.58 GiB peak RSS for Bevy's visual import.

The source-projection method can fail by mistaking an imposed plane for
measured geometry or by treating an in-frame projection as unoccluded floor.
The Hunyuan depth sheet can stretch, fold, or place a visually plausible
surface at the wrong depth. A heightfield can bridge a gap; a raw trimesh can
have holes, edges, and bad winding; voxel closing can over-block openings as
seen in the #100 result. Every inferred or unknown region must remain distinct
from authored fill, and every failure must leave the cell unsupported or fail
the test rather than silently make it walkable.

## Smallest #135 Plan

1. Preserve the camera-motion, floor projection, and route-image visibility
   checks as rerunnable evidence. Correct the diagnosis: this is a capture
   coverage limit, not a mask-label or transform error.
2. Select a deliberate route inside the candidate XZ footprint, review the
   column obstacle, and author a planar floor fill for Godot where required. A
   first 2.875 m loop and separate projected column proxy are documented in
   [`collision_proto/authored_route_around_column/AUTHORED_ROUTE_PROTOTYPE.md`](collision_proto/authored_route_around_column/AUTHORED_ROUTE_PROTOTYPE.md).
   Its 90.1% proximity to candidate cells is not semantic validation; 4.118 m2
   of the band is explicit authored fill. The loop center is offset toward the
   candidate footprint; the assumed floor plane remains unaudited for slope
   or steps. Keep source-informed footprint and authored support separately
   identified.
3. Treat original camera-path traversal as an optional branch. Audit lower-half
   floor visibility and occlusion only if camera-path fidelity is required; if
   path-length coverage cannot reach 90%, reshoot forward with the camera
   pitched down rather than inventing unseen floor.
4. Build the Avian/Tnua harness on synthetic grids now. Then test the chosen
   collision export, including positive traversal and hole, no-floor, blocking
   slab, and cleared-opening controls.
5. Keep scale, floor height, collision mesh, and traversal results experimental
   until #134's transform is accepted. Do not publish a production asset or
   copy the candidate scale into `alignment.toml` before that gate.

The camera-coverage scripts and report are evidence-only. The #139 prototype
adds a Godot-importable authored floor and separate obstacle proxy, plus a
static capsule clearance check. A renderer-free Bevy 0.18 smoke test now
imports the exported GLB and checks its node transforms, floor height, mesh
bounds, and triangle counts. Neither engine check validates physical traversal.
The route prototype and controller harness remain open #135 work; production
acceptance still depends on #134 and the traversal gates above.
