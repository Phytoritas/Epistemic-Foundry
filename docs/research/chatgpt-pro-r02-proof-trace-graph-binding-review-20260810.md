**BLOCKER — graph/trace binding is not performed over one detached input snapshot.**

`_mapping()` makes only a shallow top-level copy, while `_sequence()` re-iterates caller-owned `Sequence` objects on every use.  Consequently:

* `build_proof_trace()` hashes the graph first and only afterward re-reads `nodes`, `edges`, and other arrays. A stateful sequence can therefore present one graph during `graph_hash` verification and a different graph during proof derivation. 
* `validate_proof_trace()` separately reads conclusions and the assumption ledger, recomputes `trace_hash`, derives status, derives `proof_trace_id`, and finally serializes the original shallow projection. Different iterations can expose different content at those stages. 

A concrete caller-controlled sequence can make a graph hash as fully grounded but produce a `CONDITIONAL` trace, or make validation seal a trace whose conclusion cites an assumption while its published ledger is empty, with both `trace_hash` and `proof_trace_id` still re-deriving. The existing regressions use ordinary lists and therefore do not exercise this boundary. 

**Smallest R02-owned correction:** in both `build_proof_trace()` and `validate_proof_trace()`, after the top-level mapping and exact-field check, canonicalize exactly once and parse those bytes back into detached plain JSON. Every semantic check, graph/trace hash calculation, status derivation, content-ID derivation, and final sealing must use only that snapshot and never revisit caller-owned nested objects. Preserve the present `trace_hash → status → proof_trace_id` validation order.
