# Migration plan — Epistemic Foundry v2.0.0 to v3.0.0

## 1. Compatibility position

v3 preserves the v2 epistemic core—ClaimCard, SourceSpan, EvidenceNode, Evidence Pack, CoverageSnapshot, Parliament artifacts, ValidationTarget, Hypothesis Passport, ledger/replay principles—and adds an installable plugin shell and research-native lifecycle.

The migration is additive at the artifact level and breaking at the session/orchestration level.

## 2. Key changes

| v2 | v3 |
|---|---|
| abstract runtime invocation | native plugin shell + CLI/MCP/adapters |
| workflow-specific session state | FORGE event-sourced session |
| generic validation loop | FORGE lifecycle integrated with Validation Bay |
| provider adapters in development spec | runtime capability negotiation |
| context assembly manifest | ContextCapsule + memory retrieval receipt |
| general work packages | A–Z plugin-first implementation graph |
| 144 architecture lenses | retained plus 216 plugin-specific lenses |
| no plugin distribution contract | manifest, hooks, skills, MCP, fresh-install, upgrade and rollback |
| optional local data choices | explicit LITE/RESEARCH/TEAM/REGULATED profiles |
| budget policy | typed enforcement authority and breach behavior |

## 3. Artifact migration

- v2 artifacts retain their IDs and hashes.
- A v2 run imported into v3 receives an `ImportedRunRecord`.
- v2 sessions map to a v3 FORGE session with phase `E` only when final artifacts are complete; otherwise they map to the earliest phase whose obligations are satisfied.
- No v2 narrative completion field is converted into an ArtifactReceipt.
- Existing ContextAssemblyManifest is referenced by a new ContextCapsule, not overwritten.
- New lifecycle, stability, capability and compatibility fields default to `UNKNOWN/NOT_ASSESSED`, not optimistic values.

## 4. Store migration

1. freeze writes;
2. create verified backup;
3. validate v2 schema bundle and database;
4. generate migration plan and dry-run report;
5. create v3 tables/repositories;
6. import events and artifacts;
7. derive FORGE state without manufacturing receipts;
8. rebuild projections/indexes;
9. run replay equivalence and sample Passport comparison;
10. switch active version;
11. retain rollback snapshot;
12. reapprove changed hooks and re-run capability probe.

## 5. Plugin migration

v2 had no canonical installable plugin. v3 therefore begins with a new plugin identity `epistemic-foundry` version `3.0.0`. Existing repo-local Codex/Claude files can coexist during migration, but authority order must point to the v3 specification. Duplicate skill names are detected and reported.

## 6. Rollback

Rollback restores the prior database/artifact snapshot and plugin version, but never deletes v3 migration events. Any v3-only external effect is reconciled and listed. Rollback success requires health PASS/DEGRADED with no integrity failure.
