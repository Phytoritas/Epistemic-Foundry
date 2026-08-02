from __future__ import annotations

import pytest

from .resolver import (
    CompatibilityStatus,
    ConstructEquivalence,
    MeasurementBridge,
    MeasurementIdentity,
    OntologyContractError,
    PromotionCeiling,
    compare_measurements,
)


def measurement(measurement_id: str, **overrides: object) -> MeasurementIdentity:
    values: dict[str, object] = {
        "measurement_id": measurement_id,
        "construct_id": "construct-retention",
        "method_id": "delayed-recall-test",
        "protocol_version": "protocol-1",
        "unit": "proportion-correct",
        "timing": "P7D",
        "calibration_ref": "CAL-1",
        "population_or_entity": "adult-learners",
        "unit_of_analysis": "participant",
        "ontology_version": "ontology-2026-07",
        "domain_pack_id": "learning_science",
        "domain_pack_version": "1.2.3",
        "proxy_for_construct_id": None,
    }
    values.update(overrides)
    return MeasurementIdentity(**values)  # type: ignore[arg-type]


def bridge(
    left: MeasurementIdentity,
    right: MeasurementIdentity,
    **overrides: object,
) -> MeasurementBridge:
    values: dict[str, object] = {
        "bridge_id": "BRIDGE-1",
        "left_identity_hash": left.semantic_identity_hash,
        "right_identity_hash": right.semantic_identity_hash,
        "compatibility_status": CompatibilityStatus.CONVERTIBLE,
        "construct_equivalence": ConstructEquivalence.SAME,
        "required_transformations": ("percent_to_proportion:v1",),
        "method_threats": ("conversion_rounding",),
        "promotion_ceiling": PromotionCeiling.CONDITIONAL_ONLY,
        "authority_ref": "DOMAINPACK-BRIDGE-1",
    }
    values.update(overrides)
    return MeasurementBridge(**values)  # type: ignore[arg-type]


def test_measurement_identity_test_complete_identical_semantics_are_direct() -> None:
    result = compare_measurements(measurement("M-1"), measurement("M-2"))

    assert result.compatibility_status is CompatibilityStatus.DIRECTLY_COMPARABLE
    assert result.construct_equivalence is ConstructEquivalence.SAME
    assert result.promotion_ceiling is PromotionCeiling.NO_RESTRICTION
    assert result.aggregation_allowed is True
    assert result.bridge_id is None


def test_measurement_identity_test_same_id_with_different_semantics_fails_closed() -> None:
    with pytest.raises(OntologyContractError) as raised:
        compare_measurements(
            measurement("M-1"),
            measurement("M-1", method_id="self-report"),
        )

    assert raised.value.code == "MEASUREMENT_IDENTITY_CONFLICT"


def test_measurement_identity_test_distinct_construct_ids_are_not_pooled() -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", construct_id="construct-satisfaction"),
    )

    assert result.compatibility_status is CompatibilityStatus.NOT_COMPARABLE
    assert result.construct_equivalence is ConstructEquivalence.DIFFERENT
    assert result.promotion_ceiling is PromotionCeiling.BLOCK_AGGREGATION
    assert result.aggregation_allowed is False


def test_measurement_identity_test_different_methods_are_stratified() -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", method_id="self-report-scale"),
    )

    assert result.compatibility_status is CompatibilityStatus.WITHIN_METHOD_ONLY
    assert result.promotion_ceiling is PromotionCeiling.METHOD_BOUNDARY_ONLY
    assert result.method_threats == ("METHOD_MISMATCH",)
    assert result.aggregation_allowed is False


def test_measurement_identity_test_unit_difference_requires_explicit_bridge() -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", unit="percent-correct"),
    )

    assert result.compatibility_status is CompatibilityStatus.NOT_COMPARABLE
    assert result.method_threats == ("UNIT_MISMATCH_WITHOUT_BRIDGE",)
    assert result.promotion_ceiling is PromotionCeiling.BLOCK_AGGREGATION


