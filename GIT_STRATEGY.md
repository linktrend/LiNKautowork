# Git Strategy (LiNKautowork)

- `origin/main` is deploy source of truth.
- Release deploys must be pinned to immutable tag/SHA.
- No hotfixes directly on servers; all fixes must roundtrip through git.
- Runtime secrets and generated env/runtime artifacts are non-authoritative and excluded from source-of-truth claims.
