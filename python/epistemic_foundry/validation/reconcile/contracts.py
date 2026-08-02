"""V04 deterministic V-phase result reconciliation and evidence-class gate.

By the time a validation result reaches this module three separate surfaces
have each said their piece and none of them, alone, is allowed to decide what
the result *means*.  V01 screened a target and fixed its scope.  V02 sealed a
plan whose falsification rule was written before any number existed.  V03 ran
the target under a lease and sealed what actually happened.  V04 is the one
place those three are reconciled into a single typed claim about a candidate
piece of evidence — and its whole job is to make that claim without letting any
surface overclaim through the seams between them.

Two refusals carry the exit criteria, and both are deliberately un-optimisable.

*A failed run is not a confirmation.*  The V03 execution record already
separates a target that ran and returned a failure (``FAILED_RUN``) from a run
whose effects did not reconcile (``INCIDENT``) from a run that never started
(``DENIED``); only a ``PASS`` is a clean execution.  A result may be entered as
a ``support`` role — the one role that asserts the hypothesis was upheld — only
when the run was clean, the result status was ``COMPLETED`` and the
preregistered falsification rule returned ``NOT_FALSIFIED``.  Ask for
confirmation from anything less and the reconciliation is ``REJECT`` rather than
quietly downgraded, because a broken pipeline reading as a null result and a
broken pipeline reading as support are two different lies and only the second
is dangerous.

*Simulation, formal, benchmark and empirical evidence stay distinct.*  The
class a result carries is the class its source produced; reconciliation copies
it forward verbatim and never launders it.  The one transformation the gate
polices is the only one that matters for EF4-I11: a source whose evidence class
is not empirical may not be entered as a candidate whose evidence class *is*
empirical.  "Empirical" here is not a hand-kept list — it is every class the
canonical vocabularies mark as empirical or observational, read from the schema
at runtime, so a schema that adds an empirical class moves the boundary with it
instead of leaving a stale rule behind.  A relabel across that boundary is
``REJECT`` and its ``non_empirical_guard_passed`` flag is false.

Everything between those two refusals is preserved rather than discarded.  A run
that did not cleanly execute, a result that was falsified or inconclusive, is
``REQUIRE_HUMAN_REVIEW`` — kept, attributed and waiting for a person, never
dropped.  A clean run whose plan declared nothing falsifiable is ``QUARANTINE``:
admissible, but walled off from being read as a test it never ran.  Only a
clean, uncontested, honestly-classed result is ``PROMOTE``.  The decision is
categorical the whole way down; ``quality_adjustments`` are carried on the
record for a later reader but never touch the branch that was taken, so no score
can buy a promotion.

Every vocabulary is read from the canonical schemas rather than restated: the
reconciliation field set, the evidence roles and promotion decisions, the two
evidence-class enums, the falsification outcomes and result statuses, and the
``sha256`` pattern.  The content addressing is V01's ``digest`` and
``hash_excluding``, so a reconciliation hash and an eligibility hash come from
one implementation.  The clean-execution gate is V03's own ladder, imported
rather than duplicated.  The small named anchors this module decides against —
the confirming role, the four promotion decisions, the clean result status and
the confirming and refuting outcomes — are each asserted against the schema
enum that declares them, so a renamed enum breaks this module loudly instead of
leaving a rule governing a value nobody uses.

No clock and no randomness.  Every id and timestamp is supplied by the caller,
inputs are never mutated, every derived list is sorted, and the record
re-derives its own hash from exactly the fields it publishes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from epistemic_foundry.validation.execution import EXECUTION_GATE_LADDER
from epistemic_foundry.validation.planning import verify_preregistration
from epistemic_foundry.validation.targets import (
    SCOPE_SCHEMA_PATH,
    empty_scope_vector,
    hash_excluding,
)

#: The canonical reconciliation record this module builds and seals.
RECONCILIATION_SCHEMA_PATH: Final = "schemas/evidence-reconciliation-record.schema.json"
#: The canonical evidence node a reconciled result would become a candidate for.
EVIDENCE_NODE_SCHEMA_PATH: Final = "schemas/evidence-node.schema.json"
#: The canonical typed result a reconciliation reads its class and outcome from.
EXPERIMENT_RESULT_SCHEMA_PATH: Final = "schemas/experiment-result.schema.json"

#: RFC3339 instants.  ``format`` is annotation-only under Draft 2020-12, so the
#: shape the record's ``created_at`` depends on is checked here explicitly.
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)

#: A source or candidate evidence class is empirical observation when its
#: canonical name carries one of these markers.  The set is what makes EF4-I11
#: enforceable without a hand-kept list of empirical classes that would drift
#: from the schema: the boundary is read from the enum values themselves, so a
#: schema that names a new empirical or observational class is caught by the
#: same rule.  The derived subsets are asserted non-empty and proper below, so a
#: vocabulary in which every class matched, or none did, fails loudly.
EMPIRICAL_CLASS_MARKERS: Final = ("empirical", "observational")

#: The one evidence role that asserts a hypothesis was upheld.  A result may be
#: entered under it only from a clean, uncontested run.
CONFIRMING_ROLE: Final = "support"

#: The four decisions a reconciliation resolves to, named so the derivation
#: reads as prose.  Each is asserted to be a value the canonical schema declares.
PROMOTE: Final = "PROMOTE"
QUARANTINE: Final = "QUARANTINE"
REJECT: Final = "REJECT"
REQUIRE_HUMAN_REVIEW: Final = "REQUIRE_HUMAN_REVIEW"

#: The execution gate that means the run cleanly executed.  Everything else on
#: V03's ladder is a run that failed, incidented or never started, and none of
#: those may confirm anything.
CLEAN_EXECUTION_GATE: Final = "PASS"

#: The single result status that reports a run reached completion.
CLEAN_RESULT_STATUS: Final = "COMPLETED"
#: The falsification outcome that upholds the preregistered claim.
CONFIRMING_OUTCOME: Final = "NOT_FALSIFIED"
#: The falsification outcome that refutes it.
REFUTING_OUTCOME: Final = "FALSIFIED"
#: The outcome of a plan that declared nothing an observation could refute.
UNTESTED_OUTCOME: Final = "NOT_APPLICABLE"

#: The reconciliation questions a sealed record answers, in reading order.
RECONCILIATION_CRITERIA: Final = (
    "surfaces_bound",
    "execution_clean",
    "result_completed",
    "claim_untested",
    "evidence_class_preserved",
    "confirmation_supported",
)

#: Every way this module refuses, and why that refusal is not something a caller
#: could reasonably be asked to work around.
FINDING_CODES: dict[str, str] = {
    "CONFIRMATION_WITHOUT_CLEAN_RUN": (
        "a support role was requested from a run that did not cleanly execute, "
        "complete and pass its preregistered falsification rule, so a failed or "
        "refuted run would be recorded as though it had confirmed the claim"
    ),
    "EVIDENCE_CLASS_OVERCLAIMED": (
        "a non-empirical source result would be entered as an empirical "
        "candidate, so simulation, formal or benchmark evidence would be "
        "relabelled as observation nothing actually observed"
    ),
    "EXECUTION_UNSEALED": (
        "the supplied execution record does not re-derive the hash it "
        "publishes, so what the run is claimed to have done was edited after "
        "V03 sealed it and cannot anchor a reconciliation"
    ),
    "FIELD_SET_INVALID": (
        "a record carries a field set the declaring schema does not allow, so "
        "some field is missing or some field would be silently ignored"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this contract accepts, so continuing would "
        "mean guessing what the caller meant instead of refusing plainly"
    ),
    "PREREGISTRATION_MUTATED": (
        "the supplied preregistration no longer re-derives its own hashes, so "
        "the falsification rule a result is judged against was changed after it "
        "was sealed and the judgement could not be trusted"
    ),
    "RECORD_HASH_MISMATCH": (
        "a reconciliation record does not re-derive the hash it publishes, so "
        "it was edited after sealing and nothing downstream may rest on it"
    ),
    "RECORD_SCHEMA_INVALID": (
        "the assembled reconciliation record does not validate against its "
        "canonical schema, so this builder would be sealing a document nothing "
        "downstream accepts"
    ),
    "RESULT_SCHEMA_INVALID": (
        "the supplied experiment result does not validate against its canonical "
        "schema, so the class and outcome a reconciliation reads from it have "
        "no governing shape"
    ),
    "SCHEMA_UNREADABLE": (
        "a canonical schema this module reads its vocabulary from cannot be "
        "read or does not declare what is expected, so nothing may be sealed"
    ),
    "SURFACES_UNRECONCILED": (
        "the execution record, the experiment result and the declared ids do "
        "not agree on the run or result they describe, so there is no single "
        "result to reconcile and no record could honestly name one"
    ),
    "VOCABULARY_DRIFT": (
        "a local decision anchor no longer matches the canonical schema that "
        "declares its value, so some sealed decision has no governing rule"
    ),
}

#: The refusals the gate reports rather than raises, mapped to the decision each
#: forces.  A caller repairing an over-claimed reconciliation needs the whole
#: ledger, so these are collected and returned, not thrown on the first one.
REFUSAL_DECISION: Final = {
    "CONFIRMATION_WITHOUT_CLEAN_RUN": REJECT,
    "EVIDENCE_CLASS_OVERCLAIMED": REJECT,
}


class ValidationReconciliationError(ValueError):
    """A result, surface or record that could not describe a reconciliation."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ValidationReconciliationError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ValidationReconciliationError(code, message, context)


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


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail(
            "INPUT_INVALID",
            f"{label} must be an RFC3339 instant",
            {"label": label, "value": text},
        )
    return text


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


