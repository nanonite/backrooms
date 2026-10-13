shader_type spatial;
render_mode unshaded;

uniform int surface_kind = 0;
varying vec3 world_position;

void vertex() {
	world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 pixel = floor(world_position * 64.0);
	float grain = fract(sin(dot(pixel, vec3(12.9898, 78.233, 34.13))) * 43758.5453);
	vec3 color = vec3(0.30, 0.27, 0.09);
	if (surface_kind == 0) {
		float horizontal = world_position.x + world_position.z;
		vec2 cell = fract(vec2(horizontal * 8.0, world_position.y * 8.0));
		float diamond = abs(cell.x - 0.5) + abs(cell.y - 0.5);
		color *= mix(0.94, 1.0, step(0.15, abs(diamond - 0.42)));
		if (world_position.y < -1.05) { color = vec3(0.15, 0.12, 0.055); }
	} else if (surface_kind == 1) {
		color = vec3(0.26, 0.18, 0.07);
	} else {
		vec2 tile = fract(world_position.xz * 1.5);
		color = vec3(0.38, 0.33, 0.20) * mix(0.6, 1.0, step(0.025, min(tile.x, tile.y)));
	}
	ALBEDO = color * (0.94 + grain * 0.12);
}
