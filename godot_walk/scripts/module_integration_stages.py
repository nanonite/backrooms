"""Runner stages: derive/accept module metadata, propose/decide integrations.

Each `plan_*` function checks every precondition, writes its own artifact
(never an existing one) and returns the event payload; the runner appends the
event under the source lock. Nothing here edits a module, the catalog, a
snapshot, a map or an earlier event.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from deterministic_json import (
    ROOT, canonical_bytes, plan_write, repo_relative,
    resolve_cli_path, sha256_bytes, sha256_file, write_new,
)
from integration_fit import top_fits
from integration_preconditions import (
    EVENT_DECIDED, EVENT_RECORDED, accepted_event, admission_sequence, current_index,
    derived_event, events_of, require_admission, room_entry, verified_draft,
)
from integration_records import (
    ProposalContext, keep_standalone_record, module_geometry, propose_record,
    validate_record, SCHEMA_PATH as PROPOSAL_SCHEMA,
)
from jsonschema import Draft202012Validator
from library_index import load_json, resolve_pointer
from module_metadata_accept import (
    AcceptFlags, accepted_record, check_schema, parse_unique_details, source_frame_prefix,
    validate_flags,
)
from module_poetics import derive_record, draft_path, load_index_context
from poetics_geometry import open_ring, signed_area
from source_ingestion_policy import WorkflowGateError

MAP_SCHEMA = "godot_walk/room_catalog/generative_map.schema.json"
V2_NAME = "module_poetics_v2.json"
MAP_ID_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
CHOICES = ("accept", "reject", "keep_standalone")


def plan_derive(
    source_id: str, room_id: str, events: list[dict[str, Any]], root: Path = ROOT
) -> dict[str, Any] | None:
    index_path, index, index_sha = current_index(root)
    entry = room_entry(source_id, room_id, index, root)
    require_admission(events, entry, root)
    _, snapshot, ref = load_index_context(index_path, root)
    module = resolve_pointer(snapshot, entry["location"])
    record = derive_record(entry, module, index["connector_pairs"], ref, index["snapshot_sha256"])
    data = canonical_bytes(record)
    target = draft_path(entry, root)
    digest = sha256_bytes(data)
    already = any(
        e["payload"].get("draft_sha256") == digest and e["payload"].get("module_id") == entry["module_id"]
        for e in events_of(events, "module_metadata_derived")
    )
    status = plan_write(target, data)  # raises if a different draft exists
    if status == "create":
        write_new(target, data)
    if already:
        return None
    return {
        "module_id": entry["module_id"], "version": entry["version"],
        "draft_path": repo_relative(target, root), "draft_sha256": digest,
        "library_index_path": ref["path"], "library_index_sha256": index_sha,
        "catalog_snapshot_sha256": index["snapshot_sha256"],
    }


def plan_accept(
    source_id: str, room_id: str, flags: AcceptFlags, events: list[dict[str, Any]], root: Path = ROOT
) -> dict[str, Any]:
    _, index, index_sha = current_index(root)
    entry = room_entry(source_id, room_id, index, root)
    require_admission(events, entry, root)
    draft, draft_rel, draft_sha = verified_draft(events, entry, index_sha, root)
    target = root / entry["room_dir"] / V2_NAME
    if target.exists() or target.is_symlink() or accepted_event(events, entry) is not None:
        raise WorkflowGateError(f"Metadata already accepted for {entry['module_id']}; v2 is immutable")
    details = parse_unique_details(flags.unique_details, source_frame_prefix(source_id), root)
    validate_flags(flags, details)
    record = accepted_record(draft, draft_rel, draft_sha, flags, details)
    check_schema(record, root)
    data = canonical_bytes(record)
    write_new(target, data)
    return {
        "module_id": entry["module_id"], "version": entry["version"],
        "path": repo_relative(target, root), "sha256": sha256_bytes(data),
        "reason": flags.reason.strip(), "supersedes": record["supersedes"],
    }


def _accepted_draft(
    events: list[dict[str, Any]], entry: dict[str, Any], root: Path
) -> tuple[dict[str, Any], str] | None:
    event = accepted_event(events, entry)
    if event is None:
        return None
    path, digest = event["payload"].get("path"), event["payload"].get("sha256")
    target = root / str(path)
    if not target.is_file() or sha256_file(target) != digest:
        raise WorkflowGateError("Accepted metadata changed after it was logged")
    return load_json(target), path


def load_map(map_path: Path, index_path: Path, index: dict[str, Any], root: Path) -> tuple[dict, str, str]:
    path = resolve_cli_path(map_path, root)
    if not path.is_file():
        raise WorkflowGateError(f"Map not found: {map_path}")
    relative = repo_relative(path, root)
    record = load_json(path)
    schema = load_json(root / MAP_SCHEMA)
    problems = [e.message for e in Draft202012Validator(schema).iter_errors(record)]
    if problems:
        raise WorkflowGateError(f"{relative} fails generative_map.schema.json: {problems[0]}")
    reference = record["library_index"]
    if reference["sha256"] != sha256_file(index_path) or reference["path"] != repo_relative(index_path, root):
        raise WorkflowGateError(f"{relative} was made against a different library index (stale hash)")
    if record["catalog_snapshot"]["sha256"] != index["snapshot_sha256"]:
        raise WorkflowGateError(f"{relative} was made against a different catalog snapshot")
    if not MAP_ID_SAFE.fullmatch(record["map_id"]):
        raise WorkflowGateError("map_id is not safe to use as a folder name")
    return record, relative, sha256_file(path)


def _already_recorded(events: list[dict[str, Any]], entry: dict[str, Any], map_sha: str) -> bool:
    return any(
        e["payload"].get("map_sha256") == map_sha and e["payload"].get("module_id") == entry["module_id"]
        for e in events_of(events, EVENT_RECORDED)
    )


def _records_for_map(ctx: ProposalContext, geometry, record_map: dict[str, Any], figure_only: bool) -> list[dict]:
    cells = [c for c in record_map["cells"] if c["role"] != "void" and (c["role"] == "figure" or not figure_only)]
    fits, fitted = top_fits(cells, geometry)
    if not fits:
        return [keep_standalone_record(ctx, fitted, len(cells))]
    by_id = {c["cell_id"]: c for c in cells}
    return [
        propose_record(ctx, fit, abs(signed_area(open_ring(by_id[fit.cell_id]["envelope_xz"]))))
        for fit in fits
    ]


def plan_propose(
    source_id: str, room_id: str, map_paths: list[Path], events: list[dict[str, Any]], root: Path = ROOT
) -> list[dict[str, Any]]:
    index_path, index, index_sha = current_index(root)
    entry = room_entry(source_id, room_id, index, root)
    require_admission(events, entry, root)
    draft, draft_rel, _ = verified_draft(events, entry, index_sha, root)
    accepted = _accepted_draft(events, entry, root)
    used_draft, used_path = accepted if accepted else (draft, draft_rel)
    figure_only = accepted is not None and used_draft["poetics"]["form_role"] == "figure"
    geometry = module_geometry(used_draft, entry)
    schema = load_json(root / PROPOSAL_SCHEMA)
    planned: list[tuple[dict[str, Any], list[tuple[Path, bytes, dict[str, str]]]]] = []
    seen: set[str] = set()
    for map_path in map_paths:
        record_map, map_rel, map_sha = load_map(map_path, index_path, index, root)
        if map_sha in seen or _already_recorded(events, entry, map_sha):
            continue
        seen.add(map_sha)
        ctx = ProposalContext(
            source_id, entry["module_id"], entry["version"], used_draft, used_path,
            accepted is not None, index, index_sha, record_map["map_id"], map_rel,
        )
        writes = []
        for proposal in _records_for_map(ctx, geometry, record_map, figure_only):
            validate_record(proposal, schema)
            target = root / entry["room_dir"] / "integration_proposals" / record_map["map_id"] / f"{proposal['proposal_id']}.json"
            data = canonical_bytes(proposal)
            plan_write(target, data)  # raises on a different file at the same id
            writes.append((target, data, {"outcome": proposal["outcome"]}))
        planned.append(({"map_id": record_map["map_id"], "map_path": map_rel, "map_sha256": map_sha}, writes))
    payloads = []
    for header, writes in planned:
        listed = []
        for target, data, extra in writes:
            if plan_write(target, data) == "create":
                write_new(target, data)
            listed.append({"path": repo_relative(target, root), "sha256": sha256_bytes(data), **extra})
        payloads.append({
            "module_id": entry["module_id"], "version": entry["version"], **header, "proposals": listed,
        })
    return payloads


def plan_decide(
    source_id: str, proposal: Path, choice: str, reason: str,
    events: list[dict[str, Any]], root: Path = ROOT,
) -> dict[str, Any]:
    if choice not in CHOICES or not reason.strip():
        raise WorkflowGateError("decide-integration needs a choice (accept|reject|keep_standalone) and a reason")
    path = resolve_cli_path(proposal, root)
    if not path.is_file():
        raise WorkflowGateError(f"Proposal not found: {proposal}")
    relative, digest = repo_relative(path, root), sha256_file(path)
    cited = next(
        (e for e in events_of(events, EVENT_RECORDED)
         if any(p.get("path") == relative and p.get("sha256") == digest for p in e["payload"].get("proposals", []))),
        None,
    )
    if cited is None:
        raise WorkflowGateError("Proposal is not cited by an integration_proposal_recorded event with a matching hash")
    record = load_json(path)
    if choice == "accept" and record["outcome"] != "propose":
        raise WorkflowGateError("Only a propose outcome can be accepted")
    prior = [e for e in events_of(events, EVENT_DECIDED) if e["payload"].get("proposal_path") == relative]
    payload = {
        "proposal_path": relative, "proposal_sha256": digest, "proposal_id": record["proposal_id"],
        "module_id": record["module"]["module_id"], "version": record["module"]["version"],
        "map_id": record["map_id"], "cell_id": record["cell_id"], "proposal_outcome": record["outcome"],
        "recorded_event_sequence": cited["sequence"], "choice": choice, "reason": reason.strip(),
        "note": "Records the operator choice only. No module, catalog snapshot or map is changed.",
    }
    if prior:
        payload["supersedes_sequence"] = prior[-1]["sequence"]
    return payload


def available_stages(source_id: str, events: list[dict[str, Any]], root: Path = ROOT) -> list[str]:
    """Next-allowed module-integration stages whose preconditions hold (never raises)."""
    try:
        _, index, _ = current_index(root)
    except (WorkflowGateError, OSError, KeyError, ValueError):
        return []
    stages: list[str] = []
    for entry in index["modules"]:
        if entry["source_id"] != source_id or not (root / entry["room_dir"]).is_dir():
            continue
        if admission_sequence(events, entry, root) is None:
            continue
        room = Path(entry["room_dir"]).name
        if derived_event(events, entry) is None:
            stages.append(f"derive-module-metadata --room-id {room}")
            continue
        if accepted_event(events, entry) is None:
            stages.append(f"accept-module-metadata --room-id {room}")
        stages.append(f"propose-integrations --room-id {room} --map <generative_map.json>")
    decided = {e["payload"].get("proposal_path") for e in events_of(events, EVENT_DECIDED)}
    for event in events_of(events, EVENT_RECORDED):
        stages += [
            f"decide-integration --proposal {p['path']}"
            for p in event["payload"].get("proposals", []) if p["path"] not in decided
        ]
    return stages
