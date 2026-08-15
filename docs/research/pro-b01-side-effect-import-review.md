We are now reviewing Epistemic Foundry work package B01. Local authority requires that no component import another component's private source tree, and ADR-032 explicitly forbids dynamic imports or generated mechanisms from concealing such an edge. B01 owns `packages/**`.

Confirmed defect: the existing boundary checker extracted only specifiers preceded by `from`, `import(`, or `require(`, so valid bare static side-effect imports such as these were invisible:

```js
import "@epistemic-foundry/foundry-kernel/src/private.mjs";
import "../../foundry-kernel/src/private.mjs";
```

Current local repair:

```js
const moduleSpecifierPattern = /\b(?:from\s*|import\s*(?:\(\s*)?|require\s*\(\s*)["']([^"'\r\n]+)["']/g;

export const extractModuleSpecifiers = (sourceText) => {
  if (typeof sourceText !== "string") throw new TypeError("sourceText must be a string");
  return [...sourceText.matchAll(moduleSpecifierPattern)].map((match) => match[1]);
};
```

`check-boundaries.mjs` now feeds every extracted specifier through its existing package-name and relative-private-source checks. A non-executable text fixture covers bare package and relative side-effect imports plus existing `from`, dynamic import, and require forms; a `node:test` source file checks extraction. The actual boundary check was not run.

Decision requested:

1. Does this close the confirmed bare side-effect-import omission without changing the B01 contract?
2. Identify at most one valid JavaScript/TypeScript module-specifier form that still bypasses this exact extractor and would materially violate the same private-source rule. Do not request a general parser unless the concrete form cannot be handled locally without one.

Return exactly:

- `DECISION: ACCEPT` or `DECISION: CHANGES_REQUIRED`
- `BLOCKER:` `none` or one exact source form and why it bypasses
- `MINIMUM_REPAIR:` one local change or `none`
- `RATIONALE:` concise
