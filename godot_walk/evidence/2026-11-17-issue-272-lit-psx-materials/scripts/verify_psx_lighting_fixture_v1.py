"""Read-only integrity checks for the issue-272 lit PSX material fixture.

Verifies that the four opt-in shader variants are isolated new files whose only
intended difference is UNSHADED, that fog is held constant, that the baseline and
both material paths are independently selectable, that geometry/camera/light are
shared and non-branch-dependent, that required views and false flags are present,
and that accepted, frozen and pinned files were not edited. Renders nothing,
makes no model calls, edits nothing and admits nothing to the catalog.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
FIXTURE_DIR = EVIDENCE_DIR / "fixture"
ROOT = EVIDENCE_DIR.parents[2]

FREEZE_RECORD = "godot_walk/room_catalog/contract_freeze_v4.json"
FALSE_FLAGS = ("registration_accepted", "scale_calibrated", "operator_approved")
REQUIRED_VIEWS = ("surface_survey", "sphere_close")
SHARED_SCRIPT = "psx_lighting_fixture_v1.gd"
VARIANTS = {
    "psx_solid_baseline_v1": ("solid", "baseline", "TEXTURE_DISABLED", True),
    "psx_solid_lit_v1": ("solid", "lit", "TEXTURE_DISABLED", False),
    "psx_textured_baseline_v1": ("textured", "baseline", "TEXTURE_REPEAT", True),
    "psx_textured_lit_v1": ("textured", "lit", "TEXTURE_REPEAT", False),
}
SCENES = {
    "psx_baseline_solid_v1.tscn": ("solid", "baseline"),
    "psx_lit_solid_v1.tscn": ("solid", "lit"),
    "psx_baseline_textured_v1.tscn": ("textured", "baseline"),
    "psx_lit_textured_v1.tscn": ("textured", "lit"),
}
EXPECTED_SHAPES = ["Floor", "Cuboid", "Sphere", "Cylinder", "BackWall"]
FIXTURE_RELATIVE = "godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/fixture"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_file(relative: str, root: Path = ROOT) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes repository: {relative}")
    return path


def _numbers(value: Any, count: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != count:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    return [float(item) for item in value]


def collect_errors(fixture_dir: Path = FIXTURE_DIR, root: Path = ROOT) -> list[str]:
    """Return all integrity errors; an empty list means the fixture is consistent."""
    errors: list[str] = []
    try:
        decision = load(fixture_dir / "shader_decision_v1.json")
        views = load(fixture_dir / "views_v1.json")
        supplement = load(fixture_dir / "pinned_supplement_v1.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read fixture record: {error}"]

    errors.extend(_check_decision(decision, fixture_dir, root))
    errors.extend(_check_scenes(fixture_dir))
    errors.extend(_check_script(fixture_dir, decision))
    errors.extend(_check_views(views))
    errors.extend(_check_notes(fixture_dir))
    errors.extend(_check_pinned(supplement, root))
    return errors


def _check_decision(
    decision: dict[str, Any], fixture_dir: Path, root: Path
) -> list[str]:
    errors: list[str] = []
    if decision.get("status") != "candidate_pending_review":
        errors.append("Decision status must be candidate_pending_review")

    variants = decision.get("shader_variants", {})
    if set(variants) != set(VARIANTS):
        errors.append(
            f"Expected exactly four shader variants, found {sorted(variants)}"
        )
    for name, (kind, mode, texture_define, unshaded) in VARIANTS.items():
        entry = variants.get(name, {})
        if entry.get("path_kind") != kind or entry.get("lighting_mode") != mode:
            errors.append(f"{name} has wrong path_kind or lighting_mode")
        if entry.get("unshaded_defined") is not unshaded:
            errors.append(f"{name} unshaded_defined does not match expected define")
        if entry.get("fog_disabled_defined") is not True:
            errors.append(f"{name} must keep FOG_DISABLED")
        if entry.get("texture_path") != texture_define:
            errors.append(f"{name} texture path does not match expected define")
        if entry.get("is_new_file") is not True:
            errors.append(f"{name} must be a new file")
        if not str(entry.get("derived_from", "")).endswith(".gdshader"):
            errors.append(f"{name} must name the accepted shader it derives from")
        shader_path = entry.get("path", "")
        path = Path(shader_path)
        if str(path.parent).endswith(FIXTURE_RELATIVE):
            shader_file = fixture_dir / path.name
        else:
            shader_file = repo_file(shader_path, root)
        try:
            text = shader_file.read_text(encoding="utf-8")
        except (ValueError, OSError, UnicodeDecodeError) as error:
            errors.append(f"{name}: cannot read shader: {error}")
            continue
        if ("#define UNSHADED" in text) is not unshaded:
            errors.append(
                f"{name}: actual shader UNSHADED define disagrees with record"
            )
        if "#define FOG_DISABLED" not in text:
            errors.append(f"{name}: actual shader lost FOG_DISABLED")
        if f"#define {texture_define}" not in text:
            errors.append(f"{name}: actual shader lost {texture_define}")
        if "res://vendor/ursc/common.gdshaderinc" not in text:
            errors.append(f"{name}: actual shader dropped the shared PSX include")

    fog = decision.get("fog", {})
    if fog.get("setting") != "FOG_DISABLED":
        errors.append("Fog must be recorded as FOG_DISABLED")
    if fog.get("unchanged_between_baseline_and_lit") is not True:
        errors.append("Fog must be unchanged between baseline and lit")
    if fog.get("environment_fog_enabled") is not False:
        errors.append("Environment fog must stay disabled")

    params = decision.get("material_parameters", {})
    if _numbers(params.get("solid_albedo_rgba"), 4) != [0.62, 0.66, 0.71, 1.0]:
        errors.append("Solid albedo does not match the fixture constant")
    if params.get("solid_color_authored_not_source_derived") is not True:
        errors.append("Solid colour must be declared authored, not source-derived")
    if params.get("checker_size_px") != 64 or params.get("checker_cells") != 8:
        errors.append("Checker dimensions do not match the fixture constants")
    if _numbers(params.get("checker_color_a_rgba"), 4) != [0.86, 0.83, 0.75, 1.0]:
        errors.append("Checker colour A does not match the fixture constant")
    if _numbers(params.get("checker_color_b_rgba"), 4) != [0.27, 0.32, 0.39, 1.0]:
        errors.append("Checker colour B does not match the fixture constant")
    if params.get("checker_is_generated_in_code") is not True:
        errors.append("Checker must be declared generated in code")
    if params.get("checker_is_source_derived") is not False:
        errors.append("Checker must not be claimed source-derived")

    light = decision.get("light", {})
    if light.get("key_energy") != 1.7:
        errors.append("Key light energy does not match the fixture constant")
    if light.get("ambient_energy_on") != 0.4 or light.get("ambient_energy_off") != 0.0:
        errors.append("Ambient energies do not match the fixture constants")
    if light.get("shadow_enabled") is not False:
        errors.append("Key light shadows must be disabled in this slice")
    if light.get("toggle_method") != "set_light_on(bool)":
        errors.append("Light toggle method must be recorded")
    if light.get("light_states_compared") != [False, True]:
        errors.append("Light-off/light-on states must both be recorded")

    geometry = decision.get("geometry", {})
    if geometry.get("identical_across_all_variants") is not True:
        errors.append("Geometry must be declared identical across all variants")
    if geometry.get("shapes") != EXPECTED_SHAPES:
        errors.append("Declared surfaces do not match the fixture shapes")

    comparison = decision.get("comparison", {})
    if comparison.get("surface_paths") != ["solid", "textured"]:
        errors.append("Both material paths must be selectable and recorded")
    if comparison.get("lighting_modes") != ["baseline", "lit"]:
        errors.append("Both baseline and lit modes must be selectable and recorded")
    if comparison.get("independently_selectable") is not True:
        errors.append("Paths and modes must be independently selectable")
    if comparison.get("baseline_available") is not True:
        errors.append("Baseline must remain available")
    if comparison.get("response_preclaimed") is not False:
        errors.append("The fixture must not preclaim a lighting response")

    preserved = decision.get("preserved", {})
    for key in ("accepted_room_and_frozen_files_unchanged",):
        if preserved.get(key) is not True:
            errors.append(f"Record must state {key}")
    for key in (
        "catalog_admission",
        "ledger_events_written",
        "catalog_json_edited",
        "model_calls",
        "downloads",
    ):
        if preserved.get(key) is not False:
            errors.append(f"Record must state {key} is false")
    errors.extend(_check_flags(decision, "decision"))
    return errors


def _normalize_scene(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(
            ("surface_kind", "lighting_mode", "light_on", "[node name=")
        )
    )


def _check_scenes(fixture_dir: Path) -> list[str]:
    errors: list[str] = []
    texts: list[str] = []
    for name, (kind, mode) in SCENES.items():
        path = fixture_dir / name
        if not path.is_file():
            errors.append(f"Missing scene: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        texts.append(_normalize_scene(text))
        if SHARED_SCRIPT not in text:
            errors.append(f"{name} must instantiate the one shared fixture script")
        if f'surface_kind = "{kind}"' not in text:
            errors.append(f"{name} must set surface_kind={kind}")
        if f'lighting_mode = "{mode}"' not in text:
            errors.append(f"{name} must set lighting_mode={mode}")
        if "light_on = false" not in text:
            errors.append(f"{name} must start with light_on=false")
    if texts and any(text != texts[0] for text in texts[1:]):
        errors.append("Comparison scenes differ beyond the selectable mode properties")
    return errors


def _function_body(script: str, name: str) -> str:
    match = re.search(
        rf"^func {re.escape(name)}\(.*?\).*?:\n", script, re.MULTILINE | re.DOTALL
    )
    if match is None:
        return ""
    tail = script[match.end() :]
    next_function = re.search(r"^func ", tail, re.MULTILINE)
    return tail[: next_function.start()] if next_function else tail


def _check_script(fixture_dir: Path, decision: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    path = fixture_dir / SHARED_SCRIPT
    if not path.is_file():
        return [f"Missing shared fixture script: {SHARED_SCRIPT}"]
    script = path.read_text(encoding="utf-8")

    if script.count("func set_light_on(") != 1:
        errors.append("Exactly one set_light_on toggle is required")
    if 'set_meta("fog_setting", "FOG_DISABLED_unchanged")' not in script:
        errors.append("Shared script must record fog as unchanged")
    shader_selector = _function_body(script, "_shader_path")
    for constant in (
        "SHADER_SOLID_BASELINE",
        "SHADER_SOLID_LIT",
        "SHADER_TEXTURED_BASELINE",
        "SHADER_TEXTURED_LIT",
    ):
        if constant not in shader_selector:
            errors.append(f"Shader selector must reference {constant}")
    for name in VARIANTS:
        if name not in script:
            errors.append(f"Shared script must reference {name}")
    selector_lower = shader_selector.lower()
    for mode in ("solid", "textured", "baseline", "lit"):
        if mode not in selector_lower:
            errors.append(f"Shader selector must branch on {mode}")
    for builder in (
        "_build_surfaces",
        "_add_box",
        "_add_sphere",
        "_add_cylinder",
        "_add_inspection_camera",
    ):
        body = _function_body(script, builder)
        if not body:
            errors.append(f"Shared script is missing {builder}")
        if "surface_kind" in body or "lighting_mode" in body:
            errors.append(f"{builder} must not branch on the mode")

    color_match = re.search(r"const SOLID_ALBEDO := Color\(([^)]*)\)", script)
    if color_match is None:
        errors.append("Shared script must declare SOLID_ALBEDO")
    else:
        actual = [float(value.strip()) for value in color_match.group(1).split(",")]
        expected = decision["material_parameters"]["solid_albedo_rgba"]
        if actual != [float(value) for value in expected]:
            errors.append("Script solid albedo does not match the decision record")
    for constant, expected in (
        ("CHECKER_SIZE", 64),
        ("CHECKER_CELLS", 8),
        ("KEY_LIGHT_ENERGY", 1.7),
        ("AMBIENT_ENERGY", 0.4),
    ):
        match = re.search(rf"const {constant} := ([\d.]+)", script)
        if match is None or float(match.group(1)) != expected:
            errors.append(f"Script {constant} does not match the decision record")
    return errors


def _check_views(views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = views.get("views", [])
    by_id = {view.get("id"): view for view in entries}
    for required in REQUIRED_VIEWS:
        if required not in by_id:
            errors.append(f"Required comparison view is missing: {required}")
    positions: list[tuple[float, ...]] = []
    for view in entries:
        for key in ("position", "target"):
            if _numbers(view.get(key), 3) is None:
                errors.append(f"View {view.get('id')} has an invalid {key}")
        vector = _numbers(view.get("position"), 3)
        if vector is not None:
            positions.append(tuple(vector))
    if len(set(positions)) != len(positions):
        errors.append("Comparison view positions must be distinct")
    errors.extend(_check_flags(views, "views"))
    return errors


def _check_flags(record: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    for flag in FALSE_FLAGS:
        if record.get("flags", {}).get(flag) is not False:
            errors.append(f"{label}.{flag} must be false")
    return errors


def _check_notes(fixture_dir: Path) -> list[str]:
    errors: list[str] = []
    authored = fixture_dir / "authored_data_v1.md"
    limits = fixture_dir / "limitations_v1.md"
    if not authored.is_file():
        errors.append("Authored data record is missing")
    else:
        text = authored.read_text(encoding="utf-8").lower()
        for keyword in (
            "authored",
            "uncalibrated",
            "baseline",
            "lit",
            "solid",
            "textured",
            "fog",
            "shader",
            "light",
            "geometry",
        ):
            if keyword not in text:
                errors.append(f"Authored data record does not state {keyword}")
    if not limits.is_file():
        errors.append("Limitations record is missing")
    else:
        text = limits.read_text(encoding="utf-8").lower()
        for keyword in (
            "visual",
            "candidate",
            "operator",
            "uncalibrated",
            "fog",
            "shadow",
            "vertex_lighting",
            "approval",
        ):
            if keyword not in text:
                errors.append(f"Limitations record does not state {keyword}")
    return errors


def _check_pinned(supplement: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    try:
        entries = list(load(repo_file(FREEZE_RECORD, root))["files"].values())
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as error:
        errors.append(f"Cannot read freeze record: {error}")
        entries = []
    for entry in entries:
        relative = entry["path"]
        try:
            path = repo_file(relative, root)
        except ValueError as error:
            errors.append(f"freeze v4: {error}")
            continue
        if not path.is_file():
            errors.append(f"freeze v4: pinned file does not resolve: {relative}")
        elif sha256_file(path) != entry["sha256"]:
            errors.append(f"freeze v4: pinned file was edited: {relative}")
    for relative, expected in supplement.get("files", {}).items():
        try:
            path = repo_file(relative, root)
        except ValueError as error:
            errors.append(f"pinned supplement: {error}")
            continue
        if not path.is_file():
            errors.append(f"pinned supplement: file does not resolve: {relative}")
        elif sha256_file(path) != expected:
            errors.append(f"pinned supplement: file was edited: {relative}")
    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("FAIL issue-272 lit PSX fixture")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASS issue-272 lit PSX fixture: four isolated new shader variants, fog "
        "unchanged, baseline + solid/textured independently selectable, shared "
        "non-branching geometry, repeatable light toggle, required views, false "
        "flags and pinned assets verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
