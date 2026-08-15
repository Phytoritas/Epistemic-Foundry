# Decision

Do **not** implement a fourth lane as the first correction.

The immediate, smallest genuine capability is to make the existing chain issue a sealed, replayable **`BLOCKED` completeness certificate** when a class-floor lane has no backend. The current `WORK_CLASS_LANE_RULE_VIOLATED` refusal is exposing an upstream receipt-semantics defect: a required selected lane is being represented as `UNSEARCHED`.

The system is also not one lane short of E1:

| E1 class floor | Currently served |
| -------------- | ---------------- |
| `lexical`      | yes              |
| `semantic`     | no               |
| `citation`     | yes              |
| `temporal`     | no               |

`entity_variable` is useful, but it cannot substitute for either missing E1 lane. Adding `temporal` would leave `semantic` missing and therefore would not make E1 `PASS`.

The approved sequence is therefore:

1. Repair selected-lane failure representation.
2. Reach a truthful `BLOCKED` certificate.
3. Optionally implement a bounded temporal lane after verifying its existing backend contract.
4. Leave semantic retrieval blocked under the no-embedding constraint.
5. Leave MCP, class floors, `PACKAGE_MANIFEST.json`, and the 179 unrelated working files unchanged.

---

## 1. E1 is the correct minimum graded target, but it requires all four floor lanes

E1 is the right first graded class for a purpose-built direct fact/source lookup probe. It must not be used to relabel an intrinsically E3 task merely to obtain a lower floor.

For a legitimate E1 request, the required set is exactly:

```text
lexical
semantic
citation
temporal
```

Those lanes are class-floor selections, not recommendations. Optional lanes may add protection but cannot replace a floor lane. Therefore there is no legitimate way for E1 to complete with only lexical, citation, and entity-variable retrieval.

Changing the E1 floor to allow fewer lanes would be:

> **SPEC_GAP — E1 work-class floor amendment**

That would alter a shared canonical contract and is not justified by the current implementation limitation. Do not weaken the floor to match the backend.

### Which lane comes next?

After the blocked-certificate repair, **temporal** is the narrower implementation candidate. It can potentially use existing indexed metadata without an embedding model. But its value is incremental:

```text
Current missing E1 lanes:
    semantic, temporal

After temporal:
    semantic
```

The result would still be `BLOCKED`, not `PASS`.

A defensible local temporal implementation would require:

* authoritative publication, revision, correction, retraction, or supersession dates;
* a versioned date/correction filter sealed before execution;
* snapshot, index, backend, adapter, query, and cutoff bindings;
* deterministic ranking and stable ID tie-breaking;
* no use of filesystem modification time as document chronology;
* no invented date for undated documents;
* `SEARCHED_NONE` only after the declared indexed temporal scope was actually exhausted.

There is one contract check before that implementation. The canonical workflow currently describes the temporal lane with `approved_external_search` capability and as covering updates, corrections, retractions, and precedence. A SQLite-only corpus search is not automatically equivalent to that external-update scope.

If the current contract does not already admit a corpus-local temporal backend, treating local date filtering as the complete canonical temporal lane would be:

> **SPEC_GAP — temporal-lane backend and coverage semantics amendment**

Do not silently reinterpret the lane. A local temporal backend may be a genuine corpus-scoped capability, but it must not imply that corrections or retractions outside the pinned corpus were searched.

### Semantic remains blocked

Do not relabel any of the following as `semantic` merely to satisfy E1:

* stemming or fuzzy lexical matching;
* synonym expansion;
* BM25 with different weights;
* entity-variable matching;
* citation-neighbour expansion;
* graph traversal without the semantic backend required by the contract.

The canonical workflow identifies conceptual similarity and `vector_search` for that lane. Under the explicit prohibition on adding an embedding model or network dependency, the honest state is `BLOCKED/backend_unavailable`.

---

## 2. The first honest certificate state is `BLOCKED`, not `PARTIAL`

The receipt vocabulary already distinguishes the relevant situations:

| Situation                                                                 | Correct lane receipt                      |
| ------------------------------------------------------------------------- | ----------------------------------------- |
| Lane was not selected by the plan                                         | `UNSEARCHED` sentinel                     |
| Selected lane has no usable backend                                       | `BLOCKED` execution receipt               |
| Selected lane started but stopped because of budget, time, or manual stop | `PARTIAL` execution receipt               |
| Selected lane completed and found no candidates                           | `SEARCHED_NONE` execution receipt         |
| Selected lane completed and found candidates                              | `SEARCHED_WITH_RESULTS` execution receipt |

