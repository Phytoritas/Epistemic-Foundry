# G05 projection binding and shared dependency final review

Your prior agent-source blocker is closed and you returned PASS for that correction. A separate independent review of the latest worktree then found two additional current-disk facts:

1. G05 consumed `commandSurface()` but its receipt previously bound only counts/subsets, so a same-count change to an unclaimed projection row could preserve the receipt hash. The attached latest G05 now includes every canonical projection row (`command`, `mutating`, `segments`, `title`, `tool`) in the receipt preimage and adds a same-count projection-drift source regression.
2. The attached current shared `packages/plugin-host/src/cli/command-surface.mjs` is concurrently modified outside G05. It now projects only the 13 T01 read/planning tools, while the existing G05/G06 contracts expect the composed 22-command surface and G05 requires a non-empty authority-bearing subset. Consequently current `loadSurface()` fail-closes at `AUTHORITY_PREDICATE_EMPTY`. G05 owns only `plugin_blueprint/epistemic-foundry/v4_g05/**`; the shared CLI module is T03-owned, and G05 must not silently weaken its authority gate or overwrite concurrent work.

Review the attached latest files and answer in two explicit parts:

- `G05_LOCAL`: concrete material blocker remaining in the bounded G05 diff, or `PASS`.
- `SHARED_DEPENDENCY`: whether the 13-vs-22 current command-surface mismatch is (a) plainly stale/out-of-scope dependency drift whose owner must restore/reconcile the composed surface, or (b) a genuine shared `SPEC_GAP` requiring an authority decision. Give the exact authority conflict and smallest owner-level resolution. Do not tell G05 to remove the non-vacuity gate.

Do not assume tests ran. Do not request evidence artifacts or reports.
