# Search completeness and absence-language contract

This document is the O01 contract for immutable `QueryPlan`,
`SearchLaneReceipt`, and `SearchCompletenessCertificate` artifacts. Retrieval
execution is downstream; O01 determines what must run, how every lane is
accounted for, and what conclusions the recorded scope can support.

## Canonical lane vocabulary and order

The closed base vocabulary is:

1. `lexical`
2. `semantic`
3. `citation`
4. `entity_variable`
5. `mechanism`
6. `counterevidence`
7. `null`
8. `boundary`
9. `method`
10. `temporal`
11. `external_novelty`

`support` is an evidence role, not a retrieval lane. `counter` and `novelty`
are legacy migration inputs only; canonical writes reject them. `custom`
cannot replace or waive a canonical lane. A new lane requires a separately
registered contract, classifier/policy version change, and HumanDecision.

## Exact work-class floor

| Work class | Non-waivable selected lanes |
| --- | --- |
| `E0` | none; retrieval is explicitly `NOT_REQUIRED` |
| `E1` | `lexical`, `semantic`, `citation`, `temporal` |
| `E2` | E1 plus `entity_variable`, `counterevidence`, `null`, `boundary`, `method` |
| `E3` | E2 plus `mechanism` |
| `E4` | all ten non-novelty lanes |
| `E5` | all eleven lanes, including `external_novelty` |

The compiler takes the maximum floor implied by the immutable
`EpistemicWorkClassification`. A PolicyBundle may select additional canonical
lanes, but cannot remove a class-floor lane or reduce any protection. Each of
the eleven `lane_decisions` is one of:

- `SELECTED` with reason `CLASS_FLOOR` or `POLICY_SELECTED`;
- `NOT_REQUIRED_FOR_CLASS`; or
- `NOT_APPLICABLE`, backed by typed deterministic evidence.

E0 has empty query arrays, a zero execution budget, no selected lane, and no
backend call. It still produces an explicit no-retrieval plan and eleven
sentinels so that absence of work is not mistaken for missing evidence.

## Immutable plan binding

Every plan binds the request ID/revision/input hash, classification
ID/revision/hash, work class, classifier version, PolicyBundle hash, Insight
revision, scope, queries, budget, stop rules, and all lane decisions. The
`plan_hash` is SHA-256 over deterministic canonical JSON excluding only the
`plan_hash` field itself. A changed request, classification, policy, scope,
query, or lane decision requires a new plan revision and hash.

## Search states and receipt kinds

`UNSEARCHED`, `SEARCHED_NONE`, `SEARCHED_WITH_RESULTS`, `PARTIAL`, `BLOCKED`,
and `FAILED` are distinct.

- An unselected lane emits exactly one `SENTINEL` receipt in `UNSEARCHED`.
  Query, scope, corpus/index, result, cutoff, recall, and timestamp fields are
  null. Its reason exactly matches the plan disposition.
- A selected lane emits one or more `EXECUTION` receipts and cannot emit an
  `UNSEARCHED` sentinel.
- `SEARCHED_NONE` means a real, hash-bound query completed successfully with
  zero results. It never means that evidence does not exist.
- `SEARCHED_WITH_RESULTS` is a successful execution with a non-empty result
  set and exact count reconciliation.
- Budget exhaustion, time exhaustion, or a manual bounded stop is `PARTIAL`.
- Missing policy authority, credential, or backend prerequisite is `BLOCKED`.
- Provider failure, integrity failure, or invalid response is `FAILED`.

The query hash binds the exact persisted UTF-8 query text. Result count must
equal the number of result IDs. Sentinel and execution receipts cannot coexist
for the same unselected lane.

## All-eleven reconciliation

Every run reconciles all eleven lanes in canonical order. Selected lanes need
execution receipts; each unselected lane needs exactly one sentinel. Missing
or duplicate receipts, plan/hash mismatches, count mismatches, or sentinel /
execution conflicts are integrity failures and make the run `FAIL`.

For multiple receipts in one selected lane, the deterministic lane and run
precedence is:

```text
FAILED > BLOCKED > PARTIAL > SEARCHED_WITH_RESULTS > SEARCHED_NONE
```

The resulting run state is:

- `NOT_REQUIRED` for E0;
- `FAIL` if any selected lane failed or reconciliation integrity failed;
- otherwise `BLOCKED` if any selected lane is blocked;
- otherwise `PARTIAL` if any selected lane is partial; or
- `PASS` when every selected lane completed with or without results.

No majority, average score, or successful lane can mask a stronger failure.

## Claim ceilings

Absence and novelty ceilings derive only from reconciled executed scope.
Sentinel scope never contributes to a claim. The certificate records searched
and unsearched scope IDs, per-lane state, failures, and the exact plan hash.

Admissible language is bounded and conditional:

```text
“No matching evidence was retrieved by [executed lanes] from [sources]
under [scope/query/version/date/cutoff].”
```

The following are not admissible from O01 receipts:

```text
“No evidence exists.”
“This hypothesis is globally novel.”
“The field has never tested this.”
```

`external_novelty=SEARCHED_NONE` permits only a search-conditional novelty
statement. A partial external search remains corpus-novel only. Prior art
found in that lane is recorded as `PRIOR_ART_FOUND`. An unsearched, blocked,
or failed external lane is `NOT_ASSESSED`.

## Replay and mutation boundary

The deterministic compiler, receipt sealer, and certificate reconciler do not
mutate their inputs. Identical canonical inputs reproduce identical hashes.
Retry returns the same logical artifacts; it does not synthesize missing
receipts, infer a lane from free text, or reinterpret current backend state.
