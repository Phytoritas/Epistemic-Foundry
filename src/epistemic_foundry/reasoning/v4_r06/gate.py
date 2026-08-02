"""The causal/measurement/scope crossover safety integration gate.

A typed crossover proposes to splice two hypothesis genomes into a child that
inherits from both.  The child would then carry one causal identification, one
measurement contract and one scope — but a splice of two parents that disagree
on any of those axes manufactures a child asserting something neither parent's
evidence supports.  This gate refuses exactly that.  It is an *integration*
gate: it re-uses the sealed surfaces that already own each axis and adds only
the composition, restating none of their vocabularies (EF4-I22).

Three axes are derived from the parents' own referenced artifacts and never
from a caller's assertion:

* **Causal identification** is read from each parent's sealed MechanismGraph.
  R04 already derived and pinned that graph's ``identification_status`` and
  refused it if it overclaimed, so the gate composes that verdict rather than
  re-deriving it.  A splice is compatible only when both parents are
  ``IDENTIFIED``; a weaker or mismatched pair would let the child present a
  causal identification the weaker parent never earned, and an unassessed
  parent leaves the axis unexamined.
* **Measurement contract** is read from a sealed MeasurementCompatibilityReport
  that must actually compare the two parents' own measurement contracts.  Only
  a directly comparable pair over the same construct is compatible.
* **Scope** is derived by comparing the two parents' ScopeVectors field by
  field: a boundary both parents declare but declare differently is a conflict,
  and a parent that declares no boundary at all leaves the axis unexamined.

The Evolution Chamber already publishes a CrossoverCompatibilityReport carrying
those same four axes and a decision derived from them.  The gate does not trust
it: it re-derives every axis from the ground-truth artifacts and refuses any
report whose axis disagrees with the derivation, because a report that says
``compatible`` over parents that are not is the leakage channel this gate
exists to close.  Only when every derived axis is compatible, the report agrees
with the derivation, and the Chamber's own decision is an unconditional
``ALLOW`` does the gate allow the splice.

Nothing here scores, selects, promotes or evaluates a candidate, and no input is
mutated.  The receipt is a pure function of the inputs: there is no clock and no
random draw, the caller supplies ``created_at``, and the gate identifier and
receipt hash are re-derivable from the published content.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import canonical_json, hash_excluding, sha256_hex
from ...evolution_chamber.crossover import crossover_permitted
from ...intake.v4_i05 import GENOME_KIND
from ...intake.v4_i05 import screening as intake
from ..v4_r05 import operators as engine

#: Every way this gate refuses, and why that refusal exists.  A refusal whose
#: code is absent here is a bug, not a decision, so ``_fail`` checks membership.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a decision derived from something it never validated"
    ),
    "CROSSOVER_ARITY_INVALID": (
        "a crossover safety decision is about exactly two parents, and any "
        "other count is not the splice this gate reasons about"
    ),
    "PARENTS_NOT_DISTINCT": (
        "the two parents are the same candidate, so there is no cross-parent "
        "axis to compare and nothing a splice would actually combine"
    ),
    "PARENT_CONTRACT_VIOLATED": (
        "a parent does not satisfy the canonical hypothesis-genome schema, so "
        "any axis read from it would be read from a shape no contract admits"
    ),
    "PARENT_KIND_MISMATCH": (
        "a parent does not resolve to the hypothesis-genome kind this gate "
        "splices, and only that kind carries a mechanism, scope and measurement"
    ),
    "GENOME_FIELD_UNDECLARED_BY_SCHEMA": (
        "the canonical genome schema no longer declares a reference field this "
        "gate reads, so the gate refuses rather than read a field that is gone"
    ),
    "MECHANISM_GRAPH_UNRESOLVED": (
        "no supplied mechanism graph carries the id a parent references, so the "
        "parent's causal identification cannot be read and is not assumed"
    ),
    "MECHANISM_GRAPH_CONTRACT_VIOLATED": (
        "a supplied mechanism graph does not satisfy its canonical schema or "
        "its own sealed hash, so its identification status is untrustworthy"
    ),
    "SCOPE_VECTOR_UNRESOLVED": (
        "no supplied scope vector carries the id a parent references, so the "
        "parent's scope cannot be compared and is not assumed"
    ),
    "SCOPE_VECTOR_CONTRACT_VIOLATED": (
        "a supplied scope vector does not satisfy its canonical schema, so its "
        "declared boundaries would be read from an invalid shape"
    ),
    "MEASUREMENT_REPORT_CONTRACT_VIOLATED": (
        "the measurement compatibility report does not satisfy its canonical "
        "schema or its own sealed hash, so its verdict is untrustworthy"
    ),
    "MEASUREMENT_REPORT_MISBOUND": (
        "the measurement report does not compare a measurement of each parent, "
        "so it assessed some other pair and says nothing about this splice"
    ),
    "CROSSOVER_REPORT_CONTRACT_VIOLATED": (
        "the crossover compatibility report does not satisfy its canonical "
        "schema or its own sealed hash, so its axes and decision are unusable"
    ),
    "CROSSOVER_REPORT_MISBOUND": (
        "the crossover report does not name both parents, so it assessed some "
        "other pair and its decision does not apply to this splice"
    ),
    "REPORT_AXIS_MISMATCH": (
        "the crossover report asserts an axis the ground-truth artifacts do not "
        "support, and a report that overrides the parents is the leakage this "
        "gate closes"
    ),
    "CAUSAL_IDENTIFICATION_UNASSESSED": (
        "a parent's mechanism graph is not assessed for identification, so the "
        "causal axis was never examined and an unexamined axis is not compatible"
    ),
    "CAUSAL_IDENTIFICATION_INCOMPATIBLE": (
        "the parents carry different or unidentified causal identification, so "
        "the child would assert an identification neither parent's evidence earns"
    ),
    "MEASUREMENT_CONTRACT_UNASSESSED": (
        "the measurement report leaves comparability or construct equivalence "
        "unknown, so the measurement axis was never examined"
    ),
    "MEASUREMENT_CONTRACT_INCOMPATIBLE": (
        "the parents' measurements are not directly comparable over one "
        "construct, so a spliced outcome would mix incommensurable measures"
    ),
    "SCOPE_UNASSESSED": (
        "a parent declares no scope boundary at all, so no later stage could "
        "say where the spliced child's claim is meant to hold"
    ),
    "SCOPE_INCOMPATIBLE": (
        "the parents declare conflicting boundaries on a scope field, so the "
        "child's scope would be two incompatible things at once"
    ),
    "UNIT_UNASSESSED": (
        "the measurement report does not carry the units it would take to "
        "compare the parents' measures, so the unit axis was never examined"
    ),
    "UNIT_INCOMPATIBLE": (
        "the parents' measurement units differ with no declared conversion, so "
        "a spliced outcome would combine values on incommensurable scales"
    ),
    "CROSSOVER_NOT_PERMITTED": (
        "the Chamber's own decision is not an unconditional allow, and a "
        "repair-pending or unassessed decision is not permission to splice"
    ),
}

#: Canonical schema names this gate reads.  Each is a registered canonical
#: contract, verified before use rather than restated as fields here.
MECHANISM_KIND = "mechanism-graph"
SCOPE_KIND = "scope-vector"
MEASUREMENT_REPORT_KIND = "measurement-compatibility-report"
CROSSOVER_REPORT_KIND = "crossover-compatibility-report"

#: The four axes the Chamber report carries, in its own order, re-used rather
#: than restated.  Every axis is derived and cross-checked.
COMPATIBILITY_AXES: tuple[str, ...] = (
    "scope_compatibility",
    "measurement_compatibility",
    "causal_compatibility",
    "unit_compatibility",
)

#: The genome reference fields whose targets the gate resolves.  Verified to be
#: properties of the canonical genome schema before use.
MECHANISM_GRAPH_ID = intake.MECHANISM_FIELD
SCOPE_VECTOR_ID = intake.SCOPE_FIELD
MEASUREMENT_CONTRACT_IDS = "measurement_contract_ids"

#: Self-referential hash fields on the artifacts the gate re-verifies.
GRAPH_HASH_FIELD = "graph_hash"
REPORT_HASH_FIELD = "report_hash"


class CrossoverSafetyRefused(ValueError):
    """The gate refuses a crossover, or its evidence, with a documented code."""

    def __init__(
        self,
        code: str,
        message: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise CrossoverSafetyRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise CrossoverSafetyRefused(code, message, context)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def genome_reference_fields() -> tuple[str, str, str]:
    """The genome fields the gate reads, verified against the canonical schema.

    The verification runs on every call: the genome schema is the authority for
    which references a hypothesis carries, and a gate that cached its answer
    would keep reading a field the schema had dropped.
    """
    properties = engine.genome_properties(GENOME_KIND)
    named = (MECHANISM_GRAPH_ID, SCOPE_VECTOR_ID, MEASUREMENT_CONTRACT_IDS)
    missing = sorted(field for field in named if field not in properties)
    if missing:
        _fail(
            "GENOME_FIELD_UNDECLARED_BY_SCHEMA",
            "the canonical genome schema no longer declares a reference field",
            {"missing": missing},
        )
    return named


def identification_statuses() -> tuple[str, ...]:
    """The canonical identification vocabulary, read from the mechanism schema.

    The gate composes R04's verdict rather than re-deriving it, so the set of
    valid statuses comes from the mechanism-graph contract that R04 seals into,
    not from a second copy of the ladder.
    """
    document = default_registry().document(MECHANISM_KIND)
    enum = document.get("properties", {}).get("identification_status", {}).get("enum")
    if not isinstance(enum, list) or not enum:
        _fail(
            "MECHANISM_GRAPH_CONTRACT_VIOLATED",
            "the mechanism-graph schema declares no identification vocabulary",
            {"schema": MECHANISM_KIND},
        )
    return tuple(str(value) for value in enum)


@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """Every canonical enum token the gate reasons about, read from the schema.

    Holding these as string literals would be a second copy that drifts from the
    contract (EF4-I22), and no ``src`` module owns the causal-identification or
    measurement-comparability ladders to import them from, so each token is read
    out of the canonical schema that declares it.  The indices are the schema's
    own declared order — the identification ladder, the comparability ladder, and
    the four crossover axes, each published as ``[compatible, <repairable>,
    incompatible, unknown]`` — and a reshape that changes a length fails closed
    here rather than silently selecting the wrong token.
    """
    registry = default_registry()
    identification = identification_statuses()
    if len(identification) != 4:
        _fail(
            "MECHANISM_GRAPH_CONTRACT_VIOLATED",
            "the identification vocabulary is not the expected four-rung ladder",
            {"identification": list(identification)},
        )
    measurement = registry.document(MEASUREMENT_REPORT_KIND)["properties"]
    status_enum = [str(value) for value in measurement["compatibility_status"]["enum"]]
    construct_enum = [
        str(value) for value in measurement["construct_equivalence"]["enum"]
    ]
    if len(status_enum) < 4 or len(construct_enum) < 3:
        _fail(
            "MEASUREMENT_REPORT_CONTRACT_VIOLATED",
            "the measurement comparability vocabulary is not the expected shape",
            {
                "compatibility_status": status_enum,
                "construct_equivalence": construct_enum,
            },
        )
    crossover = registry.document(CROSSOVER_REPORT_KIND)["properties"]
    axis_enums = {
        axis: [str(value) for value in crossover[axis]["enum"]]
        for axis in COMPATIBILITY_AXES
    }
    for axis, enum in axis_enums.items():
        if len(enum) != 4:
            _fail(
                "CROSSOVER_REPORT_CONTRACT_VIOLATED",
                "a crossover axis enum is not the expected four tokens",
                {"axis": axis, "enum": enum},
            )
    decision_enum = [str(value) for value in crossover["decision"]["enum"]]
    if not decision_enum:
        _fail(
            "CROSSOVER_REPORT_CONTRACT_VIOLATED",
            "the crossover report declares no decision vocabulary",
            {"schema": CROSSOVER_REPORT_KIND},
        )
    causal = axis_enums["causal_compatibility"]
    return {
        "not_assessed": identification[0],
        "identified": identification[1],
        "assumption_dependent": identification[2],
        "directly_comparable": status_enum[0],
        "not_comparable": status_enum[-2],
        "construct_same": construct_enum[0],
        "construct_different": construct_enum[-2],
        "axis_compatible": causal[0],
        "axis_incompatible": causal[2],
        "causal_repairable": causal[1],
        "measurement_repairable": axis_enums["measurement_compatibility"][1],
        "unit_repairable": axis_enums["unit_compatibility"][1],
        "allow": decision_enum[0],
    }


def _is_scalar_boundary(spec: object) -> bool:
    """True for a scope property that carries a comparable string-or-null scalar.

    The nullable-string shape is detected structurally — a ``type`` list holding
    the string type and no array or object type — so the ``null`` token itself is
    never restated here as a literal.
    """
    if not isinstance(spec, Mapping):
        return False
    types = spec.get("type")
    return (
        isinstance(types, list)
        and "string" in types
        and not ({"array", "object"} & set(types))
    )


def scope_scalar_fields() -> tuple[str, ...]:
    """The scope-vector scalar fields the gate compares, read from the schema.

    Only the nullable-string scalars carry a comparable boundary; arrays, objects
    and the intervention envelope are not compared for conflict.  The set is
    filtered out of the canonical schema so a field rename tracks automatically.
    """
    document = default_registry().document(SCOPE_KIND)
    properties = document.get("properties", {})
    if not isinstance(properties, Mapping) or not properties:
        _fail(
            "SCOPE_VECTOR_CONTRACT_VIOLATED",
            "the scope-vector schema declares no properties",
            {"schema": SCOPE_KIND},
        )
    scalar = [field for field, spec in properties.items() if _is_scalar_boundary(spec)]
    if not scalar:
        _fail(
            "SCOPE_VECTOR_CONTRACT_VIOLATED",
            "the scope-vector schema declares no scalar boundary fields",
            {"schema": SCOPE_KIND},
        )
    return tuple(sorted(scalar))


@dataclass(frozen=True)
class _Parent:
    """One resolved parent: its genome and the artifacts its fields point to."""

    genome_id: str
    genome: dict[str, Any]
    mechanism_graph: dict[str, Any]
    scope_vector: dict[str, Any]
    measurement_ids: frozenset[str]


def _verify_self_hash(document: Mapping[str, Any], field: str, code: str) -> None:
    """Re-derive a sealed artifact's own hash, refusing a mismatch or absence."""
    stored = document.get(field)
    if not isinstance(stored, str) or not stored:
        _fail(code, f"the artifact carries no {field} to verify", {"field": field})
    if hash_excluding(dict(document), field) != stored:
        _fail(code, f"{field} does not match the artifact content", {"field": field})


