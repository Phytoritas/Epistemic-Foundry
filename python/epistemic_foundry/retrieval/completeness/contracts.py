"""O04 absence-claim and search-completeness gate contracts.

The gate closes the O-phase: an absence or novelty claim exists only as a
sealed artifact bound to a deterministically recomputed
``SearchCompletenessCertificate`` (EF4-I04/I05), and a ``FAILED``, ``BLOCKED``,
or ``UNSEARCHED`` lane is ignorance, never zero evidence.  ``PARTIAL`` lanes
support only scope-bounded claims at a demoted ceiling.  Every derived value
is a pure function of validated inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from ..planning.contracts import (
    CANONICAL_LANES,
    Lane,
    SearchState,
    validate_search_completeness_certificate,
)
from ..planning.contracts import SealedArtifact as PlanningSealedArtifact

RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")

ABSENCE_CEILINGS: Final = (
    "NONE",
    "LOCAL_CORPUS_ONLY",
    "CORPUS_CONDITIONAL",
    "EXTERNAL_CONDITIONAL",
)
NOVELTY_CEILINGS: Final = (
    "NOT_ASSESSED",
    "CORPUS_NOVEL_ONLY",
    "SEARCH_CONDITIONAL",
    "PRIOR_ART_FOUND",
)
CLAIM_KINDS: Final = ("ABSENCE", "NOVELTY")
CLAIM_CLASSES: Final = ("FULL_SCOPE", "SCOPE_BOUNDED")

#: Lane evidence classification for zero-evidence accounting: only a fully
#: executed empty search is zero evidence; everything else is ignorance.
ZERO_EVIDENCE_STATES: Final = frozenset({SearchState.SEARCHED_NONE.value})
IGNORANCE_STATES: Final = frozenset(
    {
        SearchState.UNSEARCHED.value,
        SearchState.PARTIAL.value,
        SearchState.BLOCKED.value,
        SearchState.FAILED.value,
    }
)

_CLAIM_FIELDS: Final = frozenset(
    {
        "claim_id",
        "run_id",
        "certificate_id",
        "certificate_hash",
        "claim_kind",
        "claim_class",
        "lane",
        "scope_id",
        "statement",
        "ceiling",
        "lane_reconciled_state",
        "created_at",
        "claim_hash",
    }
)

_PARTIAL_CEILING_DEMOTION: Final = MappingProxyType(
    {
        "NONE": "NONE",
        "LOCAL_CORPUS_ONLY": "LOCAL_CORPUS_ONLY",
        "CORPUS_CONDITIONAL": "LOCAL_CORPUS_ONLY",
        "EXTERNAL_CONDITIONAL": "LOCAL_CORPUS_ONLY",
    }
)


class CompletenessGateError(ValueError):
    """Typed fail-closed O04 gate error."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.run_status = "FAIL"
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise CompletenessGateError(code, message, details)


