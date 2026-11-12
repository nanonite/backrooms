# gmap-0.13.0 visual evidence

Generated from the real 0.13.0 generator path. Capture PNGs are kept outside the repository; this text log records each path and SHA-256. Map, fill, shape-room, layer, and module metadata remain text/JSON only.

## Commands and results

- Python suite: `python3 -m pytest -q godot_walk/scripts` — 1,278 passed, 5 skipped, and 58 subtests passed in 837.86 seconds (exit 0).
- Headless walkthrough for seeds 1, 2, 3, 32, 279: `godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- --map=res://room_catalog/generative_maps/gmap-<seed>-gmap-0.13.0.json --rooms=res://room_catalog/shape_rooms/gmap-<seed>-gmap-0.13.0/index.json` — exit 0 for all five.
- Render capture for each seed: `DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 --script res://scripts/capture_surface_layer.gd -- --map=res://room_catalog/generative_maps/gmap-<seed>-gmap-0.13.0.json --rooms=res://room_catalog/shape_rooms/gmap-<seed>-gmap-0.13.0/index.json --out=/tmp/gmap-0.13.0-captures-final/seed-<seed>` — exit 0 for all five; capture counts: 6, 7, 6, 6, 7 respectively.
- Artifact text/schema scan: `test_v13_metadata_and_layer_artifacts_remain_text_only` in `godot_walk/scripts/test_gmap_template_v13.py` checks all map/fill/SVG/shape-room/module-metadata artifacts as UTF-8 text, parses JSON, and rejects image-named fields and NUL bytes; included in pytest.

## Headless walkthrough per-seed results

| Seed | Exit | Result |
|---:|---:|---|
| 1 | 0 | PASS: 12 generated rooms; 30/32 directional edge sweeps; flood reached 14/14 expected cells; 0/42131 floor samples missing. |
| 2 | 0 | PASS: 14 generated rooms; 32/32 directional edge sweeps; flood reached 15/15 expected cells; 0/50290 floor samples missing. |
| 3 | 0 | PASS: 13 generated rooms; 32/32 directional edge sweeps; flood reached 14/14 expected cells; 0/31219 floor samples missing. |
| 32 | 0 | PASS: 12 generated rooms; 26/26 directional edge sweeps; flood reached 14/14 expected cells; 0/16529 floor samples missing. |
| 279 | 0 | PASS: 13 generated rooms; 31/32 directional edge sweeps; flood reached 14/14 expected cells; 0/28472 floor samples missing. |

Focused validation and reverb tests: `python3 -m pytest -q godot_walk/scripts/test_gmap_template_v13.py godot_walk/scripts/test_gmap_reverb.py` — 23 passed (exit 0). The edge denominator counts two directions for ordinary links and one upper-to-lower traversal for each intentional drop. Every map has strong graph connectivity and reaches every expected walkable cell; the drop remains one-way by design.

## Per-seed visual review and captures

### 1

Headless result: exit 0. Render result: exit 0. I inspected these captures in a contact sheet; the materials, wear, lighting, doorway openings, and elevation transitions are visible. The industrial concrete capture for seed 279 retains a bright foreground surface that looks incomplete.

| Capture path | SHA-256 | Observation |
|---|---|---|
| `/tmp/gmap-0.13.0-captures-final/seed-1/dark_wing_wear2_c04.png` | `bf733a9e2a4bf90e904fca065fe6a087a5bf44f937937c2c2fd63dcdd5a3308e` | Low-lit dark-wing room with visibly worn floor and ceiling fixtures. |
| `/tmp/gmap-0.13.0-captures-final/seed-1/surface_backrooms_yellow_wear0_c02.png` | `fe5ec4cbb30eee72b1d9ff0a11b0d408e45ed3330e2fe4a2d45c6a0c2f071e8c` | Bright tan carpet room with a clear doorway and ceiling fixtures. |
| `/tmp/gmap-0.13.0-captures-final/seed-1/surface_backrooms_yellow_wear1_c06.png` | `dc9b3f9509a4ecf6e35f4c7720dd1a72f9b8549f13bcad5db80ccf914c9cea80` | Broad yellow room; worn floor and several ceiling lights are visible. |
| `/tmp/gmap-0.13.0-captures-final/seed-1/surface_backrooms_yellow_wear2_c04.png` | `020263cf3558ee8f43fcc980df27c1eff84017e1c9fafbf77a13a35e0128dd93` | Darker yellow room with visibly distressed floor and wall texture. |
| `/tmp/gmap-0.13.0-captures-final/seed-1/surface_tiled_institutional_wear2_c11.png` | `579ae0305768c6a9405150aa1821e06bb657085e9f45a1e9e89981f65a557b5c` | Tiled institutional room with dark, heavily worn floor. |
| `/tmp/gmap-0.13.0-captures-final/seed-1/surface_wood_parquet_wear1_c05.png` | `527c5d29786eac2b1c0df5e0331140107e3ae934a2f6e07bc76838ffe1e631c6` | Brown parquet floor in a multi-opening room; ceiling texture is visible. |
### 2

