"""Sample the unchanged GLB in the existing Godot scene's world coordinates."""

import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb"
HEIGHT_BANDS = [(-1.2, -1.0), (-0.8, -0.6), (-0.1, 0.1), (0.6, 0.8), (0.8, 0.95)]


def world_vertices():
    raw = SOURCE.read_bytes()
    document_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + document_length])
    binary = raw[28 + document_length:]
    axis = np.array([0.6511913, 0.27745163, 0.27848938])
    cross = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    rotation = np.eye(3) - 2 * 0.64916414 * cross + 2 * cross @ cross
    results = {}
    for mesh in document["meshes"]:
        accessor = document["accessors"][mesh["primitives"][0]["attributes"]["POSITION"]]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        vertices = np.frombuffer(binary, dtype="<f4", count=accessor["count"] * 3, offset=offset)
        results[mesh["name"]] = vertices.reshape(-1, 3) @ rotation.T * 1.5582858 + [2.9209783, -0.205319, 3.703508]
    return results


def sample_band(vertices, low, high):
    selected = vertices[(vertices[:, 1] > low) & (vertices[:, 1] < high)
                        & (vertices[:, 0] > -0.2) & (vertices[:, 0] < 1.0)
                        & (vertices[:, 2] > 0.3) & (vertices[:, 2] < 2.0)]
    return {
        "height_band": [low, high],
        "count": len(selected),
        "percentiles_0_5_50_95_100_xyz": np.percentile(selected, [0, 5, 50, 95, 100], axis=0).tolist() if len(selected) else [],
    }


def main():
    report = {
        "source": str(SOURCE.relative_to(ROOT)),
        "selection_xz": {"x": [-0.2, 1.0], "z": [0.3, 2.0]},
        "purpose": "Diagnostic mesh envelope in matched-view column region; not semantic segmentation or metric calibration",
        "layers": {name: [sample_band(vertices, low, high) for low, high in HEIGHT_BANDS]
                   for name, vertices in world_vertices().items()},
        "box_min": [0.06, -1.27099049, 0.30],
        "box_max": [0.78, 1.12900951, 1.80],
    }
    (OUTPUT / "alignment_samples.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
