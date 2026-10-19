# Round 4 Review Commands

Open the matched-view review in Firefox:

```sh
firefox godot_walk/evidence/2026-10-14-psx-design-round-4-final/index.html
```

Run the source-textured cleanup candidate for a live walkthrough:

```sh
DISPLAY=:1 godot4 --path godot_walk --scene res://scenes/corridor_psx_design_candidate.tscn -- --variant=source_texture_cleanup
```

Run the selected flush-door control for comparison:

```sh
DISPLAY=:1 godot4 --path godot_walk --scene res://scenes/corridor_psx_design_candidate.tscn -- --variant=door_flush
```

Reproduce the full captures and mechanics bundle:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_4.py --out-dir godot_walk/evidence/2026-10-14-psx-design-round-4-replay
```

Run the design-variant contract tests:

```sh
godot4 --headless --path godot_walk --script res://scripts/test_psx_design_variants.gd
```
