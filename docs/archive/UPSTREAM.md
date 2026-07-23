# Upstream policy — RETIRED (2026-07-23)

**This document is historical.** LiNKautowork no longer maintains or depends on a LiNKtrend fork of n8n.

**Current policy:** stock upstream n8n only — official image pin in Compose (`docker.n8n.io/n8nio/n8n:2.30.0`) and upgrades from `https://github.com/n8n-io/n8n` releases. See [`../LINKAUTOWORK-TECHNICAL-PRD.md`](../LINKAUTOWORK-TECHNICAL-PRD.md) §5.

**What was removed:** git submodule `link-n8n` → `github.com/linktrend/link-n8n`. The remote fork repo may still exist on GitHub as an orphan; archiving it is a Principal action, not required for this Program.

---

## Historical text (pre-retirement, 2026-07-18)

`link-n8n` was previously described as LiNKtrend's separate fork of [n8n](https://github.com/n8n-io/n8n), referenced as a git submodule while Compose already ran the stock official image. That dual model is retired: LiNKautowork customizations live in `gateway/`, templates, Supabase, and ops — not in a forked n8n core.
