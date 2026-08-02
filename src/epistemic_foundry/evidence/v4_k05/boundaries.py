"""Corpus snapshot pinning, hidden-holdout and prior-art boundaries (K05).

K04 proved that ingested corpus material can be scanned, quality-gated and
refused.  It did not answer the three questions this module exists for: *which
bytes* was a claim assessed against, *which of them may the verifier never
show a generator*, and *against what search scope and what date* was a novelty
claim actually made.  Without those three boundaries a corpus is a moving
target: the evidence a claim cited can be edited underneath it, a generator can
be handed the material it will be judged on, and "novel" can quietly mean
"nobody looked".

Three records do the work, and each one is content-addressed so that its
identity cannot be separated from what it contains.

*Corpus snapshot pinning.*  Every source document is bound by content hash, a
declared license and a declared date; a document missing any of the three is
refused rather than pinned, and the same document id carrying two different
hashes is refused because a snapshot cannot hold two versions of one thing.
The snapshot id is *derived* from the sorted content hashes, so the identity is
the content: two pins over the same bytes collide by construction, and a
re-validation that recomputes the id and the per-document hashes detects drift
instead of trusting the record's own label.

*Hidden holdout boundary.*  A pinned snapshot is partitioned into visible,
hidden, OOD and adversarial parts, and the hidden side is sealed through the
Verifier Firewall's own ``build_holdout_manifest`` rather than a second
manifest writer.  A document appearing in both the visible and the hidden
partition is refused as leakage by construction — that is the failure the
firewall cannot see, because by the time it holds the manifest the overlap has
already been laundered into two handle lists.  Handles are derived from the
snapshot, so a holdout naming a handle the snapshot cannot produce is refused.

*Prior-art boundary.*  A novelty claim names exactly one snapshot and one
as-of date, and the assessment refuses a prior-art reference the boundary does
not contain or one dated after the bound.  The status this module can emit is
capped below the top of both canonical ladders: a corpus-bounded search is
evidence about a corpus, never about the world.

Nothing here invents vocabulary.  License, integrity-status, novelty-status,
promotion-ceiling and novelty-dimension values are read from the canonical
schemas that declare them — positionally, and for one field by declaration
order rather than by name, because that field's *name* is itself a canonical
enum value elsewhere and holding it would be the EF4-I22 violation this module
is required to avoid.  Nothing here scores, promotes, or reads a clock.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from ...contracts import default_registry, validate_artifact
from ...domain.hashing import (
    SHA256_PREFIX,
    hash_excluding,
    is_schema_digest,
    sha256_of_payload,
)
from ...verifier_firewall.firewall import FirewallRefusal, build_holdout_manifest

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "AS_OF_UNDECLARED": (
        "a prior-art boundary was declared without a parseable as-of date, so "
        "nothing would bound how recent the searched material may be"
    ),
    "BOUNDARY_DRIFT": (
        "the prior-art boundary does not re-derive its own identifier or hash, "
        "so the searched scope it claims is not the scope it records"
    ),
    "CONTENT_HASH_MISSING": (
        "a source document carries no canonical content hash, and a document "
        "that is not bound to bytes can be edited underneath every claim citing it"
    ),
    "DOCUMENT_DATE_MISSING": (
        "a source document declares no date, so no prior-art boundary could ever "
        "decide whether it falls inside or outside an as-of bound"
    ),
    "DOCUMENT_HASH_CONFLICT": (
        "one document identifier carries two different content hashes, which "
        "means the snapshot would pin two versions of the same thing at once"
    ),
    "DOCUMENT_UNPINNED": (
        "a partition, holdout or boundary names a document the pinned snapshot "
        "does not contain, so the record reaches outside the evidence it declares"
    ),
    "HOLDOUT_CONTENT_UNPINNED": (
        "the holdout binds a content hash the pinned snapshot never contained, "
        "so the hidden material is not drawn from the evidence under assessment"
    ),
    "HOLDOUT_HANDLE_UNPINNED": (
        "the holdout names a partition handle this snapshot cannot derive, so "
        "the hidden partition is not a partition of the pinned corpus at all"
    ),
    "HOLDOUT_SEAL_REFUSED": (
        "the Verifier Firewall refused to seal the holdout manifest, and this "
        "module never writes a second manifest to route around that refusal"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "pin, partition or assess against something it never validated"
    ),
    "LICENSE_UNDECLARED": (
        "a source document declares no usable license status, and unlicensed "
        "material may not be pinned into evidence a claim will rest on"
    ),
    "NOVELTY_DIMENSION_UNDECLARED": (
        "the assessment names a novelty dimension outside the canonical "
        "vocabulary, which would report novelty on an axis nothing defines"
    ),
    "PARTITION_DRIFT": (
        "the partition does not re-derive its own identifier or hash, so the "
        "split being sealed is not the split that was reviewed"
    ),
    "PARTITION_INCOMPLETE": (
        "the partition does not account for every pinned document, and an "
        "unassigned document has no declared visibility to any role"
    ),
    "PARTITION_LEAKAGE": (
        "a document appears in both the visible and the hidden partition, which "
        "hands a generator the material the verifier will judge it against"
    ),
    "PARTITION_OVERLAP": (
        "one document was assigned to two partitions, so its visibility depends "
        "on which list a reader happens to consult first"
    ),
    "PRIOR_ART_AFTER_AS_OF": (
        "a novelty claim cites prior art dated after its own as-of bound, which "
        "assesses a claim against material the declared search never covered"
    ),
    "PRIOR_ART_OUTSIDE_BOUNDARY": (
        "a novelty claim cites a document the declared boundary does not "
        "contain, so the citation cannot be checked against the searched scope"
    ),
    "SEARCH_SCOPE_UNDECLARED": (
        "a prior-art boundary names no searched source, and an unnamed search "
        "scope turns every novelty statement into an unfalsifiable one"
    ),
    "SNAPSHOT_DRIFT": (
        "the snapshot does not re-derive its own identifier, hash or content "
        "hashes, so the pinned evidence is not the evidence being read now"
    ),
    "SNAPSHOT_EMPTY": (
        "a snapshot or boundary holding no document at all cannot ground any "
        "claim, and pinning emptiness would record evidence that does not exist"
    ),
}

#: Identifier prefixes.  Every identifier this module mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
SNAPSHOT_ID_PREFIX = "CSNAP-"
PARTITION_ID_PREFIX = "CPART-"
HOLDOUT_ID_PREFIX = "HOK-"
HANDLE_ID_PREFIX = "HH-"
REPORT_ID_PREFIX = "SIR-"
BOUNDARY_ID_PREFIX = "PAB-"
ASSESSMENT_ID_PREFIX = "NVA-"

#: Handles are shortened digests: long enough that a collision is not a
#: practical forgery route, short enough to stay an opaque handle rather than
#: something a reader mistakes for a content hash.
HANDLE_DIGEST_LENGTH = 32

#: The fields a pinned document carries.  `source_uri` is optional at the input
#: and normalized to `None`, because a document may legitimately have no
#: retrievable location while still being bound by hash.
DOCUMENT_FIELDS: tuple[str, ...] = (
    "content_hash",
    "document_id",
    "license_status",
    "source_date",
    "source_uri",
)

#: Position of the license value that declares nothing.  The canonical
#: vocabulary is ordered from the most explicit grant to the absence of one, so
#: the final member is the "no license was established" case; the
#: schema-and-type suite asserts that ordering against the schema text.
UNDECLARED_LICENSE_POSITION = -1

#: Positions in the integrity-status vocabularies.  The check vocabulary is
#: declared best-to-worst and the overall vocabulary shares its first three
#: members, so index 0 is the clean outcome, index 2 the failed one and index 3
#: the not-run one.  Every position is asserted against the schema.
INTEGRITY_PASS_POSITION = 0
INTEGRITY_FAIL_POSITION = 2
INTEGRITY_NOT_RUN_POSITION = 3

#: Novelty-status position -> promotion-ceiling position.  Index 1 of the
#: status ladder is "prior art was found", index 2 "novel within this corpus
#: only" and index 3 "novel conditional on the declared search".  The top of
#: each ladder is deliberately unreachable from here: a corpus-bounded search
#: cannot certify that nothing outside the corpus exists, and this module must
#: not let a bounded search read as an unbounded one.
NOVELTY_LADDER: dict[int, int] = {1: 0, 2: 1, 3: 2}
PRIOR_ART_FOUND_POSITION = 1
CORPUS_BOUNDED_POSITION = 2
SEARCH_BOUNDED_POSITION = 3

#: The two schemas whose enum-valued scalar properties are selected by
#: declaration order rather than by name.  `novelty-assessment` declares a
#: field whose *name* is itself a canonical enum value elsewhere, so naming it
#: here would be the duplicated wire literal EF4-I22 forbids; the order is
#: asserted against the schema by the schema-and-type suite.
NOVELTY_SCHEMA = "novelty-assessment"
NOVELTY_STATUS_POSITION = 0
PROMOTION_CEILING_POSITION = 1


class CorpusBoundaryError(ValueError):
    """A pin, partition, seal or novelty assessment would breach a boundary."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise CorpusBoundaryError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise CorpusBoundaryError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return text


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len(SHA256_PREFIX) :]


