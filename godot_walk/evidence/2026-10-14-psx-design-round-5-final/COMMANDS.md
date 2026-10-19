# Round 5 Review Commands

Open matched views in Firefox:

```sh
firefox godot_walk/evidence/2026-10-14-psx-design-round-5-final/index.html
```

Run the clean-floor, aligned-column candidate:

```sh
DISPLAY=:1 godot4 --path godot_walk --scene res://scenes/corridor_psx_design_candidate.tscn -- --variant=source_floor_single_column
```

Run the lower-ceiling candidate:

```sh
DISPLAY=:1 godot4 --path godot_walk --scene res://scenes/corridor_psx_design_candidate.tscn -- --variant=source_floor_ceiling_single_column
```

Reproduce captures and mechanics:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_5.py
```
