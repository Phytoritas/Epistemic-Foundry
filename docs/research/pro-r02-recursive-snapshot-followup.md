# R02 recursive-snapshot follow-up

Re-review the attached current R02 sources after the nested-key blocker. Decide only whether the material blocker is closed or another material correctness/contract issue remains.

The correction no longer serializes caller-owned nested containers. `_json_snapshot()` recursively visits each caller-owned Mapping or non-text Sequence once, constructs plain dict/list values, and:

- rejects every non-string mapping key as `INPUT_INVALID` before JSON encoding can coerce it;
- rejects duplicate normalized string keys;
- normalizes supported scalar subclasses to plain JSON scalar values;
- rejects non-JSON leaves and cycles;
- memoizes container identities so aliased containers are read once rather than re-read through each alias.

Only the completed plain snapshot is passed to `_canonical_json()` to reject non-canonical JSON values such as non-finite floats. Both public paths then perform every hash, semantic, status, ID, and sealing operation against that snapshot. A new regression constructs otherwise matching scopes with integer `conditions` keys, seals the graph using the historical JSON behavior, and requires `build_proof_trace()` to reject it instead of laundering the keys to strings. The two caller-mutation snapshot regressions remain.

The graph-hash publication, historical proof-ID preimage compatibility, and `trace_hash -> status -> proof_trace_id` validation order are unchanged.

Return `NO_BLOCKER` or only material remaining blockers. Ignore style-only suggestions. Do not ask to run tests.
