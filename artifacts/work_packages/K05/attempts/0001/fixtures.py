"""Fixtures for the K05 corpus/holdout/prior-art boundary suites.

Every fixture is produced through the module's own builders, so a fixture is a
record the boundaries actually accept rather than a hand-written shape that
would test only itself.  The corpus deliberately holds one document dated after
the prior-art as-of bound, because "in the snapshot but outside the searched
time window" is the case the novelty gate has to distinguish from "not in the
snapshot at all".
"""

from __future__ import annotations

from typing import Any

from epistemic_foundry.evidence.v4_k05 import (
    declare_prior_art_boundary,
    partition_pinned_snapshot,
    pin_corpus_snapshot,
    seal_holdout_boundary,
)

CORPUS_ID = "CORPUS-K05"
PINNED_AT = "2026-08-02T00:00:00Z"
EVALUATED_AT = "2026-08-02T01:00:00Z"
SEALED_AT = "2026-08-02T02:00:00Z"
ASSESSED_AT = "2026-08-02T03:00:00Z"
POLICY_VERSION = "k05-source-integrity-1.0.0"
AS_OF_DATE = "2026-01-01"

EVALUATOR_ID = "EV-K05-1"
SPLIT_STRATEGY = "pinned-corpus-partition"
ACL_POLICY_HASH = "sha256:" + "d" * 64
LOG_REDACTION_POLICY = "strip-holdout-handles"
CACHE_ISOLATION_POLICY = "per-run-namespace"

VISIBLE_ID = "DOC-VISIBLE"
HIDDEN_ID = "DOC-HIDDEN"
OOD_ID = "DOC-OOD"
ADVERSARIAL_ID = "DOC-ADVERSARIAL"
LATE_ID = "DOC-LATE"

RUN_ID = "ER-K05-1"
SUBJECT_REF = "HY-K05-1"
STATEMENT_HASH = "sha256:" + "a" * 64
CERTIFICATE_ID = "SCC-K05-1"
ASSESSOR_REF = "novelty-examiner-1"
SEARCHED_SOURCES = ("pinned-local-corpus",)
UNSEARCHED_SOURCES = ("patent-registers", "paywalled-journals")


def document(
    document_id: str,
    *,
    fill: str,
    license_status: str,
    source_date: str,
    source_uri: str | None = None,
) -> dict[str, Any]:
    return {
        "content_hash": "sha256:" + fill * 64,
        "document_id": document_id,
        "license_status": license_status,
        "source_date": source_date,
        "source_uri": source_uri,
    }


def documents() -> list[dict[str, Any]]:
    return [
        document(
            VISIBLE_ID,
            fill="1",
            license_status="open_access",
            source_date="2024-01-02",
            source_uri="https://example.invalid/visible",
        ),
        document(
            HIDDEN_ID, fill="2", license_status="licensed", source_date="2024-05-06"
        ),
        document(
            OOD_ID, fill="3", license_status="open_access", source_date="2025-02-03"
        ),
        document(
            ADVERSARIAL_ID,
            fill="4",
            license_status="fair_use_metadata_only",
            source_date="2025-07-08",
        ),
        # Inside the pinned corpus, outside the prior-art as-of bound.
        document(
            LATE_ID, fill="5", license_status="open_access", source_date="2026-09-09"
        ),
    ]


def snapshot(**overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "corpus_id": CORPUS_ID,
        "documents": documents(),
        "pinned_at": PINNED_AT,
    }
    keywords.update(overrides)
    return pin_corpus_snapshot(**keywords)


def observed_hashes(**overrides: str) -> dict[str, str]:
    observed = {
        str(row["document_id"]): str(row["content_hash"]) for row in documents()
    }
    observed.update(overrides)
    return observed


def partition(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "visible_document_ids": [VISIBLE_ID, LATE_ID],
        "hidden_document_ids": [HIDDEN_ID],
        "ood_document_ids": [OOD_ID],
        "adversarial_document_ids": [ADVERSARIAL_ID],
    }
    keywords.update(overrides)
    return partition_pinned_snapshot(**keywords)


def seal_arguments(
    pinned: dict[str, Any] | None = None, **overrides: Any
) -> dict[str, Any]:
    pinned = pinned if pinned is not None else snapshot()
    keywords: dict[str, Any] = {
        "snapshot": pinned,
        "partition": partition(pinned),
        "evaluator_id": EVALUATOR_ID,
        "split_strategy": SPLIT_STRATEGY,
        "acl_policy_hash": ACL_POLICY_HASH,
        "log_redaction_policy": LOG_REDACTION_POLICY,
        "cache_isolation_policy": CACHE_ISOLATION_POLICY,
        "sealed_at": SEALED_AT,
    }
    keywords.update(overrides)
    return keywords


def holdout(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    return seal_holdout_boundary(**seal_arguments(pinned, **overrides))


def boundary(pinned: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    keywords: dict[str, Any] = {
        "snapshot": pinned if pinned is not None else snapshot(),
        "as_of_date": AS_OF_DATE,
        "searched_sources": list(SEARCHED_SOURCES),
        "unsearched_sources": list(UNSEARCHED_SOURCES),
    }
    keywords.update(overrides)
    return declare_prior_art_boundary(**keywords)


def assessment_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "boundary": boundary(),
        "run_id": RUN_ID,
        "subject_ref": SUBJECT_REF,
        "statement_hash": STATEMENT_HASH,
        "search_completeness_certificate_id": CERTIFICATE_ID,
        "novelty_dimensions": ["MECHANISM"],
        "closest_prior_art_refs": [],
        "distinguishing_features": ["a mechanism the cited corpus does not state"],
        "assessor_ref": ASSESSOR_REF,
        "assessed_at": ASSESSED_AT,
    }
    arguments.update(overrides)
    return arguments
