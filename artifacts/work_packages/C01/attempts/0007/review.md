# C01-0007 bounded GateDecision hash review

Package recommendation: `PASS`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: `actor_independence=false`. The product-owner contract
forbids Fleet and subagents, so this is a procedurally separate primary-session
review rather than external actor-independent certification.

## Correction and contract

- The only product field changed by C01-0007 is
  `examples/sample_gate_decision.json#/decision_hash`.
- The prior stale value `sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1` is replaced by
  `sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851`. Independent canonical recomputation with
  the self field excluded yields the same value, and a semantic tamper changes
  the digest.
- The fixture validates against the strict Draft 2020-12 GateDecision schema.
- All 126 canonical schemas meta-validate, map one-to-one to 126 examples, have
  126 unique `$id` values, and all 126 examples validate. No legacy promotion
  enum is active.
- OpenAPI remains 3.1.1 with 33 unique operations, canonical external schema
  references, explicit capability/security metadata, and mutation idempotency.

## Projection and regression

- B04-0007 receipt `AR-B04-0007-CANONICAL-PROJECTION` binds live root
  `sha256:1557b03db2ad7e7d23b014d4c9d5fd643803f6613696c966d9b0379573259e7f`, snapshot
  `sha256:d01bda0057584e235331b649238fc2507c60cab329fd6b8e8b6a115fac912559`, and registry
  `sha256:6b4fcade707639e537744be4075e71d3f7e068cd42eaaaddb20ef084851175d5`. Projection freshness is PASS.
- Targeted C01 contracts pass
  77/77.
- Full Python passes
  990/990.
- Full Node passes
  460/460 by
  the authoritative Node footer. The reporter's XML row count remains visible
  separately and is not used to undercount the suite.
- No failure, skip, xfail, alias, fallback, or schema weakening hides a defect.

## Scope and decision

- The schema, OpenAPI, runtime, generated models, and B04-owned derived snapshot
  were not modified by this attempt.
- Existing C01 and B04 attempts, RAH evidence/generations, and the dirty
  worktree remain preserved. No reset, clean, stash, commit, or push occurred.
- C01-0007 passes and makes C04-0002 dependency-ready. This does not establish
  C04 full conformance, B04-0008 final packaging, release readiness, or product
  completion. `implementation_gate=fail` and `completion_ready=false` remain.
