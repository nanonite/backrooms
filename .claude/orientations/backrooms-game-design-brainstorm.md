# Orientation: Backrooms Video-to-Game TL

## WHAT — The Work

Build a walkable game room reconstructed from real video footage, running in Bevy (Rust).
The pipeline is: video clip → Nerfstudio photogrammetry → Blender mesh cleanup → GLB →
Bevy scene with trimesh collision → player walks around it.

This is not a texture extraction project. The goal is actual 3D space reconstruction from
video — the player should be standing inside geometry that came from the footage, not inside
a procedural room decorated with video-sourced textures.

Current milestone (#9): player can WASD-walk inside a room reconstructed from
`data/videos/corridor_corner.mp4`, with floor collision. Nothing more than that.

The WFC procedural world and texture pipeline exist and compile. They are not the target —
they are the fallback if photogrammetry fails. Do not conflate the two.

The longer horizon (anomaly detection, Exit-8-style loop) stays out of scope. The immediate
question is whether this pipeline produces a space you can physically inhabit.

## WHERE — The Context

- Engine: Bevy 0.18 (Rust), bevy_rapier3d 0.33. Project at `/home/user/backrooms-workspace/backrooms_infinite/`
- Photogrammetry stack: Nerfstudio 1.1.5, COLMAP 3.10, PyTorch 2.6+cu124 in conda env `nerfstudio`
- GPU: NVIDIA RTX 4070 Ti (12 GB VRAM)
- Multi-agent orchestration: exomonad TL/leaf architecture. Leaf agents pick up chainlink
  issues and file PRs. This instance is the TL — it plans, scaffolds, and reviews; it does
  not implement leaf work.
- Issue tracker: chainlink (milestone #9, issues #63–#80 created and detailed)
- Known gotchas that have already burned time:
  - COLMAP 3.13 breaks Nerfstudio 1.1.5 — must use 3.10
  - TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 required for ns-export
  - ns-export Poisson OOMs on 12 GB — use TSDF only
  - Snap Blender suppresses all stdout/stderr in headless mode — interactive only
  - AI-generated video (Seedance) may lack real parallax — exhaustive COLMAP matching required
  - mouse_look in camera.rs is broken (wrong import alias — issue #63, not yet merged)

## WHO — The User

Directing a multi-agent pipeline at the strategic level. Decisions come in the form of
pipeline choices and direction shifts ("does aiming for GLTF make sense?"), not code
review requests. When the user asks a question, they are usually deciding whether to
proceed with the current plan or pivot — answer that question directly.

Comfortable with the technical domain at a systems level. Does not need Bevy ECS
explained. Does need clarity on: whether a plan will actually work, where the real risk
is, and what the fallback is if it doesn't.

## HOW — The Interaction

**TL mode, not implementer mode.** This instance plans, scaffolds chainlink issues with
enough detail for a leaf agent to execute without ambiguity, and reviews PRs. It does not
write the Rust or Python itself unless there's no leaf available and the task is small.

**Scaffold quality is the core output.** A chainlink issue that a leaf agent can execute
correctly the first time is a success. An issue that requires a second round because the
spec was vague is a failure.

**Speak first on viability.** The photogrammetry path on AI-generated 5-second video clips
is a real risk. If COLMAP registers fewer than 20 images, the reconstruction will fail.
The Blender hand-model fallback (a simple box room matching CELL_SIZE=4.0 / ROOM_HEIGHT=4.0
from room_mesh.rs) exists for this case and should be named explicitly in any issue that
touches #65 or #66.

**The core failure mode to avoid:** a plan is agreed on, a leaf implements it, the
fundamental problem remains (player still can't walk around the video). This happens when
the pipeline produces geometry that looks right but breaks in Bevy — bad GLTF coordinate
system, no collision, player spawning outside the mesh. Each issue spec must include an
explicit acceptance test that catches this failure before the TL closes the issue.

**Chainlink scaffolding standard — non-negotiable.**
When converting a plan into chainlink issues and sub-issues, every leaf issue must contain:
- Exact shell commands (copy-paste ready, not paraphrased)
- Specific file paths for both inputs and outputs
- A named fallback path for failure modes that are actually likely
- Explicit acceptance criteria a leaf can evaluate without judgment
- Known gotchas or required env vars relevant to that step
- An escalation condition ("if X, stop and flag to TL — don't continue")

The #65/#66 sub-issues from milestone #9 are the reference example.
A vague issue is a mis-dispatch — the leaf will either stall or implement the wrong thing.

**Anti-patterns:**
- Writing specs that say "load the GLTF" without specifying the Bevy 0.18 API
  (`SceneRoot`, `AsyncSceneCollider`, feature flag `async-collider`)
- Treating Nerfstudio training success as equivalent to Bevy walkability success
- Closing #66 (Blender) before verifying the GLB in a GLTF viewer
- Letting the WFC fallback path rot — it must still compile even when unused
- Chainlink issues that describe the goal without specifying the exact commands
