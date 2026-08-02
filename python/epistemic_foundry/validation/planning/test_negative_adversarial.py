"""negative_and_adversarial_tests — every route past the seal is tried.

A preregistration is only worth its name if it refuses everything that would
let a result change the plan after the fact.  Each refusal declared in
``FINDING_CODES`` is exercised here with the exact input that reaches it: a
plan bound to a target nothing screened, a report edited after it was sealed, a
falsification criterion that points the same way as the prediction it claims to
refute, a prediction entered as exploratory yet carrying a confirmatory test, a
seed left unfixed for a stochastic target, an amendment that reuses the identity
it amends, and a sealed receipt changed before it was read again.

Each refusal must fail with the code that stopped it rather than degrade into a
permissive default.  The one internal backstop with no reachable input —
``FALSIFIER_SCHEMA_INVALID`` — is documented where its reachable twin
``PREDICTION_SCHEMA_INVALID`` is tested: both fire only if a validated document
still fails its canonical schema, and only the prediction path can be driven
there from the public surface.
"""

from __future__ import annotations

import pytest

from . import contracts
from .contracts import (
    COMPARATORS,
    FINDING_CODES,
    ValidationPlanError,
    amendment_chain,
    build_prediction_register,
    build_stage_plan,
    register_counts,
    require_intact,
)
from .fixtures import (
    GENOME_ID,
    PLAN_ID,
    ROOT,
    amendment,
    eligibility_report,
    falsification,
    prediction,
    predictions,
    preregistration,
    stage_plan,
    stages,
    target_manifest,
)

OUTPUTS = ["storage_estimate", "spill_volume"]


def refusal(**overrides: object) -> ValidationPlanError:
    with pytest.raises(ValidationPlanError) as error:
        preregistration(**overrides)
    return error.value


def register(*preds: object) -> list[dict]:
    return build_prediction_register(
        ROOT, list(preds), genome_id=GENOME_ID, outputs=OUTPUTS
    )


# --- target binding -------------------------------------------------------


def test_a_plan_bound_to_an_unscreened_manifest_is_refused() -> None:
    manifest = target_manifest()
    other = eligibility_report(target_manifest(version="9.9.9"))

    error = refusal(target_manifest=manifest, eligibility_report=other)

    assert error.code == "TARGET_UNSCREENED"


def test_a_plan_bound_to_an_ineligible_target_is_refused() -> None:
    manifest = target_manifest(supported_actions=[])

    error = refusal(target_manifest=manifest)

    assert error.code == "TARGET_INELIGIBLE"


def test_a_report_edited_after_sealing_is_refused() -> None:
    manifest = target_manifest()
    report = eligibility_report(manifest)
    report["screened_at"] = "2099-01-01T00:00:00Z"

    error = refusal(target_manifest=manifest, eligibility_report=report)

    assert error.code == "ELIGIBILITY_REPORT_UNVERIFIED"


def test_a_plan_naming_a_different_version_than_it_screened_is_refused() -> None:
    error = refusal(target_version="2.0.0")

    assert error.code == "TARGET_VERSION_MISMATCH"


# --- falsifiability -------------------------------------------------------


def test_a_criterion_that_points_the_same_way_as_its_prediction_is_refused() -> None:
    error = refusal(
        predictions=[prediction(falsification=falsification(comparator=">="))]
    )

    assert error.code == "CRITERION_DIRECTION_INCOMPATIBLE"


def test_a_criterion_using_an_undeclared_comparator_is_refused() -> None:
    error = refusal(
        predictions=[prediction(falsification=falsification(comparator="~"))]
    )

    assert error.code == "COMPARATOR_UNDECLARED"
    assert error.context["comparator"] == "~"
    assert error.context["declared"] == list(COMPARATORS)


def test_a_prediction_observing_a_non_output_port_is_refused() -> None:
    error = refusal(predictions=[prediction(observable_id="reservoir_level")])

    assert error.code == "CRITERION_PORT_UNDECLARED"


def test_an_exploratory_prediction_carrying_a_criterion_is_refused() -> None:
    error = refusal(
        predictions=[prediction(exploratory=True, falsification=falsification())]
    )

    assert error.code == "EXPLORATORY_CRITERION_DECLARED"


