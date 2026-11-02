# Attempt 004 preflight stop

The operator authorized one additional run, raising this source's limit from
three to four. Attempt 003 feedback and the authorization were appended to the
source event log. Its files and the selected seed were preserved.

The launcher stopped before starting the Hunyuan child process. The strict
start-RAM limit is 34,359,738,368 bytes (32 GiB); measured available RAM was
21,851,205,632 bytes (about 20.35 GiB), short by 12,508,532,736 bytes (about
11.65 GiB). Free swap was 89,415,864,320 bytes (about 83.28 GiB), above the
16 GiB requirement. Free VRAM was 11,481,907,200 bytes (about 10.69 GiB), above
the 8 GiB requirement. The existing active-job preflight passed. No process was
terminated.

This preflight invocation took about 0.5 seconds. No inference process ran, so
inference peak RAM/VRAM and swap growth are unavailable; swap growth was zero.
No panorama was produced. The source ledger still counts three inference
invocations (limit four) and now records the resource block as a stop. The
attempt configuration and detailed measurements are in attempt_config.json and
gpu_guard.json.
