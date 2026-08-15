# Decision

**Recording the limitation is necessary, but it is not sufficient.** The finding invalidates `O02-0002` as evidence of **per-lane retrieval capability** and requires a new append-only O02 corrective attempt.

The old attempt must remain immutable: it truthfully records that the old fixture produced the asserted scores. It is not fraudulent. What no longer survives is the interpretation that those scores demonstrated eleven distinct retrieval capabilities. The repository records `O02` attempt 2 as `PASS`, while its rules require previous attempts to be preserved rather than rewritten.  

The correct current disposition is:

```text
O02-0002:
  historical execution result: PASS
  demonstrated:
    - metric calculation
    - threshold enforcement
    - per-lane aggregation
    - determinism on the old fixture
  did_not_demonstrate:
    - lane discrimination
    - adversarial-lane retrieval capability
    - resistance to lexical channel substitution
  current evidentiary authority for per-lane capability: superseded

next O02 attempt:
  retrieval_benchmark: FAIL
  package attempt: FAIL
  reason: benchmark does not reject lexical channel substitution
```

This is **`FAIL`, not `SPEC_GAP`**. The intended meaning is already sufficiently clear:

* O02 is explicitly “Lexical, semantic, citation and relation retrieval.”
* Candidate provenance and no silent cross-channel fallback are O02 exit criteria.
* `retrieval_benchmark` is a required check.
* Counterevidence, null, boundary, and method are constitutionally separate mandatory lanes when applicable.
* The workflow gives those lanes different query-family and execution requirements; for example, counterevidence requires both forward and reverse families, while null accepts only its null family.  

There is therefore no missing product meaning to resolve. A required check has failed construct validity under an already-established contract.

`BLOCKED` remains the correct **lane execution state** for a selected lane whose backend is unavailable. It does not rescue the O02 package-level performance claim. Under the current all-lane benchmark requirement, eight honest `BLOCKED` results mean that the required performance check is not passed.

## A second defect in the current fixture

The vocabulary overlap is not the only problem.

The corpus has 12 documents and the metric is Recall@20. With one relevant document per query:

```text
corpus size = 12
k = 20
```

A backend that returns every corpus document receives:

```text
Recall@20 = 1.0
```

for every query. Recall@20 is therefore structurally incapable of discriminating retrieval quality on this corpus.

For one binary relevant document, nDCG@20 is:

```text
rank 1: 1.0000
rank 2: 0.6309
rank 3: 0.5000
```

Thus the `nDCG@20 ≥ 0.85` threshold effectively means “the single relevant document must rank first.” That could still be useful, but the unique answer-key terms make first place largely a lexical lookup.

Your boundary example illustrates the distinction:

```text
ranking: DOC-ENTITY, DOC-BOUND
must-find: PASS
Recall@20: 1.0
nDCG@20: 0.6309
```

So the four-lane run already proves that the **critical must-find gate** does not establish critical-lane capability. It does not yet prove that lexical retrieval would satisfy all eleven nDCG thresholds. The next check should run that counterfactual explicitly rather than infer it from overlap alone.

# The single bounded next step

## Open `O02-0003` as a lexical-substitution corrective attempt

**Owner:** O02
**Shared-contract change:** none
**Fixture replacement:** none in this step
**Backend implementation:** none
**Expected attempt result:** `FAIL`

Touch only:

```text
tests/retrieval/test_o02_retrieval_benchmark.py

artifacts/work_packages/O02/attempts/0003/report.json
artifacts/work_packages/O02/attempts/0003/commands.jsonl
artifacts/work_packages/O02/attempts/0003/review.md
```

plus any machine-readable result, changed-file inventory, and hash inventory already required by the established O02 attempt layout. All of those paths are within O02’s declared scope, and O02 requires independent review. 

### Replace the third added check

Keep your first two checks:

1. explicit lane, target, and distractor declarations;
2. canonical `query_family`–lane compatibility.

They verify fixture integrity and plan compatibility.

Do **not** retain this as a passing invariant:

```text
every query currently has 100% overlap
```

That assertion makes the defective property part of the green suite. A later, genuinely improved fixture would fail precisely because it improved. Record the overlap table in the new report, but replace the passing assertion with an executable channel-substitution negative control.

A suitable test boundary is:

```text
test_retrieval_benchmark_rejects_lexical_channel_substitution
```

It should do the following:

