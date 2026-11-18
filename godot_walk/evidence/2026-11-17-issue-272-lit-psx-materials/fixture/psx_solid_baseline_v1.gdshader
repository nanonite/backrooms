shader_type spatial;

// Issue 272 — NEW opt-in fixture variant (baseline, solid path).
// Mirrors the accepted library_psx_vertex.gdshader defines exactly: UNSHADED and
// FOG_DISABLED are both set. This is the unshaded control; scene lights must not
// change its output. The file is new; the library shader is never edited.
#define UNSHADED
#define CULL_MODE cull_disabled
#define FOG_DISABLED
#define TEXTURE_DISABLED
#include "res://vendor/ursc/common.gdshaderinc"
