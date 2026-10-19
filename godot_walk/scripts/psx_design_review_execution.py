"""Execute Godot review steps and preserve each command's evidence log."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
SCENE = "res://scenes/corridor_psx_design_candidate.tscn"
CAPTURE = "res://scripts/capture_psx_design_review.gd"
VERIFY = "res://scripts/verify_bounded_psx.gd"
FPS = "res://scripts/measure_bounded_fps.gd"
SETTLE = 200


def resource_path(path: Path) -> str:
    """Return a Godot resource path for output contained in the project."""
    return "res://" + path.resolve().relative_to(PROJECT).as_posix()


def run_logged(name: str, command: list[str], out_dir: Path,
               expected: tuple[int, ...] = (0,)) -> dict:
    """Run a command, persist full output, and enforce its expected exit code."""
    print(f"[{name}] running")
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    log = out_dir / "logs" / f"{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr)
    record = {"name": name, "command": command, "returncode": result.returncode,
              "log": str(log.relative_to(out_dir))}
    if result.returncode not in expected:
        raise RuntimeError(f"{name} failed ({result.returncode}); see {log}")
    print(f"[{name}] exit {result.returncode}")
    return record


def godot_command(binary: str, gpu: bool) -> list[str]:
    """Build a fixed-rate Godot command with explicit render dimensions."""
    base = [binary, "--fixed-fps", "60", "--path", str(PROJECT)]
    if not gpu:
        return [*base, "--headless"]
    return [*base, "--rendering-driver", "vulkan", "--resolution", "1280x720",
            "--disable-vsync"]


def _record(manifest: dict, result: dict, out_dir: Path) -> None:
    manifest["commands"].append(result)
    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def run_verifier(binary: str, out_dir: Path, manifest: dict, name: str,
                 evidence_dir: Path, variant: str, mutation: str = "") -> None:
    args = ["--scene=" + SCENE, "--out-dir=" + resource_path(evidence_dir),
            "--variant=" + variant]
    args.append("--break=" + mutation if mutation else "--trace-state")
    command = [*godot_command(binary, False), "--script", VERIFY, "--", *args]
    result = run_logged(name, command, out_dir, (1,) if mutation else (0,))
    if mutation:
        path = evidence_dir / f"physics_candidate_broken_{mutation}.json"
        failures = json.loads(path.read_text()).get("failures", [])
        if not failures:
            raise RuntimeError(f"negative control {mutation} produced no verifier failure")
        result["expected_failure"] = failures
    _record(manifest, result, out_dir)


def run_capture(binary: str, out_dir: Path, manifest: dict, variant: str,
                repeat: int, positions: Path) -> None:
    destination = out_dir / "captures" / variant / f"repeat_{repeat}"
    args = ["--variant=" + variant, "--out-dir=" + resource_path(destination),
            "--positions-json=" + resource_path(positions), f"--settle={SETTLE}"]
    command = [*godot_command(binary, True), "--script", CAPTURE, "--", *args]
    result = run_logged(f"capture_{variant}_repeat_{repeat}", command, out_dir)
    _record(manifest, result, out_dir)


def run_fps(binary: str, out_dir: Path, manifest: dict, variant: str,
            evidence_dir: Path, capped: bool) -> None:
    label = variant if capped else variant + "_uncapped"
    command = [binary, "--path", str(PROJECT), "--rendering-driver", "vulkan",
               "--resolution", "1280x720", "--disable-vsync"]
    if capped:
        command.extend(["--max-fps", "60"])
    args = ["--scene=" + SCENE, "--out-dir=" + resource_path(evidence_dir),
            "--label=" + label, "--variant=" + variant]
    command.extend(["--script", FPS, "--", *args])
    if capped:
        command.append("--capped")
    result = run_logged("fps_" + label, command, out_dir)
    _record(manifest, result, out_dir)


def odiff_command() -> list[str]:
    """Use installed ODiff or the pinned npm binary without project changes."""
    binary = shutil.which("odiff")
    if binary:
        return [binary]
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("Install odiff-bin@4.5.0 or make npx available")
    return [npx, "--yes", "--package=odiff-bin@4.5.0", "odiff"]
