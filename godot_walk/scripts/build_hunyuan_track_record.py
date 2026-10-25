"""Append schema-validated Hunyuan workflow records from reviewed bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hunyuan_round1_records import validate_document, validate_feedback_for_round

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
EVIDENCE_ROOT = PROJECT / "evidence"
DESIGN_ROUNDS = PROJECT / "design_rounds"
ROUND_SCHEMA = DESIGN_ROUNDS / "hunyuan_round.schema.json"
FEEDBACK_SCHEMA = DESIGN_ROUNDS / "operator_feedback.schema.json"
TRACK_SCHEMA = DESIGN_ROUNDS / "hunyuan_track_record.schema.json"
DEFAULT_OUTPUT = DESIGN_ROUNDS / "hunyuan_track_record.jsonl"


def build_record(bundle_dir: Path) -> dict[str, Any]:
    bundle = _resolve_bundle(bundle_dir)
    manifest = _read_json(bundle / "round_manifest.json")
    feedback = _read_json(bundle / "operator_feedback.json")
    validate_document(manifest, ROUND_SCHEMA)
    validate_document(feedback, FEEDBACK_SCHEMA)
    validate_feedback_for_round(feedback, manifest)
    _require_confirmed_round(manifest, feedback)
    record = _record_document(bundle, manifest, feedback)
    validate_document(record, TRACK_SCHEMA)
    return record


def _resolve_bundle(bundle_dir: Path) -> Path:
    bundle = bundle_dir.resolve()
    try:
        bundle.relative_to(EVIDENCE_ROOT.resolve())
    except ValueError as error:
        raise ValueError("Round bundle must be inside godot_walk/evidence") from error
    if not bundle.is_dir():
        raise FileNotFoundError(f"Round bundle not found: {bundle}")
    return bundle


def _require_confirmed_round(
    manifest: dict[str, Any], feedback: dict[str, Any]
) -> None:
    if manifest.get("status") != "operator_reviewed":
        raise ValueError("Only operator-reviewed round manifests can be indexed")
    if feedback.get("status") != "confirmed":
        raise ValueError("Only confirmed operator feedback can be indexed")


def _record_document(
    bundle: Path, manifest: dict[str, Any], feedback: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_kind": "hunyuan_design_round",
        "issue": manifest["issue"],
        "round_id": manifest["round_id"],
        "manifest_status": manifest["status"],
        "variant_ids": [variant["variant_id"] for variant in manifest["variants"]],
        "variant_specs": manifest["variants"],
        "provenance": manifest["provenance"],
        "toolchain": manifest["toolchain"],
        "gate_results": _gate_results(bundle, manifest),
        "operator_feedback": _feedback_record(feedback),
        "calibration": {
            "registration_accepted": manifest["convention"]["registration_accepted"],
            "scale_calibrated": manifest["convention"]["scale_calibrated"],
        },
        "evidence_paths": _evidence_paths(bundle, manifest),
        "skillopt_state": "data_collection_only",
    }


def _gate_results(bundle: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    mechanics = manifest["mechanics"]
    return {
        "walkability": _walkability_results(bundle, manifest),
        "negative_controls": _negative_control_results(
            bundle, mechanics["expected_negative_controls"]
        ),
        "fps": _fps_result(bundle, mechanics["fps_report"]),
        "visual_metrics": _visual_result(bundle, manifest["visual_metrics"]),
    }


def _walkability_results(
    bundle: Path, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    results = []
    reports = manifest["mechanics"]["walkability_report"]
    for variant_id in (variant["variant_id"] for variant in manifest["variants"]):
        entry = reports[variant_id]
        route = entry["report"]["out_and_back"]
        results.append(
            {
                "variant_id": variant_id,
                "report_path": entry["path"],
                "failures": entry["report"]["failures"],
                "route": {
                    key: route[key]
                    for key in (
                        "distance_m",
                        "floor_fraction",
                        "max_step_m",
                        "safety_contacts",
                    )
                },
            }
        )
        _require_bundle_file(bundle, entry["path"])
    return results


def _negative_control_results(
    bundle: Path, controls: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    for control in controls:
        _require_bundle_file(bundle, control["path"])
    return controls


def _fps_result(bundle: Path, report_path: str) -> dict[str, Any]:
    report = _read_bundle_json(bundle, report_path)
    return {
        "report_path": report_path,
        "capped_at_60": report["capped_at_60"],
        "fps": report["fps"],
        "p95_frame_ms": report["p95_frame_ms"],
        "p99_frame_ms": report["p99_frame_ms"],
    }


def _visual_result(bundle: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    _require_bundle_file(bundle, metrics["path"])
    measurements = _read_bundle_json(bundle, metrics["path"])
    return {
        "report_path": metrics["path"],
        "odiff_threshold": metrics["odiff_threshold"],
        "noise_rule": metrics["noise_rule"],
        "measurements": measurements,
    }


def _feedback_record(feedback: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": "operator_feedback.json",
        "status": feedback["status"],
        "view_choices": feedback["view_choices"],
        "variant_decisions": feedback["variant_decisions"],
        "overall_walkthrough_notes": feedback["overall_walkthrough_notes"],
        "next_round_directives": _directive_records(feedback),
        "confidence": feedback["confidence"],
    }


def _directive_records(feedback: dict[str, Any]) -> list[dict[str, str]]:
    round_id = feedback["round_id"]
    return [
        {"directive_id": f"{round_id}-d{index}", "text": directive}
        for index, directive in enumerate(feedback["next_round_directives"], start=1)
    ]


def _evidence_paths(bundle: Path, manifest: dict[str, Any]) -> list[str]:
    relative = bundle.relative_to(ROOT).as_posix()
    bundle_files = manifest["review_bundle"]
    paths = [
        f"{relative}/round_manifest.json",
        f"{relative}/operator_feedback.json",
        f"{relative}/{bundle_files['index']}",
        f"{relative}/{bundle_files['contact_sheet']}",
        f"{relative}/{bundle_files['layout']}",
        f"{relative}/{bundle_files['commands']}",
    ]
    for path in paths:
        _require_bundle_file(bundle, path.removeprefix(f"{relative}/"))
    return paths


def _read_bundle_json(bundle: Path, relative_path: str) -> dict[str, Any]:
    return _read_json(_require_bundle_file(bundle, relative_path))


def _require_bundle_file(bundle: Path, relative_path: str) -> Path:
    path = (bundle / relative_path).resolve()
    try:
        path.relative_to(bundle)
    except ValueError as error:
        raise ValueError("Evidence path escapes its round bundle") from error
    if not path.is_file():
        raise FileNotFoundError(f"Round evidence is missing: {relative_path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return document


def append_records(
    output_path: Path, records: list[dict[str, Any]], allow_append: bool = False
) -> None:
    output = output_path.resolve()
    try:
        output.relative_to(DESIGN_ROUNDS.resolve())
    except ValueError as error:
        raise ValueError(
            "Track record output must stay inside design_rounds"
        ) from error
    for record in records:
        validate_document(record, TRACK_SCHEMA)
    existing_ids = _existing_record_ids(output, allow_append)
    new_ids = [record["round_id"] for record in records]
    if len(new_ids) != len(set(new_ids)) or set(new_ids) & existing_ids:
        raise ValueError("Track record round IDs must be unique and append-only")
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        stream.write(payload)


def _existing_record_ids(output: Path, allow_append: bool) -> set[str]:
    if not output.exists():
        return set()
    if not allow_append:
        raise FileExistsError(f"Refusing to overwrite append-only record: {output}")
    identifiers = set()
    for line_number, line in enumerate(
        output.read_text(encoding="utf-8").splitlines(), 1
    ):
        record = json.loads(line)
        validate_document(record, TRACK_SCHEMA)
        record_id = record["round_id"]
        if record_id in identifiers:
            raise ValueError(
                f"Duplicate track record at line {line_number}: {record_id}"
            )
        identifiers.add(record_id)
    return identifiers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--append", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build and validate records without changing the index",
    )
    args = parser.parse_args()
    records = [build_record(bundle) for bundle in args.bundle_dir]
    if args.validate_only:
        if args.append:
            parser.error("--validate-only cannot be combined with --append")
        print(f"HUNYUAN_TRACK_RECORDS_VALID: {len(records)}")
        return 0
    append_records(args.output, records, allow_append=args.append)
    print(f"HUNYUAN_TRACK_RECORDS_WRITTEN: {len(records)} -> {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
