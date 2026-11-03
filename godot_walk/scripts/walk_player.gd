extends "res://scripts/player.gd"

## Generated-maze walkthrough player (#191): the base player plus hold-Shift sprint.
## Applied via set_script in generative_map_assembly.gd only, so every other scene keeps
## the unmodified player.gd and project.godot stays untouched.

const SPRINT_SPEED: float = 9.0
const SPRINT_ACTION := &"sprint"


func _ready() -> void:
	super()
	_register_sprint_action()


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := Vector3(input_dir.x, 0.0, input_dir.y).rotated(Vector3.UP, rotation.y)

	var speed := SPRINT_SPEED if Input.is_action_pressed(SPRINT_ACTION) else SPEED
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed

	move_and_slide()


static func _register_sprint_action() -> void:
	if InputMap.has_action(SPRINT_ACTION):
		return
	InputMap.add_action(SPRINT_ACTION)
	for side: KeyLocation in [KEY_LOCATION_LEFT, KEY_LOCATION_RIGHT]:
		var event := InputEventKey.new()
		event.physical_keycode = KEY_SHIFT
		event.location = side
		InputMap.action_add_event(SPRINT_ACTION, event)