# -- declared vocabularies ------------------------------------------------


def license_vocabulary() -> tuple[str, ...]:
    """License statuses, read from the schema that declares a document."""
    document = default_registry().document("document-manifest")
    return tuple(document["properties"]["license_status"]["enum"])


def integrity_check_vocabulary() -> tuple[str, ...]:
    """Per-check statuses, read from the integrity report's own schema."""
    document = default_registry().document("source-integrity-report")
    return tuple(
        document["properties"]["checks"]["items"]["properties"]["status"]["enum"]
    )


def integrity_overall_vocabulary() -> tuple[str, ...]:
    """Overall integrity statuses, read from the integrity report's schema."""
    document = default_registry().document("source-integrity-report")
    return tuple(document["properties"]["overall_status"]["enum"])


def novelty_dimension_vocabulary() -> tuple[str, ...]:
    """Novelty dimensions, read from the assessment's own schema."""
    document = default_registry().document(NOVELTY_SCHEMA)
    return tuple(document["properties"]["novelty_dimensions"]["items"]["enum"])


def scalar_enum_field(schema_name: str, position: int) -> tuple[str, tuple[str, ...]]:
    """Return the name and members of a schema's `position`-th enum property.

    Properties that declare an ``enum`` directly are taken in the schema's own
    declaration order.  This exists so a vocabulary can be read without this
    module holding the *field name* as a literal: one of the fields it needs is
    named by a token that is a canonical enum value in another schema, and
    restating it here is precisely the drift EF4-I22 forbids.
    """
    document = default_registry().document(schema_name)
    fields = [
        (str(name), tuple(spec["enum"]))
        for name, spec in document["properties"].items()
        if isinstance(spec, dict) and isinstance(spec.get("enum"), list)
    ]
    if not -len(fields) <= position < len(fields):
        _fail(
            "INPUT_INVALID",
            f"{schema_name} declares no enum property at position {position}",
            {"declared": [name for name, _ in fields], "position": position},
        )
    return fields[position]


