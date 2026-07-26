"""Typed status vocabularies from `docs/status_taxonomy.md` and the schemas.

These enums are the single source of truth in code. A component that needs a
status value imports it here instead of writing a string literal, because a
literal is exactly how a taxonomy silently grows an unauthorized state.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """`str` mixin so values serialize directly into schema-valid JSON."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class ForgePhase(_StrEnum):
    """FORGE lifecycle phases (`forge-session-state.schema.json`)."""

    IDLE = "IDLE"
    INTERVIEW = "I"
    FRAME = "F"
    OBSERVE = "O"
    REASON = "R"
    GATE = "G"
    EXPORT = "E"


class WorkClass(_StrEnum):
    """Epistemic work classes E0-E5."""

    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class SessionStatus(_StrEnum):
    """Session lifecycle status (`forge-session-state.schema.json`)."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    STALE = "STALE"


class GateStatus(_StrEnum):
    """Gate outcomes (`gate-decision.schema.json`)."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCK = "BLOCK"
    WAIVE = "WAIVE"


class CapabilityStatus(_StrEnum):
    """Capability maturity (`docs/status_taxonomy.md`).

    `SPECIFIED` and `IMPLEMENTED` are deliberately distinct: conflating them is
    the overclaim this taxonomy exists to prevent.
    """

    SPECIFIED = "SPECIFIED"
    REFERENCE_BLUEPRINT = "REFERENCE_BLUEPRINT"
    IMPLEMENTED = "IMPLEMENTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    DEFERRED = "DEFERRED"
    UNSUPPORTED = "UNSUPPORTED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"


class ExitStatus(_StrEnum):
    """Typed exit vocabulary (MASTER_EXECUTION_PROMPT.md section 10).

    A truthful stop is part of the product: `BLOCKED`, `SPEC_GAP`, and
    `UNDERDETERMINED` are legitimate terminal answers, never placeholders to
    be replaced with plausible prose.
    """

    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SPEC_GAP = "SPEC_GAP"
    UNDERDETERMINED = "UNDERDETERMINED"
    UNASSESSED = "UNASSESSED"
    INVALIDATED = "INVALIDATED"
    REPLICATION_FAILED = "REPLICATION_FAILED"