@dataclass(frozen=True, slots=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, object]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CompletenessGateError(
            "CANONICAL_JSON_INVALID",
            "value must be finite canonical UTF-8 JSON",
        ) from error


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_excluding(payload: Mapping[str, object], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    return value.strip()


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str or RFC3339_PATTERN.fullmatch(value) is None:
        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompletenessGateError(
            "TIMESTAMP_INVALID", f"{label} is not a real timestamp"
        ) from error
    return value


def _lane(value: object) -> str:
    if type(value) is not str:
        _fail("LANE_UNKNOWN", "lane must be a canonical lane")
    try:
        return Lane(value).value
    except ValueError as error:
        raise CompletenessGateError(
            "LANE_UNKNOWN", f"{value!r} is not a canonical lane"
        ) from error


def _certificate_payload(
    query_plan: Mapping[str, Any] | PlanningSealedArtifact,
    receipts: Sequence[Mapping[str, Any] | PlanningSealedArtifact],
    certificate: Mapping[str, Any] | PlanningSealedArtifact,
) -> dict[str, Any]:
    """Recompute the certificate through the O01 public API before any claim."""

    payload = (
        certificate.payload
        if isinstance(certificate, PlanningSealedArtifact)
        else dict(certificate)
    )
    return validate_search_completeness_certificate(
        query_plan, receipts, payload
    ).payload


def _reconciliation(certificate: Mapping[str, Any], lane: str) -> dict[str, Any]:
    for row in certificate["lane_reconciliations"]:  # type: ignore[union-attr]
        if row.get("lane") == lane:  # type: ignore[union-attr]
            return dict(row)  # type: ignore[arg-type]
    raise AssertionError("certificate reconciliation is missing a canonical lane")


def lane_evidence_classification(certificate: Mapping[str, Any]) -> dict[str, str]:
    """Classify every lane as EVIDENCE / ZERO_EVIDENCE / IGNORANCE.

    A ``FAILED``, ``BLOCKED``, ``PARTIAL``, or ``UNSEARCHED`` lane is
    classified as ignorance and can never be counted as zero evidence.
    """

    classification: dict[str, str] = {}
    for lane in CANONICAL_LANES:
        state = str(_reconciliation(certificate, lane)["reconciled_state"])
        if state == SearchState.SEARCHED_WITH_RESULTS.value:
            classification[lane] = "EVIDENCE"
        elif state in ZERO_EVIDENCE_STATES:
            classification[lane] = "ZERO_EVIDENCE"
        else:
            classification[lane] = "IGNORANCE"
    return classification


def zero_evidence_report(
    query_plan: Mapping[str, Any] | PlanningSealedArtifact,
    receipts: Sequence[Mapping[str, Any] | PlanningSealedArtifact],
    certificate: Mapping[str, Any] | PlanningSealedArtifact,
) -> dict[str, Any]:
    """Deterministic gate report separating zero evidence from ignorance."""

    payload = _certificate_payload(query_plan, receipts, certificate)
    classification = lane_evidence_classification(payload)
    return {
        "certificate_hash": payload["certificate_hash"],
        "evidence_lanes": sorted(
            lane for lane, kind in classification.items() if kind == "EVIDENCE"
        ),
        "ignorance_lanes": sorted(
            lane for lane, kind in classification.items() if kind == "IGNORANCE"
        ),
        "lane_classification": classification,
        "run_id": payload["run_id"],
        "zero_evidence_lanes": sorted(
            lane for lane, kind in classification.items() if kind == "ZERO_EVIDENCE"
        ),
    }


def seal_absence_claim(
    query_plan: Mapping[str, Any] | PlanningSealedArtifact,
    receipts: Sequence[Mapping[str, Any] | PlanningSealedArtifact],
    certificate: Mapping[str, Any] | PlanningSealedArtifact,
    *,
    lane: str,
    statement: str,
    created_at: str,
    scope_id: str | None = None,
) -> SealedArtifact:
    """Seal an absence or novelty claim bound to its recomputed certificate.

    The claim kind derives from the lane: ``external_novelty`` seals a
    NOVELTY claim under ``novelty_claim_ceiling``; every other lane seals an
    ABSENCE claim under ``absence_claim_ceiling``.
    """

    payload = _certificate_payload(query_plan, receipts, certificate)
    lane = _lane(lane)
    statement = _text(statement, "statement")
    created_at = _timestamp(created_at, "created_at")
    if scope_id is not None:
        scope_id = _text(scope_id, "scope_id")

    reconciliation = _reconciliation(payload, lane)
    state = str(reconciliation["reconciled_state"])
    claim_kind = "NOVELTY" if lane == Lane.EXTERNAL_NOVELTY.value else "ABSENCE"

    if state in {
        SearchState.UNSEARCHED.value,
        SearchState.BLOCKED.value,
        SearchState.FAILED.value,
    }:
        _fail(
            "ABSENCE_WITHOUT_SEARCH",
            f"a {state} lane is ignorance and cannot ground a {claim_kind.lower()} claim",
            {"lane": lane, "reconciled_state": state},
        )
    if state == SearchState.SEARCHED_WITH_RESULTS.value and claim_kind == "ABSENCE":
        _fail(
            "ABSENCE_CONTRADICTED",
            "the lane returned results; an absence claim would contradict the record",
            {"lane": lane},
        )

    executed_scopes = [str(entry) for entry in reconciliation["executed_scope_ids"]]
    unsearched_scopes = [str(entry) for entry in reconciliation["unsearched_scope_ids"]]
    if scope_id is not None:
        if scope_id not in executed_scopes:
            _fail(
                "SCOPE_NOT_EXECUTED",
                "the claimed scope was not executed in this lane",
                {"lane": lane, "scope_id": scope_id},
            )
        claim_class = "SCOPE_BOUNDED"
    else:
        if state == SearchState.PARTIAL.value:
            _fail(
                "PARTIAL_REQUIRES_SCOPE_BOUND",
                "a PARTIAL lane supports only scope-bounded claims",
                {"lane": lane, "unsearched_scope_ids": unsearched_scopes},
            )
        if unsearched_scopes:
            _fail(
                "SCOPE_NOT_EXECUTED",
                "the lane retains unsearched scope; a full-scope claim is forbidden",
                {"lane": lane, "unsearched_scope_ids": unsearched_scopes},
            )
        claim_class = "FULL_SCOPE"

    if claim_kind == "NOVELTY":
        ceiling = str(payload["novelty_claim_ceiling"])
        if ceiling == "PRIOR_ART_FOUND":
            _fail(
                "NOVELTY_CONTRADICTED",
                "prior art was found; a novelty claim would contradict the record",
            )
        if ceiling == "NOT_ASSESSED":
            _fail(
                "NOVELTY_NOT_ASSESSED",
                "the external novelty lane was not assessed; no novelty claim exists",
            )
    else:
        ceiling = str(payload["absence_claim_ceiling"])
        if ceiling == "NONE":
            _fail(
                "ABSENCE_CEILING_NONE",
                "the certificate grants no absence-claim ceiling",
            )
        if state == SearchState.PARTIAL.value or claim_class == "SCOPE_BOUNDED":
            ceiling = _PARTIAL_CEILING_DEMOTION.get(ceiling, "LOCAL_CORPUS_ONLY")

    claim: dict[str, Any] = {
        "run_id": payload["run_id"],
        "certificate_id": payload["certificate_id"],
        "certificate_hash": payload["certificate_hash"],
        "claim_kind": claim_kind,
        "claim_class": claim_class,
        "lane": lane,
        "scope_id": scope_id,
        "statement": statement,
        "ceiling": ceiling,
        "lane_reconciled_state": state,
        "created_at": created_at,
    }
    claim["claim_id"] = (
        "ACL-"
        + hashlib.sha256(
            _canonical_json(
                {
                    "certificate_hash": claim["certificate_hash"],
                    "claim_kind": claim_kind,
                    "lane": lane,
                    "scope_id": scope_id,
                    "statement": statement,
                }
            )
        ).hexdigest()
    )
    claim["claim_hash"] = _hash_excluding(claim, "claim_hash")
    return SealedArtifact("AbsenceClaim", _canonical_json(claim))


def validate_absence_claim(
    claim: Mapping[str, Any],
    query_plan: Mapping[str, Any] | PlanningSealedArtifact,
    receipts: Sequence[Mapping[str, Any] | PlanningSealedArtifact],
    certificate: Mapping[str, Any] | PlanningSealedArtifact,
) -> SealedArtifact:
    """Recompute the claim from its bound run and require exact identity."""

    if not isinstance(claim, Mapping):
        _fail("INPUT_INVALID", "claim must be an object")
    value = dict(claim)
    missing = sorted(_CLAIM_FIELDS - set(value))
    unknown = sorted(set(value) - _CLAIM_FIELDS)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            "AbsenceClaim field set is not canonical",
            {"missing": missing, "unknown": unknown},
        )
    if value["claim_kind"] not in CLAIM_KINDS:
        _fail("INPUT_INVALID", "claim_kind is not canonical")
    if value["claim_class"] not in CLAIM_CLASSES:
        _fail("INPUT_INVALID", "claim_class is not canonical")
    asserted_hash = value["claim_hash"]
    if (
        type(asserted_hash) is not str
        or SHA256_PATTERN.fullmatch(asserted_hash) is None
    ):
        _fail("HASH_FORMAT_INVALID", "claim_hash must be sha256:<64 lowercase hex>")
    if asserted_hash != _hash_excluding(value, "claim_hash"):
        _fail("CLAIM_HASH_MISMATCH", "claim_hash does not match canonical content")
    rebuilt = seal_absence_claim(
        query_plan,
        receipts,
        certificate,
        lane=str(value["lane"]),
        statement=str(value["statement"]),
        created_at=str(value["created_at"]),
        scope_id=value["scope_id"]
        if value["scope_id"] is None
        else str(value["scope_id"]),
    )
    if rebuilt.canonical_bytes != _canonical_json(value):
        _fail(
            "CLAIM_RECONSTRUCTION_MISMATCH",
            "the claim is not the deterministic reconstruction of its bound run",
        )
    return rebuilt


