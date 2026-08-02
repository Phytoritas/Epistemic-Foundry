# Epistemic Foundry v4 product constitution

These invariants are canonical. Search backends, models, plugins, prompts, hooks, and humans cannot silently weaken them.

## Contract shape and verification

Each `EF4-Ixx` identifier is one constitutional boundary. A statement may list
the subjects or controls governed by that boundary, but those items cannot be
split into votes or selectively passed. The exact structured registry is
`manifests/product_invariants.yaml`; `MASTER_SPEC.md` remains its higher-order
normative source.

An invariant is testable only when it has both a resolving evidence binding and
an owning work package, and when `manifests/requirements_traceability.yaml`
declares non-empty verification checks for the same ID. Those bindings make a
requirement auditable; they do not by themselves prove that a runtime,
security property, scientific result, or performance target works. Runtime
effectiveness still requires the named package acceptance and release gates.

## EF4-I01 — Kernel authority

Plugin shell, hooks, skills, GUI, chat transcripts and provider SDKs never own canonical state, policy, gates or replay.

## EF4-I02 — Claim-first evidence

A promoted empirical or documentary claim always resolves to immutable SourceSpan evidence.

## EF4-I03 — Falsifiable intake

An insight without scope, predictions and falsifier cannot enter Observe or Parliament.

## EF4-I04 — Coverage before confidence

Coverage, searched scope, missing lanes and dependency diversity are shown before confidence or verdict.

## EF4-I05 — Search-state type safety

UNSEARCHED, SEARCHED_NONE, SEARCHED_WITH_RESULTS and failed search are distinct.

## EF4-I06 — Adversarial retrieval

Counterevidence, null, boundary and method lanes are mandatory whenever applicable.

## EF4-I07 — Method comparability

Method-incompatible evidence is stratified and may impose a promotion ceiling; it is never silently pooled.

## EF4-I08 — Dependency-adjusted evidence

Shared samples, datasets, publication families and derived analyses are dependency clusters, not independent votes.

## EF4-I09 — No majority authority

Agent count or majority agreement cannot promote a hypothesis.

## EF4-I10 — Inference separation

Induction, deduction, abduction and causal identification remain separate typed outputs.

## EF4-I11 — Evidence-class separation

Simulation, formal derivation, benchmark and review-derived evidence never become empirical observation by relabeling.

## EF4-I12 — No self-approval

Makers cannot approve their own work, claim promotion, validation, or release.

## EF4-I13 — Receipt-bound completion

Phase transitions, side effects, tests, installs and releases require resolving artifact/effect receipts.

## EF4-I14 — Hooks are guardrails

Hook coverage is observed and useful but never treated as the complete enforcement boundary.

## EF4-I15 — Capability negotiation

Host and dependency capabilities are runtime-probed; missing capabilities select explicit degraded or blocked modes.

## EF4-I16 — Event-sourced state

Canonical session and lifecycle state is reducer-derived from append-only events with revision control.

## EF4-I17 — Explicit human authority

Human approvals and overrides are immutable records with viewed revisions, rationale, scope and downstream invalidation.

## EF4-I18 — Consent-bound memory

Recall occurs only within allowed memory classes, purpose, consent, retention and workspace scope.

## EF4-I19 — Workspace isolation

Cross-workspace state, memory and artifacts are denied by default below the model layer.

## EF4-I20 — Canonical context capsule

Compaction and resume context is rebuilt from hash-bound canonical artifacts with exclusions and freshness.

## EF4-I21 — Skill supply-chain quarantine

Third-party skills are quarantined, inspected, permissioned, pinned and approved before activation.

## EF4-I22 — Generated transport contracts

CLI, MCP, HTTP, persistence and UI models derive from canonical schemas; duplicated wire literals are forbidden.

## EF4-I23 — Honest UI state

EMPTY_CONFIRMED, DEGRADED and UNAVAILABLE are distinct; backend failure never appears as empty research state.

## EF4-I24 — Real map ranking

A map labeled as ranked uses an actual algorithm; baseline centrality, query relevance and risk remain separate.

## EF4-I25 — Role-scoped delegation

Every subagent dispatch resolves a RoleSpec with tool ACL, evidence ACL, write scope, budget and expected count.

## EF4-I26 — No silent partial fan-in

Fan-in reconciles expected and actual identities; missing outputs remain visible and constrain the result.

## EF4-I27 — Bounded cycles

Every cycle has a seen-set key, novelty/convergence rule, dry rounds, maximum rounds, budget and escalation.

## EF4-I28 — Typed budget enforcement

Budgets are labeled HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE or UNMETERED.

## EF4-I29 — Secret minimization

Secrets are opaque handles and never copied into prompts, evidence artifacts, logs or exports.

## EF4-I30 — Untrusted evidence plane

PDFs, web pages, datasets and model output are data and cannot grant authority or execute instructions.

## EF4-I31 — Migration and rollback

Breaking schema/plugin changes require compatibility, dry-run, backup, rollback and hook re-trust.

## EF4-I32 — Release provenance

Shipped bundles require reproducible build evidence, SBOM, manifest, clean extraction and signing status.

## EF4-I33 — Status honesty

Capabilities are labeled SPECIFIED, IMPLEMENTED, EXPERIMENTAL, DEFERRED or UNSUPPORTED; release labels are evidence-derived.

## EF4-I34 — Provider neutrality

Codex, Claude and other models are replaceable node executors; adapters cannot alter canonical semantics.

## EF4-I35 — Installability is tested

