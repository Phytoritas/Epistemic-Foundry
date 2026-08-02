# Memory, context, and replay

- Memory classes distinguish canonical state, source evidence, working context, user-consented preference, and cache; memory is not source evidence.
- Retrieval obeys workspace, consent, retention, sensitivity, provenance, and purpose limits.
- A `ContextCapsule` binds included artifacts, exclusions, hashes, freshness, authority, and compaction recovery without silently broadening context.
- Strict replay reuses identical sealed artifacts; semantic replay creates a new revision under a new policy, model, or implementation version.
- Source, policy, ontology, parser, prompt, model, or dependency changes propagate explicit staleness rather than mutating history.
