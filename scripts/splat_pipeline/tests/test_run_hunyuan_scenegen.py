import sys
import types
from argparse import Namespace
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from hunyuan_scenegen_runtime import (
    build_low_memory_demo,
    ensure_zim_weights,
    mesh_records,
    run_demo,
    run_mesh_only,
    run_resumed_demo,
)


def test_sequential_offload_follows_parent_fp8_setup(monkeypatch, tmp_path):
    events = []

    class Pipeline:
        def enable_sequential_cpu_offload(self):
            events.append("sequential_offload")

    class BaseDemo:
        def __init__(self, args, seed=42):
            events.append("parent_init")
            self.LayerDecomposer = types.SimpleNamespace(
                inpaint_fg_model=Pipeline(),
                inpaint_sky_model=Pipeline(),
            )

    upstream = types.ModuleType("demo_scenegen")
    upstream.HYworldDemo = BaseDemo
    monkeypatch.setitem(sys.modules, "demo_scenegen", upstream)
    demo_class = build_low_memory_demo(tmp_path)
    demo_class(Namespace(), seed=17)
    assert events == ["parent_init", "sequential_offload", "sequential_offload"]


def test_indoor_scene_does_not_load_unused_sky_pipeline(monkeypatch, tmp_path):
    events = []

    class Transformer:
        def set_attn_processor(self, processor):
            events.append("fp8_attention")

    class Pipeline:
        def __init__(self):
            self.transformer = Transformer()

        def enable_sequential_cpu_offload(self):
            events.append("foreground_sequential_offload")

    def build_pipeline(model_path, lora_path, subfolder, device=0):
        events.append(("load", subfolder))
        return Pipeline()

    layer_decomposer = types.ModuleType("hy3dworld.models.layer_decomposer")
    layer_decomposer.inpaint_utils = types.SimpleNamespace(
        build_inpaint_model=build_pipeline
    )
    package = types.ModuleType("hy3dworld")
    package.__path__ = []
    models = types.ModuleType("hy3dworld.models")
    models.__path__ = []
    monkeypatch.setitem(sys.modules, "hy3dworld", package)
    monkeypatch.setitem(sys.modules, "hy3dworld.models", models)
    monkeypatch.setitem(sys.modules, "hy3dworld.models.layer_decomposer", layer_decomposer)

    class BaseDemo:
        def __init__(self, args, seed=42):
            events.append(("parent_init", args.fp8_attention, args.fp8_gemm))
            self.LayerDecomposer = types.SimpleNamespace(
                inpaint_fg_model=layer_decomposer.inpaint_utils.build_inpaint_model(
                    "model", "lora", "HunyuanWorld-PanoInpaint-Scene"
                ),
                inpaint_sky_model=layer_decomposer.inpaint_utils.build_inpaint_model(
                    "model", "lora", "HunyuanWorld-PanoInpaint-Sky"
                ),
            )

    upstream = types.ModuleType("demo_scenegen")
    upstream.HYworldDemo = BaseDemo
    upstream.FluxFp8AttnProcessor2_0 = lambda: "fp8-processor"
    upstream.FluxFp8GeMMProcessor = lambda transformer: events.append("fp8_gemm")
    monkeypatch.setitem(sys.modules, "demo_scenegen", upstream)
    demo_class = build_low_memory_demo(tmp_path)
    demo = demo_class(
        Namespace(classes="indoor", fp8_attention=True, fp8_gemm=True), seed=17
    )
    assert events == [
        ("parent_init", False, False),
        ("load", "HunyuanWorld-PanoInpaint-Scene"),
        "fp8_attention",
        "fp8_gemm",
        "foreground_sequential_offload",
    ]
    assert demo.LayerDecomposer.inpaint_sky_model is None


def test_indoor_run_skips_unused_sky_pipeline(monkeypatch, tmp_path):
    output_dir = tmp_path / "indoor-run"
    output_dir.mkdir()
    writes = []

    class Composer:
        def _load_separate_pano_from_dir(self, path, sr):
            assert path == str(output_dir)
            assert sr is True
            return {"full_img": "pano"}, {"fg1_bbox": None}

        def generate_world(self, **kwargs):
            assert kwargs["separate_pano"] == {"full_img": "pano"}
            return [{"mesh": "indoor-mesh"}]

    class Demo:
        hy3d_world = Composer()

        def __init__(self):
            self.calls = []

        def LayerDecomposer(self, inputs, layer):
            self.calls.append((inputs, layer))

        def run(self, **kwargs):
            raise AssertionError("indoor scenes must bypass upstream sky processing")

    monkeypatch.setattr(
        "hunyuan_scenegen_runtime.write_mesh_layers",
        lambda layers, path: writes.append((layers, path)),
    )
    args = Namespace(
        resume_decomposition_dir=None,
        image=tmp_path / "panorama.png",
        output_dir=output_dir,
        labels_fg1=["columns"],
        labels_fg2=[],
        classes="indoor",
    )
    demo = Demo()
    run_demo(demo, args)
    assert [layer for _, layer in demo.calls] == [0, 1]
    assert demo.calls[0][0][0]["image_path"] == str(args.image)
    assert demo.calls[1][0][0]["image_path"] == str(output_dir / "remove_fg1_image.png")
    assert writes == [([{"mesh": "indoor-mesh"}], output_dir)]


