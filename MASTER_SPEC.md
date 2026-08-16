# Epistemic Foundry v4.0.0
## Evolution-Governed Hypothesis Discovery and Validation Operating System
### Codex / Claude Code / Provider-Neutral A–Z Development Specification

- **Document status:** `SPEC_BUNDLE / IMPLEMENTATION CONTRACT`
- **Implementation status:** `NOT CLAIMED`
- **Implementation target:** `PLUGIN_ALPHA` — authorized; incomplete
- **Current qualified bundle status:** `SPEC_BUNDLE`
- **Architecture freeze:** `CONDITIONAL PASS`
- **Reference date:** 2026-07-26
- **Product:** Epistemic Foundry
- **Plugin ID:** `epistemic-foundry`
- **Python namespace:** `epistemic_foundry`
- **CLI:** `efoundry`
- **Research lifecycle:** `FORGE`
- **Evolution subprotocol:** `EVOLVE — Encode / Vary / Oppose / Learn / Validate / Elevate`
- **Canonical authority:** Foundry Kernel + Noetic Ledger
- **Scientific promotion:** deterministic gates + Evidence Parliament + independent attestation + explicit human/policy authority
- **Knowledge structure:** E/R/D/X Four-Graph plus typed evolutionary projections
- **Target scale:** 50-document gold → 200-document pilot → 1,800–2,000-document production qualification
- **Domain model:** domain-neutral core + versioned DomainPack
- **Optional search backend:** pinned, qualified ShinkaEvolve adapter

---

# Part I — Authority, truthfulness and research basis

## 1. Authority order

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `manifests/acceptance_matrix.yaml`
4. `manifests/product_invariants.yaml`
5. canonical schemas and workflows
6. `manifests/role_registry.yaml`
7. `AGENTS.md` or `CLAUDE.md`
8. work-package-local notes

Lower authority cannot override higher authority. Missing or inconsistent shared semantics return `SPEC_GAP`. A clear contract blocked by an unavailable external prerequisite returns `BLOCKED`. `PASS` requires objective checks, immutable resolving artifacts/effect receipts and independent review.

## 2. Maturity statement

This bundle specifies v4 target architecture, canonical contracts, workflows, plugin blueprint, migration, acceptance gates and A–Z implementation graph. It does not claim that a working v4 runtime has qualified for release. It does not claim `PLUGIN_ALPHA` completion, a qualified evaluator, hidden holdout, Shinka adapter, production database, production UI, independent security review or 2,000-document deployment.

### Plugin implementation authority and release qualification

The authorized implementation target for this repository is `PLUGIN_ALPHA`.
An executable installed-plugin candidate may be built, packaged, installed and
exercised while the qualified status of this bundle remains `SPEC_BUNDLE`.

The fail-closed-stub requirement applies only when the authorized implementation
target is `SPEC_BUNDLE`. It does not prohibit the executable candidate authorized
by `docs/decisions/20260815-plugin-alpha-goal.md`.

`status_of_this_bundle` records the highest release level for which every
required acceptance gate has executable and accepted evidence. It does not
assert that no unqualified implementation artifacts exist.

The existence of an executable candidate, successful manual exercise or partial
satisfaction of the `PLUGIN_ALPHA` gate set must not be represented as a
`PLUGIN_ALPHA` release. `PLUGIN_ALPHA` may be claimed only after all fifteen
gates named under `PLUGIN_ALPHA` in `manifests/acceptance_matrix.yaml` have
executable, reviewable evidence bound to the candidate source revision and
installed payload, and the authorized acceptance owner changes
`status_of_this_bundle` to `PLUGIN_ALPHA`.

Entries in `runtime_capabilities` describe mechanisms present in the candidate
payload. They do not establish host-cell verification or release qualification.
A capability whose corresponding acceptance evidence is incomplete remains
unqualified. A specification file is not execution evidence. An executable
candidate is not execution evidence for an acceptance gate either.

## 3. ShinkaEvolve source study

The public `SakanaAI/ShinkaEvolve` repository, current documentation/source surfaces and the v0.0.7 release were inspected. The study covered:

- population and lineage;
- parent and inspiration selection;
- novelty rejection;
- archive/island/migration;
- LLM ensemble and cost-aware bandit;
- prompt co-evolution;
- asynchronous proposal/evaluation/database paths;
- SQLite/WAL persistence and resume/idempotency surfaces;
- executable task/evaluator contract;
- `shinka-setup`, `shinka-convert`, `shinka-run` and `shinka-inspect` skills;
- local/Slurm/headless execution;
- paper and changelog claims.

The complete factual inventory and 55 adoption/correction decisions are in:

- `research/shinkaevolve_source_manifest.json`
- `research/shinkaevolve_gap_analysis.md`

The architectural conclusion is:

> **ShinkaEvolve is a strong optional executable-program evolution backend. Epistemic Foundry v4 generalizes its search mechanisms to typed scientific candidates while adding a Verifier Firewall, quality-diversity epistemic archive, Red Queen challenges, adaptive-search statistics, independent replication and non-evolvable promotion authority.**

## 4. v4 thesis

> **Epistemic Foundry v4 is a provenance-bound, coverage-first, adversarial and evolution-governed research operating system that searches over falsifiable hypotheses, mechanisms, experiments and challenges while keeping evidence, evaluators, hidden holdouts, statistics and scientific promotion outside the evolutionary mutation surface.**

The search system can be creative. The trust system must be conservative.

---

# Part II — Product constitution: 64 non-negotiable invariants

### EF4-I01 — Kernel authority

Plugin shell, hooks, skills, GUI, chat transcripts and provider SDKs never own canonical state, policy, gates or replay.

### EF4-I02 — Claim-first evidence

A promoted empirical or documentary claim always resolves to immutable SourceSpan evidence.

### EF4-I03 — Falsifiable intake

An insight without scope, predictions and falsifier cannot enter Observe or Parliament.

### EF4-I04 — Coverage before confidence

Coverage, searched scope, missing lanes and dependency diversity are shown before confidence or verdict.

### EF4-I05 — Search-state type safety

UNSEARCHED, SEARCHED_NONE, SEARCHED_WITH_RESULTS and failed search are distinct.

### EF4-I06 — Adversarial retrieval

Counterevidence, null, boundary and method lanes are mandatory whenever applicable.

### EF4-I07 — Method comparability

Method-incompatible evidence is stratified and may impose a promotion ceiling; it is never silently pooled.

### EF4-I08 — Dependency-adjusted evidence

Shared samples, datasets, publication families and derived analyses are dependency clusters, not independent votes.

### EF4-I09 — No majority authority

Agent count or majority agreement cannot promote a hypothesis.

### EF4-I10 — Inference separation

Induction, deduction, abduction and causal identification remain separate typed outputs.

### EF4-I11 — Evidence-class separation

Simulation, formal derivation, benchmark and review-derived evidence never become empirical observation by relabeling.

### EF4-I12 — No self-approval

Makers cannot approve their own work, claim promotion, validation, or release.

### EF4-I13 — Receipt-bound completion

Phase transitions, side effects, tests, installs and releases require resolving artifact/effect receipts.

### EF4-I14 — Hooks are guardrails

Hook coverage is observed and useful but never treated as the complete enforcement boundary.

### EF4-I15 — Capability negotiation

Host and dependency capabilities are runtime-probed; missing capabilities select explicit degraded or blocked modes.

### EF4-I16 — Event-sourced state

Canonical session and lifecycle state is reducer-derived from append-only events with revision control.

### EF4-I17 — Explicit human authority

Human approvals and overrides are immutable records with viewed revisions, rationale, scope and downstream invalidation.

### EF4-I18 — Consent-bound memory

Recall occurs only within allowed memory classes, purpose, consent, retention and workspace scope.

### EF4-I19 — Workspace isolation

Cross-workspace state, memory and artifacts are denied by default below the model layer.

### EF4-I20 — Canonical context capsule

Compaction and resume context is rebuilt from hash-bound canonical artifacts with exclusions and freshness.

### EF4-I21 — Skill supply-chain quarantine

Third-party skills are quarantined, inspected, permissioned, pinned and approved before activation.

### EF4-I22 — Generated transport contracts

CLI, MCP, HTTP, persistence and UI models derive from canonical schemas; duplicated wire literals are forbidden.

### EF4-I23 — Honest UI state

