# Issue #137: Uncalibrated Route Scene

Run date: 2026-10-18. Worktree: `track-a/hunyuan-world`.

## Decision And Scope

This is a non-production, uncalibrated comparison. `registration_accepted=false`,
`scale_calibrated=false`, and `transform_status=uncalibrated_convention` remain
locked. No artifact is promoted. Hunyuan is visual-only. The #135 authored GLB
is the only Avian collision asset.

The pre-run manifest and locked metric definitions are in
[`hunyuan_route_scene_manifest.json`](hunyuan_route_scene_manifest.json). The
CPU run is in [`hunyuan_route_scene_report.json`](hunyuan_route_scene_report.json).

## CPU Scene And Traversal

- Loaded the run-05 GLB nodes `mesh_layer0` and `mesh_layer1`: 18,019,365
  triangles total. Created no Hunyuan collider and registered none with Avian.
- Applied the #134 convention scale 1.5582858 m/unit and frame-141 camera basis.
  Plane alignment shifts the camera anchor by -0.120342 m in Y.
- Loaded the exact #135 collision GLB and ran the shared controller. Traversal
  passed: outbound 1.0, inbound 0.992126, moving support 0.9991259, maximum
  vertical step 0.002220869 m, and zero SafetyNet contacts.
- All compared traversal metrics match the #135 report exactly (deltas 0).

## Visual Alignment

These measurements are descriptive only. The transform is not calibrated.

- 1,536 route samples. Absolute vertical gap: median 0.03522 m, q90 0.07820 m,
  max 0.08568 m. Signed gap is Hunyuan floor Y minus authored collision floor Y.
- Visual holes: 0/1,536 samples have no upward-facing floor hit within the
  declared +/-0.5 m vertical search window.
- Directional absence below the collision plane: 529/1,536 samples have no
  floor hit at or below that plane within 0.5 m. This is not the visual-hole
  count: near the camera, many hits sit slightly above the plane. The report
  keeps these measures separate.
- Capsule overlap against either visual layer: 0/1,536 route samples.
- Signed gap by camera distance: 0-3 m median +0.01793 m; 3-6 m median
  -0.02081 m; 6-10 m median -0.05331 m. Absolute q90 rises from 0.02938 m in
  the nearest band to 0.08454 m at 6-10 m. There are no route samples beyond
  10 m.

## Runtime And Memory

- Visual GLB load: 21.43 s.
- CPU query preparation and 1,536 alignment checks: 63.18 s.
- Route simulation: 2.94 s; total headless run: 95.67 s.
- Bevy update wall time after preparation: mean 1.678 ms, p90 2.003 ms,
  max 5.224 ms.
- Peak process RSS: 5,977,064 KiB (about 5.70 GiB); current RSS at completion:
  2,219,508 KiB. The #133 reference was 6,898,192 KiB (about 6.58 GiB).
- Run was CPU-only, pinned to two cores. No renderer, GPU work, captures, or
  ODiff comparison ran.

## Verification And Remaining Work

- `cargo fmt --check` passed.
- `cargo clippy --all-targets -- -D warnings` passed.
- `cargo test --all-targets` passed (32 test executions across library and
  binaries; each binary target runs its shared harness tests).
- A regression test confirms a floor just above the collision plane is an
  offset, not a visual hole.
- Still pending explicit operator approval for rendering. The estimate remains
  4 GiB VRAM and 10 GiB host RAM for matched frame-141 and loop-station captures
  against the unchanged #100/Track B baseline, followed by ODiff review.
- #137 remains open for operator review. No promotion or closure is requested.
