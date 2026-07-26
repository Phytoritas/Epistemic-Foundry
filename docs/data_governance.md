# Data governance and licensing

## Data classes

Recommended classes:

```text
PUBLIC
LICENSED_INTERNAL
CONFIDENTIAL
PERSONAL
SENSITIVE_PERSONAL
RESTRICTED
```

Each DocumentManifest, artifact, ContextAssemblyManifest, and ValidationTarget declares applicable classes.

## Principles

- purpose limitation and minimum necessary context,
- source license and access policy propagation,
- no uncontrolled export through model providers,
- explicit retention and deletion schedule,
- immutable provenance retained only as legally permitted,
- redaction creates a new artifact and never modifies source bytes,
- audit access is role-controlled,
- translations and summaries inherit source restrictions.

## Deletion and legal hold

Deletion requests are represented as governed events. Where provenance must be retained, store a tombstone and non-reversible hash only if policy and law permit. Legal hold supersedes ordinary retention but must be scoped and time-bounded.