def _pattern(repository_root: str | Path, relative: str, *path: str) -> re.Pattern[str]:
    node = _node(_schema(repository_root, relative), relative, *path)
    if not isinstance(node, str) or not node:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares no pattern at {'.'.join(path)}",
            {"schema": relative},
        )
    return re.compile(str(node))


def _assert_declared(value: str, declared: Sequence[str], label: str) -> str:
    """A local anchor must be a value the canonical schema still declares."""

    if value not in declared:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} anchor is not a value the schema declares",
            {"label": label, "value": value, "declared": list(declared)},
        )
    return value


def _validate_enum(value: object, declared: Sequence[str], label: str) -> str:
    """A caller-supplied value must be one the canonical schema declares."""

    text = _text(value, label)
    if text not in declared:
        _fail(
            "INPUT_INVALID",
            f"{label} is not a value the canonical schema declares",
            {"label": label, "value": text, "allowed": list(declared)},
        )
    return text


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


def reconciliation_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a canonical EvidenceReconciliationRecord must carry."""

    return _required(repository_root, RECONCILIATION_SCHEMA_PATH)


def evidence_roles(repository_root: str | Path) -> tuple[str, ...]:
    """The target evidence roles as the reconciliation schema declares them."""

    return _enum(
        repository_root,
        RECONCILIATION_SCHEMA_PATH,
        "properties",
        "target_evidence_role",
        "enum",
    )


def promotion_decisions(repository_root: str | Path) -> tuple[str, ...]:
    """The promotion decisions the reconciliation schema declares."""

    return _enum(
        repository_root,
        RECONCILIATION_SCHEMA_PATH,
        "properties",
        "promotion_decision",
        "enum",
    )


def evidence_classes(repository_root: str | Path) -> tuple[str, ...]:
    """The evidence-node evidence classes a candidate can be entered under."""

    return _enum(
        repository_root,
        EVIDENCE_NODE_SCHEMA_PATH,
        "properties",
        "evidence_class",
        "enum",
    )


def result_evidence_classes(repository_root: str | Path) -> tuple[str, ...]:
    """The evidence classes an ExperimentResult can carry."""

    return _enum(
        repository_root,
        EXPERIMENT_RESULT_SCHEMA_PATH,
        "properties",
        "evidence_class",
        "enum",
    )


def falsification_outcomes(repository_root: str | Path) -> tuple[str, ...]:
    """The falsification outcomes an ExperimentResult can report."""

    return _enum(
        repository_root,
        EXPERIMENT_RESULT_SCHEMA_PATH,
        "properties",
        "falsification_outcome",
        "enum",
    )


def result_statuses(repository_root: str | Path) -> tuple[str, ...]:
    """The completion statuses an ExperimentResult can report."""

    return _enum(
        repository_root, EXPERIMENT_RESULT_SCHEMA_PATH, "properties", "status", "enum"
    )


def result_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a canonical ExperimentResult must carry."""

    return _required(repository_root, EXPERIMENT_RESULT_SCHEMA_PATH)