Headless result: exit 0. Render result: exit 0. I inspected these captures in a contact sheet; the materials, wear, lighting, doorway openings, and elevation transitions are visible. The industrial concrete capture for seed 279 retains a bright foreground surface that looks incomplete.

| Capture path | SHA-256 | Observation |
|---|---|---|
| `/tmp/gmap-0.13.0-captures-final/seed-2/dark_wing_wear2_c07.png` | `005ce15eb783fe2da0e077671f67fb5a0e0b93f35e9cd0b094e4aa91e9958994` | Low-lit dark-wing room with visibly worn floor and ceiling fixtures. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_backrooms_yellow_wear0_c04.png` | `21b4bb58522a370eef1a02070ab828426ff521c53f7a4d44c298c622f95cf029` | Lit yellow room with clean floor and a long opening ahead. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_backrooms_yellow_wear1_c09.png` | `0fc862f23ba699dfc628152f009873833224d9dea91c3fdd4a9bf0a68a12b1f7` | Worn yellow corridor with multiple side openings. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_backrooms_yellow_wear2_c03.png` | `c9f5159c50538d63405f3566f29ff4540be9f821c9105e9168c8f1c61804735d` | Dim, distressed yellow room with dark floor patches. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_tiled_institutional_wear1_c06.png` | `51df0cb4b70d749319fde7480a640ac11371472248bf0ce3bca9eafeb28e4230` | Clean tiled room and doorway; floor grid is clearly visible. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_wood_parquet_wear1_c11.png` | `4f646e814818f24575305b2b3af07b993a65d0ff29f9e0111164eb594815b8ec` | Capture is mostly dark geometry with only a narrow bright strip visible; camera alignment is poor. |
| `/tmp/gmap-0.13.0-captures-final/seed-2/surface_wood_parquet_wear2_c07.png` | `b35b1baa51d5a58b2807c11cf968f92b23316cce2af79f8b9adc6995d185f044` | Narrow dark corridor with strongly worn parquet floor. |
### 3

Headless result: exit 0. Render result: exit 0. I inspected these captures in a contact sheet; the materials, wear, lighting, doorway openings, and elevation transitions are visible. The industrial concrete capture for seed 279 retains a bright foreground surface that looks incomplete.

| Capture path | SHA-256 | Observation |
|---|---|---|
| `/tmp/gmap-0.13.0-captures-final/seed-3/dark_wing_wear2_c04.png` | `bb5797cece59ecc121572405f3713aee98939d6bd2af5d3347f0245b2748e55f` | Low-lit dark-wing room with visibly worn floor and ceiling fixtures. |
| `/tmp/gmap-0.13.0-captures-final/seed-3/surface_backrooms_yellow_wear0_c00.png` | `ffcecad77e143a05c5648f70a1672453a77e81f5ed81561bb8e7eace42068a79` | Bright yellow room with two visible openings. |
| `/tmp/gmap-0.13.0-captures-final/seed-3/surface_backrooms_yellow_wear1_c05.png` | `994238f7ffa2e2b56f5789e38bd884739c5e65aff7dbb39ed7f689b942873f95` | Worn yellow passage with an opening to a neighboring room. |
| `/tmp/gmap-0.13.0-captures-final/seed-3/surface_backrooms_yellow_wear2_c02.png` | `8b5dbe15b7aa94b3e586b8a397bbd51a616b8ebf7a822d936e24caebe2500729` | Yellow room with a stepped floor transition and damaged surfaces. |
| `/tmp/gmap-0.13.0-captures-final/seed-3/surface_industrial_concrete_wear1_c06.png` | `17a22029293a16d511e597de075f487e92e400a4526b9f31be7f98f3f1001fa3` | Industrial concrete scene has an oversized white foreground surface and incomplete room appearance. |
| `/tmp/gmap-0.13.0-captures-final/seed-3/surface_tiled_institutional_wear0_c08.png` | `70599e9e2d25f214f531e8f7918dda3d089691774d06eee57f5027091faa4c27` | Bright tiled room with clean grid floor and doorway. |
### 32

Headless result: exit 0. Render result: exit 0. I inspected these captures in a contact sheet; the materials, wear, lighting, doorway openings, and elevation transitions are visible. The industrial concrete capture for seed 279 retains a bright foreground surface that looks incomplete.

| Capture path | SHA-256 | Observation |
|---|---|---|
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_backrooms_yellow_wear0_c10.png` | `0168dc0daefbdc5b0338b727eae25305ba90e1a97a82fde6fbd4a17c138b223a` | Clean yellow corridor with a lit ceiling and a distant opening. |
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_backrooms_yellow_wear1_c01.png` | `9ad262ab17eb3dba875295ac38bb4c609e3f83d94d5cc7ca4754685b1b3301be` | Worn yellow corridor with side opening and ceiling lights. |
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_backrooms_yellow_wear2_c06.png` | `b2d7c7445f224d2be2861688ba1bebc29bd897049cf1a7a45564a01c554d4249` | Distressed yellow room with scuffed floor. |
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_metal_service_wear0_c05.png` | `39943a14d3cb927d7bfad4a49b4ebb4244aaebdbae4d8432c3d0383c5375e0c6` | Metal service floor and concrete walls visible at a doorway. |
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_tiled_institutional_wear1_c07.png` | `c4b99a52796bd9b0bd5aa23c8405962a6ae9b37204f3d2b9643a17ee5f2ebafd` | Narrow tiled corner with clean wall grid and worn floor. |
| `/tmp/gmap-0.13.0-captures-final/seed-32/surface_wood_parquet_wear0_c02.png` | `a87a8fdf369d31d0104f7e1b72785ba63269b755156a732c0afc74ab17a50bd8` | Clean brown parquet corridor with repeated floor boards. |
### 279

