"""Build the frozen seed-review prompt from validated candidate metadata."""

from __future__ import annotations

import json

from seed_review_candidates import CandidateSet
from seed_review_sources import SourceRecord
from seed_review_workflow import WorkflowSpec


def build_prompt(
    candidate_set: CandidateSet,
    source: SourceRecord,
    spec: WorkflowSpec,
) -> str:
    lines = [
        f"SEED REVIEW REQUEST v{spec.prompt_version}",
        "",
        f"Source video: {source.source_id}",
        f"Source video SHA-256: {source.video_sha256}",
        (
            f"Candidate frames: {len(candidate_set.reviewed)} adjacent "
            "native-resolution direct-source frames."
        ),
        "",
        "Candidate metadata and advisory mechanical measurements:",
    ]
    for candidate in candidate_set.reviewed:
        metrics = candidate.metrics
        lines.append(
            json.dumps(
                {
                    "frame_id": candidate.candidate.frame_id,
                    "index_zero_based": candidate.candidate.index_zero_based,
                    "pts_seconds": candidate.candidate.pts_seconds,
                    "frame_sha256": candidate.candidate.sha256,
                    "width": candidate.candidate.width,
                    "height": candidate.candidate.height,
                    "focus_analysis_laplacian_variance": (
                        metrics.focus_analysis_laplacian_variance
                    ),
                    "exposure_score": metrics.exposure_score,
                    "duplicate_similarity": metrics.duplicate_similarity,
                    "temporal_gap_seconds": metrics.temporal_gap_seconds,
                    "mechanical_score": metrics.mechanical_score,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    lines.extend(
        [
            "",
            (
                "Compare only the attached images, in the order listed. Choose "
                "the single best frame as a panorama seed for later Hunyuan "
                "image-to-panorama work. The mechanical measurements are "
                "advisory; they do not replace visual inspection and do not "
                "prove a quality difference."
            ),
            "",
            (
                "If the frames are effectively indistinguishable, if none is "
                "suitable, or if you cannot support a choice from visible "
                "evidence, abstain by setting selected_frame_id to null. Never "
                "choose a panorama, contact sheet, composite, or rendered-room "
                "image. Do not infer hidden rooms, unseen geometry, or source "
                "connectivity."
            ),
            "",
            "Return exactly one JSON object with these six fields and no others:",
            "{",
            '  "selected_frame_id": "<one reviewed frame_id or null>",',
            '  "ranked_alternatives": ["<reviewed frame_id>", "..."],',
            '  "evidence": "<visible details that support the choice>",',
            '  "uncertainty": "<what remains ambiguous or unverified>",',
            '  "confidence_1_to_5": <integer from 1 to 5>,',
            '  "use_original_frame_not_a_composite": true',
            "}",
            "",
            "Do not add commentary outside the JSON object.",
        ]
    )
    return "\n".join(lines) + "\n"
