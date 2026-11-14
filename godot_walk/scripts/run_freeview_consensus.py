#!/usr/bin/env python3
"""Inventory and rank direct-source frames with FreeView-style consensus.

The tool never downloads weights. `weights` reports what is already local;
`inventory` computes only the existing mechanical score; `rank` additionally
reads a local DINOv2 snapshot and writes the consensus report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deterministic_json import (
    canonical_bytes,
    resolve_cli_path,
    sha256_file,
    write_deterministic,
)
from freeview_consensus import K_SWEEP, ConsensusError, evaluate_consensus
from freeview_embedding_cache import EmbeddingCache, EmbeddingCacheError
from freeview_embeddings import (
    DEFAULT_MODEL_ID,
    MODEL_CATALOG,
    DinoV2Encoder,
    EmbeddingUnavailableError,
    LocalModel,
    discover_local_weights,
    embed_into_cache,
    resolve_local_model,
    runtime_status,
)
from seed_review_candidates import SeedCandidate, prepare_candidates
from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT, read_json_object
from seed_review_sources import SourceRecord, load_source_record
from video_source_library import LIBRARY, SourceLibraryError

TOOL_VERSION = "1.1.0"
DIRECT_SOURCE_DECODE = "direct_source_video_decode_no_resize_or_edit"
REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FrameInventory:
    source: SourceRecord
    candidates: list[SeedCandidate]
    batches: list[dict[str, Any]]
    batches_by_sha256: dict[str, list[str]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _weights_parser(subparsers)
    _inventory_parser(subparsers)
    _rank_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "weights":
            return _run_weights(args)
        if args.command == "inventory":
            return _run_inventory(args)
        return _run_rank(args)
    except (
        ConsensusError,
        EmbeddingCacheError,
        EmbeddingUnavailableError,
        SeedReviewError,
        SourceLibraryError,
        FileNotFoundError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _weights_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "weights", help="report local DINOv2 weights and runtime availability"
    )
    parser.add_argument("--hf-cache", type=Path)
    parser.add_argument("--torch-checkpoints", type=Path)


def _inventory_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "inventory", help="list candidate frames and their mechanical ranks"
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--batch", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--ground-truth", action="append", default=[])


def _rank_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "rank", help="compute consensus ranks from a local DINOv2 snapshot"
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--batch", action="append", default=[])
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ground-truth", action="append", default=[])
    parser.add_argument("--k", nargs="+", type=int, default=list(K_SWEEP))
    parser.add_argument("--batch-size", type=int, default=8)


def _run_weights(args: argparse.Namespace) -> int:
    hf_cache = args.hf_cache or Path.home() / ".cache" / "huggingface" / "hub"
    torch_checkpoints = (
        args.torch_checkpoints
        or Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
    )
    local_weights = discover_local_weights(hf_cache, torch_checkpoints)
    report = {
        "status": "available" if local_weights else "missing",
        "default_model_id": DEFAULT_MODEL_ID,
        "runtime": runtime_status(),
        "model_catalog": MODEL_CATALOG,
        "local_weights": local_weights,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if local_weights else 3


def _run_inventory(args: argparse.Namespace) -> int:
    root = ROOT
    inventory = load_frame_inventory(args.source_id, args.batch, root)
    report = _base_report("inventory", inventory, list(K_SWEEP), root)
    report["consensus_status"] = "not_requested"
    report["model"] = None
    report["consensus_variants"] = None
    report["ground_truth"] = _ground_truth(args.ground_truth, report["views"], None)
    status = _write_report(resolve_cli_path(Path(args.output), root), report)
    print(json.dumps({"status": status, "output": args.output}))
    return 0


def _run_rank(args: argparse.Namespace) -> int:
    root = ROOT
    inventory = load_frame_inventory(args.source_id, args.batch, root)
    model = resolve_local_model(args.model_dir, args.model_id)
    _validate_model_catalog(model.model_id, model.embedding_dim)
    cache_path = _cache_path(root, args.source_id, model, args.cache)
    cache = EmbeddingCache.load(cache_path, model.identity())
    encoder = DinoV2Encoder(model, batch_size=args.batch_size)
    counts = embed_into_cache(
        [
            (candidate.sha256, root / candidate.path)
            for candidate in inventory.candidates
        ],
        encoder,
        cache,
    )
    cache_status = cache.save()
    embeddings = _cached_embeddings(inventory, cache)
    frame_ids = [candidate.frame_id for candidate in inventory.candidates]
    variants = evaluate_consensus(frame_ids, embeddings, args.k)
    report = _base_report("rank", inventory, args.k, root)
    report["consensus_status"] = "computed"
    report["model"] = {**model.identity().to_dict(), "device": "cpu"}
    report["embedding_cache"] = {
        "path": _repo_relative(cache_path, root),
        "status": cache_status,
        **counts,
    }
    report["consensus_variants"] = variants
    _attach_consensus(report, variants)
    report["ground_truth"] = _ground_truth(args.ground_truth, report["views"], variants)
    status = _write_report(resolve_cli_path(Path(args.output), root), report)
    print(json.dumps({"status": status, "output": args.output}))
    return 0


def load_frame_inventory(
    source_id: str, batch_names: Sequence[str], root: Path = ROOT
) -> FrameInventory:
    """Load every unique direct-source frame from the requested batches."""
    source = load_source_record(source_id, root)
    frames_root = root / LIBRARY / "sources" / source_id / "frames"
    manifests = sorted(frames_root.glob("*/extraction_manifest.json"))
    if not manifests:
        raise FileNotFoundError(f"No extracted frame batches for {source_id}")
    selected = _select_manifests(manifests, batch_names)
    candidates: dict[str, SeedCandidate] = {}
    batches: list[dict[str, Any]] = []
    batches_by_sha256: dict[str, list[str]] = {}
    for manifest_path in selected:
        batch_name = manifest_path.parent.name
        manifest = read_json_object(manifest_path, "frame extraction manifest")
        _validate_manifest(manifest, source, manifest_path)
        frames = manifest.get("frames")
        if not isinstance(frames, list) or not frames:
            raise SeedReviewError(
                "frame_manifest_stale", f"{manifest_path} has no frame list"
            )
        batches.append(
            {
                "run_id": batch_name,
                "manifest_path": manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": sha256_file(manifest_path),
                "frame_count": len(frames),
            }
        )
        for record in frames:
            candidate = _candidate_from_manifest(record, manifest, root)
            prior = candidates.get(candidate.sha256)
            if prior is not None and _frame_identity(prior) != _frame_identity(
                candidate
            ):
                raise SeedReviewError(
                    "conflicting_frame_identity",
                    f"{candidate.frame_id} and {prior.frame_id} share a hash "
                    "but disagree on identity",
                )
            candidates.setdefault(candidate.sha256, candidate)
            batches_by_sha256.setdefault(candidate.sha256, []).append(batch_name)
    ordered = sorted(candidates.values(), key=lambda item: item.index_zero_based)
    return FrameInventory(source, ordered, batches, batches_by_sha256)


def _select_manifests(
    manifests: Sequence[Path], batch_names: Sequence[str]
) -> list[Path]:
    if not batch_names:
        return list(manifests)
    available = {manifest.parent.name: manifest for manifest in manifests}
    missing = sorted(set(batch_names) - set(available))
    if missing:
        raise FileNotFoundError(f"Unknown frame batch: {', '.join(missing)}")
    return [available[name] for name in sorted(set(batch_names))]


def _validate_manifest(
    manifest: dict[str, Any], source: SourceRecord, manifest_path: Path
) -> None:
    if manifest.get("source_video_sha256") != source.video_sha256:
        raise SeedReviewError(
            "frame_manifest_stale",
            f"{manifest_path} does not belong to the registered source video",
        )
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or (
        int(metadata.get("width", 0)) != source.width
        or int(metadata.get("height", 0)) != source.height
    ):
        raise SeedReviewError(
            "frame_manifest_stale",
            f"{manifest_path} records a different native frame size",
        )


def _candidate_from_manifest(
    record: dict[str, Any],
    manifest: dict[str, Any],
    root: Path,
) -> SeedCandidate:
    path = root / record["path"]
    if sha256_file(path) != record["sha256"]:
        raise SeedReviewError(
            "frame_hash_mismatch", f"Frame bytes changed: {record['path']}"
        )
    return SeedCandidate(
        frame_id=str(record["frame_id"]),
        index_zero_based=int(record["index_zero_based"]),
        pts_seconds=float(record["timestamp_seconds"]),
        path=str(record["path"]),
        sha256=str(record["sha256"]),
        width=int(manifest["metadata"]["width"]),
        height=int(manifest["metadata"]["height"]),
        origin="direct_source_frame",
        decode_operation=DIRECT_SOURCE_DECODE,
    )


def _frame_identity(candidate: SeedCandidate) -> tuple[object, ...]:
    return (
        candidate.frame_id,
        candidate.index_zero_based,
        candidate.pts_seconds,
        candidate.sha256,
        candidate.width,
        candidate.height,
        candidate.origin,
        candidate.decode_operation,
    )


def _base_report(
    mode: str,
    inventory: FrameInventory,
    k_values: Sequence[int],
    root: Path,
) -> dict[str, Any]:
    prepared = prepare_candidates(
        inventory.candidates,
        inventory.source,
        root,
        allow_mechanical_shortlist=True,
    )
    evaluated = list(prepared.reviewed) + list(prepared.excluded)
    views = [
        {
            "frame_id": item.candidate.frame_id,
            "sha256": item.candidate.sha256,
            "index_zero_based": item.candidate.index_zero_based,
            "pts_seconds": item.candidate.pts_seconds,
            "path": item.candidate.path,
            "batches": sorted(inventory.batches_by_sha256[item.candidate.sha256]),
            "mechanical": item.metrics.to_dict(),
            "consensus": {},
        }
        for item in evaluated
    ]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": "freeview_consensus",
        "tool_version": TOOL_VERSION,
        "issue": 210,
        "mode": mode,
        "source": inventory.source.to_dict(),
        "candidate_batches": inventory.batches,
        "unique_frame_count": len(inventory.candidates),
        "k_sweep": [int(k) for k in k_values],
        "mechanical_order": [item.candidate.frame_id for item in evaluated],
        "views": sorted(views, key=lambda view: view["frame_id"]),
    }


def _attach_consensus(report: dict[str, Any], variants: dict[str, Any]) -> None:
    by_frame = {view["frame_id"]: view for view in variants["views"]}
    for view in report["views"]:
        view["consensus"] = by_frame[view["frame_id"]]["consensus"]


def _ground_truth(
    frame_ids: Sequence[str],
    views: Sequence[dict[str, Any]],
    variants: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_frame = {view["frame_id"]: view for view in views}
    consensus = (
        {view["frame_id"]: view["consensus"] for view in variants["views"]}
        if variants is not None
        else {}
    )
    records = []
    for frame_id in sorted(set(frame_ids)):
        if frame_id not in by_frame:
            raise SeedReviewError(
                "ground_truth_not_in_inventory",
                f"Ground-truth frame is not in the candidate pool: {frame_id}",
            )
        view = by_frame[frame_id]
        ranks = {
            key: value["rank"] for key, value in consensus.get(frame_id, {}).items()
        }
        records.append(
            {
                "frame_id": frame_id,
                "mechanical_score": view["mechanical"]["mechanical_score"],
                "mechanical_rank": view["mechanical"]["mechanical_rank"],
                "consensus_rank_by_k": ranks,
            }
        )
    return records


def _cached_embeddings(
    inventory: FrameInventory, cache: EmbeddingCache
) -> list[list[float]]:
    embeddings = []
    for candidate in inventory.candidates:
        embedding = cache.get(candidate.sha256)
        if embedding is None:
            raise EmbeddingCacheError(
                f"Cached embedding missing for {candidate.frame_id}"
            )
        embeddings.append(embedding)
    return embeddings


def _cache_path(
    root: Path, source_id: str, model: LocalModel, requested: Path | None
) -> Path:
    if requested is not None:
        return resolve_cli_path(requested, root)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model.model_id).strip("-").lower()
    filename = f"embeddings-{slug}-{model.weights_sha256[:12]}.json"
    return root / LIBRARY / "sources" / source_id / "freeview" / filename


def _validate_model_catalog(model_id: str, embedding_dim: int) -> None:
    expected = MODEL_CATALOG.get(model_id, {}).get("embedding_dim")
    if expected is not None and expected != embedding_dim:
        raise SeedReviewError(
            "model_identity_mismatch",
            f"{model_id} has {expected}-d embeddings but the snapshot uses "
            f"{embedding_dim}-d; pass the matching --model-id",
        )


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _write_report(path: Path, report: dict[str, Any]) -> str:
    return write_deterministic(path, canonical_bytes(report))


if __name__ == "__main__":
    raise SystemExit(main())
