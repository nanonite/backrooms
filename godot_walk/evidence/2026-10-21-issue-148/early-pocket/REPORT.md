# Early-Pocket Module And Connector

## What It Is

The #145 inventory's candidate C appears in frames 0013-0027 as a gap between patterned partition ends with a darker wall/floor beyond. The source footage does not show the camera crossing the gap or establish what lies beyond it. This module is a new authored room inspired by that view; it is not a reconstruction of a second room or a hallway.

Standalone footprint is 6.0 x 13.8 convention-units, with a closed four-wall shell, separate collision floor/walls, and no column. Its west wall is closed. A separate assembly adaptation places it east of #150 and authors a 3.5 m hall with aligned 2.4 x 2.4 m openings. The socket, room dimensions, placement, hall, and connectivity are design proposals. They do not update source registration or scale calibration.

The existing #150 room and collision assets are not edited. The assembly uses `assembled_connector_collision.glb` and `assembled_review_visual.glb` as separate review assets. The assembled collision GLB contains one continuous 2-triangle floor, the existing #150 column proxy, four outer boundaries, and six authored interior wall pieces that leave the two openings.

## Review

Contact sheet: [candidate_contact_sheet.jpg](generated/captures/assembled_connector/candidate_contact_sheet.jpg)

Layout proposal: [authored_assembly_layout.svg](authored_assembly_layout.svg)

The capture is a flat-color authored shell study with patterned wall strips, grid ceiling, and brown floor. It uses no source-frame texture, Hunyuan visual, or Gaussian splat. The screenshots show the two authored openings and route but do not claim source connectivity.

To walk the assembled proposal from the workspace root:

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play --issue148 --play-timeout-seconds=600 --play-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/assembled-interactive-report.json
```

To inspect the pocket as an independent closed room:

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play --issue148-standalone --play-timeout-seconds=600 --play-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/standalone-interactive-report.json
```

## Validation

The standalone room and assembled route each pass outbound and return traversal, collision-boundary checks, and the shared controller checks. The assembled route has 100% outbound progress, 99.21875% return progress, 99.93691% moving support, zero SafetyNet contacts, and 0.00313 m maximum sampled vertical step. The clear opening is 2.4 m wide and 2.4 m high; its floor is continuous across the whole authored assembly.

The #150 column-block and four exterior lateral-push tests pass. Two negative controls fail closed: a solid wall across the authored opening blocks the route; deleting the connector floor causes route failure, 79.245% support, and one SafetyNet contact.

Resource and visual metrics are in `generated/early_pocket_scene_report.json`, `generated/assembled_connector_scene_report.json`, and `generated/captures/assembled_connector/bevy_capture_report.json`. The eight-view Vulkan capture ran with a 10,314 MiB free-VRAM preflight and zero GPU compute jobs. These timings are not an FPS benchmark. All calibration flags remain false.

The operator review target is the assembled walk, not source-video connectivity. #148 remains open pending that review.
