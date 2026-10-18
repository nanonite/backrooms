# Issue #129: WorldMirror Preflight

Date: 2026-10-18. Worktree: `track-a/hunyuan-world`.

## Decision

License, checkpoint identity, access, disk, and API preflight pass. Stop before
downloading or loading weights. Local 12 GiB inference is plausible for the
small 518 px test but is not verified, and current free VRAM/RAM leave little
headroom. Do not start #130 until an exclusive GPU/RAM window is approved. A
24 GiB cloud GPU is the planning floor for an 8-frame test; 48 GiB is the more
conservative class for 16 frames with all prediction heads. These are estimates,
not official minimums.

No model code was cloned, no checkpoint was downloaded, no GPU inference was
run, and neither Nerfstudio nor Track B was changed. The HF token was not used
or copied. The model repository is public and ungated.

## Code, Weights, And License

- Code: `Tencent-Hunyuan/HunyuanWorld-Mirror`, pinned to upstream `main`
  commit `c61300e47ce06db2f02c8e2551aae68be7ae3a0b` at preflight time.
- Weights: `tencent/HunyuanWorld-Mirror`, HF revision
  `5574b7b0d5ac9d80e8a92976222370a0d20a57a0`.
- Checkpoint: `model.safetensors`, 5,053,546,720 bytes (about 4.71 GiB),
  1,263,337,002 F32 parameters. HF LFS metadata SHA-256:
  `84d13afa4a55eb4969041e844ff9643e6fb1e131df503f962083ae97f1f35392`.
  The file is not cached locally; the digest is from HF metadata, not a local
  recomputation.
- HF metadata reports `private=false`, `gated=false`, and the license tag
  `tencent-hunyuanworld-mirror-community`. No API key or click-through gate is
  required to access the public checkpoint.
- Code `License.txt` and HF revision `License.txt` have the same SHA-256:
  `5570ef846e6e560d8a57ed5aad5a6310e04b2f3f435bc9890d2b4f1eafb5ba72`.
  Code and weight `Notice.txt` hashes also match:
  `c35e5cd10dc41c309db3bfd175b82ecca6e1cb612cfa5f8a95966575aa4ed282`.

The exact code and weight terms are the Tencent HunyuanWorld-Mirror Community
License, not an OSI license. Colombia is within its stated Territory; the
Territory excludes the EU, UK, and South Korea. The terms appear to permit
non-commercial use; they are not an NC-only grant. They restrict use and
distribution outside the Territory, require license/notice and provider
disclosures for third-party distribution, and require a separate license when
the stated 1-million-MAU threshold is exceeded. The AUP also bars using the
model or outputs to improve other AI models. This is a source review, not legal
advice. `Notice.txt` identifies gsplat as Apache-2.0; other dependency licenses
must be reviewed separately before redistributing an environment.

## Inputs And Inference API

The model accepts a tensor `views["img"]` shaped `[1, S, 3, H, W]`; the README
uses `target_size=518`. The programmatic API accepts `camera_poses` shaped
`[1, S, 4, 4]` and `camera_intrs` shaped `[1, S, 3, 3]`. The README maps
`cond_flags` in `[pose, depth, intrinsics/rays]` order; the pinned
`visual_transformer.py` implementation agrees. `WorldMirror.forward()` has a
conflicting docstring that says `[depth, rays, camera]`. Use the implementation
and README order, then verify the prior-on/off outputs in #130.

Important CLI limitation: pinned `infer.py` parses and prints `--cond_pose` and
`--cond_intrinsics`, but constructs `views` with only the image tensor and then
sets `cond_flags = [0, 0, 0]`. Those CLI flags do not actually condition the
inference. #130 must use a small custom driver around the documented model API
or a clearly recorded local patch. The upstream issue about priors was closed
after correcting the input keys to `camera_poses` and `camera_intrs`; the user
reported that COLMAP priors then changed outputs but made them worse. This makes
an explicit image-only / prior-conditioned A/B test essential.

