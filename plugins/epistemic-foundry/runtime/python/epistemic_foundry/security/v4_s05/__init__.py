"""Verifier Firewall composition, quarantine gate and EF4-I64 controls (S05).

The gates qualify, refuse and audit; they never score, promote or execute.
"""

from __future__ import annotations

from .threat_controls import (
    FINDING_CODES,
    INCIDENT_ACTIONS,
    INVARIANTS_PATH,
    LEAKAGE_INVARIANT_ID,
    THREAT_MODEL_PATH,
    ThreatControlError,
    build_leakage_audit,
    build_threat_coverage,
    qualify_candidate_execution,
    require_inert_mutations,
    required_leakage_surfaces,
    sandbox_classes,
    threat_register,
)

__all__ = [
    "FINDING_CODES",
    "INCIDENT_ACTIONS",
    "INVARIANTS_PATH",
    "LEAKAGE_INVARIANT_ID",
    "THREAT_MODEL_PATH",
    "ThreatControlError",
    "build_leakage_audit",
    "build_threat_coverage",
    "qualify_candidate_execution",
    "require_inert_mutations",
    "required_leakage_surfaces",
    "sandbox_classes",
    "threat_register",
]
