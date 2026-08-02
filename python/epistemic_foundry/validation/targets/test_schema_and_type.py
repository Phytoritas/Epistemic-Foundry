"""schema_and_type_check — the screen reads its vocabulary, never invents it.

Every value this component decides against is declared somewhere in
``schemas/``: the target types, the safety-class ladder, the approval-policy
ladder, the data classes, the port field set, the reproducibility contract
fields, the canonical ``sha256`` pattern and the scope axes.  The two ladders
are pinned here in their exact declared order, because the eligibility rule
takes the *last* safety class and the policy that gates *nothing* — a schema
that reordered either enum would silently move the rule, and this suite is
where that has to fail.

The local decision tables are checked against the schema that declares their
keys, and the finding vocabulary is checked for the thing that makes a refusal
usable: a reason a reader can act on rather than a bare code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .contracts import (
    APPROVAL_COVERAGE,
    CONTAINER_FIELD,
    CRITERION_FINDING,
    ELIGIBILITY_CRITERIA,
    ENVIRONMENT_FIELD,
    EXECUTED_TARGET_TYPES,
    FINDING_CODES,
    SCOPE_SCHEMA_PATH,
    SEED_FIELD,
    STOCHASTIC_TARGET_TYPES,
    TARGET_SCHEMA_PATH,
    ValidationTargetError,
    approval_coverage,
    approval_policies,
    data_classes,
    empty_scope_vector,
    highest_safety_class,
    manifest_validator,
    network_policies,
    port_fields,
    reproducibility_fields,
    reproducibility_requirements,
    safety_classes,
    scope_axes,
    screen_target,
    sha256_pattern,
    target_manifest_fields,
    target_types,
    unapproved_approval_policy,
)

ROOT = Path(__file__).resolve().parents[4]
MINIMUM_REASON_LENGTH = 50


def schema(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_the_safety_class_ladder_is_declared_weakest_first() -> None:
    ladder = safety_classes(ROOT)

    assert ladder == (
        "read_only",
        "bounded_compute",
        "controlled_effect",
        "high_risk",
    )
    assert highest_safety_class(ROOT) == ladder[-1]


def test_the_approval_policy_ladder_is_declared_weakest_first() -> None:
    ladder = approval_policies(ROOT)

    assert ladder == ("none", "high_risk_only", "all_effects")
    assert unapproved_approval_policy(ROOT) == ladder[0]


def test_the_target_types_come_from_the_declaring_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)

    assert target_types(ROOT) == tuple(document["properties"]["target_type"]["enum"])
    assert len(target_types(ROOT)) == 7


def test_the_network_policies_and_data_classes_come_from_the_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)

    assert network_policies(ROOT) == tuple(
        document["properties"]["network_policy"]["enum"]
    )
    assert data_classes(ROOT) == tuple(
        document["properties"]["allowed_data_classes"]["items"]["enum"]
    )


def test_the_manifest_field_set_comes_from_the_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)

    assert target_manifest_fields(ROOT) == frozenset(document["required"])
    assert len(target_manifest_fields(ROOT)) == 23


def test_the_port_field_set_comes_from_the_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)

    assert port_fields(ROOT) == frozenset(document["$defs"]["port"]["required"])


def test_the_reproducibility_fields_come_from_the_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)
    declared = document["properties"]["reproducibility_contract"]["required"]

    assert reproducibility_fields(ROOT) == frozenset(declared)
    assert {CONTAINER_FIELD, ENVIRONMENT_FIELD, SEED_FIELD} == set(declared)


def test_the_scope_axes_come_from_the_scope_schema() -> None:
    document = schema(SCOPE_SCHEMA_PATH)

    assert scope_axes(ROOT) == tuple(sorted(document["required"]))
    assert len(scope_axes(ROOT)) == 20


def test_the_empty_scope_vector_covers_every_declared_axis() -> None:
    scope = empty_scope_vector(ROOT)

    assert set(scope) == set(scope_axes(ROOT))
    assert manifest_validator(ROOT) is not None


def test_the_sha256_pattern_comes_from_the_schema() -> None:
    document = schema(TARGET_SCHEMA_PATH)
    pattern = sha256_pattern(ROOT)

    assert pattern.pattern == document["$defs"]["sha256"]["pattern"]
    assert pattern.fullmatch("sha256:" + "a" * 64) is not None
    assert pattern.fullmatch("sha256:" + "A" * 64) is None


def test_the_approval_coverage_table_covers_every_declared_policy() -> None:
    coverage = approval_coverage(ROOT)

    assert set(coverage) == set(approval_policies(ROOT))
    assert set(APPROVAL_COVERAGE) == set(approval_policies(ROOT))
    for gated in coverage.values():
        assert set(gated) <= set(safety_classes(ROOT))


def test_the_reproducibility_table_covers_every_declared_target_type() -> None:
    table = reproducibility_requirements(ROOT)

    assert set(table) == set(target_types(ROOT))
    for required in table.values():
        assert set(required) <= reproducibility_fields(ROOT)
        assert ENVIRONMENT_FIELD in required


def test_a_simulation_model_must_control_its_seed() -> None:
    table = reproducibility_requirements(ROOT)

    assert SEED_FIELD in table["simulation_model"]
    assert set(EXECUTED_TARGET_TYPES) <= set(target_types(ROOT))
    assert set(STOCHASTIC_TARGET_TYPES) <= set(EXECUTED_TARGET_TYPES)


def test_an_observed_target_type_is_not_forced_to_pin_an_image() -> None:
    table = reproducibility_requirements(ROOT)

    assert CONTAINER_FIELD not in table["external_service"]
    assert SEED_FIELD not in table["analysis_pipeline"]


def test_every_finding_code_carries_an_actionable_reason() -> None:
    short = {
        code: reason
        for code, reason in FINDING_CODES.items()
        if len(reason) <= MINIMUM_REASON_LENGTH
    }

    assert short == {}
    assert sorted(FINDING_CODES) == list(FINDING_CODES)


def test_every_criterion_maps_to_a_declared_finding_code() -> None:
    assert set(CRITERION_FINDING) == set(ELIGIBILITY_CRITERIA)
    assert set(CRITERION_FINDING.values()) <= set(FINDING_CODES)


def test_an_unreadable_schema_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationTargetError) as error:
        screen_target(tmp_path, {})

    assert error.value.code == "SCHEMA_UNREADABLE"
