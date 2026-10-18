# Authored Route Around the Column

This is an experimental #139 route prototype. It uses the connected
27.855 m2 all-frame candidate footprint to choose a compact loop around the
central column. It does not claim that the floor is reconstructed.

The route is a closed 2.875 m radius loop with 0.8 m width. Its center is
offset 0.25 m in X and 0.7 m in Z from the least-squares circle center of the
192 registered #100 camera centers. This offset places more of the loop near
the candidate footprint while keeping the column inside it. The floor is an
explicitly authored ring mesh generated from `route_spec.json` and imported
into Godot at the #100 declared floor height. The obstacle is a separate
conservative box. Its footprint comes from manually marked, visible
column-base pixels in frames 137 and 141, projected onto that declared plane.
Three visible corners are used per frame; the fourth corner is derived by
parallelogram closure. The 2.4 m obstacle height is a chosen room-height
convention, not a measurement.

Run the CPU-only builder from the repository root:

```sh
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/build_route.py
```

The builder writes `authored_route_collision.glb`, `route_report.json`, a plan
view, and two source-frame review overlays. The GLB has identity node transforms
and world coordinates baked into its vertices. Godot creates a concave floor
collider and a separate box obstacle from those named meshes. Open
`route_prototype.tscn` to inspect the prototype. The default project scene and
the #100 assets are unchanged.
The closed loop has a shared start/end point, marked in cyan in the plan view
and Godot preview.

The CPU contract test rebuilds the asset and checks the named floor and column
meshes, identity node transforms, baked floor height, and unaccepted scale
metadata. A separate renderer-free Bevy 0.18 smoke test imports that GLB and
checks both node transforms, floor height, triangle counts, and bounds. This
validates asset import only; it does not add a Bevy physics collider.

Candidate support cells remain unmodified. The report separates their proximity
to the loop from the complete authored floor mesh. Any part outside the
candidate cells is explicit authored fill. The candidate mask itself is still
an unreviewed image-band projection, not ground truth. The assumed Y plane
cannot pass slope or step checks. The #100 scale is chosen, not surveyed; #134
Hunyuan registration remains unaccepted. This is not a production collision
asset and no runtime character traversal is claimed. #141 owns the controller
and collision traversal tests.

The current static check measures an 18.064 m loop. 90.1% of its 1,536
centerline samples are within 0.30 m of the unreviewed candidate cells. Within
the 14.433 m2 grid-sampled route band, candidate cells occupy 10.315 m2 and
4.118 m2 is explicit authored planar fill. The 0.8 m floor band gives a
0.30 m radius capsule 0.10 m of lateral margin per side. The centerline stays
0.537 m from the conservative column box, leaving 0.237 m after capsule
radius. These are geometric checks in the chosen #100 coordinate convention,
not physical measurements or a controller pass.

Verification commands after generation:

```sh
pytest -q godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/test_route_geometry.py
godot4 --headless --path godot_walk --editor --import
godot4 --headless --path godot_walk --script res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/test_route_prototype.gd
CARGO_BUILD_JOBS=2 CARGO_INCREMENTAL=0 cargo run --manifest-path splat_walk/Cargo.toml --bin check_authored_route
```
