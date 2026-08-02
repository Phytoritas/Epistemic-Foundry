# G02-0001 payload dispatcher contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final G02 bytes. It is not actor-independent certification.

## Reviewed product boundary

- `plugins/epistemic-foundry/bin/efoundry.mjs` — `sha256:17723d450644508b755e725300a600f3792c05714056c794517bd9de2d005e05`
- `packages/plugin-host/src/cli-dispatch/payload-cli-smoke.test.mjs` — `sha256:e5f4f328a100abac6692e26dbce04e33cf15884be47a9e59d08604a133ab5b94`
- `packages/plugin-host/src/cli-dispatch/dispatcher-boundary.test.mjs` — `sha256:7c3600faf8373e1db3c1f03bca89e820668bd55e81f7e5b8535c0a13e12e543c`

The review also checked the evidence-sealed G01 dependency, current G02
manifest contract, normalized targeted and full-regression receipts, plugin
architecture guidance, and current 156-package dependency graph.

## Findings

1. The dispatcher computes exactly one payload target, `../dist/cli.mjs`,
   relative to its own module URL. It never searches the repository, current
   working directory, PATH, Python package, or an environment override.
2. It starts the payload with the absolute current Node executable
   (`process.execPath`), `shell: false`, inherited stdio, the caller's working
   directory and environment, and unchanged arguments. This is a thin process
   adapter rather than a second CLI implementation.
3. A copied installed-plugin fixture works with an empty PATH, spaces and
   Korean characters in paths and data. Arguments, stdin, stdout, stderr, cwd,
   environment, and nonzero exit code 23 are preserved.
4. Removing the fixture `dist/cli.mjs` fails closed. No repository-root or PATH
   fallback is attempted, so a missing packaged payload cannot silently use a
   checkout or editable install.
5. Static boundary checks permit only `node:child_process` and `node:url` and
   reject domain, canonical-registry, policy, promotion, PLUGIN_ROOT and
   PLUGIN_DATA logic. Root/data/workspace resolution remains G03-owned.
6. CLI command semantics and stable JSON error contracts remain T03-owned;
   marketplace fresh-install behavior remains G04-owned. G02 does not create
   or claim the downstream-built `dist/cli.mjs` payload.
7. Targeted Node is 4/4 and full Python is 947/947. Full Node is 317/318 with
   only the exact unchanged S04-TM004 stale manifest hash debt. The four G02
   tests pass in the full suite and G02 causes no new failure, skip, or xfail.
8. Product writes are confined to the two exact G02 scopes. Evidence remains
   under `artifacts/work_packages/G02/**`; unrelated dirty-worktree content and
   all earlier attempts and RAH generations remain preserved.

## Assurance boundary

This review proves the current payload process-forwarding and fail-closed
target behavior. It does not prove PLUGIN_ROOT/PLUGIN_DATA/workspace policy,
the downstream CLI's command semantics, marketplace installation, release
readiness, production authorization, or actor-independent certification.

## Decision

Both G02 exit criteria pass: absolute plugin-root invocation works without an
`efoundry` PATH alias, and the dispatcher contains no domain logic. Product
completion remains false.
