# Changelog

All notable specification-bundle changes are recorded here. This is an
architecture and development-contract changelog, not a claim that the product
implementation already exists.

## 4.0.0 — Evolution-governed hypothesis discovery and validation

### ShinkaEvolve synthesis

- Audited the public ShinkaEvolve repository, documentation, skills, core
  concepts, parent selection, novelty filtering, islands/archive, model bandit,
  asynchronous execution, package metadata, release history, and paper.
- Adopted population search, lineage, semantic islands, quality-diversity
  archives, bounded asynchronous evaluation, cost-aware model routing, and
  progressive agent skills.
- Rejected scalar fitness, raw `correct`, embedding novelty, or backend archive
  state as scientific promotion authority.
- Added an optional pinned Shinka backend adapter with qualification,
  reconciliation, and fail-closed semantics.

### Evolution architecture

- Added the EVOLVE protocol: Encode, Vary, Oppose, Learn, Validate, Elevate.
- Added typed Hypothesis, Mechanism, Prediction, Falsifier, Experiment,
  Challenge, and quarantined Prompt genomes.
- Added multi-population co-evolution of hypotheses, mechanisms, experiments,
  measurements, and adversarial challenges.
- Added epistemic islands, compatibility-gated migration, Pareto/niche
  selection, quality-diversity maps, lineage saturation checks, and archive
  rebalancing that protects negative knowledge.
- Added Red Queen challenge co-evolution and independent replication.

### Anti-Goodhart and verifier governance

- Added an immutable per-run EvaluatorBundle and Verifier Firewall.
- Added hidden, OOD, adversarial, metamorphic, leakage, and calibration stages.
- Quarantined evaluator and prompt mutations for future-run qualification.
- Separated novelty, fitness, evidence, causal identification, safety,
  calibration, and replication into typed dimensions.
- Added adaptive-search sequential-testing, multiple-testing, winner's-curse,
  and selective-inference contracts.

### Specification package

- Expanded to 124 strict JSON Schemas with 124 examples.
- Expanded to 22 workflows and 327 node contracts.
- Expanded the A–Z implementation graph to 156 work packages.
- Expanded to 64 product invariants, 28 roles, 50 prompts, 29 plugin skills,
  and 7 hook bundles.
- Added 288 structured audit lenses across 24 failure families.


## 2.0.0 — Epistemic Foundry architecture freeze candidate

### Brand and product language

- Renamed the universal architecture to **Epistemic Foundry**.
- Fixed the canonical module vocabulary: Foundry Kernel, Claim Forge,
  Epistemic Atlas, Evidence Parliament, Aporia Engine, Noetic Ledger,
  Validation Bay, and Hypothesis Passport.
- Standardized the implementation namespace on `epistemic_foundry` and the
  operator CLI on `efoundry`.
- Added a versioned brand-and-naming contract so UX labels cannot silently
  redefine canonical schema semantics.

### Epistemic correctness

- Expanded verdicts into independent epistemic, causal, novelty, lifecycle,
  promotion, and stability dimensions rather than one confidence score.
- Added immutable Claim/Evidence lifecycle revisions, supersession,
  invalidation, stale propagation, reassessment, and withdrawal.
- Added SearchQuery, SearchLaneReceipt, RetrievalCandidate, and
  search-completeness certificates; absence and novelty claims are now bounded
  by receipts instead of prose.
- Added prompt-injection and hostile-document isolation contracts for PDFs,
  metadata, search results, tool outputs, and prior-agent text.
- Added method compatibility, dependency clustering, bias-risk, calibration,
  abstention, and human override/appeal contracts.
- Added update-triggered downstream invalidation and mandatory re-deliberation.

### Runtime and operations

- Expanded the provider-neutral runtime to seven canonical workflows:
  ingest, extraction, retrieval, deliberation, validation, reassessment, and
  evaluation/release.
- Added intent-before-effect, approval, capability lease, effect receipt,
  reconciliation, checkpoint, retry, replay-equivalence, and loop-budget
  contracts.
- Added schema migration, compatibility window, DomainPack migration,
  deployment profile, recovery, cost/concurrency, and provider adapter
  contracts.
- Added release provenance, artifact manifest, detached checksum, and
  supply-chain verification requirements.

### Development package

- Expanded the canonical contract set to 48 Draft 2020-12 JSON Schemas with
  48 validating examples.
- Expanded the executable architecture specification to 7 DAGs and 112
  node contracts.
- Expanded the implementation plan to 68 dependency-checked work packages,
  25 traceable product invariants, and 26 role/extraction prompts.
- Added a 144-lens audit matrix spanning twelve independent review families,
  a deterministic parallel audit runner, a specification validator, and a
  deterministic release builder.
- Added Codex and Claude Code project instructions, bounded subagent profiles,
  reusable skills, worktree-safe write rules, and maker/reviewer/integrator
  separation.

### Compatibility

- This release is a specification-level breaking change from v1.1.0.
- Existing v1.1 artifacts require the migration contracts in
  `docs/migration_v1_1_to_v2_0.md`; silent reinterpretation is prohibited.
- Domain-specific semantics remain plug-ins through versioned `DomainPack`
  artifacts, and external execution remains optional through
  `ValidationTargetManifest`.

## 1.1.0 — Domain-neutral core

- Removed specialist model and domain coupling from the core architecture.
- Added domain-neutral ScopeVector, DomainPack, ValidationTargetManifest, and
  ValidationPlan contracts.
- Generalized the execution loop to simulations, analyses, formal solvers,
  benchmarks, experimental platforms, external services, and custom adapters.
- Preserved Claim-first evidence, coverage-first review, Four-Graph semantics,
  asymmetric parliament, deterministic gates, provenance, and replay.

## 1.0.0 — Initial specification bundle

- Added source-grounded Claim, Evidence, Insight, Coverage, Run, Node, Gate,
  Passport, and Experiment contracts.
- Added provider-neutral corpus, extraction, deliberation, and validation
  workflows.
- Added a dependency/resource-checked development manifest, Codex/Claude
  instructions, execution prompt, source traceability, and specification QA.
