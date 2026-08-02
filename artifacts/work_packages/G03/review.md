# G03-0001 path authority contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final G03 bytes. It is not actor-independent certification.

## Reviewed product boundary

- `packages/plugin-host/src/paths/path-resolution.mjs` — `sha256:b53b406829787bf3d93c4fe13744b0aeea4df2ab9dca0186a756a4f6bdca20fe`
- `packages/plugin-host/src/paths/path-resolution.test.mjs` — `sha256:b84c28f6060f6223454a542977367cbdaede605da3692470d9ce674990344fee`
- `packages/plugin-host/src/paths/path-traversal.test.mjs` — `sha256:f5b57d3989149c820278aee4545c98d6d73805bf03048839b4daf221f019d8b9`

The review also checked the evidence-sealed G01 dependency, the G02 serial
checkpoint, current G03 manifest contract, plugin bootstrap workflow, state
mapping and security guidance, normalized regression receipts, and the live
156-package dependency graph.

## Findings

1. `resolvePluginPaths` requires explicit absolute `pluginRoot`, `pluginData`,
   and `workspaceRoot` directories. It uses `lstat` plus native `realpath` and
   never consults cwd, environment, HOME, PATH, a repository checkout, or an
   editable-install fallback.
2. Installed code, plugin-writable data, and workspace authority are pairwise
   disjoint. Workspace state resolves to exactly
   `<workspaceRoot>/.epistemic-foundry`; a fresh state directory must be
   created by an authorized effect and then re-resolved before child use.
3. Root aliases, symlinks, junctions/reparse points, identity replacement,
   nested boundary overlap and cross-device children fail closed. An opaque
   `WeakMap` record prevents a copied public result from retaining authority.
4. Child paths use canonical portable forward-slash syntax and reject
   traversal, absolute paths, mixed separators, NUL/control characters,
   alternate data stream colons, Windows reserved names and invalid aliases.
   Parents are inspected without following links before an existing target or
   a missing final create target is returned.
5. Create targets are permitted only below `PLUGIN_DATA` or
   `WORKSPACE_STATE`; the resolver itself performs no filesystem write.
   Returned strings are checked locations, not durable capabilities, and
   effect code must resolve again immediately before use.
6. Spaces and Korean characters are exercised in roots and child paths.
   Targeted Node is 13/13: eight path-resolution and five path-traversal
   cases. Full Python is 947/947. Full Node is 330/331 with only the exact
   unchanged S04-TM004 stale manifest hash debt and all 13 G03 tests passing.
7. Product writes are confined to `packages/plugin-host/src/paths/**`.
   Evidence remains under `artifacts/work_packages/G03/**`; all unrelated
   dirty-worktree content and prior attempts and RAH generations remain
   preserved.

## Assurance boundary

This review proves deterministic explicit root selection and no-follow path
resolution for the current Node host boundary. It does not prove marketplace
install/enable/disable/uninstall behavior, OS-enforced sandboxing, race-free
durable file-handle capabilities, downstream effect execution, release
readiness, production authorization, or actor-independent certification.
Those claims remain outside G03; fresh-install lifecycle behavior is G04-owned.

## Decision

Both G03 exit criteria pass: installed code and writable data are separated,
and spaces/non-ASCII paths are supported. Both required checks pass. Product
completion remains false.