# -- corpus snapshot pinning ----------------------------------------------


def snapshot_id_for(content_hashes: Sequence[str]) -> str:
    """A snapshot's identity is its content, so the id is derived, never chosen.

    Two pins over the same bytes therefore produce the same id, and a record
    whose id disagrees with the hashes it carries is detectable as forged.
    """
    ordered = sorted({str(value) for value in content_hashes})
    if not ordered:
        _fail("SNAPSHOT_EMPTY", "a snapshot identity needs at least one content hash")
    return SNAPSHOT_ID_PREFIX + _digest_body(ordered)


def _iso_date(value: object, label: str, code: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        _fail(
            code,
            f"{label} must be an ISO calendar date",
            {"label": label, "value": value},
        )
        return ""
    return parsed.isoformat()


def _pin_document(candidate: object, label: str) -> dict[str, Any]:
    record = _require_mapping(candidate, label)
    document_id = _require_text(record.get("document_id"), f"{label}.document_id")
    content_hash = str(record.get("content_hash") or "")
    if not is_schema_digest(content_hash):
        _fail(
            "CONTENT_HASH_MISSING",
            f"{document_id} carries no canonical content hash",
            {"content_hash": record.get("content_hash"), "document_id": document_id},
        )
    vocabulary = license_vocabulary()
    license_status = str(record.get("license_status") or "")
    if (
        license_status not in vocabulary
        or license_status == vocabulary[UNDECLARED_LICENSE_POSITION]
    ):
        _fail(
            "LICENSE_UNDECLARED",
            f"{document_id} declares no usable license status",
            {
                "declared": list(vocabulary),
                "document_id": document_id,
                "license_status": record.get("license_status"),
            },
        )
    source_date = _iso_date(
        record.get("source_date"), f"{label}.source_date", "DOCUMENT_DATE_MISSING"
    )
    source_uri = record.get("source_uri")
    return {
        "content_hash": content_hash,
        "document_id": document_id,
        "license_status": license_status,
        "source_date": source_date,
        "source_uri": None if source_uri is None else str(source_uri),
    }


def pin_corpus_snapshot(
    *,
    corpus_id: str,
    documents: Sequence[Mapping[str, Any]],
    pinned_at: str,
) -> dict[str, Any]:
    """Bind a corpus to exact bytes, licenses and dates, or refuse to bind it.

    Every document must carry a content hash, a usable license and a date;
    those three are what later stages actually rely on, so a missing one is
    refused at the pin rather than discovered when a claim already cites the
    document.  The identifier is derived from the sorted content hashes, which
    makes the snapshot content-addressed: the record cannot be relabelled
    without becoming detectably inconsistent with itself.
    """
    label = _require_text(corpus_id, "corpus_id")
    timestamp = _require_text(pinned_at, "pinned_at")
    if not documents:
        _fail(
            "SNAPSHOT_EMPTY",
            "a corpus snapshot must pin at least one source document",
            {"corpus_id": label},
        )

    pinned: dict[str, dict[str, Any]] = {}
    for position, candidate in enumerate(documents):
        record = _pin_document(candidate, f"documents[{position}]")
        document_id = record["document_id"]
        held = pinned.get(document_id)
        if held is None:
            pinned[document_id] = record
            continue
        if held["content_hash"] != record["content_hash"]:
            _fail(
                "DOCUMENT_HASH_CONFLICT",
                f"{document_id} is pinned to two different content hashes",
                {
                    "content_hashes": sorted(
                        {held["content_hash"], record["content_hash"]}
                    ),
                    "document_id": document_id,
                },
            )
        if held != record:
            _fail(
                "INPUT_INVALID",
                f"{document_id} is declared twice with different metadata",
                {"document_id": document_id, "held": held, "repeated": record},
            )

    ordered = [pinned[document_id] for document_id in sorted(pinned)]
    content_hashes = sorted({record["content_hash"] for record in ordered})
    snapshot: dict[str, Any] = {
        "content_hashes": content_hashes,
        "corpus_id": label,
        "document_count": len(ordered),
        "documents": ordered,
        "pinned_at": timestamp,
        "snapshot_id": snapshot_id_for(content_hashes),
    }
    snapshot["snapshot_hash"] = hash_excluding(snapshot, "snapshot_hash")
    return snapshot


def require_snapshot_identity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a snapshot's identity from its own content, or refuse it.

    Called before every use of a snapshot rather than only at re-validation
    time: a partition, a holdout seal and a novelty boundary all inherit the
    snapshot's authority, so each of them re-derives it instead of trusting a
    record that arrived from somewhere else.
    """
    record = dict(_require_mapping(snapshot, "snapshot"))
    rows = record.get("documents")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        _fail(
            "SNAPSHOT_EMPTY",
            "the snapshot pins no source document",
            {"snapshot_id": record.get("snapshot_id")},
        )
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, candidate in enumerate(rows):
        document = dict(_require_mapping(candidate, f"snapshot.documents[{position}]"))
        missing = sorted(set(DOCUMENT_FIELDS) - set(document))
        if missing:
            _fail(
                "SNAPSHOT_DRIFT",
                "a pinned document no longer carries every pinned field",
                {"missing": missing, "position": position},
            )
        if not is_schema_digest(str(document["content_hash"])):
            _fail(
                "CONTENT_HASH_MISSING",
                "a pinned document carries no canonical content hash",
                {"position": position},
            )
        document_id = str(document["document_id"])
        if document_id in seen:
            _fail(
                "DOCUMENT_HASH_CONFLICT",
                f"the snapshot holds {document_id} twice",
                {"document_id": document_id},
            )
        seen.add(document_id)
        documents.append(document)

    content_hashes = sorted({str(row["content_hash"]) for row in documents})
    derived_id = snapshot_id_for(content_hashes)
    drift: dict[str, Any] = {}
    if list(record.get("content_hashes") or []) != content_hashes:
        drift["content_hashes"] = content_hashes
    if record.get("document_count") != len(documents):
        drift["document_count"] = len(documents)
    if record.get("snapshot_id") != derived_id:
        drift["snapshot_id"] = derived_id
    derived_hash = hash_excluding(record, "snapshot_hash")
    if record.get("snapshot_hash") != derived_hash:
        drift["snapshot_hash"] = derived_hash
    if drift:
        _fail(
            "SNAPSHOT_DRIFT",
            "the snapshot does not re-derive its own identity",
            {"derived": drift, "stated_snapshot_id": record.get("snapshot_id")},
        )
    return record


def pinned_documents(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """document_id -> pinned record, for a snapshot that re-derives itself."""
    record = require_snapshot_identity(snapshot)
    return {
        str(document["document_id"]): dict(document) for document in record["documents"]
    }


def report_id_for(
    *, snapshot_id: str, document_id: str, evaluated_at: str, policy_version: str
) -> str:
    """A re-derivable identifier for one document's integrity report."""
    return REPORT_ID_PREFIX + _digest_body(
        {
            "document_id": str(document_id),
            "evaluated_at": str(evaluated_at),
            "policy_version": str(policy_version),
            "snapshot_id": str(snapshot_id),
        }
    )


def build_snapshot_integrity_reports(
    snapshot: Mapping[str, Any],
    *,
    observed_content_hashes: Mapping[str, str],
    evaluated_at: str,
    policy_version: str,
) -> tuple[dict[str, Any], ...]:
    """Compare a pinned snapshot against what is actually on disk now.

    One canonical source-integrity report is produced per document across the
    union of the pinned and the observed sets, so a document that vanished, a
    document whose bytes changed and a document that appeared without being
    pinned are all *reported* rather than silently reduced to one outcome.
    Deciding what to do about a failed report is the caller's job; refusing to
    proceed on one is `revalidate_corpus_snapshot`.
    """
    record = require_snapshot_identity(snapshot)
    timestamp = _require_text(evaluated_at, "evaluated_at")
    policy = _require_text(policy_version, "policy_version")
    observed = {
        str(key): str(value)
        for key, value in _require_mapping(
            observed_content_hashes, "observed_content_hashes"
        ).items()
    }
    pinned = {
        str(document["document_id"]): str(document["content_hash"])
        for document in record["documents"]
    }
    snapshot_id = str(record["snapshot_id"])

    check_statuses = integrity_check_vocabulary()
    overall_statuses = integrity_overall_vocabulary()
    passed = check_statuses[INTEGRITY_PASS_POSITION]
    failed = check_statuses[INTEGRITY_FAIL_POSITION]
    not_run = check_statuses[INTEGRITY_NOT_RUN_POSITION]

    reports: list[dict[str, Any]] = []
    for document_id in sorted(set(pinned) | set(observed)):
        pinned_hash = pinned.get(document_id)
        observed_hash = observed.get(document_id)
        if pinned_hash is None:
            membership = (failed, "the snapshot does not pin this document")
            comparison = (not_run, "there is no pinned hash to compare against")
            subject_hash = observed_hash or ""
        else:
            membership = (passed, f"pinned by snapshot {snapshot_id}")
            subject_hash = pinned_hash
            if observed_hash is None:
                comparison = (failed, "the pinned document was not observed")
            elif observed_hash != pinned_hash:
                comparison = (failed, f"observed {observed_hash}")
            else:
                comparison = (passed, "the observed bytes match the pinned hash")
        if not is_schema_digest(subject_hash):
            _fail(
                "CONTENT_HASH_MISSING",
                f"{document_id} has no canonical hash to report on",
                {"document_id": document_id, "observed": observed_hash},
            )
        checks = [
            {
                "check_id": "document-pinned-by-snapshot",
                "details": membership[1],
                "evidence_artifact_ids": [snapshot_id],
                "status": membership[0],
            },
            {
                "check_id": "content-hash-unchanged",
                "details": comparison[1],
                "evidence_artifact_ids": [snapshot_id],
                "status": comparison[0],
            },
        ]
        clean = all(check["status"] == passed for check in checks)
        report = {
            "checks": checks,
            "content_hash": subject_hash,
            "document_id": document_id,
            "evaluated_at": timestamp,
            "overall_status": overall_statuses[
                INTEGRITY_PASS_POSITION if clean else INTEGRITY_FAIL_POSITION
            ],
            "policy_version": policy,
            "report_id": report_id_for(
                snapshot_id=snapshot_id,
                document_id=document_id,
                evaluated_at=timestamp,
                policy_version=policy,
            ),
            "trusted_for_extraction": clean,
        }
        validate_artifact("source-integrity-report", report)
        reports.append(report)
    return tuple(reports)


def revalidate_corpus_snapshot(
    snapshot: Mapping[str, Any],
    *,
    observed_content_hashes: Mapping[str, str],
    evaluated_at: str,
    policy_version: str,
) -> tuple[dict[str, Any], ...]:
    """Refuse the snapshot unless every document still hashes to what was pinned.

    The reports are returned on success so the caller keeps the evidence of the
    check rather than only its verdict.
    """
    reports = build_snapshot_integrity_reports(
        snapshot,
        observed_content_hashes=observed_content_hashes,
        evaluated_at=evaluated_at,
        policy_version=policy_version,
    )
    drifted = sorted(
        str(report["document_id"])
        for report in reports
        if not report["trusted_for_extraction"]
    )
    if drifted:
        _fail(
            "SNAPSHOT_DRIFT",
            "the observed corpus is not the corpus this snapshot pinned",
            {
                "drifted_document_ids": drifted,
                "snapshot_id": str(snapshot.get("snapshot_id")),
            },
        )
    return reports


# -- hidden holdout boundary ----------------------------------------------


def holdout_handle(snapshot_id: str, document_id: str) -> str:
    """The opaque handle a pinned document takes inside a holdout manifest.

    Derived from the snapshot and the document id, so the set of handles a
    snapshot can produce is computable — which is what makes "this holdout is
    not drawn from that snapshot" a decidable statement rather than a claim.
    """
    digest = _digest_body(
        {"document_id": str(document_id), "snapshot_id": str(snapshot_id)}
    )
    return HANDLE_ID_PREFIX + digest[:HANDLE_DIGEST_LENGTH]


def _partition_members(
    value: Sequence[str], label: str, pinned: Mapping[str, Any]
) -> list[str]:
    members = [
        _require_text(item, f"{label}[{position}]")
        for position, item in enumerate(value)
    ]
    if len(set(members)) != len(members):
        _fail(
            "PARTITION_OVERLAP",
            f"{label} names the same document twice",
            {"members": members},
        )
    unpinned = sorted(set(members) - set(pinned))
    if unpinned:
        _fail(
            "DOCUMENT_UNPINNED",
            f"{label} names documents the snapshot does not pin",
            {"unpinned": unpinned},
        )
    return sorted(members)


def partition_pinned_snapshot(
    *,
    snapshot: Mapping[str, Any],
    visible_document_ids: Sequence[str],
    hidden_document_ids: Sequence[str],
    ood_document_ids: Sequence[str] = (),
    adversarial_document_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Split a pinned snapshot into visible, hidden, OOD and adversarial parts.

    A document appearing in both the visible and the hidden partition is
    refused as leakage rather than deduplicated: by the time two handle lists
    exist the overlap is invisible to the firewall, so it has to be caught
    here, where the document identities are still the same objects.  Every
    pinned document must be assigned, because a document with no declared
    partition has no declared visibility either.
    """
    pinned = pinned_documents(snapshot)
    snapshot_id = str(snapshot["snapshot_id"])
    parts = {
        "adversarial_document_ids": _partition_members(
            adversarial_document_ids, "adversarial_document_ids", pinned
        ),
        "hidden_document_ids": _partition_members(
            hidden_document_ids, "hidden_document_ids", pinned
        ),
        "ood_document_ids": _partition_members(
            ood_document_ids, "ood_document_ids", pinned
        ),
        "visible_document_ids": _partition_members(
            visible_document_ids, "visible_document_ids", pinned
        ),
    }

    leaked = sorted(
        set(parts["visible_document_ids"]) & set(parts["hidden_document_ids"])
    )
    if leaked:
        _fail(
            "PARTITION_LEAKAGE",
            "documents are both visible and hidden",
            {"document_ids": leaked, "snapshot_id": snapshot_id},
        )
    names = sorted(parts)
    for first in range(len(names)):
        for second in range(first + 1, len(names)):
            shared = sorted(set(parts[names[first]]) & set(parts[names[second]]))
            if shared:
                _fail(
                    "PARTITION_OVERLAP",
                    f"documents are in both {names[first]} and {names[second]}",
                    {"document_ids": shared},
                )
    assigned = {document_id for members in parts.values() for document_id in members}
    unassigned = sorted(set(pinned) - assigned)
    if unassigned:
        _fail(
            "PARTITION_INCOMPLETE",
            "pinned documents were left out of every partition",
            {"snapshot_id": snapshot_id, "unassigned": unassigned},
        )

    partition: dict[str, Any] = dict(parts)
    partition.update(
        {
            "adversarial_partition_handles": [
                holdout_handle(snapshot_id, document_id)
                for document_id in parts["adversarial_document_ids"]
            ],
            "hidden_partition_handles": [
                holdout_handle(snapshot_id, document_id)
                for document_id in parts["hidden_document_ids"]
            ],
            "ood_partition_handles": [
                holdout_handle(snapshot_id, document_id)
                for document_id in parts["ood_document_ids"]
            ],
            "partition_id": PARTITION_ID_PREFIX
            + _digest_body({"parts": parts, "snapshot_id": snapshot_id}),
            "snapshot_hash": str(snapshot["snapshot_hash"]),
            "snapshot_id": snapshot_id,
        }
    )
    partition["partition_hash"] = hash_excluding(partition, "partition_hash")
    return partition


def require_partition_identity(partition: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a partition's identifier and hash from its own content."""
    record = dict(_require_mapping(partition, "partition"))
    parts = {
        name: sorted(str(item) for item in record.get(name) or [])
        for name in (
            "adversarial_document_ids",
            "hidden_document_ids",
            "ood_document_ids",
            "visible_document_ids",
        )
    }
    snapshot_id = str(record.get("snapshot_id") or "")
    derived_id = PARTITION_ID_PREFIX + _digest_body(
        {"parts": parts, "snapshot_id": snapshot_id}
    )
    derived_hash = hash_excluding(record, "partition_hash")
    if record.get("partition_id") != derived_id or (
        record.get("partition_hash") != derived_hash
    ):
        _fail(
            "PARTITION_DRIFT",
            "the partition does not re-derive its own identity",
            {
                "derived_partition_hash": derived_hash,
                "derived_partition_id": derived_id,
                "stated_partition_id": record.get("partition_id"),
            },
        )
    return record


def seal_holdout_boundary(
    *,
    snapshot: Mapping[str, Any],
    partition: Mapping[str, Any],
    evaluator_id: str,
    split_strategy: str,
    acl_policy_hash: str,
    log_redaction_policy: str,
    cache_isolation_policy: str,
    sealed_at: str,
) -> dict[str, Any]:
    """Seal the hidden side of a partition through the firewall's own builder.

    This module decides *what* the hidden material is and *which snapshot it
    came from*; the manifest itself is written by
    `verifier_firewall.build_holdout_manifest`, so the access-control fields
    and their validation stay in the module that owns them.  A refusal from
    that builder is surfaced, never worked around.
    """
    pinned = pinned_documents(snapshot)
    record = require_partition_identity(partition)
    snapshot_id = str(snapshot["snapshot_id"])
    if record.get("snapshot_id") != snapshot_id or (
        record.get("snapshot_hash") != str(snapshot["snapshot_hash"])
    ):
        _fail(
            "PARTITION_DRIFT",
            "the partition was not derived from this snapshot",
            {
                "partition_snapshot_id": record.get("snapshot_id"),
                "snapshot_id": snapshot_id,
            },
        )

    concealed = [
        document_id
        for name in (
            "adversarial_document_ids",
            "hidden_document_ids",
            "ood_document_ids",
        )
        for document_id in record.get(name) or []
    ]
    content_hashes = sorted(
        {str(pinned[str(document_id)]["content_hash"]) for document_id in concealed}
    )
    if not content_hashes:
        _fail(
            "PARTITION_INCOMPLETE",
            "the partition conceals nothing, so there is no holdout to seal",
            {"partition_id": record.get("partition_id")},
        )
    holdout_id = HOLDOUT_ID_PREFIX + _digest_body(
        {
            "evaluator_id": str(evaluator_id),
            "partition_hash": str(record["partition_hash"]),
            "split_strategy": str(split_strategy),
        }
    )
    try:
        return build_holdout_manifest(
            evaluator_id=_require_text(evaluator_id, "evaluator_id"),
            split_strategy=_require_text(split_strategy, "split_strategy"),
            public_partition_refs=list(record.get("visible_document_ids") or []),
            hidden_partition_handles=list(record.get("hidden_partition_handles") or []),
            ood_partition_handles=list(record.get("ood_partition_handles") or []),
            adversarial_partition_handles=list(
                record.get("adversarial_partition_handles") or []
            ),
            content_hashes=content_hashes,
            acl_policy_hash=acl_policy_hash,
            log_redaction_policy=log_redaction_policy,
            cache_isolation_policy=cache_isolation_policy,
            holdout_id=holdout_id,
            sealed_at=_require_text(sealed_at, "sealed_at"),
        )
    except FirewallRefusal as error:
        _fail(
            "HOLDOUT_SEAL_REFUSED",
            str(error),
            {"holdout_id": holdout_id, "partition_id": record.get("partition_id")},
        )
        return {}


def require_holdout_drawn_from_snapshot(
    *, snapshot: Mapping[str, Any], holdout: Mapping[str, Any]
) -> dict[str, Any]:
    """Refuse a holdout whose handles or hashes the snapshot cannot produce.

    A holdout that arrived from elsewhere is the leakage case the firewall
    cannot detect on its own: its manifest is internally consistent, its access
    flags are false, and it still conceals material nobody pinned.  The
    snapshot's handle universe is recomputed here and the holdout is checked
    against it, including the case where a handle in the hidden partition is
    the handle of a document the manifest also publishes.
    """
    pinned = pinned_documents(snapshot)
    # The diagnostic labels are `holdout_manifest` and `prior_art_boundary`
    # rather than the bare words: both bare words are canonical enum values in
    # other schemas, and EF4-I22 forbids this module from holding either.
    manifest = dict(_require_mapping(holdout, "holdout_manifest"))
    snapshot_id = str(snapshot["snapshot_id"])
    universe = {
        holdout_handle(snapshot_id, document_id): document_id for document_id in pinned
    }

    concealed: list[str] = []
    for name in (
        "adversarial_partition_handles",
        "hidden_partition_handles",
        "ood_partition_handles",
    ):
        concealed.extend(str(handle) for handle in manifest.get(name) or [])
    foreign = sorted(set(concealed) - set(universe))
    if foreign:
        _fail(
            "HOLDOUT_HANDLE_UNPINNED",
            "the holdout conceals handles this snapshot cannot derive",
            {"handles": foreign, "snapshot_id": snapshot_id},
        )

    public_refs = [str(ref) for ref in manifest.get("public_partition_refs") or []]
    unpinned = sorted(set(public_refs) - set(pinned))
    if unpinned:
        _fail(
            "DOCUMENT_UNPINNED",
            "the holdout publishes documents the snapshot does not pin",
            {"document_ids": unpinned, "snapshot_id": snapshot_id},
        )
    leaked = sorted(
        universe[handle]
        for handle in set(concealed)
        if universe[handle] in set(public_refs)
    )
    if leaked:
        _fail(
            "PARTITION_LEAKAGE",
            "the holdout conceals documents it also publishes",
            {"document_ids": leaked, "snapshot_id": snapshot_id},
        )

    pinned_hashes = {str(row["content_hash"]) for row in pinned.values()}
    unbound = sorted(
        {str(value) for value in manifest.get("content_hashes") or []} - pinned_hashes
    )
    if unbound:
        _fail(
            "HOLDOUT_CONTENT_UNPINNED",
            "the holdout binds content hashes the snapshot never pinned",
            {"content_hashes": unbound, "snapshot_id": snapshot_id},
        )
    return manifest


# -- prior-art boundary ---------------------------------------------------


def declare_prior_art_boundary(
    *,
    snapshot: Mapping[str, Any],
    as_of_date: str,
    searched_sources: Sequence[str],
    unsearched_sources: Sequence[str] = (),
) -> dict[str, Any]:
    """Name exactly the snapshot and the time bound a novelty claim may cite.

    Documents dated after the bound are *recorded* as excluded rather than
    dropped, so a later assessment can distinguish "that document is not in the
    corpus" from "that document is in the corpus but the search never reached
    it" — two different failures with two different remedies.
    """
    pinned = pinned_documents(snapshot)
    bound = _iso_date(as_of_date, "as_of_date", "AS_OF_UNDECLARED")
    searched = sorted(
        {
            _require_text(value, f"searched_sources[{position}]")
            for position, value in enumerate(searched_sources)
        }
    )
    if not searched:
        _fail(
            "SEARCH_SCOPE_UNDECLARED",
            "a prior-art boundary must name at least one searched source",
            {"snapshot_id": str(snapshot["snapshot_id"])},
        )
    unsearched = sorted(
        {
            _require_text(value, f"unsearched_sources[{position}]")
            for position, value in enumerate(unsearched_sources)
        }
    )
    overlap = sorted(set(searched) & set(unsearched))
    if overlap:
        _fail(
            "SEARCH_SCOPE_UNDECLARED",
            "a source cannot be both searched and unsearched",
            {"sources": overlap},
        )

    in_scope = sorted(
        document_id
        for document_id, row in pinned.items()
        if str(row["source_date"]) <= bound
    )
    excluded = sorted(set(pinned) - set(in_scope))
    if not in_scope:
        _fail(
            "SNAPSHOT_EMPTY",
            "no pinned document falls on or before the as-of bound",
            {"as_of_date": bound, "excluded_document_ids": excluded},
        )

    boundary: dict[str, Any] = {
        "as_of_date": bound,
        "corpus_snapshot_hash": str(snapshot["snapshot_hash"]),
        "excluded_document_ids": excluded,
        "in_scope_document_ids": in_scope,
        "searched_sources": searched,
        "snapshot_id": str(snapshot["snapshot_id"]),
        "unsearched_sources": unsearched,
    }
    boundary["boundary_id"] = BOUNDARY_ID_PREFIX + _digest_body(boundary)
    boundary["boundary_hash"] = hash_excluding(boundary, "boundary_hash")
    return boundary


def require_boundary_identity(boundary: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a prior-art boundary's identifier and hash from its content."""
    record = dict(_require_mapping(boundary, "prior_art_boundary"))
    body = {
        key: value
        for key, value in record.items()
        if key not in {"boundary_hash", "boundary_id"}
    }
    derived_id = BOUNDARY_ID_PREFIX + _digest_body(body)
    derived_hash = hash_excluding(record, "boundary_hash")
    if record.get("boundary_id") != derived_id or (
        record.get("boundary_hash") != derived_hash
    ):
        _fail(
            "BOUNDARY_DRIFT",
            "the prior-art boundary does not re-derive its own identity",
            {
                "derived_boundary_hash": derived_hash,
                "derived_boundary_id": derived_id,
                "stated_boundary_id": record.get("boundary_id"),
            },
        )
    return record


def assess_novelty_within_boundary(
    *,
    boundary: Mapping[str, Any],
    run_id: str,
    subject_ref: str,
    statement_hash: str,
    search_completeness_certificate_id: str,
    novelty_dimensions: Sequence[str],
    closest_prior_art_refs: Sequence[str],
    distinguishing_features: Sequence[str],
    assessor_ref: str,
    assessed_at: str,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Write the canonical novelty assessment a declared boundary can support.

    Every cited reference must be a document the boundary contains and must fall
    on or before the as-of bound; the two failures are reported separately
    because citing something the corpus never held and citing something the
    search never reached are different mistakes.  The status and the promotion
    ceiling are read positionally from the canonical ladders and are capped
    below the top of both: this module can say "nothing was found within the
    declared scope", never "nothing exists".
    """
    record = require_boundary_identity(boundary)
    in_scope = [str(value) for value in record.get("in_scope_document_ids") or []]
    excluded = [str(value) for value in record.get("excluded_document_ids") or []]
    statement = str(statement_hash or "")
    if not is_schema_digest(statement):
        _fail(
            "INPUT_INVALID",
            "statement_hash must be a canonical digest",
            {"statement_hash": statement_hash},
        )

    dimensions = sorted(
        {
            _require_text(value, f"novelty_dimensions[{position}]")
            for position, value in enumerate(novelty_dimensions)
        }
    )
    declared_dimensions = novelty_dimension_vocabulary()
    undeclared = sorted(set(dimensions) - set(declared_dimensions))
    if undeclared:
        _fail(
            "NOVELTY_DIMENSION_UNDECLARED",
            "the assessment names dimensions outside the canonical vocabulary",
            {"declared": list(declared_dimensions), "undeclared": undeclared},
        )

    refs = sorted(
        {
            _require_text(value, f"closest_prior_art_refs[{position}]")
            for position, value in enumerate(closest_prior_art_refs)
        }
    )
    outside = sorted(set(refs) - set(in_scope) - set(excluded))
    if outside:
        _fail(
            "PRIOR_ART_OUTSIDE_BOUNDARY",
            "the assessment cites documents the boundary does not contain",
            {"boundary_id": record.get("boundary_id"), "document_ids": outside},
        )
    late = sorted(set(refs) & set(excluded))
    if late:
        _fail(
            "PRIOR_ART_AFTER_AS_OF",
            "the assessment cites documents dated after its as-of bound",
            {"as_of_date": record.get("as_of_date"), "document_ids": late},
        )

    unsearched = [str(value) for value in record.get("unsearched_sources") or []]
    if refs:
        status_position = PRIOR_ART_FOUND_POSITION
    elif unsearched:
        status_position = CORPUS_BOUNDED_POSITION
    else:
        status_position = SEARCH_BOUNDED_POSITION
    # Both the field names and their vocabularies come from the schema: one of
    # these field names is a canonical enum value in another schema, so writing
    # it here would be the duplicated wire literal EF4-I22 forbids.
    status_field, status_ladder = scalar_enum_field(
        NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION
    )
    ceiling_field, ceiling_ladder = scalar_enum_field(
        NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION
    )

    assessment: dict[str, Any] = {
        "assessed_at": _require_text(assessed_at, "assessed_at"),
        "assessor_ref": _require_text(assessor_ref, "assessor_ref"),
        "closest_prior_art_refs": refs,
        "corpus_snapshot_hash": str(record["corpus_snapshot_hash"]),
        "distinguishing_features": [
            _require_text(value, f"distinguishing_features[{position}]")
            for position, value in enumerate(distinguishing_features)
        ],
        "limitations": [
            *(str(value) for value in limitations),
            f"assessed only against corpus snapshot {record['snapshot_id']} "
            f"on or before {record['as_of_date']}",
        ],
        "novelty_dimensions": dimensions,
        "run_id": _require_text(run_id, "run_id"),
        "search_completeness_certificate_id": _require_text(
            search_completeness_certificate_id, "search_completeness_certificate_id"
        ),
        "search_cutoff": str(record["as_of_date"]),
        "searched_sources": [
            str(value) for value in record.get("searched_sources") or []
        ],
        "statement_hash": statement,
        "subject_ref": _require_text(subject_ref, "subject_ref"),
        "unsearched_sources": unsearched,
    }
    assessment[ceiling_field] = ceiling_ladder[NOVELTY_LADDER[status_position]]
    assessment[status_field] = status_ladder[status_position]
    assessment["assessment_id"] = ASSESSMENT_ID_PREFIX + _digest_body(assessment)
    assessment["assessment_hash"] = hash_excluding(assessment, "assessment_hash")
    validate_artifact(NOVELTY_SCHEMA, assessment)
    return assessment
