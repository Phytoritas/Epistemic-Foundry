# R02 proof-trace graph binding review

Review the attached current R02 production and test sources against the following bounded claim. Treat the repository authority and current source as authoritative; do not propose evidence packets, report artifacts, or unrelated refactors.

R02 owns only `python/epistemic_foundry/reasoning/deduction/**`. Its local `ProofTrace` output previously used the source `ArgumentGraph.graph_hash` while deriving `proof_trace_id`, but did not publish that graph hash. Consequently, `validate_proof_trace()` could validate only the trace self-hash and could not recompute the content ID from the public trace. It also enforced only `broken_edges -> BROKEN`, allowing a fully rehashed conditional trace to claim `VALID`.

The bounded repair now:

- publishes `argument_graph_hash` in each `ProofTrace`;
- validates its canonical `sha256:<64 lowercase hex>` shape;
- recomputes `proof_trace_id` from the same historical preimage (`argument_graph_id`, `assumption_ledger`, `conclusions`, `created_at`, and the graph hash under the historical preimage key `graph_hash`), so builder-generated proof-trace IDs remain compatible;
- derives status exactly as `BROKEN` when `broken_edges` is nonempty, otherwise `CONDITIONAL` when the assumption ledger is nonempty, otherwise `VALID`;
- preserves the existing behavior that an ordinary un-rehashed mutation fails first as `TRACE_HASH_MISMATCH`, while a rehashed semantic mutation reaches the new status/content-ID checks;
- adds narrow regression fixtures for graph-hash publication, forged content IDs, forged graph hashes, and rehashed conditional-to-valid laundering.

No shared `ProofTrace` JSON Schema and no consumer outside the R02 package was found. Adding the published graph hash changes `trace_hash` because the public trace shape changes, but does not change the historical `proof_trace_id` derivation for builder output.

Return either `NO_BLOCKER` or a concise list of material correctness, authority, migration, or compatibility blockers. Ignore style-only suggestions. Do not ask to run tests.
