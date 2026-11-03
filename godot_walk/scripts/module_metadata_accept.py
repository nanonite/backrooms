"""Operator acceptance of a mechanical module_poetics draft (writes the v2 record).

Pure record building plus the kit-module path. Source-room acceptance (which
also appends a ledger event) lives in module_integration_stages.py.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import posixpath
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from deterministic_json import ROOT, canonical_bytes, repo_relative, sha256_bytes, sha256_file, write_new
from library_index import LibraryIndexError, load_json, load_verified_index

SCHEMA_PATH = "godot_walk/room_catalog/module_poetics.schema.json"
KIT_DECISIONS = "godot_walk/room_catalog/module_poetics/decisions.jsonl"
SOURCE_FRAMES = "godot_walk/source_library/sources/{source_id}/frames/"
KIT_EVIDENCE_PREFIX = "godot_walk/"
DETAIL_SEPARATOR = "::"


class AcceptError(ValueError):
    """The operator metadata flags or targets are invalid."""


@dataclass(frozen=True)
class AcceptFlags:
    form_role: str
    rarity_tier: int
    apollonian: float
    dionysian: float
    style_tags: tuple[str, ...]
    unique_details: tuple[str, ...]  # "<frame_path>::<text>"
    surface_salience: str
    reason: str


def add_accept_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--form-role", choices=("ground", "figure"), required=True)
    parser.add_argument("--rarity-tier", type=int, choices=range(4), required=True)
    parser.add_argument("--apollonian", type=float, required=True)
    parser.add_argument("--dionysian", type=float, required=True)
    parser.add_argument("--style-tag", action="append", default=[], dest="style_tags")
    parser.add_argument("--unique-detail", action="append", default=[], dest="unique_details")
    parser.add_argument("--surface-salience", required=True)
    parser.add_argument("--reason", required=True)


def flags_from_args(arguments: argparse.Namespace) -> AcceptFlags:
    return AcceptFlags(
        arguments.form_role, arguments.rarity_tier, arguments.apollonian, arguments.dionysian,
        tuple(arguments.style_tags), tuple(arguments.unique_details),
        arguments.surface_salience, arguments.reason,
    )


def _frame_ok(path: str, prefix: str, root: Path) -> bool:
    if posixpath.normpath(path) != path or path.startswith("/") or not path.startswith(prefix):
        return False
    current = root.resolve()
    for part in Path(path).parts:
        current /= part
        if current.is_symlink():
            return False
    return current.is_file()


def parse_unique_details(
    raw: tuple[str, ...], prefix: str, root: Path
) -> list[dict[str, str]]:
    details = []
    for item in raw:
        frame, separator, text = item.partition(DETAIL_SEPARATOR)
        if not separator or not text.strip():
            raise AcceptError(f"unique-detail must be '<frame_path>{DETAIL_SEPARATOR}<text>': {item!r}")
        if not _frame_ok(frame, prefix, root):
            raise AcceptError(f"unique-detail frame is missing or outside {prefix}: {frame}")
        details.append({"description": text.strip(), "source_frame": frame})
    return details


def validate_flags(flags: AcceptFlags, details: list[dict[str, str]]) -> None:
    if not flags.reason.strip() or not flags.surface_salience.strip():
        raise AcceptError("reason and surface-salience must not be empty")
    for name, value in (("apollonian", flags.apollonian), ("dionysian", flags.dionysian)):
        if not 0.0 <= value <= 1.0:
            raise AcceptError(f"{name} must be within 0..1")
    tags = [tag.strip() for tag in flags.style_tags]
    if any(not tag for tag in tags) or len(set(tags)) != len(tags):
        raise AcceptError("style tags must be unique and non-empty")
    if flags.form_role == "figure" and not details:
        raise AcceptError("form_role figure requires at least one --unique-detail")


def accepted_record(
    draft: dict[str, Any], draft_path: str, draft_sha256: str,
    flags: AcceptFlags, details: list[dict[str, str]],
) -> dict[str, Any]:
    """v1 plus filled poetics. Never mutates the draft."""
    if draft.get("metadata_status") != "draft_mechanical":
        raise AcceptError("Only a draft_mechanical record can be accepted")
    record = copy.deepcopy(draft)
    record["metadata_status"] = "operator_accepted"
    record["poetics"] = {
        "form_role": flags.form_role,
        "rarity_tier": flags.rarity_tier,
        "apollonian": flags.apollonian,
        "dionysian": flags.dionysian,
        "style_tags": sorted(tag.strip() for tag in flags.style_tags),
        "surface_salience": flags.surface_salience.strip(),
        "unique_details": details,
        "poetics_status": "operator_confirmed",
    }
    record["supersedes"] = {"path": draft_path, "sha256": draft_sha256}
    record["eligibility"]["layout_eligible_derived"] = bool(draft["ports"]["tested_sockets"])
    return record


def check_schema(record: dict[str, Any], root: Path) -> None:
    schema = load_json(root / SCHEMA_PATH)
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(record)
    ]
    if errors:
        raise AcceptError("Accepted record fails module_poetics.schema.json: " + "; ".join(errors))


def accept_kit(
    index_path: Path, module_id: str, flags: AcceptFlags,
    draft_locator: Callable[[dict[str, Any], Path], Path], root: Path = ROOT,
) -> dict[str, str]:
    """Accept a kit (no source video) module; append-only decisions.jsonl record."""
    index = load_verified_index(index_path, root)
    entries = [e for e in index["modules"] if e["module_id"] == module_id]
    if len(entries) != 1:
        raise AcceptError(f"Unknown module in index: {module_id}")
    entry = entries[0]
    if entry["source_id"] is not None:
        raise AcceptError(f"{module_id} has a source video; use the runner's accept-module-metadata")
    draft_file = draft_locator(entry, root)
    if not draft_file.is_file():
        raise AcceptError(f"No derived draft for {module_id}: {draft_file}")
    draft = load_json(draft_file)
    if draft["library_index"]["sha256"] != sha256_file(index_path):
        raise AcceptError("Draft is stale for the supplied library index")
    target = draft_file.with_name(draft_file.stem + ".accepted.json")
    if target.exists() or target.is_symlink():
        raise AcceptError(f"Refusing to overwrite {repo_relative(target, root)}")
    details = parse_unique_details(flags.unique_details, KIT_EVIDENCE_PREFIX, root)
    validate_flags(flags, details)
    record = accepted_record(draft, repo_relative(draft_file, root), sha256_file(draft_file), flags, details)
    check_schema(record, root)
    data = canonical_bytes(record)
    write_new(target, data)
    decision = {
        "module_id": entry["module_id"], "version": entry["version"],
        "path": repo_relative(target, root), "sha256": sha256_bytes(data),
        "supersedes": record["supersedes"], "reason": flags.reason.strip(),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    log = root / KIT_DECISIONS
    with log.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")
    return {"accepted": decision["path"], "sha256": decision["sha256"]}


def source_frame_prefix(source_id: str) -> str:
    return SOURCE_FRAMES.format(source_id=source_id)


__all__ = ["AcceptError", "AcceptFlags", "LibraryIndexError", "accept_kit"]
