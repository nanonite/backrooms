# Local hardware preflight and reconstruction budgets — measured

**Scope:** what this workstation can actually do for the video → walkable splat
pipeline, measured rather than assumed. Every number below was produced by the
tools in this directory on the machine named in *Measured machine*. Numbers that
were **not** produced here say so explicitly.

**Rule this document follows:** a figure is only published as a budget if it was
measured here. Upstream documentation figures are quoted as claims and are never
substituted for a measurement. Where a stage could not be measured, this document
says so and gives the exact reason, rather than publishing a number that nobody
observed.

---

## How to run it

```bash
# 1. What can this machine do? (detects hardware, probes each compute API)
python3 scripts/splat_pipeline/preflight_hardware.py \
    --scene <scene_name> \
    --measurements splat_logs/measurements.json \
    --json splat_logs/preflight.json

# 2. Price a stage
python3 scripts/splat_pipeline/benchmark_reconstruction.py splatfacto \
    --data <scene_dir> --staging-dir outputs/<scene>_ns \
    --output-dir outputs/<scene>/splatfacto --log splat_logs/splatfacto.log

python3 scripts/splat_pipeline/benchmark_reconstruction.py render \
    --project godot_walk --scene res://scenes/corridor_splat.tscn \
    --resolution 1280x720 --frames 300 --warmup 60 --orbit-radius 1.0 \
    --splat godot_walk/assets/corridor_splat/corridor.ply

# 3. Price any other stage with the same sampler
python3 scripts/splat_pipeline/benchmark_reconstruction.py command \
    --label collision --input-dir <splat> --output-dir <out> -- <command...>
```

`preflight_hardware.py` exit codes: `0` all capabilities present and the measured
default budget fits · `1` usage · `2` CUDA training unusable · `3` Vulkan
unusable · `4` WebGPU unavailable · `5` measured default budget over the
headroom-adjusted VRAM.

A non-zero exit is a **refusal with a reason**, not a crash. Each failure carries
the specific next action in the report.

---

## Measured machine

| Property | Measured value | How it was read |
|---|---|---|
| GPU | NVIDIA GeForce RTX 4070 Ti | `nvidia-smi --query-gpu` |
| VRAM total | 11.99 GiB (12282 MiB) | `nvidia-smi` |
| VRAM **usable at measurement time** | 9.2 GiB | min(card free, torch free) |
| VRAM held by others | 0.5 GiB, pid 2674337 | `nvidia-smi --query-compute-apps` |
| Compute capability | 8.9 | `torch.cuda.get_device_capability` |
| Driver | 595.91.07 (CUDA 13.2 reported by driver) | `nvidia-smi` |
| Host RAM | 62.5 GiB total, 45.5 GiB available | `/proc/meminfo` |
| CPU | AMD Ryzen 9 7900X, 24 threads | `/proc/cpuinfo`, `sched_getaffinity` |
| OS / kernel | Ubuntu 24.04.5 LTS / 6.8.0-142-generic | `/etc/os-release`, `uname` |
| Disk | `/mnt/sharedOs` 3424.9 GiB free · `/home` 686.9 GiB free | `statvfs` |

> **The project's provisional figures were right.** "RTX 4070 Ti 12 GB and
> approximately 64 GB host RAM" matches what is installed (11.99 GiB VRAM,
> 62.5 GiB RAM). They remain provisional for *planning* purposes: the budget below
> is derived from the usable VRAM on a given day, which is 9.2 GiB here, not 12.

## Pinned tool versions

