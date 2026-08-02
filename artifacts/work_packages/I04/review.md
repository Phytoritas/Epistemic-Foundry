# I04-0001 intake UX and export gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final I04 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `web/src/features/intake/frame-roundtrip.test.mjs` — `sha256:8b0875299347decc68623272e82e918ffc770fc22fa8d655824adcb91fd83c89`
- `web/src/features/intake/index.mjs` — `sha256:0079cefe80b61de635aede577b96232ad09ae90cc20834c3aacbbe5c9af9c129`
- `web/src/features/intake/intake-frame.mjs` — `sha256:252161cc937710ccb04fb582ebc6f84370696b2f8822746fd04696ba87b4ff6d`
- `web/src/features/intake/intake-test-fixtures.mjs` — `sha256:5642e877dd2fbc5eee752676ef1e2e1d45ca4964c9182dc1b6c2ca74a26024f4`
- `web/src/features/intake/intake-ui.test.mjs` — `sha256:074d41d2b05ada2d9e1218663f937e8bf4f4f2c6dbc56e86405b28bc86d50a19`
- `web/src/features/intake/intake-view.mjs` — `sha256:28ca7c7142bc0e32c8d75d53bb3841e0ad387778a309f690f42765d338c37daa`

## Findings

1. Inbox state and blockers are the first visible intake section. I02
   falsifier, scope, construct, and council blockers remain visible and keep
   their canonical vocabulary and order; no confidence or verdict is invented.
2. I03 ontology candidates, selected resolution, review-queue items,
   measurement identity, compatibility, bridge, transformation, and promotion
   ceiling are validated before projection. Unknown, ambiguous, pending, or
   incompatible authority fails closed.
3. Review found and fixed an authority-bypass path in which a caller-provided
   assembled frame could forge derived export gates. The final implementation
   reconstructs the frame from authority inputs and rejects contradictory
   derived state.
4. Review found and fixed browser-runtime dependencies and timestamp edge
   cases. Production code has no `node:*`, `Buffer`, or `Date.parse`
   dependency; its synchronous SHA-256 matches the Node oracle across padding
   boundaries and Unicode, and RFC 3339 validation covers lowercase `t`/`z`
   and leap seconds without host parsing.
5. Review bound nullable ScopeVector values to the I02 unknown sidecar, rejects
   noncanonical council blockers, validates the unique complete I03 selection,
   and checks `aggregation_allowed` in both directions. `CONVERTIBLE` requires
   bridge plus transformation, while `NO_RESTRICTION` requires `SAME` and
   `DIRECTLY_COMPARABLE`.
6. Consent is fail closed: missing, expired, revoked, scope-mismatched, or
   unevaluable records cannot unlock export. Untrusted statements and blockers
   are HTML escaped.
7. Canonical JSON export is byte-stable and order-aware. Import rejects invalid
   UTF-8, noncanonical bytes, unknown fields, content tampering, and forged
   derived gates without mutating caller-owned input.
8. The final targeted suite is 32/32 (20 intake UI and 12 round-trip cases),
   full Python is 947/947, and final serial Node is 392/393 with only exact
   unchanged S04-TM004. Product writes remain inside I04 scope and canonical
   schema count remains 124.

## Assurance boundary

I04 implements the component-local intake projection and export/import gate. It
does not add a canonical schema, implement persistence or a remote service,
issue ontology approval, perform evidence search, or implement the full
coverage-before-confidence UI owned by O01/O04/U03. S04-TM004 remains outside
I04 ownership. This review does not claim actor-independent certification.

## Decision

Both I04 exit criteria and both required checks pass. Product completion,
release readiness, a globally green repository, and `completion_ready=true`
remain unclaimed.