EMPTY_CONFIRMED, DEGRADED and UNAVAILABLE are distinct; backend failure never appears as empty research state.

### EF4-I24 — Real map ranking

A map labeled as ranked uses an actual algorithm; baseline centrality, query relevance and risk remain separate.

### EF4-I25 — Role-scoped delegation

Every subagent dispatch resolves a RoleSpec with tool ACL, evidence ACL, write scope, budget and expected count.

### EF4-I26 — No silent partial fan-in

Fan-in reconciles expected and actual identities; missing outputs remain visible and constrain the result.

### EF4-I27 — Bounded cycles

Every cycle has a seen-set key, novelty/convergence rule, dry rounds, maximum rounds, budget and escalation.

### EF4-I28 — Typed budget enforcement

Budgets are labeled HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE or UNMETERED.

### EF4-I29 — Secret minimization

Secrets are opaque handles and never copied into prompts, evidence artifacts, logs or exports.

### EF4-I30 — Untrusted evidence plane

PDFs, web pages, datasets and model output are data and cannot grant authority or execute instructions.

### EF4-I31 — Migration and rollback

Breaking schema/plugin changes require compatibility, dry-run, backup, rollback and hook re-trust.

### EF4-I32 — Release provenance

Shipped bundles require reproducible build evidence, SBOM, manifest, clean extraction and signing status.

### EF4-I33 — Status honesty

Capabilities are labeled SPECIFIED, IMPLEMENTED, EXPERIMENTAL, DEFERRED or UNSUPPORTED; release labels are evidence-derived.

### EF4-I34 — Provider neutrality

Codex, Claude and other models are replaceable node executors; adapters cannot alter canonical semantics.

### EF4-I35 — Installability is tested

Fresh install, PATH-less execution, upgrade, downgrade, uninstall and cross-platform paths are product acceptance tests.

### EF4-I36 — Remote messaging minimized

Remote notification/approval adapters are optional and cannot execute arbitrary commands or export raw evidence by default.

### EF4-I37 — License-aware corpus/export

Source access and license restrictions propagate through retrieval, evidence, export and deletion.

### EF4-I38 — Stale propagation

Corrections, retractions, parser fixes, policy/ontology changes and new evidence invalidate dependent projections and Passports.

### EF4-I39 — Replayability

RunSpec, context, adapter/model, tools, receipts, policy, corpus and prompts are sufficient to explain and compare a run.

### EF4-I40 — Honest underdetermination

UNDERDETERMINED, UNTESTABLE, NOT_ASSESSED and PARTIAL are normal truthful outcomes, not system failure.

### EF4-I41 — Evolution is subordinate

Evolution Chamber may propose, mutate, challenge and rank candidates but cannot own evidence truth, evaluator authority, policy, hidden holdout, promotion or release.

### EF4-I42 — Typed scientific genome

Every evolvable hypothesis carries scope, mechanism, predictions, falsifiers, alternatives, measurement contracts, evidence, validation plan and immutable lineage.

### EF4-I43 — Immutable evaluator per run

A running or completed EvolutionRun references one content-addressed evaluator bundle that cannot be changed retroactively.

### EF4-I44 — Hidden holdout firewall

Candidate generation, mutation prompts, external backends and ordinary agents cannot read hidden holdout content or derive it from tool/log/cache leakage.

### EF4-I45 — No scalar promotion authority

A combined score may order search but cannot promote; hard gates, FitnessVector, Pareto/niche analysis, statistics, replication and Parliament constrain promotion.

### EF4-I46 — Multi-layer novelty

Claim, mechanism, prediction, falsifier, scope, experiment, evidence and external prior-art novelty remain separate from support and truth.

### EF4-I47 — Novelty failure type safety

Absent, empty, failed or incomplete novelty assessment yields UNASSESSED, PARTIAL or FAILED and never NOVEL by default.

### EF4-I48 — Quality-diversity archive

The archive preserves epistemic niches and trade-offs rather than only a global top score.

### EF4-I49 — Protected negative memory

Nulls, counterexamples, failed replications, unsafe failures and minority lineages cannot be evicted merely for low fitness.

### EF4-I50 — Semantic islands

Islands specialize by typed mechanism, scope, method or evidence state; migration requires compatibility and preserves source/target history.

### EF4-I51 — Typed crossover

Crossover requires scope, measurement, unit and causal compatibility; semantic collage is rejected.

### EF4-I52 — Red Queen relevance

Challenges are safe, reproducible and claim-relevant; apparent failures replicate before refutation and boundary conditions remain distinct.

### EF4-I53 — Adaptive-search statistics

Evolutionary search records candidate families, repeated tests, sequential decisions, multiplicity and selective inference.

### EF4-I54 — Delayed reward routing

Model and operator bandits learn from validated holdout/replication utility and safety, not only immediate proxy score.

### EF4-I55 — Prompt evolution quarantine

Prompt genomes cannot alter current policy, evaluator, holdout or promotion gate and become active only after independent future-run qualification.

### EF4-I56 — Evaluator updates are future-only

Evaluator defects create quarantined proposals; approved changes apply to new sealed runs and never rewrite completed judgments.

### EF4-I57 — Surrogate is triage only

A surrogate may prioritize direct evaluation but cannot replace required direct, hidden or replication stages.

### EF4-I58 — Replication-gated promotion

High scientific promotion after adaptive evolution requires an appropriate independent preregistered replication or an explicit lower ceiling.

### EF4-I59 — Selection-bias visibility

Top-candidate estimates disclose search/selection history, winner's curse risk and bias-corrected uncertainty.

### EF4-I60 — Exact candidate reconciliation

Every fan-out reconciles proposed, generated, evaluated, persisted, failed, cancelled and missing candidate identities.

### EF4-I61 — Atomic evolution checkpoints

A safe resume point binds population, archive, islands, bandit, budget, testing ledger and evaluator hash atomically.

### EF4-I62 — Typed stop certificate

Budget, dry rounds, stability, coverage, safety, human stop and blockers yield an EvolutionStopCertificate that preserves partial work.

### EF4-I63 — External backend isolation

ShinkaEvolve and other search engines are optional pinned adapters; their scores, archives, novelty and state never become Foundry authority.

### EF4-I64 — Executable candidate sandbox

Candidate code executes only under declared capabilities, resource quotas, network policy, effect receipts and evaluator/holdout isolation.


---

# Part III — Final architecture

## 5. Module map

| Module | Authority and purpose |
|---|---|
| **Native Plugin Shell** | Manifest, skills, hooks, MCP/CLI, capability probe and Console; never canonical authority. |
| **Foundry Kernel** | Immutable RunSpec, FORGE/EVOLVE state machine, DAG scheduler, policy, capabilities, effects, checkpoint and replay. |
| **Claim Forge** | SourceSpan → atomic ClaimCard → EvidenceNode. |
| **Epistemic Atlas** | Coverage, search state, method compatibility, evidence dependency, bias and epistemic niche maps. |
| **Evolution Chamber** | Typed scientific populations, mutation/crossover, multi-objective quality-diversity search and bounded async execution. |
| **Verifier Firewall** | Immutable evaluator, hidden/OOD holdout, leakage, calibration, metamorphic/adversarial qualification and future-only update governance. |
| **Red Queen Lab** | Co-evolving counterexample, null, confounder, method, OOD, leakage and replication challenges. |
| **Evidence Parliament** | Blind asymmetric briefs, veto, cross-examination, minority report, deterministic gates, judge and independent attestor. |
| **Aporia Engine** | Contradiction classification, moderators, competing mechanisms and discriminating tests. |
| **Epistemic Species Archive** | Pareto/niche elites plus protected nulls, counterexamples, failed replications, unsafe and minority memory. |
| **Noetic Ledger** | Append-only events, actions, effects, approvals, candidate lineage, evaluator versions, statistics and replay. |
| **Validation Bay** | Evidence, simulation, formal, benchmark, hidden/OOD, experiment and replication stages with evidence-class separation. |
| **Hypothesis Passport** | Immutable revision containing claim, scope, mechanism, predictions, falsifiers, evidence, verdict, stability and next test. |

## 6. Authority planes

