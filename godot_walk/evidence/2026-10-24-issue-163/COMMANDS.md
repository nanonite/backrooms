# Issue #163 reproduction commands

Run from the workspace root. HunyuanWorld code and weights remain in the
read-only Track A runtime checkout. Outputs are append-only under this issue's
evidence folder. Each inference stage checks GPU/RAM headroom and stops on a
resource threshold or hard timeout. Offline Hugging Face mode prevents a paid
or hosted inference path.

**Current status:** all four Panogen attempts stopped before generating a
panorama. The final 768×384 attempt stopped when free VRAM reached 1874 MiB,
below the 2048 MiB safety floor. SceneGen was not run, and its input panorama
does not exist. Results are documented in `REPORT.md` and the `worldgen/`
status/resource files. Do not retry inference without additional GPU headroom.
The authored source-textured Godot room is reviewable without Hunyuan output.

## Panogen

The input is the exact decoded frame `room_large_frame_0013.png`. The initial
1280x640 attempt exhausted available VRAM during VAE encoding and the 1024x512
attempt reached the conservative 3 GiB guard floor. The bounded final attempt
uses 768x384 with one-second resource sampling and a 2 GiB VRAM floor. The
upstream image-to-panorama default FOV is 80 degrees;
`room_large.mp4` has no measured camera intrinsics, so this is an explicit
uncalibrated assumption.

```bash
HF_HOME=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache \
HF_HUB_CACHE=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache/hub \
TRANSFORMERS_CACHE=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache/hub \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python \
  godot_walk/evidence/2026-10-24-issue-163/run_guarded_process.py \
  --cwd /mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0 \
  --timeout-seconds 2700 \
  --log "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/panogen-768-final.log" \
  --samples "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/panogen-768-final_resources.jsonl" \
  --status "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/panogen-768-final_status.json" \
  -- /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python \
  "$PWD/godot_walk/evidence/2026-10-24-issue-163/run_issue163_panogen.py" \
  --width 768 --height 384 \
  --output-dir "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/panogen-768x384-final"
```

## SceneGen

Run only after Panogen completes and its panorama is inspected. This uses the
same panorama, seed 42, indoor class, and a column foreground label as the
earlier local workflow. It does not register geometry or provide collision.

```bash
HF_HOME=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache \
HF_HUB_CACHE=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache/hub \
TRANSFORMERS_CACHE=/mnt/sharedOs/backrooms-track-a-runtime/hf-cache/hub \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python \
  godot_walk/evidence/2026-10-24-issue-163/run_guarded_process.py \
  --cwd /mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0 \
  --timeout-seconds 3600 \
  --log "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/scenegen.log" \
  --samples "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/scenegen_resources.jsonl" \
  --status "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/scenegen_status.json" \
  -- /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python \
  /mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0/demo_scenegen.py \
  --image_path "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/panogen-768x384-final/panorama.png" \
  --labels_fg1 columns --classes indoor --seed 42 \
  --output_path "$PWD/godot_walk/evidence/2026-10-24-issue-163/worldgen/scenegen" \
  --fp8_attention --fp8_gemm
```

The guard requires at least 18 GiB available RAM, 8 GiB free VRAM, and 16 GiB
free swap at startup. It samples every second and interrupts inference if
host RAM falls below 4 GiB, free VRAM below 2048 MiB, free swap below 16 GiB,
another CUDA process appears,
or the hard timeout expires. It escalates from SIGINT to SIGTERM and SIGKILL.
