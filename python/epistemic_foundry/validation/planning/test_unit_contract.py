"""unit_and_contract_tests — what a well-formed preregistration actually gets.

The builders' contract is that each document they return is one the canonical
schema accepts, carries exactly the declared field set, and derives everything
that could otherwise drift: the stage plan re-derives its own hash, the
register carries one canonical PredictionGene and its FalsifierGene per
declared prediction, and the sealed plan's endpoints and single
``falsification_rule`` are derived from the register rather than supplied
beside it.  The seal's contract is that an intact preregistration re-derives to
nothing, an amendment is a new plan that names its predecessor's seal, and the
whole path carries no clock and no random draw — the same arguments seal to the
same receipt byte for byte.
"""

from __future__ import annotations

from .contracts import (
    RECEIPT_FIELDS,
    SEALED_PLAN_FIELDS,
    amendment_chain,
    build_prediction_register,
    cascade_fields,
    cascade_schema_errors,
    declared_ports,
    digest,
    plan_fields,
    plan_references,
    plan_schema_errors,
    reference,
    register_counts,
    render_criterion,
    render_falsification_rule,
    require_intact,
    verify_preregistration,
)
from .fixtures import (
    GENOME_ID,
    PLAN_ID,
    ROOT,
    amendment,
    outputs,
    plan_arguments,
    predictions,
    preregistration,
    stage_plan,
    stages,
    target_manifest,
)


def register() -> list[dict]:
    return build_prediction_register(
        ROOT,
        predictions(),
        genome_id=GENOME_ID,
        outputs=["storage_estimate", "spill_volume"],
    )


def test_a_built_stage_plan_validates_and_re_derives_its_hash() -> None:
    cascade = stage_plan()

    assert set(cascade) == set(cascade_fields(ROOT))
    assert cascade_schema_errors(ROOT, cascade) == []
    assert cascade["stages"] == stages()
    assert cascade["plan_hash"].startswith("sha256:")


def test_a_stage_plan_keeps_the_stages_in_declared_order() -> None:
    cascade = stage_plan()

    assert [stage["stage_id"] for stage in cascade["stages"]] == [
        "contract-screen",
        "scenario-simulation",
        "independent-replication",
    ]


def test_a_register_carries_a_gene_and_a_falsifier_for_each_prediction() -> None:
    entries = register()

    assert [entry["prediction_id"] for entry in entries] == [
        "PRED-V02-1",
        "PRED-V02-2",
        "PRED-V02-3",
    ]
    falsifiable = [entry for entry in entries if entry["criterion"] is not None]
    assert all(entry["falsifier"] is not None for entry in falsifiable)
    assert [entry["falsifier"]["linked_prediction_ids"] for entry in falsifiable] == [
        ["PRED-V02-1"],
        ["PRED-V02-2"],
    ]


def test_an_exploratory_prediction_carries_no_criterion_and_is_not_promotable() -> None:
    entry = next(e for e in register() if e["prediction_id"] == "PRED-V02-3")

    assert entry["exploratory"] is True
    assert entry["criterion"] is None
    assert entry["falsifier"] is None
    assert entry["promotable"] is False


def test_a_prediction_gene_declares_it_was_preregistered() -> None:
    entry = register()[0]

    assert entry["prediction"]["pre_registered"] is True
    assert entry["prediction"]["genome_id"] == GENOME_ID


def test_the_register_counts_reconcile() -> None:
    counts = register_counts(register())

    assert counts == {
        "exploratory": 1,
        "falsifiable": 2,
        "predictions": 3,
        "promotable": 2,
    }


def test_a_criterion_renders_from_its_threshold_rather_than_prose() -> None:
    entry = register()[0]

    assert render_criterion(entry["criterion"]) == "{storage_estimate} < 12.5 m3"
    assert entry["falsifier"]["observable_condition"] == render_criterion(
        entry["criterion"]
    )


def test_the_falsification_rule_is_derived_from_the_whole_register() -> None:
    rule = render_falsification_rule(register())

    assert rule.startswith("the preregistered claim is falsified if any")
    assert "PRED-V02-1: {storage_estimate} < 12.5 m3" in rule
    assert "PRED-V02-2: {spill_volume} >= 4.0 m3" in rule