| Tool | Version | Query used |
|---|---|---|
| NVIDIA driver | 595.91.07 | `nvidia-smi --query-gpu=driver_version` |
| CUDA toolkit (nvcc) | 12.4.99 | `nvcc --version` (only toolkit installed) |
| nerfstudio | 1.1.5 | pinned interpreter, `importlib.metadata` |
| PyTorch | 2.3.1+cu121 | same |
| gsplat | 1.4.0 | `pip list` |
| Godot | 4.6.3.stable.official.7d41c59c4 | `Godot_v4.6.3-stable_linux.x86_64 --version` |
| Brush | brush-cli 0.3.0 | `brush --version` |
| Blender | 5.2.2 LTS | `blender --version` |
| ffmpeg | 6.1.1-3ubuntu5 | `ffmpeg -version` |
| Python (system) | 3.12.3 | `python3 --version` |
| Python (nerfstudio) | 3.10.20 | pinned interpreter |
| Vulkan loader | 1.3.275 | `libvulkan.so.1` |
| Vulkan device API | 1.4.329, Forward+ | Godot banner |

**Not installed:** `colmap`, `glomap` (`FileNotFoundError` — the front-end pose
stages cannot run here as configured).

**Pinned interpreter:** `/home/user/anaconda3/envs/nerfstudio/bin/python`. The
system `python3` has no torch, so measuring with it reports a machine that does
not exist.

---

## Compute APIs, probed independently

Each API is probed by *running work*, not by finding a library.

| API | Verdict | Evidence | Failure cause / action |
|---|---|---|---|
| **CUDA training** | **PASS** | RTX 4070 Ti cc 8.9, torch 2.3.1+cu121, one forward/backward/SGD step completed, 9.2 GiB free | — |
| **Vulkan rendering** | **PASS** | `NVIDIA GeForce RTX 4070 Ti`, api **1.4.329**, Forward+, created by the shipped renderer (Godot 4.6.3) | — |
| **WebGPU collision** | **FAIL** | no adapter on this host | `ModuleNotFoundError: No module named 'wgpu'`; `navigator.gpu is undefined`. Action: run the pinned PlayCanvas splat-transform container on a host with a working Vulkan/GL stack — <https://developer.playcanvas.com/user-manual/splat-transform/docker/> |

**Why the Vulkan probe boots the renderer rather than enumerating devices.** A
loader-level enumeration was tried first and returned
`VK_ERROR_INITIALIZATION_FAILED` (`vkCreateInstance`) on this host, while the same
loader in the same shell serves Godot a working device. Probing the renderer that
actually ships therefore answers the question that matters, and a disagreement
between the two is recorded rather than resolved by assuming the convenient one.

**wgpu cannot get an adapter here at all.** Brush (`brush-cli 0.3.0`, a
Rust + wgpu + cubeCL trainer) fails before touching any data:

```
No possible adapter available for backend. Falling back to first available.:
NotFound { active_backends: Backends(0x0), requested_backends: Backends(VULKAN),
          supported_backends: Backends(VULKAN | GL) }
```

`active_backends: Backends(0x0)` means no adapter was enumerated. Reproduced with
`VK_ICD_FILENAMES=`, `VK_DRIVER_FILES=` and `WGPU_BACKEND_TYPE=vulkan` set, with
no change. **Consequence:** any wgpu-based tool — Brush, and a locally-run
splat-transform — has no measured support on this host, even though the Vulkan
device itself exists. This is a distinct fact from "no GPU" and must not be
collapsed into it.

---

## Measured results

All rows measured on the machine above. `stage VRAM` is peak *total* minus the
reading taken immediately before the stage started, sampled at 1 Hz.

| Stage | Asset / settings | Exit | Elapsed | Stage VRAM | Stage RAM | Disk written | Splats | FPS |
|---|---|---|---|---|---|---|---|---|
| render | `corridor_prev.ply`, Godot Vulkan, 1280x720, orbiting, 300 frames | 0 | 6.9 s | 0.22 GiB | — | 0 | 52,034 | 60.16 |
| render | `corridor_squeeze96.ply`, same | 0 | 6.9 s | 0.35 GiB | — | 0 | 100,824 | 60.14 |
| render | `corridor.ply`, same | 0 | 7.0 s | 0.29 GiB | — | 0 | 182,569 | 60.12 |
| splatfacto | default Splatfacto, 96 frames @960x540, 30000 iters | **1** | 60.1 s | 0.26 GiB | **26.8 GiB** | 0 | — | — |
| brush_train | `brush-cli 0.3.0`, 300 iters | **101** | 0.0 s | 0.00 GiB | 0.02 GiB | 0 | — | — |