def assert_pack_consistent_with_ignorance(
    pack: Mapping[str, Any],
    query_plan: Mapping[str, Any] | PlanningSealedArtifact,
    receipts: Sequence[Mapping[str, Any] | PlanningSealedArtifact],
    certificate: Mapping[str, Any] | PlanningSealedArtifact,
) -> dict[str, Any]:
    """Gate an EvidencePack: an ignorance lane can never look complete-empty.

    For the adversarial lanes (counterevidence, null, boundary, method,
    external novelty), a ``FAILED``/``BLOCKED``/``PARTIAL``/``UNSEARCHED``
    reconciliation must surface as an incomplete pack lane; an empty pack
    list with ``*_lane_complete=true`` over an ignorance lane is the exact
    "failed lane counted as zero evidence" defect this gate exists to stop.
    """

    payload = _certificate_payload(query_plan, receipts, certificate)
    if not isinstance(pack, Mapping):
        _fail("INPUT_INVALID", "pack must be an object")
    if pack.get("completeness_certificate_hash") != payload["certificate_hash"]:
        _fail(
            "PACK_CERTIFICATE_MISMATCH",
            "the pack does not bind the recomputed completeness certificate",
        )
    classification = lane_evidence_classification(payload)
    completeness = pack.get("completeness")
    if not isinstance(completeness, Mapping):
        _fail("INPUT_INVALID", "pack.completeness must be an object")
    lane_bindings = (
        (Lane.COUNTEREVIDENCE.value, "counter_lane_complete"),
        (Lane.NULL.value, "null_lane_complete"),
        (Lane.BOUNDARY.value, "boundary_lane_complete"),
        (Lane.METHOD.value, "method_lane_complete"),
        (Lane.EXTERNAL_NOVELTY.value, "novelty_lane_complete"),
    )
    violations: list[dict[str, object]] = []
    for lane, complete_field in lane_bindings:
        if classification[lane] != "IGNORANCE":
            continue
        if bool(completeness.get(complete_field)):
            violations.append(
                {
                    "completeness_field": complete_field,
                    "lane": lane,
                    "reason": "ignorance lane reported as complete",
                }
            )
    if violations:
        _fail(
            "IGNORANCE_COUNTED_AS_ZERO_EVIDENCE",
            "a failed, blocked, partial, or unsearched lane cannot be complete",
            {"violations": violations},
        )
    return {
        "certificate_hash": payload["certificate_hash"],
        "lane_classification": classification,
        "status": "PASS",
    }
