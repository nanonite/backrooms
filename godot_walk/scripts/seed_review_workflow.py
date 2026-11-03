"""Load and verify the frozen seed-review workflow specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seed_review_errors import SeedReviewError
from seed_review_paths import (
    ROOT,
    WORKFLOW_MANIFEST,
    read_json_object,
    resolve_repo_path,
    sha256_file,
)

WORKFLOW_SPEC_VERSION = "1.0.0"
STAGE = "seed_review"
MAX_CANDIDATES = 3
SCHEMA_KINDS = ("request", "response", "receipt")


@dataclass(frozen=True)
class WorkflowSpec:
    """The frozen values a receipt is bound to."""

    spec_version: str
    stage: str
    max_candidates: int
    default_timeout_seconds: float
    max_timeout_seconds: float
    default_confidence_threshold: int
    prompt_version: str
    preferred_vision_model: str
    manifest_path: str
    manifest_sha256: str
    schema_paths: dict[str, str]
    schema_sha256: dict[str, str]

    def schema_path(self, kind: str, root: Path = ROOT) -> Path:
        return resolve_repo_path(self.schema_paths[kind], root, require_file=True)


def load_workflow_spec(root: Path = ROOT) -> WorkflowSpec:
    manifest_path = root / WORKFLOW_MANIFEST.relative_to(ROOT)
    manifest = read_json_object(manifest_path, "seed-review workflow manifest")
    _verify_manifest_identity(manifest)
    schema_paths = _schema_paths(manifest)
    schema_hashes = {
        kind: sha256_file(resolve_repo_path(path, root, require_file=True))
        for kind, path in schema_paths.items()
    }
    model_policy = manifest.get("model_policy", {})
    flags = manifest.get("flags", {})
    if (
        flags.get("registration_accepted") is not False
        or flags.get("scale_calibrated") is not False
    ):
        raise SeedReviewError(
            "workflow_flag_changed",
            "Seed-review workflow flags must stay false for this slice",
        )
    return WorkflowSpec(
        spec_version=manifest["workflow_spec_version"],
        stage=manifest["stage"],
        max_candidates=int(manifest["max_candidates"]),
        default_timeout_seconds=float(manifest["default_timeout_seconds"]),
        max_timeout_seconds=float(manifest["max_timeout_seconds"]),
        default_confidence_threshold=int(manifest["default_confidence_threshold"]),
        prompt_version=manifest["prompt_version"],
        preferred_vision_model=model_policy.get(
            "preferred_vision_model",
            "opencode/nemotron-3.5-super-vl-free",
        ),
        manifest_path=WORKFLOW_MANIFEST.relative_to(ROOT).as_posix(),
        manifest_sha256=sha256_file(manifest_path),
        schema_paths=schema_paths,
        schema_sha256=schema_hashes,
    )


def _verify_manifest_identity(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise SeedReviewError(
            "workflow_schema_unsupported",
            "Seed-review workflow manifest must use schema_version 1",
        )
    if manifest.get("workflow_spec_version") != WORKFLOW_SPEC_VERSION:
        raise SeedReviewError(
            "workflow_version_unsupported",
            f"Expected workflow spec {WORKFLOW_SPEC_VERSION}",
        )
    if manifest.get("stage") != STAGE:
        raise SeedReviewError(
            "workflow_stage_unsupported", "Seed-review workflow stage mismatch"
        )
    if manifest.get("max_candidates") != MAX_CANDIDATES:
        raise SeedReviewError(
            "workflow_limit_changed",
            "This slice accepts exactly three review candidates",
        )


def _schema_paths(manifest: dict[str, Any]) -> dict[str, str]:
    schemas = manifest.get("schemas")
    if not isinstance(schemas, dict):
        raise SeedReviewError(
            "workflow_schema_missing", "Seed-review workflow lacks schema paths"
        )
    paths: dict[str, str] = {}
    for kind in SCHEMA_KINDS:
        value = schemas.get(kind)
        if not isinstance(value, str) or not value.startswith("godot_walk/"):
            raise SeedReviewError(
                "workflow_schema_missing", f"Missing repository schema: {kind}"
            )
        paths[kind] = value
    return paths
