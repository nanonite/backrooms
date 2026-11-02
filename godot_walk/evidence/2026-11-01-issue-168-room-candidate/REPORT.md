# Issue 168 — debris-window rock-room candidate

## Candidate

This is one standalone, pending-review room adaptation for `video-ccf9722164a0bdc8`. The operator-approved Hunyuan attempt-006 panorama is used as a composition reference only; it is not rendered as a background. The operator asked for a room with many rocks, so the candidate uses an authored low-poly boulder and gravel field around a clear central lane.

Candidate identity: `016fab6e6cc1edff5088bb6da3b81fdf0d8bca5bdabb70b62cb11476cc9f8214`. The 43-entry dependency manifest, source-frame/crop hashes and immutable catalog/contract references are in `adaptation_candidate.json`.

The source video directly shows high windows, painted walls, concrete beams, and mixed floor debris in the selected frames. It does not establish that the floor debris is natural rock. The rocks are an authored PSX interpretation guided by the panorama and operator direction. The candidate has a closed roof and four closed perimeter walls. The visible window band is only an overlay: the wall and collider continue behind it. No opening, connector, or relationship to the dark passage in frame 4936 is asserted.

The layout diagram is explicitly an authored proposal, not a recovered floor plan. Its 12×10 dimensions are uncalibrated design units. `registration_accepted=false` and `scale_calibrated=false` remain unchanged. The candidate is not admitted to the catalog.

## Source provenance

The approved Hunyuan seed is `frame_4560` (zero-based index 4559, PTS 151.966667 s), directly decoded from the source video. SHA-256: `7a2b3dd1b43478fa491447731c06b0f36fce71e2b80cbb089d3744cb02abcd0f`.

The direct-source context sequence is `frame_4336` (144.5 s), `frame_4486` (149.5 s), `frame_4560` (151.966667 s), `frame_4636` (154.5 s), `frame_4786` (159.5 s), and `frame_4936` (164.5 s). These samples show selected views only. The relation between the final dark passage and this candidate remains unknown. The source contact sheet and direct crop sheet are included alongside the captures.

## Geometry and collision

- Authored walkable rectangle: X=[−6,6], Z=[−5,5], floor Y=0.
- Authored ceiling underside: Y=3.92; no ceiling collider.
- Safe spawn/reset: [0,0.6,3.8], using the existing player controller.
- Four separate perimeter collision bodies; all edges closed.
- 72 large collidable low-poly boulders, one additional pathside boulder, and one pier collider.
- 336 seeded visual-only gravel meshes. The continuous floor collider remains beneath them.
- No sockets or tested connectors.

The floor uses a flat PSX concrete base. The direct floor crop was kept in the provenance bundle but not repeated across the room because it carries a strong perspective debris pattern. The wall and window crops are used locally. The roof is an authored closed underlay and beam grid.

Three pre-review visual passes and their contact sheets are logged in `ITERATIONS.md`; the first two capture folders are retained as iteration evidence.

## Verification

The Godot 4.6.3 headless test passed spawn support, floor and boundary rays, four capsule boundary probes, boulder collision, central-lane traversal and backtracking, reset, plus missing-floor and open-boundary negative controls. This is measured runtime evidence for those checks, not proof of an exhaustive capsule-clear area map.

The guarded Vulkan review capture contains five 1280×720 views. At a 60 FPS engine cap with VSync disabled, 300 sampled process-frame intervals measured 16.666 ms mean, 16.687 ms p95, and 16.706 ms p99. Scene load measured 9.56 ms, procedural `_ready` build 34.12 ms, and Godot static memory 58,558,498 bytes. The guarded process reached 554,926,080 bytes RSS and 720,371,712 bytes GPU memory (229,638,144 bytes above its start). The capture completed in 9.54 s on an RTX 4070 Ti.

These measurements cover the capture run at 1280×720. The capture loop is a bounded rendering sample, not a long gameplay stress test. No exhaustive connected-area measurement or connector traversal was performed.

## Review status

Standalone candidate review is pending. No catalog admission, new room connection, or source-video connectivity is claimed. The accepted #167 room and its approvals are unchanged.
