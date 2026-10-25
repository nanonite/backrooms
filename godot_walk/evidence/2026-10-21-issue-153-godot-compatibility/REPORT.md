# #153 — Godot-native PSX workflow assessment

Status: architecture assessed; existing native treatment retained. No production visual change, room promotion, commit, or issue closure. Operator clarification makes Blender optional: adapt useful architectural ideas to Godot, not the proprietary implementation.

## Decision

Keep Godot's current material and compositor layers. The accepted column already has a simple box, source-frame texture, nearest filtering, and the native PSX post effect. There is no demonstrated need for another plugin framework or a vertex animation pass. A column approval is not approval of the complete room, and no second independently PSX-ready Godot room was established by this audit.

The immediate gap is **a shared visual readiness review across two independent rooms**, not a missing dither shader. Next: review the first whole room, produce a second bounded Godot room, apply the same explicit material/post settings, approve both independently, and only then test their connection. Historical Bevy module approvals do not automatically satisfy Godot readiness.

## Feature and license matrix

Based on the installed Readme and [public feature list](https://fawkek.itch.io/psx-retro-tools), not implementation inspection:

| Feature | Appropriate layer | Godot decision |
| --- | --- | --- |
| Mesh simplification / triangulation | Optional offline geometry preparation | Export resulting mesh through GLB; never derive collision automatically from styled visuals. Box already needs no simplification. |
| Low-resolution baking, generated textures, texture dithering | Optional offline image preparation | Save images with provenance; ordinary UV/image materials can travel with GLB. Not proven by this smoke test. |
| Nearest sampling and UV layout | Per-material configuration | Already native on authored source patches; explicitly review remaining Hunyuan materials rather than globally replacing them. |
| Pixelation, color-depth reduction, ordered dithering | Godot presentation compositor | Already implemented by `scripts/psx/psx_post_effect.gd` and its compute shader. Reuse those. Color-depth quantization is not a curated indexed palette. |
| Vertex jitter, camera-relative screen snapping | Optional Godot vertex shader | Blender node/modifier behavior does not transfer as live runtime logic. Deferred; add independently only after a useful separate visual comparison. |
| UV distortion | Optional Godot material shader | No current demonstrated need; preserve accepted face mapping. |
| Shadows, resolution, AA and lighting presets | Godot environment/render configuration | Choose directly in Godot. Blender scene rendering/compositor settings do not accompany a visual-only GLB. |

The installed `LICENSE.txt` allows using created game assets and forbids copying/modifying/reusing addon source. No proprietary source is vendored or ported here. The separation above is a design assessment of publicly described capabilities, not a claim of feature parity.

[Godot recommends glTF](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html); its `.blend` importer also converts through glTF. Therefore a Blender install does not make its compositor executable in Godot. [Blender's exporter documentation](https://docs.blender.org/manual/en/4.0/addons/import_export/scene_gltf2.html) describes exportable UV/image material configurations and evaluated meshes. Static evaluated modifiers are distinct from ongoing camera-dependent behavior.

## Existing native settings and readiness contract

The accepted scene inherits `_build_environment()` from `hunyuan_psx_round1.gd`: block size 3 output pixels, 24 quantization levels per color channel, Bayer dither strength 1.0. `--no-psx` bypasses presentation for comparison. Three-pixel sampling of a 960×540 output is not equivalent to rendering all geometry at 320×180. Current code targets Forward+ / Vulkan; this audit does not claim Compatibility-renderer portability.

For every room, record stable room ID; reference frame/crop and hashes; authored versus source surfaces; visual bounds; separately validated collision; connector sockets; renderer/resolution/FOV; per-material nearest/filter decisions; post-effect settings; matched PSX-on/off captures; representative walkaround and seam views; resource/traversal results; and direct operator acceptance. Preserve `registration_accepted=false` and `scale_calibrated=false` until independent evidence changes them. An operator-approved local repair does not satisfy every room-level field.

Do not force the Hunyuan room into a single material or overwrite the accepted column to obtain consistency. Review first-room floors/walls/ceiling and the second room under matched native treatment. Review material cohesion separately from geometry readiness. Connection gates still require clearance, floor continuity, boundaries and bidirectional traversal in Godot.

## Installed Blender finding and bounded smoke test

- Installed legacy addon: `/home/goya/.config/blender/5.0/scripts/addons/PSX tools`, Readme version 1.6.1. Its install is real. The background probe reported its configuration path as `/home/goya/.config/blender/5.2/config`; its initial enabled-addon preference list contained only built-in addons, with no PSX entry. `/home/goya/.config/blender/5.2` exists; the probe does not establish which profile a separately launched Blender UI uses.
- Running executable: `/snap/bin/blender`, Blender 5.2.2 LTS. Public download links currently advertise 1.7.16; the page heading still says 1.7.14. No update, dependency installation, preference save or installed-addon edit occurred.
- Temporary registration exposed public operators but emitted missing-Pillow, invalid `EnumProperty` default, and duplicate-class warnings. This does not establish a fully operational installation.
- Optional copied-source box smoke test used factory startup. It ended with exit 139 during `bpy.ops.object.psx_texture_bake()`. `/tmp/blender.crash.txt` identifies `popup_menu` in its Python backtrace. This is a background-mode popup crash, not proof the interactive tool cannot bake. No GLB, `.blend`, baked texture, or Blender/Godot round-trip result was produced. The prior triangulation call was reached, but no saved result proves its output.
- No further Blender experiments are required by the revised Godot-native task. Interactive addon repair/upgrade would be separate optional work, not a dependency of room readiness.

## Verification and evidence

`godot_column_test.log`: Godot 4.6.3 accepted-column regression PASS. It checks unchanged collision against round 3, Hunyuan presence, four faces plus backing, accepted texture bytes/dimensions/nearest sampling, and false flags. Headless testing does not prove GPU compositor appearance; this audit creates no new appearance candidate. Existing accepted comparison remains `../2026-10-21-issue-151-column-box/comparison.png`, with original matched camera records under that folder's `captures/`.

`provenance.json`: installed-addon file hashes/license location, native file hashes, five protected fixture hashes compared with prior evidence, current readiness statuses and honest Blender failure. `blender.log` records the failed smoke; `python_tests.log` records existing Hunyuan suite execution. Protected hashes match. No Rust/runtime implementation changed; Cargo checks are out of scope.

Reproduce from repository root:

```bash
python3 godot_walk/evidence/2026-10-21-issue-153-godot-compatibility/authoring/audit_native.py
godot4 --headless --path godot_walk --script res://scripts/test_hunyuan_psx_column_box.gd
python3 -m unittest discover -s godot_walk/scripts -p 'test_hunyuan*.py'
```

The optional failing Blender smoke is preserved as `authoring/probe_addon.py` for reproducibility; it is not part of native verification. Its exact invocation was `/snap/bin/blender --background --factory-startup --python godot_walk/evidence/2026-10-21-issue-153-godot-compatibility/authoring/probe_addon.py`. Do not interpret a process launch as a successful export.

Changed files: focused active-runtime/authoring guidance in `PLAN.md` and this new evidence folder only. Earlier rounds, protected source assets, column implementation, collision, runtime shaders, default scene and installed Blender preferences remain untouched.