def test_measurement_identity_test_missing_method_context_is_unknown() -> None:
    result = compare_measurements(
        measurement("M-1", calibration_ref=None),
        measurement("M-2", calibration_ref=None),
    )

    assert result.compatibility_status is CompatibilityStatus.UNKNOWN
    assert result.construct_equivalence is ConstructEquivalence.SAME
    assert result.method_threats == ("MISSING_CALIBRATION_REF",)
    assert result.aggregation_allowed is False


def test_measurement_identity_test_explicit_directional_bridge_allows_conversion() -> None:
    left = measurement("M-1")
    right = measurement("M-2", unit="percent-correct")
    declared = bridge(left, right)

    result = compare_measurements(left, right, bridges=(declared,))

    assert result.compatibility_status is CompatibilityStatus.CONVERTIBLE
    assert result.required_transformations == ("percent_to_proportion:v1",)
    assert result.promotion_ceiling is PromotionCeiling.CONDITIONAL_ONLY
    assert result.bridge_id == "BRIDGE-1"
    assert result.aggregation_allowed is True


def test_measurement_identity_test_bridge_is_not_silently_reversed() -> None:
    left = measurement("M-1")
    right = measurement("M-2", unit="percent-correct")

    result = compare_measurements(right, left, bridges=(bridge(left, right),))

    assert result.compatibility_status is CompatibilityStatus.NOT_COMPARABLE
    assert result.bridge_id is None


def test_measurement_identity_test_partial_bridge_cannot_remove_ceiling() -> None:
    left = measurement("M-1")
    right = measurement("M-2", construct_id="construct-performance-proxy")

    with pytest.raises(OntologyContractError) as raised:
        bridge(
            left,
            right,
            compatibility_status=CompatibilityStatus.DIRECTLY_COMPARABLE,
            construct_equivalence=ConstructEquivalence.PARTIAL,
            required_transformations=(),
            promotion_ceiling=PromotionCeiling.NO_RESTRICTION,
        )

    assert raised.value.code == "MEASUREMENT_BRIDGE_INVALID"


def test_measurement_identity_test_partial_convertible_bridge_does_not_pool() -> None:
    left = measurement("M-1")
    right = measurement("M-2", construct_id="construct-performance-proxy")
    declared = bridge(
        left,
        right,
        construct_equivalence=ConstructEquivalence.PARTIAL,
        promotion_ceiling=PromotionCeiling.CONDITIONAL_ONLY,
    )

    result = compare_measurements(left, right, bridges=(declared,))

    assert result.compatibility_status is CompatibilityStatus.CONVERTIBLE
    assert result.construct_equivalence is ConstructEquivalence.PARTIAL
    assert result.aggregation_allowed is False
    assert result.promotion_ceiling is PromotionCeiling.CONDITIONAL_ONLY


@pytest.mark.parametrize(
    "ceiling",
    [
        PromotionCeiling.METHOD_BOUNDARY_ONLY,
        PromotionCeiling.BLOCK_AGGREGATION,
    ],
)
def test_measurement_identity_test_bridge_ceiling_blocks_pooling(
    ceiling: PromotionCeiling,
) -> None:
    left = measurement("M-1")
    right = measurement("M-2", unit="percent-correct")
    declared = bridge(left, right, promotion_ceiling=ceiling)

    result = compare_measurements(left, right, bridges=(declared,))

    assert result.compatibility_status is CompatibilityStatus.CONVERTIBLE
    assert result.construct_equivalence is ConstructEquivalence.SAME
    assert result.promotion_ceiling is ceiling
    assert result.aggregation_allowed is False


def test_measurement_identity_test_convertible_bridge_requires_transformation() -> None:
    left = measurement("M-1")
    right = measurement("M-2", unit="percent-correct")

    with pytest.raises(OntologyContractError) as raised:
        bridge(left, right, required_transformations=())

    assert raised.value.code == "MEASUREMENT_BRIDGE_INVALID"


