# Hunyuan Column Face Iteration

Status: **diagnostic only; this does not meet the column-cleanup goal**.

## What Changed

The previous #153 Bevy sheet showed a six-face cuboid sized to the full collision proxy, plus a separate wall return, over the Hunyuan scene. That replaced the generated column silhouette with a broad authored block. This iteration uses the existing Godot Hunyuan scene and PSX compositor instead. It keeps the Hunyuan GLB visible and adds only one source-image face with a 0.025 m shallow backing; there is no added wall return. The Hunyuan sides and depth remain visible.

The face crop is a direct 394 x 750 pixel region from frame 0152, stretched over a 1.50 x 2.40 m face. The width and +0.62 m Z offset are manually fit to the rendered silhouette in the fixed east view, not measured from registered geometry. The patch sits on the east side of the existing column collision proxy, which remains unchanged. The proxy-centered and +0.90 m trials are retained in `captures/` and `captures_aligned/` as placement diagnostics.

## Limits

The face dimensions, east-face placement, and +0.62 m Z offset are uncalibrated visual-fit conventions. The collision proxy is not a measured Hunyuan visual boundary. Frame 0152 supplies the source texture but does not establish column depth; this version deliberately leaves the Hunyuan depth and other sides untouched. It is therefore a smaller visual intervention, not a claim that the original column has been reconstructed exactly.

`registration_accepted=false` and `scale_calibrated=false` remain unchanged. The original Hunyuan visual and #150 collision assets are hashed in `review_manifest_fitted.json`.

## Review

`candidate_contact_sheet_fitted.jpg` shows two matched views: the original Hunyuan column and the single-face extrusion. `captures/` and `captures_aligned/` preserve the earlier placement diagnostics; `captures_fitted/` contains this visual-fit pass. The authored face is the one direct source crop; the surrounding column remains Hunyuan. Machine-rendered differences are not treated as quality scores.

The east view still shows jagged Hunyuan geometry across the authored face, and the anchor view still reads as a separate flat slab. This experiment therefore does not clear the Gaussian/surface artifacts or solve the blocky appearance. It should not be promoted as the column repair.

The next technical step needs to identify the actual visible column surface in the Hunyuan GLB and conform/replace that surface, or establish an operator-approved visual-to-proxy alignment. A flat overlay positioned from the collision proxy is not sufficient.

See `COMMANDS.md` to open the candidate in the live walkthrough.
