# Four-sided column box — accepted visual repair

Status: **accepted_visual_repair**. The operator accepts the four-sided box and considers the column repair task complete. No default-scene or catalog promotion occurs; no commit made. This decision does not complete the umbrella work in #151 or #153.

## Operator decision

The operator reviewed the result, described it as "very nice", and explicitly resolved the column task. Matching the column texture to surrounding room surfaces is deferred polish and does not block acceptance. Existing geometric estimates, collision differences and false calibration flags remain documented below. `comparison.png` and `captures/capture_manifest.json` record the earlier review-candidate state; their not-selected labels predate this approval and remain unchanged as historical evidence.

## Alignment evidence and estimates

Read the current Hunyuan Godot scene, round-3 source-face code, original/aligned/fitted captures, reports, and source-crop provenance before authoring. The current fitted code uses a 1.50 × 2.40 face, not the stale 1.261 width in its variant JSON. Retain that full source-frame-0152 crop, dimensions, nearest filtering, unshaded treatment, and existing PSX compositor.

The collision proxy is not the visible column. Its bounds are X −1.37686..0.48193 and Z −0.86156..1.50852; the fitted face is X 0.51293, Z 0.19348..1.69348. In the existing east view, pale generated geometry projects in front of that face; the anchor view exposes the separate shallow slab.

`alignment_samples.json` is reproduced by `authoring/analyze_column.py`. It reads the GLB vertices directly, applies the exact existing scene quaternion, scale and translation, and selects X −0.2..1.0, Z 0.3..2.0 at five height bands. All selected points are on mesh_layer0; layer1 contributes none. The middle-height region (−0.8 < Y < 0.6) inspected during fitting spans approximately X 0.087..0.725, Z 0.547..1.745. Recorded individual slices show X up to 0.744 and Z up to 1.757 near the top. This is the isolated central upright seen in both matched views: no surrounding wall enters this X/Z neighborhood at these heights. Floor/ceiling junction slices are less clean and are not treated as measured architectural edges. Sampling is a diagnostic bounding region, not semantic segmentation or complete column reconstruction.

The candidate is an axis-aligned rectangular prism: X 0.06..0.78, Z 0.30..1.80, Y −1.27099..1.12901; size 0.72 × 2.40 × 1.50 in current uncalibrated scene units. The narrow X extent follows the actual visual mesh, rather than the 1.859-wide proxy. The Z extent retains the accepted face width and encloses the observed jagged limits. The top/bottom retain the existing authored floor/ceiling convention, not a recovered metric height. The west extent and hidden sides are conservative authored enclosure estimates, not verified surfaces.

Keeping the original face plane would leave geometry protruding about 0.23 scene units in front. Therefore the same accepted face is translated +0.27307 X (including the same 0.006 surface clearance) and +0.10652 Z, without changing texture or face size. Four vertical source-textured faces and flat top/bottom caps make one simple closed prism. The crop repeated/compressed on the narrower side faces is an authored treatment; there is no evidence for their true appearance. No source triangles are removed or clipped.

## Matched visual review

Open `comparison.png`: baseline on the left, candidate on the right, patch_anchor above column_east. Raw 960 × 540 captures and camera settings are under `captures/`. These use the identical two round-3 camera positions, directions, 75-degree FOV, 20 settling frames, Vulkan renderer and PSX settings. The inherited player HUD reports the player's position, not the capture camera; use `capture_manifest.json` for camera coordinates. Fresh baseline and candidate are rendered in the same run; earlier JPEG/PNG baseline bytes are not claimed identical.

- East: the accepted face now covers the pale jagged vertical strip from cap to base; no obvious Hunyuan column fragments remain in front of it in this view. The full crop and its bottom strip remain visible.
- Anchor: the slab becomes a coherent two-visible-face rectangular prism. No obvious pale column fragments protrude at its sides, cap or base in this view. Its silhouette is somewhat broader/deeper than the original pale upright; this is a clearance envelope, not a tight surface reconstruction.
- The result remains blocky: flat faces and sharp corners are intentional, and the PSX compositor adds stair-stepping. It is a clean simple box, not an attempt to smooth away that style.
- Existing torn/dark floor and wall boundaries elsewhere in the Hunyuan room remain visible. They are outside this column change.

Two matched views support this local visual fit, not the unseen back face, all walkaround viewpoints, metric scale, or a recovered floor plan. The unchanged proxy extends substantially west/south of the visual box, while the visual extends east/north of the proxy. Physics therefore still does not match this visual envelope; close approach/walkaround remains a limitation beyond this accepted visual repair. `registration_accepted=false` and `scale_calibrated=false` remain unchanged.

## Verification

Vulkan capture completed, with resource preflight reporting approximately 9.84 GiB free VRAM and 28.2 GiB available RAM. The new Godot column-box check passes: static collision paths/transforms/dimensions match round 3 exactly; no cover collision is added; Hunyuan remains loaded; calibration flags remain false; accepted face dimensions and texture bytes match exactly. The existing bounded physics verifier passes with no failures, a 54.80-unit out-and-back route, full floor support, eight boundary pushes and no safety contacts. `mechanics/physics_candidate.json` contains the result. Existing round-1/round-2 Godot checks and all 13 Hunyuan Python unittest cases also pass. No Rust code changed; Cargo checks were not run. Protected source/collision/frame/crop hashes are checked against the earlier recorded manifest in `verification.json`; this is not a retrospective full-worktree hash snapshot.

## Reproduce

Run from the workspace root:

```bash
python3 godot_walk/evidence/2026-10-21-issue-151-column-box/authoring/analyze_column.py
python3 -c 'import sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(check_capture_headroom())'
godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_hunyuan_psx_column_box.gd -- --out=res://evidence/2026-10-21-issue-151-column-box/captures
python3 godot_walk/evidence/2026-10-21-issue-151-column-box/authoring/build_comparison.py
godot4 --headless --path godot_walk --script res://scripts/test_hunyuan_psx_column_box.gd
godot4 --fixed-fps 60 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/hunyuan_psx_column_box.tscn --variant=four_sided_box --out-dir=res://evidence/2026-10-21-issue-151-column-box/mechanics
```

Live review: `godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_column_box.tscn -- --variant=four_sided_box`. The default remains the Hunyuan baseline unless this explicit candidate argument is supplied.

Only the new column-box scene, implementation, capture/check scripts, generated UID companions and this new evidence folder are added. Earlier rounds, source textures, GLBs, collision and project main-scene settings are untouched. No Blender, inference, new video, default-scene/catalog promotion or umbrella issue closure occurs. Operator acceptance resolves the column visual repair task only.
