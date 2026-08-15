**BLOCKER — primitive/container hybrid subclasses can still launder their value.**

Because `_json_snapshot()` tests `Mapping` before the primitive branches, an object such as `class Forged(str, Mapping)` is processed through caller-controlled `items()` instead of through `str.__str__()`. Python’s historical `json.dumps()` treats that object as its underlying string, but the snapshot can transform it into an arbitrary mapping. The same path exists for `int`/`float` subclasses—or even non-JSON `bytes` subclasses—that also satisfy `Mapping` or `Sequence`. The four stated regressions do not cover this cross-category case. That conflicts with R02’s fail-closed input discipline. 

Smallest correction: classify primitives before containers, with `bool` before `int`, and reject byte-like values before either container branch:

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
    ...
if isinstance(value, Sequence):
    ...
```

The memoization, cycle detection, single traversal, and final canonicalization can remain unchanged.


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-2ec51b-b750cc\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
