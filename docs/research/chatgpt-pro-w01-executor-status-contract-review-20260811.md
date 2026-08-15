SPEC_GAP

* **Dropping `executor_status` from the compiled identity is a W01-local correctness defect.** `absent`, `executor_bound`, and `executor_unbound` have materially different canonical meanings; compiling them to the same `compiled_sha256` erases information needed for replay and satisfiability analysis. A census alone is insufficient because two nodes can swap statuses while preserving identical counts. The compiler must include a deterministic, `node_id`-sorted per-node projection whose value is exactly `null`, `executor_bound`, or `executor_unbound`; the census may be derived from it. This projection must participate in `compiled_sha256`. The scheduler projection and `scheduler_plan_sha256` may remain unchanged because the scheduler does not own this optional field.

* **W01 may fail closed locally on an explicit unbound declaration.** With the frozen `missing_node_policy: FAIL`, any required node declaring `executor_unbound` makes the workflow structurally unsatisfiable and must raise a W01-local typed refusal such as `EXECUTOR_UNBOUND` before scheduler compilation. This does not invent execution semantics; it directly enforces the schema’s stated consequence. An absent status remains **unverified**, not equivalent to unbound. An `executor_bound` value remains a caller declaration pending resolution, not proof of liveness.

* **The current regression expecting all three variants to compile to the same hashes is incorrect.** The minimum corrected expectations are:

  * absent and `executor_bound` may compile structurally, but produce distinct compiler identities and status projections;
  * `executor_unbound` under `missing_node_policy: FAIL` is refused;
  * none of these cases establishes verified executor reachability without the resolution gate.

* **Full “unknown executor blocked” completion cannot be achieved inside W01.** W01 owns only `packages/foundry-kernel/src/workflows/compiler/**`, while its exit criteria require both resource-edge validation and unknown-executor blocking.  Syntax validation cannot establish that a Python symbol, prompt, subworkflow, tool path, or other executor is present and callable in a particular release. A higher-authority decision must assign the executor-resolution contract and owner: the authoritative inventory/resolver source, release or repository identity, type-specific resolution rules, and immutable resolution result consumed by W01. Until that binding exists, `executor_bound` cannot be accepted as verified and W01 cannot claim its second exit criterion. Under the authority order, missing shared semantics require `SPEC_GAP`. 

* **The `exclusive:*` repair is independently authorized.** A shared `quota:*` resource controls capacity and may permit concurrency; it therefore cannot prove serialization of overlapping writers. Only dependency ancestry or a shared `exclusive:*` resource may satisfy the write-conflict check. Quota resources should remain in scheduler capacity accounting, but must not count as write serialization.

**Smallest truthful next change:** retain the `exclusive:*` correction; add the per-node status projection and census to the compiled identity; refuse explicit unbound nodes under `FAIL`; revise the three-status regression accordingly; and leave W01 blocked on a product-owner assignment for the shared executor-resolution gate.
