# B01 boundary checker final diff review

Review the attached current `packages/repo-checks/check-boundaries.mjs` as an advisory security/correctness reviewer. The higher-authority B01 requirement is to fail closed on cross-component private-source imports and on duplicate Python implementations forbidden by `packages/boundary-policy.json`. The implementation must remain dependency-free and local to this checker.

The latest patch intentionally:

- recognizes bare/static/dynamic import, export-from, `require()`, and optional-call `require?.()` without treating comments, ordinary strings, regex bodies, template raw text, or JSX text as code;
- treats escaped or unterminated module specifiers as failures;
- normalizes valid Unicode escapes in IdentifierNames so escaped `require` cannot bypass inspection;
- keeps template and JSX expression segments separated;
- distinguishes expression-valued braces from statement blocks, and control-header parentheses from expression parentheses, when choosing regex versus division lexical goal;
- scans JSX/TSX expression containers while skipping JSX tags/text;
- enforces `duplicateImplementationPolicy: forbidden` by exact case-sensitive relative Python paths and fails on unknown policy values.

Focus only on material false negatives or material false positives in the current attached bytes. In particular, adversarially inspect object/class/function expressions followed by division, regex statements after blocks/control headers, JSX/TSX, escaped IdentifierNames, `import from from "..."`, template segment adjacency, and private `#require` names.

Return exactly one of:

- `B01_CHECKER: PASS` if no concrete material blocker remains; or
- `B01_CHECKER: BLOCKED` followed by the exact executable source pattern, causal path, and smallest one-file repair.

Do not propose schema, manifest, policy, test, artifact, or evidence changes. Do not infer that any repository gate was run.