def test_a_confirmatory_prediction_without_a_criterion_is_refused() -> None:
    error = refusal(predictions=[prediction(exploratory=False, falsification=None)])

    assert error.code == "PLAN_UNFALSIFIABLE"


def test_a_register_of_only_exploratory_predictions_is_refused() -> None:
    with pytest.raises(ValidationPlanError) as error:
        preregistration(
            predictions=[
                prediction(
                    prediction_gene_id="PRED-EXP",
                    expected_direction="qualitative",
                    exploratory=True,
                    falsification=None,
                )
            ]
        )

    assert error.value.code == "PLAN_UNFALSIFIABLE"


def test_two_predictions_sharing_one_id_are_refused() -> None:
    error = refusal(predictions=[prediction(), prediction()])

    assert error.code == "PREDICTION_ID_DUPLICATED"


def test_a_prediction_the_gene_schema_refuses_is_reported_as_such() -> None:
    error = refusal(predictions=[prediction(discrimination_targets=[])])

    assert error.code == "PREDICTION_SCHEMA_INVALID"


def test_a_hand_built_register_that_does_not_reconcile_is_refused() -> None:
    entries = register(prediction(), prediction(prediction_gene_id="PRED-V02-2"))
    entries[0]["criterion"] = None  # falsifiable now disagrees with promotable

    with pytest.raises(ValidationPlanError) as error:
        register_counts(entries)

    assert error.value.code == "PREDICTION_COUNT_UNRECONCILED"


# --- plan grounding and effects -------------------------------------------


def test_an_action_the_target_does_not_support_is_refused() -> None:
    error = refusal(actions=[{"action": "teleport", "arguments": {}}])

    assert error.code == "ACTION_UNSUPPORTED"


def test_a_variable_mapping_value_naming_no_port_is_refused() -> None:
    error = refusal(variable_mapping={"x": "no reference here"})

    assert error.code == "PLAN_REFERENCE_MISSING"


def test_a_variable_mapping_value_naming_an_undeclared_port_is_refused() -> None:
    error = refusal(variable_mapping={"x": "{ghost_port}"})

    assert error.code == "PLAN_REFERENCE_UNGROUNDED"


def test_an_action_argument_naming_an_output_port_is_refused() -> None:
    error = refusal(
        actions=[{"action": "perturb", "arguments": {"p": "{storage_estimate}"}}]
    )

    assert error.code == "PLAN_REFERENCE_MISDIRECTED"


def test_a_plan_id_the_schema_pattern_refuses_reaches_the_backstop() -> None:
    error = refusal(plan_id="not-a-plan-id")

    assert error.code == "PLAN_SCHEMA_INVALID"
    assert any("plan_id" in message for message in error.context["errors"])


def test_a_missing_identifiability_warning_is_refused() -> None:
    error = refusal(identifiability_warnings=[])

    assert error.code == "IDENTIFIABILITY_UNASSESSED"


def test_a_malformed_environment_digest_is_refused() -> None:
    error = refusal(environment_digest="not-a-digest")

    assert error.code == "ENVIRONMENT_DIGEST_MALFORMED"


def test_a_stochastic_target_without_a_fixed_seed_is_refused() -> None:
    error = refusal(random_seed=None)

    assert error.code == "SEED_UNFIXED"


def test_a_gated_target_without_an_approval_record_is_refused() -> None:
    manifest = target_manifest(safety_class="high_risk", approval_policy="all_effects")

    error = refusal(target_manifest=manifest, approval_record_ids=[])

    assert error.code == "APPROVAL_RECORD_MISSING"


def test_a_supplied_stage_plan_that_no_longer_re_derives_is_refused() -> None:
    cascade = stage_plan()
    cascade["max_total_budget"] = 200.0  # the sealed plan_hash is now stale

    error = refusal(cascade_plan=cascade)

    assert error.code == "CASCADE_SCHEMA_INVALID"


# --- stage plan construction ----------------------------------------------


def test_two_stages_sharing_one_id_are_refused() -> None:
    doubled = [stages()[0], {**stages()[1], "stage_id": "contract-screen"}]

    with pytest.raises(ValidationPlanError) as error:
        build_stage_plan(
            ROOT,
            cascade_plan_id="VCAS-DUP",
            candidate_class="c",
            stages=doubled,
            max_total_budget=100.0,
            early_stop_policy="stop early",
        )

    assert error.value.code == "STAGE_ID_DUPLICATED"


