# PKT-08 generated-output closure

The generated-output graph is authoritative for identity-bound repository
outputs. Each output declares one physical generator, invalidating source
patterns, and explicit dependencies. Generators run in deterministic
topological order after source or integration repair.

Closure is reached only when the invalidating source identity and every output
digest are unchanged across a complete pass. A bounded pass limit rejects
non-convergence. The runtime rejects ambiguous dependencies, generator
failure, dirty output, source mutation during generation, post-generation
mutation, and stale output at finalization. Diagnostics include the output,
generator, invalidating sources, expected and observed digest, and expected and
observed source tree.

Generated outputs are excluded from candidate-content-tree identity so changing
an identity binding cannot create a circular fixture invalidation. Secret
scanning remains additive and fail closed; the exclusion is only an identity
boundary, never a scan exclusion.
