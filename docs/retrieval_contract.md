# Retrieval, Ranking, and Evidence-Pack Contract

## 1. Authority and ownership

Retrieval optimizes decision coverage, not generic semantic similarity. O01
owns `QueryPlan`, the eleven-lane reconciliation, `SearchLaneReceipt`, and
`SearchCompletenessCertificate`. O02 owns provider adapters, untrusted-response
validation, `RetrievalCandidate`, lane-local deduplication, rank fusion, and the
candidate-set result. O03 alone resolves candidates to `SourceSpan`,
`EvidenceNode`, dependency clusters, and an Evidence Pack.

`RetrievalCandidate` is the O02 business output. `ResultEnvelope` is telemetry
only and records candidate IDs in `output_artifact_ids`; it is not candidate
truth. The O01 sealer verifies candidate IDs, hashes, counts, query, snapshot,
and index bindings before it emits a lane receipt.

## 2. Provider-neutral backend request

Every backend request seals these values:

- `run_id`, `query_plan_id`, `plan_hash`, and `lane`
- `query_families`, canonical `query_batch`, and `query_hash`
- `scope_filter`, `corpus_snapshot_hash`, and `index_versions`
- `max_candidates`, `cutoff_policy_id`, and `deterministic_seed`
- `policy_bundle_hash` and `capability_lease_id`
- `backend_id`, `backend_version`, `adapter_id`, and `adapter_version`

`query_batch` is an object containing the lane and a canonical-family-ordered
array of deduplicated ordered queries. `SearchLaneReceipt.query_text` stores its
exact JCS-equivalent JSON string, and `query_hash` is the SHA-256 of those UTF-8
bytes. A raw backend response is untrusted until its schema, request, receipt,
query, snapshot, index, rank, and source locator all validate.

## 3. Lanes and query families

The lane-to-family binding is fixed:

| Lane | Required query family | Additional contract |
|---|---|---|
| `lexical` | `FORWARD` | Preserve exact terms, identifiers, and phrases. |
| `semantic` | `FORWARD` | Record vector provenance explicitly. |
| `citation` | `FORWARD` | Use queries as citation seeds. |
| `entity_variable` | `FORWARD` | Entity, variable, and unit edges may expand the query. |
| `mechanism` | `FORWARD` | Preserve mechanism edges and intermediate nodes. |
| `counterevidence` | `FORWARD`, `REVERSE` | Both families are required. |
| `null` | `NULL` | Use only null, no-effect, or equivalence queries. |
| `boundary` | `BOUNDARY` | Include moderator, threshold, or neighboring scope. |
| `method` | `METHOD` | Include measurement, design, or construct terms. |
| `temporal` | `FORWARD` | A versioned date/correction filter is required. |
| `external_novelty` | `NOVELTY` | External scope and a stop rule are required. |

A selected lane with a missing required family fails closed with
`INVALID_QUERY_FAMILY_BINDING`.

## 4. Canonical candidate identity and content hash

`candidate_id` is `RC-` plus the lowercase SHA-256 of the JCS-equivalent object
containing, in the schema-declared identity preimage, `plan_hash`, `lane`,
`query_hash`, `canonical_source_key`, `source_version`, and
`source_snapshot_hash`.

`candidate_hash` covers the schema-declared full canonical content: resolved
provenance, backend observations and receipts, ranks, scores, features, and
duplicate lineage. It excludes only `candidate_id`, `candidate_hash`, generated
time, and storage locator. Placeholder hashes are invalid. Nullable values keep
their keys.

The duplicate identity is the tuple `canonical_source_key`, `source_version`,
`source_snapshot_hash`, and `source_locator`. Same-lane duplicates collapse to
one candidate while retaining every channel observation and duplicate ID.
Cross-lane evidence-dependency deduplication remains O03 responsibility.

A candidate with `source_span_id=null` is metadata-only. It may be retained for
discovery but cannot directly become an `EvidenceNode` or promoted evidence.

## 5. Relation direction

