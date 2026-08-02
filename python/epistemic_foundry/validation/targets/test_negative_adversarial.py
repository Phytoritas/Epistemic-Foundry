"""negative_and_adversarial_tests — every route past the door is tried.

Construction refuses four things outright, and each one is a way a manifest
could describe a target that is not the target that would actually run: an
entrypoint outside the pinned artifact set, two ports claiming one id, a
constraint written against a port nobody declared, and an artifact hash that is
not content-addressable.  Eligibility refuses four more, and each one is a way
a well-formed manifest could still produce a result nobody could bound: the top
safety class with no approval anywhere, a reproducibility contract too weak for
what the type does, no action to take, and a scope vector that is entirely
null.

Each refusal has to fail with the code that stopped it rather than degrade into
a permissive default, and a manifest failing four screens has to report four
findings rather than the first one it hit.
"""

from __future__ import annotations

import pytest

from . import contracts
from .contracts import (
    CRITERION_FINDING,
    FINDING_CODES,
    ValidationTargetError,
    build_eligibility_report,
    empty_scope_vector,
    screen_target,
)
from .fixtures import (
    ARTIFACT_HASH,
    ENTRYPOINT,
    REPORT_ID,
    ROOT,
    SCREENED_AT,
    bounded_scope,
    empty_scope,
    port,
    raw_manifest,
    target_manifest,
)


def refusal(**overrides: object) -> ValidationTargetError:
    with pytest.raises(ValidationTargetError) as error:
        target_manifest(**overrides)
    return error.value


def codes(**overrides: object) -> list[str]:
    return screen_target(ROOT, target_manifest(**overrides))["reason_codes"]


def test_an_entrypoint_outside_the_artifact_set_is_refused() -> None:
    error = refusal(entrypoint="targets/reservoir/not_pinned.py")

    assert error.code == "ENTRYPOINT_UNDECLARED"
    assert error.context["entrypoint"] == "targets/reservoir/not_pinned.py"
    assert ENTRYPOINT in error.context["artifacts"]


def test_a_duplicate_port_id_inside_one_collection_is_refused() -> None:
    error = refusal(
        inputs=[
            port("rainfall_series", "timeseries"),
            port("rainfall_series", "number"),
        ]
    )

    assert error.code == "PORT_ID_DUPLICATED"
    assert error.context["port_id"] == "rainfall_series"
    assert error.context["collections"] == ["inputs"]


def test_a_duplicate_port_id_across_collections_is_refused() -> None:
    error = refusal(outputs=[port("seed", "integer")])

    assert error.code == "PORT_ID_DUPLICATED"
    assert error.context["collections"] == ["outputs", "parameters"]


def test_a_constraint_naming_an_undeclared_port_is_refused() -> None:
    error = refusal(constraints=["{evaporation_rate} >= 0"])

    assert error.code == "CONSTRAINT_UNBOUND"
    assert error.context["unknown"] == ["evaporation_rate"]
    assert error.context["bindable"] == ["reservoir_level", "seed"]


def test_a_constraint_naming_an_output_rather_than_an_input_state_is_refused() -> None:
    error = refusal(constraints=["{storage_estimate} >= 0"])

    assert error.code == "CONSTRAINT_UNBOUND"
    assert error.context["unknown"] == ["storage_estimate"]


def test_a_constraint_naming_nothing_at_all_is_refused() -> None:
    error = refusal(constraints=["the reservoir never overflows"])

    assert error.code == "CONSTRAINT_UNGROUNDED"


@pytest.mark.parametrize(
    "value",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "a" * 64,
        "sha512:" + "a" * 64,
        " sha256:" + "a" * 64,
    ],
)
def test_an_artifact_hash_outside_canonical_sha256_form_is_refused(value: str) -> None:
    error = refusal(artifacts={ENTRYPOINT: value})

    assert error.code == "ARTIFACT_HASH_MALFORMED"
    assert error.context["value"] == value


def test_a_target_declaring_no_artifact_is_refused() -> None:
    assert refusal(artifacts={}).code == "ARTIFACT_SET_EMPTY"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_type", "neural_oracle"),
        ("safety_class", "catastrophic"),
        ("approval_policy", "sometimes"),
        ("network_policy", "open"),
        ("allowed_data_classes", ["secret"]),
    ],
)
def test_a_value_the_schema_does_not_declare_is_refused(
    field: str, value: object
) -> None:
    error = refusal(**{field: value})

    assert error.code == "INPUT_INVALID"


def test_a_port_carrying_an_unknown_field_is_refused() -> None:
    error = refusal(parameters=[{**port("seed", "integer"), "default": 0}])

    assert error.code == "FIELD_SET_INVALID"
    assert error.context["unknown"] == ["default"]


def test_a_target_id_the_schema_pattern_refuses_reaches_the_backstop() -> None:
    # Nothing before the final schema check inspects the id's shape, so this is
    # the path that proves the backstop is load-bearing rather than decorative.
    error = refusal(target_id="VT-Reservoir")

    assert error.code == "MANIFEST_SCHEMA_INVALID"
    assert any("target_id" in message for message in error.context["errors"])


def test_a_scope_value_that_is_not_json_is_refused() -> None:
    error = refusal(validation_scope={**bounded_scope(), "domain": {"a", "b"}})

    assert error.code == "CANONICALIZATION_FAILED"


def test_the_highest_safety_class_may_not_run_unapproved() -> None:
    reasons = codes(safety_class="high_risk", approval_policy="none")

    assert reasons == [CRITERION_FINDING["approval_coherent"]]


@pytest.mark.parametrize("policy", ["high_risk_only", "all_effects"])
def test_the_highest_safety_class_under_a_gating_policy_is_eligible(
    policy: str,
) -> None:
    assert codes(safety_class="high_risk", approval_policy=policy) == []