### What failed, and why

**Splatfacto — gsplat's CUDA extension does not compile.** Nerfstudio's Splatfacto
rasterises through gsplat, which JIT-builds a CUDA extension on first import. That
build fails:

```
/home/user/anaconda3/envs/nerfstudio/lib/python3.10/site-packages/torch/include/ATen/core/boxing/impl/boxing.h:42:103:
error: expected primary-expression before '>' token
   42 | struct has_ivalue_to<T, std::void_t<decltype(std::declval<IValue>().to<T>())>>
```

The compile line is `nvcc 12.4.99` against **torch 2.3.1** headers. The pinned
environment ships CUDA *runtime* libraries 12.1 (`nvidia-cublas-cu12 12.1.3.1`,
`nvidia-cuda-runtime-cu12 12.1.105`) but **no `nvcc`** — the only toolkit on the
box is the system CUDA 12.4. `CXXFLAGS="-std=c++17"` does not change the outcome
(retested).

**This is the single most consequential finding of this document: default
Splatfacto does not run on this machine as installed.** Two things must be true
before a training budget can be published here:

1. a CUDA toolkit whose `nvcc` agrees with torch 2.3.1 (install a 12.1 toolkit and
   point `CUDA_HOME` at it), **or** upgrade torch/gsplat to a pair that agrees with
   CUDA 12.4; **and**
2. a wgpu adapter, which does not currently exist here — relevant only if the
   rasteriser is moved off gsplat's CUDA path.

**Brush — no wgpu adapter.** See above. It fails in under a second, before
reading any frames, so it costs no meaningful time to discover — but it means the
project's other trainer cannot produce a training measurement here either.

**Collision — never ran.** No WebGPU adapter. Cost, VRAM and elapsed time for
collision generation are **unmeasured**, and must not be quoted from this document.

---

## Published budget

### Runtime budget (measured, publishable)

This is the budget that decides interactive walking, and it *is* measured.

| Property | Value | Basis |
|---|---|---|
| Asset | 182,569 Gaussians (`corridor.ply`) | measured |
| Resolution | 1280x720 | measured |
| Frame rate | **60.12 fps** | measured, 300 frames after 40-frame warmup, viewpoint orbiting |
| Stage VRAM | **0.29 GiB** | measured, 1 Hz sampling |
| Marginal cost | **~506 bytes/splat** at runtime | measured slope over 52,034 → 182,569 splats |
| Frame rate is vsync-limited | **yes** | 60.12 fps against a 60 Hz display |

**The 60 fps aspiration is met at this splat count, and the measurement says so
without overclaiming.** 60.12 fps is the display's refresh rate: it shows the
renderer keeps up, it does **not** show how much headroom remains. At 52k, 100k and
182k splats the frame rate is flat at the refresh cap and VRAM moves by ~0.1 GiB,
so **neither splat count nor VRAM is the binding constraint in this range** — the
display is. Establishing where the renderer actually becomes the limit requires
measuring above the refresh rate (uncapped, or at higher resolution); that has not
been done and is not claimed.

### Training budget (not published)

No default training run completed here, for the two reasons above. The preflight
therefore prints *"not published: no successful training run has been measured on
this host"* rather than a number. **There is no measured default VRAM or splat
budget for training on this machine, and the upstream figures below must not be
substituted for one.**

Upstream claims, quoted as claims only:

| Claim | Value | Source |
|---|---|---|
| Splatfacto (default) VRAM | ~6 GB | <https://docs.nerf.studio/nerfology/methods/splat.html> |
| Splatfacto (`big`) VRAM | ~12 GB | same |

Neither was produced on this machine. `big` at ~12 GB is also larger than the
**total** VRAM of this card, so `big` is not an option here regardless of what a
6 GB default run turns out to cost.

### Supported maximum

