# Issue #151 Round 1

## Run The Bounded Round

From the workspace root:

```bash
python3 godot_walk/scripts/run_hunyuan_psx_round1.py
```

The runner refuses to overwrite an existing evidence directory. Each GPU capture and FPS command runs only after the project GPU/RAM headroom guard passes and has a 300-second timeout. If a run stops partway through, preserve that attempt and use a new `--out-dir` for a rerun.

## Review

From the workspace root, start the local review server:

```bash
python3 godot_walk/scripts/hunyuan_review_server.py
```

Open `http://127.0.0.1:8765/` in Firefox. The server binds only to loopback. Review the same eight room/column poses plus the frame-0152 anchor for both variants. Complete the per-view choices and reasons, both variant decisions, confidence, notes, problems, and next-round directives, then choose **Submit feedback to workspace**. A valid submission is written directly to this round folder and updates its manifest review status. **Download JSON copy** remains available as a fallback. Stop the server with Ctrl+C.

To serve another round's bundle with the same feedback schema, pass its folder explicitly:

```bash
python3 godot_walk/scripts/hunyuan_review_server.py --bundle-dir godot_walk/evidence/<round-folder>
```

Before the capture runner succeeds, `candidate_layout.svg` is the only review artifact in this directory. It is an authored layout proposal, not a rendered comparison. The contact sheet, ODiff results, and `index.html` are generated only after the GPU-guarded capture run completes.

`preserve_hunyuan` and `source_surface_cleanup` are both proposals. The review bundle does not choose or promote one.

## Walkthrough

From the workspace root, launch either proposal explicitly:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round1.tscn -- --variant=preserve_hunyuan
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round1.tscn -- --variant=source_surface_cleanup
```

Controls are the project's normal first-person controls: WASD and mouse; Escape releases the pointer.
