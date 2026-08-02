# H01-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/plugin-host/src/hooks/gateway. Reviewer: this seal-prep
  session, a distinct actor that did not author the gateway. The author
  never approves its own work, so actor_independence HOLDS for this
  review; external actor-independent certification does NOT, and no such
  claim is made. H01 is risk_class=critical; the gateway was attacked on
  its normalization, hash-sealing, fail-closed decision, and timeout
  contracts rather than skimmed.
- Host payloads hash and normalize. dispatchHookEvent asserts the raw host
  payload is canonical JSON before anything else: cycles, sparse or
  accessor-backed arrays, Proxies, BigInt, NaN, -0, Infinity, lone
  surrogates, prototype-polluted objects, and symbol-keyed objects each
  fail closed with NON_CANONICAL_JSON, and the fixture test proves the
  decision callback is never invoked and neither an accessor getter nor a
  Proxy ownKeys trap runs. The payload is hashed under sha256:<hex> and
  cloned into a deep-frozen normalized_payload whose keys are sorted, so
  object insertion order changes neither raw_payload_hash nor
  envelope_hash. The callback receives only an immutable canonical view;
  raw_payload and normalized_payload are distinct contract fields.
- Hook decisions schema-valid. Every emitted envelope carries exactly the
  schemas/hook-event-envelope.schema.json required keys with
  additionalProperties false, canonical host/event_type/decision/coverage
  vocabulary, and sha256 hash patterns. validateHookEventEnvelope
  recomputes the canonical preimage hash and rejects tampering with
  HOOK_ENVELOPE_HASH_MISMATCH; a malformed hash field is rejected with
  HOOK_ENVELOPE_INVALID. Invalid callback output (an extra hidden_authority
  key) does not leak through: it becomes a sealed ERROR envelope with
  reasons [HOOK_DECISION_INVALID], never coerced to ALLOW.
- Decisions are timeout-bounded and fail closed. timeout_ms is validated as
  a positive platform-bounded safe integer before the callback runs; 0,
  -1, 1.5, NaN, Infinity, and 2147483648 all reject with INVALID_INPUT and
  the callback is never invoked. A non-settling callback resolves via
  Promise.race and AbortController.abort to a bounded ERROR envelope
  (HOOK_DECISION_TIMEOUT) with the signal aborted; the elapsed time is
  bounded, a late resolution cannot mutate the deep-frozen result, and a
  rejecting callback becomes HOOK_DECISION_CALLBACK_ERROR without leaking
  its message. A fast canonical decision wins without timeout rewriting and
  without aborting the signal. No path converts a timeout or error into
  ALLOW.
- Dependency and checks: the gateway builds on the sealed E04-0001,
  G04-0001, and S02-0001 attempts and adds no new production dependency; it
  reads schemas/hook-event-envelope.schema.json read-only (outside the
  write scope, hash-pinned). Ruff lint and format, the two required checks
  (hook_schema_fixture_test 6/6, hook_timeout_test 5/5), targeted 11/11,
  full Python 1261/1261, full Node 1291/1291 across 115 files, and git diff
  --check all pass with zero failures.
- Residual limitations: H02/H03 own the host-specific hook response mapping
  and lifecycle/tool hook integration; hook coverage remains observed
  guardrail coverage, never the complete enforcement boundary; and
  same-event-loop timers cannot preempt a synchronously non-returning
  callback, which a later isolation boundary must bound. Verdict: PASS on
  the exact H01 package contract.
