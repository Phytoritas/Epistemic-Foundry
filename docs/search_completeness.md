# Search completeness and absence-language contract

## Core distinction

`UNSEARCHED`, `SEARCHED_NONE`, and `SEARCHED_WITH_RESULTS` are different states.

A zero-result response is evidence about a particular query execution, not evidence that the literature contains no relevant work.

## Mandatory eleven lanes

1. lexical
2. semantic
3. citation
4. entity/variable
5. mechanism
6. counterevidence
7. null/failed replication
8. boundary/moderator
9. method
10. temporal/update
11. external novelty/prior art

## SearchLaneReceipt

Each lane records query text/hash, scope, source/index snapshot, result and exclusion IDs, cutoffs, stop reason, errors, and timestamps. A failed lane cannot be represented as zero results.

## Completeness certificate

RetrievalRun aggregates receipts and states:

- mandatory lanes completed,
- blocked and failed lanes,
- unsearched scope partitions,
- effective independent candidate count,
- ranking/deduplication versions,
- corpus and external index coverage,
- certificate hash.

## Admissible absence language

```text
“No matching evidence was retrieved by [lanes] from [sources]
under [scope/query/version/date/cutoff].”
```

Not admissible:

```text
“No evidence exists.”
“This hypothesis is globally novel.”
“The field has never tested this.”
```

## Stop rules

A search may stop because of preregistered saturation, budget, time, source exhaustion, or policy. The reason is visible and caps conclusion strength.
