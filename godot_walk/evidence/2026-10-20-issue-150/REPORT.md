# Issue #150: Authored Room-Ends Candidate

Status: **operator-accepted playable design baseline; not yet admitted to the room catalog**.

This is a new playable design candidate based on the accepted #147 Hunyuan visual. It does not modify #147, the #100 source, or the tagged reference. The room shell, safety walls, walk path, and smooth column cover are authored geometry. They are not reconstructed footage. `registration_accepted=false` and `scale_calibrated=false` remain in the manifest and reports.

## Candidate

The authored room is a 9.9 by 13.8 convention-space rectangle with a continuous planar floor, four visible 2.4 m walls, and a separate column collision proxy. The perimeter path is 40.6 m one-way; the automated test follows it out and back. These dimensions are design choices under the uncalibrated #100 convention, not measured room dimensions.

The column cover is a smooth, slightly padded visual box over the existing authored collision proxy. The existing Hunyuan visual asset is unchanged. The four room walls are both visible authored meshes and matching collision boundaries. The report lists each authored surface separately from the two Hunyuan visual layers.

Layout proposal: `candidate_layout.svg`.

## CPU Verification

`walkability_report.json` records the route-only harness run:

- Perimeter traversal passed: 100% outbound, 99.51% return, 99.96% moving floor support.
- SafetyNet contacts: 0. Floor-ray support: 100% of route ticks.
- The column blocking probe passed. Four boundary-push probes contacted their named wall and stayed within the 0.12 m displacement gate.
- The collision asset contains one 2-triangle floor, one 12-triangle column proxy, and four 12-triangle boundary boxes.
- Three deliberate missing-geometry controls failed closed: removing the floor, column, or four room boundaries made the room static probe fail for an incomplete six-node room asset. Reports and control assets are under `negative_controls/`.

`hunyuan_route_scene_report.json` independently loaded the issue-150 manifest, original #147 visual, and authored collision asset in the Bevy scene. It completed the same traversal with 0 SafetyNet contacts. This report is CPU/headless and is not an FPS result.

## Visual Evidence

`candidate_contact_sheet.jpg` is built only from the nine views listed in `captures/bevy/bevy_capture_report.json`: four room ends, four column faces, and the registered frame-0152 camera anchor. Authored wall and column surfaces are included in the Bevy captures. This evidence shows the chosen candidate from fixed review poses; it does not establish that its composition or scale is desirable.

Capture used Bevy 0.18 / Vulkan on the RTX 4070 Ti after the built-in RAM/VRAM and competing-GPU-process checks passed. No inference or training ran. Registration and scale remain unaccepted.

The release interactive smoke run loaded the room and wrote `interactive_play_report.json`. In this X11 session the cursor could not be grabbed, and the report had only 30 eligible frame intervals with a median near 1 s. A matched #147 baseline showed the same cursor-grab failure and similarly slow intervals, so this is not evidence of a regression caused by #150; live performance still needs a normal desktop check. No FPS pass is claimed. The interactive session exited automatically after its 60 s timeout.

## Operator Review

On 2026-10-20, the operator accepted #150 for now: the source-derived walkthrough preserves a useful core perspective, while exact video-to-Bevy architectural precision is not a requirement for this design pipeline. The visible far side of the column is still unfinished and remains room-specific art polish; it does not block accepting this playable baseline.

The shell, floor, collision boundaries, and column cover remain authored proposals. Registration and scale remain unaccepted. The candidate is not yet catalog-admitted or stitched. #148 owns catalog admission and any connector experiment; the #145 footage inventory does not establish a physical connection to the tagged reference zone, so a designed connector must be labeled as authored and tested before use.
