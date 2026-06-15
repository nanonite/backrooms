# GDGS demo asset

Issue #73 uses this directory for a known-good Gaussian splat sample copied from the GDGS demo assets. Keep the sample local because the source PLY is large.

Expected local file for the smoke scene:

```text
res://assets/gdgs_demo/demo.compressed.ply
```

The scene at `res://scenes/gdgs_demo.tscn` references that path. Recreate it by copying the GDGS demo compressed PLY into this directory before running the screenshot smoke test.
