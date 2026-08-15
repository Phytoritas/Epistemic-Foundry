"""V02 deterministic preregistered ValidationPlan construction and sealing.

A validation run that decides what would count as failure *after* it has seen
its own numbers has decided nothing.  This module is where that ordering is
made structural rather than promised: the stages a plan will walk, the
endpoints it will read, the analysis it will run and the predictions it could
be refuted by are all assembled, sealed by hash, and only then published as a
:class:`ValidationPlan`.  There is no field anywhere in the sealed document for
a result, and the seal covers exactly the fields that would have to move for a
result to change the plan.

Three layers, kept apart on purpose.

*Binding.*  A plan may only be written against a target V01 already screened
and found ELIGIBLE.  The caller hands over both the manifest and V01's
eligibility report; this module re-derives the report's own hash, finds the
record whose ``manifest_hash`` is the digest of *this* manifest, and re-runs
V01's screen to confirm the record is what a fresh screening would produce.  A
hand-written report claiming eligibility therefore fails, and a report that
screened a different version of the same target is ``TARGET_UNSCREENED`` rather
than silently accepted.

*Grounding.*  V01 introduced one reference grammar — ``{port_id}`` naming a
port the manifest declares — and flagged it as the seam V02 would have to
reconcile.  This module adopts that grammar unchanged, down to reusing V01's
compiled pattern and its ``constraint_references`` reader, and extends it from
constraints to the whole plan: every ``{...}`` anywhere in the sealed document
must name a declared port, and the four structured surfaces are additionally
bound by direction, because an endpoint that names an input reads nothing and
an action argument that names an output writes nowhere.  One deliberate
divergence in wording is recorded here rather than hidden: V01 says
``CONSTRAINT_UNGROUNDED`` for a constraint that names no port at all and
``CONSTRAINT_UNBOUND`` for one that names a port the manifest never declared;
V02's ``PLAN_REFERENCE_UNGROUNDED`` is the *latter* sense — a reference that
does not resolve — and ``PLAN_REFERENCE_MISSING`` is the former.

*Falsifiability.*  A prediction that no observation could contradict is not a
prediction, so the register is refused outright when nothing in it is
falsifiable.  Each falsifiable prediction carries a threshold and a comparator
bound to a declared *output* port, and the comparator has to point against the
direction the prediction claims: a prediction of increase is falsified by the
observable staying low, not by it going higher still.  A prediction whose
declared direction is qualitative carries no threshold that could refute it, so
it may only be entered as exploratory — labelled, counted, and recorded as not
promotable, never quietly folded into the falsifiable set.

Every vocabulary is read from the canonical schemas rather than restated: the
plan and cascade field sets, the stage classes and failure actions, the
prediction directions, the falsifier trigger types and severities, the port
collections and the ``sha256`` pattern.  The two local decision tables — which
port collections each plan surface may reference, and which comparators can
falsify each declared direction — are asserted against the schemas that declare
their keys and values, so a schema edit breaks this module loudly instead of
leaving a rule governing a vocabulary that no longer exists.  The comparator
set itself has no canonical declaration anywhere in ``schemas/``; it is local,
and the schema-and-type suite pins it so that stays visible.

The small input guards below are declared here rather than imported because
V01's are private and raise V01's finding vocabulary; a V02 refusal has to
carry a V02 code.  The content addressing is *not* re-declared: ``digest`` and
``hash_excluding`` are V01's, so a preregistration hash and an eligibility
record hash come from one implementation and cannot drift apart.

No clock and no randomness.  The caller supplies every id, timestamp and seed,
inputs are never mutated, every derived list is sorted, and every record, plan
and receipt re-derives its own hash from exactly the fields it publishes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from epistemic_foundry.validation.targets import (
    SCOPE_SCHEMA_PATH,
    SEED_FIELD,
    TARGET_SCHEMA_PATH,
    approval_coverage,
    constraint_references,
    digest,
    hash_excluding,
    reproducibility_requirements,
    screen_target,
    sha256_pattern,
)

#: The canonical preregistered plan this package constructs and seals.
PLAN_SCHEMA_PATH: Final = "schemas/validation-plan.schema.json"
#: The canonical staged-evaluation order a plan is preregistered against.
CASCADE_SCHEMA_PATH: Final = "schemas/validation-cascade-plan.schema.json"
#: The canonical observable prediction a plan can be refuted through.
PREDICTION_SCHEMA_PATH: Final = "schemas/prediction-gene.schema.json"
#: The canonical refutation condition attached to one prediction.
FALSIFIER_SCHEMA_PATH: Final = "schemas/falsifier-gene.schema.json"

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ACTION_UNSUPPORTED": (
        "the plan names an action the bound target never declares it supports, "
        "so execution would ask the target to do something it cannot do"
    ),
    "AMENDMENT_CHAIN_BROKEN": (
        "the predecessor a plan amends does not re-derive its own sealed hash, "
        "so the amended plan would descend from a document nobody can verify"
    ),
    "AMENDMENT_IDENTITY_REUSED": (
        "an amendment reuses the plan id it amends, so the record would show "
        "one plan changing after sealing instead of a successor plan existing"
    ),
    "APPROVAL_RECORD_MISSING": (
        "the bound target's policy gates its safety class but the plan names no "
        "approval record, so a gated effect would run with no decision behind it"
    ),
    "CASCADE_SCHEMA_INVALID": (
        "the assembled stage plan does not validate against its canonical "
        "schema, so this builder would be sealing an order nothing accepts"
    ),
    "COMPARATOR_UNDECLARED": (
        "a falsification criterion uses a comparator this contract does not "
        "declare, so what would count as a refuting observation is undefined"
    ),
    "CRITERION_DIRECTION_INCOMPATIBLE": (
        "a falsification criterion points the same way as the prediction it is "
        "attached to, so no observation satisfying it could ever refute that "
        "prediction and the criterion only looks like a falsifier"
    ),
    "CRITERION_PORT_UNDECLARED": (
        "a falsification criterion names a port the bound target does not "
        "declare as an output, so nothing a run emits could ever trigger it"
    ),
    "ELIGIBILITY_REPORT_UNVERIFIED": (
        "the supplied eligibility report does not re-derive its own hashes or "
        "disagrees with a fresh screening, so its verdict cannot be trusted"
    ),
    "ENVIRONMENT_DIGEST_MALFORMED": (
        "the environment digest is not in the canonical sha256 form the target "
        "schema declares, so the environment a result came from is unpinnable"
    ),
    "EXPLORATORY_CRITERION_DECLARED": (
        "a prediction labelled exploratory carries falsification criteria, so a "
        "confirmatory test would be counted under a label that escapes the "
        "multiplicity accounting exploratory work exists to keep separate"
    ),
    "FALSIFIER_SCHEMA_INVALID": (
        "an assembled falsifier does not validate against its canonical schema, "
        "so the refutation condition is not a document the system can carry"
    ),
    "FIELD_SET_INVALID": (
        "a record carries a field set the declaring schema does not allow, so "
        "some field is missing or some field would be silently ignored"
    ),
    "IDENTIFIABILITY_UNASSESSED": (
        "the bound target declares an identifiability limit the plan never "
        "repeats, so the plan would run as though the limit had been assessed"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this contract accepts, so continuing would "
        "mean guessing what the caller meant instead of refusing plainly"
    ),
    "PLAN_REFERENCE_MISDIRECTED": (
        "a plan reference resolves to a declared port of the wrong direction, "
        "so it would read something no run emits or set something no run reads"
    ),
    "PLAN_REFERENCE_MISSING": (
        "a plan surface that must name exactly one declared port names none, so "
        "the mapping it states connects the plan to nothing in the target"
    ),
    "PLAN_REFERENCE_UNGROUNDED": (
        "a plan reference names a port the bound target never declares, so the "
        "plan is written against an interface that does not exist"
    ),
    "PLAN_SCHEMA_INVALID": (
        "the assembled plan does not validate against its canonical schema, so "
        "this builder would be sealing a document nothing downstream accepts"
    ),
    "PLAN_UNFALSIFIABLE": (
        "the plan declares no prediction that any observation could refute, so "
        "running it could produce support and never produce a contradiction"
    ),
    "PREDICTION_COUNT_UNRECONCILED": (
        "the declared predictions do not equal the falsifiable plus exploratory "
        "predictions, so some prediction is counted twice or not counted at all"
    ),
    "PREDICTION_ID_DUPLICATED": (
        "two predictions claim the same id, so a refutation could not be "
        "attributed to one prediction and the register could not be reconciled"
    ),
    "PREDICTION_SCHEMA_INVALID": (
        "an assembled prediction does not validate against its canonical "
        "schema, so the prediction is not a document the system can carry"
    ),
    "PREREGISTRATION_MUTATED": (
        "a sealed preregistration no longer re-derives the hashes it publishes, "
        "so something was changed after sealing and before it was read again"
    ),
    "SCHEMA_UNREADABLE": (
        "a canonical schema this module reads its vocabulary from cannot be "
        "read or does not declare what is expected, so nothing may be planned"
    ),
    "SEED_UNFIXED": (
        "the bound target's type requires seed control but the plan fixes no "
        "random seed, so two runs of this same plan would not be comparable"
    ),
    "STAGE_BUDGET_OVERCOMMITTED": (
        "the declared stage budget fractions sum above the whole budget, so the "
        "cascade could not run the order it preregistered within its envelope"
    ),
    "STAGE_ID_DUPLICATED": (
        "two stages claim the same id, so a stage outcome could not be "
        "attributed to one stage and the cascade order would be ambiguous"
    ),
    "TARGET_INELIGIBLE": (
        "the bound target was screened and found ineligible, so a plan against "
        "it could not bound any claim no matter how the plan itself is written"
    ),
    "TARGET_UNSCREENED": (
        "no eligibility record in the supplied report screened this exact "
        "manifest, so the plan would bind a target nothing has ever screened"
    ),
    "TARGET_VERSION_MISMATCH": (
        "the plan names a target id or version other than the manifest it was "
        "screened against, so the sealed plan points at a different interface"
    ),
    "VOCABULARY_DRIFT": (
        "a local decision table no longer matches the canonical schema that "
        "declares its keys or values, so some planned value has no rule"
    ),
}

#: The comparators a falsification criterion may use.  No canonical schema in
#: ``schemas/`` declares a comparator vocabulary — the ``comparator`` field on
#: ExperimentGenome and ExperimentTicket is a control arm, not an operator — so
#: this set is local by necessity and pinned by the schema-and-type suite.
COMPARATORS: Final = ("<", "<=", "==", "!=", ">=", ">")

#: Which comparators can actually refute each direction the canonical
#: PredictionGene declares.  A prediction of increase is contradicted by the
#: observable failing to rise past the threshold, so its falsifier must point
#: downward; a null prediction is contradicted by a deviation large enough to
#: exceed the threshold, so its falsifier points upward.  ``qualitative`` has no
#: entry that any threshold could settle, which is why it is empty rather than
#: permissive: such a prediction may only be registered as exploratory.
DIRECTION_COMPARATORS: Final = {
    "increase": ("<", "<="),
    "decrease": (">", ">="),
    "null": (">", ">="),
    "nonmonotonic": ("<", "<=", ">=", ">"),
    "distribution_shift": ("<", "<="),
    "qualitative": (),
}

#: Which port collections each plan surface may name.  Everything else in the
#: document may name any declared port; these four are the surfaces where a
#: direction error is a real error rather than a matter of phrasing.
REFERENCE_DIRECTION: Final = {
    "actions": ("inputs", "parameters"),
    "controlled_conditions": ("inputs", "parameters", "state_variables"),
    "falsification_rule": ("outputs",),
    "observables": ("outputs",),
}

#: The exact prediction the caller declares, before this module turns it into a
#: canonical PredictionGene and, unless exploratory, a canonical FalsifierGene.
PREDICTION_INPUT_FIELDS: Final = frozenset(
    {
        "discrimination_targets",
        "expected_direction",
        "expected_range",
        "exploratory",
        "falsification",
        "observable_id",
        "prediction_gene_id",
        "scope_vector_id",
        "statement",
        "time_horizon",
    }
)
#: The exact falsification criterion a non-exploratory prediction declares.
FALSIFICATION_INPUT_FIELDS: Final = frozenset(
    {
        "comparator",
        "decision_rule",
        "falsifier_gene_id",
        "severity",
        "statement",
        "threshold",
        "trigger_type",
        "unit",
    }
)

#: The plan fields the seal freezes: the stages are carried by the cascade
#: plan, the endpoints by ``observables`` and ``metrics``, and the analysis by
#: the baseline, actions, scenario matrix, conditions, inputs, stopping rules,
#: leakage guards, seed and analysis artifact.  A plan may still be re-titled
#: after sealing; it may not be re-aimed.
SEALED_PLAN_FIELDS: Final = (
    "actions",
    "analysis_plan_artifact_id",
    "baseline",
    "controlled_conditions",
    "data_leakage_guards",
    "environment_digest",
    "falsification_rule",
    "identifiability_warnings",
    "inputs",
    "metrics",
    "observables",
    "random_seed",
    "resource_limits",
    "scenario_matrix",
    "stopping_rules",
    "target_id",
    "target_version",
)

#: The keys a preregistration receipt publishes, excluding its own hash.
RECEIPT_FIELDS: Final = (
    "amendment_index",
    "amends",
    "cascade_plan",
    "counts",
    "eligibility_record",
    "exploratory_prediction_ids",
    "plan",
    "plan_hash",
    "prediction_register",
    "preregistered_at",
    "preregistration_hash",
    "promotable_prediction_ids",
    "receipt_id",
    "target_manifest_hash",
    "vocabulary_hash",
)

_BUDGET_TOLERANCE: Final = 1e-9


class ValidationPlanError(ValueError):
    """A plan, register or seal that could not describe a preregistration."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ValidationPlanError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ValidationPlanError(code, message, context)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings", {"label": label})
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean", {"label": label})
    return bool(value)


