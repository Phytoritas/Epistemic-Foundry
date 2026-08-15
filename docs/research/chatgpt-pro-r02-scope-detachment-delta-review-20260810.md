**BLOCKER — `seal_argument_graph()` still bypasses the new top-level duplicate-key boundary.**

It still calls `_mapping(payload, ...)` before hashing. A custom `Mapping.items()` that emits the same JSON field name twice is therefore collapsed by last-write-wins into a plain `dict`; `graph_hash` is then calculated over that collapsed value. Passing the returned graph to `build_proof_trace()` succeeds because the duplicate evidence has already disappeared before the newly hardened detached snapshot sees it. 

Smallest R02-owned correction:

```python
def seal_argument_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _detached_json_object(payload, "ArgumentGraph")
    _exact_fields(value, GRAPH_FIELDS, "ArgumentGraph")
    value["graph_hash"] = _hash_excluding(value, "graph_hash")
    return value
```

Add the same duplicate-top-level `Mapping.items()` regression through:

```text
seal_argument_graph(ambiguous_mapping)
```

and require `INPUT_INVALID`. The scope-type and JSON-semantic-equality delta otherwise introduces no material blocker.