def sha256_pattern(repository_root: str | Path) -> re.Pattern[str]:
    """The canonical sha256 form the reconciliation record's hash must take."""

    return _pattern(
        repository_root,
        RECONCILIATION_SCHEMA_PATH,
        "properties",
        "record_hash",
        "pattern",
    )


def _empirical(classes: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            value
            for value in classes
            if any(marker in value for marker in EMPIRICAL_CLASS_MARKERS)
        )
    )


def _assert_partition(classes: Sequence[str], label: str) -> tuple[str, ...]:
    """The empirical subset of a class vocabulary, non-empty and proper.

    A vocabulary in which every class read as empirical, or none did, would
    make the guard either refuse everything or nothing, so both are drift.
    """

    empirical = _empirical(classes)
    if not empirical:
        _fail(
            "VOCABULARY_DRIFT",
            f"no {label} class carries an empirical marker, so the guard would "
            "never refuse a relabel",
            {"label": label, "classes": list(classes)},
        )
    if len(empirical) == len(set(classes)):
        _fail(
            "VOCABULARY_DRIFT",
            f"every {label} class carries an empirical marker, so the guard "
            "would refuse every non-empirical source",
            {"label": label, "classes": list(classes)},
        )
    return empirical


def empirical_evidence_classes(repository_root: str | Path) -> tuple[str, ...]:
    """The empirical evidence-node classes, derived from the schema enum."""

    return _assert_partition(evidence_classes(repository_root), "evidence node")