def _number(value: object, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INPUT_INVALID", f"{label} must be a number", {"label": label})
    if isinstance(value, float) and not math.isfinite(value):
        _fail("INPUT_INVALID", f"{label} must be a finite number", {"label": label})
    return value  # type: ignore[return-value]


def _string_list(value: object, label: str) -> list[str]:
    return [
        _text(entry, f"{label}[{index}]")
        for index, entry in enumerate(_sequence(value, label))
    ]


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _schema(repository_root: str | Path, relative: str) -> dict[str, Any]:
    path = Path(repository_root) / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, relative)


def _node(document: Mapping[str, Any], relative: str, *path: str) -> Any:
    node: Any = document
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            _fail(
                "SCHEMA_UNREADABLE",
                f"{relative} does not declare {'.'.join(path)}",
                {"schema": relative},
            )
        node = node[key]
    return node


def _enum(repository_root: str | Path, relative: str, *path: str) -> tuple[str, ...]:
    node = _node(_schema(repository_root, relative), relative, *path)
    if not isinstance(node, list) or not node:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares an empty {'.'.join(path)}",
            {"schema": relative},
        )
    return tuple(str(entry) for entry in node)  # type: ignore[union-attr]


def _required(repository_root: str | Path, relative: str, *path: str) -> frozenset[str]:
    document = _schema(repository_root, relative)
    node = _node(document, relative, *path) if path else document
    required = node.get("required") if isinstance(node, Mapping) else None
    if not isinstance(required, list) or not required:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares no required set at {'.'.join(path) or 'root'}",
            {"schema": relative},
        )
    return frozenset(str(entry) for entry in required)  # type: ignore[union-attr]


