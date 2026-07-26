# Epistemic Foundry v3.0.0
## Native Plugin Shell + Evidence-Gated Research Operating System
### Codex / Claude Code 상세 아키텍처 및 A–Z 개발 명세서

- 문서 상태: **SPEC_BUNDLE / Implementation Contract**
- 구현 상태: **NOT CLAIMED**
- 기준일: **2026-07-26**
- 제품명: **Epistemic Foundry**
- 플러그인 ID: `epistemic-foundry`
- CLI: `efoundry`
- 핵심 연구 프로토콜: **FORGE — Frame / Observe / Reason / Gate / Export-Evolve**
- 추론 런타임: **Foundry Kernel**
- 증거 심의: **Asymmetric Evidence Parliament**
- 지식 구조: **E/R/D/X Four-Graph**
- 기준 규모: 50편 gold → 200편 pilot → 1,800–2,000편 production qualification
- 도메인 정책: **domain-neutral core + versioned DomainPack**

---

# Part I — Authority, research basis and v3 decision

## 1. Authority order

1. `MASTER_SPEC.md`
2. `manifests/development_manifest.yaml`
3. `manifests/acceptance_matrix.yaml`
4. `manifests/product_invariants.yaml`
5. canonical schemas and workflows
6. `manifests/role_registry.yaml`
7. `AGENTS.md` or `CLAUDE.md`
8. work-package-local notes

A lower source cannot override a higher source. A missing or inconsistent shared contract yields `SPEC_GAP`; a clear contract blocked by an unavailable external prerequisite yields `BLOCKED`. `PASS` requires objective checks, resolving artifacts/receipts and independent review.

## 2. Status semantics

This package defines the target v3 architecture and implementation graph. It does **not** claim a working marketplace plugin, MCP server, hooks, dashboard, parser stack or production deployment. The reference plugin blueprint contains safe stubs that exit with code 78 specifically to prevent a specification from masquerading as implementation.

Status vocabulary is defined in `docs/status_taxonomy.md`.

## 3. CodexClaw research result

The public `lidge-jun/codexclaw` main branch was inspected at the latest visible 2026-07-23 commit (`bb143d9`), with plugin/package version `0.1.1`. The study covered its plugin manifest, 27-skill layout, 18 lifecycle hooks, PABCD file-backed FSM and attestations, payload CLI, recall, repository map, remote skill search, role-based subagent configuration, optional MCP, GUI, and repository-authored architecture audit.

The v3 adoption decision is:

- adopt the native plugin delivery model, payload CLI, progressive skills, lifecycle integration, recall, mapping, skill routing, role configuration, doctor and fresh-install discipline;
- replace PABCD with the research-native FORGE lifecycle;
- replace narrative attestation with schema-valid artifact/effect receipts;
- treat hooks as observed guardrails, never the complete security boundary;
- use transactional local/team stores instead of JSON session files as canonical authority;
- correct default map ranking and separate centrality, relevance and risk;
- quarantine remote skills before exact-hash activation;
- generate GUI/API contracts and expose explicit degraded states;
- make remote messaging optional and non-commanding by default.

The complete source inventory and 32-row adoption/correction matrix are in `research/codexclaw_gap_analysis.md`.

## 4. v3 thesis

> **Epistemic Foundry v3 is a domain-neutral, coverage-first, evidence-gated research operating system delivered through a native plugin shell. The shell supplies host integration and user experience; Foundry Kernel owns state, evidence, authority, side effects, replay and scientific promotion.**

A native experience must make rigor immediate without making rigor optional.

# Part II — Product constitution: 40 invariants

### EF3-I01 — Kernel authority

Plugin shell, hooks, skills, GUI, chat transcripts and provider SDKs never own canonical state, policy, gates or replay.

### EF3-I02 — Claim-first evidence

A promoted empirical or documentary claim always resolves to immutable SourceSpan evidence.

### EF3-I03 — Falsifiable intake

An insight without scope, predictions and falsifier cannot enter Observe or Parliament.

### EF3-I04 — Coverage before confidence

Coverage, searched scope, missing lanes and dependency diversity are shown before confidence or verdict.

### EF3-I05 — Search-state type safety

UNSEARCHED, SEARCHED_NONE, SEARCHED_WITH_RESULTS and failed search are distinct.

### EF3-I06 — Adversarial retrieval

Counterevidence, null, boundary and method lanes are mandatory whenever applicable.

### EF3-I07 — Method comparability

Method-incompatible evidence is stratified and may impose a promotion ceiling; it is never silently pooled.

### EF3-I08 — Dependency-adjusted evidence

Shared samples, datasets, publication families and derived analyses are dependency clusters, not independent votes.

### EF3-I09 — No majority authority

Agent count or majority agreement cannot promote a hypothesis.

### EF3-I10 — Inference separation

Induction, deduction, abduction and causal identification remain separate typed outputs.

### EF3-I11 — Evidence-class separation

Simulation, formal derivation, benchmark and review-derived evidence never become empirical observation by relabeling.

### EF3-I12 — No self-approval

Makers cannot approve their own work, claim promotion, validation, or release.

### EF3-I13 — Receipt-bound completion

Phase transitions, side effects, tests, installs and releases require resolving artifact/effect receipts.

### EF3-I14 — Hooks are guardrails

Hook coverage is observed and useful but never treated as the complete enforcement boundary.

### EF3-I15 — Capability negotiation

Host and dependency capabilities are runtime-probed; missing capabilities select explicit degraded or blocked modes.

### EF3-I16 — Event-sourced state

Canonical session and lifecycle state is reducer-derived from append-only events with revision control.

### EF3-I17 — Explicit human authority

Human approvals and overrides are immutable records with viewed revisions, rationale, scope and downstream invalidation.

### EF3-I18 — Consent-bound memory

Recall occurs only within allowed memory classes, purpose, consent, retention and workspace scope.

### EF3-I19 — Workspace isolation

Cross-workspace state, memory and artifacts are denied by default below the model layer.

### EF3-I20 — Canonical context capsule

Compaction and resume context is rebuilt from hash-bound canonical artifacts with exclusions and freshness.

### EF3-I21 — Skill supply-chain quarantine

Third-party skills are quarantined, inspected, permissioned, pinned and approved before activation.

### EF3-I22 — Generated transport contracts

CLI, MCP, HTTP, persistence and UI models derive from canonical schemas; duplicated wire literals are forbidden.

### EF3-I23 — Honest UI state

EMPTY_CONFIRMED, DEGRADED and UNAVAILABLE are distinct; backend failure never appears as empty research state.

### EF3-I24 — Real map ranking

A map labeled as ranked uses an actual algorithm; baseline centrality, query relevance and risk remain separate.

### EF3-I25 — Role-scoped delegation

Every subagent dispatch resolves a RoleSpec with tool ACL, evidence ACL, write scope, budget and expected count.

### EF3-I26 — No silent partial fan-in

Fan-in reconciles expected and actual identities; missing outputs remain visible and constrain the result.

### EF3-I27 — Bounded cycles

Every cycle has a seen-set key, novelty/convergence rule, dry rounds, maximum rounds, budget and escalation.

### EF3-I28 — Typed budget enforcement

Budgets are labeled HARD_METERED, HARD_PREALLOCATED, SOFT_ESTIMATE or UNMETERED.

### EF3-I29 — Secret minimization

Secrets are opaque handles and never copied into prompts, evidence artifacts, logs or exports.

### EF3-I30 — Untrusted evidence plane

PDFs, web pages, datasets and model output are data and cannot grant authority or execute instructions.

### EF3-I31 — Migration and rollback

Breaking schema/plugin changes require compatibility, dry-run, backup, rollback and hook re-trust.

### EF3-I32 — Release provenance

Shipped bundles require reproducible build evidence, SBOM, manifest, clean extraction and signing status.

### EF3-I33 — Status honesty

Capabilities are labeled SPECIFIED, IMPLEMENTED, EXPERIMENTAL, DEFERRED or UNSUPPORTED; release labels are evidence-derived.

### EF3-I34 — Provider neutrality

Codex, Claude and other models are replaceable node executors; adapters cannot alter canonical semantics.

### EF3-I35 — Installability is tested

Fresh install, PATH-less execution, upgrade, downgrade, uninstall and cross-platform paths are product acceptance tests.

### EF3-I36 — Remote messaging minimized

Remote notification/approval adapters are optional and cannot execute arbitrary commands or export raw evidence by default.

### EF3-I37 — License-aware corpus/export

Source access and license restrictions propagate through retrieval, evidence, export and deletion.

### EF3-I38 — Stale propagation

Corrections, retractions, parser fixes, policy/ontology changes and new evidence invalidate dependent projections and Passports.

### EF3-I39 — Replayability

RunSpec, context, adapter/model, tools, receipts, policy, corpus and prompts are sufficient to explain and compare a run.

### EF3-I40 — Honest underdetermination

UNDERDETERMINED, UNTESTABLE, NOT_ASSESSED and PARTIAL are normal truthful outcomes, not system failure.



# Part III — Native plugin architecture

# Epistemic Foundry v3 plugin architecture

## 1. Status and product boundary

This document specifies the **v3.0.0 target architecture**. The bundle is an implementation contract and reference blueprint, not a claim that the production plugin has already been built.

Epistemic Foundry is split into two deliberately unequal parts:

1. **Foundry Plugin Shell** — native host integration: plugin manifest, skills, hooks, optional MCP, CLI dispatcher, dashboard assets, capability probes, and user-facing phase controls.
2. **Foundry Kernel** — canonical authority: immutable RunSpec, FORGE state machine, evidence ledger, action/effect receipts, policy, evidence graph, Parliament, replay, migrations, and release gates.

A hook, skill, model response, chat transcript, GUI cache, or provider SDK is never the canonical source of truth.

## 2. Product thesis

> A native plugin should make rigorous research feel immediate without making rigor optional.

CodexClaw demonstrates that skills, hooks, state, recall, mapping, subagent routing, and a payload CLI can be shipped in one plugin. v3 adopts this delivery shape but preserves Epistemic Foundry's claim-first and evidence-gated constitution.

## 3. Logical planes

```text
┌──────────────────────────────────────────────────────────────────────┐
│ P0  Experience Plane                                                │
│ Chat skills · CLI · dashboard · source-span viewer · Atlas · status │
├──────────────────────────────────────────────────────────────────────┤
│ P1  Plugin Integration Plane                                        │
│ manifest · hook gateway · MCP · capability probe · host adapters     │
├──────────────────────────────────────────────────────────────────────┤
│ P2  Orchestration Plane                                             │
│ E0-E5 classifier · FORGE FSM · DAG scheduler · role router           │
├──────────────────────────────────────────────────────────────────────┤
│ P3  Epistemic Plane                                                 │
│ Claim Forge · Atlas · Parliament · Aporia · Passport                 │
├──────────────────────────────────────────────────────────────────────┤
│ P4  Authority Plane                                                 │
│ policy · consent · capabilities · approvals · budgets · veto         │
├──────────────────────────────────────────────────────────────────────┤
│ P5  State and Provenance Plane                                      │
│ ledger · artifacts · receipts · snapshots · replay · migrations      │
├──────────────────────────────────────────────────────────────────────┤
│ P6  Execution Plane                                                 │
│ parsers · retrieval · sandbox · formal tools · validation targets    │
├──────────────────────────────────────────────────────────────────────┤
│ P7  Interoperability Plane                                          │
│ Codex · Claude Code · MCP · OpenAPI · DomainPack · export formats    │
├──────────────────────────────────────────────────────────────────────┤
│ P8  Assurance Plane                                                 │
│ evals · red team · compatibility · SBOM · signing · recovery         │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. Named modules

| Module | Responsibility | Must not own |
|---|---|---|
| **Foundry Kernel** | RunSpec, state transitions, scheduler, policy, gates, replay | provider chat state |
| **Plugin Shell** | native install and host lifecycle integration | epistemic truth |
| **Claim Forge** | SourceSpan → atomic ClaimCard → EvidenceNode | final verdict |
| **Epistemic Atlas** | coverage, absence/search state, method and dependency maps | unsupported confidence |
| **Evidence Parliament** | asymmetric independent briefs, attacks, vetoes, adjudication | majority-based promotion |
| **Aporia Engine** | contradiction resolution, moderators, competing explanations | forced single explanation |
| **Noetic Ledger** | append-only events, artifacts, approvals, effects, revisions | mutable summaries as authority |
| **Validation Bay** | preregistered model/solver/benchmark/experiment execution | empirical-label promotion by itself |
| **Context Capsule Service** | just-in-time, hash-bound context reconstruction | unconstrained memory dumping |
| **Workspace Cartographer** | code/corpus/workflow/artifact graph and ranking | fabricated global importance |
| **Skill Vault** | skill discovery, quarantine, inspection, locking, activation | immediate remote execution |
| **Compatibility Sentinel** | host feature probes and degraded-mode selection | optimistic assumptions |
| **Foundry Console** | local dashboard and source-span UX | duplicated wire contracts |

## 5. Deployment profiles

### 5.1 LITE

- Local SQLite WAL and content-addressed artifact directory.
- Markdown, text, structured datasets, and host-provided search.
- No GROBID, Docling, Postgres, or object store required.
- Supports Frame, bounded Observe, Reason, Gate, Passport, replay, and export.
- Honest limitations: large corpus parsing, shared-team concurrency, and high-throughput ingestion are disabled.

### 5.2 RESEARCH

- Python 3.12+ core, GROBID and Docling adapters, lexical/vector/citation retrieval.
- Local or remote PostgreSQL and S3-compatible object store.
- Full Claim Forge, Atlas, Parliament, and Validation Bay.
- Suitable for the 50- and 200-document gates.

### 5.3 TEAM

- PostgreSQL canonical store, object store, queue, RBAC, approval routing, shared DomainPacks.
- Concurrent sessions, policy packs, signed exports, backup/restore, audit views.
- Remote notification adapters are optional and read-only by default.

### 5.4 REGULATED

- Managed hook policy where available, controlled egress, retention and legal-hold rules.
- Signed releases and exports, dual control for overrides, immutable audit sink.
- Provider allowlist, confidential-compute or on-prem execution profile where required.
- No feature is inferred from profile name; every capability is runtime-probed.

## 6. Repository and plugin package boundary

```text
epistemic-foundry/
├── MASTER_SPEC.md
├── AGENTS.md
├── CLAUDE.md
├── packages/
│   ├── contracts/              # dependency-free generated contracts
│   ├── foundry-kernel/         # state, ledger, policy, scheduler
│   ├── plugin-host/            # hook gateway, CLI, MCP, capability probes
│   ├── role-router/            # RoleSpec compilation and dispatch
│   ├── context-capsule/        # context assembly and compaction recovery
│   ├── workspace-map/          # code/corpus/artifact graph
│   ├── skill-vault/            # quarantine, scan, lock, activation
│   ├── transport-kernel/       # retry, timeout, redaction, receipts
│   └── ui-api/                 # OpenAPI server and generated clients
├── python/
│   └── epistemic_foundry/      # scientific core and parser/retrieval adapters
├── web/                        # Foundry Console
├── plugins/
│   └── epistemic-foundry/
│       ├── .codex-plugin/plugin.json
│       ├── .mcp.json
│       ├── bin/efoundry.mjs
│       ├── skills/
│       ├── hooks/
│       ├── dist/
│       └── assets/
└── tests/
    ├── contracts/
    ├── install/
    ├── compatibility/
    ├── golden/
    ├── security/
    └── recovery/
