# GDGS demo asset

Issue #73 uses this directory for a known-good Gaussian splat sample copied from the GDGS demo assets. Keep the sample local because the source PLY is large.

Expected local file for the smoke scene:

```text
res://assets/gdgs_demo/demo.compressed.ply
```

The scene at `res://scenes/gdgs_demo.tscn` references that path. Recreate it by copying the GDGS demo compressed PLY into this directory before running the screenshot smoke test.

## Verification

Run the renderer proof from a real desktop GPU session, not headless or xvfb:

```bash
GODOT_BIN=godot4 godot_walk/tools/verify_gdgs_demo.sh
```

The verifier fails if the local demo PLY is missing, Godot falls back to OpenGL/llvmpipe, or any of the three screenshots are background-only.
