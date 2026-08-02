# H01-0001 normalized Hook Gateway contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner explicitly requires primary-session execution without
subagents or Fleet. This is a procedurally separate review of the final H01
bytes and receipts. It is not actor-independent certification.

## Reviewed product boundary

- `packages/plugin-host/src/hooks/gateway/hook-gateway.mjs` — `sha256:8b9d1f72e4b4649d6588a7bfabd7c96c568f955f8eb4a11785c0930d50322e8c`
- `packages/plugin-host/src/hooks/gateway/hook-schema-fixture.test.mjs` — `sha256:c34112b0cdbce2b5e2bcd6336faf25a8ca6bb95d2a46caf70cabd8699b21608c`
- `packages/plugin-host/src/hooks/gateway/hook-timeout.test.mjs` — `sha256:1d1a4853beb54735ed271108e23f4b2df3a7e1c01c5b66f774ab156cfbba8f33`

## Findings

1. The gateway admits only non-proxy plain JSON data. Accessors, cycles,
   sparse/decorated arrays, symbols, `undefined`, bigint, non-finite numbers,
   negative zero, invalid Unicode, and custom prototypes fail closed before a
   decision callback runs.
2. Raw payload bytes are represented by a deterministic canonical JSON hash;
   normalized payload data is cloned separately. Object keys are sorted while
   semantically ordered arrays retain their order. The sealed fixture hashes
   independently recompute to the expected SHA-256 values.
3. The emitted envelope is validated against the unchanged canonical Draft
   2020-12 schema with format checking. String bounds use Unicode scalar count,
   matching JSON Schema length semantics for astral characters.
4. The callback sees an immutable canonical view. Decision output has a closed
   four-field shape and canonical vocabulary. Invalid output, callback failure,
   and async non-settlement yield explicit schema-valid `ERROR` envelopes and
   never become `ALLOW`.
5. A timeout abort signal is issued, the timeout envelope is immutable, and a
   late callback completion cannot alter it. Error messages are not copied into
   the envelope.
6. `OBSERVED`, `PARTIAL`, and `UNOBSERVED` remain coverage statements. H01 does
   not treat hook observation as the complete enforcement boundary, consistent
   with `EF4-I14`.
7. Targeted Node is 11/11 and full Python is 947/947. Full Node is 342/343
   with only exact unchanged S04-TM004; the Node JUnit footer/testcase-element
   count difference is recorded rather than hidden.
8. Product writes are confined to `packages/plugin-host/src/hooks/gateway/**`;
   canonical schemas, manifests, dependency reports, earlier generations, and
   unrelated dirty-worktree content retain their sealed hashes.

## Assurance boundary

This review verifies the normalized gateway primitive and its deterministic
envelope contract. Host-specific session/prompt and tool/delegation response
mapping belongs to H02/H03. It does not claim exhaustive hook enforcement,
production host integration, or actor-independent certification. JavaScript
timers bound asynchronously non-settling callbacks but cannot preempt a callback
that synchronously monopolizes the same event loop; an untrusted synchronous
decision engine would require a later process/worker isolation boundary.

## Decision

Both H01 exit criteria and both required checks pass. Product completion and
release readiness remain false.
