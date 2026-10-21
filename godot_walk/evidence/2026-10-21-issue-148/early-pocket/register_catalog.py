"""Update Issue 148 catalog hashes and register its authored module link."""

from __future__ import annotations

import json

from catalog_record import early_module
from catalog_support import (
    EARLY_ID,
    EARLY_SOCKET_ID,
    ISSUE_ROOT,
    LATER_SOCKET_ID,
    ROOT,
    connector_socket,
    file_hash,
    tested_connector,
)

CATALOG_PATH = ROOT / "splat_walk/room_catalog/catalog.json"
LATER_ID = "hunyuan-issue-150-later-bay"


def refresh_evidence(module: dict, relative_path: str) -> None:
    for evidence in module["validation_evidence"]:
        if evidence["path"] == relative_path:
            evidence["sha256"] = file_hash(relative_path)
    for boundary in module["boundary_rules"]:
        if boundary["evidence"]["path"] == relative_path:
            boundary["evidence"]["sha256"] = file_hash(relative_path)


def main() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    reference, later_bay = catalog["modules"][:2]
    refresh_evidence(reference, f"{ISSUE_ROOT}/tagged-reference-walkability.json")
    for path in (
        f"{ISSUE_ROOT}/REPORT.md",
        f"{ISSUE_ROOT}/COMMANDS.md",
        f"{ISSUE_ROOT}/issue150-standalone-walkability.json",
        "splat_walk/src/bin/walkability_harness/route_scene/authored_visuals.rs",
    ):
        refresh_evidence(later_bay, path)

    later_bay["connector_sockets"] = [connector_socket(
        LATER_SOCKET_ID,
        "Authored east-wall socket only in the #148 assembly adaptation; #150 remains unchanged as a closed standalone baseline.",
        [4.5, -1.2709904909133911 + 1.2, 4.0],
    )]
    later_bay["tested_connectors"] = [tested_connector(
        "issue148-later-bay-to-early-pocket",
        LATER_SOCKET_ID,
        EARLY_ID,
        EARLY_SOCKET_ID,
    )]

    modules = [reference, later_bay]
    existing = next((index for index, module in enumerate(modules) if module["id"] == EARLY_ID), None)
    record = early_module(later_bay["shared_controller"])
    if existing is None:
        modules.append(record)
    else:
        modules[existing] = record
    catalog["modules"] = modules
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
