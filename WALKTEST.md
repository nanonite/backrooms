# v1 Walk-Test (Chainlink #44 / corridor.tscn)

## 1. Open the project

```bash
cd /home/user/backrooms-workspace/godot_walk
godot4 --editor .
```
(or launch Godot 4.6, open project at `godot_walk/`)

## 2. Run the corridor scene

- In the FileSystem dock, open `scenes/corridor.tscn`
- Press F6 (Run Current Scene) -- or F5 if it's set as the main scene
- Mouse-look should capture immediately (cursor hidden); press Esc to release it back to the editor

## 3. Controls

- WASD to move, mouse to look, Space to jump (if implemented), Esc to release mouse capture

## 4. What to check (fable-plan section 5 acceptance)

- Spawn: you should land standing on the floor, not falling through or floating above it
- Walk the full corridor: WASD end-to-end -- no invisible walls, no falling through the floor partway, no getting stuck
- Shoulder-rub every wall: walk into each wall at an angle -- you should slide along it smoothly, not clip through it or get stuck/jittery
- Stand in corners: walk into a corner where two walls meet -- no tunneling through into geometry, no jitter
- Doorway scale: if there's a doorway/opening, it should feel "door-sized" (~2m tall) relative to your character -- not a tiny crawlspace or a giant cathedral opening
- No floating debris/geometry gaps: look around -- textures should be applied (not all-white/missing), no obvious holes in the mesh
- Performance: check FPS counter (Godot's debug overlay, or add one) -- should be >= 60fps

## 5. Report back

Tell me pass/fail on each, plus anything visually off (texture stretching, scale weirdness, lighting issues). If it all looks good, say so and the v2 wave (#45-47, Gaussian splat overlay) gets forked next. If something's off, describe it and a fix-up issue gets spec'd.
