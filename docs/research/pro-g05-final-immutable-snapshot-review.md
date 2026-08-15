# G05 final immutable snapshot review

Review the attached current G05 implementation as an advisory, read-only final code review. Do not propose evidence packets, reports, receipts outside the product API, or test execution.

Authority and intended bounded repair:

- `MASTER_SPEC.md` defines G05 as the evolution plugin skills, CLI surface, and progressive-disclosure routing package. It may route and disclose metadata but may not acquire evaluator, holdout, or promotion authority.
- G05 owns only `plugin_blueprint/epistemic-foundry/v4_g05/**`.
- A validated `loadSurface()` result must remain a stable behavior-bearing snapshot after return. Nested arrays/objects and its two Map-backed indexes must not be mutable by a caller.
- `resolveDisclosure()` must reject a skill that exists in the payload inventory but is not a member of the G05 evolution surface.
- `surfaceReceipt(loaded)` must use the exact source bytes captured by that successful `loadSurface()` call. Later filesystem drift must not rewrite the receipt for the already-loaded snapshot.

The current patch adds recursive freezing, private Map-backed read-only facades, the surface-membership guard, one-time source byte capture, frozen source digests, and a deeply frozen receipt. Tests shown in the attachments are source-level regressions only and have not been executed.

Please inspect the exact attached current files and return:

1. Any concrete material correctness, authority, compatibility, or TOCTOU blocker, with exact function/line locator and the smallest G05-local fix.
2. Pay special attention to `deepFreeze`, `readonlyMap`, all current consumers of `agentCards`/`referencesById`, exact receipt preimage stability, and whether any source is semantically read after its receipt digest was captured from different bytes.
3. If no material blocker remains in this bounded repair, answer `PASS` plainly.

Do not assume tests passed. Do not recommend shared-contract changes unless the current G05-local semantics genuinely cannot close the issue.
