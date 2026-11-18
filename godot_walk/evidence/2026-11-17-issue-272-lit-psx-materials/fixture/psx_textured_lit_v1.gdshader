shader_type spatial;

// Issue 272 — NEW opt-in fixture variant (lit, textured path).
// The ONLY difference from psx_textured_baseline_v1.gdshader is that UNSHADED is
// removed, so the shared URSC include selects diffuse_lambert_wrap +
// vertex_lighting. FOG_DISABLED and TEXTURE_REPEAT are retained: fog stays
// unchanged and the textured PSX path is kept. CULL_MODE and vertex snapping are
// untouched. The file is new; the library shader and common include are never edited.
#define CULL_MODE cull_disabled
#define FOG_DISABLED
#define TEXTURE_REPEAT
#include "res://vendor/ursc/common.gdshaderinc"
