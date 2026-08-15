# R03 conflict/status consistency review

Act as an independent, read-only contract reviewer for one bounded Epistemic
Foundry R03 change. Return only material blockers, or `NO_BLOCKER` with one
short rationale.

Authority and current behavior:

- R03 owns only `python/epistemic_foundry/reasoning/aporia/**`.
- Its exit criteria require competing explanations to survive and condition
  differences to be classified.
- `build_aporia_record` deterministically emits `OPEN` when classified
  conflicts remain, otherwise `NO_CONFLICT`.
- `validate_aporia_record` already rejects noncanonical status strings,
  unclassified conflicts, duplicate/unsorted conflicts, explanation
  monoculture, unexplained conflicts, adjudication by R03, and hash mismatch.

Observed defect:

The public validator did not bind status to the actual conflict set. A caller
could change a valid conflict-bearing record to `status="NO_CONFLICT"`, or an
empty record to `status="OPEN"`, recompute `aporia_hash`, and pass validation.
That can hide a classified disagreement from downstream consumers.

Bounded repair:

```python
expected_status = (
    AporiaStatus.OPEN.value if conflict_ids else AporiaStatus.NO_CONFLICT.value
)
if value["status"] != expected_status:
    _fail(
        "STATUS_MISMATCH",
        "aporia status must reflect whether classified conflicts remain",
        {"actual": value["status"], "expected": expected_status},
    )
```

This runs after conflict shape/type/order validation and before explanation
reconciliation and self-hash validation. Regression source covers both forged
directions after recomputing `aporia_hash`. No schema, manifest, workflow, or
other package changes.

Review whether this exact invariant follows existing R03 semantics and whether
the validation placement or new typed local error creates any material
correctness or compatibility blocker.
