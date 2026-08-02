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

The deterministic Foundry Kernel is the sole final classification authority.
PolicyBundle typed declarations, typed request metadata, deterministic
detectors, and non-authoritative LLM SignalProposals contribute signals in
that authority order. A lower source cannot remove a higher-source signal.

The closed signal vocabulary and minimum floors are:

| Signal | Floor |
|---|---|
| `TRANSFORM` | E0 |
| `LOOKUP` | E1 |
| `SYNTHESIS` | E2 |
| `MECHANISM` | E3 |
| `CAUSAL`, `VALIDATION`, `HIGH_STAKES`, `EXPENSIVE` | E4 |
| `NOVELTY`, `AMBIGUOUS` | E5 |

The effective class is the maximum floor across all accepted signals. A set
with no recognized signal receives sticky `AMBIGUOUS`, producing E5 with
Interview. Duplicate signals are removed and the canonical reason order is
`AMBIGUOUS`, `NOVELTY`, `HIGH_STAKES`, `EXPENSIVE`, `CAUSAL`, `VALIDATION`,
`MECHANISM`, `SYNTHESIS`, `LOOKUP`, `TRANSFORM`. Signal addition cannot lower
class, human gate, Interview protection, phases, roles, policy checks, or
evidence obligations.

| Class | Exact base phases | Logical roles | Human gate |
|---|---|---:|---|
| E0 | `[]` | 0 | false |
| E1 | `F → O → E` | 1 | false |
| E2 | `F → O → R → G → E` | 3 | false |
| E3 | `F → O → R → G → E` | 6 | false |
| E4 | `F → O → R → G → E` | 10 | true |
| E5 | `F → O → R → G → E` | 12 | true |

E4/E5 prepend `I` only when an I01-I09 rule identifies ambiguity,
conflicting requirements, a missing goal, scope, falsifier, authority,
high-risk contract, novelty boundary, or bounded-cost input. An otherwise
complete novelty request remains E5 without Interview. Missing-contract rules
that would require Interview below E4 fail closed through `AMBIGUOUS` rather
than creating a non-canonical lower-class phase sequence. Interview resolves
the research contract; the E4/E5 human gate separately authorizes risky
execution, expenditure, validation, promotion, release, or publication-grade
export.

The default role counts describe logical epistemic roles, not model calls,
processes, retries, or agents. E1 uses Evidence Scout; E2 adds Synthesis
Analyst and Counterevidence/Method Auditor; E3 uses Evidence Scout,
Inductivist, Deductivist, Prosecutor/Falsifier, Method Auditor, and Judge; E4
adds Scope Auditor, Causal Auditor, Statistician/Replication Auditor, and an
Independent Attestor; E5 adds Novelty Examiner and Abductive Mediator.

Classification controls minimum research process and protection, never the
desired conclusion. Every correction or reclassification creates a new
immutable EpistemicWorkClassification. A same-request HumanDecision may only
raise class or protection. Lower classification requires a new request
revision or PolicyBundle.

### 2.1 Classification identity and execution binding

The classifier version introduced by F01 is `4.0.1-f01.1`.
`classification_hash` is the SHA-256 of RFC 8785 JCS-equivalent canonical JSON
containing exactly the schema ID, request ID, immutable request input hash,
classifier version, PolicyBundle hash, normalized signals, ordered reasons and
risk factors, exact projection, and nullable superseded classification and
HumanDecision hashes. `classification_id` is `EWC-` plus the digest hex.
Identity, time, receipt, storage, ledger sequence, retry, duration, and
provider fields are excluded from that preimage.

The ClassificationCommitter assigns one UTC millisecond timestamp, writes the
classification artifact and ArtifactReceipt, appends the Noetic Ledger event,
and compare-and-swaps the active pointer. Equal idempotency key and preimage
returns the existing ID, hash, time, artifact, and receipt; a changed preimage
fails `IDEMPOTENCY_CONFLICT`. Strict replay requires exact semantic and
identity equality or fails `REPLAY_DIVERGENCE`. An override binds the previous
classification hash and HumanDecision hash, preserves the prior artifact,
records `SUPERSEDES`, and cannot reduce protection.

`EpistemicWorkClassification` is the classifier node's canonical business
artifact. `ResultEnvelope` is execution telemetry only and must name that
artifact in `output_artifact_ids`; envelope-only success fails
`CLASSIFICATION_ARTIFACT_MISSING`. F01 uses only the canonical capabilities
`artifact_read` and `artifact_write`; dotted or colon aliases fail closed.

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
