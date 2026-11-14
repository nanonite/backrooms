"""Markdown tables for the issue 246 picture-set consensus results."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

SCENE_ROLE = "scene"
DISTRACTOR_ROLE = "distractor"


def render_summary(results: dict[str, Any]) -> str:
    collections = results["collections"]
    lines = ["# Issue 246 collection results", ""]
    _similarity(lines, results.get("similarity_diagnostics") or {})
    _overview(lines, collections)
    _clean(lines, collections)
    _mixed(lines, collections)
    _distractor_ranks(lines, collections)
    _sanity(lines, collections)
    _score_levels(lines, collections)
    _mechanical(lines, collections)
    _top_views(lines, collections)
    _appendix(lines, collections)
    return "\n".join(lines) + "\n"


def _similarity(lines: list[str], diagnostics: dict[str, Any]) -> None:
    lines.extend(["## DINOv2 similarity diagnostics", ""])
    if not diagnostics:
        lines.extend(["No similarity diagnostics recorded.", ""])
        return
    lines.extend(
        [
            "| Pair | Pairs | Mean | Median | p10 | p90 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key, label in (
        ("scene_to_scene", "scene to scene"),
        ("distractor_to_distractor", "distractor to distractor"),
        ("scene_to_distractor", "scene to distractor"),
    ):
        item = diagnostics.get(key) or {}
        lines.append(
            f"| {label} | {item.get('pairs', 0)} | {_f(item.get('mean'))} | "
            f"{_f(item.get('median'))} | {_f(item.get('p10'))} | "
            f"{_f(item.get('p90'))} |"
        )
    lines.extend(
        ["", "Nearest-neighbour role mix (one nearest neighbour per image):", ""]
    )
    lines.extend(
        [
            "| Images | Count | Nearest is other role | Nearest own (median) | Nearest other (median) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for key in ("scene", "distractor"):
        item = (diagnostics.get("nearest_neighbour") or {}).get(key) or {}
        lines.append(
            f"| {key} | {item.get('count', 0)} | "
            f"{_count_rate(item.get('nearest_is_other_role'), item.get('count'))} | "
            f"{_f(item.get('nearest_own_median'))} | "
            f"{_f(item.get('nearest_cross_median'))} |"
        )
    lines.append("")


def _overview(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    lines.extend(["## Collections", ""])
    lines.extend(
        [
            "| Collection | Seed | Scene | Distractor | Realized distractor share | Collection SHA-256 (first 12) |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for collection in collections:
        lines.append(
            f"| {collection['name']} | {_int(collection.get('seed'))} | "
            f"{collection.get('scene_count')} | {collection.get('distractor_count')} | "
            f"{_percent(collection.get('realized_distractor_fraction'))} | "
            f"`{str(collection.get('collection_sha256'))[:12]}` |"
        )
    lines.append("")


def _clean(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    clean = [item for item in collections if item["kind"] == "clean"]
    lines.extend(["## Clean collections (scene only)", ""])
    lines.extend(
        [
            "| Collection | k | Reference | Threshold | Scene flagged | Scene keep rate |",
            "|---|---:|---|---:|---:|---:|",
        ]
    )
    for collection in clean:
        for k in _k_values(collection):
            metric = _metric(collection, k)
            lines.append(
                f"| {collection['name']} | {k} | `{_short(metric.get('reference_image_id'))}` | "
                f"{_f(metric.get('outlier_threshold'))} | "
                f"{metric.get('flagged_scene')} / {collection.get('scene_count')} | "
                f"{_percent(metric.get('scene_keep_rate'))} |"
            )
    lines.append("")


def _mixed(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    mixed = [item for item in collections if item["kind"] == "mixed"]
    lines.extend(["## Mixed collections, pooled across seeds", ""])
    lines.extend(
        [
            "| Mix | k | Reference role (scene / distractor) | Scene kept | Distractors rejected | Flag precision | Rank AUC | Threshold accepted |",
            "|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, group in _mix_groups(mixed):
        for k in _group_k_values(group):
            metrics = [_metric(item, k) for item in group]
            reference = [item.get("reference_role") for item in metrics]
            lines.append(
                f"| {label} | {k} | "
                f"{reference.count(SCENE_ROLE)} / {reference.count(DISTRACTOR_ROLE)} | "
                f"{_pooled(metrics, 'flagged_scene', 'scene_count', group, keep=True)} | "
                f"{_pooled(metrics, 'flagged_distractor', 'distractor_count', group, keep=False)} | "
                f"{_pooled_precision(metrics)} | "
                f"{_f(_mean([item.get('role_rank_auc') for item in metrics]))} | "
                f"{sum(1 for item in metrics if item.get('outlier_threshold') is not None)} / "
                f"{len(metrics)} |"
            )
    lines.append("")


def _distractor_ranks(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    mixed = [item for item in collections if item["kind"] == "mixed"]
    lines.extend(["## Distractor ranking", ""])
    lines.extend(
        [
            "| Mix | k | Distractor rank percentile (median) | Best distractor percentile | Distractors in top decile | Distractors in top quartile |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, group in _mix_groups(mixed):
        for k in _group_k_values(group):
            metrics = [_metric(item, k) for item in group]
            lines.append(
                f"| {label} | {k} | "
                f"{_f(_mean([item.get('distractor_rank_percentile_median') for item in metrics]))} | "
                f"{_f(_min([item.get('distractor_best_rank_percentile') for item in metrics]))} | "
                f"{sum(int(item.get('distractors_in_top_decile') or 0) for item in metrics)} | "
                f"{sum(int(item.get('distractors_in_top_quartile') or 0) for item in metrics)} |"
            )
    lines.append("")


def _sanity(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    sanity = [item for item in collections if item["kind"] == "distractor_only"]
    lines.extend(["## Sanity: distractor-only collection", ""])
    if not sanity:
        lines.extend(["Not present.", ""])
        return
    collection = sanity[0]
    lines.extend(
        [
            "| k | Reference | Threshold | Flagged | Score mean | Score max |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for k in _k_values(collection):
        metric = _metric(collection, k)
        scores = metric.get("distractor_scores") or {}
        lines.append(
            f"| {k} | `{_short(metric.get('reference_image_id'))}` | "
            f"{_f(metric.get('outlier_threshold'))} | "
            f"{metric.get('flagged_distractor')} / {collection.get('distractor_count')} | "
            f"{_f(scores.get('mean'))} | {_f(scores.get('max'))} |"
        )
    lines.append("")


def _score_levels(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    clean = next(
        (item for item in collections if item["name"] == "clean-full"),
        None,
    )
    sanity = next(
        (item for item in collections if item["kind"] == "distractor_only"),
        None,
    )
    if clean is None or sanity is None:
        return
    lines.extend(["## Score levels: coherent scene vs unrelated photos", ""])
    lines.extend(
        [
            "| k | Clean-full scene mean | Clean-full scene min | Distractor-only mean | Distractor-only max |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for k in _k_values(clean):
        scene = _metric(clean, k).get("scene_scores") or {}
        other = _metric(sanity, k).get("distractor_scores") or {}
        lines.append(
            f"| {k} | {_f(scene.get('mean'))} | {_f(scene.get('min'))} | "
            f"{_f(other.get('mean'))} | {_f(other.get('max'))} |"
        )
    lines.append("")


def _mechanical(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    lines.extend(["## Picture mechanical score comparison", ""])
    if any(item.get("mechanical") is None for item in collections):
        lines.extend(["Mechanical scoring was skipped for this run.", ""])
        return
    lines.extend(
        [
            "| Collection | Scene rank percentile (median) | Distractor rank percentile (median) | Rank AUC | Spearman vs consensus k5 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for collection in collections:
        item = collection.get("mechanical") or {}
        lines.append(
            f"| {collection['name']} | "
            f"{_f(item.get('scene_mechanical_rank_percentile_median'))} | "
            f"{_f(item.get('distractor_mechanical_rank_percentile_median'))} | "
            f"{_f(item.get('role_rank_auc'))} | "
            f"{_f(item.get('spearman_vs_k5'))} |"
        )
    lines.append("")


def _top_views(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    full = next(
        (item for item in collections if item["name"] == "clean-full"),
        collections[0] if collections else None,
    )
    if full is None:
        return
    lines.extend([f"## Highest-ranked scene views ({full['name']})", ""])
    lines.extend(
        [
            "| k | Rank | Image | Score | Mechanical rank | Outlier |",
            "|---|---:|---|---:|---:|---|",
        ]
    )
    ranks = full.get("mechanical_ranks") or {}
    for label, views in sorted(
        (full.get("top_views") or {}).items(), key=lambda item: int(item[0].lstrip("k"))
    ):
        for view in views:
            lines.append(
                f"| {label[1:]} | {view['rank']} | `{_short(view['image_id'])}` | "
                f"{_f(view['score'])} | {ranks.get(view['image_id'], 'n/a')} | "
                f"{'yes' if view['outlier'] else '-'} |"
            )
    lines.append("")


def _appendix(lines: list[str], collections: Sequence[dict[str, Any]]) -> None:
    lines.extend(["## Per-collection appendix", ""])
    lines.extend(
        [
            "| Collection | N | Ref k3 | Ref k5 | Ref k8 | k5 scene kept | k5 distractors rejected | k5 AUC | k15 AUC | k30 AUC |",
            "|---|---:|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for collection in collections:
        total = (collection.get("scene_count") or 0) + (
            collection.get("distractor_count") or 0
        )
        line = [f"| {collection['name']} | {total}"]
        for k in (3, 5, 8):
            metric = _metric(collection, k)
            line.append(f"{_short(metric.get('reference_role'))}")
        metric = _metric(collection, 5)
        line.append(f"{_percent(metric.get('scene_keep_rate'))}")
        line.append(f"{_percent(metric.get('distractor_rejection_rate'))}")
        for k in (5, 15, 30):
            line.append(f"{_f(_metric(collection, k).get('role_rank_auc'))}")
        lines.append(" | ".join(line) + " |")
    lines.append("")


def _mix_groups(
    mixed: Sequence[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for collection in mixed:
        if collection["name"] == "mixed-all":
            label = (
                f"all ({float(collection['realized_distractor_fraction']) * 100:.1f}%)"
            )
        else:
            label = _mix_label(collection.get("requested_distractor_fraction"))
        groups.setdefault(label, []).append(collection)
    return sorted(groups.items(), key=lambda item: _mix_sort_key(item[0]))


def _mix_sort_key(label: str) -> tuple[int, str]:
    if label.startswith("all"):
        return (99, label)
    return (int(float(label.rstrip("%"))), label)


def _mix_label(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.0f}%"


def _group_k_values(group: Sequence[dict[str, Any]]) -> list[int]:
    return sorted(int(key.lstrip("k")) for key in group[0]["metrics"]["by_k"])


def _k_values(collection: dict[str, Any]) -> list[int]:
    return sorted(int(key.lstrip("k")) for key in collection["metrics"]["by_k"])


def _metric(collection: dict[str, Any], k: int) -> dict[str, Any]:
    return collection["metrics"]["by_k"].get(f"k{k}", {})


def _pooled_precision(metrics: Sequence[dict[str, Any]]) -> str:
    flagged_scene = sum(int(item.get("flagged_scene") or 0) for item in metrics)
    flagged_distractor = sum(
        int(item.get("flagged_distractor") or 0) for item in metrics
    )
    total = flagged_scene + flagged_distractor
    if total == 0:
        return "n/a"
    return f"{flagged_distractor} / {total} ({_percent(flagged_distractor / total)})"


def _pooled(
    metrics: Sequence[dict[str, Any]],
    flag_key: str,
    count_key: str,
    collections: Sequence[dict[str, Any]],
    keep: bool,
) -> str:
    flagged = sum(int(item.get(flag_key) or 0) for item in metrics)
    total = sum(int(item.get(count_key) or 0) for item in collections)
    if total == 0:
        return "n/a"
    kept = total - flagged if keep else flagged
    return f"{kept} / {total} ({_percent(kept / total)})"


def _count_rate(value: Any, count: Any) -> str:
    if value is None or not count:
        return "n/a"
    return f"{int(value)} / {int(count)} ({_percent(float(value) / int(count))})"


def _mean(values: Sequence[Any]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _min(values: Sequence[Any]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return min(usable) if usable else None


def _f(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def _percent(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _int(value: Any) -> str:
    return "n/a" if value is None else str(int(value))


def _short(value: Any) -> str:
    if value is None:
        return "n/a"
    text = str(value)
    return text.rsplit("/", 1)[-1]
