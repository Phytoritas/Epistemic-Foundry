# Verification and Test Plan

## 1. Test layers

### Unit
- schema/domain invariants
- unit conversion
- scope overlap
- dependency clustering
- gate predicates
- reducer transitions
- hash/idempotency

### Property-based
- event replay determinism
- serialization round-trip
- no scope widening through normalization
- unit conversion reversibility within tolerance
- duplicate insertion idempotency
- DAG scheduler respects dependencies

### Golden
- GROBID/Docling fixtures
- source bbox/char mapping
- atomic claims
- method compatibility
- contradiction labels
- known false insights

### Integration
- PostgreSQL migrations/repositories
- object store integrity
- parser adapters
- lexical/vector retrieval
- provider adapter ResultEnvelope
- lease/fencing/retry
- registered ValidationTarget sandbox and capability-denial fixtures

### E2E
```text
PDF → Claim → Evidence → Insight → Coverage → Evidence Pack
→ Parliament → Gates → Passport → Validation Plan or Experiment Ticket → Reconciliation → Replay
```

### Security
- prompt injection PDF
- malicious metadata/filenames
- path traversal
- oversized/decompression bomb limits
- secret redaction
- capability denial
- untrusted tool argument rejection

### Recovery/chaos
- parser outage
- provider timeout/rate limit
- worker death after external effect
- stale lease writer
- partial fan-out
- DB restart
- object checksum mismatch
- restore from backup
- model/prompt drift replay

## 2. Test evidence

A test run artifact includes:
- command
- environment/commit
- start/end
- exit code
- collected/pass/fail/skip/xpass/xfail counts
- stdout/stderr references
- coverage where relevant
- fixture/gold version
- hash

## 3. Scientific benchmark splits

- tuning/development
- visible validation
- hidden holdout
- time-sliced future evidence
- adversarial known-false
- method-incompatibility
- boundary-not-contradiction
- dependency duplication

No hidden holdout item may be used in prompt examples.

## 4. Required non-regression

Every bug/finding that is fixed adds a focused regression test or a documented reason why a deterministic test is impossible.

## 5. Empty-test defense

Fail CI when:
- expected test directory collects zero
- benchmark subset unexpectedly empty
- all cases skipped
- requested provider integration silently uses a mock
- expected workflow node produces no receipt

## 6. Performance

Report distributions, not one anecdotal runtime:
- pages/sec ingest
- claims/page
- retrieval p50/p95
- council layer p50/p95
- tokens/cost per accepted/rejected passport
- object/DB growth
- cache/reprocessing ratio

## 7. Acceptance authority

`manifests/acceptance_matrix.yaml` is the release threshold source. Threshold changes after seeing results require a versioned decision record.
