# PRD Projection

- mode: emit-from-coverage
- source_coverage_contract_hash: 3bbeccb08a0c1d4db3dbb391cff1c74e50cda3a1ae3b320604b442e8a6e1aef9
- source_atoms_hash: 2f22f501ada434b32d4ab7bfb6a50800b646455dd666ad8975b768401ca0a64f
- authority: planning view only; completion stays with source coverage + RALPH readiness

## architecture/design

### PRD-085: Part III — Final architecture

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part III — Final architecture'.

- linked source rows: SRC002-S0074
- linked source atoms: (none)

### PRD-140: A — Authority and architecture

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'A — Authority and architecture'.

- linked source rows: SRC002-S0129-R001, SRC002-S0129-R002, SRC002-S0129-R003, SRC002-S0129-R004, SRC002-S0129-R005, SRC002-S0129-R006
- linked source atoms: SRC002-S0129-R001-A01, SRC002-S0129-R002-A01, SRC002-S0129-R003-A01, SRC002-S0129-R004-A01, SRC002-S0129-R005-A01, SRC002-S0129-R006-A01
- [ ] AC-PRD-140-01: Satisfy source atom SRC002-S0129-R001-A01: -: **A01 — Authority chain, repository constitution and status vocabulary** Dependencies: `none` · Risk: `critical` ·  [constraints: none; critical; required] (verify: interface-check -> verify_src002_s0129_r001_a01)
- [ ] AC-PRD-140-02: Satisfy source atom SRC002-S0129-R002-A01: -: **A02 — Product invariants and non-goals** Dependencies: `A01` · Risk: `medium` · Review: `required` [constraints: A01; medium; required] (verify: interface-check -> verify_src002_s0129_r002_a01)
- [ ] AC-PRD-140-03: Satisfy source atom SRC002-S0129-R003-A01: -: **A03 — Architecture decision records and boundary map** Dependencies: `A01` · Risk: `medium` · Review: `required` [constraints: A01; medium; required] (verify: interface-check -> verify_src002_s0129_r003_a01)
- [ ] AC-PRD-140-04: Satisfy source atom SRC002-S0129-R004-A01: -: **A04 — A-phase integration and independent architecture review** Dependencies: `A02, A03` · Risk: `critical` · Rev [constraints: A02, A03; critical; required] (verify: interface-check -> verify_src002_s0129_r004_a01)
- [ ] AC-PRD-140-05: Satisfy source atom SRC002-S0129-R005-A01: -: **A05 — Evolution authority boundary and scientific promotion charter** Dependencies: `A04` · Risk: `critical` · Re [constraints: A04; critical; required] (verify: interface-check -> verify_src002_s0129_r005_a01)
- [ ] AC-PRD-140-06: Satisfy source atom SRC002-S0129-R006-A01: -: **A06 — Independent constitutional audit of evolution authority and non-mutable surfaces** Dependencies: `A05` · Ri [constraints: A05; critical; required] (verify: interface-check -> verify_src002_s0129_r006_a01)

### PRD-177: 47. Final architecture freeze

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '47. Final architecture freeze'.

- linked source rows: SRC002-S0166
- linked source atoms: SRC002-S0166-A01
- [ ] AC-PRD-177-01: Satisfy source atom SRC002-S0166-A01: Conditional items are external implementation and deployment evidence: licensed corpus, qualified evaluator/holdout, e [constraints: evaluator/holdout; sandbox/DB/queue; credentials/metering; 50/200/2] (verify: interface-check -> verify_src002_s0166_a01)

## data/interfaces

### PRD-160: U — Foundry Console and API

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'U — Foundry Console and API'.