def _assert_table(
    table: Mapping[str, Any], declared: Sequence[str], label: str
) -> None:
    missing = sorted(set(declared) - set(table))
    unknown = sorted(set(table) - set(declared))
    if missing or unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} table no longer matches the schema that declares it",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _assert_subset(values: Sequence[str], declared: Sequence[str], label: str) -> None:
    unknown = sorted(set(values) - set(declared))
    if unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} set names a value the schema does not declare",
            {"label": label, "unknown": unknown},
        )


def _validate_enum(value: object, declared: Sequence[str], label: str) -> str:
    text = _text(value, label)
    if text not in declared:
        _fail(
            "INPUT_INVALID",
            f"{label} is not a value the canonical schema declares",
            {"label": label, "value": text, "allowed": list(declared)},
        )
    return text


def plan_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a canonical ValidationPlan must carry."""

    return _required(repository_root, PLAN_SCHEMA_PATH)


def cascade_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a canonical ValidationCascadePlan must carry."""

    return _required(repository_root, CASCADE_SCHEMA_PATH)


def stage_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(
        repository_root, CASCADE_SCHEMA_PATH, "properties", "stages", "items"
    )


def stage_classes(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        CASCADE_SCHEMA_PATH,
        "properties",
        "stages",
        "items",
        "properties",
        "stage_class",
        "enum",
    )


def stage_failure_actions(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        CASCADE_SCHEMA_PATH,
        "properties",
        "stages",
        "items",
        "properties",
        "failure_action",
        "enum",
    )


def prediction_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, PREDICTION_SCHEMA_PATH)


def falsifier_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, FALSIFIER_SCHEMA_PATH)


def prediction_directions(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        PREDICTION_SCHEMA_PATH,
        "properties",
        "expected_direction",
        "enum",
    )


def falsifier_trigger_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, FALSIFIER_SCHEMA_PATH, "properties", "trigger_type", "enum"
    )


def falsifier_severities(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, FALSIFIER_SCHEMA_PATH, "properties", "severity", "enum"
    )


def port_collections(repository_root: str | Path) -> tuple[str, ...]:
    """The manifest properties that declare ports, read from the schema.

    A collection is one whose items are the schema's own ``port`` definition,
    so a manifest schema that renames or adds a collection moves this list with
    it rather than leaving the direction table governing a name nobody uses.
    """

    properties = _mapping(
        _node(
            _schema(repository_root, TARGET_SCHEMA_PATH),
            TARGET_SCHEMA_PATH,
            "properties",
        ),
        "target properties",
    )
    collections = tuple(
        sorted(
            name
            for name, node in properties.items()
            if isinstance(node, Mapping)
            and isinstance(node.get("items"), Mapping)
            and node["items"].get("$ref") == "#/$defs/port"
        )
    )
    if not collections:
        _fail("SCHEMA_UNREADABLE", "the manifest schema declares no port collection")
    return collections


def direction_table(repository_root: str | Path) -> dict[str, tuple[str, ...]]:
    """The reference-direction table, checked against the declaring schema."""

    collections = port_collections(repository_root)
    for surface, allowed in REFERENCE_DIRECTION.items():
        _assert_subset(allowed, collections, f"reference direction for {surface}")
    return {surface: tuple(allowed) for surface, allowed in REFERENCE_DIRECTION.items()}


def falsifying_comparators(repository_root: str | Path) -> dict[str, tuple[str, ...]]:
    """Which comparators can refute each canonical prediction direction."""

    directions = prediction_directions(repository_root)
    _assert_table(DIRECTION_COMPARATORS, directions, "direction comparator")
    for direction, allowed in DIRECTION_COMPARATORS.items():
        _assert_subset(allowed, COMPARATORS, f"comparators for {direction}")
    return {
        direction: tuple(DIRECTION_COMPARATORS[direction])
        for direction in sorted(directions)
    }


def _resource(document: Mapping[str, Any]) -> tuple[str, Resource[Any]]:
    identifier = document.get("$id")
    if not isinstance(identifier, str) or not identifier:
        _fail("SCHEMA_UNREADABLE", "a canonical schema declares no $id")
    return str(identifier), Resource.from_contents(
        dict(document), default_specification=DRAFT202012
    )


def _validator(repository_root: str | Path, relative: str) -> Draft202012Validator:
    """A validator for one canonical schema, registered under its own ``$id``.

    Every canonical document this module builds is registered the same way V01
    registers the manifest and its scope vector, so a schema that grows a
    cross-document reference resolves against canonical identifiers rather than
    against wherever the file happens to sit on disk.
    """

    documents = [
        _schema(repository_root, relative),
        _schema(repository_root, SCOPE_SCHEMA_PATH),
        _schema(repository_root, TARGET_SCHEMA_PATH),
    ]
    registry: Registry[Any] = Registry().with_resources(
        _resource(document) for document in documents
    )
    return Draft202012Validator(documents[0], registry=registry)


def plan_validator(repository_root: str | Path) -> Draft202012Validator:
    return _validator(repository_root, PLAN_SCHEMA_PATH)


def _schema_errors(
    repository_root: str | Path, relative: str, document: object
) -> list[str]:
    return sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in _validator(repository_root, relative).iter_errors(document)
    )


def plan_schema_errors(repository_root: str | Path, plan: object) -> list[str]:
    """Every canonical schema error in a candidate plan, sorted."""

    return _schema_errors(repository_root, PLAN_SCHEMA_PATH, plan)


def cascade_schema_errors(repository_root: str | Path, cascade: object) -> list[str]:
    """Every canonical schema error in a candidate stage plan, sorted."""

    return _schema_errors(repository_root, CASCADE_SCHEMA_PATH, cascade)


