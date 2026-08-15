# R02 detached-snapshot follow-up

Re-review the attached current R02 sources after your blocker. Focus only on whether the blocker is closed and whether the correction introduced a material contract or compatibility issue.

The correction adds `_detached_json_object()`, which canonicalizes the already top-level-copied, exact-field-checked input exactly once and parses those bytes into plain JSON. Both `build_proof_trace()` and `validate_proof_trace()` immediately replace their shallow projection with that detached object. All graph/trace hash calculations, semantic checks, status derivation, proof ID derivation, and final sealing now use only the detached object.

The existing validation order remains: semantic structural checks, then `trace_hash`, then derived status, then `proof_trace_id`. Two regression fixtures inject a caller-side mutation immediately after graph-hash or trace-hash computation and assert that the sealed result remains the detached snapshot rather than revisiting the mutated source.

The earlier bounded repair remains unchanged: `argument_graph_hash` is published, historical builder proof IDs are preserved by retaining the old `graph_hash` preimage key, and rehashed status/content-ID laundering fails closed.

Return either `NO_BLOCKER` or only material remaining correctness, authority, migration, or compatibility blockers. Ignore style-only suggestions. Do not ask to run tests.
