# Hunyuan Column Face Iteration

Status: **candidate for operator review; no design is auto-selected**.

## What Changed

The previous #153 Bevy sheet showed a six-face cuboid sized to the full collision proxy, plus a separate wall return, over the Hunyuan scene. That replaced the generated column silhouette with a broad authored block. This iteration uses the existing Godot Hunyuan scene and PSX compositor instead. It keeps the Hunyuan GLB visible and adds only one source-image face with a 0.025 m shallow backing; there is no added wall return. The Hunyuan sides and depth remain visible.

The face crop is a direct 394 x 750 pixel region from frame 0152. Its aspect ratio sets a 1.261 m face width when paired with the existing 2.4 m room-height convention. The patch sits on the east side of the existing column collision proxy, which remains unchanged.

## Limits

The 2.4 m height and the east-face placement are uncalibrated design conventions. The collision proxy is not a measured Hunyuan visual boundary. Frame 0152 supports the face aspect, but it does not establish column depth; this version deliberately leaves the Hunyuan depth and other sides untouched. It is therefore a smaller visual intervention, not a claim that the original column has been reconstructed exactly.

`registration_accepted=false` and `scale_calibrated=false` remain unchanged. The original Hunyuan visual and #150 collision assets are hashed in `review_manifest.json`.

## Review

`candidate_contact_sheet.jpg` shows two matched views: the original Hunyuan column and the single-face extrusion. The authored face is the one direct source crop; the surrounding column remains Hunyuan. Machine-rendered differences are not treated as quality scores.

Does this source-face extrusion read closer to the existing Hunyuan column than the full box did, while keeping its original-looking sides and depth?

See `COMMANDS.md` to open the candidate in the live walkthrough.
