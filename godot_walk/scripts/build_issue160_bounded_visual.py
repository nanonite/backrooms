"""Build the separate room-bounded Hunyuan visual for Chainlink #160."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from issue160_glb import (
    CEILING_Y,
    C02_SOURCE_MASK_XZ,
    FLOOR_Y,
    ROOM_POLYGON_XZ,
    accessor_array,
    clip_layer,
    points_inside_room,
    read_glb,
    sha256,
    write_bounded_glb,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DEFAULT = ROOT / "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb"
OUTPUT_DEFAULT = ROOT / "godot_walk/evidence/2026-10-22-issue-160/bounded_hunyuan_visual.glb"
REPORT_DEFAULT = ROOT / "godot_walk/evidence/2026-10-22-issue-160/visual_derivative.json"


def main() -> int:
    arguments = _arguments()
    source = read_glb(arguments.source)
    layers = []
    layer_records = []
    for index, primitive in enumerate(_primitives(source.document)):
        attributes = primitive["attributes"]
        if set(attributes) != {"POSITION", "COLOR_0"}:
            raise ValueError(f"Layer {index} has unsupported attributes: {attributes}")
        positions = accessor_array(source, attributes["POSITION"])
        colors = accessor_array(source, attributes["COLOR_0"])
        indices = accessor_array(source, primitive["indices"])
        c02_masked = index == 0
        clipped_positions, clipped_colors, clipped_indices, source_triangles, masked_vertices = clip_layer(
            positions, colors, indices, mask_c02=c02_masked
        )
        layers.append((clipped_positions, clipped_colors, clipped_indices))
        layer_records.append(
            {
                "source_mesh": source.document["meshes"][index]["name"],
                "source_vertices": int(len(positions)),
                "source_triangles": source_triangles,
                "retained_vertices": int(len(clipped_positions)),
                "retained_triangles": int(len(clipped_indices)),
                "retained_triangle_fraction": round(len(clipped_indices) / source_triangles, 6),
                "C02_source_mask_enabled": c02_masked,
                "source_vertices_in_C02_mask": masked_vertices,
                "bounds_min": np.min(clipped_positions, axis=0).tolist(),
                "bounds_max": np.max(clipped_positions, axis=0).tolist(),
            }
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    write_bounded_glb(layers, arguments.output)
    derivative = read_glb(arguments.output)
    for index, primitive in enumerate(_primitives(derivative.document)):
        positions = accessor_array(derivative, primitive["attributes"]["POSITION"])
        if not np.isfinite(positions).all() or not points_inside_room(positions).all():
            raise ValueError(f"Output layer {index} escaped its authored room bounds")
    report = {
        "issue": 160,
        "method": "retain only source triangles whose three transformed vertices lie within the proposed authored polygon and floor-to-ceiling range",
        "source_path": str(arguments.source),
        "source_sha256": sha256(arguments.source),
        "output_path": str(arguments.output),
        "output_sha256": sha256(arguments.output),
        "output_bytes": arguments.output.stat().st_size,
        "output_vertex_validation": "all output vertices inside authored xz polygon and floor/ceiling bounds",
        "room_polygon_xz_authored": ROOM_POLYGON_XZ.tolist(),
        "floor_y": FLOOR_Y,
        "ceiling_y": CEILING_Y,
        "C02_source_mask_xz_authored": C02_SOURCE_MASK_XZ.tolist(),
        "layers": layer_records,
        "registration_accepted": False,
        "scale_calibrated": False,
        "generation_ready": False,
        "limitations": [
            "The polygon is an authored room proposal, not surveyed source geometry.",
            "The derivative removes geometry outside its bounds; it does not reconstruct hidden surfaces.",
            "Triangle retention can leave interior holes where source triangles crossed the authored boundary.",
            "C02 mesh-layer-0 geometry inside the mask is omitted and replaced by the estimated authored prism.",
        ],
    }
    arguments.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    return parser.parse_args()


def _primitives(document: dict) -> list[dict]:
    primitives = [primitive for mesh in document.get("meshes", []) for primitive in mesh["primitives"]]
    if len(primitives) != 2 or any(primitive.get("mode", 4) != 4 for primitive in primitives):
        raise ValueError("Expected exactly two triangle-list Hunyuan visual layers")
    return primitives


if __name__ == "__main__":
    raise SystemExit(main())
