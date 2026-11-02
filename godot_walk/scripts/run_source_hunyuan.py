"""Launch one guarded Hunyuan panorama attempt for a reviewed source."""

from __future__ import annotations

import argparse
import json

from source_ingestion_gpu import run_panorama_attempt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=2700)
    parser.add_argument(
        "--offload-mode", choices=("sequential_cpu",), default="sequential_cpu"
    )
    arguments = parser.parse_args()
    result = run_panorama_attempt(
        arguments.source_id,
        arguments.prompt,
        width=arguments.width,
        height=arguments.height,
        seed=arguments.seed,
        offload_mode=arguments.offload_mode,
        timeout_seconds=arguments.timeout_seconds,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"produced", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
