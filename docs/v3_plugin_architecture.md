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
