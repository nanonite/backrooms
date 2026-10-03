#!/usr/bin/env python3
"""Decide whether a capture can support a coherent walkable scene, and say why.

A finding here is a measurement compared against a threshold, plus the lever
that moves it. Two properties are deliberate:

* **Resolution is not a rejection criterion.** 720p is not too small for
  photometric matching -- SIFT on a 1280x720 frame finds more features than a
  sparse reconstruction needs. What 720p costs is texture at distance and
  small high-frequency detail, which shows up later as a soft reconstruction
  rather than as a failure to register, so it is reported with its feature
  budget and nothing more. The only resolution floor is a frame too small to
  carry features at all.
* **Every rejection names a capture change.** "Fail" is not an outcome an
  operator can act on; "the camera turned instead of travelling, so re-shoot
  with the camera body moving" is. Each blocking finding carries a cause and an
  action, and the statuses are ``rejected``, ``accepted_with_warnings`` and
  ``accepted`` -- a warning is a fact about the capture, not a failure to
  measure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from candidate_scan import ScanResult
from frame_selection import SelectionResult
from geometry_consistency import (
    CONSISTENT,
    INCOHERENT,
    MOVING_CONTENT,
    TRANSLATION_EXPLAINED_LIMIT,
    ConsistencyVerdict,
)
from resource_estimate import ResourceVerdict
from sampling_budget import SamplingBudget
from view_coverage import CoverageReport
from video_probe import VideoMetadata

SEVERITY_BLOCK = "block"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"

STATUS_ACCEPTED = "accepted"
STATUS_WARNED = "accepted_with_warnings"
STATUS_REJECTED = "rejected"

#: Below this a frame carries too little for feature matching to register
#: anything. 320x240 is roughly 1.5% of the pixels of a 1080p frame and the
#: point where "it is small" stops being about detail and starts being about
#: matching failing outright.
MIN_USABLE_PIXELS = 320 * 240
MIN_USABLE_WIDTH = 320
MIN_USABLE_HEIGHT = 240

#: Advisory only. Reported with the feature budget that 720p does support, so
#: the number informs the decision instead of making it.
RECOMMENDED_HEIGHT = 1080

#: Shorter than this and there is no baseline to reconstruct from: at 24 fps it
#: is under 36 frames, fewer than a sequential matcher can bootstrap from.
MIN_DURATION_SECONDS = 1.5
MIN_CLIP_FRAMES = 12

#: Variance-of-Laplacian floor at the default 640x360 analysis resolution.
#: The six 1080p captures in ``data/videos/`` measure 134-188 (median) there;
#: a frame well below this is soft enough that features will not repeat.
BLUR_SHARPNESS_FLOOR = 40.0

#: p10/median sharpness below this means sharpness varies across the clip, so
#: some frames are soft and will fail to register while others do not.
BLUR_UNEVEN_RATIO = 0.35

#: Total camera path across the clip, in analysis frame widths. A quarter-frame
#: walk is the minimum that separates "moved" from "pivoted".
MIN_PATH_WIDTHS = 0.25

#: Fewer selected frames than this cannot triangulate a small room, whatever
#: the target was set to.
MIN_USEFUL_FRAMES = 30

#: A walk that only ever travelled one direction sees every surface from one
#: side. Surfaces need two or more viewing angles to triangulate at all.
MIN_DIRECTIONS = 2


@dataclass(frozen=True)
class Finding:
    """One measured fact, compared against a threshold, with the lever to pull."""

    code: str
    severity: str
    measured: str
    threshold: str
    cause: str
    action: str

    @property
    def is_block(self) -> bool:
        return self.severity == SEVERITY_BLOCK

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "measured": self.measured,
            "threshold": self.threshold,
            "cause": self.cause,
            "action": self.action,
        }


@dataclass(frozen=True)
class CaptureVerdict:
    """The verdict plus every finding behind it and what was not measured."""

    status: str
    findings: tuple[Finding, ...]
    limits: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def rejected(self) -> bool:
        return self.status == STATUS_REJECTED

    def findings_of(self, severity: str) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == severity)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "findings": [finding.to_dict() for finding in self.findings],
            "limits": list(self.limits),
            "notes": list(self.notes),
        }


def _resolution_findings(metadata: VideoMetadata) -> list[Finding]:
    """Resolution, as a hard floor and an advisory -- never as a 720p rejection."""
    if metadata.total_pixels < MIN_USABLE_PIXELS:
        return [
            Finding(
                code="resolution_unusable",
                severity=SEVERITY_BLOCK,
                measured=f"{metadata.width}x{metadata.height} ({metadata.megapixels:.2f} MP)",
                threshold=f">= {MIN_USABLE_WIDTH}x{MIN_USABLE_HEIGHT} ({MIN_USABLE_PIXELS / 1_000_000:.2f} MP)",
                cause="a frame this small does not carry enough texture for features to be matched twice",
                action="re-capture at 1280x720 or higher; this is the one resolution limit that is not negotiable",
            )
        ]
    if metadata.height < RECOMMENDED_HEIGHT:
        return [
            Finding(
                code="resolution_below_recommended",
                severity=SEVERITY_INFO,
                measured=f"{metadata.width}x{metadata.height} ({metadata.megapixels:.2f} MP)",
                threshold=f">= {RECOMMENDED_HEIGHT}p recommended, not required",
                cause=(
                    f"{metadata.megapixels:.2f} MP is enough to match features on surfaces close to the "
                    "camera; it costs detail on distant surfaces, which softens the reconstruction rather "
                    "than preventing registration"
                ),
                action="proceed; if the result is soft at distance, re-shoot at 1080p or move closer to the surfaces",
            )
        ]
    return []


def _duration_findings(metadata: VideoMetadata) -> list[Finding]:
    findings = []
    if metadata.duration_seconds < MIN_DURATION_SECONDS or metadata.frame_count < MIN_CLIP_FRAMES:
        findings.append(
            Finding(
                code="clip_too_short",
                severity=SEVERITY_BLOCK,
                measured=f"{metadata.duration_seconds:.2f}s, {metadata.frame_count} frames",
                threshold=f">= {MIN_DURATION_SECONDS:.1f}s and >= {MIN_CLIP_FRAMES} frames",
                cause="there is no baseline between views: a mapper needs at least three views that moved",
                action="re-capture a continuous walk of several seconds rather than a single still frame",
            )
        )
    return findings


def _motion_findings(scan: ScanResult, budget: SamplingBudget) -> list[Finding]:
    shifts = [
        candidate.translation.magnitude_fraction
        for candidate in scan.candidates
        if candidate.translation is not None
    ]
    explained = [
        candidate.translation.explained_fraction
        for candidate in scan.candidates
        if candidate.translation is not None
    ]
    if not shifts:
        return []
    median_shift = float(np.median(shifts))
    median_explained = float(np.median(explained))
    threshold = f">= {budget.min_shift_fraction:.1%} of frame width between candidates"
    measured = (
        f"median {median_shift:.2%} of frame width over {scan.parallax_gap} candidate gaps "
        f"({scan.motion_px_per_frame:.2f} px per source frame)"
    )
    if median_shift < budget.min_shift_fraction:
        return [
            Finding(
                code="no_parallax_baseline",
                severity=SEVERITY_BLOCK,
                measured=measured,
                threshold=threshold,
                cause=(
                    "the view barely changes between samples, so there is no triangulation baseline and "
                    "the reconstruction has no depth to recover"
                ),
                action="re-capture while walking the camera body through the room; turning the view in place adds no baseline",
            )
        ]
    if median_explained < TRANSLATION_EXPLAINED_LIMIT:
        return [
            Finding(
                code="rotation_dominant",
                severity=SEVERITY_WARN,
                measured=f"median global translation explains {median_explained:.0%} of the frame change",
                threshold=f">= {TRANSLATION_EXPLAINED_LIMIT:.0%} explained by one global translation",
                cause=(
                    "the picture changes without the camera translating, which is a pan, a zoom or a "
                    "handheld wobble; those give no depth"
                ),
                action="keep translating while turning; translate the camera body, not just the view",
            )
        ]
    return []


def _cut_findings(scan: ScanResult, consistency: ConsistencyVerdict, budget: SamplingBudget) -> list[Finding]:
    cuts = [candidate for candidate in scan.candidates if candidate.is_cut]
    if not cuts:
        return []
    if consistency.classification == INCOHERENT:
        return []
    first = cuts[0]
    return [
        Finding(
            code="scene_cuts",
            severity=SEVERITY_BLOCK,
            measured=(
                f"{len(cuts)} cut(s) among {len(scan.candidates)} candidates, first at frame "
                f"{first.index} ({first.cut_signal})"
            ),
            threshold=(
                f"histogram distance <= {budget.cut_distance_limit:.2f} and unalignable pixels "
                f"<= {budget.cut_residual_limit:.0%} between consecutive samples"
            ),
            cause=(
                "frames on opposite sides of a cut share no geometry, so they cannot be registered into "
                "one sparse model"
            ),
            action=(
                "shoot one continuous take, or split the clip into one scene per file and reconstruct "
                "them separately"
            ),
        )
    ]


def _blur_findings(scan: ScanResult) -> list[Finding]:
    sharpness = [candidate.sharpness for candidate in scan.candidates]
    if not sharpness:
        return []
    findings = []
    median = float(np.median(sharpness))
    low = float(np.percentile(sharpness, 10))
    if median < BLUR_SHARPNESS_FLOOR:
        findings.append(
            Finding(
                code="low_sharpness",
                severity=SEVERITY_WARN,
                measured=f"median sharpness {median:.0f} at {scan.size.width}x{scan.size.height}",
                threshold=f">= {BLUR_SHARPNESS_FLOOR:.0f} at this analysis resolution",
                cause="soft frames yield fewer repeatable features, so pose estimation registers fewer views",
                action="re-shoot with a faster shutter (more light or higher ISO) and steady hands; check the focus",
            )
        )
    elif low < median * BLUR_UNEVEN_RATIO:
        findings.append(
            Finding(
                code="uneven_sharpness",
                severity=SEVERITY_WARN,
                measured=f"10th percentile sharpness {low:.0f} against median {median:.0f}",
                threshold=f"10th percentile >= {BLUR_UNEVEN_RATIO:.0%} of median",
                cause="part of the clip is soft; those frames will fail to register while the rest succeed",
                action="stabilise the capture; the selector already drops the softest frames below their neighbours",
            )
        )
    eligible = sum(1 for candidate in scan.candidates if candidate.sharpness >= BLUR_SHARPNESS_FLOOR)
    if eligible == 0:
        findings.append(
            Finding(
                code="no_sharp_frames",
                severity=SEVERITY_BLOCK,
                measured=f"all {len(sharpness)} candidates below {BLUR_SHARPNESS_FLOOR:.0f}",
                threshold=f">= {BLUR_SHARPNESS_FLOOR:.0f}",
                cause="no sampled frame has enough detail to match features against another frame",
                action="re-capture; brightening can help but a soft capture is usually motion blur, which brightening cannot undo",
            )
        )
    return findings


def _consistency_findings(consistency: ConsistencyVerdict) -> list[Finding]:
    if consistency.classification == CONSISTENT:
        return []
    severity = SEVERITY_BLOCK if consistency.rejected else SEVERITY_WARN
    if consistency.classification == INCOHERENT:
        cause = (
            "the whole frame changes between adjacent frames and no global translation explains it, so there is "
            "no single rigid scene: this is the signature of generated or heavily reprocessed footage, where detail "
            "is re-imagined every frame"
        )
        action = (
            "capture a real walk-through of the place. Reconstruction cannot invent geometry that was never "
            "consistent, and a generated clip will not show surfaces the generator did not draw twice the same way"
        )
    elif consistency.classification == MOVING_CONTENT:
        cause = "content that moves occupies enough of the frame to corrupt the static surfaces behind it"
        action = "shoot an empty room, or one without people, pets, traffic or anything that moves during the take"
    else:
        return [
            Finding(
                code="consistency_not_measured",
                severity=SEVERITY_INFO,
                measured=consistency.evidence,
                threshold="at least one contiguous window decodable",
                cause="temporal consistency could not be measured, so nothing is claimed about it either way",
                action="re-run with a longer clip, or lower burst_length if the clip is very short",
            )
        ]
    return [
        Finding(
            code=f"geometry_{consistency.classification}",
            severity=severity,
            measured=consistency.evidence,
            threshold="static scene: one translation plus parallax explains adjacent frames",
            cause=cause,
            action=action,
        )
    ]


def _coverage_findings(coverage: CoverageReport, selection: SelectionResult, budget: SamplingBudget) -> list[Finding]:
    findings = []
    if coverage.path_length_widths < MIN_PATH_WIDTHS:
        findings.append(
            Finding(
                code="camera_path_too_short",
                severity=SEVERITY_BLOCK,
                measured=f"{coverage.path_length_widths:.2f} frame widths of camera travel",
                threshold=f">= {MIN_PATH_WIDTHS:.2f} frame widths",
                cause="the walkable volume a splat can support is the volume the camera passed through",
                action="re-shoot walking the length of the space you want to walk in",
            )
        )
    if coverage.distinct_directions < MIN_DIRECTIONS and coverage.path_length_widths > MIN_PATH_WIDTHS:
        findings.append(
            Finding(
                code="single_direction_walk",
                severity=SEVERITY_WARN,
                measured=f"camera travelled in {coverage.distinct_directions} direction(s) over "
                f"{coverage.path_length_widths:.2f} frame widths",
                threshold=f">= {MIN_DIRECTIONS} directions of travel",
                cause=(
                    "a one-way walk sees every surface from one side, and a surface seen from one "
                    "angle cannot be triangulated"
                ),
                action="weave the walk: pass close to one wall then cross to the other, or round a corner",
            )
        )
    if selection.count < MIN_USEFUL_FRAMES:
        findings.append(
            Finding(
                code="too_few_frames",
                severity=SEVERITY_WARN,
                measured=f"{selection.count} usable frames selected",
                threshold=f">= {MIN_USEFUL_FRAMES} for a small room",
                cause=f"a small room needs enough views to triangulate; {budget.hypothesis_note(selection.count)}",
                action="capture a longer walk, or accept a smaller reconstruction volume",
            )
        )
    if coverage.span_fraction < 0.5 and coverage.clip_span_seconds > MIN_DURATION_SECONDS:
        findings.append(
            Finding(
                code="partial_clip_used",
                severity=SEVERITY_INFO,
                measured=f"selected frames span {coverage.span_fraction:.0%} of the clip",
                threshold="selection spread across the whole take",
                cause="frames outside the selected span contribute nothing, so the room is reconstructed from part of the walk only",
                action="no action needed if the omitted part is redundant; re-shoot if it covered different geometry",
            )
        )
    return findings


def _resource_findings(verdict: ResourceVerdict) -> list[Finding]:
    return [
        Finding(
            code="resource_budget_exceeded",
            severity=SEVERITY_BLOCK,
            measured="; ".join(verdict.blockers),
            threshold="estimate must fit free disk and RAM after headroom",
            cause="the run would fail during extraction or mapping, after the sampling work is spent",
            action="; ".join(verdict.actions),
        )
    ]


def judge_capture(
    metadata: VideoMetadata,
    scan: ScanResult,
    selection: SelectionResult,
    coverage: CoverageReport,
    consistency: ConsistencyVerdict,
    resources: ResourceVerdict,
    budget: SamplingBudget,
) -> CaptureVerdict:
    """Combine every measurement into one status, with the findings that produced it."""
    findings: list[Finding] = []
    findings += _resolution_findings(metadata)
    findings += _duration_findings(metadata)
    findings += _motion_findings(scan, budget)
    findings += _cut_findings(scan, consistency, budget)
    findings += _blur_findings(scan)
    findings += _consistency_findings(consistency)
    findings += _coverage_findings(coverage, selection, budget)
    if not resources.fits:
        findings += _resource_findings(resources)
    return CaptureVerdict(
        status=_status_for(findings),
        findings=tuple(_by_severity(findings)),
        limits=scan.limits,
        notes=(
            budget.hypothesis_note(selection.count),
            "resolution is reported, never used as a rejection: 720p matches features, it only softens distance",
        ),
    )


#: Blocking findings first: a report that opens with a blur warning buries the
#: reason the capture was refused.
_SEVERITY_ORDER = {SEVERITY_BLOCK: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}


def _by_severity(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda finding: _SEVERITY_ORDER.get(finding.severity, 3))


def _status_for(findings: list[Finding]) -> str:
    if any(finding.is_block for finding in findings):
        return STATUS_REJECTED
    if any(finding.severity == SEVERITY_WARN for finding in findings):
        return STATUS_WARNED
    return STATUS_ACCEPTED