class_name MazeEndCard
extends CanvasLayer

## The M3 run-end card (#233).
##
## It shows the run's seed, rooms visited, edits and re-rolls, all supplied by
## the exit runtime from its log. It deliberately has no action: no next seed,
## no next level, no restart button. Level chaining belongs outside this
## repository (§6.4, Q3).

const TITLE := "RUN ENDED"
const FOOTER := "The threshold is the end of this run."
const SHADE_COLOR := Color(0.015, 0.02, 0.025, 0.82)
const PANEL_COLOR := Color(0.86, 0.89, 0.88, 0.97)
const INK_COLOR := Color(0.07, 0.10, 0.10)
const ACCENT_COLOR := Color(0.10, 0.52, 0.58)
const ROWS := [
	["seed", "SEED"],
	["rooms_visited", "ROOMS VISITED"],
	["edits", "EDITS"],
	["rerolls", "RE-ROLLS"],
]

var root: Control
var shown := false
var show_count := 0
var values: Dictionary = {}
var _rows: Dictionary = {}


func _ready() -> void:
	layer = 30
	_build()


func _build() -> void:
	if root != null:
		return
	root = Control.new()
	root.name = "EndCardRoot"
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var shade := ColorRect.new()
	shade.name = "Shade"
	shade.color = SHADE_COLOR
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(shade)
	var center := CenterContainer.new()
	center.name = "Center"
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(center)
	var panel := PanelContainer.new()
	panel.name = "Card"
	panel.custom_minimum_size = Vector2(420.0, 0.0)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL_COLOR
	style.border_color = ACCENT_COLOR
	style.set_border_width_all(2)
	style.set_corner_radius_all(6)
	style.set_content_margin_all(28.0)
	panel.add_theme_stylebox_override("panel", style)
	center.add_child(panel)
	var column := VBoxContainer.new()
	column.name = "Column"
	column.add_theme_constant_override("separation", 10)
	panel.add_child(column)
	var title := Label.new()
	title.name = "Title"
	title.text = TITLE
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 34)
	title.add_theme_color_override("font_color", INK_COLOR)
	column.add_child(title)
	var rule := HSeparator.new()
	column.add_child(rule)
	for entry: Array in ROWS:
		var key := String(entry[0])
		var caption := String(entry[1])
		var row := HBoxContainer.new()
		row.name = "Row_%s" % key
		row.add_theme_constant_override("separation", 18)
		var label := Label.new()
		label.text = caption
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.add_theme_font_size_override("font_size", 17)
		label.add_theme_color_override("font_color", INK_COLOR)
		row.add_child(label)
		var value := Label.new()
		value.text = "0"
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		value.add_theme_font_size_override("font_size", 20)
		value.add_theme_color_override("font_color", ACCENT_COLOR)
		row.add_child(value)
		column.add_child(row)
		_rows[key] = value
	var footer := Label.new()
	footer.name = "Footer"
	footer.text = FOOTER
	footer.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	footer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	footer.add_theme_font_size_override("font_size", 14)
	footer.add_theme_color_override("font_color", INK_COLOR)
	column.add_child(footer)
	root.visible = false


func show_card(card: Dictionary) -> void:
	if root == null:
		_build()
	values = card.duplicate(true)
	for entry: Array in ROWS:
		var key := String(entry[0])
		var label: Label = _rows[key]
		label.text = _value_text(key, card.get(key, 0))
	root.visible = true
	shown = true
	show_count += 1


func hide_card() -> void:
	if root != null:
		root.visible = false
	shown = false


## There is no button, link or other progression affordance on the card.
func action_count() -> int:
	if root == null:
		return 0
	var count := 0
	for node in root.find_children("*", "BaseButton", true, false):
		count += 1
	return count


static func _value_text(_key: String, value: Variant) -> String:
	return str(int(value))
