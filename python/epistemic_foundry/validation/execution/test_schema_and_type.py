"""schema_and_type_check — every vocabulary comes from a canonical schema.

This component makes decisions about approval, status, capture completeness and
metered usage.  Each of those decisions is only as good as the vocabulary it
runs against, so none of them are restated here: the intent field set, the risk
ladder, the principal types, the effect statuses, the artifact check statuses,
the metered resource dimensions and the reproducibility contract fields all come
from ``schemas/`` at call time.

The three local decision tables that do exist — observation to status, exit-code
coherence, and channel partitioning — are asserted key-for-key against the
vocabulary that declares their keys, so a schema edit breaks this component
loudly instead of leaving a rule that quietly governs nothing.  A root with no
schemas at all fails closed rather than falling through to a permissive default.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from .contracts import (
    ACTION_INTENT_SCHEMA_PATH,
    APPROVAL_REQUIRED_RISK_CLASSES,
    ARTIFACT_CLASSES,
    ARTIFACT_SCHEMA_PATH,
    AUTHORIZATION_CRITERIA,
    BUDGET_SCHEMA_PATH,
    CAPTURE_CHANNELS,
    CHANNEL_CLASS,
    CRITERION_DENIALS,
    DENIAL_CODES,
    EFFECT_SCHEMA_PATH,
    EXECUTION_GATE_LADDER,
    EXIT_CODE_RULE,
    FENCEABLE_PRINCIPAL_TYPES,
    LEASE_SCHEMA_PATH,
    OBSERVATION_STATUS,
    TARGET_SCHEMA_PATH,
    UNRESOLVED_STATUS,
    ValidationExecutionError,
    actor_types,
    approval_required_risk_classes,
    artifact_receipt_fields,
    authorize_execution,
    build_action_intent,
    capture_channels,
    check_statuses,
    digest,
    effect_receipt_fields,
    effect_statuses,
    fenceable_principal_types,
    intent_fields,
    lease_fields,
    network_policies,
    observation_statuses,
    principal_types,
    reproducibility_fields,
    resource_dimensions,
    risk_classes,
    schema_errors,
    seal_run_environment,
    sha256_pattern,
)
from .fixtures import (
    ROOT,
    action_intent,
    authorization_arguments,
    channel_receipt,
    environment_arguments,
    intent_arguments,
    receipt_arguments,
)
from .contracts import build_effect_receipt

SCHEMAS = (
    ACTION_INTENT_SCHEMA_PATH,
    ARTIFACT_SCHEMA_PATH,
    BUDGET_SCHEMA_PATH,
    EFFECT_SCHEMA_PATH,
    LEASE_SCHEMA_PATH,
    TARGET_SCHEMA_PATH,
)


def canonical(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def mirrored(tmp_path: Path) -> Path:
    (tmp_path / "schemas").mkdir()
    for relative in SCHEMAS:
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    return tmp_path


def rewrite(root: Path, relative: str, document: dict) -> None:
    (root / relative).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_field_sets_are_exactly_what_the_schemas_require() -> None:
    assert intent_fields(ROOT) == frozenset(
        canonical(ACTION_INTENT_SCHEMA_PATH)["required"]
    )
    assert lease_fields(ROOT) == frozenset(canonical(LEASE_SCHEMA_PATH)["required"])
    assert effect_receipt_fields(ROOT) == frozenset(
        canonical(EFFECT_SCHEMA_PATH)["required"]
    )
    assert artifact_receipt_fields(ROOT) == frozenset(
        canonical(ARTIFACT_SCHEMA_PATH)["required"]
    )


def test_enumerations_are_read_and_not_restated() -> None:
    intent_schema = canonical(ACTION_INTENT_SCHEMA_PATH)
    assert risk_classes(ROOT) == tuple(
        intent_schema["properties"]["risk_class"]["enum"]
    )
    lease_schema = canonical(LEASE_SCHEMA_PATH)
    assert principal_types(ROOT) == tuple(
        lease_schema["properties"]["principal_type"]["enum"]
    )
    effect_schema = canonical(EFFECT_SCHEMA_PATH)
    assert effect_statuses(ROOT) == tuple(effect_schema["properties"]["status"]["enum"])
    artifact_schema = canonical(ARTIFACT_SCHEMA_PATH)
    assert check_statuses(ROOT) == tuple(
        artifact_schema["properties"]["validation_results"]["items"]["properties"][
            "status"
        ]["enum"]
    )
    assert actor_types(ROOT) == tuple(
        artifact_schema["properties"]["created_by"]["properties"]["actor_type"]["enum"]
    )
    assert network_policies(ROOT) == tuple(
        canonical(TARGET_SCHEMA_PATH)["properties"]["network_policy"]["enum"]
    )


def test_metered_dimensions_come_from_the_budget_envelope() -> None:
    declared = canonical(BUDGET_SCHEMA_PATH)["properties"]["hard_limits"]["required"]
    assert resource_dimensions(ROOT) == tuple(sorted(declared))


def test_reproducibility_fields_come_from_the_target_manifest() -> None:
    declared = canonical(TARGET_SCHEMA_PATH)["properties"]["reproducibility_contract"][
        "required"
    ]
    assert reproducibility_fields(ROOT) == frozenset(declared)


def test_the_risk_ladder_is_ordered_weakest_first() -> None:
    assert risk_classes(ROOT) == (
        "read_only",
        "bounded_compute",
        "controlled_effect",
        "high_risk",
    )
    assert approval_required_risk_classes(ROOT) == tuple(
        sorted(APPROVAL_REQUIRED_RISK_CLASSES)
    )
    assert set(APPROVAL_REQUIRED_RISK_CLASSES) == set(risk_classes(ROOT)[-2:])


def test_a_human_principal_is_the_one_the_fencing_rule_screens_out() -> None:
    assert fenceable_principal_types(ROOT) == tuple(sorted(FENCEABLE_PRINCIPAL_TYPES))
    assert set(principal_types(ROOT)) - set(FENCEABLE_PRINCIPAL_TYPES) == {"human"}


def test_observation_table_covers_the_status_enum_exactly() -> None:
    table = observation_statuses(ROOT)
    assert set(table.values()) == set(effect_statuses(ROOT))
    assert set(EXIT_CODE_RULE) == set(OBSERVATION_STATUS)
    assert UNRESOLVED_STATUS in effect_statuses(ROOT)
    assert set(EXIT_CODE_RULE.values()) <= {"absent", "any", "nonzero", "zero"}


def test_capture_channel_partition_covers_every_channel() -> None:
    assert capture_channels(ROOT) == tuple(sorted(CAPTURE_CHANNELS))
    assert set(CHANNEL_CLASS) == set(CAPTURE_CHANNELS)
    assert set(CHANNEL_CLASS.values()) <= set(ARTIFACT_CLASSES)


def test_every_authorization_criterion_maps_to_declared_denials() -> None:
    assert set(CRITERION_DENIALS) == set(AUTHORIZATION_CRITERIA)
    declared = {code for codes in CRITERION_DENIALS.values() for code in codes}
    assert declared == set(DENIAL_CODES)


def test_the_gate_ladder_is_closed_and_ordered() -> None:
    assert EXECUTION_GATE_LADDER == ("PASS", "FAILED_RUN", "INCIDENT", "DENIED")
    assert len(set(EXECUTION_GATE_LADDER)) == len(EXECUTION_GATE_LADDER)


def test_the_sha256_pattern_comes_from_the_intent_schema() -> None:
    pattern = sha256_pattern(ROOT)
    declared = canonical(ACTION_INTENT_SCHEMA_PATH)["properties"]["intent_hash"][
        "pattern"
    ]
    assert pattern.pattern == declared
    assert pattern.fullmatch(digest({"a": 1})) is not None


def test_every_built_document_validates_against_its_canonical_schema() -> None:
    assert schema_errors(ROOT, ACTION_INTENT_SCHEMA_PATH, action_intent()) == []
    assert schema_errors(ROOT, ARTIFACT_SCHEMA_PATH, channel_receipt("stdout")) == []
    assert (
        schema_errors(
            ROOT, EFFECT_SCHEMA_PATH, build_effect_receipt(ROOT, **receipt_arguments())
        )
        == []
    )


def test_an_unreadable_schema_root_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationExecutionError) as error:
        build_action_intent(tmp_path, **intent_arguments())

    assert error.value.code == "SCHEMA_UNREADABLE"


def test_an_authorization_against_an_empty_root_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationExecutionError) as error:
        authorize_execution(tmp_path, **authorization_arguments())

    assert error.value.code == "SCHEMA_UNREADABLE"


def test_a_schema_that_drops_a_metered_dimension_is_visible(tmp_path: Path) -> None:
    root = mirrored(tmp_path)
    budget = canonical(BUDGET_SCHEMA_PATH)
    budget["properties"]["hard_limits"]["required"].remove("tokens")
    rewrite(root, BUDGET_SCHEMA_PATH, budget)

    assert "tokens" not in resource_dimensions(root)
    assert "tokens" in resource_dimensions(ROOT)


def test_a_status_enum_the_table_no_longer_covers_is_drift(tmp_path: Path) -> None:
    root = mirrored(tmp_path)
    effect = canonical(EFFECT_SCHEMA_PATH)
    effect["properties"]["status"]["enum"].append("PARTIALLY_APPLIED")
    rewrite(root, EFFECT_SCHEMA_PATH, effect)

    with pytest.raises(ValidationExecutionError) as error:
        observation_statuses(root)

    assert error.value.code == "VOCABULARY_DRIFT"
    assert error.value.context["missing"] == ["PARTIALLY_APPLIED"]


def test_a_risk_enum_without_the_approval_row_is_drift(tmp_path: Path) -> None:
    root = mirrored(tmp_path)
    intent = canonical(ACTION_INTENT_SCHEMA_PATH)
    intent["properties"]["risk_class"]["enum"] = ["read_only", "bounded_compute"]
    rewrite(root, ACTION_INTENT_SCHEMA_PATH, intent)

    with pytest.raises(ValidationExecutionError) as error:
        approval_required_risk_classes(root)

    assert error.value.code == "VOCABULARY_DRIFT"


def test_a_principal_enum_with_nothing_unfenceable_is_drift(tmp_path: Path) -> None:
    root = mirrored(tmp_path)
    lease = canonical(LEASE_SCHEMA_PATH)
    lease["properties"]["principal_type"]["enum"] = list(FENCEABLE_PRINCIPAL_TYPES)
    rewrite(root, LEASE_SCHEMA_PATH, lease)

    with pytest.raises(ValidationExecutionError) as error:
        fenceable_principal_types(root)

    assert error.value.code == "VOCABULARY_DRIFT"


def test_a_reproducibility_contract_field_the_schema_dropped_is_refused(
    tmp_path: Path,
) -> None:
    root = mirrored(tmp_path)
    target = canonical(TARGET_SCHEMA_PATH)
    target["properties"]["reproducibility_contract"]["required"].remove("seed_control")
    rewrite(root, TARGET_SCHEMA_PATH, target)

    with pytest.raises(ValidationExecutionError) as error:
        seal_run_environment(root, **environment_arguments())

    assert error.value.code == "FIELD_SET_INVALID"
    assert error.value.context["unknown"] == ["seed_control"]
