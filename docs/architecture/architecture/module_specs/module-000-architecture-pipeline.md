# Module Spec: module-000-architecture-pipeline

## Responsibility
Describe the workflow module that owns:
- repository audit
- design artifact generation
- runtime sidecar updates
- Memento-aware resume packets
- implementation gate discipline

## Public Artifacts
- `docs/architecture/Phytoritas.md`
- `.rah/state/status.json`
- `.rah/state/gates.json`
- `.rah/state/memento_status.json`
- `.rah/plans/current_loop.md`
- `.rah/memory/wakeup.md`

## Failure / Recovery
If runtime state drifts from repository reality:
1. re-read files and scripts
2. repair `.rah/`
3. amend Memento only after facts are confirmed
