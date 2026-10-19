#!/usr/bin/env python3
"""Generate a controlled HunyuanWorld image-to-panorama candidate set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
HUNYUAN_COMMIT = "57fa9f3a79eae1079c279968cdb9d82c75fa7c86"
DEFAULT_PROMPT = (
    "Empty Backrooms corridor matching this frame: pale yellow geometric "
    "wallpaper, cream columns, off-white tiled ceiling with fluorescent panels, "
    "beige carpet, and connected open corridors. Preserve the architecture, "
    "viewpoint, and lighting; continue the unseen room consistently. No people or furniture."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--camera-metadata", type=Path, required=True)
    parser.add_argument(
        "--image",
        type=Path,
        default=REPO_ROOT / "data/track-a/hunyuan/source_frame_0141.png",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=(42, 43, 44))
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--true-cfg-scale", type=float, default=2.0)
    parser.add_argument(
        "--fp8-attention", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--fp8-gemm", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--offload-mode", choices=("model", "sequential"), default="sequential"
    )
    parser.add_argument(
        "--measured-fov-only",
        action="store_true",
        help="skip the upstream 80-degree comparison candidate",
    )
    return parser.parse_args()


def read_env_token(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if not separator or key.strip() not in {"HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"}:
            continue
        token = value.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            token = token[1:-1]
        else:
            token = token.split(" #", 1)[0].strip()
        if token and not any(character.isspace() for character in token):
            return token
    return None


def configure_runtime(args: argparse.Namespace) -> None:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    token = token or read_env_token(args.env_file)
    if not token:
        raise ValueError(
            "Set HF_TOKEN in the environment or provide a local --env-file"
        )
    os.environ["HF_TOKEN"] = token
    runtime_root = args.upstream_repo.resolve().parent
    os.environ.setdefault("HF_HOME", str(runtime_root / "hf-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ["PYTHONNOUSERSITE"] = "1"
    if os.environ.get("HUNYUAN_RUNTIME_READY") == "1":
        return
    system_libstdcpp = Path("/usr/lib/x86_64-linux-gnu/libstdc++.so.6")
    if not system_libstdcpp.is_file():
        raise FileNotFoundError(
            "System libstdc++.so.6 is required for the upstream Open3D wheel"
        )
    preload = os.environ.get("LD_PRELOAD", "")
    os.environ["LD_PRELOAD"] = ":".join(filter(None, [str(system_libstdcpp), preload]))
    os.environ["HUNYUAN_RUNTIME_READY"] = "1"
    os.execvpe(
        sys.executable,
        [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_specs(
    seeds: list[int], measured_fov: float, include_upstream_fov: bool = True
) -> list[dict]:
    measured = [
        {
            "name": "measured_fov_%.2f_seed_%d" % (measured_fov, seed),
            "seed": seed,
            "fov": measured_fov,
        }
        for seed in seeds
    ]
    if not include_upstream_fov:
        return measured
    return [
        {"name": "upstream_fov_80_seed_%d" % seeds[0], "seed": seeds[0], "fov": 80.0},
        *measured,
    ]


def validate_panorama_dimensions(width: int, height: int) -> None:
    if width < 8 or height < 8 or width != 2 * height or width % 8 or height % 8:
        raise ValueError("panorama dimensions must be 2:1 and divisible by 8")


def configure_offload(pipeline, mode: str) -> None:
    if mode == "sequential":
        pipeline.enable_sequential_cpu_offload()


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def make_contact_sheet(candidates: list[dict], output_path: Path) -> None:
    from PIL import Image, ImageDraw

    tile_width, tile_height, label_height = 960, 480, 36
    sheet = Image.new(
        "RGB", (tile_width * 2, (tile_height + label_height) * 2), "#151719"
    )
    draw = ImageDraw.Draw(sheet)
    for index, candidate in enumerate(candidates):
        if candidate["status"] != "complete":
            continue
        image = Image.open(candidate["output_path"]).convert("RGB")
        image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
        column, row = index % 2, index // 2
        x, y = column * tile_width, row * (tile_height + label_height)
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 8, y + 10), candidate["name"], fill="#ffffff")
    sheet.save(output_path, quality=92)


def load_metadata(path: Path) -> dict:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    fov = float(metadata["camera"]["approx_horizontal_fov_degrees"])
    if not 1.0 < fov < 179.0:
        raise ValueError("camera metadata has an invalid horizontal FOV")
    return metadata


def build_manifest(
    args: argparse.Namespace, source: dict, candidates: list[dict]
) -> dict:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_repository": str(args.upstream_repo.resolve()),
        "upstream_commit": HUNYUAN_COMMIT,
        "source_video": source["source_video"],
        "selected_frame": source["selected_frame"],
        "source_camera": source["camera"],
        "image_path": str(args.image.resolve()),
        "image_sha256": sha256_file(args.image),
        "prompt": args.prompt,
        "negative_prompt": args.negative_prompt,
        "theta_degrees": 0.0,
        "phi_degrees": 0.0,
        "height": args.height,
        "width": args.width,
        "steps": 50,
        "guidance_scale": 30.0,
        "true_cfg_scale": args.true_cfg_scale,
        "blend_extend": 6,
        "fp8_attention": args.fp8_attention,
        "fp8_gemm": args.fp8_gemm,
        "cache": args.cache,
        "offload_mode": args.offload_mode,
        "measured_fov_only": args.measured_fov_only,
        "candidates": candidates,
    }


def run_candidates(
    args: argparse.Namespace, source: dict, candidates: list[dict]
) -> int:
    sys.path.insert(0, str(args.upstream_repo.resolve()))
    from demo_panogen import Image2PanoramaDemo
    import torch

    manifest_path = args.output_root / "run_manifest.json"
    manifest = build_manifest(args, source, candidates)
    save_manifest(manifest_path, manifest)
    print("Loading Hunyuan image-to-panorama pipeline", flush=True)
    try:
        demo = Image2PanoramaDemo(
            argparse.Namespace(
                fp8_attention=args.fp8_attention,
                fp8_gemm=args.fp8_gemm,
                cache=args.cache,
            )
        )
        configure_offload(demo.pipe, args.offload_mode)
        demo.height = args.height
        demo.width = args.width
        demo.true_cfg_scale = args.true_cfg_scale
    except Exception as error:
        manifest["model_load_error"] = type(error).__name__
        manifest["model_load_message"] = str(error)[:1000]
        save_manifest(manifest_path, manifest)
        print(
            "Pipeline load failed (%s)" % type(error).__name__,
            file=sys.stderr,
            flush=True,
        )
        return 1
    for candidate in candidates:
        print(
            "Generating %s at FOV %.6f, seed %d"
            % (candidate["name"], candidate["fov"], candidate["seed"]),
            flush=True,
        )
        torch.cuda.reset_peak_memory_stats()
        demo.FOV = candidate["fov"]
        output_dir = args.output_root / candidate["name"]
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            demo.run(
                args.prompt,
                args.negative_prompt,
                str(args.image),
                candidate["seed"],
                str(output_dir),
            )
            output_path = output_dir / "panorama.png"
            torch.cuda.synchronize()
            candidate.update(
                {
                    "status": "complete",
                    "output_path": str(output_path.resolve()),
                    "output_sha256": sha256_file(output_path),
                    "peak_cuda_memory_bytes": int(torch.cuda.max_memory_allocated()),
                }
            )
        except Exception as error:
            candidate.update(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:1000],
                    "peak_cuda_memory_bytes": int(torch.cuda.max_memory_allocated()),
                    "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                }
            )
            save_manifest(manifest_path, manifest)
            print(
                "Candidate %s failed (%s)" % (candidate["name"], type(error).__name__),
                file=sys.stderr,
            )
            return 1
        save_manifest(manifest_path, manifest)
        print(
            "Generated %s: %s" % (candidate["name"], candidate["output_sha256"]),
            flush=True,
        )
    make_contact_sheet(candidates, args.output_root / "contact_sheet.jpg")
    return 0


def main() -> int:
    args = parse_args()
    configure_runtime(args)
    if not 1 <= len(args.seeds) <= 3 or len(set(args.seeds)) != len(args.seeds):
        raise ValueError("provide one to three distinct candidate seeds")
    validate_panorama_dimensions(args.width, args.height)
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise FileExistsError("output directory is not empty: %s" % args.output_root)
    if not args.image.is_file():
        raise FileNotFoundError("source image is missing: %s" % args.image)
    source = load_metadata(args.camera_metadata)
    measured_fov = float(source["camera"]["approx_horizontal_fov_degrees"])
    candidates = candidate_specs(
        list(args.seeds),
        measured_fov,
        include_upstream_fov=not args.measured_fov_only,
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    return run_candidates(args, source, candidates)


if __name__ == "__main__":
    raise SystemExit(main())
