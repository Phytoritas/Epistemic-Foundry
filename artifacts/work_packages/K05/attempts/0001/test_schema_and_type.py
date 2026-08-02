"""schema_and_type_check — the boundaries read their vocabulary, never restate it.

Licence, integrity-status, novelty-status, promotion-ceiling and
novelty-dimension values all come from the canonical schemas that declare them,
and every position this module selects by index is asserted here against the
schema text so the assumption cannot rot in silence.  The last test is the
package-scoped form of EF4-I22: this module must hold *no* canonical enum value
as a literal at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from epistemic_foundry.contracts import default_registry, validate_artifact
from epistemic_foundry.evidence.v4_k05 import (
    CORPUS_BOUNDED_POSITION,
    FINDING_CODES,
    INTEGRITY_FAIL_POSITION,
    INTEGRITY_NOT_RUN_POSITION,
    INTEGRITY_PASS_POSITION,
    NOVELTY_LADDER,
    NOVELTY_SCHEMA,
    NOVELTY_STATUS_POSITION,
    PRIOR_ART_FOUND_POSITION,
    PROMOTION_CEILING_POSITION,
    SEARCH_BOUNDED_POSITION,
    UNDECLARED_LICENSE_POSITION,
    CorpusBoundaryError,
    integrity_check_vocabulary,
    integrity_overall_vocabulary,
    license_vocabulary,
    novelty_dimension_vocabulary,
    scalar_enum_field,
)
from epistemic_foundry.evidence.v4_k05 import boundaries as boundaries_module
from fixtures import (
    EVALUATED_AT,
    POLICY_VERSION,
    assessment_arguments,
    holdout,
    observed_hashes,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[5]
BOUNDARIES = ROOT / "src/epistemic_foundry/evidence/v4_k05/boundaries.py"


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def canonical_enum_values() -> set[str]:
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list):
                values.update(item for item in enum if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    registry = default_registry()
    for name in registry.names():
        walk(registry.document(name))
    return values


def test_the_license_vocabulary_is_declared_grant_first_and_absence_last() -> None:
    # The pin refuses the vocabulary's final member as "no license was
    # established"; that positional rule is only sound while the schema
    # declares the list from an explicit grant down to the absence of one.
    document = default_registry().document("document-manifest")

    assert document["properties"]["license_status"]["enum"] == [
        "licensed",
        "open_access",
        "fair_use_metadata_only",
        "restricted",
        "unknown",
    ]
    assert license_vocabulary()[UNDECLARED_LICENSE_POSITION] == "unknown"


def test_the_integrity_vocabularies_are_declared_best_outcome_first() -> None:
    document = default_registry().document("source-integrity-report")
    checks = document["properties"]["checks"]["items"]["properties"]["status"]["enum"]

    assert checks == ["PASS", "WARN", "FAIL", "NOT_RUN"]
    assert document["properties"]["overall_status"]["enum"] == [
        "PASS",
        "WARN",
        "FAIL",
        "QUARANTINE",
    ]
    assert integrity_check_vocabulary()[INTEGRITY_PASS_POSITION] == "PASS"
    assert integrity_check_vocabulary()[INTEGRITY_FAIL_POSITION] == "FAIL"
    assert integrity_check_vocabulary()[INTEGRITY_NOT_RUN_POSITION] == "NOT_RUN"
    assert integrity_overall_vocabulary()[INTEGRITY_PASS_POSITION] == "PASS"
    assert integrity_overall_vocabulary()[INTEGRITY_FAIL_POSITION] == "FAIL"


def test_the_novelty_fields_are_selected_by_declaration_order() -> None:
    # The status field's *name* is a canonical enum value in another schema, so
    # the module reads it by declaration order instead of holding it. This test
    # pins that order against the schema.
    status_field, status_ladder = scalar_enum_field(
        NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION
    )
    ceiling_field, ceiling_ladder = scalar_enum_field(
        NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION
    )

    assert status_field == "novelty_status"
    assert ceiling_field == "promotion_ceiling"
    assert list(status_ladder) == [
        "NOT_ASSESSED",
        "KNOWN_PRIOR_ART",
        "CORPUS_NOVEL_ONLY",
        "SEARCH_CONDITIONAL",
        "POTENTIALLY_NOVEL",
    ]
    assert list(ceiling_ladder) == [
        "NO_NOVELTY_CLAIM",
        "CORPUS_ONLY",
        "SEARCH_CONDITIONAL",
        "ELIGIBLE_FOR_HUMAN_REVIEW",
    ]


def test_the_reachable_novelty_ladder_stops_below_both_tops() -> None:
    _, status_ladder = scalar_enum_field(NOVELTY_SCHEMA, NOVELTY_STATUS_POSITION)
    _, ceiling_ladder = scalar_enum_field(NOVELTY_SCHEMA, PROMOTION_CEILING_POSITION)

    assert set(NOVELTY_LADDER) == {
        PRIOR_ART_FOUND_POSITION,
        CORPUS_BOUNDED_POSITION,
        SEARCH_BOUNDED_POSITION,
    }
    assert max(NOVELTY_LADDER) < len(status_ladder) - 1
    assert max(NOVELTY_LADDER.values()) < len(ceiling_ladder) - 1


def test_the_novelty_dimensions_come_from_the_assessment_schema() -> None:
    document = default_registry().document(NOVELTY_SCHEMA)

    assert novelty_dimension_vocabulary() == tuple(
        document["properties"]["novelty_dimensions"]["items"]["enum"]
    )
    assert "MECHANISM" in novelty_dimension_vocabulary()


def test_an_out_of_range_enum_position_is_refused() -> None:
    with pytest.raises(CorpusBoundaryError) as caught:
        scalar_enum_field(NOVELTY_SCHEMA, 99)

    assert caught.value.code == "INPUT_INVALID"


def test_the_emitted_records_validate_against_their_canonical_schemas() -> None:
    pinned = snapshot()
    reports = boundaries_module.build_snapshot_integrity_reports(
        pinned,
        observed_content_hashes=observed_hashes(),
        evaluated_at=EVALUATED_AT,
        policy_version=POLICY_VERSION,
    )

    for report in reports:
        validate_artifact("source-integrity-report", report)
    validate_artifact("holdout-manifest", holdout(pinned))
    validate_artifact(
        NOVELTY_SCHEMA,
        boundaries_module.assess_novelty_within_boundary(**assessment_arguments()),
    )


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 21
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert code.replace("_", "").isalpha(), code
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = CorpusBoundaryError("PARTITION_LEAKAGE", "message", {"a": 1})

    assert error.code == "PARTITION_LEAKAGE"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(CorpusBoundaryError) as caught:
        boundaries_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}


def test_the_boundaries_hold_no_canonical_enum_literal_at_all() -> None:
    # The package-scoped form of EF4-I22. The repository gate says the same
    # thing for every module; running it here means a K05 regression is
    # attributed to K05 rather than surfacing as a repository-wide failure.
    held = sorted(string_literals(BOUNDARIES) & canonical_enum_values())

    assert held == [], held