def reference(port_id: str) -> str:
    """One port id written in V01's ``{port_id}`` reference grammar."""

    return "{" + _text(port_id, "port_id") + "}"


def declared_ports(
    manifest: Mapping[str, Any], collections: Sequence[str]
) -> dict[str, str]:
    """Every port the manifest declares, mapped to the collection it lives in."""

    document = _mapping(manifest, "target_manifest")
    result: dict[str, str] = {}
    for collection in collections:
        for index, entry in enumerate(
            _sequence(document.get(collection), f"target_manifest.{collection}")
        ):
            port = _mapping(entry, f"{collection}[{index}]")
            result[_text(port.get("id"), f"{collection}[{index}].id")] = collection
    return result


def plan_references(document: object) -> tuple[tuple[str, str], ...]:
    """Every ``{port_id}`` reference in a document, with where it was found.

    The reader is V01's ``constraint_references``, so the grammar cannot drift
    between what a manifest constrains and what a plan names.  Each result is
    the JSON pointer-style path of the string that carried the reference and
    the port id it named, in document order under sorted keys.
    """

    found: list[tuple[str, str]] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, str):
            found.extend((path, name) for name in constraint_references(node))
        elif isinstance(node, Mapping):
            for key in sorted(node):
                walk(node[key], f"{path}/{key}")
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for index, entry in enumerate(node):
                walk(entry, f"{path}/{index}")

    walk(document, "")
    return tuple(found)


def _single_reference(value: object, label: str) -> str:
    """The one port id a surface names, refusing anything less exact."""

    text = _text(value, label)
    names = constraint_references(text)
    if not names:
        _fail(
            "PLAN_REFERENCE_MISSING",
            f"{label} names no declared port",
            {"label": label, "value": text},
        )
    if len(names) != 1 or text.strip() != reference(names[0]):
        _fail(
            "INPUT_INVALID",
            f"{label} must be exactly one {{port_id}} reference",
            {"label": label, "value": text, "names": list(names)},
        )
    return names[0]


def _ground_references(
    document: Mapping[str, Any],
    ports: Mapping[str, str],
    directions: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[str, str], ...]:
    """Every reference in a plan resolves, and points the allowed way."""

    references = plan_references(document)
    for path, name in references:
        if name not in ports:
            _fail(
                "PLAN_REFERENCE_UNGROUNDED",
                f"{path or '/'} names an undeclared port",
                {"path": path, "port_id": name, "declared": sorted(ports)},
            )
        surface = path.split("/")[1] if path.startswith("/") else path
        allowed = directions.get(surface)
        if allowed is not None and ports[name] not in allowed:
            _fail(
                "PLAN_REFERENCE_MISDIRECTED",
                f"{path} names a {ports[name]} port where {surface} may not",
                {
                    "path": path,
                    "port_id": name,
                    "collection": ports[name],
                    "allowed": list(allowed),
                },
            )
    return references


@dataclass(frozen=True)
class _Vocabulary:
    """One snapshot of every canonical vocabulary a planning run reads."""

    comparators: dict[str, tuple[str, ...]]
    directions: tuple[str, ...]
    port_collections: tuple[str, ...]
    reference_directions: dict[str, tuple[str, ...]]
    severities: tuple[str, ...]
    stage_classes: tuple[str, ...]
    stage_failure_actions: tuple[str, ...]
    stage_fields: frozenset[str]
    trigger_types: tuple[str, ...]
    vocabulary_hash: str


def _open_vocabulary(repository_root: str | Path) -> _Vocabulary:
    root = Path(repository_root)
    return _Vocabulary(
        comparators=falsifying_comparators(root),
        directions=prediction_directions(root),
        port_collections=port_collections(root),
        reference_directions=direction_table(root),
        severities=falsifier_severities(root),
        stage_classes=stage_classes(root),
        stage_failure_actions=stage_failure_actions(root),
        stage_fields=stage_fields(root),
        trigger_types=falsifier_trigger_types(root),
        vocabulary_hash=digest(
            {
                path: _schema(root, path)
                for path in (
                    CASCADE_SCHEMA_PATH,
                    FALSIFIER_SCHEMA_PATH,
                    PLAN_SCHEMA_PATH,
                    PREDICTION_SCHEMA_PATH,
                    SCOPE_SCHEMA_PATH,
                    TARGET_SCHEMA_PATH,
                )
            }
        ),
    )


def build_stage_plan(
    repository_root: str | Path,
    *,
    cascade_plan_id: str,
    candidate_class: str,
    stages: Sequence[Any],
    max_total_budget: float | int,
    early_stop_policy: str,
) -> dict[str, Any]:
    """Assemble the canonical stage order a plan is preregistered against.

    The stages are what makes "declared before execution" checkable: each one
    states its entry rule, its pass rule and what happens when it fails, before
    anything has run.  The budget fractions are fractions of the whole envelope,
    so a set summing above one is refused rather than left to be discovered when
    the cascade runs out of budget mid-order.
    """

    root = Path(repository_root)
    vocabulary = _open_vocabulary(root)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0.0
    for index, value in enumerate(_sequence(stages, "stages")):
        label = f"stages[{index}]"
        stage = _mapping(value, label)
        _exact_fields(stage, vocabulary.stage_fields, label)
        identifier = _text(stage.get("stage_id"), f"{label}.stage_id")
        if identifier in seen:
            _fail(
                "STAGE_ID_DUPLICATED",
                f"stage id {identifier} is declared more than once",
                {"stage_id": identifier, "index": index},
            )
        seen.add(identifier)
        fraction = _number(stage.get("budget_fraction"), f"{label}.budget_fraction")
        total += float(fraction)
        entries.append(
            {
                "budget_fraction": fraction,
                "entry_rule": _text(stage.get("entry_rule"), f"{label}.entry_rule"),
                "failure_action": _validate_enum(
                    stage.get("failure_action"),
                    vocabulary.stage_failure_actions,
                    f"{label}.failure_action",
                ),
                "pass_rule": _text(stage.get("pass_rule"), f"{label}.pass_rule"),
                "stage_class": _validate_enum(
                    stage.get("stage_class"),
                    vocabulary.stage_classes,
                    f"{label}.stage_class",
                ),
                "stage_id": identifier,
            }
        )
    if total > 1 + _BUDGET_TOLERANCE:
        _fail(
            "STAGE_BUDGET_OVERCOMMITTED",
            "the declared stage budget fractions sum above the whole budget",
            {"total_fraction": total, "stage_count": len(entries)},
        )
    cascade: dict[str, Any] = {
        "cascade_plan_id": _text(cascade_plan_id, "cascade_plan_id"),
        "candidate_class": _text(candidate_class, "candidate_class"),
        "early_stop_policy": _text(early_stop_policy, "early_stop_policy"),
        "max_total_budget": _number(max_total_budget, "max_total_budget"),
        "stages": entries,
    }
    cascade["plan_hash"] = hash_excluding(cascade, "plan_hash")
    _exact_fields(cascade, cascade_fields(root), "cascade_plan")
    errors = cascade_schema_errors(root, cascade)
    if errors:
        _fail(
            "CASCADE_SCHEMA_INVALID",
            "the assembled stage plan does not validate against its schema",
            {"errors": errors},
        )
    return cascade