1. Build the actual SQLite FTS5 index from the current O02 corpus.
2. Execute the real lexical backend for all eleven fixture queries.
3. Preserve the actual query hash, index snapshot, backend identity, adapter revision, ranking, and candidate provenance.
4. Present those rankings to the same benchmark gate under the eleven declared lane cases.
5. Require the gate to reject any non-lexical lane whose candidates have only lexical execution provenance.
6. Record the resulting Recall@20, nDCG@20, and critical must-find results as diagnostic evidence.
7. Exit nonzero when the current benchmark grants semantic, mechanism, counterevidence, null, boundary, method, temporal, or novelty credit solely from lexical results.

The local finding may be named in O02 evidence, without adding a shared error-code contract:

```text
O02_BENCHMARK_CHANNEL_SUBSTITUTION_NOT_REJECTED
```

The important predicate is not merely:

```text
semantic query happened to be answerable lexically
```

Natural queries can often be answerable through more than one channel. The failure is:

```text
lexical execution provenance
    +
non-lexical lane label
    →
non-lexical lane performance credit
```

A benchmark may report that lexical retrieval happened to find a semantic target. It may not use that result to claim that the semantic lane was implemented or evaluated.

## Why the corrected attempt should intentionally end in `FAIL`

The successful outcome of this step is an accurate failing gate, not another green test suite.

The repository’s execution rules say that a clear contract plus a failed implementation or acceptance check is `FAIL`; `SPEC_GAP` is reserved for absent meaning or authority. They also require append-only evidence and prohibit synthetic or plausible-looking evidence from substituting for missing capability. 

Therefore:

```text
fixture integrity checks: PASS
query-family binding check: PASS
metric implementation checks: PASS
lexical-substitution rejection: FAIL
retrieval_benchmark: FAIL
O02-0003 overall: FAIL
```

The unrelated O02 integrity, replay, and policy checks may continue to pass. A package-level `FAIL` does not require pretending that every component is broken.

# What a genuinely discriminating fixture requires

A corrected fixture does **not** need to make unavailable lanes pass. It needs to make their absence observable.

At minimum, it needs these properties:

### 1. The corpus must be larger than the cutoff

For Recall@20, the eligible corpus must contain more than 20 documents. In practice it should contain enough hard negatives that returning a broad vocabulary-matched set does not almost automatically recover the target.

One relevant document among 21 is still a weak test: a random top-20 result has a 95.2% probability of including it. A materially larger pool or multiple relevant judgments is needed.

### 2. Queries must not carry unique document keys

A non-lexical case should not contain:

* the lane name;
* a unique identifier copied from the target;
* a phrase occurring in only the relevant document;
* an artificial vocabulary bundle written specifically for that lane.

Some shared vocabulary is normal. The requirement is not zero overlap. The requirement is that exact matching alone cannot distinguish the relevant document from credible hard negatives.

### 3. Each lane needs a lane-specific contrast

| Lane family      | Discriminating signal                                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Semantic         | Relevant target is a paraphrase; a lexical decoy shares more surface terms but expresses a different concept.                                                 |
| Citation         | Relevance depends on a citation, correction, replication, or lineage edge rather than prose overlap.                                                          |
| Entity-variable  | Documents share entity names, but only the target has the correct entity–variable–unit relation.                                                              |
| Mechanism        | Target contains the required intermediate causal path; a hard negative reports association without that path.                                                 |
| Counterevidence  | Support and counterevidence share topic vocabulary; polarity, direction, reverse causation, or alternative explanation distinguishes them.                    |
| Null             | Target reports equivalence, failed replication, or no detectable effect without relying on the token `null`; a positive-effect document is the lexical decoy. |
| Boundary         | Target limits the effect by dose, subgroup, stage, or threshold; the hard negative makes the unqualified general claim.                                       |
| Method           | Target establishes an instrument, construct, preregistration, or compatibility limitation; the decoy shares method vocabulary but is method-compatible.       |
| Temporal         | Relevance depends on publication/version date, correction, retraction, or precedence metadata.                                                                |
| External novelty | Relevance depends on membership in a separately frozen local prior-art corpus and an explicit corpus boundary, not a live network search.                     |

### 4. Metamorphic controls must be present

For each relation-sensitive family, make a paired case in which most text is held constant while the claimed signal changes:

