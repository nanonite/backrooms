# Four-room authored connection candidate

**Review state:** the operator accepted this exact seed-166 four-room layout and authored connection after a live walkthrough. The candidate modules remain outside the shared catalog; their `catalog_admission` is still `candidate_not_admitted`. The exact #164 three-room layout is preserved as the prefix and regression reference, and its earlier approval was not extended to the new connection. `registration_accepted=false` and `scale_calibrated=false`.

## Candidate

The playable chain contains four distinct designs: the accepted #160 column room, accepted #149 pocket, accepted #163 source-textured room in a new west-back-socket adapter, and accepted #165 L-corridor in a new west-socket adapter. The old accepted scenes, layouts, snapshots, and decisions remain unchanged. The authored connection joins `R002.west_back` to `R003.west` at world position `(28.56, -1.27099, 3.10)`, with opposing X normals, a `2.0 × 2.1` design-unit opening, and `1.2` units of approach clearance on each side. The opening is game geometry chosen for this comparison; neither source video establishes this connection. The large room's unused socket and the corridor's unused perimeter are capped in standalone scenes.

The new #163 adapter preserves its accepted appearance and hall-end connection while opening a separately authored west wall. The #165 adapter preserves the accepted corridor, replaces only its west boundary with matching returns and header, and retains a closed standalone version. Both candidates reuse the accepted controller and PSX profile. No source, inference, renderer, or calibration settings changed.

The serialized layout and candidate manifest retain their build-time `review_pending` marker. The later, fingerprint-bound [`operator_review.json`](operator_review.json) records the operator's acceptance of this exact layout and connection. The static layout validator reports the build-time marker; it does not supersede the operator decision. Admission of the new adapters into the shared catalog is still pending.

See [layout diagram](layout_four_room.svg), [serialized layout](layout_four_room.json), [candidate catalog snapshot](catalog_snapshot.json), [candidate manifest](candidate_manifest.json), and [candidate adaptation record](corridor_socket_adaptation_v3.json). Full per-file dependency hashes are in the snapshot and adaptation record.

## Mechanical verification

Godot 4.6.3 CPU checks passed on the candidate and on the unchanged #164 regression scene:

| Scene | Route targets | Out-and-back distance (design units) | Floor support | SafetyNet |
|---|---:|---:|---:|---:|
| Four-room candidate | 51/51 | 107.47 | 100% | 0 |
| #164 regression prefix | 33/33 | 75.60 | 100% | 0 |
| Large-room standalone adapter | 13/13 | 41.73 | 100% | 0 |
| Corridor standalone adapter | 11/11 | 25.60 | 100% | 0 |

The four-room trace reaches the new connector from both directions and backtracks through all four room designs. Maximum observed physics step was `0.0667` design units. Standalone reset restores spawn and clears velocity. All six corridor boundaries capsule-block in its standalone scene; the large-room standalone scene closes both openings. The candidate check also found clear full-capsule approaches on both sides, continuous ray-tested floor support across the seam, matching frame mesh/collider dimensions, and rendered meshes contained by the declared module envelopes.

Negative controls behaved as intended: a temporary connector blocker prevents passage; removing the corridor floor allows the fall probe; removing the east perimeter wall permits escape. The #164 route's existing two connections remain traversable. Serialized placement-footprint validation rejects overlap; the new footprints meet at their designed socket. Conservative rendered envelopes do overlap at the door frames, by design, because their boundary slabs meet at the authored opening; that junction still needs visual review.

The #149 generator validator is intentionally not used to admit this finite comparison: it requires exactly one three-way branch, while this request is a chain, and its socket floor comparison assumes equal local floor values. The dedicated #166 validator checks this topology and compares transformed world-space socket centers/normals, alongside the frozen snapshot, all declared dependency hashes, module identities, connectivity, and non-overlapping walkable placement footprints.

Machine-readable results: [`connection_controls_final.json`](mechanics/connection_controls_final.json), [`traversal_analysis_final_v2.json`](mechanics/traversal_analysis_final_v2.json), and the final candidate route/boundary reports. The out-and-back assembly trace (including both connector crossings) is in [`assembled_final_v3/`](mechanics/assembled_final_v3/); standalone reports are in the `*_standalone_final_v2/` folders. The exact #164 regression is in [`issue164_regression_verified/`](mechanics/issue164_regression_verified/). These are runtime checks; static contract validation alone is not treated as traversal evidence.

## Visual and resource results

The guarded capture produced two fixed 1280×720 views from opposite sides of the authored doorway: [large room into corridor](captures_final/connection_large_room_to_corridor.png) and [corridor back into large room](captures_final/connection_corridor_to_large_room.png). The capture manifest records the camera poses and Godot version. The earlier failed preflight receipts remain preserved; after the operator closed the graphics client, both the visual capture and frame profile completed under the existing GPU/RAM guard. These captures document the exact candidate already accepted during the live walkthrough; they do not broaden the accepted scope.

The measured run was uncapped and sampled `RenderingServer.frame_post_draw` across 34 poses and 10,199 frames: average `239.86 FPS`, p95 frame time `4.287 ms`, and p99 `4.403 ms`. First scene-ready time was `2,352 ms`. The guarded capture run took `3.42 s`; its peak child RSS was `2.43 GB` and GPU-memory increase was `580 MB`. The frame-profile wrapper took `48.75 s`; peak child RSS was `2.43 GB` and GPU-memory increase was `583 MB`. At preflight, free VRAM was `11.43 GB` of `12.88 GB`; available system RAM was `44.26 GB` for capture and `44.03 GB` for profiling. Resource receipts and frame samples are linked in the review page and listed in `COMMANDS.md`.

## Integrity and provenance

- Candidate snapshot SHA-256: `d516b32ff16fb9f04bde3330a1eeb1c4e562c8b74d01205cf702fa03f649e54a`.
- Candidate layout file SHA-256: `85b298b3efd408007bfdd9145adb0e3bc5cc8e5850d9a2d7ecf22725fa957b18`.
- Fingerprint-bound candidate identity: `d5aaeacd623ada369b4826e576d216c19fc2829754a1630a7c2f9bdcb5b0ae0f`.
- Protected accepted input hash check: 72 files verified; see [`protected_asset_hashes.json`](protected_asset_hashes.json).
- #163 source: `data/videos/room_large.mp4`, SHA-256 `ef0ec21cd4ae7b2699d5d9ec08467eddb6d62582d659c4035dc995e78df4b418`; source frame `0013` is the direct room appearance reference, with `0049` and `0085` retained as comparisons.
- #165 source: `data/videos/corridor_corner.mp4`, SHA-256 `51abd379f94b8f84799c79927113f37c03014b41b0d5f0d4c23095d3d67587e0`; the 96-frame clip references `0001`, `0013`, `0036`, `0059`, `0085`, and `0096` (one-based IDs). Decoded frames, extraction manifest, crops, and hashes remain in the original #165 evidence and adaptation record.
- The source-visible openings belong to separate video observations. Neither establishes continuity or a connector between the #163 and #165 spaces. The world-space doorway is an authored game-layout choice.
- Both calibration flags remain false. The operator accepted this exact four-room layout and authored connection; candidate module admission remains pending.

Exact launch, validation, and guarded capture commands are in [COMMANDS.md](COMMANDS.md). Open the [review page](index.html) for the layout and evidence links.
