# F04-0002 F-phase end-to-end revalidation review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking F04 findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Actor independence: `false`

The product owner requires this repair sequence to run in the primary session
without Fleet or subagents. This is a procedurally separate review of the final
F04 bytes; it is not actor-independent certification.

## Reviewed boundary

- `tests/golden/forge/f04_forge_golden_flows.json` — `sha256:0641cbbdf734d107dfb3055a4160656f7974afec3d282e07bcbb31439115e628`
- `tests/golden/forge/f04-test-support.mjs` — `sha256:bde8970e2520697211bc24f30ae6f75cf10811daa71616d88f6e76a72cf5b52b`
- `tests/golden/forge/f04_forge_golden_flows.test.mjs` — `sha256:5f645adb0acdafc45e5a1e30937cb089e83147fe11f2a2c8af2309d03d2778b6`
- `tests/golden/forge/f04_phase_artifact_reconciliation.test.mjs` — `sha256:8a7774b4068b12cf4ed56449d9a11fc2825b131b0537195ee458ff756451fd14`

- F02 sealed report — `sha256:4d6dae9525ac559cba26e59ff1ab93f7e94918e21076030c50c55f7022b3b152`
- F03-0002 sealed report — `sha256:bb70fa7718bac42169c4b529e52861733dac2d6c129482b9155f97154d9c44b9`
- complete normalized Node receipt — `sha256:d64dc7e1995c599352502fef06f1306bd9c7191e1439bf6dedf94cd2c92ce0b7`
- normalized Python receipt — `sha256:c99e3c2c0f5be7dea1dabe5e18c4168995cecb0b3488a8e223d95edc0fa54ab6`

## Findings

1. F04 now consumes the corrected 20-field GateDecision runtime boundary sealed
   by F03-0002. The original 0/8 failure and the earlier 21/21 false-green F03
   receipt remain immutable reproduction evidence.
2. The exact E1, E3, and ambiguous E5 projections execute F-O-E, F-O-R-G-E,
   and I-F-O-R-G-E. Every path returns to IDLE with orchestration status
   COMPLETED and a truthful `UNDERDETERMINED` scientific outcome.
3. All 17 transition requests are admitted, reduced, replayed, and persisted.
   All 14 PhaseArtifactSets reconcile exactly once; removing a persisted
   transition fails closed.
4. The final F04 targeted suite is 8/8 with no skip or xfail.
5. The first Node regression receipt contained only 50 of 52 test files and
   omitted 32 intake UI tests. It is explicitly classified as a diagnostic and
   cannot satisfy the full-suite gate. The replacement receipt covers all 52
   files and reports 457 passes with exactly two J02 and one S04 failures.
6. Full Python reports 986 passes with only the exact J02 `tiktoken==0.13.0`
   declaration failure. No residual failure is caused by F04.
7. JUnit normalization removes only machine-local paths, timestamps, hostnames,
   and durations. The complete raw Node receipt is preserved at
   `sha256:39f0a53307c63fc8b529d0c02c6799415527cfa04134a1e3a1683b23961eebe1` and derives byte-for-byte into the
   normalized receipt under the declared transform.
8. The C01-owned GateDecision example remains structurally valid but its stored
   hash `sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1` does not equal the canonical
   recomputation `sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851`. F04 does not hide or repair
   this debt; it remains mandatory before C04 full conformance.

## Assurance boundary

This evidence establishes deterministic in-process F-phase composition. It
does not certify distributed delivery, production external effects, J02, S04,
C04 conformance, final packaging, release readiness, or product completion.
`implementation_gate=fail` and `completion_ready=false` remain explicit.