- linked source rows: SRC002-S0149-R001, SRC002-S0149-R002, SRC002-S0149-R003, SRC002-S0149-R004, SRC002-S0149-R005, SRC002-S0149-R006
- linked source atoms: SRC002-S0149-R001-A01, SRC002-S0149-R002-A01, SRC002-S0149-R003-A01, SRC002-S0149-R004-A01, SRC002-S0149-R005-A01, SRC002-S0149-R006-A01
- [ ] AC-PRD-160-01: Satisfy source atom SRC002-S0149-R001-A01: -: **U01 — OpenAPI server and generated clients** Dependencies: `C04, T04` · Risk: `medium` · Review: `required` [constraints: C04, T04; medium; required] (verify: interface-check -> verify_src002_s0149_r001_a01)
- [ ] AC-PRD-160-02: Satisfy source atom SRC002-S0149-R002-A01: -: **U02 — Dashboard shell, auth and explicit health states** Dependencies: `U01` · Risk: `medium` · Review: `required [constraints: U01; medium; required] (verify: interface-check -> verify_src002_s0149_r002_a01)
- [ ] AC-PRD-160-03: Satisfy source atom SRC002-S0149-R003-A01: -: **U03 — Atlas, Parliament, Aporia and Passport views** Dependencies: `U01` · Risk: `medium` · Review: `required` [constraints: U01; medium; required] (verify: interface-check -> verify_src002_s0149_r003_a01)
- [ ] AC-PRD-160-04: Satisfy source atom SRC002-S0149-R004-A01: -: **U04 — U-phase accessibility and packaged-path parity gate** Dependencies: `U02, U03` · Risk: `medium` · Review: ` [constraints: U02, U03; medium; required] (verify: interface-check -> verify_src002_s0149_r004_a01)
- [ ] AC-PRD-160-05: Satisfy source atom SRC002-S0149-R005-A01: -: **U05 — Evolution Chamber console: Pareto, niches, lineages, challenges and operator controls** Dependencies: `U04, [constraints: U04, M05, G05; high; required] (verify: interface-check -> verify_src002_s0149_r005_a01)
- [ ] AC-PRD-160-06: Satisfy source atom SRC002-S0149-R006-A01: -: **U06 — Honest degraded UI and operator usability integration gate** Dependencies: `U05` · Risk: `critical` · Revie [constraints: U05; critical; required] (verify: interface-check -> verify_src002_s0149_r006_a01)

### PRD-166: Part XIV — Data and contract inventory

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part XIV — Data and contract inventory'.

- linked source rows: SRC002-S0155
- linked source atoms: (none)

### PRD-167: 39. Canonical schemas

Cover 20 source coverage row(s) and 20 requirement atom(s) from section '39. Canonical schemas'.

- linked source rows: SRC002-S0156-R001, SRC002-S0156-R002, SRC002-S0156-R003, SRC002-S0156-R004, SRC002-S0156-R005, SRC002-S0156-R006, SRC002-S0156-R007, SRC002-S0156-R008, SRC002-S0156-R009, SRC002-S0156-R010, SRC002-S0156-R011, SRC002-S0156-R012, SRC002-S0156-R013, SRC002-S0156-R014, SRC002-S0156-R015, SRC002-S0156-R016, SRC002-S0156-R017, SRC002-S0156-R018, SRC002-S0156-R019, SRC002-S0156-R020
- linked source atoms: SRC002-S0156-R001-A01, SRC002-S0156-R002-A01, SRC002-S0156-R003-A01, SRC002-S0156-R004-A01, SRC002-S0156-R005-A01, SRC002-S0156-R006-A01, SRC002-S0156-R007-A01, SRC002-S0156-R008-A01, SRC002-S0156-R009-A01, SRC002-S0156-R010-A01, SRC002-S0156-R011-A01, SRC002-S0156-R012-A01, SRC002-S0156-R013-A01, SRC002-S0156-R014-A01, SRC002-S0156-R015-A01, SRC002-S0156-R016-A01, SRC002-S0156-R017-A01, SRC002-S0156-R018-A01, SRC002-S0156-R019-A01, SRC002-S0156-R020-A01
- [ ] AC-PRD-167-01: Satisfy source atom SRC002-S0156-R001-A01: -: **A:** `action-intent.schema.json`, `adjudication.schema.json`, `approval-record.schema.json`, `archive-rebalance-p [constraints: action-intent.schema.json; adjudication.schema.json; approval-record.schema.json; archive-rebalance-plan.schema.json; argument-graph.schema.json; artifact-manifest.schema.json; artifact-receipt.schema.json; attestation.schema.json] (verify: interface-check -> verify_src002_s0156_r001_a01)
- [ ] AC-PRD-167-02: Satisfy source atom SRC002-S0156-R002-A01: -: **B:** `backend-adapter-qualification.schema.json`, `bias-risk-register.schema.json`, `budget-envelope.schema.json` [constraints: backend-adapter-qualification.schema.json; bias-risk-register.schema.json; budget-envelope.schema.json] (verify: interface-check -> verify_src002_s0156_r002_a01)
- [ ] AC-PRD-167-03: Satisfy source atom SRC002-S0156-R003-A01: -: **C:** `calibration-report.schema.json`, `candidate-generation-record.schema.json`, `candidate-lineage.schema.json` [constraints: calibration-report.schema.json; candidate-generation-record.schema.json; candidate-lineage.schema.json; capability-lease.schema.json; challenge-genome.schema.json; challenge-result.schema.json; checkpoint-manifest.schema.json; claim-card.schema.json; claim-lifecycle-event.schema.json; compatibility-matrix.schema.json; consent-record.schema.json; context-assembly-manifest.schema.json; context-capsule.schema.json; council-brief.schema.json; coverage-snapshot.schema.json; cross-examination.schema.json; crossover-compatibility-report.schema.json] (verify: interface-check -> verify_src002_s0156_r003_a01)
- [ ] AC-PRD-167-04: Satisfy source atom SRC002-S0156-R004-A01: -: **D:** `decision-stability-report.schema.json`, `document-manifest.schema.json`, `document-registration-request.sch [constraints: decision-stability-report.schema.json; document-manifest.schema.json; document-registration-request.schema.json; document-registration.schema.json; domain-pack.schema.json] (verify: interface-check -> verify_src002_s0156_r004_a01)
- [ ] AC-PRD-167-05: Satisfy source atom SRC002-S0156-R005-A01: -: **E:** `effect-receipt.schema.json`, `epistemic-archive-entry.schema.json`, `epistemic-niche.schema.json`, `epistem [constraints: effect-receipt.schema.json; epistemic-archive-entry.schema.json; epistemic-niche.schema.json; epistemic-utility-report.schema.json; epistemic-work-classification.schema.json; evaluation-run.schema.json; evaluator-bundle.schema.json; evaluator-mutation-proposal.schema.json; evaluator-qualification-report.schema.json; event-record.schema.json; evidence-dependency-cluster.schema.json; evidence-node.schema.json; evidence-pack.schema.json; evidence-reconciliation-record.schema.json; evolution-checkpoint.schema.json; evolution-run-spec.schema.json; evolution-stop-certificate.schema.json; experiment-genome.schema.json; experiment-result.schema.json; experiment-ticket.schema.json] (verify: interface-check -> verify_src002_s0156_r005_a01)
- [ ] AC-PRD-167-06: Satisfy source atom SRC002-S0156-R006-A01: -: **F:** `falsifier-gene.schema.json`, `fitness-evidence-receipt.schema.json`, `fitness-vector.schema.json`, `forge-s [constraints: falsifier-gene.schema.json; fitness-evidence-receipt.schema.json; fitness-vector.schema.json; forge-session-state.schema.json; forge-transition-request.schema.json] (verify: interface-check -> verify_src002_s0156_r006_a01)
- [ ] AC-PRD-167-07: Satisfy source atom SRC002-S0156-R007-A01: -: **G:** `gate-decision.schema.json` [constraints: gate-decision.schema.json] (verify: interface-check -> verify_src002_s0156_r007_a01)
- [ ] AC-PRD-167-08: Satisfy source atom SRC002-S0156-R008-A01: -: **H:** `holdout-manifest.schema.json`, `hook-event-envelope.schema.json`, `host-capability-report.schema.json`, `hu [constraints: holdout-manifest.schema.json; hook-event-envelope.schema.json; host-capability-report.schema.json; human-decision.schema.json; hypothesis-genome.schema.json; hypothesis-passport.schema.json] (verify: interface-check -> verify_src002_s0156_r008_a01)
- [ ] AC-PRD-167-09: Satisfy source atom SRC002-S0156-R009-A01: -: **I:** `imported-run-record.schema.json`, `insight-card.schema.json`, `island-state.schema.json` [constraints: imported-run-record.schema.json; insight-card.schema.json; island-state.schema.json] (verify: interface-check -> verify_src002_s0156_r009_a01)
- [ ] AC-PRD-167-10: Satisfy source atom SRC002-S0156-R010-A01: -: **L:** `leakage-audit.schema.json`, `lineage-diversity-report.schema.json`, `loop-contract.schema.json` [constraints: leakage-audit.schema.json; lineage-diversity-report.schema.json; loop-contract.schema.json] (verify: interface-check -> verify_src002_s0156_r010_a01)
- [ ] AC-PRD-167-11: Satisfy source atom SRC002-S0156-R011-A01: -: **M:** `measurement-compatibility-report.schema.json`, `mechanism-graph.schema.json`, `memory-policy.schema.json`,  [constraints: measurement-compatibility-report.schema.json; mechanism-graph.schema.json; memory-policy.schema.json; memory-retrieval-receipt.schema.json; minority-report.schema.json; model-routing-receipt.schema.json; multiple-testing-adjustment.schema.json; mutation-operator-spec.schema.json; mutation-receipt.schema.json] (verify: interface-check -> verify_src002_s0156_r011_a01)
- [ ] AC-PRD-167-12: Satisfy source atom SRC002-S0156-R012-A01: -: **N:** `node-contract.schema.json`, `node-invocation.schema.json`, `novelty-assessment.schema.json`, `novelty-vecto [constraints: node-contract.schema.json; node-invocation.schema.json; novelty-assessment.schema.json; novelty-vector.schema.json] (verify: interface-check -> verify_src002_s0156_r012_a01)
- [ ] AC-PRD-167-13: Satisfy source atom SRC002-S0156-R013-A01: -: **O:** `operator-bandit-state.schema.json` [constraints: operator-bandit-state.schema.json] (verify: interface-check -> verify_src002_s0156_r013_a01)
- [ ] AC-PRD-167-14: Satisfy source atom SRC002-S0156-R014-A01: -: **P:** `parent-selection-receipt.schema.json`, `pareto-front-snapshot.schema.json`, `phase-artifact-set.schema.json [constraints: parent-selection-receipt.schema.json; pareto-front-snapshot.schema.json; phase-artifact-set.schema.json; plugin-capability-manifest.schema.json; plugin-health-report.schema.json; plugin-install-state.schema.json; plugin-policy-pack.schema.json; plugin-release-provenance.schema.json; policy-bundle.schema.json; prediction-gene.schema.json; promotion-decision.schema.json; prompt-genome.schema.json; prompt-mutation-proposal.schema.json] (verify: interface-check -> verify_src002_s0156_r014_a01)
- [ ] AC-PRD-167-15: Satisfy source atom SRC002-S0156-R015-A01: -: **Q:** `quality-diversity-map.schema.json`, `query-plan.schema.json` [constraints: quality-diversity-map.schema.json; query-plan.schema.json] (verify: interface-check -> verify_src002_s0156_r015_a01)
- [ ] AC-PRD-167-16: Satisfy source atom SRC002-S0156-R016-A01: -: **R:** `red-queen-round.schema.json`, `replay-report.schema.json`, `replication-plan.schema.json`, `replication-res [constraints: red-queen-round.schema.json; replay-report.schema.json; replication-plan.schema.json; replication-result.schema.json; result-envelope.schema.json; retrieval-run.schema.json; role-dispatch-plan.schema.json; run-spec.schema.json] (verify: interface-check -> verify_src002_s0156_r016_a01)
- [ ] AC-PRD-167-17: Satisfy source atom SRC002-S0156-R017-A01: -: **S:** `schema-migration.schema.json`, `scope-vector.schema.json`, `search-completeness-certificate.schema.json`, ` [constraints: schema-migration.schema.json; scope-vector.schema.json; search-completeness-certificate.schema.json; search-lane-receipt.schema.json; selective-inference-report.schema.json; sequential-testing-ledger.schema.json; shinka-backend-manifest.schema.json; skill-lockfile.schema.json; skill-routing-decision.schema.json; source-integrity-report.schema.json; source-span.schema.json; stage-evaluation-result.schema.json; surrogate-triage-report.schema.json] (verify: interface-check -> verify_src002_s0156_r017_a01)
- [ ] AC-PRD-167-18: Satisfy source atom SRC002-S0156-R018-A01: -: **U:** `update-impact-report.schema.json` [constraints: update-impact-report.schema.json] (verify: interface-check -> verify_src002_s0156_r018_a01)
- [ ] AC-PRD-167-19: Satisfy source atom SRC002-S0156-R019-A01: -: **V:** `validation-cascade-plan.schema.json`, `validation-plan.schema.json`, `validation-target-manifest.schema.jso [constraints: validation-cascade-plan.schema.json; validation-plan.schema.json; validation-target-manifest.schema.json] (verify: interface-check -> verify_src002_s0156_r019_a01)
- [ ] AC-PRD-167-20: Satisfy source atom SRC002-S0156-R020-A01: -: **W:** `workspace-map-snapshot.schema.json` [constraints: workspace-map-snapshot.schema.json] (verify: interface-check -> verify_src002_s0156_r020_a01)

## implementation

### PRD-001: MASTER EXECUTION PROMPT — Epistemic Foundry v4.0.0

Cover 1 source coverage row(s) and 3 requirement atom(s) from section 'MASTER EXECUTION PROMPT — Epistemic Foundry v4.0.0'.

- linked source rows: SRC001-S0001
- linked source atoms: SRC001-S0001-A01, SRC001-S0001-A02, SRC001-S0001-A03
- [ ] AC-PRD-001-01: Satisfy source atom SRC001-S0001-A01: You are the **Parent Architect, Research Integrity Officer, Evolution Governor, Verifier-Firewall Custodian, and Integ (verify: risk-verification -> verify_src001_s0001_a01)
- [ ] AC-PRD-001-02: Satisfy source atom SRC001-S0001-A02: Your task is not to improvise the whole product in one context. (verify: negative-test -> verify_src001_s0001_a02)
- [ ] AC-PRD-001-03: Satisfy source atom SRC001-S0001-A03: Compile and execute the A–Z dependency graph, preserve the v4 constitution, delegate only bounded nodes, require recei (verify: negative-test -> verify_src001_s0001_a03)

### PRD-002: 1. Authority order

Cover 8 source coverage row(s) and 9 requirement atom(s) from section '1. Authority order'.

- linked source rows: SRC001-S0002-R001, SRC001-S0002-R002, SRC001-S0002-R003, SRC001-S0002-R004, SRC001-S0002-R005, SRC001-S0002-R006, SRC001-S0002-R007, SRC001-S0002-R008
- linked source atoms: SRC001-S0002-R001-A01, SRC001-S0002-R002-A01, SRC001-S0002-R003-A01, SRC001-S0002-R004-A01, SRC001-S0002-R005-A01, SRC001-S0002-R006-A01, SRC001-S0002-R007-A01, SRC001-S0002-R008-A01, SRC001-S0002-R008-A02
- [ ] AC-PRD-002-01: Satisfy source atom SRC001-S0002-R001-A01: 1: `MASTER_SPEC.md` [constraints: MASTER_SPEC.md] (verify: interface-check -> verify_src001_s0002_r001_a01)
- [ ] AC-PRD-002-02: Satisfy source atom SRC001-S0002-R002-A01: 2: `manifests/development_manifest.yaml` [constraints: manifests/development_manifest.yaml] (verify: interface-check -> verify_src001_s0002_r002_a01)
- [ ] AC-PRD-002-03: Satisfy source atom SRC001-S0002-R003-A01: 3: `manifests/acceptance_matrix.yaml` [constraints: manifests/acceptance_matrix.yaml] (verify: interface-check -> verify_src001_s0002_r003_a01)
- [ ] AC-PRD-002-04: Satisfy source atom SRC001-S0002-R004-A01: 4: `manifests/product_invariants.yaml` [constraints: manifests/product_invariants.yaml] (verify: interface-check -> verify_src001_s0002_r004_a01)
- [ ] AC-PRD-002-05: Satisfy source atom SRC001-S0002-R006-A01: 6: `manifests/role_registry.yaml` [constraints: manifests/role_registry.yaml] (verify: interface-check -> verify_src001_s0002_r006_a01)
- [ ] AC-PRD-002-06: Satisfy source atom SRC001-S0002-R007-A01: 7: `AGENTS.md` or `CLAUDE.md` [constraints: AGENTS.md; CLAUDE.md] (verify: interface-check -> verify_src001_s0002_r007_a01)
- [ ] AC-PRD-002-07: Satisfy source atom SRC001-S0002-R008-A02: Return `SPEC_GAP` when a required higher-order decision is absent. [constraints: SPEC_GAP] (verify: interface-check -> verify_src001_s0002_r008_a02)

### PRD-003: 2. Product boundary

Cover 8 source coverage row(s) and 9 requirement atom(s) from section '2. Product boundary'.

- linked source rows: SRC001-S0003-R001, SRC001-S0003-R002, SRC001-S0003-R003, SRC001-S0003-R004, SRC001-S0003-R005, SRC001-S0003-R006, SRC001-S0003-R007, SRC001-S0003-R008
- linked source atoms: SRC001-S0003-R001-A01, SRC001-S0003-R002-A01, SRC001-S0003-R003-A01, SRC001-S0003-R004-A01, SRC001-S0003-R005-A01, SRC001-S0003-R006-A01, SRC001-S0003-R007-A01, SRC001-S0003-R008-A01, SRC001-S0003-R008-A02
- [ ] AC-PRD-003-01: Satisfy source atom SRC001-S0003-R001-A01: -: a native Plugin Shell for skills, hooks, MCP/CLI, Console, and capability negotiation; [constraints: MCP/CLI] (verify: interface-check -> verify_src001_s0003_r001_a01)
- [ ] AC-PRD-003-02: Satisfy source atom SRC001-S0003-R002-A01: -: a provider-neutral Foundry Kernel for FORGE/EVOLVE state, policy, capabilities, effects, checkpoint, and replay; [constraints: FORGE/EVOLVE] (verify: interface-check -> verify_src001_s0003_r002_a01)
- [ ] AC-PRD-003-03: Satisfy source atom SRC001-S0003-R005-A01: -: a Verifier Firewall for immutable evaluators and hidden/OOD qualification; [constraints: hidden/OOD] (verify: interface-check -> verify_src001_s0003_r005_a01)
- [ ] AC-PRD-003-04: Satisfy source atom SRC001-S0003-R008-A01: -: an optional, pinned, fail-closed ShinkaEvolve backend adapter. (verify: negative-test -> verify_src001_s0003_r008_a01)
- [ ] AC-PRD-003-05: Satisfy source atom SRC001-S0003-R008-A02: The shell, model provider, and search backend never own epistemic truth. (verify: negative-test -> verify_src001_s0003_r008_a02)

### PRD-004: 3. Current status

Cover 1 source coverage row(s) and 4 requirement atom(s) from section '3. Current status'.

- linked source rows: SRC001-S0004
- linked source atoms: SRC001-S0004-A01, SRC001-S0004-A02, SRC001-S0004-A03, SRC001-S0004-A04
- [ ] AC-PRD-004-01: Satisfy source atom SRC001-S0004-A01: The delivered bundle is `SPEC_BUNDLE` plus `REFERENCE_BLUEPRINT`. [constraints: SPEC_BUNDLE; REFERENCE_BLUEPRINT] (verify: interface-check -> verify_src001_s0004_a01)
- [ ] AC-PRD-004-02: Satisfy source atom SRC001-S0004-A02: It is not an implemented plugin. (verify: negative-test -> verify_src001_s0004_a02)
- [ ] AC-PRD-004-03: Satisfy source atom SRC001-S0004-A03: Reference stubs must fail closed. (verify: negative-test -> verify_src001_s0004_a03)
- [ ] AC-PRD-004-04: Satisfy source atom SRC001-S0004-A04: Do not claim runtime, security, scientific, or performance properties without implementation evidence. (verify: negative-test -> verify_src001_s0004_a04)

### PRD-005: 4. FORGE and EVOLVE

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '4. FORGE and EVOLVE'.

- linked source rows: SRC001-S0005
- linked source atoms: SRC001-S0005-A01
- [ ] AC-PRD-005-01: Satisfy source atom SRC001-S0005-A01: Evolution cannot alter its current evaluator, holdout, policy, authority, or promotion rule. (verify: risk-verification -> verify_src001_s0005_a01)

### PRD-006: 5. Scientific search contract

Cover 13 source coverage row(s) and 13 requirement atom(s) from section '5. Scientific search contract'.

- linked source rows: SRC001-S0006-R001, SRC001-S0006-R002, SRC001-S0006-R003, SRC001-S0006-R004, SRC001-S0006-R005, SRC001-S0006-R006, SRC001-S0006-R007, SRC001-S0006-R008, SRC001-S0006-R009, SRC001-S0006-R010, SRC001-S0006-R011, SRC001-S0006-R012, SRC001-S0006-R013
- linked source atoms: SRC001-S0006-R001-A01, SRC001-S0006-R002-A01, SRC001-S0006-R003-A01, SRC001-S0006-R004-A01, SRC001-S0006-R005-A01, SRC001-S0006-R006-A01, SRC001-S0006-R007-A01, SRC001-S0006-R008-A01, SRC001-S0006-R009-A01, SRC001-S0006-R010-A01, SRC001-S0006-R011-A01, SRC001-S0006-R012-A01, SRC001-S0006-R013-A01
- [ ] AC-PRD-006-01: Satisfy source atom SRC001-S0006-R002-A01: -: mutable genome classes and forbidden authority fields; (verify: negative-test -> verify_src001_s0006_r002_a01)
- [ ] AC-PRD-006-02: Satisfy source atom SRC001-S0006-R004-A01: -: semantic islands and migration rules; (verify: risk-verification -> verify_src001_s0006_r004_a01)
- [ ] AC-PRD-006-03: Satisfy source atom SRC001-S0006-R005-A01: -: mutation/crossover operators; [constraints: mutation/crossover] (verify: interface-check -> verify_src001_s0006_r005_a01)
- [ ] AC-PRD-006-04: Satisfy source atom SRC001-S0006-R013-A01: -: hard/soft budgets, concurrency, and stop rules. [constraints: hard/soft] (verify: interface-check -> verify_src001_s0006_r013_a01)

### PRD-007: 6. Implementation protocol

Cover 12 source coverage row(s) and 13 requirement atom(s) from section '6. Implementation protocol'.

- linked source rows: SRC001-S0007-R001, SRC001-S0007-R002, SRC001-S0007-R003, SRC001-S0007-R004, SRC001-S0007-R005, SRC001-S0007-R006, SRC001-S0007-R007, SRC001-S0007-R008, SRC001-S0007-R009, SRC001-S0007-R010, SRC001-S0007-R011, SRC001-S0007-R012
- linked source atoms: SRC001-S0007-R001-A01, SRC001-S0007-R002-A01, SRC001-S0007-R003-A01, SRC001-S0007-R004-A01, SRC001-S0007-R005-A01, SRC001-S0007-R006-A01, SRC001-S0007-R007-A01, SRC001-S0007-R008-A01, SRC001-S0007-R009-A01, SRC001-S0007-R010-A01, SRC001-S0007-R011-A01, SRC001-S0007-R012-A01, SRC001-S0007-R012-A02

### PRD-009: 8. Promotion

Cover 10 source coverage row(s) and 10 requirement atom(s) from section '8. Promotion'.

- linked source rows: SRC001-S0009-R001, SRC001-S0009-R002, SRC001-S0009-R003, SRC001-S0009-R004, SRC001-S0009-R005, SRC001-S0009-R006, SRC001-S0009-R007, SRC001-S0009-R008, SRC001-S0009-R009, SRC001-S0009-R010
- linked source atoms: SRC001-S0009-R001-A01, SRC001-S0009-R002-A01, SRC001-S0009-R003-A01, SRC001-S0009-R004-A01, SRC001-S0009-R005-A01, SRC001-S0009-R006-A01, SRC001-S0009-R007-A01, SRC001-S0009-R008-A01, SRC001-S0009-R009-A01, SRC001-S0009-R010-A01
- [ ] AC-PRD-009-01: Satisfy source atom SRC001-S0009-R002-A01: -: scope/method compatibility; [constraints: scope/method] (verify: interface-check -> verify_src001_s0009_r002_a01)
- [ ] AC-PRD-009-02: Satisfy source atom SRC001-S0009-R009-A01: -: independent replication where required; (verify: functional-test -> verify_src001_s0009_r009_a01)

### PRD-010: 9. ShinkaEvolve adapter

Cover 1 source coverage row(s) and 3 requirement atom(s) from section '9. ShinkaEvolve adapter'.

- linked source rows: SRC001-S0010
- linked source atoms: SRC001-S0010-A01, SRC001-S0010-A02, SRC001-S0010-A03
- [ ] AC-PRD-010-01: Satisfy source atom SRC001-S0010-A01: Pin exact revision/digest, record Apache-2.0 obligations, map every backend event to Foundry artifacts, and qualify se [constraints: revision/digest] (verify: interface-check -> verify_src001_s0010_a01)
- [ ] AC-PRD-010-02: Satisfy source atom SRC001-S0010-A02: Backend scores, novelty, archive, islands, lineage, and bandit state are search signals, never promotion authority. (verify: negative-test -> verify_src001_s0010_a02)
- [ ] AC-PRD-010-03: Satisfy source atom SRC001-S0010-A03: On missing capability or ambiguous mapping, fail closed. (verify: negative-test -> verify_src001_s0010_a03)

### PRD-011: 10. Exit behavior

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '10. Exit behavior'.

- linked source rows: SRC001-S0011
- linked source atoms: SRC001-S0011-A01, SRC001-S0011-A02
- [ ] AC-PRD-011-01: Satisfy source atom SRC001-S0011-A01: Never replace missing evidence with plausible prose. (verify: negative-test -> verify_src001_s0011_a01)
- [ ] AC-PRD-011-02: Satisfy source atom SRC001-S0011-A02: Never weaken a gate to finish. (verify: negative-test -> verify_src001_s0011_a02)

### PRD-012: Epistemic Foundry v4.0.0

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Epistemic Foundry v4.0.0'.

- linked source rows: SRC002-S0001
- linked source atoms: (none)

### PRD-014: Codex / Claude Code / Provider-Neutral A–Z Development Specification

Cover 17 source coverage row(s) and 17 requirement atom(s) from section 'Codex / Claude Code / Provider-Neutral A–Z Development Specification'.

- linked source rows: SRC002-S0003-R001, SRC002-S0003-R002, SRC002-S0003-R003, SRC002-S0003-R004, SRC002-S0003-R005, SRC002-S0003-R006, SRC002-S0003-R007, SRC002-S0003-R008, SRC002-S0003-R009, SRC002-S0003-R010, SRC002-S0003-R011, SRC002-S0003-R012, SRC002-S0003-R013, SRC002-S0003-R014, SRC002-S0003-R015, SRC002-S0003-R016, SRC002-S0003-R017
- linked source atoms: SRC002-S0003-R001-A01, SRC002-S0003-R002-A01, SRC002-S0003-R003-A01, SRC002-S0003-R004-A01, SRC002-S0003-R005-A01, SRC002-S0003-R006-A01, SRC002-S0003-R007-A01, SRC002-S0003-R008-A01, SRC002-S0003-R009-A01, SRC002-S0003-R010-A01, SRC002-S0003-R011-A01, SRC002-S0003-R012-A01, SRC002-S0003-R013-A01, SRC002-S0003-R014-A01, SRC002-S0003-R015-A01, SRC002-S0003-R016-A01, SRC002-S0003-R017-A01
- [ ] AC-PRD-014-01: Satisfy source atom SRC002-S0003-R001-A01: -: **Document status:** `SPEC_BUNDLE / IMPLEMENTATION CONTRACT` [constraints: SPEC_BUNDLE / IMPLEMENTATION CONTRACT] (verify: interface-check -> verify_src002_s0003_r001_a01)
- [ ] AC-PRD-014-02: Satisfy source atom SRC002-S0003-R002-A01: -: **Implementation status:** `NOT CLAIMED` [constraints: NOT CLAIMED] (verify: negative-test -> verify_src002_s0003_r002_a01)
- [ ] AC-PRD-014-03: Satisfy source atom SRC002-S0003-R003-A01: -: **Architecture freeze:** `CONDITIONAL PASS` [constraints: CONDITIONAL PASS] (verify: interface-check -> verify_src002_s0003_r003_a01)
- [ ] AC-PRD-014-04: Satisfy source atom SRC002-S0003-R006-A01: -: **Plugin ID:** `epistemic-foundry` [constraints: epistemic-foundry] (verify: interface-check -> verify_src002_s0003_r006_a01)
- [ ] AC-PRD-014-05: Satisfy source atom SRC002-S0003-R007-A01: -: **Python namespace:** `epistemic_foundry` [constraints: epistemic_foundry] (verify: interface-check -> verify_src002_s0003_r007_a01)
- [ ] AC-PRD-014-06: Satisfy source atom SRC002-S0003-R008-A01: -: **CLI:** `efoundry` [constraints: efoundry] (verify: interface-check -> verify_src002_s0003_r008_a01)
- [ ] AC-PRD-014-07: Satisfy source atom SRC002-S0003-R009-A01: -: **Research lifecycle:** `FORGE` [constraints: FORGE] (verify: interface-check -> verify_src002_s0003_r009_a01)
- [ ] AC-PRD-014-08: Satisfy source atom SRC002-S0003-R010-A01: -: **Evolution subprotocol:** `EVOLVE — Encode / Vary / Oppose / Learn / Validate / Elevate` [constraints: EVOLVE — Encode / Vary / Oppose / Learn / Validate / Elevate] (verify: interface-check -> verify_src002_s0003_r010_a01)
- [ ] AC-PRD-014-09: Satisfy source atom SRC002-S0003-R011-A01: -: **Canonical authority:** Foundry Kernel + Noetic Ledger (verify: risk-verification -> verify_src002_s0003_r011_a01)
- [ ] AC-PRD-014-10: Satisfy source atom SRC002-S0003-R012-A01: -: **Scientific promotion:** deterministic gates + Evidence Parliament + independent attestation + explicit human/poli [constraints: human/policy] (verify: interface-check -> verify_src002_s0003_r012_a01)
- [ ] AC-PRD-014-11: Satisfy source atom SRC002-S0003-R013-A01: -: **Knowledge structure:** E/R/D/X Four-Graph plus typed evolutionary projections [constraints: E/R/D/X] (verify: interface-check -> verify_src002_s0003_r013_a01)

### PRD-015: Part I — Authority, truthfulness and research basis

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part I — Authority, truthfulness and research basis'.

- linked source rows: SRC002-S0004
- linked source atoms: (none)

### PRD-016: 1. Authority order

Cover 8 source coverage row(s) and 12 requirement atom(s) from section '1. Authority order'.

- linked source rows: SRC002-S0005-R001, SRC002-S0005-R002, SRC002-S0005-R003, SRC002-S0005-R004, SRC002-S0005-R005, SRC002-S0005-R006, SRC002-S0005-R007, SRC002-S0005-R008
- linked source atoms: SRC002-S0005-R001-A01, SRC002-S0005-R002-A01, SRC002-S0005-R003-A01, SRC002-S0005-R004-A01, SRC002-S0005-R005-A01, SRC002-S0005-R006-A01, SRC002-S0005-R007-A01, SRC002-S0005-R008-A01, SRC002-S0005-R008-A02, SRC002-S0005-R008-A03, SRC002-S0005-R008-A04, SRC002-S0005-R008-A05
- [ ] AC-PRD-016-01: Satisfy source atom SRC002-S0005-R001-A01: 1: `MASTER_SPEC.md` [constraints: MASTER_SPEC.md] (verify: interface-check -> verify_src002_s0005_r001_a01)
- [ ] AC-PRD-016-02: Satisfy source atom SRC002-S0005-R002-A01: 2: `manifests/development_manifest.yaml` [constraints: manifests/development_manifest.yaml] (verify: interface-check -> verify_src002_s0005_r002_a01)
- [ ] AC-PRD-016-03: Satisfy source atom SRC002-S0005-R003-A01: 3: `manifests/acceptance_matrix.yaml` [constraints: manifests/acceptance_matrix.yaml] (verify: interface-check -> verify_src002_s0005_r003_a01)
- [ ] AC-PRD-016-04: Satisfy source atom SRC002-S0005-R004-A01: 4: `manifests/product_invariants.yaml` [constraints: manifests/product_invariants.yaml] (verify: interface-check -> verify_src002_s0005_r004_a01)
- [ ] AC-PRD-016-05: Satisfy source atom SRC002-S0005-R006-A01: 6: `manifests/role_registry.yaml` [constraints: manifests/role_registry.yaml] (verify: interface-check -> verify_src002_s0005_r006_a01)
- [ ] AC-PRD-016-06: Satisfy source atom SRC002-S0005-R007-A01: 7: `AGENTS.md` or `CLAUDE.md` [constraints: AGENTS.md; CLAUDE.md] (verify: interface-check -> verify_src002_s0005_r007_a01)
- [ ] AC-PRD-016-07: Satisfy source atom SRC002-S0005-R008-A02: Lower authority cannot override higher authority. (verify: risk-verification -> verify_src002_s0005_r008_a02)
- [ ] AC-PRD-016-08: Satisfy source atom SRC002-S0005-R008-A03: Missing or inconsistent shared semantics return `SPEC_GAP`. [constraints: SPEC_GAP] (verify: interface-check -> verify_src002_s0005_r008_a03)
- [ ] AC-PRD-016-09: Satisfy source atom SRC002-S0005-R008-A04: A clear contract blocked by an unavailable external prerequisite returns `BLOCKED`. [constraints: BLOCKED] (verify: interface-check -> verify_src002_s0005_r008_a04)
- [ ] AC-PRD-016-10: Satisfy source atom SRC002-S0005-R008-A05: `PASS` requires objective checks, immutable resolving artifacts/effect receipts and independent review. [constraints: PASS; artifacts/effect] (verify: interface-check -> verify_src002_s0005_r008_a05)

### PRD-017: 2. Maturity statement

Cover 1 source coverage row(s) and 4 requirement atom(s) from section '2. Maturity statement'.

- linked source rows: SRC002-S0006
- linked source atoms: SRC002-S0006-A01, SRC002-S0006-A02, SRC002-S0006-A03, SRC002-S0006-A04
- [ ] AC-PRD-017-01: Satisfy source atom SRC002-S0006-A01: This bundle specifies v4 target architecture, canonical contracts, workflows, plugin blueprint, migration, acceptance  (verify: risk-verification -> verify_src002_s0006_a01)
- [ ] AC-PRD-017-02: Satisfy source atom SRC002-S0006-A02: It does not claim that a working v4 runtime, qualified evaluator, hidden holdout, Shinka adapter, production database, (verify: negative-test -> verify_src002_s0006_a02)
- [ ] AC-PRD-017-03: Satisfy source atom SRC002-S0006-A03: Reference plugin executables remain fail-closed stubs. (verify: negative-test -> verify_src002_s0006_a03)
- [ ] AC-PRD-017-04: Satisfy source atom SRC002-S0006-A04: A specification file is not execution evidence. (verify: negative-test -> verify_src002_s0006_a04)

### PRD-018: 3. ShinkaEvolve source study

Cover 14 source coverage row(s) and 18 requirement atom(s) from section '3. ShinkaEvolve source study'.

- linked source rows: SRC002-S0007-R001, SRC002-S0007-R002, SRC002-S0007-R003, SRC002-S0007-R004, SRC002-S0007-R005, SRC002-S0007-R006, SRC002-S0007-R007, SRC002-S0007-R008, SRC002-S0007-R009, SRC002-S0007-R010, SRC002-S0007-R011, SRC002-S0007-R012, SRC002-S0007-R013, SRC002-S0007-R014
- linked source atoms: SRC002-S0007-R001-A01, SRC002-S0007-R002-A01, SRC002-S0007-R003-A01, SRC002-S0007-R004-A01, SRC002-S0007-R005-A01, SRC002-S0007-R006-A01, SRC002-S0007-R007-A01, SRC002-S0007-R008-A01, SRC002-S0007-R009-A01, SRC002-S0007-R010-A01, SRC002-S0007-R011-A01, SRC002-S0007-R012-A01, SRC002-S0007-R012-A02, SRC002-S0007-R013-A01, SRC002-S0007-R014-A01, SRC002-S0007-R014-A02, SRC002-S0007-R014-A03, SRC002-S0007-R014-A04
- [ ] AC-PRD-018-01: Satisfy source atom SRC002-S0007-R004-A01: -: archive/island/migration; [constraints: archive/island/migration] (verify: interface-check -> verify_src002_s0007_r004_a01)
- [ ] AC-PRD-018-02: Satisfy source atom SRC002-S0007-R007-A01: -: asynchronous proposal/evaluation/database paths; [constraints: proposal/evaluation/database] (verify: interface-check -> verify_src002_s0007_r007_a01)
- [ ] AC-PRD-018-03: Satisfy source atom SRC002-S0007-R008-A01: -: SQLite/WAL persistence and resume/idempotency surfaces; [constraints: SQLite/WAL; resume/idempotency] (verify: interface-check -> verify_src002_s0007_r008_a01)
- [ ] AC-PRD-018-04: Satisfy source atom SRC002-S0007-R009-A01: -: executable task/evaluator contract; [constraints: task/evaluator] (verify: interface-check -> verify_src002_s0007_r009_a01)
- [ ] AC-PRD-018-05: Satisfy source atom SRC002-S0007-R010-A01: -: `shinka-setup`, `shinka-convert`, `shinka-run` and `shinka-inspect` skills; [constraints: shinka-setup; shinka-convert; shinka-run; shinka-inspect] (verify: interface-check -> verify_src002_s0007_r010_a01)
- [ ] AC-PRD-018-06: Satisfy source atom SRC002-S0007-R011-A01: -: local/Slurm/headless execution; [constraints: local/Slurm/headless] (verify: interface-check -> verify_src002_s0007_r011_a01)
- [ ] AC-PRD-018-07: Satisfy source atom SRC002-S0007-R012-A02: The complete factual inventory and 55 adoption/correction decisions are in: [constraints: adoption/correction] (verify: interface-check -> verify_src002_s0007_r012_a02)
- [ ] AC-PRD-018-08: Satisfy source atom SRC002-S0007-R013-A01: -: `research/shinkaevolve_source_manifest.json` [constraints: research/shinkaevolve_source_manifest.json] (verify: interface-check -> verify_src002_s0007_r013_a01)
- [ ] AC-PRD-018-09: Satisfy source atom SRC002-S0007-R014-A01: -: `research/shinkaevolve_gap_analysis.md` [constraints: research/shinkaevolve_gap_analysis.md] (verify: interface-check -> verify_src002_s0007_r014_a01)
- [ ] AC-PRD-018-10: Satisfy source atom SRC002-S0007-R014-A04: Epistemic Foundry v4 generalizes its search mechanisms to typed scientific candidates while adding a Verifier Firewall (verify: risk-verification -> verify_src002_s0007_r014_a04)

### PRD-019: 4. v4 thesis

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '4. v4 thesis'.

- linked source rows: SRC002-S0008
- linked source atoms: SRC002-S0008-A01
- [ ] AC-PRD-019-01: Satisfy source atom SRC002-S0008-A01: The trust system must be conservative. (verify: functional-test -> verify_src002_s0008_a01)

### PRD-020: Part II — Product constitution: 64 non-negotiable invariants

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part II — Product constitution: 64 non-negotiable invariants'.

- linked source rows: SRC002-S0009
- linked source atoms: (none)

### PRD-021: EF4-I01 — Kernel authority

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I01 — Kernel authority'.

- linked source rows: SRC002-S0010
- linked source atoms: SRC002-S0010-A01
- [ ] AC-PRD-021-01: Satisfy source atom SRC002-S0010-A01: Plugin shell, hooks, skills, GUI, chat transcripts and provider SDKs never own canonical state, policy, gates or repla (verify: negative-test -> verify_src002_s0010_a01)

### PRD-022: EF4-I02 — Claim-first evidence

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I02 — Claim-first evidence'.

- linked source rows: SRC002-S0011
- linked source atoms: (none)

### PRD-023: EF4-I03 — Falsifiable intake

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I03 — Falsifiable intake'.

- linked source rows: SRC002-S0012
- linked source atoms: SRC002-S0012-A01
- [ ] AC-PRD-023-01: Satisfy source atom SRC002-S0012-A01: An insight without scope, predictions and falsifier cannot enter Observe or Parliament. (verify: negative-test -> verify_src002_s0012_a01)

### PRD-024: EF4-I04 — Coverage before confidence

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I04 — Coverage before confidence'.

- linked source rows: SRC002-S0013
- linked source atoms: (none)

### PRD-025: EF4-I05 — Search-state type safety

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I05 — Search-state type safety'.

- linked source rows: SRC002-S0014
- linked source atoms: SRC002-S0014-A01
- [ ] AC-PRD-025-01: Satisfy source atom SRC002-S0014-A01: UNSEARCHED, SEARCHED_NONE, SEARCHED_WITH_RESULTS and failed search are distinct. [constraints: SEARCHED_NONE; SEARCHED_WITH_RESULTS] (verify: negative-test -> verify_src002_s0014_a01)

### PRD-026: EF4-I06 — Adversarial retrieval

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I06 — Adversarial retrieval'.

- linked source rows: SRC002-S0015
- linked source atoms: (none)

### PRD-027: EF4-I07 — Method comparability

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I07 — Method comparability'.

- linked source rows: SRC002-S0016
- linked source atoms: SRC002-S0016-A01
- [ ] AC-PRD-027-01: Satisfy source atom SRC002-S0016-A01: Method-incompatible evidence is stratified and may impose a promotion ceiling; it is never silently pooled. (verify: negative-test -> verify_src002_s0016_a01)

### PRD-028: EF4-I08 — Dependency-adjusted evidence

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I08 — Dependency-adjusted evidence'.

- linked source rows: SRC002-S0017
- linked source atoms: SRC002-S0017-A01
- [ ] AC-PRD-028-01: Satisfy source atom SRC002-S0017-A01: Shared samples, datasets, publication families and derived analyses are dependency clusters, not independent votes. (verify: negative-test -> verify_src002_s0017_a01)

### PRD-029: EF4-I09 — No majority authority

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I09 — No majority authority'.

- linked source rows: SRC002-S0018
- linked source atoms: (none)

### PRD-030: EF4-I10 — Inference separation

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I10 — Inference separation'.

- linked source rows: SRC002-S0019
- linked source atoms: (none)

### PRD-031: EF4-I11 — Evidence-class separation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I11 — Evidence-class separation'.

- linked source rows: SRC002-S0020
- linked source atoms: SRC002-S0020-A01
- [ ] AC-PRD-031-01: Satisfy source atom SRC002-S0020-A01: Simulation, formal derivation, benchmark and review-derived evidence never become empirical observation by relabeling. (verify: negative-test -> verify_src002_s0020_a01)

### PRD-032: EF4-I12 — No self-approval

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I12 — No self-approval'.

- linked source rows: SRC002-S0021
- linked source atoms: (none)

### PRD-033: EF4-I13 — Receipt-bound completion

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I13 — Receipt-bound completion'.

- linked source rows: SRC002-S0022
- linked source atoms: SRC002-S0022-A01
- [ ] AC-PRD-033-01: Satisfy source atom SRC002-S0022-A01: Phase transitions, side effects, tests, installs and releases require resolving artifact/effect receipts. [constraints: artifact/effect] (verify: interface-check -> verify_src002_s0022_a01)

### PRD-034: EF4-I14 — Hooks are guardrails

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I14 — Hooks are guardrails'.

- linked source rows: SRC002-S0023
- linked source atoms: SRC002-S0023-A01
- [ ] AC-PRD-034-01: Satisfy source atom SRC002-S0023-A01: Hook coverage is observed and useful but never treated as the complete enforcement boundary. (verify: negative-test -> verify_src002_s0023_a01)

### PRD-035: EF4-I15 — Capability negotiation

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I15 — Capability negotiation'.

- linked source rows: SRC002-S0024
- linked source atoms: (none)

### PRD-036: EF4-I16 — Event-sourced state

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I16 — Event-sourced state'.

- linked source rows: SRC002-S0025
- linked source atoms: (none)

### PRD-037: EF4-I17 — Explicit human authority

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I17 — Explicit human authority'.

- linked source rows: SRC002-S0026
- linked source atoms: (none)

### PRD-038: EF4-I18 — Consent-bound memory

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I18 — Consent-bound memory'.

- linked source rows: SRC002-S0027
- linked source atoms: (none)

### PRD-039: EF4-I19 — Workspace isolation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I19 — Workspace isolation'.

- linked source rows: SRC002-S0028
- linked source atoms: SRC002-S0028-A01
- [ ] AC-PRD-039-01: Satisfy source atom SRC002-S0028-A01: Cross-workspace state, memory and artifacts are denied by default below the model layer. (verify: negative-test -> verify_src002_s0028_a01)

### PRD-040: EF4-I20 — Canonical context capsule

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I20 — Canonical context capsule'.

- linked source rows: SRC002-S0029
- linked source atoms: (none)

### PRD-041: EF4-I21 — Skill supply-chain quarantine

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I21 — Skill supply-chain quarantine'.

- linked source rows: SRC002-S0030
- linked source atoms: SRC002-S0030-A01
- [ ] AC-PRD-041-01: Satisfy source atom SRC002-S0030-A01: Third-party skills are quarantined, inspected, permissioned, pinned and approved before activation. (verify: risk-verification -> verify_src002_s0030_a01)

### PRD-042: EF4-I22 — Generated transport contracts

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I22 — Generated transport contracts'.

- linked source rows: SRC002-S0031
- linked source atoms: SRC002-S0031-A01
- [ ] AC-PRD-042-01: Satisfy source atom SRC002-S0031-A01: CLI, MCP, HTTP, persistence and UI models derive from canonical schemas; duplicated wire literals are forbidden. (verify: negative-test -> verify_src002_s0031_a01)

### PRD-043: EF4-I23 — Honest UI state

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I23 — Honest UI state'.

- linked source rows: SRC002-S0032
- linked source atoms: SRC002-S0032-A01
- [ ] AC-PRD-043-01: Satisfy source atom SRC002-S0032-A01: EMPTY_CONFIRMED, DEGRADED and UNAVAILABLE are distinct; backend failure never appears as empty research state. [constraints: EMPTY_CONFIRMED] (verify: negative-test -> verify_src002_s0032_a01)

### PRD-044: EF4-I24 — Real map ranking

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I24 — Real map ranking'.

- linked source rows: SRC002-S0033
- linked source atoms: (none)

### PRD-046: EF4-I26 — No silent partial fan-in

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I26 — No silent partial fan-in'.

- linked source rows: SRC002-S0035
- linked source atoms: (none)

### PRD-047: EF4-I27 — Bounded cycles

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I27 — Bounded cycles'.

- linked source rows: SRC002-S0036
- linked source atoms: SRC002-S0036-A01
- [ ] AC-PRD-047-01: Satisfy source atom SRC002-S0036-A01: Every cycle has a seen-set key, novelty/convergence rule, dry rounds, maximum rounds, budget and escalation. [constraints: novelty/convergence] (verify: interface-check -> verify_src002_s0036_a01)

### PRD-048: EF4-I28 — Typed budget enforcement

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I28 — Typed budget enforcement'.

- linked source rows: SRC002-S0037
- linked source atoms: SRC002-S0037-A01
- [ ] AC-PRD-048-01: Satisfy source atom SRC002-S0037-A01: Budgets are labeled HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE or UNMETERED. [constraints: HARD_METERED; HARD_PREALLOCATED; SOFT_ESTIMATE] (verify: interface-check -> verify_src002_s0037_a01)

### PRD-049: EF4-I29 — Secret minimization

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I29 — Secret minimization'.

- linked source rows: SRC002-S0038
- linked source atoms: SRC002-S0038-A01
- [ ] AC-PRD-049-01: Satisfy source atom SRC002-S0038-A01: Secrets are opaque handles and never copied into prompts, evidence artifacts, logs or exports. (verify: negative-test -> verify_src002_s0038_a01)

### PRD-050: EF4-I30 — Untrusted evidence plane

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I30 — Untrusted evidence plane'.

- linked source rows: SRC002-S0039
- linked source atoms: SRC002-S0039-A01
- [ ] AC-PRD-050-01: Satisfy source atom SRC002-S0039-A01: PDFs, web pages, datasets and model output are data and cannot grant authority or execute instructions. (verify: risk-verification -> verify_src002_s0039_a01)

### PRD-051: EF4-I31 — Migration and rollback

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I31 — Migration and rollback'.

- linked source rows: SRC002-S0040
- linked source atoms: SRC002-S0040-A01
- [ ] AC-PRD-051-01: Satisfy source atom SRC002-S0040-A01: Breaking schema/plugin changes require compatibility, dry-run, backup, rollback and hook re-trust. [constraints: schema/plugin] (verify: negative-test -> verify_src002_s0040_a01)

### PRD-053: EF4-I33 — Status honesty

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I33 — Status honesty'.

- linked source rows: SRC002-S0042
- linked source atoms: (none)

### PRD-054: EF4-I34 — Provider neutrality

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I34 — Provider neutrality'.

- linked source rows: SRC002-S0043
- linked source atoms: (none)

### PRD-056: EF4-I36 — Remote messaging minimized

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I36 — Remote messaging minimized'.

- linked source rows: SRC002-S0045
- linked source atoms: SRC002-S0045-A01
- [ ] AC-PRD-056-01: Satisfy source atom SRC002-S0045-A01: Remote notification/approval adapters are optional and cannot execute arbitrary commands or export raw evidence by def [constraints: notification/approval] (verify: interface-check -> verify_src002_s0045_a01)

### PRD-057: EF4-I37 — License-aware corpus/export

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I37 — License-aware corpus/export'.

- linked source rows: SRC002-S0046
- linked source atoms: (none)

### PRD-058: EF4-I38 — Stale propagation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I38 — Stale propagation'.

- linked source rows: SRC002-S0047
- linked source atoms: SRC002-S0047-A01
- [ ] AC-PRD-058-01: Satisfy source atom SRC002-S0047-A01: Corrections, retractions, parser fixes, policy/ontology changes and new evidence invalidate dependent projections and  [constraints: policy/ontology] (verify: interface-check -> verify_src002_s0047_a01)

### PRD-059: EF4-I39 — Replayability

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I39 — Replayability'.

- linked source rows: SRC002-S0048
- linked source atoms: SRC002-S0048-A01
- [ ] AC-PRD-059-01: Satisfy source atom SRC002-S0048-A01: RunSpec, context, adapter/model, tools, receipts, policy, corpus and prompts are sufficient to explain and compare a r [constraints: adapter/model] (verify: interface-check -> verify_src002_s0048_a01)

### PRD-060: EF4-I40 — Honest underdetermination

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I40 — Honest underdetermination'.

- linked source rows: SRC002-S0049
- linked source atoms: SRC002-S0049-A01
- [ ] AC-PRD-060-01: Satisfy source atom SRC002-S0049-A01: UNDERDETERMINED, UNTESTABLE, NOT_ASSESSED and PARTIAL are normal truthful outcomes, not system failure. [constraints: NOT_ASSESSED] (verify: negative-test -> verify_src002_s0049_a01)

### PRD-061: EF4-I41 — Evolution is subordinate

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I41 — Evolution is subordinate'.

- linked source rows: SRC002-S0050
- linked source atoms: SRC002-S0050-A01
- [ ] AC-PRD-061-01: Satisfy source atom SRC002-S0050-A01: Evolution Chamber may propose, mutate, challenge and rank candidates but cannot own evidence truth, evaluator authorit (verify: risk-verification -> verify_src002_s0050_a01)

### PRD-062: EF4-I42 — Typed scientific genome

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I42 — Typed scientific genome'.

- linked source rows: SRC002-S0051
- linked source atoms: (none)

### PRD-063: EF4-I43 — Immutable evaluator per run

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I43 — Immutable evaluator per run'.

- linked source rows: SRC002-S0052
- linked source atoms: (none)

### PRD-064: EF4-I44 — Hidden holdout firewall

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I44 — Hidden holdout firewall'.

- linked source rows: SRC002-S0053
- linked source atoms: SRC002-S0053-A01
- [ ] AC-PRD-064-01: Satisfy source atom SRC002-S0053-A01: Candidate generation, mutation prompts, external backends and ordinary agents cannot read hidden holdout content or de [constraints: tool/log/cache] (verify: interface-check -> verify_src002_s0053_a01)

### PRD-065: EF4-I45 — No scalar promotion authority

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I45 — No scalar promotion authority'.

- linked source rows: SRC002-S0054
- linked source atoms: SRC002-S0054-A01
- [ ] AC-PRD-065-01: Satisfy source atom SRC002-S0054-A01: A combined score may order search but cannot promote; hard gates, FitnessVector, Pareto/niche analysis, statistics, re [constraints: Pareto/niche] (verify: interface-check -> verify_src002_s0054_a01)

### PRD-066: EF4-I46 — Multi-layer novelty

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I46 — Multi-layer novelty'.

- linked source rows: SRC002-S0055
- linked source atoms: (none)

### PRD-067: EF4-I47 — Novelty failure type safety

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I47 — Novelty failure type safety'.

- linked source rows: SRC002-S0056
- linked source atoms: SRC002-S0056-A01
- [ ] AC-PRD-067-01: Satisfy source atom SRC002-S0056-A01: Absent, empty, failed or incomplete novelty assessment yields UNASSESSED, PARTIAL or FAILED and never NOVEL by default (verify: negative-test -> verify_src002_s0056_a01)

### PRD-068: EF4-I48 — Quality-diversity archive

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I48 — Quality-diversity archive'.

- linked source rows: SRC002-S0057
- linked source atoms: (none)

### PRD-069: EF4-I49 — Protected negative memory

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I49 — Protected negative memory'.

- linked source rows: SRC002-S0058
- linked source atoms: SRC002-S0058-A01
- [ ] AC-PRD-069-01: Satisfy source atom SRC002-S0058-A01: Nulls, counterexamples, failed replications, unsafe failures and minority lineages cannot be evicted merely for low fi (verify: negative-test -> verify_src002_s0058_a01)

### PRD-070: EF4-I50 — Semantic islands

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I50 — Semantic islands'.

- linked source rows: SRC002-S0059
- linked source atoms: SRC002-S0059-A01
- [ ] AC-PRD-070-01: Satisfy source atom SRC002-S0059-A01: Islands specialize by typed mechanism, scope, method or evidence state; migration requires compatibility and preserves [constraints: source/target] (verify: interface-check -> verify_src002_s0059_a01)

### PRD-071: EF4-I51 — Typed crossover

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I51 — Typed crossover'.

- linked source rows: SRC002-S0060
- linked source atoms: SRC002-S0060-A01
- [ ] AC-PRD-071-01: Satisfy source atom SRC002-S0060-A01: Crossover requires scope, measurement, unit and causal compatibility; semantic collage is rejected. (verify: negative-test -> verify_src002_s0060_a01)

### PRD-072: EF4-I52 — Red Queen relevance

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I52 — Red Queen relevance'.

- linked source rows: SRC002-S0061
- linked source atoms: (none)

### PRD-073: EF4-I53 — Adaptive-search statistics

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I53 — Adaptive-search statistics'.

- linked source rows: SRC002-S0062
- linked source atoms: (none)

### PRD-074: EF4-I54 — Delayed reward routing

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I54 — Delayed reward routing'.

- linked source rows: SRC002-S0063
- linked source atoms: SRC002-S0063-A01
- [ ] AC-PRD-074-01: Satisfy source atom SRC002-S0063-A01: Model and operator bandits learn from validated holdout/replication utility and safety, not only immediate proxy score [constraints: holdout/replication] (verify: negative-test -> verify_src002_s0063_a01)

### PRD-075: EF4-I55 — Prompt evolution quarantine

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I55 — Prompt evolution quarantine'.

- linked source rows: SRC002-S0064
- linked source atoms: (none)

### PRD-076: EF4-I56 — Evaluator updates are future-only

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I56 — Evaluator updates are future-only'.

- linked source rows: SRC002-S0065
- linked source atoms: SRC002-S0065-A01
- [ ] AC-PRD-076-01: Satisfy source atom SRC002-S0065-A01: Evaluator defects create quarantined proposals; approved changes apply to new sealed runs and never rewrite completed  (verify: negative-test -> verify_src002_s0065_a01)

### PRD-077: EF4-I57 — Surrogate is triage only

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I57 — Surrogate is triage only'.

- linked source rows: SRC002-S0066
- linked source atoms: SRC002-S0066-A01
- [ ] AC-PRD-077-01: Satisfy source atom SRC002-S0066-A01: A surrogate may prioritize direct evaluation but cannot replace required direct, hidden or replication stages. (verify: functional-test -> verify_src002_s0066_a01)

### PRD-078: EF4-I58 — Replication-gated promotion

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I58 — Replication-gated promotion'.

- linked source rows: SRC002-S0067
- linked source atoms: (none)

### PRD-079: EF4-I59 — Selection-bias visibility

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I59 — Selection-bias visibility'.

- linked source rows: SRC002-S0068
- linked source atoms: SRC002-S0068-A01
- [ ] AC-PRD-079-01: Satisfy source atom SRC002-S0068-A01: Top-candidate estimates disclose search/selection history, winner's curse risk and bias-corrected uncertainty. [constraints: search/selection] (verify: interface-check -> verify_src002_s0068_a01)

### PRD-080: EF4-I60 — Exact candidate reconciliation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I60 — Exact candidate reconciliation'.

- linked source rows: SRC002-S0069
- linked source atoms: SRC002-S0069-A01
- [ ] AC-PRD-080-01: Satisfy source atom SRC002-S0069-A01: Every fan-out reconciles proposed, generated, evaluated, persisted, failed, cancelled and missing candidate identities (verify: negative-test -> verify_src002_s0069_a01)

### PRD-081: EF4-I61 — Atomic evolution checkpoints

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I61 — Atomic evolution checkpoints'.

- linked source rows: SRC002-S0070
- linked source atoms: (none)

### PRD-082: EF4-I62 — Typed stop certificate

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I62 — Typed stop certificate'.

- linked source rows: SRC002-S0071
- linked source atoms: (none)

### PRD-083: EF4-I63 — External backend isolation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I63 — External backend isolation'.

- linked source rows: SRC002-S0072
- linked source atoms: SRC002-S0072-A01
- [ ] AC-PRD-083-01: Satisfy source atom SRC002-S0072-A01: ShinkaEvolve and other search engines are optional pinned adapters; their scores, archives, novelty and state never be (verify: negative-test -> verify_src002_s0072_a01)

### PRD-084: EF4-I64 — Executable candidate sandbox

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'EF4-I64 — Executable candidate sandbox'.

- linked source rows: SRC002-S0073
- linked source atoms: SRC002-S0073-A01
- [ ] AC-PRD-084-01: Satisfy source atom SRC002-S0073-A01: Candidate code executes only under declared capabilities, resource quotas, network policy, effect receipts and evaluat [constraints: evaluator/holdout] (verify: interface-check -> verify_src002_s0073_a01)

### PRD-086: 5. Module map

Cover 1 source coverage row(s) and 13 requirement atom(s) from section '5. Module map'.

- linked source rows: SRC002-S0075
- linked source atoms: SRC002-S0075-A01, SRC002-S0075-A02, SRC002-S0075-A03, SRC002-S0075-A04, SRC002-S0075-A05, SRC002-S0075-A06, SRC002-S0075-A07, SRC002-S0075-A08, SRC002-S0075-A09, SRC002-S0075-A10, SRC002-S0075-A11, SRC002-S0075-A12, SRC002-S0075-A13
- [ ] AC-PRD-086-01: Satisfy source atom SRC002-S0075-A01: **Native Plugin Shell** | Manifest, skills, hooks, MCP/CLI, capability probe and Console; never canonical authority. [constraints: MCP/CLI] (verify: negative-test -> verify_src002_s0075_a01)
- [ ] AC-PRD-086-02: Satisfy source atom SRC002-S0075-A02: **Foundry Kernel** | Immutable RunSpec, FORGE/EVOLVE state machine, DAG scheduler, policy, capabilities, effects, chec [constraints: FORGE/EVOLVE] (verify: interface-check -> verify_src002_s0075_a02)
- [ ] AC-PRD-086-03: Satisfy source atom SRC002-S0075-A04: **Epistemic Atlas** | Coverage, search state, method compatibility, evidence dependency, bias and epistemic niche maps (verify: risk-verification -> verify_src002_s0075_a04)
- [ ] AC-PRD-086-04: Satisfy source atom SRC002-S0075-A05: **Evolution Chamber** | Typed scientific populations, mutation/crossover, multi-objective quality-diversity search and [constraints: mutation/crossover] (verify: interface-check -> verify_src002_s0075_a05)
- [ ] AC-PRD-086-05: Satisfy source atom SRC002-S0075-A06: **Verifier Firewall** | Immutable evaluator, hidden/OOD holdout, leakage, calibration, metamorphic/adversarial qualifi [constraints: hidden/OOD; metamorphic/adversarial] (verify: interface-check -> verify_src002_s0075_a06)
- [ ] AC-PRD-086-06: Satisfy source atom SRC002-S0075-A10: **Epistemic Species Archive** | Pareto/niche elites plus protected nulls, counterexamples, failed replications, unsafe [constraints: Pareto/niche] (verify: negative-test -> verify_src002_s0075_a10)
- [ ] AC-PRD-086-07: Satisfy source atom SRC002-S0075-A12: **Validation Bay** | Evidence, simulation, formal, benchmark, hidden/OOD, experiment and replication stages with evide [constraints: hidden/OOD] (verify: interface-check -> verify_src002_s0075_a12)

### PRD-087: 6. Authority planes

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '6. Authority planes'.

- linked source rows: SRC002-S0076
- linked source atoms: SRC002-S0076-A01
- [ ] AC-PRD-087-01: Satisfy source atom SRC002-S0076-A01: The upper three planes cannot grant themselves rights in the lower authority plane. (verify: risk-verification -> verify_src002_s0076_a01)

### PRD-089: E-Graph — Evidence

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'E-Graph — Evidence'.

- linked source rows: SRC002-S0078
- linked source atoms: (none)

### PRD-090: R-Graph — Reasoning

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'R-Graph — Reasoning'.

- linked source rows: SRC002-S0079
- linked source atoms: (none)

### PRD-091: D-Graph — Deliberation

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'D-Graph — Deliberation'.

- linked source rows: SRC002-S0080
- linked source atoms: SRC002-S0080-A01
- [ ] AC-PRD-091-01: Satisfy source atom SRC002-S0080-A01: Blind briefs, objections, cross-examinations, method/scope veto, minority reports, adjudications, attestations, human  [constraints: method/scope] (verify: interface-check -> verify_src002_s0080_a01)

### PRD-093: Part IV — FORGE and EVOLVE protocols

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part IV — FORGE and EVOLVE protocols'.

- linked source rows: SRC002-S0082
- linked source atoms: (none)

### PRD-094: 8. FORGE

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '8. FORGE'.

- linked source rows: SRC002-S0083
- linked source atoms: SRC002-S0083-A01, SRC002-S0083-A02
- [ ] AC-PRD-094-01: Satisfy source atom SRC002-S0083-A01: An insight cannot leave Frame without canonical statement, scope, mechanism sketch, predictions and falsifiers. (verify: negative-test -> verify_src002_s0083_a01)
- [ ] AC-PRD-094-02: Satisfy source atom SRC002-S0083-A02: Observe must distinguish support/counter/null/boundary/method/prior-art lanes and `UNSEARCHED` from `SEARCHED_NONE`. [constraints: UNSEARCHED; SEARCHED_NONE; support/counter/null/boundary/method/prior-art] (verify: interface-check -> verify_src002_s0083_a02)

### PRD-095: 9. EVOLVE

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '9. EVOLVE'.

- linked source rows: SRC002-S0084
- linked source atoms: (none)

### PRD-096: Encode

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'Encode'.

- linked source rows: SRC002-S0085
- linked source atoms: SRC002-S0085-A01
- [ ] AC-PRD-096-01: Satisfy source atom SRC002-S0085-A01: Freeze `EvolutionRunSpec`, current evaluator/holdout, allowed candidate classes, seed populations, operator registry,  [constraints: EvolutionRunSpec; evaluator/holdout] (verify: interface-check -> verify_src002_s0085_a01)

### PRD-097: Vary

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'Vary'.

- linked source rows: SRC002-S0086
- linked source atoms: SRC002-S0086-A01
- [ ] AC-PRD-097-01: Satisfy source atom SRC002-S0086-A01: Select parents and operators, route models, mutate typed genomes or perform compatibility-gated crossover. (verify: risk-verification -> verify_src002_s0086_a01)

### PRD-098: Oppose

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'Oppose'.

- linked source rows: SRC002-S0087
- linked source atoms: SRC002-S0087-A01
- [ ] AC-PRD-098-01: Satisfy source atom SRC002-S0087-A01: Reproduce apparent failures and classify true refutation, scope restriction, method failure, measurement artifact or i (verify: negative-test -> verify_src002_s0087_a01)

### PRD-099: Learn

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'Learn'.

- linked source rows: SRC002-S0088
- linked source atoms: SRC002-S0088-A01
- [ ] AC-PRD-099-01: Satisfy source atom SRC002-S0088-A01: Compute uncertainty-bearing FitnessVectors, Pareto front, niche occupancy, lineage diversity and delayed model/operato [constraints: model/operator] (verify: interface-check -> verify_src002_s0088_a01)

### PRD-100: Validate

Cover 1 source coverage row(s) and 1 requirement atom(s) from section 'Validate'.

- linked source rows: SRC002-S0089
- linked source atoms: SRC002-S0089-A01
- [ ] AC-PRD-100-01: Satisfy source atom SRC002-S0089-A01: Apply hidden/OOD evaluation, multiple-testing/sequential policy, selective-inference correction and independent prereg [constraints: hidden/OOD; multiple-testing/sequential] (verify: interface-check -> verify_src002_s0089_a01)

### PRD-101: Elevate

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Elevate'.

- linked source rows: SRC002-S0090
- linked source atoms: (none)

### PRD-102: 10. State machine

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '10. State machine'.

- linked source rows: SRC002-S0091
- linked source atoms: SRC002-S0091-A01
- [ ] AC-PRD-102-01: Satisfy source atom SRC002-S0091-A01: Illegal transitions are defined in `docs/evolution_state_machine.md`. [constraints: docs/evolution_state_machine.md] (verify: interface-check -> verify_src002_s0091_a01)

### PRD-103: Part V — Scientific genome and evolutionary operators

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part V — Scientific genome and evolutionary operators'.

- linked source rows: SRC002-S0092
- linked source atoms: (none)

### PRD-104: 11. HypothesisGenome

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '11. HypothesisGenome'.

- linked source rows: SRC002-S0093
- linked source atoms: SRC002-S0093-A01, SRC002-S0093-A02
- [ ] AC-PRD-104-01: Satisfy source atom SRC002-S0093-A01: Required fields: (verify: functional-test -> verify_src002_s0093_a01)
- [ ] AC-PRD-104-02: Satisfy source atom SRC002-S0093-A02: A prose-only hypothesis is not eligible. (verify: negative-test -> verify_src002_s0093_a02)

### PRD-105: 12. Co-evolving populations

Cover 5 source coverage row(s) and 6 requirement atom(s) from section '12. Co-evolving populations'.

- linked source rows: SRC002-S0094-R001, SRC002-S0094-R002, SRC002-S0094-R003, SRC002-S0094-R004, SRC002-S0094-R005
- linked source atoms: SRC002-S0094-R001-A01, SRC002-S0094-R002-A01, SRC002-S0094-R003-A01, SRC002-S0094-R004-A01, SRC002-S0094-R005-A01, SRC002-S0094-R005-A02
- [ ] AC-PRD-105-01: Satisfy source atom SRC002-S0094-R002-A01: -: mechanism/model population; [constraints: mechanism/model] (verify: interface-check -> verify_src002_s0094_r002_a01)
- [ ] AC-PRD-105-02: Satisfy source atom SRC002-S0094-R003-A01: -: experiment/probe population; [constraints: experiment/probe] (verify: interface-check -> verify_src002_s0094_r003_a01)
- [ ] AC-PRD-105-03: Satisfy source atom SRC002-S0094-R004-A01: -: challenge/falsifier population; [constraints: challenge/falsifier] (verify: interface-check -> verify_src002_s0094_r004_a01)
- [ ] AC-PRD-105-04: Satisfy source atom SRC002-S0094-R005-A01: -: measurement/operationalization population. [constraints: measurement/operationalization] (verify: interface-check -> verify_src002_s0094_r005_a01)
- [ ] AC-PRD-105-05: Satisfy source atom SRC002-S0094-R005-A02: Prompt genomes and evaluator proposals live in quarantine, not the ordinary scientific population. (verify: negative-test -> verify_src002_s0094_r005_a02)

### PRD-106: 13. Mutation operators

Cover 12 source coverage row(s) and 13 requirement atom(s) from section '13. Mutation operators'.

- linked source rows: SRC002-S0095-R001, SRC002-S0095-R002, SRC002-S0095-R003, SRC002-S0095-R004, SRC002-S0095-R005, SRC002-S0095-R006, SRC002-S0095-R007, SRC002-S0095-R008, SRC002-S0095-R009, SRC002-S0095-R010, SRC002-S0095-R011, SRC002-S0095-R012
- linked source atoms: SRC002-S0095-R001-A01, SRC002-S0095-R002-A01, SRC002-S0095-R003-A01, SRC002-S0095-R004-A01, SRC002-S0095-R005-A01, SRC002-S0095-R006-A01, SRC002-S0095-R007-A01, SRC002-S0095-R008-A01, SRC002-S0095-R009-A01, SRC002-S0095-R010-A01, SRC002-S0095-R011-A01, SRC002-S0095-R012-A01, SRC002-S0095-R012-A02
- [ ] AC-PRD-106-01: Satisfy source atom SRC002-S0095-R012-A02: Each operator declares input/output types, preconditions, preserved invariants, changed paths, required audits, prompt [constraints: input/output] (verify: interface-check -> verify_src002_s0095_r012_a02)

### PRD-107: 14. Crossover

Cover 7 source coverage row(s) and 8 requirement atom(s) from section '14. Crossover'.

- linked source rows: SRC002-S0096-R001, SRC002-S0096-R002, SRC002-S0096-R003, SRC002-S0096-R004, SRC002-S0096-R005, SRC002-S0096-R006, SRC002-S0096-R007
- linked source atoms: SRC002-S0096-R001-A01, SRC002-S0096-R002-A01, SRC002-S0096-R003-A01, SRC002-S0096-R004-A01, SRC002-S0096-R005-A01, SRC002-S0096-R006-A01, SRC002-S0096-R006-A02, SRC002-S0096-R007-A01
- [ ] AC-PRD-107-01: Satisfy source atom SRC002-S0096-R001-A01: -: Scope compatibility; (verify: risk-verification -> verify_src002_s0096_r001_a01)
- [ ] AC-PRD-107-02: Satisfy source atom SRC002-S0096-R002-A01: -: Measurement compatibility; (verify: risk-verification -> verify_src002_s0096_r002_a01)
- [ ] AC-PRD-107-03: Satisfy source atom SRC002-S0096-R003-A01: -: Unit compatibility; (verify: risk-verification -> verify_src002_s0096_r003_a01)
- [ ] AC-PRD-107-04: Satisfy source atom SRC002-S0096-R004-A01: -: Causal compatibility; (verify: risk-verification -> verify_src002_s0096_r004_a01)
- [ ] AC-PRD-107-05: Satisfy source atom SRC002-S0096-R006-A02: An incompatible child is rejected before expensive evaluation. (verify: negative-test -> verify_src002_s0096_r006_a02)

### PRD-108: Part VI — Search and quality-diversity algorithm

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part VI — Search and quality-diversity algorithm'.

- linked source rows: SRC002-S0097
- linked source atoms: (none)

### PRD-109: 15. Hard gates and FitnessVector

Cover 2 source coverage row(s) and 3 requirement atom(s) from section '15. Hard gates and FitnessVector'.

- linked source rows: SRC002-S0098-R001, SRC002-S0098-R002
- linked source atoms: SRC002-S0098-R001-A01, SRC002-S0098-R002-A01, SRC002-S0098-R002-A02
- [ ] AC-PRD-109-01: Satisfy source atom SRC002-S0098-R001-A01: +: evaluator/holdout isolation + method floor [constraints: evaluator/holdout] (verify: interface-check -> verify_src002_s0098_r001_a01)
- [ ] AC-PRD-109-02: Satisfy source atom SRC002-S0098-R002-A02: grounding support counterevidence resistance predictive accuracy calibration robustness/OOD causal identifiability fal [constraints: robustness/OOD; safety/ethics] (verify: interface-check -> verify_src002_s0098_r002_a02)

### PRD-110: 16. Pareto selection

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '16. Pareto selection'.

- linked source rows: SRC002-S0099
- linked source atoms: SRC002-S0099-A01
- [ ] AC-PRD-110-01: Satisfy source atom SRC002-S0099-A01: Pareto rank guides search but does not prove truth. (verify: negative-test -> verify_src002_s0099_a01)

### PRD-111: 17. Epistemic MAP-Elites

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '17. Epistemic MAP-Elites'.

- linked source rows: SRC002-S0100
- linked source atoms: SRC002-S0100-A01, SRC002-S0100-A02
- [ ] AC-PRD-111-01: Satisfy source atom SRC002-S0100-A02: Niche occupancy and lineage diversity are product outputs, not hidden internals. (verify: negative-test -> verify_src002_s0100_a02)

### PRD-112: 18. Parent acquisition

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '18. Parent acquisition'.

- linked source rows: SRC002-S0101
- linked source atoms: SRC002-S0101-A01, SRC002-S0101-A02
- [ ] AC-PRD-112-01: Satisfy source atom SRC002-S0101-A01: An implementation may use UCB, Thompson or other bounded policy, but it must expose components equivalent to: (verify: functional-test -> verify_src002_s0101_a01)
- [ ] AC-PRD-112-02: Satisfy source atom SRC002-S0101-A02: The `ParentSelectionReceipt` records the eligible set, components, random seed and selected parents. [constraints: ParentSelectionReceipt] (verify: interface-check -> verify_src002_s0101_a02)

### PRD-113: 19. Model and operator routing

Cover 1 source coverage row(s) and 3 requirement atom(s) from section '19. Model and operator routing'.

- linked source rows: SRC002-S0102
- linked source atoms: SRC002-S0102-A01, SRC002-S0102-A02, SRC002-S0102-A03
- [ ] AC-PRD-113-01: Satisfy source atom SRC002-S0102-A01: Immediate proxy reward may improve throughput. (verify: risk-verification -> verify_src002_s0102_a01)
- [ ] AC-PRD-113-02: Satisfy source atom SRC002-S0102-A02: Scientific routing reward is delayed until hidden/OOD or replication results. [constraints: hidden/OOD] (verify: interface-check -> verify_src002_s0102_a02)
- [ ] AC-PRD-113-03: Satisfy source atom SRC002-S0102-A03: Different providers are not assumed statistically independent. (verify: negative-test -> verify_src002_s0102_a03)

### PRD-114: 20. Multi-fidelity evaluation

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '20. Multi-fidelity evaluation'.

- linked source rows: SRC002-S0103
- linked source atoms: (none)

### PRD-116: 21. EvaluatorBundle

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '21. EvaluatorBundle'.

- linked source rows: SRC002-S0105
- linked source atoms: SRC002-S0105-A01
- [ ] AC-PRD-116-01: Satisfy source atom SRC002-S0105-A01: A sealed bundle includes evaluator code, metrics, environment, policy, public fixtures, hidden/OOD manifests, metamorp [constraints: hidden/OOD] (verify: interface-check -> verify_src002_s0105_a01)

### PRD-117: 22. Qualification

Cover 11 source coverage row(s) and 11 requirement atom(s) from section '22. Qualification'.

- linked source rows: SRC002-S0106-R001, SRC002-S0106-R002, SRC002-S0106-R003, SRC002-S0106-R004, SRC002-S0106-R005, SRC002-S0106-R006, SRC002-S0106-R007, SRC002-S0106-R008, SRC002-S0106-R009, SRC002-S0106-R010, SRC002-S0106-R011
- linked source atoms: SRC002-S0106-R001-A01, SRC002-S0106-R002-A01, SRC002-S0106-R003-A01, SRC002-S0106-R004-A01, SRC002-S0106-R005-A01, SRC002-S0106-R006-A01, SRC002-S0106-R007-A01, SRC002-S0106-R008-A01, SRC002-S0106-R009-A01, SRC002-S0106-R010-A01, SRC002-S0106-R011-A01
- [ ] AC-PRD-117-01: Satisfy source atom SRC002-S0106-R003-A01: 3: leakage audit; (verify: risk-verification -> verify_src002_s0106_r003_a01)
- [ ] AC-PRD-117-02: Satisfy source atom SRC002-S0106-R004-A01: 4: deterministic/crash tests; [constraints: deterministic/crash] (verify: interface-check -> verify_src002_s0106_r004_a01)
- [ ] AC-PRD-117-03: Satisfy source atom SRC002-S0106-R007-A01: 7: false-positive/false-negative gold comparison; [constraints: false-positive/false-negative] (verify: interface-check -> verify_src002_s0106_r007_a01)
- [ ] AC-PRD-117-04: Satisfy source atom SRC002-S0106-R008-A01: 8: calibration/OOD assessment; [constraints: calibration/OOD] (verify: interface-check -> verify_src002_s0106_r008_a01)

### PRD-118: 23. Future-only evaluator evolution

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '23. Future-only evaluator evolution'.

- linked source rows: SRC002-S0107
- linked source atoms: SRC002-S0107-A01, SRC002-S0107-A02
- [ ] AC-PRD-118-01: Satisfy source atom SRC002-S0107-A01: A candidate may submit an `EvaluatorMutationProposal`. [constraints: EvaluatorMutationProposal] (verify: interface-check -> verify_src002_s0107_a01)

### PRD-119: Part VIII — Red Queen, archive and scientific memory

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part VIII — Red Queen, archive and scientific memory'.

- linked source rows: SRC002-S0108
- linked source atoms: (none)

### PRD-120: 24. Red Queen Lab

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '24. Red Queen Lab'.

- linked source rows: SRC002-S0109
- linked source atoms: SRC002-S0109-A01, SRC002-S0109-A02
- [ ] AC-PRD-120-01: Satisfy source atom SRC002-S0109-A01: A successful challenge must reproduce. (verify: functional-test -> verify_src002_s0109_a01)
- [ ] AC-PRD-120-02: Satisfy source atom SRC002-S0109-A02: Its result is typed as `REFUTED`, `SCOPE_RESTRICTED`, `METHOD_FAILURE`, `INCONCLUSIVE` or another explicit state. [constraints: REFUTED; SCOPE_RESTRICTED; METHOD_FAILURE; INCONCLUSIVE] (verify: interface-check -> verify_src002_s0109_a02)

### PRD-121: 25. Epistemic Species Archive

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '25. Epistemic Species Archive'.

- linked source rows: SRC002-S0110
- linked source atoms: SRC002-S0110-A01
- [ ] AC-PRD-121-01: Satisfy source atom SRC002-S0110-A01: Archive changes require an independently audited `ArchiveRebalancePlan`. [constraints: ArchiveRebalancePlan] (verify: interface-check -> verify_src002_s0110_a01)

### PRD-122: 26. Semantic islands

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '26. Semantic islands'.

- linked source rows: SRC002-S0111
- linked source atoms: SRC002-S0111-A01, SRC002-S0111-A02
- [ ] AC-PRD-122-01: Satisfy source atom SRC002-S0111-A01: Migration creates a new revision and requires compatibility. (verify: risk-verification -> verify_src002_s0111_a01)
- [ ] AC-PRD-122-02: Satisfy source atom SRC002-S0111-A02: Dynamic island creation requires documented coverage debt/stagnation, budget and stop conditions. [constraints: debt/stagnation] (verify: interface-check -> verify_src002_s0111_a02)

### PRD-123: Part IX — Adaptive-search statistical governance

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part IX — Adaptive-search statistical governance'.

- linked source rows: SRC002-S0112
- linked source atoms: (none)

### PRD-124: 27. Selection problem

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '27. Selection problem'.

- linked source rows: SRC002-S0113
- linked source atoms: SRC002-S0113-A01
- [ ] AC-PRD-124-01: Satisfy source atom SRC002-S0113-A01: Therefore naive estimates for the winner are biased and repeated public/hidden feedback can leak test information. [constraints: public/hidden] (verify: interface-check -> verify_src002_s0113_a01)

### PRD-125: 28. Required artifacts

Cover 7 source coverage row(s) and 7 requirement atom(s) from section '28. Required artifacts'.

- linked source rows: SRC002-S0114-R001, SRC002-S0114-R002, SRC002-S0114-R003, SRC002-S0114-R004, SRC002-S0114-R005, SRC002-S0114-R006, SRC002-S0114-R007
- linked source atoms: SRC002-S0114-R001-A01, SRC002-S0114-R002-A01, SRC002-S0114-R003-A01, SRC002-S0114-R004-A01, SRC002-S0114-R005-A01, SRC002-S0114-R006-A01, SRC002-S0114-R007-A01
- [ ] AC-PRD-125-01: Satisfy source atom SRC002-S0114-R001-A01: -: `SequentialTestingLedger` [constraints: SequentialTestingLedger] (verify: interface-check -> verify_src002_s0114_r001_a01)
- [ ] AC-PRD-125-02: Satisfy source atom SRC002-S0114-R002-A01: -: `MultipleTestingAdjustment` [constraints: MultipleTestingAdjustment] (verify: interface-check -> verify_src002_s0114_r002_a01)
- [ ] AC-PRD-125-03: Satisfy source atom SRC002-S0114-R003-A01: -: `SelectiveInferenceReport` [constraints: SelectiveInferenceReport] (verify: interface-check -> verify_src002_s0114_r003_a01)
- [ ] AC-PRD-125-04: Satisfy source atom SRC002-S0114-R005-A01: -: candidate family/lineage [constraints: family/lineage] (verify: interface-check -> verify_src002_s0114_r005_a01)

### PRD-126: 29. Allowed policies

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '29. Allowed policies'.

- linked source rows: SRC002-S0115
- linked source atoms: SRC002-S0115-A01, SRC002-S0115-A02
- [ ] AC-PRD-126-01: Satisfy source atom SRC002-S0115-A01: Domain-specific justified choices include fixed nested holdout, alpha spending/investing, e-values/e-processes, Bayesi [constraints: spending/investing; e-values/e-processes; hierarchical/FDR] (verify: interface-check -> verify_src002_s0115_a01)
- [ ] AC-PRD-126-02: Satisfy source atom SRC002-S0115-A02: `none_justified` imposes a non-inferential promotion ceiling. [constraints: none_justified] (verify: interface-check -> verify_src002_s0115_a02)

### PRD-127: 30. Replication

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '30. Replication'.

- linked source rows: SRC002-S0116
- linked source atoms: (none)

### PRD-128: Part X — ShinkaEvolve adapter

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part X — ShinkaEvolve adapter'.

- linked source rows: SRC002-S0117
- linked source atoms: (none)

### PRD-129: 31. Role

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '31. Role'.

- linked source rows: SRC002-S0118
- linked source atoms: SRC002-S0118-A01
- [ ] AC-PRD-129-01: Satisfy source atom SRC002-S0118-A01: The domain-neutral core continues to work without it. (verify: negative-test -> verify_src002_s0118_a01)

### PRD-130: 32. Mapping

Cover 1 source coverage row(s) and 11 requirement atom(s) from section '32. Mapping'.

- linked source rows: SRC002-S0119
- linked source atoms: SRC002-S0119-A01, SRC002-S0119-A02, SRC002-S0119-A03, SRC002-S0119-A04, SRC002-S0119-A05, SRC002-S0119-A06, SRC002-S0119-A07, SRC002-S0119-A08, SRC002-S0119-A09, SRC002-S0119-A10, SRC002-S0119-A11
- [ ] AC-PRD-130-01: Satisfy source atom SRC002-S0119-A02: parent/inspiration | parent/inspiration IDs [constraints: parent/inspiration] (verify: interface-check -> verify_src002_s0119_a02)
- [ ] AC-PRD-130-02: Satisfy source atom SRC002-S0119-A03: generation/island | EvolutionCheckpoint / IslandState [constraints: generation/island] (verify: interface-check -> verify_src002_s0119_a03)
- [ ] AC-PRD-130-03: Satisfy source atom SRC002-S0119-A11: attempt/event | Noetic Ledger attempt/effect [constraints: attempt/event; attempt/effect] (verify: interface-check -> verify_src002_s0119_a11)

### PRD-132: Part XI — Plugin and user experience

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part XI — Plugin and user experience'.

- linked source rows: SRC002-S0121
- linked source atoms: (none)

### PRD-133: 34. Reference skills

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '34. Reference skills'.

- linked source rows: SRC002-S0122
- linked source atoms: SRC002-S0122-A01, SRC002-S0122-A02
- [ ] AC-PRD-133-01: Satisfy source atom SRC002-S0122-A01: v4 adds evolution-specific progressive skills for setup, conversion, run, inspection, evaluator audit, challenge, arch (verify: risk-verification -> verify_src002_s0122_a01)
- [ ] AC-PRD-133-02: Satisfy source atom SRC002-S0122-A02: Skills route requests; they do not own state or authority. (verify: negative-test -> verify_src002_s0122_a02)

### PRD-134: 35. Proposed CLI

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '35. Proposed CLI'.

- linked source rows: SRC002-S0123
- linked source atoms: (none)

### PRD-135: 36. Console

Cover 11 source coverage row(s) and 12 requirement atom(s) from section '36. Console'.

- linked source rows: SRC002-S0124-R001, SRC002-S0124-R002, SRC002-S0124-R003, SRC002-S0124-R004, SRC002-S0124-R005, SRC002-S0124-R006, SRC002-S0124-R007, SRC002-S0124-R008, SRC002-S0124-R009, SRC002-S0124-R010, SRC002-S0124-R011
- linked source atoms: SRC002-S0124-R001-A01, SRC002-S0124-R002-A01, SRC002-S0124-R003-A01, SRC002-S0124-R004-A01, SRC002-S0124-R005-A01, SRC002-S0124-R006-A01, SRC002-S0124-R007-A01, SRC002-S0124-R008-A01, SRC002-S0124-R009-A01, SRC002-S0124-R010-A01, SRC002-S0124-R010-A02, SRC002-S0124-R011-A01

### PRD-136: Part XII — Canonical workflows

Cover 1 source coverage row(s) and 22 requirement atom(s) from section 'Part XII — Canonical workflows'.

- linked source rows: SRC002-S0125
- linked source atoms: SRC002-S0125-A01, SRC002-S0125-A02, SRC002-S0125-A03, SRC002-S0125-A04, SRC002-S0125-A05, SRC002-S0125-A06, SRC002-S0125-A07, SRC002-S0125-A08, SRC002-S0125-A09, SRC002-S0125-A10, SRC002-S0125-A11, SRC002-S0125-A12, SRC002-S0125-A13, SRC002-S0125-A14, SRC002-S0125-A15, SRC002-S0125-A16, SRC002-S0125-A17, SRC002-S0125-A18, SRC002-S0125-A19, SRC002-S0125-A20, SRC002-S0125-A21, SRC002-S0125-A22
- [ ] AC-PRD-136-01: Satisfy source atom SRC002-S0125-A01: `archive_rebalancing` | 11 | Rebalance quality-diversity archives without erasing negative scientific memory. [constraints: archive_rebalancing] (verify: negative-test -> verify_src002_s0125_a01)
- [ ] AC-PRD-136-02: Satisfy source atom SRC002-S0125-A02: `claim_extraction` | 13 | Select evidence units, extract atomic claims, verify grounding, and create dependency-aware  [constraints: claim_extraction] (verify: interface-check -> verify_src002_s0125_a02)
- [ ] AC-PRD-136-03: Satisfy source atom SRC002-S0125-A03: `corpus_ingest` | 11 | Register, integrity-screen, parse, reconcile, and release immutable source documents. [constraints: corpus_ingest] (verify: interface-check -> verify_src002_s0125_a03)
- [ ] AC-PRD-136-04: Satisfy source atom SRC002-S0125-A04: `evaluation_release` | 16 | Run specification, plugin compatibility, scientific, security, calibration, recovery, cros [constraints: evaluation_release] (verify: interface-check -> verify_src002_s0125_a04)
- [ ] AC-PRD-136-05: Satisfy source atom SRC002-S0125-A05: `evaluator_update_governance` | 14 | Govern evaluator evolution in quarantine and apply changes only to future sealed  [constraints: evaluator_update_governance] (verify: interface-check -> verify_src002_s0125_a05)
- [ ] AC-PRD-136-06: Satisfy source atom SRC002-S0125-A06: `evidence_retrieval` | 20 | Compile a relation-aware query plan, execute eleven evidence lanes, and issue a completene [constraints: evidence_retrieval] (verify: interface-check -> verify_src002_s0125_a06)
- [ ] AC-PRD-136-07: Satisfy source atom SRC002-S0125-A07: `evidence_update_reassessment` | 12 | Detect evidence or policy changes, compute impact, invalidate stale state, rerun [constraints: evidence_update_reassessment] (verify: interface-check -> verify_src002_s0125_a07)
- [ ] AC-PRD-136-08: Satisfy source atom SRC002-S0125-A08: `evolution_chamber_cycle` | 26 | Run one governed quality-diversity hypothesis evolution cycle under immutable evaluat [constraints: evolution_chamber_cycle] (verify: interface-check -> verify_src002_s0125_a08)
- [ ] AC-PRD-136-09: Satisfy source atom SRC002-S0125-A09: `evolution_release` | 15 | Validate and package v4 specification and later implementation releases without maturity ov [constraints: evolution_release] (verify: negative-test -> verify_src002_s0125_a09)
- [ ] AC-PRD-136-10: Satisfy source atom SRC002-S0125-A10: `forge_research_cycle` | 26 | Execute the research-native FORGE lifecycle from classification to Passport. [constraints: forge_research_cycle] (verify: interface-check -> verify_src002_s0125_a10)
- [ ] AC-PRD-136-11: Satisfy source atom SRC002-S0125-A11: `hypothesis_replication` | 12 | Run independent preregistered replication and propagate its result without rewriting h [constraints: hypothesis_replication] (verify: negative-test -> verify_src002_s0125_a11)
- [ ] AC-PRD-136-12: Satisfy source atom SRC002-S0125-A12: `insight_deliberation` | 27 | Run asymmetric evidence deliberation, adversarial challenge, stability analysis, attesta [constraints: insight_deliberation] (verify: interface-check -> verify_src002_s0125_a12)
- [ ] AC-PRD-136-13: Satisfy source atom SRC002-S0125-A13: `memory_recall` | 8 | Retrieve prior context under explicit purpose, consent, scope, redaction and receipts. [constraints: memory_recall] (verify: interface-check -> verify_src002_s0125_a13)
- [ ] AC-PRD-136-14: Satisfy source atom SRC002-S0125-A14: `plugin_bootstrap` | 12 | Initialize a native host session without surrendering authority to host chat state. [constraints: plugin_bootstrap] (verify: negative-test -> verify_src002_s0125_a14)
- [ ] AC-PRD-136-15: Satisfy source atom SRC002-S0125-A15: `plugin_release` | 16 | Build, test, audit, sign and package the native plugin without overstating implementation matu [constraints: plugin_release] (verify: negative-test -> verify_src002_s0125_a15)
- [ ] AC-PRD-136-16: Satisfy source atom SRC002-S0125-A16: `plugin_upgrade_migration` | 12 | Upgrade or roll back the plugin with package verification, hook trust, migration dry [constraints: plugin_upgrade_migration] (verify: interface-check -> verify_src002_s0125_a16)
- [ ] AC-PRD-136-17: Satisfy source atom SRC002-S0125-A17: `red_queen_challenge_coevolution` | 14 | Co-evolve a diverse falsifier population against hypotheses without turning a [constraints: red_queen_challenge_coevolution] (verify: negative-test -> verify_src002_s0125_a17)
- [ ] AC-PRD-136-18: Satisfy source atom SRC002-S0125-A18: `shinka_backend_qualification` | 13 | Qualify ShinkaEvolve as an optional executable-program search backend behind Fou [constraints: shinka_backend_qualification] (verify: interface-check -> verify_src002_s0125_a18)
- [ ] AC-PRD-136-19: Satisfy source atom SRC002-S0125-A19: `skill_acquisition` | 12 | Discover and activate third-party skills through a supply-chain quarantine and lockfile. [constraints: skill_acquisition] (verify: interface-check -> verify_src002_s0125_a19)
- [ ] AC-PRD-136-20: Satisfy source atom SRC002-S0125-A20: `validation_execution` | 13 | Screen an optional validation target, preregister and authorize a plan, execute it safel [constraints: validation_execution] (verify: interface-check -> verify_src002_s0125_a20)
- [ ] AC-PRD-136-21: Satisfy source atom SRC002-S0125-A21: `verifier_firewall_qualification` | 14 | Qualify evaluators as fallible scientific instruments before they can score c [constraints: verifier_firewall_qualification] (verify: interface-check -> verify_src002_s0125_a21)
- [ ] AC-PRD-136-22: Satisfy source atom SRC002-S0125-A22: `workspace_mapping` | 10 | Create auditable code, research, artifact and authority maps with real baseline and query-s [constraints: workspace_mapping] (verify: interface-check -> verify_src002_s0125_a22)

### PRD-137: Part XIII — A–Z implementation graph

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part XIII — A–Z implementation graph'.

- linked source rows: SRC002-S0126
- linked source atoms: (none)

### PRD-138: 37. Execution rules

Cover 8 source coverage row(s) and 8 requirement atom(s) from section '37. Execution rules'.

- linked source rows: SRC002-S0127-R001, SRC002-S0127-R002, SRC002-S0127-R003, SRC002-S0127-R004, SRC002-S0127-R005, SRC002-S0127-R006, SRC002-S0127-R007, SRC002-S0127-R008
- linked source atoms: SRC002-S0127-R001-A01, SRC002-S0127-R002-A01, SRC002-S0127-R003-A01, SRC002-S0127-R004-A01, SRC002-S0127-R005-A01, SRC002-S0127-R006-A01, SRC002-S0127-R007-A01, SRC002-S0127-R008-A01
- [ ] AC-PRD-138-01: Satisfy source atom SRC002-S0127-R004-A01: -: Authors never approve their own packages. (verify: negative-test -> verify_src002_s0127_r004_a01)
- [ ] AC-PRD-138-02: Satisfy source atom SRC002-S0127-R006-A01: -: Missing evaluator, holdout, statistical family or authority semantics returns `SPEC_GAP`. [constraints: SPEC_GAP] (verify: interface-check -> verify_src002_s0127_r006_a01)
- [ ] AC-PRD-138-03: Satisfy source atom SRC002-S0127-R007-A01: -: Missing external capability/credential/licensed data returns `BLOCKED`. [constraints: BLOCKED; capability/credential/licensed] (verify: interface-check -> verify_src002_s0127_r007_a01)
- [ ] AC-PRD-138-04: Satisfy source atom SRC002-S0127-R008-A01: -: Leakage, reward hacking, silent missing worker, unreconciled effect or non-waivable integrity failure returns `FAIL [constraints: FAIL] (verify: negative-test -> verify_src002_s0127_r008_a01)

