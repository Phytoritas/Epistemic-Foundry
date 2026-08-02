"""schema_and_type_check — the map reads its vocabulary, never restates it.

The niche axes come from the canonical niche schema, coverage summaries from
the sealed archive builder, and every emitted record validates against the
schema that governs it.  The mapper source is scanned for canonical enum
values because EF4-I22 is what stops a second copy of a wire vocabulary from
drifting.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from epistemic_foundry.cartography.v4_m05 import (
    CartographyError,
    FINDING_CODES,
    INBREEDING_RULES,
    NicheMap,
    axis_vocabulary,
    build_coverage_map,
    build_lineage_diversity_report,
    canonical_axis_values,
    niche_id_for,
)
from epistemic_foundry.cartography.v4_m05 import mapper as mapper_module
from epistemic_foundry.contracts import default_registry, validate_artifact
from fixtures import RUN_ID, THRESHOLDS, coordinates, models, niche, population

ROOT = Path(__file__).resolve().parents[5]
MAPPER = ROOT / "src/epistemic_foundry/cartography/v4_m05/mapper.py"


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


def test_the_axis_vocabulary_comes_from_the_declaring_schema() -> None:
    document = default_registry().document("epistemic-niche")

    assert axis_vocabulary() == tuple(document["properties"]["axis_values"]["required"])
    assert len(axis_vocabulary()) == 5


def test_a_built_niche_validates_against_the_canonical_schema() -> None:
    record = niche("hormonal", ["C1"], elite_id="C1")

    validate_artifact("epistemic-niche", record)
    assert set(record["axis_values"]) == set(axis_vocabulary())


def test_the_niche_id_is_a_pure_function_of_the_coordinates() -> None:
    assert niche_id_for(coordinates("hormonal")) == niche_id_for(
        coordinates("hormonal")
    )
    assert niche_id_for(coordinates("hormonal")) != niche_id_for(
        coordinates("hydraulic")
    )


def test_axis_order_does_not_change_the_identity() -> None:
    forward = coordinates("hormonal")
    reversed_order = dict(reversed(list(forward.items())))

    assert niche_id_for(forward) == niche_id_for(reversed_order)


def test_canonical_axis_values_preserve_the_declared_order() -> None:
    values = canonical_axis_values(dict(reversed(list(coordinates("x").items()))))

    assert tuple(values) == axis_vocabulary()


def test_the_coverage_map_validates_against_its_canonical_schema() -> None:
    board = NicheMap([niche("a", ["C1"]), niche("b", [])])
    record = build_coverage_map(
        niche_map=board,
        evolution_run_id=RUN_ID,
        generation=1,
        lineage_entropy=0.5,
        map_id="QDM-M05-T",
    )

    validate_artifact("quality-diversity-map", record)
    assert record["coverage_ratio"] == 0.5


def test_the_diversity_report_validates_against_its_canonical_schema() -> None:
    memory = population()
    report = build_lineage_diversity_report(
        lineage=memory,
        evolution_run_id=RUN_ID,
        generation=3,
        model_attribution=models(memory),
        thresholds=THRESHOLDS,
        report_id="LDR-M05-T",
    )

    validate_artifact("lineage-diversity-report", report)


def test_the_mapper_holds_no_archive_entry_class_literal() -> None:
    document = default_registry().document("epistemic-archive-entry")
    held = string_literals(MAPPER) & set(document["properties"]["entry_class"]["enum"])

    assert held == set(), held


def test_the_mapper_holds_no_stop_reason_literal() -> None:
    from epistemic_foundry.evolution_chamber.checkpoint import (
        ADVERSE_STOPS,
        ORDERLY_STOPS,
    )

    held = string_literals(MAPPER) & (set(ORDERLY_STOPS) | set(ADVERSE_STOPS))

    assert held == set(), held


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 11
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_every_inbreeding_alert_recommends_a_concrete_action() -> None:
    assert len(INBREEDING_RULES) == 4
    for alert, action in INBREEDING_RULES.items():
        assert alert == alert.upper()
        assert len(action) > 40, alert


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = CartographyError("CELL_DUPLICATED", "message", {"a": 1})

    assert error.code == "CELL_DUPLICATED"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(CartographyError) as caught:
        mapper_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
