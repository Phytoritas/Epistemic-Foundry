# A06 constitutional audit of evolution authority

## Verdict

`A06-0001` is `FAIL`. The A05-0002 authority contract is clear, locally
available, and hash-bound, but the governing evaluator, holdout, and promotion
execution surfaces do not enforce it. This is implementation and integration
nonconformance, not a new `SPEC_GAP` and not an unavailable-resource
`BLOCKED` outcome.

`completion_ready` remains `false`. This audit changes no product schema,
workflow, runtime, prompt, policy, or package implementation.

## Authority and scope

The audited authority is the product-owner decision
`HD-EF4-A05-C01-B04-20260727-001` as realized by the immutable A05-0002
charter. The five A05-0002 bound artifacts still match their recorded SHA-256
values. The historical top-level A05 `SPEC_GAP` report remains unchanged while
the later A05-0002 attempt remains the resolving `PASS` evidence.

A06 may write only `docs/v4_a06/**` and
`artifacts/work_packages/A06/**`. Accordingly, this attempt provides audit
evidence and a fail-closed verdict only. It does not repair the failed
surfaces.

## Blocking findings

| ID | Severity | Constitutional failure |
|---|---|---|
| `A06-F001` | CRITICAL | `schemas/evaluator-bundle.schema.json` accepts `readable_by_candidates=true` and `mutable_during_run=true`. |
| `A06-F002` | CRITICAL | `schemas/holdout-manifest.schema.json` and the runtime seal path accept `METADATA_ONLY` and `AGGREGATE_ONLY` candidate access instead of enforcing `NONE`. |
| `A06-F003` | CRITICAL | `run_evidence_parliament_promotion` is a provider-nondeterministic LLM node that directly emits `PromotionDecision`, and Passport issuance depends directly on it. |
| `A06-F004` | CRITICAL | The Passport path does not graph-enforce G00-G14 decisions, Parliament adjudication, independent attestation, approval, a short `promotion:commit` lease, expected-revision CAS, or effect/artifact receipts. |
| `A06-F005` | HIGH | The bounded helper in `src/epistemic_foundry/governance/promotion.py` is present but is not bound to the canonical evolution workflow. |

The detailed machine-readable reproduction is
`artifacts/work_packages/A06/attempts/0001/constitutional-audit-verification.json`.
The verifier intentionally returns exit code 1 when these constitutional
findings are present. Two independent executions produced byte-identical JSON.

## Why passing tests do not override the verdict

The focused Python regression selection passed 214 of 214 tests, the filtered
adversarial selection passed 13 of 13 tests, and the capability/fencing Node
selection passed 30 of 30 tests. Those results show that existing bounded
helpers remain internally consistent. They do not show that the canonical
workflow calls those helpers or that the schemas reject constitutionally
forbidden states. The hostile fixtures in the A06 verifier demonstrate the
opposite.

The full Python suite collected 964 tests: 963 passed and one failed. The sole
failure is the pre-existing J02 dependency-lock failure
`tests.test_j02_context_budget::test_repository_dependency_lock_closes_exact_tiktoken_pin`.
Its node ID and message match the prior J02-0002 evidence. A06 caused no new
Python failure and did not mask the existing failure with a skip or xfail.

## RAH preservation

RAH remains read-only because its implementation gate is already failed for
the J02 exact `tiktoken==0.13.0` lock and S04-TM004 traceability fingerprint
blockers. Generation `000081-843d5565`, its manifest, and all six payload
hashes were verified without appending evidence, creating a generation,
resuming, or resealing state. The latest preserved evidence remains `E0084`.

## Dependency effect

With A06 recorded as `FAIL`, the current 156-package projection has 42 latest
attempts at `PASS`, four attempted non-PASS packages (`J02`, `K01`, `T01`, and
`A06`), one independently ready package (`J03`), and 109 unstarted blocked
packages. The seven direct A06 dependents are `B05`, `C05`, `D05`, `E05`,
`F05`, `G05`, and `S05`; each remains `WAITING_ON_A06_REMEDIATION`.

## Remediation boundary

A resolving attempt needs bounded ownership and write authority for all of the
following coordinated surfaces:

- the evaluator and holdout canonical schemas and their examples/tests;
- the verifier-firewall runtime that seals and enforces those artifacts;
- the canonical evolution workflow and promotion prompt boundary;
- deterministic G00-G14, Parliament, attestation, approval, lease, CAS, and
  receipt bindings on the Passport path;
- relevant generated projections and the B04 canonical-package reprojection
  after any root canonical schema change.

A06 itself does not own those paths. The five findings remain `FAIL`; the
separate question of assigning a remediation owner and exact write scopes must
be resolved before a new A06 attempt can pass.

## Review limitation

The product owner prohibited Fleet and subagents. The review is therefore a
procedurally separate `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`, not
actor-independent certification. Its verdict is `FAIL_CONFIRMED`.
