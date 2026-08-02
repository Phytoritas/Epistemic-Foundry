# G01-0001 native plugin manifest contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and explicitly
forbids subagents for this sequence. This is a procedurally separate review of
the final G01 bytes. It is not actor-independent certification.

## Reviewed product boundary

- `plugins/epistemic-foundry/.codex-plugin/plugin.json` — `sha256:1b1ec359ab93733114c95acb34c4a74615974456ddab52fa7c1c538159318a87`
- `plugins/epistemic-foundry/assets/composer-icon.svg` — `sha256:ca04da7e14c09211ee56fd8568f11f757837e7490fb8c059e5907889ccf22cfd`
- `plugins/epistemic-foundry/assets/logo.svg` — `sha256:ed2847842f2108ec64cd98700ffa1d0ef4d4195095b1b92c47fe9783b4b9a4d4`

The review also checked the latest PASS reports for B04-0004, C04 and S01,
the current 156-package manifest, the official local plugin validator, the
current Codex plugin manifest/path guidance, and normalized full-regression
receipts.

## Findings

1. The package contains exactly one `.codex-plugin/plugin.json` plus two local
   SVG assets. Every referenced asset resolves inside the plugin root; parent
   traversal, Windows absolute paths and missing resources fail closed.
2. The manifest version is `4.0.0`, matching the workspace version. Its name,
   descriptions, author and interface fields pass the official validator.
3. The manifest intentionally declares no `skills`, `hooks`, `mcpServers` or
   `apps`. Those components belong to later work packages and are not exposed
   before their gates pass.
4. `interface.capabilities` is the exact empty array. The G01 shell therefore
   makes no runtime, scientific, approval, holdout or canonical-authority
   claim. Capability overclaim is rejected by an adversarial fixture.
5. Both SVGs are well-formed, local-only, square, bounded and free of active
   references. The composer icon is 64x64 and the logo is 256x256.
6. The unresolved release-license placeholder in the reference blueprint is
   not represented as a real license claim. G01 establishes package identity,
   not release authorization.
7. Full Python is 947/947. Full Node is 313/314 with only the exact unchanged
   S04-TM004 stale manifest hash debt; G01 causes no new failure, skip or
   xfail and does not reassign that debt.
8. Product writes are confined to the exact G01 manifest and asset scope.
   Evidence files remain under `artifacts/work_packages/G01/**`; unrelated
   dirty-worktree content and every earlier RAH generation remain preserved.

## Assurance boundary

This review proves the current local manifest and asset package shape. It does
not prove marketplace installation, payload dispatch, plugin-root/data-root
resolution, hooks, MCP runtime, skills, production capability enforcement,
release licensing, or actor-independent certification. Those claims remain
owned by later packages.

## Decision

Both G01 exit criteria pass: manifest paths remain within the plugin root, and
the declared version and empty capability surface are accurate. Product
completion remains false.
