"""Cartography integration gate over M05 (M06).

Three questions the map cannot ask about itself: does it still agree with the
archive, has a ranking figure been asked to promote, and has a stale map
already propagated into the records derived from it.
"""

from __future__ import annotations

from .gate import (
    AUTHORITY_SCHEMA_NAMES,
    CartographyIntegrationError,
    DERIVATION_FIELDS,
    DERIVED_RECORD_FIELDS,
    EXTERNAL_RANKING_FIGURE,
    FINDING_CODES,
    RANKING_FIGURE_NAMES,
    audit_promotion_request,
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    build_staleness_cascade,
    map_agreement_findings,
    require_current_revision,
)

__all__ = [
    "AUTHORITY_SCHEMA_NAMES",
    "CartographyIntegrationError",
    "DERIVATION_FIELDS",
    "DERIVED_RECORD_FIELDS",
    "EXTERNAL_RANKING_FIGURE",
    "FINDING_CODES",
    "RANKING_FIGURE_NAMES",
    "audit_promotion_request",
    "bind_derived_record",
    "build_map_agreement_record",
    "build_map_revision",
    "build_staleness_cascade",
    "map_agreement_findings",
    "require_current_revision",
]
