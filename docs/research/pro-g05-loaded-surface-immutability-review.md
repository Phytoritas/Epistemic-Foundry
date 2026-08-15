# G05 validated-surface immutability boundary

Review one current G05 authority bypass and choose the smallest complete local repair.

`loadSurface()` validates the evolution surface, inventory, agent cards, reference closure, projected commands, budgets, and authority-bearing command exclusions. It then returns only `Object.freeze(loaded)`. That freeze is shallow. A caller can mutate `loaded.surface.skills[*].available_commands` after validation, and `routeEvolutionRequest()` later returns the inserted command without re-running `verifyCommands()`. This can insert a promotion-authority command after the authority gate passed.

A concurrent G05 edit already adds an out-of-surface guard to `resolveDisclosure()` and its adversarial test. Preserve it.

The narrow question is the immutable snapshot boundary:

- Is recursively freezing only `loaded.surface` sufficient for this package contract?
- Or must every behavior-bearing validated input used later by `routeEvolutionRequest`, `resolveDisclosure`, `assertWithinBudget`, and `surfaceReceipt` be immutable: `surface`, `inventory`, `projectedCommands`, `proposedCommands`, `mutableSearchSpace`, agent-card values, reference values, and authority-bearing command arrays?
- `agentCards` and `referencesById` are Maps. `Object.freeze(map)` does not block `.set/delete/clear`. Would a G05-local read-only Map facade exposing only `size/get/has/keys/values/entries/forEach/[Symbol.iterator]`, backed by a private Map whose values are deep-frozen, be the smallest robust compatible solution? Current production/tests use `.get`; no shared wire schema names this internal type.
- Should the return object and all plain object/array descendants be deep-frozen after all validation, with Maps replaced by those read-only facades?

The repair must stay inside `plugin_blueprint/epistemic-foundry/v4_g05/**`, preserve current reads and deterministic receipts, add no authority, and not alter schemas/workflows/manifests or shared package dependencies.

Return `AUTHORIZED` or `SPEC_GAP`, then the exact minimum graph that must be immutable and any concrete compatibility blocker. Do not request test execution, evidence/report regeneration, or unrelated refactors.
