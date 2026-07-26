# PostgreSQL Schema Blueprint

This document is a migration blueprint, not executable DDL. Work package A04 converts it into versioned migrations.

## 1. Namespaces

```text
catalog       papers, versions, documents, corpora
evidence      spans, experiments, methods, claims, evidence, dependencies
reasoning     insights, hypotheses, predictions, falsifiers, arguments
deliberation  council runs, briefs, objections, gates, adjudications
execution     experiment tickets, validation targets, validation plans, runs, typed results
runtime       runs, nodes, leases, events, artifacts, receipts, checkpoints
ontology      terms, mappings, units, measurement constructs
audit         human reviews, overrides, exports, security events
```

Use UUID/ULID or validated text IDs consistently; do not mix implicit serial IDs with public IDs without an explicit surrogate/public mapping.

## 2. Catalog

### `catalog.papers`

- `paper_id` PK
- normalized title
- DOI and other identifiers
- publication metadata
- correction/retraction status
- created event

Unique constraints are conditional because DOI can be absent. Deduplication is a reviewed identity relation, not only a unique title.

### `catalog.paper_versions`

- `paper_version_id` PK
- `paper_id` FK
- version type: preprint/accepted/version-of-record/correction
- publication date
- source document ID
- content hash
- supersedes/superseded-by
- active flag

No in-place replacement of PDF bytes.

### `catalog.source_documents`

- `document_id` PK
- content SHA-256 unique
- object-store URI
- byte size
- MIME
- acquisition source
- license/access policy
- parser status
- created event

### `catalog.corpus_snapshots`

- `snapshot_id` PK
- collection ID
- canonical manifest artifact
- manifest hash unique
- created at
- source cutoff date
- query/license policy versions

A run always references one immutable snapshot hash.

## 3. Evidence

### `evidence.source_spans`

- `span_id` PK
- `paper_version_id` FK
- page
- section ID/name
- char start/end
- normalized bbox
- exact text hash
- optional element/caption/table cell ID
- parser version
- source artifact ID
- review status

Constraints:
- page >= 1
- char start < char end
- bbox coordinates within normalized range
- span hash cannot change after creation
- paper version ownership enforced

### `evidence.experiments`

- `experiment_id` PK
- paper version
- experiment label
- design type
- population/treatment/comparator JSON
- temporal/spatial support
- sample size and unit of independence
- dataset family ID
- provenance

### `evidence.methods`

- `method_id` PK
- method class
- instrument/protocol
- calibration/QC
- measurement construct ID
- unit and support
- proxy/direct classification
- source spans

### `evidence.claims`

Immutable revision model:
- `claim_id`
- `revision`
- paper/paper version
- subject/relation/object canonical IDs
- direction
- claim type
- author stance
- hedging level
- evidence layer
- extraction confidence
- scope JSONB plus normalized hot fields
- quantitative JSONB
- dataset family ID
- extraction provenance
- status

Primary key `(claim_id, revision)`. Human correction creates a revision and lineage edge.

### `evidence.claim_spans`

Many-to-many:
- claim ID/revision
- span ID
- role: primary/context/method/quantitative/caption
- ordinal

A promoted claim requires at least one primary span.

### `evidence.evidence_nodes`

- `evidence_id` PK
- experiment ID
- role: support/counter/null/boundary/method/alternative
- scope
- quality vector
- dataset family
- status
- provenance manifest
- created event

### `evidence.evidence_claims`

Evidence-to-claim relation with relation type and exact target proposition.

### `evidence.dependency_edges`

- left/right evidence or experiment
- dependency type
- confidence
- source/rationale
- human review
- cluster version

A cluster table materializes the current reviewed grouping but can be regenerated from edges.

## 4. Ontology and measurement

### `ontology.terms`

- term ID
- canonical label
- domain
- class
- ontology source/version
- deprecated/replaced-by

### `ontology.mappings`

- raw string/context
- term ID
- mapping type
- confidence
- method/measurement disambiguator
- reviewer

### `ontology.measurement_constructs`

Separates latent construct, operational variable, method, unit, temporal/spatial support.

### `ontology.method_compatibility`

- method A/B or construct-method pair
- compatibility class
- conditions
- promotion ceiling
- rationale/provenance
- version

## 5. Reasoning

### `reasoning.insights`

- insight ID/revision
- statement
- scope
- mechanism path
- predictions
- falsifiers
- alternatives
- null model
- registration status
- creator/created at

### `reasoning.coverage_snapshots`

