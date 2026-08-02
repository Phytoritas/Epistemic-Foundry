# F02-0001 independent review of bounded-agent work

- Author: the bounded implementation agent that wrote
  packages/foundry-kernel/src/forge/fsm. Reviewer: this seal-prep session, a
  distinct actor that did not author the FORGE FSM. The author never
  approves its own work, so actor_independence HOLDS for this review;
  external actor-independent certification does NOT, and no such claim is
  made. F02 is risk_class=medium and governs the FORGE transition kernel, so
  the legal graph, return-edge staleness, and F01 integrity were attacked on
  their contracts rather than skimmed.
- Legal transitions and return edges are class-derived and fail closed.
  compileForgePlan validates the F01 classification against the exact
  per-work-class EXPECTED_PROJECTIONS and re-verifies its hash-bound
  identity; a required_phases that is not one of the class projections is
  rejected INVALID_CLASSIFICATION_PROJECTION and a classification whose
  reasons or identity were tampered fails CLASSIFICATION_INTEGRITY_FAILED.
  Forward edges are chained from the projection, the return-edge set is the
  fixed legal set (F/O/R/G->I, R/G->O, G->R, E->F) filtered to the phases
  reachable for the class, and E->IDLE closes only when E is reachable, so
  the E1 LOOKUP class exposes exactly its F/O/E surface and never R or G.
  describeForgeTransition returns PHASE_NOT_REACHABLE_FOR_CLASSIFICATION for
  a phase outside the projection and ILLEGAL_FORGE_TRANSITION for an
  unreachable edge between reachable phases; the property test walks every
  phase pair for all seven E0-E5 cases against the exact expected graph.
- The reducer is deterministic and fails closed before mutating. 
  reduceForgeTransition asserts the sealed state hash, then refuses a
  non-transitionable session (FORGE_SESSION_NOT_TRANSITIONABLE), a
  work-class/plan mismatch (CLASSIFICATION_STATE_MISMATCH), an unreachable
  current phase, a foreign session (SESSION_MISMATCH), a stale revision
  (STALE_REVISION), a wrong from_phase (FROM_PHASE_MISMATCH), and an illegal
  edge, each before any state is produced. The next state is deep-frozen and
  hash-bound, and the transition record is hash-bound over the request,
  event, prior/current state hash, plan hash, and phase-set hashes, so
  changing the request reason, event, or phase set changes the transition
  hash. Strict event replay reproduces the direct reducer chain and the
  empty replay still verifies every sealed initial input.
- Return edges stale the target-inclusive downstream and never leave silent
  stale state. On a RETURN edge projectReturnStaleness marks the return
  target and every downstream execution phase reachable for the class STALE:
  each superseded set is re-derived as PAS-STALE-<digest> bound to the event
  and source set, with complete=false, STALE artifact status, and a fresh
  set_hash, while the untouched I/F sets keep their original ids. The
  transition records stale_phases and sorted stale_artifact_ids and the
  result emits the superseded sets explicitly; the source PhaseArtifactSets
  passed in are left byte-for-byte immutable. Projection identity is
  deterministic and event-bound (set order does not change it; a different
  event does). FORWARD and CLOSE edges stale nothing. Cross-session,
  unretained, and tampered phase sets fail closed
  (PHASE_ARTIFACT_SESSION_MISMATCH, PHASE_ARTIFACT_NOT_IN_STATE,
  PHASE_ARTIFACT_SET_HASH_MISMATCH).
- Dependencies and checks: the FSM derives its graph from the sealed F01
  epistemic-work classification (F01-0003 PASS) and adds no new production
  dependency; it re-verifies F01 artifact integrity on every plan compile.
  Ruff lint and format, the two required checks (fsm_property_test 8/8, stale_propagation_test 6/6), targeted 14/14, full Python 1261/1261, full Node 1291/1291 across 115 files, and git diff --check all pass with
  zero failures; the earlier S04-TM004 pre-existing Node debt is resolved in
  the current tree, so F02 seals against a clean full Node suite.
- Residual limitations: F02 provides the deterministic FORGE FSM, its legal
  graph, and return-edge staleness only; receipt resolution, policy,
  capability, approval, and veto admission gates remain F03 responsibility,
  and phase_history is validated for shape, revision bound, and current-tail
  agreement but is not reinterpreted as a stronger authoritative event log.
  Verdict: PASS on the exact F02 package contract.
