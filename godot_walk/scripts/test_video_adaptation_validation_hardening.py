"""Regression coverage for candidate, spatial, and scene validation gaps."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_adaptation_compatibility import verify_legacy_source_record
from video_adaptation_contracts import (
    V2_COMPAT_DIR,
    candidate_identity_v2,
)
from video_adaptation_decisions import (
    verify_v1_decision_binding as _verify_v1_decision_binding,
)
from video_adaptation_decisions import verify_v2_decision as _verify_v2_decision
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_validation import (
    ROOT,
    canonical_fingerprint,
)

TRANSFER = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"
REFERENCE = ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json"


def load_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class DecisionBindingTests(unittest.TestCase):
    def test_accepted_v1_rejects_missing_fingerprint_or_artifact(self) -> None:
        source = load_record(TRANSFER)
        fingerprint = canonical_fingerprint(
            source["resolved_adaptation"]["dependencies"]
        )
        cases = [
            ("candidate_fingerprint", None),
            ("decision_record_path", None),
            ("decision_sha256", None),
        ]
        for field, value in cases:
            record = copy.deepcopy(source)
            record["operator_decision"][field] = value
            with (
                self.subTest(field=field),
                self.assertRaises(AdaptationValidationError),
            ):
                _verify_v1_decision_binding(
                    record, record["operator_decision"], fingerprint
                )

    def test_v2_schema_allows_pending_but_rejects_unbound_acceptance(self) -> None:
        schema_path = ROOT / "godot_walk/room_catalog/video_adaptation.schema.v2.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        record = copy.deepcopy(load_record(REFERENCE))
        record.update(
            {
                "schema_version": 2,
                "contract_version": "2.0.0",
                "candidate_identity": "a" * 64,
            }
        )
        record["catalog_snapshot"] = json.loads(
            (ROOT / "godot_walk/room_catalog/contract_freeze_v2.json").read_text(
                encoding="utf-8"
            )
        )["catalog_snapshot"]
        record["contract_freeze"] = {
            "path": "godot_walk/room_catalog/contract_freeze_v2.json",
            "sha256": "b" * 64,
        }
        record["status"] = "candidate_pending_review"
        record["operator_decision"] = {
            "status": "pending",
            "decision_record_path": None,
            "decision_sha256": None,
            "candidate_fingerprint": None,
        }
        jsonschema.Draft202012Validator(schema).validate(record)
        record["status"] = "accepted_reference"
        accepted = record["operator_decision"]
        accepted.update(
            {
                "status": "accepted",
                "decision_record_path": "decision.json",
                "decision_sha256": "c" * 64,
                "candidate_fingerprint": "a" * 64,
            }
        )
        for field in (
            "decision_record_path",
            "decision_sha256",
            "candidate_fingerprint",
        ):
            for missing_value in (None, "__missing__"):
                candidate = copy.deepcopy(record)
                if missing_value == "__missing__":
                    candidate["operator_decision"].pop(field)
                else:
                    candidate["operator_decision"][field] = None
                with (
                    self.subTest(field=field, value=missing_value),
                    self.assertRaises(jsonschema.ValidationError),
                ):
                    jsonschema.Draft202012Validator(schema).validate(candidate)

    def test_v2_decision_artifact_must_match_candidate_and_accept(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for artifact in (
                {
                    "adaptation_id": "other-room",
                    "candidate_identity": "a" * 64,
                    "decision": "accepted",
                },
                {
                    "adaptation_id": "fixture-room",
                    "candidate_identity": "b" * 64,
                    "decision": "accepted",
                },
                {
                    "adaptation_id": "fixture-room",
                    "candidate_identity": "a" * 64,
                    "decision": "rejected",
                },
            ):
                with self.subTest(artifact=artifact):
                    self._assert_invalid_decision(root, artifact)

    def _assert_invalid_decision(self, root: Path, artifact: dict) -> None:
        path = root / "decision.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        record = {
            "adaptation_id": "fixture-room",
            "operator_decision": {
                "status": "accepted",
                "candidate_fingerprint": "a" * 64,
                "decision_record_path": "decision.json",
                "decision_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        }
        with self.assertRaises(AdaptationValidationError):
            _verify_v2_decision(record, "a" * 64, root=root)

    def test_metadata_edit_invalidates_legacy_approval_binding(self) -> None:
        original = load_record(REFERENCE)
        compatibility_path = ROOT / f"{V2_COMPAT_DIR}/{original['adaptation_id']}.json"
        compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
        mutations = {
            "footprint": lambda candidate: candidate["resolved_adaptation"][
                "walkable_space"
            ]["footprint"]["vertices_xz"][0].__setitem__(0, -5.9),
            "render envelope": lambda candidate: candidate["resolved_adaptation"][
                "rendered_placement_envelope"
            ]["bounds_xyz"]["max"].__setitem__(0, 13.2),
            "spawn": lambda candidate: candidate["resolved_adaptation"][
                "walkable_space"
            ]["safe_spawn_xyz"].__setitem__(0, -3.9),
            "socket": lambda candidate: candidate["resolved_adaptation"]["sockets"][0][
                "clear_size"
            ].__setitem__(0, 2.1),
        }
        for label, mutate in mutations.items():
            changed = copy.deepcopy(original)
            mutate(changed)
            with (
                self.subTest(metadata=label),
                tempfile.TemporaryDirectory() as temporary,
            ):
                path = Path(temporary) / "record.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                binding = copy.deepcopy(compatibility)
                binding["source_record_sha256"] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                with self.assertRaisesRegex(
                    AdaptationValidationError, "metadata changed"
                ):
                    verify_legacy_source_record(
                        changed, path, binding, root=Path(temporary)
                    )
            self.assertNotEqual(
                candidate_identity_v2(original), candidate_identity_v2(changed)
            )

    def test_legacy_decision_artifact_must_match_accepted_layout(self) -> None:
        original = load_record(REFERENCE)
        compatibility = self._compatibility(original)
        artifact_path = ROOT / original["operator_decision"]["decision_record_path"]
        source_artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        for change in (
            {"reviewed_layout_id": "another-layout"},
            {"decision": "rejected"},
        ):
            with (
                self.subTest(change=change),
                tempfile.TemporaryDirectory() as temporary,
            ):
                artifact = {**source_artifact, **change}
                self._assert_legacy_artifact_fails(
                    original, compatibility, artifact, Path(temporary)
                )

    def _compatibility(self, record: dict) -> dict:
        path = ROOT / f"{V2_COMPAT_DIR}/{record['adaptation_id']}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_legacy_artifact_fails(
        self, original: dict, compatibility: dict, artifact: dict, root: Path
    ) -> None:
        artifact_path = root / "decision.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        record = copy.deepcopy(original)
        record["operator_decision"]["decision_record_path"] = "decision.json"
        record["operator_decision"]["decision_sha256"] = hashlib.sha256(
            artifact_path.read_bytes()
        ).hexdigest()
        record_path = root / "record.json"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        binding = copy.deepcopy(compatibility)
        binding["source_record_sha256"] = hashlib.sha256(
            record_path.read_bytes()
        ).hexdigest()
        binding["decision_artifact"] = {
            "path": "decision.json",
            "sha256": record["operator_decision"]["decision_sha256"],
        }
        with self.assertRaisesRegex(AdaptationValidationError, "does not affirm"):
            verify_legacy_source_record(record, record_path, binding, root=root)


if __name__ == "__main__":
    unittest.main()
