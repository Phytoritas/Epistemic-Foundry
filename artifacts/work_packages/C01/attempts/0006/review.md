# C01-0006 adversarial contract review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

Non-waivable C01 findings: 0

The product-owner execution contract prohibits Fleet and subagents. This is a
separate primary-session review performed after implementation and test
capture. It is not actor-independent certification, and it does not waive a
contract, projection, runtime, packaging, or repository-wide conformance gate.

## Contract result

The active canonical inventory is exactly 126 Draft 2020-12 schemas and 126
matching examples. Every schema has a unique `$id`; the mapping is one-to-one;
all examples validate. `DocumentRegistrationRequest` and immutable
`DocumentRegistration` are separate canonical artifacts with recomputed
request/registration hashes and digest-bound IDs. The request requires a
staged source artifact rather than instructing the registration operation to
fetch an arbitrary URI.

OpenAPI remains 3.1.1 with 33 unique operations. `POST /documents` references
the canonical request schema and records the canonical registration artifact
as its asynchronous result. It does not retain an OpenAPI-local transport
duplicate. External schema references resolve, operation security/capability
metadata remains explicit, and every mutation requires `Idempotency-Key`.

The targeted contract suite records 77 passed, zero failed, and zero skipped.
External OpenAPI validation and the generated Python client dry-run both
completed successfully. The deterministic evidence builder reproduces its
stored contract, regression, and dependency artifacts byte-for-byte.

## Adversarial findings

1. Legacy evaluator aliases `readable_by_candidates=true` and
   `mutable_during_run=true` are rejected rather than accepted beside the
   canonical immutable fields.
2. Holdout access through candidate, mutation-model, prompt, or backend
   identity is rejected. Legacy `METADATA_ONLY` and `AGGREGATE_ONLY` candidate
   access values are also rejected.
3. `PILOT` and `HYPOTHESIS_PASSPORT_ONLY` are absent from active canonical JSON.
4. Document filename/path and `file:` URI attacks are rejected by the staged
   registration contract.
5. C01 did not modify `src/epistemic_foundry/_canonical/**`; root
   `schemas/**` and `openapi/**` remain the sole canonical authority.
6. C01 did not claim runtime implementation of the G00-G14 graph,
   actor-independence, short leases, CAS, crash reconciliation, or receipt-bound
   commits. Under `HD-EF4-A06-RM001-20260730-001`, A06-F001/F002 are resolved at
   the schema layer, while A06-F003 through A06-F005 remain assigned to the A05
   correction and later C02/C03/C04/B04 reconciliation layers.

## Full-suite boundary

The full Python receipt is **not PASS**: 970 tests were collected, 951 passed,
19 failed, and none were skipped. All 19 nodes are retained in
`full-regression-impact.json` with normalized fingerprints.

- 18 failures are the explicitly authorized pre-C04 B04 reconciliation
  surface: 17 packaging/materializer failures still enforcing 124 schemas and
  one packaged-snapshot example-validation failure.
- 1 failure is the pre-existing J02 tokenizer-lock visibility debt. It is not
  attributed to C01 and is not silently corrected outside C01 scope.
- No additional C01-owned failure was observed.

This residual classification is only sufficient for the bounded C01 package
gate. It does not make the repository green, does not permit C04 to start, and
does not authorize B04 reprojection before C02 and C03 pass.

## Scope and history

All declared C01 changes match the exact manifest write scope. Scoped
`git diff --check` exits 0; the only output is CRLF advisory text. Existing
C01-0001 through C01-0005 reports, RAH evidence and generations, and unrelated
dirty-worktree content remain preserved. No reset, clean, stash, commit, push,
Fleet, or subagent action was used.

## Decision

`C01-0006` may be recorded as package `PASS` and contract `CONFORMANT` with
`C02-0002` dependency-ready. Generated projection remains pending C02, runtime
migration remains pending C03, canonical package projection remains pending
pre-C04 B04, the global implementation gate remains failed, and
`completion_ready` remains false.
