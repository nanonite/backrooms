"""Shared identifiers and source record for picture seed review v1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from seed_review_metrics import DUPLICATE_WEIGHT, EXPOSURE_WEIGHT, FOCUS_WEIGHT

PICTURE_SOURCE_ID_PATTERN = re.compile(r"^picture-set-[0-9a-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVIEW_SPEC_VERSION = "1.0.0"
MAX_REVIEW_IMAGES = 3
MIN_HUNYUAN_LONG_SIDE = 1024
DIRECT_IMAGE_REVIEW = "direct_source_picture_bytes_no_resize_or_edit"
LOW_RESOLUTION_REASON = "below_1024_pixels_on_long_side"
SHORTLIST_REASON = "beyond_three_image_model_review_limit"
PICTURE_REVIEW_WEIGHT_TOTAL = FOCUS_WEIGHT + EXPOSURE_WEIGHT + DUPLICATE_WEIGHT


@dataclass(frozen=True)
class PictureSetRecord:
    source_id: str
    source_path: str
    source_image_set_sha256: str
    manifest_path: str
    manifest_sha256: str
    images: tuple[dict[str, Any], ...]
