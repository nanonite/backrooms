# #145 Source Footage Inventory

## Result

The 8.0 s source clip shows one visually continuous Backrooms-like interior: patterned wall/partition runs, perpendicular returns, carpet, tiled ceiling with fluorescent panels, pale square columns, and several open sightlines into a wider column bay. It does not establish separate enclosed rooms or the perimeter beyond the visible surfaces. The layout below is a review proposal, not a reconstruction target.

**Registration and scale:** all 192 video frames have registered COLMAP camera poses. This is a camera reconstruction, not accepted registration to a surveyed world. Keep `registration_accepted=false` and `scale_calibrated=false`; COLMAP distances below are reconstruction units, not metres.

## Source And Coverage

- Video: `data/scenes/corridor_travel/video.mp4`, 1920 x 1080, 24 fps, 192 frames, 8.000 s.
- Frame time: `t = (frame_id - 1) / 24`; frame 0001 is 0.000 s and frame 0192 is 7.958 s.
- Sparse model: 192 registered images, one `SIMPLE_RADIAL` camera, 1920 x 1080, focal length 1230.189 px, principal point (960, 540), radial coefficient -0.07134.
- The camera path is continuous in frame order. Its 3D COLMAP center bounds are X [-3.3575, 1.8429], Y [-0.0144, 0.0425], Z [-4.3565, 5.2190]. Total path length is 15.1325 reconstruction units; adjacent-pose step is 0.0380 / 0.0830 / 0.0954 units (min / median / max). This is not a metric calibration.
- Full pose table: [camera_path.csv](camera_path.csv). The [all-frame overview](contact_sheet_all_192.jpg) and four labeled detail sheets cover every source frame: [0001-0048](contact_sheet_0001-0048.jpg), [0049-0096](contact_sheet_0049-0096.jpg), [0097-0144](contact_sheet_0097-0144.jpg), [0145-0192](contact_sheet_0145-0192.jpg).

## Inventory

See [ROOM_CATALOG.md](ROOM_CATALOG.md) for the compact observation catalog and frame-indexed references. The only spatial layout recommendation is to start with one continuous interior and the visible partition/column arrangement. Keep beyond-opening space open/unknown until the operator approves a specific authored extension.

## Layout Review

[layout_proposal.svg](layout_proposal.svg) separates the measured camera trace from the not-to-scale authored topology proposal. The proposal does not add unseen rooms, close an unobserved perimeter, or assert that a visible opening is a door.

**Operator gate:** review or revise the topology proposal before room production. No production, stitching, generation, Hunyuan inference, or GPU capture was run for #145.

## Hashes

[source_hashes.sha256](source_hashes.sha256) records hashes for the source video, all 192 extracted frames, the four COLMAP sparse-model inputs, the pose table, and all produced contact sheets. The source video SHA-256 is `ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4`.
