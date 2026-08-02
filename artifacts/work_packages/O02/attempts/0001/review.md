# O02 primary-session separate adversarial contract review

Status: `SPEC_GAP (O02-SG001)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: this is a procedurally separate primary-session review,
not actor-independent certification. Fleet and subagents are prohibited by the
active execution contract, so the manifest's independent-review requirement is
not waived or misrepresented as independently satisfied.

## Verdict

O01-0002 is an evidence-sealed `PASS`, so O02 is dependency-ready. The active
authority chain fixes the retrieval lanes, QueryPlan selection, snapshot-bound
plan hashes, and common SearchLaneReceipt state fields. It does not define the
provider-neutral candidate or execution semantics required to implement the
lexical, semantic, citation, and relation lanes or to score their acceptance
checks. The correct result is fail-closed `SPEC_GAP`, before product code is
created.

## Blocking findings

1. There is no canonical `RetrievalCandidate` (or equivalent) artifact. A raw
   hit therefore has no authoritative identity, rank, score, source locator,
   provenance, backend receipt, or integrity binding. `EvidenceNode` and
   `SourceSpan` are downstream evidence contracts, not retrieval-hit contracts.
2. QueryPlan contains forward, reverse, null, boundary, method, temporal, and
   novelty query families, but no contract maps those families to each O02
   lane or defines whether one lane may execute multiple families.
3. Relation direction is prose only. There is no closed direction enum, edge
   orientation, inverse-predicate behavior, reverse-query mapping, invalid
   direction rule, or fixture with exact expected results.
4. Ranking semantics are absent: score domains and normalization, cutoff
   timing, deduplication identity and ordering, deterministic tie-breaking, and
   cross-channel fusion are all undefined.
5. Query and receipt hashes exist, but the exact binding from corpus snapshot
   and index revision through backend response and candidate set is missing.
   Stale or mismatched backend results therefore cannot be rejected by a
   canonical rule.
6. Backend failure semantics are not closed. Unavailable, partial, malformed,
   stale, or policy-denied responses have no required lane outcome or fallback
   rule, and silent lexical/vector substitution is not explicitly bounded.
7. `vector-only retrieval avoided` is a narrative invariant. No minimum
   independent channel, fusion contribution, evidence-count, or provenance
   rule makes it mechanically testable.
8. `retrieval_benchmark` and `relation_direction_test` occur only as manifest
   check names. There is no benchmark corpus, query set, relevance judgment,
   metric, threshold, tolerance, direction fixture, or exact answer oracle.
9. O02's implementation-only write scope does not authorize the tests,
   fixtures, benchmark corpus, or evidence artifacts a resolving attempt would
   require. It also does not resolve whether O02 emits raw candidates or a
   complete SearchLaneReceipt.

## Classification

This is not `FAIL`: no implementation was run against a clear oracle. It is not
`BLOCKED`: the audit has not established that a required tool, credential,
licensed corpus, backend, or host capability is unavailable. The missing item
is the shared product contract itself, and the O02 stop condition explicitly
requires `SPEC_GAP` when an authority boundary or threshold is ambiguous.

## Required product decision

A product-owner HumanDecision must freeze the candidate artifact, backend
interfaces, lane-to-query mapping, relation direction, ranking/deduplication,
snapshot integrity, failure/fallback, multi-channel rule, exact benchmark and
direction fixtures and thresholds, ownership boundary, and bounded resolving
write scopes.

O02-0001 must remain immutable `SPEC_GAP` history. Do not invent a backend,
candidate schema, metric, threshold, or fallback; do not start a later package
while this earliest manifest-order package is unresolved.
