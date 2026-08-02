# C01 attempt 0003 contract review

Status: `SPEC_GAP_WITH_USER_AUTHORIZED_PRIMARY_SESSION_REVIEW`

Review procedure: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

Reviewer identity: primary-session contract review. The product owner prohibited
Fleet and subagents and explicitly approved direct review for this serial
execution. This pass was performed after implementation and deterministic
verification. It is procedurally separate from authoring, but it is not
actor-independent assurance and does not waive a non-waivable regression or
shared-contract gate.

## Authority and history reviewed

- `HD-EF4-C01-SG002-20260728-001`, including its exact two-file example scope;
- `HD-EF4-A05-C01-B04-20260727-001` and the A05 attempt-0002 charter;
- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, and the C01 entry
  in `manifests/development_manifest.yaml`;
- all C01-0003 schema, example, OpenAPI, documentation, and contract-test
  changes;
- the unchanged C01-0001 and C01-0002 reports and C01-SG002 evidence;
- the five runtime/test paths implicated by the full-suite regression;
- deterministic evidence at
  `artifacts/work_packages/C01/attempts/0003/c01-regression-boundary-verification.json`.

The C01-0003 verification artifact is
`sha256:c0bf2ba5e156845731229bced427af3f390bcc3f77891fcd7e3075701fa27ee0`.
The prior C01-0002 report remains
`sha256:c8100002239cf826c9fe521f86f84295e1cdec3bbe5e49f210c4a7e124d31369`.

## Findings

1. **C01-SG002 resolution — confirmed.** The new HumanDecision is recorded,
   its hash is preserved, and only the two exact example paths were appended
   to C01's existing write scope. No dependency, owner, resource scope, or
   other package scope was changed by that decision.
2. **EvolutionRunSpec contract — PASS.** The schema requires twenty canonical
   resolved reference classes, uses the A05 pin tuple and hash constraints,
   conditionally handles an external backend manifest, and keeps
   `resolved_refs` mandatory. The deterministic example has no floating
   reference and its `spec_hash` recomputes to
   `sha256:580392a2d791515a6523472372fa3139321807a9fa3a2a0f183e93b4686948df`.
3. **Promotion contract — PASS.** The schema exposes only the six A05 promotion
   levels and the canonical G00-G14 order. The example requests `REPLICATED`,
   grants `EMPIRICALLY_TESTED`, records `PARTIAL` replication and
   `CONDITIONAL`, and its `decision_hash` recomputes to
   `sha256:781e2449498ee9799c8f62b6a8b4cd08289891587a86a795e8f45459e09f9f5f`.
   `PILOT` and `HYPOTHESIS_PASSPORT_ONLY` have zero hits in canonical schemas
   and examples.
4. **Canonical schema/examples — PASS.** All 124 Draft 2020-12 schemas
   meta-validate, all 124 `$id` values are unique, all 124 mapped examples
   validate, and the authorized schema/example cardinality remains unchanged.
5. **REST v1 contract — PASS on the authorized surface.** The canonical file is
   OpenAPI 3.1.1, uses `/api/v1`, contains 33 unique operations, and retains
   the required security, idempotency, revision-precondition, async,
   pagination, problem-response, and scientific-schema reference checks.
   The targeted C01 contract suite passes 64 tests.
6. **Full regression — blocking.** The full Python suite collects 848 tests,
   with 824 passing and 24 failing: two in `test_evolution_chamber.py`, fourteen
   in `test_governance.py`, and eight in `test_integration_forge_cycle.py`.
   The pre-C01 baseline was 789 passing tests; the failures are not hidden
   behind that baseline.
7. **Runtime producer mismatch — confirmed.** The EvolutionRunSpec producer
   does not emit the new required `resolved_refs` or
   `external_backend_enabled` values. The promotion runtime and regression
   fixtures retain out-of-contract `NONE` and `SUPPORTED` meanings. C01 is
   explicitly forbidden to implement API/runtime behavior or modify these
   paths.
8. **Migration ownership gap — confirmed.** No work package in the development
   manifest owns any of the following paths:
   `src/epistemic_foundry/evolution_chamber/run_spec.py`,
   `src/epistemic_foundry/governance/promotion.py`,
   `tests/test_evolution_chamber.py`, `tests/test_governance.py`, or
   `tests/test_integration_forge_cycle.py`. There is therefore no authorized
   package to perform the required contract migration.
9. **Non-promotion level semantics — undefined.** `PromotionDecision` requires
   a closed six-level `granted_level`, while the runtime uses `NONE` when a
   request is blocked or underdetermined. The request/runtime input supplies no
   current Passport level. Defaulting to `INBOX` or another level would be an
   invented authority decision and could relabel a failed request as a lower
   scientific state without the immutable revision workflow required by A05.
10. **Typed outcome — SPEC_GAP.** This is not a simple in-scope implementation
    failure: the authorized C01 surface passes, the needed runtime paths are
    both out of scope and unowned, and a required semantic is absent. It is not
    `BLOCKED` because no tool, credential, licensed source, or backend is
    missing. Schema relaxation or legacy alias restoration would violate the
    product-owner contract.
11. **Whole-bundle diagnostic — separated.** `validate_spec_bundle.py
    --no-audit` reports fourteen `PACKAGE_MANIFEST` hash/inventory diagnostics
    from the preserved dirty worktree. They are not used as C01 PASS evidence,
    are not deleted or rewritten here, and remain a separate integration
    concern.
12. **History and dependency effect — preserved.** Bound A05, C01-0001,
    C01-0002, C01-SG002, and HumanDecision artifacts retain their hashes.
    A05 remains PASS, C01 is SPEC_GAP, and B04/C02/C03 remain waiting. B04 and
    the later 156-package DAG were not started.

## Required higher-order decision

The minimum resolving decision must:

1. assign a migration owner and exact write scope for the five affected
   runtime/test paths;
2. define `granted_level` for non-promotion decisions, including whether the
   immutable current Passport level must be supplied and retained; and
3. state whether this migration is a prerequisite to C01 PASS or whether the
   full-suite regression gate moves to an explicitly named migration package.

It must not make `resolved_refs` optional, restore legacy promotion aliases,
grant C01 broad runtime scope, waive the full regression, or authorize B04
before C01 passes.

## Decision

The authorized C01 contract implementation is internally conformant, but C01
attempt 0003 cannot be integrated as PASS. `C01-SG003` is a new, minimal
shared-contract and migration-ownership gap. Execution stops fail-closed with
B04 at `WAITING_ON_C01`; all prior history and the dirty worktree are
preserved.
