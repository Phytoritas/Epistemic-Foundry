# H03-0001 tool and delegation hook contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires primary-session execution without subagents or Fleet.
This is a procedurally separate review of the final H03 product bytes and
receipts. It is not actor-independent certification.

## Reviewed product boundary

- `plugins/epistemic-foundry/hooks/tools.json` — `sha256:7bd22606fa69ebc447d538c682d2175547e56247fe66755b4c2ac33f0ab31007`
- `plugins/epistemic-foundry/hooks/delegation.json` — `sha256:05fb9047ce62d00d296e47843c2130bbeb550ea43aa9d009dbcc8c2ce82cd4b6`

## Findings

1. The complete hook directory contains exactly `delegation.json`,
   `prompt.json`, `session.json`, and `tools.json`; only the tool and delegation
   declarations are H03 product writes. Both are byte-equivalent to their
   immutable reference blueprints and decode as BOM-less UTF-8 without
   replacement characters.
2. `PermissionRequest`, `PreToolUse`, and `PostToolUse` are present. The pre/post
   matcher is identical, policy and receipt routes are both declared, and
   missing coverage, asymmetric matchers, direct allow substitution, expanded
   timeouts, and extra events are rejected by deterministic tests.
3. `SubagentStart` and `SubagentStop` both use the exhaustive declaration
   matcher `.*`; their handlers bind `RoleSpec` and validate `ResultEnvelope`.
   Missing routes, partial identity matchers, and handler substitution are
   rejected. This establishes the static expected-count handler binding; it
   does not claim that H03 implements runtime fan-in reconciliation.
4. The plugin manifest still has no hook registration or capabilities and no
   `dist/hook-runner.mjs` exists. This is an explicit responsibility boundary,
   not a silent fallback.
5. The targeted suite is 27/27: eight H03 cases, eight H02 regressions, and
   eleven H01 gateway regressions. Full Python is 947/947. Full Node is 342/343
   with only exact unchanged S04-TM004; the Node footer/testcase-element
   difference remains explicitly reconciled.
6. Product writes are confined to the two exact H03 paths. Earlier reports,
   RAH generations, and unrelated dirty-worktree content remain preserved.

## Assurance boundary

H03 verifies static tool/delegation declarations and their fail-closed handler
bindings only. It does not claim an implemented hook runner, plugin-manifest
registration, actual policy/receipt execution, host capability probing,
degraded-mode behavior, expected identity/count reconciliation, Codex adapter
integration, exhaustive enforcement, or packaged runtime integration. H04 owns
capability and degraded-mode gates; N04 owns runtime fan-in identity/count
reconciliation; X01 and G06 own later host-adapter and packaging integration.

## Decision

Both H03 exit criteria pass at the static declaration and handler-binding
boundary, and both required checks pass. Product completion, release readiness,
and a globally green repository remain false.
