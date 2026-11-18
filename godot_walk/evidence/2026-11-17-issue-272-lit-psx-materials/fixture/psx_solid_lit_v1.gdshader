shader_type spatial;

// Issue 272 — NEW opt-in fixture variant (lit, solid path).
// The ONLY difference from psx_solid_baseline_v1.gdshader is that UNSHADED is
// removed, so the shared URSC include selects diffuse_lambert_wrap +
// vertex_lighting. FOG_DISABLED is retained: fog is deliberately unchanged so a
// lighting comparison never changes two variables at once. CULL_MODE and the
// whole PSX path (vertex snapping, cull distance, texture LOD) are untouched.
// The file is new; the library shader and common include are never edited.
#define CULL_MODE cull_disabled
#define FOG_DISABLED
#define TEXTURE_DISABLED
#include "res://vendor/ursc/common.gdshaderinc"