```text
Experience plane
  Plugin manifest · skills · hooks · CLI · MCP · Console

Execution plane
  provider adapters · parsers · retrieval · sandbox · Shinka adapter

Search plane
  genomes · operators · islands · bandits · Pareto · niches · challenges

Scientific control plane
  evidence contracts · evaluator firewall · statistics · replication · Parliament

Authority plane
  Foundry Kernel · Noetic Ledger · policy · approvals · release
```

The upper three planes cannot grant themselves rights in the lower authority plane.

## 7. Four-Graph integration

### E-Graph — Evidence

Documents, SourceSpans, Claims, experiments, methods, measurements, datasets, quantitative results, dependency clusters, corrections and retractions.

### R-Graph — Reasoning

Hypotheses, premises, assumptions, mechanisms, predictions, falsifiers, alternatives, causal DAGs, rules and argument edges.

### D-Graph — Deliberation

Blind briefs, objections, cross-examinations, method/scope veto, minority reports, adjudications, attestations, human decisions and appeals.

### X-Graph — Validation and execution

Validation targets/plans, evaluator bundles, experiment genomes, model/code runs, stage results, challenges, replication, effects and reconciliation.

Evolution produces append-only revisions and projections across these graphs; it does not overwrite them.

---

# Part IV — FORGE and EVOLVE protocols

## 8. FORGE

```text
Interview(optional)
→ Frame
→ Observe
→ Reason
→ Gate
→ Export / Evolve
```

An insight cannot leave Frame without canonical statement, scope, mechanism sketch, predictions and falsifiers. Observe must distinguish support/counter/null/boundary/method/prior-art lanes and `UNSEARCHED` from `SEARCHED_NONE`.

## 9. EVOLVE

```text
Encode
→ Vary
→ Oppose
→ Learn
→ Validate
→ Elevate
```

### Encode

Freeze `EvolutionRunSpec`, current evaluator/holdout, allowed candidate classes, seed populations, operator registry, budgets, statistical family, quality-diversity axes and stop policy.

### Vary

Select parents and operators, route models, mutate typed genomes or perform compatibility-gated crossover. Record every context, prompt, model, cost, lineage and changed path.

### Oppose

Generate and run safe Red Queen challenges. Reproduce apparent failures and classify true refutation, scope restriction, method failure, measurement artifact or irrelevant exploit.

### Learn

Compute uncertainty-bearing FitnessVectors, Pareto front, niche occupancy, lineage diversity and delayed model/operator rewards. Preserve negative memory.

### Validate

Apply hidden/OOD evaluation, multiple-testing/sequential policy, selective-inference correction and independent preregistered replication.

### Elevate

Submit a sealed promotion pack to Evidence Parliament and independent attestation. Evolution cannot self-promote.

## 10. State machine

```text
DRAFT → FRAMED → EVALUATOR_SEALED → POPULATION_READY
→ GENERATING → CONTRACT_SCREEN → EVALUATING → CHALLENGING
→ SELECTING → REPLICATING → PROMOTION_REVIEW → CHECKPOINTED
→ PAUSED | COMPLETED | BLOCKED | FAILED | CANCELLED
```

Illegal transitions are defined in `docs/evolution_state_machine.md`.

---

# Part V — Scientific genome and evolutionary operators

## 11. HypothesisGenome

Required fields:

```text
canonical claim
ScopeVector
MechanismGraph
PredictionGenes
FalsifierGenes
alternative hypotheses
measurement contracts
Evidence Pack
ValidationPlan
causal-identification status
complexity budget
uncertainty
CandidateLineage
provenance hash
```

A prose-only hypothesis is not eligible.

## 12. Co-evolving populations

- hypothesis population;
- mechanism/model population;
- experiment/probe population;
- challenge/falsifier population;
- measurement/operationalization population.

Prompt genomes and evaluator proposals live in quarantine, not the ordinary scientific population.

## 13. Mutation operators

Canonical operator classes:

- scope;
- mechanism;
- prediction;
- falsifier;
- alternative explanation;
- measurement;
- causal DAG;
- scale transfer;
- method transfer;
- contradiction resolution;
- simplification;
- crossover.

Each operator declares input/output types, preconditions, preserved invariants, changed paths, required audits, prompt reference, risk and hash.

## 14. Crossover

Crossover requires:

- Scope compatibility;
- Measurement compatibility;
- Unit compatibility;
- Causal compatibility;
- lineage preservation;
- one genuinely new discriminating prediction.

An incompatible child is rejected before expensive evaluation.

---

# Part VI — Search and quality-diversity algorithm

## 15. Hard gates and FitnessVector

A candidate first passes non-negotiable contracts:

```text
schema + lineage + provenance + falsifiability
+ evaluator/holdout isolation + method floor
+ safety + budget + receipt completeness
```

Then it receives a vector, not a promotion score:

```text
grounding
support
counterevidence resistance
predictive accuracy
calibration
robustness/OOD
causal identifiability
falsifiability
novelty dimensions
parsimony
information gain
coverage value
replicability
cost efficiency
safety/ethics
```

Each dimension carries uncertainty and a `FitnessEvidenceReceipt`.

## 16. Pareto selection

Let candidate vectors be \(f(c)\). Candidate \(a\) dominates \(b\) only if it is no worse on all selected objectives and strictly better on at least one, after hard-gate filtering and uncertainty policy. Pareto rank guides search but does not prove truth.

## 17. Epistemic MAP-Elites

Default niche coordinates:

```text
mechanism family × scope class × evidence state
× testability band × causal status
```

A DomainPack may add axes. The map exposes sparse, stagnant, unsearched and overpopulated cells. Niche occupancy and lineage diversity are product outputs, not hidden internals.

## 18. Parent acquisition

An implementation may use UCB, Thompson or other bounded policy, but it must expose components equivalent to:

\[
A(c)=g(\mathrm{EIG}, U, C_{debt}, R_{debt}, H_{survival},
      L_{saturation}, Cost, Risk)
\]

where no fixed global weighted sum is mandated. The `ParentSelectionReceipt` records the eligible set, components, random seed and selected parents.

## 19. Model and operator routing

Immediate proxy reward may improve throughput. Scientific routing reward is delayed until hidden/OOD or replication results. Safety violations, leakage, unreconciled workers and invalid candidates are explicit negative outcomes. Different providers are not assumed statistically independent.

## 20. Multi-fidelity evaluation

```text
S0 contract/provenance
S1 static/logic/security
S2 evidence/method/scope
S3 simulation/metamorphic/multi-seed
S4 Red Queen/Parliament adversarial
S5 hidden time/OOD
S6 independent replication/human promotion
```

Cheap, decisive failures stop early. Surrogate models only prioritize direct evaluation.

---

# Part VII — Verifier Firewall

## 21. EvaluatorBundle

A sealed bundle includes evaluator code, metrics, environment, policy, public fixtures, hidden/OOD manifests, metamorphic tests, challenge sets, disclosure rules and exact hash.

```text
mutable_during_run = false
candidate_access_to_hidden = none
```

## 22. Qualification

Before use:

1. supply-chain scan;
2. construct-validity review;
3. leakage audit;
4. deterministic/crash tests;
5. metamorphic tests;
6. adversarial reward-hacking tests;
7. false-positive/false-negative gold comparison;
8. calibration/OOD assessment;
9. independent review;
10. explicit approval;
11. content-addressed seal.

## 23. Future-only evaluator evolution

A candidate may submit an `EvaluatorMutationProposal`. It cannot alter the current run. A shadow bundle is independently qualified; approval creates a future version. Historical decisions remain immutable and may only be reassessed through a new run.

---

# Part VIII — Red Queen, archive and scientific memory

## 24. Red Queen Lab

Challenge classes:

```text
counterexample · null model · confounder · reverse causation
measurement artifact · method failure · scope shift · OOD
leakage probe · adversarial input · replication failure
```

A successful challenge must reproduce. Its result is typed as `REFUTED`, `SCOPE_RESTRICTED`, `METHOD_FAILURE`, `INCONCLUSIVE` or another explicit state.

## 25. Epistemic Species Archive

Entry classes:

```text
elite · diverse · null · counterexample · failed_replication
minority_lineage · unsafe · superseded
```

Raw score cannot evict protected negative memory. Archive changes require an independently audited `ArchiveRebalancePlan`.

## 26. Semantic islands

Islands specialize by mechanism, scope, method or evidence state. Migration creates a new revision and requires compatibility. Dynamic island creation requires documented coverage debt/stagnation, budget and stop conditions.

