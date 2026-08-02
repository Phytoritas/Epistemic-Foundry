"""Evidence/holdout version and leakage-prevention integration gate (K06).

The gate composes the sealed K05 evidence/holdout surface, the O05 evolution
retrieval surface and the S05 verifier-firewall leakage controls into one bound
evidence/holdout version, and refuses every operation that would reuse a stale
version, expose a hidden holdout, or let evaluator feedback leak into a
candidate or the search.  It never re-pins evidence, re-seals a holdout, scores,
promotes, mutates its inputs, or reads a clock; every decision resolves to an
immutable, re-derivable receipt.
"""

from __future__ import annotations

from .gate import (
    CONCEALED_DOCUMENT_FIELDS,
    CONCEALED_HANDLE_FIELDS,
    EXECUTION_RECEIPT_PREFIX,
    FEEDBACK_RECEIPT_PREFIX,
    FINDING_CODES,
    HOLDOUT_DENIAL_PROBE,
    LEAKAGE_AUDIT_ID_PREFIX,
    RESULTS_RECEIPT_PREFIX,
    RETRIEVAL_RECEIPT_PREFIX,
    VERSION_ID_PREFIX,
    LeakageGateError,
    admit_candidate_execution_against_version,
    admit_evaluator_feedback_against_version,
    admit_retrieval_against_version,
    admit_search_results_against_version,
    bind_evidence_holdout_version,
    require_version_identity,
)

__all__ = [
    "CONCEALED_DOCUMENT_FIELDS",
    "CONCEALED_HANDLE_FIELDS",
    "EXECUTION_RECEIPT_PREFIX",
    "FEEDBACK_RECEIPT_PREFIX",
    "FINDING_CODES",
    "HOLDOUT_DENIAL_PROBE",
    "LEAKAGE_AUDIT_ID_PREFIX",
    "RESULTS_RECEIPT_PREFIX",
    "RETRIEVAL_RECEIPT_PREFIX",
    "VERSION_ID_PREFIX",
    "LeakageGateError",
    "admit_candidate_execution_against_version",
    "admit_evaluator_feedback_against_version",
    "admit_retrieval_against_version",
    "admit_search_results_against_version",
    "bind_evidence_holdout_version",
    "require_version_identity",
]
