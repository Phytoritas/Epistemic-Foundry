"""Evidence/holdout version and leakage-prevention integration gate (K06).

K05 sealed *which bytes* a claim rests on, *which of them the verifier may never
show a generator*, and *against what date* a novelty claim was made.  O05 built
the evolution retrieval, layered novelty and coverage-debt records that live
inside one pinned K05 snapshot.  S05 sealed the evaluator, the hidden holdout
and the leakage audit.  Each is correct alone, and none of them answers the one
question this gate exists for: are those three surfaces describing *the same
evidence/holdout version*, and does every candidate-facing operation stay inside
the visible side of it?

Nothing here re-pins evidence, re-seals a holdout, re-derives a novelty ladder,
or writes a second leakage audit.  It *composes* the sealed surfaces and refuses
the compositions that would breach a boundary none of them can see alone:

*Version binding.*  ``bind_evidence_holdout_version`` re-derives the K05
snapshot, partition, holdout and prior-art boundary through the functions that
own them, cross-checks the S05 ``VerifierFirewall`` so the holdout it guards is
the same manifest the snapshot produced — verified against the sealed record,
never asserted — and confirms the concealed partition is exactly the set the
firewall treats as leakage-bound.  A candidate-generating role that can reach
the holdout, or an access flag left open, is refused here rather than discovered
mid-run.  The result is one re-derivable version receipt binding the snapshot
bytes, the concealed set, the holdout manifest, the evaluator bundle and the
date.

*Admission against the version.*  ``admit_retrieval_against_version`` and
``admit_search_results_against_version`` refuse an O05 plan or lane receipt that
pins a *different* evidence version (stale reuse) or that names a concealed
holdout document (exposure).  ``admit_candidate_execution_against_version``
composes the S05 execution qualifier and refuses a candidate qualified against a
different evaluator version.

*Feedback as a leakage channel.*  ``admit_evaluator_feedback_against_version``
treats evaluator feedback as a possible leakage path: it drives the S05 leakage
audit over the feedback surface and refuses to admit any feedback the audit
finds intersecting the holdout, rather than letting it flow back into the
candidate or the search.

Every decision resolves to an immutable, content-addressed receipt: two runs
over equal inputs produce byte-equal receipts, so a decision is replayable
rather than merely recorded.  Nothing here scores, promotes, mutates its inputs,
or reads a clock.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...retrieval.v4_o05 import (
    RECEIPT_SCHEMA,
    AcquisitionError,
    require_plan_identity,
)
from ...security.v4_s05 import (
    ThreatControlError,
    build_leakage_audit,
    qualify_candidate_execution,
)
from ...verifier_firewall.firewall import (
    CANDIDATE_GENERATING_ROLES,
    EvaluatorDrift,
    VerifierFirewall,
)
from ..v4_k05 import (
    CorpusBoundaryError,
    holdout_handle,
    pinned_documents,
    require_boundary_identity,
    require_holdout_drawn_from_snapshot,
    require_partition_identity,
    require_snapshot_identity,
)

#: Every way this gate refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "BOUNDARY_NOT_FROM_SNAPSHOT": (
        "the prior-art boundary does not re-derive its identity or does not "
        "bound this pinned snapshot, so the date and the bytes describe two "
        "different corpora"
    ),
    "EVALUATOR_BUNDLE_DRIFT": (
        "the firewall's sealed evaluator bundle no longer hashes to its recorded "
        "digest, so the evaluator version the holdout is bound to has changed "
        "underneath the run"
    ),
    "EVALUATOR_FEEDBACK_LEAKAGE": (
        "the evaluator-feedback surface intersects the sealed holdout, so "
        "admitting it into the candidate or the search would feed a generator "
        "the material it will be judged against"
    ),
    "EXECUTION_REFUSED": (
        "the sealed S05 execution qualifier refused the candidate, and this gate "
        "surfaces that refusal instead of admitting an unqualified execution"
    ),
    "FIREWALL_HOLDOUT_MISMATCH": (
        "the firewall does not guard the holdout this snapshot produced — the "
        "manifest, its evaluator binding, or its concealed handle set differ — "
        "so the holdout identity cannot be verified against the sealed record"
    ),
    "HOLDOUT_ACCESS_OPEN": (
        "a candidate, mutation-model, prompt or backend surface can reach the "
        "hidden holdout, which lets a mutable role acquire the evaluator's own "
        "authority over the hidden material"
    ),
    "HOLDOUT_EXPOSURE": (
        "a candidate-facing operation names a document the partition conceals, "
        "so the search would touch the hidden holdout it must never see"
    ),
    "HOLDOUT_NOT_FROM_SNAPSHOT": (
        "the sealed corpus boundaries refused the holdout as not drawn from this "
        "snapshot, and this gate never re-seals a holdout to route around it"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would bind "
        "or admit against something it never validated"
    ),
    "LEAKAGE_AUDIT_REFUSED": (
        "the sealed S05 leakage audit refused the feedback surface, and this "
        "gate surfaces that refusal instead of admitting an unaudited channel"
    ),
    "PARTITION_NOT_FROM_SNAPSHOT": (
        "the partition does not re-derive its identity or was not derived from "
        "this snapshot, so the visible/hidden split being bound is not the split "
        "the snapshot was partitioned into"
    ),
    "PLAN_REFUSED": (
        "the sealed O05 retrieval surface refused the plan's own identity, and "
        "this gate never re-derives a plan to obtain an admission it was denied"
    ),
    "RECEIPT_REFUSED": (
        "the lane receipt does not validate against its canonical schema, so "
        "whether it escaped the evidence boundary is undecidable"
    ),
    "SNAPSHOT_REFUSED": (
        "the sealed corpus boundaries refused the snapshot's own identity, so "
        "the pinned evidence is not the evidence being read now"
    ),
    "STALE_EVIDENCE_VERSION": (
        "an operation binds a snapshot, boundary or evaluator version other than "
        "the one this gate bound, which reuses a stale evidence/holdout version"
    ),
    "VERSION_DRIFT": (
        "a bound version record does not re-derive its own identifier or hash, "
        "so the version being admitted against is not the version that was bound"
    ),
}

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
VERSION_ID_PREFIX = "EHV-"
RETRIEVAL_RECEIPT_PREFIX = "KRR-"
RESULTS_RECEIPT_PREFIX = "KSR-"
FEEDBACK_RECEIPT_PREFIX = "KFR-"
EXECUTION_RECEIPT_PREFIX = "KXR-"
LEAKAGE_AUDIT_ID_PREFIX = "KLA-"

#: The partition fields whose documents are concealed from a generator.  The
#: visible partition is admissible; every other partition is holdout material.
CONCEALED_DOCUMENT_FIELDS: tuple[str, ...] = (
    "adversarial_document_ids",
    "hidden_document_ids",
    "ood_document_ids",
)
CONCEALED_HANDLE_FIELDS: tuple[str, ...] = (
    "adversarial_partition_handles",
    "hidden_partition_handles",
    "ood_partition_handles",
)

#: The principal id used only to *exercise* the firewall's holdout-read denial
#: for every candidate-generating role.  It is never granted access; the probe
#: proves the separation is enforced rather than assumed.
HOLDOUT_DENIAL_PROBE = "K06-HOLDOUT-DENIAL-PROBE"


class LeakageGateError(ValueError):
    """A version binding or an admission would breach a leakage boundary."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise LeakageGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise LeakageGateError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return text


