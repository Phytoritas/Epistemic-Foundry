# E04 E-phase strict and semantic replay gate review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_ADVERSARIAL_REVIEW`

Final verdict: `PASS`

blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_PASS`

The product owner requires serial primary-session execution for this work-package
sequence and explicitly authorizes the independent-review artifacts. This is a
procedurally separate adversarial review of the final E04 bytes. It is not
external actor-independent certification.

## Authority and reviewed boundary

- `MASTER_SPEC.md`, `MASTER_EXECUTION_PROMPT.md`, `AGENTS.md`, E04 in
  `manifests/development_manifest.yaml`, and invariant `EF4-I39`;
- canonical `schemas/replay-report.schema.json` —
  `sha256:6828658341f34f5ebf7dee947b3483f79440d68c48b91aa1cae689cbcbd7b798`;
- authorized development manifest —
  `sha256:a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345`;
- E02 dependency report —
  `sha256:97a308d90bd0f57334a5d9505e672d402b0409adcb17547780b2803f9c417772`;
- E03 dependency report —
  `sha256:e4737460f2375d46d4b348d79cdfa5c51ee84f1db2bcf34b8a3f5aea1d0091d2`;
- unchanged dependency implementations: E01 Noetic Ledger
  (`sha256:58ea9dc0d52d9c20720b33970ee3b8d8d05703ba7dd0fb4f51a483d9f505f1ed`),
  E02 EffectCoordinator
  (`sha256:a4d2b9b851f9055869db842d10702e6017a61c18fcc637521fdec398b5abc1f2`),
  and E03 CapabilityAuthority
  (`sha256:a8e3376568350229ca1a997aafbc1c4c138f2f01fbee945c916d390283a3720a`);
- final E04 files:
  - `tests/replay/effects/replay-test-support.mjs` —
    `sha256:da299cd4d9fd44a30d4851be3c4f7ac5104aadb94de57fe525cb2b1c8a98ca4b`;
  - `tests/replay/effects/strict-replay.test.mjs` —
    `sha256:b4d930073c16169139ae480a9fca549f6216a538adce5dec5c7da11f3f35adc1`;
  - `tests/replay/effects/semantic-replay.test.mjs` —
    `sha256:bfb99786cdc201c486fb710ffa973d2c0a241af4e53fb6be2cbb6a0587b036ed`.

E04 owns only `tests/replay/effects/**` and its declared evidence artifacts.
No canonical schema, manifest, E01 ledger, E02 coordinator, E03 authority, or
other production implementation was changed to make E04 pass.

## Adversarial findings

1. **Strict durable replay — PASS.** The E04 reducer rebuilds the exact ordered
   E02 ActionIntent/Attempt/EffectReceipt and E03 ApprovalRecord/CapabilityLease/
   lease-use/revocation event stream. Two rebuilds and a close/reopen rebuild
   produce the same state, state hash, event count, and tail hash. The replayed
   effect, approval, lease, and protected-operation projections match the live
   public dependency projections.
2. **Receipt and sequence binding — PASS.** An EffectReceipt must resolve the
   replayed tail Attempt and preserve run and idempotency identity. Attempts
   must be contiguous and unique. Each known payload kind must follow its
   prerequisite, and duplicate intent, attempt, receipt, approval, lease, or
   lease-use identities fail closed instead of overwriting replay state.
3. **Event-envelope integrity — PASS.** Payload identity is checked against the
   immutable event envelope's run, aggregate type, and aggregate ID. A valid
   payload cannot be rebound to a different aggregate. Missing or tampered D03
   payload bytes fail before reducer equivalence is considered.
4. **Retry replay neutrality — PASS.** Exact E02 and E03 retries return the
   existing logical result without invoking the protected callback, appending
   an event, allocating authority, or changing the replay state hash. A revoked
   lease retry remains the immutable revoked revision.
5. **Non-vacuous strict equivalence — PASS.** `EXACT` requires the same run
   identity, all eight exact pins, equal semantic state, and an exact strict
   identity containing only event count, state hash, and tail event hash. The
   state hash must bind the semantic projection; empty or detached identities
   cannot receive `EXACT`.
6. **Semantic replay honesty — PASS.** Different run/event identities are never
   mislabeled strict exact. Equivalent scientific outcomes are reported as
   `SEMANTICALLY_EQUIVALENT`; gate, verdict, or semantic-state differences are
   `DRIFT`; and unavailable mandatory pins are `NOT_COMPARABLE`. Semantic
   projection changes cannot disappear merely because gates and verdicts are
   unchanged.
7. **Pin and drift accounting — PASS.** Run spec, context, adapter/model, tools,
   receipts, policy, corpus, and prompts require exact `sha256:` pins. Floating
   or malformed pins fail closed. Model, prompt, corpus, policy, workflow, and
   multi-pin drift remain classified, while missing pins are side-qualified as
   `source:<pin>` or `replay:<pin>`.
8. **Bidirectional provenance — PASS.** `pinned_artifacts` records both source
   and replay pin provenance rather than silently privileging one side. Match
   and mismatch counts are computed only for comparable pins and are checked
   against the sealed report.
9. **Canonical report integrity — PASS.** Replay reports use plain canonical
   JSON data, deterministic UTF-8 hashing, and a report hash that excludes only
   itself. Proxy, accessor, decorated/sparse array, symbol, non-finite number,
   and unpaired-Unicode inputs are rejected without executing accessors. Report
   mutation and placeholder hashes are rejected, and emitted reports validate
   against the unchanged Draft 2020-12 `ReplayReport` schema.
10. **Regression and repeatability — PASS for E04.** The final targeted gate is
    18/18; five final repeats are 90/90; support coverage is 93.02% lines,
    77.78% branches, and 95.92% functions. Python is 913/913. Repository
    structure, package boundaries, pinned toolchains/locks, CI matrix/cache,
    ten CI policy mutation tests, syntax, strict UTF-8, marker audit, and
    `git diff --check` pass. Final repository-wide Node discovery is 237 passed
    with only the pre-existing out-of-scope `S04-TM004` stale manifest-hash
    binding.

## Resolved review findings

- `E04-RF001_RECEIPT_TAIL_ATTEMPT_BINDING`: receipts now resolve the exact
  replayed tail Attempt rather than merely an intent-level identity.
- `E04-RF002_SEMANTIC_PROJECTION_DRIFT`: semantic-state differences now force
  `DRIFT` even when gate and verdict maps happen to match.
- `E04-RF003_NON_VACUOUS_STRICT_IDENTITY`: strict comparison requires a
  complete event-count/state-hash/tail-hash identity bound to replay state.
- `E04-RF004_BIDIRECTIONAL_PIN_PROVENANCE`: reports retain both source and
  replay pin provenance and side-qualify unavailable pins.
- `E04-RF005_DUPLICATE_LOGICAL_IDENTITY`: duplicate logical payload identities
  are rejected instead of overwriting deterministic reducer state.
- `E04-RF006_EVENT_ENVELOPE_REBIND`: reducer payload identities must match the
  event run and aggregate envelope.
- `E04-RF007_CANONICAL_JSON_ACCESSOR_UNICODE`: canonical hashing rejects
  accessors without execution and rejects invalid Unicode scalar sequences.

## Preserved failed and residual observations

- The first schema-validation harness passed the Python validator program and
  the candidate instance through the same stdin stream. That harness defect
  produced 10 passed and 13 failed. The instance was moved to an argv value;
  the corrected harness and final code pass 18/18. The initial failure remains
  recorded in `commands.jsonl`.
- Repository-wide Node discovery ends at 237 passed and 1 failed. The sole
  failure is `S04-TM004`, whose historical threat-model fixture expects the old
  `development_manifest.yaml` hash
  `456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7`
  while the authorized manifest is
  `a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345`.
  E04 has no S04 write authority and does not alter or hide this failure.
- `scripts/build/double_build.py` still fails while building its staged source
  because that staging path omits the existing `scripts/` build-hook package.
  E04 has no B02/B04 packaging authority; the failure is preserved.
- Two read-only explorations used paths that do not exist
  (`.rah/ralph/current-generation.json` and
  `.rah/ralph/evidence-ledger.jsonl`). The canonical paths are
  `.rah/ralph/current.json` and `.rah/ralph/evidence_ledger.json`; no state was
  changed. A separate `foreach`-to-pipeline PowerShell read was blocked by the
  command-safety hook before execution and was replaced with a safe shape.

## Assurance limitations

- E04 qualifies deterministic replay of the implemented local E01/E02/E03
  event surface and comparison contract. It does not prove arbitrary future
  event reducers, distributed consensus, cross-region exactly-once execution,
  or the scientific truth of an external effect.
- `SEMANTICALLY_EQUIVALENT` means the declared semantic projection, gates, and
  verdicts match under the recorded pins. It is not a claim that distinct model
  weights, corpora, prompts, policies, or workflows are scientifically
  interchangeable.
- The E04 support module is a gate implementation under the authorized test
  scope. Runtime packages that later expose replay as a product feature still
  own their transport, authorization, persistence, and operational boundaries.
- The separate review is user-authorized and procedurally independent within
  the primary session; it is not external actor-independent certification.

## Decision

E04 satisfies its exact package contract. Strict reducer equivalence passes;
semantic drift and unavailable provenance remain visible; replay reports are
schema-valid and hash-bound; and no narration, retry, floating pin, or
payload/event rebinding can manufacture equivalence. The overall Foundry
objective remains active and `completion_ready=false`.
