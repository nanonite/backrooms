"""Bounded static traversal of Godot text-resource dependencies."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path

EXTERNAL_RESOURCE = re.compile(r"\[ext_resource[^\]]*\]")
RESOURCE_PATH = re.compile(r'path="([^"]+)"')
SCRIPT_EXTENDS = re.compile(r"^\s*extends\s+([\"'])([^\"']+)\1", re.MULTILINE)
STRING_CONSTANT = re.compile(
    r"^\s*const\s+([A-Za-z_]\w*)\s*(?::[^=]+)?[:=]+\s*([\"'])([^\"']+)\2",
    re.MULTILINE,
)
LOAD_START = re.compile(r"\b(?:preload|load)\s*\(")
SHADER_INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$')


def discover_resource_graph(
    scene_paths: list[str],
    dynamic_declarations: list[dict[str, Any]],
    root: Path = ROOT,
) -> set[str]:
    pending = list(scene_paths)
    visited: set[str] = set()
    discovered: set[str] = set()
    declared = _index_dynamic_declarations(dynamic_declarations)
    used_declarations = set()
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        path = resolve_repo_path(relative, root, require_file=True)
        visited.add(relative)
        discovered.add(relative)
        references, sites = _resource_references(path, relative, root)
        pending.extend(references)
        for site in sites:
            key = _site_key(site)
            declaration = declared.get(key)
            if declaration is None:
                raise AdaptationValidationError(
                    f"Dynamic resource reference needs an explicit declaration: {site['script_path']}:{site['line']}"
                )
            used_declarations.add(key)
            pending.extend(_declared_resource_paths(declaration, site, root))
    if declared.keys() - used_declarations:
        raise AdaptationValidationError(
            "Dynamic resource declaration no longer matches a reachable source call"
        )
    return discovered


def _resource_references(
    path: Path, relative: str, root: Path
) -> tuple[list[str], list[dict[str, Any]]]:
    if path.suffix in {".tscn", ".tres"}:
        return _scene_resource_paths(path), []
    if path.suffix == ".gd":
        return _script_resource_paths(path, relative, root)
    if path.suffix in {".gdshader", ".gdshaderinc", ".glsl"}:
        return _shader_resource_paths(path, root), []
    return [], []


def _scene_resource_paths(path: Path) -> list[str]:
    references = []
    for declaration in EXTERNAL_RESOURCE.findall(path.read_text(encoding="utf-8")):
        match = RESOURCE_PATH.search(declaration)
        if match is None:
            raise AdaptationValidationError(f"External resource lacks a path: {path}")
        references.append(_godot_resource_path(match.group(1)))
    return references


def _script_resource_paths(
    path: Path, relative: str, root: Path
) -> tuple[list[str], list[dict[str, Any]]]:
    source = path.read_text(encoding="utf-8")
    constants = {name: value for name, _, value in STRING_CONSTANT.findall(source)}
    references = _extends_references(source, path)
    dynamic_sites = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        code = _without_comment(line)
        masked = _mask_strings(code)
        for call_index, call in enumerate(LOAD_START.finditer(masked)):
            argument = _call_argument(code, call.end(), relative, line_number)
            literal = _literal_argument(argument, constants)
            if literal is not None and literal.startswith("res://"):
                resource_path = _godot_resource_path(literal)
                resolved = resolve_repo_path(resource_path, root)
                if resolved.is_file():
                    references.append(resource_path)
                    continue
                dynamic_sites.append(
                    _dynamic_site(
                        relative,
                        line_number,
                        call_index,
                        argument,
                        missing_resource_path=resource_path,
                    )
                )
                continue
            if literal is None or not literal.startswith("res://"):
                dynamic_sites.append(
                    _dynamic_site(relative, line_number, call_index, argument)
                )
    return references, dynamic_sites


def _extends_references(source: str, path: Path) -> list[str]:
    references = []
    for _, reference in SCRIPT_EXTENDS.findall(source):
        if not reference.startswith("res://"):
            raise AdaptationValidationError(
                f"Script extends path must use repository res:// form: {path}"
            )
        references.append(_godot_resource_path(reference))
    return references


def _shader_resource_paths(path: Path, root: Path) -> list[str]:
    references = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.lstrip().startswith("#include"):
            continue
        match = SHADER_INCLUDE.fullmatch(line)
        if match is None:
            if line.lstrip().startswith("#include <"):
                continue
            raise AdaptationValidationError(
                f"Unsupported shader include at {path}:{line_number}; use a quoted res:// path"
            )
        reference = match.group(1)
        references.append(_shader_include_path(reference, path, root, line_number))
    return references


def _shader_include_path(
    reference: str, current: Path, root: Path, line_number: int
) -> str:
    if reference.startswith("res://"):
        return _godot_resource_path(reference)
    include = Path(reference)
    if include.is_absolute() or "\\" in reference:
        raise AdaptationValidationError(
            f"Shader include path is not repository-relative: {current}:{line_number}"
        )
    resolved = (current.parent / include).resolve(strict=False)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise AdaptationValidationError(
            f"Shader include is missing or escapes the repository: {current}:{line_number}"
        )
    return resolved.relative_to(root.resolve()).as_posix()


def _call_argument(code: str, start: int, script: str, line: int) -> str:
    end = _matching_call_end(code, start, script, line)
    argument = code[start:end].strip()
    return argument


def _matching_call_end(code: str, start: int, script: str, line: int) -> int:
    depth = 1
    quote = None
    escaped = False
    for index in range(start, len(code)):
        character = code[index]
        if escaped:
            escaped = False
        elif character == "\\" and quote:
            escaped = True
        elif quote and character == quote:
            quote = None
        elif not quote and character in {'"', "'"}:
            quote = character
        elif not quote and character == "(":
            depth += 1
        elif not quote and character == ")":
            depth -= 1
            if depth == 0:
                return index
    raise AdaptationValidationError(
        f"Multiline load/preload is unsupported at {script}:{line}; use a resolvable one-line call"
    )


def _mask_strings(line: str) -> str:
    masked = list(line)
    quote = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            masked[index] = " "
            escaped = False
        elif character == "\\" and quote:
            masked[index] = " "
            escaped = True
        elif quote and character == quote:
            masked[index] = " "
            quote = None
        elif quote:
            masked[index] = " "
        elif character in {'"', "'"}:
            masked[index] = " "
            quote = character
    return "".join(masked)


def _literal_argument(argument: str, constants: dict[str, str]) -> str | None:
    if argument in constants:
        return constants[argument]
    if len(argument) < 2 or argument[0] not in {'"', "'"}:
        return None
    if argument[-1] != argument[0] or "\\" in argument:
        return None
    return argument[1:-1]


def _dynamic_site(
    script: str,
    line: int,
    call_index: int,
    expression: str,
    *,
    missing_resource_path: str | None = None,
) -> dict[str, Any]:
    site = {
        "script_path": script,
        "line": line,
        "call_index": call_index,
        "expression": " ".join(expression.split()),
    }
    if missing_resource_path is not None:
        site["missing_resource_path"] = missing_resource_path
    return site


def _index_dynamic_declarations(
    declarations: list[dict[str, Any]],
) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    declared = {_site_key(item): item for item in declarations}
    if len(declared) != len(declarations):
        raise AdaptationValidationError("Duplicate dynamic resource declaration")
    return declared


def _declared_resource_paths(
    declaration: dict[str, Any], site: dict[str, Any], root: Path
) -> list[str]:
    paths = declaration.get("resource_paths", [])
    missing = declaration.get("optional_missing_paths", [])
    expected_missing = site.get("missing_resource_path")
    if not paths and expected_missing is None:
        raise AdaptationValidationError(
            "Dynamic reference declaration must name every possible repository resource path"
        )
    missing_paths = {item["path"]: item["reason"] for item in missing}
    if expected_missing and expected_missing not in missing_paths:
        raise AdaptationValidationError(
            f"Unresolved literal resource must be declared optional: {expected_missing}"
        )
    references = []
    for relative in paths:
        path = resolve_repo_path(relative, root, require_file=True)
        references.append(path.relative_to(root.resolve()).as_posix())
    for relative, reason in missing_paths.items():
        if not isinstance(reason, str) or not reason.strip():
            raise AdaptationValidationError(
                "Optional missing resource needs a rationale"
            )
        path = resolve_repo_path(relative, root)
        if path.exists():
            raise AdaptationValidationError(
                f"Declared optional resource now exists and must be fingerprinted: {relative}"
            )
    return references


def _site_key(site: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        site["script_path"],
        site["line"],
        site["call_index"],
        " ".join(site["expression"].split()),
    )


def _godot_resource_path(reference: str) -> str:
    if not reference.startswith("res://"):
        raise AdaptationValidationError(f"Unsupported Godot resource path: {reference}")
    return f"godot_walk/{reference.removeprefix('res://')}"


def _without_comment(line: str) -> str:
    quote = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
        elif character == "\\" and quote:
            escaped = True
        elif quote and character == quote:
            quote = None
        elif not quote and character in {'"', "'"}:
            quote = character
        elif not quote and character == "#":
            return line[:index]
    return line
