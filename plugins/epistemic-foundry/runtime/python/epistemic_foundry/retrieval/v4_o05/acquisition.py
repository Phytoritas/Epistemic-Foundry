"""Evolution evidence retrieval, layered novelty and coverage-debt acquisition.

O04 closed the question of whether an absence claim carries a certificate, and
K05 closed the question of *which bytes* a claim was assessed against.  Neither
answers the three questions an evolution run asks before it spends a
generation: where may this run look, what did it actually learn on each
separate novelty layer, and which part of the map is it still blind to.

Three records do the work here, and each one is content-addressed so its
identity cannot be separated from what it contains.

*Evolution evidence retrieval plan.*  A plan is declared **inside** a pinned
K05 snapshot and the prior-art boundary declared over that same snapshot: the
snapshot fixes the bytes, the boundary fixes the date, and a plan naming a
document the snapshot never pinned — or one the snapshot pins but the as-of
bound excludes — is refused rather than quietly widened.  Those two refusals
stay separate because "the corpus never held it" and "the search never reached
it" have different remedies.  A plan must declare a disposition for every one
of the canonical lanes, because the completeness certificate reconciles exactly
that many and a plan short of one could never produce a valid certificate.
Where a lane receipt is emitted it is emitted in the canonical shape and
validated against the canonical schema, and its state is *derived* from the
results rather than accepted as a parameter: a caller that both runs the search
and labels how well it ran can label a lane it never queried as complete.

*Multi-layer novelty.*  The layers are the novelty vector's own declared
dimensions, read from the schema rather than restated, and a layer the schema
does not declare is refused instead of being scored into a record no reader can
interpret.  The ladder is K05's, and it is inherited honestly: this module
composes ``assess_novelty_within_boundary`` rather than writing a second
assessment, so the capped status and capped promotion ceiling come from the
module that owns them.  A caller declaring that the external search completed
while the bound boundary still names unsearched sources is refused — that is
exactly the corpus-bounded search claiming it reached outside the corpus.

*Coverage-debt acquisition.*  Coverage debt lives on a niche, so the ranking
composes the sealed M05 niche map: cell identity, occupancy and the declared
debt range are enforced by the modules that own them, and a debt outside its
declared range surfaces as this module's own refusal rather than a raw schema
error.  Ranking is deterministic — descending debt, then niche id — so two runs
over equal input produce byte-equal plans, and the plan records what it did
*not* search: the deferred niches, the unsearched sources, the unselected lanes
and the documents the as-of bound excluded.

Nothing here invents vocabulary.  Lane names, lane order, receipt states,
receipt kinds, sentinel reasons, stop reasons, plan dispositions and novelty
layers are all read from the canonical schemas that declare them, positionally
where the value's *name* would itself be a canonical enum value elsewhere.
Nothing here scores, promotes, or reads a clock.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...cartography.v4_m05 import CartographyError, NicheMap
from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import (
    SHA256_PREFIX,
    hash_excluding,
    is_schema_digest,
    sha256_hex,
    sha256_of_payload,
)
from ...evaluation.novelty_layers import NoveltyVectorRefused, build_novelty_vector
from ...evidence.v4_k05 import (
    NOVELTY_SCHEMA,
    NOVELTY_STATUS_POSITION,
    PROMOTION_CEILING_POSITION,
    CorpusBoundaryError,
    assess_novelty_within_boundary,
    pinned_documents,
    require_boundary_identity,
    scalar_enum_field,
)
from ..search_state import SearchState, missing_lanes

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ACQUISITION_TARGETS_EMPTY": (
        "an acquisition ranking was requested over no niche at all, and a "
        "ranking of nothing would report zero coverage debt as if the map were "
        "fully covered"
    ),
    "BOUNDARY_NOT_FROM_SNAPSHOT": (
        "the prior-art boundary was declared over a different snapshot than the "
        "one this plan pins, so the dates and the bytes describe two corpora"
    ),
    "COVERAGE_DEBT_OUT_OF_RANGE": (
        "a niche declares a coverage debt outside the range its own schema "
        "permits, so the acquisition ranking would order incomparable numbers"
    ),
    "DISPOSITION_UNDECLARED": (
        "a lane carries a plan disposition the completeness certificate does "
        "not declare, so the lane's presence in the plan means nothing"
    ),
    "DOCUMENT_AFTER_AS_OF": (
        "the plan names a document the snapshot pins but the as-of bound "
        "excludes, so the declared search window never covered it"
    ),
    "DOCUMENT_OUTSIDE_SNAPSHOT": (
        "the plan names a document the pinned snapshot does not contain, which "
        "reaches outside the evidence boundary the run declared"
    ),
    "EXTERNAL_LAYER_UNBOUNDED": (
        "the external prior-art layer was declared complete while the boundary "
        "still names unsearched sources, which reads a corpus-bounded search as "
        "an unbounded one"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "plan, assess or rank against something it never validated"
    ),
    "LANE_COVERAGE_INCOMPLETE": (
        "the plan or the receipt set does not account for every canonical "
        "retrieval lane, and an unaccounted lane has no declared search state"
    ),
    "LANE_DISPOSITION_CONFLICT": (
        "a lane receipt contradicts the plan's own disposition for that lane, "
        "so the record of what ran disagrees with the record of what was chosen"
    ),
    "LANE_UNDECLARED": (
        "a lane is outside the canonical retrieval vocabulary, or the two "
        "schemas declaring that vocabulary disagree about its members"
    ),
    "MANDATORY_LANE_UNCOVERED": (
        "a selected adversarial lane was never conclusively searched, and an "
        "unsearched counter, null, boundary, method or novelty lane cannot "
        "ground a confident acquisition decision"
    ),
    "NICHE_REFUSED": (
        "the sealed cartography refused the niche map, and this module never "
        "writes a second map to route around that refusal"
    ),
    "NOVELTY_LAYER_UNDECLARED": (
        "the layered assessment names or omits a novelty layer the canonical "
        "vector schema does not declare, which reports novelty on an axis "
        "nothing defines"
    ),
    "PLAN_DRIFT": (
        "a plan does not re-derive its own identifier or hash, so the search "
        "being recorded is not the search that was declared"
    ),
    "RECEIPT_NOT_FROM_PLAN": (
        "a lane receipt binds a different plan hash than the plan it is being "
        "reconciled against, so the two describe different searches"
    ),
    "RECEIPT_REFUSED": (
        "the canonical schema refused the lane receipt, and this module surfaces "
        "that refusal instead of emitting a receipt no reader can validate"
    ),
    "RECEIPT_STATE_UNDECLARED": (
        "a lane carries a search state the canonical receipt schema does not "
        "declare, so whether that lane produced evidence is undecidable"
    ),
    "RESULT_OUTSIDE_SNAPSHOT": (
        "a lane returned a document the pinned snapshot never pinned, which "
        "means the search escaped the evidence boundary while it was running"
    ),
    "SNAPSHOT_BOUNDARY_REFUSED": (
        "the sealed corpus boundaries refused the snapshot or the prior-art "
        "boundary, and this module never re-pins evidence to route around it"
    ),
    "TARGET_BUDGET_INVALID": (
        "an acquisition budget is not a positive count of niches, so the plan "
        "would either target nothing or target an unbounded amount"
    ),
    "VECTOR_REFUSED": (
        "the multi-layer novelty owner refused the vector, and this module "
        "never writes a second vector to obtain a score it was denied"
    ),
}

#: The canonical schemas whose vocabularies this module reads rather than holds.
RECEIPT_SCHEMA = "search-lane-receipt"
CERTIFICATE_SCHEMA = "search-completeness-certificate"
VECTOR_SCHEMA = "novelty-vector"
NICHE_SCHEMA = "epistemic-niche"

#: Identifier prefixes.  Every identifier this module mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
PLAN_ID_PREFIX = "ERP-"
RECEIPT_ID_PREFIX = "SLR-"
VECTOR_ID_PREFIX = "NLV-"
LAYERED_ID_PREFIX = "LNA-"
ACQUISITION_ID_PREFIX = "CDA-"
TARGET_ID_PREFIX = "AQT-"

#: Positions in the receipt's search-state vocabulary.  The list is declared
#: from "never looked" through the two conclusive outcomes to the three
#: inconclusive ones; the schema-and-type suite asserts every position against
#: the schema text, and asserts that the first three agree member-for-member
#: with the four-state vocabulary `retrieval/search_state.py` owns.
UNSEARCHED_STATE_POSITION = 0
SEARCHED_NONE_STATE_POSITION = 1
SEARCHED_WITH_RESULTS_STATE_POSITION = 2

#: Position of the sentinel and execution receipt kinds, and of the stop reason
#: that means the declared query plan was worked through to its end.
SENTINEL_KIND_POSITION = 0
EXECUTION_KIND_POSITION = 1
EXHAUSTED_STOP_POSITION = 1

#: Position of the disposition that selects a lane.  The two non-selecting
#: dispositions share their positions with the two sentinel reasons, which is
#: what lets a sentinel receipt carry the plan's own reason rather than a second
#: vocabulary; the suite asserts that alignment rather than assuming it.
SELECTED_DISPOSITION_POSITION = 0

#: Lanes whose absence is not neutral.  Counter-evidence, null, boundary,
#: method and external-novelty lanes are the ones EF4-I06 makes mandatory when
#: applicable, so a *selected* one that never reached a conclusive state is
#: refused rather than averaged away.  The positions are asserted against the
#: canonical lane order.
ADVERSARIAL_LANE_POSITIONS: tuple[int, ...] = (5, 6, 7, 8, 10)

#: Position of the lane and of the novelty layer that cannot be settled from
#: the pinned corpus alone.  Both vocabularies declare it last.
EXTERNAL_LANE_POSITION = -1
EXTERNAL_LAYER_POSITION = -1


class AcquisitionError(ValueError):
    """A retrieval plan, novelty layer or acquisition target breaches a bound."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise AcquisitionError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise AcquisitionError(code, message, context)


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
    return sha256_of_payload(payload)[len(SHA256_PREFIX) :]


