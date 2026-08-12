---
description: Search and select verified LiNKlibraries entries.
---

Use the physical managed client installed at `.cursor/library/library-client.mjs`:

```bash
node .cursor/library/library-client.mjs search --query "<plain-English need>"
node .cursor/library/library-client.mjs select --entry <entry-id>
```

Selection validates the catalog digest, immutable catalog/entry commit binding,
entry state, exhaustive payload hashes, and consumer compatibility. Metadata-only
records are searchable but never selectable. Do not build or import a Starter Kit
from this command.