### PRD-139: 38. Full package inventory

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '38. Full package inventory'.

- linked source rows: SRC002-S0128
- linked source atoms: (none)

### PRD-141: B — Build and reproducibility

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'B — Build and reproducibility'.

- linked source rows: SRC002-S0130-R001, SRC002-S0130-R002, SRC002-S0130-R003, SRC002-S0130-R004, SRC002-S0130-R005, SRC002-S0130-R006
- linked source atoms: SRC002-S0130-R001-A01, SRC002-S0130-R002-A01, SRC002-S0130-R003-A01, SRC002-S0130-R004-A01, SRC002-S0130-R005-A01, SRC002-S0130-R006-A01
- [ ] AC-PRD-141-01: Satisfy source atom SRC002-S0130-R001-A01: -: **B01 — Polyglot monorepo scaffold and package boundaries** Dependencies: `A04` · Risk: `medium` · Review: `require [constraints: A04; medium; required] (verify: interface-check -> verify_src002_s0130_r001_a01)
- [ ] AC-PRD-141-02: Satisfy source atom SRC002-S0130-R002-A01: -: **B02 — Pinned toolchains, lockfiles and deterministic build** Dependencies: `B01` · Risk: `medium` · Review: `requ [constraints: B01; medium; required] (verify: interface-check -> verify_src002_s0130_r002_a01)
- [ ] AC-PRD-141-03: Satisfy source atom SRC002-S0130-R003-A01: -: **B03 — Cross-platform CI and cache policy** Dependencies: `B01` · Risk: `medium` · Review: `required` [constraints: B01; medium; required] (verify: interface-check -> verify_src002_s0130_r003_a01)
- [ ] AC-PRD-141-04: Satisfy source atom SRC002-S0130-R004-A01: -: **B04 — B-phase build gate** Dependencies: `B02, B03` · Risk: `medium` · Review: `required` [constraints: B02, B03; medium; required] (verify: interface-check -> verify_src002_s0130_r004_a01)
- [ ] AC-PRD-141-05: Satisfy source atom SRC002-S0130-R005-A01: -: **B05 — Deterministic v4 build, dependency pinning and Shinka optional-feature profile** Dependencies: `A06, B04` · [constraints: A06, B04; high; required] (verify: interface-check -> verify_src002_s0130_r005_a01)
- [ ] AC-PRD-141-06: Satisfy source atom SRC002-S0130-R006-A01: -: **B06 — Reproducible build and backend-pin integration gate** Dependencies: `B05, C05, S05` · Risk: `critical` · Re [constraints: B05, C05, S05; critical; required] (verify: interface-check -> verify_src002_s0130_r006_a01)

