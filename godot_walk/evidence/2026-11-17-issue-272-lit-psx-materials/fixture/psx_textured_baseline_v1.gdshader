shader_type spatial;

// Issue 272 — NEW opt-in fixture variant (baseline, textured path).
// Mirrors the accepted library_psx_textured.gdshader defines exactly: UNSHADED
// and FOG_DISABLED are both set. TEXTURE_REPEAT keeps the textured PSX path.
// This is the unshaded control; scene lights must not change its output.
#define UNSHADED
#define CULL_MODE cull_disabled
#define FOG_DISABLED
#define TEXTURE_REPEAT
#include "res://vendor/ursc/common.gdshaderinc"
