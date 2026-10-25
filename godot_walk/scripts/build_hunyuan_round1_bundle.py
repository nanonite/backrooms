"""Create matched visual diagnostics and an operator review bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from hunyuan_round1_contract import EXPECTED_HASHES, SCHEMA_DIR
from hunyuan_round1_operator_form import write_review_page
from hunyuan_round1_records import (
    build_pending_feedback,
    build_round_manifest,
    validate_document,
)
from hunyuan_round1_report import write_report
from hunyuan_round1_visual_evidence import (
    build_metrics,
    draw_contact_sheet,
    validate_captures,
)


def main() -> int:
    out_dir = _parse_args()
    _validate_source_hashes()
    frames = validate_captures(out_dir)
    metrics = build_metrics(out_dir)
    draw_contact_sheet(out_dir)
    _write_review_records(out_dir, frames, metrics)
    print(f"REVIEW_BUNDLE_READY: {out_dir / 'index.html'}")
    return 0


def _parse_args() -> Path:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    return Path(parser.parse_args().out_dir).resolve()


def _validate_source_hashes() -> None:
    for token, expected in EXPECTED_HASHES.items():
        actual = _sha256(Path(__file__).resolve().parents[2] / token)
        if actual != expected:
            raise ValueError(f"Protected source hash mismatch: {token}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_review_records(out_dir: Path, frames: dict, metrics: dict) -> None:
    feedback = build_pending_feedback()
    manifest = build_round_manifest(out_dir, frames, metrics)
    validate_document(feedback, SCHEMA_DIR / "operator_feedback.schema.json")
    validate_document(manifest, SCHEMA_DIR / "hunyuan_round.schema.json")
    _write_json(out_dir / "operator_feedback.json", feedback)
    _write_json(out_dir / "round_manifest.json", manifest)
    write_report(out_dir, manifest, metrics)
    write_review_page(out_dir, metrics)


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
