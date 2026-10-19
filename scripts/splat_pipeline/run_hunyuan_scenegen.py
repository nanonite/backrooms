#!/usr/bin/env python3
"""Generate an exploratory Hunyuan indoor mesh-layer candidate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from run_hunyuan_panogen import HUNYUAN_COMMIT, read_env_token
from hunyuan_scenegen_runtime import (
    ensure_zim_weights,
    instantiate_demo,
    mesh_records,
    run_demo,
    run_mesh_only,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--labels-fg1", nargs="*", default=["columns"])
    parser.add_argument("--labels-fg2", nargs="*", default=[])
    parser.add_argument("--classes", choices=("indoor", "outdoor"), default="indoor")
    parser.add_argument("--resume-decomposition-dir", type=Path)
    parser.add_argument("--mesh-only", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fp8-attention", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fp8-gemm", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def configure_runtime(args: argparse.Namespace) -> None:
    token = None
    if not args.mesh_only:
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        token = token or read_env_token(args.env_file)
    if not args.mesh_only and not token:
        raise ValueError("Set HF_TOKEN in the environment or provide a local --env-file")
    if token:
        os.environ["HF_TOKEN"] = token
    os.environ.setdefault("HF_HOME", str(args.upstream_repo.resolve().parent / "hf-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ["PYTHONNOUSERSITE"] = "1"
    if os.environ.get("HUNYUAN_SCENE_RUNTIME_READY") == "1":
        return
    libstdcpp = Path("/usr/lib/x86_64-linux-gnu/libstdc++.so.6")
    if not libstdcpp.is_file():
        raise FileNotFoundError("System libstdc++.so.6 is required by upstream Open3D")
    os.environ["LD_PRELOAD"] = ":".join(filter(None, [str(libstdcpp), os.environ.get("LD_PRELOAD", "")]))
    os.environ["HUNYUAN_SCENE_RUNTIME_READY"] = "1"
    os.execvpe(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], os.environ)


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_manifest(args: argparse.Namespace) -> dict:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "upstream_commit": HUNYUAN_COMMIT,
        "image_path": str(args.image.resolve()),
        "image_sha256": sha256_file(args.image),
        "scene_class": args.classes,
        "foreground_layer_1_labels": args.labels_fg1,
        "foreground_layer_2_labels": args.labels_fg2,
        "seed": args.seed,
        "fp8_attention": args.fp8_attention,
        "fp8_gemm": args.fp8_gemm,
        "cache": args.cache,
        "offload_mode": "not used (mesh-only)" if args.mesh_only else "sequential; installed after FP8 module conversion",
        "zim_checkpoint_path": str(args.upstream_repo.resolve().parent / "ZIM/zim_vit_l_2092"),
        "resume_decomposition_dir": (
            str(args.resume_decomposition_dir.resolve())
            if args.resume_decomposition_dir is not None else None
        ),
        "mesh_only": args.mesh_only,
        "status": "running",
        "mesh_layers": [],
    }


def generate_layers(args: argparse.Namespace, manifest_path: Path) -> int:
    import torch

    manifest = build_manifest(args)
    save_manifest(manifest_path, manifest)
    try:
        layers = execute_generation(args, torch)
    except Exception as error:
        record_failure(manifest, manifest_path, error, torch)
        return 1
    record_success(manifest, manifest_path, layers, torch)
    return 0


def execute_generation(args: argparse.Namespace, torch) -> list[dict]:
    if not torch.cuda.is_available():
        raise RuntimeError("Hunyuan scene generation requires CUDA")
    torch.cuda.reset_peak_memory_stats()
    runtime_root = args.upstream_repo.resolve().parent
    os.chdir(runtime_root)
    if args.mesh_only:
        run_mesh_only(args)
    else:
        ensure_zim_weights(runtime_root)
        run_demo(instantiate_demo(args), args)
    torch.cuda.synchronize()
    layers = mesh_records(args.output_dir)
    if not layers:
        raise RuntimeError("Hunyuan scene generation did not write a mesh layer")
    return layers


def record_failure(manifest: dict, path: Path, error: Exception, torch) -> None:
    token = os.environ.get("HF_TOKEN", "")
    message = str(error)
    details = traceback.format_exc()
    if token:
        message = message.replace(token, "[REDACTED]")
        details = details.replace(token, "[REDACTED]")
    manifest.update({
        "status": "failed",
        "error_type": type(error).__name__,
        "error_message": message[:1000],
        "error_traceback": details[-12000:],
        "peak_cuda_memory_bytes": int(torch.cuda.max_memory_allocated()),
    })
    save_manifest(path, manifest)


def record_success(manifest: dict, path: Path, layers: list[dict], torch) -> None:
    manifest.update({"status": "complete", "mesh_layers": layers})
    manifest["peak_cuda_memory_bytes"] = int(torch.cuda.max_memory_allocated())
    save_manifest(path, manifest)


def main() -> int:
    args = parse_args()
    args.upstream_repo = args.upstream_repo.resolve()
    args.image = args.image.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.env_file is not None:
        args.env_file = args.env_file.resolve()
    if args.resume_decomposition_dir is not None:
        args.resume_decomposition_dir = args.resume_decomposition_dir.resolve()
    if args.mesh_only and args.resume_decomposition_dir is None:
        raise ValueError("--mesh-only requires --resume-decomposition-dir")
    configure_runtime(args)
    if not args.image.is_file():
        raise FileNotFoundError("panorama image is missing: %s" % args.image)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError("output directory is not empty: %s" % args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return generate_layers(args, args.output_dir / "scene_manifest.json")


if __name__ == "__main__":
    raise SystemExit(main())
