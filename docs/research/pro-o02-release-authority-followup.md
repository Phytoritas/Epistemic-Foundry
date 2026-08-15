Follow-up on the O02 review in this new conversation. The local JCS repair is implemented under the prior `AUTHORIZED_LOCAL_REPAIR` decision, including binary64/JCS decode-reseal, I-JSON noncharacter rejection, immutable policy data, canonical-byte-backed request/response/candidate projections, and typed deep-input refusal.

One separate authority issue remains. Please decide it against the following frozen facts.

1. Public O02 `evaluate_non_vector_release(candidates, required_lane_states, work_class, silent_fallback_count)` accepts caller-provided candidate mappings and caller-provided lane-state strings. It checks each candidate's self-rederived candidate ID/hash, but `compute_candidate_id/hash` are also public. A caller can change a candidate's retrieval channel or source-span status, recompute its hash, and supply favorable lane states; the guard has no original request/response or O01 receipt to resolve.
2. O02 depends on O01. O01 publicly validates and seals QueryPlan and SearchLaneReceipt, and `reconcile_search_run` derives a canonical SearchCompletenessCertificate from exactly eleven lane receipts. A SearchLaneReceipt binds run ID, QueryPlan ID/hash, lane, canonical query text/hash, scope, snapshot/index versions, result IDs/counts, and receipt hash. The certificate binds receipt IDs and per-lane reconciled states.
3. RetrievalCandidate carries its candidate ID/hash, request/response hashes, backend receipt ID, run/plan/query/snapshot/index bindings, but it does not carry an O01 SearchLaneReceipt ID/hash. A SearchLaneReceipt may list candidate IDs as `result_ids`; the current contracts do not explicitly state that this is the required O01↔O02 binding.
4. O02 owns only `python/epistemic_foundry/retrieval/lanes/**` and its named configuration/workflow/tests. O01 owns `python/epistemic_foundry/retrieval/planning/**`. O02 may consume O01's existing public API because O02 depends on O01, but it may not change O01 or invent a missing shared meaning.
5. `CandidateSetResult` now stores canonical candidate bytes, but its public constructor alone is not provenance authority; valid candidates can still be newly self-sealed by any caller. `build_candidate_set(sealed_request, sealed_response)` is the O02 derivation path from validated backend observations.

Decision requested:

A. Can O02 replace the raw release API with an O02-local composition that rebuilds candidate sets from sealed request/response inputs and derives lane states from existing O01-validated receipts/certificate, while requiring exact equality between each receipt's `result_ids` and the rebuilt candidate IDs? Or is the meaning of `SearchLaneReceipt.result_ids == RetrievalCandidate.candidate_id` a missing shared contract and therefore a SPEC_GAP?

B. If SPEC_GAP, state the exact smallest owner decision needed and whether the existing raw function must be renamed/documented as a non-authoritative assessment rather than a release authorization.

Return exactly:

- `DECISION: AUTHORIZED_LOCAL_REPAIR` or `DECISION: SPEC_GAP`
- `BINDING:` one exact required binding or `UNRESOLVED`
- `RAW_API:` one precise disposition
- `RATIONALE:` concise authority-based reasoning
