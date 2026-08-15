"""Genome intake, scope and falsifiability integration gate (I06).

I05 screens one hypothesis genome *document* in isolation: it admits a
submission that declares a scope vector, declares a falsifier and belongs to the
sealed search space, and it refuses one that does not.  What it cannot see is
whether the artifacts those declarations *point at* actually exist, satisfy
their own canonical contracts, and describe the same hypothesis.  A genome can
name a ``scope_vector_id`` no scope vector was ever written for, list a
``falsifier_gene_ids`` entry that resolves to a falsifier belonging to a
different genome, or carry a prediction scoped outside the boundary the genome
claims.  Each of those passes intake screening and only fails once something
downstream tries to reason over a reference that was never bound.  This gate is
that binding: it composes the I05 screen and then resolves the references across
the genome, its scope vector, its falsifier genes and its prediction genes.

Five kinds of refusal carry the weight, and none of them re-derive a judgement
I05 already owns.

*Screening.*  The gate defers eligibility entirely to I05.  A submission the
screen refuses is refused here as ``SCREENING_REFUSED`` carrying the screen's
own reason codes — the gate does not restate the falsifier-present or
scope-present checks, because a second copy would drift (EF4-I22).

*Scope binding.*  The scope vector the genome names must be supplied and must
satisfy the canonical scope-vector contract, and every prediction the genome
declares must be scoped to that same vector.  A prediction naming a different
scope is out of the bounds the genome declared, so the falsifiability of the
genome would be tested against a claim it never made.

*Falsifier binding.*  Every ``falsifier_gene_ids`` entry must resolve to a
supplied falsifier gene that satisfies its canonical contract, names this genome
as its subject, and links only predictions the genome actually declares.  A
falsifier for another genome, or one testing an undeclared prediction, is not
this hypothesis's falsifier.

*Prediction binding.*  Every ``prediction_gene_ids`` entry must resolve to a
supplied prediction gene that satisfies its contract and names this genome, and
no extra prediction or falsifier may be smuggled in under an id the genome does
not declare.

*Authority.*  A genome enters intake as an un-evaluated draft.  One arriving
with an evaluated, promoted or otherwise advanced lifecycle status is trying to
acquire — through the intake door — the evaluator, holdout or promotion
authority that door does not grant, so it is refused.  The un-evaluated status
is read from the canonical genome schema rather than named here.

Every decision, admit or refuse, resolves to one immutable receipt whose hash
re-derives from its own fields.  The gate reads no clock and draws no random
value: the caller supplies the decision timestamp, and an identifier is minted
only when the caller declines to name the receipt.  Nothing here scores,
ranks, selects or promotes anything, and no input is ever mutated.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import canonical_json, hash_excluding, sha256_of_payload
from ...domain.ids import new_id
from ...intake.v4_i05 import screening as intake

#: Every way this gate refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "AUTHORITY_STATUS_PRESUMED": (
        "the genome enters intake already carrying an evaluated, promoted or "
        "otherwise advanced lifecycle status, and intake grants no candidate "
        "evaluator, holdout or promotion authority — that status is earned "
        "downstream, never asserted at the door"
    ),
    "CONTRACT_DRIFT": (
        "a field this gate resolves references across is no longer declared by "
        "the canonical schema that is supposed to own it, so the binding check "
        "would silently pass on an absent field"
    ),
    "FALSIFIER_GENOME_MISMATCH": (
        "a supplied falsifier gene names a different genome as its subject, so "
        "it does not falsify the hypothesis being admitted"
    ),
    "FALSIFIER_MALFORMED": (
        "a supplied falsifier gene does not satisfy the canonical falsifier "
        "contract, so admitting it would bind the genome to a falsifier no "
        "contract admits"
    ),
    "FALSIFIER_PREDICTION_UNLINKED": (
        "a falsifier links a prediction the genome does not declare, so it "
        "tests a prediction this hypothesis never makes"
    ),
    "FALSIFIER_UNDECLARED": (
        "a supplied falsifier gene carries an id the genome does not list, so "
        "an unnamed falsifier would be bound to the hypothesis it screens"
    ),
    "FALSIFIER_UNRESOLVED": (
        "the genome names a falsifier gene id no supplied falsifier resolves, "
        "so the declared falsifier exists only as a reference"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record an intake decision derived from something it never validated"
    ),
    "PREDICTION_GENOME_MISMATCH": (
        "a supplied prediction gene names a different genome as its subject, "
        "so it is not a prediction of the hypothesis being admitted"
    ),
    "PREDICTION_MALFORMED": (
        "a supplied prediction gene does not satisfy the canonical prediction "
        "contract, so the genome's falsifiers would link to a prediction no "
        "contract admits"
    ),
    "PREDICTION_SCOPE_OUT_OF_BOUNDS": (
        "a supplied prediction is scoped to a different scope vector than the "
        "genome declares, so it asserts a claim outside the genome's own bounds"
    ),
    "PREDICTION_UNDECLARED": (
        "a supplied prediction gene carries an id the genome does not list, so "
        "an unnamed prediction would be bound to the hypothesis"
    ),
    "PREDICTION_UNRESOLVED": (
        "the genome names a prediction gene id no supplied prediction "
        "resolves, so the declared prediction exists only as a reference"
    ),
    "SCOPE_VECTOR_MALFORMED": (
        "the supplied scope vector does not satisfy the canonical scope-vector "
        "contract, so the genome's declared bounds are not well-formed"
    ),
    "SCOPE_VECTOR_MISSING": (
        "no scope vector was supplied to resolve the genome's declared "
        "scope_vector_id against, so its bounds cannot be checked at all"
    ),
    "SCREENING_REFUSED": (
        "the I05 eligibility screen refused this submission, and an ineligible "
        "genome cannot be bound to its scope and falsifiers"
    ),
}

#: The canonical schema names this gate resolves references against.  These are
#: schema *names*, not wire vocabulary, and each is checked against the registry
#: before use so a rename fails here rather than un-guarding a binding.
GENOME_KIND = intake.GENOME_KIND
SCOPE_KIND = "scope-vector"
FALSIFIER_KIND = "falsifier-gene"
PREDICTION_KIND = "prediction-gene"

#: Genome fields this gate reads, by the names the canonical schemas declare.
#: `verify_contract` refuses if any of them stops being a declared property.
IDENTITY_FIELD = intake.IDENTITY_FIELD
SCOPE_FIELD = intake.SCOPE_FIELD
FALSIFIER_FIELD = intake.FALSIFIER_FIELD
PREDICTION_FIELD = "prediction_gene_ids"
STATUS_FIELD = "status"

#: Falsifier-gene fields the binding reads back rather than trusts.
FALSIFIER_ID_FIELD = "falsifier_gene_id"
FALSIFIER_GENOME_FIELD = "genome_id"
FALSIFIER_LINK_FIELD = "linked_prediction_ids"

#: Prediction-gene fields the binding reads back rather than trusts.
PREDICTION_ID_FIELD = "prediction_gene_id"
PREDICTION_GENOME_FIELD = "genome_id"
PREDICTION_SCOPE_FIELD = "scope_vector_id"

#: Intake-request envelope keys.
SUBMISSION_KEY = "submission"
SCOPE_KEY = "scope_vector"
FALSIFIERS_KEY = "falsifier_genes"
PREDICTIONS_KEY = "prediction_genes"

#: The schema property key whose contents bound what fields the gate may read.
PROPERTY_KEY = "properties"

#: The two decisions a receipt can record.
ADMITTED = "ADMITTED"
REFUSED = "REFUSED"

#: A deterministic report id for the composed I05 screen: the gate reads only
#: the single screen record and never publishes this id, but naming it keeps the
#: composed call from drawing a random one and so keeps the gate pure.
_SCREEN_REPORT_ID = "GSR-I06-GATE"

#: The genome/scope/falsifier/prediction fields, grouped by the schema that must
#: still declare each.  Verified on every gate call so a schema edit closes the
#: door instead of silently binding nothing.
_CONTRACT_FIELDS: dict[str, tuple[str, ...]] = {
    GENOME_KIND: (
        IDENTITY_FIELD,
        SCOPE_FIELD,
        FALSIFIER_FIELD,
        PREDICTION_FIELD,
        STATUS_FIELD,
    ),
    FALSIFIER_KIND: (
        FALSIFIER_ID_FIELD,
        FALSIFIER_GENOME_FIELD,
        FALSIFIER_LINK_FIELD,
    ),
    PREDICTION_KIND: (
        PREDICTION_ID_FIELD,
        PREDICTION_GENOME_FIELD,
        PREDICTION_SCOPE_FIELD,
    ),
}


class GenomeIntakeGateError(intake.GenomeIntakeError):
    """A genome's references do not bind, or it presumes authority at intake.

    It subclasses the I05 intake refusal deliberately: a caller already handling
    an intake refusal must not silently miss an integration refusal, and the two
    stay distinguishable by type when the difference matters.
    """


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise GenomeIntakeGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise GenomeIntakeGateError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_sequence(value: object, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return value  # type: ignore[return-value]


def _finding(code: str, **fields: Any) -> dict[str, Any]:
    """One binding failure, carrying the reason its code exists."""
    if code not in FINDING_CODES:
        _fail("INPUT_INVALID", f"undeclared finding code {code}", {"code": code})
    return {"code": code, "reason": FINDING_CODES[code], **fields}


def _sort_key(row: Mapping[str, Any]) -> tuple[str, bytes]:
    return (str(row["code"]), canonical_json(row))


def verify_contract() -> dict[str, tuple[str, ...]]:
    """Every field this gate reads is still a declared property of its schema.

    The schemas are the authority.  Reading a field back out of the schema
    before trusting it means a rename of, say, ``linked_prediction_ids`` closes
    the falsifier-binding door loudly here instead of leaving a check that
    silently passes on an absent field.  Verification runs on every gate call
    rather than once at import, because the schemas can move under a long run.
    """
    registry = default_registry()
    known = set(registry.names())
    verified: dict[str, tuple[str, ...]] = {}
    for schema_name, fields in _CONTRACT_FIELDS.items():
        if schema_name not in known:
            _fail(
                "CONTRACT_DRIFT",
                f"the registry no longer declares the {schema_name} schema",
                {"schema": schema_name},
            )
        properties = set(
            _require_mapping(registry.document(schema_name), schema_name).get(
                PROPERTY_KEY
            )
            or ()
        )
        missing = sorted(field for field in fields if field not in properties)
        if missing:
            _fail(
                "CONTRACT_DRIFT",
                f"the canonical {schema_name} schema no longer declares every "
                "field this gate resolves references across",
                {"missing": missing, "schema": schema_name},
            )
        verified[schema_name] = tuple(fields)
    return verified


def intake_status() -> str:
    """The lifecycle status a genome must carry to be admitted at intake.

    Read as the first value the canonical genome ``status`` enum declares — the
    un-evaluated draft state — rather than named here, because the state's wire
    literal belongs to the schema and a copy of it would drift (EF4-I22).
    """
    verify_contract()
    document = default_registry().document(GENOME_KIND)
    status = _require_mapping(document, GENOME_KIND).get(PROPERTY_KEY, {})
    field = _require_mapping(status, PROPERTY_KEY).get(STATUS_FIELD, {})
    enum = _require_mapping(field, STATUS_FIELD).get("enum")
    if not isinstance(enum, list) or not enum:
        _fail(
            "CONTRACT_DRIFT",
            "the canonical genome schema declares no status enum to read",
            {"schema": GENOME_KIND},
        )
    return str(enum[0])  # type: ignore[index]


def _screen(submission: Any, *, decided_at: str) -> dict[str, Any]:
    """The I05 screen record for one submission, via the sealed intake surface.

    The gate composes the batch screen over a single submission rather than
    re-deriving the envelope handling: a malformed envelope, an out-of-space
    kind and a missing falsifier are all I05's answers to give.  Only the one
    screen record is read, and its ``record_hash`` is a pure function of the
    submission, so the composed call names a fixed report id and draws no random
    value.
    """
    report = intake.screen_submissions(
        [submission], screened_at=decided_at, report_id=_SCREEN_REPORT_ID
    )
    return dict(report["records"][0])


def _text_field(document: Mapping[str, Any], field: str) -> str | None:
    value = document.get(field)
    if isinstance(value, str) and value.strip():
        return str(value)
    return None


def _id_list(document: Mapping[str, Any], field: str) -> list[str]:
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _index_by_id(
    documents: Sequence[Any],
    *,
    kind: str,
    id_field: str,
    malformed_code: str,
    findings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate each supplied artifact and index it by its own declared id.

    Malformed artifacts are surveyed rather than raised, so a caller repairing
    an intake sees every gap in one pass.  A validated artifact whose id another
    validated artifact already claims is a caller error the schema cannot catch,
    and it is reported as malformed against the duplicate id so the survey stays
    complete instead of silently overwriting.
    """
    index: dict[str, dict[str, Any]] = {}
    for position, candidate in enumerate(documents):
        if not isinstance(candidate, Mapping):
            findings.append(
                _finding(
                    malformed_code,
                    kind=kind,
                    position=position,
                    submitted_type=type(candidate).__name__,
                )
            )
            continue
        document = dict(candidate)
        try:
            validate_artifact(kind, document)
        except ContractViolation as error:
            findings.append(
                _finding(
                    malformed_code,
                    kind=kind,
                    position=position,
                    schema_errors=list(error.errors),
                )
            )
            continue
        artifact_id = str(document[id_field])
        if artifact_id in index:
            findings.append(
                _finding(
                    malformed_code,
                    kind=kind,
                    position=position,
                    duplicate_id=artifact_id,
                )
            )
            continue
        index[artifact_id] = document
    return index


