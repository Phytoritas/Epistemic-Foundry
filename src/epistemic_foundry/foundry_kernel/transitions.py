"""Legal FORGE phase transitions.

Lifecycle (MASTER_EXECUTION_PROMPT section 4):

    Interview(optional) -> Frame -> Observe -> Reason -> Gate -> Export/Evolve

The map is explicit rather than derived from ordering, because two rules are
not orderings: Interview is skippable (IDLE may enter Frame directly), and Gate
may send a session back to Observe or Reason when evidence is insufficient.
A backward edge from Gate is a legitimate research outcome, not an error path.
"""

from __future__ import annotations

from ..domain.status import ForgePhase

ILLEGAL_TRANSITION_REASON = "illegal FORGE phase transition"

_ALLOWED: dict[ForgePhase, frozenset[ForgePhase]] = {
    # Interview is optional, so IDLE may open at I or F.
    ForgePhase.IDLE: frozenset({ForgePhase.INTERVIEW, ForgePhase.FRAME}),
    ForgePhase.INTERVIEW: frozenset({ForgePhase.FRAME}),
    ForgePhase.FRAME: frozenset({ForgePhase.OBSERVE}),
    ForgePhase.OBSERVE: frozenset({ForgePhase.REASON}),
    # Reason may return to Observe when retrieval is incomplete.
    ForgePhase.REASON: frozenset({ForgePhase.GATE, ForgePhase.OBSERVE}),
    # Gate is the only decision point: forward to Export, or back for more work.
    ForgePhase.GATE: frozenset({ForgePhase.EXPORT, ForgePhase.OBSERVE, ForgePhase.REASON}),
    # Export terminates the cycle; a new cycle starts from IDLE.
    ForgePhase.EXPORT: frozenset({ForgePhase.IDLE}),
}


def allowed_targets(phase: ForgePhase) -> frozenset[ForgePhase]:
    """Phases reachable from `phase` in one transition."""
    return _ALLOWED[ForgePhase(phase)]


def is_legal_transition(from_phase: ForgePhase, to_phase: ForgePhase) -> bool:
    """True when the edge exists in the lifecycle contract."""
    return ForgePhase(to_phase) in allowed_targets(from_phase)


def requires_gate_evidence(to_phase: ForgePhase) -> bool:
    """Entering Export requires a passing gate result.

    This is the promotion boundary in miniature: a session may not leave the
    Gate phase into Export on narrative confidence alone.
    """
    return ForgePhase(to_phase) is ForgePhase.EXPORT
