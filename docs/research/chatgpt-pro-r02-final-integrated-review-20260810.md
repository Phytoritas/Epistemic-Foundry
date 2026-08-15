## BLOCKER 1 — The attached source still lacks the claimed recursive snapshot

The current `_detached_json_object()` remains a direct `json.dumps(..., sort_keys=True) → json.loads(...)` round trip. It does not recursively inspect keys, preserve generic `Mapping`/`Sequence` semantics, detect projected-key collisions, or normalize primitive subclasses through base implementations. `_exact_fields()` is also performed only **before** detachment in both public paths.   

Consequently, a nested mapping such as:

```python
conditions = {1: "x"}
```

is converted to `{"1": "x"}` before semantic validation and can be sealed and accepted. This violates the required invariant that the values hashed, validated, and reasoned over are the same caller-supplied JSON values. The current `_mapping()` protects only mappings it explicitly visits later; JSON coercion occurs before it reaches nested scope maps. 

**Smallest correction:** install the previously reviewed primitive-first, memoized recursive snapshot; reject byte-like/non-JSON values and non-string keys; use base primitive implementations; detect duplicate projected keys and cycles; canonicalize only the completed plain snapshot; then repeat `_exact_fields()` after detachment in both `build_proof_trace()` and `validate_proof_trace()`.

## BLOCKER 2 — Scope validation and equality remain type-unsafe

`_validate_scope()` validates criteria arrays and converts `conditions`/`domain_extensions` only to mappings; it does not validate scalar-field types or the maps’ `scalar_or_list` values.  The canonical schema requires fields such as `domain` to be string-or-null and each condition value to be a scalar or scalar array.   

Additionally, condition comparison uses ordinary Python `!=`. Thus a premise condition `{"flag": True}` and conclusion condition `{"flag": 1}` are treated as equal, although boolean and number are distinct schema-valid JSON types. The same alias exists inside arrays. 

**Smallest correction:** fully validate the existing `ScopeVector` value types locally, including finite scalar/list members, and compare condition values with JSON-type-aware equality: booleans distinct from numbers, numeric values compared numerically, strings/null exact, and arrays compared elementwise.
