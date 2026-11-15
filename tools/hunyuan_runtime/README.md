# Hunyuan Panogen runtime

Pinned inference environment for the HunyuanWorld-1.0 **image → panorama** step of
the source-ingestion track (Chainlink #251, children of #195 / #169).

`godot_walk/scripts/source_ingestion_gpu.py` refuses to start an attempt unless
three fixed paths exist and the Python environment reports four exact package
versions. Those paths live outside this repository on purpose — the runtime
checkout, the model cache and the virtualenv are machine state, not source:

| Constant          | Path                                                     |
| ----------------- | -------------------------------------------------------- |
| `HUNYUAN_RUNTIME` | `/mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0` |
| `HUNYUAN_PYTHON`  | `/mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python` |
| `HUNYUAN_CACHE`   | `/mnt/sharedOs/backrooms-track-a-runtime/hf-cache`        |

The checkout must stay at commit `57fa9f3a79eae1079c279968cdb9d82c75fa7c86`
(`HUNYUAN_COMMIT`), clean, and outside this repository.

## What is tracked here

| File           | Purpose                                                        |
| -------------- | -------------------------------------------------------------- |
| `pyproject.toml` | Declares the pinned Python dependencies and their sources.    |
| `uv.lock`      | Hash-pinned resolution for Python 3.10 on linux-x86_64.        |
| `.python-version` | `3.10` — uv-managed CPython (this nixpkgs no longer ships 3.10). |

The nix side is `devShells.hunyuan` in the repository root `flake.nix`. It adds
**only** `uv`, `git` and the shared libraries that the PyPI wheels `dlopen`
(`libGL`, `libX11`, `libstdc++`, …). It does not add a Python interpreter and it
does not change `devShells.default` or the flake inputs.

## Rebuild from scratch

```bash
# 1. Enter the Hunyuan shell from the repository root.
nix develop .#hunyuan

# The shell exports HUNYUAN_RUNTIME / HUNYUAN_CACHE / HUNYUAN_ENV and points
# UV_PROJECT_ENVIRONMENT at /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env.

# 2. Check out the pinned HunyuanWorld-1.0 (skip if it already exists).
git clone https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0.git \
    "$HUNYUAN_RUNTIME"
git -C "$HUNYUAN_RUNTIME" checkout 57fa9f3a79eae1079c279968cdb9d82c75fa7c86

# 3. Create the venv and install the locked dependencies.
cd tools/hunyuan_runtime
uv sync --locked
```

`uv sync` downloads the uv-managed CPython 3.10 build, the PyPI wheels,
`torch==2.5.0` / `torchvision==0.20.0`, and three git sources pinned by commit
(MoGe, utils3d, ZIM). The venv lands at `$HUNYUAN_ENV`, i.e. the exact path
`HUNYUAN_PYTHON` expects. Expect about 5.4 GB on disk and several GB of
downloads on a cold uv cache (a warm cache rebuilds the venv in seconds). Nothing is written
inside the repository unless `UV_PROJECT_ENVIRONMENT` is unset, in which case
`tools/hunyuan_runtime/.venv/` is used (ignored by git).

Re-running step 3 is idempotent; `uv lock --check` fails if `pyproject.toml` and
`uv.lock` drift apart.

## What the lock contains and why

The four versions that `_validate_local_runtime()` enforces:

* `torch==2.5.0` (PyPI linux wheel = the cu124 build, `torch.version.cuda` is
  `12.4`), `diffusers==0.34.0`, `accelerate==1.6.0`, `transformers==4.51.0`

`torch.__version__` prints `2.5.0+cu124` (the build tag), but the installed
distribution version — what `importlib.metadata.version("torch")` returns and
what `_validate_local_runtime()` compares — is exactly `2.5.0`. Installing from
`https://download.pytorch.org/whl/cu124` instead would record the distribution
version as `2.5.0+cu124` and fail the guard, so the lock takes torch from PyPI,
whose linux wheel for 2.5.0 is the same cu124 build.

Supporting pins taken from the upstream `docker/HunyuanWorld.yaml` for
HunyuanWorld-1.0:

* `torchvision==0.20.0` (matches torch 2.5.0), `peft==0.15.0` (diffusers uses
  PEFT to load and fuse the PanoDiT LoRAs), `huggingface-hub==0.30.2`,
  `tokenizers==0.21.1`, `safetensors==0.5.3`, `sentencepiece==0.2.0`,
  `protobuf==5.29.3`
* `numpy==1.24.1` — upstream pins 1.x; Open3D and MoGe in this stack predate
  NumPy 2.
* `opencv-python==4.11.0.86`, `pillow==11.1.0`, `scipy==1.15.2`,
  `scikit-image==0.24.0`, `matplotlib==3.10.1`, `tqdm==4.67.1`

Import-time requirements of `hy3dworld` that Panogen never calls:

`hy3dworld/__init__.py` eagerly imports the scene-generation classes
(`LayerDecomposition`, `WorldComposer`) and `hy3dworld.utils`, so
`from hy3dworld import Image2PanoramaPipelines` — the exact import in
`run_source_panogen.py` — transitively imports Open3D, trimesh, MoGe, utils3d,
BasicSR, Real-ESRGAN and ZIM even though the panorama path does not use them.
Those modules are therefore in the lock (`open3d==0.19.0`, `trimesh==4.6.1`,
`basicsr-fixed==1.4.2`, `realesrgan==0.3.0`, `onnx==1.17.0`,
`onnxruntime-gpu==1.21.1`, plus the git pins). Neither the checkout nor the
ingestion scripts were edited to avoid this; the upstream commit stays pristine.

Two of those packages (`realesrgan`, `gfpgan`) declare a dependency on PyPI
`basicsr` 1.4.2, whose `basicsr.data` package cannot import with
torchvision >= 0.17. Upstream's own instructions install `basicsr-fixed`
instead (same `basicsr` module, patched). `[tool.uv.dependency-metadata]` in
`pyproject.toml` redirects those two requirements to `basicsr-fixed==1.4.2` so
uv does not install two copies of the same module.

Deliberately **not** installed, because neither `demo_panogen.py` nor the
Panogen pipeline imports them (they belong to the scene-generation step and are
not needed to produce a panorama): `pytorch3d`, `flash-attn`, `natten`,
`sageattention`, `xformers`, `ultralytics`, `qwen-vl-utils`, `decord`,
`webdataset`, `hydra-core`, `pytorch-lightning`, `diffdist`.

## Verification

```bash
nix develop .#hunyuan

# 1. The runtime guard used by the ingestion script.
cd godot_walk/scripts
python3 -c 'import source_ingestion_gpu as s; s._validate_local_runtime(); print("runtime ok")'

# 2. GPU visibility on the host RTX 4070 Ti.
"$HUNYUAN_PYTHON" -c 'import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))'

# 3. Panogen pipeline classes import (no weights, no generation).
"$HUNYUAN_PYTHON" -c 'import sys; sys.path.insert(0, "/mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0"); from hy3dworld import Image2PanoramaPipelines, Text2PanoramaPipelines, Perspective; from hy3dworld.AngelSlim.attention_quantization_processor import FluxFp8AttnProcessor2_0; from hy3dworld.AngelSlim.gemm_quantization_processor import FluxFp8GeMMProcessor; from hy3dworld.AngelSlim.cache_helper import DeepCacheHelper; print("panogen imports ok")'
```

No Hunyuan generation attempt is run by the rebuild; the guarded attempt
belongs to the ingestion issues that depend on this one.

### Verified 2026-11-15

```
runtime ok
2.5.0+cu124 12.4 True NVIDIA GeForce RTX 4070 Ti
panogen imports ok
offload compatibility ok
```

`python3 -m pytest -q godot_walk/scripts` stays green (1495 passed, 5 skipped)
— the guard tests use a fake runner and never touch this venv.

## Remaining FLUX gate

The image-to-panorama pipeline needs two Hugging Face repositories:

* `tencent/HunyuanWorld-1` — the PanoDiT LoRAs (`HunyuanWorld-PanoDiT-Image`,
  `HunyuanWorld-PanoDiT-Text`, ~457 MB) in `$HUNYUAN_CACHE/hub`.
* `black-forest-labs/FLUX.1-Fill-dev` — the base model
  (`run_source_panogen.py` sets
  `model_path = "black-forest-labs/FLUX.1-Fill-dev"`). The repository is
  **gated**: the saved Hugging Face login returns HTTP 401 `GatedRepoError`, and
  the FLUX.1 [dev] licence must be accepted on the model page before any
  download. This rebuild must never work around that, and must never print,
  copy or move the token.

Cache state observed on 2026-11-15: `$HUNYUAN_CACHE/hub` holds
`models--tencent--HunyuanWorld-1` and, under ref `358293da…`, a complete
`models--black-forest-labs--FLUX.1-Fill-dev` snapshot — 32 GB of files
(23.6 GB transformer in three shards, 8.4 GB T5-2 text encoder, 235 MB CLIP,
320 MB VAE, tokenizer/scheduler configs), with every snapshot symlink
resolving. **Neither copy was downloaded by this task**, which issued no
Hugging Face request at all; the FLUX files appeared in the cache between
13:18 and 13:38 that day from outside this rebuild. Reproducing the rebuild
does not require them.

`_panogen_environment()` runs an attempt with `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`, so a guarded attempt only ever reads the cache. With
the weights above the offline Panogen path is complete, but this issue runs no
attempt: spending a guarded attempt belongs to the Hunyuan steps of #171–#178,
and the FLUX.1 [dev] / HunyuanWorld non-commercial terms still apply to any use.