def empirical_result_classes(repository_root: str | Path) -> tuple[str, ...]:
    """The empirical ExperimentResult classes, derived from the schema enum."""

    return _assert_partition(result_evidence_classes(repository_root), "result")


def confirming_role(repository_root: str | Path) -> str:
    """The confirming role, checked against the declared role vocabulary."""

    return _assert_declared(CONFIRMING_ROLE, evidence_roles(repository_root), "role")


def promotion_vocabulary(repository_root: str | Path) -> dict[str, str]:
    """The four named decisions, asserted to cover the schema enum exactly."""

    declared = promotion_decisions(repository_root)
    table = {
        PROMOTE: PROMOTE,
        QUARANTINE: QUARANTINE,
        REJECT: REJECT,
        REQUIRE_HUMAN_REVIEW: REQUIRE_HUMAN_REVIEW,
    }
    _assert_table(table, declared, "promotion decision")
    return dict(table)


def outcome_vocabulary(repository_root: str | Path) -> dict[str, str]:
    """The falsification anchors this module decides against, checked in place."""

    declared = falsification_outcomes(repository_root)
    return {
        anchor: _assert_declared(anchor, declared, "falsification outcome")
        for anchor in (CONFIRMING_OUTCOME, REFUTING_OUTCOME, UNTESTED_OUTCOME)
    }