def intake_binding_findings(
    *,
    genome: Mapping[str, Any],
    scope_vector: Any,
    falsifier_genes: Sequence[Any],
    prediction_genes: Sequence[Any],
) -> tuple[dict[str, Any], ...]:
    """Every place the genome's references fail to bind to their artifacts.

    The survey is complete rather than first-failure: a caller fixing one
    dangling reference at a time would keep re-running against a bundle that is
    still inconsistent somewhere else.  Nothing is raised here — the gate below
    is what refuses — and no input is modified.  The genome is assumed to have
    already passed the I05 screen, so it is a schema-valid document whose fields
    can be read directly.
    """
    verify_contract()
    document = dict(_require_mapping(genome, "genome"))
    genome_id = str(document[IDENTITY_FIELD])
    declared_scope = _text_field(document, SCOPE_FIELD)
    declared_falsifiers = _id_list(document, FALSIFIER_FIELD)
    declared_predictions = set(_id_list(document, PREDICTION_FIELD))
    findings: list[dict[str, Any]] = []

    # Authority: a genome may not enter carrying an advanced lifecycle status.
    admissible_status = intake_status()
    genome_status = document.get(STATUS_FIELD)
    if str(genome_status) != admissible_status:
        findings.append(
            _finding(
                "AUTHORITY_STATUS_PRESUMED",
                admissible_status=admissible_status,
                genome_id=genome_id,
                presented_status=genome_status,
            )
        )

    # Scope: the declared scope vector must be supplied and well-formed.
    if scope_vector is None:
        findings.append(
            _finding(
                "SCOPE_VECTOR_MISSING", genome_id=genome_id, scope_id=declared_scope
            )
        )
    elif not isinstance(scope_vector, Mapping):
        findings.append(
            _finding(
                "SCOPE_VECTOR_MALFORMED",
                genome_id=genome_id,
                submitted_type=type(scope_vector).__name__,
            )
        )
    else:
        try:
            validate_artifact(SCOPE_KIND, dict(scope_vector))
        except ContractViolation as error:
            findings.append(
                _finding(
                    "SCOPE_VECTOR_MALFORMED",
                    genome_id=genome_id,
                    schema_errors=list(error.errors),
                )
            )

    # Predictions: index the supplied genes, then reconcile with the genome.
    predictions = _index_by_id(
        _require_sequence(prediction_genes, PREDICTIONS_KEY),
        kind=PREDICTION_KIND,
        id_field=PREDICTION_ID_FIELD,
        malformed_code="PREDICTION_MALFORMED",
        findings=findings,
    )
    for prediction_id, prediction in sorted(predictions.items()):
        if prediction_id not in declared_predictions:
            findings.append(
                _finding(
                    "PREDICTION_UNDECLARED",
                    genome_id=genome_id,
                    prediction_id=prediction_id,
                )
            )
            continue
        if str(prediction[PREDICTION_GENOME_FIELD]) != genome_id:
            findings.append(
                _finding(
                    "PREDICTION_GENOME_MISMATCH",
                    genome_id=genome_id,
                    prediction_genome_id=str(prediction[PREDICTION_GENOME_FIELD]),
                    prediction_id=prediction_id,
                )
            )
        prediction_scope = _text_field(prediction, PREDICTION_SCOPE_FIELD)
        if declared_scope is not None and prediction_scope != declared_scope:
            findings.append(
                _finding(
                    "PREDICTION_SCOPE_OUT_OF_BOUNDS",
                    genome_id=genome_id,
                    genome_scope_id=declared_scope,
                    prediction_id=prediction_id,
                    prediction_scope_id=prediction_scope,
                )
            )
    for prediction_id in sorted(declared_predictions - set(predictions)):
        findings.append(
            _finding(
                "PREDICTION_UNRESOLVED",
                genome_id=genome_id,
                prediction_id=prediction_id,
            )
        )

    # Falsifiers: index the supplied genes, then reconcile with the genome.
    falsifiers = _index_by_id(
        _require_sequence(falsifier_genes, FALSIFIERS_KEY),
        kind=FALSIFIER_KIND,
        id_field=FALSIFIER_ID_FIELD,
        malformed_code="FALSIFIER_MALFORMED",
        findings=findings,
    )
    declared_falsifier_set = set(declared_falsifiers)
    for falsifier_id, falsifier in sorted(falsifiers.items()):
        if falsifier_id not in declared_falsifier_set:
            findings.append(
                _finding(
                    "FALSIFIER_UNDECLARED",
                    falsifier_id=falsifier_id,
                    genome_id=genome_id,
                )
            )
            continue
        if str(falsifier[FALSIFIER_GENOME_FIELD]) != genome_id:
            findings.append(
                _finding(
                    "FALSIFIER_GENOME_MISMATCH",
                    falsifier_genome_id=str(falsifier[FALSIFIER_GENOME_FIELD]),
                    falsifier_id=falsifier_id,
                    genome_id=genome_id,
                )
            )
        unlinked = sorted(
            set(_id_list(falsifier, FALSIFIER_LINK_FIELD)) - declared_predictions
        )
        if unlinked:
            findings.append(
                _finding(
                    "FALSIFIER_PREDICTION_UNLINKED",
                    falsifier_id=falsifier_id,
                    genome_id=genome_id,
                    unlinked_prediction_ids=unlinked,
                )
            )
    for falsifier_id in sorted(declared_falsifier_set - set(falsifiers)):
        findings.append(
            _finding(
                "FALSIFIER_UNRESOLVED", falsifier_id=falsifier_id, genome_id=genome_id
            )
        )

    return tuple(sorted(findings, key=_sort_key))


