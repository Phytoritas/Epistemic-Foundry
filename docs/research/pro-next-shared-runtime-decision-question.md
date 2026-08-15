# Epistemic Foundry v4 — next shared runtime decision

We are continuing implementation against `MASTER_SPEC.md` in the current dirty workspace. Do not treat prior work-package PASS reports as proof of end-to-end runtime reachability, and do not propose fake receipts, evidence packets, or local convenience wrappers that bypass the authority order.

Several package-local correctness repairs are now on disk (RFC3339/chronology alignment in H01/D03/E01/E02/F02, F03 state-history validation, K01 replay fencing, U05 duplicate challenge identity, V02/V04/V05 hash binding). The next progress is blocked mainly by shared ownership gaps:

1. Workflow execution reachability: `workflow-compiler.mjs` validates executor-ref syntax and the scheduler preserves refs, but there is no provider-neutral scheduler-to-executor composition root. A static census found most workflow executor refs unresolved. N02 owns bounded role execution, N03 owns scheduler behavior, while concrete workflow adapters such as `epistemic_foundry.plugin.conduct_bounded_interview:run` and `epistemic_foundry.validation.runner:execute` are absent or outside current package scopes.
2. A05 promotion gate composition: G12/G13 `NOT_REQUIRED` decisions need sealed applicability inputs (`requested_level`, `human_approval_required`) that are absent from the closed NodeInvocation/payload contract.
3. S05 candidate execution qualification accepts raw hard limits rather than a canonical `BudgetEnvelope`; a correct migration spans S05, K06 and downstream requalification.
4. G02 dispatcher parent/child lifecycle has no frozen cross-platform termination guarantee; Node-only Windows/Unix semantics do not establish process-tree cleanup.
5. J02 runtime token recount needs a packaged, pinned canonical tokenizer capability, while the only current implementation is a development-only Python tool.

Question: Which **single shared authority decision** should be ratified first because it unlocks the greatest amount of real, dependency-ready runtime work without weakening Foundry invariants?

Return one recommendation only, with:

- the exact existing authority owner(s) or the exact new L4 work-package owner that must decide it;
- the smallest manifest/write-scope change required;
- the minimal provider-neutral public interface and typed inputs/outputs;
- the dependency edges that must be added or corrected;
- the first three concrete consumers that become implementable after ratification;
- explicit non-goals and failure semantics;
- why each of the other four gaps should remain deferred.

Do not call the recommendation ratified. If the current authority sources cannot select an owner, say `SPEC_GAP` and name the smallest human decision needed.