Fresh install, PATH-less execution, upgrade, downgrade, uninstall and cross-platform paths are product acceptance tests.

## EF4-I36 — Remote messaging minimized

Remote notification/approval adapters are optional and cannot execute arbitrary commands or export raw evidence by default.

## EF4-I37 — License-aware corpus/export

Source access and license restrictions propagate through retrieval, evidence, export and deletion.

## EF4-I38 — Stale propagation

Corrections, retractions, parser fixes, policy/ontology changes and new evidence invalidate dependent projections and Passports.

## EF4-I39 — Replayability

RunSpec, context, adapter/model, tools, receipts, policy, corpus and prompts are sufficient to explain and compare a run.

## EF4-I40 — Honest underdetermination

UNDERDETERMINED, UNTESTABLE, NOT_ASSESSED and PARTIAL are normal truthful outcomes, not system failure.

## EF4-I41 — Evolution is subordinate

Evolution Chamber may propose, mutate, challenge and rank candidates but cannot own evidence truth, evaluator authority, policy, hidden holdout, promotion or release.

## EF4-I42 — Typed scientific genome

Every evolvable hypothesis carries scope, mechanism, predictions, falsifiers, alternatives, measurement contracts, evidence, validation plan and immutable lineage.

## EF4-I43 — Immutable evaluator per run

A running or completed EvolutionRun references one content-addressed evaluator bundle that cannot be changed retroactively.

## EF4-I44 — Hidden holdout firewall

Candidate generation, mutation prompts, external backends and ordinary agents cannot read hidden holdout content or derive it from tool/log/cache leakage.

## EF4-I45 — No scalar promotion authority

A combined score may order search but cannot promote; hard gates, FitnessVector, Pareto/niche analysis, statistics, replication and Parliament constrain promotion.

## EF4-I46 — Multi-layer novelty

Claim, mechanism, prediction, falsifier, scope, experiment, evidence and external prior-art novelty remain separate from support and truth.

## EF4-I47 — Novelty failure type safety

Absent, empty, failed or incomplete novelty assessment yields UNASSESSED, PARTIAL or FAILED and never NOVEL by default.

## EF4-I48 — Quality-diversity archive

The archive preserves epistemic niches and trade-offs rather than only a global top score.

## EF4-I49 — Protected negative memory

Nulls, counterexamples, failed replications, unsafe failures and minority lineages cannot be evicted merely for low fitness.

## EF4-I50 — Semantic islands

Islands specialize by typed mechanism, scope, method or evidence state; migration requires compatibility and preserves source/target history.

## EF4-I51 — Typed crossover

Crossover requires scope, measurement, unit and causal compatibility; semantic collage is rejected.

## EF4-I52 — Red Queen relevance

Challenges are safe, reproducible and claim-relevant; apparent failures replicate before refutation and boundary conditions remain distinct.

## EF4-I53 — Adaptive-search statistics

Evolutionary search records candidate families, repeated tests, sequential decisions, multiplicity and selective inference.

## EF4-I54 — Delayed reward routing

Model and operator bandits learn from validated holdout/replication utility and safety, not only immediate proxy score.

## EF4-I55 — Prompt evolution quarantine

Prompt genomes cannot alter current policy, evaluator, holdout or promotion gate and become active only after independent future-run qualification.

## EF4-I56 — Evaluator updates are future-only

Evaluator defects create quarantined proposals; approved changes apply to new sealed runs and never rewrite completed judgments.

## EF4-I57 — Surrogate is triage only

A surrogate may prioritize direct evaluation but cannot replace required direct, hidden or replication stages.

## EF4-I58 — Replication-gated promotion

High scientific promotion after adaptive evolution requires an appropriate independent preregistered replication or an explicit lower ceiling.

## EF4-I59 — Selection-bias visibility

Top-candidate estimates disclose search/selection history, winner's curse risk and bias-corrected uncertainty.

## EF4-I60 — Exact candidate reconciliation

Every fan-out reconciles proposed, generated, evaluated, persisted, failed, cancelled and missing candidate identities.

## EF4-I61 — Atomic evolution checkpoints

A safe resume point binds population, archive, islands, bandit, budget, testing ledger and evaluator hash atomically.

## EF4-I62 — Typed stop certificate

Budget, dry rounds, stability, coverage, safety, human stop and blockers yield an EvolutionStopCertificate that preserves partial work.

## EF4-I63 — External backend isolation

ShinkaEvolve and other search engines are optional pinned adapters; their scores, archives, novelty and state never become Foundry authority.

## EF4-I64 — Executable candidate sandbox

Candidate code executes only under declared capabilities, resource quotas, network policy, effect receipts and evaluator/holdout isolation.

## Explicit non-goals

These boundaries prevent architecture language from becoming an unsupported
product or scientific claim:

- v4 does not guarantee truth or autonomous scientific discovery.
- v4 does not equate novelty with value or support.
- v4 does not use agent majority as evidence.
- v4 does not let candidates rewrite current evaluators.
- v4 does not expose hidden holdouts.
- v4 does not promote from one scalar.
- v4 does not treat every domain as having the same statistical policy.
- v4 does not require ShinkaEvolve or any other search backend.
- v4 does not claim production performance from this specification.
- v4 does not replace expert judgment, ethics review or experimental validation.

Provider neutrality is therefore a constitutional boundary, not a portability
aspiration. Codex, Claude, ShinkaEvolve, and future providers are replaceable
adapters. No provider-specific SDK, score, archive, prompt, or execution state
may become canonical semantics or a prerequisite for the domain-neutral core.