def test_resume_reuses_fg1_outputs_and_skips_indoor_sky_pipeline(monkeypatch, tmp_path):
    source_dir = tmp_path / "prepared"
    output_dir = tmp_path / "mesh-run"
    source_dir.mkdir()
    output_dir.mkdir()
    writes = []
    for name in (
        "full_image.png",
        "full_image_sr.png",
        "fg1.json",
        "fg1_mask.png",
        "remove_fg1_image.png",
        "remove_fg1_image_sr.png",
    ):
        (source_dir / name).write_bytes(name.encode("ascii"))

    class Composer:
        def _load_separate_pano_from_dir(self, path, sr):
            assert path == str(output_dir)
            assert sr is True
            return {"full_img": "pano"}, {"fg1_bbox": None}

        def generate_world(self, **kwargs):
            assert kwargs["separate_pano"] == {"full_img": "pano"}
            return [{"mesh": "mesh-0"}]

    class Demo:
        hy3d_world = Composer()

        def __init__(self):
            self.calls = []

        def LayerDecomposer(self, inputs, layer):
            self.calls.append((inputs, layer))

    monkeypatch.setattr(
        "hunyuan_scenegen_runtime.write_mesh_layers",
        lambda layers, path: writes.append((layers, path)),
    )
    args = Namespace(
        resume_decomposition_dir=source_dir,
        output_dir=output_dir,
        labels_fg2=[],
        classes="indoor",
    )
    demo = Demo()
    run_resumed_demo(demo, args)
    assert [layer for _, layer in demo.calls] == [1]
    assert all((output_dir / name).is_file() for name in ("full_image.png", "remove_fg1_image.png"))
    assert writes == [([{"mesh": "mesh-0"}], output_dir)]


def test_mesh_only_loads_prepared_panorama_without_decomposition_models(monkeypatch, tmp_path):
    events = []
    source_dir = tmp_path / "prepared"
    output_dir = tmp_path / "mesh-only"
    source_dir.mkdir()
    output_dir.mkdir()

    class Composer:
        def __init__(self, **kwargs):
            events.append(("composer", kwargs))

        def _load_separate_pano_from_dir(self, path, sr):
            assert path == str(source_dir)
            assert sr is True
            return {"full_img": "pano"}, {"fg1_bbox": None}

        def generate_world(self, **kwargs):
            assert kwargs["separate_pano"] == {"full_img": "pano"}
            return [{"mesh": "mesh-0"}]

    package = types.ModuleType("hy3dworld")
    package.__path__ = []
    models = types.ModuleType("hy3dworld.models")
    models.__path__ = []
    world_composer = types.ModuleType("hy3dworld.models.world_composer")
    world_composer.WorldComposer = Composer
    torch = types.ModuleType("torch")
    torch.device = lambda name: name
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "hy3dworld", package)
    monkeypatch.setitem(sys.modules, "hy3dworld.models", models)
    monkeypatch.setitem(sys.modules, "hy3dworld.models.world_composer", world_composer)

    open3d = types.ModuleType("open3d")
    open3d.io = types.SimpleNamespace(write_triangle_mesh=lambda path, mesh: (
        Path(path).write_text(mesh, encoding="ascii") is not None
    ))
    monkeypatch.setitem(sys.modules, "open3d", open3d)

    args = Namespace(
        upstream_repo=tmp_path,
        resume_decomposition_dir=source_dir,
        output_dir=output_dir,
        seed=42,
    )
    run_mesh_only(args)
    assert (output_dir / "mesh_layer0.ply").read_text(encoding="ascii") == "mesh-0"
    assert events[0][0] == "composer"


def test_mesh_records_include_hash_and_size(tmp_path):
    layer = tmp_path / "mesh_layer0.ply"
    layer.write_bytes(b"ply\n")
    assert mesh_records(tmp_path) == [{
        "path": "mesh_layer0.ply",
        "bytes": 4,
        "sha256": "8036011d143b572d2d6340235f226d69dbd4d8b0da3ac1ea86157bd001ac8ac7",
    }]


def test_ensures_zim_checkpoint_files_in_external_runtime(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"

    def download(repo_id, filename, token):
        assert repo_id == "naver-iv/zim-anything-vitl"
        assert token == "hf_test-token"
        path = cache_dir / Path(filename).name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(filename.encode("utf-8"))
        return str(path)

    monkeypatch.setenv("HF_TOKEN", "hf_test-token")
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=download))
    checkpoint_dir = ensure_zim_weights(tmp_path / "runtime")
    assert (checkpoint_dir / "encoder.onnx").read_bytes() == b"zim_vit_l_2092/encoder.onnx"
    assert (checkpoint_dir / "decoder.onnx").read_bytes() == b"zim_vit_l_2092/decoder.onnx"
