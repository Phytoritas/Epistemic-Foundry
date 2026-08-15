# R02 scalar-snapshot follow-up

Re-review only the last blocker in the prior answer. The recursive container snapshot is unchanged, but primitive subclass normalization now bypasses caller overrides exactly as follows:

```python
if not isinstance(key, str):
    _fail("INPUT_INVALID", f"{label} keys must be strings")
plain_key = str.__str__(key)

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
```

Mapping/Sequence containers are still memoized, cycle checked, recursively copied once, and only the completed plain snapshot is canonicalized. Both public R02 paths install that snapshot before all hashes and semantic reads.

Regression source now uses malicious subclasses whose underlying values are invalid/different but whose overridden `__str__`, `__int__`, or `__float__` return valid projected values. It covers a scalar string, a nested mapping key, an integer confidence, and a float confidence. Each must retain its underlying primitive and therefore fail the pre-existing graph hash instead of being laundered into the hash-valid graph.

Return `NO_BLOCKER` or only a material remaining blocker in this bounded R02 correction. Ignore style-only suggestions. Do not ask to run tests.