def render_criterion(criterion: Mapping[str, Any]) -> str:
    """One falsification criterion, rendered deterministically.

    The rendering is what the canonical FalsifierGene carries in its free-text
    ``observable_condition``, derived from the structured threshold rather than
    written separately, so the prose and the number can never disagree.
    """

    condition = _mapping(criterion, "criterion")
    unit = condition.get("unit")
    suffix = "" if unit is None else " " + _text(unit, "criterion.unit")
    return (
        f"{reference(_text(condition.get('observable'), 'criterion.observable'))} "
        f"{_text(condition.get('comparator'), 'criterion.comparator')} "
        f"{json.dumps(_number(condition.get('threshold'), 'criterion.threshold'))}"
        f"{suffix}"
    )


def render_falsification_rule(register: Sequence[Any]) -> str:
    """The plan's single ``falsification_rule``, derived from the register.

    The canonical plan schema carries one rule string, and the register carries
    the structured criteria; deriving the string from the register means the
    field the schema pins and the criteria the plan is actually judged by are
    the same statement, sorted by prediction id so two identical registers
    render identically.
    """

    clauses = sorted(
        f"{entry['prediction_id']}: {render_criterion(entry['criterion'])}"
        for entry in _sequence(register, "prediction_register")
        if _mapping(entry, "register entry").get("criterion") is not None
    )
    if not clauses:
        _fail(
            "PLAN_UNFALSIFIABLE",
            "no registered prediction declares a falsification criterion",
            {"registered": len(_sequence(register, "prediction_register"))},
        )
    return (
        "the preregistered claim is falsified if any of the following holds: "
        + "; ".join(clauses)
    )


