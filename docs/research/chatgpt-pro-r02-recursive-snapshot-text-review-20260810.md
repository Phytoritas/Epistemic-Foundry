**BLOCKER — scalar subclasses can still rewrite the detached semantic value.**

The prior nested-key and stateful-container blocker is otherwise closed: both public paths install the detached snapshot before any graph/trace hashing or semantic reads.  

However, these conversions invoke overridable methods:

```python
plain_key = str(key)
return str(value)
return int(value)
return float(value)
```

A `str` subclass whose underlying value is `"invalid"` can override `__str__()` to return `"premise"`; the same technique can transform a nested field name into an allowed one. Numeric subclasses can similarly override `__int__()` or `__float__()`. The rewritten snapshot is then internally hash-consistent, so this is semantic input laundering rather than a hash mismatch.

Smallest compatibility-preserving correction:

```python
plain_key = str.__str__(key)

if isinstance(value, str):
    return str.__str__(value)
if isinstance(value, int):       # after bool
    return int.__int__(value)
if isinstance(value, float):
    return float.__float__(value)
```

This captures the primitive’s underlying value as historical `json.dumps` would, while still returning exact plain built-in JSON scalars. Exact-type rejection is also safe but would unnecessarily reject previously serializable `str`/numeric subclasses such as typed enums.


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-5e2f83-008ca3\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