The model can emit point maps, depth, normals, camera poses/intrinsics, and
3DGS. The official inference script also writes COLMAP-format output. This is a
direct multi-view reconstruction route, not the single-image panorama path.

## Environment And Storage

The upstream setup recommends Python 3.10, CUDA 12.4, PyTorch 2.4.0,
torchvision 0.19.0, CMake 3.14.0, and a gsplat wheel built for PyTorch 2.4/CUDA
12.4. `requirements.txt` includes NumPy <2, Open3D 0.18.0, and pycolmap 3.10.0.
`infer.py` imports `onnxruntime`, which is listed in `requirements_demo.txt` but
not the main requirements file; add it explicitly to an isolated inference
environment.

Neither existing environment matches this setup:

- `/mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env`: Python 3.10.16,
  PyTorch 2.5.0, torchvision 0.20.0, gsplat 1.4.0, Open3D 0.19.0; no pycolmap
  or onnxruntime. It occupies 9.4 GiB and should not be modified for Mirror.
- `nerfstudio`: Python 3.10.20, PyTorch 2.3.1, torchvision 0.18.1,
  gsplat 1.4.0+pt23cu121, Open3D 0.19.0, pycolmap 0.6.1; no onnxruntime.
  Leave this environment untouched.

Storage is sufficient: 3.2 TiB free on `/mnt/sharedOs` and 494 GiB free on
`/home`. Hugging Face cache is 98 GiB, but this checkpoint is not cached. A
fresh checkpoint requires about 5.05 GB, before repository and environment
dependencies.

## Resource Snapshot

- GPU: NVIDIA RTX 4070 Ti, 12,282 MiB total; 10,351 MiB free and 1,519 MiB in
  use; driver 595.99.02.
- Host: 62 GiB total, 11 GiB currently available.
- The F32 checkpoint alone represents about 4.71 GiB of weights if resident on
  the GPU, before activations, workspaces, outputs, and renderer allocations.
- Upstream publishes no minimum inference VRAM. In GitHub issue #18, a user
  reported OOM with many 518 px images on an 80 GiB A100; a maintainer
  recommended 518 px inference and `frames_chunk_size=1` for high-resolution
  cases. That does not establish the peak for this 8-16 frame test.

At this snapshot, the GPU has only about 5.4 GiB beyond the F32 weights and
host available RAM is 11 GiB. Because the number of frames, all output heads,
and model workspaces affect peak use, do not treat this as a guaranteed fit.
For #130, start with 8 registered frames at 518 px in one process, measure
peak VRAM/RAM, and add frames only if the first run is clean. If local capacity
is not available, use a cloud GPU with at least 24 GiB VRAM for the first
8-frame attempt; budget 48 GiB for a less constrained 16-frame run. These
cloud classes are conservative planning estimates, not vendor requirements.

## Sources

- [Pinned upstream README](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/blob/c61300e47ce06db2f02c8e2551aae68be7ae3a0b/README.md)
- [Pinned upstream inference script](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/blob/c61300e47ce06db2f02c8e2551aae68be7ae3a0b/infer.py)
- [Code license](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/blob/c61300e47ce06db2f02c8e2551aae68be7ae3a0b/License.txt)
- [Code notice](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/blob/c61300e47ce06db2f02c8e2551aae68be7ae3a0b/Notice.txt)
- [HF model revision](https://huggingface.co/tencent/HunyuanWorld-Mirror/tree/5574b7b0d5ac9d80e8a92976222370a0d20a57a0)
- [HF model license at that revision](https://huggingface.co/tencent/HunyuanWorld-Mirror/blob/5574b7b0d5ac9d80e8a92976222370a0d20a57a0/License.txt)
- [Upstream issue #18: image count and memory](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/issues/18)
- [Upstream issue #32: prior keys and behavior](https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror/issues/32)
