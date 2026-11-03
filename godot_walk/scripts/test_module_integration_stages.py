"""Tests for the #184 runner stages, using a tmp-dir fixture library."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integration_fit as fit
import library_index as li
import module_metadata_accept as accept
import module_poetics as mp
import source_ingestion_runner as runner
from deterministic_json import ROOT, DeterministicWriteError, sha256_file
from integration_preconditions import admission_sequence, current_index
from register_video_sources import append_event, register_video
from source_event_reconciliation import validate_decision_event_coverage
from source_ingestion_policy import WorkflowGateError
from video_source_library import LIBRARY, SourceLibraryError

CATALOG_DIR = ROOT / "godot_walk/room_catalog"
RECT = [[0, 0], [6, 0], [6, 4], [0, 4]]
COMPAT = "level_doorway_2m_v1"
ROOM = "r1"
MODULE = "src_room_v1"


def fake_probe(_path: Path) -> dict[str, object]:
    return {"width": 1920, "height": 1080, "fps": 24.0, "frame_count": 96, "duration_seconds": 4.0}


def scratch_module(module_id: str, scene: str, socket: dict) -> dict:
    return {
        "id": module_id, "version": 1, "scene": scene, "kind": "authored_room",
        "variant_status": "test", "sockets": [socket], "source_provenance": [],
        "visual_assets": [], "collision_provenance": "Authored.",
        "placement_footprint_xz": RECT, "collision_footprint_xz": RECT,
        "floor_elevation_m": 0.0, "ceiling_elevation_m": 3.0,
        "observed_openings": [], "obstacles": [],
    }


def socket(socket_id: str, x: float, normal_x: float) -> dict:
    return {
        "id": socket_id, "local_floor_center": [x, 0.0, 2.0], "outward_normal": [normal_x, 0.0, 0.0],
        "compatibility_type": COMPAT, "approach_clearance_m": 1.2,
    }


class Library:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "data/videos").mkdir(parents=True)
        video = root / "data/videos/room.mp4"
        video.write_bytes(b"video bytes")
        self.source_id = register_video(video, root, fake_probe)
        self.room_dir = root / LIBRARY / "sources" / self.source_id / "rooms" / ROOM
        self.room_dir.mkdir(parents=True)
        frame = root / LIBRARY / "sources" / self.source_id / "frames/seed/frame_0001.png"
        frame.parent.mkdir(parents=True)
        frame.write_bytes(b"frame")
        self.frame = frame.relative_to(root).as_posix()
        catalog_dir = root / "godot_walk/room_catalog"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        for name in ("module_poetics", "integration_proposal", "generative_map"):
            shutil.copy(CATALOG_DIR / f"{name}.schema.json", catalog_dir / f"{name}.schema.json")
        scene = f"res://source_library/sources/{self.source_id}/rooms/{ROOM}/room.tscn"
        catalog = {
            "catalog_id": "test_kit", "catalog_version": "9.9.9",
            "modules": [
                scratch_module("kit_room_v1", "res://scenes/k.tscn", socket("west", 0.0, -1.0)),
                scratch_module(MODULE, scene, socket("east", 6.0, 1.0)),
            ],
            "tested_connector_pairs": [{
                "id": "pair_ab", "status": "operator_accepted_first_pass_pair",
                "from": ["kit_room_v1", "west"], "to": [MODULE, "east"],
                "scope": "This pair only.", "evidence": [],
            }],
            "source_video_adaptations": [],
        }
        (catalog_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        snapshot = catalog_dir / "catalog_snapshots/test_kit-9.9.9.json"
        snapshot.parent.mkdir()
        snapshot.write_text(json.dumps(catalog), encoding="utf-8")
        self.snapshot = snapshot
        self.index_path = root / li.build_index(snapshot, root=root)["index"]

    def admit(self) -> None:
        append_event(self.source_id, "catalog_admission_accepted",
                     {"module_id": MODULE, "module_version": 1}, self.root)

    def events(self) -> list[dict]:
        return runner.load_source(self.source_id, self.root)[1]

    def derive(self) -> int | None:
        return runner.derive_module_metadata(self.source_id, ROOM, self.root)

    def accept(self, **overrides) -> int:
        values = dict(
            form_role="ground", rarity_tier=1, apollonian=0.4, dionysian=0.6,
            style_tags=("flat",), unique_details=(f"{self.frame}::scuffed floor",),
            surface_salience="the scuffed floor", reason="Looks right.",
        )
        values.update(overrides)
        return runner.accept_module_metadata(self.source_id, ROOM, accept.AcceptFlags(**values), self.root)

    def make_map(self, cells: list[dict], map_id: str = "gmap-1-test", **changes) -> Path:
        document = {
            "schema_version": 1, "map_id": map_id, "generator_version": "gmap-test", "seed": 1,
            "catalog_snapshot": {"path": self.snapshot.relative_to(self.root).as_posix(),
                                 "sha256": sha256_file(self.snapshot)},
            "library_index": {"path": self.index_path.relative_to(self.root).as_posix(),
                              "sha256": sha256_file(self.index_path)},
            "lattice": {"kind": "square", "unit_m": 1.0, "port_unit": COMPAT},
            "shape_stage_max": 0, "cells": cells, "edges": [],
            "distribution": {"tier_curve": "flat",
                             "repetition_budget": {"max_same_module_adjacent": 0, "max_same_primitive_run": 3}},
            "void_budget": {"min": 0, "max": 1}, "rules": [],
            "registration_accepted": False, "scale_calibrated": False,
        } | changes
        path = self.root / "maps" / f"{map_id}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def propose(self, *maps: Path) -> list[int]:
        return runner.propose_integrations(self.source_id, ROOM, list(maps), self.root)


def cell(cell_id: str, envelope: list, ports: list, role: str = "ground") -> dict:
    return {
        "cell_id": cell_id, "envelope_xz": envelope, "ceiling_range_m": [2.6, 4.8],
        "allowed_primitives": ["box"], "required_ports": ports, "role": role, "rarity_tier": 0,
    }


def port(port_id: str, pos: list, normal: list, kind: str = COMPAT) -> dict:
    return {"port_id": port_id, "pos_xz": pos, "normal": normal, "compatibility_type": kind}


@pytest.fixture
def lib(tmp_path: Path) -> Library:
    return Library(tmp_path)


@pytest.fixture
def derived(lib: Library) -> Library:
    lib.admit()
    lib.derive()
    return lib


def types(lib: Library) -> list[str]:
    return [e["event_type"] for e in lib.events()]


# --- fit math -------------------------------------------------------------------


def geometry(sockets: bool = True) -> fit.ModuleGeometry:
    ring = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    slots = [
        fit.SlotGeom("edge-0", (0.0, 0.0), (6.0, 0.0), (0.0, -1.0)),
        fit.SlotGeom("edge-2", (6.0, 4.0), (0.0, 4.0), (0.0, 1.0)),
        fit.SlotGeom("edge-3", (0.0, 4.0), (0.0, 0.0), (-1.0, 0.0)),
    ]
    found = [fit.SocketGeom("east", (6.0, 2.0), (1.0, 0.0), COMPAT)] if sockets else []
    return fit.ModuleGeometry(ring, found, slots)


def best(envelope: list, ports: list, sockets: bool = True):
    return fit.best_fit_for_cell(cell("c", envelope, ports), geometry(sockets))


def test_rotation_aligns_socket_with_cell_port() -> None:
    result = best([[0, 0], [4, 0], [4, 6], [0, 6]], [port("p", [2, 0], [0, -1])])
    assert (result.fit.yaw_deg, result.fit.translation) == (90, (0.0, 6.0))
    assert [(c.kind, c.ref) for c in result.fit.covers] == [("socket", "east")]
    assert result.fit.score == 1.0


def test_socket_must_be_within_half_a_metre_and_share_type_and_normal() -> None:
    envelope = [[0, 0], [6, 0], [6, 4], [0, 4]]
    assert best(envelope, [port("p", [6.4, 2], [1, 0])]).fit.covers[0].kind == "socket"
    assert best(envelope, [port("p", [6.6, 2], [1, 0])]).fit is None
    wrong_type = best(envelope, [port("p", [6, 2], [1, 0], "other_type")]).fit
    assert [c.kind for c in wrong_type.covers] == ["adapter"]  # only a port slot can serve it
    assert best(envelope, [port("p", [6, 2], [-1, 0])]).fit is None


def test_adapter_via_port_slot_scores_half() -> None:
    envelope = [[0, 0], [6, 0], [6, 4], [0, 4]]
    result = best(envelope, [port("p", [3, 0], [0, -1], "other_type")])
    assert (result.fit.yaw_deg, [(c.kind, c.ref) for c in result.fit.covers]) == (0, [("adapter", "edge-0")])
    assert result.fit.score == 0.5


def test_mixed_coverage_and_slack_penalty() -> None:
    mixed = best([[0, 0], [6, 0], [6, 4], [0, 4]],
                 [port("a", [6, 2], [1, 0]), port("b", [3, 0], [0, -1], "other_type")])
    assert mixed.fit.score == 0.75
    slack = best([[0, 0], [8, 0], [8, 4], [0, 4]], [port("a", [6, 2], [1, 0])])
    assert slack.fit.translation == (0.0, 0.0) and slack.fit.score == round(1 - 0.1 * 8 / 32, 9)


def test_no_fit_cases_report_why() -> None:
    too_small = best([[0, 0], [3, 0], [3, 3], [0, 3]], [port("p", [1, 0], [0, -1])])
    assert (too_small.fit, too_small.footprint_fitted) == (None, False)
    uncovered = best([[0, 0], [6, 0], [6, 4], [0, 4]], [port("p", [3, 4], [0.707107, 0.707107])])
    assert (uncovered.fit, uncovered.footprint_fitted) == (None, True)
    fits, fitted = fit.top_fits([cell("c", [[0, 0], [6, 0], [6, 4], [0, 4]], [])], geometry())
    assert (fits, fitted) == ([], True)


def test_l_shaped_envelope_requires_true_containment() -> None:
    notch = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 8], [0, 8]]
    assert fit.polygon_within([(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], [tuple(map(float, p)) for p in notch])
    assert not fit.polygon_within([(0.0, 2.0), (6.0, 2.0), (6.0, 6.0), (0.0, 6.0)], [tuple(map(float, p)) for p in notch])


# --- derive ---------------------------------------------------------------------


def test_derive_fails_closed_without_admission(lib: Library) -> None:
    with pytest.raises(WorkflowGateError, match="No admission event"):
        lib.derive()
    assert not (lib.room_dir / "module_poetics_v1.json").exists()
    assert types(lib) == ["source_registered"]


def test_derive_rejects_unknown_room_and_stale_catalog(lib: Library) -> None:
    lib.admit()
    with pytest.raises(WorkflowGateError, match="Unknown room"):
        runner.derive_module_metadata(lib.source_id, "nope", lib.root)
    with pytest.raises(WorkflowGateError, match="lowercase"):
        runner.derive_module_metadata(lib.source_id, "../x", lib.root)
    catalog = lib.root / "godot_walk/room_catalog/catalog.json"
    document = json.loads(catalog.read_text(encoding="utf-8"))
    catalog.write_text(json.dumps(document | {"catalog_version": "9.9.10"}), encoding="utf-8")
    with pytest.raises(WorkflowGateError, match="No library index for catalog version"):
        lib.derive()


def test_derive_writes_draft_logs_event_and_is_idempotent(lib: Library) -> None:
    lib.admit()
    sequence = lib.derive()
    draft = lib.room_dir / "module_poetics_v1.json"
    event = lib.events()[-1]
    assert (sequence, event["event_type"]) == (3, "module_metadata_derived")
    assert event["payload"]["draft_sha256"] == sha256_file(draft)
    assert event["payload"]["library_index_sha256"] == sha256_file(lib.index_path)
    assert event["payload"]["draft_path"] == draft.relative_to(lib.root).as_posix()
    before = draft.read_bytes()
    assert lib.derive() is None
    assert draft.read_bytes() == before and types(lib).count("module_metadata_derived") == 1


def test_derive_reuses_identical_existing_draft_and_refuses_different(lib: Library) -> None:
    lib.admit()
    mp.derive_all(lib.index_path, lib.root)
    draft = lib.room_dir / "module_poetics_v1.json"
    before = draft.read_bytes()
    assert lib.derive() == 3 and draft.read_bytes() == before
    draft.write_text("{}\n", encoding="utf-8")
    with pytest.raises(DeterministicWriteError):
        lib.derive()


def test_derive_accepts_reconciled_and_confirmed_admissions(lib: Library) -> None:
    decision = lib.room_dir / "catalog_admission_decision.json"
    decision.write_text(json.dumps({"decision": "accepted", "module_id": MODULE}), encoding="utf-8")
    cited = {"artifact_path": decision.relative_to(lib.root).as_posix(), "artifact_sha256": sha256_file(decision)}
    _, index, _ = current_index(lib.root)
    entry = next(e for e in index["modules"] if e["module_id"] == MODULE)
    bad = dict(cited, artifact_sha256="0" * 64)
    append_event(lib.source_id, "historical_decision_reconciled", {"reconciles": bad}, lib.root)
    assert admission_sequence(lib.events(), entry, lib.root) is None
    append_event(lib.source_id, "historical_decision_reconciled", {"reconciles": cited}, lib.root)
    assert admission_sequence(lib.events(), entry, lib.root) == 3


def test_confirmed_admission_may_cover_module_listed_in_another_folder(lib: Library) -> None:
    other = lib.room_dir.parent / "pair-room"
    other.mkdir()
    decision = other / "catalog_admission_decision.json"
    decision.write_text(json.dumps({"module_ids": ["x", MODULE]}), encoding="utf-8")
    append_event(lib.source_id, "operator_catalog_admission_confirmed", {
        "confirmed_artifact_path": decision.relative_to(lib.root).as_posix(),
        "confirmed_artifact_sha256": sha256_file(decision)}, lib.root)
    assert lib.derive() == 3


# --- accept ---------------------------------------------------------------------


def test_accept_requires_a_derived_event(lib: Library) -> None:
    lib.admit()
    with pytest.raises(WorkflowGateError, match="no module_metadata_derived"):
        lib.accept()


def test_accept_writes_v2_without_touching_v1(derived: Library) -> None:
    v1 = derived.room_dir / "module_poetics_v1.json"
    v1_bytes = v1.read_bytes()
    assert derived.accept() == 4
    v2 = derived.room_dir / "module_poetics_v2.json"
    record = json.loads(v2.read_text(encoding="utf-8"))
    assert v1.read_bytes() == v1_bytes
    assert record["metadata_status"] == "operator_accepted"
    assert record["poetics"]["poetics_status"] == "operator_confirmed"
    assert record["supersedes"] == {"path": v1.relative_to(derived.root).as_posix(), "sha256": sha256_file(v1)}
    assert record["eligibility"]["layout_eligible_derived"] is True
    event = derived.events()[-1]
    assert (event["event_type"], event["payload"]["sha256"]) == ("module_metadata_accepted", sha256_file(v2))
    assert event["payload"]["reason"] == "Looks right."
    with pytest.raises(WorkflowGateError, match="immutable"):
        derived.accept()


def test_accept_rejects_figure_without_unique_detail(derived: Library) -> None:
    with pytest.raises(accept.AcceptError, match="requires at least one"):
        derived.accept(form_role="figure", unique_details=())
    assert not (derived.room_dir / "module_poetics_v2.json").exists()
    derived.accept(form_role="figure")
    assert json.loads((derived.room_dir / "module_poetics_v2.json").read_text())["poetics"]["form_role"] == "figure"


@pytest.mark.parametrize("detail", [
    "godot_walk/source_library/sources/video-0000000000000000/frames/x.png::a",
    "no-separator", "FRAME::   ", "../../etc/passwd::a", "FRAME_MISSING::a",
])
def test_accept_rejects_bad_frame_paths(derived: Library, detail: str) -> None:
    detail = detail.replace("FRAME_MISSING", derived.frame + ".missing").replace("FRAME", derived.frame)
    with pytest.raises(accept.AcceptError):
        derived.accept(unique_details=(detail,))
    assert not (derived.room_dir / "module_poetics_v2.json").exists()
    assert types(derived)[-1] == "module_metadata_derived"


def test_accept_rejects_out_of_range_scores(derived: Library) -> None:
    with pytest.raises(accept.AcceptError, match="apollonian"):
        derived.accept(apollonian=1.5)
    with pytest.raises(accept.AcceptError, match="unique"):
        derived.accept(style_tags=("a", "a"))


def test_kit_accept_writes_accepted_file_and_decision_log(lib: Library) -> None:
    mp.derive_all(lib.index_path, lib.root)
    kit_dir = lib.root / mp.KIT_DRAFT_DIR
    flags = accept.AcceptFlags("ground", 0, 0.5, 0.5, ("kit",), (), "the plain walls", "Kit baseline.")
    result = accept.accept_kit(lib.index_path, "kit_room_v1", flags, mp.draft_path, lib.root)
    target = kit_dir / "kit_room_v1-v1.accepted.json"
    assert result["accepted"] == target.relative_to(lib.root).as_posix()
    assert json.loads(target.read_text())["eligibility"]["layout_eligible_derived"] is True
    log = (lib.root / accept.KIT_DECISIONS).read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])["sha256"] == sha256_file(target)
    with pytest.raises(accept.AcceptError, match="overwrite"):
        accept.accept_kit(lib.index_path, "kit_room_v1", flags, mp.draft_path, lib.root)
    with pytest.raises(accept.AcceptError, match="source video"):
        accept.accept_kit(lib.index_path, MODULE, flags, mp.draft_path, lib.root)
    assert len((lib.root / accept.KIT_DECISIONS).read_text().splitlines()) == 1


# --- propose / decide -------------------------------------------------------------


STANDARD = [
    cell("c01", RECT, [port("c01:e", [6, 2], [1, 0])]),
    cell("c02", [[0, 0], [6, 0], [6, 4], [0, 4]], [port("c02:s", [3, 0], [0, -1], "other_type")]),
    cell("c03", [[0, 0], [3, 0], [3, 3], [0, 3]], [port("c03:e", [3, 1], [1, 0])]),
    cell("cv", RECT, [port("cv:e", [6, 2], [1, 0])], role="void"),
]


def test_propose_requires_derived_event_and_current_map(derived: Library) -> None:
    fresh = Library(derived.root.parent / "other")
    fresh.admit()
    with pytest.raises(WorkflowGateError, match="no module_metadata_derived"):
        fresh.propose(fresh.make_map(STANDARD))
    stale = derived.make_map(STANDARD, library_index={"path": derived.index_path.relative_to(derived.root).as_posix(),
                                                      "sha256": "0" * 64})
    with pytest.raises(WorkflowGateError, match="stale hash"):
        derived.propose(stale)
    broken = derived.make_map(STANDARD, map_id="gmap-2-broken", seed=-1)
    with pytest.raises(WorkflowGateError, match="generative_map.schema.json"):
        derived.propose(broken)
    assert types(derived)[-1] == "module_metadata_derived"
    assert not (derived.room_dir / "integration_proposals").exists()


def test_propose_records_ranked_proposals_and_is_idempotent(derived: Library) -> None:
    path = derived.make_map(STANDARD)
    assert derived.propose(path) == [4]
    event = derived.events()[-1]
    payload = event["payload"]
    assert (event["event_type"], payload["map_id"], payload["map_sha256"]) == (
        "integration_proposal_recorded", "gmap-1-test", sha256_file(path))
    assert [item["outcome"] for item in payload["proposals"]] == ["propose", "propose"]
    records = [json.loads((derived.root / item["path"]).read_text()) for item in payload["proposals"]]
    assert [(r["cell_id"], r["confidence"]) for r in records] == [("c01", 1.0), ("c02", 0.5)]
    first = records[0]
    assert first["sockets_used"][0]["to"] == {"module_id": "kit_room_v1", "version": 1, "socket_id": "west"}
    assert first["targets"] == [{"module_id": "kit_room_v1", "version": 1}]
    assert first["adapter_required"] is None
    assert "No video connectivity inferred" in first["assumptions"]
    assert "poetics not operator-accepted" in first["assumptions"]
    adapter = records[1]
    assert adapter["adapter_required"]["port_slot_ids"] == ["edge-0"] and adapter["sockets_used"] == []
    assert any(a.startswith("Adapter work requires a new module version") for a in adapter["assumptions"])
    assert adapter["fit_result"] == {"footprint_fits": True, "ports_covered": False,
                                     "notes": "mechanical fit score, not a visual judgement"}
    assert first["evidence"] == [
        derived.events()[2]["payload"]["draft_path"], path.relative_to(derived.root).as_posix(),
        li.load_json(derived.index_path)["snapshot_path"]]
    assert derived.propose(path) == [] and types(derived).count("integration_proposal_recorded") == 1


def test_propose_keeps_standalone_when_nothing_fits(derived: Library) -> None:
    path = derived.make_map([STANDARD[2]])
    derived.propose(path)
    proposals = derived.events()[-1]["payload"]["proposals"]
    assert [p["outcome"] for p in proposals] == ["keep_standalone"]
    record = json.loads((derived.root / proposals[0]["path"]).read_text())
    assert (record["placement"], record["fit_result"]["footprint_fits"]) == (None, False)


def test_propose_emits_at_most_five_and_respects_figure_role(derived: Library) -> None:
    cells = [cell(f"c{n:02d}", RECT, [port(f"c{n:02d}:e", [6, 2], [1, 0])],
                  role="figure" if n < 2 else "ground") for n in range(7)]
    path = derived.make_map(cells)
    derived.propose(path)
    assert len(derived.events()[-1]["payload"]["proposals"]) == 5
    derived.accept(form_role="figure")
    other = derived.make_map(cells, map_id="gmap-2-test")
    derived.propose(other)
    payload = derived.events()[-1]["payload"]
    figure_records = [json.loads((derived.root / p["path"]).read_text()) for p in payload["proposals"]]
    assert sorted(r["cell_id"] for r in figure_records) == ["c00", "c01"]
    assert all("poetics not operator-accepted" not in r["assumptions"] for r in figure_records)
    assert figure_records[0]["evidence"][0].endswith("module_poetics_v2.json")


def test_proposal_ids_are_deterministic_across_libraries(tmp_path: Path) -> None:
    ids = []
    for name in ("one", "two"):
        library = Library(tmp_path / name)
        library.admit()
        library.derive()
        library.propose(library.make_map(STANDARD))
        ids.append([Path(p["path"]).name for p in library.events()[-1]["payload"]["proposals"]])
    assert ids[0] == ids[1] and all(len(Path(i).stem) == 16 for i in ids[0])


def test_propose_refuses_to_overwrite_a_different_proposal(derived: Library) -> None:
    path = derived.make_map(STANDARD)
    derived.propose(path)
    target = derived.root / derived.events()[-1]["payload"]["proposals"][0]["path"]
    target.write_text("{}\n", encoding="utf-8")
    events_before = len(derived.events())
    other = derived.make_map(STANDARD, map_id="gmap-1-test", seed=2)
    with pytest.raises(DeterministicWriteError):
        derived.propose(other)
    assert len(derived.events()) == events_before


def test_decide_needs_a_recorded_proposal_with_matching_hash(derived: Library) -> None:
    derived.propose(derived.make_map(STANDARD))
    recorded = derived.events()[-1]["payload"]["proposals"]
    stray = derived.room_dir / "integration_proposals/stray.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("{}\n", encoding="utf-8")
    with pytest.raises(WorkflowGateError, match="not cited"):
        runner.decide_integration(derived.source_id, stray, "reject", "no", derived.root)
    proposal = derived.root / recorded[0]["path"]
    with pytest.raises(WorkflowGateError, match="reason"):
        runner.decide_integration(derived.source_id, proposal, "reject", " ", derived.root)
    assert runner.decide_integration(derived.source_id, proposal, "accept", "Good fit.", derived.root) == 5
    event = derived.events()[-1]
    assert event["event_type"] == "integration_proposal_decided"
    assert (event["payload"]["choice"], event["payload"]["recorded_event_sequence"]) == ("accept", 4)
    runner.decide_integration(derived.source_id, proposal, "reject", "Changed my mind.", derived.root)
    assert derived.events()[-1]["payload"]["supersedes_sequence"] == 5
    proposal.write_text(proposal.read_text() + " ", encoding="utf-8")
    with pytest.raises(WorkflowGateError, match="not cited"):
        runner.decide_integration(derived.source_id, proposal, "reject", "x", derived.root)


def test_decide_cannot_accept_keep_standalone(derived: Library) -> None:
    derived.propose(derived.make_map([STANDARD[2]]))
    proposal = derived.root / derived.events()[-1]["payload"]["proposals"][0]["path"]
    with pytest.raises(WorkflowGateError, match="Only a propose"):
        runner.decide_integration(derived.source_id, proposal, "accept", "x", derived.root)
    runner.decide_integration(derived.source_id, proposal, "keep_standalone", "Agreed.", derived.root)


# --- validator and status ---------------------------------------------------------


def test_validator_passes_when_cited_and_flags_uncited_artifacts(derived: Library) -> None:
    derived.accept()
    derived.propose(derived.make_map(STANDARD))
    validate_decision_event_coverage(derived.root)
    room = derived.root / LIBRARY / "sources" / derived.source_id / "rooms" / "r2"
    room.mkdir()
    shutil.copy(derived.room_dir / "module_poetics_v2.json", room / "module_poetics_v2.json")
    stray = room / "integration_proposals/gmap-9-x/abc.json"
    stray.parent.mkdir(parents=True)
    stray.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SourceLibraryError) as raised:
        validate_decision_event_coverage(derived.root)
    message = str(raised.value)
    assert "no module_metadata_accepted event cites" in message and "r2/module_poetics_v2.json" in message
    assert "no integration_proposal_recorded event cites" in message and "abc.json" in message


def test_validator_flags_a_cited_file_whose_bytes_changed(derived: Library) -> None:
    derived.accept()
    v2 = derived.room_dir / "module_poetics_v2.json"
    v2.write_text(v2.read_text() + "\n", encoding="utf-8")
    with pytest.raises(SourceLibraryError, match="bytes changed"):
        validate_decision_event_coverage(derived.root)


def test_status_lists_stages_whose_preconditions_hold(lib: Library) -> None:
    assert runner.source_status(lib.source_id, lib.root)["next_worker_actions"] == ["review-source"]
    lib.admit()
    actions = runner.source_status(lib.source_id, lib.root)["next_worker_actions"]
    assert "derive-module-metadata --room-id r1" in actions
    lib.derive()
    actions = runner.source_status(lib.source_id, lib.root)["next_worker_actions"]
    assert "accept-module-metadata --room-id r1" in actions
    assert any(a.startswith("propose-integrations --room-id r1") for a in actions)
    lib.propose(lib.make_map(STANDARD))
    actions = runner.source_status(lib.source_id, lib.root)["next_worker_actions"]
    assert sum(a.startswith("decide-integration --proposal") for a in actions) == 2


def test_schema_enforces_accepted_record_rules(derived: Library) -> None:
    derived.accept()
    record = json.loads((derived.room_dir / "module_poetics_v2.json").read_text())
    accept.check_schema(record, derived.root)
    for change in (
        lambda r: r.pop("supersedes"),
        lambda r: r["poetics"].update(form_role="figure", unique_details=[]),
        lambda r: r["poetics"].update(rarity_tier=None),
    ):
        broken = json.loads(json.dumps(record))
        change(broken)
        with pytest.raises(accept.AcceptError):
            accept.check_schema(broken, derived.root)
