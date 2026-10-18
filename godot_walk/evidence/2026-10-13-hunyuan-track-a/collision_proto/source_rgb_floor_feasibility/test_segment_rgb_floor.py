from __future__ import annotations

import numpy as np
from segment_rgb_floor import FloorColorRule, bottom_connected_mask, candidate_mask


def test_hsv_rule_keeps_floor_like_region_below_crop_only():
    hsv = np.zeros((10, 8, 3), dtype=np.uint8)
    hsv[5:, :, :] = [30, 150, 150]

    mask = candidate_mask(hsv, FloorColorRule(top_fraction=0.5))

    assert mask.sum() == 40
    assert not mask[:5].any()
    assert mask[5:].all()


def test_bottom_connectivity_does_not_bridge_a_mask_gap():
    candidates = np.zeros((12, 12), dtype=bool)
    candidates[4:9, 4:8] = True
    candidates[10:, 4:8] = True

    selected, record = bottom_connected_mask(candidates, seed_band_rows=2)

    assert selected[10, 5]
    assert not selected[8, 5]
    assert record["bottom_seeded_component_count"] == 1


def test_candidate_color_overlap_can_admit_wall_and_floor_equally():
    hsv = np.zeros((4, 4, 3), dtype=np.uint8)
    hsv[2:, :2] = [31, 160, 155]
    hsv[2:, 2:] = [31, 160, 155]

    mask = candidate_mask(hsv, FloorColorRule(top_fraction=0.5))

    assert mask[3].all()
