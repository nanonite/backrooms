# Source RGB Floor-Mask Feasibility

## Result

Stop before camera-ray projection. The candidate mask is not sufficiently precise to seed a floor-support grid: it labels a large vertical patch of the foreground column in frame 17, while omitting visible floor patches in frames 17, 97, and 145. The frame 113 overlay also shows candidate pixels crossing the foreground column/base and wall-return boundary. These are material segmentation errors, not gaps that should be filled.

This is a qualitative inspection of algorithm-generated overlays, not human review or annotation. No candidate pixels were projected onto the declared #100 plane. Therefore this attempt reports no grid coverage, connectedness, holes, path residuals, or walkability result. Unknown regions remain unknown. No collision asset was produced, and #135 remains open.

## Method

The CPU-only script processes 13 representative registered RGB frames from the 192-frame `corridor_travel` sequence: frames 1, 17, 33, 49, 65, 81, 97, 113, 129, 145, 161, 177, and 192. Each 1920x1080 JPEG is loaded individually. It converts each image to PIL's 8-bit HSV representation, selects pixels with hue 26-35, saturation at least 125, value 80-205, and image row `y >= 0.42 * height`. It then retains only 8-connected candidate components touching the bottom eight image rows. There is no morphology, dilation, gap bridging, or inference.

This simple rule is deliberately a feasibility probe, not a trained floor classifier. The vertical crop suppresses most ceiling pixels by image position; it does not identify floor material or distinguish floor from nearby columns and lower walls. Floor and cream-column samples overlap in HSV, so bottom connectivity does not resolve the ambiguity.

## Measurements

- Raw HSV candidates: median 594,930 pixels per frame (10th/90th percentile 573,335 / 619,508; maximum 651,980).
- Bottom-connected candidates: median 548,156 pixels (10th/90th percentile 497,217 / 592,533; maximum 637,048), or 26.43% of image pixels at the median.
- Candidate connected-component counts: 498-1,734 across the sampled frames before bottom seeding.
- Latest run: 6.14 seconds and peak process RSS 930,975,744 bytes (about 888 MiB). Images were streamed one at a time; SciPy connected-component labeling still creates substantial temporary arrays.
- GPU: unused. Hunyuan inference: not run. Projection: not run.

## Artifacts

- Predicted floor candidate contact sheet: [rgb_floor_candidate_contact_sheet.jpg](rgb_floor_candidate_contact_sheet.jpg)
- Raw HSV candidate contact sheet: [rgb_color_candidate_contact_sheet.jpg](rgb_color_candidate_contact_sheet.jpg)
- Full-size overlays: [overlays](overlays)
- Per-frame raw and bottom-connected masks: `frame_*_raw_mask.npy` and `frame_*_bottom_connected_mask.npy`
- Machine-readable measurements and frame hashes: [RGB_FLOOR_FEASIBILITY.json](RGB_FLOOR_FEASIBILITY.json)
- Reproduction: `python build_rgb_floor_feasibility.py`
- Focused tests: `pytest -q test_segment_rgb_floor.py`

The JSON records the exact frame IDs, source image hashes, thresholds, pixel counts, runtime, and RSS. The masks and overlays are diagnostic candidates only. Do not use them as collision geometry or feed them into the all-frame plane projection. A future projection attempt needs a higher-precision floor mask, such as audited per-frame polygons or a segmentation method shown to reject columns and wall returns before projection.
