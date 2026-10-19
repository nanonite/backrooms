"""Runtime adapters for the pinned HunyuanWorld SceneGen implementation."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

def build_low_memory_demo(upstream_repo: Path):
    sys.path.insert(0, str(upstream_repo.resolve()))
    import demo_scenegen

    class SequentialOffloadDemo(demo_scenegen.HYworldDemo):
        def __init__(self, args: argparse.Namespace, seed: int = 42):
            if getattr(args, "classes", "outdoor") == "indoor":
                initialize_indoor_demo(self, super().__init__, args, seed, demo_scenegen)
            else:
                super().__init__(args, seed=seed)
            self.LayerDecomposer.inpaint_fg_model.enable_sequential_cpu_offload()
            if getattr(args, "classes", "outdoor") != "indoor":
                self.LayerDecomposer.inpaint_sky_model.enable_sequential_cpu_offload()

    return SequentialOffloadDemo


def initialize_indoor_demo(demo, parent_initializer, args, seed, upstream_module) -> None:
    from importlib import import_module
    from unittest.mock import patch

    layer_decomposer = import_module("hy3dworld.models.layer_decomposer")
    original_builder = layer_decomposer.inpaint_utils.build_inpaint_model

    def build_foreground_model(*builder_args, **builder_kwargs):
        subfolder = builder_kwargs.get("subfolder")
        if len(builder_args) > 2:
            subfolder = builder_args[2]
        if subfolder == "HunyuanWorld-PanoInpaint-Sky":
            return None
        return original_builder(*builder_args, **builder_kwargs)

    parent_args = argparse.Namespace(**vars(args))
    parent_args.fp8_attention = False
    parent_args.fp8_gemm = False
    with patch.object(layer_decomposer.inpaint_utils, "build_inpaint_model", build_foreground_model):
        parent_initializer(parent_args, seed=seed)
    demo.args = args
    demo.LayerDecomposer.inpaint_sky_model = None
    foreground_model = demo.LayerDecomposer.inpaint_fg_model
    if getattr(args, "fp8_attention", False):
        processor = upstream_module.FluxFp8AttnProcessor2_0()
        foreground_model.transformer.set_attn_processor(processor)
    if getattr(args, "fp8_gemm", False):
        upstream_module.FluxFp8GeMMProcessor(foreground_model.transformer)


def ensure_zim_weights(runtime_root: Path) -> Path:
    checkpoint_dir = runtime_root / "ZIM" / "zim_vit_l_2092"
    filenames = ("encoder.onnx", "decoder.onnx")
    missing = [name for name in filenames if not (checkpoint_dir / name).is_file()]
    if not missing:
        return checkpoint_dir
    from huggingface_hub import hf_hub_download

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for name in missing:
        cached = hf_hub_download(
            repo_id="naver-iv/zim-anything-vitl",
            filename="zim_vit_l_2092/%s" % name,
            token=os.environ["HF_TOKEN"],
        )
        shutil.copyfile(cached, checkpoint_dir / name)
    return checkpoint_dir


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mesh_records(output_dir: Path) -> list[dict]:
    return [
        {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(output_dir.glob("mesh_layer*.ply"))
    ]


def instantiate_demo(args: argparse.Namespace):
    demo_class = build_low_memory_demo(args.upstream_repo)
    demo_args = argparse.Namespace(
        fp8_attention=args.fp8_attention,
        fp8_gemm=args.fp8_gemm,
        cache=args.cache,
        classes=args.classes,
    )
    return demo_class(demo_args, seed=args.seed)


def run_demo(demo, args: argparse.Namespace) -> None:
    if args.resume_decomposition_dir is not None:
        run_resumed_demo(demo, args)
        return
    if args.classes == "indoor":
        # Indoor scenes have no sky output, but upstream still cleans up its sky models.
        run_indoor_demo(demo, args)
        return
    demo.run(
        image_path=str(args.image),
        labels_fg1=args.labels_fg1,
        labels_fg2=args.labels_fg2,
        classes=args.classes,
        output_dir=str(args.output_dir),
    )


def run_indoor_demo(demo, args: argparse.Namespace) -> None:
    fg1_infos = [{
        "image_path": str(args.image),
        "output_path": str(args.output_dir),
        "labels": args.labels_fg1,
        "class": args.classes,
    }]
    demo.LayerDecomposer(fg1_infos, layer=0)
    fg2_infos = [{
        "image_path": str(args.output_dir / "remove_fg1_image.png"),
        "output_path": str(args.output_dir),
        "labels": args.labels_fg2,
        "class": args.classes,
    }]
    demo.LayerDecomposer(fg2_infos, layer=1)
    compose_mesh_layers(demo.hy3d_world, args.output_dir)


def copy_foreground_outputs(source_dir: Path, output_dir: Path) -> None:
    reusable_files = (
        "full_image.png",
        "full_image_sr.png",
        "fg1.json",
        "fg1_mask.png",
        "remove_fg1_image.png",
        "remove_fg1_image_sr.png",
    )
    missing = [name for name in reusable_files if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("resume directory lacks required outputs: %s" % ", ".join(missing))
    for name in reusable_files:
        shutil.copy2(source_dir / name, output_dir / name)


def run_resumed_demo(demo, args: argparse.Namespace) -> None:
    copy_foreground_outputs(args.resume_decomposition_dir, args.output_dir)
    fg2_infos = [{
        "image_path": str(args.output_dir / "remove_fg1_image.png"),
        "output_path": str(args.output_dir),
        "labels": args.labels_fg2,
        "class": args.classes,
    }]
    demo.LayerDecomposer(fg2_infos, layer=1)
    if args.classes != "indoor":
        demo.LayerDecomposer(fg2_infos, layer=2)
    compose_mesh_layers(demo.hy3d_world, args.output_dir)


def compose_mesh_layers(composer, output_dir: Path) -> None:
    separate_pano, fg_bboxes = composer._load_separate_pano_from_dir(
        str(output_dir), sr=True
    )
    layered_meshes = composer.generate_world(
        separate_pano=separate_pano, fg_bboxes=fg_bboxes, world_type="mesh"
    )
    if not layered_meshes:
        raise RuntimeError("Hunyuan scene composition returned no mesh layers")
    write_mesh_layers(layered_meshes, output_dir)


def build_world_composer(args: argparse.Namespace):
    import torch

    sys.path.insert(0, str(args.upstream_repo))
    from hy3dworld.models.world_composer import WorldComposer

    return WorldComposer(
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        resolution=(3840, 1920),
        seed=args.seed,
        filter_mask=True,
        kernel_scale=2,
    )


def run_mesh_only(args: argparse.Namespace) -> None:
    composer = build_world_composer(args)
    separate_pano, fg_bboxes = composer._load_separate_pano_from_dir(
        str(args.resume_decomposition_dir), sr=True
    )
    layered_meshes = composer.generate_world(
        separate_pano=separate_pano, fg_bboxes=fg_bboxes, world_type="mesh"
    )
    if not layered_meshes:
        raise RuntimeError("Hunyuan scene composition returned no mesh layers")
    write_mesh_layers(layered_meshes, args.output_dir)


def write_mesh_layers(layered_meshes: list[dict], output_dir: Path) -> None:
    import open3d as o3d

    for layer_index, layer_info in enumerate(layered_meshes):
        output_path = output_dir / ("mesh_layer%d.ply" % layer_index)
        if not o3d.io.write_triangle_mesh(str(output_path), layer_info["mesh"]):
            raise OSError("failed to write Hunyuan mesh layer: %s" % output_path)
