# Epistemic Foundry v4 — the O02 retrieval benchmark measures string overlap

Follow-up in the same conversation. The A01 source-root and executor-binding
freeze you specified is written up and waiting on the product owner. While it
waits I stayed inside O02, which I do own, and found something concrete.

## What I found

O02's `retrieval_benchmark` is one of its two headline required checks. It
reports, and its test asserts, per-lane Recall@20 ≥ 0.90 and nDCG@20 ≥ 0.85
across all eleven canonical lanes, plus 100% on the four critical must-find
cases (counterevidence, null, boundary, method).

I measured how much of each fixture query is literally copied from its one
labelled relevant document. Every query, all eleven:

```
query        lane               overlap  distinctive terms shared
Q-LEX        lexical              100%  ['exact', 'identifier', 'phrase']
Q-SEM        semantic             100%  ['conceptually', 'distributed', 'improvement', 'long', 'similar']
Q-CIT        citation             100%  ['citation', 'graph']
Q-ENTITY     entity_variable      100%  ['adult', 'entity', 'learner', 'outcome', 'unit']
Q-MECH       mechanism            100%  ['consolidation', 'effort', 'intermediate', 'mechanism', 'pathway']
Q-COUNTER    counterevidence      100%  ['counterevidence', 'immediate', 'massed', 'outperforms']
Q-NULL       null                 100%  ['effect', 'equivalence', 'failed']
Q-BOUND      boundary             100%  ['boundary', 'condition', 'dose', 'moderator', 'threshold']
Q-METHOD     method               100%  ['compatibility', 'instrument', 'method', 'preregistration', 'validity']
Q-TEMP       temporal             100%  ['historical', 'later', 'temporal', 'update']
Q-NOV        external_novelty     100%  ['art', 'external', 'formulation', 'independent', 'novelty']
```

"Distinctive" means the term appears in exactly one corpus document. So each
query contains a unique key to its own answer.

The corpus is 12 documents: one per lane, each written to contain its lane's
name and vocabulary, plus one distractor explicitly described as "General
research record without the lane-specific target terms."

I then ran the shipped lexical backend — the only non-vector lane with a real
index — against the same corpus and the four critical must-find queries:

```
Q-COUNTER    expected=['DOC-COUNTER']  got=['DOC-COUNTER']
Q-NULL       expected=['DOC-NULL']     got=['DOC-NULL']
Q-BOUND      expected=['DOC-BOUND']    got=['DOC-ENTITY', 'DOC-BOUND']
Q-METHOD     expected=['DOC-METHOD']   got=['DOC-METHOD']
```

A single SQLite FTS5 BM25 index finds every critical must-find document,
including the ones labelled for lanes that have no backend at all.

## Why I think this matters

The eleven-lane contract exists to stop one retrieval channel from standing in
for all of them. `retrieval_candidate_contract.non_vector_release_origins` and
the PARTIAL run ceiling encode that in one direction: vector similarity may not
be the sole channel.

This fixture allows the same substitution in the other direction. Lexical
matching alone scores 100% on the semantic and mechanism lanes. The benchmark
cannot distinguish a system that implements eleven lanes from one that
implements string search and labels the results eleven ways.

That does not make O02's recorded PASS fraudulent — the thresholds really are
enforced, the determinism check is real, the "does not average away a failing
lane" check is real. But the per-lane scores do not establish per-lane
capability, and nothing currently says so.

## What I did, pending your view

I did not change the fixture. Two reasons: O02's sealed evidence hashes the
current fixture bytes, and building a genuinely lane-discriminating corpus is a
different piece of work from recording that the current one is not.

Instead I added three checks to `tests/retrieval/test_o02_retrieval_benchmark.py`
(O02's own scope):

1. lane coverage, labelled targets, and at least one distractor are declared
   rather than assumed;
2. each fixture query's `query_family` is one the canonical plan actually binds
   to that lane;
3. the 100% overlap is asserted as a recorded limitation — if someone later
   builds a discriminating fixture, that check fails and has to be deliberately
   removed.

## The question

**Is recording the limitation the right response, or does this invalidate
O02's benchmark evidence and require a corrected attempt?**

Specifically:

1. Under the repository's own evidence rules, is a required check that measures
   the wrong thing a `FAIL`, a `SPEC_GAP`, or an accepted limitation that must
   simply be visible? O02-0002 is recorded PASS on this check. I do not want to
   quietly leave a PASS that overstates what was demonstrated, nor to
   unilaterally reopen a sealed package.

2. If a corrected fixture is required, what makes a lane fixture actually
   discriminating without inventing capabilities we do not have? For the
   adversarial lanes I can imagine a corpus where the null-result document does
   not contain the word "null", the counterevidence document does not contain
   "counterevidence", and the distinguishing signal is the claim's relationship
   to the query rather than shared vocabulary. But then no current backend
   retrieves them, and the benchmark would have to record BLOCKED for eight
   lanes rather than 0.90+ scores. Is that the honest fixture, and is a
   benchmark that mostly reports BLOCKED still a useful required check?

3. Does the same defect class exist in the other O02 required checks
   (`relation_direction_test`, `non_vector_release_guard_test`) — that is,
   should I audit whether their fixtures also encode the answer in the input?
   I have not looked yet and would rather ask before spending the effort.

4. Does this change anything about the pending A01 request? My instinct is no:
   it is one more instance of "the artifact exists and the check passes, but the
   thing the check names is not demonstrated", which is the same shape as the
   executor-binding finding. But it is O02-local, and the A01 freeze is about
   authority, so I do not think it belongs in that request.

Constraints unchanged: no embedding models, no network dependencies, no
external services, local determinism is hard. Name one step. State the
observable outcome that proves it worked and the one that proves it only
appeared to work. If it requires a shared-contract change outside O02's write
scope, say so — that is a `SPEC_GAP` I stop on rather than improvise.