def clean_execution_gate(repository_root: str | Path) -> str:
    """The gate that means a clean run, checked against V03's own ladder."""

    if CLEAN_EXECUTION_GATE not in EXECUTION_GATE_LADDER:
        _fail(
            "VOCABULARY_DRIFT",
            "the clean-execution anchor is not on V03's execution gate ladder",
            {"anchor": CLEAN_EXECUTION_GATE, "ladder": list(EXECUTION_GATE_LADDER)},
        )
    return CLEAN_EXECUTION_GATE


def clean_result_status(repository_root: str | Path) -> str:
    """The status that means the run completed, checked against the enum."""

    return _assert_declared(
        CLEAN_RESULT_STATUS, result_statuses(repository_root), "result status"
    )


def _resource(document: Mapping[str, Any]) -> tuple[str, Resource[Any]]:
    identifier = document.get("$id")
    if not isinstance(identifier, str) or not identifier:
        _fail("SCHEMA_UNREADABLE", "a canonical schema declares no $id")
    return str(identifier), Resource.from_contents(
        dict(document), default_specification=DRAFT202012
    )


def _record_validator(repository_root: str | Path) -> Draft202012Validator:
    """A validator for the reconciliation record, resolving its scope ref.

    The record embeds a full scope vector by reference, so the scope schema is
    registered under its own ``$id`` exactly as V01 and V02 register it, rather
    than resolved from wherever the file sits on disk.
    """

    documents = [
        _schema(repository_root, RECONCILIATION_SCHEMA_PATH),
        _schema(repository_root, SCOPE_SCHEMA_PATH),
    ]
    registry: Registry[Any] = Registry().with_resources(
        _resource(document) for document in documents
    )
    return Draft202012Validator(documents[0], registry=registry)


def record_schema_errors(repository_root: str | Path, record: object) -> list[str]:
    """Every canonical schema error in a candidate reconciliation record."""

    return sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in _record_validator(repository_root).iter_errors(record)
    )


def result_schema_errors(repository_root: str | Path, result: object) -> list[str]:
    """Every canonical schema error in a candidate ExperimentResult."""

    return sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in Draft202012Validator(
            _schema(repository_root, EXPERIMENT_RESULT_SCHEMA_PATH)
        ).iter_errors(result)
    )


def _quality_adjustments(value: object) -> dict[str, Any]:
    """A carried-forward scalar map, refused if it is anything the schema is not.

    The values are recorded for a later reader and, by construction, never enter
    the decision; refusing a non-scalar here keeps a caller from smuggling a
    structure the schema would reject only at the very end.
    """

    document = _mapping(value, "quality_adjustments")
    resolved: dict[str, Any] = {}
    for key in sorted(document):
        entry = document[key]
        if entry is not None and not isinstance(entry, (str, int, float)):
            _fail(
                "INPUT_INVALID",
                "a quality adjustment must be a number, a string or null",
                {"key": key},
            )
        if isinstance(entry, bool):
            _fail(
                "INPUT_INVALID",
                "a quality adjustment must be a number, a string or null",
                {"key": key},
            )
        resolved[key] = entry
    return resolved


