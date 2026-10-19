"""Compare a replayed design round with its preserved original evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FPS_GATE_MINIMUM = 59.0


def compare_reproduction(original_dir: Path, replay_dir: Path,
                         variant_ids: list[str]) -> dict[str, Any]:
    """Compare round-5 gate outcomes and ODiff metrics within its noise floor."""
    original_manifest = _read_json(original_dir / "review_manifest.json")
    replay_manifest = _read_json(replay_dir / "review_manifest.json")
    original_metrics = _read_json(original_dir / "review_metrics.json")
    replay_metrics = _read_json(replay_dir / "review_metrics.json")
    if original_manifest.get("variants") != variant_ids:
        raise ValueError("original evidence variant IDs do not match the replay spec")
    if replay_manifest.get("variants") != variant_ids:
        raise ValueError("replay manifest variant IDs do not match the replay spec")
    original_gates = gate_results(original_dir, variant_ids)
    replay_gates = gate_results(replay_dir, variant_ids)
    gate_match = original_gates == replay_gates
    metric_rows, metric_tolerance = compare_metrics(original_metrics, replay_metrics)
    metrics_match = all(row["within_noise_floor"] for row in metric_rows)
    return {
        "original_evidence": str(original_dir),
        "replay_evidence": str(replay_dir),
        "variant_ids_match": True,
        "gate_results_match": gate_match,
        "original_gates": original_gates,
        "replay_gates": replay_gates,
        "metric_tolerance_pct": metric_tolerance,
        "metrics_within_control_repeat_noise": metrics_match,
        "metric_comparisons": metric_rows,
        "passed": gate_match and metrics_match,
    }


def gate_results(evidence_dir: Path, variant_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"variants": {}, "negative_controls": {}}
    for variant in variant_ids:
        repeats = _repeat_ids(evidence_dir / "mechanics" / variant)
        result["variants"][variant] = {}
        for repeat_id in repeats:
            physics_path = evidence_dir / "mechanics" / variant / repeat_id / "physics_candidate.json"
            physics = _read_json(physics_path)
            fps_path = evidence_dir / "mechanics" / variant / "repeat_1" / f"fps_{variant}_capped.json"
            if repeat_id != "repeat_1":
                fps = _read_json(fps_path)
            else:
                fps = _read_json(fps_path)
            result["variants"][variant][repeat_id] = {
                "verify_pass": not physics.get("failures", []),
                "route_pass": _route_pass(physics),
                "collision_support_pass": _support_pass(physics),
                "capped_fps_pass": bool(fps.get("capped_at_60"))
                and float(fps.get("fps", 0.0)) >= FPS_GATE_MINIMUM
                and int(fps.get("frames", 0)) > 0,
            }
    for mutation in ("boundary", "floor"):
        path = evidence_dir / "mechanics" / f"negative_{mutation}" \
            / f"physics_candidate_broken_{mutation}.json"
        result["negative_controls"][mutation] = bool(_read_json(path).get("failures", []))
    return result


def compare_metrics(original: dict[str, Any], replay: dict[str, Any]) -> tuple[list[dict], float]:
    tolerance = max(item["max_diff_pct"] for item in original["repeat_noise"])
    original_values = _metric_values(original)
    replay_values = _metric_values(replay)
    if set(original_values) != set(replay_values):
        raise ValueError("ODiff metric keys differ between original and replay")
    rows = []
    for key in sorted(original_values):
        old_value, new_value = original_values[key], replay_values[key]
        delta = abs(old_value - new_value)
        rows.append({"metric": key, "original": old_value, "replay": new_value,
                     "absolute_delta": delta, "within_noise_floor": delta <= tolerance})
    return rows, tolerance


def _metric_values(metrics: dict[str, Any]) -> dict[str, float]:
    values = {}
    for repeat in metrics["repeat_noise"]:
        values[f"repeat_noise/{repeat['repeat']}/max"] = float(repeat["max_diff_pct"])
        for view in repeat["views"]:
            values[f"repeat_noise/{repeat['repeat']}/{view['view']}"] = float(view["diff_pct"])
    for candidate in metrics["candidate_comparisons"]:
        values[f"candidate/{candidate['variant']}/mean"] = float(candidate["mean_diff_pct"])
        values[f"candidate/{candidate['variant']}/max"] = float(candidate["max_diff_pct"])
        for view in candidate["views"]:
            values[f"candidate/{candidate['variant']}/{view['view']}"] = float(view["diff_pct"])
    return values


def _route_pass(physics: dict[str, Any]) -> bool:
    reached = all(segment.get("reached") for segment in physics.get("route_segments", []))
    out_and_back = physics.get("out_and_back", {})
    return reached and bool(physics.get("route_segments")) and out_and_back.get("distance_m", 0) > 0


def _support_pass(physics: dict[str, Any]) -> bool:
    summary = physics.get("out_and_back", {})
    return float(summary.get("floor_fraction", 0)) >= 1.0 \
        and int(summary.get("safety_contacts", 0)) == 0


def _repeat_ids(variant_dir: Path) -> list[str]:
    repeats = sorted(path.name for path in variant_dir.glob("repeat_*") if path.is_dir())
    if not repeats:
        raise FileNotFoundError(f"no verifier repeats found in {variant_dir}")
    return repeats


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