### PRD-142: C — Canonical contracts and code generation

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'C — Canonical contracts and code generation'.

- linked source rows: SRC002-S0131-R001, SRC002-S0131-R002, SRC002-S0131-R003, SRC002-S0131-R004, SRC002-S0131-R005, SRC002-S0131-R006
- linked source atoms: SRC002-S0131-R001-A01, SRC002-S0131-R002-A01, SRC002-S0131-R003-A01, SRC002-S0131-R004-A01, SRC002-S0131-R005-A01, SRC002-S0131-R006-A01
- [ ] AC-PRD-142-01: Satisfy source atom SRC002-S0131-R001-A01: -: **C01 — v4 JSON Schema and OpenAPI authority** Dependencies: `A04` · Risk: `critical` · Review: `required` [constraints: A04; critical; required] (verify: interface-check -> verify_src002_s0131_r001_a01)
- [ ] AC-PRD-142-02: Satisfy source atom SRC002-S0131-R002-A01: -: **C02 — TypeScript, Python and UI model generation** Dependencies: `C01` · Risk: `medium` · Review: `required` [constraints: C01; medium; required] (verify: interface-check -> verify_src002_s0131_r002_a01)
- [ ] AC-PRD-142-03: Satisfy source atom SRC002-S0131-R003-A01: -: **C03 — Compatibility windows and schema migration contracts** Dependencies: `C01` · Risk: `medium` · Review: `requ [constraints: C01; medium; required] (verify: interface-check -> verify_src002_s0131_r003_a01)
- [ ] AC-PRD-142-04: Satisfy source atom SRC002-S0131-R004-A01: -: **C04 — C-phase contract conformance gate** Dependencies: `C02, C03` · Risk: `critical` · Review: `required` [constraints: C02, C03; critical; required] (verify: interface-check -> verify_src002_s0131_r004_a01)
- [ ] AC-PRD-142-05: Satisfy source atom SRC002-S0131-R005-A01: -: **C05 — Evolution genome, evaluator, archive, statistics and adapter schema implementation** Dependencies: `A06, C0 [constraints: A06, C04; critical; required] (verify: interface-check -> verify_src002_s0131_r005_a01)
- [ ] AC-PRD-142-06: Satisfy source atom SRC002-S0131-R006-A01: -: **C06 — Generated types, fixtures and compatibility integration gate** Dependencies: `C05` · Risk: `critical` · Rev [constraints: C05; critical; required] (verify: interface-check -> verify_src002_s0131_r006_a01)