---

# Part IX — Adaptive-search statistical governance

## 27. Selection problem

Evolution adaptively generates, tests and selects many related candidates. Therefore naive estimates for the winner are biased and repeated public/hidden feedback can leak test information.

## 28. Required artifacts

- `SequentialTestingLedger`
- `MultipleTestingAdjustment`
- `SelectiveInferenceReport`
- hidden exposure log
- candidate family/lineage
- selection and stop events
- replication result

## 29. Allowed policies

Domain-specific justified choices include fixed nested holdout, alpha spending/investing, e-values/e-processes, Bayesian monitoring, hierarchical/FDR control and post-selection correction.

`none_justified` imposes a non-inferential promotion ceiling.

## 30. Replication

High promotion requires appropriate independent preregistered replication or an explicit lower ceiling. Independence is audited across executor, code, model, context, data, method and environment.

---

# Part X — ShinkaEvolve adapter

## 31. Role

The adapter supplies optional executable-program evolution. It is pinned, qualified and sandboxed. The domain-neutral core continues to work without it.

## 32. Mapping

| Shinka surface | Foundry v4 object |
|---|---|
| Program | executable candidate + CandidateLineage |
| parent/inspiration | parent/inspiration IDs |
| generation/island | EvolutionCheckpoint / IslandState |
| combined score | advisory search metric |
| correct | typed StageEvaluationResult |
| archive | Epistemic Archive projection |
| novelty | one partial NoveltyVector input |
| model bandit | OperatorBanditState / ModelRoutingReceipt |
| prompt archive | quarantined PromptGenome |
| evaluator output | evaluator-owned FitnessEvidenceReceipt |
| attempt/event | Noetic Ledger attempt/effect |

## 33. Required adapter tests

- exact source/package/license pin;
- candidate lineage fidelity;
- proposed/evaluated/persisted/failed/missing reconciliation;
- crash/resume/idempotency;
- novelty outage typing;
- evaluator/holdout isolation;
- sandbox/egress/resource controls;
- score/evidence-class separation;
- prompt co-evolution quarantine;
- delayed reward mapping;
- clean rollback/uninstall.

The source study is not an endorsement of a floating `main` dependency.

---

# Part XI — Plugin and user experience

## 34. Reference skills

v4 adds evolution-specific progressive skills for setup, conversion, run, inspection, evaluator audit, challenge, archive, promotion, replication, replay, stop and Shinka qualification. Skills route requests; they do not own state or authority.

## 35. Proposed CLI

```text
efoundry evolve setup|convert|run|pause|resume|stop|inspect|replay
efoundry evaluator register|audit|qualify|diff
efoundry challenge generate|run|inspect
efoundry archive map|inspect|rebalance
efoundry replicate plan|run|audit
efoundry promote evolved
efoundry backend shinka qualify|inspect|disable
```

Mutating commands require dry-run support, expected revision, idempotency key, capability profile, explicit budget and machine-readable receipts.

## 36. Console

Required views:

- Run Charter;
- Species Map;
- Pareto Studio;
- Lineage Graph;
- Red Queen Arena;
- Verifier Firewall;
- Replication Board;
- Archive Vault;
- Operator Console;
- Promotion Docket.

No default single-score leaderboard is permitted.

---

# Part XII — Canonical workflows

| Workflow | Nodes | Purpose |
|---|---:|---|
| `archive_rebalancing` | 11 | Rebalance quality-diversity archives without erasing negative scientific memory. |
| `claim_extraction` | 13 | Select evidence units, extract atomic claims, verify grounding, and create dependency-aware evidence nodes. |
| `corpus_ingest` | 11 | Register, integrity-screen, parse, reconcile, and release immutable source documents. |
| `evaluation_release` | 16 | Run specification, plugin compatibility, scientific, security, calibration, recovery, cross-provider, and scale checks before a signed Epistemic Foundry release manifest. |
| `evaluator_update_governance` | 14 | Govern evaluator evolution in quarantine and apply changes only to future sealed runs. |
| `evidence_retrieval` | 20 | Compile a relation-aware query plan, execute eleven evidence lanes, and issue a completeness-bounded EvidencePack. |
| `evidence_update_reassessment` | 12 | Detect evidence or policy changes, compute impact, invalidate stale state, rerun affected workflows, and record decision deltas. |
| `evolution_chamber_cycle` | 26 | Run one governed quality-diversity hypothesis evolution cycle under immutable evaluators and evidence gates. |
| `evolution_promotion` | 23 | Execute the receipt-bound A05 promotion chain: deterministic G00-G14, sealed Parliament, independent attestation, approval, and atomic commit. |
| `evolution_release` | 15 | Validate and package v4 specification and later implementation releases without maturity overclaim. |
| `forge_research_cycle` | 26 | Execute the research-native FORGE lifecycle from classification to Passport. |
| `hypothesis_replication` | 12 | Run independent preregistered replication and propagate its result without rewriting history. |
| `insight_deliberation` | 27 | Run asymmetric evidence deliberation, adversarial challenge, stability analysis, attestation, and Passport issuance. |
| `memory_recall` | 8 | Retrieve prior context under explicit purpose, consent, scope, redaction and receipts. |
| `plugin_bootstrap` | 12 | Initialize a native host session without surrendering authority to host chat state. |
| `plugin_release` | 16 | Build, test, audit, sign and package the native plugin without overstating implementation maturity. |
| `plugin_upgrade_migration` | 12 | Upgrade or roll back the plugin with package verification, hook trust, migration dry-run and replay. |
| `red_queen_challenge_coevolution` | 14 | Co-evolve a diverse falsifier population against hypotheses without turning attacks into authority. |
| `shinka_backend_qualification` | 13 | Qualify ShinkaEvolve as an optional executable-program search backend behind Foundry authority. |
| `skill_acquisition` | 12 | Discover and activate third-party skills through a supply-chain quarantine and lockfile. |
| `validation_execution` | 13 | Screen an optional validation target, preregister and authorize a plan, execute it safely, and reconcile typed evidence. |
| `verifier_firewall_qualification` | 14 | Qualify evaluators as fallible scientific instruments before they can score candidates. |
| `workspace_mapping` | 10 | Create auditable code, research, artifact and authority maps with real baseline and query-specific rankings. |

Total: **23 workflows / 350 nodes**.

Every fan-in validates expected count and identity. Every cycle has a LoopContract or an explicit external generation loop with seen-set, budget, dry rounds and stop certificate.

---

# Part XIII — A–Z implementation graph

## 37. Execution rules

- Work in dependency order.
- Parallel work requires frozen shared contracts, disjoint writes, independent tests and no shared exclusive resource.
- Default write concurrency is 4; read concurrency is 8; hard role cap is 16.
- Authors never approve their own packages.
- Existing x04 packages are v3-foundation checkpoints; x06 packages are v4 evolution-integration checkpoints.
- Missing evaluator, holdout, statistical family or authority semantics returns `SPEC_GAP`.
- Missing external capability/credential/licensed data returns `BLOCKED`.
- Leakage, reward hacking, silent missing worker, unreconciled effect or non-waivable integrity failure returns `FAIL`.

## 38. Full package inventory

## A — Authority and architecture

- **A01 — Authority chain, repository constitution and status vocabulary**  
  Dependencies: `none` · Risk: `critical` · Review: `required`
- **A02 — Product invariants and non-goals**  
  Dependencies: `A01` · Risk: `medium` · Review: `required`
- **A03 — Architecture decision records and boundary map**  
  Dependencies: `A01` · Risk: `medium` · Review: `required`
- **A04 — A-phase integration and independent architecture review**  
  Dependencies: `A02, A03` · Risk: `critical` · Review: `required`
- **A05 — Evolution authority boundary and scientific promotion charter**  
  Dependencies: `A04` · Risk: `critical` · Review: `required`
- **A06 — Independent constitutional audit of evolution authority and non-mutable surfaces**  
  Dependencies: `A05` · Risk: `critical` · Review: `required`

## B — Build and reproducibility

- **B01 — Polyglot monorepo scaffold and package boundaries**  
  Dependencies: `A04` · Risk: `medium` · Review: `required`
- **B02 — Pinned toolchains, lockfiles and deterministic build**  
  Dependencies: `B01` · Risk: `medium` · Review: `required`
