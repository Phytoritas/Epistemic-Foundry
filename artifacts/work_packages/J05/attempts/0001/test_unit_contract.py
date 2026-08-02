"""unit_and_contract_tests — the registry works the way J05 claims it works.

An operator inside the sealed search space registers into a typed record; its
declared parameters actually bind; a prompt genome is born quarantined; a change
to an active prompt genome comes back as a quarantined proposal the governance
module built and a successor genome that descends from it; and a released
proposal becomes an activation record that names the workflow node it mirrors.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.governance.quarantine import may_influence_run
from epistemic_foundry.operators.v4_j05 import (
    PROMPT_GENOME_KIND,
    MutationOperatorRegistry,
    build_activation_record,
    build_prompt_genome,
    governance_retroactivity_node,
    operator_genome_kinds,
    proposal_status_vocabulary,
    quarantined_prompt_status,
    verify_activation_record,
)
from fixtures import (
    EVIDENCE,
    HYPOTHESIS_KIND,
    SOURCE_RUN,
    TARGET_RUN,
    activation_arguments,
    active_genome,
    arguments,
    change,
    declared_parameters,
    hypothesis_operator_spec,
    operator_spec,
    prompt_genome,
    released_proposal,
)


def registered(**overrides) -> tuple[MutationOperatorRegistry, dict]:
    registry = MutationOperatorRegistry()
    record = registry.register(
        spec=operator_spec(),
        declared_parameters=declared_parameters(),
        proposal=overrides.get("proposal", released_proposal()),
    )
    return registry, record


def test_a_prompt_operator_inside_the_search_space_registers() -> None:
    registry, record = registered()

    assert record["operator_id"] == "MOP-J05-PROMPT"
    assert record["genome_kinds"] == [PROMPT_GENOME_KIND]
    assert record["output_genome_kind"] == PROMPT_GENOME_KIND
    assert record["prompt_affecting"] is True
    assert record["declared_parameter_names"] == [
        "candidate_count",
        "preserve_falsifier",
    ]
    assert registry.operator_ids() == ("MOP-J05-PROMPT",)


def test_the_record_carries_the_quarantine_status_of_its_proposal() -> None:
    registry, record = registered()
    proposal = registry.proposal("MOP-J05-PROMPT")

    assert record["quarantine_status"] == proposal["status"]
    assert record["quarantine_inert"] is not may_influence_run(proposal)
    assert record["proposal_id"] == proposal["proposal_id"]


def test_an_operator_that_touches_no_prompt_registers_without_a_proposal() -> None:
    registry = MutationOperatorRegistry()

    record = registry.register(
        spec=hypothesis_operator_spec(), declared_parameters=declared_parameters()
    )

    assert record["genome_kinds"] == [HYPOTHESIS_KIND]
    assert record["prompt_affecting"] is False
    assert record["quarantine_status"] is None
    assert record["quarantine_inert"] is None
    assert registry.proposal("MOP-J05-HYPOTHESIS") is None


def test_the_genome_kinds_are_derived_from_the_specification() -> None:
    spec = operator_spec(input_genome_types=[HYPOTHESIS_KIND, PROMPT_GENOME_KIND])

    assert operator_genome_kinds(spec) == (HYPOTHESIS_KIND, PROMPT_GENOME_KIND)


def test_declared_arguments_bind_and_the_binding_hashes_itself() -> None:
    registry, record = registered()

    binding = registry.bind_parameters("MOP-J05-PROMPT", arguments())

    assert binding["arguments"] == arguments()
    assert binding["parameter_contract_hash"] == record["parameter_contract_hash"]
    assert binding["binding_hash"] == hash_excluding(dict(binding), "binding_hash")


def test_the_registry_hands_back_copies_rather_than_its_own_state() -> None:
    registry, _ = registered()

    record = registry.record("MOP-J05-PROMPT")
    record["prompt_affecting"] = False
    contract = registry.parameter_contract("MOP-J05-PROMPT")
    contract.pop("candidate_count")

    assert registry.record("MOP-J05-PROMPT")["prompt_affecting"] is True
    assert "candidate_count" in registry.parameter_contract("MOP-J05-PROMPT")


def test_two_registries_holding_the_same_operators_agree_exactly() -> None:
    first, _ = registered()
    second, _ = registered()

    assert first.registry_hash() == second.registry_hash()
    assert first.records() == second.records()


def test_a_constructed_prompt_genome_is_born_quarantined_and_valid() -> None:
    genome = build_prompt_genome(
        prompt_genome_id="PG-U-1",
        task_class="hypothesis_mutation",
        template="restate {claim} with one fewer assumption",
        forbidden_authorities=["evaluator_bundle"],
    )

    assert genome["status"] == quarantined_prompt_status()
    assert genome["version"] == 1
    assert genome["parent_prompt_ids"] == []
    assert genome["prompt_hash"] == hash_excluding(dict(genome), "prompt_hash")


def test_a_change_returns_the_quarantine_modules_own_proposal() -> None:
    proposed = change()

    assert proposed["proposal"]["status"] == proposal_status_vocabulary()[0]
    assert proposed["proposal"]["source_prompt_genome_id"] == "PG-J05-1"
    assert proposed["proposal"]["proposed_prompt_genome_id"] == "PG-J05-2"
    assert proposed["proposal"]["qualification_plan_id"] == "QP-J05-1"
    assert may_influence_run(proposed["proposal"]) is False


def test_the_changed_sections_are_derived_from_the_documents() -> None:
    proposed = change(
        changes={
            "template": "propose two bounded variants of {claim}",
            "task_class": "prompt_simplification",
        }
    )

    assert proposed["changed_sections"] == ["task_class", "template"]
    assert proposed["proposal"]["changed_sections"] == ["task_class", "template"]


def test_a_no_op_field_is_not_reported_as_a_change() -> None:
    source = active_genome()
    proposed = change(changes={"task_class": source["task_class"], "template": "new"})

    assert proposed["changed_sections"] == ["template"]


def test_the_successor_descends_from_the_source_and_is_quarantined() -> None:
    proposed = change()
    successor = proposed["proposed_genome"]

    assert successor["prompt_genome_id"] == "PG-J05-2"
    assert successor["version"] == active_genome()["version"] + 1
    assert successor["parent_prompt_ids"] == ["PG-J05-1"]
    assert successor["status"] == quarantined_prompt_status()
    assert successor["prompt_hash"] == hash_excluding(dict(successor), "prompt_hash")


def test_the_source_genome_is_returned_unchanged_beside_its_successor() -> None:
    source = active_genome()
    proposed = change(source_genome=source)

    assert proposed["source_prompt_genome_id"] == source["prompt_genome_id"]
    assert proposed["source_prompt_hash"] == source["prompt_hash"]
    assert proposed["proposed_genome"]["template"] != source["template"]


def test_the_change_is_gated_against_the_runs_active_prompt_surface() -> None:
    proposed = change()

    assert proposed["gate"]["target_run_id"] == TARGET_RUN
    assert proposed["gate"]["active_prompt_genome_count"] == 1
    assert proposed["gate"]["proposals_examined"] == 1
    assert proposed["gate"]["released_activations"] == 0


def test_a_released_proposal_may_be_claimed_as_an_active_prompt_operator() -> None:
    registry, record = registered()

    claim = registry.claim_active_prompt_operator(
        "MOP-J05-PROMPT", target_run_id=TARGET_RUN
    )

    assert claim["active_prompt_genome_id"] == "PG-J05-2"
    assert claim["quarantine_status"] == released_proposal()["status"]
    assert claim["gate"]["released_activations"] == 1
    assert claim["record_hash"] == record["record_hash"]


def test_an_activation_record_names_the_workflow_node_it_mirrors() -> None:
    record = build_activation_record(**activation_arguments())

    assert record["governance_node_id"] == governance_retroactivity_node()
    assert record["source_run_id"] == SOURCE_RUN
    assert record["target_run_id"] == TARGET_RUN
    assert record["qualification_evidence_ids"] == sorted(EVIDENCE)
    assert record["proposed_prompt_genome_id"] == "PG-J05-2"
    assert verify_activation_record(record) == record["activation_hash"]


def test_a_quarantined_genome_can_still_be_changed_without_being_active() -> None:
    """Quarantine is where a genome starts, not a reason it cannot be revised."""
    proposed = change(source_genome=prompt_genome(), active_prompt_genome_ids=[])

    assert proposed["proposal"]["source_prompt_genome_id"] == "PG-J05-1"
    assert proposed["gate"]["active_prompt_genome_count"] == 0