def derive_content_addressed_record_identity(
    record: Mapping[str, Any], prefix: str, id_field: str, hash_field: str
) -> tuple[str, str]:
    """Derive a record's content-addressed identifier and canonical hash.

    This is O05's authoritative derivation rule.  Verifiers must call it rather
    than copy its implementation, so producer and verifier cannot drift.
    """
    body = {
        key: value for key, value in record.items() if key not in {id_field, hash_field}
    }
    derived_id = prefix + _digest_body(body)
    identified = {**body, id_field: derived_id}
    return derived_id, hash_excluding(identified, hash_field)


def _identified(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    derived_id, derived_hash = derive_content_addressed_record_identity(
        record, prefix, id_field, hash_field
    )
    record[id_field] = derived_id
    record[hash_field] = derived_hash
    return record


# -- declared vocabularies ------------------------------------------------


def _document(name: str) -> dict[str, Any]:
    return default_registry().document(name)


def lane_vocabulary() -> tuple[str, ...]:
    """The retrieval lanes, read from the receipt schema that declares them."""
    return tuple(_document(RECEIPT_SCHEMA)["$defs"]["lane"]["enum"])


def canonical_lane_order() -> tuple[str, ...]:
    """The lane order the completeness certificate reconciles positionally.

    The receipt schema declares the lanes as a set; only the certificate pins an
    *order*, one positional constant per reconciliation slot.  Reading the order
    from the certificate and cross-checking it against the receipt's own
    vocabulary means a schema edit that changes one and not the other is refused
    here rather than discovered when a certificate fails to validate.
    """
    document = _document(CERTIFICATE_SCHEMA)
    rows = document["properties"]["lane_reconciliations"]["prefixItems"]
    order = tuple(str(row["allOf"][1]["properties"]["lane"]["const"]) for row in rows)
    declared = lane_vocabulary()
    if len(order) != len(declared) or set(order) != set(declared):
        _fail(
            "LANE_UNDECLARED",
            "the certificate and the receipt declare different lane vocabularies",
            {"certificate_order": list(order), "receipt_vocabulary": list(declared)},
        )
    return order


def receipt_state_vocabulary() -> tuple[str, ...]:
    """Lane search states, read from the receipt schema that declares them."""
    return tuple(_document(RECEIPT_SCHEMA)["properties"]["search_state"]["enum"])


def receipt_kind_vocabulary() -> tuple[str, ...]:
    """Sentinel versus execution, read from the receipt's own schema."""
    return tuple(_document(RECEIPT_SCHEMA)["properties"]["receipt_kind"]["enum"])


def sentinel_reason_vocabulary() -> tuple[Any, ...]:
    """Sentinel reasons; the first member is the absence of one."""
    return tuple(_document(RECEIPT_SCHEMA)["properties"]["sentinel_reason"]["enum"])


def stop_reason_vocabulary() -> tuple[Any, ...]:
    """Stop reasons; the first member is the absence of one."""
    return tuple(_document(RECEIPT_SCHEMA)["properties"]["stop_reason"]["enum"])


def plan_disposition_vocabulary() -> tuple[str, ...]:
    """Lane dispositions, read from the certificate's reconciliation shape."""
    document = _document(CERTIFICATE_SCHEMA)
    reconciliation = document["$defs"]["lane_reconciliation"]
    return tuple(reconciliation["properties"]["plan_disposition"]["enum"])


def novelty_layer_vocabulary() -> tuple[str, ...]:
    """The novelty layers, read from the vector schema's own dimensions.

    The names come from the dimension object's property keys in declaration
    order rather than from its ``required`` list, because that word is itself a
    canonical enum value elsewhere and EF4-I22 forbids this module from holding
    another schema's vocabulary as a literal.
    """
    document = _document(VECTOR_SCHEMA)
    return tuple(document["properties"]["dimensions"]["properties"])


def external_novelty_lane() -> str:
    """The one lane a pinned local corpus cannot settle, by canonical position."""
    return canonical_lane_order()[EXTERNAL_LANE_POSITION]


def adversarial_lanes() -> tuple[str, ...]:
    """The lanes whose silence is not neutral, by canonical position."""
    order = canonical_lane_order()
    return tuple(order[position] for position in ADVERSARIAL_LANE_POSITIONS)


def coverage_state(receipt_state: str) -> SearchState:
    """Project a canonical receipt state onto the four-state coverage vocabulary.

    ``retrieval/search_state.py`` owns four states and the receipt schema
    declares six; the three extra ones — partially searched, blocked and failed
    — are all cases where the lane did not conclusively answer, so they project
    onto the failed state rather than onto "searched and found nothing".
    Collapsing them the other way is exactly the inference the search-state
    vocabulary exists to block.
    """
    declared = receipt_state_vocabulary()
    if receipt_state not in declared:
        _fail(
            "RECEIPT_STATE_UNDECLARED",
            f"{receipt_state} is not a canonical lane search state",
            {"declared": list(declared), "search_state": receipt_state},
        )
    try:
        return SearchState(receipt_state)
    except ValueError:
        return SearchState.SEARCH_FAILED


# -- evolution evidence retrieval plan ------------------------------------


def _bound_documents(
    snapshot: Mapping[str, Any], boundary: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Re-derive both K05 records and require the boundary to bound *this* snapshot."""
    try:
        pinned = pinned_documents(snapshot)
        record = require_boundary_identity(boundary)
    except CorpusBoundaryError as error:
        _fail(
            "SNAPSHOT_BOUNDARY_REFUSED",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    snapshot_id = str(snapshot["snapshot_id"])
    if record.get("snapshot_id") != snapshot_id or (
        record.get("corpus_snapshot_hash") != str(snapshot["snapshot_hash"])
    ):
        _fail(
            "BOUNDARY_NOT_FROM_SNAPSHOT",
            "the prior-art boundary does not bound this pinned snapshot",
            {
                "boundary_snapshot_id": record.get("snapshot_id"),
                "snapshot_id": snapshot_id,
            },
        )
    return pinned, record


def build_evolution_retrieval_plan(
    *,
    snapshot: Mapping[str, Any],
    boundary: Mapping[str, Any],
    run_id: str,
    query_plan_id: str,
    subject_document_ids: Sequence[str],
    lane_dispositions: Mapping[str, str],
) -> dict[str, Any]:
    """Declare where an evolution run may look, inside a pinned snapshot.

    The snapshot fixes the bytes and the boundary fixes the date; naming a
    document outside either is refused, and the two refusals stay separate
    because "the corpus never held it" and "the search never reached it" are
    different failures.  Every canonical lane must carry a disposition, because
    the completeness certificate reconciles exactly that many lanes and a plan
    short of one could never produce a valid certificate.
    """
    pinned, record = _bound_documents(snapshot, boundary)
    in_scope = {str(value) for value in record.get("in_scope_document_ids") or []}
    excluded = {str(value) for value in record.get("excluded_document_ids") or []}

    subjects = sorted(
        {
            _require_text(value, f"subject_document_ids[{position}]")
            for position, value in enumerate(
                _require_sequence(subject_document_ids, "subject_document_ids")
            )
        }
    )
    if not subjects:
        _fail(
            "INPUT_INVALID",
            "a retrieval plan must name at least one subject document",
            {"snapshot_id": str(snapshot["snapshot_id"])},
        )
    unpinned = sorted(set(subjects) - set(pinned))
    if unpinned:
        _fail(
            "DOCUMENT_OUTSIDE_SNAPSHOT",
            "the plan names documents the pinned snapshot does not contain",
            {"document_ids": unpinned, "snapshot_id": str(snapshot["snapshot_id"])},
        )
    late = sorted(set(subjects) & (excluded - in_scope))
    if late:
        _fail(
            "DOCUMENT_AFTER_AS_OF",
            "the plan names documents dated after its own as-of bound",
            {"as_of_date": record.get("as_of_date"), "document_ids": late},
        )

    order = canonical_lane_order()
    dispositions = _require_mapping(lane_dispositions, "lane_dispositions")
    undeclared = sorted(set(map(str, dispositions)) - set(order))
    if undeclared:
        _fail(
            "LANE_UNDECLARED",
            "the plan dispositions name lanes outside the canonical vocabulary",
            {"declared": list(order), "undeclared": undeclared},
        )
    missing = [lane for lane in order if lane not in dispositions]
    if missing:
        _fail(
            "LANE_COVERAGE_INCOMPLETE",
            "the plan leaves canonical lanes without a disposition",
            {"missing": missing},
        )
    declared_dispositions = plan_disposition_vocabulary()
    selecting = declared_dispositions[SELECTED_DISPOSITION_POSITION]
    resolved: dict[str, str] = {}
    for lane in order:
        disposition = str(dispositions[lane])
        if disposition not in declared_dispositions:
            _fail(
                "DISPOSITION_UNDECLARED",
                f"lane {lane} carries an undeclared plan disposition",
                {
                    "declared": list(declared_dispositions),
                    "disposition": disposition,
                    "lane": lane,
                },
            )
        resolved[lane] = disposition

    plan: dict[str, Any] = {
        "as_of_date": str(record["as_of_date"]),
        "boundary_hash": str(record["boundary_hash"]),
        "boundary_id": str(record["boundary_id"]),
        "corpus_snapshot_hash": str(snapshot["snapshot_hash"]),
        "excluded_document_ids": sorted(excluded),
        "lane_dispositions": resolved,
        "query_plan_id": _require_text(query_plan_id, "query_plan_id"),
        "run_id": _require_text(run_id, "run_id"),
        "searched_sources": [
            str(value) for value in record.get("searched_sources") or []
        ],
        "selected_lanes": [lane for lane in order if resolved[lane] == selecting],
        "snapshot_id": str(snapshot["snapshot_id"]),
        "subject_document_ids": subjects,
        "unselected_lanes": [lane for lane in order if resolved[lane] != selecting],
        "unsearched_sources": [
            str(value) for value in record.get("unsearched_sources") or []
        ],
    }
    return _identified(plan, PLAN_ID_PREFIX, "plan_id", "plan_hash")


def require_plan_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a retrieval plan's identifier and hash from its own content."""
    record = dict(_require_mapping(plan, "plan"))
    derived_id, derived_hash = derive_content_addressed_record_identity(
        record, PLAN_ID_PREFIX, "plan_id", "plan_hash"
    )
    if record.get("plan_id") != derived_id or record.get("plan_hash") != derived_hash:
        _fail(
            "PLAN_DRIFT",
            "the retrieval plan does not re-derive its own identity",
            {
                "derived_plan_hash": derived_hash,
                "derived_plan_id": derived_id,
                "stated_plan_id": record.get("plan_id"),
            },
        )
    return record


def _plan_lane(plan: Mapping[str, Any], lane: str) -> str:
    order = canonical_lane_order()
    if lane not in order:
        _fail(
            "LANE_UNDECLARED",
            f"{lane} is not a canonical retrieval lane",
            {"declared": list(order), "lane": lane},
        )
    dispositions = _require_mapping(
        plan.get("lane_dispositions"), "plan.lane_dispositions"
    )
    if lane not in dispositions:
        _fail(
            "LANE_COVERAGE_INCOMPLETE",
            f"the plan declares no disposition for lane {lane}",
            {"lane": lane},
        )
    return str(dispositions[lane])


def _emit(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt = _identified(receipt, RECEIPT_ID_PREFIX, "receipt_id", "receipt_hash")
    try:
        validate_artifact(RECEIPT_SCHEMA, receipt)
    except ContractViolation as error:
        _fail(
            "RECEIPT_REFUSED",
            str(error),
            {"errors": list(error.errors), "lane": receipt.get("lane")},
        )
    return receipt


def emit_unsearched_lane_receipt(
    *,
    plan: Mapping[str, Any],
    lane: str,
    lane_decision_evidence_ids: Sequence[str],
) -> dict[str, Any]:
    """Emit the truthful sentinel for a lane the plan chose not to select.

    The sentinel reason is the plan's own disposition rather than a second
    vocabulary: the two lists are declared in the same order, and the suite
    asserts that alignment instead of assuming it.  A lane the plan *did*
    select cannot take a sentinel, because "we chose to look" and "we never
    looked" would then be recorded as the same thing.
    """
    record = require_plan_identity(plan)
    disposition = _plan_lane(record, lane)
    dispositions = plan_disposition_vocabulary()
    if disposition == dispositions[SELECTED_DISPOSITION_POSITION]:
        _fail(
            "LANE_DISPOSITION_CONFLICT",
            f"lane {lane} was selected, so it cannot carry an unsearched sentinel",
            {"disposition": disposition, "lane": lane},
        )
    reasons = sentinel_reason_vocabulary()
    states = receipt_state_vocabulary()
    kinds = receipt_kind_vocabulary()
    receipt: dict[str, Any] = {
        "corpus_snapshot_hash": None,
        "errors": [],
        "excluded_count": None,
        "finished_at": None,
        "index_versions": None,
        "lane": lane,
        "lane_decision_evidence_ids": [
            _require_text(value, f"lane_decision_evidence_ids[{position}]")
            for position, value in enumerate(
                _require_sequence(
                    lane_decision_evidence_ids, "lane_decision_evidence_ids"
                )
            )
        ],
        "plan_hash": str(record["plan_hash"]),
        "query_hash": None,
        "query_plan_id": str(record["query_plan_id"]),
        "query_text": None,
        "recall_proxy": None,
        "result_count": None,
        "result_ids": None,
        "run_id": str(record["run_id"]),
        "scope_filter": None,
        "search_state": states[UNSEARCHED_STATE_POSITION],
        "sentinel_reason": reasons[dispositions.index(disposition)],
        "started_at": None,
        "stop_reason": None,
    }
    receipt["receipt_kind"] = kinds[SENTINEL_KIND_POSITION]
    return _emit(receipt)


def emit_searched_lane_receipt(
    *,
    plan: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    lane: str,
    query_text: str,
    scope_filter: Mapping[str, Any],
    index_versions: Mapping[str, str],
    result_document_ids: Sequence[str],
    lane_decision_evidence_ids: Sequence[str],
    started_at: str,
    finished_at: str,
    excluded_count: int = 0,
) -> dict[str, Any]:
    """Emit the execution receipt for a selected lane, inside the pinned snapshot.

    The search state is *derived* from the results rather than supplied: a
    caller that both runs the lane and labels how well it ran can label an
    empty lane as complete.  A result the snapshot never pinned is refused,
    because that is the search escaping the evidence boundary while running.
    """
    record = require_plan_identity(plan)
    disposition = _plan_lane(record, lane)
    dispositions = plan_disposition_vocabulary()
    if disposition != dispositions[SELECTED_DISPOSITION_POSITION]:
        _fail(
            "LANE_DISPOSITION_CONFLICT",
            f"lane {lane} was not selected, so it cannot carry an execution receipt",
            {"disposition": disposition, "lane": lane},
        )
    try:
        pinned = pinned_documents(snapshot)
    except CorpusBoundaryError as error:
        _fail(
            "SNAPSHOT_BOUNDARY_REFUSED",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    if str(snapshot["snapshot_hash"]) != str(record["corpus_snapshot_hash"]):
        _fail(
            "BOUNDARY_NOT_FROM_SNAPSHOT",
            "the receipt would bind a snapshot the plan does not pin",
            {
                "plan_id": str(record["plan_id"]),
                "snapshot_id": str(snapshot["snapshot_id"]),
            },
        )

    results = [
        _require_text(value, f"result_document_ids[{position}]")
        for position, value in enumerate(
            _require_sequence(result_document_ids, "result_document_ids")
        )
    ]
    if len(set(results)) != len(results):
        _fail(
            "INPUT_INVALID",
            "a lane cannot return the same document twice",
            {"lane": lane, "result_document_ids": results},
        )
    escaped = sorted(set(results) - set(pinned))
    if escaped:
        _fail(
            "RESULT_OUTSIDE_SNAPSHOT",
            "the lane returned documents the pinned snapshot never pinned",
            {"document_ids": escaped, "lane": lane},
        )
    after_as_of = sorted(
        set(results) & set(record.get("excluded_document_ids") or [])
    )
    if after_as_of:
        _fail(
            "DOCUMENT_AFTER_AS_OF",
            "the lane returned documents dated after the plan's as-of bound",
            {
                "as_of_date": record.get("as_of_date"),
                "document_ids": after_as_of,
                "lane": lane,
            },
        )
    if not isinstance(excluded_count, int) or isinstance(excluded_count, bool):
        _fail(
            "INPUT_INVALID",
            "excluded_count must be an integer",
            {"excluded_count": excluded_count},
        )
    if excluded_count < 0:
        _fail(
            "INPUT_INVALID",
            "excluded_count cannot be negative",
            {"excluded_count": excluded_count},
        )

    states = receipt_state_vocabulary()
    kinds = receipt_kind_vocabulary()
    stops = stop_reason_vocabulary()
    text = _require_text(query_text, "query_text")
    receipt: dict[str, Any] = {
        "corpus_snapshot_hash": str(record["corpus_snapshot_hash"]),
        "errors": [],
        "excluded_count": excluded_count,
        "finished_at": _require_text(finished_at, "finished_at"),
        "index_versions": {
            _require_text(key, "index_versions key"): _require_text(
                value, f"index_versions[{key}]"
            )
            for key, value in _require_mapping(index_versions, "index_versions").items()
        },
        "lane": lane,
        "lane_decision_evidence_ids": [
            _require_text(value, f"lane_decision_evidence_ids[{position}]")
            for position, value in enumerate(
                _require_sequence(
                    lane_decision_evidence_ids, "lane_decision_evidence_ids"
                )
            )
        ],
        "plan_hash": str(record["plan_hash"]),
        "query_hash": sha256_hex(text.encode("utf-8")),
        "query_plan_id": str(record["query_plan_id"]),
        "query_text": text,
        "recall_proxy": None,
        "result_count": len(results),
        "result_ids": sorted(results),
        "run_id": str(record["run_id"]),
        "scope_filter": dict(_require_mapping(scope_filter, "scope_filter")),
        "search_state": states[
            SEARCHED_WITH_RESULTS_STATE_POSITION
            if results
            else SEARCHED_NONE_STATE_POSITION
        ],
        "sentinel_reason": None,
        "started_at": _require_text(started_at, "started_at"),
        "stop_reason": stops[EXHAUSTED_STOP_POSITION],
    }
    receipt["receipt_kind"] = kinds[EXECUTION_KIND_POSITION]
    return _emit(receipt)


# -- multi-layer novelty ---------------------------------------------------


def canonical_layer_scores(layer_scores: Mapping[str, Any]) -> dict[str, float]:
    """Exactly the layers the vector schema declares, each a number in its range.

    A missing layer and an undeclared one fail together: an omitted layer would
    be read as either no novelty or full novelty, and it is neither.
    """
    record = _require_mapping(layer_scores, "layer_scores")
    declared = novelty_layer_vocabulary()
    given = set(map(str, record))
    expected = set(declared)
    if given != expected:
        _fail(
            "NOVELTY_LAYER_UNDECLARED",
            "the layer scores do not name exactly the declared novelty layers",
            {
                "declared": list(declared),
                "missing": sorted(expected - given),
                "undeclared": sorted(given - expected),
            },
        )
    scores: dict[str, float] = {}
    for layer in declared:
        value = record[layer]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail(
                "NOVELTY_LAYER_UNDECLARED",
                f"layer {layer} does not carry a numeric novelty score",
                {"layer": layer, "value": value},
            )
        scores[layer] = float(value)
    return scores


def assess_layered_novelty(
    *,
    boundary: Mapping[str, Any],
    plan: Mapping[str, Any],
    candidate_id: str,
    subject_ref: str,
    statement_hash: str,
    search_completeness_certificate_id: str,
    layer_scores: Mapping[str, Any],
    novelty_dimensions: Sequence[str],
    nearest_candidate_ids: Sequence[str],
    closest_prior_art_refs: Sequence[str],
    distinguishing_features: Sequence[str],
    assessor_ref: str,
    assessed_at: str,
    external_search_completed: bool = False,
    uncertainties: Sequence[str] = (),
) -> dict[str, Any]:
    """Bind one layered novelty record to a boundary and a declared plan.

    The per-layer vector is written by the module that owns the layers and the
    corpus-bounded assessment by the module that owns the ladder; this module
    binds the two to one boundary and one plan and refuses the combination that
    would let either read as more than it is.  Declaring the external search
    complete while the boundary still names unsearched sources is that
    combination, and it is refused rather than downgraded, because a downgrade
    would leave the caller's false claim in the record.
    """
    if type(external_search_completed) is not bool:
        _fail(
            "INPUT_INVALID",
            "external_search_completed must be a boolean",
            {"external_search_completed": external_search_completed},
        )
    record = require_plan_identity(plan)
    try:
        bounded = require_boundary_identity(boundary)
    except CorpusBoundaryError as error:
        _fail(
            "SNAPSHOT_BOUNDARY_REFUSED",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises
    if str(bounded["boundary_id"]) != str(record.get("boundary_id")) or (
        str(bounded["boundary_hash"]) != str(record.get("boundary_hash"))
    ):
        _fail(
            "BOUNDARY_NOT_FROM_SNAPSHOT",
            "the assessment binds a boundary the retrieval plan does not declare",
            {
                "boundary_id": str(bounded["boundary_id"]),
                "plan_boundary_id": record.get("boundary_id"),
            },
        )

    scores = canonical_layer_scores(layer_scores)
    unsearched = [str(value) for value in bounded.get("unsearched_sources") or []]
    if external_search_completed and unsearched:
        _fail(
            "EXTERNAL_LAYER_UNBOUNDED",
            "the boundary names unsearched sources, so the external layer is open",
            {
                "external_layer": novelty_layer_vocabulary()[EXTERNAL_LAYER_POSITION],
                "unsearched_sources": unsearched,
            },
        )

    try:
        assessment = assess_novelty_within_boundary(
            boundary=bounded,
            run_id=str(record["run_id"]),
            subject_ref=subject_ref,
            statement_hash=statement_hash,
            search_completeness_certificate_id=search_completeness_certificate_id,
            novelty_dimensions=novelty_dimensions,
            closest_prior_art_refs=closest_prior_art_refs,
            distinguishing_features=distinguishing_features,
            assessor_ref=assessor_ref,
            assessed_at=assessed_at,
        )
    except CorpusBoundaryError as error:
        _fail(
            "SNAPSHOT_BOUNDARY_REFUSED",
            str(error),
            {"corpus_finding_code": error.code, "corpus_context": error.context},
        )
        raise  # pragma: no cover - _fail always raises

    subject = _require_text(candidate_id, "candidate_id")
    stated = [
        _require_text(value, f"uncertainties[{position}]")
        for position, value in enumerate(
            _require_sequence(uncertainties, "uncertainties")
        )
    ]
    declared_uncertainties = [
        *stated,
        *(f"source {source} was not searched" for source in unsearched),
    ]
    vector_id = VECTOR_ID_PREFIX + _digest_body(
        {
            "assessed_at": str(assessment["assessed_at"]),
            "boundary_hash": str(bounded["boundary_hash"]),
            "candidate_id": subject,
            "layer_scores": scores,
        }
    )
    try:
        vector = build_novelty_vector(
            candidate_id=subject,
            dimensions=scores,
            nearest_candidate_ids=[
                _require_text(value, f"nearest_candidate_ids[{position}]")
                for position, value in enumerate(
                    _require_sequence(nearest_candidate_ids, "nearest_candidate_ids")
                )
            ],
            external_search_certificate_id=_require_text(
                search_completeness_certificate_id,
                "search_completeness_certificate_id",
            ),
            uncertainties=declared_uncertainties,
            external_search_completed=external_search_completed,
            novelty_vector_id=vector_id,
            computed_at=str(assessment["assessed_at"]),
        )
    except (ContractViolation, NoveltyVectorRefused) as error:
        _fail("VECTOR_REFUSED", str(error), {"candidate_id": subject})
        raise  # pragma: no cover - _fail always raises

    status_field, _ = scalar_enum_field(NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION)
    ceiling_field, _ = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)
    layered: dict[str, Any] = {
        "assessment": dict(assessment),
        "boundary_hash": str(bounded["boundary_hash"]),
        "boundary_id": str(bounded["boundary_id"]),
        "candidate_id": subject,
        "external_search_completed": external_search_completed,
        "inherited_ceiling": str(assessment[ceiling_field]),
        "inherited_status": str(assessment[status_field]),
        "layer_scores": scores,
        "layers": list(novelty_layer_vocabulary()),
        "novelty_vector": dict(vector),
        "plan_hash": str(record["plan_hash"]),
        "plan_id": str(record["plan_id"]),
        "unsearched_sources": unsearched,
    }
    return _identified(
        layered, LAYERED_ID_PREFIX, "layered_novelty_id", "layered_novelty_hash"
    )


def require_layered_novelty_identity(layered: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a layered novelty record's identifier and hash from its content."""
    record = dict(_require_mapping(layered, "layered_novelty"))
    derived_id, derived_hash = derive_content_addressed_record_identity(
        record, LAYERED_ID_PREFIX, "layered_novelty_id", "layered_novelty_hash"
    )
    if record.get("layered_novelty_id") != derived_id or (
        record.get("layered_novelty_hash") != derived_hash
    ):
        _fail(
            "PLAN_DRIFT",
            "the layered novelty record does not re-derive its own identity",
            {
                "derived_layered_novelty_hash": derived_hash,
                "derived_layered_novelty_id": derived_id,
                "stated_layered_novelty_id": record.get("layered_novelty_id"),
            },
        )
    return record


# -- coverage-debt acquisition --------------------------------------------


def _validated_niche(candidate: object, position: int) -> dict[str, Any]:
    niche = dict(_require_mapping(candidate, f"niches[{position}]"))
    try:
        validate_artifact(NICHE_SCHEMA, niche)
    except ContractViolation as error:
        debt_errors = [
            entry for entry in error.errors if entry.startswith("coverage_debt")
        ]
        if debt_errors:
            _fail(
                "COVERAGE_DEBT_OUT_OF_RANGE",
                "; ".join(debt_errors),
                {"coverage_debt": niche.get("coverage_debt"), "position": position},
            )
        _fail(
            "NICHE_REFUSED",
            str(error),
            {"errors": list(error.errors), "position": position},
        )
    return niche


def rank_acquisition_targets(
    *, niches: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], ...]:
    """Order acquisition targets by the coverage debt the niches declare.

    The ordering is descending debt with the niche identifier as the tie break,
    so it is total and two runs over equal input produce byte-equal rankings.
    Cell identity and single occupancy are the sealed cartography's to enforce
    and its refusal is surfaced, never worked around.
    """
    rows = _require_sequence(niches, "niches")
    if not rows:
        _fail(
            "ACQUISITION_TARGETS_EMPTY",
            "an acquisition ranking needs at least one niche to rank",
        )
    validated = [
        _validated_niche(candidate, position) for position, candidate in enumerate(rows)
    ]
    try:
        niche_map = NicheMap(validated)
    except CartographyError as error:
        _fail(
            "NICHE_REFUSED",
            str(error),
            {
                "cartography_context": error.context,
                "cartography_finding_code": error.code,
            },
        )
        raise  # pragma: no cover - _fail always raises

    ordered = sorted(
        (niche_map.niche(niche_id) for niche_id in niche_map.niche_ids()),
        key=lambda niche: (-float(niche["coverage_debt"]), str(niche["niche_id"])),
    )
    targets: list[dict[str, Any]] = []
    for position, niche in enumerate(ordered):
        occupants = list(niche["occupant_ids"])
        capacity = int(niche["capacity"])
        target: dict[str, Any] = {
            "acquisition_rank": position + 1,
            "capacity": capacity,
            "coverage_debt": float(niche["coverage_debt"]),
            "niche_hash": str(niche["niche_hash"]),
            "niche_id": str(niche["niche_id"]),
            "occupant_count": len(occupants),
            "vacancy": capacity - len(occupants),
        }
        targets.append(
            _identified(target, TARGET_ID_PREFIX, "target_id", "target_hash")
        )
    return tuple(targets)


def build_coverage_debt_acquisition_plan(
    *,
    plan: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    niches: Sequence[Mapping[str, Any]],
    target_budget: int,
    evolution_run_id: str,
    generation: int,
) -> dict[str, Any]:
    """Rank where the run is still blind, and record what it did not search.

    Every canonical lane must carry exactly one receipt bound to this plan, and
    a *selected* adversarial lane that never reached a conclusive state is
    refused: acquiring against an unsearched counter, null, boundary, method or
    novelty lane would spend a generation on a gap that may not exist.  The
    deferred niches, the unsearched sources, the unselected lanes and the
    documents the as-of bound excluded are all carried on the plan, because an
    acquisition plan that records only what it will do reads as complete.
    """
    record = require_plan_identity(plan)
    order = canonical_lane_order()
    rows = _require_sequence(receipts, "receipts")

    states: dict[str, str] = {}
    receipt_ids: dict[str, str] = {}
    for position, candidate in enumerate(rows):
        receipt = dict(_require_mapping(candidate, f"receipts[{position}]"))
        try:
            validate_artifact(RECEIPT_SCHEMA, receipt)
        except ContractViolation as error:
            _fail(
                "RECEIPT_REFUSED",
                str(error),
                {"errors": list(error.errors), "position": position},
            )
        if str(receipt.get("plan_hash")) != str(record["plan_hash"]):
            _fail(
                "RECEIPT_NOT_FROM_PLAN",
                "a lane receipt binds a different retrieval plan",
                {"plan_id": str(record["plan_id"]), "position": position},
            )
        lane = str(receipt["lane"])
        if lane in states:
            _fail(
                "LANE_COVERAGE_INCOMPLETE",
                f"lane {lane} carries more than one receipt in this reconciliation",
                {"lane": lane},
            )
        states[lane] = str(receipt["search_state"])
        receipt_ids[lane] = str(receipt["receipt_id"])
    absent = [lane for lane in order if lane not in states]
    if absent:
        _fail(
            "LANE_COVERAGE_INCOMPLETE",
            "the receipt set does not account for every canonical lane",
            {"missing": absent},
        )

    projected = {lane: coverage_state(states[lane]).value for lane in order}
    dispositions = plan_disposition_vocabulary()
    selecting = dispositions[SELECTED_DISPOSITION_POSITION]
    plan_dispositions = _require_mapping(
        record.get("lane_dispositions"), "plan.lane_dispositions"
    )
    applicable = [
        lane
        for lane in adversarial_lanes()
        if str(plan_dispositions.get(lane)) == selecting
    ]
    uncovered = missing_lanes(projected, applicable=applicable)
    if uncovered:
        _fail(
            "MANDATORY_LANE_UNCOVERED",
            "selected adversarial lanes were never conclusively searched",
            {
                "lanes": uncovered,
                "search_states": {lane: states[lane] for lane in uncovered},
            },
        )

    targets = rank_acquisition_targets(niches=niches)
    if not isinstance(target_budget, int) or isinstance(target_budget, bool):
        _fail(
            "TARGET_BUDGET_INVALID",
            "target_budget must be an integer count of niches",
            {"target_budget": target_budget},
        )
    if target_budget < 1:
        _fail(
            "TARGET_BUDGET_INVALID",
            "target_budget must select at least one niche",
            {"target_budget": target_budget},
        )
    selected = list(targets[:target_budget])
    deferred = list(targets[target_budget:])

    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
    ):
        _fail(
            "INPUT_INVALID",
            "generation must be a non-negative integer",
            {"generation": generation},
        )

    acquisition: dict[str, Any] = {
        "acquisition_targets": selected,
        "as_of_date": str(record["as_of_date"]),
        "boundary_id": str(record["boundary_id"]),
        "corpus_snapshot_hash": str(record["corpus_snapshot_hash"]),
        "deferred_niche_ids": [str(target["niche_id"]) for target in deferred],
        "evolution_run_id": _require_text(evolution_run_id, "evolution_run_id"),
        "generation": generation,
        "lane_receipt_ids": [receipt_ids[lane] for lane in order],
        "lane_search_states": {lane: states[lane] for lane in order},
        "not_searched": {
            "deferred_niche_ids": [str(target["niche_id"]) for target in deferred],
            "excluded_document_ids": list(record.get("excluded_document_ids") or []),
            "unselected_lanes": list(record.get("unselected_lanes") or []),
            "unsearched_sources": list(record.get("unsearched_sources") or []),
        },
        "plan_hash": str(record["plan_hash"]),
        "plan_id": str(record["plan_id"]),
        "projected_coverage_states": projected,
        "ranked_niche_count": len(targets),
        "snapshot_id": str(record["snapshot_id"]),
        "target_budget": target_budget,
    }
    return _identified(
        acquisition,
        ACQUISITION_ID_PREFIX,
        "acquisition_plan_id",
        "acquisition_plan_hash",
    )


def require_acquisition_plan_identity(
    acquisition_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute an acquisition plan's identifier and hash from its own content."""
    record = dict(_require_mapping(acquisition_plan, "acquisition_plan"))
    derived_id, derived_hash = derive_content_addressed_record_identity(
        record,
        ACQUISITION_ID_PREFIX,
        "acquisition_plan_id",
        "acquisition_plan_hash",
    )
    if record.get("acquisition_plan_id") != derived_id or (
        record.get("acquisition_plan_hash") != derived_hash
    ):
        _fail(
            "PLAN_DRIFT",
            "the acquisition plan does not re-derive its own identity",
            {
                "derived_acquisition_plan_hash": derived_hash,
                "derived_acquisition_plan_id": derived_id,
                "stated_acquisition_plan_id": record.get("acquisition_plan_id"),
            },
        )
    return record


def acquisition_plan_is_rederivable(
    acquisition_plan: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    niches: Sequence[Mapping[str, Any]],
) -> bool:
    """True when rebuilding the plan from its inputs reproduces it exactly.

    This is the replay check rather than a second identity check: the identity
    functions prove a record is internally consistent, this proves the record is
    the deterministic function of the inputs it names.
    """
    record = require_acquisition_plan_identity(acquisition_plan)
    rebuilt = build_coverage_debt_acquisition_plan(
        plan=plan,
        receipts=receipts,
        niches=niches,
        target_budget=int(record["target_budget"]),
        evolution_run_id=str(record["evolution_run_id"]),
        generation=int(record["generation"]),
    )
    return sha256_of_payload(rebuilt) == sha256_of_payload(record)


def statement_digest(statement: str) -> str:
    """The canonical digest of a claim statement, for callers without one.

    Provided so a caller never invents a digest shape: the assessment refuses a
    ``statement_hash`` that is not canonical, and this is the one derivation
    that produces one.
    """
    text = _require_text(statement, "statement")
    digest = sha256_of_payload(text)
    if not is_schema_digest(digest):  # pragma: no cover - hashing invariant
        _fail("INPUT_INVALID", "the canonical digest is not schema-shaped")
    return digest
