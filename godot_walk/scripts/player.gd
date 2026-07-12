extends CharacterBody3D

const SPEED: float = 4.0
const MOUSE_SENSITIVITY: float = 0.002
const PITCH_LIMIT: float = deg_to_rad(89.0)

var pitch_angle: float = 0.0
var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity") as float

@onready var head: Node3D = $Head

var _pos_label: Label


func _ready() -> void:
	floor_snap_length = 0.3
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	var cl := CanvasLayer.new()
	add_child(cl)
	_pos_label = Label.new()
	_pos_label.position = Vector2(10, 10)
	cl.add_child(_pos_label)


func _process(_delta: float) -> void:
	var p := global_position
	_pos_label.text = "pos  X:%.2f  Y:%.2f  Z:%.2f" % [p.x, p.y, p.z]


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := Vector3(input_dir.x, 0.0, input_dir.y).rotated(Vector3.UP, rotation.y)

	velocity.x = direction.x * SPEED
	velocity.z = direction.z * SPEED

	move_and_slide()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var motion := event as InputEventMouseMotion
		rotate_y(-motion.relative.x * MOUSE_SENSITIVITY)
		pitch_angle = clamp(
			pitch_angle - motion.relative.y * MOUSE_SENSITIVITY,
			-PITCH_LIMIT,
			PITCH_LIMIT
		)
		head.rotation.x = pitch_angle

	if event is InputEventKey:
		var key := event as InputEventKey
		if key.physical_keycode == KEY_ESCAPE and key.pressed:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

	if event is InputEventMouseButton and event.pressed:
		if Input.mouse_mode == Input.MOUSE_MODE_VISIBLE:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
