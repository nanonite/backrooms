"""Build evidence diagrams from the live Godot audit; never modify scene assets."""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

EVIDENCE = Path(__file__).resolve().parent
SCALE = 42
ORIGIN = (680, 520)
MODULE_POLYGON = [(-4.4, -1.2), (0, -1.2), (3.5, 1.2),
                  (3.5, 5.6), (-0.3, 5.6), (-4.4, 3.7)]
CANDIDATES = {
    "C01": {"center": (0.42, 1.05), "color": "#ffe67c"},
    "C02": {"center": (-0.7, 4.45), "color": "#ff7997"},
    "C03": {"center": (5.0, 4.7), "color": "#d6a3ff"},
}


def document(filename):
    return json.loads((EVIDENCE / filename).read_text())


def pixel(point):
    return (round(ORIGIN[0] + SCALE * point[0]),
            round(ORIGIN[1] - SCALE * point[1]))


def rectangle(draw, bounds, **options):
    start = pixel((bounds[0], bounds[3]))
    end = pixel((bounds[1], bounds[2]))
    draw.rectangle((start, end), **options)


def diagram():
    image = Image.new("RGB", (1080, 1080), "#1b2024")
    draw = ImageDraw.Draw(image)
    draw.text((24, 20), "#159 CURRENT COLLISION / VISUAL SURFACE AUDIT (Godot units, uncalibrated)", fill="white")
    for coordinate in range(-15, 11):
        draw.line((pixel((coordinate, -12)), pixel((coordinate, 10))), fill="#30383f")
        draw.line((pixel((-16, coordinate)), pixel((9, coordinate))), fill="#30383f")
        draw.text(pixel((coordinate, 9)), str(coordinate), fill="#9babb8")
        draw.text(pixel((7, coordinate)), str(coordinate), fill="#9babb8")
    for point in document("capsule_clear_cells.json"):
        center = pixel((point[0] / 10, point[1] / 10))
        draw.rectangle((center[0]-1, center[1]-1, center[0]+1, center[1]+1), fill="#24534c")
    for point in document("midheight_visual_slice.json"):
        center = pixel(point)
        draw.ellipse((center[0]-1, center[1]-1, center[0]+1, center[1]+1), fill="#aab9c5")
    rectangle(draw, [-5.4, 4.5, -5, 8.8], outline="#42dbb0", width=3)
    rectangle(draw, [-1.3768562, .4819264, -.8615601, 1.5085216], outline="#ff9e52", width=3)
    rectangle(draw, [.06, .78, .30, 1.8], outline="#ffe67c", width=3)
    draw.line([pixel(point) for point in MODULE_POLYGON + MODULE_POLYGON[:1]],
              fill="#ef83ed", width=3)
    for label, candidate in CANDIDATES.items():
        draw.text(pixel(candidate["center"]), label, fill=candidate["color"])
    for record in document("capture_manifest.json") + document("close_manifest.json"):
        start = pixel((record["eye"][0], record["eye"][2]))
        target = pixel((record["target"][0], record["target"][2]))
        draw.line((start, target), fill="#4f82b9")
        draw.ellipse((start[0]-4, start[1]-4, start[0]+4, start[1]+4), fill="#72b8ff")
        draw.text((start[0]+6, start[1]), record["id"].split("_")[0], fill="white")
    draw.text((24, 982), "GREEN: authored floor + capsule-clear samples   ORANGE: invisible column proxy", fill="#c8eee1")
    draw.text((24, 1004), "YELLOW: C01 accepted visual box   GRAY: source mesh vertices at y[-0.1,0.1]", fill="#ffe67c")
    draw.text((24, 1026), "MAGENTA: proposed authored envelope, UNTESTED. Blue lines: review views.", fill="#ef83ed")
    draw.text((24, 1048), "Slice shows surfaces, NOT room semantics, floor support, or collision.", fill="white")
    image.save(EVIDENCE / "current_envelope.png")


def contact_sheet():
    image = Image.new("RGB", (1920, 2304), "#1b2024")
    draw = ImageDraw.Draw(image)
    for index, record in enumerate(document("capture_manifest.json")):
        left = (index % 2) * 960
        top = (index // 2) * 576
        draw.text((left + 12, top + 10), record["id"] + " | existing URSC | reachable eye", fill="white")
        with Image.open(EVIDENCE / "captures" / (record["id"] + ".png")) as capture:
            image.paste(capture, (left, top + 36))
    image.save(EVIDENCE / "review_views.png")


def project(record, point):
    eye = record["eye"]
    target = record["target"]
    forward = (target[0] - eye[0], target[2] - eye[2])
    magnitude = math.hypot(*forward)
    forward = (forward[0] / magnitude, forward[1] / magnitude)
    delta = (point[0] - eye[0], point[1] - eye[2])
    depth = delta[0] * forward[0] + delta[1] * forward[1]
    if depth <= 0:
        return None
    side = -delta[0] * forward[1] + delta[1] * forward[0]
    focal = 270 / math.tan(math.radians(record["fov"] / 2))
    return (round(480 + focal * side / depth), round(270 + focal * eye[1] / depth))


def annotated():
    records = document("capture_manifest.json") + document("close_manifest.json")
    canvas = Image.new("RGB", (960, 1728), "#1b2024")
    draw = ImageDraw.Draw(canvas)
    names = ["V05_west", "V09_C02_front", "V10_C02_reverse"]
    for index, name in enumerate(names):
        record = next(row for row in records if row["id"] == name)
        with Image.open(EVIDENCE / "captures" / (name + ".png")) as source:
            capture = source.convert("RGB")
        painter = ImageDraw.Draw(capture)
        for label, candidate in CANDIDATES.items():
            point = project(record, candidate["center"])
            if point is None or not (0 < point[0] < 960 and 0 < point[1] < 540):
                continue
            painter.ellipse((point[0]-15, point[1]-15, point[0]+15, point[1]+15),
                            outline=candidate["color"], width=3)
            painter.text((point[0]+18, point[1]-12), label, fill=candidate["color"],
                         stroke_width=2, stroke_fill="black")
        draw.text((12, index * 576 + 10), name + " | IDs mark estimated surface positions, not recovered solids", fill="white")
        canvas.paste(capture, (0, index * 576 + 36))
    canvas.save(EVIDENCE / "column_inventory.png")


if __name__ == "__main__":
    diagram()
    contact_sheet()
    annotated()
