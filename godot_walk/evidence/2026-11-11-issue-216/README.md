# Issue #216: measured module acoustics

The committed probe results were produced in Godot 4.6.3 by instantiating each
of the 11 admitted library scenes in an isolated headless assembly and calling
`RoomAcousticProbe.sample` from `scripts/room_acoustic_probe.gd` (#205).

The runner uses the accepted module profile's footprint area centroid, the
scene's `walk_floor_y` metadata (or a named floor collider fallback), a head
offset of 1.1 m, the existing 12-ray horizontal fan at 20 m, collision mask 1,
three physics settling frames, and the profile ceiling as the up-ray hint.
Those settings and per-module sample positions are recorded in
`module_acoustics_probe_results.json` and projected into the v0.2.0 sidecar.
Every per-module probe record is marked `measured`.

Re-run and validate from the workspace root:

```bash
XDG_DATA_HOME=/tmp/godot-xdg-data XDG_CONFIG_HOME=/tmp/godot-xdg-config \
  godot4 --headless --path godot_walk --script res://scripts/probe_module_acoustics.gd
python3 godot_walk/scripts/module_acoustics.py generate-v2
python3 godot_walk/scripts/module_acoustics.py check-v2
python3 -m pytest -q godot_walk/scripts
```

The reproducibility check runs the Godot probe a second time and compares
distances and ceiling within 0.001 m, openness exactly, and mapped reverb
parameters within 0.000001. The probe output and the v0.2.0 sidecar each have a
detached SHA-256 pin. Operator listening in 2–3 modules is **pending**; no
listening review is claimed here. Registration and scale calibration remain
unaccepted.
