# Issue 167 — bounded Hunyuan memory diagnostic

## Finding

Attempt 003 used the pinned Hunyuan environment, 512×256 output, the shorter
prompt, and PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True. It still failed
on the first transformer call. Accelerate's existing model-offload hook called
module.to(execution_device), and the full transformer transfer requested 36 MiB
with 30.25 MiB free. The attempt peaked at 23,786,504,192 bytes of child RSS and
used 11,467,227,136 additional GPU bytes. No panorama was written.

The source launcher now constructs the same custom image-to-panorama pipeline
without calling Image2PanoramaDemo.__init__, because that constructor always
installs model-level offload. It loads/fuses the same LoRA, enables VAE tiling,
applies the existing FP8 attention and GEMM processors, then enables
Diffusers sequential CPU offload. The upstream demo's run() method and pinned
runtime remain unchanged. Cache is off; output is 512×256; one seed is used.
No pipeline-wide CUDA move is made.

The pinned environment reports PyTorch 2.5.0, Diffusers 0.34.0, Accelerate
1.6.0, and Transformers 4.51.0. A CUDA-hidden import/API check confirmed that
the custom panorama pipeline derives from Diffusers DiffusionPipeline, has VAE
tiling, and exposes the FP8 processors. The installed sequential-offload
implementation calls remove_all_hooks() before attaching CPU-offload hooks.
This is API and construction-path evidence only; FP8 weights/hooks were not
exercised with loaded model weights.

## Proposed resource policy

| Check | Limit |
| --- | ---: |
| Start: available host RAM | ≥32 GiB |
| Start: free swap | ≥16 GiB |
| Start: free VRAM | ≥8 GiB |
| During run: available host RAM | ≥8 GiB |
| During run: free swap | ≥16 GiB |
| During run: swap use growth from start | ≤1 GiB |
| During run: free VRAM | ≥2 GiB |
| Hard runtime | ≤2,700 seconds (45 minutes) |
| Sampling interval | 1 second |

The RAM start threshold provides roughly 9.85 GiB above the measured attempt
003 child RSS peak. The limits are conservative guard proposals, not measured
requirements for sequential offload. If a threshold is crossed, the process
group is stopped and the sample log, stop reason, and thresholds are recorded.
The start snapshot is taken again immediately before the child is launched.

## Verification and gate

CPU-only checks passed: 51 ingestion/guard/offload tests, Ruff, Ruff format,
Python compilation, local source-library validation (12 sources), and a
CUDA-hidden pinned-runtime API check. The direct seed remains frame 1096 /
frame_1097.png, PTS 36.533333 seconds, SHA-256
61ca4b37295a948c8aa61686c912da51c7cff6dd16aac012b5c2f02bf051b2af.

No inference or GPU capture was run. The source remains at 3/3 attempts and is
still awaiting feedback on attempt 003. The current policy gate rejects another
attempt; the diagnostic command below is for use only after the operator
authorizes a new per-source budget. It does not reset the counter:

    python3 godot_walk/scripts/run_source_hunyuan.py video-ccf9722164a0bdc8 --prompt "Abandoned industrial hall with concrete walls, high grid windows, dusty floor, steel posts and beams. Preserve a coherent single-level interior; no people, signs, or exterior landscape." --width 512 --height 256 --seed 42 --offload-mode sequential_cpu --timeout-seconds 2700

Sequential offload may reduce peak VRAM substantially, but it increases CPU
parameter movement and can raise host-memory pressure. It may still fail due
to attention activations, the custom FP8 modules, or another peak not covered by
these static/API checks. Fitting in VRAM and successful generation remain
unproven. Calibration flags remain false; no room assets or previous attempts
were changed.
