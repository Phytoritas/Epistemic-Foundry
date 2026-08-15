# AUTHORIZED_LOCAL_REPAIR

The defect is real. `compile()` currently converts **every** used resource into a capacity declaration of `1`. An undeclared `quota:` resource therefore reaches `normalizeResourceCapacities()` as though the operator had explicitly supplied capacity `1`, making the canonical `RESOURCE_CAPACITY_MISSING` branch unreachable. 

The scheduler already defines the complete semantics needed for repair:

* every used `quota:` resource requires an explicit positive bounded capacity;
* an omitted `exclusive:` resource defaults to `1`;
* an explicit `exclusive:` capacity must equal `1`;
* capacities for unused resources are rejected;
* normalized capacities are deterministically key-sorted before hashing. 

The compiler already has the explicit `resourceCapacities` input ABI, so no new decision about persistence, versioning, or capacity provenance is needed. W01 owns the workflow compiler and its DAG/resource-edge validation boundary. 

## Smallest production repair

**Only:** `packages/foundry-kernel/src/workflows/compiler/workflow-compiler.mjs`

```diff
     Object.freeze(resourceEdges);
+    const usedResources = new Set();
     const capacities = {};
     for (const node of document.nodes) {
       for (const resource of node.resource_dependencies) {
-        capacities[resource] = 1;
+        usedResources.add(resource);
+        if (resource.startsWith("exclusive:")) capacities[resource] = 1;
       }
     }
     if (!isPlainObject(resourceCapacities)) {
       fail("WORKFLOW_DOCUMENT_INVALID", "resourceCapacities override must be an object");
     }
     for (const [resource, capacity] of Object.entries(resourceCapacities)) {
-      if (!Object.hasOwn(capacities, resource)) {
+      if (!usedResources.has(resource)) {
         fail("WORKFLOW_DOCUMENT_INVALID", "capacity override names an unused resource", {
           resource,
         });
       }
       capacities[resource] = capacity;
```

This produces the required behavior:

* all used resource names are collected independently of capacity declarations;
* only `exclusive:` resources receive compiler defaults;
* absent `quota:` resources remain absent, allowing the scheduler to raise `RESOURCE_CAPACITY_MISSING`;
* valid explicit quota overrides are preserved;
* unused overrides remain rejected;
* no capacity is invented for any other resource class, while the scheduler remains authoritative over the currently permitted resource vocabulary;
* valid compiled output order, normalized scheduler plans, `plan_hash`, and `compiled_sha256` bytes remain unchanged.

The existing resource-edge freeze and all unrelated dirty compiler hunks remain untouched.

The absence of a current production importer affects **reachability only**, not correctness. The package currently exposes no public exports, but an internally incorrect compiler does not become contract-correct merely because its defective path is not yet publicly reachable. 
