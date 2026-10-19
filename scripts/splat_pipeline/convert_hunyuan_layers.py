#!/usr/bin/env python3
"""Convert Hunyuan triangle-mesh PLY layers to one named glTF scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_triangle_mesh(path: Path) -> trimesh.Trimesh:
    try:
        mesh = trimesh.load(path, force="mesh", process=False)
    except Exception as error:
        raise ValueError("could not parse triangle-mesh PLY: %s" % path) from error
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError("layer is not a non-empty triangle mesh: %s" % path)
    if not np.isfinite(mesh.vertices).all() or not np.isfinite(mesh.faces).all():
        raise ValueError("layer contains non-finite geometry: %s" % path)
    if mesh.faces.ndim != 2 or mesh.faces.shape[1] != 3:
        raise ValueError("layer faces must be triangles: %s" % path)
    return mesh


def layer_record(path: Path, mesh: trimesh.Trimesh) -> dict:
    return {
        "source_path": str(path.resolve()),
        "source_sha256": sha256_file(path),
        "name": path.stem,
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "bounds_min": mesh.bounds[0].tolist(),
        "bounds_max": mesh.bounds[1].tolist(),
        "vertex_color_kind": getattr(mesh.visual, "kind", "unknown"),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "watertight": bool(mesh.is_watertight),
    }


def build_layer_scene(inputs: list[Path]) -> tuple[trimesh.Scene, list[dict]]:
    if not inputs or len({path.stem for path in inputs}) != len(inputs):
        raise ValueError("provide at least one uniquely named PLY layer")
    scene = trimesh.Scene()
    records = []
    for path in inputs:
        if path.suffix.lower() != ".ply" or not path.is_file():
            raise ValueError("input layer must be an existing PLY: %s" % path)
        mesh = load_triangle_mesh(path)
        name = path.stem
        scene.add_geometry(mesh, geom_name=name, node_name=name, transform=np.eye(4))
        records.append(layer_record(path, mesh))
    return scene, records


def convert_layers(inputs: list[Path], output: Path, metadata_path: Path) -> dict:
    if output.resolve() == metadata_path.resolve():
        raise ValueError("GLB and metadata paths must be different")
    if output.exists() or metadata_path.exists():
        raise FileExistsError("refusing to overwrite an existing GLB or metadata file")
    scene, records = build_layer_scene(inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(scene.export(file_type="glb"))
    metadata = {
        "format": "glTF 2.0 binary",
        "output_path": str(output.resolve()),
        "output_sha256": sha256_file(output),
        "unit_scale": "unknown; no scale was applied",
        "layer_transforms": "identity; Hunyuan PLY layers share their exported coordinates",
        "layers": records,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = convert_layers(args.input, args.output, args.metadata)
    print("Converted %d layers to %s" % (len(metadata["layers"]), args.output))


if __name__ == "__main__":
    main()
