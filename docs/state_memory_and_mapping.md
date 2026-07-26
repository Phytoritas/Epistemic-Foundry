# State, memory, mapping and context architecture

## 1. Canonical state

Chat history is navigation; canonical artifacts and ledger events are evidence.

Local layout:

```text
.epistemic-foundry/
├── foundry.db                  # SQLite WAL canonical local state
├── artifacts/sha256/           # immutable content-addressed objects
├── exports/                    # portable .efpack bundles
├── backups/
├── policy/
├── domain-packs/
├── skill-vault/
├── logs/                       # redacted operational logs
└── cache/                      # disposable indexes and parser caches
```

The installed plugin writes only to `PLUGIN_DATA`. Workspace authority lives in `.epistemic-foundry/`, selected explicitly and recorded in `PluginInstallState`.

## 2. Event and effect model

State changes are produced by a deterministic reducer over append-only events. External side effects use:

```text
ActionIntent
→ policy and approval
→ CapabilityLease with fencing token
→ Attempt
→ external effect
→ EffectReceipt
→ reconciliation
→ committed event
```

On restart, unresolved intents are classified as not-started, in-flight, succeeded-uncommitted, failed, or unknown. Unknown effects are never retried blindly.

## 3. Memory

The recall subsystem is a retrieval adapter over policy-governed memory records, not an automatic prompt dump.

Before retrieval:

- detect explicit or implicit recall intent;
- identify workspace and purpose;
- verify consent and retention;
- select permitted stores;
- build a query plan.

After retrieval:

- redact;
- score provenance and relevance separately;
- deduplicate;
- emit `MemoryRetrievalReceipt`;
- place only selected artifact IDs/summaries in a ContextCapsule.

The plugin asks the user only when the missing fact is genuinely unavailable from permitted state.

## 4. Context Capsule

A ContextCapsule contains:

- session and phase cursor;
- governing RunSpec/policy hashes;
- active Insight/Hypothesis revisions;
- selected artifact IDs and bounded summaries;
- open blockers and unresolved objections;
- allowed tools and leases;
- exclusions and unavailable sources;
- token budget;
- source and summary hashes.

Post-compaction reinjection reconstructs the capsule from canonical state. It never reuses the prior capsule without checking freshness.

## 5. Workspace Cartographer

Graph layers:

- code symbols/imports;
- schemas and schema references;
- workflows and dependencies;
- work packages/write scopes;
- papers/citations/datasets;
- SourceSpans/Claims/Evidence;
- artifacts/provenance;
- skills/hooks/MCP tools;
- tests and coverage;
- decisions and stale propagation.

Ranking:

1. baseline structural centrality is always real, never uniform placeholder ranking;
2. query-specific personalization is a separate score;
3. risk/blast radius and semantic relevance are separate dimensions;
4. generated/vendor/test files are classified, not silently mixed;
5. ranking algorithm, inputs and exclusions are recorded in `WorkspaceMapSnapshot`.

Outputs:

- global map;
- query-focused map;
- change-impact map;
- research coverage map;
- authority/dependency map;
- orphan/dead-contract report.

## 6. Cache and index semantics

Caches are disposable projections. They include parser output, embeddings, lexical index, graph projections, UI read models, and map rankings. Every cache key includes source hash, schema/ontology version, parser/model version, and configuration hash. Deleting cache must not delete canonical evidence.
