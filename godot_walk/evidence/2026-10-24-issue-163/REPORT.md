# Issue #163 — distinct source video room candidate

## Result

The operator accepted this playable Godot room as an authored room baseline.
It uses direct source-video texture crops on manually authored PSX room
geometry. It is not a Hunyuan-generated room: every bounded Panogen attempt
stopped before producing a panorama, so SceneGen was not run. The acceptance
covers this room design and walkthrough, not metric calibration, video
registration, or catalog admission. `registration_accepted=false`,
`scale_calibrated=false`, and `operator_approved=true`.

## Video evidence and authored choices

The distinct source is `data/videos/room_large.mp4` (SHA-256
`ef0ec21cd4ae7b2699d5d9ec08467eddb6d62582d659c4035dc995e78df4b418`), a
1920×1080, 24 fps, four-second clip. The previous room uses
`data/scenes/corridor_travel/video.mp4`; its hash and the distinction are
recorded in `source_manifest.json`.

Frame 0013 (0.5 s; decoded frame index 12) directly shows wallpaper, a column,
ceiling grid/lights, a carpet-like floor, and an open view into a passage. It
does not establish room bounds, metric scale, unseen wall positions, camera
intrinsics, or connectivity to another room. Frames 0049 and 0085 are retained
as comparisons. `source_candidates_contact.jpg` shows three sampled frames
from each of six local videos.

Four material images are rectangular pixel crops from frame 0013, with no
resizing, color change, or synthesis: wallpaper `(1490,390)-(1830,650)`, floor
`(1060,810)-(1430,1040)`, ceiling `(790,10)-(1050,155)`, and column face
`(466,330)-(590,720)`. Their hashes are in
`source_textures/crop_manifest.json`. The seed image itself is the full decoded
source frame; no Gaussian render is used.

The room shell, single box column, open passage, and hallway are authored
proposals. The layout has arbitrary uncalibrated design dimensions. The
passage is part of this standalone room, not a tested connector to another
catalog module. `layout_proposal.svg` labels evidence separately from these
design choices.

## Hunyuan attempt

HunyuanWorld is the pinned local Track A runtime, offline with cached weights.
Panogen used the direct frame 0013 seed, FP8, seed 42, and the upstream 80° FOV
default as an explicitly unmeasured assumption. Attempts were automatically
bounded by GPU/RAM checks and timeouts:

| Attempt | Duration | Outcome |
| --- | ---: | --- |
| 1280×640 | 91.6 s | Guard stopped at 101 MiB free VRAM during the VAE stage |
| 1024×512 | 85.7 s | Guard stopped at 2823 MiB free VRAM (3 GiB cutoff) |
| 768×384 | 79.5 s | Guard stopped at 1849 MiB free VRAM (3 GiB cutoff) |
| 768×384 final | 78.5 s | Guard stopped at 1874 MiB free VRAM (2 GiB cutoff), before panorama generation |

The per-run status and resource samples are under `worldgen/`. No panorama,
SceneGen mesh, or Hunyuan visual was produced. Do not rerun inference without
more GPU headroom. The authored room below is the reviewable fallback, not a
claim that the Hunyuan leg succeeded.

## Godot implementation and checks

`issue163_room.tscn` uses Godot 4.6.3, the existing player/controller, the
project PSX compositor, and the pinned URSC material preset. Source-textured
visuals are separate from authored collision. The one column has its own
obstacle collider. One L-shaped floor visual and one ceiling visual keep the
room/passage junction continuous; floor collision uses two shapes under one
named floor body.

The scene contract test passed. The bounded route verifier passed with:

- 35.733 m out-and-back route;
- 100% floor support, zero SafetyNet contacts, and 0.0667 maximum step;
- 117.08 m² estimated connected walkable area under the arbitrary scene-unit
  convention; this is not calibrated physical area.

Boundary-removal and floor-removal negative controls both produced the
expected verifier failures in `mechanics_v2/`. The final repeated mechanics
result is `mechanics_final/physics_candidate.json`.

Seven Vulkan views at 960×540 and 12 settle frames are in `captures_final/`.
The capture process completed with 549 MB peak child RSS and a 3 MiB GPU
memory increase over its measured start. The capture preflight found no other
compute applications. FPS was not measured.

## Operator decision

The operator approved the authored source-textured room for use as the
distinct-source room baseline. The room remains outside the module catalog
until the workflow task records its contract and provenance. The Hunyuan stage
remains blocked on GPU capacity; the accepted room does not claim a generated
panorama or mesh.

## Reproduction and review

Open `index.html` or `candidate_contact_sheet.jpg`, then run the live candidate
from the workspace root:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://evidence/2026-10-24-issue-163/issue163_room.tscn
```

Use WASD and mouse to walk; Escape releases the pointer. Review the column,
source-texture mapping, authored passage/hallway, and whether the distinct
source video is useful for the next Hunyuan attempt. The room is accepted as an
authored design baseline; it is not calibrated, registered to the video, or
catalog-admitted.

## Key hashes

| File | SHA-256 |
| --- | --- |
| `issue163_room.gd` | `61c2c9506a63dcdccda1c262dfa0474c1abc074e12d8447272b9fce7b9a8ef73` |
| `issue163_room.tscn` | `987d4e173705b989c2e831481bc4b63c5721764b7ab0c26af5f418cc28a32d12` |
| `room_large_frame_0013.png` | `b75558f58ac9ccd169e444c9978b961179ca5bc2b0d77db97acd81aa65e842ae` |

