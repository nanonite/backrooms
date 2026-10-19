"""Exercise Stage C staging and option forwarding without invoking training."""

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "train_splatfacto.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | 0o111)


def _make_image(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=1920x1080", "-frames:v", "1", str(path)],
        check=True,
    )


def test_training_stages_selected_model_and_forwards_regularization(tmp_path):
    scene = tmp_path / "scene"
    images = scene / "images"
    selected = scene / "glomap" / "0"
    images.mkdir(parents=True)
    selected.mkdir(parents=True)
    _make_image(images / "frame_0001.jpg")
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (selected / name).write_bytes(name.encode())

    output = scene / "training_output"
    capture = tmp_path / "ns_args.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "ns-train",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then
    echo "Nerfstudio 1.1.5"
    exit 0
fi
printf '%s\\n' "$@" > "$NS_ARGS_CAPTURE"
run="$NS_OUTPUT_DIR/run/splatfacto/2026-01-01"
mkdir -p "$run"
printf 'ply\\nformat ascii 1.0\\nelement vertex 1\\nend_header\\n' > "$run/splat.ply"
printf 'config: test\\n' > "$run/config.yml"
printf '{"transform": []}\\n' > "$run/dataparser_transforms.json"
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SPARSE_MODEL_DIR"] = str(selected)
    env["NS_OUTPUT_DIR"] = str(output)
    env["NS_ARGS_CAPTURE"] = str(capture)
    env["NS_USE_SCALE_REGULARIZATION"] = "true"

    result = subprocess.run(
        ["bash", str(SCRIPT), str(scene)], capture_output=True, text=True, env=env, check=False
    )

    assert result.returncode == 0, result.stderr + result.stdout
    arguments = capture.read_text().splitlines()
    regularization = arguments.index("--pipeline.model.use-scale-regularization")
    assert arguments[regularization + 1] == "True"
    viewer_exit = arguments.index("--viewer.quit-on-train-completion")
    assert arguments[viewer_exit + 1] == "True"
    assert arguments[arguments.index("--data") + 1] == str(scene / ".splatfacto_dataset")
    assert arguments[-5:] == ["colmap", "--colmap-path", "sparse/0", "--eval-mode", "all"]
    staged_model = scene / ".splatfacto_dataset" / "sparse" / "0"
    assert staged_model.resolve() == selected.resolve()
    assert (scene / ".splatfacto_dataset" / "images_2" / "frame_0001.jpg").is_file()
    assert (scene / "scene.ply").is_file()
    tool_versions = json.loads((scene / "tool_versions.json").read_text())
    assert tool_versions["sparse_model"]["path"] == "glomap/0"
