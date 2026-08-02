"""schema_and_type_check — the gate reads its vocabulary, never invents it.

Every value this component decides against is declared somewhere in
``schemas/``: the reconciliation field set, the evidence roles and promotion
decisions, both evidence-class enums, the falsification outcomes and result
statuses, and the canonical ``sha256`` pattern.  The empirical boundary EF4-I11
turns on is not a hand-kept list either — it is derived from the class enums by
marker and asserted here to be non-empty and proper, so a schema that adds an
empirical class moves the boundary rather than leaving a stale rule.

The small named anchors the gate decides against — the confirming role, the
four promotion decisions, the clean result status and the confirming, refuting
and untested outcomes — are pinned here against the enums that declare them,
and the clean-execution gate is pinned against V03's own ladder, because a
renamed enum would otherwise silently move a rule and this suite is where that
has to fail instead.  The finding vocabulary is checked for the thing that
makes a refusal usable: a reason a reader can act on rather than a bare code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epistemic_foundry.validation.execution import EXECUTION_GATE_LADDER

from .contracts import (
    CLEAN_EXECUTION_GATE,
    CLEAN_RESULT_STATUS,
    CONFIRMING_OUTCOME,
    CONFIRMING_ROLE,
    EMPIRICAL_CLASS_MARKERS,
    EVIDENCE_NODE_SCHEMA_PATH,
    EXPERIMENT_RESULT_SCHEMA_PATH,
    FINDING_CODES,
    PROMOTE,
    QUARANTINE,
    RECONCILIATION_SCHEMA_PATH,
    REFUSAL_DECISION,
    REFUTING_OUTCOME,
    REJECT,
    REQUIRE_HUMAN_REVIEW,
    UNTESTED_OUTCOME,
    ValidationReconciliationError,
    clean_execution_gate,
    clean_result_status,
    confirming_role,
    empirical_evidence_classes,
    empirical_result_classes,
    evidence_classes,
    evidence_roles,
    falsification_outcomes,
    outcome_vocabulary,
    promotion_decisions,
    promotion_vocabulary,
    reconciliation_fields,
    result_evidence_classes,
    result_fields,
    result_statuses,
    sha256_pattern,
)

ROOT = Path(__file__).resolve().parents[4]
MINIMUM_REASON_LENGTH = 50


def schema(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_the_reconciliation_field_set_comes_from_the_schema() -> None:
    document = schema(RECONCILIATION_SCHEMA_PATH)

    assert reconciliation_fields(ROOT) == frozenset(document["required"])
    assert len(reconciliation_fields(ROOT)) == 13


def test_the_roles_and_decisions_come_from_the_schema() -> None:
    document = schema(RECONCILIATION_SCHEMA_PATH)["properties"]

    assert evidence_roles(ROOT) == tuple(document["target_evidence_role"]["enum"])
    assert promotion_decisions(ROOT) == tuple(document["promotion_decision"]["enum"])


def test_the_evidence_classes_come_from_the_two_schemas() -> None:
    node = schema(EVIDENCE_NODE_SCHEMA_PATH)["properties"]["evidence_class"]["enum"]
    result = schema(EXPERIMENT_RESULT_SCHEMA_PATH)["properties"]["evidence_class"][
        "enum"
    ]

    assert evidence_classes(ROOT) == tuple(node)
    assert result_evidence_classes(ROOT) == tuple(result)


def test_the_result_vocabulary_comes_from_the_schema() -> None:
    document = schema(EXPERIMENT_RESULT_SCHEMA_PATH)

    assert falsification_outcomes(ROOT) == tuple(
        document["properties"]["falsification_outcome"]["enum"]
    )
    assert result_statuses(ROOT) == tuple(document["properties"]["status"]["enum"])
    assert result_fields(ROOT) == frozenset(document["required"])


def test_the_empirical_subset_is_derived_and_non_trivial() -> None:
    # The boundary EF4-I11 turns on is read from the enum by marker, so exactly
    # the classes the vocabularies name empirical or observational are refused
    # as relabel targets — and neither vocabulary may collapse to all or none.
    assert empirical_evidence_classes(ROOT) == (
        "primary_empirical",
        "secondary_empirical",
    )
    assert empirical_result_classes(ROOT) == (
        "prospective_empirical",
        "retrospective_observational",
    )
    for classes in (evidence_classes(ROOT), result_evidence_classes(ROOT)):
        empirical = {
            value
            for value in classes
            if any(marker in value for marker in EMPIRICAL_CLASS_MARKERS)
        }
        assert 0 < len(empirical) < len(classes)


def test_the_named_anchors_are_values_the_schema_declares() -> None:
    assert confirming_role(ROOT) == CONFIRMING_ROLE
    assert CONFIRMING_ROLE in evidence_roles(ROOT)
    for anchor in (CONFIRMING_OUTCOME, REFUTING_OUTCOME, UNTESTED_OUTCOME):
        assert anchor in falsification_outcomes(ROOT)
    assert set(outcome_vocabulary(ROOT)) == {
        CONFIRMING_OUTCOME,
        REFUTING_OUTCOME,
        UNTESTED_OUTCOME,
    }
    assert clean_result_status(ROOT) == CLEAN_RESULT_STATUS
    assert CLEAN_RESULT_STATUS in result_statuses(ROOT)


def test_the_promotion_anchors_cover_the_schema_enum_exactly() -> None:
    table = promotion_vocabulary(ROOT)

    assert set(table) == set(promotion_decisions(ROOT))
    assert {PROMOTE, QUARANTINE, REJECT, REQUIRE_HUMAN_REVIEW} == set(table)


def test_the_clean_execution_gate_is_on_v03s_ladder() -> None:
    assert clean_execution_gate(ROOT) == CLEAN_EXECUTION_GATE
    assert CLEAN_EXECUTION_GATE in EXECUTION_GATE_LADDER


def test_every_refusal_decision_forces_a_declared_decision() -> None:
    for code, decision in REFUSAL_DECISION.items():
        assert decision in promotion_decisions(ROOT)
        assert code in FINDING_CODES


def test_the_record_hash_pattern_comes_from_the_schema() -> None:
    document = schema(RECONCILIATION_SCHEMA_PATH)

    assert (
        sha256_pattern(ROOT).pattern == document["properties"]["record_hash"]["pattern"]
    )


def test_every_finding_code_carries_an_actionable_reason() -> None:
    short = {
        code: reason
        for code, reason in FINDING_CODES.items()
        if len(reason) <= MINIMUM_REASON_LENGTH
    }

    assert short == {}
    assert sorted(FINDING_CODES) == list(FINDING_CODES)


def test_an_unreadable_schema_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationReconciliationError) as error:
        reconciliation_fields(tmp_path)

    assert error.value.code == "SCHEMA_UNREADABLE"
