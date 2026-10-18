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
- The Bevy scene and route measurements were CPU-only, pinned to two cores.

## Supplemental Godot Cross-Check

- This Godot-to-Godot comparison is supplemental only. It is not the Bevy scene
  capture required by #137 and does not complete the Bevy port gate.
- After operator approval, rendered nine matched views at the registered
  frame-141 camera and eight evenly spaced authored-loop stations. Both scenes
  used the same 960x540 viewport and 47.3988-degree vertical FOV. Loop cameras
  sit 1.17071 m above the assumed #100 floor and face the route tangent.
- Captured three same-pose #100 baseline repeats and eight settling frames
  before each image. The Hunyuan GLB was visual-only. The capture did not load
  the collision mesh or touch the #100/Track B worktree.
- Baseline corridor PLY, alignment manifest, scene, project settings and
  Gaussian node/compositor script hashes matched the main #100 worktree. ODiff 4.5.0 used
  threshold 0.1. Maximum baseline repeat noise was 1.58% at frame 141 and 0%
  at the eight loop stations.
- Godot ODiff found 97.55% changed pixels at frame 141 and 94.32-99.65% at the loop
  stations. These are pixel-change diagnostics, not quality scores. At frame
  141 both images show a corridor and foreground column, but the Hunyuan image
  is brighter and smoother. At loop stations the #100 splat has large smeared
  and floating regions, while Hunyuan shows continuous but simplified room
  surfaces. These views do not establish which representation is more accurate.
  See the [contact sheet](captures/contact_sheet.png), the
  [frame-141 baseline](captures/baseline_repeat_1/frame_141.png), the
  [frame-141 Hunyuan view](captures/hunyuan/frame_141.png), and matched
  [station-00 baseline](captures/baseline_repeat_1/loop_station_00.png) /
  [Hunyuan](captures/hunyuan/loop_station_00.png) and
  [station-05 baseline](captures/baseline_repeat_1/loop_station_05.png) /
  [Hunyuan](captures/hunyuan/loop_station_05.png) captures.
- Godot Hunyuan capture process peak RSS was 1,634,236 KiB and wall time was 5.16 s.
  GPU board memory peaked at 2,845 MiB total (1,387 MiB above the 1,458 MiB
  pre-run baseline) on the RTX 4070 Ti. This stayed within the approved 4 GiB
  VRAM and 10 GiB host-RAM budgets. Full ODiff values and capture hashes are in
  [`captures/odiff_report.json`](captures/odiff_report.json). The images show
  why the Hunyuan views are compelling, but do not prove their appearance has
  been ported to Bevy.

## Bevy Port Status

- The import, transform, renderer boundary, and follow-up guidance are in the
  [Bevy porting guide](BEVY_PORTING_GUIDE.md). The Bevy asset import/render path
  is ported and verified; renderer parity is not claimed.
- The `--capture` mode loaded both named visual GLB nodes with the locked
  plane-aligned transform and rendered all nine locked poses at 960x540 and
  47.3988-degree vertical FOV. The Hunyuan layers remained visual-only and the
  collision GLB was not loaded.
- The port follows the existing Bevy fixture: glTF vertex colors, a white
  unlit, double-sided material, and the explicit Hunyuan-to-world transform.
  It does not emulate Godot lighting or tone mapping. The direct Godot-Hunyuan
  versus Bevy-Hunyuan ODiff is a same-asset, cross-renderer diagnostic; the
  Godot #100 baseline comparison is also diagnostic, not a quality score. See
  [the comparison report](ISSUE_137_BEVY_COMPARISON.md) and
  [same-asset contact sheet](captures/bevy_port_contact_sheet.png).
- Operator approval was given before rendering. The Bevy GPU capture completed
  in 42.33 s with process peak RSS 9,273,148 KiB (about 8.84 GiB), below the
  approved 10 GiB host-RAM budget but close enough that no second render was
  needed. On the RTX 4070 Ti (12,282 MiB), polling sampled 1,500 MiB before and
  1,773 MiB during the run, a sampled increase of 273 MiB. This is a sampled
  high-water, not a driver-reported exact peak. The full capture metadata is in
  [`captures/bevy_hunyuan/bevy_capture_report.json`](captures/bevy_hunyuan/bevy_capture_report.json).

## Verification And Remaining Work

- Post-render checks passed: `cargo fmt --check`,
  `cargo clippy --all-targets -- -D warnings`, and
  `cargo test --all-targets` (38 tests passed across library and binaries).
- A regression test confirms a floor just above the collision plane is an
  offset, not a visual hole.
- Nine matched Bevy captures are 960x540 RGB. The same-asset Godot-Hunyuan vs
  Bevy-Hunyuan ODiff ranges from 51.16% to 96.54% changed pixels. Visual review
  shows the same broad room layout and Hunyuan surfaces, with Bevy notably less
  saturated/bright. The high pixel deltas are renderer/material differences to
  investigate, not proof that the mesh geometry failed to port. See the
  [comparison table](ISSUE_137_BEVY_COMPARISON.md) and
  [side-by-side contact sheet](captures/bevy_port_contact_sheet.png).
- `registration_accepted=false`, `scale_calibrated=false`, and
  `transform_status=uncalibrated_convention` remain unchanged. No asset is
  promoted. Traversal acceptance still comes from the exact #135 authored
  collision GLB and shared controller; this render-only capture does not alter
  or rerun that gate.
- The visual GLB is ported into a working Bevy comparison scene. This does not
  port the Hunyuan inference pipeline, prove Godot/Bevy renderer parity, or
  calibrate the transform. The work is committed as an experimental,
  uncalibrated scene and is ready for #137 closure; no promotion is implied.
