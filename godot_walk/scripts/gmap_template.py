"""Attach generation-template and consolidated module metadata references."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, repo_relative, sha256_file
from gmap_reverb import polygon_area_m2
from module_metadata import record_paths

TEMPLATE_PATH = Path("docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md")
TEMPLATE_VERSION = "generation-template-0.1.0"


def consolidated_records(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Load the single authoritative consolidated record for each module."""
    records: dict[str, dict[str, Any]] = {}
    for path in record_paths(root):
        record = json.loads(path.read_text(encoding="utf-8"))
        module_id = record.get("module_id")
        if not isinstance(module_id, str) or module_id in records:
            raise ValueError(
                f"invalid or duplicate consolidated module metadata at {path}"
            )
        records[module_id] = {
            "document": record,
            "reference": {
                "path": repo_relative(path, root),
                "sha256": sha256_file(path),
            },
        }
    return records


def _module_ids(document: dict[str, Any]) -> set[str]:
    return {
        cell["module"]["module_id"]
        for cell in document["cells"]
        if isinstance(cell.get("module"), dict)
        and isinstance(cell["module"].get("module_id"), str)
    }


def _cell_volume(
    cell: dict[str, Any], metadata: dict[str, Any] | None
) -> dict[str, Any]:
    if metadata is not None:
        shape = metadata["profile"]["shape"]
        return {
            "nominal_m3": shape.get("volume_nominal_m3"),
            "measured_m3": shape.get("volume_measured_m3"),
            "source": "module_profile",
        }
    ceiling = cell.get("ceiling_range_m", [0.0, 0.0])
    nominal = polygon_area_m2(cell["envelope_xz"]) * max(
        float(value) for value in ceiling
    )
    return {
        "nominal_m3": round(nominal, 6),
        "measured_m3": None,
        "source": "cell_envelope",
    }


def _door(port_id: str) -> dict[str, Any]:
    return {
        "port_id": port_id,
        "state": "open",
        "lock": {"lock_id": None, "unlock_condition": None, "locked_by": None},
        "reroll": {
            "eligible": False,
            "stream": "door-reroll:gmap-0.13.0",
            "draw_index": None,
            "max_rerolls": 0,
            "last_reroll_id": None,
        },
        "follower_visibility": "untouched",
        "breadcrumb": {"marker_id": None, "kind": None, "persistent": False},
    }


def _absorption_placeholder() -> dict[str, Any]:
    return {
        "status": "unknown",
        "wall": None,
        "floor": None,
        "ceiling": None,
        "trim": None,
        "source": "#213",
        "confidence": 0.0,
    }


def add_template_fields(document: dict[str, Any], root: Path = ROOT) -> None:
    available = consolidated_records(root)
    used_ids = _module_ids(document)
    missing = sorted(used_ids - available.keys())
    if missing:
        raise ValueError("missing consolidated module metadata: " + ", ".join(missing))
    used = {module_id: available[module_id] for module_id in sorted(used_ids)}
    document["template"] = {
        "version": TEMPLATE_VERSION,
        "path": repo_relative(TEMPLATE_PATH, root),
        "sha256": sha256_file(root / TEMPLATE_PATH),
    }
    document["module_metadata"] = [
        {"module_id": module_id, **item["reference"]}
        for module_id, item in used.items()
    ]
    for cell in document["cells"]:
        module_id = cell.get("module", {}).get("module_id")
        metadata = used.get(module_id, {}).get("document")
        if metadata is not None:
            profile = metadata["profile"]
            mood = profile["mood"]
            reference = used[module_id]["reference"]
            cell["module_profile"] = dict(reference)
            cell["mood"] = {
                "tension": mood.get("tension"),
                "tags": sorted(set(mood.get("tags", []))),
            }
            absorption = metadata["acoustics"]["committed_block"].get("absorption", {})
            cell["absorption"] = {
                "status": absorption.get("status", "unknown"),
                "wall": absorption.get("wall"),
                "floor": absorption.get("floor"),
                "ceiling": absorption.get("ceiling"),
                "trim": absorption.get("trim"),
                "source": absorption.get("source", "#213"),
                "confidence": absorption.get("confidence", 0.0),
            }
        else:
            cell["mood"] = {"tension": None, "tags": []}
            cell["absorption"] = _absorption_placeholder()
        cell["volume"] = _cell_volume(cell, metadata)
        cell["doors"] = [
            _door(port["port_id"]) for port in cell.get("required_ports", [])
        ]
        cell["mutation"] = {
            "eligible": False,
            "classes": [],
            "follower_visibility": "untouched",
            "policy": "none",
            "last_change_id": None,
        }
    door_ports = {
        door["port_id"] for cell in document["cells"] for door in cell["doors"]
    }
    for edge in document["edges"]:
        edge["door_id"] = edge["from"] if edge["from"] in door_ports else edge["to"]
