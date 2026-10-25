"""Build a compact matched review for the Hunyuan column-face extrusion."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[4]
ROUND = Path(__file__).resolve().parents[1]
CAPTURES = ROUND / "captures_fitted"
VIEWS = ("patch_anchor", "column_east")
VARIANTS = ("preserve_hunyuan", "column_face_extrusion")
IMAGE_SIZE = (720, 405)
GUTTER = 24


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def font(size: int):
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(font_path), size) if font_path.is_file() else ImageFont.load_default()


def build_contact_sheet() -> None:
    row_height = IMAGE_SIZE[1] + 56
    width = GUTTER * 3 + IMAGE_SIZE[0] * 2
    height = GUTTER * 2 + 42 + row_height * len(VIEWS)
    canvas = Image.new("RGB", (width, height), (239, 239, 230))
    draw = ImageDraw.Draw(canvas)
    draw.text((GUTTER, GUTTER), "#151 Round 3 | Hunyuan-preserving column face extrusion", fill=(31, 33, 29), font=font(24))
    for row, view in enumerate(VIEWS):
        y = GUTTER + 42 + row * row_height
        for column, variant in enumerate(VARIANTS):
            path = CAPTURES / variant / f"{view}.png"
            if not path.is_file():
                raise FileNotFoundError(path)
            with Image.open(path) as source:
                image = ImageOps.fit(source.convert("RGB"), IMAGE_SIZE)
            x = GUTTER + column * (IMAGE_SIZE[0] + GUTTER)
            label = "Hunyuan baseline" if column == 0 else "Source-face extrusion"
            draw.text((x, y), f"{label} | {view}", fill=(31, 33, 29), font=font(17))
            canvas.paste(image, (x, y + 28))
    canvas.save(ROUND / "candidate_contact_sheet_fitted.jpg", quality=92, optimize=True)


def write_bundle() -> None:
    crop = json.loads((ROUND / "source/crop_manifest.json").read_text(encoding="utf-8"))
    capture = json.loads((CAPTURES / "capture_manifest.json").read_text(encoding="utf-8"))
    visual = ROOT / "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb"
    collision = ROOT / "godot_walk/evidence/2026-10-20-issue-150/authored_room_collision.glb"
    manifest = {
        "round_id": "hunyuan-psx-r3",
        "issue": 151,
        "status": "diagnostic_not_accepted",
        "toolchain": "Godot 4.6.3 / Vulkan / existing PSX compositor",
        "registration_accepted": False,
        "scale_calibrated": False,
        "visual_input": {"path": visual.relative_to(ROOT).as_posix(), "sha256": sha256(visual)},
        "collision_input": {"path": collision.relative_to(ROOT).as_posix(), "sha256": sha256(collision)},
        "source_crop": crop,
        "capture": capture,
        "geometry": {
            "column_height_convention_m": 2.4,
            "face_width_m": 1.5,
            "extrusion_depth_m": 0.025,
            "placement": "positive-X/east face; manually offset +0.62 m along Z to align with the visible Hunyuan column in the matched east view; visual-only and uncalibrated",
            "other_faces_and_depth": "left to the Hunyuan visual input",
        },
    }
    (ROUND / "review_manifest_fitted.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_report() -> None:
    crop = json.loads((ROUND / "source/crop_manifest.json").read_text(encoding="utf-8"))
    report = f"""# Hunyuan Column Face Iteration

Status: **diagnostic only; this does not meet the column-cleanup goal**.

## What Changed

The previous #153 Bevy sheet showed a six-face cuboid sized to the full collision proxy, plus a separate wall return, over the Hunyuan scene. That replaced the generated column silhouette with a broad authored block. This iteration uses the existing Godot Hunyuan scene and PSX compositor instead. It keeps the Hunyuan GLB visible and adds only one source-image face with a {0.025:.3f} m shallow backing; there is no added wall return. The Hunyuan sides and depth remain visible.

The face crop is a direct {crop['crop_size_px'][0]} x {crop['crop_size_px'][1]} pixel region from frame 0152, stretched over a 1.50 x 2.40 m face. The width and +0.62 m Z offset are manually fit to the rendered silhouette in the fixed east view, not measured from registered geometry. The patch sits on the east side of the existing column collision proxy, which remains unchanged. The proxy-centered and +0.90 m trials are retained in `captures/` and `captures_aligned/` as placement diagnostics.

## Limits

The face dimensions, east-face placement, and +0.62 m Z offset are uncalibrated visual-fit conventions. The collision proxy is not a measured Hunyuan visual boundary. Frame 0152 supplies the source texture but does not establish column depth; this version deliberately leaves the Hunyuan depth and other sides untouched. It is therefore a smaller visual intervention, not a claim that the original column has been reconstructed exactly.

`registration_accepted=false` and `scale_calibrated=false` remain unchanged. The original Hunyuan visual and #150 collision assets are hashed in `review_manifest_fitted.json`.

## Review

`candidate_contact_sheet_fitted.jpg` shows two matched views: the original Hunyuan column and the single-face extrusion. `captures/` and `captures_aligned/` preserve the earlier placement diagnostics; `captures_fitted/` contains this visual-fit pass. The authored face is the one direct source crop; the surrounding column remains Hunyuan. Machine-rendered differences are not treated as quality scores.

The east view still shows jagged Hunyuan geometry across the authored face, and the anchor view still reads as a separate flat slab. This experiment therefore does not clear the Gaussian/surface artifacts or solve the blocky appearance. It should not be promoted as the column repair.

The next technical step needs to identify the actual visible column surface in the Hunyuan GLB and conform/replace that surface, or establish an operator-approved visual-to-proxy alignment. A flat overlay positioned from the collision proxy is not sufficient.

See `COMMANDS.md` to open the candidate in the live walkthrough.
"""
    (ROUND / "REPORT_FITTED.md").write_text(report, encoding="utf-8")


def write_index() -> None:
    title = "Hunyuan Column Face Diagnostic"
    sheet = "candidate_contact_sheet_fitted.jpg"
    report = "REPORT_FITTED.md"
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>body{{max-width:1500px;margin:24px auto;padding:0 18px;font:16px system-ui;color:#222;background:#f4f4ee}}h1{{font-size:24px}}img{{display:block;width:100%;height:auto;border:1px solid #ccc}}a{{color:#245e56}}</style>
<h1>{title}</h1>
<p>Two matched Hunyuan views. This diagnostic adds one shallow source-video face; it does not resolve the column artifacts.</p>
<a href="{html.escape(report)}">Read the evidence and limits</a>
<img src="{html.escape(sheet)}" alt="Hunyuan baseline compared with one-face source-textured extrusion at two camera views">
</html>
"""
    (ROUND / "index_fitted.html").write_text(page, encoding="utf-8")


def main() -> None:
    build_contact_sheet()
    write_bundle()
    write_report()
    write_index()
    print(f"HUNYUAN_COLUMN_REVIEW_READY: {ROUND / 'index_fitted.html'}")


if __name__ == "__main__":
    main()