- **B03 — Cross-platform CI and cache policy**  
  Dependencies: `B01` · Risk: `medium` · Review: `required`
- **B04 — B-phase build gate**  
  Dependencies: `B02, B03` · Risk: `medium` · Review: `required`
- **B05 — Deterministic v4 build, dependency pinning and Shinka optional-feature profile**  
  Dependencies: `A06, B04` · Risk: `high` · Review: `required`
- **B06 — Reproducible build and backend-pin integration gate**  
  Dependencies: `B05, C05, S05` · Risk: `critical` · Review: `required`

## C — Canonical contracts and code generation

- **C01 — v4 JSON Schema and OpenAPI authority**  
  Dependencies: `A04, A05` · Risk: `critical` · Review: `required`
- **C02 — TypeScript, Python and UI model generation**  
  Dependencies: `C01` · Risk: `medium` · Review: `required`
- **C03 — Compatibility windows and schema migration contracts**  
  Dependencies: `C01` · Risk: `medium` · Review: `required`
- **C04 — C-phase contract conformance gate**  
  Dependencies: `C02, C03` · Risk: `critical` · Review: `required`
- **C05 — Evolution genome, evaluator, archive, statistics and adapter schema implementation**  
  Dependencies: `A06, C04` · Risk: `critical` · Review: `required`
- **C06 — Generated types, fixtures and compatibility integration gate**  
  Dependencies: `C05` · Risk: `critical` · Review: `required`

## D — Durable state and artifacts

- **D01 — SQLite WAL local canonical store**  
  Dependencies: `B04, C04` · Risk: `critical` · Review: `required`
- **D02 — PostgreSQL team store and tenant isolation**  
  Dependencies: `D01` · Risk: `medium` · Review: `required`
- **D03 — Content-addressed artifact store and receipts**  
  Dependencies: `D01` · Risk: `medium` · Review: `required`
- **D04 — D-phase backup, corruption and recovery gate**  
  Dependencies: `D02, D03` · Risk: `critical` · Review: `required`
- **D05 — Lineage, quality-diversity archive, island and checkpoint transactional store**  
  Dependencies: `A06, D04, C05` · Risk: `critical` · Review: `required`
- **D06 — Archive migration, crash recovery and atomic checkpoint integration gate**  
  Dependencies: `D05, E05` · Risk: `critical` · Review: `required`

## E — Events, effects and capabilities

- **E01 — Append-only Noetic Ledger and reducer**  
  Dependencies: `C04, D04` · Risk: `critical` · Review: `required`
- **E02 — ActionIntent, Attempt and EffectReceipt**  
  Dependencies: `E01` · Risk: `medium` · Review: `required`
- **E03 — Capability leases, fencing and approval policy**  
  Dependencies: `E01` · Risk: `medium` · Review: `required`
- **E04 — E-phase strict and semantic replay gate**  
  Dependencies: `E02, E03` · Risk: `critical` · Review: `required`
- **E05 — Candidate action/effect, mutation receipt and count-reconciliation engine**  
  Dependencies: `A05, A06, C05, E02, E03, E04` · Risk: `high` · Review: `required`
- **E06 — Concurrent candidate effect and idempotency integration gate**  
  Dependencies: `E05` · Risk: `critical` · Review: `required`

## F — FORGE lifecycle

- **F01 — E0-E5 epistemic work classifier**  
  Dependencies: `C04, E04` · Risk: `critical` · Review: `required`
- **F02 — FORGE FSM and legal return edges**  
  Dependencies: `F01` · Risk: `medium` · Review: `required`
- **F03 — Artifact-receipt transition gates**  
  Dependencies: `F01` · Risk: `medium` · Review: `required`
- **F04 — F-phase end-to-end E1/E3/E5 flows**  
  Dependencies: `F02, F03` · Risk: `critical` · Review: `required`
- **F05 — EVOLVE subprotocol state machine, return edges and typed stop certificates**  
  Dependencies: `A06, F04, C05` · Risk: `critical` · Review: `required`
- **F06 — FORGE–EVOLVE lifecycle integration and replay gate**  
  Dependencies: `F05, I05, R05` · Risk: `critical` · Review: `required`

## G — Plugin package and gateway

- **G01 — Native plugin manifest and package layout**  
  Dependencies: `B04, C04, S01` · Risk: `high` · Review: `required`
- **G02 — Payload-resident efoundry dispatcher**  
  Dependencies: `G01` · Risk: `high` · Review: `required`
- **G03 — PLUGIN_ROOT/PLUGIN_DATA and workspace resolution**  
  Dependencies: `G01` · Risk: `high` · Review: `required`
- **G04 — G-phase local marketplace fresh-install gate**  
  Dependencies: `G02, G03` · Risk: `high` · Review: `required`
- **G05 — Evolution plugin skills, CLI surface and progressive-disclosure routing**  
  Dependencies: `A06, G04, C05` · Risk: `high` · Review: `required`
- **G06 — Native plugin packaging and skill-discovery integration gate**  
  Dependencies: `G05, H05, T05` · Risk: `critical` · Review: `required`

## H — Host hooks and capability negotiation

- **H01 — Normalized Hook Gateway and event envelopes**  
  Dependencies: `E04, G04, S02` · Risk: `critical` · Review: `required`
- **H02 — Session and prompt lifecycle hooks**  
  Dependencies: `H01` · Risk: `medium` · Review: `required`
- **H03 — Tool and delegation hooks**  
  Dependencies: `H01` · Risk: `medium` · Review: `required`
- **H04 — Hook feature probe, trust and degraded-mode gate**  
  Dependencies: `H02, H03` · Risk: `critical` · Review: `required`
- **H05 — Evolution/holdout observability hooks with explicit coverage limits**  
  Dependencies: `G05, H04` · Risk: `high` · Review: `required`
- **H06 — Hook-disabled and hosted-tool degraded-mode integration gate**  
  Dependencies: `H05, G05` · Risk: `critical` · Review: `required`

## I — Intake and research framing

- **I01 — Bounded Interview and contradiction scan**  
  Dependencies: `C04, F04` · Risk: `medium` · Review: `required`
- **I02 — InsightCard, falsifier and ScopeVector compiler**  
  Dependencies: `I01` · Risk: `medium` · Review: `required`
- **I03 — Ontology and measurement construct resolution**  
  Dependencies: `I01` · Risk: `medium` · Review: `required`
- **I04 — I-phase intake UX and export gate**  
  Dependencies: `I02, I03` · Risk: `medium` · Review: `required`
- **I05 — HypothesisGenome intake, seed population bootstrap and eligibility screening**  
  Dependencies: `F05, I04, C05` · Risk: `high` · Review: `required`
- **I06 — Genome intake, scope and falsifiability integration gate**  
  Dependencies: `I05, R05` · Risk: `critical` · Review: `required`

## J — Just-in-time skills and context

- **J01 — Parent skill router and trigger boundaries**  
  Dependencies: `C04, G04, H01, S03` · Risk: `medium` · Review: `required`
- **J02 — Progressive references and context budgets**  
  Dependencies: `J01` · Risk: `medium` · Review: `required`
- **J03 — ContextCapsule assembly and exclusions**  
  Dependencies: `J01` · Risk: `medium` · Review: `required`
- **J04 — Post-compaction recovery gate**  
  Dependencies: `J02, J03` · Risk: `medium` · Review: `required`
- **J05 — Typed mutation-operator registry, prompt genomes and quarantine workflow**  
  Dependencies: `I05, J04, C05` · Risk: `high` · Review: `required`
- **J06 — Operator/prompt qualification and context-budget integration gate**  
  Dependencies: `J05, S05` · Risk: `critical` · Review: `required`

## K — Knowledge and corpus ingest

- **K01 — Document registry, versions, licensing and trust**  
  Dependencies: `B04, C04, D04, S01` · Risk: `medium` · Review: `required`
- **K02 — GROBID/Docling and fallback parser adapters**  
  Dependencies: `K01` · Risk: `medium` · Review: `required`
- **K03 — SourceSpan emission for text/table/figure/formula**  
  Dependencies: `K01` · Risk: `medium` · Review: `required`
- **K04 — K-phase ingest quality and prompt-injection gate**  
  Dependencies: `K02, K03` · Risk: `medium` · Review: `required`
