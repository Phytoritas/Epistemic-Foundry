# Decision needed: the completeness certificate is one lane short of reachable

## What changed since the last turn

Your acceptance-gate decision was implemented as scoped. `A04` now owns
`manifests/acceptance_matrix.yaml`; the SPEC_BUNDLE pins read 23/350, matching
`MASTER_SPEC.md:814`; and `validate_spec_bundle.py` no longer holds its own
count literals. It reads the matrix gates and compares them with observation.

I verified the comparator both ways. Reverting the gate to 22 produces
`workflow count 23 != 22`; setting it to `'many'` produces
`not an integer: 'many'` plus `350 != -1`. That second case exposed a real
defect in my first attempt: an invalid gate raised `KeyError` and killed the
validator instead of failing the check, so I made unreadable gates resolve to a
sentinel that can never match. Inventory errors are now zero; the remaining 56
are all `PACKAGE_MANIFEST.json` hash differences, still blocked on the 179
uncommitted files.

## The finding

I went looking for the next real capability and found that far more of the
evidence-completeness chain exists than I expected. All of these are already
implemented and exported:

- `pin_corpus_snapshot` (K05) — content-addressed corpus pin
- `declare_prior_art_boundary` (K05) — date/scope boundary
- `build_evolution_retrieval_plan` (O05) — plan with per-lane dispositions
- `efoundry retrieve query --lane` — real lane execution with sealed receipts
- `build_search_completeness_certificate` (O06) — reconciles receipts into the
  canonical `search-completeness-certificate`

I ran the whole chain against a real two-document corpus. It gets all the way
to the final step:

```
SNAPSHOT_OK id=CSNAP-676cfcf3...
BOUNDARY_OK
PLAN_OK     plan_id=ERP-dfca8a04...
LANES_OK    receipts=11 candidates=1
CERT_FAILED WORK_CLASS_LANE_RULE_VIOLATED
```

The certificate builder is correct to refuse. The problem is a genuine
capability gap:

| Work class | Required lanes | Backend serves |
|---|---|---|
| E0 | none (exempt) | — |
| E1 | lexical, semantic, citation, temporal | lexical, citation, entity_variable |
| E3 | ten lanes | same three |

`retrieval/lanes.py` implements exactly three lanes: `lexical`, `citation`,
`entity_variable`. Every other canonical lane returns its `UNSEARCHED`
sentinel, which is honest but means no graded work class can currently reach a
`PASS` completeness certificate.

E0 does not help: it is exempt, so it requires that *no* lane was searched.
Running the lexical lane and then claiming E0 fails schema validation with
`completed_lanes: ['lexical'] is expected to be empty`. That refusal is also
correct.

So the chain is complete except that the served lane set and the lowest graded
work class do not intersect.

## The questions

1. Is implementing a fourth lane the right move, and if so which one? `semantic`
   and `temporal` are both in E1's floor. `temporal` looks tractable against the
   existing SQLite index if documents carry dates. `semantic` implies embeddings,
   which is a much larger dependency and I suspect out of scope. Do you agree
   E1 is the target, and is `temporal` + `semantic` genuinely required, or is
   there a legitimate way for a graded class to complete with fewer served
   lanes?

2. Is `PARTIAL` the honest destination rather than `PASS`? The completion
   vocabulary is `NOT_REQUIRED / PASS / PARTIAL / BLOCKED / FAIL`. Perhaps the
   correct first capability is a truthful `PARTIAL` certificate with explicit
   unsearched lanes and a correspondingly capped `absence_claim_ceiling`,
   rather than chasing `PASS`. If so, what currently prevents `PARTIAL` from
   being produced, and is that a defect or intended?

3. Should any of this be surfaced through MCP? `foundry.search.plan` is a
   `DURABLE_PLAN_ARTIFACT` tool bound to `query-plan.schema.json`. The plan I
   built is an `ERP-` evolution retrieval plan, which may be a different
   artifact. Are they the same contract or two different things?

4. Who owns a new lane implementation? `retrieval/lanes.py` lives under
   `src/epistemic_foundry/retrieval/`, which I have not found in any declared
   `write_scope`. If nothing owns it, that is presumably another SPEC_GAP.

5. Is this the right target at all? The alternative is that the certificate
   chain is deliberately gated behind a real corpus (EVOLUTION_MVP_50 requires
   50 licensed documents) and that making it pass with a toy corpus is not
   meaningful progress. Push back if so.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work beyond what the completeness certificate itself requires.
- Flag explicitly as SPEC_GAP anything requiring a manifest ownership
  amendment or a shared canonical contract change.
- Prefer the smallest change that produces a genuine, verifiable capability.
- Do not propose adding an embedding model or network dependency.
- Assume no tests will be run unless explicitly requested.
