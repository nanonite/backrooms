#!/usr/bin/env python3
"""Compare Bevy Hunyuan captures with the unchanged Godot #100 baseline."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EVIDENCE = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE.parents[2]
CAPTURES = EVIDENCE / "captures"
THRESHOLD = "0.1"
VIEW_NAMES = ["frame_141", *(f"loop_station_{index:02d}" for index in range(8))]
THUMBNAIL = (320, 180)


def odiff_command() -> list[str]:
    binary = shutil.which("odiff")
    if binary:
        return [binary]
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("ODiff is not installed and npx is unavailable")
    return [npx, "--yes", "--package=odiff-bin@4.5.0", "odiff"]


def compare(command: list[str], left: Path, right: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    result = subprocess.run(
        [*command, str(left), str(right), str(output), "--threshold", THRESHOLD,
         "--parsable-stdout"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 22):
        raise RuntimeError(f"ODiff failed for {left.name}: {result.stderr.strip()}")
    match = re.search(r"(\d+);([0-9]+(?:\.[0-9]+)?)", result.stdout)
    if match:
        count, percent = int(match.group(1)), float(match.group(2))
    elif result.returncode == 0:
        count, percent = 0, 0.0
    else:
        raise RuntimeError(f"ODiff returned no parsable result: {result.stdout}")
    if count and not output.is_file():
        raise RuntimeError(f"ODiff reported {count} pixels but did not write {output}")
    return {
        "diff_pixels": count,
        "diff_percent": percent,
        "diff_image": output.relative_to(EVIDENCE).as_posix() if count else None,
        "threshold": float(THRESHOLD),
    }


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_hashes() -> dict:
    paths = {
        "hunyuan_visual_glb": REPO_ROOT / "godot_walk/generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb",
        "baseline_corridor_ply": REPO_ROOT / "godot_walk/assets/corridor_splat/corridor.ply",
        "baseline_alignment_manifest": REPO_ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json",
        "baseline_scene": REPO_ROOT / "godot_walk/scenes/corridor_splat.tscn",
        "baseline_project_settings": REPO_ROOT / "godot_walk/project.godot",
        "baseline_gaussian_node_script": REPO_ROOT / "godot_walk/addons/gdgs/runtime/nodes/gaussian_splat_node.gd",
        "baseline_gaussian_compositor_script": REPO_ROOT / "godot_walk/addons/gdgs/runtime/compositor/gaussian_compositor_effect.gd",
        "route_report": EVIDENCE / "collision_proto/authored_route_around_column/route_report.json",
        "frame_141_camera_metadata": EVIDENCE / "source_selection.json",
        "locked_capture_pose_manifest": CAPTURES / "capture_poses.json",
        "bevy_capture_report": CAPTURES / "bevy_hunyuan/bevy_capture_report.json",
    }
    return {name: {"path": str(path.relative_to(REPO_ROOT)), "sha256": file_sha256(path)}
            for name, path in paths.items()}


def compare_view(command: list[str], name: str) -> dict:
    baselines = [
        CAPTURES / f"baseline_repeat_{index}" / f"{name}.png"
        for index in range(1, 4)
    ]
    hunyuan = CAPTURES / "bevy_hunyuan" / f"{name}.png"
    expected_size = (960, 540)
    for path in [*baselines, hunyuan]:
        if not path.is_file() or image_size(path) != expected_size:
            raise ValueError(f"missing or wrong-size capture: {path}")
    noise_pairs = []
    for left_index, right_index in itertools.combinations(range(3), 2):
        left, right = baselines[left_index], baselines[right_index]
        label = f"repeat_{left_index + 1}_vs_{right_index + 1}"
        metrics = compare(command, left, right,
                          CAPTURES / "odiff" / "noise" / f"{name}_{label}.png")
        noise_pairs.append({"pair": label, **metrics})
    noise = max(noise_pairs, key=lambda item: item["diff_percent"])
    delta = compare(command, baselines[0], hunyuan,
                    CAPTURES / "odiff" / "bevy_vs_godot_baseline" / f"{name}.png")
    delta["interpretation"] = (
        "inconclusive_at_or_below_baseline_noise"
        if delta["diff_percent"] <= noise["diff_percent"]
        else "above_Godot_repeat_noise; cross_renderer_difference_requires_visual_review"
    )
    return {
        "view": name,
        "baseline_noise": noise,
        "baseline_noise_pairs": noise_pairs,
        "bevy_hunyuan_vs_godot_baseline": delta,
        "captures": {
            **{
                f"baseline_repeat_{index}": path.relative_to(EVIDENCE).as_posix()
                for index, path in enumerate(baselines, start=1)
            },
            "bevy_hunyuan": hunyuan.relative_to(EVIDENCE).as_posix(),
        },
        "sha256": {
            **{
                f"baseline_repeat_{index}": file_sha256(path)
                for index, path in enumerate(baselines, start=1)
            },
            "bevy_hunyuan": file_sha256(hunyuan),
        },
    }


def create_contact_sheet(results: list[dict]) -> None:
    label_height = 24
    gutter = 8
    sheet = Image.new("RGB", (gutter + 3 * (THUMBNAIL[0] + gutter),
                               gutter + len(results) * (THUMBNAIL[1] + label_height + gutter)),
                       (24, 27, 28))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    columns = ["baseline_repeat_1", "bevy_hunyuan", "diff"]
    for row, result in enumerate(results):
        y = gutter + row * (THUMBNAIL[1] + label_height + gutter)
        for column, label in enumerate(columns):
            x = gutter + column * (THUMBNAIL[0] + gutter)
            draw.text((x, y), f"{result['view']} | {label}", fill=(242, 242, 242), font=font)
            if label == "diff":
                diff_path = result["bevy_hunyuan_vs_godot_baseline"]["diff_image"]
                if not diff_path:
                    continue
                source = EVIDENCE / diff_path
            else:
                source = EVIDENCE / result["captures"][label]
            with Image.open(source) as image:
                thumbnail = image.convert("RGB").resize(THUMBNAIL, Image.Resampling.LANCZOS)
            sheet.paste(thumbnail, (x, y + label_height))
    sheet.save(CAPTURES / "bevy_contact_sheet.png")


def write_markdown(results: list[dict], command: list[str]) -> None:
    noise_max = max(item["baseline_noise"]["diff_percent"] for item in results)
    command_text = " ".join(command)
    lines = [
        "# Issue #137 Bevy Hunyuan Comparison",
        "",
        "The candidate is the run-05 Hunyuan GLB loaded in Bevy 0.18. The unchanged #100 `corridor_splat` baseline was captured in Godot 4.6.3. Both use the same nine camera poses, 960x540 output, and 47.3988-degree vertical field of view. The Hunyuan capture uses the recorded uncalibrated convention transform and contains no collision geometry.",
        "",
        f"ODiff threshold: `{THRESHOLD}`. Maximum same-pose Godot baseline repeat noise: `{noise_max:.6f}%` of pixels. ODiff is a pixel-change diagnostic, not a quality score. Because the candidate and baseline use different renderers, differences can come from renderer, material, tone-mapping, or geometry behavior. This comparison does not establish visual quality or parity. Changes at or below the per-view Godot repeat noise are inconclusive.",
        "",
        f"ODiff command: `{command_text}`. Contact sheet: [captures/bevy_contact_sheet.png](captures/bevy_contact_sheet.png). Pose contract: [captures/capture_poses.json](captures/capture_poses.json). Bevy capture details: [captures/bevy_hunyuan/bevy_capture_report.json](captures/bevy_hunyuan/bevy_capture_report.json).",
        "",
        "| View | Godot baseline repeat noise | Bevy Hunyuan vs Godot baseline | Interpretation | Captures |",
        "|---|---:|---:|---|---|",
    ]
    for result in results:
        noise = result["baseline_noise"]["diff_percent"]
        delta = result["bevy_hunyuan_vs_godot_baseline"]
        left, right = result["captures"]["baseline_repeat_1"], result["captures"]["bevy_hunyuan"]
        lines.append(
            f"| `{result['view']}` | {noise:.6f}% | {delta['diff_percent']:.3f}% "
            f"({delta['diff_pixels']} px) | `{delta['interpretation']}` | "
            f"[Godot baseline]({left}), [Bevy Hunyuan]({right}) |"
        )
    lines.extend([
        "",
        "No visual-quality or renderer-parity claim is made from ODiff. Review the linked same-pose captures to guide the Bevy material and render-pipeline port. Differences identify where the images diverge, not which representation is better.",
        "",
    ])
    (EVIDENCE / "ISSUE_137_BEVY_COMPARISON.md").write_text("\n".join(lines))


def main() -> None:
    command = odiff_command()
    poses = json.loads((CAPTURES / "capture_poses.json").read_text())
    names = [pose["name"] for pose in poses.get("poses", [])]
    if names != VIEW_NAMES:
        raise ValueError(f"capture pose names do not match the locked view set: {names}")
    results = [compare_view(command, name) for name in names]
    report = {
        "issue": 137,
        "label": "uncalibrated",
        "registration_accepted": False,
        "scale_calibrated": False,
        "baseline_renderer": "Godot 4.6.3 Forward+ Vulkan",
        "candidate_renderer": "Bevy 0.18.0 wgpu",
        "comparison_scope": "cross_renderer_pixel_differences_are_diagnostic_not_a_quality_score",
        "tool": "ODiff",
        "tool_command": command,
        "threshold": float(THRESHOLD),
        "source_assets": source_hashes(),
        "noise_method": "maximum pairwise ODiff delta among three same-pose baseline repeats",
        "maximum_baseline_repeat_noise_percent": max(
            item["baseline_noise"]["diff_percent"] for item in results
        ),
        "views": results,
        "interpretation": "pixel changes are diagnostic; at-or-below-noise differences are inconclusive",
    }
    (CAPTURES / "bevy_odiff_report.json").write_text(json.dumps(report, indent=2) + "\n")
    create_contact_sheet(results)
    write_markdown(results, command)
    print(json.dumps({
        "odiff_command": command,
        "maximum_repeat_noise_percent": report["maximum_baseline_repeat_noise_percent"],
        "views": len(results),
        "report": "ISSUE_137_BEVY_COMPARISON.md",
    }, indent=2))


if __name__ == "__main__":
    main()
