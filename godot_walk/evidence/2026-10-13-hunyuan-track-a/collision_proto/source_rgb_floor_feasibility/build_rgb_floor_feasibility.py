"""Generate sampled RGB floor-mask overlays and a contact sheet for audit."""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE))

from segment_rgb_floor import FloorColorRule, bottom_connected_mask, candidate_mask

IMAGE_DIR = ROOT / "data/scenes/corridor_travel/images"
OVERLAY_DIR = HERE / "overlays"
CONTACT_SHEET = HERE / "rgb_floor_candidate_contact_sheet.jpg"
RAW_CONTACT_SHEET = HERE / "rgb_color_candidate_contact_sheet.jpg"
REPORT_PATH = HERE / "RGB_FLOOR_FEASIBILITY.json"
FRAME_NUMBERS = (1, 17, 33, 49, 65, 81, 97, 113, 129, 145, 161, 177, 192)
RULE = FloorColorRule()
TILE_WIDTH = 480
TILE_HEIGHT = 300
SHEET_COLUMNS = 4
GREEN = (20, 235, 125, 115)
ORANGE = (255, 95, 20, 115)


def overlay_image(source: Image.Image, mask: np.ndarray, color) -> Image.Image:
    """Blend one candidate mask over its original RGB image."""
    rgba = source.convert("RGBA")
    tint = Image.new("RGBA", rgba.size, color)
    tint.putalpha(Image.fromarray(mask.astype(np.uint8) * color[3]))
    return Image.alpha_composite(rgba, tint).convert("RGB")


