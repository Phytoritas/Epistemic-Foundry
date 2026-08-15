AUTHORIZED

**DUPLICATE IMPLEMENTATION POLICY:** Enforce it locally. B01 owns `packages/**` and `python/**`, declares both Python roots, and must provide `forbidden_source_import_check`; the current B01 policy explicitly sets `duplicateImplementationPolicy` to `forbidden`. Reporting an overlap does not choose a canonical root or perform the later packaging consolidation.  

The bounded behavior is:

* Enumerate regular `.py` files under `runtimeRoot` and `componentRoot`.
* Key each file by its path relative to its own root, converting platform separators to `/`.
* Treat an exact relative-path intersection as a duplicate regardless of whether the bytes are equal.
* Compare paths exactly and case-sensitively, with no case folding, Unicode normalization, content equivalence, import-name inference, or canonical-owner selection.
* Sort intersecting relative paths by deterministic code-unit order and emit one failure per path. Existing intersections therefore make the current check return `FAIL`; that is truthful enforcement, not a `SPEC_GAP`.
* Preserve the current walk exclusions—`node_modules`, `dist`, `build`, and `coverage`—and add no undeclared generated-source exemption.
* Preserve the current walker’s symlink behavior: do not follow nested symbolic links and do not introduce `realpath`-based alias semantics.
* Require the policy value to be exactly `"forbidden"`. A missing or unknown value must produce an unsupported-policy failure rather than being treated as permission or assigned a new meaning. Resolving such an unknown value would then require higher authority.

A shared packaging decision is needed only to remove/reconcile the reported duplicates or to change the policy—not to detect the already-forbidden condition.

**JAVASCRIPT/TYPESCRIPT EXTRACTION:** Close the side-effect-import omission in the same B01 patch. The accepted ADR prohibits private-source imports and also prohibits hiding them through dynamic or generated mechanisms, while the present regex visibly omits bare import declarations.  

The minimum dependency-free lexical contract is:

* Scan code separately from quoted strings, line and block comments, regular-expression literals, and template raw text; recursively scan `${...}` template expressions.
* Recognize exact identifier tokens, with whitespace and comments as trivia, for:

  * `import "specifier"` bare side-effect declarations;
  * `from "specifier"` static import/export declarations;
  * `import("specifier")`;
  * `require("specifier")`;
  * direct optional calls `require?.("specifier")`.
* Preserve the existing package-private and relative-private-source checks after extraction.
* Read single- and double-quoted literals through their matching delimiter while correctly consuming escaped characters and every ECMAScript LineContinuation form: backslash followed by LF, CR, CRLF, U+2028, or U+2029.
* For the minimum repair, any extracted module literal containing an escape or LineContinuation must fail closed as an uncomparable escaped module specifier. It must not be checked using its raw spelling, partially decoded, silently skipped, or evaluated with `eval`/`Function`. Thus `\u002f`, `\x2f`, `\u{2f}`, escaped characters, and line-spliced `/src/` paths cannot bypass the boundary.
* Unterminated or otherwise lexically indeterminate module literals must likewise fail closed. Arbitrary computed runtime expressions need not be assigned a target by this bounded repair.

**SMALLEST FILE CHANGE:** Modify only `packages/repo-checks/check-boundaries.mjs`: replace the regex with the local lexical scanner and add the policy-driven two-root `.py` intersection check. No change is required to `boundary-policy.json`, ADR-032, manifests, package dependencies, or lockfiles. The existing failure wording should remain unchanged; only the new unsupported-policy, escaped-specifier, and duplicate-path messages need stable B01-local wording because no higher authority fixes their prose.
