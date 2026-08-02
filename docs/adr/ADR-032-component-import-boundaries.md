# ADR-032 — Component import direction and cycle policy

**Status:** Accepted

## Context

Epistemic Foundry has foundation contracts, canonical authority, scientific
services, and replaceable adapters. Unconstrained imports would allow an
authority module to depend on a host, create circular initialization, or make
provider-specific data structures part of canonical semantics.

## Decision

Internal Python components depend inward through public package APIs. The
layer policy is:

| Layer | Components | May import |
|---|---|---|
| L0 foundation | `contracts`, `domain` | Python standard library and pinned third-party libraries only |
| L1 ledger authority | `noetic_ledger` | L0 |
| L2 kernel authority | `foundry_kernel` | L0 and L1 |
| L3 governed services | Claim Forge, Atlas, Parliament, Aporia, Validation, evolution, governance, memory, retrieval, statistics, release, security, and other scientific services | L0 and public L1/L2 APIs; peer services only when the dependency is explicit and acyclic |
| L4 adapters/composition | `plugin_shell`, `providers`, `shinka_adapter`, `cli`, host/MCP/HTTP/UI adapters | Public APIs from inward layers; composition roots may wire adapters but adapters do not become authority |

The dependency arrow is always importer → dependency. These rules are
non-negotiable:

1. L0 imports no Epistemic Foundry package outside L0.
2. L1/L2 import no L3 or L4 component.
3. L3 imports no L4 adapter.
4. No component imports another component's private module or source tree;
   cross-component calls use exported package APIs and canonical contracts.
5. The top-level internal component graph is a directed acyclic graph.
6. Dynamic imports, service locators, plugin registries, and generated code may
   not be used to conceal a forbidden edge.
7. A collaboration that appears cyclic is split by moving shared types into
   L0 and coordinating through events, commands, or interfaces wired at L4.

An exception requires a superseding ADR, an updated boundary check, and proof
that Kernel/Ledger authority and provider neutrality remain intact. A waiver
cannot authorize an actual authority cycle.

## Consequences

- Foundation contracts can be reused by all surfaces without importing
  runtime owners.
- Kernel behavior is testable without loading a plugin host or model SDK.
- Scientific services can evolve independently while canonical state changes
  still flow through Kernel and Ledger.
- Cycles are design errors, not packaging inconveniences.

## Rejected alternatives

- A single package with unrestricted relative imports.
- Bidirectional Kernel ↔ Plugin Shell callbacks.
- Provider SDK models as canonical contract classes.
- Runtime monkey-patching to break import cycles.

## Verification

`boundary_cycle_policy_check` parses Python imports, resolves relative edges to
top-level components, applies the layer constraints above, and performs a
topological cycle check. Published multi-language packages must add equivalent
checks when B01 introduces their roots.