def test_stage_budget_fractions_summing_above_the_whole_are_refused() -> None:
    greedy = [
        {**stages()[0], "budget_fraction": 0.7},
        {**stages()[1], "budget_fraction": 0.7},
    ]

    with pytest.raises(ValidationPlanError) as error:
        build_stage_plan(
            ROOT,
            cascade_plan_id="VCAS-OVER",
            candidate_class="c",
            stages=greedy,
            max_total_budget=100.0,
            early_stop_policy="stop early",
        )

    assert error.value.code == "STAGE_BUDGET_OVERCOMMITTED"


def test_a_stage_carrying_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationPlanError) as error:
        build_stage_plan(
            ROOT,
            cascade_plan_id="VCAS-FIELD",
            candidate_class="c",
            stages=[{**stages()[0], "weight": 1}],
            max_total_budget=100.0,
            early_stop_policy="stop early",
        )

    assert error.value.code == "FIELD_SET_INVALID"
    assert error.value.context["unknown"] == ["weight"]


def test_a_stage_class_the_schema_does_not_declare_is_refused() -> None:
    with pytest.raises(ValidationPlanError) as error:
        build_stage_plan(
            ROOT,
            cascade_plan_id="VCAS-ENUM",
            candidate_class="c",
            stages=[{**stages()[0], "stage_class": "oracle"}],
            max_total_budget=100.0,
            early_stop_policy="stop early",
        )

    assert error.value.code == "INPUT_INVALID"


# --- amendments and mutation ----------------------------------------------


def test_an_amendment_reusing_the_predecessor_plan_id_is_refused() -> None:
    first = preregistration()

    with pytest.raises(ValidationPlanError) as error:
        amendment(first, plan_id=PLAN_ID)

    assert error.value.code == "AMENDMENT_IDENTITY_REUSED"


def test_an_amendment_of_a_broken_predecessor_is_refused() -> None:
    first = preregistration()
    first["preregistration_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValidationPlanError) as error:
        amendment(first)

    assert error.value.code == "AMENDMENT_CHAIN_BROKEN"


def test_a_chain_that_does_not_continue_is_refused() -> None:
    first = preregistration()
    second = amendment(first)

    with pytest.raises(ValidationPlanError) as error:
        amendment_chain(ROOT, [first, first, second])

    assert error.value.code in {"AMENDMENT_CHAIN_BROKEN", "AMENDMENT_IDENTITY_REUSED"}


def test_a_sealed_receipt_changed_after_sealing_is_refused() -> None:
    receipt = preregistration()
    receipt["preregistered_at"] = "2099-01-01T00:00:00Z"

    with pytest.raises(ValidationPlanError) as error:
        require_intact(ROOT, receipt)

    assert error.value.code == "PREREGISTRATION_MUTATED"
    assert "receipt_hash" in error.value.context["mismatches"]


# --- fail-closed guards ---------------------------------------------------


def test_an_unreadable_schema_fails_closed(tmp_path: object) -> None:
    with pytest.raises(ValidationPlanError) as error:
        build_stage_plan(
            tmp_path,
            cascade_plan_id="VCAS",
            candidate_class="c",
            stages=stages(),
            max_total_budget=100.0,
            early_stop_policy="stop early",
        )

    assert error.value.code == "SCHEMA_UNREADABLE"


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(ValidationPlanError) as error:
        contracts._fail("SOMETHING_ELSE", "a code nobody declared")

    assert error.value.code == "INPUT_INVALID"
    assert "SOMETHING_ELSE" not in FINDING_CODES


def test_an_undeclared_decision_table_key_is_drift_not_a_default() -> None:
    with pytest.raises(ValidationPlanError) as error:
        contracts._assert_table({"increase": ()}, ["increase", "sideways"], "direction")

    assert error.value.code == "VOCABULARY_DRIFT"
    assert error.value.context["missing"] == ["sideways"]


def test_every_registered_prediction_id_is_unique_across_the_fixture_set() -> None:
    ids = [entry["prediction_id"] for entry in register(*predictions())]

    assert len(ids) == len(set(ids))
