# O02-0003 review

## Disposition

`FAIL`, by design. This attempt does not implement anything. It replaces a
benchmark assertion that could not fail with one that does, and records why.

## What was found

`retrieval_benchmark` is one of O02's two headline required checks. It asserts
per-lane Recall@20 >= 0.90 and nDCG@20 >= 0.85 across all eleven canonical
lanes. Those thresholds are genuinely enforced — the "does not average away a
failing lane" check is real, and so is the determinism check.

What the benchmark cannot do is tell eleven retrieval capabilities apart from
one. Executing every fixture query through the single shipped SQLite FTS5
index, and scoring the results against the benchmark's own labels and
thresholds, gives ten of the eleven lanes a perfect score on `LEXICAL`
provenance alone:

```text
Q-SEM      semantic          recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-CIT      citation          recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-ENTITY   entity_variable   recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-MECH     mechanism         recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-COUNTER  counterevidence   recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-NULL     null              recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-BOUND    boundary          recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-METHOD   method            recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-TEMP     temporal          recall=1.00 ndcg=1.00 channels=['LEXICAL']
Q-NOV      external_novelty  recall=1.00 ndcg=1.00 channels=['LEXICAL']
```

Feeding that ranking to the acceptance gate itself, `assert_benchmark_thresholds`
accepts it: fused Recall@20 = 1.00, critical must-find 4/4, every lane at
1.00/1.00. The gate, not just the raw numbers, admits a single-channel run as
an eleven-lane pass.

Two fixture properties contribute. Every query shares 100% of its terms with
its one labelled relevant document, including terms that occur in exactly one
corpus document — so each query carries a unique key to its own answer. And the
corpus holds 12 documents against a cutoff of 20, so Recall@20 reaches 1.0 for
any backend that returns the corpus, leaving the nDCG threshold to mean only
"rank the answer first".

But the deeper cause is not the fixture. `evaluate_retrieval_benchmark` takes:

```text
(rankings, queries, relevance, *, must_find_query_ids, k=20)
```

Document rankings, and nothing else. No candidate provenance, no retrieval
channel, no backend or adapter identity. The gate has no information with which
to reject a lane whose result came from a channel other than the one the lane
names. **No fixture, however discriminating, can fix that while the gate's
inputs stay provenance-free.**

## A second check that cannot fire

`assert_benchmark_thresholds` also refuses a report whose `live_network_calls`
or `live_llm_calls` are non-zero — the guarantee that the benchmark is local and
deterministic. But `evaluate_retrieval_benchmark` writes both as literal zeros
into the report it returns. Neither is an argument, and nothing observes the
run.

So the gate reads back a constant it supplied itself. Confirmed directly: the
check refuses only a hand-edited report; no genuine run can make it fire. A
benchmark that did call the network would report zero and pass.

This is not a claim that the current benchmark makes such calls. It is that the
check which says it does not is decorative.

## How widespread is this?

Worth asking, since two of this attempt's findings have the same shape: a check
that names a property without establishing it. An AST census over `src/**` and
`python/**` looked for the exact reporter/gate pair — a function writing a
literal into its own return value for a key it never otherwise touches, read
back by a sibling function to raise.

One match: the benchmark pair above. Eight apparent matches in
`python/epistemic_foundry/storage/postgres/store.py` were inspected and
rejected; those reporters query the database and raise on a bad observation
before returning, so their `ok` and `code` fields are earned.

A second census asked whether any canonical schema field that asserts a
property — verification, counting, independence, leakage, determinism,
reproducibility, attestation, audit — is only ever written as a constant. Of 35
such fields, none. Every one has at least one computed write somewhere.

A third pass covered `packages/**` for the same shape in JavaScript: object
fields named for verification, counting, independence, leakage, determinism, or
reproducibility, written as a constant and never assigned a computed value in
the same file. Zero. That pass was text triage rather than parsing, so it is
good for finding candidates and not authoritative on absence.

So the shape is not a habit in either tree. The benchmark's live-call counters
are an exception, not a symptom. None of the three censuses can detect a field
that is computed but only from caller-controlled input, or one whose
observation is real but wrong.

The eleven-lane contract exists so that one retrieval channel cannot stand in
for the rest. `non_vector_release_origins` and the PARTIAL ceiling encode that
against vector similarity. This fixture permits the same substitution from the
other side.

## Why this is FAIL rather than SPEC_GAP

No product meaning is missing. O02 is titled "Lexical, semantic, citation and
relation retrieval"; the workflow gives the adversarial lanes distinct query
families and execution requirements; "no silent cross-channel fallback" is an
exit criterion. A required check that fails construct validity under an
established contract is a failure, not an absent decision.