Your current unsupported-lane behavior conflates the first two rows.

For E1, `semantic` and `temporal` are selected with `CLASS_FLOOR`. Consequently, neither may be represented by an `UNSEARCHED` sentinel carrying `NOT_REQUIRED_FOR_CLASS` or `NOT_APPLICABLE`. The certificate builder is correct to reject that plan/receipt contradiction.

The unsupported selected lanes should instead emit approximately this semantic state:

```yaml
receipt_kind: EXECUTION
sentinel_reason: null
search_state: BLOCKED
stop_reason: backend_unavailable
result_ids: null
result_count: null
excluded_count: null
recall_proxy: null
errors:
  - required lane backend is unavailable
```

All normal plan, query, snapshot, index, backend, adapter, and receipt-hash bindings still have to be present where required by the existing receipt contract.

After that correction, the expected chain is:

```text
PLAN_OK
    work_class=E1
    required_lanes=[lexical, semantic, citation, temporal]

LANES_OK
    receipts=11
    blocked_lanes=[semantic, temporal]

CERT_OK
    completion_state=BLOCKED
```

After a valid temporal implementation:

```text
CERT_OK
    completion_state=BLOCKED
    blocked_lanes=[semantic]
```

### Why `PARTIAL` is not appropriate here

`PARTIAL` describes an actually executed search that stopped because of:

```text
budget_exhausted
time_exhausted
manual_stop
```

A backend that does not exist did not execute partially. Its condition is:

```text
backend_unavailable → BLOCKED
```

The workflow’s node-level `failure_policy: mark_partial` does not authorize rewriting a lane’s business receipt from `BLOCKED` to `PARTIAL`. That policy controls workflow continuation or degradation; the receipt must still record the actual lane condition.

The certificate precedence is also deliberate:

```text
FAIL
→ BLOCKED
→ PARTIAL
→ PASS
```

Thus one blocked required lane makes the overall certificate `BLOCKED`, even when another lane is genuinely partial.

### What currently prevents `PARTIAL`?

Two intended constraints:

1. E1 floor lanes cannot be unselected.
2. Backend absence cannot masquerade as partial execution.

Those are not defects. The defect is that the execution layer currently emits an unselected-lane sentinel for a selected-but-unavailable lane.

If a valid set of `BLOCKED` execution receipts still causes `build_search_completeness_certificate` to throw rather than issue a `BLOCKED` certificate, that would be a separate O06 implementation defect. The workflow explicitly includes `BLOCKED` as a terminal certificate state.

The `absence_claim_ceiling` must remain a deterministic result of executed scope. A blocked lane is ignorance and contributes no absence or novelty support. Do not manually choose a more favourable ceiling merely because lexical or citation retrieval succeeded.

---

## 3. Do not surface this increment through MCP

The current MCP contract should remain unchanged.

`foundry.search.plan` is a planning-only `DURABLE_PLAN_ARTIFACT` tool. It must:

* compile a domain-owned plan;
* validate the artifact against the exact schema bound in the tool catalog;
* persist it in the append-only plan store;
* produce exactly one durable artifact receipt;
* perform no retrieval execution or certificate reconciliation.

The frozen T01 surface deliberately excludes `foundry.search.execute`. Therefore neither lane execution nor completeness-certificate construction belongs in the current MCP increment.

### `ERP-...` versus canonical `QueryPlan`

Treat them as **different contracts unless exact equivalence is demonstrated**.

An `ERP-` identifier does not establish that the object is a canonical `QueryPlan`. They are the same artifact only when all of the following hold:

1. The complete ERP payload validates directly against `query-plan.schema.json`.
2. It uses the same canonical lane order and class-floor rules.
3. Its hash is computed from the same canonical JSON representation.
4. Its identity and revision semantics match the canonical QueryPlan contract.
5. The MCP plan compiler would persist that exact artifact, rather than an adapter projection of it.
6. Idempotency replay and conflict semantics are identical.
7. No ERP-only fields are added outside the schema; the QueryPlan schema is closed with `additionalProperties: false`.

An ERP wrapper that contains or references a QueryPlan is still a separate artifact.

Making the existing MCP tool accept a different ERP shape would be:

> **SPEC_GAP — ERP/QueryPlan canonical contract alignment**

Adding a separate MCP tool or altering the frozen thirteen-tool catalog would be:

> **SPEC_GAP — MCP tool-catalog amendment**

Neither is needed to repair certificate reachability.

---

## 4. A new generic lane implementation belongs to O02, but the live path is unowned

The development manifest assigns O02 the retrieval-lane implementation responsibility, but its declared path is:

```yaml
python/epistemic_foundry/retrieval/lanes/**
```

The live implementation is:

```text
src/epistemic_foundry/retrieval/lanes.py
```

Those paths do not overlap. This is:

> **SPEC_GAP — O02 retrieval-lane live-path ownership mismatch**

The smallest ownership amendment is to add the exact live file to O02:

```yaml
- id: O02
  write_scope:
    - python/epistemic_foundry/retrieval/lanes/**
    - src/epistemic_foundry/retrieval/lanes.py
    # existing exact scopes remain unchanged
```

Do not grant:

```yaml
- src/epistemic_foundry/retrieval/**
```

That would overlap O05, O06, completeness, planning, and other retrieval owners unnecessarily.

Do not remove the existing `python/...` scope unless its retirement is independently established. The operator or existing canonical manifest authority must approve the amendment; O02 cannot grant itself new authority.

The ownership split should remain:

| Concern                                            | Owner |
| -------------------------------------------------- | ----- |
| Generic lane execution and lane receipt production | O02   |
| Current ERP-plan implementation under `v4_o05/`    | O05   |
| Current completeness integration under `v4_o06/`   | O06   |
| MCP planning transport and tool catalog            | T01   |

O05 and O06 already have exact `src/.../v4_o05/**` and `src/.../v4_o06/**` scopes, so the observed ownership gap is specifically the generic `lanes.py` path.

---

## 5. This is worth doing now, but the target is state fidelity rather than toy-corpus `PASS`

A two-document corpus is sufficient to verify:

* class-floor selection;
* selected versus unselected lane handling;
* eleven-lane reconciliation;
* receipt and certificate hashing;
* deterministic replay;
* `BLOCKED`, `PARTIAL`, and `PASS` precedence;
* E0’s no-search rule;
* absence-ceiling derivation from executed scope.

It is not sufficient to establish:

* meaningful retrieval recall;
* representative counterevidence coverage;
* broad absence or novelty;
* corpus adequacy;
* the fifty-document release gate;
* release maturity.

The fifty-document requirement is a release-level evidence threshold, not a reason to leave the certificate state machine internally inconsistent. A scope-bounded certificate can be mechanically verified on a small corpus without claiming that the corpus is scientifically sufficient.

Therefore the meaningful near-term result is:

```text
A valid graded QueryPlan
+ eleven schema-valid receipts
+ truthful required-lane BLOCKED states
+ one deterministic BLOCKED certificate
```

Forcing a toy-corpus `PASS` by weakening class floors or relabelling search methods would not be meaningful progress.

The 56 `PACKAGE_MANIFEST.json` hash differences remain a separate release-integrity issue. This increment must not:

* regenerate the trusted baseline around the working tree;
* commit the user’s 179 files;
* treat those files as explained;
* suppress their drift signal.

---

# Approved minimum change

1. Resolve **SPEC_GAP — O02 retrieval-lane live-path ownership mismatch** by adding only `src/epistemic_foundry/retrieval/lanes.py` to O02.
2. Keep the E1 floor unchanged at lexical, semantic, citation, and temporal.
3. Change unsupported **selected** lanes from `UNSEARCHED` sentinels to `BLOCKED/backend_unavailable` execution receipts.
4. Keep genuinely unselected lanes as `UNSEARCHED` sentinels.
5. Require O06 to emit a sealed `BLOCKED` certificate from valid blocked receipts rather than throwing.
6. Do not implement or imitate semantic retrieval.
7. Do not alter MCP.
8. Do not touch `PACKAGE_MANIFEST.json` or the unrelated working files.
9. Consider temporal only after confirming that a corpus-local backend satisfies the current lane contract; otherwise record the conditional temporal-backend **SPEC_GAP**.

## Explicit verification requested for this increment

Run only these bounded checks:

1. An E1 plan with unavailable semantic and temporal backends yields eleven receipts and a `BLOCKED` certificate, not `WORK_CLASS_LANE_RULE_VIOLATED`.
2. Replacing temporal’s blocked receipt with a genuine completed temporal receipt leaves the certificate `BLOCKED` solely because semantic remains unavailable.
3. An optional unselected lane still receives exactly one `UNSEARCHED` sentinel and performs no backend call.
4. A selected, executable lane stopped by a simulated time or budget limit produces `PARTIAL`; with no failed or blocked lanes, the certificate becomes `PARTIAL`.
5. E0 with any searched lane continues to fail validation.
6. Replaying identical plan, receipts, and snapshot produces an identical certificate hash.

No implementation or test execution is claimed here.
