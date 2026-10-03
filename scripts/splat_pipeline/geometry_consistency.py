#!/usr/bin/env python3
"""Tell a real capture apart from footage whose geometry does not hold still.

Photogrammetry assumes one scene: a pixel that is a wall corner in one frame is
the same corner in the next, and the displacement between the two views is what
gives depth. Generated footage breaks that assumption in a way that is
measurable -- detail is re-rendered each frame, so a tracked feature does not
land where the geometry says it should. The signature is specific:

* **The picture changes everywhere, not somewhere.** A person walking through
  the shot leaves a few hot blocks. Footage whose texture is rewritten leaves
  the whole frame hot, with a global translation explaining almost none of it.
* **The translation explains nothing.** For a real camera, one global shift
  plus parallax accounts for most of the frame change. When the unexplained
  share stays near the original change, nothing rigid happened.

What this module refuses to do is call that "AI video". It reports *inconsistent
temporal geometry* -- a measured property of the pixels -- and it says a real
capture is the fix, because no amount of parameter tuning reconstructs geometry
that was never consistent. It cannot prove provenance either: a heavily
stabilised, heavily denoised or heavily cropped real capture can look the same
way, which is why the finding names the measurement and the remedy rather than
the culprit.

Measured basis for the thresholds (see ``fixtures/README.md`` for the clips):
the six 1080p captures in ``data/videos/`` measure a 90th-percentile hot-block
fraction of 0.003-0.059 and a median residual of 0.034-0.069 between adjacent
frames; the ``incoherent`` fixture, which regenerates the scene's texture every
frame over an otherwise plausible camera move, measures 1.00 and 0.73.
"""

from __future__ import annotations

from dataclasses import dataclass

from candidate_scan import BurstStats

#: Hot-block fraction at the 90th percentile above which moving content is
#: reported. The measured clips reach 0.059; the dynamic fixture reaches 0.133.
MOVING_BLOCK_WARN = 0.08

#: Above this the scene is dominated by content that moves, and no static
#: surface can be reconstructed reliably.
MOVING_BLOCK_REJECT = 0.25

#: Fraction of hot blocks above which the *whole frame* is changing rather than
#: part of it. The incoherent fixture measures 1.00.
INCOHERENT_BLOCK_LIMIT = 0.35

#: Median pixel residual above which a global translation explains almost none
#: of the frame change. The incoherent fixture measures 0.73.
INCOHERENT_PIXEL_LIMIT = 0.25

#: Below this share of the change explained, motion is not the camera moving.
TRANSLATION_EXPLAINED_LIMIT = 0.25

CONSISTENT = "temporal_geometry_consistent"
MOVING_CONTENT = "moving_content_dominant"
INCOHERENT = "temporal_geometry_inconsistent"
UNMEASURED = "not_measured"


@dataclass(frozen=True)
class ConsistencyVerdict:
    """What the burst probe measured, and what it means for reconstruction."""

    classification: str
    median_residual_fraction: float
    p90_hot_block_fraction: float
    max_hot_block_fraction: float
    rejected: bool
    warned: bool
    evidence: str

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "median_residual_fraction": round(self.median_residual_fraction, 4),
            "p90_hot_block_fraction": round(self.p90_hot_block_fraction, 4),
            "max_hot_block_fraction": round(self.max_hot_block_fraction, 4),
            "rejected": self.rejected,
            "warned": self.warned,
            "evidence": self.evidence,
        }


def classify_consistency(bursts: BurstStats) -> ConsistencyVerdict:
    """Classify a burst measurement as consistent, moving or geometrically inconsistent."""
    if bursts.pairs == 0:
        return ConsistencyVerdict(
            classification=UNMEASURED,
            median_residual_fraction=0.0,
            p90_hot_block_fraction=0.0,
            max_hot_block_fraction=0.0,
            rejected=False,
            warned=False,
            evidence="no contiguous window could be decoded, so temporal consistency was not measured",
        )
    return _verdict_for(
        bursts.median_residual_fraction, bursts.p90_hot_block_fraction, bursts.max_hot_block_fraction
    )


def _verdict_for(median_residual: float, p90_blocks: float, max_blocks: float) -> ConsistencyVerdict:
    evidence = (
        f"adjacent frames leave {median_residual:.1%} of pixels changed after a global "
        f"translation, and {p90_blocks:.1%} of 24px blocks still differ (worst window {max_blocks:.1%})"
    )
    if p90_blocks >= INCOHERENT_BLOCK_LIMIT or median_residual >= INCOHERENT_PIXEL_LIMIT:
        return ConsistencyVerdict(
            classification=INCOHERENT,
            median_residual_fraction=median_residual,
            p90_hot_block_fraction=p90_blocks,
            max_hot_block_fraction=max_blocks,
            rejected=True,
            warned=True,
            evidence=evidence + " -- the whole frame changes, so no single scene persists",
        )
    if p90_blocks >= MOVING_BLOCK_REJECT:
        return ConsistencyVerdict(
            classification=MOVING_CONTENT,
            median_residual_fraction=median_residual,
            p90_hot_block_fraction=p90_blocks,
            max_hot_block_fraction=max_blocks,
            rejected=True,
            warned=True,
            evidence=evidence + " -- most of the frame is moving, leaving little static surface",
        )
    if p90_blocks >= MOVING_BLOCK_WARN:
        return ConsistencyVerdict(
            classification=MOVING_CONTENT,
            median_residual_fraction=median_residual,
            p90_hot_block_fraction=p90_blocks,
            max_hot_block_fraction=max_blocks,
            rejected=False,
            warned=True,
            evidence=evidence + " -- part of the frame moves, which is a person or a door, not the room",
        )
    return ConsistencyVerdict(
        classification=CONSISTENT,
        median_residual_fraction=median_residual,
        p90_hot_block_fraction=p90_blocks,
        max_hot_block_fraction=max_blocks,
        rejected=False,
        warned=False,
        evidence=evidence + " -- one rigid scene accounts for the change",
    )