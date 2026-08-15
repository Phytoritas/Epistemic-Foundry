"""Search-completeness, novelty-failure and prior-art integration gate.

This package reconciles the eleven canonical O05 lane receipts into the
``search-completeness-certificate`` the schema declares, and gates a novelty or
prior-art claim on that certificate together with the sealed Q05 admissibility
receipt.  It composes O05 (retrieval, layered novelty, coverage), the
K05/evaluation novelty owners and the Q05 selective-inference gate, and holds no
canonical enum vocabulary of its own: completion states, claim ceilings, work
classes and lane states are read from the schema that declares them or imported
from the surface that owns them (EF4-I22).  Nothing here promotes, scores, or
reads a clock.
"""

from __future__ import annotations

from .gate import (
    ABSENCE_CORPUS_CONDITIONAL_POSITION,
    ABSENCE_EXTERNAL_CONDITIONAL_POSITION,
    ABSENCE_NONE_POSITION,
    ADMIT,
    CERTIFICATE_ID_PREFIX,
    COMPLETION_BLOCKED_POSITION,
    COMPLETION_FAIL_POSITION,
    COMPLETION_NOT_REQUIRED_POSITION,
    COMPLETION_PARTIAL_POSITION,
    COMPLETION_PASS_POSITION,
    EXEMPT_WORK_CLASS_POSITION,
    FINDING_CODES,
    GATE_ID_PREFIX,
    GATE_NAME,
    NOVELTY_CORPUS_NOVEL_ONLY_POSITION,
    NOVELTY_NOT_ASSESSED_POSITION,
    NOVELTY_SEARCH_CONDITIONAL_POSITION,
    RECEIPT_BLOCKED_POSITION,
    RECEIPT_FAILED_POSITION,
    RECEIPT_PARTIAL_POSITION,
    REFUSE,
    SchemaNotFound,
    SearchIntegrityRefused,
    absence_ceiling_vocabulary,
    build_search_completeness_certificate,
    certificate_earns_novelty,
    completion_state_vocabulary,
    derive_search_integrity_admissibility,
    evaluate_search_integrity_admissibility,
    novelty_ceiling_vocabulary,
    require_certificate_identity,
    work_class_vocabulary,
)

__all__ = [
    "ABSENCE_CORPUS_CONDITIONAL_POSITION",
    "ABSENCE_EXTERNAL_CONDITIONAL_POSITION",
    "ABSENCE_NONE_POSITION",
    "ADMIT",
    "CERTIFICATE_ID_PREFIX",
    "COMPLETION_BLOCKED_POSITION",
    "COMPLETION_FAIL_POSITION",
    "COMPLETION_NOT_REQUIRED_POSITION",
    "COMPLETION_PARTIAL_POSITION",
    "COMPLETION_PASS_POSITION",
    "EXEMPT_WORK_CLASS_POSITION",
    "FINDING_CODES",
    "GATE_ID_PREFIX",
    "GATE_NAME",
    "NOVELTY_CORPUS_NOVEL_ONLY_POSITION",
    "NOVELTY_NOT_ASSESSED_POSITION",
    "NOVELTY_SEARCH_CONDITIONAL_POSITION",
    "RECEIPT_BLOCKED_POSITION",
    "RECEIPT_FAILED_POSITION",
    "RECEIPT_PARTIAL_POSITION",
    "REFUSE",
    "SchemaNotFound",
    "SearchIntegrityRefused",
    "absence_ceiling_vocabulary",
    "build_search_completeness_certificate",
    "certificate_earns_novelty",
    "completion_state_vocabulary",
    "derive_search_integrity_admissibility",
    "evaluate_search_integrity_admissibility",
    "novelty_ceiling_vocabulary",
    "require_certificate_identity",
    "work_class_vocabulary",
]
