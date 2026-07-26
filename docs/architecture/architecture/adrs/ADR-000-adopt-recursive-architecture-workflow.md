# ADR-000: Adopt Recursive Architecture Workflow

## Status
Accepted

## Context
Epistemic-Foundry is being handled with a recursive architecture workflow that separates:
- design artifacts in `docs/architecture/`
- runtime/control-plane state in `.rah/`
- long-term memory in Memento

## Decision
Adopt the harness-backed recursive architecture workflow as the default way to plan, refactor, and validate non-trivial work.

## Consequences
- setup / doctor / status / resume become explicit operator surfaces
- implementation stays blocked until architecture and validation gates pass
- Memento assists recall and reflection but does not override `AGENTS.md`
