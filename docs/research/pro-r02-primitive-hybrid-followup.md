# R02 primitive/container hybrid follow-up

Re-review only the primitive/container hybrid blocker. `_json_snapshot()` now classifies values in this exact order before any container check:

```python
if value is None:
    return None
if isinstance(value, bool):
    return value
if isinstance(value, str):
    return str.__str__(value)
if isinstance(value, int):
    return int.__int__(value)
if isinstance(value, float):
    return float.__float__(value)
if isinstance(value, (bytes, bytearray)):
    _fail("CANONICALIZATION_FAILED", f"{label} contains a non-JSON value")
if isinstance(value, Mapping):
    # one-read memoized recursive mapping snapshot
    ...
if isinstance(value, Sequence):
    # one-read memoized recursive sequence snapshot
    ...
_fail("CANONICALIZATION_FAILED", f"{label} contains a non-JSON value")
```

The earlier base-method normalization remains for mapping keys and scalar subclasses. A new regression defines a `str + Mapping` hybrid whose underlying string is `not-a-mapping` but whose Mapping projection is a valid `conditions` object; the graph carries the hash of the valid mapping. `build_proof_trace()` must retain the underlying string and fail `GRAPH_HASH_MISMATCH` instead of selecting the forged Mapping interface. The prior string-key/value and integer/float subclass regressions remain.

Both public functions still install the single recursive detached snapshot before all hashes and semantic reads. Return `NO_BLOCKER` or only a material remaining blocker in this bounded R02 correction. Ignore style-only suggestions. Do not ask to run tests.
