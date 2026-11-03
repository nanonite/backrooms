#!/usr/bin/env python3
"""Build one bounded review request from a direct-source extraction receipt."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from seed_review_errors import SeedReviewError
from seed_review_request_builder import build_request, write_request


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        request = build_request(args.source_id, args.extraction_manifest)
        path = write_request(request, args.output)
    except SeedReviewError as error:
        return _report_error(error)
    _report_ready(path.as_posix(), len(request["candidates"]))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--extraction-manifest", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def _report_error(error: SeedReviewError) -> int:
    print(
        json.dumps({"status": "error", **error.to_dict()}, indent=2),
        file=sys.stderr,
    )
    return 1


def _report_ready(path: str, candidate_count: int) -> None:
    print(
        json.dumps(
            {
                "status": "ready",
                "request": path,
                "candidates": candidate_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