### PRD-143: D — Durable state and artifacts

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'D — Durable state and artifacts'.

- linked source rows: SRC002-S0132-R001, SRC002-S0132-R002, SRC002-S0132-R003, SRC002-S0132-R004, SRC002-S0132-R005, SRC002-S0132-R006
- linked source atoms: SRC002-S0132-R001-A01, SRC002-S0132-R002-A01, SRC002-S0132-R003-A01, SRC002-S0132-R004-A01, SRC002-S0132-R005-A01, SRC002-S0132-R006-A01
- [ ] AC-PRD-143-01: Satisfy source atom SRC002-S0132-R001-A01: -: **D01 — SQLite WAL local canonical store** Dependencies: `B04, C04` · Risk: `critical` · Review: `required` [constraints: B04, C04; critical; required] (verify: interface-check -> verify_src002_s0132_r001_a01)
- [ ] AC-PRD-143-02: Satisfy source atom SRC002-S0132-R002-A01: -: **D02 — PostgreSQL team store and tenant isolation** Dependencies: `D01` · Risk: `medium` · Review: `required` [constraints: D01; medium; required] (verify: interface-check -> verify_src002_s0132_r002_a01)
- [ ] AC-PRD-143-03: Satisfy source atom SRC002-S0132-R003-A01: -: **D03 — Content-addressed artifact store and receipts** Dependencies: `D01` · Risk: `medium` · Review: `required` [constraints: D01; medium; required] (verify: interface-check -> verify_src002_s0132_r003_a01)
- [ ] AC-PRD-143-04: Satisfy source atom SRC002-S0132-R004-A01: -: **D04 — D-phase backup, corruption and recovery gate** Dependencies: `D02, D03` · Risk: `critical` · Review: `requi [constraints: D02, D03; critical; required] (verify: interface-check -> verify_src002_s0132_r004_a01)
- [ ] AC-PRD-143-05: Satisfy source atom SRC002-S0132-R005-A01: -: **D05 — Lineage, quality-diversity archive, island and checkpoint transactional store** Dependencies: `A06, D04, C0 [constraints: A06, D04, C05; critical; required] (verify: interface-check -> verify_src002_s0132_r005_a01)
- [ ] AC-PRD-143-06: Satisfy source atom SRC002-S0132-R006-A01: -: **D06 — Archive migration, crash recovery and atomic checkpoint integration gate** Dependencies: `D05, E05` · Risk: [constraints: D05, E05; critical; required] (verify: interface-check -> verify_src002_s0132_r006_a01)

### PRD-144: E — Events, effects and capabilities

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'E — Events, effects and capabilities'.

