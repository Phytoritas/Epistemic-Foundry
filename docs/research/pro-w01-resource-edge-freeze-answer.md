# AUTHORIZED_LOCAL_REPAIR

## Repository authorization

W01 owns `packages/foundry-kernel/src/workflows/compiler/**`, and its explicit exit criterion includes validation of DAG and resource edges. The higher architecture assigns immutable RunSpec, scheduling, checkpoint, and replay authority to the Foundry Kernel. Enforcing immutability of a compiler-created, hash-covered projection is therefore within W01; it does not require a persistence, versioning, schema, or cross-package ABI decision.  

The defect is concrete: `validateResourceEdges()` creates mutable edge objects plus mutable `nodes` and `shared_resources` arrays. `compile()` includes that projection in the input to `compiled_sha256`, but the final `Object.freeze(...)` protects only the returned top-level object. A caller can consequently change hash-covered resource-edge content while retaining the original hash. 

## Authorized scope

Deep-freeze **only the normalized `resource_edges` projection**, not the complete compiled artifact.

That is sufficient because the other nested return values are already immutable: executor-status rows and their array are explicitly frozen, while `scheduler_plan` and its referenced `topological_order` are recursively frozen by the scheduler compiler. A generic full-artifact freezer would broaden runtime policy beyond this defect and beyond W01’s smallest necessary repair.  

## Smallest one-file production repair

**Path:** `packages/foundry-kernel/src/workflows/compiler/workflow-compiler.mjs`

```diff
     const resourceEdges = validateResourceEdges(document.nodes);
+    for (const edge of resourceEdges) {
+      Object.freeze(edge.nodes);
+      Object.freeze(edge.shared_resources);
+      Object.freeze(edge);
+    }
+    Object.freeze(resourceEdges);
     const capacities = {};
```

This freezes the outer projection, every edge row, and both nested arrays before hashing. It changes no values, property order, array order, canonical JSON, or `compiled_sha256` bytes. No scheduler, schema, manifest, test, report, evidence, export, or unrelated compiler hunk is touched.

The absence of a current production import caller **only limits exploit reachability**. The package’s empty `exports` map does not make the compiler’s hash-bearing return value internally correct; it merely means the defect is not presently exposed through the package-level production API. 
