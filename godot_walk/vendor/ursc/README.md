# Ultimate Retro Shader Collection subset

Upstream: https://github.com/Zorochase/ultimate-retro-shader-collection

Release 1.5, commit `8cd971d0a275ef126151a99adf49cae1a64614c4`.
MIT license retained in `LICENSE.md`. `common.gdshaderinc` and the license
are byte-identical upstream files. `utilities.gdshaderinc` only gains a final
newline. No shader effect logic has been changed.

Upstream credits MenacingMecha's PSX and N64 shaders as its primary basis.
The collection additionally credits Zacksly (Shiny shaders) and tentabrobpy
(Flat Sky); those optional shader configurations are not included here.
The utility conversion functions retain their original attribution links.

The project's two macro-only shader configurations use the documented URSC
unshaded, texture-disabled/textured, double-sided and fog-disabled options.
They deliberately avoid editor auto-conversion, global project setup and
additional post-processing. See the #155 evidence manifest for exact hashes,
runtime settings and tested Godot version. Renderer globals are initialized
once per process only when a review wrapper is instantiated; no settings
are saved to `project.godot`.
