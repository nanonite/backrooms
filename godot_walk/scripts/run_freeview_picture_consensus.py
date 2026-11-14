#!/usr/bin/env python3
"""Build and run the picture-set consensus validation on labelled collections.

The tool is advisory and read-only over the source images. It never registers a
picture set, never writes into the source library, and never downloads weights.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from deterministic_json import (
    ROOT,
    canonical_bytes,
    resolve_cli_path,
    sha256_file,
    write_deterministic,
)
from freeview_collection_evaluation import (
    collection_metrics,
    mechanical_summary,
    similarity_diagnostics,
)
from freeview_collection_summary import render_summary
from freeview_consensus import ConsensusError, evaluate_consensus
from freeview_embedding_cache import EmbeddingCache, EmbeddingCacheError
from freeview_embeddings import (
    DEFAULT_MODEL_ID,
    MODEL_CATALOG,
    DinoV2Encoder,
    EmbeddingUnavailableError,
    discover_local_weights,
    embed_into_cache,
    resolve_local_model,
    runtime_status,
)
from freeview_image_collections import (
    DEFAULT_MIX_LEVELS,
    DEFAULT_ROOM_SAMPLE,
    DEFAULT_SEEDS,
    SCENE_ROLE,
    CollectionError,
    build_collection_spec,
    collection_images,
    resolve_collection_path,
    scan_image_directory,
    verify_picture_set_manifest,
    verify_scene_manifest,
)
from picture_seed_review_candidates_v1 import evaluate_and_rank_images
from picture_seed_review_contract_v1 import PictureSetRecord
from seed_review_errors import SeedReviewError

TOOL_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = 1
DEFAULT_K_VALUES = (3, 5, 8, 15, 30)
TOP_VIEW_COUNT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_parser(subparsers)
    _run_parser(subparsers)
    _summary_parser(subparsers)
    _weights_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            return _run_build(args)
        if args.command == "run":
            return _run_collections(args)
        if args.command == "summary":
            return _run_summary(args)
        return _run_weights(args)
    except (
        CollectionError,
        ConsensusError,
        EmbeddingCacheError,
        EmbeddingUnavailableError,
        SeedReviewError,
        FileNotFoundError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _build_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "build", help="scan two image directories and write the collection spec"
    )
    parser.add_argument("--scene-dir", required=True, type=Path)
    parser.add_argument("--distractor-dir", required=True, type=Path)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scene-manifest", type=Path)
    parser.add_argument("--scene-resolution", default="images_4")
    parser.add_argument("--distractor-manifest", type=Path)
    parser.add_argument("--room-sample", type=int, default=DEFAULT_ROOM_SAMPLE)
    parser.add_argument("--seed", action="append", type=int, default=[])
    parser.add_argument("--mix", action="append", type=float, default=[])
    parser.add_argument("--k", action="append", type=int, default=[])


def _run_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "run", help="embed every collection and score role-aware consensus metrics"
    )
    parser.add_argument("--collections", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--skip-mechanical", action="store_true")


def _summary_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "summary", help="render markdown tables from a results report"
    )
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output")


def _weights_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("weights", help="report the local DINOv2 snapshot")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)


def _run_build(args: argparse.Namespace) -> int:
    scene = scan_image_directory(resolve_cli_path(args.scene_dir, ROOT), SCENE_ROLE)
    distractors = scan_image_directory(
        resolve_cli_path(args.distractor_dir, ROOT), "distractor"
    )
    seeds = args.seed or list(DEFAULT_SEEDS)
    mixes = args.mix or list(DEFAULT_MIX_LEVELS)
    k_values = args.k or list(DEFAULT_K_VALUES)
    spec = build_collection_spec(
        scene, distractors, seeds, mixes, args.room_sample, k_values
    )
    spec["scene_source"].update(_scene_provenance(args, scene))
    spec["distractor_source"].update(_distractor_provenance(args, distractors))
    status = write_deterministic(
        resolve_cli_path(Path(args.output), ROOT), canonical_bytes(spec)
    )
    print(
        json.dumps(
            {
                "status": status,
                "output": args.output,
                "collections": len(spec["collections"]),
            }
        )
    )
    return 0


def _scene_provenance(args: argparse.Namespace, scene: Sequence[Any]) -> dict[str, Any]:
    if args.scene_manifest is None:
        return {}
    manifest = resolve_cli_path(args.scene_manifest, ROOT)
    return {"manifest": verify_scene_manifest(manifest, scene, args.scene_resolution)}


def _distractor_provenance(
    args: argparse.Namespace, distractors: Sequence[Any]
) -> dict[str, Any]:
    if args.distractor_manifest is None:
        return {}
    manifest = resolve_cli_path(args.distractor_manifest, ROOT)
    return {"manifest": verify_picture_set_manifest(manifest, distractors)}


def _run_collections(args: argparse.Namespace) -> int:
    collections_path = resolve_cli_path(args.collections, ROOT)
    spec = _read_object(collections_path, "collection spec")
    collections = spec.get("collections")
    if not isinstance(collections, list) or not collections:
        raise CollectionError(f"No collections in {collections_path}")
    k_values = [int(k) for k in spec.get("k_values") or DEFAULT_K_VALUES]
    model = resolve_local_model(args.model_dir, args.model_id)
    _validate_model(model.model_id, model.embedding_dim)
    output_path = resolve_cli_path(Path(args.output), ROOT)
    cache_path = (
        resolve_cli_path(args.cache, ROOT)
        if args.cache is not None
        else output_path.parent / _cache_filename(model.model_id, model.weights_sha256)
    )
    cache = EmbeddingCache.load(cache_path, model.identity())
    encoder = DinoV2Encoder(model, batch_size=args.batch_size)
    frames = _unique_frames(collections)
    counts = embed_into_cache(frames, encoder, cache)
    cache.save()
    report = _build_results(
        spec, collections, cache, cache_path, k_values, model, args.skip_mechanical
    )
    status = write_deterministic(output_path, canonical_bytes(report))
    print(
        json.dumps(
            {
                "status": status,
                "output": args.output,
                "collections": len(collections),
                "encoded": counts["encoded"],
                "reused": counts["reused"],
            }
        )
    )
    return 0


def _build_results(
    spec: dict[str, Any],
    collections: Sequence[dict[str, Any]],
    cache: EmbeddingCache,
    cache_path: Path,
    k_values: Sequence[int],
    model: Any,
    skip_mechanical: bool,
) -> dict[str, Any]:
    embeddings = _collection_embeddings(collections, cache)
    scene_ids, distractor_ids = _global_roles(collections)
    results = []
    for collection in collections:
        results.append(
            _collection_result(collection, embeddings, k_values, skip_mechanical)
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": "freeview_picture_set_consensus",
        "tool_version": TOOL_VERSION,
        "issue": 246,
        "mode": "run",
        "model": {**model.identity().to_dict(), "device": "cpu"},
        "runtime": runtime_status(),
        "embedding_cache": {
            "path": _repo_relative(cache_path),
            "cached_total": len(cache),
        },
        "collection_spec": {
            "seeds": spec.get("seeds"),
            "mix_levels": spec.get("mix_levels"),
            "room_sample_size": spec.get("room_sample_size"),
            "scene_source": spec.get("scene_source"),
            "distractor_source": spec.get("distractor_source"),
        },
        "k_values": [int(k) for k in k_values],
        "similarity_diagnostics": similarity_diagnostics(
            scene_ids, distractor_ids, embeddings
        ),
        "collections": results,
    }


def _collection_result(
    collection: dict[str, Any],
    embeddings: dict[str, list[float]],
    k_values: Sequence[int],
    skip_mechanical: bool,
) -> dict[str, Any]:
    images = collection_images(collection)
    roles = {image["image_id"]: image["role"] for image in images}
    frame_ids = sorted(roles)
    vectors = [embeddings[frame_id] for frame_id in frame_ids]
    variants = evaluate_consensus(frame_ids, vectors, k_values)
    result = {
        "name": collection["name"],
        "kind": collection["kind"],
        "seed": collection.get("seed"),
        "requested_distractor_fraction": collection.get(
            "requested_distractor_fraction"
        ),
        "realized_distractor_fraction": collection.get("realized_distractor_fraction"),
        "scene_count": collection.get("scene_count"),
        "distractor_count": collection.get("distractor_count"),
        "collection_sha256": collection.get("collection_sha256"),
        "consensus": variants,
        "metrics": collection_metrics(variants["views"], roles, k_values),
        "top_views": _top_views(variants, roles),
        "mechanical": None,
        "mechanical_ranks": None,
    }
    if not skip_mechanical:
        summary, ranks = _mechanical(collection, roles, variants)
        result["mechanical"] = summary
        result["mechanical_ranks"] = ranks
    return result


def _top_views(
    variants: dict[str, Any], roles: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    top: dict[str, list[dict[str, Any]]] = {}
    for label in sorted(variants["variants"], key=lambda item: int(item.lstrip("k"))):
        ordered = sorted(
            variants["views"],
            key=lambda view: (view["consensus"][label]["rank"], view["frame_id"]),
        )[:TOP_VIEW_COUNT]
        top[label] = [
            {
                "image_id": view["frame_id"],
                "role": roles[view["frame_id"]],
                "score": view["consensus"][label]["score"],
                "rank": view["consensus"][label]["rank"],
                "outlier": view["consensus"][label]["outlier"],
            }
            for view in ordered
        ]
    return top


def _mechanical(
    collection: dict[str, Any],
    roles: dict[str, str],
    variants: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    images = collection_images(collection)
    record = PictureSetRecord(
        source_id="advisory-unregistered-246",
        source_path=collection["name"],
        source_image_set_sha256=collection["collection_sha256"],
        manifest_path="(none: in-memory advisory record)",
        manifest_sha256="0" * 64,
        images=tuple(
            {
                "image_id": image["image_id"],
                "capture_index": index,
                "path": image["path"],
                "sha256": image["sha256"],
                "width": image["width"],
                "height": image["height"],
            }
            for index, image in enumerate(images, start=1)
        ),
    )
    ranked = evaluate_and_rank_images(record, ROOT)
    ranks = {
        view["frame_id"]: {
            label: payload["rank"] for label, payload in view["consensus"].items()
        }
        for view in variants["views"]
    }
    mechanical_ranks = {
        record["image_id"]: int(record["mechanical_rank"]) for record in ranked
    }
    return mechanical_summary(ranked, roles, ranks), mechanical_ranks


def _collection_embeddings(
    collections: Sequence[dict[str, Any]],
    cache: EmbeddingCache,
) -> dict[str, list[float]]:
    embeddings = {}
    for collection in collections:
        for image in collection_images(collection):
            vector = cache.get(image["sha256"])
            if vector is None:
                raise EmbeddingCacheError(
                    f"Cached embedding missing for {image['image_id']}"
                )
            embeddings[image["image_id"]] = vector
    return embeddings


def _unique_frames(collections: Sequence[dict[str, Any]]) -> list[tuple[str, Path]]:
    frames: dict[str, Path] = {}
    for collection in collections:
        for image in collection_images(collection):
            path = resolve_collection_path(image["path"])
            if not path.is_file():
                raise FileNotFoundError(f"Collection image is missing: {path}")
            if sha256_file(path) != image["sha256"]:
                raise CollectionError(f"Collection image bytes changed: {path}")
            frames.setdefault(image["sha256"], path)
    return sorted(frames.items())


def _global_roles(collections: Sequence[dict[str, Any]]) -> tuple[list[str], list[str]]:
    roles: dict[str, str] = {}
    for collection in collections:
        for image in collection_images(collection):
            roles[image["image_id"]] = image["role"]
    scene = sorted(image_id for image_id, role in roles.items() if role == SCENE_ROLE)
    distractor = sorted(
        image_id for image_id, role in roles.items() if role == "distractor"
    )
    return scene, distractor


def _run_summary(args: argparse.Namespace) -> int:
    results = _read_object(resolve_cli_path(args.results, ROOT), "results report")
    text = render_summary(results)
    if args.output:
        status = write_deterministic(
            resolve_cli_path(Path(args.output), ROOT), text.encode("utf-8")
        )
        print(json.dumps({"status": status, "output": args.output}))
    else:
        print(text, end="")
    return 0


def _run_weights(args: argparse.Namespace) -> int:
    model = resolve_local_model(args.model_dir, args.model_id)
    _validate_model(model.model_id, model.embedding_dim)
    report = {
        "status": "available",
        "runtime": runtime_status(),
        "requested_model": {**model.identity().to_dict(), "device": "cpu"},
        "discovered_weights": discover_local_weights(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _validate_model(model_id: str, embedding_dim: int) -> None:
    expected = MODEL_CATALOG.get(model_id, {}).get("embedding_dim")
    if expected is not None and expected != embedding_dim:
        raise EmbeddingUnavailableError(
            f"{model_id} has {expected}-d embeddings but the snapshot uses "
            f"{embedding_dim}-d; pass the matching --model-id"
        )


def _cache_filename(model_id: str, weights_sha256: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", model_id).strip("-").lower()
    return f"embeddings-{slug}-{weights_sha256[:12]}.json"


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionError(f"Cannot read {label}: {path}") from error
    if not isinstance(document, dict):
        raise CollectionError(f"{label} must be a JSON object: {path}")
    return document


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