def test_a_preregistration_carries_exactly_the_receipt_field_set() -> None:
    receipt = preregistration()

    assert set(receipt) == set(RECEIPT_FIELDS) | {"receipt_hash"}
    assert plan_schema_errors(ROOT, receipt["plan"]) == []


def test_the_sealed_plan_publishes_derived_endpoints_and_rule() -> None:
    receipt = preregistration()
    plan = receipt["plan"]

    assert plan["observables"] == ["{spill_volume}", "{storage_estimate}"]
    assert plan["falsification_rule"] == render_falsification_rule(
        receipt["prediction_register"]
    )
    assert plan["preregistration_hash"] == receipt["preregistration_hash"]


def test_the_receipt_reconciles_predictions_and_stages() -> None:
    receipt = preregistration()

    assert receipt["counts"] == {
        "exploratory": 1,
        "falsifiable": 2,
        "predictions": 3,
        "promotable": 2,
        "stages": 3,
    }
    assert receipt["exploratory_prediction_ids"] == ["PRED-V02-3"]
    assert receipt["promotable_prediction_ids"] == ["PRED-V02-1", "PRED-V02-2"]


def test_a_variable_mapping_value_is_normalised_to_the_reference_grammar() -> None:
    plan = preregistration()["plan"]

    assert plan["variable_mapping"]["drawdown_state"] == reference("reservoir_level")
    assert plan["variable_mapping"]["forcing"] == reference("rainfall_series")


def test_declared_ports_maps_each_port_to_its_collection() -> None:
    ports = declared_ports(
        target_manifest(), ("inputs", "outputs", "parameters", "state_variables")
    )

    assert ports["storage_estimate"] == "outputs"
    assert ports["spill_volume"] == "outputs"
    assert ports["seed"] == "parameters"
    assert ports["reservoir_level"] == "state_variables"


def test_the_plan_references_are_read_in_the_declared_grammar() -> None:
    plan = preregistration()["plan"]
    names = {name for _, name in plan_references(plan)}

    assert "reservoir_level" in names
    assert "storage_estimate" in names


def test_an_intact_preregistration_re_derives_to_nothing() -> None:
    receipt = preregistration()

    assert verify_preregistration(ROOT, receipt) == []
    assert require_intact(ROOT, receipt) == receipt


def test_an_amendment_is_a_new_plan_that_names_its_predecessor() -> None:
    first = preregistration()
    second = amendment(first)

    assert second["amends"] == first["preregistration_hash"]
    assert second["amendment_index"] == 1
    assert second["plan"]["plan_id"] != first["plan"]["plan_id"]
    assert verify_preregistration(ROOT, second) == []


def test_an_amendment_chain_returns_its_seals_oldest_first() -> None:
    first = preregistration()
    second = amendment(first)

    assert amendment_chain(ROOT, [first, second]) == (
        first["preregistration_hash"],
        second["preregistration_hash"],
    )


def test_the_two_declared_outputs_let_endpoints_be_seen_as_derived() -> None:
    assert [port["id"] for port in outputs()] == ["storage_estimate", "spill_volume"]


def test_the_builder_does_not_mutate_what_the_caller_passed() -> None:
    arguments = plan_arguments()
    before = digest(
        {
            key: value
            for key, value in arguments.items()
            if key not in ("target_manifest", "eligibility_report", "cascade_plan")
        }
    )

    preregistration()

    after = digest(
        {
            key: value
            for key, value in arguments.items()
            if key not in ("target_manifest", "eligibility_report", "cascade_plan")
        }
    )
    assert after == before


def test_the_same_arguments_seal_to_the_same_receipt() -> None:
    assert preregistration() == preregistration()


def test_every_sealed_field_is_present_in_the_published_plan() -> None:
    plan = preregistration()["plan"]

    assert set(SEALED_PLAN_FIELDS) <= set(plan)
    assert set(plan) == set(plan_fields(ROOT))


def test_a_fresh_preregistration_does_not_share_state_with_the_next() -> None:
    first = preregistration()
    first["plan"]["metrics"].append("mutated")

    assert preregistration()["plan"]["metrics"] == [
        "adjusted_mean_difference",
        "holdout_error",
    ]
    assert PLAN_ID == "VPLAN-V02-0001"