- **K05 — Corpus/evidence snapshot pinning, hidden holdout and prior-art boundaries**  
  Dependencies: `K04, S05, C05` · Risk: `high` · Review: `required`
- **K06 — Evidence/holdout version and leakage-prevention integration gate**  
  Dependencies: `K05, O05` · Risk: `critical` · Review: `required`

## L — Local memory and recall

- **L01 — Memory classes, consent and retention policy**  
  Dependencies: `D04, H02, J04, S02` · Risk: `medium` · Review: `required`
- **L02 — Memory indexing and scoped retrieval**  
  Dependencies: `L01` · Risk: `medium` · Review: `required`
- **L03 — Redaction, dedupe, forget and legal hold**  
  Dependencies: `L01` · Risk: `medium` · Review: `required`
- **L04 — L-phase recall quality/privacy gate**  
  Dependencies: `L02, L03` · Risk: `medium` · Review: `required`
- **L05 — Lineage memory, negative-result retention and evolution forget/export policies**  
  Dependencies: `L04, D05` · Risk: `high` · Review: `required`
- **L06 — Memory retention, deletion and legal-hold integration gate**  
  Dependencies: `L05, D05` · Risk: `critical` · Review: `required`

## M — Workspace Cartographer

- **M01 — Typed inventory and dependency extraction**  
  Dependencies: `B04, C04, D04, J04, K04` · Risk: `medium` · Review: `required`
- **M02 — Real baseline centrality and graph algorithms**  
  Dependencies: `M01` · Risk: `medium` · Review: `required`
- **M03 — Query personalization, risk and change impact**  
  Dependencies: `M01` · Risk: `medium` · Review: `required`
- **M04 — M-phase map UI and ranking-claim gate**  
  Dependencies: `M02, M03` · Risk: `medium` · Review: `required`
- **M05 — Epistemic niche mapper, lineage map and evolution blast-radius cartography**  
  Dependencies: `M04, D05` · Risk: `high` · Review: `required`
- **M06 — Map correctness, ranking separation and stale-propagation integration gate**  
  Dependencies: `M05` · Risk: `critical` · Review: `required`

## N — Nodes, agents and graph execution

- **N01 — Canonical RoleSpec and evidence/tool ACLs**  
  Dependencies: `C04, E04, G04, H04, J04` · Risk: `high` · Review: `required`
- **N02 — Codex/Claude role compilation and spawn adapters**  
  Dependencies: `N01` · Risk: `high` · Review: `required`
- **N03 — DAG scheduler, leases, retries and concurrency**  
  Dependencies: `N01` · Risk: `high` · Review: `required`
- **N04 — N-phase fan-in, missing-node and independent-review gate**  
  Dependencies: `N02, N03` · Risk: `high` · Review: `required`
- **N05 — Bounded asynchronous proposal/evaluation/persistence lanes and scheduler**  
  Dependencies: `N04, E05, F05` · Risk: `high` · Review: `required`
- **N06 — Backpressure, missing-worker and resource-lock integration gate**  
  Dependencies: `N05` · Risk: `critical` · Review: `required`

## O — Observe and evidence retrieval

- **O01 — QueryPlan and SearchLaneReceipt contracts**  
  Dependencies: `I04, K04, M04` · Risk: `medium` · Review: `required`
- **O02 — Lexical, semantic, citation and relation retrieval**  
  Dependencies: `O01` · Risk: `medium` · Review: `required`
- **O03 — Dependency clusters and Evidence Pack assembly**  
  Dependencies: `O01` · Risk: `medium` · Review: `required`
- **O04 — O-phase absence and completeness gate**  
  Dependencies: `O02, O03` · Risk: `medium` · Review: `required`
- **O05 — Evolution evidence retrieval, multi-layer novelty and coverage-debt acquisition**  
  Dependencies: `O04, K05, C05` · Risk: `high` · Review: `required`
- **O06 — Search-completeness, novelty-failure and prior-art integration gate**  
  Dependencies: `O05, Q05` · Risk: `critical` · Review: `required`

## P — Evidence Parliament

- **P01 — Blind independent briefs and asymmetric dispatch**  
  Dependencies: `N04, O04, R04` · Risk: `critical` · Review: `required`
- **P02 — Method, scope, causal and novelty audits with veto**  
  Dependencies: `P01` · Risk: `medium` · Review: `required`
- **P03 — Cross-examination and Minority Report**  
  Dependencies: `P01` · Risk: `medium` · Review: `required`
- **P04 — P-phase judge and independent attestation gate**  
  Dependencies: `P02, P03` · Risk: `critical` · Review: `required`
- **P05 — Evolution promotion Parliament, Red Queen evidence and minority-lineage review**  
  Dependencies: `P04, O05, Q05, R05` · Risk: `critical` · Review: `required`
- **P06 — No-majority promotion and sealed-candidate attestation integration gate**  
  Dependencies: `P05, V05` · Risk: `critical` · Review: `required`

## Q — Quality, evaluation and calibration

- **Q01 — Gold corpus and annotation protocol**  
  Dependencies: `K04, O04, P04, R04` · Risk: `medium` · Review: `required`
- **Q02 — Parser, Claim and grounding evaluation**  
  Dependencies: `Q01` · Risk: `medium` · Review: `required`
- **Q03 — Retrieval, verdict and calibration evaluation**  
  Dependencies: `Q01` · Risk: `medium` · Review: `required`
- **Q04 — Q-phase time-sliced and adversarial benchmark gate**  
  Dependencies: `Q02, Q03` · Risk: `medium` · Review: `required`
- **Q05 — Multi-objective fitness, hidden evaluation, multiplicity and selective inference**  
  Dependencies: `Q04, O05, C05` · Risk: `critical` · Review: `required`
- **Q06 — Calibration, winner-curse and statistical-governance integration gate**  
  Dependencies: `Q05, V05` · Risk: `critical` · Review: `required`

## R — Reasoning and Aporia

- **R01 — Inductive synthesis and heterogeneity engine**  
  Dependencies: `C04, O04` · Risk: `high` · Review: `required`
- **R02 — Deductive proof trace and assumption ledger**  
  Dependencies: `R01` · Risk: `high` · Review: `required`
- **R03 — Abduction, contradiction and moderator engine**  
  Dependencies: `R01` · Risk: `high` · Review: `required`
- **R04 — R-phase causal identification and ArgumentGraph gate**  
  Dependencies: `R02, R03` · Risk: `high` · Review: `required`
- **R05 — Scientific mutation, typed crossover, mechanism and Aporia operators**  
  Dependencies: `R04, I05, C05` · Risk: `high` · Review: `required`
- **R06 — Causal/measurement/scope crossover safety integration gate**  
  Dependencies: `R05` · Risk: `critical` · Review: `required`

## S — Security, privacy and skill supply chain

- **S01 — Trust-zone enforcement and document injection defense**  
  Dependencies: `A04, B01` · Risk: `critical` · Review: `required`
- **S02 — Secrets, path, sandbox and egress controls**  
  Dependencies: `S01` · Risk: `medium` · Review: `required`
- **S03 — Skill Vault quarantine and SkillLockfile**  
  Dependencies: `S01` · Risk: `medium` · Review: `required`
- **S04 — S-phase threat model and red-team gate**  
  Dependencies: `S02, S03` · Risk: `critical` · Review: `required`
- **S05 — Verifier Firewall, prompt/evaluator quarantine and executable-candidate threat controls**  
  Dependencies: `S04, A06, C05` · Risk: `critical` · Review: `required`
- **S06 — Leakage, reward-hacking and evaluator-update governance integration gate**  
  Dependencies: `S05, J05` · Risk: `critical` · Review: `required`

## T — Tools, MCP, CLI and sandbox

- **T01 — MCP read/planning tools**  
  Dependencies: `E04, G04, S04` · Risk: `high` · Review: `required`
- **T02 — MCP mutating tools with intents and receipts**  
  Dependencies: `T01, E02, E03, F01, F04` · Risk: `high` · Review: `required`
- **T03 — Stable CLI JSON/error and PATH-less surfaces**  
  Dependencies: `T01, T02, J02` · Risk: `high` · Review: `required`
- **T04 — T-phase sandbox and external tool adapter gate**  
  Dependencies: `T02, T03` · Risk: `high` · Review: `required`
- **T05 — Evolution CLI/MCP tools, sandbox executors and Shinka backend adapter**  
  Dependencies: `T04, S05, G05` · Risk: `high` · Review: `required`
