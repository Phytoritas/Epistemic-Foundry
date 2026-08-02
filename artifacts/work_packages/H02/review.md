# H02-0001 session and prompt lifecycle hook contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final H02 bytes and receipts. It
is not actor-independent certification.

## Reviewed product boundary

- `plugins/epistemic-foundry/hooks/session.json` — `sha256:d3030145bd0943125ccaea7d566a795e0b26501ce44813f8f329f826536f3a6e`
- `plugins/epistemic-foundry/hooks/prompt.json` — `sha256:a2f8e95358c377dd7344c4702f65fb06e666afeddb76beb26df0d0639929818b`

## Findings

1. The product directory contains exactly the two H02-owned JSON declarations.
   Both are byte-equivalent to the immutable reference blueprint and decode as
   BOM-less UTF-8 without replacement characters.
2. `SessionStart` is limited to `startup|resume|clear|compact`; `PostCompact` is
   limited to `manual|auto`. Each route has one plugin-root-relative command and
   a canonical timeout no greater than 15 seconds. Extra events, expanded
   timeouts, and direct transition commands are rejected by tests.
3. `UserPromptSubmit` has one bounded eight-second classification request. Its
   declaration has no state, revision, decision, approval, receipt, or phase
   authority field. Direct commit/state commands, authority fields, and tool,
   completion, or delegation events are rejected.
4. The declarations do not register themselves in the plugin manifest, do not
   add capabilities, and do not provide `dist/hook-runner.mjs`. This is an
   intentional responsibility boundary rather than silent fallback.
5. The targeted suite is 19/19: eight H02 cases plus eleven H01 gateway
   regressions. Full Python is 947/947. Full Node is 342/343 with only exact
   unchanged S04-TM004; the Node footer/testcase-element difference remains
   explicitly reconciled.
6. Product writes are confined to the two exact H02 paths. Earlier reports,
   RAH generations, and unrelated dirty-worktree content remain preserved.

## Assurance boundary

H02 verifies static lifecycle declaration assets only. It does not claim an
implemented hook runner, plugin-manifest registration, host capability probing,
degraded-mode behavior, Codex adapter integration, exhaustive enforcement, or
packaged runtime integration. H04 owns capability/degraded-mode gates; X01 and
G06 own later host-adapter and packaging integration. A future runner must
preserve the no-direct-state-authority boundary established here.

## Decision

Both H02 exit criteria and both required checks pass. Product completion,
release readiness, and a globally green repository remain false.
