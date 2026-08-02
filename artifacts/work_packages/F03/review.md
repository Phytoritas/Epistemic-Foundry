# F03-0002 canonical GateDecision admission review

Status: `PASS_WITH_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires this correction sequence to run in the primary
session without Fleet or subagents. This review is procedurally separate from
the edit pass, but it is not actor-independent certification.

## Reviewed boundary

- `packages/foundry-kernel/src/forge/gates/transition-admission-gate.mjs` — `sha256:62549b467fccd773c89ae751db8f01e9bd3ee7e314087076f01a582081d0a0c1`
- `packages/foundry-kernel/src/forge/gates/index.mjs` — `sha256:002d53b0ed821fc5b2cb9b089616e9830aa08a19a42f9d56b845dc96c186f9c6`
- `packages/foundry-kernel/src/forge/gates/gate-test-support.mjs` — `sha256:33dfc20a5c0ccb5cd0facef7167c0663ea01c43c6ba9f2711c94e8597f369b8b`
- `packages/foundry-kernel/src/forge/gates/transition-receipt.test.mjs` — `sha256:1f3cc002196c50934832a0b2ee1a79031e3321c9d0209f75a46bcf4ee8166a31`
- `packages/foundry-kernel/src/forge/gates/override-provenance.test.mjs` — `sha256:9cdd09ed0dd88cb41f2e7917724d8fc756c6307d6f39c70173cf8865e4a2bfa3`

- `tests/golden/forge/f04-test-support.mjs` — `sha256:bde8970e2520697211bc24f30ae6f75cf10811daa71616d88f6e76a72cf5b52b`
- `schemas/gate-decision.schema.json` — `sha256:ee341a7adab98d1814906c2f37b36cdbb03842b77ea8b52e94a164d061b7379c`
- `examples/sample_gate_decision.json` — `sha256:3680818e3376ab2592e6df0876ab6dcb67843bf73d3dbbb4c3ada366ba93b035`

## Findings

1. F03 now consumes the canonical 20-field `GateDecision` shape instead of the
   earlier 14-field runtime projection. Unknown, missing, or forged fields fail
   before admission.
2. `input_artifact_ids` must be explicit and receipt-resolved, and
   `policy_bundle_hash` must equal the active session policy. This closes the
   false-green path that F04 exposed.
3. A conclusion equal to a gate status must match `status`. The separately
   canonical, policy-evidenced `NOT_REQUIRED` conclusion remains valid only
   with `status=PASS`; `FAIL/NOT_REQUIRED` is rejected.
4. The decision hash covers every semantic field except itself, including the
   version, inputs, policy, conclusion, waiver data, evaluator, and timestamps.
5. F03 targeted execution is 23/23 and the combined repaired F03/F04 path is
   31/31. No test is skipped or xfailed.
6. The repository is not globally green. Node retains exactly two J02 failures
   and one S04-TM004 failure; Python retains exactly the J02 `tiktoken==0.13.0`
   declaration failure. Their fingerprints match the authorized later repair
   attempts, and F03 causal failure count is zero.
7. The canonical GateDecision example is structurally valid, but its stored
   `decision_hash` does not recompute after the earlier 14-field to 20-field
   canonical expansion. Both official Python hash implementations produce
   `sha256:a6a50d4285e844b71093e999b5addccf969d09d4c14221a92531d73172369851`
   rather than the stored
   `sha256:816c793545f4c3a194ce6b4fa842856defbcb34d991f27277ea9cd2a082e4be1`.
   F03 neither modifies nor certifies that C01-owned example: its declared
   acceptance gates are `transition_receipt_test` and
   `override_provenance_test`. The mismatch remains explicit debt that must be
   reconciled before C04 full conformance.

## Assurance boundary

This review establishes the in-process transition-admission contract and its
current F04 integration. It does not declare J02, S04, full repository
conformance, final packaging, release readiness, or product completion.
`actor_independence=false`, `implementation_gate=fail`, and
`completion_ready=false` remain explicit.