- **T06 — External-backend qualification and fallback integration gate**  
  Dependencies: `T05` · Risk: `critical` · Review: `required`

### T02 additive FORGE public mutation contract

- T01 remains the sealed thirteen-tool read/planning catalog. T02 v1.1 contains
  exactly eleven mutating tools, and the composed catalog contains exactly
  twenty-four tools. The two additions are appended so the original
  thirteen-plus-nine names and ordering remain stable.
- `foundry.work.classify` (`mutate_work_classify`) and
  `foundry.session.open` (`mutate_session_open`) are separate durable
  operations. They may not be collapsed into a composite because F01 and F04
  have distinct idempotency, outbox, ledger, retry, and reconciliation
  boundaries.
- Classification requires `mcp.write.classification`; session OPEN reuses
  `mcp.write.session`. Both are `medium` risk and `POLICY_CONDITIONAL`, and
  both require the common outer `expected_revision` field to be null.
- The classification arguments are the existing F01 classification input.
  Session OPEN accepts only caller-owned OPEN values; its worker derives
  `request_id`, `run_spec_id`, and `policy_hash` from the sealed F01 replay
  projection, derives `workspace_id` and `idempotency_key` from the common
  mutation envelope, and obtains the current E01 ledger head immediately
  before the F04 call. A caller never supplies or relabels those authoritative
  values.
- F01 human override is not exposed by this additive surface. It remains a
  separate human-authority operation if a later product requirement needs it.
- T03 projects the composed catalog for CLI commands only after T02 is frozen.
  The installed surface switches atomically from the sealed T01 thirteen-tool
  profile to the composed twenty-four-tool profile only after X01 binds both
  new mutation runtimes; until then, unbound tools remain explicit
  `UNAVAILABLE` results.

## U — Foundry Console and API

- **U01 — OpenAPI server and generated clients**  
  Dependencies: `C04, T04` · Risk: `medium` · Review: `required`
- **U02 — Dashboard shell, auth and explicit health states**  
  Dependencies: `U01` · Risk: `medium` · Review: `required`
- **U03 — Atlas, Parliament, Aporia and Passport views**  
  Dependencies: `U01` · Risk: `medium` · Review: `required`
- **U04 — U-phase accessibility and packaged-path parity gate**  
  Dependencies: `U02, U03` · Risk: `medium` · Review: `required`
- **U05 — Evolution Chamber console: Pareto, niches, lineages, challenges and operator controls**  
  Dependencies: `U04, M05, G05` · Risk: `high` · Review: `required`
- **U06 — Honest degraded UI and operator usability integration gate**  
  Dependencies: `U05` · Risk: `critical` · Review: `required`

## V — Validation Bay

- **V01 — ValidationTarget manifests and eligibility**  
  Dependencies: `E04, F04, R04, T04` · Risk: `high` · Review: `required`
- **V02 — Preregistered ValidationPlan and falsification rules**  
  Dependencies: `V01` · Risk: `high` · Review: `required`
- **V03 — Capability-controlled execution and receipts**  
  Dependencies: `V01` · Risk: `high` · Review: `required`
- **V04 — V-phase result reconciliation and evidence-class gate**  
  Dependencies: `V02, V03` · Risk: `high` · Review: `required`
- **V05 — Validation cascade, OOD challenge, independent replication and promotion ceiling**  
  Dependencies: `V04, S05, Q05, R05` · Risk: `critical` · Review: `required`
- **V06 — Experiment/replication end-to-end integration gate**  
  Dependencies: `V05, P05, Q05` · Risk: `critical` · Review: `required`

## W — Workflow, checkpoints and reassessment

- **W01 — Workflow compiler and NodeContract validator**  
  Dependencies: `D04, E04, F04, N04` · Risk: `high` · Review: `required`
- **W02 — Checkpoint, pause, resume and cancellation**  
  Dependencies: `W01` · Risk: `high` · Review: `required`
- **W03 — Evidence updates, staleness and reassessment**  
  Dependencies: `W01` · Risk: `high` · Review: `required`
- **W04 — W-phase replay, drift and audit export gate**  
  Dependencies: `W02, W03` · Risk: `high` · Review: `required`
- **W05 — Evolution checkpoint/resume/cancel, evaluator drift and reassessment workflow**  
  Dependencies: `W04, D05, F05, N05` · Risk: `critical` · Review: `required`
- **W06 — Crash recovery, future-only evaluator update and replay integration gate**  
  Dependencies: `W05, D06, N06` · Risk: `critical` · Review: `required`

## X — Cross-provider adapters

- **X01 — Codex plugin, hooks and subagent adapter**  
  Dependencies: `G04, N04, T04, W04` · Risk: `high` · Review: `required`
- **X02 — Claude Code skills, agents and worktree adapter**  
  Dependencies: `X01` · Risk: `high` · Review: `required`
- **X03 — Model routing and fallback policy**  
  Dependencies: `X01` · Risk: `high` · Review: `required`
- **X04 — X-phase cross-provider parity and diversity gate**  
  Dependencies: `X02, X03` · Risk: `high` · Review: `required`
- **X05 — Cross-provider mutation routing, safe delayed-reward bandit and fallback**  
  Dependencies: `X04, N05, T05` · Risk: `high` · Review: `required`
- **X06 — Provider diversity, cost, safety and reward-attribution integration gate**  
  Dependencies: `X05` · Risk: `critical` · Review: `required`

## Y — Yield, operations and scale

- **Y01 — Typed budgets, adaptive fleet and performance controls**  
  Dependencies: `B04, D04, Q04, W04, X04` · Risk: `high` · Review: `required`
- **Y02 — Observability, SLOs and privacy-safe telemetry**  
  Dependencies: `Y01` · Risk: `high` · Review: `required`
- **Y03 — Backup, disaster recovery and operational runbooks**  
  Dependencies: `Y01` · Risk: `high` · Review: `required`
- **Y04 — Y-phase 50/200/2000 corpus scale qualification**  
  Dependencies: `Y02, Y03` · Risk: `high` · Review: `required`
- **Y05 — Quality-diversity scaling, surrogate triage, budgets and production load**  
  Dependencies: `Y04, N05, Q05, X05` · Risk: `high` · Review: `required`
- **Y06 — 2,000-document evolution qualification and cost/latency integration gate**  
  Dependencies: `Y05` · Risk: `critical` · Review: `required`

## Z — Zero-trust release and lifecycle

- **Z01 — Fresh-install, compatibility and uninstall matrix**  
  Dependencies: `G04, H04, L04, M04, P04, Q04, S04, T04, U04, V04, W04, X04, Y04` · Risk: `critical` · Review: `required`
- **Z02 — SBOM, signing, provenance and deterministic bundle**  
  Dependencies: `Z01` · Risk: `medium` · Review: `required`
- **Z03 — Upgrade, downgrade, migration and rollback matrix**  
  Dependencies: `Z01` · Risk: `medium` · Review: `required`
- **Z04 — Final independent release gate and architecture freeze**  
  Dependencies: `Z02, Z03` · Risk: `critical` · Review: `required`
- **Z05 — Zero-trust v4 release, 288-lens audit, migration and signing provenance**  
  Dependencies: `Z04, B05, S05, T05, Y05` · Risk: `critical` · Review: `required`
- **Z06 — Independent release, clean extraction and truthful maturity gate**  
  Dependencies: `Z05, B06, C06, F06, G06, K06, N06, P06, Q06, S06, T06, V06, W06, Y06` · Risk: `critical` · Review: `required`

Total: **156 work packages**, dependency-checked in `manifests/development_manifest.yaml`.

---

# Part XIV — Data and contract inventory

## 39. Canonical schemas

Total: **127 Draft 2020-12 strict schemas** and **127 matching examples**.

