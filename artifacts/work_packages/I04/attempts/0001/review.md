# I04-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  web/src/features/intake. Reviewer: this seal-prep session, a distinct
  actor that did not author the intake projection or the export gate. The
  author never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. I04 is risk_class=medium; the projection and gate were
  attacked on their visibility, round-trip, and fail-closed contracts
  rather than skimmed.
- Inbox and blockers are visible, not hidden. buildIntakeView reconstructs
  the frame from authority inputs and renders Blockers as the first
  visible section inside an aria-live=assertive region. The I02 inbox and
  the council, scope-unknown, ontology-review, and measurement blockers
  keep their canonical vocabulary and order; a non-canonical council
  blocker, a missing unknown-scope sidecar, or a council state conflict
  fails closed (INTAKE_COUNCIL_STATE_CONFLICT, INTAKE_UNKNOWN_SCOPE_
  CONFLICT). Pending ontology approval stays a visible blocker and an
  AUTHORITY_REQUIRED review item; a within-method measurement boundary
  stays a visible limitation and is not relabelled a blocker.
- No fabricated confidence or verdict. The serialized projection contains
  neither a confidence nor a verdict field, and the export control exposes
  only a truthful READY/BLOCKED status with the exact blocker reason_codes.
  Untrusted statement and blocker text is HTML-escaped, and the export
  button is disabled with aria-disabled when export is not permitted.
- Frame export round-trips byte-for-byte. serializeIntakeFrame emits
  canonical UTF-8 JSON whose SHA-256 equals the Node oracle across padding
  boundaries and Unicode; parseIntakeFrame re-imports it and a second
  export is byte-identical. The export is key-order independent while
  meaningful array order is preserved, and no lossy transform is applied
  (lowercase/leap-second RFC 3339 timestamps round-trip unchanged).
- Honest degradation fails closed. Import rejects invalid UTF-8
  (INTAKE_FRAME_INVALID_UTF8), non-canonical bytes
  (INTAKE_FRAME_NOT_CANONICAL), one-byte content tampering
  (INTAKE_FRAME_HASH_MISMATCH), unknown envelope fields
  (INTAKE_FIELD_SET_INVALID), and a fabricated derived gate
  (INTAKE_FRAME_DERIVATION_MISMATCH). An Inbox frame refuses export with
  INTAKE_EXPORT_BLOCKED, and a forged assembled frame whose blockers were
  cleared cannot be projected (INTAKE_FRAME_DERIVATION_MISMATCH). Assembly,
  projection, export, and import never mutate caller-owned inputs.
- Dependency and checks: the intake surface builds on the sealed I02
  (I02-0001 PASS) inbox/council contract and the sealed I03 (I03-0001 PASS)
  ontology and measurement resolution, and adds no new production
  dependency; product code reads no node:* module, Buffer, Date.parse, or
  environment. The two required checks (intake_ui_test 20/20,
  frame_roundtrip_test 12/12), targeted 32/32, full Python 1261/1261, full
  Node 1253/1253 across 111 files, and git diff --check all pass with zero
  failures.
- Residual limitations: I04 is a component-local intake projection and
  export/import gate. It adds no canonical schema, implements no
  persistence, remote service, ontology approval issuance, or evidence
  search, and the full coverage-before-confidence UI remains owned by
  O01/O04/U03. Verdict: PASS on the exact I04 package contract.