```

Rules:

- Components import only published package APIs, never another component's `src/`.
- JSON Schema/OpenAPI is canonical; TypeScript/Python/UI types are generated.
- `dist/` is reproducibly generated and checked for source equivalence.
- Plugin-writable state uses `PLUGIN_DATA`; repository state uses `.epistemic-foundry/`.
- User corpus and secrets never live under the installed plugin root.
- Plugin upgrade never edits the user's corpus in place without a migration plan and backup receipt.

## 7. Host capability negotiation

At session start and after upgrade, the plugin runs a bounded capability probe and emits `HostCapabilityReport`.

Capabilities include:

- plugin manifest version and root hash;
- available hook events and tool coverage;
- MCP startup and tool schema;
- local Node and Python versions;
- SQLite/WAL support;
- worktree and sandbox availability;
- hosted-tool observability limitations;
- parser and retrieval adapters;
- network and proxy policy;
- signing and key availability;
- compatible schema/migration range.

Modes:

```text
FULL        required capabilities present
DEGRADED    optional capabilities missing; explicit substitutions available
READ_ONLY   writes or side effects unavailable
SAFE_MODE   state/migration integrity uncertain; only doctor/export/recovery allowed
BLOCKED     required invariant cannot be preserved
```

No missing hook is silently treated as active. The canonical CLI and kernel gates remain authoritative when hooks are disabled.

## 8. State architecture

### Local profile

- SQLite WAL for session, phase, ledger index, jobs, memory index, skill lock, compatibility, and migration records.
- Content-addressed immutable artifact directory.
- Append-only JSONL export mirror for inspection, not authority.
- Optimistic compare-and-swap on `expected_revision`.
- Single migration owner; repositories are split by bounded context.
- Crash recovery replays committed ledger events and reconciles orphan intents/effects.

### Team profile

- PostgreSQL for canonical relational state.
- S3-compatible content-addressed object store.
- Queue with lease/fencing semantics.
- Outbox/inbox pattern for external effects.
- Tenant and workspace isolation enforced below the model layer.

## 9. Hook architecture

All host hook payloads enter one `Hook Gateway`:

```text
host payload
→ normalize and hash
→ capability/policy lookup
→ side-effect-free decision
→ optional ActionIntent
→ kernel call
→ HookDecision + receipts
→ bounded host response
```

Hook categories:

| Category | Events | Default behavior |
|---|---|---|
| Bootstrap | SessionStart | probe, resume, health, minimal context |
| Intake | UserPromptSubmit | classify intent, detect unresolved scope, suggest skill |
| Tool guard | PreToolUse / PermissionRequest | capability, path, egress, secret, phase checks |
| Tool receipt | PostToolUse | hash outputs, register effects and failures |
| Delegation | SubagentStart / SubagentStop | bind RoleSpec, expected count, validate ResultEnvelope |
| Completion | Stop / SessionEnd | block unsupported completion claims at kernel/CLI; hook advises |
| Compaction | PreCompact / PostCompact | freeze cursor; rebuild ContextCapsule |

Because specialized and hosted tools may bypass local tool hooks, hook coverage is recorded as an observed capability and never described as exhaustive enforcement.

## 10. Skill architecture

The skill family follows progressive disclosure:

- `foundry` — parent router and constitution.
- `foundry-intake` — E0-E5 classification, Interview and Frame.
- `foundry-observe` — corpus/search plan, receipts, Evidence Pack.
- `foundry-claim-forge` — atomic extraction and grounding.
- `foundry-atlas` — coverage, gaps, dependency and method map.
- `foundry-reason` — induction, deduction, abduction and causal separation.
- `foundry-parliament` — asymmetric deliberation and veto.
- `foundry-aporia` — contradiction/moderator/competing mechanism.
- `foundry-validation` — preregistered external execution.
- `foundry-passport` — adjudicated export and next discriminating test.
- `foundry-recall` — consent-bound memory retrieval.
- `foundry-map` — workspace/corpus/repository map.
- `foundry-replay` — replay, drift, stale propagation.
- `foundry-domain-pack` — domain extension authoring.
- `foundry-admin` — doctor, policy, migration, backup, recovery.
- `foundry-plugin-dev` — plugin implementation and release.

Only metadata is always visible. Detailed references are loaded on demand. Sensitive or side-effecting skills disallow implicit invocation.

## 11. Subagent model

Canonical roles are `RoleSpec` records, not host names:

```text
evidence_scout
claim_extractor
defender
prosecutor
method_auditor
scope_auditor
inductivist
deductivist
causal_auditor
novelty_examiner
abductive_mediator
minority_reporter
judge
independent_attestor
validation_executor
contract_reviewer
```

Each RoleSpec declares:

- semantic mission and forbidden behavior;
- built-in host agent type mapping;
- model tier and fallback;
- read/write scopes;
- tool and network ACL;
- evidence ACL;
- expected input/output schema;
- budget and timeout;
- independence group;
- acceptance checks;
- failure and retry policy.

The spawn adapter injects host-specific prompts, but the ledger records the canonical RoleSpec and resolved model/runtime.

## 12. Concurrency and graph rules

- Data dependency, shared write target, quota, exclusive resource, mutable contract, approval, and privacy boundary all count as edges.
- Default write concurrency is 4; default read concurrency is 8; hard fleet cap is 16.
- A barrier is allowed only for a real set-wide operation.
- Pipeline/streaming is preferred to full barriers.
- Fan-in validates expected count, successful count, missing identities, and coverage.
- Missing results are never filtered away without a partiality record.
- Large fan-in is hierarchical and evidence-preserving.
- Cycles require a `LoopContract`: novelty measure, seen-set key, dry-round rule, max rounds, max budget, and escalation.
- Dedupe is against all seen candidates, not only accepted candidates.

## 13. Authority and degraded behavior

The plugin may be useful in degraded mode, but never deceptively complete.

Examples:

- hooks unavailable → explicit skill/CLI gates; health is DEGRADED;
- MCP unavailable → CLI adapter; no tool is advertised as active;
- parser unavailable → text-only ingest with `layout_unverified`;
- external novelty search unavailable → `NOVELTY_NOT_ASSESSED`;
- budget meter unavailable → `SOFT_ESTIMATE`, never hard-cap language;
- backend unavailable → dashboard shows UNAVAILABLE, not empty data;
- partial agent fan-out → no full synthesis unless policy explicitly allows a PARTIAL result.

## 14. Architectural non-goals

v3 does not promise:

- universal truth discovery;
- fully autonomous production operation without policy and deployment values;
- independence merely because agents use different model vendors;
- global novelty from a local corpus;
- empirical confirmation from simulation;
- complete prompt-injection defense from hooks alone;
- a hard currency budget when the provider exposes no authoritative meter;
- safe remote command execution through chat messengers by default;
- that a specification bundle is a completed implementation.


# Part IV — FORGE lifecycle

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


# Part V — Epistemic core retained and strengthened from v2

The following core contracts remain normative. Where terminology or counts differ, the v3 constitution, FORGE protocol and current manifests take precedence.

## 4. 사용자 경험: 씽킹 매트릭스의 정확한 이식

### 4.1 네 개의 보드

#### A. Idea Matrix
사용자가 한 줄 아이디어를 입력하면 다음을 구조화한다.

- canonical statement
- ScopeVector
- mechanism path
- atomic predictions
- null model
- alternative hypotheses
- falsifiers
- lens/operator provenance

반증조건이 비어 있거나 핵심 용어가 모호하면 `INBOX`. 자동 보정으로 의회에 밀어 넣지 않는다.

#### B. Evidence Coverage Board
기본 화면은 논문 목록이 아니라 coverage cube의 2D slice다.

필수 증거 역할:
- direct support
- indirect/mechanistic support
- counterevidence
- null / failed replication
- boundary condition
- method validity
- alternative explanation
- independent replication
- unsearched scope

#### C. Council Board
카드는 다음만 보여준다.

- role
- typed claim/objection
- Evidence IDs
- target Claim/Argument ID
- assumption
- gate effect
- resolved/unresolved
- minority status

에이전트의 자유로운 대화 transcript를 권위 있는 산출물로 취급하지 않는다.

#### D. Convergence Matrix
기본 축:

- x: **독립성 보정 증거 강도**
- y: **판별 가능한 검증 가능성**

novelty, impact, chapter fit, cost는 보조 필터다. 사람은 자동 배치된 카드를 드래그할 수 있지만, 이동은 새 revision과 rationale로 기록한다.

### 4.2 Coverage Cube

보드의 2축은 실제 저장모델이 아니라 고차원 cube의 projection이다. Core는 다음 범용 축을 제공하고, DomainPack이 전문 축을 추가한다.

필수 core 축:

1. evidence role: support/counter/null/boundary/method/alternative
2. unit of analysis: component/item → individual/entity → group → organization → population/system
3. temporal scale: instantaneous → short-term → longitudinal → lifecycle
4. population/entity and setting
5. intervention or exposure and comparator
6. outcome/construct family
7. method/measurement construct
8. dataset/source family and era

DomainPack 선택 축 예:

- 생물학적 수준, 재료 계층, 법적 관할, 시장 체제, 언어권, 소프트웨어 계층
- 도메인 고유 과정·자원·위험축
- 도메인 고유 처리 강도·상태·단계

핵심 지표:

- `coverage_gap_count`
- `independent_evidence_units`
- `method_diversity`
- `source_family_diversity`
- `era_diversity`
- `scope_extrapolation_distance`
- `lens_entropy`
- `dominant_lens_share`
- `dependency_inflation_ratio`
- `unsearched_scope_count`
- `domain_pack_coverage`

한 숫자의 “신뢰점수”로 압축하지 않는다. UI에는 vector, 빈칸, 과집중, 검색되지 않은 범위를 함께 보여준다.

### 4.3 9렌즈의 지위

오스본 계열 9렌즈는 ontology가 아니라 **Hypothesis Mutation Operator plug-in**이다.

| Operator | 범용 변형 |
|---|---|
| adapt | 대상·환경·관할·언어·시간·공간 스케일 전이 |
| borrow | 인접 분야의 메커니즘·표현·검증법 이식 |
| modify | 가정·함수형·상태·정의 변경 |
| magnify | 시간·공간·강도·복잡도 확대 |
| minify | 최소 상태·최소 메커니즘·최소 증거 |
| substitute | 변수·측정·proxy·모델·데이터원 대체 |
| rearrange | 인과 순서·모듈·단계·제어체적 재배치 |
| reverse | 역인과·부정·null model·반례 |
| combine | 독립 Claim·기전·데이터·방법 결합 |

모든 파생 가설은 `parent_hypothesis_id`, `operator_id`, `delta`, `domain_pack_id`를 가진다. 렌즈 분포가 한 operator에 과도하게 몰리면 관성 경고를 낸다. 임계값은 config로 관리하고 gold set으로 보정한다.

## 5. 정규 데이터 모델

### 5.1 핵심 분리: Paper ≠ Claim ≠ Evidence

- `Paper`: 서지적 작품(work)
- `PaperVersion`: preprint, accepted manuscript, journal version, correction 등 실제 버전
- `SourceSpan`: 특정 버전의 페이지·bbox·문자 범위·hash
- `ClaimCard`: 저자 또는 시스템이 표현한 원자적 명제
- `Experiment`: 처리–비교–측정–표본 설계
- `EvidenceNode`: 특정 Experiment/SourceSpan이 Claim에 제공하는 증거 역할
- `Argument`: 여러 Claim/Evidence를 연결한 추론
- `Hypothesis`: 검정 가능한 등록 명제
- `Adjudication`: 의회가 특정 run에서 내린 구조화 판정

한 Claim은 여러 span에 걸칠 수 있고, 한 EvidenceNode가 여러 관련 Claim을 지지할 수 있다. 그러나 “논문 전체가 가설을 지지한다”는 edge는 금지한다.

### 5.2 ClaimCard 최소 계약

정식 스키마는 `schemas/claim-card.schema.json`과 `schemas/scope-vector.schema.json`이 권위다. 의미상 필수 필드는 다음과 같다.

```yaml
identity:
  claim_id:
  version:
  paper_id:
  paper_version_id:

source:
  source_spans:
  verbatim_text:

proposition:
  claim_type:
  author_stance:
  subject:
  relation:
  object:
  direction:

scope:
  domain:
  population:
  entity_type:
  entity_subtype:
  unit_of_analysis:
  setting:
  geography:
  jurisdiction:
  language:
  lifecycle_stage:
  spatial_scale:
  temporal_scale:
  time_period:
  measurement_time:
  intervention_or_exposure:
  comparator:
  inclusion_criteria:
  exclusion_criteria:
  conditions:
  domain_extensions:

design:
  method_ids:
  dataset_family_id:
  quantitative:
  hedging_level:
  evidence_layer:

provenance:
  parser_version:
  extractor_model:
  prompt_hash:
  created_at:
  human_review:
```

#### Claim 유형
`observation, association, causal, mechanism, theory, model, method, limitation, review_synthesis, background_assertion, speculation`

#### Author stance
`asserted, supported, suggested, speculative, qualified, negated, unclear`

#### Evidence layer
`direct_measurement, primary_analysis, modeling, formal_derivation, benchmark_execution, review, background, unsupported`

Evidence layer는 provenance·검색·승격 제한을 위한 구분이다. 서로 다른 추론 종류를 하나의 전역 순위로 강제하지 않으며, 실제 증거력은 QualityVector의 직접성·설계·측정·정밀도·재현·독립성·범위 일치로 따로 기록한다.

### 5.3 ScopeVector

Scope는 edge의 부가 메모가 아니라 비교·추론의 1급 객체다. Core 계약은 `schemas/scope-vector.schema.json`이며 어느 도메인에도 특정된 필드를 포함하지 않는다.

Core 축:

- domain
- population
- entity type/subtype
- unit of analysis
- setting
- geography/jurisdiction/language
- lifecycle stage
- spatial and temporal scale
- time period and measurement time
- intervention or exposure
- comparator
- inclusion/exclusion criteria
- material conditions
- domain extensions

`intervention_or_exposure`는 이름, 범주, 값 범위, 단위, 지속, 빈도, 속도, 전달 경로를 가질 수 있다. 도메인 고유 필드는 core schema에 추가하지 않고 `domain_extensions`에 넣으며, 사용 가능한 key와 비교 규칙은 versioned `DomainPack`이 선언한다.

값이 보고되지 않았으면 `null` 또는 명시적 unknown 상태를 사용한다. 일반 지식이나 문맥으로 누락된 범위를 보완하지 않는다. 같은 용어를 사용해도 대상·분석단위·시간·방법이 다르면 별도 scope로 유지한다.

### 5.4 MethodConstruct

이름이 같은 변수가 동일한 측정량임을 보장하지 않는다.

```yaml
method_id:
construct_id:
instrument_family:
protocol:
calibration:
spatial_resolution:
temporal_resolution:
stabilization_rule:
valid_range:
known_biases:
direct_or_proxy:
```

두 Evidence를 합치기 전에 comparability를 판정한다.

- `DIRECT`: 같은 construct와 직접 측정
- `COMPATIBLE`: 검증된 변환/비교 가능
- `PROXY`: 간접 지표; 별도 층
- `NOT_COMPARABLE`
- `UNKNOWN`

### 5.5 DatasetFamily와 독립성

다음은 독립 증거로 중복 계산하지 않는다.

- 동일 실험의 여러 논문
- 동일 cohort/dataset의 재분석
- preprint와 journal version
- review가 원논문을 재서술
- 동일 모델 output의 반복 출판
- 동일 표본의 여러 outcome 보고

`DatasetFamily`, `ExperimentFamily`, `PublicationFamily`를 분리할 수 있으며, 최소 MVP에서는 하나의 dependency cluster와 edge reason을 저장한다.

### 5.6 QualityVector

사용자에게 보이는 품질 정보:

- directness
- design strength
- measurement validity
- statistical precision
- replication
- independence
- scope match
- extraction confidence

검색 정렬을 위해 내부 scalar를 계산할 수 있으나:
1. 공식 판정에서 scalar만 제시하지 않는다.
2. null은 0과 다르다.
3. journal prestige와 citation count를 직접성으로 대체하지 않는다.
4. dependency-adjustment 전 paper count를 evidence strength로 표시하지 않는다.

---

## 6. Four-Graph 의미 구조

Four-Graph는 네 개의 독립 DB를 뜻하지 않는다. canonical relational/event store에서 목적별로 projection되는 논리 그래프다.

### 6.1 E-Graph — Evidence

노드:
`Paper, PaperVersion, SourceSpan, Figure, Table, Experiment, EvidenceNode, Method, DatasetFamily, Variable, Condition`

핵심 edge:
- `VERSION_OF`
- `CONTAINS`
- `STATES`
- `GROUNDS`
- `MEASURES`
- `USES_METHOD`
- `SUPPORTS`
- `COUNTERS`
- `NULL_FOR`
- `BOUNDARY_OF`
- `REPLICATES`
- `SHARES_SAMPLE`
- `DERIVED_FROM`

규칙: evidence edge는 SourceSpan과 provenance manifest 없이는 생성되지 않는다.

### 6.2 R-Graph — Reasoning

노드:
`Hypothesis, Prediction, Premise, Rule, Assumption, Mechanism, Falsifier, AlternativeHypothesis, BoundaryCondition, Argument`

edge:
- `PREMISE_OF`
- `IMPLIES`
- `INDUCTIVELY_SUPPORTS`
- `ATTACKS`
- `UNDERCUTS`
- `REBUTS`
- `EXPLAINS`
- `COMPETES_WITH`
- `PREDICTS`
- `FALSIFIED_BY`
- `DEPENDS_ON`

실증 사실과 에이전트 추론을 섞지 않는다.

### 6.3 D-Graph — Deliberation

노드:
`CouncilRun, AgentAssignment, ContextManifest, Brief, Objection, MinorityReport, GateDecision, Adjudication, Attestation, HumanDecision`

edge:
- `ASSIGNED_TO`
- `SEES_CONTEXT`
- `CITES`
- `TARGETS`
- `BLOCKS`
- `WAIVES`
- `ATTESTS`
- `REVISES`

판정뿐 아니라 어떤 증거가 누구에게 보였고 어떤 증거가 제외되었는지 재생한다.

### 6.4 X-Graph — Validation and Execution

노드:
`ValidationTarget, ValidationPlan, ExperimentTicket, ArtifactVersion, InputSet, ParameterSet, Scenario, ExecutionRun, DatasetSlice, Metric, Result, Failure, EffectReceipt, ReconciliationRecord`

edge:
- `TARGETS`
- `IMPLEMENTS`
- `USES_ARTIFACT`
- `USES_INPUT_SET`
- `USES_PARAMETER_SET`
- `RUNS_ACTION`
- `RUNS_SCENARIO`
- `PRODUCES`
- `TESTS_PREDICTION`
- `EVALUATES_FALSIFIER`
- `RECONCILES_TO_EVIDENCE`

`ExecutionRun`은 simulation, analysis pipeline, formal solver, benchmark, external service, experimental platform의 공통 상위 개념이다. 결과 subtype을 지우지 않으며, 계산 결과를 실측으로 재라벨링하지 않는다.

### 6.5 Core ontology와 DomainPack

Ontology는 다섯 번째 그래프가 아니라 Four-Graph를 관통하는 공통 의미 계층이다.

Core가 보장하는 것:

- synonym/abbreviation
- unit, representation, and dimension
- broader/narrower
- measured variable vs latent state vs parameter vs control vs output
- proxy/direct
- causal role
- spatial/temporal scale
- method construct
- study and execution design
- provenance and dependency

도메인 전문성은 `schemas/domain-pack.schema.json`을 따르는 versioned `DomainPack`으로 분리한다.

DomainPack이 제공할 수 있는 것:

- 전문 ontology와 controlled vocabulary
- `domain_extensions` 허용 key
- method catalog와 measurement bridge
- unit registry
- coverage axes
- retrieval lexicon
- validation-adapter reference

DomainPack은 core Claim/Evidence status, gate, capability, provenance, replay 계약을 덮어쓸 수 없다. 초기에는 도메인별 핵심 개념 약 20–50개와 고빈도 mapping만 사람이 승인하고 완성형 ontology를 기다리지 않는다.

## 7. 코퍼스 인제스트

정식 DAG는 `workflows/corpus_ingest.workflow.yaml`.

### 7.1 저장 단계

1. 원본 PDF bytes를 content-addressed object store에 저장
2. SHA-256, 크기, mime, 등록 시각 기록
3. DOI/title/author/year 정규화
4. preprint/final/correction/retraction 관계 등록
5. GROBID TEI 생성
6. DoclingDocument 생성
7. 페이지·bbox·문자 범위를 가진 Canonical SourceSpan 생성
8. Results/Methods/Discussion, caption, table, figure, formula를 별도 element로 유지
9. parse QC 후 Tier 부여

원본은 덮어쓰지 않는다. 새 파일은 새 `PaperVersion`.

### 7.2 GROBID와 Docling의 역할

- GROBID: 논문 구조, header, section, citation/reference, TEI
- Docling: reading order, layout, table structure, formula, image classification, element provenance

둘 중 하나를 진실로 간주하지 않는다. `normalize_document`가 충돌을 기록하며 병합한다. 좌표 제공이 없는 구조는 char span과 page를 최소 locator로 유지한다.

### 7.3 표·그림 보존

정량 evidence가 표·그림에 집중될 수 있으므로:

- caption은 본문 chunk에 단순 병합하지 않고 독립 span으로 저장
- Results paragraph의 figure/table reference를 edge로 연결
- table cell은 row/column header를 포함한 주소를 가진다
- figure OCR/vision은 Tier 2에서만, 사람이 확인 가능한 artifact와 confidence를 남긴다
- 추출 불가 값은 “그림에 있음”으로 표시하고 수치를 발명하지 않는다

### 7.4 처리 Tier

#### Tier 0 — 전량
metadata, structure, full text, lexical index, embeddings, citations, layout inventory

#### Tier 1 — 전량 또는 관련 subset
claim candidate, variables, coarse scope, method family, extraction confidence

#### Tier 2 — query-activated 200–500편
quantitative result, detailed protocol, tables/figures, boundary conditions, alternatives, human review

전체 2,000편에 가장 비싼 반복 추출을 선행하지 않는다.

### 7.5 로컬 우선과 저작권

- 사용자가 합법적으로 보유한 PDF는 로컬 처리 기본
- 외부 provider에 원문을 전송할지는 corpus policy와 라이선스로 결정
- 외부 전송 금지 문서는 local model/deterministic parser lane만 사용하거나 사람이 검토
- 원문을 API response에 재배포하지 않는다
- export에는 필요한 짧은 evidence span과 citation metadata만 포함

---

## 8. Claim–Evidence 추출 파이프라인

정식 DAG는 `workflows/claim_extraction.workflow.yaml`.

### 8.1 Evidence Unit

기본 chunk:

> Results paragraph + 그 paragraph가 직접 참조한 figure/table caption/cells + 필요한 최소 Methods context

고정 토큰 chunk가 아니라 논문 구조와 연결관계를 사용한다.

### 8.2 다중 패스

#### Pass A — Candidate detection
고재현율. Claim 후보와 span만 추출. 저비용 모델 가능.

#### Pass B — Atomicization and scope
한 명제로 분해하고 ScopeVector, author stance, hedging, method, quantitative field를 추출.

#### Pass C — Grounding verifier
더 강한 모델 또는 독립 검증기가 원문 span을 다시 읽고:
`accept / correct / reject`

승격된 Claim은 Pass C를 통과해야 한다.

### 8.3 결정론적 validator

- source span 존재
- char_end > char_start
- page valid
- passage hash 일치
- 한 Claim에 상충하는 두 relation이 섞이지 않음
- 필수 scope key 존재
- 숫자와 단위 원문 일치
- review/background layer가 direct_measurement로 지정되지 않음
- extractor output schema strict
- unknown fields reject

### 8.4 서론·리뷰 격리

서론에서 “X가 Y를 증가시킨다”고 말해도 그 논문의 직접 evidence가 아니다.

- `background_assertion`: E-Graph의 background layer
- 인용 원문을 찾으면 primary Claim/Evidence로 연결
- review synthesis는 dependency ancestry를 통해 primary evidence와 구분
- 직접측정 > 분석 > 모델링 > 리뷰 > 배경의 layer를 항상 노출

### 8.5 인간 검토 큐

다음 Claim은 자동 승격하지 않고 큐로 보낸다.

- extraction confidence < threshold
- ontology mapping conflict
- method construct unknown
- quantitative value가 그림에서만 추출됨
- causal/mechanistic claim인데 중간 premise가 없음
- high-impact hypothesis에서 핵심 edge 역할
- contradiction priority 상위

---

## 9. 검색: Relation-Aware Multi-Lane Retrieval

Vector-only 검색은 비슷한 문장을 우선하므로 확증편향을 만들 수 있다. 검색 planner는 다음 lane을 별도로 컴파일한다.

1. exact lexical/method/equation
2. semantic paraphrase
3. entity/variable
4. citation ancestry and descendants
5. mechanism
6. direct counterevidence
7. null/failed replication
8. boundary condition/moderator
9. method/measurement validity
10. prior-art/novelty

### 9.1 역방향 검색

가설이 `A increases B`이면 최소한:

- A decreases B
- A has no effect on B
- B causes A
- C causes A and B
- effect only under/above/below condition M
- measurement artifact or proxy mismatch

를 별도 query로 만든다.

### 9.2 Evidence Pack quota

기본 target은 config로 관리한다. 예시:

- 2–4 direct support
- 2–4 counter/refuting
- 1–3 null/failed replication
- 2–3 boundary
- 1–2 method
- closest prior art
- unsearched scopes

quota를 못 채우면 빈칸을 그대로 기록한다. 저품질 evidence로 숫자를 맞추지 않는다.

### 9.3 Reconciliation

fan-in은 LLM이 아니라 deterministic code가 우선 수행한다.

- flatten
- strict schema validation
- duplicate/version merge
- dependency cluster
- role classification
- method comparability
- expected node/lane count
- partial status
- source hash check

semantic judgment이 필요한 관계만 모델에 위임한다.

### 9.4 검색 완전성의 의미

“전체 문헌을 검색했다”는 표현을 금지한다. 기록할 것:

- corpus snapshot hash
- indexes
- query strings/hashes
- date range
- language
- included/excluded source
- top-k and stopping rule
- failed lanes
- unsearched scope

---

## 10. 조건 인식형 모순 및 moderator 엔진

### 10.1 후보 생성

같은 normalized `(subject, relation target, outcome)`에 대해 direction이 반대/null인 Claim pair를 후보로 만든다.

### 10.2 비교 순서

1. 같은 construct인가
2. method가 direct/compatible인가
3. population/entity/unit of analysis/lifecycle stage가 겹치는가
4. intervention/exposure metric, range, duration, and rate가 겹치는가
5. ambient conditions, operating context, and measurement time가 겹치는가
6. temporal/spatial scale가 겹치는가
7. dataset family가 독립적인가

### 10.3 분류

- `TRUE_CONTRADICTION`
- `SCOPE_DIFFERENCE`
- `BOUNDARY_CONDITION`
- `METHOD_DIFFERENCE`
- `TEMPORAL_DIFFERENCE`
- `MEASUREMENT_ARTIFACT_CANDIDATE`
- `DIFFERENT_QUESTION`
- `INSUFFICIENT_SCOPE_DATA`

### 10.4 moderator discovery

LLM이 후보를 제안할 수 있으나 순위는 검증 가능한 feature 비교로 계산한다.

추천 절차:

1. contradiction pair의 condition vector difference 생성
2. 단일 moderator 후보를 먼저 평가
3. 충분한 사례가 있으면 decision tree, hierarchical model, information gain 사용
4. 적은 사례에서는 MDL/parsimony + evidence support
5. residual contradiction을 계산
6. 두 개 이상 competing explanation 유지
7. 각각을 구분하는 관측을 생성

출력은 “해결됨”이 아니라:
`candidate moderator / supporting pairs / exceptions / discriminating test`.

### 10.5 우선순위

모순 우선순위는 다음 vector로 표시한다.

- scope overlap
- method comparability
- evidence quality
- independence
- direction opposition
- novelty
- validation-target representability
- experimental actionability

---

## 11. 네 추론 엔진

### 11.1 Deductive Engine

입력:
`Premise + Rule + Scope + Evidence IDs`

출력:
`proof trace, assumptions, entailed predictions, broken edges, countermodel`

원칙:
- conservation law/definition과 empirical premise 분리
- 모든 empirical premise에 Evidence ID
- 임계값·ceteris paribus·시간순서 명시
- conclusion scope ≤ premises scope
- 끊긴 edge는 연구 공백

Datalog 또는 제한된 rule representation을 MVP에 사용한다. 자연어 chain-of-thought를 canonical proof로 저장하지 않는다.

### 11.2 Inductive Engine

입력:
dependency-adjusted `(condition, intervention/exposure, outcome)` tuples

절차:
- dataset family collapse
- method strata
- effect measure compatibility
- 방향·크기·불확실성
- heterogeneity
- moderator candidates
- coverage zeros

정량적으로 비교 가능할 때만 meta-analysis module. 그렇지 않으면 qualitative synthesis.

### 11.3 Abductive Engine

입력:
contradiction set 또는 하나의 observation을 설명하는 경쟁 mechanism

목표:
- 모든 observation을 설명
- 추가 가정 최소
- 알려진 mechanism과 양립
- 서로 구분 가능한 prediction 생성

한 설명을 “최선”으로 고정하기보다 최소 두 개 대안을 유지한다. 정보이득이 큰 판별 실험을 후속으로 보낸다.

### 11.4 Causal Engine

모든 causal hypothesis에 DAG와 Assumption Ledger를 요구한다.

검사:
- temporal order
- confounders
- mediator/collider
- intervention/natural experiment
- measurement error
- selection
- identifiability
- transportability

판정:
- `IDENTIFIED`
- `ASSUMPTION_DEPENDENT`
- `NOT_IDENTIFIED`
- `NOT_APPLICABLE`

문헌상 지지를 causal identification과 동일시하지 않는다.

## 12. Asymmetric Evidence Parliament

정식 DAG는 `workflows/insight_deliberation.workflow.yaml`.

### 12.1 기본 역할

#### Defender
지지/기전 evidence만 보고 **가장 좁고 강한** 방어 명제를 만든다. 넓히는 것이 아니라 살아남는 범위를 찾는다.

#### Prosecutor
counter/null/failed replication만 우선 보고 하나의 결정적 반례, 역인과, 공통원인, scope reduction을 찾는다. generic skepticism은 실패다.

#### Method Auditor — Veto
측정법과 설계가 목표 claim을 지탱할 수 있는지 판단한다. veto는 evidence를 삭제하지 않고 허용 가능한 promotion을 낮춘다.

예:
- self-report scale: 해당 설문 문항이 정의한 construct의 관측은 가능
- 객관적 행동 또는 장기 성과의 직접 입증: 별도 타당화 없이는 불가
- computational result: formal or mechanistic compatibility는 가능
- empirical confirmation: 별도 관측·실험 증거 없이는 불가

#### Scope Auditor
population/entity/unit of analysis/lifecycle stage/setting/intervention intensity/duration/method/scale 외삽을 감사한다.

#### Inductivist
조건–결과 tuple을 dependency-adjusted로 집계하고 효과 방향, 이질성, 관측되지 않은 범위를 분리한다. 관측된 scope 밖의 일반화를 금지한다.

#### Deductivist
명시적 전제·규칙·보존 법칙에서 scoped prediction이 실제로 따라오는지 proof trace를 만든다. 숨은 전제와 끊긴 edge는 연구 공백으로 남긴다.

#### Causal Auditor
target effect, confounder, mediator, collider, proxy, 시간 순서를 DAG로 감사하고 `IDENTIFIED / ASSUMPTION_DEPENDENT / NOT_IDENTIFIED`를 분리한다.

#### Judge
gate를 통과한 material만 사용해 orthogonal verdict를 작성한다. 투표 수를 세지 않는다.

### 12.2 조건부·후속 역할

- Abductive Mediator: contradiction 또는 미설명 이질성이 있는 경우
- Novelty Examiner: novelty status를 `NOT_ASSESSED`보다 높게 요청하는 모든 run
- Statistician: 정량 effect synthesis가 가능한 경우
- Execution Verifier: configured ValidationTarget으로 검증 가능할 때
- Independent Attestor: 모든 promotion run에 필수

표준 workflow는 Inductivist, Deductivist, Causal Auditor를 포함한다. MVP profile은 사전 선언된 축소 workflow를 사용할 수 있지만, 실행 뒤 임의로 불리한 역할을 제거하지 않는다.

### 12.3 Evidence ACL

Blind Round에서 역할별 context가 다르다.

| 역할 | 볼 수 있음 | 숨김 |
|---|---|---|
| Defender | support, mechanism, selected boundaries | Prosecutor brief, counter lane |
| Prosecutor | counter, null, failed replication | Defender brief, support lane |
| Method | cited claims, methods, design, quantitative context | 타 역할 rhetoric |
| Scope | ScopeVector, condition tables, target statement | 타 역할 rhetoric |
| Inductivist | support/null/boundary tuples, dependency clusters | Defender/Prosecutor prose |
| Deductivist | accepted theory/mechanism premises, predictions | 타 역할 결론 |
| Causal Auditor | cited evidence, method context, target effect | 타 역할 rhetoric |
| Novelty Examiner | novelty lane, prior-art candidates, search scope/date | 지지·반박 투표와 Judge 결론 |
| Judge | blind brief 이후 full structured pack | 없음 |
| Attestor | evidence pack, gates, argument graph, proposed verdict | debate prose/transcript |

`ContextAssemblyManifest`가 실제 포함·제외 evidence와 query/model/prompt version을 기록한다.

### 12.4 비대칭 손실함수

- Defender: 근거보다 넓은 주장을 하면 큰 손실
- Prosecutor: 강한 반증을 놓치면 큰 손실
- Method Auditor: construct invalidity를 놓치면 veto failure
- Scope Auditor: 외삽을 허용하면 큰 손실
- Inductivist: dependency와 이질성을 무시한 일반화에 큰 손실
- Deductivist: 숨은 전제 또는 non sequitur를 놓치면 큰 손실
- Causal Auditor: association을 identification으로 승격하면 큰 손실
- Novelty Examiner: bounded not-found를 absolute novelty로 표현하면 큰 손실
- Judge: false promotion과 unjustified certainty를 최소화
- Attestor: rhetorical anchoring을 제거하고 구조만 재검증

같은 prompt를 여러 모델에 복제하는 것은 diversity가 아니다.

### 12.5 프로토콜

#### Round 0 — Immutable RunSpec
가설 revision, corpus snapshot, ontology, workflow, model policy, capability, budget를 hash.

#### Round 1 — Retrieval and Reconciliation
다중 lane을 병렬 실행. lane 실패는 숨기지 않는다.

#### Round 2 — Blind Briefs
Defender/Prosecutor/Method/Scope/Inductivist/Deductivist/Causal Auditor/Novelty Examiner가 서로의 문장을 보지 않는다.

#### Round 3 — Typed Cross-Examination
공격은 다음 유형 중 하나:
`premise, evidence, scope, method, causal, alternative_explanation`

각 공격은 target ID와 Evidence IDs를 가진다.

#### Round 4 — Falsification
null, reverse causation, common cause, artifact, selection, publication bias, boundary를 의무 점검.

#### Round 5 — Abductive Mediation
진짜 모순 또는 미설명 variation에서 경쟁 설명과 판별 실험을 만든다.

#### Round 6 — Minority Report
다수/판사와 다른 가장 강한 grounded position을 보존한다.

#### Round 7 — Deterministic Gates
코드가 promotion eligibility를 판정한다.

#### Round 8 — Judge
판정문은 fixed schema.

#### Round 9 — Independent Attestation
debate prose를 제거한 package로 재검증.

#### Round 10 — Passport
새 revision을 발행하고 next action을 연결한다.

### 12.6 결정론적 Gate

| Gate | 실패 시 |
|---|---|
| G0 schema valid | BLOCK |
| G1 source provenance complete | BLOCK |
| G2 atomicity/scope normalized | BLOCK 또는 Inbox |
| G3 dependency clusters resolved | BLOCK promotion |
| G4 counter/null search executed | BLOCK |
| G5 method compatibility | veto 또는 scope narrowing |
| G6 inference-mode contract | causal/mechanistic overclaim 차단 |
| G7 strongest counter + minority preserved | BLOCK |
| G8 novelty search scope recorded | novelty status 제한 |
| G9 validation execution contract | execution-based promotion 제한 |
| G10 independent attestation | BLOCK |

Human waiver는 가능하나 `authority, reason, scope, timestamp`가 있어야 하며 evidence를 삭제하지 않는다.

### 12.7 최종 판정은 다축

#### Epistemic
`ENTAILED, SUPPORTED, CONDITIONAL, MIXED, CONTRADICTED, UNDERDETERMINED, UNTESTABLE`

#### Causal
`IDENTIFIED, ASSUMPTION_DEPENDENT, NOT_IDENTIFIED, NOT_APPLICABLE`

#### Novelty
`PRIOR_ART_FOUND, CORPUS_NOVEL, NOT_FOUND_WITHIN_SEARCH_SCOPE, NOT_ASSESSED`

#### Promotion
`INBOX, CANDIDATE, LITERATURE_GROUNDED, SIMULATION_SCREENED, EMPIRICALLY_TESTED, REPLICATED`

`SUPPORTED`이면서 `NOT_IDENTIFIED`일 수 있고, `NOT_FOUND_WITHIN_SEARCH_SCOPE`는 “세계 최초”가 아니다.

---

## 13. Hypothesis Passport

정식 스키마: `schemas/hypothesis-passport.schema.json`.

Passport에는 반드시 다음이 있다.

- canonical statement and revision
- exact scope
- reasoning modes
- mechanism chain
- predictions and falsifiers
- Evidence Pack
- strongest counterevidence
- unresolved objections
- epistemic/causal/novelty/promotion status
- quality/confidence vector
- minority report
- next ExperimentTicket
- run, attestation, provenance manifest

Passport는 덮어쓰지 않는다. 새 evidence, DomainPack, ValidationTarget, 실행 결과, human decision은 새 revision을 만든다.

### 13.1 올바른 문장 예

- “해당 corpus snapshot과 검색 범위 안에서, 총 학습시간이 일치한 성인 학습자에게 분산 인출연습의 지연회상 이점은 조건부로 지지된다.”
- “관찰 자료만으로 인출연습 자체의 인과효과를 식별한다는 판정은 선택과 기대효과 교란 때문에 `NOT_IDENTIFIED`다.”
- “한 달 이상·기관 수준 직접 증거는 검색 범위에서 발견되지 않았으며 가장 중요한 coverage gap이다.”
- “선행 문헌은 기록된 검색 범위에서 발견되지 않았으나 전역 novelty를 확정하지 않는다.”

### 13.2 금지 문장

- “12편이 지지하므로 증명되었다.”
- “반박 논문이 검색되지 않아 참이다.”
- “분석 파이프라인이 재현했으므로 현실의 원인이 확인되었다.”
- “두 모델 제공자가 모두 동의했다.”
- “현재 corpus에서 처음이므로 세계 최초다.”

## 14. 범용 검증·실행 폐루프

정식 DAG: `workflows/validation_execution.workflow.yaml`.

Core는 특정 모델, 장비, 변수명, 방정식, 데이터 포맷을 알지 않는다. 문헌 심의를 통과한 Passport를 외부 검증 수단과 연결하려면 `ValidationTargetManifest`와 `ValidationPlan`을 사용한다.

지원 target 유형:

- `simulation_model`
- `analysis_pipeline`
- `formal_solver`
- `benchmark_harness`
- `experimental_platform`
- `external_service`
- `custom`

외부 target이 없어도 문헌 검색·의회·Passport까지의 core는 정상 작동한다. 이 상태는 `TARGET_NOT_CONFIGURED`이며 실패나 가짜 완료가 아니다.

### 14.1 Eligibility

Passport를 target으로 보내기 전 다음을 검사한다.

- target manifest와 version이 고정되었는가
- hypothesis variable과 target input/output의 mapping이 명시되는가
- state/parameter/control/intervention/input/output 역할이 구분되는가
- 필요한 action이 target의 `supported_actions`에 존재하는가
- type, unit, representation, schema가 호환되는가
- 관측가능한 output과 사전등록 metric이 존재하는가
- 식별 가능성·표현 가능성·유효범위 경고가 기록되는가
- capability, safety class, approval policy를 만족하는가
- target artifact hash와 environment가 고정되는가

가능한 상태:

`DIRECTLY_EXPRESSIBLE, PROXY_EXPRESSIBLE, PARTIALLY_EXPRESSIBLE, NOT_EXPRESSIBLE, UNIDENTIFIABLE, OUT_OF_DOMAIN, TARGET_NOT_CONFIGURED`

표현할 수 없으면 억지 mapping을 만들지 않는다. 이는 `MODEL_NOT_EXPRESSIVE` 같은 특정 구현명이 아니라 일반적인 검증 공백이다.

### 14.2 ValidationPlan

정식 스키마: `schemas/validation-plan.schema.json`.

```yaml
plan_id:
hypothesis_id:
target_id:
target_version:
objective:
variable_mapping:
mechanism_mapping:
baseline:
actions:
scenario_matrix:
inputs:
controlled_conditions:
observables:
metrics:
falsification_rule:
assumptions:
identifiability_warnings:
random_seed:
environment_digest:
resource_limits:
approval_required:
provenance_manifest_id:
```

LLM은 plan 후보를 작성할 수 있지만 canonical target code, configuration, parameter, instrument setting을 직접 변경하거나 누락값을 발명하지 않는다.

### 14.3 실행

1. schema와 interface validation
2. input hash와 target artifact hash 확인
3. type/unit/representation 검사
4. capability·safety·approval gate
5. baseline 또는 dry-run
6. sandboxed/controlled execution
7. expected action·scenario count 대조
8. EffectReceipt와 side-effect receipt
9. uncertainty·sensitivity·failure retention
10. registered metric과 falsifier 판정
11. result subtype과 validity domain 기록

### 14.4 증거 반환

실행 결과는 원래 subtype을 유지한다.

- modeling evidence
- computed analysis
- formal derivation
- benchmark execution
- external-system observation
- prospective empirical measurement

비실증 결과를 empirical confirmation으로 승격하지 않는다. 실측 또는 실제 운영 관측이 들어오면 raw artifact hash, preprocessing, inclusion/exclusion, data slice, analysis code, result, limitation을 X-Graph에 기록하고 E-Graph에 새 EvidenceNode revision으로 projection한다.

### 14.5 다음 판별 테스트

ExperimentTicket은 “가설을 지지할 실험”이 아니라 competing hypotheses를 가장 싸고 예리하게 구분하는 다음 행동이다.

평가 vector:

- expected information gain
- existing-data feasibility
- construct and measurement validity
- cost/time
- safety and authorization burden
- research-program contribution
- risk of ambiguous outcome
- reversibility and reproducibility

---

## 15. Foundry Kernel: provider-neutral 그래프 런타임

### 15.1 책임 경계

Kernel이 소유:
- RunSpec
- canonical state and reducer
- workflow compilation
- schema/gates
- capability policy
- secrets and approvals
- event/effect ledger
- retries/idempotency
- checkpoints/replay
- model routing policy
- observability

Provider adapter가 소유:
- model request/response translation
- tool invocation envelope
- provider trace link
- provider-specific session/subagent/worktree lifecycle

Provider SDK가 DB state, approval truth, final verdict를 소유하면 안 된다.

### 15.2 RunSpec

정식 스키마: `schemas/run-spec.schema.json`.

고정할 것:
- run type
- input artifact IDs
- corpus snapshot hash
- ontology version
- workflow ID/version
- model policy version
- capabilities
- token/cost/time/concurrency budget
- approval policy
- run hash

Run 중 핵심 hypothesis가 바뀌면 새 revision/run을 만든다.

### 15.3 NodeContract

각 node는:
- one job
- explicit input schema
- explicit output schema
- dependencies
- read/write scope
- capabilities
- model tier
- timeout/retry/failure policy
- acceptance checks

를 가진다. free-form “알아서 조사” node는 금지한다.

### 15.4 EdgeContract

Edge는 순서가 아니라 data/resource dependency다.

필드:
- producer/consumer
- artifact schema/version
- transform
- cardinality
- completeness requirement
- barrier/stream semantics
- confidentiality label
- shared-resource lease
- failure propagation

`A 다음 B`라는 서술만으로 edge를 만들지 않는다. B가 A output을 읽거나, 동일 mutable resource를 공유하거나, rate limit/authority lease를 공유할 때 edge가 있다.

### 15.5 DAG topology

#### Fan-out
- PDF per-document
- retrieval lanes
- role briefs
- evaluation cases

#### Pipeline
item마다 다음 단계가 독립적인 경우:
`parse → candidate → normalize → verify`

#### Barrier
전체 set이 필요한 경우만:
- cross-document dedupe
- dependency clustering
- evidence reconciliation
- council synthesis
- integration gate

#### Layered fan-in
수백/수천 raw output을 한 model context에 넣지 않는다.

`item outputs → deterministic reduction → batch summary/subgraph → final synthesis`

### 15.6 Completeness

fan-in은:
- expected node IDs
- received
- failed
- timed out
- skipped with reason
- schema invalid

을 비교한다. 일부만 왔는데 완성 보고서를 만들 수 없다.

### 15.7 실패와 재시도

- retry는 idempotency key 필수
- write node는 lease/fencing token
- transient/provider error와 semantic failure 분리
- max attempts
- retry budget
- fallback model은 새 Attempt와 model ID 기록
- partial output은 `PARTIAL`, complete로 승격 금지

### 15.8 Bounded cycles

과학적 탐색에는 cycle이 필요하지만 종료 조건을 코드로 고정한다.

예:
- 두 번 연속 fresh contradiction 없음
- marginal coverage gain < threshold
- expected information gain < threshold
- max rounds
- token/cost/time budget
- repeated candidate hash

dedupe는 accepted item만이 아니라 **모든 seen item** 기준이다.

### 15.9 Event/effect sourcing

이벤트 예:
- `RunCreated`
- `NodeScheduled`
- `AttemptStarted`
- `ArtifactProduced`
- `GateEvaluated`
- `ApprovalGranted`
- `EffectAttempted`
- `EffectReceipted`
- `RunPaused/Completed`

외부 side effect:
`ActionIntent → exact hash approval → Attempt → EffectReceipt → ReconciliationRecord`

읽기·분석과 DB canonical write를 분리한다.

### 15.10 Checkpoint and replay

Checkpoint:
- reducer state hash
- completed node map
- artifact hashes
- leases
- model/search/corpus versions
- unresolved failures

Replay levels:
1. reducer-only exact replay
2. artifact replay without new model calls
3. full re-execution pinned environment
4. comparative replay with new model/search version

“같은 LLM 문장”이 아니라 reducer state와 evidence links의 동등성이 핵심이다.

---

## 21. 평가·검증 체계

### 21.1 Gold set

초기:
- 50편
- 최소 200 atomic claims
- source span, scope, method, result, hedge, evidence layer 수작업 라벨
- 인사이트 30개: 참/조건부/거짓/판정불가 균형
- 그중 최소 10개는 거짓 또는 과도한 일반화
- contradiction pairs와 non-contradiction scope pairs 포함
- shared dataset/preprint-journal/review-primary 중복 포함

Gold annotation은 2인 독립 + adjudication을 권장한다. 단일 annotator의 직관을 ground truth로 고정하지 않는다.

### 21.2 Parser metrics

- section boundary F1
- reading-order accuracy
- caption linkage accuracy
- table extraction cell accuracy
- formula preservation
- page/bbox locator accuracy
- reference resolution
- scanned/low-quality failure recall

### 21.3 Claim/Evidence metrics

- claim identification precision/recall/F1
- atomicity violation rate
- span grounding precision/recall
- claim–span entailment
- ScopeVector field accuracy
- direction/magnitude/unit accuracy
- method-construct compatibility accuracy
- hedge preservation
- unsupported extraction rate
- review-introduction leakage rate

### 21.4 Retrieval metrics

각 lane과 통합 결과에 대해:
- Recall@5/20/50
- nDCG
- direct counterevidence recall
- null-result recall
- boundary-condition recall
- method evidence recall
- independent-source diversity
- dependency-adjusted recall
- unsearched-vs-none-found classification

### 21.5 Reasoning/Council metrics

- verdict accuracy
- false-support rate
- false-contradiction rate
- scope overgeneralization
- causal overclaim rate
- deductive proof validity
- missing-premise detection
- moderator resolution precision
- alternative-explanation coverage
- falsifier discriminativeness
- minority-correct preservation
- method-veto precision/recall
- calibration/Brier/ECE
- expert agreement and disagreement reason

### 21.6 System metrics

- run completion and expected/actual node reconciliation
- retry count
- duplicate effect rate
- strict replay equality
- semantic replay drift
- cost per accepted passport
- latency per workflow layer
- context tokens per role
- cache hit rate
- human review minutes
- silent node loss = 반드시 0
- provenance completeness = release gate에서 100%

### 21.7 필수 ablation

1. paper-level RAG vs claim/evidence
2. vector-only vs multi-lane retrieval
3. condition-unaware vs condition-aware contradiction
4. independent blind briefs 유/무
5. prosecutor 유/무
6. method auditor veto 유/무
7. majority vote vs deterministic gate
8. dependency clustering 유/무
9. compact Evidence Pack vs full context
10. single-model replicas vs heterogeneous roles
11. literature-only vs generic validation-target screen
12. hard-coded domain fields vs DomainPack specialization
13. 3-agent MVP vs 7-role standard profile

### 21.8 Time-sliced backtest

cutoff date 이전 corpus만 사용해 이후 연구의:
- 방향
- boundary condition
- moderator
- failure
- 아직 미검증

을 예측한다. 미래 논문도 절대적 진실이 아니라 출판된 후속 증거로 취급한다. publication bias와 corpus shift를 함께 보고한다.

### 21.9 Release gates

#### MVP-50

- promoted Claim source-span validity ≥ 0.95
- unsupported promoted claim rate ≤ 0.02
- known-false rejection rate ≥ 0.80
- expected/actual node mismatch detection = 1.00
- replay reducer equivalence = 1.00
- counter/null lane 실행률 100%

#### Pilot-200

- promoted Claim source-span validity ≥ 0.97
- unsupported promoted claim rate ≤ 0.015
- counterevidence Recall@20 ≥ 0.80
- known-false rejection rate ≥ 0.85
- method-veto fixture accuracy = 1.00
- contradiction classifier가 scope-difference를 분리
- dependency clustering과 비용/지연 budget 검증

#### Production-2000

- promoted Claim source-span validity ≥ 0.98
- unsupported promoted claim rate ≤ 0.01
- known-false rejection rate ≥ 0.90
- run manifest completeness = 1.00
- silent partial completion = 0
- backup/restore success = 1.00
- 증분 ingest, correction/retraction propagation, scale/chaos/recovery, privacy/license, rollback runbook 통과

정확한 threshold는 gold annotation 완료 후 `acceptance_matrix.yaml`에 고정하며, 결과를 본 뒤 낮추는 변경은 새 version과 근거가 필요하다.

---

## 26. 범용 검증·실행 폐루프 상세

### 26.1 입력 Hypothesis

예:

> 총 학습시간과 피드백을 일치시킨 성인 학습자에서 분산 인출연습은 재독보다 14일 지연회상을 향상시키며, 그 차이는 단순 노출량이 아니라 인출에 의한 기억 재활성화로 설명된다.

등록 시:

- domain: learning science
- population: adult learners
- unit of analysis: individual
- setting: controlled course-based study
- intervention: spaced retrieval practice
- comparator: matched-time rereading
- temporal scale: 14-day delayed outcome
- mechanism: effortful retrieval → trace reactivation → consolidation → delayed recall
- falsifier: independent preregistered contrast가 실용적 최소효과보다 작고 그 임계값을 신뢰구간이 배제

이 예시는 core 기본 도메인이 아니다. `DomainPack`과 `ValidationTarget`을 교체하면 동일한 계약이 다른 연구 분야에 적용된다.

### 26.2 Evidence/R-Graph 분해

- H1: matched study time 조건에서 intervention → delayed recall
- H2: immediate보다 delayed outcome에서 효과가 커진다
- H3: feedback/expectancy가 아니라 retrieval-specific mediator가 필요하다
- H4: population, material, interval이 moderator다

각 H는 독립 falsifier와 Evidence Pack을 가진다. 전체 서사를 한 문장으로 판정하지 않는다.

### 26.3 ValidationTargetManifest

정식 스키마: `schemas/validation-target-manifest.schema.json`.

```yaml
target_id: delayed_recall_pipeline
version: pinned-version
target_type: analysis_pipeline
interface_version: efoundry-validation-target-v1
entrypoint:
inputs:
  - id: baseline_score
    data_type: number
    unit: score
  - id: treatment_group
    data_type: category
    unit: null
  - id: delayed_recall_score
    data_type: number
    unit: score
