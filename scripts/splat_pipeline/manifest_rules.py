#!/usr/bin/env python3
"""The fixed, hand-maintained parts of an alignment manifest.

Two things in a manifest are not *measured* by
``measure_splat_frame.py``: the list of transforms the GDGS toolchain applies on
its own, and the scales that were available and must not be reused.  Both are
recorded once here so the runtime verifier and any reviewer read the same
statement of what the pipeline does behind our back.
"""

from __future__ import annotations

from splat_frame import AutomaticTransform

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
ZERO = (0.0, 0.0, 0.0)

#: GDGS' default model-orientation correction, a -180 degree rotation about z.
GDGS_DEFAULT_CORRECTION = ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))

DECODER = "addons/gdgs/importers/decoders/standard_ply_decoder.gd"
BUILDER = "addons/gdgs/importers/builders/gaussian_resource_builder.gd"
ORIENTATION = (
    "addons/gdgs/runtime/nodes/gaussian_splat_node.gd:_apply_default_orientation_if_needed"
)
REGISTRY = (
    "addons/gdgs/runtime/render/gaussian_scene_registry.gd"
    " + render/shaders/compute/gsplat_projection.glsl"
)


def automatic_transforms() -> tuple[AutomaticTransform, ...]:
    """Return every transform the GDGS pipeline applies without being asked.

    Each entry says whether the scene neutralises it and how, so the manifest
    can answer "is this applied exactly once?" without reading the addon.
    """
    return (
        AutomaticTransform(
            stage="import",
            source=DECODER,
            summary="Centres, exp(scale_N) extents and (rot_1..3, rot_0) quaternions are "
            "stored verbatim. No axis swap, no handedness flip, no unit change: a z-up PLY "
            "reaches the renderer still z-up.",
            basis=IDENTITY,
            origin=ZERO,
            neutralised=False,
            neutralised_by="",
        ),
        AutomaticTransform(
            stage="import",
            source=BUILDER,
            summary="Subtracts the mean Gaussian centre. A pure translation, so Gaussian "
            "orientations, covariances and extents are untouched and stay correct.",
            basis=IDENTITY,
            origin=ZERO,
            neutralised=False,
            neutralised_by="Applied once by the addon and accounted for explicitly: the "
            "contract is expressed relative to the PLY origin, and the runtime verifier "
            "predicts the world AABB from the raw PLY bounds and the recorded centroid.",
        ),
        AutomaticTransform(
            stage="node_enter_tree",
            source=ORIENTATION,
            summary="When a node's basis is identity, right-multiplies by a -180 degree z "
            "rotation. It leaves the up axis alone, so it cannot make a z-up splat stand "
            "up in Godot's y-up world -- which is why an earlier fix that relied on it "
            "silently did nothing.",
            basis=GDGS_DEFAULT_CORRECTION,
            origin=ZERO,
            neutralised=True,
            neutralised_by="Splat nodes now carry this contract's explicit non-identity "
            "basis, so the identity test cannot fire. verify_alignment.gd proves the "
            "effective transform equals the manifest and fails loudly if a future addon "
            "changes that rule.",
        ),
        AutomaticTransform(
            stage="render",
            source=REGISTRY,
            summary="world = node.global_transform * centre and covariance_world = "
            "M3 * covariance * M3^T, so orientations, covariances and splat extents are "
            "transformed along with centres.",
            basis=IDENTITY,
            origin=ZERO,
            neutralised=False,
            neutralised_by="",
        ),
    )


def rejected_scales() -> tuple[dict[str, str], ...]:
    """Return metric-scale factors that exist in the repo and must not be reused."""
    return (
        {
            "value": "0.800977",
            "source": "data/scenes/corridor_straight/scene_transform.txt",
            "why": "Computed as 2.0 m divided by the Z extent of the retired COLMAP-dense "
            "Poisson mesh (scripts/splat_pipeline/blender_cleanup_mesh.py:estimate_scale). "
            "That mesh is a different asset, from a reconstruction path proven non-viable "
            "for these captures (PLAN_pipeline_visual_feedback.md). It is not the splat any "
            "scene loads, so the number carries an assumption with no evidence behind it.",
        },
        {
            "value": "1.0",
            "source": "implicit (loading the PLY unscaled)",
            "why": "COLMAP and nerfstudio normalise a similarity transform, so one "
            "reconstruction unit is not one metre. Unscaled loading is the defect this "
            "contract removes.",
        },
    )