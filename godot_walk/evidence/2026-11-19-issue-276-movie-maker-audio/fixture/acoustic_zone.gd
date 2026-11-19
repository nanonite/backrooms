extends Node3D
## Runtime-only acoustic metadata provider for the #276 walk fixture.
## walk_player.gd asks its parent for room_reverb_at() and room_ceiling_height_at().
## The accepted room scripts are read-only, so this tiny zone is inserted as an
## intermediate parent at runtime. It is a fixture, not a claim about the room's
## measured acoustics.

func room_reverb_at(_position: Vector3) -> bool:
	return true


func room_ceiling_height_at(_position: Vector3) -> float:
	return 4.8
