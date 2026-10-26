"""Full-bundle coverage for the bounded Godot resource dependency graph."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Self

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_adaptation_contracts import (
    V2_FREEZE,
    V3_FREEZE,
    candidate_identity_v2,
    sha256_file,
)
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_validation import ROOT, validate_bundle

TEMPLATE = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"
SNAPSHOT_PATH = (
    "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.2.0.json"
)


class RuntimeDependencyBundleTests(unittest.TestCase):
    def test_v2_bundle_requires_the_preloaded_geometry_script(self) -> None:
        source = 'extends Node3D\nconst GEOMETRY = preload("res://{base}/assets/issue165_room_geometry.gd")\n'
        with _BundleFixture(2, source) as fixture:
            missing = fixture.add(
                "assets/issue165_room_geometry.gd", "extends RefCounted\n"
            )
            fixture.omit_dependency(missing)
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError,
                "Required runtime dependency is not fingerprinted",
            ):
                validate_bundle(fixture.bundle)

    def test_nested_scene_material_shader_and_include_cannot_be_omitted(self) -> None:
        source = 'extends Node3D\nconst GEOMETRY = preload("res://{base}/assets/geometry.gd")\n'
        with _BundleFixture(3, source) as fixture:
            fixture.add(
                "assets/geometry.gd",
                f'extends RefCounted\nconst MATERIAL = preload("res://{fixture.res_base}/assets/room_material.tres")\n',
            )
            fixture.add(
                "assets/room_material.tres",
                f'[gd_resource type="ShaderMaterial" format=3]\n[ext_resource type="Shader" path="res://{fixture.res_base}/assets/room.gdshader" id="1"]\n',
            )
            fixture.add(
                "assets/room.gdshader",
                '#shader_type spatial;\n#include "room_common.gdshaderinc"\n',
            )
            include = fixture.add(
                "assets/room_common.gdshaderinc", "// shared shader declarations\n"
            )
            fixture.omit_dependency(include)
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError,
                "Required runtime dependency is not fingerprinted",
            ):
                validate_bundle(fixture.bundle)

    def test_required_dependency_change_invalidates_identity_approval_and_result(
        self,
    ) -> None:
        source = 'extends Node3D\nconst GEOMETRY = preload("res://{base}/assets/geometry.gd")\n'
        with _BundleFixture(3, source) as fixture:
            geometry = fixture.add("assets/geometry.gd", "extends RefCounted\n")
            fixture.write()
            fixture.accept_with_passed_stage()
            fixture.write(refresh_identity=False)
            validate_bundle(fixture.bundle)

            geometry.write_text(
                "extends RefCounted\nvar changed := true\n", encoding="utf-8"
            )
            fixture.refresh_dependency(geometry)
            fixture.write(refresh_identity=False)
            with self.assertRaisesRegex(
                AdaptationValidationError, "Candidate identity is stale"
            ):
                validate_bundle(fixture.bundle)

            fixture.record["candidate_identity"] = candidate_identity_v2(fixture.record)
            fixture.write(refresh_identity=False)
            with self.assertRaisesRegex(
                AdaptationValidationError,
                "Accepted decision needs the current candidate fingerprint",
            ):
                validate_bundle(fixture.bundle)

            fixture.record["operator_decision"]["candidate_fingerprint"] = (
                fixture.record["candidate_identity"]
            )
            fixture.write(refresh_identity=False)
            with self.assertRaisesRegex(
                AdaptationValidationError, "Decision artifact identity"
            ):
                validate_bundle(fixture.bundle)

            fixture.make_pending_but_keep_old_passed_stage()
            fixture.write(refresh_identity=False)
            with self.assertRaisesRegex(
                AdaptationValidationError, "Passed result is stale"
            ):
                validate_bundle(fixture.bundle)

    def test_cycles_terminate_and_dynamic_paths_need_explicit_declarations(
        self,
    ) -> None:
        cycle_source = (
            'extends Node3D\nconst CYCLE = preload("res://{base}/assets/a.gd")\n'
        )
        with _BundleFixture(3, cycle_source) as fixture:
            fixture.add(
                "assets/a.gd",
                f'extends "res://{fixture.res_base}/assets/base.gd"\nconst NEXT = preload("res://{fixture.res_base}/assets/b.gd")\nvar material = load("res://{fixture.res_base}/assets/literal_material.tres")\n',
            )
            fixture.add(
                "assets/b.gd",
                f'extends RefCounted\nconst NEXT = preload("res://{fixture.res_base}/assets/a.gd")\n',
            )
            fixture.add(
                "assets/literal_material.tres",
                '[gd_resource type="Resource" format=3]\n',
            )
            fixture.add("assets/base.gd", "extends RefCounted\n")
            fixture.write()
            validate_bundle(fixture.bundle)

    def test_expression_constant_requires_exhaustive_targets_in_full_bundle(
        self,
    ) -> None:
        source = (
            "extends Node3D\n"
            'const TARGET = "res://{base}/assets/first.tres" if false else "res://{base}/assets/second.tres"\n'
            "func _ready():\n"
            "\tload(TARGET)\n"
        )
        with _BundleFixture(3, source) as fixture:
            fixture.add("assets/first.tres", '[gd_resource type="Resource" format=3]\n')
            second = fixture.add(
                "assets/second.tres", '[gd_resource type="Resource" format=3]\n'
            )
            fixture.omit_dependency(second)
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError, "needs an explicit declaration"
            ):
                validate_bundle(fixture.bundle)

            fixture.record["resolved_adaptation"]["dynamic_resource_declarations"] = [
                {
                    "script_path": fixture.repo_path("assets/room.gd"),
                    "line": 4,
                    "call_index": 0,
                    "expression": "TARGET",
                    "resource_paths": [
                        fixture.repo_path("assets/first.tres"),
                        fixture.repo_path("assets/second.tres"),
                    ],
                }
            ]
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError,
                "Required runtime dependency is not fingerprinted",
            ):
                validate_bundle(fixture.bundle)

            fixture.include_dependency(second)
            fixture.write()
            validate_bundle(fixture.bundle)

    def test_dynamic_paths_need_explicit_declarations_and_targets(self) -> None:
        dynamic_source = (
            "extends Node3D\n"
            'var resource_path := "res://{base}/assets/dynamic_target.tres"\n'
            "func _ready():\n"
            "\tload(resource_path)\n"
        )
        with _BundleFixture(3, dynamic_source) as fixture:
            target = fixture.add(
                "assets/dynamic_target.tres", '[gd_resource type="Resource" format=3]\n'
            )
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError, "needs an explicit declaration"
            ):
                validate_bundle(fixture.bundle)

            fixture.record["resolved_adaptation"]["dynamic_resource_declarations"] = [
                {
                    "script_path": fixture.repo_path("assets/room.gd"),
                    "line": 4,
                    "call_index": 0,
                    "expression": "resource_path",
                    "resource_paths": [fixture.repo_path("assets/dynamic_target.tres")],
                }
            ]
            fixture.omit_dependency(target)
            fixture.write()
            with self.assertRaisesRegex(
                AdaptationValidationError,
                "Required runtime dependency is not fingerprinted",
            ):
                validate_bundle(fixture.bundle)

            fixture.include_dependency(target)
            fixture.write()
            validate_bundle(fixture.bundle)


class _BundleFixture:
    def __init__(self, version: int, room_script: str) -> None:
        self.version = version
        self.temporary = tempfile.TemporaryDirectory(
            prefix="test-video-adaptation-", dir=ROOT / "godot_walk/evidence"
        )
        self.directory = Path(self.temporary.name)
        self.identifier = f"dependency-fixture-{uuid.uuid4().hex[:12]}"
        self.res_base = f"evidence/{self.directory.name}"
        self.dependencies: dict[str, Path] = {}
        self.omitted: set[str] = set()
        self.record = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        self.bundle = self.directory / "adaptation.json"
        self._configure_record()
        self.add("main.tscn", self._main_scene())
        self.add(
            "player.tscn",
            '[gd_scene format=3]\n[node name="Player" type="CharacterBody3D"]\n',
        )
        self.add("assets/room.gd", room_script.format(base=self.res_base))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.temporary.cleanup()

    def _configure_record(self) -> None:
        version_text = f"{self.version}.0.0"
        freeze_path = V2_FREEZE if self.version == 2 else V3_FREEZE
        self.record.update(
            schema_version=self.version,
            contract_version=version_text,
            status="candidate_pending_review",
            adaptation_id=self.identifier,
            contract_freeze={
                "path": freeze_path,
                "sha256": sha256_file(ROOT / freeze_path),
            },
            catalog_snapshot=json.loads((ROOT / V3_FREEZE).read_text(encoding="utf-8"))[
                "catalog_snapshot"
            ],
            operator_decision={
                "status": "pending",
                "decision_record_path": None,
                "decision_sha256": None,
                "candidate_fingerprint": None,
            },
            validation={"mechanical_status": "pending", "stages": []},
        )
        resolved = self.record["resolved_adaptation"]
        resolved["scene_path"] = self.repo_path("main.tscn")
        resolved["catalog_module_refs"] = []
        resolved["sockets"] = []
        resolved["walkable_space"]["footprint"]["vertices_xz"] = RECTANGLE
        resolved["walkable_space"]["floor_elevation"] = 0
        resolved["walkable_space"]["safe_spawn_xyz"] = [0, 0.6, 0]
        resolved["rendered_placement_envelope"]["footprint"]["vertices_xz"] = RECTANGLE
        resolved["rendered_placement_envelope"]["bounds_xyz"] = {
            "min": [-3.1, -0.1, -2.1],
            "max": [3.1, 3.1, 2.1],
        }
        if self.version == 3:
            resolved["room_clearance"] = {
                "floor_elevation": 0,
                "ceiling_elevation": 3,
                "basis": "authored",
            }
            resolved["dynamic_resource_declarations"] = []
        else:
            resolved.pop("room_clearance", None)
            resolved.pop("dynamic_resource_declarations", None)
        self.record["reusable_requirements"]["player"]["controller_scene"] = (
            self.repo_path("player.tscn")
        )
        self.add_snapshot_dependency()

    def _main_scene(self) -> str:
        return (
            "[gd_scene load_steps=2 format=3]\n"
            f'[ext_resource type="Script" path="res://{self.res_base}/assets/room.gd" id="1"]\n'
            '[node name="Room" type="Node3D"]\nscript = ExtResource("1")\n'
        )

    def add_snapshot_dependency(self) -> None:
        snapshot = ROOT / SNAPSHOT_PATH
        self._add_dependency(SNAPSHOT_PATH, snapshot)

    def add(self, suffix: str, content: str) -> Path:
        path = self.directory / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self._add_dependency(self.repo_path(suffix), path)

    def _add_dependency(self, relative: str, path: Path) -> Path:
        self.dependencies[relative] = path
        return path

    def omit_dependency(self, path: Path) -> None:
        self.omitted.add(path.relative_to(ROOT).as_posix())

    def include_dependency(self, path: Path) -> None:
        self.omitted.discard(path.relative_to(ROOT).as_posix())

    def repo_path(self, suffix: str) -> str:
        return (self.directory / suffix).relative_to(ROOT).as_posix()

    def refresh_dependency(self, path: Path) -> None:
        relative = path.relative_to(ROOT).as_posix()
        self.dependencies[relative] = path

    def write(self, *, refresh_identity: bool = True) -> None:
        self.record["resolved_adaptation"]["dependencies"] = [
            {
                "path": relative,
                "sha256": sha256_file(path),
                "role": "runtime-test fixture",
            }
            for relative, path in sorted(self.dependencies.items())
            if relative not in self.omitted
        ]
        if refresh_identity:
            self.record["candidate_identity"] = candidate_identity_v2(self.record)
        self.bundle.write_text(json.dumps(self.record, indent=2), encoding="utf-8")

    def accept_with_passed_stage(self) -> None:
        identity = candidate_identity_v2(self.record)
        decision = self.directory / "operator_decision.json"
        decision.write_text(
            json.dumps(
                {
                    "adaptation_id": self.identifier,
                    "candidate_identity": identity,
                    "decision": "accepted",
                }
            ),
            encoding="utf-8",
        )
        self.record["status"] = "accepted_reference"
        self.record["operator_decision"] = {
            "status": "accepted",
            "decision_record_path": decision.relative_to(ROOT).as_posix(),
            "decision_sha256": sha256_file(decision),
            "candidate_fingerprint": identity,
        }
        self.record["validation"]["mechanical_status"] = "passed"
        self.record["validation"]["stages"] = [
            {
                "stage_id": "fixture-stage",
                "status": "passed",
                "candidate_fingerprint": identity,
                "artifacts": [],
            }
        ]
        self.record["candidate_identity"] = identity

    def make_pending_but_keep_old_passed_stage(self) -> None:
        self.record["status"] = "candidate_pending_review"
        self.record["operator_decision"] = {
            "status": "pending",
            "decision_record_path": None,
            "decision_sha256": None,
            "candidate_fingerprint": None,
        }


RECTANGLE = [[-3, -2], [3, -2], [3, 2], [-3, 2]]


if __name__ == "__main__":
    unittest.main()
