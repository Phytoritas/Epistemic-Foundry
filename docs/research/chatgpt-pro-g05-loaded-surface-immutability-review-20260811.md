AUTHORIZED

**MINIMUM IMMUTABLE GRAPH:** After all existing validation and authority checks succeed, freeze the final `loaded` object and every plain-object/array descendant reachable through:

* `surface`, including membership, authority declarations, every skill row, and all command/mutable-kind arrays;
* `inventory`, including skills, references, predicates, budgets, metadata projection, and nested arrays;
* `projectedCommands`, `proposedCommands`, `mutableSearchSpace`, and `authorityBearingCommands`;
* every `agentCards` value;
* every `referencesById` value.

Freezing only `loaded.surface` is insufficient. Post-validation routing also reads mutable inventory budgets and skill projections, agent-card policies and phrases, reference closure rows, projected/proposed commands, mutable-search-space data, and authority-bearing command arrays. `surfaceReceipt()` combines several of those independently validated views.   

**MAP BOUNDARY:** Replace `agentCards` and `referencesById` after validation with frozen G05-local read-only facades backed by private Maps whose values are already deep-frozen. The proposed read surface—`size`, `get`, `has`, `keys`, `values`, `entries`, `forEach`, and `[Symbol.iterator]`—is compatible and preserves insertion order. Do not expose `set`, `delete`, or `clear`.

The backing Map must never escape. In particular, `forEach` must wrap the callback and pass the read-only facade as its third argument; using `backing.forEach.bind(backing)` would disclose the mutable backing Map. The facade should use own closure-backed methods on a frozen/null-prototype object, or an equivalently frozen prototype, so callers cannot replace its read methods.

**RECEIPT:** Apply the same deep-freeze helper to the object returned by `surfaceReceipt()`, including `sources`, command rows, and all arrays. This makes its existing “immutable receipt” contract true without changing its preimage, ordering, or receipt hash. The current implementation freezes only the receipt’s outer object. 

**COMPATIBILITY BLOCKER:** none. Current G05 production and tests use Map-style reads, chiefly `.get`, and no shared wire schema requires native `Map` identity. The change is an internal representation hardening within G05’s declared write scope and directly preserves its prohibition on acquiring promotion authority and its immutable-receipt requirement.  
