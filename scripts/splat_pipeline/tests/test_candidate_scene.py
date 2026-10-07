#!/usr/bin/env python3
"""Structural diff test for the #103 candidate scene (``corridor_candidate_psx.tscn``).

The whole fixed-view comparison rests on one claim: the candidate scene is the
#100 presentation scene with exactly two edits -- the splat resource and the
splat node's translation (which the candidate report records for GDGS
re-centring). If a third line differs, a before/after capture would be
measuring something other than the cleanup. So the test parses both scenes and
requires every line to match except those two, plus the header comment and the
splat resource path the translation belongs to.

It also checks the translation in the scene equals the report's
``node_translation_world``, so the scene cannot silently disagree with the
provenance document.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_candidate_scene.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: Repository root (this file lives at scripts/splat_pipeline/tests/).
ROOT = Path(__file__).resolve().parents[3]
SCENES = ROOT / "godot_walk" / "scenes"
BASELINE_SCENE = SCENES / "corridor_psx.tscn"
CANDIDATE_SCENE = SCENES / "corridor_candidate_psx.tscn"
REPORT = ROOT / "godot_walk" / "assets" / "corridor_splat" / "corridor_candidate.report.json"

#: The only non-comment lines allowed to differ between the two scenes.
RESOURCE_LINE = "res://assets/corridor_splat/corridor_candidate.ply"


#: Transform of the splat node: the line after the ``CorridorSplatNode`` node
#: declaration (the scene's first transform belongs to the light, so a bare
#: transform regex would read the wrong numbers).
SPLAT_TRANSFORM_RE = re.compile(
    r"\[node name=\"CorridorSplatNode\"[^\]]*\]\ntransform = Transform3D\(([^)]*)\)"
)


def lines(path: Path) -> list[str]:
    """Return the scene's lines with comments and blanks removed."""
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    ]


def test_the_candidate_scene_exists_alongside_the_baseline() -> None:
    assert BASELINE_SCENE.is_file()
    assert CANDIDATE_SCENE.is_file()


class TestStructuralDiff:
    def test_only_the_splat_resource_and_its_translation_differ(self) -> None:
        baseline = lines(BASELINE_SCENE)
        candidate = lines(CANDIDATE_SCENE)
        assert len(baseline) == len(candidate), "scene node sets diverged"
        differing = [
            (old, new)
            for old, new in zip(baseline, candidate)
            if old != new
        ]
        assert len(differing) == 2, "unexpected structural differences:\n%s" % (
            "\n".join("  - %s\n  + %s" % pair for pair in differing),
        )
        (old_resource, new_resource), (old_transform, new_transform) = differing
        assert old_resource != new_resource
        assert RESOURCE_LINE in new_resource
        assert "corridor_clean.ply" in old_resource
        assert old_transform.startswith("transform = Transform3D(")
        assert new_transform.startswith("transform = Transform3D(")
        # Rotation/scale part (first 9 numbers) must be untouched.
        old_numbers = old_transform.split("(")[1].rstrip(")").split(", ")
        new_numbers = new_transform.split("(")[1].rstrip(")").split(", ")
        assert old_numbers[:9] == new_numbers[:9]
        assert old_numbers[9:] != new_numbers[9:]

    def test_the_splat_translation_matches_the_candidate_report(self) -> None:
        report = json.loads(REPORT.read_text())
        translation = report["node_translation_world"]
        match = SPLAT_TRANSFORM_RE.search(CANDIDATE_SCENE.read_text())
        assert match is not None, "splat node transform not found in candidate scene"
        numbers = [float(part) for part in match.group(1).split(", ")]
        assert numbers[9:12] == pytest.approx(translation, abs=1e-6)

    def test_every_other_resource_is_shared_with_the_baseline_scene(self) -> None:
        def ext_resources(path: Path) -> set[str]:
            return {
                line
                for line in path.read_text().splitlines()
                if line.startswith("[ext_resource")
            }

        baseline = ext_resources(BASELINE_SCENE)
        candidate = ext_resources(CANDIDATE_SCENE)
        only_baseline = baseline - candidate
        only_candidate = candidate - baseline
        assert len(only_baseline) == 1 and len(only_candidate) == 1
        assert "corridor_clean.ply" in only_baseline.pop()
        assert RESOURCE_LINE in only_candidate.pop()
