# Video adaptation validator successor v4

This is a validator-only successor to the v3 adaptation contract. Adaptation
records keep their existing schema versions, frozen references, candidate
identities, decisions and result artifacts. The v4 freeze preserves the exact
v3 validator sources in `archives/contract_v3/` and binds the current validator
sources separately. It does not broaden historical approvals.

The static Godot dependency scanner treats a constant as a statically known
resource path only when its complete declaration is one unescaped string
literal. Expression-valued constants, including conditional expressions, are
not evaluated or partially interpreted. A `load()` or `preload()` that uses
such a value requires an explicit dynamic-resource declaration listing every
possible target. Every declared target must exist in the repository and be
included in the candidate's fingerprinted dependency manifest.

This remains bounded static analysis, not a complete GDScript interpreter.
Runtime behavior and Godot traversal still require separate measured evidence.
