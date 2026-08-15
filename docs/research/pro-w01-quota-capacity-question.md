# W01 follow-up: compiler bypasses explicit quota capacity

Continue in the same new Epistemic Foundry conversation. The prior W01 `resource_edges` immutability repair is now implemented and independently reviewed; do not reopen it.

Assess exactly one additional W01 candidate against the already attached compiler/scheduler/authority files and the newly attached current compiler bytes.

## Candidate

`workflow-compiler.mjs::compile()` currently inserts `capacities[resource] = 1` for every node `resource_dependency`. It then passes this map to `compileSchedulerPlan()`. The scheduler’s canonical `normalizeResourceCapacities()` requires every used `quota:` resource to have an explicitly supplied bounded capacity and raises `RESOURCE_CAPACITY_MISSING` when absent; it auto-defaults only `exclusive:` resources to `1`. The compiler’s blanket default therefore makes the quota-missing gate unreachable and hashes an invented capacity as though it were operator-supplied.

Return exactly one verdict:

- `AUTHORIZED_LOCAL_REPAIR` if W01 already owns this fail-closed correction;
- `SPEC_GAP` if the source of quota capacities or compile ABI needs a new shared decision;
- `NONE` if current behavior is contract-correct.

If authorized, decide the exact smallest one-file behavior:

- collect the set of all used resources;
- default only `exclusive:` resources to capacity `1`;
- validate overrides against the used-resource set;
- leave `quota:` absent unless explicitly supplied so the existing scheduler error fires;
- leave generic resources without capacities unless explicitly supplied;
- preserve valid explicit quota overrides, exclusive semantics, deterministic ordering/hashes, the new resource-edge freeze, and every unrelated dirty compiler hunk.

Do not propose tests, schemas, manifests, reports, evidence artifacts, package exports, or scheduler edits. State whether lack of a current production importer affects correctness or only reachability.
