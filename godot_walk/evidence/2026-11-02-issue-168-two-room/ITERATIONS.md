# Issue 168 connection-candidate capture iterations

| Run | Result | Handling |
|---|---|---|
| Initial guarded capture | GPU preflight passed, but the capture script had not created its output directory; PNG save stopped before any image was written. | Preserved as `capture_resource_run.json`. Fixed the script to create its output folder before capture. |
| v2 | Three captures completed and were visually inspected. | Preserved under `captures-v2/` with `capture_resource_run_v2.json`; not used for the final frame-time claim because this run was not frame-capped. |
| v3 | Three matched connection/room captures completed with 120 warmup frames and a 300-frame sample at `--max-fps 60 --disable-vsync`. | Current review evidence under `captures-v3/`; resource data is in `capture_resource_run_v3.json`. |

No room geometry changed between v2 and v3. The v3 difference is measurement: it adds a capped frame-time sample to the capture manifest.
