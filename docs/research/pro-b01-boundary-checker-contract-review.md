# B01 boundary checker contract review

Review the attached current B01 boundary policy and checker as an advisory contract decision. The repository authority order is `MASTER_SPEC.md` → `manifests/development_manifest.yaml` → lower contracts/docs. B01 owns `packages/**`, depends only on PASS A04, and must implement `forbidden_source_import_check` without inventing later packaging architecture.

Two current-source omissions are visible:

1. `packages/boundary-policy.json` declares Python `runtimeRoot`, `componentRoot`, and `duplicateImplementationPolicy: "forbidden"`. `check-boundaries.mjs` scans the two roots only for `sys.path` mutation and filesystem-relative bypass strings; it never reads or enforces `duplicateImplementationPolicy`. The current roots contain intersecting relative `.py` paths. A checker can deterministically report those intersections, but consolidating the roots belongs to later packaging work and is not defined in B01.
2. The JavaScript import regex recognizes `from "..."`, `import("...")`, and `require("...")`, but not a bare static side-effect declaration such as `import "@epistemic-foundry/contracts/src/private.mjs";`. Raw escaped or line-continued string literals can also hide a cooked `/src/` path from the current regex.

Please decide the smallest authority-correct B01 repair against the exact attached files:

- Is enforcing `duplicateImplementationPolicy: forbidden` by indexing normalized relative `.py` paths and emitting sorted failures an authorized B01-local fail-closed correction even though existing duplicates will make the repository check fail, or is a shared packaging decision required first?
- Should the same B01 patch also close the side-effect-import extraction gap? If yes, specify the minimal lexical contract that is complete enough for valid ECMAScript string-literal forms without adding a new dependency or editing a lockfile. State how escapes and LineContinuation should be treated.
- Freeze deterministic ordering, unknown-policy behavior, path normalization/case semantics, generated/cache exclusions, symlink handling, and error wording only where current authority determines them. Do not propose deleting or consolidating Python implementations.

Return `AUTHORIZED` with exact bounded behavior and smallest file changes, or `SPEC_GAP` with the exact missing higher-authority decision. Do not assume checks ran and do not request evidence artifacts.
