# Godot Backrooms material language

Status: current shared conventions for the reviewed column-to-pocket connection.
This records a first-pass style contract; it does not promote unreviewed room
variants or claim that the rooms have identical texture density.

## Shared renderer profile

- Engine: Godot 4.6.3; existing pinned URSC 1.5 subset (`8cd971d`) and native
  compositor.
- Effective project default: affine texture mapping off, nearest texture
  filtering, vertex snap intensity 1. `project.godot` overrides the preset's
  affine-on fallback. Keep that project override when adding rooms.
- Source-derived materials use nearest sampling, unshaded rendering and the
  existing PSX profile. Keep mesh UV orientation as authored; do not globally
  rotate or flip source textures to address a local seam.
- `registration_accepted=false` and `scale_calibrated=false` remain unchanged.

## Material roles

| Role | Existing source and use | Current rule |
| --- | --- | --- |
| Wallpaper | `assets/psx_extension/textures/wallpaper_source_video.png`; shared by bounded column and pocket walls | Reuse the same source and nearest-filtered material. Existing material UV scale is 4×4. Fix a local mismatch on its surface, not by changing both rooms globally. |
| Carpet/floor | `assets/psx_extension/textures/floor_source_video.png`; authored floors and the connector threshold | Preserve the operator-selected 4×4 material scale. The pocket mesh multiplies its XZ UVs by 0.25, while the column polygon floor uses XZ directly; visible repeat density therefore differs. The proposed 16× pocket scale was rejected. Do not call the floors density-matched. |
| Ceiling | `assets/psx_extension/textures/ceiling_source_video.png`; authored ceilings and pocket ceiling surfaces | Keep the per-room source UV mapping. The optional cross-doorway bridge was rejected and stays disabled. A future ceiling repair must name the target surface and use a separate review candidate. |
| Column faces | `assets/psx_extension/textures/column_source_video.png` and the accepted frame-0152 face crop in the bounded column treatment | Preserve the accepted four-sided column dimensions and source-facing texture treatment. Keep the crop limited to its reviewed face; do not infer unseen faces from it. |
| Grid and lamps | Existing pocket detail surfaces; muted olive grid/trim (`Color(0.37, 0.34, 0.23)`) and warm pale lamps (`Color(1.0, 0.97, 0.76)`) | Keep these authored color accents, unshaded, as restrained ceiling details. They are not source-video texture samples. |
| Connector trim | Authored jambs and header use the same muted olive color; threshold uses the source floor texture | Keep a visible, narrow doorway frame and supported threshold. The trim marks an authored connection; it is not evidence of a source-video doorway. |

Texture files and the exact renderer, scene, layout, and capture inputs are
SHA-256 recorded in
[`evidence/2026-10-23-issue-157/source_hashes.json`](../evidence/2026-10-23-issue-157/source_hashes.json).
The focused comparison uses the accepted #160 assembly in the unchanged #156
seeded walkthrough. Matched transition views are in
[`evidence/2026-10-23-issue-157/contact_sheet.jpg`](../evidence/2026-10-23-issue-157/contact_sheet.jpg).
The cross-room wall texture is shared; the different floor repeat density and
ceiling patterns are documented current differences, not proven improvements.

## Transition rules for the current kit

1. Carry the shared wallpaper source and PSX sampling profile across room
   boundaries, while preserving each mesh's existing UV orientation.
2. Keep the accepted 4× pocket floor setting and the current column-floor
   mapping. The visible density mismatch is known and operator-selected for
   this iteration; do not silently normalize it.
3. Use the authored dark jamb/header and source-textured threshold to make the
   tested socket readable. Keep their visual boundaries aligned with collision.
4. Leave the ceiling bridge off. The capture bundle did not establish the
   source of the bright triangular ceiling shape, so do not hide it with a
   global overlay.
5. For remaining wall, ceiling, or column artifacts, make a surface-specific
   candidate and compare it from both sides of the connector. Do not treat
   pixel-difference metrics as a quality score.

## Operator decisions and limits

The operator selected affine mapping off, retained the pocket floor at 4×, and
rejected the ceiling bridge. Those decisions are recorded in the #161 and #157
review bundles. The exact #160 connector pair is accepted for first-pass
traversal only. New openings, arbitrary placements, other column faces, and
future room variants still require their own validation and operator review.

The source textures are video-derived, but this material note does not assign
frame IDs or claim that every texel is a complete reconstruction. Consult the
source-specific evidence before reusing a crop in another module.
