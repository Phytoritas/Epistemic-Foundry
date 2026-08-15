# R02 scope and detachment delta review

Review only the current post-review R02 delta. Return `NO_BLOCKER` or concrete material blockers. Ignore style and do not ask to run tests.

Correction to your immediately preceding answer: its Blocker 1 described an older implementation. The current on-disk `_detached_json_object` was already a primitive-first recursive walker before that answer: it normalizes base bool/str/int/float values, rejects bytes/non-JSON values/non-string or duplicate projected keys/cycles, memoizes Mapping/Sequence containers, canonicalizes only the completed plain dict/list snapshot, and both public paths checked exact fields after detachment. There was no `json.dumps→json.loads` detachment in the reviewed disk state. Treat that earlier Blocker 1 as stale.

The new local correction now closes the remaining top-level projection edge too:

- `build_proof_trace(graph)` and `validate_proof_trace(payload)` pass the original object directly to `_detached_json_object` instead of first copying it through `_mapping`.
- Therefore a custom top-level `Mapping.items()` that yields the same JSON name twice is rejected before a dict can overwrite one occurrence.

The valid portion of your prior Blocker 2 is implemented against `schemas/scope-vector.schema.json`:

1. Every `SCOPE_SCALAR_FIELDS` value must be exact string or null.
2. Inclusion/exclusion criteria must be arrays of exact strings; schema-legal empty strings remain accepted.
3. `conditions` and `domain_extensions` values must be a JSON scalar (string, finite number, boolean, null) or a one-dimensional array of those scalars; nested objects/arrays and non-JSON members fail closed.
4. JSON-semantic equality makes booleans distinct from numbers, permits int/float numeric equality, compares strings/null by exact type/value, and compares arrays elementwise. Thus `True` differs from `1`, including inside arrays.
5. Existing intervention/exposure validation and bounded-range narrowing remain unchanged.

Regression source now covers duplicate top-level mapping items in both public paths, invalid scalar field types, nested non-scalar condition values, boolean-vs-number scalar/array conditions, and preservation of schema-legal empty criteria strings.

Check for any material mismatch with the ScopeVector schema or any remaining way the bytes hashed/sealed can differ from the detached values reasoned over. Do not repeat the stale round-trip claim; no shared-schema or manifest change is requested.
