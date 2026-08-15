We are continuing a bounded review of Epistemic Foundry work package B01.

Authority and scope:

- B01 requires that no component import another component's private source tree.
- ADR-032 also forbids concealing a forbidden edge through dynamic imports or generated mechanisms.
- The local repair is confined to `packages/repo-checks/**`; it does not change a shared schema or policy.

Confirmed original defect: `check-boundaries.mjs` used a regex that ignored valid bare static side-effect imports such as:

```js
import "@epistemic-foundry/foundry-kernel/src/private.mjs";
import "../../foundry-kernel/src/private.mjs";
```

The attached current repair replaces that regex with a dependency-free lexical scanner. It separates code from strings, comments, regular-expression literals, and template raw text; scans `${...}` template expressions recursively; recognizes bare imports, `from`, literal `import(...)`, and literal `require(...)`; and fails closed on escaped or computed module specifiers that cannot be compared as written. Regression sources cover comment trivia, all JavaScript line terminators, escaped static specifiers, line continuation, template imports, non-code lookalikes, and a postfix-`++`/division case.

Review the exact attached current files, not the earlier regex proposal. Identify at most one concrete valid JavaScript/TypeScript source form that the current scanner either misses (allowing a private-source edge) or falsely extracts from a non-import lexical state (blocking valid source). Stay within the confirmed B01 source-boundary contract; do not turn this into a general parser or a new policy for arbitrary computed runtime imports.

Return exactly:

- `DECISION: ACCEPT` or `DECISION: CHANGES_REQUIRED`
- `BLOCKER:` `none` or one exact source form and causal scanner path
- `MINIMUM_REPAIR:` one B01-local change or `none`
- `RATIONALE:` concise
