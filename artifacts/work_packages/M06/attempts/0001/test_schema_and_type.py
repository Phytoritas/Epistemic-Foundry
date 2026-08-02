"""schema_and_type_check — the gate reads its vocabulary, never restates it.

Everything this gate compares belongs to somebody else: the archive entry shape
to the canonical schema, the map figures to the records M05 and the archive
builder publish, and the authority artifacts to the canonical registry.  So the
checks here are about ownership rather than behaviour — a figure name that no
record publishes, an authority schema the registry has dropped, or a canonical
enum value copied into the gate's source would each leave a check that looks
like it guards something and does not.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from epistemic_foundry.cartography.v4_m05 import CartographyError
from epistemic_foundry.cartography.v4_m06 import (
    AUTHORITY_SCHEMA_NAMES,
    DERIVATION_FIELDS,
    DERIVED_RECORD_FIELDS,
    EXTERNAL_RANKING_FIGURE,
    FINDING_CODES,
    RANKING_FIGURE_NAMES,
    CartographyIntegrationError,
    audit_promotion_request,
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    build_staleness_cascade,
)
from epistemic_foundry.cartography.v4_m06 import gate as gate_module
from epistemic_foundry.contracts import default_registry
from fixtures import (
    RUN_ID,
    authority_citation,
    board,
    coverage,
    derived,
    diversity,
    entries,
    figure_citation,
    promotion_request,
    radius,
    revision,
)

GATE = Path(gate_module.__file__)


def test_every_finding_code_explains_why_it_exists() -> None:
    """A code without a reason is an error message nobody can act on."""
    for code, reason in FINDING_CODES.items():
        assert code == code.upper(), code
        assert len(reason) > 50, (code, len(reason))


def test_the_finding_codes_are_the_only_codes_the_gate_can_raise() -> None:
    with pytest.raises(CartographyIntegrationError) as caught:
        gate_module._fail("NOT_A_DECLARED_CODE", "should never be raised")

    assert caught.value.code == "INPUT_INVALID"


def test_the_integration_refusal_is_a_cartographic_refusal() -> None:
    """A caller already handling M05's refusal must not miss M06's."""
    assert issubclass(CartographyIntegrationError, CartographyError)
    error = CartographyIntegrationError("INPUT_INVALID", "message", {"key": "value"})
    assert error.code == "INPUT_INVALID"
    assert error.context == {"key": "value"}


def test_every_authority_schema_is_declared_by_the_canonical_registry() -> None:
    known = set(default_registry().names())

    assert set(AUTHORITY_SCHEMA_NAMES) <= known
    assert AUTHORITY_SCHEMA_NAMES == tuple(sorted(AUTHORITY_SCHEMA_NAMES))


def test_every_ranking_figure_is_published_by_a_map_record() -> None:
    """Except the combined score, which no map record publishes by design."""
    published = set(coverage(board())) | set(diversity())
    checked = set(RANKING_FIGURE_NAMES) - {EXTERNAL_RANKING_FIGURE}

    assert checked <= published, sorted(checked - published)
    assert EXTERNAL_RANKING_FIGURE not in published


def test_every_derived_record_kind_publishes_the_fields_it_is_tracked_by() -> None:
    surface = board()
    source = revision(surface)
    records = {
        "blast_radius": radius(surface),
        "coverage_map": coverage(surface),
        "lineage_diversity_report": diversity(),
    }

    assert set(records) == set(DERIVED_RECORD_FIELDS)
    for kind, record in records.items():
        hash_field, id_field = DERIVED_RECORD_FIELDS[kind]
        assert hash_field in record and id_field in record
        binding = bind_derived_record(record=record, record_kind=kind, revision=source)
        assert set(binding) == set(DERIVATION_FIELDS)


def _schema_enum_values() -> set[str]:
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("enum"), list):
                values.update(item for item in node["enum"] if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    registry = default_registry()
    for name in registry.names():
        walk(registry.document(name))
    return values


def _literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_the_package_holds_no_canonical_enum_vocabulary() -> None:
    """EF4-I22 locally: no module here names a schema enum value as a literal.

    The repository-wide invariant runs as its own check across every shipped
    module.  This asserts it over the two files this package adds, so a
    violation introduced here is attributed here — and stays provable while the
    repository gate is red for a module belonging to somebody else.
    """
    enum_values = _schema_enum_values()
    # Generic English that happens to be an enum value somewhere is not a wire
    # literal; the repository gate applies the same exclusion.
    generic = {"none", "other", "all", "any", "unknown", "read", "write", "scope"}
    held = {
        path.name: sorted((_literals(path) & enum_values) - generic)
        for path in sorted(GATE.parent.glob("*.py"))
    }

    assert not any(held.values()), held
    assert set(held) == {"__init__.py", "gate.py"}


def test_the_archive_entries_are_validated_against_the_canonical_schema() -> None:
    surface = board()
    rows = entries(surface)
    rows[0] = {key: value for key, value in rows[0].items() if key != "niche_id"}

    with pytest.raises(Exception) as caught:
        build_map_agreement_record(niche_map=surface, archive_entries=rows)

    assert "niche_id" in str(caught.value)


def test_every_published_record_is_serialisable_evidence() -> None:
    surface = board()
    source = revision(surface)
    coverage_map = coverage(surface)
    report = diversity()
    records = [
        build_map_agreement_record(
            niche_map=surface, archive_entries=entries(surface), record_id="MAR-S"
        ),
        build_map_revision(
            niche_map=surface,
            evolution_run_id=RUN_ID,
            generation=3,
            revision_id="MRV-S",
        ),
        build_staleness_cascade(
            revision=source,
            serving_generation=4,
            derived_records=derived(surface, source),
            cascade_id="MSC-S",
        ),
        audit_promotion_request(
            request=promotion_request(
                [
                    authority_citation(),
                    figure_citation(
                        coverage_map["map_id"],
                        "coverage_ratio",
                        coverage_map["coverage_ratio"],
                    ),
                ]
            ),
            coverage_map=coverage_map,
            diversity_report=report,
            record_id="RSR-S",
        ),
    ]

    for record in records:
        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True)) == (
            record
        )