def sha256_file(path: Path) -> str:
    """Hash the sampled RGB input without retaining a second copy in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_overlay(frame_number: int, image: Image.Image, mask: np.ndarray) -> Path:
    """Save a full-size overlay with a visible candidate-only label."""
    destination = OVERLAY_DIR / f"frame_{frame_number:04d}_floor_candidate.png"
    output = overlay_image(image, mask, GREEN)
    draw = ImageDraw.Draw(output)
    draw.rectangle((0, 0, output.width, 36), fill=(0, 0, 0))
    draw.text(
        (12, 11),
        f"frame_{frame_number:04d} / algorithmic floor candidate / unreviewed",
        fill=(255, 255, 255),
    )
    output.save(destination)
    return destination


def contact_sheet(records: list[dict], destination: Path, mask_key: str, color) -> None:
    """Compose original-frame overlays in chronological order."""
    rows = (len(records) + SHEET_COLUMNS - 1) // SHEET_COLUMNS
    sheet = Image.new(
        "RGB", (SHEET_COLUMNS * TILE_WIDTH, rows * TILE_HEIGHT), (28, 28, 28)
    )
    fraction_key = (
        "pixel_fraction" if mask_key == "selected_mask_path" else "raw_pixel_fraction"
    )
    label = (
        "HSV + bottom-connected / unreviewed"
        if mask_key == "selected_mask_path"
        else "raw HSV / unreviewed"
    )
    for index, record in enumerate(records):
        source = Image.open(record["source_path"]).convert("RGB")
        mask = np.load(record[mask_key])
        thumb = overlay_image(source, mask, color)
        thumb.thumbnail((TILE_WIDTH, TILE_HEIGHT - 30))
        x = (index % SHEET_COLUMNS) * TILE_WIDTH
        y = (index // SHEET_COLUMNS) * TILE_HEIGHT
        sheet.paste(thumb, (x, y + 30))
        draw = ImageDraw.Draw(sheet)
        draw.rectangle((x, y, x + TILE_WIDTH - 1, y + 28), fill=(0, 0, 0))
        draw.text(
            (x + 8, y + 8),
            f"frame_{record['frame_number_1_based']:04d} / {label} / {record[fraction_key]:.1%}",
            fill=(255, 255, 255),
        )
    sheet.save(destination, quality=92)


def analyze_frame(frame_number: int) -> dict:
    """Read one source image, segment it, and preserve raw and seeded masks."""
    source_path = IMAGE_DIR / f"frame_{frame_number:04d}.jpg"
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    image = Image.open(source_path).convert("RGB")
    hsv = np.asarray(image.convert("HSV"))
    raw_mask = candidate_mask(hsv, RULE)
    selected, components = bottom_connected_mask(raw_mask, RULE.seed_band_rows)
    raw_path = HERE / f"frame_{frame_number:04d}_raw_mask.npy"
    selected_path = HERE / f"frame_{frame_number:04d}_bottom_connected_mask.npy"
    np.save(raw_path, raw_mask.astype(np.uint8))
    np.save(selected_path, selected.astype(np.uint8))
    overlay_path = write_overlay(frame_number, image, selected)
    return {
        "frame_number_1_based": frame_number,
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "raw_mask_path": str(raw_path),
        "selected_mask_path": str(selected_path),
        "overlay_path": str(overlay_path),
        "image_shape_hw": list(selected.shape),
        "raw_candidate_pixels": int(raw_mask.sum()),
        "bottom_connected_pixels": int(selected.sum()),
        "pixel_fraction": float(selected.mean()),
        "raw_pixel_fraction": float(raw_mask.mean()),
        **components,
    }


def build() -> dict:
    """Generate 13 representative frame masks without projection or inference."""
    started = time.monotonic()
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    records = [analyze_frame(number) for number in FRAME_NUMBERS]
    contact_sheet(records, CONTACT_SHEET, "selected_mask_path", GREEN)
    contact_sheet(records, RAW_CONTACT_SHEET, "raw_mask_path", ORANGE)
    selected_pixels = np.asarray([row["bottom_connected_pixels"] for row in records])
    raw_pixels = np.asarray([row["raw_candidate_pixels"] for row in records])
    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "ambiguous_color_segmentation_stop_before_projection",
        "asset_status": "diagnostic_candidate_masks_only_not_reviewed_not_collision",
        "human_reviewed": False,
        "gpu_used": False,
        "inference_run": False,
        "projection_run": False,
        "registered_frame_count": 192,
        "representative_frame_numbers_1_based": list(FRAME_NUMBERS),
        "input": {
            "image_dir": "data/scenes/corridor_travel/images",
            "dimensions": "1920x1080 RGB JPEG",
            "selected_frames_loaded_one_at_a_time": True,
        },
        "rule": {
            "color_space": "PIL HSV 8-bit channels",
            "hue_range_inclusive_0_255": [RULE.hue_min, RULE.hue_max],
            "saturation_min_0_255": RULE.saturation_min,
            "value_range_inclusive_0_255": [RULE.value_min, RULE.value_max],
            "vertical_crop": f"y >= {RULE.top_fraction:.2f} * image height",
            "connectivity": f"8-connected candidate components; retain only components touching the bottom {RULE.seed_band_rows} rows",
            "morphology_or_gap_bridging": False,
        },
        "candidate_pixel_counts": {
            "raw_hsv_median_q10_q50_q90_max": np.quantile(
                raw_pixels, [0.10, 0.50, 0.90, 1.0]
            ).tolist(),
            "bottom_connected_median_q10_q50_q90_max": np.quantile(
                selected_pixels, [0.10, 0.50, 0.90, 1.0]
            ).tolist(),
            "bottom_connected_fraction_of_pixels_median": float(
                np.median(selected_pixels / (1920 * 1080))
            ),
        },
        "outputs": {
            "predicted_floor_contact_sheet": CONTACT_SHEET.name,
            "raw_color_candidate_contact_sheet": RAW_CONTACT_SHEET.name,
            "full_size_overlay_dir": OVERLAY_DIR.name,
            "per_frame_mask_arrays": "frame_*_raw_mask.npy and frame_*_bottom_connected_mask.npy",
        },
        "frame_records": records,
        "visual_assessment": {
            "floor_color_overlap": "Floor HSV samples are near (30-33, 131-187, 149-180), with overlapping values on cream columns and lower wall returns.",
            "observed_false_positives": [
                "Frame 17: the bottom-connected candidate extends over a large lower vertical face of the foreground cream column.",
                "Frame 113: candidate patches touch the foreground column face/base and wall-return boundary.",
            ],
            "observed_false_negatives": [
                "Frames 17, 97, and 145 leave large visibly horizontal floor patches unselected, especially where lighting or texture changes.",
                "Several otherwise continuous floor regions are speckled or clipped at shadows, baseboards, and occlusion edges.",
            ],
            "ceiling_false_positive_control": "The y >= 0.42 crop suppresses most ceiling pixels by image position. It is not a ceiling classifier and cannot distinguish nearby floor from columns or lower walls.",
            "decision": "Do not project. This candidate has visible column false positives and substantial floor false negatives; it is not high precision. Contact sheets are exploratory and remain unreviewed.",
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
