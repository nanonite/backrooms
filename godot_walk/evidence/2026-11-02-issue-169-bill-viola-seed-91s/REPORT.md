# Issue #169: Bill Viola source-to-room candidate

## Review status

A bounded single-room Godot candidate is playable and ready for operator review. Its adaptation record is `candidate_pending_review`; it is not admitted to the room catalog. `registration_accepted=false` and `scale_calibrated=false` remain unchanged. The model-assisted worker/reviewer loop is not proven by this manual fallback, so #169 remains open.

## Source and seed

- Source ID: `video-b9161c467ed2d30a`
- Source: `data/videos/Bill Viola 'The Sleep of Reason' 1988.mp4`
- Video SHA-256: `b9161c467ed2d30aefa6bf2969c2ed63fc79a387d93016197e356e9bf531ddaa`
- Native video: 1280×720, 30 fps, 5,459 frames, 182.021224 s
- Selected direct-source seed: frame 2731, zero-based index 2730, PTS 91.000000 s
- Seed SHA-256: `b5e623658f40f3f5fe195dbffb475d941755a1b4ecbcfd78aa838f4539203822`
- Adjacent blur check: frames 2730–2732 at 90.966667, 91.000000, and 91.033333 s are nearly identical; frame 2731 remains the selected seed.
- Additional direct context frames: frame 0820 at 27.3 s, SHA-256 `96919aefe094b7171c93a98fbef3feec384ec476030d4924ce4fc3ba00df2f86`; frame 4642 at 154.7 s, SHA-256 `0a00dc9220a1f7a36898d3180ee100ffa35132eaca37c1b5727bcaa7d5c8bcea`.

The three sampled views show a recurring subdued room: pale walls, dark carpet, and a dresser with a lamp, lit television, and vase/flowers. The operator described the entire clip as being in this room; that suitability direction is recorded. The selected frames do not establish the room's dimensions, scale, hidden boundaries, openings, ceiling, adjacent spaces, or connectivity.

The seed was decoded directly from the source video at native resolution. The room uses direct rectangular crops from that frame for wall, carpet, dresser-front, and television-screen appearance. The vase/flower crop is retained as a modeling reference. Crop coordinates, operations, and hashes are in the crop manifest.

## Model attempts and manual fallback

Two earlier one-shot free vision requests failed with OpenCode HTTP 429 and returned no frame selection. One guarded Hunyuan attempt used the direct seed and produced a 512×256 panorama in 199.586 s. It depicts a bright glass-walled space and does not preserve the source's dresser-centered composition; it was rejected as a room-matching input. The operator explicitly directed that no more free models be tried and that the work continue manually from direct source frames. No further model request or Hunyuan attempt was made.

The attempt's peak process-group RSS was 40.7 GB and peak GPU use was 1.60 GB. Available host RAM reached a minimum of 18.3 GB; free swap grew by 14.7 GB; minimum free VRAM was 10.8 GB. Full receipts and the rejected panorama remain at `godot_walk/source_library/sources/video-b9161c467ed2d30a/hunyuan/attempt-001/`.

## Authored room candidate

The candidate is one closed, single-level 8×8 Godot-world-unit room. The closed shell, dimensions, furniture depth, object proportions, near/side walls, ceiling, and safe spawn are authored gameplay choices. They are not recovered room geometry or calibrated measurements. The dresser arrangement sits against the negative-Z wall; low-poly authored geometry supplies the dresser body, lamp, CRT cabinet, vase, stems, leaves, and flower heads. Source crops supply the far wall, floor, dresser front, and television screen appearance. The existing player/controller and `library-psx-ursc-1.5-native-compositor` profile are used.

The room has an authored floor at y=0, a declared authored clearance up to y=2.8, and a conservative rendered shell bound from `[-4.12, -0.20, -4.12]` to `[4.12, 2.96, 4.12]`. It has four closed perimeter walls, a ceiling collider, a dresser collider, and a separate SafetyNet. It has no opening, authored socket, tested connector, splat layer, or Gaussian collision. The layout diagram marks the shell as authored and the dresser arrangement as source-observed.

The candidate is recorded against the immutable v3 catalog snapshot and adaptation contract. Its static dependency graph includes the Godot scene, player/controller, PSX scripts/shaders, and shader includes. All five direct crop files are separately fingerprinted because the current static graph does not inspect `Image.load_from_file`. That limitation is explicit in the adaptation record; static validation does not establish runtime geometry.

## Verification

Godot 4.6.3 standalone checks passed:

- 225/225 downward floor-ray probes on a 0.5-unit grid.
- Four perimeter-wall ray checks and the dresser collider check.
- Walk movement and R reset to the declared spawn, with floor support.
- Missing-floor and open-boundary negative controls both detected their removed collision.
- Adaptation v3 schema, frozen-contract/snapshot binding, dependency hashes, static polygon/bounds/spawn checks, and candidate identity validation passed.

These are bounded runtime checks, not a calibrated room survey or proof of source-video topology. Connected walkable area was not measured.

Two earlier receipts (`standalone_test_receipt_v4.json` and `_v5.json`) record a discarded attempt to switch the direct crops to `preload()` before Godot had imported those new PNG resources. Those runs failed to load the room and their follow-on checks are invalid. The implementation reverted to the tested raw-image loading path; the successful final run is `standalone_test_receipt_v6.json`.

## Render and resource measurements

The guarded Vulkan capture completed on Godot 4.6.3. GPU preflight found no competing compute applications. The capture took 2.764 s and recorded four views: spawn toward dresser, left oblique, right oblique, and back toward the authored closed boundary.

- Scene ready: 47.287 ms
- 300-frame capture profile after 120 warmup frames: mean 4.165 ms, p95 4.385 ms, p99 4.780 ms
- Peak child RSS: 548,974,592 bytes (about 523 MiB)
- Peak GPU memory use: 896,532,480 bytes (about 855 MiB), a 186,646,528-byte increase from capture start

This is a bounded capture profile, not a broad gameplay benchmark. The raw capture and guarded resource receipt are linked from `index.html`.

## Review files and reproduction

- Review page: `index.html`
- Contact sheet: `room_comparison_v2.jpg`
- Layout and uncertainty diagram: `../../source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/layout.svg`
- Candidate record: `../../source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/adaptation_candidate.json`
- Launch and validation commands: `../../source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/COMMANDS.md`

From the workspace root, launch the playable candidate with:

```bash
godot4 --path godot_walk res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/room.tscn
```

The candidate remains pending operator visual review and catalog admission. No other source video was processed. No files were committed and #169 remains open.
