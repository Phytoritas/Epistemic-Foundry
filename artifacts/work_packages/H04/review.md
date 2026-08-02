# H04-0001 capability probe and degraded-mode integration review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_INTEGRATION_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final H04 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `packages/plugin-host/src/capability-probe/capability-probe.mjs` — `sha256:1b419ca7902d4dfcceaaec92f9c533c3d4990ec7c42afc4b7ce45b2827e0d2b4`
- `tests/compatibility/hooks/hook-feature-probe.test.mjs` — `sha256:a55247f3eccf223d49c187843be681f056cd40c25681111a2b9f15d50751d4b3`
- `tests/compatibility/hooks/hook-degraded-mode.test.mjs` — `sha256:7a5c6bbf507b7524f786dfae9aa961817548a5f5c9c45f725b948186335843db`

## Findings

1. `hashHookDefinitionBytes` hashes exact installed bytes. Active hook IDs and
   observed hashes must both be unique, and `verifyHookTrust` compares the full
   active hash set with `PluginInstallState.trusted_hook_hashes`. Added, changed,
   removed, and disabled-but-changed hooks retain explicit re-trust debt.
2. Hook trust objects have verifier provenance and cannot be forged by copying
   fields. Missing observations become `UNKNOWN`; profile names never confer a
   capability; proxies, accessors, sparse arrays, undeclared capabilities,
   events, and tool paths fail closed.
3. Empty or incomplete event/tool coverage is explicit and cannot prove
   `FULL`. Coverage limitations do not overwrite stronger `ERROR`, `DISABLED`,
   or `UNSUPPORTED` evidence. Unobserved hosted paths remain visible.
4. Degraded modes use the strongest declared projection across `DEGRADED`,
   `READ_ONLY`, `SAFE_MODE`, and `BLOCKED`; a missing fallback contract blocks.
   `HostCapabilityReport` and `PluginHealthReport` are canonical, hash-bound,
   schema-shaped, and deeply frozen.
5. The targeted suite is 45/45: 18 H04 cases, eight H03 regressions, eight H02
   regressions, and eleven H01 gateway regressions. Full Python is 947/947.
   Full Node is 360/361 with only exact unchanged S04-TM004; its footer/XML
   testcase delta is explicitly reconciled.
6. Product writes are confined to the H04 implementation and test scopes.
   Earlier reports, all RAH generations, and unrelated dirty-worktree content
   remain preserved.

## Assurance boundary

H04 consumes bounded observations and emits truthful capability and health
projections. It does not claim a live cross-host discovery adapter, exhaustive
enforcement from observed hooks, runtime hook-runner registration, hosted-tool
interception, evolution/holdout observability, release readiness, or production
readiness. H05/H06 and later host integration packages retain those boundaries.

## Decision

Both H04 exit criteria and both required checks pass. Product completion,
release readiness, and a globally green repository remain false.