def _build_falsification(
    vocabulary: _Vocabulary,
    value: object,
    *,
    label: str,
    genome_id: str,
    prediction_id: str,
    observable: str,
    direction: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    declaration = _mapping(value, label)
    _exact_fields(declaration, FALSIFICATION_INPUT_FIELDS, label)
    comparator = _text(declaration.get("comparator"), f"{label}.comparator")
    if comparator not in COMPARATORS:
        _fail(
            "COMPARATOR_UNDECLARED",
            f"{label} uses a comparator this contract does not declare",
            {"comparator": comparator, "declared": list(COMPARATORS)},
        )
    allowed = vocabulary.comparators[direction]
    if comparator not in allowed:
        _fail(
            "CRITERION_DIRECTION_INCOMPATIBLE",
            f"{label} cannot refute a prediction of {direction}",
            {
                "comparator": comparator,
                "expected_direction": direction,
                "allowed": list(allowed),
                "prediction_id": prediction_id,
            },
        )
    unit = declaration.get("unit")
    criterion: dict[str, Any] = {
        "comparator": comparator,
        "observable": observable,
        "threshold": _number(declaration.get("threshold"), f"{label}.threshold"),
        "unit": None if unit is None else _text(unit, f"{label}.unit"),
    }
    falsifier: dict[str, Any] = {
        "decision_rule": _text(
            declaration.get("decision_rule"), f"{label}.decision_rule"
        ),
        "falsifier_gene_id": _text(
            declaration.get("falsifier_gene_id"), f"{label}.falsifier_gene_id"
        ),
        "genome_id": genome_id,
        "linked_prediction_ids": [prediction_id],
        "observable_condition": render_criterion(criterion),
        "severity": _validate_enum(
            declaration.get("severity"), vocabulary.severities, f"{label}.severity"
        ),
        "statement": _text(declaration.get("statement"), f"{label}.statement"),
        "trigger_type": _validate_enum(
            declaration.get("trigger_type"),
            vocabulary.trigger_types,
            f"{label}.trigger_type",
        ),
    }
    return criterion, falsifier


def build_prediction_register(
    repository_root: str | Path,
    predictions: Sequence[Any],
    *,
    genome_id: str,
    outputs: Sequence[str],
) -> list[dict[str, Any]]:
    """Turn declared predictions into canonical genes plus their criteria.

    Each entry is one canonical PredictionGene, the canonical FalsifierGene it
    can be refuted by, the structured criterion that falsifier renders, and the
    two labels the accounting needs: whether the prediction is exploratory, and
    whether it is promotable at all.  An exploratory prediction is never
    promotable — that is recorded on the entry rather than inferred later — and
    it may not carry criteria, because a confirmatory test entered under an
    exploratory label escapes exactly the multiplicity accounting the label
    exists to keep honest.
    """

    root = Path(repository_root)
    vocabulary = _open_vocabulary(root)
    declared_outputs = set(_string_list(outputs, "outputs"))
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(_sequence(predictions, "predictions")):
        label = f"predictions[{index}]"
        declaration = _mapping(value, label)
        _exact_fields(declaration, PREDICTION_INPUT_FIELDS, label)
        identifier = _text(
            declaration.get("prediction_gene_id"), f"{label}.prediction_gene_id"
        )
        if identifier in seen:
            _fail(
                "PREDICTION_ID_DUPLICATED",
                f"prediction id {identifier} is declared more than once",
                {"prediction_id": identifier, "index": index},
            )
        seen.add(identifier)
        observable = _text(declaration.get("observable_id"), f"{label}.observable_id")
        if observable not in declared_outputs:
            _fail(
                "CRITERION_PORT_UNDECLARED",
                f"{label} observes a port the target does not declare as output",
                {
                    "prediction_id": identifier,
                    "observable_id": observable,
                    "outputs": sorted(declared_outputs),
                },
            )
        direction = _validate_enum(
            declaration.get("expected_direction"),
            vocabulary.directions,
            f"{label}.expected_direction",
        )
        exploratory = _boolean(declaration.get("exploratory"), f"{label}.exploratory")
        prediction: dict[str, Any] = {
            "discrimination_targets": _string_list(
                declaration.get("discrimination_targets"),
                f"{label}.discrimination_targets",
            ),
            "expected_direction": direction,
            "expected_range": _text(
                declaration.get("expected_range"), f"{label}.expected_range"
            ),
            "genome_id": genome_id,
            "observable_id": observable,
            "pre_registered": True,
            "prediction_gene_id": identifier,
            "scope_vector_id": _text(
                declaration.get("scope_vector_id"), f"{label}.scope_vector_id"
            ),
            "statement": _text(declaration.get("statement"), f"{label}.statement"),
            "time_horizon": _text(
                declaration.get("time_horizon"), f"{label}.time_horizon"
            ),
        }
        _exact_fields(prediction, prediction_fields(root), f"{label}.prediction")
        errors = _schema_errors(root, PREDICTION_SCHEMA_PATH, prediction)
        if errors:
            _fail(
                "PREDICTION_SCHEMA_INVALID",
                f"{label} does not validate against the PredictionGene schema",
                {"prediction_id": identifier, "errors": errors},
            )

        criterion: dict[str, Any] | None = None
        falsifier: dict[str, Any] | None = None
        declared = declaration.get("falsification")
        if exploratory and declared is not None:
            _fail(
                "EXPLORATORY_CRITERION_DECLARED",
                f"{label} is exploratory and may not carry falsification criteria",
                {"prediction_id": identifier},
            )
        if not exploratory:
            if declared is None:
                _fail(
                    "PLAN_UNFALSIFIABLE",
                    f"{label} is confirmatory but declares no falsification criterion",
                    {"prediction_id": identifier},
                )
            criterion, falsifier = _build_falsification(
                vocabulary,
                declared,
                label=f"{label}.falsification",
                genome_id=genome_id,
                prediction_id=identifier,
                observable=observable,
                direction=direction,
            )
            _exact_fields(falsifier, falsifier_fields(root), f"{label}.falsifier")
            falsifier_errors = _schema_errors(root, FALSIFIER_SCHEMA_PATH, falsifier)
            if falsifier_errors:
                _fail(
                    "FALSIFIER_SCHEMA_INVALID",
                    f"{label} does not validate against the FalsifierGene schema",
                    {"prediction_id": identifier, "errors": falsifier_errors},
                )
        entry: dict[str, Any] = {
            "criterion": criterion,
            "exploratory": exploratory,
            "falsifier": falsifier,
            "prediction": prediction,
            "prediction_id": identifier,
            "promotable": not exploratory,
        }
        entry["entry_hash"] = hash_excluding(entry, "entry_hash")
        entries.append(entry)
    return entries


def register_counts(register: Sequence[Any]) -> dict[str, int]:
    """The prediction accounting, reconciled rather than asserted.

    Predictions equal falsifiable plus exploratory exactly.  Promotable is
    reported separately from falsifiable even though the two coincide, because
    the day they stop coinciding is the day this has to fail rather than round.
    """

    entries = [
        _mapping(entry, f"prediction_register[{index}]")
        for index, entry in enumerate(_sequence(register, "prediction_register"))
    ]
    falsifiable = sum(1 for entry in entries if entry.get("criterion") is not None)
    exploratory = sum(1 for entry in entries if entry.get("exploratory") is True)
    promotable = sum(1 for entry in entries if entry.get("promotable") is True)
    counts = {
        "exploratory": exploratory,
        "falsifiable": falsifiable,
        "predictions": len(entries),
        "promotable": promotable,
    }
    if falsifiable + exploratory != len(entries) or promotable != falsifiable:
        _fail(
            "PREDICTION_COUNT_UNRECONCILED",
            "the prediction register does not reconcile",
            {"counts": counts},
        )
    if falsifiable == 0:
        _fail(
            "PLAN_UNFALSIFIABLE",
            "the register holds no falsifiable prediction",
            {"counts": counts},
        )
    return counts


def _bind_target(
    root: Path,
    manifest: Mapping[str, Any],
    eligibility_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Find, verify and re-screen the eligibility record for this manifest."""

    document = _mapping(manifest, "target_manifest")
    report = _mapping(eligibility_report, "eligibility_report")
    if report.get("report_hash") != hash_excluding(report, "report_hash"):
        _fail(
            "ELIGIBILITY_REPORT_UNVERIFIED",
            "the eligibility report does not re-derive its own hash",
            {"report_id": report.get("report_id")},
        )
    manifest_hash = digest(document)
    matched = [
        _mapping(record, "eligibility record")
        for record in _sequence(report.get("records"), "eligibility_report.records")
        if _mapping(record, "eligibility record").get("manifest_hash") == manifest_hash
    ]
    if len(matched) != 1:
        _fail(
            "TARGET_UNSCREENED",
            "no eligibility record screened this exact manifest",
            {"manifest_hash": manifest_hash, "matches": len(matched)},
        )
    record = matched[0]
    if record.get("record_hash") != hash_excluding(record, "record_hash"):
        _fail(
            "ELIGIBILITY_REPORT_UNVERIFIED",
            "the eligibility record does not re-derive its own hash",
            {"manifest_hash": manifest_hash},
        )
    index = record.get("screened_index")
    if not isinstance(index, int) or isinstance(index, bool):
        _fail(
            "ELIGIBILITY_REPORT_UNVERIFIED",
            "the eligibility record carries no screened index",
            {"manifest_hash": manifest_hash},
        )
    fresh = screen_target(root, document, screened_index=int(index))  # type: ignore[arg-type]
    if fresh != record:
        _fail(
            "ELIGIBILITY_REPORT_UNVERIFIED",
            "a fresh screening disagrees with the supplied eligibility record",
            {
                "manifest_hash": manifest_hash,
                "reported_hash": record.get("record_hash"),
                "screened_hash": fresh["record_hash"],
            },
        )
    if record.get("eligible") is not True:
        _fail(
            "TARGET_INELIGIBLE",
            "the bound target was screened and found ineligible",
            {
                "target_id": record.get("target_id"),
                "reason_codes": list(record.get("reason_codes") or ()),
            },
        )
    return record


def _observables(register: Sequence[Any]) -> list[str]:
    """The endpoints a register implies, derived rather than declared."""

    return sorted(
        {
            reference(
                _mapping(
                    _mapping(entry, "register entry").get("prediction"), "prediction"
                )["observable_id"]
            )
            for entry in _sequence(register, "prediction_register")
        }
    )


class _Underivable:
    """A value no published field can equal, so a broken derivation mismatches."""

    __slots__ = ()


def _derived(build: Any) -> Any:
    """Re-derive one published field, or return something nothing equals."""

    try:
        return build()
    except ValidationPlanError:
        return _Underivable()


def _sealed_core(
    plan: Mapping[str, Any],
    cascade: Mapping[str, Any],
    register: Sequence[Any],
    manifest_hash: object,
    amends: object,
) -> dict[str, Any]:
    """Exactly what the preregistration hash covers."""

    core: dict[str, Any] = {
        "amends": amends,
        "cascade_plan": cascade,
        "prediction_register": list(register),
        "target_manifest_hash": manifest_hash,
    }
    for field in SEALED_PLAN_FIELDS:
        core[field] = plan[field]
    return core


def preregister_plan(
    repository_root: str | Path,
    *,
    target_manifest: Mapping[str, Any],
    eligibility_report: Mapping[str, Any],
    cascade_plan: Mapping[str, Any],
    predictions: Sequence[Any],
    genome_id: str,
    receipt_id: str,
    preregistered_at: str,
    plan_id: str,
    hypothesis_id: str,
    target_id: str,
    target_version: str,
    objective: str,
    variable_mapping: Mapping[str, Any],
    mechanism_mapping: Mapping[str, Any],
    baseline: Mapping[str, Any],
    actions: Sequence[Any],
    scenario_matrix: Sequence[Any],
    inputs: Mapping[str, Any],
    controlled_conditions: Mapping[str, Any],
    metrics: Sequence[Any],
    assumptions: Sequence[Any],
    identifiability_warnings: Sequence[Any],
    random_seed: int | None,
    environment_digest: str,
    resource_limits: Mapping[str, Any],
    provenance_manifest_id: str,
    analysis_plan_artifact_id: str,
    stopping_rules: Sequence[Any],
    data_leakage_guards: Sequence[Any],
    approval_record_ids: Sequence[Any],
    amends: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Seal one preregistration: stages, endpoints, analysis, predictions.

    The order is the point.  The target is bound and re-screened first, so a
    plan cannot be written against something ineligible or unscreened.  The
    register is built next, so what would refute the plan exists before the
    plan does.  The endpoints and the single canonical ``falsification_rule``
    are then *derived* from that register rather than supplied, so the fields
    the schema pins and the criteria the run is judged by are one statement.
    Only then is the plan assembled, sealed over the frozen core, and published
    with the seal inside it.

    ``amends`` carries the predecessor receipt when this is an amendment.  An
    amendment is a new plan with a new id that names its predecessor's seal;
    the predecessor is re-verified first, so a chain cannot be grown from a
    document that no longer re-derives.
    """

    root = Path(repository_root)
    vocabulary = _open_vocabulary(root)
    manifest = _mapping(target_manifest, "target_manifest")
    record = _bind_target(root, manifest, eligibility_report)
    manifest_hash = digest(manifest)

    predecessor_hash: str | None = None
    amendment_index = 0
    if amends is not None:
        predecessor = _mapping(amends, "amends")
        mismatches = verify_preregistration(root, predecessor)
        if mismatches:
            _fail(
                "AMENDMENT_CHAIN_BROKEN",
                "the amended predecessor does not re-derive its own hashes",
                {"mismatches": mismatches},
            )
        if _mapping(predecessor.get("plan"), "amends.plan").get("plan_id") == plan_id:
            _fail(
                "AMENDMENT_IDENTITY_REUSED",
                "an amendment must be a new plan with a new plan id",
                {"plan_id": plan_id},
            )
        predecessor_hash = _text(
            predecessor.get("preregistration_hash"), "amends.preregistration_hash"
        )
        amendment_index = (
            int(predecessor["amendment_index"])
            if isinstance(predecessor.get("amendment_index"), int)
            and not isinstance(predecessor.get("amendment_index"), bool)
            else 0
        ) + 1

    ports = declared_ports(manifest, vocabulary.port_collections)
    outputs = sorted(
        name for name, collection in ports.items() if collection == "outputs"
    )
    register = build_prediction_register(
        root, predictions, genome_id=_text(genome_id, "genome_id"), outputs=outputs
    )
    counts = register_counts(register)

    supported = set(
        _string_list(
            manifest.get("supported_actions"), "target_manifest.supported_actions"
        )
    )
    planned_actions: list[dict[str, Any]] = []
    for index, value in enumerate(_sequence(actions, "actions")):
        label = f"actions[{index}]"
        action = _mapping(value, label)
        _exact_fields(action, frozenset({"action", "arguments"}), label)
        name = _text(action.get("action"), f"{label}.action")
        if name not in supported:
            _fail(
                "ACTION_UNSUPPORTED",
                f"{label} names an action the target does not support",
                {"action": name, "supported": sorted(supported)},
            )
        planned_actions.append(
            {
                "action": name,
                "arguments": json.loads(
                    json.dumps(
                        _mapping(action.get("arguments"), f"{label}.arguments"),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
            }
        )

    warnings = _string_list(identifiability_warnings, "identifiability_warnings")
    notes = _string_list(
        manifest.get("identifiability_notes"), "target_manifest.identifiability_notes"
    )
    unassessed = sorted(set(notes) - set(warnings))
    if unassessed:
        _fail(
            "IDENTIFIABILITY_UNASSESSED",
            "the plan omits an identifiability limit the target declares",
            {"unassessed": unassessed},
        )

    if (
        sha256_pattern(root).fullmatch(_text(environment_digest, "environment_digest"))
        is None
    ):
        _fail(
            "ENVIRONMENT_DIGEST_MALFORMED",
            "the environment digest is not canonical sha256",
            {"environment_digest": environment_digest},
        )

    target_type = _text(manifest.get("target_type"), "target_manifest.target_type")
    if SEED_FIELD in reproducibility_requirements(root)[target_type] and (
        random_seed is None
    ):
        _fail(
            "SEED_UNFIXED",
            f"a {target_type} target requires seed control but the plan fixes none",
            {"target_type": target_type},
        )
    if random_seed is not None and (
        isinstance(random_seed, bool) or not isinstance(random_seed, int)
    ):
        _fail("INPUT_INVALID", "random_seed must be an integer or null")

    approval_ids = _string_list(approval_record_ids, "approval_record_ids")
    gated = approval_coverage(root)[
        _text(manifest.get("approval_policy"), "target_manifest.approval_policy")
    ]
    approval_required = (
        _text(manifest.get("safety_class"), "target_manifest.safety_class") in gated
    )
    if approval_required and not approval_ids:
        _fail(
            "APPROVAL_RECORD_MISSING",
            "the target's policy gates its safety class but no approval is named",
            {"safety_class": manifest.get("safety_class")},
        )

    mapping: dict[str, str] = {}
    for key, value in sorted(_mapping(variable_mapping, "variable_mapping").items()):
        port = _single_reference(value, f"variable_mapping.{key}")
        mapping[key] = reference(port)

    cascade = _mapping(cascade_plan, "cascade_plan")
    if cascade.get("plan_hash") != hash_excluding(cascade, "plan_hash"):
        _fail(
            "CASCADE_SCHEMA_INVALID",
            "the supplied stage plan does not re-derive its own hash",
            {"cascade_plan_id": cascade.get("cascade_plan_id")},
        )
    cascade_errors = cascade_schema_errors(root, cascade)
    if cascade_errors:
        _fail(
            "CASCADE_SCHEMA_INVALID",
            "the supplied stage plan does not validate against its schema",
            {"errors": cascade_errors},
        )

    plan: dict[str, Any] = {
        "actions": planned_actions,
        "analysis_plan_artifact_id": _text(
            analysis_plan_artifact_id, "analysis_plan_artifact_id"
        ),
        "approval_record_ids": sorted(approval_ids),
        "approval_required": approval_required,
        "assumptions": _string_list(assumptions, "assumptions"),
        "baseline": json.loads(
            json.dumps(
                _mapping(baseline, "baseline"), ensure_ascii=False, sort_keys=True
            )
        ),
        "controlled_conditions": json.loads(
            json.dumps(
                _mapping(controlled_conditions, "controlled_conditions"),
                ensure_ascii=False,
                sort_keys=True,
            )
        ),
        "data_leakage_guards": _string_list(data_leakage_guards, "data_leakage_guards"),
        "environment_digest": _text(environment_digest, "environment_digest"),
        "falsification_rule": render_falsification_rule(register),
        "hypothesis_id": _text(hypothesis_id, "hypothesis_id"),
        "identifiability_warnings": warnings,
        "inputs": json.loads(
            json.dumps(_mapping(inputs, "inputs"), ensure_ascii=False, sort_keys=True)
        ),
        "mechanism_mapping": {
            key: _text(value, f"mechanism_mapping.{key}")
            for key, value in sorted(
                _mapping(mechanism_mapping, "mechanism_mapping").items()
            )
        },
        "metrics": _string_list(metrics, "metrics"),
        "objective": _text(objective, "objective"),
        "observables": _observables(register),
        "plan_id": _text(plan_id, "plan_id"),
        "preregistration_hash": "",
        "provenance_manifest_id": _text(
            provenance_manifest_id, "provenance_manifest_id"
        ),
        "random_seed": random_seed,
        "resource_limits": json.loads(
            json.dumps(
                _mapping(resource_limits, "resource_limits"),
                ensure_ascii=False,
                sort_keys=True,
            )
        ),
        "scenario_matrix": [
            json.loads(
                json.dumps(
                    _mapping(entry, f"scenario_matrix[{index}]"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            for index, entry in enumerate(_sequence(scenario_matrix, "scenario_matrix"))
        ],
        "stopping_rules": _string_list(stopping_rules, "stopping_rules"),
        "target_id": _text(target_id, "target_id"),
        "target_version": _text(target_version, "target_version"),
        "variable_mapping": mapping,
    }
    _exact_fields(plan, plan_fields(root), "plan")
    declared_binding = (manifest.get("target_id"), manifest.get("version"))
    if (plan["target_id"], plan["target_version"]) != declared_binding or (
        record.get("target_id") != plan["target_id"]
    ):
        _fail(
            "TARGET_VERSION_MISMATCH",
            "the plan names a different target or version than the screened manifest",
            {
                "plan_target": [plan["target_id"], plan["target_version"]],
                "manifest_target": list(declared_binding),
                "record_target_id": record.get("target_id"),
            },
        )
    _ground_references(plan, ports, vocabulary.reference_directions)

    core = _sealed_core(plan, cascade, register, manifest_hash, predecessor_hash)
    plan["preregistration_hash"] = digest(core)
    errors = plan_schema_errors(root, plan)
    if errors:
        _fail(
            "PLAN_SCHEMA_INVALID",
            "the assembled plan does not validate against its schema",
            {"errors": errors},
        )

    receipt: dict[str, Any] = {
        "amendment_index": amendment_index,
        "amends": predecessor_hash,
        "cascade_plan": cascade,
        "counts": {**counts, "stages": len(cascade["stages"])},
        "eligibility_record": record,
        "exploratory_prediction_ids": sorted(
            entry["prediction_id"] for entry in register if entry["exploratory"]
        ),
        "plan": plan,
        "plan_hash": digest(plan),
        "prediction_register": register,
        "preregistered_at": _text(preregistered_at, "preregistered_at"),
        "preregistration_hash": plan["preregistration_hash"],
        "promotable_prediction_ids": sorted(
            entry["prediction_id"] for entry in register if entry["promotable"]
        ),
        "receipt_id": _text(receipt_id, "receipt_id"),
        "target_manifest_hash": manifest_hash,
        "vocabulary_hash": vocabulary.vocabulary_hash,
    }
    _exact_fields(receipt, frozenset(RECEIPT_FIELDS), "receipt")
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def verify_preregistration(
    repository_root: str | Path, receipt: Mapping[str, Any]
) -> list[str]:
    """Everything about a sealed preregistration that no longer re-derives.

    Reported rather than raised, because a caller auditing a chain of receipts
    needs the whole ledger and not the first break.  The derived fields are
    re-derived too, not only the hashes: an edit that moved a criterion and
    recomputed every digest would still have to leave the rendered rule and the
    endpoint list matching the register it claims to come from.
    """

    root = Path(repository_root)
    document = _mapping(receipt, "receipt")
    mismatches: list[str] = []
    if set(document) != set(RECEIPT_FIELDS) | {"receipt_hash"}:
        return ["receipt_fields"]
    if document["receipt_hash"] != hash_excluding(document, "receipt_hash"):
        mismatches.append("receipt_hash")
    if (
        not isinstance(document.get("plan"), Mapping)
        or not isinstance(document.get("cascade_plan"), Mapping)
        or not isinstance(document.get("prediction_register"), list)
    ):
        return sorted({*mismatches, "receipt_shape"})
    plan = dict(document["plan"])
    cascade = dict(document["cascade_plan"])
    register = list(document["prediction_register"])
    if set(plan) != set(plan_fields(root)):
        return sorted({*mismatches, "plan_fields"})
    if cascade.get("plan_hash") != hash_excluding(cascade, "plan_hash"):
        mismatches.append("cascade_plan_hash")
    for entry in register:
        if not isinstance(entry, Mapping) or entry.get("entry_hash") != hash_excluding(
            entry, "entry_hash"
        ):
            mismatches.append("register_entry_hash")
            break
    core = _sealed_core(
        plan,
        cascade,
        register,
        document.get("target_manifest_hash"),
        document.get("amends"),
    )
    sealed = digest(core)
    if document.get("preregistration_hash") != sealed:
        mismatches.append("preregistration_hash")
    if plan.get("preregistration_hash") != sealed:
        mismatches.append("plan_preregistration_hash")
    if document.get("plan_hash") != digest(plan):
        mismatches.append("plan_hash")
    if plan.get("falsification_rule") != _derived(
        lambda: render_falsification_rule(register)
    ):
        mismatches.append("falsification_rule")
    if plan.get("observables") != _derived(lambda: _observables(register)):
        mismatches.append("observables")
    if document.get("counts") != _derived(
        lambda: {
            **register_counts(register),
            "stages": len(cascade.get("stages") or ()),
        }
    ):
        mismatches.append("counts")
    if plan_schema_errors(root, plan):
        mismatches.append("plan_schema")
    if cascade_schema_errors(root, cascade):
        mismatches.append("cascade_schema")
    return sorted(set(mismatches))


def require_intact(
    repository_root: str | Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Refuse a preregistration that was changed after it was sealed."""

    mismatches = verify_preregistration(repository_root, receipt)
    if mismatches:
        _fail(
            "PREREGISTRATION_MUTATED",
            "the sealed preregistration no longer re-derives its own hashes",
            {"mismatches": mismatches},
        )
    return dict(receipt)


def amendment_chain(
    repository_root: str | Path, receipts: Sequence[Any]
) -> tuple[str, ...]:
    """The seals of an unbroken amendment chain, oldest first.

    Each receipt must re-derive, must name the previous receipt's seal, and
    must carry the next amendment index.  A chain that skips, repeats or points
    at a seal nobody published is refused rather than reordered.
    """

    root = Path(repository_root)
    seals: list[str] = []
    previous: dict[str, Any] | None = None
    for index, value in enumerate(_sequence(receipts, "receipts")):
        receipt = _mapping(value, f"receipts[{index}]")
        require_intact(root, receipt)
        expected = None if previous is None else previous["preregistration_hash"]
        expected_index = 0 if previous is None else previous["amendment_index"] + 1
        if receipt.get("amends") != expected or (
            receipt.get("amendment_index") != expected_index
        ):
            _fail(
                "AMENDMENT_CHAIN_BROKEN",
                f"receipts[{index}] does not continue the chain",
                {
                    "expected_predecessor": expected,
                    "declared_predecessor": receipt.get("amends"),
                    "expected_index": expected_index,
                    "declared_index": receipt.get("amendment_index"),
                },
            )
        seals.append(str(receipt["preregistration_hash"]))
        previous = receipt
    return tuple(seals)
