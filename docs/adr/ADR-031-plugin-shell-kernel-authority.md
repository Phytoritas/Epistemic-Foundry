# ADR-031 — Plugin Shell and Kernel authority separation

**Status:** Accepted

## Context

Native skills, hooks, CLI/MCP surfaces, provider SDKs, and Console views make
the product usable, but they execute in host-controlled environments with
partial observability and mutable local state. Treating any of those surfaces
as canonical would let presentation or adapter behavior rewrite research
state, policy, gates, or replay history.

## Decision

The Plugin Shell is an experience and integration adapter. It may normalize
host events, probe capabilities, collect a requested action, submit a typed
command, and render kernel-owned results. It does not commit lifecycle state,
grant capabilities, decide a gate, certify evidence, or declare an effect
complete.

Foundry Kernel owns legal transitions, revision checks, policy, capability
decisions, deterministic gates, checkpoint coordination, and replay
semantics. Noetic Ledger owns append-only events, attempts, effects,
approvals, artifact references, and the audit chain. State-changing shell
requests therefore follow this direction:

```text
host / skill / hook / CLI / MCP / Console
  → Plugin Shell normalization
  → typed command or ActionIntent
  → Foundry Kernel validation and revision check
  → Noetic Ledger append / effect reconciliation
  → receipt-bound projection
  → Plugin Shell rendering
```

Shell caches and chat transcripts are disposable projections. They can help
resume navigation only after hash-bound reconstruction from canonical
artifacts.

## Consequences

- Hook absence produces an explicit degraded mode; it does not remove kernel
  gates.
- A shell or provider crash cannot become a committed transition without a
  resolving ledger event and receipt.
- UX state must distinguish unavailable, degraded, and confirmed-empty data.
- Kernel and Ledger packages never import Plugin Shell, host SDK, UI, or
  provider implementation modules.

## Rejected alternatives

- Store canonical phase state in chat, hooks, or UI caches.
- Let provider tool callbacks grant their own capability or completion claim.
- Duplicate transition rules in each host adapter.

## Verification

- `boundary_cycle_policy_check` rejects authority-to-adapter imports and any
  internal package cycle.
- Kernel transition and ledger integrity tests remain the behavioral gate.
- Host-disabled and adapter-failure acceptance tests must show explicit
  degraded or blocked behavior before a runtime maturity claim.
