# S01 review record

Status: `PASS_WITH_RECORDED_PROCEDURE_DEVIATION`

Review mode: `USER_AUTHORIZED_SELF_REVIEW`

The user prohibited subagents and authorized direct handling of review. The
primary author therefore performed the contract-review role. This record does
not claim independent assurance.

Reviewed implementation hashes:

- `packages/foundry-kernel/src/security/trust/trust-boundary.mjs`: `a25b5f4daa7cd8f1d98e66ba721728bb6fe333498117c830b1caa46b20bb8c75`
- `packages/foundry-kernel/src/security/trust/prompt-injection.test.mjs`: `ef429f1ced9c8c5b16c86939a7ea560989d95f35d640099003ac58d7bdb69747`
- `packages/foundry-kernel/src/security/trust/authority-escalation.test.mjs`: `71505517034cf25ab40b632bf9aade8e0c3c0a452e356cbb34fa2cc4dda18b14`
- `packages/foundry-kernel/src/security/trust/README.md`: `2ba17e1e6c6b32df0326ebe3320c050ad470afbe1a2b89aa3bc13510f701a9d8`

Resolved finding:

- `S01-RF001` — The initial plain-record validation did not explicitly reject
  JavaScript `Proxy` input. Prototype, key, or descriptor traps could therefore
  run during validation. The implementation now calls the trap-free
  `node:util.types.isProxy` predicate before reflective inspection. The
  authority-escalation suite proves that a hostile Proxy is denied and none of
  its traps executes.
- `S01-RF002` — An invalid object-valued trust label could reach string
  interpolation in the rejection message and invoke attacker-controlled
  coercion. The message no longer interpolates the rejected value, and a
  regression test proves `Symbol.toPrimitive` is not called.
- `S01-RF003` — Context assembly initially iterated the caller-provided array.
  A Proxy array or accessor element could therefore execute caller code during
  boundary validation. Context assembly now rejects Proxy arrays and reads
  only a plain dense array's own data descriptors; regression tests prove
  neither Proxy traps nor element getters execute.

Review confirmed:

1. The only accepted source kinds map to the evidence-data or model-output
   plane. Claimed host-instruction, plugin-control, and managed-policy kinds
   fail closed.
2. Sealed segments are immutable and carry a runtime-private `WeakMap` brand.
   Copies, JSON round trips, and hand-forged lookalikes cannot enter scanning,
   data-use, or context-assembly paths.
3. Sidecar `role`, approval, capability, policy, or phase fields are rejected.
   Claims inside the content string remain opaque data.
4. The allowlist contains data transforms only. `instruction`, policy mutation,
   execution, approval, and unknown future authority uses are denied.
5. `denyUntrustedAuthorityRequest` always emits `DENY` with
   `UNTRUSTED_ORIGIN` and empty capability, approval, policy, phase, and
   instruction identifiers. It does not inspect persuasive content to decide.
6. Prompt-injection scanning is advisory and cannot upgrade trust. Both a
   `NO_SIGNAL` result and a `trusted` extraction label remain non-authoritative.
7. Data-only context assembly accepts only runtime-branded segments, retains
   evidence and model-output plane identity, and exposes neither an instruction
   nor messages field.
8. Six hostile fixtures exercise role override, role delimiters, forged
   authority, tool execution, secret exfiltration, and policy rewrite. The
   authority suite additionally covers JSON-shaped self-approval, unknown
   authority actions, immutability, record and array Proxies, hostile
   coercion, and accessor-bearing record/array inputs.
9. All 17 security tests pass; implementation coverage is 92.33% lines,
   77.50% branches, and 100% functions. Workspace checks, all 789 Python tests,
   and the 11-artifact deterministic build remain green.
10. The exact S01 implementation scope contains four strict UTF-8 files and is
    included in the reproducible `foundry-kernel` npm package.

Open package-scope findings: none.

Scope limits retained for later packages:

- S01 establishes the deterministic trust-boundary primitive. Provider
  adapters, corpus ingest, context-capsule compilation, execution guards, and
  release red-team integration are later work-package scopes and do not yet
  constitute an end-to-end runtime enforcement claim.
- Injection-signal patterns are intentionally advisory indicators, not a claim
  to detect every prompt-injection phrasing. Safety rests on origin-based
  authority denial even when the scan returns `NO_SIGNAL`.
- The package remains a private scaffold and has no declared public export map.
  Package consumption and API stabilization belong to later integration work.