The closed vocabulary is `SAME_DIRECTION`, `REVERSE_DIRECTION`,
`INVERSE_PREDICATE`, `BIDIRECTIONAL`, `NO_DIRECTION`, and `UNRESOLVED`.

For canonical `A parent_of B`, `A parent_of B` is `SAME_DIRECTION`,
`B parent_of A` is `REVERSE_DIRECTION`, and registered inverse
`B child_of A` is `INVERSE_PREDICATE`. Explicit claims in both directions are
`BIDIRECTIONAL`; symmetric relations are `NO_DIRECTION`; insufficient trusted
grounding is `UNRESOLVED`. Neither `NO_DIRECTION` nor `UNRESOLVED` is a
direction match. Only a versioned ontology or DomainPack may register an
inverse predicate; a model cannot invent one.

## 6. Deterministic deduplication, ranking, and cutoff

Each lane processes results in exactly this order:

1. validate backend response and receipt;
2. validate QueryPlan, corpus snapshot, and index bindings;
3. generate `canonical_source_key`;
4. collapse exact duplicates within each channel;
5. stably order channel hits by `raw_rank`, then `canonical_source_key`;
6. fuse multi-channel candidates with RRF;
7. calculate transparent ranking features;
8. apply the policy `max_candidates` cutoff;
9. resolve final ties by ascending `candidate_id`;
10. record excluded, duplicate, and cutoff counts.

RRF is mandatory for multi-channel fusion and is fixed at:

```text
RRF(d) = Σ_channel 1 / (60 + rank_channel(d))
```

Raw scores are never compared across channels. O02-0002 has no learned
reranker. A future learned reranker requires a separate product decision,
version, qualification, and replay contract. Retrieval rank and score are
search priority, never scientific evidence strength.

## 7. Snapshot, integrity, terminal state, and fallback

`plan_hash`, `corpus_snapshot_hash`, `index_versions`, backend and adapter
versions, `policy_bundle_hash`, and cutoff policy are immutable during a lane
execution. A request/response mismatch or a source/index change during the run
ends as `FAILED / integrity_failure / STALE_RETRIEVAL_SNAPSHOT`. Candidate,
hash, or receipt mismatch also fails.

Policy denial, missing credentials, and a missing required backend are typed
`BLOCKED`. Provider errors and malformed or unknown responses are `FAILED`.
Valid bounded interruption is `PARTIAL`. Only a fully executed zero-result plan
is `SEARCHED_NONE`; only a fully executed non-empty plan is
`SEARCHED_WITH_RESULTS`. Silent cross-channel fallback is forbidden, and an
incomplete planned backend or query family cannot be reported as complete.

## 8. Non-vector guard

For E1 or higher, the O01-required lexical, semantic, citation, and temporal
lanes actually execute. A semantic-only run cannot pass. Any non-empty release
set contains at least one candidate originating from `LEXICAL`,
`CITATION_GRAPH`, `RELATION_GRAPH`, or `EXTERNAL_INDEX`. Vector-only candidates
remain retained with `multi_channel_verified=false`, and the run ceiling is
`PARTIAL`. A bounded complete search in which all required lanes are
`SEARCHED_NONE` may pass.

## 9. Evaluation oracle

Acceptance uses versioned local, network-free, and LLM-free fixtures. Contract,
direction, provenance, integrity rejection, invalid-response rejection,
deduplication, and replay cases require 100% exact results. Per-required-lane
Recall@20 is at least 0.90 and nDCG@20 at least 0.85; fused Recall@20 is at
least 0.95. Critical counter, null, boundary, and method must-find cases require
100%. Vector-only violations, silent fallbacks, skips, and xfails are zero. A
failing lane cannot be averaged away, and `PARTIAL`, `BLOCKED`, or `FAILED`
runs are not successful benchmark samples.

## 10. Evidence-pack boundary

Before evidence promotion, O03 resolves an exact full-text source span,
verifies grounding, normalizes scope and method, and resolves source version
and dependency. Abstract-only and metadata-only candidates remain labeled and
cannot masquerade as direct measurement. Evidence Pack quotas are targets, not
permission to invent missing evidence; truthful searched-none and unsearched
states remain visible.