def _resolve_parent(
    genome: Mapping[str, Any],
    mechanism_graphs: Mapping[str, Mapping[str, Any]],
    scope_vectors: Mapping[str, Mapping[str, Any]],
    reference_fields: tuple[str, str, str],
) -> _Parent:
    """Validate one parent genome and bind every artifact its fields reference."""
    document = _require_mapping(genome, "parent")
    try:
        kind = engine.genome_kind_of(document)
    except engine.MutationOperatorError as error:
        _fail(
            "PARENT_CONTRACT_VIOLATED",
            "the parent does not satisfy a canonical genome contract",
            {"genome_kind_error": error.code},
        )
        raise AssertionError  # pragma: no cover - _fail always raises
    if kind != GENOME_KIND:
        _fail(
            "PARENT_KIND_MISMATCH",
            "the parent is not a hypothesis genome",
            {"resolved": kind},
        )
    mechanism_field, scope_field, measurement_field = reference_fields
    genome_id = _require_text(
        document.get(intake.IDENTITY_FIELD), intake.IDENTITY_FIELD
    )

    mechanism_id = _require_text(document.get(mechanism_field), mechanism_field)
    graph = mechanism_graphs.get(mechanism_id)
    if graph is None:
        _fail(
            "MECHANISM_GRAPH_UNRESOLVED",
            "no supplied mechanism graph carries the referenced id",
            {"mechanism_graph_id": mechanism_id},
        )
    graph_document = _require_mapping(graph, "mechanism_graph")
    try:
        validate_artifact(MECHANISM_KIND, graph_document)
    except ContractViolation as error:
        _fail(
            "MECHANISM_GRAPH_CONTRACT_VIOLATED",
            "a mechanism graph does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    _verify_self_hash(
        graph_document, GRAPH_HASH_FIELD, "MECHANISM_GRAPH_CONTRACT_VIOLATED"
    )

    scope_id = _require_text(document.get(scope_field), scope_field)
    scope = scope_vectors.get(scope_id)
    if scope is None:
        _fail(
            "SCOPE_VECTOR_UNRESOLVED",
            "no supplied scope vector carries the referenced id",
            {"scope_vector_id": scope_id},
        )
    scope_document = _require_mapping(scope, "scope_vector")
    try:
        validate_artifact(SCOPE_KIND, scope_document)
    except ContractViolation as error:
        _fail(
            "SCOPE_VECTOR_CONTRACT_VIOLATED",
            "a scope vector does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )

    measurement_ids = frozenset(
        _require_text(item, "measurement_contract_id")
        for item in _require_sequence(
            document.get(measurement_field), measurement_field
        )
    )
    return _Parent(
        genome_id=genome_id,
        genome=document,
        mechanism_graph=graph_document,
        scope_vector=scope_document,
        measurement_ids=measurement_ids,
    )


def _bind_mechanism_graphs(
    value: object,
) -> dict[str, Mapping[str, Any]]:
    """Index supplied mechanism graphs by their own declared id."""
    graphs: dict[str, Mapping[str, Any]] = {}
    for entry in _require_sequence(value, "mechanism_graphs"):
        document = _require_mapping(entry, "mechanism_graph")
        graph_id = _require_text(
            document.get("mechanism_graph_id"), "mechanism_graph_id"
        )
        graphs[graph_id] = document
    return graphs


def _derive_causal(left: _Parent, right: _Parent) -> tuple[str, list[str]]:
    """The causal axis, read from each parent's sealed identification status."""
    valid = set(identification_statuses())
    statuses: list[str] = []
    for parent in (left, right):
        status = str(parent.mechanism_graph.get("identification_status"))
        if status not in valid:  # pragma: no cover - schema-validated upstream
            _fail(
                "MECHANISM_GRAPH_CONTRACT_VIOLATED",
                "a mechanism graph carries a non-canonical identification status",
                {"identification_status": status},
            )
        statuses.append(status)
    reasons = [f"{p.genome_id}:{s}" for p, s in zip((left, right), statuses)]
    vocab = _vocab()
    if vocab["not_assessed"] in statuses:
        return "unknown", reasons
    if statuses[0] == statuses[1] == vocab["identified"]:
        return vocab["axis_compatible"], reasons
    if statuses[0] == statuses[1] == vocab["assumption_dependent"]:
        return vocab["causal_repairable"], reasons
    return vocab["axis_incompatible"], reasons


def _bind_measurement_report(
    report: Mapping[str, Any], left: _Parent, right: _Parent
) -> dict[str, Any]:
    """Validate the measurement report and bind it to the two parents."""
    document = _require_mapping(report, "measurement_report")
    try:
        validate_artifact(MEASUREMENT_REPORT_KIND, document)
    except ContractViolation as error:
        _fail(
            "MEASUREMENT_REPORT_CONTRACT_VIOLATED",
            "the measurement report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    _verify_self_hash(
        document, REPORT_HASH_FIELD, "MEASUREMENT_REPORT_CONTRACT_VIOLATED"
    )
    left_id = str(document["left"]["measurement_id"])
    right_id = str(document["right"]["measurement_id"])
    forward = left_id in left.measurement_ids and right_id in right.measurement_ids
    swapped = left_id in right.measurement_ids and right_id in left.measurement_ids
    if not (forward or swapped):
        _fail(
            "MEASUREMENT_REPORT_MISBOUND",
            "the measurement report does not compare a measurement of each parent",
            {
                "left_measurement_id": left_id,
                "right_measurement_id": right_id,
            },
        )
    return document


def _derive_measurement(report: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The measurement axis, mapped from the report's own sealed verdict."""
    status = str(report["compatibility_status"])
    construct = str(report["construct_equivalence"])
    reasons = [f"compatibility_status:{status}", f"construct_equivalence:{construct}"]
    vocab = _vocab()
    # "UNKNOWN" is a generic unassessed marker rather than a wire-pinned value.
    if status == "UNKNOWN" or construct == "UNKNOWN":
        return "unknown", reasons
    if status == vocab["not_comparable"] or construct == vocab["construct_different"]:
        return vocab["axis_incompatible"], reasons
    if status == vocab["directly_comparable"] and construct == vocab["construct_same"]:
        return vocab["axis_compatible"], reasons
    return vocab["measurement_repairable"], reasons


def _derive_unit(report: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The unit axis, read from the two measurements' declared units."""
    left_unit = report["left"]["unit"]
    right_unit = report["right"]["unit"]
    transforms = report.get("required_transformations") or []
    reasons = [f"left_unit:{left_unit}", f"right_unit:{right_unit}"]
    vocab = _vocab()
    if left_unit is None or right_unit is None:
        # A measurement that declares no unit leaves the unit axis unexamined;
        # the gate will not assert two undeclared scales are comparable.
        return "unknown", reasons
    if left_unit == right_unit:
        return vocab["axis_compatible"], reasons
    if transforms:
        return vocab["unit_repairable"], reasons
    return vocab["axis_incompatible"], reasons


def _scope_is_empty(scope: Mapping[str, Any], scalar_fields: tuple[str, ...]) -> bool:
    """True when a scope vector declares no boundary of any kind."""
    for field in scalar_fields:
        if scope.get(field) not in (None, ""):
            return False
    if scope.get("intervention_or_exposure") is not None:
        return False
    for field in ("inclusion_criteria", "exclusion_criteria"):
        if scope.get(field):
            return False
    for field in ("conditions", "domain_extensions"):
        if scope.get(field):
            return False
    return True


def _derive_scope(left: _Parent, right: _Parent) -> tuple[str, list[str]]:
    """The scope axis, derived by comparing the two parents' scope vectors."""
    scalar_fields = scope_scalar_fields()
    left_scope = left.scope_vector
    right_scope = right.scope_vector
    if _scope_is_empty(left_scope, scalar_fields):
        return "unknown", [f"{left.genome_id}:no-declared-scope"]
    if _scope_is_empty(right_scope, scalar_fields):
        return "unknown", [f"{right.genome_id}:no-declared-scope"]
    conflicts: list[str] = []
    for field in scalar_fields:
        left_value = left_scope.get(field)
        right_value = right_scope.get(field)
        if left_value in (None, "") or right_value in (None, ""):
            continue
        if left_value != right_value:
            conflicts.append(field)
    vocab = _vocab()
    if conflicts:
        return vocab["axis_incompatible"], [
            f"conflict:{field}" for field in sorted(conflicts)
        ]
    return vocab["axis_compatible"], ["no-conflicting-declared-field"]


#: Which finding code a non-compatible derived axis raises, split by whether the
#: axis was never examined (``unknown``) or examined and found incompatible.
_AXIS_REFUSALS: dict[str, tuple[str, str]] = {
    "causal_compatibility": (
        "CAUSAL_IDENTIFICATION_UNASSESSED",
        "CAUSAL_IDENTIFICATION_INCOMPATIBLE",
    ),
    "measurement_compatibility": (
        "MEASUREMENT_CONTRACT_UNASSESSED",
        "MEASUREMENT_CONTRACT_INCOMPATIBLE",
    ),
    "scope_compatibility": ("SCOPE_UNASSESSED", "SCOPE_INCOMPATIBLE"),
    "unit_compatibility": ("UNIT_UNASSESSED", "UNIT_INCOMPATIBLE"),
}


def _bind_crossover_report(
    report: Mapping[str, Any], left: _Parent, right: _Parent
) -> dict[str, Any]:
    """Validate the Chamber report and bind it to the two parents."""
    document = _require_mapping(report, "crossover_report")
    try:
        validate_artifact(CROSSOVER_REPORT_KIND, document)
    except ContractViolation as error:
        _fail(
            "CROSSOVER_REPORT_CONTRACT_VIOLATED",
            "the crossover report does not satisfy its canonical schema",
            {"schema_errors": list(error.errors)},
        )
    _verify_self_hash(document, REPORT_HASH_FIELD, "CROSSOVER_REPORT_CONTRACT_VIOLATED")
    named = {str(item) for item in document.get("candidate_ids", [])}
    if {left.genome_id, right.genome_id} - named:
        _fail(
            "CROSSOVER_REPORT_MISBOUND",
            "the crossover report does not name both parents",
            {
                "candidate_ids": sorted(named),
                "parents": sorted({left.genome_id, right.genome_id}),
            },
        )
    return document


def _decide(
    derived: Mapping[str, tuple[str, list[str]]],
    crossover_report: Mapping[str, Any],
) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve the decision, its finding code, its message, and its context.

    Report faithfulness comes first: a report that overrides the parents is the
    leakage this gate closes, so a disagreement is refused before the axis
    itself is judged.  Then every axis must be compatible, and the Chamber's own
    decision must be an unconditional allow.  None of the three substitutes for
    another.
    """
    vocab = _vocab()
    for axis in COMPATIBILITY_AXES:
        derived_value = derived[axis][0]
        reported = str(crossover_report.get(axis))
        if reported != derived_value:
            return (
                "REFUSE",
                "REPORT_AXIS_MISMATCH",
                "the crossover report asserts an axis the artifacts do not support",
                {"axis": axis, "report_value": reported, "derived": derived_value},
            )
    for axis in COMPATIBILITY_AXES:
        derived_value = derived[axis][0]
        if derived_value == vocab["axis_compatible"]:
            continue
        unassessed_code, incompatible_code = _AXIS_REFUSALS[axis]
        code = unassessed_code if derived_value == "unknown" else incompatible_code
        return (
            "REFUSE",
            code,
            f"the {axis} axis is not compatible",
            {"axis": axis, "derived": derived_value, "reasons": derived[axis][1]},
        )
    if not crossover_permitted(crossover_report):
        return (
            "REFUSE",
            "CROSSOVER_NOT_PERMITTED",
            "the Chamber decision is not an unconditional allow",
            {"decision": crossover_report.get("decision")},
        )
    return vocab["allow"], None, "the crossover is compatible on every derived axis", {}


def derive_crossover_safety(
    *,
    parents: Sequence[Mapping[str, Any]],
    mechanism_graphs: Sequence[Mapping[str, Any]],
    scope_vectors: Mapping[str, Mapping[str, Any]],
    measurement_report: Mapping[str, Any],
    crossover_report: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Derive the gate decision and its immutable receipt without enforcing it.

    Input-integrity failures — a malformed genome, an unresolved reference, a
    misbound or self-inconsistent report — refuse immediately, because there is
    no well-formed decision to record over evidence the gate cannot read.  Once
    every input is validated and bound, the safety decision always produces a
    receipt, whether it allows or refuses, so every gate decision over
    well-formed inputs is auditable and re-derivable.
    """
    stamp = _require_text(created_at, "created_at")
    reference_fields = genome_reference_fields()
    documents = _require_sequence(parents, "parents")
    if len(documents) != 2:
        _fail(
            "CROSSOVER_ARITY_INVALID",
            "a crossover safety decision is about exactly two parents",
            {"count": len(documents)},
        )
    graphs = _bind_mechanism_graphs(mechanism_graphs)
    scopes = _require_mapping(scope_vectors, "scope_vectors")

    resolved = [
        _resolve_parent(document, graphs, scopes, reference_fields)
        for document in documents
    ]
    if resolved[0].genome_id == resolved[1].genome_id:
        _fail(
            "PARENTS_NOT_DISTINCT",
            "a candidate cannot be spliced with itself",
            {"genome_id": resolved[0].genome_id},
        )
    # Order the two parents by identity so the receipt is a pure function of the
    # pair and not of the caller's argument order.
    left, right = sorted(resolved, key=lambda parent: parent.genome_id)

    measurement = _bind_measurement_report(measurement_report, left, right)
    report = _bind_crossover_report(crossover_report, left, right)

    derived: dict[str, tuple[str, list[str]]] = {
        "causal_compatibility": _derive_causal(left, right),
        "measurement_compatibility": _derive_measurement(measurement),
        "unit_compatibility": _derive_unit(measurement),
        "scope_compatibility": _derive_scope(left, right),
    }

    decision, finding_code, message, decision_context = _decide(derived, report)

    receipt: dict[str, Any] = {
        "gate": "crossover-safety",
        "created_at": stamp,
        "decision": decision,
        "finding_code": finding_code,
        "message": message,
        "decision_context": decision_context,
        "candidate_ids": [left.genome_id, right.genome_id],
        "parent_genome_hashes": [
            sha256_hex(canonical_json(left.genome)),
            sha256_hex(canonical_json(right.genome)),
        ],
        "mechanism_graph_hashes": [
            str(left.mechanism_graph[GRAPH_HASH_FIELD]),
            str(right.mechanism_graph[GRAPH_HASH_FIELD]),
        ],
        "scope_vector_hashes": [
            sha256_hex(canonical_json(left.scope_vector)),
            sha256_hex(canonical_json(right.scope_vector)),
        ],
        "measurement_report_id": str(measurement["report_id"]),
        "measurement_report_hash": str(measurement[REPORT_HASH_FIELD]),
        "crossover_report_id": str(report["report_id"]),
        "crossover_report_hash": str(report[REPORT_HASH_FIELD]),
        "derived_axes": {axis: derived[axis][0] for axis in COMPATIBILITY_AXES},
        "derived_reasons": {axis: derived[axis][1] for axis in COMPATIBILITY_AXES},
    }
    receipt["gate_id"] = (
        "XSG-"
        + sha256_hex(
            canonical_json(
                {
                    "candidate_ids": receipt["candidate_ids"],
                    "created_at": stamp,
                    "crossover_report_hash": receipt["crossover_report_hash"],
                    "decision": decision,
                    "mechanism_graph_hashes": receipt["mechanism_graph_hashes"],
                }
            )
        )[len("sha256:") :]
    )
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_crossover_safety(
    *,
    parents: Sequence[Mapping[str, Any]],
    mechanism_graphs: Sequence[Mapping[str, Any]],
    scope_vectors: Mapping[str, Mapping[str, Any]],
    measurement_report: Mapping[str, Any],
    crossover_report: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Enforce the gate: return the receipt on allow, raise on any refusal.

    The refusal carries its finding code and the same immutable receipt the
    derivation produced, so a caller that catches it still holds the auditable
    record of why the splice was stopped.
    """
    receipt = derive_crossover_safety(
        parents=parents,
        mechanism_graphs=mechanism_graphs,
        scope_vectors=scope_vectors,
        measurement_report=measurement_report,
        crossover_report=crossover_report,
        created_at=created_at,
    )
    if receipt["decision"] != _vocab()["allow"]:
        raise CrossoverSafetyRefused(
            str(receipt["finding_code"]),
            str(receipt["message"]),
            {"receipt": receipt, **dict(receipt["decision_context"])},
        )
    return receipt


#: Public views of the canonical tokens the gate reasons about, read once from
#: the schema rather than restated as literals.  ``COMPATIBLE_TOKEN`` is the
#: shared compatible axis value; ``IDENTIFIED`` and ``NOT_ASSESSED`` are the two
#: identification statuses callers most often check a mechanism graph against.
COMPATIBLE_TOKEN = _vocab()["axis_compatible"]
IDENTIFIED = _vocab()["identified"]
NOT_ASSESSED = _vocab()["not_assessed"]


# ``SchemaNotFound`` is imported so a caller can distinguish a missing canonical
# schema (an environment fault) from a refusal; re-exported for that use.
__all__ = [
    "COMPATIBILITY_AXES",
    "COMPATIBLE_TOKEN",
    "FINDING_CODES",
    "CrossoverSafetyRefused",
    "SchemaNotFound",
    "derive_crossover_safety",
    "evaluate_crossover_safety",
    "genome_reference_fields",
    "identification_statuses",
    "scope_scalar_fields",
]