def _bind_surfaces(
    repository_root: str | Path,
    *,
    run_id: str,
    source_result_id: str,
    execution_record: Mapping[str, Any],
    experiment_result: Mapping[str, Any],
    preregistration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Reconcile the three surfaces onto one run, or refuse to name one.

    The execution record must re-derive the hash V03 sealed it under, the
    experiment result must validate against its canonical schema, and the run
    and result ids the two surfaces carry must agree with each other and with
    the ids the caller declared.  A preregistration, when supplied, must still
    re-derive its own seal, so a result cannot be judged against a falsification
    rule that was edited after the fact.
    """

    root = Path(repository_root)
    execution = _mapping(execution_record, "execution_record")
    if execution.get("record_hash") != hash_excluding(execution, "record_hash"):
        _fail(
            "EXECUTION_UNSEALED",
            "the execution record does not re-derive the hash it publishes",
            {"run_id": execution.get("run_id")},
        )
    gate = _text(execution.get("gate"), "execution_record.gate")
    if gate not in EXECUTION_GATE_LADDER:
        _fail(
            "VOCABULARY_DRIFT",
            "the execution record carries a gate outcome V03 does not declare",
            {"gate": gate, "ladder": list(EXECUTION_GATE_LADDER)},
        )

    result = _mapping(experiment_result, "experiment_result")
    _exact_fields(result, result_fields(root), "experiment_result")
    errors = result_schema_errors(root, result)
    if errors:
        _fail(
            "RESULT_SCHEMA_INVALID",
            "the experiment result does not validate against its schema",
            {"errors": errors},
        )

    declared_run = _text(run_id, "run_id")
    declared_result = _text(source_result_id, "source_result_id")
    execution_run = _text(execution.get("run_id"), "execution_record.run_id")
    result_run = _text(result.get("run_id"), "experiment_result.run_id")
    result_id = _text(result.get("result_id"), "experiment_result.result_id")
    disagreements = {
        "execution_run_id": execution_run,
        "result_run_id": result_run,
        "result_id": result_id,
    }
    if (
        not (execution_run == result_run == declared_run)
        or result_id != declared_result
    ):
        _fail(
            "SURFACES_UNRECONCILED",
            "the surfaces do not agree on the run or result they describe",
            {
                "declared_run_id": declared_run,
                "declared_result_id": declared_result,
                **disagreements,
            },
        )

    if preregistration is not None:
        mismatches = verify_preregistration(root, _mapping(preregistration, "prereg"))
        if mismatches:
            _fail(
                "PREREGISTRATION_MUTATED",
                "the supplied preregistration no longer re-derives its own hashes",
                {"mismatches": mismatches},
            )

    return {
        "gate": gate,
        "result_status": _text(result.get("status"), "experiment_result.status"),
        "falsification_outcome": _text(
            result.get("falsification_outcome"),
            "experiment_result.falsification_outcome",
        ),
        "source_evidence_class": _text(
            result.get("evidence_class"), "experiment_result.evidence_class"
        ),
        "run_id": declared_run,
    }


def assess_reconciliation(
    repository_root: str | Path,
    *,
    run_id: str,
    source_result_id: str,
    execution_record: Mapping[str, Any],
    experiment_result: Mapping[str, Any],
    target_evidence_role: str,
    candidate_evidence_class: str,
    preregistration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Weigh one reconciliation against every criterion without sealing it.

    Every criterion is evaluated rather than short-circuited, so a caller
    repairing an over-claimed reconciliation sees the whole gap in one pass.
    The two policy refusals — a confirmation asked of an unclean run, and a
    non-empirical source relabelled as empirical — are reported here rather than
    raised, and each forces the decision the record will publish.  The
    structural refusals that make a result un-reconcilable at all are raised by
    :func:`_bind_surfaces` before any of this runs.
    """

    root = Path(repository_root)
    bound = _bind_surfaces(
        root,
        run_id=run_id,
        source_result_id=source_result_id,
        execution_record=execution_record,
        experiment_result=experiment_result,
        preregistration=preregistration,
    )

    role = _validate_enum(
        target_evidence_role, evidence_roles(root), "target_evidence_role"
    )
    candidate_class = _validate_enum(
        candidate_evidence_class, evidence_classes(root), "candidate_evidence_class"
    )
    confirm = confirming_role(root)
    outcomes = outcome_vocabulary(root)
    promotion_vocabulary(root)
    clean_gate = clean_execution_gate(root)
    completed = clean_result_status(root)
    empirical_candidate = candidate_class in empirical_evidence_classes(root)
    empirical_source = bound["source_evidence_class"] in empirical_result_classes(root)

    execution_clean = bound["gate"] == clean_gate
    result_completed = bound["result_status"] == completed
    not_falsified = bound["falsification_outcome"] == outcomes[CONFIRMING_OUTCOME]
    falsified = bound["falsification_outcome"] == outcomes[REFUTING_OUTCOME]
    untested = bound["falsification_outcome"] == outcomes[UNTESTED_OUTCOME]
    confirming = execution_clean and result_completed and not_falsified
    guard_passed = not (empirical_candidate and not empirical_source)

    refusals: list[str] = []
    satisfied: list[str] = []
    reasons: list[str] = []

    reasons.append(
        f"the execution record, the result and the declared ids agree on run "
        f"{bound['run_id']}"
    )
    satisfied.append("surfaces_bound")

    if execution_clean:
        satisfied.append("execution_clean")
        reasons.append(f"the run executed cleanly at gate {bound['gate']}")
    else:
        reasons.append(f"the run did not cleanly execute; its gate was {bound['gate']}")
    if result_completed:
        satisfied.append("result_completed")
    else:
        reasons.append(
            f"the result status was {bound['result_status']} rather than {completed}"
        )
    if untested:
        satisfied.append("claim_untested")
        reasons.append("the preregistered plan declared nothing falsifiable to test")

    if guard_passed:
        satisfied.append("evidence_class_preserved")
        reasons.append(
            f"the {bound['source_evidence_class']} source is entered as a "
            f"{candidate_class} candidate without crossing the empirical boundary"
        )
    else:
        refusals.append("EVIDENCE_CLASS_OVERCLAIMED")
        reasons.append(
            f"a {bound['source_evidence_class']} source may not be entered as the "
            f"empirical class {candidate_class}"
        )

    if role == confirm and not confirming:
        refusals.append("CONFIRMATION_WITHOUT_CLEAN_RUN")
        reasons.append(
            f"the {confirm} role was requested but the run did not cleanly "
            "execute, complete and pass its falsification rule"
        )
    elif role == confirm:
        satisfied.append("confirmation_supported")
        reasons.append(f"a clean, uncontested run supports the {confirm} role")

    if falsified:
        reasons.append("the preregistered claim was falsified by this result")

    codes = sorted(set(refusals))
    if codes:
        # A refusal decides the record: a relabel or a false confirmation is
        # rejected outright, and REJECT dominates if both are present.
        decision = REJECT
    elif execution_clean and result_completed and untested:
        decision = QUARANTINE
        reasons.append(
            "a clean run that tested nothing falsifiable is quarantined, not "
            "read as a test it never ran"
        )
    elif confirming:
        # Only a clean run that completed and was not falsified is promotable;
        # a positive outcome is required, never merely the absence of a refusal.
        decision = PROMOTE
        reasons.append("a clean, uncontested, honestly-classed result is promotable")
    else:
        decision = REQUIRE_HUMAN_REVIEW
        reasons.append(
            "the result is preserved for human review rather than promoted or dropped"
        )

    return {
        "candidate_evidence_class": candidate_class,
        "criteria": list(RECONCILIATION_CRITERIA),
        "criteria_satisfied": sorted(satisfied),
        "non_empirical_guard_passed": guard_passed,
        "promotion_decision": decision,
        "reasons": sorted(reasons),
        "refusal_codes": codes,
        "source_evidence_class": bound["source_evidence_class"],
        "target_evidence_role": role,
    }


def reconcile_evidence(
    repository_root: str | Path,
    *,
    reconciliation_id: str,
    run_id: str,
    source_result_id: str,
    candidate_evidence_id: str,
    execution_record: Mapping[str, Any],
    experiment_result: Mapping[str, Any],
    target_evidence_role: str,
    candidate_evidence_class: str,
    scope_mapping: Mapping[str, Any],
    quality_adjustments: Mapping[str, Any],
    created_at: str,
    preregistration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile one result across the V01/V02/V03 surfaces into one record.

    The class the source produced is copied forward verbatim into
    ``source_evidence_class``; reconciliation never launders it.  The
    ``promotion_decision`` and ``non_empirical_guard_passed`` are derived by
    :func:`assess_reconciliation` from categorical gates alone.
    ``quality_adjustments`` are carried onto the record for a later reader but,
    by construction, are read after the decision is fixed and cannot change it,
    so no score can buy a promotion.  The record re-derives its own hash over
    exactly the fields it publishes.
    """

    root = Path(repository_root)
    assessment = assess_reconciliation(
        root,
        run_id=run_id,
        source_result_id=source_result_id,
        execution_record=execution_record,
        experiment_result=experiment_result,
        target_evidence_role=target_evidence_role,
        candidate_evidence_class=candidate_evidence_class,
        preregistration=preregistration,
    )

    record: dict[str, Any] = {
        "candidate_evidence_id": _text(candidate_evidence_id, "candidate_evidence_id"),
        "created_at": _timestamp(created_at, "created_at"),
        "non_empirical_guard_passed": assessment["non_empirical_guard_passed"],
        "promotion_decision": assessment["promotion_decision"],
        "quality_adjustments": _quality_adjustments(quality_adjustments),
        "reasons": list(assessment["reasons"]),
        "reconciliation_id": _text(reconciliation_id, "reconciliation_id"),
        "run_id": _text(run_id, "run_id"),
        "scope_mapping": _scope(root, scope_mapping),
        "source_evidence_class": assessment["source_evidence_class"],
        "source_result_id": _text(source_result_id, "source_result_id"),
        "target_evidence_role": assessment["target_evidence_role"],
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    _exact_fields(record, reconciliation_fields(root), "reconciliation_record")
    errors = record_schema_errors(root, record)
    if errors:
        _fail(
            "RECORD_SCHEMA_INVALID",
            "the assembled reconciliation record does not validate against its schema",
            {"errors": errors},
        )
    return record


def _scope(
    repository_root: str | Path, scope_mapping: Mapping[str, Any]
) -> dict[str, Any]:
    """The scope vector V01 fixed for the target, carried onto the record.

    The full validation happens when the assembled record is checked against
    its schema, which resolves the scope reference; the exact-field check here
    turns a caller who dropped an axis into a clear refusal rather than a schema
    error buried among the record's own fields.
    """

    document = _mapping(scope_mapping, "scope_mapping")
    _exact_fields(
        document, frozenset(empty_scope_vector(repository_root)), "scope_mapping"
    )
    return json.loads(json.dumps(document, ensure_ascii=False, sort_keys=True))


def verify_reconciliation_record(
    repository_root: str | Path, record: Mapping[str, Any]
) -> dict[str, Any]:
    """Re-derive a reconciliation record's hash and schema, without deciding.

    Returned rather than raised, because a caller auditing a ledger of records
    wants the whole picture; the record is what turns a mismatch into a refusal
    at the point it is next relied on.
    """

    root = Path(repository_root)
    document = _mapping(record, "reconciliation_record")
    _exact_fields(document, reconciliation_fields(root), "reconciliation_record")
    expected = hash_excluding(document, "record_hash")
    record_out = {
        "promotion_decision": document["promotion_decision"],
        "reconciliation_id": document["reconciliation_id"],
        "record_hash_declared": document["record_hash"],
        "record_hash_derived": expected,
        "record_hash_matches": document["record_hash"] == expected,
        "schema_errors": record_schema_errors(root, document),
    }
    record_out["verification_hash"] = hash_excluding(record_out, "verification_hash")
    return record_out


def require_reconciled(
    repository_root: str | Path, record: Mapping[str, Any]
) -> dict[str, Any]:
    """Refuse a reconciliation record that was changed after it was sealed."""

    verification = verify_reconciliation_record(repository_root, record)
    if not verification["record_hash_matches"]:
        _fail(
            "RECORD_HASH_MISMATCH",
            "the reconciliation record no longer re-derives its own hash",
            {"reconciliation_id": verification["reconciliation_id"]},
        )
    if verification["schema_errors"]:
        _fail(
            "RECORD_SCHEMA_INVALID",
            "the reconciliation record no longer validates against its schema",
            {"errors": verification["schema_errors"]},
        )
    return dict(record)
