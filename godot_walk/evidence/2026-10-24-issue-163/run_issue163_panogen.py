"""Generate a bounded panorama from the direct room_large source frame."""

from __future__ import annotations

import hashlib
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-24-issue-163"
HUNYUAN = Path("/mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0")
EXPECTED_COMMIT = "57fa9f3a79eae1079c279968cdb9d82c75fa7c86"
INPUT = EVIDENCE / "room_large_frame_0013.png"
EXPECTED_INPUT_SHA256 = "b75558f58ac9ccd169e444c9978b961179ca5bc2b0d77db97acd81aa65e842ae"
PROMPT = (
    "An empty Backrooms interior based on the provided source frame: pale "
    "yellow-green geometric wallpaper, modular cream ceiling panels with "
    "fluorescent lights, a broad beige floor, square cream columns, and "
    "open wall partitions. Preserve the visible room style and perspective. "
    "Continue the same visual language into the unseen panorama. No people, "
    "furniture, signs, or windows."
)


def main() -> int:
    options = _arguments()
    output = Path(options.output_dir).resolve()
    _validate_inputs(output, options.width, options.height)
    sys.path.insert(0, str(HUNYUAN))
    from demo_panogen import Image2PanoramaDemo

    args = SimpleNamespace(fp8_attention=True, fp8_gemm=True, cache=True)
    demo = Image2PanoramaDemo(args)
    demo.height = options.height
    demo.width = options.width
    demo.FOV = 80.0
    demo.true_cfg_scale = 1.0
    output.mkdir(parents=True, exist_ok=False)
    demo.run(PROMPT, "", str(INPUT), seed=42, output_path=str(output))
    _write_manifest(output, options.width, options.height)
    print(f"PANOGEN_COMPLETE: {output / 'panorama.png'}")
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--output-dir", required=True)
    options = parser.parse_args()
    if options.width < 512 or options.height < 256:
        parser.error("panorama dimensions must be at least 512 by 256")
    if options.width % 64 or options.height % 64:
        parser.error("panorama dimensions must be multiples of 64")
    return options


def _validate_inputs(output: Path, width: int, height: int) -> None:
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)
    if _sha256(INPUT) != EXPECTED_INPUT_SHA256:
        raise ValueError("Direct source frame hash differs from the reviewed manifest")
    if not HUNYUAN.is_dir():
        raise FileNotFoundError(HUNYUAN)
    commit = subprocess.run(
        ["git", "-C", str(HUNYUAN), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise ValueError(f"Unexpected HunyuanWorld revision: {commit}")
    if output.exists():
        raise FileExistsError(f"Append-only inference output already exists: {output}")


def _write_manifest(output: Path, width: int, height: int) -> None:
    image = output / "panorama.png"
    if not image.is_file():
        raise RuntimeError("Panogen returned without writing panorama.png")
    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_repository": str(HUNYUAN),
        "upstream_commit": EXPECTED_COMMIT,
        "source_frame": INPUT.relative_to(ROOT).as_posix(),
        "source_frame_sha256": _sha256(INPUT),
        "source_type": "direct video frame; not a Gaussian or rendered image",
        "prompt": PROMPT,
        "fov_degrees": 80.0,
        "fov_source": "upstream Image2PanoramaDemo default; source camera FOV is unmeasured",
        "height": height,
        "width": width,
        "steps": 50,
        "guidance_scale": 30.0,
        "true_cfg_scale": 1.0,
        "seed": 42,
        "fp8_attention": True,
        "fp8_gemm": True,
        "cache": True,
        "output": image.relative_to(ROOT).as_posix(),
        "output_sha256": _sha256(image),
        "output_bytes": image.stat().st_size,
        "registration_accepted": False,
        "scale_calibrated": False,
    }
    target = output / "panogen_manifest.json"
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