| Claim | Value | Basis |
|---|---|---|
| Training splat ceiling | **unknown** | needs one successful training run, plus a second at a different count to measure the slope |
| Runtime splat ceiling | **not established** | all three probes sat on the 60 Hz cap; VRAM had ~9 GiB spare at 182,569 splats and is nowhere near binding |

Publishing a runtime "maximum" from this data would be the unmeasured performance
claim this task forbids. The honest statement is: **at 182,569 splats the runtime
uses 0.29 GiB of 9.2 GiB usable VRAM and holds the display's refresh rate; the
point at which either becomes binding has not been located.**

---

## Policy the preflight enforces

- **Usable VRAM, never total.** The budget is `min(card free, torch free)` at the
  moment of the probe, minus headroom. A display server and any other job already
  hold part of the card; here 0.5 GiB was held by an unrelated process at
  measurement time, and during the run that was sampled the card was at 96% load
  with 10.4 GiB held — which would have blocked a stage that the 12 GiB total
  happily admits.
- **20% VRAM headroom / 25% RAM headroom.** Splatfacto densifies until it OOMs, so
  running exactly to the limit guarantees an intermittent failure. A stage whose
  measured peak would cross the headroom line is refused with
  `--stop-split-at` / `--downscale-factor` / free-the-GPU as the suggested action.
- **A missing compute API blocks the stage, whatever the memory says.** Collision is
  blocked here despite 9.2 GiB free, because it would not run slowly — it would not
  run.
- **A stage attempted here and failed is not reported as runnable.** The resource
  verdict answers "is there space"; only a measured attempt answers "does it work".
  A recorded failure re-issues that stage's verdict as BLOCKED with the log line
  that explains it, which is why `splatfacto` reads BLOCKED above even though the
  card has room for it.
- **Failed stages are recorded.** Both failures above are in
  `splat_logs/measurements.json` with their log tail, so a later fix has the exact
  error to address.
- **Bounded inputs, measured not assumed.** nerfstudio 1.1.5's Splatfacto has **no
  hard cap on Gaussian count** (there is no `--cap-max-num-splats`). The levers
  that exist are `--pipeline.model.stop-split-at` (default 15000) and the
  dataparser's `--downscale-factor`, and any bound must be stated as a *measured*
  splat count from a run that used it — never as a configured cap.
- **Sequential GPU stages.** One GPU stage at a time; the benchmark runs a single
  command under one sampler, so peak figures are not two jobs' peaks added
  together.
- **Non-interactive by construction.** Nerfstudio's colmap dataparser prompts
  before generating downscaled images, which turns an unattended run into
  `EOFError`. `colmap_dataset.py` stages the capture (symlinked read-only inputs,
  pre-rendered `images_2`) and the model path is passed as `--colmap-path sparse/0`
  to match this repo's COLMAP 3.10 + GLOMAP layout.

---

## Reproducing

Everything above regenerates with:

```bash
python3 scripts/splat_pipeline/preflight_hardware.py \
    --scene corridor_walk_v2 --measurements splat_logs/measurements.json \
    --json splat_logs/preflight.json
```

Machine-readable artifacts, checked in so a reviewer does not have to re-run
anything to check a number in this document:

| Artifact | Contents |
|---|---|
| `budgets/rtx4070ti/measurements.json` | every stage attempted: exact argv, interpreter, exit code, peak VRAM/RAM, elapsed, splat count, fps, and for failures the log tail |
| `budgets/rtx4070ti/preflight.json` | hardware snapshot, three capability probes, four stage verdicts, budgets |
| `budgets/rtx4070ti/splatfacto_failed.log` | full Splatfacto failure |

`splat_logs/measurements.json` and `splat_logs/preflight.json` are the working
copies the tools write (that directory is gitignored); the files under
`budgets/` are the frozen evidence for the numbers quoted above.

**Not verified here:** collision generation (no WebGPU), Blender decimation cost,
the pose stages (`colmap`/`glomap` not installed), and any training number. Those
remain open, and the tasks depending on them (#84, #88, #91, #92) should treat
this document as establishing *feasibility of the measurement*, not completion of
those stages.