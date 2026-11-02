# Chainlink #167 — industrial hall room candidate v3

Recorded: 2026-11-01T20:58:38.415588+00:00

## Review status

The operator accepted this candidate as one bounded playable interpretation of the source hall and judged the 512×256 panorama adequate for broad layout. Resolution refinement is deferred until a larger room library exists. This acceptance does not admit the candidate to the catalog or establish metric scale, source-video connectivity, or approval of other candidates. `registration_accepted=false`; `scale_calibrated=false`.

Decision artifact: [`operator_review.json`](operator_review.json), SHA-256 `9e44f8caaef2f7a3d1abf49076baba8bb7991a8dcb900559a9c3eb550b51bab6`.

Candidate identity: `d3e84f32e439a3f5e0dad242ccd80b63f23eed3d49d7cb236059b5f323e26ca5`  
Adaptation record: [`adaptation_candidate.json`](adaptation_candidate.json)  
Review page: [`index.html`](index.html)  
Layout: [`layout.svg`](layout.svg)  
Contact sheet: [`contact_sheet_v3_final.png`](contact_sheet_v3_final.png)

## Source evidence

- Video: `data/videos/GoPro Awards_ Haunting FPV Drone Flight Through Abandoned Building.mp4`  
  SHA-256: `ccf9722164a0bdc8aa0497e8f4ca16b30fcdc6b752192859fd8fef537ba5a0bb`
- Seed: frame `frame_1097` (zero-based index `1096`), presentation timestamp `36.533333 s`, decoded directly from the source at `1280×720`.  
  SHA-256: `61ca4b37295a948c8aa61686c912da51c7cff6dd16aac012b5c2f02bf051b2af`
- Hunyuan attempt 005 panorama: `512×256`, SHA-256 `ab6ed18a33d959d53612f63d5bbc0700fd6ff89220d4a4cfb0bccdccdaca5213`. It provides a useful broad hall/post/roof composition reference, but its resolution and lack of parallax make it unsuitable as walkable scene geometry, room projection, or detailed surface texture.

The room uses two direct rectangular crops from the seed frame: floor `[760,505,1080,650]` and window grid `[640,297,795,379]`; neither was resized or color-edited. Wall `[742,186,830,278]`, roof `[430,145,650,248]`, and post `[816,240,870,464]` crops were sampled but not used as final textures because they contain surrounding scene context. The other surfaces use authored flat materials.

## Candidate design

The candidate is one closed hall shell with an authored footprint of `16×13` Godot design units. These units are not calibrated to meters. It has a floor at `Y=0`, an authored roof underside at `Y=4.78`, four closed perimeter walls, a far-wall window cue, six square support posts in a three-by-two rhythm, a low slab obstacle, and simple roof beams/light panels. Collision uses separate floor, perimeter, post, and slab bodies. The safe spawn is `[0,0.6,4.1]`; `R` resets the player there.

The partially seen far-right source gap remains an unknown video observation. The candidate closes all four room boundaries and declares no authored sockets. It makes no claim about video connectivity or a recovered full floor plan. The panorama itself is not rendered in the room, so it does not slide as a fixed image while the player moves. Earlier v1/v2 panorama and crop experiments remain preserved in their own folders.

## Verification

Godot `4.6.3.stable.official.7d41c59c4` standalone test passed spawn support, floor ray, four boundary rays, support-post capsule collision, walk and backtrack, no escape, safe reset, missing-floor negative control, and open-boundary negative control. Full capsule-clear area coverage was not measured; the adaptation record leaves the spawn-connected area measurement pending.

Test receipt: [`standalone_test_receipt_v3_final.json`](standalone_test_receipt_v3_final.json), SHA-256 `2abbee417d8b20717697cb3923fe77032b9583d78bd1e85b0e4f911c342d2fcf`.

The guarded Vulkan capture used the existing GPU/RAM preflight and completed in `2.937 s`. At preflight, no GPU compute applications were active; available VRAM was `11687428096` bytes and available RAM was `49763573760` bytes. Godot child-group peak RSS was `547094528` bytes; sampled GPU use rose from `759169024` to `912261120` bytes (delta `153092096` bytes). These are capture-process measurements, not Hunyuan measurements.

The 1152×648 capture profile reported scene load `8.417 ms`, instantiation `0.041 ms`, static Godot memory `54295833` bytes, and display-synchronized frame intervals with mean `4.167 ms`, p95 `4.241 ms`, p99 `4.317 ms` across `300` samples. The timing includes display sync and is not an uncapped throughput claim.

Final captures:
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/spawn_toward_windows.png` — `2befe3e514b8f6cee79a2f851fa6872037a2bd8811235419186ecc61d718aed7`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/support_rows.png` — `81c436f7e958ff90adf40f675bb6940ffec0ce90c739db1b92804de44a15614c`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/roof_grid.png` — `7594e7b2f54b4b48abf5a2d32efefeded4e20fd346df741e3cd006013e9790a1`
- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/captures-v3-final/far_boundary.png` — `9e5ba6cd00396773a34ad3e98e7631e2b329bb5d96e70d948982869c6e8b96b6`

Capture resource receipt: [`capture_resource_run_v3_final.json`](capture_resource_run_v3_final.json), SHA-256 `b8e36f0cf136b4f1f397743d228cfa00c438e2cfafeb2232275f0387239af958`. Capture manifest: [`captures-v3-final/capture_manifest.json`](captures-v3-final/capture_manifest.json), SHA-256 `fa4be364430f22bfbb39dc42a2aca55108c4751a19ebad5611aa63857e6456b3`.

## Run

From the workspace root:

```sh
godot4 --path godot_walk res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/room.tscn
```

Use WASD and the mouse to walk/look; press `R` to reset. No new source video or Hunyuan inference was run during room authoring.

## Recorded operator direction

The operator accepted the six-support, closed 16×13 design-unit shell as the first playable interpretation. The low panorama resolution is acceptable for this layout pass; revisit it after the room library grows. Keep the uncertain far-right gap closed until separate evidence or an authored connector decision supports a change.
