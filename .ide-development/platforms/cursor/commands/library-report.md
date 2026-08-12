---
description: Show durable LiNKlibraries verification and provenance evidence.
---

Use the physical managed client installed at `.cursor/library/library-client.mjs`:

```bash
node .cursor/library/library-client.mjs report --entry <entry-id>
node .cursor/library/library-client.mjs verify-cache --entry <entry-id>
```

Reports include the exact catalog and entry commit SHA, catalog digest, payload
hash evidence, compatibility result, stale/offline status, and consumer run
identity. A missing or tampered verification record is a failure, not a cache
hit.
