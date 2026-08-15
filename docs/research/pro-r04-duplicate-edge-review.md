# R04 duplicate-edge causal assessment review

Act as an independent, read-only contract reviewer for one bounded Epistemic
Foundry R04 change. Return only material blockers, or `NO_BLOCKER` with one
short rationale.

Authority and behavior:

- R04 owns `python/epistemic_foundry/reasoning/causal/**`.
- Its exit criteria require confounders, colliders, and time order to be
  assessed while inference modes remain separate.
- Canonical MechanismGraph edges carry a non-empty `edge_id`; R04 already
  requires unique node IDs and validates each edge endpoint, relation, sign,
  lag, and graph hash.
- `assess_time_order` stores one state per `edge_id` in a mapping, then derives
  whether every causal edge establishes temporal order.

Observed defect:

`_validate_graph` did not require edge IDs to be unique. Two causal edges with
the same ID could enter `assess_time_order`; because the state mapping is keyed
by that ID, a later `P1D` edge could overwrite an earlier `unknown` edge and
make the time-order assessment pass, allowing a causal overclaim.

Bounded repair:

```python
edges = []
edge_ids: set[str] = set()
for ...:
    edge_id = _text(edge["edge_id"], "edge_id")
    if edge_id in edge_ids:
        _fail("DUPLICATE_EDGE", "edge ids must be unique", {"edge_id": edge_id})
    edge_ids.add(edge_id)
    # existing endpoint/relation/sign/lag validation follows
```

A regression constructs two `E-1` causal edges, first `lag="unknown"`, then
`lag="P1D"`, and requires `DUPLICATE_EDGE` before assessment. No schema,
manifest, workflow, or other package changed.

Review whether edge-ID uniqueness is a necessary R04-local graph invariant at
this placement and whether the repair introduces any material correctness or
compatibility blocker.
