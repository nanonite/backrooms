# Exact seed candidate: debris/window interior

Candidate source: `video-ccf9722164a0bdc8`  
Source video SHA-256: `ccf9722164a0bdc8aa0497e8f4ca16b30fcdc6b752192859fd8fef537ba5a0bb`

## Recommended frame for operator review

- Frame ID: `frame_4560`
- Zero-based decoded frame index: `4559`
- Presentation timestamp: `151.966667 s` (ffprobe `best_effort_timestamp_time`)
- Native frame size: `1280×720`
- Direct decoded PNG SHA-256: `7a2b3dd1b43478fa491447731c06b0f36fce71e2b80cbb089d3744cb02abcd0f`
- File: [`frame_4560.png`](frames/frame_4560.png)

The frame shows a debris-filled interior with a window band, roof beams, a rear wall, and cluttered floor. The windowed side and wall corner are clearly visible. This is a seed recommendation, not yet operator-approved and not a claim about source connectivity to the accepted industrial hall.

## Adjacent-frame check

Eleven contiguous frames from zero-based indices 4555–4565 (PTS 151.833333–152.166667 s) were decoded directly at native 1280×720. Their hashes and a blur/sharpness diagnostic are recorded in [`seed_candidate_manifest.json`](seed_candidate_manifest.json). Frame `frame_4560` had the highest 640×360 Laplacian-variance score in the adjacent set; the metric is only a blur diagnostic. See [`adjacent_seed_candidates.jpg`](adjacent_seed_candidates.jpg).

The wider 152–156 s probe also ranked this frame highest after 640×360 downsampling. No output has been used as Hunyuan input. No Hunyuan attempt, GPU capture, source-ledger edit, room authoring, or connector authoring has occurred.

## Next gate

Operator approval is required for this exact seed before starting the second-room panorama stage. The source has 5 of 6 authorized attempts recorded, and the remaining slot is not authorized by this seed-review package.
