# B01 current boundary-checker advisory review

Review the attached current B01 boundary checker and policy as a read-only architecture/security adviser. The checker file is the exact current working-tree revision (SHA-256 `FC624B916A903B8EDA2CC45092E4292614B1A577271E13417FFA5BA557C2FEEC`).

The intended contract is:

- reject every relative import that crosses a declared component boundary;
- reject package-private/deep imports and enforce each package's explicit `exports` surface;
- reject absolute paths, non-`node:` URL schemes, encoded specifier bypasses, and symlinked policy roots or children;
- detect forbidden duplicate Python implementations by exact normalized `/`-separated relative module path across the two declared roots; Python duplicate identity is case-sensitive here;
- fail closed on unknown policy values;
- parse supported JS/TS/JSX/TSX module forms without letting comments, regexes, templates, JSX, or TypeScript-erased syntax hide or invent module specifiers;
- terminate in bounded time without evaluating repository code.

The last repair made JSX/TSX balanced type-argument scanning delegate nested template-literal types to the shared recursive raw-template scanner. It also preserves exact-case Python duplicate keys; filesystem case folding remains limited to runtime filesystem/component boundary comparison.

Return exactly one of:

1. `NONE` if there is no concrete material correctness or security blocker in the attached current files; or
2. one strongest blocker, including a minimal valid source example, exact causal path, and smallest B01-local repair.

Do not request tests, builds, evidence artifacts, schema changes, or broader parser expansion. Do not treat hypothetical unsupported syntax as a blocker unless it is valid syntax in one of the extensions the checker currently declares as supported and it can concretely bypass or falsely trigger the boundary policy.
