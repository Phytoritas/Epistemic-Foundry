# B04-0006 pre-C04 projection review

Overall projection status: `PASS`

Overall package status: `SPEC_GAP` (`B04-SG002`)

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_INTEGRATION_REVIEW`

Assurance limitation: `actor_independence=false`. This is a procedurally
separate primary-session review, not external actor-independent certification.
Fleet and subagents were not used.

## Projection boundary

- Root authority remains `schemas/**` and `openapi/**`; the package snapshot is
  derived only from those roots.
- 126 schemas plus OpenAPI 3.1.1/33 operations produce 127 canonical resources.
- Source `sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f`, snapshot
  `sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559`, and registry `sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5`
  are recomputed from live bytes.
- Missing, extra, hash-mismatched, and duplicate-ID counts are all zero after
  projection. The stored stale prestate retains two missing and five mismatched
  resources and the prior registry hash.
- Targeted projection tests are 41/41. Clean wheel/sdist, sdist-to-wheel,
  installed-wheel-only loading, arbitrary empty cwd, tamper/missing rejection,
  deterministic rebuild, and source fallback success count zero pass.
- The projection receipt binds the live registry and proves projection
  integrity only. It does not prove runtime or repository conformance.

## Adversarial regression and ownership review

- Full Python is not green: 916 passed, 52 failed, 15 errors. The 67 problems
  resolve exactly to 51 `GATE_DECISION_RUNTIME_SCHEMA_DRIFT`, 15
  `HOLDOUT_MANIFEST_RUNTIME_SCHEMA_DRIFT`, and one existing J02 dependency debt.
- Full Node is not green: TAP records 458 tests, 447 pass, 11 fail, 0 skipped;
  JUnit contains ten failing leaf testcases (F04=7, J02=2, S04=1). The TAP and
  leaf totals are intentionally recorded separately.
- The active manifest assigns no writer to
  `src/epistemic_foundry/foundry_kernel/gates.py` or
  `src/epistemic_foundry/verifier_firewall/firewall.py`.
- F04, J02, and S04 own their derived paths, but the current decision does not
  authorize a pre-C04 correction sequence for those packages. B04 cannot invent
  that ordering or broaden another package's scope.
- No runtime, fixture, inventory, binding, schema, or test gate was weakened.

## Decision

The deterministic canonical projection is verified `PASS`. B04-0006 as a
package is `SPEC_GAP` because `B04-SG002` requires a product-owner decision
assigning bounded runtime migration ownership and authorizing the pre-C04
F04/J02/S04 correction sequence. `C04-0002` and final B04 packaging must not
start. The projection receipt is not package-PASS evidence. The dirty worktree
and all prior attempts/RAH history remain preserved; `completion_ready=false`.
