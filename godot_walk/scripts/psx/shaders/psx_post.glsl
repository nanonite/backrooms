#[compute]
#version 450

// Optional PSX presentation pass (#100).
//
// Two effects, both presentation-only and independently switchable at the
// effect script level:
//   1. coarse pixel grid  -- snap each output pixel to the top-left texel of a
//      `pixel_size` block, a nearest-neighbour downsample with no extra target;
//   2. ordered dither + colour-depth reduction -- quantize to `color_levels`
//      steps per channel with a 4x4 Bayer threshold, in display (sRGB) space so
//      the steps are perceptually even.
//
// It writes the scene colour buffer in place and never touches depth, geometry
// or collision. With `enabled = false` the effect returns before dispatch, so
// the geometry/alignment review view is bit-for-bit the un-effected render.

layout(local_size_x = 16, local_size_y = 16, local_size_z = 1) in;

layout(rgba16f, set = 0, binding = 0) uniform image2D scene_tex;

layout(push_constant, std430) uniform Params {
    vec2 screen_size;
    float pixel_size;
    float color_levels;
    float dither_strength;
    float _pad0;
    float _pad1;
    float _pad2;
} p;

const float BAYER4[16] = float[](
     0.0,  8.0,  2.0, 10.0,
    12.0,  4.0, 14.0,  6.0,
     3.0, 11.0,  1.0,  9.0,
    15.0,  7.0, 13.0,  5.0
);

vec3 linear_to_srgb(vec3 color) {
    bvec3 cutoff = lessThanEqual(color, vec3(0.0031308));
    vec3 lower = color * 12.92;
    vec3 higher = 1.055 * pow(color, vec3(1.0 / 2.4)) - 0.055;
    return mix(higher, lower, cutoff);
}

vec3 srgb_to_linear(vec3 color) {
    bvec3 cutoff = lessThanEqual(color, vec3(0.04045));
    vec3 lower = color / 12.92;
    vec3 higher = pow((color + 0.055) / 1.055, vec3(2.4));
    return mix(higher, lower, cutoff);
}

void main() {
    ivec2 pixel = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = ivec2(p.screen_size);
    if (pixel.x >= size.x || pixel.y >= size.y) {
        return;
    }

    int block = max(int(p.pixel_size + 0.5), 1);
    ivec2 sample_pixel = clamp((pixel / block) * block, ivec2(0), size - ivec2(1));
    vec4 color = imageLoad(scene_tex, sample_pixel);

    int levels = max(int(p.color_levels + 0.5), 2);
    float scale = float(levels - 1);

    vec3 display = linear_to_srgb(clamp(color.rgb, 0.0, 1.0));
    ivec2 cell = pixel % 4;
    float threshold = (BAYER4[cell.y * 4 + cell.x] + 0.5) / 16.0 - 0.5;
    vec3 dithered = display + threshold * (p.dither_strength / scale);
    vec3 quantized = floor(clamp(dithered, 0.0, 1.0) * scale + 0.5) / scale;

    imageStore(scene_tex, pixel, vec4(srgb_to_linear(quantized), color.a));
}
