# W01 follow-up: post-hash mutation of compiled resource edges

Continue in the same new Epistemic Foundry conversation. The W03 timestamp repair is now implemented and independently reviewed. `model_update`, unbound provenance graph identity, and graph-bound Passport application remain `SPEC_GAP`; do not reopen them.

Assess exactly one W01 candidate using the newly attached current files and the existing authority context.

## Candidate

`createWorkflowCompiler().compile()` validates `resource_edges`, places the returned nested arrays/objects in the compiled artifact, computes `compiled_sha256` from them, and returns only `Object.freeze(compiled)`. If `validateResourceEdges()` leaves the edge rows and their `nodes`/`shared_resources` arrays mutable, a caller can mutate the supposedly compiled/hashed resource graph after hashing while `compiled_sha256` remains unchanged.

Return exactly one verdict:

- `AUTHORIZED_LOCAL_REPAIR` if W01 already owns the immutability/hash-integrity meaning and a source-only repair is complete;
- `SPEC_GAP` if persistence/versioning/ABI authority is missing;
- `NONE` if current code already prevents the mutation.

If authorized, specify the smallest one-file production repair. Decide whether to deep-freeze only the normalized `resource_edges` projection or the complete compiled artifact, and ensure normal output order and `compiled_sha256` bytes remain unchanged. Preserve all unrelated dirty compiler changes. Do not touch tests, manifests, schemas, reports, evidence artifacts, package exports, or scheduler source.

Also state whether the absence of a current production import caller changes the correctness verdict or merely limits exploit reachability.
