# F04-0001 F-phase end-to-end integration review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final F04 bytes. It is not actor-independent certification.

## Reviewed boundary

- `tests/golden/forge/f04_forge_golden_flows.json` — `sha256:0641cbbdf734d107dfb3055a4160656f7974afec3d282e07bcbb31439115e628`
- `tests/golden/forge/f04-test-support.mjs` — `sha256:c2bf7746995025713d0814e061bd2465e99bbae1af131deadcce64407508bdc8`
- `tests/golden/forge/f04_forge_golden_flows.test.mjs` — `sha256:5f645adb0acdafc45e5a1e30937cb089e83147fe11f2a2c8af2309d03d2778b6`
- `tests/golden/forge/f04_phase_artifact_reconciliation.test.mjs` — `sha256:8a7774b4068b12cf4ed56449d9a11fc2825b131b0537195ee458ff756451fd14`

The review also checked the sealed F02 and F03 reports, the canonical
EpistemicWorkClassification, PhaseArtifactSet, GateDecision, Adjudication and
ResultEnvelope schemas, all normalized regression receipts, and the live
156-package dependency graph.

## Findings

1. The exact E1, E3 and E5 projections are exercised end to end. E1 follows
   F-O-E, E3 follows F-O-R-G-E, and ambiguous E5 follows I-F-O-R-G-E; every
   path returns to IDLE with a COMPLETED orchestration status.
2. Every one of the 17 transition requests first passes the F03 admission
   gate, then the identical request passes the F02 reducer. Admission and
   reduction bind the same canonical request hash.
3. Direct reduction, persisted transition bytes and strict replay are exactly
   equal. Reconciliation accounts for 17 generated, admitted, reduced,
   replayed and persisted transitions with no missing or duplicate identity.
4. All 14 required PhaseArtifactSets are complete, current, receipt-bound and
   admitted exactly once. Removing one persisted transition makes the
   reconciliation test fail closed.
5. E admission is backed by a resolving non-waivable PASS GateDecision. The E
   artifact is a canonical Adjudication whose UNDERDETERMINED verdict and
   BLOCK promotion recommendation are preserved as a successful truthful
   scientific outcome rather than converted into a system error.
6. Draft 2020-12 validation is executed by the local locked Python environment
   before admission. The PASS validation claims stored in ephemeral receipts
   cannot reach admission or persistence if actual schema validation fails.
7. Mutating policy_bundle_hash in the classification identity context is
   rejected by compilation, reduction and replay with
   CLASSIFICATION_INTEGRITY_FAILED. F04 does not infer or weaken the F01/F02
   semantic preimage boundary.
8. F04 contributes 8/8 targeted Node passes; the combined gate is 76/76. Full
   Python is 947/947. Full Node is 313/314 with only the exact unchanged
   S04-TM004 debt and no F04-caused failure, skip or xfail.

## Assurance boundary

The fixtures exercise deterministic in-process composition using local
content-addressed stores and simulated service actors. They do not prove
distributed exactly-once delivery, transport authentication, external side
effects, production concurrency, or actor-independent certification. Those
claims remain owned by later work packages.

## Decision

F04 meets both exit criteria: minimum and full paths pass, and
UNDERDETERMINED is accepted as a receipt-bound truthful outcome. Product
completion remains false.