- insight revision
- corpus snapshot
- cube definition/version
- cell counts by evidence role and dependency-adjusted count
- unsearched cells
- artifact hash

### `reasoning.hypotheses`

Canonical hypothesis revisions and promotion history.

### `reasoning.argument_nodes/edges`

Typed premises, rules, objections, attacks, undercuts, rebuttals, explanations, dependencies. Every empirical premise links to Evidence IDs.

## 6. Deliberation

### `deliberation.council_runs`

- run ID
- insight/hypothesis revision
- evidence pack
- workflow version
- blind-round policy
- status
- checkpoint
- final adjudication

### `deliberation.briefs`

- role
- round
- structured artifact
- context manifest
- model identity
- input/output hashes
- status

### `deliberation.objections`

- target argument/claim
- attack type
- evidence IDs
- materiality
- disposition
- resolution artifact

### `deliberation.gate_decisions`

Use `gate-decision.schema.json`; never overwrite a decision. Waiver is a new decision with human authority.

### `deliberation.adjudications`, `attestations`, `minority_reports`

Store structured payload artifact ID plus indexed status fields.

## 7. Validation and execution

### `execution.experiment_tickets`

Schema-aligned ticket, approval, ownership, and status for prospective empirical work.

### `execution.validation_targets`

Versioned `ValidationTargetManifest` records for a simulation model, analysis pipeline, formal solver, benchmark harness, experimental platform, external service, or custom executor. Store interface contracts, supported variables and actions, artifact hashes, execution policy, and capability requirements.

### `execution.validation_plans`

Immutable, preregistered `ValidationPlan` records containing the target revision, inputs, baseline and perturbation actions, metrics, falsification rules, seeds where applicable, environment pinning, and expected evidence class.

### `execution.runs`

- validation plan ID and target revision
- code/model/container/service hash or immutable version
- start/end/exit and attempt number
- input/output artifacts
- capability grants and EffectReceipts
- resource usage
- reconciliation status

### `execution.results`

Typed results labelled by evidence class, including simulation, retrospective analysis, formal derivation, benchmark execution, prospective experiment, measurement audit, and external-service observation. No execution result is promoted to empirical evidence without the corresponding provenance and evidence-class gate.

## 8. Runtime

### `runtime.runs`

- RunSpec fields
- status
- current workflow version
- parent run/replay relation
- expected node count
- completion summary

### `runtime.node_attempts`

- run/node/attempt unique
- state
- lease owner
- fencing token
- input/output hashes
- result artifact
- timestamps/error class

### `runtime.events`

- run ID
- monotonically increasing sequence per run
- event type/version
- canonical payload
- previous event hash
- event hash
- created at

A reducer reconstructs current state. Stored materialized status is checked against replay.

### `runtime.artifacts`

- artifact ID
- content hash
- type/schema version
- size
- object URI
- creator event
- verification status

### `runtime.action_intents`

Typed proposed external effect, capability, approval state, idempotency key.

### `runtime.effect_receipts`

Actual effect result, external ID, input/output hash, exit status, timestamps.

### `runtime.reconciliation_records`

Intent/receipt/state comparison and repair disposition.

### `runtime.checkpoints`

- checkpoint ID
- run/workflow layer
- artifact manifest
- DB event sequence
- repository commit/hash if development run
- gate summary
- approved by

## 9. Indexes

Initial:
- DOI/identifier indexes
- paper version/content hash
- source span paper/page
- GIN on normalized scope JSONB where needed
- subject/relation/object composite
- evidence role + scope hot fields
- dataset family/cluster
- FTS vectors for spans/claims
- pgvector embedding indexes after benchmark
- run/node/state
- event run/sequence unique
- artifact content hash
- idempotency key unique in effect domain

Do not add HNSW/IVFFlat before corpus/vector benchmark selects dimensions and recall/latency tradeoff.

## 10. Transaction boundaries

- document registration + artifact record
- claim revision + span links
- evidence pack manifest + membership
- node result + event + artifact references
- effect receipt + reconciliation
- promotion gate + passport revision

External effects use outbox/intent pattern; DB transaction cannot pretend to atomically commit a remote API call.

## 11. Row integrity

- unknown enum values rejected at domain boundary
- canonical integers remain integers; no coercive read
- timestamps timezone-aware
- units have canonical and original representation
- null means unknown/not reported; separate flags for not applicable
- deletion uses tombstone and impact analysis
- derived projections carry source snapshot/version
