"""Validate committed operator approval receipts for template layer fields."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from deterministic_json import ROOT

RECEIPT_SCHEMA = Path("godot_walk/room_catalog/operator_approval_receipt.schema.json")
RECEIPT_DIR = Path("godot_walk/room_catalog/operator_approval_receipts")
APPROVED_ISSUE_IDS = frozenset({216, 217, 218, 219})
MAPPING_TABLE_PATH = "godot_walk/room_catalog/module_surface_palette_mapping_v0.1.0.md"


def _field_matches(pattern: str, actual: str) -> bool:
    expected_parts = pattern.strip("/").split("/")
    actual_parts = actual.strip("/").split("/")
    return len(expected_parts) <= len(actual_parts) and all(
        expected == "*" or expected == found
        for expected, found in zip(expected_parts, actual_parts[: len(expected_parts)])
    )


def _field_exists(document: Any, pattern: str) -> bool:
    nodes = [document]
    for segment in pattern.strip("/").split("/"):
        next_nodes: list[Any] = []
        for node in nodes:
            if segment == "*":
                if isinstance(node, dict):
                    children = list(node.values())
                elif isinstance(node, list):
                    children = node
                else:
                    return False
            elif isinstance(node, dict):
                if segment not in node:
                    return False
                children = [node[segment]]
            elif isinstance(node, list) and segment.isdigit():
                index = int(segment)
                if index >= len(node):
                    return False
                children = [node[index]]
            else:
                return False
            if not children:
                return False
            next_nodes.extend(children)
        nodes = next_nodes
    return bool(nodes)


def _load_receipt_schema(root: Path) -> dict[str, Any]:
    schema = json.loads((root / RECEIPT_SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_receipt(receipt_path: Path, root: Path = ROOT) -> list[str]:
    """Return schema, reference, hash, and field errors for one receipt."""
    try:
        return _validate_receipt(receipt_path, root)
    except Exception as error:
        return [f"{receipt_path}: cannot validate receipt: {error}"]


def _validate_receipt(receipt_path: Path, root: Path) -> list[str]:
    relative_receipt = receipt_path.relative_to(root).as_posix()
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            return [f"{relative_receipt}: receipt must be a JSON object"]
        errors = [
            f"{relative_receipt}: {error.message}"
            for error in Draft202012Validator(_load_receipt_schema(root)).iter_errors(receipt)
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return [f"{relative_receipt}: cannot validate receipt: {error}"]
    if errors:
        return errors
    if receipt["issue_id"] not in APPROVED_ISSUE_IDS:
        return [f"{relative_receipt}: unknown issue {receipt['issue_id']}"]
    if receipt["source"]["issue_id"] != receipt["issue_id"]:
        return [f"{relative_receipt}: source issue does not match receipt issue"]
    for item in receipt["scope"]:
        if "derived_from" in item and (
            receipt["issue_id"] != 217 or item["path"] != MAPPING_TABLE_PATH
        ):
            errors.append(f"{relative_receipt}: derived approval is only valid for issue 217's mapping table")
        errors.extend(_validate_scope_item(relative_receipt, item, root))
    return errors


def _validate_scope_item(receipt_path: str, item: dict[str, Any], root: Path) -> list[str]:
    path = root / item["path"]
    label = f"{receipt_path}: {item['path']}"
    try:
        path.resolve().relative_to(root.resolve())
        content = path.read_bytes()
        hash_errors = (
            [f"{label}: sha256 mismatch"]
            if hashlib.sha256(content).hexdigest() != item["sha256"]
            else []
        )
        if path.suffix.lower() == ".md":
            errors = hash_errors + _markdown_scope_errors(label, content, item["fields"])
            if "derived_from" in item:
                errors.extend(_validate_derived_mapping(receipt_path, item, root))
            return errors
        document = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"{label}: cannot read referenced JSON file: {error}"]
    errors = hash_errors
    for field in item["fields"]:
        if not _field_exists(document, field):
            errors.append(f"{label}: scoped field does not exist: {field}")
    if "derived_from" in item:
        errors.extend(_validate_derived_mapping(receipt_path, item, root))
    return errors


def _validate_derived_mapping(receipt_path: str, item: dict[str, Any], root: Path) -> list[str]:
    if item["path"] != MAPPING_TABLE_PATH:
        return [f"{receipt_path}: derived approval target is not the approved mapping table"]
    derived = item["derived_from"]
    descriptor_records = derived["files"]
    errors: list[str] = []
    descriptors: list[dict[str, Any]] = []
    for record in descriptor_records:
        descriptor_path = root / record["path"]
        errors.extend(_validate_derived_file(receipt_path, record, root))
        try:
            descriptors.append(json.loads(descriptor_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{receipt_path}: cannot read derived descriptor {record['path']}: {error}")
    if errors:
        return errors
    try:
        from module_surface_palette import mapping_table

        generated = mapping_table(descriptors).encode("utf-8")
        table_path = root / item["path"]
        if generated != table_path.read_bytes():
            errors.append(f"{receipt_path}: derived mapping table differs from regenerated descriptors")
    except (OSError, ImportError, KeyError, TypeError, ValueError) as error:
        errors.append(f"{receipt_path}: cannot regenerate derived mapping table: {error}")
    return errors


def _validate_derived_file(receipt_path: str, record: dict[str, str], root: Path) -> list[str]:
    path = root / record["path"]
    try:
        path.resolve().relative_to(root.resolve())
        matches = hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    except (OSError, ValueError):
        matches = False
    if not matches:
        return [f"{receipt_path}: derived file hash mismatch or unreadable: {record['path']}"]
    return []


def _markdown_scope_errors(label: str, content: bytes, fields: list[str]) -> list[str]:
    headers = _markdown_headers(content.decode("utf-8"))
    if not headers:
        return [f"{label}: markdown table header does not exist"]
    errors = []
    for field in fields:
        if not field.startswith("/table/") or field.removeprefix("/table/") not in headers:
            errors.append(f"{label}: scoped field does not exist: {field}")
    return errors


def _concrete_field_exists(path: Path, field_path: str) -> bool:
    if "*" in field_path:
        return False
    try:
        content = path.read_bytes()
        if path.suffix.lower() == ".md":
            text = content.decode("utf-8")
            return any(
                field_path == f"/table/{header}"
                for header in _markdown_headers(text)
            )
        return _field_exists(json.loads(content), field_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False


def _markdown_headers(text: str) -> set[str]:
    for line in text.splitlines():
        if line.strip().startswith("|") and "---" not in line:
            return {part.strip() for part in line.strip().strip("|").split("|")}
    return set()


def validate_receipts(root: Path = ROOT) -> list[str]:
    """Validate all committed receipts; malformed records are reported, never raised."""
    directory = root / RECEIPT_DIR
    try:
        receipt_paths = sorted(directory.glob("*.json"))
    except OSError as error:
        return [f"{RECEIPT_DIR}: cannot list receipts: {error}"]
    if not receipt_paths:
        return [f"{RECEIPT_DIR}: no approval receipts found"]
    errors: list[str] = []
    seen_issue_ids: set[int] = set()
    for receipt_path in receipt_paths:
        try:
            errors.extend(validate_receipt(receipt_path, root))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            issue_id = receipt.get("issue_id") if isinstance(receipt, dict) else None
            if isinstance(issue_id, int) and issue_id in seen_issue_ids:
                errors.append(f"{receipt_path}: duplicate receipt for issue {issue_id}")
            elif isinstance(issue_id, int) and issue_id in APPROVED_ISSUE_IDS:
                seen_issue_ids.add(issue_id)
        except (OSError, ValueError, TypeError, KeyError) as error:
            errors.append(f"{receipt_path}: cannot validate receipt: {error}")
    for issue_id in sorted(APPROVED_ISSUE_IDS - seen_issue_ids):
        errors.append(f"{RECEIPT_DIR}: missing approval receipt for issue {issue_id}")
    return errors


def operator_approval_for_field(
    file_path: str, field_path: str, root: Path = ROOT
) -> dict[str, Any] | None:
    """Return the matching valid receipt for a field, using committed receipts only."""
    for receipt_path in sorted((root / RECEIPT_DIR).glob("*.json")):
        if validate_receipt(receipt_path, root):
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for item in receipt["scope"]:
            target_path = root / file_path
            if (
                item["path"] == file_path
                and _concrete_field_exists(target_path, field_path)
                and any(_field_matches(field, field_path) for field in item["fields"])
            ):
                return receipt
            if item["path"] == file_path or "derived_from" not in item:
                continue
            if _approved_derived_descriptor(item, file_path, field_path, root):
                return {**receipt, "approval_via": "approved mapping table"}
    return None


def _approved_derived_descriptor(
    item: dict[str, Any], file_path: str, field_path: str, root: Path
) -> bool:
    if item["path"] != MAPPING_TABLE_PATH:
        return False
    if field_path not in ("/surfaces/*/material_id", "/surfaces/*/palette_id"):
        if not (field_path.endswith("/material_id") or field_path.endswith("/palette_id")):
            return False
    if not _concrete_field_exists(root / file_path, field_path):
        return False
    return any(record["path"] == file_path for record in item["derived_from"]["files"])
