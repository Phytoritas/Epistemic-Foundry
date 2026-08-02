# F03-0001 artifact-receipt transition gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final F03 bytes. It is not actor-independent certification.

## Reviewed boundary

- `packages/foundry-kernel/src/forge/gates/transition-admission-gate.mjs` — `sha256:bef51dc910b2d600d2c4a0a40a91d04e67dbd7d43e8b39c330f4ffa86a4218bd`
- `packages/foundry-kernel/src/forge/gates/index.mjs` — `sha256:002d53b0ed821fc5b2cb9b089616e9830aa08a19a42f9d56b845dc96c186f9c6`
- `packages/foundry-kernel/src/forge/gates/gate-test-support.mjs` — `sha256:99372425f21abe0fd5076eff5393f2f506fc31da8e4acf359ea1fe18e8e92266`
- `packages/foundry-kernel/src/forge/gates/transition-receipt.test.mjs` — `sha256:e396e0bacaf3ef6b5482b872f126137b90df2d192297e9e3e4f12090887ca617`
- `packages/foundry-kernel/src/forge/gates/override-provenance.test.mjs` — `sha256:2472f8d773c20b6161ba60ad2b3210d323f4d37cb572d59c8faa73aee7ea5653`

The review also checked the sealed F01 report, the F02 transition boundary,
`docs/forge_protocol.md`, ArtifactReceipt, PhaseArtifactSet, GateDecision, and
HumanDecision contracts, and all normalized regression receipts.

## Findings

1. A narrative reason cannot authorize a transition. Every admitted transition
   resolves the declared receipts, manifests, and bytes, independently
   recomputes byte length and SHA-256, and binds validation evidence to both
   content and manifest hashes.
2. IDLE admission requires exactly one canonical F01 classification receipt.
   The classification artifact's closed fields, identity, timestamp, version,
   E0-E5 projection, schema-validation receipt, and session work class are
   checked before an admission can exist.
3. Non-IDLE admission requires exactly one complete current PhaseArtifactSet.
   Every required entry must be VALID and bound to the exact receipt, content
   hash, schema reference, session, phase, and retained state artifact.
4. GateDecisions bind run, input, decision hash, and resolving evidence. FAIL
   and BLOCK are never absorbed, E requires gates, and a non-waivable WAIVE is
   rejected even when a human decision is supplied.
5. A waivable override requires a declared, resolving, canonical HumanDecision
   whose human receipt creator, authority, type, run, scope, and hash agree.
   Authority prose or an unused decision artifact is not an override.
6. Admission output is immutable and content-addressed as `FTA-<digest>`.
   F03 does not mutate F02 state or silently perform the F02 transition.
7. F03 tests are 21/21 (15 receipt and 6 override); the combined F01/F02/F03
   gate is 68/68. Full Python is 947/947. Full Node is 305/306 with only the
   exact unchanged S04-TM004 debt and no F03-caused failure or skip.

## Assurance boundary

F03 verifies the classification business artifact's bytes, schema identity,
classification identity, exact projection, and ForgeSessionState work-class
agreement. Recomputing the complete `classification_hash` semantic preimage
also requires `request_input_hash`, `policy_bundle_hash`, `accepted_signals`,
and supersedes/human-decision context, which are deliberately absent from the
business artifact. F03 does not guess them. F02's
`classification_identity_context` validation and the F04 composition gate own
that cross-artifact semantic binding.

This gate proves the in-process deterministic admission surface. It does not
claim future distributed exactly-once delivery, transport authentication, or
actor-independent certification.

## Decision

F03 meets both exit criteria: prose-only transitions are impossible and human
override provenance remains explicit. Product completion remains false.
