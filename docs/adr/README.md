# Epistemic Foundry architecture decision records

This directory indexes v4 boundary decisions. Earlier accepted decisions
ADR-001 through ADR-030 remain in `docs/architecture_decisions.md`; the records
below continue that sequence without renumbering history.

| ADR | Status | Decision |
|---|---|---|
| [ADR-031](ADR-031-plugin-shell-kernel-authority.md) | Accepted | Plugin Shell is an adapter; Foundry Kernel and Noetic Ledger own canonical authority. |
| [ADR-032](ADR-032-component-import-boundaries.md) | Accepted | Components depend inward through public contracts and the internal import graph must remain acyclic. |
| [ADR-033](ADR-033-adapter-isolation-and-degraded-mode.md) | Accepted | Provider and search backends are replaceable, capability-probed adapters that fail closed. |
| [ADR-034](ADR-034-l3-integration-gate-cycle-exception.md) | Accepted | Runtime acyclicity is enforced at module-slice granularity; two fingerprinted L3-service top-level 2-cycles are the only permitted exception, refining ADR-032 rule 5. |

## Record requirements

Every ADR in this directory has a unique ID, status, context, decision,
consequences, rejected alternatives, and verification section. Accepted
records may be superseded only by a new ADR that names the superseded ID;
history is never edited to make a later decision appear original.

The index is navigation, not a second authority source. `MASTER_SPEC.md` and
the authority order it defines remain normative.