Headless result: exit 0. Render result: exit 0. I inspected these captures in a contact sheet; the materials, wear, lighting, doorway openings, and elevation transitions are visible. The industrial concrete capture for seed 279 retains a bright foreground surface that looks incomplete.

| Capture path | SHA-256 | Observation |
|---|---|---|
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_backrooms_yellow_wear0_c00.png` | `959e7aa6e994d079ec19377534fb9702d31cd501ed9fef5d784999d312349f7d` | Yellow room with multiple doorways; a white floor strip intrudes at the lower edge. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_backrooms_yellow_wear2_c02.png` | `d783791176ea04415555761c4e6d9eac2f1fd23c2e2a869837578c6e81399fd4` | Yellow room with damaged floor texture and ceiling fixtures. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_industrial_concrete_wear0_c07.png` | `ac97548bd5fe10fe7aac59081e3184d5728730cf71fdd5b221a50dc5f197da0f` | Large white foreground plane obscures much of the room; visibly incomplete geometry. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_industrial_concrete_wear1_c03.png` | `7573082194c73a1e97385409d4ef13605ba9dc98cd267a5eb323315dfd53b1a9` | Concrete corridor with white upper surfaces and doorway ahead. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_metal_service_wear0_c09.png` | `ba1d5dfd8ad71af4feb4aeac306e2c1ee0dedf8c61abb7ff919b03f2e0599c45` | Narrow metal service stair passage with metal floor grid. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_wood_parquet_wear0_c06.png` | `705416087cd8648045c4ea0542fe8ffbaa991d1d198d1baa0feeb0aab913f7ee` | Brown parquet corridor with clear doorway and comparatively clean surfaces. |
| `/tmp/gmap-0.13.0-captures-final/seed-279/surface_wood_parquet_wear1_c11.png` | `046f8182d56daeeca0b2e0adfa9bf9bbcf4bc164a21fbf23c0269455b84d2d80` | Long brown parquet corridor with visible ceiling lamp and side opening. |

## Layer identity against gmap-0.12.0


Cell topology, roles, envelopes, modules, and base `p` ports are identical across the five seed pairs. Elevation-loop `e` ports, elevation metadata, and floor levels shift under the 0.13.0 elevation stream for all five seeds. The versioned 0.13.0 keyed streams also change dark-wing/light values and surface wear/variants for all five seeds; palette-anchor output shifts for seed 279. These streams are versioned independently so each layer can be redrawn without consuming another layer’s random sequence. The floor-region stream remains `floor_regions:gmap-0.12.0`: output is byte-equivalent for seeds 1, 2, 3, and 32, and changes for seed 279 because its upstream palette-anchor assignment changed. Reverb retains the existing `reverb:gmap-0.11.0` stream and its metadata is identical to 0.12.0. Reverb flags match 0.12.0 for all cells except `c03` in seeds 1 and 3: 0.13.0 elevation raises that cell’s minimum ceiling from 2.6 m to 4.1 m, crossing the 3.6 m double-height threshold and adding the documented 0.10 wet-probability bonus; the keyed draw itself is unchanged. Volume, mood, door, absorption, and mutation placeholders are metadata-derived and do not draw random values.


## Approval state

Operator walk: **pending**. Captures and passing headless checks are not operator approval.
