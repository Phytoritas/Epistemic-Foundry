# N02-0001 Codex/Claude role compilation and spawn-adapter review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Actor independence: `false`

The product owner requires serial primary-session execution without Fleet or
subagents. This is a procedurally separate adversarial review over fixed N02
source hashes and immutable verification receipts, not actor-independent
certification.

## Findings

1. The verified canonical `RoleSpec` is the only role authority. Codex CLI,
   Codex Desktop, and Claude Code host selections change only the bounded host
   descriptor; mission, ACLs, scopes, budgets, expected count, acceptance
   checks, and business output remain hash-bound to the same `RoleSpec`.
2. Every executable descriptor records exact provider/model/version and exact
   runtime/version plus the model-routing receipt. Floating aliases, ranges,
   unauthorized tiers, and unapproved fallback tiers fail closed.
3. Host capability reports are integrity-checked at the adapter boundary.
   RFC 3339 time, closed hook-event vocabulary and order, limitation/path/
   blocker order, report hash, host identity, and capability state are all
   validated before a descriptor can be emitted.
4. `subagent_dispatch` unavailability permits only an explicitly observed
   `serial_execution` fallback. If neither capability is supported the adapter
   blocks; `BLOCKED`, `SAFE_MODE`, and write-capable work on `READ_ONLY` hosts
   also fail closed.
5. Host/model/caller data cannot inject a prompt or broaden authority. Proxy,
   accessor, custom-prototype, tampered RoleSpec, tampered report, prompt
   replacement, descriptor mutation, and attacker-rehash paths are rejected.
6. Spawn descriptors and canonical role prompts are deterministic,
   content-addressed, deeply immutable, and semantically revalidated. A valid
   outer hash cannot conceal an internally altered target, prompt, model, host,
   output schema, or count.
7. `ResultEnvelope` remains execution telemetry only; the business output
   schema and expected count come from the RoleSpec, and prose completion is
   explicitly non-authoritative.
8. Required N02 checks pass 29/29: 17
   `adapter_compilation_test` and 12 `prompt_injection_boundary_test` cases.
   N01 RoleSpec/ACL regression passes 21/21 and upstream host-capability
   regression passes 18/18. Full Node passes
   769/769
   across 75 files; full Python passes
   1064/1064.
   Codegen remains 126/126; structure, boundaries, syntax, and diff checks pass.
9. All seven product files are BOM-less UTF-8 and remain inside exact
   `packages/role-router/src/adapters/**` scope. Existing dirty worktree changes
   and every historical report/evidence/generation are preserved.

## Assurance boundary

This gate establishes deterministic compilation of verified RoleSpecs into
bounded Codex/Claude spawn descriptors and adapter-side integrity validation.
It does not execute provider hosts, implement scheduler leases/retries (N03),
enforce N-phase fan-in/reviewer independence (N04), prove remote-provider
availability, claim actor-independent certification, complete the product, or
set `completion_ready=true`. Global `implementation_gate=fail` remains required.
