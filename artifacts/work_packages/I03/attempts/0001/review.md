# I03-0001 independent review of bounded-agent work

- Author: a bounded implementation agent (disjoint write scope, frozen
  contracts) under the product owner's explicit instruction. Reviewer:
  the sealing agent, which did not author this attempt; author/reviewer
  separation holds with actor_independence=true, while external
  actor-independent certification does not.
- Same label, different construct is never silently merged: a raw term
  resolves only when exactly one complete viable candidate exists within
  the pinned ontology/DomainPack authority; a label shared by distinct
  construct_ids returns AMBIGUOUS and routes to the review queue when the
  mapping is high-impact or high-frequency, and an inexact term is UNKNOWN
  with no candidate.
- String similarity is not mapping authority: NFKC, case, and whitespace
  folding is compatibility normalization only; no edit distance, stemming,
  synonym expansion, or embedding is ever consulted, and an alias binds a
  label only when the catalog entry declares it explicitly.
- Distinct construct identities are never pooled: compare_measurements
  returns NOT_COMPARABLE / DIFFERENT with BLOCK_AGGREGATION for distinct
  construct_ids, and scope, support, unit, method, protocol, calibration,
  domain-pack, and proxy differences each bind aggregation to their exact
  promotion ceiling rather than collapsing to a single comparable pool.
- The human approval queue exists and is authoritative: ambiguous,
  high-impact, high-frequency, and unknown-term mappings each produce a
  deterministic MappingReviewItem whose required_authority_artifact is
  HumanDecision; the item is a proposal that never selects the construct,
  and its review_item_id binds the full mapping context so a change in
  population or frequency mints a new item.
- Unit conversion needs an explicit directional bridge: an external
  authority MeasurementBridge, matched on the ordered identity-hash pair,
  is the only path from a unit mismatch to CONVERTIBLE; it is not silently
  reversed, duplicate matching bridges fail closed, and a permissive
  ceiling is required before aggregation is allowed.
- Fail-closed on adversarial input: mutable catalog or bridge collections,
  duplicate construct or bridge ids, one measurement id naming two
  semantic identities, foreign or absent authority, and malformed
  contracts each raise the exact finding code (ONTOLOGY_INPUT_INVALID,
  ONTOLOGY_INPUT_DUPLICATE, ONTOLOGY_CATALOG_DUPLICATE_ID,
  ONTOLOGY_AUTHORITY_UNAVAILABLE, MEASUREMENT_INPUT_INVALID,
  MEASUREMENT_IDENTITY_INVALID, MEASUREMENT_IDENTITY_CONFLICT,
  MEASUREMENT_BRIDGE_INVALID, MEASUREMENT_BRIDGE_DUPLICATE_ID,
  MEASUREMENT_BRIDGE_AMBIGUOUS) rather than degrading silently.
- Boundary: the resolver imports the standard library alone and resolves
  one mapping or compares two measurement identities; it does not add a
  canonical schema, issue a HumanDecision, persist authority, or implement
  a review UI, and I01 is a manifest-order dependency, not composed code.
  The component ships under python/ and stays out of the wheel.
- Non-blocking residual: the component-local enum strings are documented
  as execution contracts with no canonical schema, and the EF4-I22
  wire-literal gate scans only src/, so it is honestly GREEN here (the same
  idiom as sealed I01/I02).
- Integration gates at review time: ruff check clean, git diff --check
  clean, the two required suites green at 16/16 and 23/23 (39 targeted),
  the EF4-I22 wire-literal gate 5/5, packaging discovery PASS, full Python
  1261/1261 and full Node 1702/1702 across the 136-file inventory. Zero
  blocking findings.