def test_a_lower_safety_class_without_approval_is_left_to_the_invocation_gate() -> None:
    # V01 screens whether a target may be *planned against*.  Which individual
    # controlled-effect call needs an approval record is T04's decision at
    # invocation time, so this package does not pre-empt it here.
    assert codes(safety_class="controlled_effect", approval_policy="none") == []


def test_a_simulation_model_without_seed_control_is_ineligible() -> None:
    record = screen_target(
        ROOT,
        target_manifest(
            reproducibility_contract={
                "container_digest_required": True,
                "environment_capture": True,
                "seed_control": False,
            }
        ),
    )

    assert record["reason_codes"] == [CRITERION_FINDING["reproducibility_sufficient"]]
    assert record["screen_detail"]["reproducibility_unmet"] == ["seed_control"]


def test_an_observed_target_type_without_seed_control_is_eligible() -> None:
    assert (
        codes(
            target_type="external_service",
            reproducibility_contract={
                "container_digest_required": False,
                "environment_capture": True,
                "seed_control": False,
            },
        )
        == []
    )


def test_a_target_declaring_no_action_is_ineligible() -> None:
    assert codes(supported_actions=[]) == [CRITERION_FINDING["actions_declared"]]


def test_a_fully_null_scope_vector_is_ineligible() -> None:
    record = screen_target(ROOT, target_manifest(validation_scope=empty_scope()))

    assert record["reason_codes"] == [CRITERION_FINDING["scope_bounded"]]
    assert record["eligible"] is False


def test_a_scope_carrying_only_empty_lists_and_objects_is_ineligible() -> None:
    scope = empty_scope_vector(ROOT)
    scope["inclusion_criteria"] = []
    scope["conditions"] = {}

    assert codes(validation_scope=scope) == [CRITERION_FINDING["scope_bounded"]]


def test_a_scope_carrying_one_non_empty_list_axis_is_bounded() -> None:
    scope = empty_scope_vector(ROOT)
    scope["inclusion_criteria"] = ["catchment area above 5 km2"]

    assert codes(validation_scope=scope) == []


def test_a_scope_carrying_only_a_domain_extension_is_bounded() -> None:
    scope = empty_scope_vector(ROOT)
    scope["domain_extensions"] = {"catchment_class": "upland"}

    assert codes(validation_scope=scope) == []


def test_a_target_failing_every_criterion_reports_every_finding() -> None:
    record = screen_target(
        ROOT,
        target_manifest(
            safety_class="high_risk",
            approval_policy="none",
            supported_actions=[],
            validation_scope=empty_scope(),
            reproducibility_contract={
                "container_digest_required": False,
                "environment_capture": False,
                "seed_control": False,
            },
        ),
    )

    assert record["reason_codes"] == sorted(CRITERION_FINDING.values())
    assert record["criteria_satisfied"] == []
    assert set(record["reasons"]) == set(record["reason_codes"])


@pytest.mark.parametrize(
    "document",
    [
        {},
        None,
        "vt-reservoir-sim",
        [1, 2],
        raw_manifest(target_type="neural_oracle"),
        raw_manifest(artifact_hashes=["not-a-hash"]),
        raw_manifest(unexpected="field"),
    ],
)
def test_a_document_the_schema_refuses_is_reported_not_screened(
    document: object,
) -> None:
    record = screen_target(ROOT, document)

    assert record["reason_codes"] == ["MANIFEST_MALFORMED"]
    assert record["criteria_satisfied"] == []
    assert record["screen_detail"]["schema_errors"]


def test_two_manifests_claiming_one_target_id_are_refused() -> None:
    with pytest.raises(ValidationTargetError) as error:
        build_eligibility_report(
            ROOT,
            [target_manifest(), target_manifest(version="9.9.9")],
            report_id=REPORT_ID,
            screened_at=SCREENED_AT,
        )

    assert error.value.code == "TARGET_ID_DUPLICATED"
    assert error.value.context["positions"] == [0, 1]


def test_a_mapping_handed_in_place_of_a_target_set_is_refused() -> None:
    with pytest.raises(ValidationTargetError) as error:
        build_eligibility_report(
            ROOT, target_manifest(), report_id=REPORT_ID, screened_at=SCREENED_AT
        )

    assert error.value.code == "INPUT_INVALID"


@pytest.mark.parametrize(
    ("report_id", "screened_at"), [("", SCREENED_AT), (REPORT_ID, "")]
)
def test_a_report_without_a_caller_supplied_identity_is_refused(
    report_id: str, screened_at: str
) -> None:
    with pytest.raises(ValidationTargetError) as error:
        build_eligibility_report(ROOT, [], report_id=report_id, screened_at=screened_at)

    assert error.value.code == "INPUT_INVALID"


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(ValidationTargetError) as error:
        contracts._fail("SOMETHING_ELSE", "a code nobody declared")

    assert error.value.code == "INPUT_INVALID"
    assert error.value.context["code"] == "SOMETHING_ELSE"
    assert "SOMETHING_ELSE" not in FINDING_CODES


def test_an_undeclared_decision_table_key_is_drift_not_a_default() -> None:
    with pytest.raises(ValidationTargetError) as error:
        contracts._assert_table({"none": ()}, ["none", "added_policy"], "approval")

    assert error.value.code == "VOCABULARY_DRIFT"
    assert error.value.context["missing"] == ["added_policy"]


def test_a_bounded_scope_is_not_disturbed_by_screening() -> None:
    scope = bounded_scope()
    before = dict(scope)
    manifest = target_manifest(validation_scope=scope)

    screen_target(ROOT, manifest)

    assert scope == before
    assert manifest["validation_scope"] == before
    assert ARTIFACT_HASH in manifest["artifact_hashes"]
