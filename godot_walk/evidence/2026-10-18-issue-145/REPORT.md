# #145 Source Footage Inventory

## Result

The 8.0 s source clip shows a connected observed environment with at least two visually distinct zones: an early partition-bounded pocket and a later, much wider repeated-column bay. Frames 0013-0027 look through a broad gap to a darker wallpapered surface beyond the nearer green-patterned partitions. This could be an adjoining area with a different finish, but the clip does not establish separate room boundaries or the full perimeter beyond visible surfaces. The layout below is a review proposal, not a reconstruction target.

**Registration and scale:** all 192 video frames have registered COLMAP camera poses. This is a camera reconstruction, not accepted registration to a surveyed world. Keep `registration_accepted=false` and `scale_calibrated=false`; COLMAP distances below are reconstruction units, not metres.

## Source And Coverage

- Video: `data/scenes/corridor_travel/video.mp4`, 1920 x 1080, 24 fps, 192 frames, 8.000 s.
- Frame time: `t = (frame_id - 1) / 24`; frame 0001 is 0.000 s and frame 0192 is 7.958 s.
- Sparse model: 192 registered images, one `SIMPLE_RADIAL` camera, 1920 x 1080, focal length 1230.189 px, principal point (960, 540), radial coefficient -0.07134.
- The camera path is continuous in frame order. Its 3D COLMAP center bounds are X [-3.3575, 1.8429], Y [-0.0144, 0.0425], Z [-4.3565, 5.2190]. Total path length is 15.1325 reconstruction units; adjacent-pose step is 0.0380 / 0.0830 / 0.0954 units (min / median / max). This is not a metric calibration.
- Full pose table: [camera_path.csv](camera_path.csv). The [all-frame overview](contact_sheet_all_192.jpg) and four labeled detail sheets cover every source frame: [0001-0048](contact_sheet_0001-0048.jpg), [0049-0096](contact_sheet_0049-0096.jpg), [0097-0144](contact_sheet_0097-0144.jpg), [0145-0192](contact_sheet_0145-0192.jpg).

## Inventory

See [ROOM_CATALOG.md](ROOM_CATALOG.md) for the compact observation catalog and frame-indexed references. The proposal keeps the early partition-bounded pocket and later column bay as distinct observed zones, with an opening candidate between views. It does not decide whether they are separate rooms. Keep beyond-opening space open/unknown until the operator approves a specific authored extension.

## Room-Separation Assessment

- Frames 0013-0027 show a broad, doorless gap between visible partition ends. A darker wallpapered surface and floor are visible beyond the nearer green-patterned walls. This is evidence of a visually distinct area and possible connector, not proof of a separate room or formal doorway.
- Frames 0049-0096 show a perpendicular wall return and changing sightlines around columns. The occluded side of the return is not visible, so it cannot establish a room boundary or a corridor turn in the unseen space.
- Frames 0085-0192 reveal a larger open bay with repeated columns and additional wall fragments. This is a distinct visible spatial zone, but its far extent and relation to the earlier pocket remain partly occluded.
- Across the sampled full-resolution frames and all-frame overview, the carpet, ceiling grid, and fluorescent lighting appear consistent; wallpaper differs in at least one sightline beyond the early opening. The 192 registered poses form a smooth camera path, but no cut, door leaf, or closed threshold establishes a room boundary. Camera-path continuity alone does not prove architectural continuity or that the camera traverses the apparent connector.

**Best-supported interpretation:** one connected observed environment with multiple visible subareas and candidate openings; a separate-room interpretation is plausible but unverified. Preserve the distinct visual zones in the proposal, but do not claim separate bounded room modules or infer the spaces beyond the openings from this clip alone.

## Layout Review

[layout_proposal.svg](layout_proposal.svg) shows nine sampled camera poses and a not-to-scale illustrative topology. Object placement and relationships in the diagram are not recovered coordinates; the connection between observed zones is unknown. It does not add unseen rooms, close an unobserved perimeter, or assert that a visible opening is a door.

**Operator review (2026-10-20):** approved #145 as an inventory, not as a recovered floor plan. Room count, connectivity, and scale remain unknown. The diagram is illustrative only. No production, stitching, generation, Hunyuan inference, or GPU capture was run for #145.

## Hashes

[source_hashes.sha256](source_hashes.sha256) records hashes for the source video, all 192 extracted frames, the four COLMAP sparse-model inputs, the pose table, and all produced contact sheets. The source video SHA-256 is `ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4`.