def _require_sequence(value: object, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return value  # type: ignore[return-value]


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len("sha256:") :]


def _identified(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record[id_field] = prefix + _digest_body(record)
    record[hash_field] = hash_excluding(record, hash_field)
    return record


def _derive_identity(
    record: Mapping[str, Any], prefix: str, id_field: str, hash_field: str
) -> tuple[str, str]:
    body = {
        key: value for key, value in record.items() if key not in {id_field, hash_field}
    }
    return prefix + _digest_body(body), hash_excluding(dict(record), hash_field)


def _concealed_documents(partition: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            str(document_id)
            for field in CONCEALED_DOCUMENT_FIELDS
            for document_id in partition.get(field) or []
        }
    )


def _concealed_handles(partition: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            str(handle)
            for field in CONCEALED_HANDLE_FIELDS
            for handle in partition.get(field) or []
        }
    )


# -- evidence/holdout version binding -------------------------------------


def bind_evidence_holdout_version(
    *,
    snapshot: Mapping[str, Any],
    partition: Mapping[str, Any],
    holdout: Mapping[str, Any],
    evaluator_bundle: Mapping[str, Any],
    firewall: VerifierFirewall,
    boundary: Mapping[str, Any],
    bound_at: str,
) -> dict[str, Any]:
    """Bind one authoritative evidence/holdout version from the sealed surfaces.

    Every identity is re-derived through the module that owns it: the snapshot,
    partition, holdout and boundary through K05, the evaluator/holdout binding
    through the S05 firewall.  The holdout the firewall guards is proven to be
    the manifest this snapshot produced — through the sealed bundle's own
    binding and the firewall's leakage set — rather than trusted from a label.
    A candidate-generating role that can reach the holdout is refused here.
    """
    bundle = dict(_require_mapping(evaluator_bundle, "evaluator_bundle"))
    # The diagnostic label is `holdout_manifest` rather than the bare word: the
    # bare word is a canonical enum value in other schemas, and EF4-I22 forbids
    # this module from holding it as a wire literal (mirrors K05's own labels).
    manifest = dict(_require_mapping(holdout, "holdout_manifest"))
    timestamp = _require_text(bound_at, "bound_at")

    # -- K05: re-derive the evidence bytes, the split and the date --------
    try:
        snapshot_record = require_snapshot_identity(snapshot)
    except CorpusBoundaryError as error:
        _fail(
            "SNAPSHOT_REFUSED",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    snapshot_id = str(snapshot_record["snapshot_id"])
    snapshot_hash = str(snapshot_record["snapshot_hash"])

    try:
        partition_record = require_partition_identity(partition)
    except CorpusBoundaryError as error:
        _fail(
            "PARTITION_NOT_FROM_SNAPSHOT",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    if str(partition_record.get("snapshot_id")) != snapshot_id or (
        str(partition_record.get("snapshot_hash")) != snapshot_hash
    ):
        _fail(
            "PARTITION_NOT_FROM_SNAPSHOT",
            "the partition was not derived from this pinned snapshot",
            {
                "partition_snapshot_id": partition_record.get("snapshot_id"),
                "snapshot_id": snapshot_id,
            },
        )

    try:
        manifest_record = require_holdout_drawn_from_snapshot(
            snapshot=snapshot_record, holdout=manifest
        )
    except CorpusBoundaryError as error:
        _fail(
            "HOLDOUT_NOT_FROM_SNAPSHOT",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises

    try:
        boundary_record = require_boundary_identity(boundary)
    except CorpusBoundaryError as error:
        _fail(
            "BOUNDARY_NOT_FROM_SNAPSHOT",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    if str(boundary_record.get("snapshot_id")) != snapshot_id or (
        str(boundary_record.get("corpus_snapshot_hash")) != snapshot_hash
    ):
        _fail(
            "BOUNDARY_NOT_FROM_SNAPSHOT",
            "the prior-art boundary does not bound this pinned snapshot",
            {
                "boundary_snapshot_id": boundary_record.get("snapshot_id"),
                "snapshot_id": snapshot_id,
            },
        )

    # -- S05: the firewall guards this exact holdout and evaluator --------
    manifest_hash = str(manifest_record.get("manifest_hash") or "")
    if hash_excluding(dict(manifest_record), "manifest_hash") != manifest_hash:
        _fail(
            "FIREWALL_HOLDOUT_MISMATCH",
            "the holdout manifest does not re-derive its own hash",
            {"holdout_id": manifest_record.get("holdout_id")},
        )
    if str(bundle.get("bundle_hash") or "") != firewall.sealed_hash:
        _fail(
            "FIREWALL_HOLDOUT_MISMATCH",
            "the evaluator bundle is not the bundle the firewall sealed",
            {
                "bundle_hash": bundle.get("bundle_hash"),
                "firewall_sealed_hash": firewall.sealed_hash,
            },
        )
    try:
        firewall.assert_unchanged(bundle)
    except EvaluatorDrift as error:
        _fail(
            "EVALUATOR_BUNDLE_DRIFT", str(error), {"evaluator_id": firewall.bundle_id}
        )
    if str(bundle.get("evaluator_id") or "") != firewall.bundle_id:
        _fail(
            "FIREWALL_HOLDOUT_MISMATCH",
            "the evaluator bundle names an evaluator the firewall does not guard",
            {"bundle_evaluator_id": bundle.get("evaluator_id")},
        )
    if str(bundle.get("holdout_manifest_id") or "") != str(
        manifest_record.get("holdout_id") or ""
    ) or str(bundle.get("evaluator_id") or "") != str(
        manifest_record.get("evaluator_id") or ""
    ):
        _fail(
            "FIREWALL_HOLDOUT_MISMATCH",
            "the sealed bundle does not bind this holdout manifest",
            {
                "bundle_holdout_manifest_id": bundle.get("holdout_manifest_id"),
                "holdout_id": manifest_record.get("holdout_id"),
            },
        )

    # The concealed partition must be exactly the firewall's leakage set: the
    # snapshot's whole handle universe is recomputed, and the handles the
    # firewall treats as holdout-bound must equal the handles the partition
    # conceals.  Any difference means the firewall guards a different holdout.
    pinned = pinned_documents(snapshot_record)
    universe = sorted(
        holdout_handle(snapshot_id, document_id) for document_id in pinned
    )
    concealed_handles = _concealed_handles(partition_record)
    firewall_bound = firewall.leakage_invalidates(universe)
    if firewall_bound != concealed_handles:
        _fail(
            "FIREWALL_HOLDOUT_MISMATCH",
            "the firewall's holdout-bound handles are not the concealed partition",
            {
                "concealed_partition_handles": concealed_handles,
                "firewall_bound_handles": firewall_bound,
            },
        )

    # -- authority: no mutable surface can reach the holdout --------------
    for access_field in (
        "candidate_access",
        "mutation_model_access",
        "prompt_access",
        "backend_access",
    ):
        if manifest_record.get(access_field) is not False:
            _fail(
                "HOLDOUT_ACCESS_OPEN",
                f"the holdout manifest leaves {access_field} open",
                {"access_field": access_field},
            )
    reachable = sorted(
        role
        for role in CANDIDATE_GENERATING_ROLES
        if firewall.may_read_holdout(HOLDOUT_DENIAL_PROBE, role)
    )
    if reachable:
        _fail(
            "HOLDOUT_ACCESS_OPEN",
            "candidate-generating roles can read the hidden holdout",
            {"roles": reachable},
        )

    version: dict[str, Any] = {
        "as_of_date": str(boundary_record["as_of_date"]),
        "boundary_hash": str(boundary_record["boundary_hash"]),
        "boundary_id": str(boundary_record["boundary_id"]),
        "bound_at": timestamp,
        "concealed_document_ids": _concealed_documents(partition_record),
        "concealed_partition_handles": concealed_handles,
        "corpus_snapshot_hash": snapshot_hash,
        "evaluator_bundle_hash": firewall.sealed_hash,
        "evaluator_id": firewall.bundle_id,
        "holdout_id": str(manifest_record["holdout_id"]),
        "holdout_manifest_hash": manifest_hash,
        "partition_hash": str(partition_record["partition_hash"]),
        "partition_id": str(partition_record["partition_id"]),
        "snapshot_id": snapshot_id,
        "visible_document_ids": sorted(
            str(value) for value in partition_record.get("visible_document_ids") or []
        ),
    }
    return _identified(version, VERSION_ID_PREFIX, "version_id", "version_hash")


def require_version_identity(version: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a bound version's identifier and hash from its own content."""
    record = dict(_require_mapping(version, "version"))
    derived_id, derived_hash = _derive_identity(
        record, VERSION_ID_PREFIX, "version_id", "version_hash"
    )
    if record.get("version_id") != derived_id or (
        record.get("version_hash") != derived_hash
    ):
        _fail(
            "VERSION_DRIFT",
            "the bound evidence/holdout version does not re-derive its identity",
            {
                "derived_version_hash": derived_hash,
                "derived_version_id": derived_id,
                "stated_version_id": record.get("version_id"),
            },
        )
    return record


def _require_same_version(
    version: Mapping[str, Any],
    *,
    snapshot_hash: object,
    snapshot_id: object,
    boundary_hash: object,
    boundary_id: object,
    as_of_date: object,
    label: str,
) -> None:
    """Refuse an operation pinning a different evidence version than the bound one."""
    stale = {
        field: (stated, expected)
        for field, stated, expected in (
            (
                "corpus_snapshot_hash",
                str(snapshot_hash),
                version["corpus_snapshot_hash"],
            ),
            ("snapshot_id", str(snapshot_id), version["snapshot_id"]),
            ("boundary_hash", str(boundary_hash), version["boundary_hash"]),
            ("boundary_id", str(boundary_id), version["boundary_id"]),
            ("as_of_date", str(as_of_date), version["as_of_date"]),
        )
        if stated != str(expected)
    }
    if stale:
        _fail(
            "STALE_EVIDENCE_VERSION",
            f"the {label} pins a different evidence/holdout version than the bound one",
            {"bound_version_id": version["version_id"], "differences": stale},
        )


def _require_no_exposure(
    version: Mapping[str, Any], document_ids: Sequence[str], *, label: str
) -> list[str]:
    """Refuse any document the bound partition conceals."""
    concealed = set(version["concealed_document_ids"])
    exposed = sorted({str(value) for value in document_ids} & concealed)
    if exposed:
        _fail(
            "HOLDOUT_EXPOSURE",
            f"the {label} names documents the partition conceals",
            {"document_ids": exposed, "version_id": version["version_id"]},
        )
    return exposed


# -- admission against the bound version ----------------------------------


def admit_retrieval_against_version(
    *, version: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Admit an O05 retrieval plan only against its own bound evidence version.

    The plan's identity is re-derived through the O05 surface that owns it, its
    evidence version is required to be the bound one, and a subject the
    partition conceals is refused as holdout exposure.  The receipt is
    re-derivable, so the admission is a replayable decision, not a note.
    """
    bound = require_version_identity(version)
    try:
        plan_record = require_plan_identity(plan)
    except AcquisitionError as error:
        _fail(
            "PLAN_REFUSED",
            str(error),
            {"retrieval_finding_code": error.code, "retrieval_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises

    _require_same_version(
        bound,
        snapshot_hash=plan_record.get("corpus_snapshot_hash"),
        snapshot_id=plan_record.get("snapshot_id"),
        boundary_hash=plan_record.get("boundary_hash"),
        boundary_id=plan_record.get("boundary_id"),
        as_of_date=plan_record.get("as_of_date"),
        label="retrieval plan",
    )
    subjects = [str(value) for value in plan_record.get("subject_document_ids") or []]
    _require_no_exposure(bound, subjects, label="retrieval plan")

    # The gate tag is `evidence_retrieval` rather than the bare word: the bare
    # word is a canonical enum value in other schemas, and EF4-I22 forbids this
    # module from holding it as a wire literal.
    receipt: dict[str, Any] = {
        "admitted_subject_document_ids": sorted(subjects),
        "gate": "evidence_retrieval",
        "plan_hash": str(plan_record["plan_hash"]),
        "plan_id": str(plan_record["plan_id"]),
        "version_hash": str(bound["version_hash"]),
        "version_id": str(bound["version_id"]),
    }
    return _identified(receipt, RETRIEVAL_RECEIPT_PREFIX, "receipt_id", "receipt_hash")


def admit_search_results_against_version(
    *, version: Mapping[str, Any], receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Admit an O05 lane receipt's results against the bound evidence version.

    The receipt must validate against its canonical schema, must pin the bound
    snapshot when it pins one at all, and must not return a document the
    partition conceals — the case of a search escaping into the hidden holdout
    while it ran.
    """
    bound = require_version_identity(version)
    lane_receipt = dict(_require_mapping(receipt, "receipt"))
    try:
        validate_artifact(RECEIPT_SCHEMA, lane_receipt)
    except ContractViolation as error:
        _fail(
            "RECEIPT_REFUSED",
            str(error),
            {"errors": list(error.errors), "lane": lane_receipt.get("lane")},
        )

    # A sentinel receipt pins no snapshot; an execution receipt does, and it
    # must be the bound one.  Comparing only when present keeps a truthful
    # "never looked" sentinel from being read as a stale-version reuse.
    receipt_snapshot_hash = lane_receipt.get("corpus_snapshot_hash")
    if receipt_snapshot_hash is not None and str(receipt_snapshot_hash) != str(
        bound["corpus_snapshot_hash"]
    ):
        _fail(
            "STALE_EVIDENCE_VERSION",
            "the lane receipt pins a different snapshot than the bound version",
            {
                "bound_version_id": bound["version_id"],
                "receipt_snapshot_hash": receipt_snapshot_hash,
            },
        )
    results = [str(value) for value in lane_receipt.get("result_ids") or []]
    _require_no_exposure(bound, results, label="lane receipt")

    admission: dict[str, Any] = {
        "admitted_result_ids": sorted(results),
        "gate": "search_results",
        "lane": str(lane_receipt["lane"]),
        "receipt_hash": str(lane_receipt["receipt_hash"]),
        "source_receipt_id": str(lane_receipt["receipt_id"]),
        "version_hash": str(bound["version_hash"]),
        "version_id": str(bound["version_id"]),
    }
    return _identified(
        admission, RESULTS_RECEIPT_PREFIX, "receipt_id", "admission_hash"
    )


def admit_candidate_execution_against_version(
    *,
    version: Mapping[str, Any],
    firewall: VerifierFirewall,
    candidate_kind: str,
    target_manifest: Mapping[str, Any],
    hard_limits: Mapping[str, Any],
    effect_receipt_channel_id: str,
    qualification_id: str | None = None,
) -> dict[str, Any]:
    """Admit a candidate execution only under the bound evaluator version.

    The firewall is required to be the one the version bound, so a candidate
    cannot be qualified against a fresher or staler evaluator than the holdout
    it will be judged on.  The qualification itself — including the live probe
    that no candidate-generating role can read the holdout — is the sealed S05
    gate's; a refusal from it is surfaced, never worked around.
    """
    bound = require_version_identity(version)
    if firewall.sealed_hash != str(bound["evaluator_bundle_hash"]):
        _fail(
            "STALE_EVIDENCE_VERSION",
            "the firewall guards a different evaluator version than the bound one",
            {
                "bound_evaluator_bundle_hash": bound["evaluator_bundle_hash"],
                "firewall_sealed_hash": firewall.sealed_hash,
            },
        )
    try:
        qualification = qualify_candidate_execution(
            candidate_kind=_require_text(candidate_kind, "candidate_kind"),
            target_manifest=dict(_require_mapping(target_manifest, "target_manifest")),
            hard_limits=dict(_require_mapping(hard_limits, "hard_limits")),
            effect_receipt_channel_id=_require_text(
                effect_receipt_channel_id, "effect_receipt_channel_id"
            ),
            firewall=firewall,
            holdout_read_probe_principal=HOLDOUT_DENIAL_PROBE,
            qualification_id=qualification_id,
        )
    except ThreatControlError as error:
        _fail(
            "EXECUTION_REFUSED",
            str(error),
            {"threat_finding_code": error.code, "threat_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises

    admission: dict[str, Any] = {
        "candidate_kind": str(qualification["candidate_kind"]),
        "evaluator_bundle_hash": str(bound["evaluator_bundle_hash"]),
        "gate": "candidate_execution",
        "qualification_hash": str(qualification["qualification_hash"]),
        "qualification_id": str(qualification["qualification_id"]),
        "version_hash": str(bound["version_hash"]),
        "version_id": str(bound["version_id"]),
    }
    return _identified(
        admission, EXECUTION_RECEIPT_PREFIX, "receipt_id", "admission_hash"
    )


def admit_evaluator_feedback_against_version(
    *,
    version: Mapping[str, Any],
    firewall: VerifierFirewall,
    run_or_bundle_id: str,
    feedback_artifact_ids: Sequence[str],
    surfaces_checked: Sequence[str],
    access_log_artifact_id: str,
    similarity_alerts: Sequence[str] = (),
) -> dict[str, Any]:
    """Refuse evaluator feedback that the sealed leakage audit finds leaking.

    Evaluator feedback is treated as a possible leakage channel: the S05 audit
    is driven over the feedback surface, and any feedback the audit finds
    intersecting the holdout is refused rather than allowed to flow back into
    the candidate or the search.  A clean audit is embedded in the receipt so
    the admitted feedback carries the evidence of its own clearance.
    """
    bound = require_version_identity(version)
    if firewall.sealed_hash != str(bound["evaluator_bundle_hash"]):
        _fail(
            "STALE_EVIDENCE_VERSION",
            "the firewall guards a different evaluator version than the bound one",
            {
                "bound_evaluator_bundle_hash": bound["evaluator_bundle_hash"],
                "firewall_sealed_hash": firewall.sealed_hash,
            },
        )
    observed = [
        _require_text(value, f"feedback_artifact_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(feedback_artifact_ids, "feedback_artifact_ids")
        )
    ]
    # A deterministic audit id keeps the receipt re-derivable: the S05 builder
    # would otherwise mint a random one, and a random field cannot be replayed.
    audit_id = LEAKAGE_AUDIT_ID_PREFIX + _digest_body(
        {
            "feedback_artifact_ids": sorted(observed),
            "run_or_bundle_id": str(run_or_bundle_id),
            "version_id": str(bound["version_id"]),
        }
    )
    try:
        audit = build_leakage_audit(
            firewall=firewall,
            run_or_bundle_id=_require_text(run_or_bundle_id, "run_or_bundle_id"),
            surfaces_checked=list(surfaces_checked),
            observed_artifact_ids=observed,
            access_log_artifact_id=_require_text(
                access_log_artifact_id, "access_log_artifact_id"
            ),
            similarity_alerts=list(similarity_alerts),
            leakage_audit_id=audit_id,
        )
    except ThreatControlError as error:
        _fail(
            "LEAKAGE_AUDIT_REFUSED",
            str(error),
            {"threat_finding_code": error.code, "threat_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises

    if audit["detected_exposures"]:
        _fail(
            "EVALUATOR_FEEDBACK_LEAKAGE",
            "the evaluator feedback surface intersects the sealed holdout",
            {
                "detected_exposures": list(audit["detected_exposures"]),
                "leakage_audit_id": str(audit["leakage_audit_id"]),
                "version_id": str(bound["version_id"]),
            },
        )

    admission: dict[str, Any] = {
        "admitted_feedback_artifact_ids": sorted(observed),
        "gate": "evaluator_feedback",
        "leakage_audit": dict(audit),
        "leakage_audit_id": str(audit["leakage_audit_id"]),
        "version_hash": str(bound["version_hash"]),
        "version_id": str(bound["version_id"]),
    }
    return _identified(
        admission, FEEDBACK_RECEIPT_PREFIX, "receipt_id", "admission_hash"
    )
