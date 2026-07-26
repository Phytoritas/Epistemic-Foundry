# Phytoritas Blueprint

## Objective
Use recursive architecture design and refactoring to improve **Epistemic-Foundry** in a controlled, reviewable way.

## Bound Root
`C:\dev\insight\Epistemic-Foundry`

## Scaffold Root
`docs\architecture`

## Repo Profile
`generic`

## Harness Mode
`auto-bootstrap`

## Authority Order
1. repo-local `AGENTS.md`
2. global `AGENTS.md`
3. live repository facts
4. `.rah/` runtime state
5. Memento recall results
6. chat memory

## Memento Identity
- workspace: `epistemic-foundry`
- topic: `architecture-refactor`
- sessionId: `epistemic-foundry#adhoc:bootstrap`
- caseId: `case/epistemic-foundry/adhoc/generic`

## Stage Map
1. Setup / doctor / status
2. AGENTS and workflow intake
3. Workspace audit and current-system recon
4. Architecture and module decisions
5. Validation design
6. Implementation gate
7. Incremental implementation
8. Review and regression hardening
9. Reflect and next loop setup

## Decision Gates
- AGENTS/workflow gate
- scaffold/harness gate
- current-system recon gate
- architecture evidence gate
- implementation gate
- memento recall / feedback hygiene gate

## Loop Contract
- Keep implementation blocked until the implementation gate passes.
- Re-read the nearest `AGENTS.md` before broad writes.
- Use `.rah/` for control-plane state and `docs/architecture/` for design artifacts.
- Use Memento as a memory aid, not as a policy source.
