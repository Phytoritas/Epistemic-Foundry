# Epistemic Foundry v4 plugin architecture and boundary map

**Capability status:** `SPECIFIED`  
**Runtime maturity:** not established by this document

## 1. Constitutional split

Epistemic Foundry deliberately separates experience, execution, scientific
control, and canonical authority. The Plugin Shell makes Foundry available in
a host; it does not become Foundry.

| Plane | Components | Authority limit |
|---|---|---|
| Experience | skills, hooks, CLI, MCP, Console, host manifest | request and render only |
| Execution | providers, parsers, retrieval, sandbox, optional Shinka adapter | produce untrusted observations/effects only |
| Search | genomes, operators, challenges, islands, Pareto/niche archives | propose and prioritize only |
| Scientific control | evidence contracts, Verifier Firewall, statistics, replication, Parliament | qualify and constrain; no state rewrite |
| Authority | Foundry Kernel, Noetic Ledger, policy, approvals, release gates | canonical transitions, history, effects, replay, and release |

Higher rows cannot grant themselves rights in lower authority rows.

## 2. State ownership

| State or decision | Canonical owner | Non-authoritative projections |
|---|---|---|
| RunSpec, lifecycle revision, legal transition | Foundry Kernel | shell session, UI route, chat summary |
| events, attempts, effects, approvals, receipts | Noetic Ledger | logs, hook traces, dashboard timelines |
| policy, capability and deterministic gate result | Foundry Kernel with ledger record | host permission dialog, provider response |
| evidence and scientific artifacts | content-addressed artifacts registered in the Ledger | search index, vector cache, rendered brief |
| evaluator identity and holdout access decision | Verifier Firewall under Kernel policy | backend score or aggregate feedback |
| promotion and release | configured hard gates, Parliament/attestation, human/policy authority | model confidence, vote, novelty or scalar score |

No adapter cache is a recovery source unless its content resolves to canonical
hashes and the current revision.

## 3. Command and effect boundary

```text
user or host event
  → Plugin Shell: normalize + capability observation
  → canonical command / ActionIntent with expected revision
  → Foundry Kernel: schema + policy + gate + revision validation
  → Noetic Ledger: append attempt and authoritative event
  → executor: bounded external effect under capability lease
  → Noetic Ledger: reconcile EffectReceipt
  → projections: CLI/MCP/HTTP/UI response
```

A request is not an effect, and an attempted effect is not completion. Missing
or unreconciled receipts constrain transitions and release claims.

## 4. Component dependency map

Dependency arrows point from importer to dependency:

```text
L4 adapters/composition ───────────────┐
  plugin_shell · providers · cli       │
  Shinka/host/MCP/HTTP/UI adapters     │
          │                             │
          ▼                             │
L3 governed scientific services        │
  Claim Forge · Atlas · Parliament      │
  Aporia · Evolution · Validation       │
  Verifier · Archive · memory · etc.    │
          │                             │
          ▼                             │
L2 foundry_kernel ───────────────┐      │
          │                      │      │
          ▼                      │      │
L1 noetic_ledger                 │      │
          │                      │      │
          └──────────┬───────────┘      │
                     ▼                  │
L0 contracts · domain ◄────────────────┘
```

Allowed edges point inward or to a lower-numbered layer. L3 peer edges must be
explicit and acyclic. L4 is the only composition layer. Kernel and Ledger may
never import Plugin Shell, provider, Shinka, host, MCP, HTTP, or UI
implementations.

## 5. Cycle and API policy

- Components consume exported package APIs, never another component's source
  tree or private implementation module.
- Shared wire types live in canonical schemas/contracts, not provider SDKs.
- The internal component graph must be acyclic. The load-bearing runtime
  invariant is enforced at **module-slice granularity** — each component and
  each `component/v4_*` subpackage is a distinct node — and must be a strict
  DAG, so there is no runtime circular import. At top-level component
  granularity a 2-cycle between two L3 governed services is permitted only
  under the closed, fingerprinted exception recorded in ADR-034; authority
  (L0/L1/L2) and adapter (L4) cycles remain forbidden at every granularity.
- Apparent bidirectional collaboration is implemented with commands, events,
  receipts, or dependency-inverted interfaces composed at L4.
- Dynamic loading cannot bypass the same boundary policy.
- Any boundary change requires a new ADR, compatibility analysis, and an
  updated deterministic check.

## 6. Adapter failure and fallback

Capabilities are probed at runtime. Missing optional capability is reported as
`DEGRADED` or `UNAVAILABLE` with its substitution; loss of a constitutional
control is `BLOCKED` or `SAFE_MODE`. In particular:

- disabled hooks do not disable Kernel gates;
- unavailable MCP may fall back to the canonical CLI;
- unavailable parser yields a typed layout limitation;
- unavailable novelty search yields `UNASSESSED`, never `NOVEL`;
- unavailable authoritative budget metering yields `SOFT_ESTIMATE`;
- unavailable ShinkaEvolve leaves the core operational and removes only that
  optional search path.

## 7. Decision records and verification

The boundary decisions are indexed in `docs/adr/README.md`:

- ADR-031: Plugin Shell and Kernel authority separation;
- ADR-032: component import direction and cycle policy;
- ADR-033: adapter isolation and explicit degraded modes;
- ADR-034: L3 integration-gate cycle exception (module-slice acyclicity refines
  ADR-032 rule 5).

`adr_index_check` proves the ADR set is indexed and structurally complete.
`boundary_cycle_policy_check` validates current Python imports against the
layer policy and rejects cycles. Passing documentation checks proves the
boundary contract is coherent, not that every target runtime component is
implemented or production-qualified.