def test_measurement_identity_test_duplicate_matching_bridges_fail_closed() -> None:
    left = measurement("M-1")
    right = measurement("M-2", unit="percent-correct")
    first = bridge(left, right, bridge_id="BRIDGE-1")
    second = bridge(left, right, bridge_id="BRIDGE-2")

    with pytest.raises(OntologyContractError) as raised:
        compare_measurements(left, right, bridges=(first, second))

    assert raised.value.code == "MEASUREMENT_BRIDGE_AMBIGUOUS"


def test_measurement_identity_test_domain_pack_mismatch_is_unknown_without_bridge() -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", domain_pack_version="2.0.0"),
    )

    assert result.compatibility_status is CompatibilityStatus.UNKNOWN
    assert result.construct_equivalence is ConstructEquivalence.UNKNOWN
    assert result.method_threats == ("ONTOLOGY_OR_DOMAIN_PACK_MISMATCH",)


@pytest.mark.parametrize(
    ("field", "value", "threat"),
    [
        ("population_or_entity", "children", "POPULATION_OR_ENTITY_MISMATCH"),
        ("unit_of_analysis", "classroom", "UNIT_OF_ANALYSIS_MISMATCH"),
        ("timing", "P30D", "TEMPORAL_SUPPORT_MISMATCH"),
    ],
)
def test_measurement_identity_test_scope_or_support_mismatch_blocks_aggregation(
    field: str,
    value: str,
    threat: str,
) -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", **{field: value}),
    )

    assert result.compatibility_status is CompatibilityStatus.NOT_COMPARABLE
    assert result.method_threats == (threat,)
    assert result.aggregation_allowed is False


def test_measurement_identity_test_protocol_and_calibration_changes_stay_method_bound() -> None:
    result = compare_measurements(
        measurement("M-1"),
        measurement("M-2", protocol_version="protocol-2", calibration_ref="CAL-2"),
    )

    assert result.compatibility_status is CompatibilityStatus.WITHIN_METHOD_ONLY
    assert result.method_threats == (
        "CALIBRATION_MISMATCH",
        "PROTOCOL_VERSION_MISMATCH",
    )
    assert result.promotion_ceiling is PromotionCeiling.METHOD_BOUNDARY_ONLY


def test_measurement_identity_test_proxy_identity_retains_promotion_ceiling() -> None:
    result = compare_measurements(
        measurement("M-1", proxy_for_construct_id="latent-retention"),
        measurement("M-2", proxy_for_construct_id="latent-retention"),
    )

    assert result.compatibility_status is CompatibilityStatus.DIRECTLY_COMPARABLE
    assert result.construct_equivalence is ConstructEquivalence.SAME
    assert result.promotion_ceiling is PromotionCeiling.CONDITIONAL_ONLY
    assert result.method_threats == ("PROXY_DEFINED_OUTCOME_ONLY",)


def test_measurement_identity_test_distinct_proxy_targets_are_not_merged() -> None:
    result = compare_measurements(
        measurement("M-1", proxy_for_construct_id="latent-retention"),
        measurement("M-2", proxy_for_construct_id="latent-engagement"),
    )

    assert result.compatibility_status is CompatibilityStatus.NOT_COMPARABLE
    assert result.construct_equivalence is ConstructEquivalence.PARTIAL
    assert result.method_threats == ("PROXY_RELATION_MISMATCH",)


def test_measurement_identity_test_semantic_hash_excludes_record_identifier() -> None:
    left = measurement("M-1")
    right = measurement("M-2")

    assert left.semantic_identity_hash == right.semantic_identity_hash
    assert left.measurement_id != right.measurement_id


def test_measurement_identity_test_mutable_bridge_collection_is_rejected() -> None:
    with pytest.raises(OntologyContractError) as raised:
        compare_measurements(  # type: ignore[arg-type]
            measurement("M-1"),
            measurement("M-2"),
            bridges=[],
        )

    assert raised.value.code == "MEASUREMENT_INPUT_INVALID"