def gate_genome_intake(
    *,
    submission: Any,
    scope_vector: Any,
    falsifier_genes: Sequence[Any] = (),
    prediction_genes: Sequence[Any] = (),
    decided_at: str,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Decide one genome's intake and return the immutable receipt of it.

    The receipt is emitted whether the genome is admitted or refused, so a
    refusal is an artifact rather than only an exception, and every decision
    carries the hashes of exactly the artifacts it was made from.  On any
    binding failure the decision is ``REFUSED`` and ``findings`` names every
    failure at once; an admitted genome's receipt records the resolved bindings.

    Screening is deferred to I05 and is terminal: an ineligible genome cannot be
    bound to its scope and falsifiers, so its receipt carries only
    ``SCREENING_REFUSED`` with the screen's own reason codes.
    """
    if not isinstance(decided_at, str) or not decided_at.strip():
        _fail("INPUT_INVALID", "decided_at must be a non-empty timestamp string")
    verify_contract()

    screen = _screen(submission, decided_at=decided_at)
    if not screen["admitted"]:
        findings: tuple[dict[str, Any], ...] = (
            _finding(
                "SCREENING_REFUSED",
                genome_id=screen["genome_id"],
                screen_reason_codes=list(screen["reason_codes"]),
            ),
        )
        return _build_receipt(
            decided_at=decided_at,
            findings=findings,
            genome_hash=screen["genome_hash"],
            genome_id=screen["genome_id"],
            receipt_id=receipt_id,
            resolved=None,
        )

    envelope = dict(_require_mapping(submission, SUBMISSION_KEY))
    genome = dict(_require_mapping(envelope[intake.GENOME_KEY], intake.GENOME_KEY))
    findings = intake_binding_findings(
        genome=genome,
        scope_vector=scope_vector,
        falsifier_genes=falsifier_genes,
        prediction_genes=prediction_genes,
    )
    resolved = None
    if not findings:
        resolved = {
            "falsifier_gene_hashes": {
                str(item[FALSIFIER_ID_FIELD]): sha256_of_payload(dict(item))
                for item in sorted(
                    (dict(gene) for gene in falsifier_genes),
                    key=lambda row: str(row[FALSIFIER_ID_FIELD]),
                )
            },
            "prediction_gene_hashes": {
                str(item[PREDICTION_ID_FIELD]): sha256_of_payload(dict(item))
                for item in sorted(
                    (dict(gene) for gene in prediction_genes),
                    key=lambda row: str(row[PREDICTION_ID_FIELD]),
                )
            },
            "scope_vector_hash": sha256_of_payload(dict(scope_vector)),
            "scope_vector_id": _text_field(genome, SCOPE_FIELD),
        }
    return _build_receipt(
        decided_at=decided_at,
        findings=findings,
        genome_hash=sha256_of_payload(genome),
        genome_id=str(genome[IDENTITY_FIELD]),
        receipt_id=receipt_id,
        resolved=resolved,
    )


def _build_receipt(
    *,
    decided_at: str,
    findings: Sequence[Mapping[str, Any]],
    genome_hash: str | None,
    genome_id: str | None,
    receipt_id: str | None,
    resolved: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """One self-proving record of an intake decision and what it was made from."""
    ordered = [dict(row) for row in findings]
    receipt: dict[str, Any] = {
        "admitted": not ordered,
        "decided_at": decided_at,
        "decision": ADMITTED if not ordered else REFUSED,
        "finding_codes": sorted({str(row["code"]) for row in ordered}),
        "findings": ordered,
        "genome_hash": genome_hash,
        "genome_id": genome_id,
        "receipt_id": receipt_id or new_id("GIR"),
        "resolved_bindings": dict(resolved) if resolved is not None else None,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def require_admissible(receipt: Mapping[str, Any]) -> None:
    """Raise unless the receipt records an admitted genome.

    The fail-closed enforcement path.  The raised code is the alphabetically
    first finding's code — a deterministic choice, not a claim it is the worst
    one; ``context["findings"]`` is the complete answer, exactly as it appears
    in the receipt.
    """
    record = dict(_require_mapping(receipt, "receipt"))
    if hash_excluding(record, "receipt_hash") != record.get("receipt_hash"):
        _fail(
            "INPUT_INVALID",
            "the intake receipt does not re-derive its own hash",
            {"receipt_id": record.get("receipt_id")},
        )
    if record.get("admitted"):
        return
    findings = list(record.get("findings") or [])
    if not findings:
        _fail(
            "INPUT_INVALID",
            "a refused receipt carries no findings to raise",
            {"receipt_id": record.get("receipt_id")},
        )
    first = str(findings[0]["code"])
    _fail(
        first,
        f"genome intake refused with {len(findings)} finding(s)",
        {
            "finding_codes": sorted({str(row["code"]) for row in findings}),
            "findings": [dict(row) for row in findings],
            "genome_id": record.get("genome_id"),
            "receipt_id": record.get("receipt_id"),
        },
    )


def gate_intake_batch(
    requests: Sequence[Any],
    *,
    decided_at: str,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Decide a whole intake batch into one reconciled report of receipts.

    Each request is an envelope carrying a submission and the artifacts its
    references resolve against.  Receipts keep request order so a caller can line
    the report up against what it sent, and the counts reconcile exactly —
    submitted equals admitted plus refused — so the batch can never report a
    genome it never decided.  Every derived list is sorted, so the report is a
    pure function of the batch and its own report hash re-derives.
    """
    if not isinstance(decided_at, str) or not decided_at.strip():
        _fail("INPUT_INVALID", "decided_at must be a non-empty timestamp string")
    rows = _require_sequence(requests, "requests")

    # The batch is a pure function of its inputs, so a receipt id a request
    # declines to name is derived from the report id and the request position
    # rather than drawn at random: replaying the same batch re-derives the same
    # report byte for byte.
    resolved_report_id = report_id or new_id("GIB")
    receipts: list[dict[str, Any]] = []
    for position, candidate in enumerate(rows):
        request = _require_mapping(candidate, f"requests[{position}]")
        receipt = gate_genome_intake(
            submission=request.get(SUBMISSION_KEY),
            scope_vector=request.get(SCOPE_KEY),
            falsifier_genes=request.get(FALSIFIERS_KEY) or (),
            prediction_genes=request.get(PREDICTIONS_KEY) or (),
            decided_at=decided_at,
            receipt_id=request.get("receipt_id") or f"{resolved_report_id}-{position}",
        )
        receipts.append({**receipt, "request_index": position})

    admitted = [receipt for receipt in receipts if receipt["admitted"]]
    refused = [receipt for receipt in receipts if not receipt["admitted"]]
    finding_totals: dict[str, int] = {}
    for receipt in refused:
        for code in receipt["finding_codes"]:
            finding_totals[code] = finding_totals.get(code, 0) + 1

    report: dict[str, Any] = {
        "admitted_genome_ids": sorted(
            str(receipt["genome_id"])
            for receipt in admitted
            if receipt["genome_id"] is not None
        ),
        "counts": {
            "admitted": len(admitted),
            "refused": len(refused),
            "submitted": len(receipts),
        },
        "decided_at": decided_at,
        "finding_totals": {
            code: finding_totals[code] for code in sorted(finding_totals)
        },
        "receipts": receipts,
        "report_id": resolved_report_id,
    }
    _require_reconciled(report["counts"])
    report["report_hash"] = hash_excluding(report, "report_hash")
    return report


def _require_reconciled(counts: Mapping[str, int]) -> None:
    """Submitted equals admitted plus refused, checked rather than assumed."""
    submitted = int(counts["submitted"])
    accounted = int(counts["admitted"]) + int(counts["refused"])
    if submitted != accounted:
        _fail(
            "INPUT_INVALID",
            "the intake counts do not reconcile with the submitted batch",
            dict(counts),
        )
