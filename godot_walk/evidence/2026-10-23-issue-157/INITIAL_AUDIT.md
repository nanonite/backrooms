# Issue 157 — Initial material and transition audit

This is a source-based starting point for the local PLAN.md scope: establish a shared Backrooms material and transition language across modules. GitHub CLI access returned HTTP 401 for issue reads, so this audit follows the local issue summary and does not claim to reproduce the full remote issue specification.

## Existing shared behavior

- The accepted project-wide mapping profile is affine-off, selected by the operator after a live walkthrough and verified by an exact rendered match to the #161 affine-off capture.
- `godot_walk/project.godot` sets `affine_texture_mapping=false`.
- `library_psx_preset.gd` applies the same URSC textured/vertex shaders, nearest filtering, zero texture LOD halve distance, and vertex snap intensity 1 to room materials. It preserves the source material's texture and UV scale when wrapping a `StandardMaterial3D`.
- The source-video materials built by `hunyuan_psx_round1.gd` use a 4×4 UV scale for floor, wallpaper, ceiling, and column textures.

## Current differences to inspect

- The bounded column room builds a Hunyuan visual with authored floor, walls, ceiling, and column cover. The source-video textures are also used by its authored shell.
- The early-pocket room maps its imported floor/ceiling planes and adds authored wall, trim, and lamp geometry from its scene report.
- Both room families use the shared preset, but their geometry, source meshes, UV layouts, and texture assignments differ. A shared shader alone does not guarantee continuity across a doorway or floor seam.
- `issue156_streamed_walkthrough.tscn` is the accepted connected-room reference. Its layout and prior screenshots remain unchanged; #161 changed the project's rendering default only.

## Focus for the next review round

Capture the accepted column-to-pocket connector from both approaches with affine mapping off. Include a matched view that shows the doorway, floor threshold, adjoining wall surfaces, and ceiling edge. Record which mismatch comes from the source texture, UV scale, or authored junction geometry before changing material assignments. Keep a review gate before promoting any material or transition variant.

This is an initial audit, not a claim that the connector has passed a material-continuity review.

