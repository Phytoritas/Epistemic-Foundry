# A06-0001 constitutional integration review

## Verdict

`FAIL_CONFIRMED`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

The A05-0002 contract is hash-bound, complete enough to supply a deterministic
oracle, and locally reproducible. A06 nevertheless fails five non-waivable
constitutional integration criteria. The correct typed outcome is `FAIL`, not
`SPEC_GAP` or `BLOCKED`.

## Blocking findings

1. `A06-F001` — CRITICAL. The canonical evaluator schema accepts
   `readable_by_candidates=true` and `mutable_during_run=true`. These are
   forbidden evaluator states, not harmless optional policy choices.
2. `A06-F002` — CRITICAL. The canonical holdout schema and runtime seal path
   accept `METADATA_ONLY` and `AGGREGATE_ONLY` candidate access. A05 requires
   candidate access to be false/`NONE`.
3. `A06-F003` — CRITICAL. The canonical evolution workflow assigns a
   provider-nondeterministic LLM prompt direct `PromotionDecision` output, and
   Passport issuance depends directly on that node. This makes the model/prompt
   an effective promotion authority.
4. `A06-F004` — CRITICAL. The Passport path does not graph-enforce G00-G14
   `GateDecision` artifacts, Parliament adjudication, independent attestation,
   approval, a short `promotion:commit` lease, expected-revision CAS, or
   resolving effect/artifact receipts.
5. `A06-F005` — HIGH. The bounded promotion helper implements strong controls,
   but the canonical evolution workflow binds neither its decider nor its
   committer. Isolated helper correctness is not canonical-path enforcement.

All five are reproduced by
`constitutional-audit-verification.json`. The verifier exits 1 by design when
the findings exist; two executions leave the JSON byte-identical at
`sha256:5c5c5ad88c5aba464ab007fb8ac278c5be8e2ada00c54726e816569702be7431`.

## Adversarial interpretation

The strongest plausible counterargument is that existing governance,
firewall, and evolution tests pass and that
`src/epistemic_foundry/governance/promotion.py` already implements the required
rules. That argument fails at the authority boundary. The governing schemas
accept hostile fixtures, and the governing evolution graph bypasses the
helper. Passing 214 targeted tests, 13 filtered adversarial tests, and 30
capability/fencing tests therefore cannot override the direct schema and graph
counterexamples.

The full Python suite has one failure among 964 tests. Its node ID and
`TOKENIZER_CONTRACT_UNAVAILABLE` message match J02-0002's existing exact-lock
failure. It is not attributed to A06 and is not hidden. Repository-wide green
status is not claimed.

## Scope and history review

A06 product-file modifications are zero. The attempt writes only
`docs/v4_a06/**` and `artifacts/work_packages/A06/**`. It does not weaken a
schema, edit a workflow, change runtime behavior, append RAH evidence, create a
generation, resume the blocked goal, or alter prior attempts. The dirty
worktree remains preserved.

RAH generation `000081-843d5565` and all six manifest-bound payload hashes
match in read-only verification. RAH remains blocked by the pre-existing J02
tokenizer-lock and S04-TM004 traceability blockers.

## Dependency consequence

`B05`, `C05`, `D05`, `E05`, `F05`, `G05`, and `S05` remain
`WAITING_ON_A06_REMEDIATION`. `J03` is independently dependency-ready and does
not depend on A06.

A resolving change needs bounded ownership of the evaluator/holdout schemas,
verifier-firewall runtime, canonical evolution workflow, related tests and
generated projections, and any required B04 reprojection. Those repairs are
outside A06's audit-only write scope. The A06 failure itself is not converted
into a `SPEC_GAP`; only the subsequent remediation owner/write-scope assignment
remains a product-authority action.

## Assurance limitation

The product owner prohibited Fleet and subagents. This review is procedurally
separate within the primary session, not actor-independent certification. No
independent-attestor claim is made.

Final verdict: `FAIL_CONFIRMED` with blocking findings
`A06-F001` through `A06-F005`.
