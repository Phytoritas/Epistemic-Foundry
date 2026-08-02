# F01-0002 primary-session separate adversarial review

Overall package status: `SPEC_GAP (F01-SG002)`

Classifier implementation assessment: `PASS`

Review context: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

The product-owner decision requires primary-session-only execution and forbids
Fleet and subagents. This review was conducted as a procedurally separate
adversarial pass after implementation and test execution. It is not external
actor-independent certification, and it does not claim that assurance.

## Reviewed boundaries

- HumanDecision `HD-EF4-F01-SG001-20260729-001`;
- the deterministic classifier and ClassificationCommitter under
  `packages/foundry-kernel/src/forge/classifier/**`;
- the exact F01 schema, example, workflow, prompt, documentation, manifest,
  acceptance matrix, gold/adversarial/hash/override fixtures and tests;
- all targeted Node and Python results;
- the repository-wide Python and Node regression results;
- the B04 source-authority versus packaged-runtime-snapshot contract; and
- F01-0001, B04-0002 and all retained RAH history.

## Implementation findings

1. **Final authority is deterministic and provider-neutral.** LLM output is
   accepted only as bounded `SignalProposal` input. The Kernel owns signal
   normalization, maximum-floor classification, exact projection, Interview
   routing, stable reasons, risk factors, hash and ID calculation.
2. **The closed vocabulary and fail-closed rules hold.** Trusted unknown
   signals fail input validation. Unsupported or low-confidence LLM proposals
   cannot remove hard signals or lower protection. Empty recognized input
   injects sticky `AMBIGUOUS` and produces E5 with Interview.
3. **Underprocessing protection is exhaustive.** All 1,023 non-empty signal
   subsets and 58,025 subset-to-superset relationships were checked. No class,
   human gate, Interview, phase or role-count regression was observed.
4. **Projection and schema constraints are exact.** E0-E5 phase arrays, role
   counts and human gates are enforced in both deterministic implementation and
   Draft 2020-12 schema. The canonical schema/example cardinality remains
   124/124 and `additionalProperties=false` remains intact.
5. **Identity and replay are receipt-bound.** The JCS-equivalent SHA-256
   preimage excludes self/volatile fields. Exact retry returns the original ID,
   hash and timestamp; conflicting idempotency reuse fails; strict replay
   diverges on any semantic difference; reclassification and upward-only human
   override create immutable superseding artifacts.
6. **Workflow authority is correctly bound.** The classifier node is a
   deterministic policy executor, emits the canonical business artifact,
   retains `ResultEnvelope` only as telemetry and uses only `artifact_read` and
   `artifact_write` capabilities.
7. **The fixed oracles all pass.** Node targeted tests are 30/30; Python F01
   contract tests are 24/24; gold is 14/14; adversarial is 16/16; hash vectors
   are 4/4; override fixtures are 6/6; skips, xfails and live network calls are
   zero.

No blocking defect was found in the F01 classifier implementation itself.

## Blocking integration finding: F01-SG002

The full Python suite is `936 passed, 1 failed`. The failure is
`tests/packaging/test_canonical_registry.py::test_source_projection_is_current_and_complete`.
It reports exactly two mismatches:

- `canonical-registry.json`;
- `schemas/epistemic-work-classification.schema.json`.

The root schema now has SHA-256
`dbe8437eae1ec8c956b1290556efa7f2bb89c862134870d80f15e6e49679efa9`,
while the packaged snapshot retains
`5c0c574605f4d1d2e8ea42385d6bc40ac273d1cbf1319169f6e26db6656d6049`.
This mismatch is a direct, expected consequence of the product-owner-authorized
F01 canonical schema strengthening, but it is still a real repository failure.

F01 cannot repair it: `src/epistemic_foundry/_canonical/**` is B04-owned, and
the F01 decision deliberately did not authorize that path. B04-0002 correctly
sealed a snapshot of the canonical sources that existed at its build time. The
authority chain does not define who reprojects that snapshot after a later
canonical contract change, when that reprojection runs, or whether F01 must
wait for it before PASS. Updating the snapshot inside F01 would be a write-scope
violation; ignoring the failure would violate F01's zero-new-regression gate.

The repository-wide Node result is `267 passed, 1 failed`. Its sole failure,
`S04-TM004`, is a stale development-manifest hash binding documented before
F01 in D01 and every later Node regression. It is preserved as separate
pre-existing integration debt and is not part of F01-SG002.

## Verdict

`F01-0002` cannot be marked PASS. The correct typed result is `SPEC_GAP`, not
`FAIL`, because the deterministic classifier implementation and its acceptance
oracles pass, while the only new repository failure crosses an unassigned
B04/F01 ownership and sequencing boundary. It is not `BLOCKED` by a missing
tool, credential or external service.

The minimum resolving product-owner decision must define:

1. the owner and execution point for packaged snapshot reprojection after later
   canonical schema/OpenAPI changes;
2. whether B04 is rerun as a new attempt or a separate integration package owns
   the reprojection; and
3. whether F01 PASS waits for that reprojection or may transfer the exact drift
   as explicit bounded downstream debt.

F01-0001 remains immutable `SPEC_GAP` history. F02 and F03 remain waiting on
F01. No packaged canonical file was modified during this review.