- linked source rows: SRC002-S0133-R001, SRC002-S0133-R002, SRC002-S0133-R003, SRC002-S0133-R004, SRC002-S0133-R005, SRC002-S0133-R006
- linked source atoms: SRC002-S0133-R001-A01, SRC002-S0133-R002-A01, SRC002-S0133-R003-A01, SRC002-S0133-R004-A01, SRC002-S0133-R005-A01, SRC002-S0133-R006-A01
- [ ] AC-PRD-144-01: Satisfy source atom SRC002-S0133-R001-A01: -: **E01 — Append-only Noetic Ledger and reducer** Dependencies: `C04, D04` · Risk: `critical` · Review: `required` [constraints: C04, D04; critical; required] (verify: interface-check -> verify_src002_s0133_r001_a01)
- [ ] AC-PRD-144-02: Satisfy source atom SRC002-S0133-R002-A01: -: **E02 — ActionIntent, Attempt and EffectReceipt** Dependencies: `E01` · Risk: `medium` · Review: `required` [constraints: E01; medium; required] (verify: interface-check -> verify_src002_s0133_r002_a01)
- [ ] AC-PRD-144-03: Satisfy source atom SRC002-S0133-R003-A01: -: **E03 — Capability leases, fencing and approval policy** Dependencies: `E01` · Risk: `medium` · Review: `required` [constraints: E01; medium; required] (verify: interface-check -> verify_src002_s0133_r003_a01)
- [ ] AC-PRD-144-04: Satisfy source atom SRC002-S0133-R004-A01: -: **E04 — E-phase strict and semantic replay gate** Dependencies: `E02, E03` · Risk: `critical` · Review: `required` [constraints: E02, E03; critical; required] (verify: interface-check -> verify_src002_s0133_r004_a01)
- [ ] AC-PRD-144-05: Satisfy source atom SRC002-S0133-R005-A01: -: **E05 — Candidate action/effect, mutation receipt and count-reconciliation engine** Dependencies: `A06, E04, C05` · [constraints: A06, E04, C05; high; required; action/effect] (verify: interface-check -> verify_src002_s0133_r005_a01)
- [ ] AC-PRD-144-06: Satisfy source atom SRC002-S0133-R006-A01: -: **E06 — Concurrent candidate effect and idempotency integration gate** Dependencies: `E05` · Risk: `critical` · Rev [constraints: E05; critical; required] (verify: interface-check -> verify_src002_s0133_r006_a01)

### PRD-145: F — FORGE lifecycle

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'F — FORGE lifecycle'.

- linked source rows: SRC002-S0134-R001, SRC002-S0134-R002, SRC002-S0134-R003, SRC002-S0134-R004, SRC002-S0134-R005, SRC002-S0134-R006
- linked source atoms: SRC002-S0134-R001-A01, SRC002-S0134-R002-A01, SRC002-S0134-R003-A01, SRC002-S0134-R004-A01, SRC002-S0134-R005-A01, SRC002-S0134-R006-A01
- [ ] AC-PRD-145-01: Satisfy source atom SRC002-S0134-R001-A01: -: **F01 — E0-E5 epistemic work classifier** Dependencies: `C04, E04` · Risk: `critical` · Review: `required` [constraints: C04, E04; critical; required] (verify: interface-check -> verify_src002_s0134_r001_a01)
- [ ] AC-PRD-145-02: Satisfy source atom SRC002-S0134-R002-A01: -: **F02 — FORGE FSM and legal return edges** Dependencies: `F01` · Risk: `medium` · Review: `required` [constraints: F01; medium; required] (verify: interface-check -> verify_src002_s0134_r002_a01)
- [ ] AC-PRD-145-03: Satisfy source atom SRC002-S0134-R003-A01: -: **F03 — Artifact-receipt transition gates** Dependencies: `F01` · Risk: `medium` · Review: `required` [constraints: F01; medium; required] (verify: interface-check -> verify_src002_s0134_r003_a01)
- [ ] AC-PRD-145-04: Satisfy source atom SRC002-S0134-R004-A01: -: **F04 — F-phase end-to-end E1/E3/E5 flows** Dependencies: `F02, F03` · Risk: `critical` · Review: `required` [constraints: F02, F03; critical; required; E1/E3/E5] (verify: interface-check -> verify_src002_s0134_r004_a01)
- [ ] AC-PRD-145-05: Satisfy source atom SRC002-S0134-R005-A01: -: **F05 — EVOLVE subprotocol state machine, return edges and typed stop certificates** Dependencies: `A06, F04, C05`  [constraints: A06, F04, C05; critical; required] (verify: interface-check -> verify_src002_s0134_r005_a01)
- [ ] AC-PRD-145-06: Satisfy source atom SRC002-S0134-R006-A01: -: **F06 — FORGE–EVOLVE lifecycle integration and replay gate** Dependencies: `F05, I05, R05` · Risk: `critical` · Rev [constraints: F05, I05, R05; critical; required] (verify: interface-check -> verify_src002_s0134_r006_a01)

### PRD-146: G — Plugin package and gateway

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'G — Plugin package and gateway'.

- linked source rows: SRC002-S0135-R001, SRC002-S0135-R002, SRC002-S0135-R003, SRC002-S0135-R004, SRC002-S0135-R005, SRC002-S0135-R006
- linked source atoms: SRC002-S0135-R001-A01, SRC002-S0135-R002-A01, SRC002-S0135-R003-A01, SRC002-S0135-R004-A01, SRC002-S0135-R005-A01, SRC002-S0135-R006-A01
- [ ] AC-PRD-146-01: Satisfy source atom SRC002-S0135-R001-A01: -: **G01 — Native plugin manifest and package layout** Dependencies: `B04, C04, S01` · Risk: `high` · Review: `require [constraints: B04, C04, S01; high; required] (verify: interface-check -> verify_src002_s0135_r001_a01)
- [ ] AC-PRD-146-02: Satisfy source atom SRC002-S0135-R002-A01: -: **G02 — Payload-resident efoundry dispatcher** Dependencies: `G01` · Risk: `high` · Review: `required` [constraints: G01; high; required] (verify: interface-check -> verify_src002_s0135_r002_a01)
- [ ] AC-PRD-146-03: Satisfy source atom SRC002-S0135-R003-A01: -: **G03 — PLUGIN_ROOT/PLUGIN_DATA and workspace resolution** Dependencies: `G01` · Risk: `high` · Review: `required` [constraints: G01; high; required; PLUGIN_ROOT/PLUGIN_DATA; PLUGIN_ROOT; PLUGIN_DATA] (verify: interface-check -> verify_src002_s0135_r003_a01)
- [ ] AC-PRD-146-04: Satisfy source atom SRC002-S0135-R004-A01: -: **G04 — G-phase local marketplace fresh-install gate** Dependencies: `G02, G03` · Risk: `high` · Review: `required` [constraints: G02, G03; high; required] (verify: interface-check -> verify_src002_s0135_r004_a01)
- [ ] AC-PRD-146-05: Satisfy source atom SRC002-S0135-R005-A01: -: **G05 — Evolution plugin skills, CLI surface and progressive-disclosure routing** Dependencies: `A06, G04, C05` · R [constraints: A06, G04, C05; high; required] (verify: interface-check -> verify_src002_s0135_r005_a01)
- [ ] AC-PRD-146-06: Satisfy source atom SRC002-S0135-R006-A01: -: **G06 — Native plugin packaging and skill-discovery integration gate** Dependencies: `G05, H05, T05` · Risk: `criti [constraints: G05, H05, T05; critical; required] (verify: interface-check -> verify_src002_s0135_r006_a01)

### PRD-147: H — Host hooks and capability negotiation

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'H — Host hooks and capability negotiation'.

- linked source rows: SRC002-S0136-R001, SRC002-S0136-R002, SRC002-S0136-R003, SRC002-S0136-R004, SRC002-S0136-R005, SRC002-S0136-R006
- linked source atoms: SRC002-S0136-R001-A01, SRC002-S0136-R002-A01, SRC002-S0136-R003-A01, SRC002-S0136-R004-A01, SRC002-S0136-R005-A01, SRC002-S0136-R006-A01
- [ ] AC-PRD-147-01: Satisfy source atom SRC002-S0136-R001-A01: -: **H01 — Normalized Hook Gateway and event envelopes** Dependencies: `E04, G04, S02` · Risk: `critical` · Review: `r [constraints: E04, G04, S02; critical; required] (verify: interface-check -> verify_src002_s0136_r001_a01)
- [ ] AC-PRD-147-02: Satisfy source atom SRC002-S0136-R002-A01: -: **H02 — Session and prompt lifecycle hooks** Dependencies: `H01` · Risk: `medium` · Review: `required` [constraints: H01; medium; required] (verify: interface-check -> verify_src002_s0136_r002_a01)
- [ ] AC-PRD-147-03: Satisfy source atom SRC002-S0136-R003-A01: -: **H03 — Tool and delegation hooks** Dependencies: `H01` · Risk: `medium` · Review: `required` [constraints: H01; medium; required] (verify: interface-check -> verify_src002_s0136_r003_a01)
- [ ] AC-PRD-147-04: Satisfy source atom SRC002-S0136-R004-A01: -: **H04 — Hook feature probe, trust and degraded-mode gate** Dependencies: `H02, H03` · Risk: `critical` · Review: `r [constraints: H02, H03; critical; required] (verify: interface-check -> verify_src002_s0136_r004_a01)
- [ ] AC-PRD-147-05: Satisfy source atom SRC002-S0136-R005-A01: -: **H05 — Evolution/holdout observability hooks with explicit coverage limits** Dependencies: `G05, H04` · Risk: `hig [constraints: G05, H04; high; required; Evolution/holdout] (verify: interface-check -> verify_src002_s0136_r005_a01)
- [ ] AC-PRD-147-06: Satisfy source atom SRC002-S0136-R006-A01: -: **H06 — Hook-disabled and hosted-tool degraded-mode integration gate** Dependencies: `H05, G05` · Risk: `critical`  [constraints: H05, G05; critical; required] (verify: interface-check -> verify_src002_s0136_r006_a01)

### PRD-148: I — Intake and research framing

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'I — Intake and research framing'.

- linked source rows: SRC002-S0137-R001, SRC002-S0137-R002, SRC002-S0137-R003, SRC002-S0137-R004, SRC002-S0137-R005, SRC002-S0137-R006
- linked source atoms: SRC002-S0137-R001-A01, SRC002-S0137-R002-A01, SRC002-S0137-R003-A01, SRC002-S0137-R004-A01, SRC002-S0137-R005-A01, SRC002-S0137-R006-A01
- [ ] AC-PRD-148-01: Satisfy source atom SRC002-S0137-R001-A01: -: **I01 — Bounded Interview and contradiction scan** Dependencies: `C04, F04` · Risk: `medium` · Review: `required` [constraints: C04, F04; medium; required] (verify: interface-check -> verify_src002_s0137_r001_a01)
- [ ] AC-PRD-148-02: Satisfy source atom SRC002-S0137-R002-A01: -: **I02 — InsightCard, falsifier and ScopeVector compiler** Dependencies: `I01` · Risk: `medium` · Review: `required` [constraints: I01; medium; required] (verify: interface-check -> verify_src002_s0137_r002_a01)
- [ ] AC-PRD-148-03: Satisfy source atom SRC002-S0137-R003-A01: -: **I03 — Ontology and measurement construct resolution** Dependencies: `I01` · Risk: `medium` · Review: `required` [constraints: I01; medium; required] (verify: interface-check -> verify_src002_s0137_r003_a01)
- [ ] AC-PRD-148-04: Satisfy source atom SRC002-S0137-R004-A01: -: **I04 — I-phase intake UX and export gate** Dependencies: `I02, I03` · Risk: `medium` · Review: `required` [constraints: I02, I03; medium; required] (verify: interface-check -> verify_src002_s0137_r004_a01)
- [ ] AC-PRD-148-05: Satisfy source atom SRC002-S0137-R005-A01: -: **I05 — HypothesisGenome intake, seed population bootstrap and eligibility screening** Dependencies: `F05, I04, C05 [constraints: F05, I04, C05; high; required] (verify: interface-check -> verify_src002_s0137_r005_a01)
- [ ] AC-PRD-148-06: Satisfy source atom SRC002-S0137-R006-A01: -: **I06 — Genome intake, scope and falsifiability integration gate** Dependencies: `I05, R05` · Risk: `critical` · Re [constraints: I05, R05; critical; required] (verify: interface-check -> verify_src002_s0137_r006_a01)

### PRD-149: J — Just-in-time skills and context

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'J — Just-in-time skills and context'.

- linked source rows: SRC002-S0138-R001, SRC002-S0138-R002, SRC002-S0138-R003, SRC002-S0138-R004, SRC002-S0138-R005, SRC002-S0138-R006
- linked source atoms: SRC002-S0138-R001-A01, SRC002-S0138-R002-A01, SRC002-S0138-R003-A01, SRC002-S0138-R004-A01, SRC002-S0138-R005-A01, SRC002-S0138-R006-A01
- [ ] AC-PRD-149-01: Satisfy source atom SRC002-S0138-R001-A01: -: **J01 — Parent skill router and trigger boundaries** Dependencies: `C04, G04, H01, S03` · Risk: `medium` · Review:  [constraints: C04, G04, H01, S03; medium; required] (verify: interface-check -> verify_src002_s0138_r001_a01)
- [ ] AC-PRD-149-02: Satisfy source atom SRC002-S0138-R002-A01: -: **J02 — Progressive references and context budgets** Dependencies: `J01` · Risk: `medium` · Review: `required` [constraints: J01; medium; required] (verify: interface-check -> verify_src002_s0138_r002_a01)
- [ ] AC-PRD-149-03: Satisfy source atom SRC002-S0138-R003-A01: -: **J03 — ContextCapsule assembly and exclusions** Dependencies: `J01` · Risk: `medium` · Review: `required` [constraints: J01; medium; required] (verify: interface-check -> verify_src002_s0138_r003_a01)
- [ ] AC-PRD-149-04: Satisfy source atom SRC002-S0138-R004-A01: -: **J04 — Post-compaction recovery gate** Dependencies: `J02, J03` · Risk: `medium` · Review: `required` [constraints: J02, J03; medium; required] (verify: interface-check -> verify_src002_s0138_r004_a01)
- [ ] AC-PRD-149-05: Satisfy source atom SRC002-S0138-R005-A01: -: **J05 — Typed mutation-operator registry, prompt genomes and quarantine workflow** Dependencies: `I05, J04, C05` ·  [constraints: I05, J04, C05; high; required] (verify: interface-check -> verify_src002_s0138_r005_a01)
- [ ] AC-PRD-149-06: Satisfy source atom SRC002-S0138-R006-A01: -: **J06 — Operator/prompt qualification and context-budget integration gate** Dependencies: `J05, S05` · Risk: `criti [constraints: J05, S05; critical; required; Operator/prompt] (verify: interface-check -> verify_src002_s0138_r006_a01)

### PRD-150: K — Knowledge and corpus ingest

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'K — Knowledge and corpus ingest'.

- linked source rows: SRC002-S0139-R001, SRC002-S0139-R002, SRC002-S0139-R003, SRC002-S0139-R004, SRC002-S0139-R005, SRC002-S0139-R006
- linked source atoms: SRC002-S0139-R001-A01, SRC002-S0139-R002-A01, SRC002-S0139-R003-A01, SRC002-S0139-R004-A01, SRC002-S0139-R005-A01, SRC002-S0139-R006-A01
- [ ] AC-PRD-150-01: Satisfy source atom SRC002-S0139-R001-A01: -: **K01 — Document registry, versions, licensing and trust** Dependencies: `B04, C04, D04, S01` · Risk: `medium` · Re [constraints: B04, C04, D04, S01; medium; required] (verify: interface-check -> verify_src002_s0139_r001_a01)
- [ ] AC-PRD-150-02: Satisfy source atom SRC002-S0139-R002-A01: -: **K02 — GROBID/Docling and fallback parser adapters** Dependencies: `K01` · Risk: `medium` · Review: `required` [constraints: K01; medium; required; GROBID/Docling] (verify: interface-check -> verify_src002_s0139_r002_a01)
- [ ] AC-PRD-150-03: Satisfy source atom SRC002-S0139-R003-A01: -: **K03 — SourceSpan emission for text/table/figure/formula** Dependencies: `K01` · Risk: `medium` · Review: `require [constraints: K01; medium; required; text/table/figure/formula**] (verify: interface-check -> verify_src002_s0139_r003_a01)
- [ ] AC-PRD-150-04: Satisfy source atom SRC002-S0139-R004-A01: -: **K04 — K-phase ingest quality and prompt-injection gate** Dependencies: `K02, K03` · Risk: `medium` · Review: `req [constraints: K02, K03; medium; required] (verify: interface-check -> verify_src002_s0139_r004_a01)
- [ ] AC-PRD-150-05: Satisfy source atom SRC002-S0139-R005-A01: -: **K05 — Corpus/evidence snapshot pinning, hidden holdout and prior-art boundaries** Dependencies: `K04, S05, C05` · [constraints: K04, S05, C05; high; required; Corpus/evidence] (verify: interface-check -> verify_src002_s0139_r005_a01)
- [ ] AC-PRD-150-06: Satisfy source atom SRC002-S0139-R006-A01: -: **K06 — Evidence/holdout version and leakage-prevention integration gate** Dependencies: `K05, O05` · Risk: `critic [constraints: K05, O05; critical; required; Evidence/holdout] (verify: interface-check -> verify_src002_s0139_r006_a01)

### PRD-151: L — Local memory and recall

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'L — Local memory and recall'.

- linked source rows: SRC002-S0140-R001, SRC002-S0140-R002, SRC002-S0140-R003, SRC002-S0140-R004, SRC002-S0140-R005, SRC002-S0140-R006
- linked source atoms: SRC002-S0140-R001-A01, SRC002-S0140-R002-A01, SRC002-S0140-R003-A01, SRC002-S0140-R004-A01, SRC002-S0140-R005-A01, SRC002-S0140-R006-A01
- [ ] AC-PRD-151-01: Satisfy source atom SRC002-S0140-R001-A01: -: **L01 — Memory classes, consent and retention policy** Dependencies: `D04, H02, J04, S02` · Risk: `medium` · Review [constraints: D04, H02, J04, S02; medium; required] (verify: interface-check -> verify_src002_s0140_r001_a01)
- [ ] AC-PRD-151-02: Satisfy source atom SRC002-S0140-R002-A01: -: **L02 — Memory indexing and scoped retrieval** Dependencies: `L01` · Risk: `medium` · Review: `required` [constraints: L01; medium; required] (verify: interface-check -> verify_src002_s0140_r002_a01)
- [ ] AC-PRD-151-03: Satisfy source atom SRC002-S0140-R003-A01: -: **L03 — Redaction, dedupe, forget and legal hold** Dependencies: `L01` · Risk: `medium` · Review: `required` [constraints: L01; medium; required] (verify: interface-check -> verify_src002_s0140_r003_a01)
- [ ] AC-PRD-151-04: Satisfy source atom SRC002-S0140-R004-A01: -: **L04 — L-phase recall quality/privacy gate** Dependencies: `L02, L03` · Risk: `medium` · Review: `required` [constraints: L02, L03; medium; required; quality/privacy] (verify: interface-check -> verify_src002_s0140_r004_a01)
- [ ] AC-PRD-151-05: Satisfy source atom SRC002-S0140-R005-A01: -: **L05 — Lineage memory, negative-result retention and evolution forget/export policies** Dependencies: `L04, D05` · [constraints: L04, D05; high; required; forget/export] (verify: interface-check -> verify_src002_s0140_r005_a01)
- [ ] AC-PRD-151-06: Satisfy source atom SRC002-S0140-R006-A01: -: **L06 — Memory retention, deletion and legal-hold integration gate** Dependencies: `L05, D05` · Risk: `critical` ·  [constraints: L05, D05; critical; required] (verify: interface-check -> verify_src002_s0140_r006_a01)

### PRD-152: M — Workspace Cartographer

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'M — Workspace Cartographer'.