outputs:
  - id: adjusted_effect
    data_type: number
    unit: standardized_difference
parameters: []
state_variables: []
constraints:
supported_actions:
  - validate_input
  - fit_preregistered_model
  - run_holdout_analysis
validation_scope:
identifiability_notes:
capability_requirements:
safety_class: bounded_compute
approval_policy: none
artifact_hashes:
```

Adapter는 hard-coded variable name을 추측하지 않는다. mapping이 불가능하면 target 또는 data contract의 공백으로 남긴다.

### 26.4 Eligibility screen

분류:

- `DIRECTLY_EXPRESSIBLE`
- `PROXY_EXPRESSIBLE`
- `PARTIALLY_EXPRESSIBLE`
- `NOT_EXPRESSIBLE`
- `UNIDENTIFIABLE`
- `OUT_OF_DOMAIN`
- `TARGET_NOT_CONFIGURED`

표현할 수 없거나 식별되지 않는 메커니즘을 억지 parameter, proxy, outcome으로 만들지 않는다.

### 26.5 ValidationPlan

필수:

- target id/version/hash
- hypothesis and variable mapping
- baseline and comparator
- allowed actions
- scenario or test matrix
- controlled conditions
- input artifact hashes
- expected outputs
- preregistered metrics
- falsification rule
- assumptions and identifiability warnings
- seed when stochastic
- environment/container digest
- timeout/resource limit
- approval requirement

### 26.6 결과 판정

가능한 결과:

- `TARGET_INCONSISTENT_WITH_HYPOTHESIS`
- `TARGET_COMPATIBLE_NOT_CONFIRMED`
- `DISCRIMINATES_ALTERNATIVES`
- `NON_IDENTIFIABLE`
- `OUT_OF_DOMAIN`
- `TARGET_NOT_CONFIGURED`
- `EXECUTION_INVALID`

계산·형식검증·벤치마크·simulation의 성공이 현실의 사실 확인을 의미하지 않는다. 실행은 선별, 반증 압축, 재현성 점검을 위한 별도 증거다.

### 26.7 실측·실행 feedback

새 결과는:

1. target, action, method, input, outcome으로 등록
2. 결과 subtype에 맞는 EvidenceNode 생성
3. code, environment, data slice, target hash 연결
4. 사전등록 prediction/falsifier와 비교
5. 기존 Passport의 새 revision 생성
6. conflicting evidence이면 재의회
7. empirical 여부를 provenance에 따라 별도 판정

원문 문헌, 계산 결과, 형식적 산출물, 벤치마크, 사용자 실험을 같은 provenance layer로 섞지 않는다.

---

## 27. 실패 모드와 대응

| 실패 모드 | 탐지 | 대응 |
|---|---|---|
| span 없는 claim | schema/gate | reject |
| Discussion 추측이 result로 승격 | section/hedge audit | evidence layer 강등 |
| 조건 차이를 모순으로 판정 | ScopeOverlap | moderator queue |
| 동일 데이터 5편을 5증거로 계산 | dependency cluster | effective independence 조정 |
| vector 검색이 지지문헌만 회수 | lane coverage | counter/null mandatory |
| self-report 또는 간접 proxy로 객관적 행동·성과 메커니즘을 직접 입증 | method compatibility | veto |
| 의회가 유창한 합의로 수렴 | blind/asymmetric roles | minority + deterministic gate |
| 한 node 실패가 숨음 | expected/actual receipts | incomplete run |
| parallel write 충돌 | resource graph/worktree | serialize or isolate |
| retry가 duplicate side effect 생성 | idempotency/receipt | reconcile |
| 모델/프롬프트 drift | manifest/replay | re-eval |
| 2,000편 재처리 비용 폭증 | content hash/delta | incremental tiers |
| corpus 안에서만 novelty | external lane | bounded novelty statement |
| 모델링이 truth로 오인 | X-Graph label | compatible ≠ confirmed |
| 화려한 UI가 누락을 숨김 | coverage-first UI | unsearched explicit |
| 출판편향 | verdict disclaimer | “published evidence” scope |

### 27.1 운영상 SLO 초안

MVP에서 수치 고정 전 측정:
- canonical write durability
- ingest throughput
- council run completion
- source viewer availability
- p95 API latency
- recovery point/recovery time
- artifact verification failure
- external provider failure rate

정확한 SLO는 F06/F08 benchmark 후 freeze한다. 근거 없는 “99.99%”를 명세하지 않는다.

### 27.2 복구

- durable queue/event log
- checkpoint resume
- effect reconciliation
- object-store checksum scan
- DB backup + point-in-time recovery
- workflow version pin
- provider failure fallback
- quarantine for corrupt documents
- migration rollback/forward fix policy
- disaster-recovery drill artifact

---

## 28. 명시적 비목표

v1에서 하지 않는다.

- 자유 채팅형 “에이전트 회의실”
- 다수결을 truth gate로 사용
- 매 질의마다 전체 2,000편 long-context 입력
- vector-only retrieval
- citation count/journal prestige 기반 단일 evidence score
- span 없는 knowledge graph edge
- 완성 온톨로지를 기다린 뒤 시작
- Neo4j/RDF/vector DB를 동시에 canonical로 운영
- GNN/fine-tuning 우선 도입
- 자동 hypothesis 개수로 성능 주장
- 문헌 지지를 “증명 완료”로 표현
- agent 수를 throughput/quality의 대리변수로 사용
- 1,000 agent scale을 MVP 요구사항으로 사용
- 승인 없는 자동 실험·외부 서비스 mutation
- configured ValidationTarget에 없는 mechanism·action·parameter를 임의 구현
- human override를 흔적 없이 허용

---

## 30. Definition of Done

제품 v1은 다음이 모두 참일 때만 완료다.

- 50/200/2000 gate 중 선언한 target을 충족
- 모든 Passport가 원문 source span으로 역추적 가능
- counter/null/method/boundary lane 상태가 명시
- dependency-adjusted evidence count
- `UNDERDETERMINED`와 `UNTESTABLE`이 정상 동작
- method veto와 minority report 보존
- workflow expected node completeness
- strict replay 또는 설명된 drift
- validation-run provenance와 reconciliation
- security/injection tests
- backup/restore drill
- API/CLI schema compatibility
- 사용자 UI에서 원문 확인 가능
- known-false evaluation 공개
- 비용·지연·오류 budget 보고
- 미검증·미구현 항목을 완료로 표시하지 않음

---

## 35. Claim·Evidence·Passport lifecycle

고영향·저신뢰 Claim은 인간 검토 큐와 active learning 큐로 보낸다.

### 35.1 상태 모델

Claim, Evidence, Passport는 mutable row 하나가 아니라 immutable revision과 lifecycle event의 조합이다.

```text
DRAFT → GROUNDED → REVIEWED → PROMOTED
   ↘ REJECTED
