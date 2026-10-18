# Issue #137 Supplemental Godot Matched-View Cross-Check

This supplemental comparison renders both the unchanged #100 `corridor_splat` baseline and the run-05 Hunyuan GLB in Godot 4.6.3. It uses the same nine camera poses, 960x540 output, and 47.3988-degree vertical field of view. Hunyuan uses the recorded uncalibrated convention transform and contains no collision geometry. This is not the Bevy render required by #137.

ODiff threshold: `0.1`. Maximum same-pose baseline repeat noise: `1.580000%` of pixels. ODiff is a pixel-change diagnostic, not a quality score. Changes at or below the per-view repeat noise are inconclusive.

Renderer command: `/home/goya/.nvm/versions/node/v22.5.1/bin/npx --yes --package=odiff-bin@4.5.0 odiff`. Contact sheet: [captures/contact_sheet.png](captures/contact_sheet.png). Pose contract: [captures/capture_poses.json](captures/capture_poses.json).

| View | Baseline repeat noise | Hunyuan vs baseline | Interpretation | Captures |
|---|---:|---:|---|---|
| `frame_141` | 1.580000% | 97.550% (505708 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/frame_141.png), [Hunyuan](captures/hunyuan/frame_141.png) |
| `loop_station_00` | 0.000000% | 97.880% (507398 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_00.png), [Hunyuan](captures/hunyuan/loop_station_00.png) |
| `loop_station_01` | 0.000000% | 97.970% (507868 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_01.png), [Hunyuan](captures/hunyuan/loop_station_01.png) |
| `loop_station_02` | 0.000000% | 98.880% (512600 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_02.png), [Hunyuan](captures/hunyuan/loop_station_02.png) |
| `loop_station_03` | 0.000000% | 97.990% (507959 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_03.png), [Hunyuan](captures/hunyuan/loop_station_03.png) |
| `loop_station_04` | 0.000000% | 99.340% (514972 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_04.png), [Hunyuan](captures/hunyuan/loop_station_04.png) |
| `loop_station_05` | 0.000000% | 99.650% (516570 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_05.png), [Hunyuan](captures/hunyuan/loop_station_05.png) |
| `loop_station_06` | 0.000000% | 97.800% (506996 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_06.png), [Hunyuan](captures/hunyuan/loop_station_06.png) |
| `loop_station_07` | 0.000000% | 94.320% (488963 px) | `above_baseline_noise; requires visual review` | [baseline](captures/baseline_repeat_1/loop_station_07.png), [Hunyuan](captures/hunyuan/loop_station_07.png) |

No visual-quality claim is made from ODiff alone. Review the linked same-pose captures; differences above the repeat noise identify where the images differ, not which image is better.
