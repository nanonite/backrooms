# Issue #135 Acceptance Review

Status: implementation and blocking harness gates pass; posted for operator
review. Do not close #135 until that review is complete.

All assets remain experimental and authored where stated. No geometry from the
Hunyuan visual mesh is used for collision. `registration_accepted=false` and
`scale_calibrated=false` remain false.

## Requirements

| Requirement | Evidence | Verdict |
|---|---|---|
| Deliberately select a route and review the column obstacle | [`authored_route_around_column/route_spec.json`](authored_route_around_column/route_spec.json), [`authored_route_around_column/route_report.json`](authored_route_around_column/route_report.json), and the decision recorded in Chainlink issue #140 | Pass for the authored prototype. It is an 18.064 m closed loop around a separately represented column proxy. The column base was reviewed in frames 137 and 141; its height is a chosen 2.4 m #100 convention, not measured. |
| Support at least 90% of the selected route without silently filling unknowns | [`authored_route_around_column/route_report.json`](authored_route_around_column/route_report.json), `route.explicit_authored_fill`, and `route.candidate_footprint_proximity`; runtime evidence in [`avian_tnua_harness/walkability_report.json`](avian_tnua_harness/walkability_report.json) | Pass as an explicitly authored planar route, not as reconstructed coverage. Candidate-footprint proximity is 1,384/1,536 samples (90.104%). The route mesh explicitly fills the full loop; the 4.1175 m2 authored fill and unmodified unknown candidate-grid cells are recorded. Runtime moving support is 99.9126%; outbound progress is 100%, inbound 99.2126%. |
| Reproducible Bevy collision export | [`authored_route_around_column/build_route.py`](authored_route_around_column/build_route.py), [`authored_route_around_column/authored_route_collision.glb`](authored_route_around_column/authored_route_collision.glb), [`authored_route_around_column/route_report.json`](authored_route_around_column/route_report.json), [`authored_route_around_column/test_route_prototype.gd`](authored_route_around_column/test_route_prototype.gd), and [`route_mesh.rs`](../../../../splat_walk/src/bin/walkability_harness/route_mesh.rs) | Pass. Deterministic GLB SHA-256: `c1c587cfdd773c058d13e71daf841aa460a2413229454ccab6bbf08cacfc460d`. The four imported collision nodes are route floor, column proxy, and two edge boundaries. Godot source placement and GLB node transforms are identity; vertices are already in #100 world coordinates. |
| Avian/Tnua positive and negative controls | [`avian_tnua_harness/walkability_report.json`](avian_tnua_harness/walkability_report.json) and [`avian_tnua_harness/README.md`](avian_tnua_harness/README.md) | Pass. All 33 blocking scenarios pass, including the original controller/collision controls and authored-route traversal. The unchanged 0.8 m open-ledge negative control still reaches the SafetyNet (tick 57). The complete CPU suite took 26.29 s and peaked at 89,280 KiB RSS. The report also retains 11 nonblocking slope diagnostics; one 30-degree/0.25 m/s diagnostic is marked not passed and is not an acceptance gate. |
| Edge boundaries and lateral-push behavior | [`authored_route_around_column/route_spec.json`](authored_route_around_column/route_spec.json), [`authored_route_around_column/route_report.json`](authored_route_around_column/route_report.json), [`avian_tnua_harness/walkability_report.json`](avian_tnua_harness/walkability_report.json), and [`simulation.rs`](../../../../splat_walk/src/bin/walkability_harness/simulation.rs) | Pass. Both open edges have authored 1.4 m high, 0.08 m thick boundaries. Total centerline length is 36.1283 m (inner 15.5509 m, outer 20.5774 m); segments are at most 0.0824 m long with no gaps. Capsule-radius clearance to each floor edge is 0.10 m and the minimum static route clearance is positive. All 18 lateral pushes (9 stations × 2 sides) passed: minimum moving support 99.1667%, maximum center offset 0.1171 m (0.12 m gate), maximum capsule-bottom rise -0.000037 m, and all runs logged boundary contact and ended at rest. |

The lateral-push thresholds were written to the harness report using
`--write-gate-plan` before the first physics run. The completed report retains
those same locked thresholds: 120 input ticks plus 60 release ticks per side,
zero SafetyNet contacts, moving support at least 0.95, center offset at most
0.12 m, required boundary-contact telemetry, bottom rise at most 0.02 m, and
rest in the final 10 ticks. No gate was relaxed. The shared player controller
was not changed.

## Provenance And Limits

- Route choice: the authored loop is the #135 target. #140 records that the
  original camera path is optional, and that reshooting is only triggered if
  camera-path fidelity later becomes a requirement and an occlusion-aware audit
  cannot establish at least 90% support. No reshoot is required for this
  authored-route experiment.
- The floor is a planar authored mesh at Y = -1.27099049 m, copied from the
  chosen #100 floor convention. This Y is assumed, not surveyed. The column
  proxy also uses the chosen 2.4 m room-height convention.
- This does not prove measured slope or step geometry. Slope and step results
  only test controller behavior against synthetic harness geometry; the
  authored loop itself has no measured terrain variation.
- This does not establish surveyed scale or Hunyuan registration.
  `registration_accepted=false` and `scale_calibrated=false` remain false.
- The visual Hunyuan mesh is not used as collision. The boundaries and floor
  are authored, not reconstructed.

## Reproduction

From the Track A worktree, regenerate and verify the route export with:

```sh
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/build_route.py
python3 -m pytest godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/test_route_geometry.py -q
godot4 --headless --path godot_walk --script res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/test_route_prototype.gd
cargo run --manifest-path splat_walk/Cargo.toml --bin walkability_harness
```

The Bevy harness is CPU-only and headless. The report records `gpu_used=false`
and `rendering_enabled=false`.