PROMOTED → STALE → SUPERSEDED
PROMOTED → INVALIDATED
```

- `STALE`은 삭제가 아니라 현행 사용 금지 신호다.
- correction은 영향을 받은 필드와 descendants를 계산한다.
- retraction은 문서 전체를 지우지 않고 evidence validity와 모든 downstream current projection을 재평가한다.
- 새 정책·온톨로지·스키마도 동일한 impact graph를 사용한다.
- 사람의 override 역시 원래 판정과 함께 revision chain에 남는다.

### 35.2 targeted reassessment

`evidence_update_reassessment.workflow.yaml`은 update를 감지하고 다음 순서로 최소 재계산한다.

```text
detect → impact report → mark stale → reassessment plan
→ affected ingest → affected claims → affected retrieval
→ affected Parliament → decision delta → supersession → notification
```

재심은 이전 verdict를 수정하지 않고 새 adjudication과 Passport revision을 만든다.

## 36. 검색 완전성·부재·신규성 계약

### 36.1 세 상태

```text
UNSEARCHED
SEARCHED_NONE
SEARCHED_WITH_RESULTS
```

`SEARCHED_NONE`은 특정 query, source, index version, date, cutoff, scope에서 결과가 없었다는 뜻일 뿐 존재하지 않는다는 증명이 아니다.

### 36.2 SearchLaneReceipt

각 lane은 결과가 0이어도 receipt를 남긴다.

- query text/hash와 relation direction
- scope filters
- corpus and index snapshots
- result and exclusion IDs
- stop reason
- errors/outages
- start/finish time
- receipt hash

부재·신규성 문장은 RetrievalRun의 completeness certificate를 넘을 수 없다. novelty examiner는 “검색 범위 내에서 선행 직접 일치를 찾지 못함”보다 강한 표현을 쓰지 않는다.

## 37. hostile-document threat model

### 37.1 신뢰 경계

다음은 모두 untrusted input이다.

- PDF와 supplementary file의 본문·메타데이터·주석·embedded prompt
- 웹 검색 snippet과 tool output
- prior-agent text와 imported graph
- 외부 모델·벤치마크·서비스 결과

SourceIntegrityReport는 malformed structure, active content, archive bomb, suspicious link, instruction-like text, data exfiltration pattern을 기록한다. 원문은 보존하되 실행하지 않고, quarantine 또는 제한된 parser profile로 격리한다.

### 37.2 컨텍스트 격리

ContextAssemblyManifest는 source trust label, injection scan, redaction policy, ordering, included/excluded Evidence IDs, token accounting, context hash를 기록한다. Corpus text가 tool 권한·system instruction·policy·output schema를 바꾸는 경로는 P0 취약점이다.

## 38. 인간 거버넌스·승인·appeal

사람은 최종 책임을 가질 수 있지만 provenance를 지울 수 없다.

HumanDecision은 다음을 필수로 한다.

- authority identity와 role
- decision type와 exact subject
- rationale와 evidence artifacts
- scope, expiry, affected artifacts
- superseded decision
- machine result non-mutation acknowledgement
- decision hash

고위험 실험·민감 데이터·외부 부작용·정책 면제는 ApprovalRecord가 필요하다. appeal은 overwrite가 아니라 새 decision revision이다. 이해상충, quorum, separation of duties, emergency revocation은 PolicyBundle에서 versioning한다.

## 39. schema·policy·prompt evolution

Breaking change는 코드보다 먼저 SchemaMigration을 요구한다.

```text
proposal
→ compatibility classification
→ fixtures and transform
→ reverse transform or explicit irreversible approval
→ dry run on snapshot
→ independent review
→ migration event
→ projection rebuild
```

Schema, prompt, policy, ontology, DomainPack, model routing은 서로 독립된 version과 hash를 갖는다. Model alias는 운영 편의일 수 있으나 reproducible run에는 resolved identifier를 저장한다.

## 40. calibration·stability·evaluation

### 40.1 정확도만으로는 부족하다

평가는 다음을 분리한다.

- parser and source locator quality
- claim atomicity, stance, scope, grounding
- support/counter/null/boundary/method retrieval
- dependency correction and coverage
- verdict accuracy and causal overclaim
- known-false rejection
- abstention quality
- Brier score, ECE, confidence-vector calibration
- decision stability under evidence ordering, role omission, dependency removal, cutoff and provider variation
- prompt-injection escape and citation laundering
- time-sliced backtest and leakage audit
- recovery, replay, accessibility, latency, cost

### 40.2 평가 계층

`SPEC_BUNDLE`은 명세 정합성만 뜻한다. `MVP_50`, `PILOT_200`, `PRODUCTION_2000`은 각각 별도의 실측 gate다. 낮은 레벨 PASS를 상위 레벨 readiness로 표현하지 않는다.

## 41. release·supply-chain assurance

Release는 다음 독립 증거를 요구한다.

1. frozen evaluation snapshot
2. schema/example meta-validation
3. workflow/node/resource DAG validation
4. 216-lens plugin audit
5. gold, adversarial, temporal, ablation, calibration 결과
6. secret/license/dependency scan
7. SBOM and build provenance
8. independent release attestation
9. final-byte `PACKAGE_MANIFEST.json`
10. ZIP SHA-256, CRC, duplicate-entry, extraction, per-file hash 검증

서명 키가 없는 개발 환경에서는 `SIGNING_NOT_CONFIGURED`를 조건으로 남기며 서명 완료로 가장하지 않는다.

# Part VI — State, memory, mapping and context

# State, memory, mapping and context architecture

## 1. Canonical state

Chat history is navigation; canonical artifacts and ledger events are evidence.

Local layout:

```text
.epistemic-foundry/
├── foundry.db                  # SQLite WAL canonical local state
├── artifacts/sha256/           # immutable content-addressed objects
├── exports/                    # portable .efpack bundles
├── backups/
├── policy/
├── domain-packs/
├── skill-vault/
├── logs/                       # redacted operational logs
└── cache/                      # disposable indexes and parser caches
```

The installed plugin writes only to `PLUGIN_DATA`. Workspace authority lives in `.epistemic-foundry/`, selected explicitly and recorded in `PluginInstallState`.

## 2. Event and effect model

State changes are produced by a deterministic reducer over append-only events. External side effects use:

```text
ActionIntent
→ policy and approval
→ CapabilityLease with fencing token
→ Attempt
→ external effect
→ EffectReceipt
→ reconciliation
→ committed event
```

On restart, unresolved intents are classified as not-started, in-flight, succeeded-uncommitted, failed, or unknown. Unknown effects are never retried blindly.

## 3. Memory

The recall subsystem is a retrieval adapter over policy-governed memory records, not an automatic prompt dump.

Before retrieval:

- detect explicit or implicit recall intent;
- identify workspace and purpose;
- verify consent and retention;
- select permitted stores;
- build a query plan.

After retrieval:

- redact;
- score provenance and relevance separately;
- deduplicate;
- emit `MemoryRetrievalReceipt`;
- place only selected artifact IDs/summaries in a ContextCapsule.

The plugin asks the user only when the missing fact is genuinely unavailable from permitted state.

## 4. Context Capsule

A ContextCapsule contains:

- session and phase cursor;
- governing RunSpec/policy hashes;
- active Insight/Hypothesis revisions;
- selected artifact IDs and bounded summaries;
- open blockers and unresolved objections;
- allowed tools and leases;
- exclusions and unavailable sources;
- token budget;
- source and summary hashes.

Post-compaction reinjection reconstructs the capsule from canonical state. It never reuses the prior capsule without checking freshness.

## 5. Workspace Cartographer

Graph layers:

- code symbols/imports;
- schemas and schema references;
- workflows and dependencies;
- work packages/write scopes;
- papers/citations/datasets;
- SourceSpans/Claims/Evidence;
- artifacts/provenance;
- skills/hooks/MCP tools;
- tests and coverage;
- decisions and stale propagation.

Ranking:

1. baseline structural centrality is always real, never uniform placeholder ranking;
2. query-specific personalization is a separate score;
3. risk/blast radius and semantic relevance are separate dimensions;
4. generated/vendor/test files are classified, not silently mixed;
5. ranking algorithm, inputs and exclusions are recorded in `WorkspaceMapSnapshot`.

Outputs:

- global map;
- query-focused map;
- change-impact map;
- research coverage map;
- authority/dependency map;
- orphan/dead-contract report.

## 6. Cache and index semantics

Caches are disposable projections. They include parser output, embeddings, lexical index, graph projections, UI read models, and map rankings. Every cache key includes source hash, schema/ontology version, parser/model version, and configuration hash. Deleting cache must not delete canonical evidence.


# Part VII — Security, privacy and supply chain

# Plugin security, privacy and supply-chain threat model

## 1. Trust zones

1. **Host instruction plane** — system/developer/user instructions and managed policy.
2. **Plugin control plane** — manifest, signed distribution, hook gateway, kernel policy.
3. **Evidence data plane** — PDFs, web pages, datasets, captions, metadata, retrieved text.
4. **Model output plane** — all LLM/subagent text and structured candidates.
5. **Execution plane** — shell, filesystem, MCP, parsers, network, validation targets.
6. **Memory plane** — session, workspace, user and evidence memory.
7. **External supply chain** — plugins, skills, npm/Python packages, containers, models.
8. **Presentation plane** — local dashboard, exports, notifications.

Evidence and model output are always untrusted data. They cannot grant capabilities, alter policy, change phase, or approve themselves.

## 2. Threat catalog and mandatory controls

| Threat | Failure | Mandatory control |
|---|---|---|
| Prompt injection in paper/web page | evidence text becomes instruction | data/instruction separation; quoting; no authority inheritance; injection fixtures |
| Tool-hook bypass | hosted/specialized tool not observed | hooks are guardrails; kernel capabilities and receipts are authoritative; capability report |
| Forged attestation | agent narrates a command/result | artifact hash, command/effect receipt, schema validation, independent verifier |
| Stale replay | old context used after corpus/policy change | snapshot hashes, stale propagation, compatibility and lifecycle status |
| Cross-workspace recall | confidential context leak | consent, workspace boundary, retrieval receipt, redaction, retention |
| Malicious remote skill | scripts or instructions gain authority | quarantine, static/dynamic scan, permissions, signature/hash, review, lockfile |
| Plugin upgrade tampering | modified hook or dist code | package hash, hook re-trust, SBOM, signature, source/dist equivalence |
| Symlink/path escape | write outside allowed root | canonical path resolution, no-follow policy, resource scope and sandbox |
| Secret exfiltration | evidence/model sends keys externally | secret handles only, egress allowlist, redaction, no secret in prompt/artifact |
| Partial fan-out hidden | missing critics makes verdict look complete | expected/actual count gate and PARTIAL status |
| UI outage hidden as empty | user trusts blank state | explicit UNAVAILABLE/DEGRADED state and health telemetry |
| Budget overrun | loop continues without meter | typed budget enforcement, preallocation, cancellation, hard round/concurrency caps |
| Provider drift | model version changes behavior | model identifier, adapter version, eval drift and attestation |
| Corpus licensing violation | unlicensed full text exported | source policy, license class, export filter and audit |
| Remote messaging abuse | command injection/data leakage | disabled by default; status/approval only; allowlist; no raw evidence |
| SQLite corruption/concurrency | lost phase or ledger | WAL, transactions, migrations, backup, integrity and recovery tests |
| Dependency confusion | malicious package resolution | lockfiles, registry allowlist, checksums, provenance and offline build |
| UI/API contract drift | dev and release paths differ | generated clients, one handler contract, conformance tests |
| Majority capture | correlated agents amplify error | asymmetric ACLs, veto, minority report, attestor, deterministic gates |
| Human override invisibility | unreviewable policy bypass | immutable OverrideRecord and downstream invalidation |

## 3. Hook fail-open/fail-closed matrix

- Informational bootstrap and map/recall suggestions: fail open with health warning.
- Secret/path/egress guard for local side effects: fail closed when the kernel can observe the action.
- Hosted tool path not observable: mark coverage gap; never claim enforcement.
- State integrity or migration uncertainty: SAFE_MODE; only doctor, export, backup, and recovery.
- Evidence lane unavailable: allow PARTIAL/UNDERDETERMINED, deny complete-coverage claims.
- Signature service unavailable: allow unsigned local development artifact, deny signed-release label.

## 4. Skill Vault

Remote skill acquisition is a workflow, not a copy command:

```text
discover metadata
→ fetch to quarantine
→ pin source revision and hash
→ inspect SKILL.md boundaries
→ enumerate scripts/assets/dependencies
→ license and provenance check
→ static secret/path/network scan
→ permission inference
→ sandbox smoke test
→ human or policy review
→ write SkillLockfile
→ install disabled
→ activate explicitly
```

A skill can recommend an action but cannot expand its own capabilities.

## 5. Privacy model

Memory classes:

- `EPHEMERAL`: current invocation, deleted on close unless promoted.
- `SESSION`: current FORGE run.
- `WORKSPACE`: explicit project memory.
- `USER`: cross-workspace, opt-in only.
- `EVIDENCE`: source-bound durable research artifacts.
- `REGULATED`: retention, legal hold, and access policy.

Every memory write has purpose, data classes, retention, workspace, actor, source, and consent basis. Every memory retrieval has query, searched stores, excluded stores, hits, redactions, and context hash.

## 6. Release security gates

- dependency lock and license scan;
- secret scan;
- malicious fixture suite;
- hook and MCP schema tests;
- sandbox/path escape tests;
- network egress tests;
- fresh-install and upgrade tests;
- SBOM and release provenance;
- deterministic bundle and hash manifest;
- signature verification;
- rollback package;
- compatibility matrix;
- no critical unresolved threat-model finding.


# Part VIII — CLI, MCP, API and Foundry Console

# Plugin UX, CLI, MCP and API contract

## 1. User-facing principle

The plugin exposes the minimum state needed to make rigor visible. It does not force users to memorize internal graph concepts, and it never turns a missing backend or missing search lane into a deceptively clean answer.

## 2. Primary commands

```text
efoundry init
efoundry doctor [--json]
efoundry status [--session ID] [--json]

