"""Verify that #164 preserved the accepted #160/#149/#163 reference files."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-24-issue-164"
START = EVIDENCE / "protected_hashes_start.json"
END = EVIDENCE / "protected_hashes_end.json"


def verify() -> list[dict[str, str | bool]]:
    manifest = json.loads(START.read_text(encoding="utf-8"))
    records = []
    for expected in manifest["files"]:
        path = ROOT / expected["path"]
        actual = _sha256(path) if path.is_file() else "missing"
        records.append(
            {
                "path": expected["path"],
                "expected_sha256": expected["sha256"],
                "actual_sha256": actual,
                "verified": actual == expected["sha256"],
            }
        )
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    records = verify()
    result = {
        "issue": 164,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "protected_file_count": len(records),
        "all_verified": all(item["verified"] for item in records),
        "files": records,
    }
    END.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    failed = [item["path"] for item in records if not item["verified"]]
    if failed:
        print("ISSUE164_PROTECTED_HASH_FAILURE: " + ", ".join(failed))
        return 1
    print(f"ISSUE164_PROTECTED_HASHES_VERIFIED: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
