# R02 recursive-snapshot text-only follow-up

The prior follow-up did not reach Send because its attachments timed out. Review this exact bounded correction from the code excerpts below. Decide only whether the previously reported nested-key/stateful-container blocker is closed or another material correctness/contract issue remains.

Both public functions first call `_mapping()`, enforce the exact top-level field set, and then immediately replace that shallow object with `_detached_json_object()`. Every later semantic read, graph/trace hash, status derivation, proof ID derivation, and final seal uses only that replacement.

```python
def _json_snapshot(value, label, memo, active):
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            _fail("CANONICALIZATION_FAILED", f"{label} contains a cycle")
        if identity in memo:
            return memo[identity]
        detached_mapping = {}
        memo[identity] = detached_mapping
        active.add(identity)
        try:
            for key, entry in value.items():
                if not isinstance(key, str):
                    _fail("INPUT_INVALID", f"{label} keys must be strings")
                plain_key = str(key)
                if plain_key in detached_mapping:
                    _fail("INPUT_INVALID", f"{label} keys must be unique")
                detached_mapping[plain_key] = _json_snapshot(
                    entry, f"{label}.{plain_key}", memo, active
                )
        finally:
            active.remove(identity)
        return detached_mapping
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        identity = id(value)
        if identity in active:
            _fail("CANONICALIZATION_FAILED", f"{label} contains a cycle")
        if identity in memo:
            return memo[identity]
        detached_sequence = []
        memo[identity] = detached_sequence
        active.add(identity)
        try:
            for index, entry in enumerate(value):
                detached_sequence.append(
                    _json_snapshot(entry, f"{label}[{index}]", memo, active)
                )
        finally:
            active.remove(identity)
        return detached_sequence
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    _fail("CANONICALIZATION_FAILED", f"{label} contains a non-JSON value")


def _detached_json_object(value, label):
    detached = _json_snapshot(value, label, {}, set())
    if type(detached) is not dict:
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    _canonical_json(detached)
    return detached
```

Call-site shape in both public functions:

```python
value = _mapping(input_value, label)
_exact_fields(value, EXPECTED_FIELDS, label)
value = _detached_json_object(value, label)
# all subsequent work uses only value
```

Regression coverage in source now includes:

- mutate the original graph nodes immediately after graph-hash computation; the built trace remains the pre-mutation detached snapshot;
- mutate the original trace ledger immediately after trace-hash computation; the sealed trace remains the pre-mutation detached snapshot;
- put integer keys in otherwise matching nested `scope.conditions` mappings, seal using historical JSON behavior, and require `build_proof_trace()` to reject with `INPUT_INVALID` instead of coercing those keys.

The broader R02 repair publishes `argument_graph_hash`, preserves historical builder `proof_trace_id` values by retaining the old `graph_hash` preimage key, derives status from broken edges/ledger, and preserves validation precedence `trace_hash -> status -> proof_trace_id`. No shared ProofTrace schema or external R02 consumer was found.

Return `NO_BLOCKER` or only material remaining blockers. Ignore style-only suggestions. Do not ask to run tests.
