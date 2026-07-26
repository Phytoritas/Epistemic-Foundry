# FORGE protocol — research-native lifecycle

## 1. Why FORGE replaces PABCD

PABCD is a disciplined software implementation lifecycle. Epistemic Foundry needs a lifecycle in which the deliverable is not code but a source-bound, scope-bounded, adversarially examined epistemic object. FORGE keeps the useful properties—durable phase state, bounded transitions, re-entry, artifacts, and explicit completion—but changes the semantics.

```text
IDLE
  └─→ I  Interview (optional, human-led)
       └─→ F  Frame
             └─→ O  Observe
                   └─→ R  Reason
                         └─→ G  Gate
                               └─→ E  Export / Evolve
                                     └─→ IDLE or a new revision cycle
```

Return edges:

```text
F/O/R/G → I   unresolved requirement, ontology, scope or authority
R/G     → O   missing, failed or biased evidence search
G       → R   invalid inference, hidden premise or unresolved alternative
E       → F   revised hypothesis creates a new immutable revision
```

A return edge preserves prior artifacts but marks downstream artifacts stale.

## 2. Epistemic work classes

| Class | Typical request | Minimum path | Default agents | Promotion |
|---|---|---|---:|---|
| E0 | formatting, translation, deterministic transform | no FORGE | 0 | none |
| E1 | direct fact/source lookup | F → O → E | 0–1 | answer with source receipt |
| E2 | bounded literature synthesis | F → O → R → G → E | 2–4 | conditional Passport |
| E3 | cross-source claim/mechanism analysis | full FORGE | 4–8 | Parliament required |
| E4 | causal/high-stakes/expensive validation | full FORGE + human gates | 6–12 | method/causal veto and attestation |
| E5 | ambiguous/open novelty research | I + full FORGE | adaptive ≤16 | staged output; underdetermination normal |

Classification is recorded, explainable, and overridable by an `OverrideRecord`. The class controls process depth, not the desired conclusion.

## 3. Phase contracts

### I — Interview

Purpose: resolve the minimum research contract without turning the session into endless questioning.

Required dimensions:

- goal and intended decision;
- canonical claim and prohibited overclaim;
- population/system and scope;
- success and falsification;
- corpus/data authority and licensing;
- time boundary and novelty scope;
- output form;
- privacy, safety and human approval needs.

Exit artifact: `ResearchBrief`, `OntologyIssueList`, `ConsentRecord` where relevant.

Gate: all critical contradictions resolved or explicitly accepted as blockers. The model cannot invent missing organizational decisions.

### F — Frame

Purpose: convert free text into a falsifiable, scope-bounded research object.

Required artifacts:

- `InsightCard`;
- `ScopeVector`;
- mechanism or argument sketch;
- predictions;
- falsifiers;
- alternatives known at intake;
- reasoning modes requested;
- QueryPlan and required search lanes;
- work class and budget envelope;
- authority/corpus policy.

`F → O` is denied when the falsifier is absent, scope is non-normalizable, the claim contains an undefined construct, or required consent is missing.

### O — Observe

Purpose: acquire and normalize evidence without pre-committing to a verdict.

Required search lanes, selected by class and query:

- lexical;
- semantic;
- citation lineage;
- entity/variable;
- mechanism;
- counterevidence;
- null results;
- boundary conditions;
- method/measurement;
- temporal update/correction/retraction;
- external novelty.

Every lane emits a `SearchLaneReceipt`. The phase emits:

- source registry and document hashes;
- SourceSpans;
- ClaimCards/EvidenceNodes;
- dependency clusters;
- Evidence Pack;
- SearchCompletenessCertificate;
- searched and unsearched scope.

`UNSEARCHED`, `SEARCHED_NONE`, and `SEARCHED_WITH_RESULTS` are distinct states. A failed lane cannot be rewritten as zero evidence.

### R — Reason

Purpose: perform mode-specific reasoning while preserving incompatible inference semantics.

Parallel outputs:

- inductive synthesis and heterogeneity;
- deductive proof trace and hidden premises;
- abductive competing explanations;
- causal DAG and identification status;
- contradiction classification and moderators;
- uncertainty and dependency sensitivity;
- expected discriminating observations.

Required artifacts:

- ArgumentGraph;
- mode-specific traces;
- AlternativeHypothesisSet;
- weakest-link report;
- inference assumptions;
- candidate verdicts.

No inference mode is allowed to promote another mode's status. Association does not become causal; simulation does not become empirical.

### G — Gate

Purpose: try to kill, narrow, or suspend the candidate conclusion.

Blind first-round roles receive different evidence ACLs. Standard roles:

- Defender;
- Prosecutor;
- Method Auditor;
- Scope Auditor;
- Causal Auditor;
- Novelty Examiner;
- Cross-Examiner;
- Abductive Mediator;
- Minority Reporter;
- Judge;
- Independent Attestor.

Hard gates:

- provenance and schema;
- source-span grounding;
- search-lane completion;
- dependency clustering;
- method comparability;
- scope compatibility;
- causal status;
- novelty search scope;
- strongest counterevidence;
- minority report;
- missing-agent count;
- policy/consent;
- independent attestation.

A judge cannot override a failed deterministic gate. Method and safety vetoes impose a promotion ceiling. Majority is diagnostic, not authoritative.

### E — Export / Evolve

Purpose: publish a precise, replayable result and prepare the next discriminating action.

Required artifacts:

- Hypothesis Passport revision;
- evidence and provenance bundle;
- SearchCompletenessCertificate;
- GateDecision;
- minority report;
- ContextAssemblyManifest;
- lifecycle and stability status;
- next discriminating test or explicit no-test reason;
- export receipt and redaction report.

Possible outcomes include `SUPPORTED`, `MIXED`, `CONTRADICTED`, `UNDERDETERMINED`, `UNTESTABLE`, and `NOT_ASSESSED`. `UNDERDETERMINED` is a successful truthful output.

## 4. Transition enforcement

A `ForgeTransitionRequest` includes:

```text
session_id
expected_revision
from_phase
to_phase
actor
artifact_receipt_ids
gate_result_ids
human_decision_id, when applicable
reason
idempotency_key
```

The transition reducer:

1. loads the exact expected revision;
2. checks the legal edge;
3. resolves required artifacts by receipt;
4. validates artifact schemas and hashes;
5. applies policy and veto;
6. appends the transition event;
7. commits state atomically;
8. emits a transition receipt.

A free-form chat message can request a transition but cannot constitute evidence.

## 5. Human authority

Humans may:

- approve a risky action;
- narrow or expand the scope;
- accept a documented limitation;
- override a non-safety decision;
- reopen a phase;
- reject or supersede a Passport.

Humans may not erase provenance. Every intervention records actor, viewed revisions, rationale, conflicts, scope, expiry, and downstream invalidation.

## 6. Completion semantics

A run is complete only when:

- the final state is committed;
- required artifacts exist and hashes resolve;
- expected fan-out counts reconcile;
- effect intents have receipts;
- the Passport is schema-valid;
- incomplete searches and limitations are visible;
- a replay manifest can reconstruct the result.

The phrases “done”, “verified”, “novel”, “proved”, and “no evidence exists” are controlled claims and require the corresponding gate state.