- linked source rows: SRC002-S0141-R001, SRC002-S0141-R002, SRC002-S0141-R003, SRC002-S0141-R004, SRC002-S0141-R005, SRC002-S0141-R006
- linked source atoms: SRC002-S0141-R001-A01, SRC002-S0141-R002-A01, SRC002-S0141-R003-A01, SRC002-S0141-R004-A01, SRC002-S0141-R005-A01, SRC002-S0141-R006-A01
- [ ] AC-PRD-152-01: Satisfy source atom SRC002-S0141-R001-A01: -: **M01 — Typed inventory and dependency extraction** Dependencies: `B04, C04, D04, J04, K04` · Risk: `medium` · Revi [constraints: B04, C04, D04, J04, K04; medium; required] (verify: interface-check -> verify_src002_s0141_r001_a01)
- [ ] AC-PRD-152-02: Satisfy source atom SRC002-S0141-R002-A01: -: **M02 — Real baseline centrality and graph algorithms** Dependencies: `M01` · Risk: `medium` · Review: `required` [constraints: M01; medium; required] (verify: interface-check -> verify_src002_s0141_r002_a01)
- [ ] AC-PRD-152-03: Satisfy source atom SRC002-S0141-R003-A01: -: **M03 — Query personalization, risk and change impact** Dependencies: `M01` · Risk: `medium` · Review: `required` [constraints: M01; medium; required] (verify: interface-check -> verify_src002_s0141_r003_a01)
- [ ] AC-PRD-152-04: Satisfy source atom SRC002-S0141-R004-A01: -: **M04 — M-phase map UI and ranking-claim gate** Dependencies: `M02, M03` · Risk: `medium` · Review: `required` [constraints: M02, M03; medium; required] (verify: interface-check -> verify_src002_s0141_r004_a01)
- [ ] AC-PRD-152-05: Satisfy source atom SRC002-S0141-R005-A01: -: **M05 — Epistemic niche mapper, lineage map and evolution blast-radius cartography** Dependencies: `M04, D05` · Ris [constraints: M04, D05; high; required] (verify: interface-check -> verify_src002_s0141_r005_a01)
- [ ] AC-PRD-152-06: Satisfy source atom SRC002-S0141-R006-A01: -: **M06 — Map correctness, ranking separation and stale-propagation integration gate** Dependencies: `M05` · Risk: `c [constraints: M05; critical; required] (verify: interface-check -> verify_src002_s0141_r006_a01)

### PRD-153: N — Nodes, agents and graph execution

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'N — Nodes, agents and graph execution'.

- linked source rows: SRC002-S0142-R001, SRC002-S0142-R002, SRC002-S0142-R003, SRC002-S0142-R004, SRC002-S0142-R005, SRC002-S0142-R006
- linked source atoms: SRC002-S0142-R001-A01, SRC002-S0142-R002-A01, SRC002-S0142-R003-A01, SRC002-S0142-R004-A01, SRC002-S0142-R005-A01, SRC002-S0142-R006-A01
- [ ] AC-PRD-153-01: Satisfy source atom SRC002-S0142-R001-A01: -: **N01 — Canonical RoleSpec and evidence/tool ACLs** Dependencies: `C04, E04, G04, H04, J04` · Risk: `high` · Review [constraints: C04, E04, G04, H04, J04; high; required; evidence/tool] (verify: interface-check -> verify_src002_s0142_r001_a01)
- [ ] AC-PRD-153-02: Satisfy source atom SRC002-S0142-R002-A01: -: **N02 — Codex/Claude role compilation and spawn adapters** Dependencies: `N01` · Risk: `high` · Review: `required` [constraints: N01; high; required; Codex/Claude] (verify: interface-check -> verify_src002_s0142_r002_a01)
- [ ] AC-PRD-153-03: Satisfy source atom SRC002-S0142-R003-A01: -: **N03 — DAG scheduler, leases, retries and concurrency** Dependencies: `N01` · Risk: `high` · Review: `required` [constraints: N01; high; required] (verify: interface-check -> verify_src002_s0142_r003_a01)
- [ ] AC-PRD-153-04: Satisfy source atom SRC002-S0142-R004-A01: -: **N04 — N-phase fan-in, missing-node and independent-review gate** Dependencies: `N02, N03` · Risk: `high` · Review [constraints: N02, N03; high; required] (verify: interface-check -> verify_src002_s0142_r004_a01)
- [ ] AC-PRD-153-05: Satisfy source atom SRC002-S0142-R005-A01: -: **N05 — Bounded asynchronous proposal/evaluation/persistence lanes and scheduler** Dependencies: `N04, E05, F05` ·  [constraints: N04, E05, F05; high; required; proposal/evaluation/persistence] (verify: interface-check -> verify_src002_s0142_r005_a01)
- [ ] AC-PRD-153-06: Satisfy source atom SRC002-S0142-R006-A01: -: **N06 — Backpressure, missing-worker and resource-lock integration gate** Dependencies: `N05` · Risk: `critical` ·  [constraints: N05; critical; required] (verify: interface-check -> verify_src002_s0142_r006_a01)

### PRD-154: O — Observe and evidence retrieval

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'O — Observe and evidence retrieval'.

- linked source rows: SRC002-S0143-R001, SRC002-S0143-R002, SRC002-S0143-R003, SRC002-S0143-R004, SRC002-S0143-R005, SRC002-S0143-R006
- linked source atoms: SRC002-S0143-R001-A01, SRC002-S0143-R002-A01, SRC002-S0143-R003-A01, SRC002-S0143-R004-A01, SRC002-S0143-R005-A01, SRC002-S0143-R006-A01
- [ ] AC-PRD-154-01: Satisfy source atom SRC002-S0143-R001-A01: -: **O01 — QueryPlan and SearchLaneReceipt contracts** Dependencies: `I04, K04, M04` · Risk: `medium` · Review: `requi [constraints: I04, K04, M04; medium; required] (verify: interface-check -> verify_src002_s0143_r001_a01)
- [ ] AC-PRD-154-02: Satisfy source atom SRC002-S0143-R002-A01: -: **O02 — Lexical, semantic, citation and relation retrieval** Dependencies: `O01` · Risk: `medium` · Review: `requir [constraints: O01; medium; required] (verify: interface-check -> verify_src002_s0143_r002_a01)
- [ ] AC-PRD-154-03: Satisfy source atom SRC002-S0143-R003-A01: -: **O03 — Dependency clusters and Evidence Pack assembly** Dependencies: `O01` · Risk: `medium` · Review: `required` [constraints: O01; medium; required] (verify: interface-check -> verify_src002_s0143_r003_a01)
- [ ] AC-PRD-154-04: Satisfy source atom SRC002-S0143-R004-A01: -: **O04 — O-phase absence and completeness gate** Dependencies: `O02, O03` · Risk: `medium` · Review: `required` [constraints: O02, O03; medium; required] (verify: interface-check -> verify_src002_s0143_r004_a01)
- [ ] AC-PRD-154-05: Satisfy source atom SRC002-S0143-R005-A01: -: **O05 — Evolution evidence retrieval, multi-layer novelty and coverage-debt acquisition** Dependencies: `O04, K05,  [constraints: O04, K05, C05; high; required] (verify: interface-check -> verify_src002_s0143_r005_a01)
- [ ] AC-PRD-154-06: Satisfy source atom SRC002-S0143-R006-A01: -: **O06 — Search-completeness, novelty-failure and prior-art integration gate** Dependencies: `O05, Q05` · Risk: `cri [constraints: O05, Q05; critical; required] (verify: negative-test -> verify_src002_s0143_r006_a01)

### PRD-155: P — Evidence Parliament

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'P — Evidence Parliament'.

- linked source rows: SRC002-S0144-R001, SRC002-S0144-R002, SRC002-S0144-R003, SRC002-S0144-R004, SRC002-S0144-R005, SRC002-S0144-R006
- linked source atoms: SRC002-S0144-R001-A01, SRC002-S0144-R002-A01, SRC002-S0144-R003-A01, SRC002-S0144-R004-A01, SRC002-S0144-R005-A01, SRC002-S0144-R006-A01
- [ ] AC-PRD-155-01: Satisfy source atom SRC002-S0144-R001-A01: -: **P01 — Blind independent briefs and asymmetric dispatch** Dependencies: `N04, O04, R04` · Risk: `critical` · Revie [constraints: N04, O04, R04; critical; required] (verify: interface-check -> verify_src002_s0144_r001_a01)
- [ ] AC-PRD-155-02: Satisfy source atom SRC002-S0144-R002-A01: -: **P02 — Method, scope, causal and novelty audits with veto** Dependencies: `P01` · Risk: `medium` · Review: `requir [constraints: P01; medium; required] (verify: interface-check -> verify_src002_s0144_r002_a01)
- [ ] AC-PRD-155-03: Satisfy source atom SRC002-S0144-R003-A01: -: **P03 — Cross-examination and Minority Report** Dependencies: `P01` · Risk: `medium` · Review: `required` [constraints: P01; medium; required] (verify: interface-check -> verify_src002_s0144_r003_a01)
- [ ] AC-PRD-155-04: Satisfy source atom SRC002-S0144-R004-A01: -: **P04 — P-phase judge and independent attestation gate** Dependencies: `P02, P03` · Risk: `critical` · Review: `req [constraints: P02, P03; critical; required] (verify: interface-check -> verify_src002_s0144_r004_a01)
- [ ] AC-PRD-155-05: Satisfy source atom SRC002-S0144-R005-A01: -: **P05 — Evolution promotion Parliament, Red Queen evidence and minority-lineage review** Dependencies: `P04, O05, Q [constraints: P04, O05, Q05, R05; critical; required] (verify: interface-check -> verify_src002_s0144_r005_a01)
- [ ] AC-PRD-155-06: Satisfy source atom SRC002-S0144-R006-A01: -: **P06 — No-majority promotion and sealed-candidate attestation integration gate** Dependencies: `P05, V05` · Risk:  [constraints: P05, V05; critical; required] (verify: interface-check -> verify_src002_s0144_r006_a01)

### PRD-156: Q — Quality, evaluation and calibration

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'Q — Quality, evaluation and calibration'.

- linked source rows: SRC002-S0145-R001, SRC002-S0145-R002, SRC002-S0145-R003, SRC002-S0145-R004, SRC002-S0145-R005, SRC002-S0145-R006
- linked source atoms: SRC002-S0145-R001-A01, SRC002-S0145-R002-A01, SRC002-S0145-R003-A01, SRC002-S0145-R004-A01, SRC002-S0145-R005-A01, SRC002-S0145-R006-A01
- [ ] AC-PRD-156-01: Satisfy source atom SRC002-S0145-R001-A01: -: **Q01 — Gold corpus and annotation protocol** Dependencies: `K04, O04, P04, R04` · Risk: `medium` · Review: `requir [constraints: K04, O04, P04, R04; medium; required] (verify: interface-check -> verify_src002_s0145_r001_a01)
- [ ] AC-PRD-156-02: Satisfy source atom SRC002-S0145-R002-A01: -: **Q02 — Parser, Claim and grounding evaluation** Dependencies: `Q01` · Risk: `medium` · Review: `required` [constraints: Q01; medium; required] (verify: interface-check -> verify_src002_s0145_r002_a01)
- [ ] AC-PRD-156-03: Satisfy source atom SRC002-S0145-R003-A01: -: **Q03 — Retrieval, verdict and calibration evaluation** Dependencies: `Q01` · Risk: `medium` · Review: `required` [constraints: Q01; medium; required] (verify: interface-check -> verify_src002_s0145_r003_a01)
- [ ] AC-PRD-156-04: Satisfy source atom SRC002-S0145-R004-A01: -: **Q04 — Q-phase time-sliced and adversarial benchmark gate** Dependencies: `Q02, Q03` · Risk: `medium` · Review: `r [constraints: Q02, Q03; medium; required] (verify: interface-check -> verify_src002_s0145_r004_a01)
- [ ] AC-PRD-156-05: Satisfy source atom SRC002-S0145-R005-A01: -: **Q05 — Multi-objective fitness, hidden evaluation, multiplicity and selective inference** Dependencies: `Q04, O05, [constraints: Q04, O05, C05; critical; required] (verify: interface-check -> verify_src002_s0145_r005_a01)
- [ ] AC-PRD-156-06: Satisfy source atom SRC002-S0145-R006-A01: -: **Q06 — Calibration, winner-curse and statistical-governance integration gate** Dependencies: `Q05, V05` · Risk: `c [constraints: Q05, V05; critical; required] (verify: interface-check -> verify_src002_s0145_r006_a01)

### PRD-157: R — Reasoning and Aporia

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'R — Reasoning and Aporia'.

- linked source rows: SRC002-S0146-R001, SRC002-S0146-R002, SRC002-S0146-R003, SRC002-S0146-R004, SRC002-S0146-R005, SRC002-S0146-R006
- linked source atoms: SRC002-S0146-R001-A01, SRC002-S0146-R002-A01, SRC002-S0146-R003-A01, SRC002-S0146-R004-A01, SRC002-S0146-R005-A01, SRC002-S0146-R006-A01
- [ ] AC-PRD-157-01: Satisfy source atom SRC002-S0146-R001-A01: -: **R01 — Inductive synthesis and heterogeneity engine** Dependencies: `C04, O04` · Risk: `high` · Review: `required` [constraints: C04, O04; high; required] (verify: interface-check -> verify_src002_s0146_r001_a01)
- [ ] AC-PRD-157-02: Satisfy source atom SRC002-S0146-R002-A01: -: **R02 — Deductive proof trace and assumption ledger** Dependencies: `R01` · Risk: `high` · Review: `required` [constraints: R01; high; required] (verify: interface-check -> verify_src002_s0146_r002_a01)
- [ ] AC-PRD-157-03: Satisfy source atom SRC002-S0146-R003-A01: -: **R03 — Abduction, contradiction and moderator engine** Dependencies: `R01` · Risk: `high` · Review: `required` [constraints: R01; high; required] (verify: interface-check -> verify_src002_s0146_r003_a01)
- [ ] AC-PRD-157-04: Satisfy source atom SRC002-S0146-R004-A01: -: **R04 — R-phase causal identification and ArgumentGraph gate** Dependencies: `R02, R03` · Risk: `high` · Review: `r [constraints: R02, R03; high; required] (verify: interface-check -> verify_src002_s0146_r004_a01)
- [ ] AC-PRD-157-05: Satisfy source atom SRC002-S0146-R005-A01: -: **R05 — Scientific mutation, typed crossover, mechanism and Aporia operators** Dependencies: `R04, I05, C05` · Risk [constraints: R04, I05, C05; high; required] (verify: interface-check -> verify_src002_s0146_r005_a01)
- [ ] AC-PRD-157-06: Satisfy source atom SRC002-S0146-R006-A01: -: **R06 — Causal/measurement/scope crossover safety integration gate** Dependencies: `R05` · Risk: `critical` · Revie [constraints: R05; critical; required; Causal/measurement/scope] (verify: interface-check -> verify_src002_s0146_r006_a01)

### PRD-158: S — Security, privacy and skill supply chain

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'S — Security, privacy and skill supply chain'.

- linked source rows: SRC002-S0147-R001, SRC002-S0147-R002, SRC002-S0147-R003, SRC002-S0147-R004, SRC002-S0147-R005, SRC002-S0147-R006
- linked source atoms: SRC002-S0147-R001-A01, SRC002-S0147-R002-A01, SRC002-S0147-R003-A01, SRC002-S0147-R004-A01, SRC002-S0147-R005-A01, SRC002-S0147-R006-A01
- [ ] AC-PRD-158-01: Satisfy source atom SRC002-S0147-R001-A01: -: **S01 — Trust-zone enforcement and document injection defense** Dependencies: `A04, B01` · Risk: `critical` · Revie [constraints: A04, B01; critical; required] (verify: interface-check -> verify_src002_s0147_r001_a01)
- [ ] AC-PRD-158-02: Satisfy source atom SRC002-S0147-R002-A01: -: **S02 — Secrets, path, sandbox and egress controls** Dependencies: `S01` · Risk: `medium` · Review: `required` [constraints: S01; medium; required] (verify: interface-check -> verify_src002_s0147_r002_a01)
- [ ] AC-PRD-158-03: Satisfy source atom SRC002-S0147-R003-A01: -: **S03 — Skill Vault quarantine and SkillLockfile** Dependencies: `S01` · Risk: `medium` · Review: `required` [constraints: S01; medium; required] (verify: interface-check -> verify_src002_s0147_r003_a01)
- [ ] AC-PRD-158-04: Satisfy source atom SRC002-S0147-R004-A01: -: **S04 — S-phase threat model and red-team gate** Dependencies: `S02, S03` · Risk: `critical` · Review: `required` [constraints: S02, S03; critical; required] (verify: interface-check -> verify_src002_s0147_r004_a01)
- [ ] AC-PRD-158-05: Satisfy source atom SRC002-S0147-R005-A01: -: **S05 — Verifier Firewall, prompt/evaluator quarantine and executable-candidate threat controls** Dependencies: `S0 [constraints: S04, A06, C05; critical; required; prompt/evaluator] (verify: interface-check -> verify_src002_s0147_r005_a01)
- [ ] AC-PRD-158-06: Satisfy source atom SRC002-S0147-R006-A01: -: **S06 — Leakage, reward-hacking and evaluator-update governance integration gate** Dependencies: `S05, J05` · Risk: [constraints: S05, J05; critical; required] (verify: interface-check -> verify_src002_s0147_r006_a01)

### PRD-159: T — Tools, MCP, CLI and sandbox

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'T — Tools, MCP, CLI and sandbox'.

- linked source rows: SRC002-S0148-R001, SRC002-S0148-R002, SRC002-S0148-R003, SRC002-S0148-R004, SRC002-S0148-R005, SRC002-S0148-R006
- linked source atoms: SRC002-S0148-R001-A01, SRC002-S0148-R002-A01, SRC002-S0148-R003-A01, SRC002-S0148-R004-A01, SRC002-S0148-R005-A01, SRC002-S0148-R006-A01
- [ ] AC-PRD-159-01: Satisfy source atom SRC002-S0148-R001-A01: -: **T01 — MCP read/planning tools** Dependencies: `E04, G04, S04` · Risk: `high` · Review: `required` [constraints: E04, G04, S04; high; required; read/planning] (verify: interface-check -> verify_src002_s0148_r001_a01)
- [ ] AC-PRD-159-02: Satisfy source atom SRC002-S0148-R002-A01: -: **T02 — MCP mutating tools with intents and receipts** Dependencies: `T01` · Risk: `high` · Review: `required` [constraints: T01; high; required] (verify: interface-check -> verify_src002_s0148_r002_a01)
- [ ] AC-PRD-159-03: Satisfy source atom SRC002-S0148-R003-A01: -: **T03 — Stable CLI JSON/error and PATH-less surfaces** Dependencies: `T01` · Risk: `high` · Review: `required` [constraints: T01; high; required; JSON/error] (verify: negative-test -> verify_src002_s0148_r003_a01)
- [ ] AC-PRD-159-04: Satisfy source atom SRC002-S0148-R004-A01: -: **T04 — T-phase sandbox and external tool adapter gate** Dependencies: `T02, T03` · Risk: `high` · Review: `require [constraints: T02, T03; high; required] (verify: interface-check -> verify_src002_s0148_r004_a01)
- [ ] AC-PRD-159-05: Satisfy source atom SRC002-S0148-R005-A01: -: **T05 — Evolution CLI/MCP tools, sandbox executors and Shinka backend adapter** Dependencies: `T04, S05, G05` · Ris [constraints: T04, S05, G05; high; required; CLI/MCP] (verify: interface-check -> verify_src002_s0148_r005_a01)
- [ ] AC-PRD-159-06: Satisfy source atom SRC002-S0148-R006-A01: -: **T06 — External-backend qualification and fallback integration gate** Dependencies: `T05` · Risk: `critical` · Rev [constraints: T05; critical; required] (verify: interface-check -> verify_src002_s0148_r006_a01)

### PRD-162: W — Workflow, checkpoints and reassessment

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'W — Workflow, checkpoints and reassessment'.

- linked source rows: SRC002-S0151-R001, SRC002-S0151-R002, SRC002-S0151-R003, SRC002-S0151-R004, SRC002-S0151-R005, SRC002-S0151-R006
- linked source atoms: SRC002-S0151-R001-A01, SRC002-S0151-R002-A01, SRC002-S0151-R003-A01, SRC002-S0151-R004-A01, SRC002-S0151-R005-A01, SRC002-S0151-R006-A01
- [ ] AC-PRD-162-01: Satisfy source atom SRC002-S0151-R001-A01: -: **W01 — Workflow compiler and NodeContract validator** Dependencies: `D04, E04, F04, N04` · Risk: `high` · Review:  [constraints: D04, E04, F04, N04; high; required] (verify: interface-check -> verify_src002_s0151_r001_a01)
- [ ] AC-PRD-162-02: Satisfy source atom SRC002-S0151-R002-A01: -: **W02 — Checkpoint, pause, resume and cancellation** Dependencies: `W01` · Risk: `high` · Review: `required` [constraints: W01; high; required] (verify: interface-check -> verify_src002_s0151_r002_a01)
- [ ] AC-PRD-162-03: Satisfy source atom SRC002-S0151-R003-A01: -: **W03 — Evidence updates, staleness and reassessment** Dependencies: `W01` · Risk: `high` · Review: `required` [constraints: W01; high; required] (verify: interface-check -> verify_src002_s0151_r003_a01)
- [ ] AC-PRD-162-04: Satisfy source atom SRC002-S0151-R004-A01: -: **W04 — W-phase replay, drift and audit export gate** Dependencies: `W02, W03` · Risk: `high` · Review: `required` [constraints: W02, W03; high; required] (verify: interface-check -> verify_src002_s0151_r004_a01)
- [ ] AC-PRD-162-05: Satisfy source atom SRC002-S0151-R005-A01: -: **W05 — Evolution checkpoint/resume/cancel, evaluator drift and reassessment workflow** Dependencies: `W04, D05, F0 [constraints: W04, D05, F05, N05; critical; required; checkpoint/resume/cancel] (verify: interface-check -> verify_src002_s0151_r005_a01)
- [ ] AC-PRD-162-06: Satisfy source atom SRC002-S0151-R006-A01: -: **W06 — Crash recovery, future-only evaluator update and replay integration gate** Dependencies: `W05, D06, N06` ·  [constraints: W05, D06, N06; critical; required] (verify: interface-check -> verify_src002_s0151_r006_a01)

### PRD-163: X — Cross-provider adapters

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'X — Cross-provider adapters'.