- **A:** `action-intent.schema.json`, `adjudication.schema.json`, `approval-record.schema.json`, `archive-rebalance-plan.schema.json`, `argument-graph.schema.json`, `artifact-manifest.schema.json`, `artifact-receipt.schema.json`, `attestation.schema.json`
- **B:** `backend-adapter-qualification.schema.json`, `bias-risk-register.schema.json`, `budget-envelope.schema.json`
- **C:** `calibration-report.schema.json`, `candidate-generation-record.schema.json`, `candidate-lineage.schema.json`, `capability-lease.schema.json`, `challenge-genome.schema.json`, `challenge-result.schema.json`, `checkpoint-manifest.schema.json`, `claim-card.schema.json`, `claim-lifecycle-event.schema.json`, `compatibility-matrix.schema.json`, `consent-record.schema.json`, `context-assembly-manifest.schema.json`, `context-capsule.schema.json`, `council-brief.schema.json`, `coverage-snapshot.schema.json`, `cross-examination.schema.json`, `crossover-compatibility-report.schema.json`
- **D:** `decision-stability-report.schema.json`, `document-manifest.schema.json`, `document-registration-request.schema.json`, `document-registration.schema.json`, `domain-pack.schema.json`
- **E:** `effect-receipt.schema.json`, `epistemic-archive-entry.schema.json`, `epistemic-niche.schema.json`, `epistemic-utility-report.schema.json`, `epistemic-work-classification.schema.json`, `evaluation-run.schema.json`, `evaluator-bundle.schema.json`, `evaluator-mutation-proposal.schema.json`, `evaluator-qualification-report.schema.json`, `event-record.schema.json`, `evidence-dependency-cluster.schema.json`, `evidence-node.schema.json`, `evidence-pack.schema.json`, `evidence-reconciliation-record.schema.json`, `evolution-checkpoint.schema.json`, `evolution-run-spec.schema.json`, `evolution-stop-certificate.schema.json`, `experiment-genome.schema.json`, `experiment-result.schema.json`, `experiment-ticket.schema.json`
- **F:** `falsifier-gene.schema.json`, `fitness-evidence-receipt.schema.json`, `fitness-vector.schema.json`, `forge-session-state.schema.json`, `forge-transition-request.schema.json`
- **G:** `gate-decision.schema.json`
- **H:** `holdout-manifest.schema.json`, `hook-event-envelope.schema.json`, `host-capability-report.schema.json`, `human-decision.schema.json`, `hypothesis-genome.schema.json`, `hypothesis-passport.schema.json`
- **I:** `imported-run-record.schema.json`, `insight-card.schema.json`, `island-state.schema.json`
- **L:** `leakage-audit.schema.json`, `lineage-diversity-report.schema.json`, `loop-contract.schema.json`
- **M:** `measurement-compatibility-report.schema.json`, `mechanism-graph.schema.json`, `memory-policy.schema.json`, `memory-retrieval-receipt.schema.json`, `minority-report.schema.json`, `model-routing-receipt.schema.json`, `multiple-testing-adjustment.schema.json`, `mutation-operator-spec.schema.json`, `mutation-receipt.schema.json`
- **N:** `node-contract.schema.json`, `node-invocation.schema.json`, `novelty-assessment.schema.json`, `novelty-vector.schema.json`
- **O:** `operator-bandit-state.schema.json`
- **P:** `parent-selection-receipt.schema.json`, `pareto-front-snapshot.schema.json`, `phase-artifact-set.schema.json`, `plugin-capability-manifest.schema.json`, `plugin-health-report.schema.json`, `plugin-install-state.schema.json`, `plugin-policy-pack.schema.json`, `plugin-release-provenance.schema.json`, `policy-bundle.schema.json`, `prediction-gene.schema.json`, `promotion-decision.schema.json`, `prompt-genome.schema.json`, `prompt-mutation-proposal.schema.json`
- **Q:** `quality-diversity-map.schema.json`, `query-plan.schema.json`
- **R:** `red-queen-round.schema.json`, `replay-report.schema.json`, `replication-plan.schema.json`, `replication-result.schema.json`, `result-envelope.schema.json`, `retrieval-candidate.schema.json`, `retrieval-run.schema.json`, `role-dispatch-plan.schema.json`, `run-spec.schema.json`
- **S:** `schema-migration.schema.json`, `scope-vector.schema.json`, `search-completeness-certificate.schema.json`, `search-lane-receipt.schema.json`, `selective-inference-report.schema.json`, `sequential-testing-ledger.schema.json`, `shinka-backend-manifest.schema.json`, `skill-lockfile.schema.json`, `skill-routing-decision.schema.json`, `source-integrity-report.schema.json`, `source-span.schema.json`, `stage-evaluation-result.schema.json`, `surrogate-triage-report.schema.json`
- **U:** `update-impact-report.schema.json`
- **V:** `validation-cascade-plan.schema.json`, `validation-plan.schema.json`, `validation-target-manifest.schema.json`
- **W:** `workspace-map-snapshot.schema.json`

## 40. Roles, prompts and plugin assets

- canonical roles: **28**
- semantic/extraction/evolution prompts: **65**
- reference plugin skills: **29**
- hook bundles: **7**
- architecture audit: **288 lenses = 264 PASS / 24 CONDITIONAL / 0 FAIL**

The audit is a structured failure-surface matrix, not 288 independent agents or proofs.

---

# Part XV — Evaluation, release and migration

## 41. Release ladder

```text
SPEC_BUNDLE
→ PLUGIN_ALPHA
→ EVOLUTION_MVP_50
→ PILOT_200
→ PRODUCTION_2000
→ CROSS_DOMAIN_QUALIFIED
```

Only `manifests/acceptance_matrix.yaml` selects the release level.

## 42. Required baselines

- single-agent generation;
- v3 Parliament without evolution;
- scalar best-of-N;
- program search with one public evaluator;
- Pareto without Red Queen;
- quality-diversity without hidden holdout;
- full v4.

Improvement claims require preregistered metrics, hidden evaluation, uncertainty and cost.

## 43. v3 migration

v3 Claims, Evidence, Passports, Parliament, Validation and Ledger remain valid. v4 adds candidate genomes, evaluator/holdout, fitness, niches, challenge, statistics and replication as new linked objects. Historical hashes are never rewritten.

## 44. Reproducible release

A release requires:

```text
schema/example validation
→ workflow and work-graph validation
→ security/statistical/adversarial suites
→ 288-lens audit
→ reference-blueprint fail-closed check
→ deterministic archive build
→ clean extraction/hash comparison
→ independent attestation
→ truthful release label
→ signature or explicit unsigned status
```

---

# Part XVI — Failure modes and non-goals

## 45. Major failure modes

- verifier overfitting and reward hacking;
- hidden-holdout leakage through aggregate feedback;
- scalar Goodhart pressure;
- code novelty mistaken for scientific novelty;
- fluent but unfalsifiable hypotheses;
- semantic crossover without compatibility;
- best-of-many winner's curse;
- archive erasure of negative results;
- challenge overfit or irrelevant exploits;
- prompt self-modification acquiring authority;
- missing async worker hidden in fan-in;
- external backend version drift;
- same-context rerun mislabeled replication;
- association relabeled causation;
- simulation relabeled empirical confirmation.

Each has a canonical control and test.

## 46. Explicit non-goals

v4 does not:

- guarantee truth or autonomous scientific discovery;
- equate novelty with value or support;
- use agent majority as evidence;
- let candidates rewrite current evaluators;
- expose hidden holdouts;
- promote from one scalar;
- treat every domain as having the same statistical policy;
- require ShinkaEvolve;
- claim production performance from this specification;
- replace expert judgment, ethics review or experimental validation.

## 47. Final architecture freeze

```text
SHINKAEVOLVE SOURCE STUDY: COMPLETE WITH PUBLIC-SOURCE BOUNDARY
V4 SPECIFICATION STRUCTURE: DEFINED
EVOLUTION AUTHORITY SEPARATION: DEFINED
VERIFIER FIREWALL: DEFINED
QUALITY-DIVERSITY / RED QUEEN / STATISTICAL GOVERNANCE: DEFINED
A–Z IMPLEMENTATION GRAPH: DEFINED
PRODUCTION READINESS (NOT CLAIMED): NONE
IMPLEMENTATION TARGET: PLUGIN_ALPHA — AUTHORIZED, NOT COMPLETE

ARCHITECTURE FREEZE: CONDITIONAL PASS
CURRENT QUALIFIED BUNDLE STATUS: SPEC_BUNDLE
```

Conditional items are external implementation and deployment evidence: licensed corpus, qualified evaluator/holdout, expert gold labels, statistical policy, sandbox/DB/queue topology, exact Shinka revision, provider credentials/metering, signing identity, independent security review, host compatibility and real 50/200/2,000-scale results.
