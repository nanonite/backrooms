"""Validate request, response, and receipt documents against frozen schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT, read_json_object, resolve_repo_path
from seed_review_workflow import WorkflowSpec


def validate_request(document: dict[str, Any], spec: WorkflowSpec) -> None:
    validate_document(document, spec, "request", "seed-review request")


def validate_response(document: dict[str, Any], spec: WorkflowSpec) -> None:
    validate_document(document, spec, "response", "seed-review response")


def validate_receipt(document: dict[str, Any], spec: WorkflowSpec) -> None:
    validate_document(document, spec, "receipt", "seed-review receipt")


def validate_document(
    document: dict[str, Any],
    spec: WorkflowSpec,
    kind: str,
    label: str,
) -> None:
    schema = load_schema(spec, kind)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=_error_sort_key)
    if not errors:
        return
    details = [
        {
            "path": "/".join(str(part) for part in error.absolute_path),
            "message": error.message,
        }
        for error in errors[:5]
    ]
    raise SeedReviewError(
        "schema_violation",
        f"{label} violates the frozen {kind} schema: {details[0]['message']}",
        details={"schema": kind, "errors": details},
    )


def load_schema(spec: WorkflowSpec, kind: str, root: Path = ROOT) -> dict[str, Any]:
    if kind not in spec.schema_paths:
        raise SeedReviewError(
            "schema_unknown", f"Unknown seed-review schema kind: {kind}"
        )
    path = resolve_repo_path(spec.schema_paths[kind], root, require_file=True)
    return read_json_object(path, f"seed-review {kind} schema")


def _error_sort_key(error: jsonschema.ValidationError) -> list[str]:
    return [str(part) for part in error.absolute_path]