- linked source rows: SRC002-S0152-R001, SRC002-S0152-R002, SRC002-S0152-R003, SRC002-S0152-R004, SRC002-S0152-R005, SRC002-S0152-R006
- linked source atoms: SRC002-S0152-R001-A01, SRC002-S0152-R002-A01, SRC002-S0152-R003-A01, SRC002-S0152-R004-A01, SRC002-S0152-R005-A01, SRC002-S0152-R006-A01
- [ ] AC-PRD-163-01: Satisfy source atom SRC002-S0152-R001-A01: -: **X01 — Codex plugin, hooks and subagent adapter** Dependencies: `G04, N04, T04, W04` · Risk: `high` · Review: `req [constraints: G04, N04, T04, W04; high; required] (verify: interface-check -> verify_src002_s0152_r001_a01)
- [ ] AC-PRD-163-02: Satisfy source atom SRC002-S0152-R002-A01: -: **X02 — Claude Code skills, agents and worktree adapter** Dependencies: `X01` · Risk: `high` · Review: `required` [constraints: X01; high; required] (verify: interface-check -> verify_src002_s0152_r002_a01)
- [ ] AC-PRD-163-03: Satisfy source atom SRC002-S0152-R003-A01: -: **X03 — Model routing and fallback policy** Dependencies: `X01` · Risk: `high` · Review: `required` [constraints: X01; high; required] (verify: interface-check -> verify_src002_s0152_r003_a01)
- [ ] AC-PRD-163-04: Satisfy source atom SRC002-S0152-R004-A01: -: **X04 — X-phase cross-provider parity and diversity gate** Dependencies: `X02, X03` · Risk: `high` · Review: `requi [constraints: X02, X03; high; required] (verify: interface-check -> verify_src002_s0152_r004_a01)
- [ ] AC-PRD-163-05: Satisfy source atom SRC002-S0152-R005-A01: -: **X05 — Cross-provider mutation routing, safe delayed-reward bandit and fallback** Dependencies: `X04, N05, T05` ·  [constraints: X04, N05, T05; high; required] (verify: interface-check -> verify_src002_s0152_r005_a01)
- [ ] AC-PRD-163-06: Satisfy source atom SRC002-S0152-R006-A01: -: **X06 — Provider diversity, cost, safety and reward-attribution integration gate** Dependencies: `X05` · Risk: `cri [constraints: X05; critical; required] (verify: interface-check -> verify_src002_s0152_r006_a01)

### PRD-164: Y — Yield, operations and scale

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'Y — Yield, operations and scale'.

- linked source rows: SRC002-S0153-R001, SRC002-S0153-R002, SRC002-S0153-R003, SRC002-S0153-R004, SRC002-S0153-R005, SRC002-S0153-R006
- linked source atoms: SRC002-S0153-R001-A01, SRC002-S0153-R002-A01, SRC002-S0153-R003-A01, SRC002-S0153-R004-A01, SRC002-S0153-R005-A01, SRC002-S0153-R006-A01
- [ ] AC-PRD-164-01: Satisfy source atom SRC002-S0153-R001-A01: -: **Y01 — Typed budgets, adaptive fleet and performance controls** Dependencies: `B04, D04, Q04, W04, X04` · Risk: `h [constraints: B04, D04, Q04, W04, X04; high; required] (verify: interface-check -> verify_src002_s0153_r001_a01)
- [ ] AC-PRD-164-02: Satisfy source atom SRC002-S0153-R002-A01: -: **Y02 — Observability, SLOs and privacy-safe telemetry** Dependencies: `Y01` · Risk: `high` · Review: `required` [constraints: Y01; high; required] (verify: interface-check -> verify_src002_s0153_r002_a01)
- [ ] AC-PRD-164-03: Satisfy source atom SRC002-S0153-R003-A01: -: **Y03 — Backup, disaster recovery and operational runbooks** Dependencies: `Y01` · Risk: `high` · Review: `required [constraints: Y01; high; required] (verify: interface-check -> verify_src002_s0153_r003_a01)
- [ ] AC-PRD-164-04: Satisfy source atom SRC002-S0153-R004-A01: -: **Y04 — Y-phase 50/200/2000 corpus scale qualification** Dependencies: `Y02, Y03` · Risk: `high` · Review: `require [constraints: Y02, Y03; high; required; 50/200/2000] (verify: interface-check -> verify_src002_s0153_r004_a01)
- [ ] AC-PRD-164-05: Satisfy source atom SRC002-S0153-R005-A01: -: **Y05 — Quality-diversity scaling, surrogate triage, budgets and production load** Dependencies: `Y04, N05, Q05, X0 [constraints: Y04, N05, Q05, X05; high; required] (verify: interface-check -> verify_src002_s0153_r005_a01)
- [ ] AC-PRD-164-06: Satisfy source atom SRC002-S0153-R006-A01: -: **Y06 — 2,000-document evolution qualification and cost/latency integration gate** Dependencies: `Y05` · Risk: `cri [constraints: Y05; critical; required; cost/latency] (verify: interface-check -> verify_src002_s0153_r006_a01)

### PRD-168: 40. Roles, prompts and plugin assets

Cover 6 source coverage row(s) and 7 requirement atom(s) from section '40. Roles, prompts and plugin assets'.

- linked source rows: SRC002-S0157-R001, SRC002-S0157-R002, SRC002-S0157-R003, SRC002-S0157-R004, SRC002-S0157-R005, SRC002-S0157-R006
- linked source atoms: SRC002-S0157-R001-A01, SRC002-S0157-R002-A01, SRC002-S0157-R003-A01, SRC002-S0157-R004-A01, SRC002-S0157-R005-A01, SRC002-S0157-R005-A02, SRC002-S0157-R006-A01
- [ ] AC-PRD-168-01: Satisfy source atom SRC002-S0157-R002-A01: -: semantic/extraction/evolution prompts: **65** [constraints: semantic/extraction/evolution] (verify: interface-check -> verify_src002_s0157_r002_a01)
- [ ] AC-PRD-168-02: Satisfy source atom SRC002-S0157-R005-A01: -: architecture audit: **288 lenses = 264 PASS / 24 CONDITIONAL / 0 FAIL** (verify: negative-test -> verify_src002_s0157_r005_a01)
- [ ] AC-PRD-168-03: Satisfy source atom SRC002-S0157-R005-A02: The audit is a structured failure-surface matrix, not 288 independent agents or proofs. (verify: negative-test -> verify_src002_s0157_r005_a02)

### PRD-171: 42. Required baselines

Cover 7 source coverage row(s) and 8 requirement atom(s) from section '42. Required baselines'.

- linked source rows: SRC002-S0160-R001, SRC002-S0160-R002, SRC002-S0160-R003, SRC002-S0160-R004, SRC002-S0160-R005, SRC002-S0160-R006, SRC002-S0160-R007
- linked source atoms: SRC002-S0160-R001-A01, SRC002-S0160-R002-A01, SRC002-S0160-R003-A01, SRC002-S0160-R004-A01, SRC002-S0160-R005-A01, SRC002-S0160-R006-A01, SRC002-S0160-R007-A01, SRC002-S0160-R007-A02
- [ ] AC-PRD-171-01: Satisfy source atom SRC002-S0160-R002-A01: -: v3 Parliament without evolution; (verify: negative-test -> verify_src002_s0160_r002_a01)
- [ ] AC-PRD-171-02: Satisfy source atom SRC002-S0160-R005-A01: -: Pareto without Red Queen; (verify: negative-test -> verify_src002_s0160_r005_a01)
- [ ] AC-PRD-171-03: Satisfy source atom SRC002-S0160-R006-A01: -: quality-diversity without hidden holdout; (verify: negative-test -> verify_src002_s0160_r006_a01)

### PRD-172: 43. v3 migration

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '43. v3 migration'.

- linked source rows: SRC002-S0161
- linked source atoms: SRC002-S0161-A01, SRC002-S0161-A02
- [ ] AC-PRD-172-01: Satisfy source atom SRC002-S0161-A01: v4 adds candidate genomes, evaluator/holdout, fitness, niches, challenge, statistics and replication as new linked obj [constraints: evaluator/holdout] (verify: interface-check -> verify_src002_s0161_a01)
- [ ] AC-PRD-172-02: Satisfy source atom SRC002-S0161-A02: Historical hashes are never rewritten. (verify: negative-test -> verify_src002_s0161_a02)

### PRD-174: Part XVI — Failure modes and non-goals

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part XVI — Failure modes and non-goals'.

- linked source rows: SRC002-S0163
- linked source atoms: (none)

### PRD-175: 45. Major failure modes

Cover 15 source coverage row(s) and 16 requirement atom(s) from section '45. Major failure modes'.

- linked source rows: SRC002-S0164-R001, SRC002-S0164-R002, SRC002-S0164-R003, SRC002-S0164-R004, SRC002-S0164-R005, SRC002-S0164-R006, SRC002-S0164-R007, SRC002-S0164-R008, SRC002-S0164-R009, SRC002-S0164-R010, SRC002-S0164-R011, SRC002-S0164-R012, SRC002-S0164-R013, SRC002-S0164-R014, SRC002-S0164-R015
- linked source atoms: SRC002-S0164-R001-A01, SRC002-S0164-R002-A01, SRC002-S0164-R003-A01, SRC002-S0164-R004-A01, SRC002-S0164-R005-A01, SRC002-S0164-R006-A01, SRC002-S0164-R007-A01, SRC002-S0164-R008-A01, SRC002-S0164-R009-A01, SRC002-S0164-R010-A01, SRC002-S0164-R011-A01, SRC002-S0164-R012-A01, SRC002-S0164-R013-A01, SRC002-S0164-R014-A01, SRC002-S0164-R015-A01, SRC002-S0164-R015-A02
- [ ] AC-PRD-175-01: Satisfy source atom SRC002-S0164-R006-A01: -: semantic crossover without compatibility; (verify: negative-test -> verify_src002_s0164_r006_a01)
- [ ] AC-PRD-175-02: Satisfy source atom SRC002-S0164-R010-A01: -: prompt self-modification acquiring authority; (verify: risk-verification -> verify_src002_s0164_r010_a01)

### PRD-176: 46. Explicit non-goals

Cover 10 source coverage row(s) and 10 requirement atom(s) from section '46. Explicit non-goals'.

- linked source rows: SRC002-S0165-R001, SRC002-S0165-R002, SRC002-S0165-R003, SRC002-S0165-R004, SRC002-S0165-R005, SRC002-S0165-R006, SRC002-S0165-R007, SRC002-S0165-R008, SRC002-S0165-R009, SRC002-S0165-R010
- linked source atoms: SRC002-S0165-R001-A01, SRC002-S0165-R002-A01, SRC002-S0165-R003-A01, SRC002-S0165-R004-A01, SRC002-S0165-R005-A01, SRC002-S0165-R006-A01, SRC002-S0165-R007-A01, SRC002-S0165-R008-A01, SRC002-S0165-R009-A01, SRC002-S0165-R010-A01
- [ ] AC-PRD-176-01: Satisfy source atom SRC002-S0165-R009-A01: -: claim production performance from this specification; (verify: risk-verification -> verify_src002_s0165_r009_a01)

## integration

### PRD-088: 7. Four-Graph integration

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '7. Four-Graph integration'.

- linked source rows: SRC002-S0077
- linked source atoms: (none)

## release/closeout

### PRD-052: EF4-I32 — Release provenance

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I32 — Release provenance'.

- linked source rows: SRC002-S0041
- linked source atoms: (none)

### PRD-165: Z — Zero-trust release and lifecycle

Cover 7 source coverage row(s) and 8 requirement atom(s) from section 'Z — Zero-trust release and lifecycle'.

- linked source rows: SRC002-S0154-R001, SRC002-S0154-R002, SRC002-S0154-R003, SRC002-S0154-R004, SRC002-S0154-R005, SRC002-S0154-R006, SRC002-S0154-R007
- linked source atoms: SRC002-S0154-R001-A01, SRC002-S0154-R002-A01, SRC002-S0154-R003-A01, SRC002-S0154-R004-A01, SRC002-S0154-R005-A01, SRC002-S0154-R006-A01, SRC002-S0154-R006-A02, SRC002-S0154-R007-A01
- [ ] AC-PRD-165-01: Satisfy source atom SRC002-S0154-R001-A01: -: **Z01 — Fresh-install, compatibility and uninstall matrix** Dependencies: `G04, H04, L04, M04, P04, Q04, S04, T04,  [constraints: G04, H04, L04, M04, P04, Q04, S04, T04, U04, V04, W04, X04, Y04; critical; required] (verify: interface-check -> verify_src002_s0154_r001_a01)
- [ ] AC-PRD-165-02: Satisfy source atom SRC002-S0154-R002-A01: -: **Z02 — SBOM, signing, provenance and deterministic bundle** Dependencies: `Z01` · Risk: `medium` · Review: `requir [constraints: Z01; medium; required] (verify: interface-check -> verify_src002_s0154_r002_a01)
- [ ] AC-PRD-165-03: Satisfy source atom SRC002-S0154-R003-A01: -: **Z03 — Upgrade, downgrade, migration and rollback matrix** Dependencies: `Z01` · Risk: `medium` · Review: `require [constraints: Z01; medium; required] (verify: negative-test -> verify_src002_s0154_r003_a01)
- [ ] AC-PRD-165-04: Satisfy source atom SRC002-S0154-R004-A01: -: **Z04 — Final independent release gate and architecture freeze** Dependencies: `Z02, Z03` · Risk: `critical` · Revi [constraints: Z02, Z03; critical; required] (verify: interface-check -> verify_src002_s0154_r004_a01)
- [ ] AC-PRD-165-05: Satisfy source atom SRC002-S0154-R005-A01: -: **Z05 — Zero-trust v4 release, 288-lens audit, migration and signing provenance** Dependencies: `Z04, B05, S05, T05 [constraints: Z04, B05, S05, T05, Y05; critical; required] (verify: interface-check -> verify_src002_s0154_r005_a01)
- [ ] AC-PRD-165-06: Satisfy source atom SRC002-S0154-R006-A01: -: **Z06 — Independent release, clean extraction and truthful maturity gate** Dependencies: `Z05, B06, C06, F06, G06,  [constraints: Z05, B06, C06, F06, G06, K06, N06, P06, Q06, S06, T06, V06, W06, Y06; critical; required] (verify: interface-check -> verify_src002_s0154_r006_a01)
- [ ] AC-PRD-165-07: Satisfy source atom SRC002-S0154-R006-A02: Total: **156 work packages**, dependency-checked in `manifests/development_manifest.yaml`. [constraints: manifests/development_manifest.yaml] (verify: interface-check -> verify_src002_s0154_r006_a02)

### PRD-169: Part XV — Evaluation, release and migration

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part XV — Evaluation, release and migration'.

- linked source rows: SRC002-S0158
- linked source atoms: (none)

### PRD-170: 41. Release ladder

Cover 1 source coverage row(s) and 1 requirement atom(s) from section '41. Release ladder'.

- linked source rows: SRC002-S0159
- linked source atoms: SRC002-S0159-A01
- [ ] AC-PRD-170-01: Satisfy source atom SRC002-S0159-A01: Only `manifests/acceptance_matrix.yaml` selects the release level. [constraints: manifests/acceptance_matrix.yaml] (verify: interface-check -> verify_src002_s0159_a01)

### PRD-173: 44. Reproducible release

Cover 1 source coverage row(s) and 0 requirement atom(s) from section '44. Reproducible release'.

- linked source rows: SRC002-S0162
- linked source atoms: (none)

## requirements/scope

### PRD-045: EF4-I25 — Role-scoped delegation

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I25 — Role-scoped delegation'.

- linked source rows: SRC002-S0034
- linked source atoms: (none)

## tests/validation

### PRD-008: 7. Verifier Firewall

Cover 1 source coverage row(s) and 2 requirement atom(s) from section '7. Verifier Firewall'.

- linked source rows: SRC001-S0008
- linked source atoms: SRC001-S0008-A01, SRC001-S0008-A02
- [ ] AC-PRD-008-01: Satisfy source atom SRC001-S0008-A01: The current `EvaluatorBundle` is immutable. [constraints: EvaluatorBundle] (verify: interface-check -> verify_src001_s0008_a01)
- [ ] AC-PRD-008-02: Satisfy source atom SRC001-S0008-A02: Hidden/OOD artifacts are least privilege. [constraints: Hidden/OOD] (verify: interface-check -> verify_src001_s0008_a02)

### PRD-013: Evolution-Governed Hypothesis Discovery and Validation Operating System

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Evolution-Governed Hypothesis Discovery and Validation Operating System'.

- linked source rows: SRC002-S0002
- linked source atoms: (none)

### PRD-055: EF4-I35 — Installability is tested

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'EF4-I35 — Installability is tested'.

- linked source rows: SRC002-S0044
- linked source atoms: (none)

### PRD-092: X-Graph — Validation and execution

Cover 1 source coverage row(s) and 2 requirement atom(s) from section 'X-Graph — Validation and execution'.

- linked source rows: SRC002-S0081
- linked source atoms: SRC002-S0081-A01, SRC002-S0081-A02
- [ ] AC-PRD-092-01: Satisfy source atom SRC002-S0081-A01: Validation targets/plans, evaluator bundles, experiment genomes, model/code runs, stage results, challenges, replicati [constraints: targets/plans; model/code] (verify: interface-check -> verify_src002_s0081_a01)
- [ ] AC-PRD-092-02: Satisfy source atom SRC002-S0081-A02: Evolution produces append-only revisions and projections across these graphs; it does not overwrite them. (verify: negative-test -> verify_src002_s0081_a02)

### PRD-115: Part VII — Verifier Firewall

Cover 1 source coverage row(s) and 0 requirement atom(s) from section 'Part VII — Verifier Firewall'.

- linked source rows: SRC002-S0104
- linked source atoms: (none)

### PRD-131: 33. Required adapter tests

Cover 12 source coverage row(s) and 13 requirement atom(s) from section '33. Required adapter tests'.

- linked source rows: SRC002-S0120-R001, SRC002-S0120-R002, SRC002-S0120-R003, SRC002-S0120-R004, SRC002-S0120-R005, SRC002-S0120-R006, SRC002-S0120-R007, SRC002-S0120-R008, SRC002-S0120-R009, SRC002-S0120-R010, SRC002-S0120-R011, SRC002-S0120-R012
- linked source atoms: SRC002-S0120-R001-A01, SRC002-S0120-R002-A01, SRC002-S0120-R003-A01, SRC002-S0120-R004-A01, SRC002-S0120-R005-A01, SRC002-S0120-R006-A01, SRC002-S0120-R007-A01, SRC002-S0120-R008-A01, SRC002-S0120-R009-A01, SRC002-S0120-R010-A01, SRC002-S0120-R011-A01, SRC002-S0120-R011-A02, SRC002-S0120-R012-A01
- [ ] AC-PRD-131-01: Satisfy source atom SRC002-S0120-R001-A01: -: exact source/package/license pin; [constraints: source/package/license] (verify: interface-check -> verify_src002_s0120_r001_a01)
- [ ] AC-PRD-131-02: Satisfy source atom SRC002-S0120-R003-A01: -: proposed/evaluated/persisted/failed/missing reconciliation; [constraints: proposed/evaluated/persisted/failed/missing] (verify: negative-test -> verify_src002_s0120_r003_a01)
- [ ] AC-PRD-131-03: Satisfy source atom SRC002-S0120-R004-A01: -: crash/resume/idempotency; [constraints: crash/resume/idempotency] (verify: interface-check -> verify_src002_s0120_r004_a01)
- [ ] AC-PRD-131-04: Satisfy source atom SRC002-S0120-R006-A01: -: evaluator/holdout isolation; [constraints: evaluator/holdout] (verify: interface-check -> verify_src002_s0120_r006_a01)
- [ ] AC-PRD-131-05: Satisfy source atom SRC002-S0120-R007-A01: -: sandbox/egress/resource controls; [constraints: sandbox/egress/resource] (verify: interface-check -> verify_src002_s0120_r007_a01)
- [ ] AC-PRD-131-06: Satisfy source atom SRC002-S0120-R008-A01: -: score/evidence-class separation; [constraints: score/evidence-class] (verify: interface-check -> verify_src002_s0120_r008_a01)
- [ ] AC-PRD-131-07: Satisfy source atom SRC002-S0120-R011-A01: -: clean rollback/uninstall. [constraints: rollback/uninstall.] (verify: negative-test -> verify_src002_s0120_r011_a01)
- [ ] AC-PRD-131-08: Satisfy source atom SRC002-S0120-R011-A02: The source study is not an endorsement of a floating `main` dependency. [constraints: main] (verify: negative-test -> verify_src002_s0120_r011_a02)

### PRD-161: V — Validation Bay

Cover 6 source coverage row(s) and 6 requirement atom(s) from section 'V — Validation Bay'.

- linked source rows: SRC002-S0150-R001, SRC002-S0150-R002, SRC002-S0150-R003, SRC002-S0150-R004, SRC002-S0150-R005, SRC002-S0150-R006
- linked source atoms: SRC002-S0150-R001-A01, SRC002-S0150-R002-A01, SRC002-S0150-R003-A01, SRC002-S0150-R004-A01, SRC002-S0150-R005-A01, SRC002-S0150-R006-A01
- [ ] AC-PRD-161-01: Satisfy source atom SRC002-S0150-R001-A01: -: **V01 — ValidationTarget manifests and eligibility** Dependencies: `E04, F04, R04, T04` · Risk: `high` · Review: `r [constraints: E04, F04, R04, T04; high; required] (verify: interface-check -> verify_src002_s0150_r001_a01)
- [ ] AC-PRD-161-02: Satisfy source atom SRC002-S0150-R002-A01: -: **V02 — Preregistered ValidationPlan and falsification rules** Dependencies: `V01` · Risk: `high` · Review: `requir [constraints: V01; high; required] (verify: interface-check -> verify_src002_s0150_r002_a01)
- [ ] AC-PRD-161-03: Satisfy source atom SRC002-S0150-R003-A01: -: **V03 — Capability-controlled execution and receipts** Dependencies: `V01` · Risk: `high` · Review: `required` [constraints: V01; high; required] (verify: interface-check -> verify_src002_s0150_r003_a01)
- [ ] AC-PRD-161-04: Satisfy source atom SRC002-S0150-R004-A01: -: **V04 — V-phase result reconciliation and evidence-class gate** Dependencies: `V02, V03` · Risk: `high` · Review: ` [constraints: V02, V03; high; required] (verify: interface-check -> verify_src002_s0150_r004_a01)
- [ ] AC-PRD-161-05: Satisfy source atom SRC002-S0150-R005-A01: -: **V05 — Validation cascade, OOD challenge, independent replication and promotion ceiling** Dependencies: `V04, S05, [constraints: V04, S05, Q05, R05; critical; required] (verify: interface-check -> verify_src002_s0150_r005_a01)
- [ ] AC-PRD-161-06: Satisfy source atom SRC002-S0150-R006-A01: -: **V06 — Experiment/replication end-to-end integration gate** Dependencies: `V05, P05, Q05` · Risk: `critical` · Rev [constraints: V05, P05, Q05; critical; required; Experiment/replication] (verify: interface-check -> verify_src002_s0150_r006_a01)

