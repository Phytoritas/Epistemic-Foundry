# A05 Negative and Adversarial Contract Test Registry

Status: `NORMATIVE TEST REQUIREMENTS`

These tests bind the A05 charter. A C01 schema implementation and every later
runtime implementation must preserve the listed rejection. `PASS` below means
that the test successfully observed the required rejection or typed blocker;
it never means that the adversarial promotion was accepted.

## 1. Pin, seal, and integrity cases

| Test ID | Adversarial fixture | Required gate/outcome |
| --- | --- | --- |
| `A05-NEG-001` | `resolved_refs.workflow.exact_version_or_revision` is `main`. | G00 rejects the floating reference with `FAIL`; it does not resolve current HEAD. |
| `A05-NEG-002` | A resolved artifact's bytes do not match its `content_hash`. | G00 emits `FAIL` for hash mismatch/tampering. |
| `A05-NEG-003` | The exact licensed corpus snapshot is defined but unavailable. | G00 emits `BLOCK` and the run outcome is `BLOCKED`; no replacement corpus is selected. |
| `A05-NEG-004` | A set-semantic array has no schema-declared canonical sort. | Resolution stops with `SPEC_GAP`; the implementation does not invent ordering. |
| `A05-NEG-005` | A sealed prompt bundle changes under the same `evolution_run_id`. | G00 emits `FAIL`; a new spec revision and run ID are required. |

## 2. Firewall, evidence, and statistics cases

| Test ID | Adversarial fixture | Required gate/outcome |
| --- | --- | --- |
| `A05-NEG-006` | The current evaluator is mutated after the spec is sealed. | `G02_EVALUATOR_HOLDOUT_FIREWALL` emits non-waivable `FAIL`. |
| `A05-NEG-007` | Candidate, model, prompt, or backend requests `holdout:read`. | `G02_EVALUATOR_HOLDOUT_FIREWALL` denies access and emits non-waivable `FAIL`; approval cannot override it. |
| `A05-NEG-008` | Promotion is justified only by a scalar or combined score. | G01 rejects scalar-only promotion with non-waivable `FAIL`. |
| `A05-NEG-009` | Expected/generated/evaluated/persisted/failed/cancelled/missing counts do not reconcile. | G03 emits non-waivable `FAIL`; partial fan-in cannot promote. |
| `A05-NEG-010` | Required source span or artifact receipt is absent. | G04 emits non-waivable `FAIL`. |
| `A05-NEG-011` | `UNSEARCHED` is relabeled `SEARCHED_NONE` to claim absence or novelty. | G05 emits `FAIL` and prohibits the broader claim. |
| `A05-NEG-012` | Adaptive selection occurred but the sequential ledger, multiplicity adjustment, or selective-inference report is missing. | G08 emits non-waivable `FAIL`. |

## 3. Replication, Parliament, attestation, and approval cases

| Test ID | Adversarial fixture | Required gate/outcome |
| --- | --- | --- |
| `A05-NEG-013` | A request for `REPLICATED` has no calculated replication ceiling or replication status. | G10 emits `FAIL`; an empty result array is not accepted. |
| `A05-NEG-014` | Replication is `FAILED` for the core empirical effect but grant is `REPLICATED`. | G10 emits `FAIL`, maximum level becomes `LITERATURE_GROUNDED`, and PromotionEffect is `LOWER` or `BLOCK`. |
| `A05-NEG-015` | Parliament majority recommends promotion while a deterministic gate failed. | G11 emits `FAIL`; majority cannot override the deterministic gate. |
| `A05-NEG-016` | Candidate generator, implementer, first adjudicator, same mutable prompt lineage, or promotion committer acts as attestor. | G12 emits `FAIL` for self/non-independent attestation. |
| `A05-NEG-017` | The candidate's maker issues its own ApprovalRecord. | G01/G13 emit non-waivable `FAIL` for self-approval. |
| `A05-NEG-018` | Human approval attempts to waive evaluator mutation, holdout leakage, missing provenance, statistics, reconciliation, receipt, or integrity. | The originating non-waivable gate remains `FAIL`; G13 cannot convert it to PASS. |
| `A05-NEG-019` | Approval is required but `approval_record_ids` is empty. | G13 emits `FAIL` or `BLOCK`; absence is not silently treated as `NOT_REQUIRED`. |

## 4. Receipt, idempotency, and crash cases

| Test ID | Adversarial fixture | Required gate/outcome |
| --- | --- | --- |
| `A05-NEG-020` | Promotion commit lacks an `EffectReceipt` or required `ArtifactReceipt`. | G14 emits non-waivable `FAIL`; completion is not recorded. |
| `A05-NEG-021` | The same idempotency key is retried with a different canonical request hash. | G14 returns conflict and performs no state change. |
| `A05-NEG-022` | The same idempotency key and request hash are retried after a response loss. | The existing logical result is returned or resumed; no duplicate effect or revision is created. |
| `A05-NEG-023` | A crash occurs after CAS may have committed but before a resolving EffectReceipt is observed. | Success remains unknown; canonical state and ledger are reconciled before retry, `FAIL`, or `BLOCKED`. |
| `A05-NEG-024` | A prior Passport or PromotionDecision would be overwritten in place. | G14 rejects the write; a new immutable revision is required. |

## 5. Positive boundary controls

These controls prevent the negative tests from overblocking truthful lower
states:

| Test ID | Control | Required result |
| --- | --- | --- |
| `A05-POS-001` | An incomplete claim is stored as `INBOX` with provenance and no support/novelty claim. | G03/G05/G11/G12 may PASS only with policy-backed `NOT_REQUIRED`; no higher-level meaning is granted. |
| `A05-POS-002` | A low-risk internal `CANDIDATE` promotion is explicitly allowed by the sealed PolicyBundle. | G13 records policy rule and `NOT_REQUIRED` for human approval; it does not omit the gate. |
| `A05-POS-003` | Replication is not run for an otherwise valid empirical test. | Grant is at most `EMPIRICALLY_TESTED`, and decision is `CONDITIONAL` or `UNDERDETERMINED`. |
| `A05-POS-004` | A purely formal artifact has the policy-declared not-applicable class and two independent formal-verifier paths. | Replication-equivalent eligibility may be recognized; the exception remains unavailable to empirical claims. |

## 6. Implementation expectations

Schema tests must prove the closed level enum, required references, hash
patterns, promotion-pack links, and semantic checks that can be represented in
JSON Schema. Contract tests must handle cross-artifact rules that JSON Schema
cannot prove alone. Runtime tests must exercise capability denial, immutable
evaluator/holdout boundaries, deterministic gates, idempotency, CAS, crash
recovery, ledger/receipt reconciliation, and no source-tree or conversational
fallback.

Every failure assertion records the gate ID, input hash, decision hash, policy
version, and evidence IDs. A test that merely raises an untyped exception or
returns a scalar false does not satisfy this registry.
