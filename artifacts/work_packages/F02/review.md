# F02-0001 FORGE FSM contract review

Status: `PASS_WITH_USER_AUTHORIZED_PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

Final verdict: `PASS`

Blocking findings: 0

Review mode: `PRIMARY_SESSION_SEPARATE_CONTRACT_REVIEW`

The product owner requires serial primary-session execution and forbids
subagents for this sequence. This review is a procedurally separate pass over
the final F02 bytes. It is not external actor-independent certification.

## Reviewed boundary

- `packages/foundry-kernel/src/forge/fsm/forge-fsm.mjs` — `sha256:f66a98d8c5359621c1ce3be1f11af4ff07cfd2838c66ca7b357798b8e8e8ed16`
- `packages/foundry-kernel/src/forge/fsm/index.mjs` — `sha256:76403f4efac53cfc0f422a2dc644d8d45133217c070097107e0f4e4600d4bc17`
- `packages/foundry-kernel/src/forge/fsm/fsm-test-support.mjs` — `sha256:d62316b37cc1359595c97f6e3fe98e93a75576a632847516451be67ec11a8e49`
- `packages/foundry-kernel/src/forge/fsm/fsm-property.test.mjs` — `sha256:86bfdbac70ef909e5809eb814feb5e0934231ace0b8498ab0e007cf00d68be4f`
- `packages/foundry-kernel/src/forge/fsm/stale-propagation.test.mjs` — `sha256:6bf19b049155c43d3254cc153542f7c518732f22351a8bfcded36bc59a5a353d`

The review also checked the F01 sealed dependency, `docs/forge_protocol.md`,
the canonical ForgeSessionState and PhaseArtifactSet schemas, F02 manifest
scope, and both normalized Node/Python regression receipts.

## Findings

1. Exact F01 E0-E5 phase projections drive the generated plan; a caller cannot
   weaken or enlarge them without invalidating the sealed classification.
2. All canonical forward, return, close, and illegal phase pairs are checked.
   State and PhaseArtifactSet phases must be reachable in the sealed plan,
   including the zero-event replay path.
3. Transitions are immutable, revision-bound, session-bound, and hash-bound to
   request, event, prior/current state, classification plan, and phase sets.
4. Every return edge applies target-inclusive downstream staleness. Original
   PhaseArtifactSets remain immutable history and projections record explicit
   supersession identities.
5. Cross-session, unretained, tampered, stale-revision, wrong-from-phase, and
   completed-session inputs fail closed.
6. Targeted tests are 14/14. Full Python is 947/947. Full Node is 284/285 with
   only exact pre-existing `S04-TM004`; F02 introduces zero failures or skips.
7. F02 modifies only `packages/foundry-kernel/src/forge/fsm/**`. It does not
   implement F03 receipt resolution, policy, capability, approval, or veto
   gates and does not weaken a schema or test.

## Assurance boundaries

- `phase_history` is validated for shape, revision bound, and current-tail
  agreement. F02 does not reinterpret it as a complete authoritative event log
  and therefore does not invent a stronger historical-continuity contract.
- Receipt validity, policy/veto authority, and transition admission based on
  resolving receipts belong to F03 and are intentionally not certified here.
- The review proves the in-process deterministic kernel surface, not a future
  distributed transport, persistence service, or exactly-once deployment.

## Decision

F02 meets both exit criteria: FORGE transitions are deterministic, and legal
return edges preserve prior artifacts while staling the target-inclusive
downstream projection. Wider product completion remains false.
