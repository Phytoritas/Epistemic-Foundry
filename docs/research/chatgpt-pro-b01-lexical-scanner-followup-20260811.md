DECISION: CHANGES_REQUIRED

BLOCKER: `const privateModule = require?.("@epistemic-foundry/foundry-kernel/src/private.cjs");` is valid CommonJS and loads the module, but after scanning `require`, `readKeywordSpecifier` sees `?` rather than `(` and returns `null`; the quoted specifier is then skipped, so no private-source check occurs.

MINIMUM_REPAIR: Extend the B01-local `require` branch to recognize the direct optional-call sequence `require?.(<literal>)` and process its literal argument exactly like `require(<literal>)`.

RATIONALE: The scanner closes the confirmed bare-import omission, but the checker can enforce the boundary only for returned specifiers; this direct literal private-source load remains invisible and violates ADR-032 without requiring a general parser to fix.