```text
A causes B       ↔ B causes A
effect present   ↔ equivalence / failed replication
all populations  ↔ only subgroup X
method compatible ↔ method incompatible
original article ↔ corrected or retracted version
```

A system insensitive to the changed relation must fail.

### 5. Lane provenance must be part of evaluation

The score must be tied to:

```text
declared lane
query family
backend identity
adapter revision
index or graph snapshot
receipt
candidate origins
```

A correct document returned by the wrong channel can be useful retrieval output, but it is not evidence that the declared lane ran.

### 6. Unsupported lanes remain unscored

For a selected but unsupported lane:

```text
execution_state: BLOCKED
Recall@20: not assessed
nDCG@20: not assessed
```

Do not convert `BLOCKED` to zero, because zero means the backend executed and failed to retrieve. Do not convert it to one, because that fabricates performance.

A benchmark with eight `BLOCKED` lanes is still valuable. It becomes an honest capability census and prevents later implementations from gaming the old fixture. It simply does not satisfy the present O02 all-lane performance requirement.

Changing the required-check semantics so that “the benchmark truthfully reports eight blocked lanes” itself qualifies as an O02 `PASS` would be a shared acceptance change, not an O02-local edit. It would affect at least the acceptance authority and development-manifest projection. Until that change has an authorized owner and exact postimage, it is `SPEC_GAP`; do not make it locally.

# The other O02 checks

The **risk class** applies to `relation_direction_test` and `non_vector_release_guard_test`, but their defect is not yet established.

For `relation_direction_test`, the decisive audit is a same-vocabulary reversal:

```text
original: A increases B
mutant:   B increases A
```

or:

```text
original edge: source → target
mutant edge:   target → source
```

The expected result must change. A fixture where the correct direction is also encoded by unique entity names or a direction label is self-fulfilling.

For `non_vector_release_guard_test`, the decisive mutation is provenance rather than wording:

```text
same candidate payload and ranks
case 1: real non-vector origin and resolving receipt
case 2: vector-only origin
case 3: vector result relabelled as lexical without matching receipt
```

Only case 1 may receive an unrestricted release state. A test that trusts an `origin_lane: lexical` string without reconciling its receipt can be gamed in the same way as the benchmark.

Those audits should not be folded into `O02-0003`; the bounded step is the benchmark substitution control alone.

# Effect on the pending A01 request

**No change.**

The A01 request freezes:

* Python source-root authority;
* executor-binding authority;
* ownership of the shared runtime boundary.

This O02 finding concerns the validity of one package’s evidence, and O02 already owns the relevant tests, fixtures, workflow, and evidence directory. It is structurally similar to the executor finding—an artifact exists and a superficial check passes without demonstrating the named capability—but it introduces no new source-root or executor-contract decision.

Adding it to the pending A01 request would broaden that decision without resolving anything O02 cannot already record locally.

# Observable proof

The step worked when all of the following are true:

1. The actual lexical FTS5 backend executes all eleven current queries.
2. Its index, query, ranking, backend, adapter, and candidate provenance are recorded.
3. The old benchmark is shown to grant at least one non-lexical capability credit from lexical-only execution, or to lack the information needed to reject that credit.
4. The targeted required check exits nonzero with the local substitution finding.
5. `O02-0003/report.json` records `retrieval_benchmark: FAIL` and overall `FAIL`.
6. `O02-0002` and its fixture hashes remain byte-for-byte unchanged.
7. An independent reviewer confirms that the result is a construct-validity failure, not a failed attempt to implement eight fake backends.
8. No unavailable lane is relabelled `SEARCHED_WITH_RESULTS`, and no synthetic lane receipt is generated.

It only appeared to work when:

* the suite stays green because “100% overlap” is asserted as expected behavior;
* the limitation appears only in prose while O02 remains currently qualified by the old PASS;
* the test checks lane labels or `query_family` values but never executes the lexical counterfactual;
* precomputed `backend-responses.json` is treated as proof that distinct backends ran;
* lexical candidates are relabelled as semantic, counterevidence, null, or method candidates;
* blocked lanes are assigned artificial zero or perfect metrics;
* thresholds are lowered or critical cases removed;
* `O02-0002` is edited in place.

The bounded correction is therefore **one O02 append-only FAIL attempt driven by an actual lexical-channel substitution negative control**. The discriminating corpus comes later; the present obligation is first to stop the existing benchmark from carrying a capability claim it does not support.
