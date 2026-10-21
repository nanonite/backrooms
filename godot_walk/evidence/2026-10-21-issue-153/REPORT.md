# Chainlink #153: Blender-To-Bevy Visual Repair

Status: **candidate ready for one focused operator review; #153 remains open**.

## Why This Pass Is Different

Historical diligence found a relevant May workflow, not the remembered PSX add-on: commit `70b0ca0` has `scripts/extract_textures.py` sampling source video frames for room-module faces and `scripts/apply_textures_headless.py` assigning those images to named Blender room meshes before GLB export. The old tree contains modular room-part textures, but the tracked files do not identify a PSX Blender add-on or its license. This prototype therefore tests that closest reproducible pattern with native Blender features; it does not claim to reproduce an unidentified plug-in. The analogous recent failure is #151 Round 2: one column crop was applied to all six box faces, so the operator could not assess face-specific treatment (`godot_walk/evidence/2026-10-21-issue-151-round-2/ADDENDUM-2026-10-21-texture-mapping.md`). This pass maps the source crop to one named face and compares two matched anchors.

## Authored Repair

`column_corner_repair.blend` is the editable source. It contains separate quad meshes for the authored column faces and a small right-angle wallpaper return. Only `column_source_face_east` uses the direct column crop; the remaining faces use separate flat fill. The return is explicitly an authored proposal, not recovered architecture. The crop starts from original source-video frame 0152, not from a splat or Hunyuan render. The source image hash, crop coordinates, crop hashes, GLB hash, Blender version, license, and export settings are recorded in `generated/authoring_manifest.json` and `source/crop_manifest.json`.

The GLB is visual-only. Bevy loads it as a separate scene behind `--issue153`; the existing player, route, #150 visual input, and collision asset remain the source of gameplay. The Bevy route capture reports `collision_loaded=false` because the capture harness is render-only. The separate timed interactive run loads the existing collision route.

## Evidence

- `candidate_contact_sheet.jpg` compares the accepted #150 baseline and imported GLB at `registered_frame_0152_anchor` and `column_east_face`. These are change illustrations, not a quality score.
- `captures/candidate/bevy_capture_report.json` records Bevy 0.18.0 / Vulkan, the selected anchors, calibration flags, resource preflight, and runtime.
- `interactive_play_report.json` records the bounded interactive run. The X11 cursor-grab warning is environmental; the run still auto-exited and wrote its report.
- `source/crop_manifest.json` identifies both direct crops from `data/scenes/corridor_travel/images/frame_0152.jpg`.
- `generated/authoring_manifest.json` records the editable Blender file, GLB, hashes, coordinates, and export settings.

The matched views show the crop on the intended east-facing column plane and the small wallpaper return beside it. A jagged visual edge remains exposed beside the authored face. No claim is made that all Gaussian/Hunyuan artifacts are removed or that the corner is final. This is exactly the bounded decision for review.

## Preserved Inputs

The #150 source visual remains SHA-256 `5b3e879c0309448887cd3ceb7b29eaca49476566ac75010f7e5c5253443a23bf`; its separate collision GLB remains `1dfdf15153194eb4b1c9f8d276bd54286168488cd693de27b1d9fa91f3b28ad9`. `registration_accepted=false` and `scale_calibrated=false` remain unchanged. No #100 or #115 asset was edited. The first three captures, which exposed the PBR lighting, face orientation, and return-placement problems, are retained under `captures/iteration-01-pbr/`, `captures/iteration-02-north-face/`, and `captures/iteration-03-front-wall/`; they are diagnostics, not review candidates.

## Operator Question

At these two views, does the correctly oriented source-textured east column face with the small wallpaper return feel like the right repair direction?

The answer and one next directive should be recorded on #153. Do not close it or begin #154 until the operator reviews this candidate.