efoundry forge interview|frame|observe|reason|gate|export
efoundry forge reopen <phase>
efoundry forge history
efoundry forge reset --reason ...

efoundry corpus add|list|verify|update
efoundry claim extract|show|verify|supersede
efoundry atlas coverage|contradictions|dependencies|methods
efoundry parliament run|status|docket|attest
efoundry aporia generate|compare|test
efoundry validate target|plan|run|reconcile
efoundry passport show|export|supersede

efoundry recall search|policy|forget
efoundry map workspace|repo|corpus|artifact
efoundry skill discover|inspect|quarantine|approve|activate|lock
efoundry replay run|compare|drift
efoundry backup create|verify|restore
efoundry plugin capability|migrate|rollback|uninstall
```

Every mutating command supports `--dry-run`, `--json`, `--expected-revision`, and an idempotency key. PATH-less invocation through the installed plugin root is a release gate.

## 3. MCP tool surface

Read tools:

- `foundry.status`
- `foundry.health`
- `foundry.session.get`
- `foundry.artifact.get`
- `foundry.claim.get`
- `foundry.atlas.query`
- `foundry.passport.get`
- `foundry.replay.diff`
- `foundry.map.query`

Planning tools:

- `foundry.frame.compile`
- `foundry.search.plan`
- `foundry.parliament.plan`
- `foundry.validation.plan`

Mutating/executing tools:

- `foundry.session.transition`
- `foundry.corpus.register`
- `foundry.search.execute`
- `foundry.claim.promote`
- `foundry.parliament.execute`
- `foundry.validation.execute`
- `foundry.passport.publish`
- `foundry.memory.write`
- `foundry.skill.activate`

Mutating tools require ActionIntent, policy evaluation, optional approval, capability lease, effect receipt, and reconciliation. Tool descriptions must state side effects and authority boundaries.

## 4. Dashboard states

The Foundry Console has seven primary views:

1. **Forge Docket** — phase, blockers, artifact obligations, revisions.
2. **Claim Forge** — source span, atomic claim, scope, method, promotion status.
3. **Epistemic Atlas** — coverage cells, search state, dependencies, contradiction classes.
4. **Evidence Parliament** — role briefs, attacks, vetoes, minority report, missing agents.
5. **Aporia Lab** — competing explanations, moderators, discriminating tests.
6. **Hypothesis Passport** — verdict dimensions, evidence, uncertainty, lifecycle.
7. **Health and Replay** — capabilities, migrations, drift, effects, backups.

Read models have four states:

```text
READY
EMPTY_CONFIRMED
DEGRADED
UNAVAILABLE
```

A network or backend error may never be rendered as `EMPTY_CONFIRMED`.

## 5. Contract generation

- JSON Schema is canonical for domain artifacts.
- OpenAPI is canonical for HTTP transport.
- TypeScript and Python models are generated.
- UI client is generated from OpenAPI.
- MCP tool schemas reference the same canonical definitions.
- Contract tests compare CLI JSON, MCP output, HTTP output, and persisted artifact shape.
- Development middleware and packaged server call the same handler services.

## 6. Local UI security

- bind to loopback by default;
- random per-run bearer token or OS-authenticated channel;
- strict Origin and CSRF checks for writes;
- Content Security Policy;
- no raw HTML rendering from evidence;
- source spans escaped and separately downloadable;
- no secrets in browser storage;
- explicit profile/workspace indicator;
- session timeout and revocation;
- audit receipt for approval/override actions.

## 7. Notifications

Notification adapters are optional. Default policy allows:

- run status;
- blocker summary;
- approval request with artifact IDs;
- final Passport availability.

Default policy denies:

- raw PDF/full-text export;
- secrets;
- arbitrary shell command submission;
- unredacted evidence excerpts;
- remote phase override.

## 8. Error model

Stable error envelope:

```json
{
  "code": "FORGE_GATE_FAILED",
  "message": "Observe phase is missing a counterevidence search receipt.",
  "category": "contract",
  "retryable": false,
  "session_id": "FS-...",
  "expected_revision": 12,
  "details": {"missing": ["counterevidence"]},
  "remediation": ["run `efoundry forge observe --lane counterevidence`"]
}
```

Errors are categorized as contract, policy, capability, dependency, transient, integrity, migration, provider, or user decision.


# Part IX — Codex and Claude Code adapters

# Codex and Claude Code adapter contract

## 1. Provider-neutral authority

Codex and Claude Code are execution surfaces. They do not own:

- FORGE phase;
- canonical artifacts;
- policy or consent;
- capability leases;
- evidence promotion;
- final replay state.

Each adapter translates the same `RoleSpec`, `NodeContract`, `ContextCapsule`, and `ResultEnvelope`.

## 2. Codex adapter

Uses:

- `.codex-plugin/plugin.json`;
- progressive skills;
- plugin-bundled hooks where supported and trusted;
- optional local MCP;
- built-in subagent types with inline compiled role prompts;
- worktrees for isolated parallel writes;
- `PLUGIN_ROOT` and `PLUGIN_DATA`;
- payload-resident `efoundry` dispatcher.

Rules:

- feature probe rather than assume hook support;
- hosted tool paths not observed by local hooks are listed as coverage gaps;
- custom scientific role semantics are compiled into built-in host roles;
- subagent results require schema validation and expected-count reconciliation;
- managed enterprise hooks can strengthen policy, but the plugin still retains kernel gates;
- plugin hook approval status is visible in health.

## 3. Claude Code adapter

Uses:

- repository `CLAUDE.md`;
- `.claude/agents/*.md` custom role definitions;
- `.claude/skills/`;
- hooks only as host guardrails;
- worktree isolation for parallel writes;
- CLI/MCP bridge to Foundry Kernel.

Rules:

- custom agent metadata is generated from canonical RoleSpec;
- main session remains Parent Architect/Research Governor;
- parallel writers require disjoint scopes and frozen contracts;
- every returned result is a ResultEnvelope, not a prose completion claim.

## 4. Model routing

Route by failure cost and empirical evaluation:

```text
high blast radius, causal or security decision → frontier + independent review
bounded extraction/classification             → economy/balanced
semantic synthesis and adversarial critique   → balanced/frontier
deterministic transform/gate                  → code, not model
validation execution                          → sandbox/tool, not model narration
```

Routing inputs:

- task class and node contract;
- observed model accuracy for that task;
- blast radius;
- error diversity from other roles;
- latency and hard/soft budget;
- privacy/provider constraints;
- current availability and rate limits.

Different vendors are not presumed independent. Independence is measured through eval disagreement and shared retrieval/prompt lineage.

## 5. Result envelope

Every adapter returns:

```text
node_id
role_spec_id
resolved_provider/model/version
input artifact and context hashes
output artifact IDs
claims with Evidence IDs
uncertainty and abstentions
tool/action receipts
checks
partial/missing status
token/latency accounting
adapter version
```

Free text may be attached as presentation but is not the contract.

## 6. Fallback

- unavailable preferred model → use only policy-approved fallback and record it;
- unavailable host subagent → serial execution with same RoleSpec;
- unavailable worktree → no parallel writes;
- unavailable MCP → CLI or local library adapter;
- unavailable hooks → explicit invocation and health DEGRADED;
- no compliant fallback → BLOCKED, not silent substitution.


# Part X — Canonical v3 contracts

## 1. Schema inventory

The package contains **76 canonical JSON Schemas** and matching examples. The 28 v3 plugin-native and audit-discovered additions are:

- `artifact-receipt.schema.json`
- `budget-envelope.schema.json`
- `capability-lease.schema.json`
- `compatibility-matrix.schema.json`
- `evidence-dependency-cluster.schema.json`
- `consent-record.schema.json`
- `context-capsule.schema.json`
- `epistemic-work-classification.schema.json`
- `forge-session-state.schema.json`
- `forge-transition-request.schema.json`
- `hook-event-envelope.schema.json`
- `host-capability-report.schema.json`
- `imported-run-record.schema.json`
- `memory-policy.schema.json`
- `memory-retrieval-receipt.schema.json`
- `measurement-compatibility-report.schema.json`
- `phase-artifact-set.schema.json`
- `plugin-capability-manifest.schema.json`
- `plugin-health-report.schema.json`
- `plugin-install-state.schema.json`
- `plugin-policy-pack.schema.json`
- `plugin-release-provenance.schema.json`
- `novelty-assessment.schema.json`
- `role-dispatch-plan.schema.json`
- `skill-lockfile.schema.json`
- `skill-routing-decision.schema.json`
- `search-completeness-certificate.schema.json`
- `workspace-map-snapshot.schema.json`

All transport types are generated from canonical schemas/OpenAPI. Hand-written duplicate wire enums are forbidden.

## 2. Workflow inventory

| Workflow | Version | Nodes | Purpose |
|---|---:|---:|---|
| `claim_extraction` | 3.0.0 | 13 | Select evidence units, extract atomic claims, verify grounding, and create dependency-aware evidence nodes. |
| `corpus_ingest` | 3.0.0 | 11 | Register, integrity-screen, parse, reconcile, and release immutable source documents. |
| `evaluation_release` | 3.0.0 | 16 | Run specification, plugin compatibility, scientific, security, calibration, recovery, cross-provider, and scale checks before a signed Epistemic Foundry release manifest. |
| `evidence_retrieval` | 3.0.0 | 20 | Compile a relation-aware query plan, execute eleven evidence lanes, and issue a completeness-bounded EvidencePack. |
| `evidence_update_reassessment` | 3.0.0 | 12 | Detect evidence or policy changes, compute impact, invalidate stale state, rerun affected workflows, and record decision deltas. |
| `forge_research_cycle` | 3.0.0 | 26 | Execute the research-native FORGE lifecycle from classification to Passport. |
| `insight_deliberation` | 3.0.0 | 27 | Run asymmetric evidence deliberation, adversarial challenge, stability analysis, attestation, and Passport issuance. |
| `memory_recall` | 3.0.0 | 8 | Retrieve prior context under explicit purpose, consent, scope, redaction and receipts. |
| `plugin_bootstrap` | 3.0.0 | 12 | Initialize a native host session without surrendering authority to host chat state. |
| `plugin_release` | 3.0.0 | 16 | Build, test, audit, sign and package the native plugin without overstating implementation maturity. |
| `plugin_upgrade_migration` | 3.0.0 | 12 | Upgrade or roll back the plugin with package verification, hook trust, migration dry-run and replay. |
| `skill_acquisition` | 3.0.0 | 12 | Discover and activate third-party skills through a supply-chain quarantine and lockfile. |
| `validation_execution` | 3.0.0 | 13 | Screen an optional validation target, preregister and authorize a plan, execute it safely, and reconcile typed evidence. |
| `workspace_mapping` | 3.0.0 | 10 | Create auditable code, research, artifact and authority maps with real baseline and query-specific rankings. |

## 3. Artifact migration

- v2 artifacts retain their IDs and hashes.
- A v2 run imported into v3 receives an `ImportedRunRecord`.
- v2 sessions map to a v3 FORGE session with phase `E` only when final artifacts are complete; otherwise they map to the earliest phase whose obligations are satisfied.
- No v2 narrative completion field is converted into an ArtifactReceipt.
- Existing ContextAssemblyManifest is referenced by a new ContextCapsule, not overwritten.
- New lifecycle, stability, capability and compatibility fields default to `UNKNOWN/NOT_ASSESSED`, not optimistic values.

## 4. Store migration

1. freeze writes;
2. create verified backup;
3. validate v2 schema bundle and database;
4. generate migration plan and dry-run report;
5. create v3 tables/repositories;
6. import events and artifacts;
7. derive FORGE state without manufacturing receipts;
8. rebuild projections/indexes;
9. run replay equivalence and sample Passport comparison;
10. switch active version;
11. retain rollback snapshot;
12. reapprove changed hooks and re-run capability probe.

## 5. Plugin migration

v2 had no canonical installable plugin. v3 therefore begins with a new plugin identity `epistemic-foundry` version `3.0.0`. Existing repo-local Codex/Claude files can coexist during migration, but authority order must point to the v3 specification. Duplicate skill names are detected and reported.

## 6. Rollback

Rollback restores the prior database/artifact snapshot and plugin version, but never deletes v3 migration events. Any v3-only external effect is reconciled and listed. Rollback success requires health PASS/DEGRADED with no integrity failure.


# Part XV — Architecture freeze

```text
SPECIFICATION COMPLETENESS: TARGET PASS after bundle validation
CODE/PLUGIN IMPLEMENTATION: NOT CLAIMED
CODEXCLAW GAP INTEGRATION: SPECIFIED
DOMAIN NEUTRALITY: REQUIRED
PLUGIN SHELL / KERNEL AUTHORITY SEPARATION: REQUIRED
ARCHITECTURE FREEZE: CONDITIONAL PASS
```

The remaining production conditions are intentionally external:

1. production plugin implementation and real fresh-install matrix;
2. supported Codex/Claude host-version policy;
3. production corpus licenses and access controls;
4. gold annotators, adjudication and domain benchmarks;
5. provider credentials, quotas, cancellation and metering authority;
6. PostgreSQL/object store/queue/region and recovery topology;
7. production signing identity and key custody;
8. organizational approval, conflict, appeal and retention authorities;
9. first production DomainPack and any ValidationTargets;
10. independent security, usability and production-scale qualification.

These conditions cannot be invented inside a development specification.
