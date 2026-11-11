"""Build and validate the measured module_acoustics v0.2.0 sidecar (#216)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, repo_relative, sha256_file, write_deterministic
from gmap_library import load_library
from module_acoustics import INDEX, mapping_document as legacy_mapping_document

OUTPUT = Path("godot_walk/room_catalog/module_acoustics_v0.2.0.json")
PROBE_RESULTS = Path(
    "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json"
)
PROBE_RUNNER = Path("godot_walk/scripts/probe_module_acoustics.gd")
PROBE_SCRIPT = Path("godot_walk/scripts/room_acoustic_probe.gd")
PROBE_VERSION = "room-acoustic-probe-#205"
GENERATOR_VERSION = "module-acoustics-0.2.0"
DISTANCE_TOLERANCE_M = 0.001
REVERB_TOLERANCE = 0.000001
METRIC_FIELDS = (
    "mean_distance_m",
    "max_distance_m",
    "ceiling_height_m",
    "openness",
    "room_size",
    "damping",
    "wet",
    "predelay_msec",
)


def load_v2(root: Path = ROOT) -> dict[str, Any]:
    """Load the v0.2.0 document while leaving the v0.1.0 path untouched."""
    path = root / OUTPUT
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot load {OUTPUT.as_posix()}: {error}") from error
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        raise ValueError(f"{OUTPUT.as_posix()} is not module_acoustics schema v2")
    return document


def mapping_document(root: Path = ROOT) -> dict[str, Any]:
    """Project actual headless probe output and accepted references into v0.2.0."""
    library = load_library(root / INDEX, root)
    legacy = legacy_mapping_document(library)
    measurements = _read_probe_results(root / PROBE_RESULTS)
    expected_keys = set(legacy["modules"])
    if set(measurements) != expected_keys:
        raise ValueError("probe output module set differs from the admitted library")

    from backfill_module_profiles import expected_profiles

    profiles = {item.module_id: item.path for item in expected_profiles(root)}
    modules = {}
    for key in sorted(expected_keys):
        module_id = key.rsplit("@", 1)[0]
        profile_path = profiles.get(module_id)
        if profile_path is None or not profile_path.is_file():
            raise ValueError(f"{key}: accepted module profile is missing")
        modules[key] = _module_record(
            legacy["modules"][key], measurements[key], profile_path, root
        )
    return {
        "generator": "godot_walk/scripts/module_acoustics.py",
        "generator_version": GENERATOR_VERSION,
        "schema_version": 2,
        "source_index": dict(library.index_ref),
        "probe_method": _probe_method(measurements, root),
        "reproducibility": {
            "distance_tolerance_m": DISTANCE_TOLERANCE_M,
            "openness_tolerance": 0.0,
            "reverb_parameter_tolerance": REVERB_TOLERANCE,
            "comparison": "a fresh Godot headless run compared with this sidecar",
        },
        "operator_listening": "pending",
        "modules": modules,
    }


def _module_record(
    legacy: dict[str, Any],
    measurement: dict[str, Any],
    profile_path: Path,
    root: Path,
) -> dict[str, Any]:
    measured = dict(measurement["metrics"])
    measured.update(
        {
            "probe_version": PROBE_VERSION,
            "provenance": "measured",
            "sample_points": [
                {
                    "method": measurement["sample_method"],
                    "position_m": measurement["sample_point_m"],
                    "floor_y_m": measurement["floor_y_m"],
                    "ceiling_hint_m": measurement["ceiling_hint_m"],
                }
            ],
            "evidence": [
                {"path": PROBE_RESULTS.as_posix(), "sha256": sha256_file(root / PROBE_RESULTS)}
            ],
        }
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return {
        "acoustic": legacy["acoustic"],
        "evidence": legacy["evidence"],
        "poetics": dict(legacy["poetics"]),
        "profile": {
            "path": repo_relative(profile_path, root),
            "sha256": sha256_file(profile_path),
        },
        "probe": measured,
        "absorption": dict(profile["acoustics"]["absorption"]),
    }


def _probe_method(measurements: dict[str, Any], root: Path) -> dict[str, Any]:
    raw = json.loads((root / PROBE_RESULTS).read_text(encoding="utf-8"))
    return {
        "probe_version": raw["probe_version"],
        "runner_version": raw["runner_version"],
        "runner": {"path": PROBE_RUNNER.as_posix(), "sha256": sha256_file(root / PROBE_RUNNER)},
        "probe_script": {"path": PROBE_SCRIPT.as_posix(), "sha256": sha256_file(root / PROBE_SCRIPT)},
        "result": {"path": PROBE_RESULTS.as_posix(), "sha256": sha256_file(root / PROBE_RESULTS)},
        "settings": dict(raw["settings"]),
        "module_count": len(measurements),
    }


def _read_probe_results(path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read headless probe results {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("headless probe output is not a JSON object")
    if raw.get("schema_version") != 1 or raw.get("probe_version") != PROBE_VERSION:
        raise ValueError("headless probe output has an unsupported schema or probe version")
    modules = raw.get("modules")
    if not isinstance(modules, dict):
        raise ValueError("headless probe output has no modules object")
    for key, record in modules.items():
        _validate_measurement(key, record)
    return modules


def _validate_measurement(key: str, record: Any) -> None:
    if not isinstance(record, dict) or not isinstance(record.get("metrics"), dict):
        raise ValueError(f"{key}: probe result is malformed")
    metrics = record["metrics"]
    for field in METRIC_FIELDS:
        value = metrics.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key}: {field} is not a finite measured number")
    if record.get("sample_method") != "accepted_footprint_area_centroid":
        raise ValueError(f"{key}: unsupported probe sample method")
    if len(record.get("sample_point_m", [])) != 3:
        raise ValueError(f"{key}: probe sample point is missing")


def _checksum(path: Path, root: Path) -> Path:
    return root / Path(f"{path.as_posix()}.sha256")


def generate(root: Path = ROOT) -> dict[str, Any]:
    """Create the v0.2.0 sidecar and its detached sha256 pin, refusing replacement."""
    document = mapping_document(root)
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output = root / OUTPUT
    status = write_deterministic(output, data)
    pin_data = f"{sha256_file(output)}  {output.name}\n".encode("utf-8")
    pin_status = write_deterministic(_checksum(OUTPUT, root), pin_data)
    result_pin = _checksum(PROBE_RESULTS, root)
    result_data = (root / PROBE_RESULTS).read_bytes()
    result_pin_data = f"{sha256_file(root / PROBE_RESULTS)}  {PROBE_RESULTS.name}\n".encode("utf-8")
    result_pin_status = write_deterministic(result_pin, result_pin_data)
    return {
        "path": OUTPUT.as_posix(),
        "status": status,
        "sha256_status": pin_status,
        "probe_results_sha256_status": result_pin_status,
        "modules": len(document["modules"]),
        "probe_results_bytes": len(result_data),
    }


def check(root: Path = ROOT) -> list[str]:
    """Check source hashes, exact projection, and detached pins for v0.2.0."""
    errors: list[str] = []
    try:
        document = load_v2(root)
        expected = mapping_document(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [str(error)]
    if document != expected:
        errors.append(f"{OUTPUT.as_posix()}: differs from the measured probe projection")
    errors.extend(_check_pin(root, OUTPUT))
    errors.extend(_check_pin(root, PROBE_RESULTS))
    return errors


def _check_pin(root: Path, path: Path) -> list[str]:
    target = root / path
    pin = _checksum(path, root)
    if not target.is_file():
        return [f"{path.as_posix()}: missing"]
    if not pin.is_file():
        return [f"{pin.relative_to(root).as_posix()}: missing"]
    expected = f"{sha256_file(target)}  {target.name}\n"
    if pin.read_text(encoding="utf-8") != expected:
        return [f"{pin.relative_to(root).as_posix()}: stale sha256 pin"]
    return []