## What was not done

The fixture was not changed. O02-0002 hashes its bytes, and building a
discriminating corpus is separate work with its own requirements: a corpus
larger than the cutoff, queries without unique document keys, per-lane
contrastive hard negatives, metamorphic pairs for the relation-sensitive lanes,
and lane provenance bound into scoring. Unserved lanes would stay BLOCKED and
unscored — neither zero, which would claim the backend ran and missed, nor one,
which would fabricate performance.

No lane was relabelled, no threshold was lowered, and no critical case was
removed. O02-0001 and O02-0002 are unchanged. To be exact about receipts: the
lexical executions seal ordinary transient `EXECUTION` receipts for the lexical
lane, as any real lane run does. None is persisted, and none is offered as
evidence that an unserved lane ran.

The recorded evidence carries the substitution run's corpus snapshot hash,
index versions, backend and adapter identity, and the observed candidate
channels. It does not persist the full per-query ranking or per-candidate
hashes; a replayer rebuilds the index from the recorded fixture hashes instead.

## Open

## The sibling checks

Pro named two decisive audits for the other O02 required checks. One ran and
passed; the other could not run.

**`relation_direction_test` is sound.** The audit was a same-vocabulary
reversal: hold the tokens constant, flip only the argument order, and require
the answer to change. It does, in both directions. Renaming the entities leaves
the verdict unchanged, so the classifier is not keyed to fixture-specific
names. Removing the inverse-predicate mapping turns `INVERSE_PREDICATE` into
`UNRESOLVED` rather than inventing the inverse.

This fixture already has what the benchmark lacks. `SAME_DIRECTION` and
`REVERSE_DIRECTION` share identical tokens and differ only in argument order —
a contrastive pair, not an answer key.

**`non_vector_release_guard_test` could not be audited at first**, and
attempting it surfaced a third finding.

`seal_backend_request`, `seal_backend_response`,
`validate_sealed_backend_request`, `validate_backend_response`, and
`build_candidate_set` now all take a required keyword-only `query_plan`, binding
each backend call to the exact O01 QueryPlan. That looks like a genuine
tightening. But the O02 tests that exercise them were not carried with it: 37
call sites across `test_o02_integrity_and_fallback.py` and
`test_o02_non_vector_guard.py` omit the argument.

Both files raise `TypeError` at their first contract call. Two of O02's six
required checks — `retrieval_integrity_and_fallback_test` and
`non_vector_release_guard_test` — cannot run at all, so neither currently
demonstrates anything.

That is a different failure from the benchmark's. The benchmark runs and
measures the wrong thing; these do not run.

### Repaired

Each affected fixture now compiles the QueryPlan its request is a lane
projection of, taking the forward queries from the fixture's own query batch,
and binds `plan_hash` to it. The confirmation that the plan matches the fixture
rather than merely satisfying the signature is that the projected lexical query
hash equals the hash the fixture already recorded. All 37 call sites pass
`query_plan`; a static re-audit reports zero missing.

With that done, the provenance audit runs:

```text
real LEXICAL + CITATION_GRAPH origin   ceiling=PASS     reason=non_vector_origin_present
SEMANTIC-only origin                   ceiling=PARTIAL  reason=vector_only_release
relabelled as LEXICAL, hash untouched  REFUSED  CANDIDATE_HASH_MISMATCH
relabelled as LEXICAL, hash recomputed REFUSED  CHANNEL_OBSERVATION_MISMATCH
```

So `non_vector_release_guard_test` is sound. It does exactly what the benchmark
gate cannot: it holds the recorded backend observation and reconciles the
claimed channel against it, rather than trusting the label.

Two of the three required checks audited this attempt are healthy. The
benchmark is the one that is not.

Whether a benchmark that truthfully reports eight BLOCKED lanes can satisfy
O02's all-lane performance requirement is a shared acceptance question. It
touches the acceptance authority and the development-manifest projection, has
no authorized owner, and is not decided here.

Whether `evaluate_retrieval_benchmark` should take candidate provenance is an
O02-owned change to `python/epistemic_foundry/retrieval/lanes/contracts.py`,
but it changes what the required check means and would invalidate the current
benchmark evidence again. It is named here rather than made.

`relation_direction_test` and `non_vector_release_guard_test` are in the same
risk class but their defect is not established. The decisive audits would be a
same-vocabulary relation reversal and a provenance mutation respectively.
Neither was run; folding them into this attempt would have widened it past the
one bounded finding.

## Reviewer

Independent review of this attempt is still required. The author performed the
measurements; a reviewer who did not should confirm that the result is a
construct-validity failure rather than a failed attempt to implement eight
backends, and that no unavailable lane was relabelled.
