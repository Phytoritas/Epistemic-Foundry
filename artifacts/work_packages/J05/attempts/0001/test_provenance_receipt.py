"""provenance_and_receipt_audit — every effect is a self-proving receipt.

Nothing in J05 scores, selects or promotes; what it must instead prove is that
each record it emits re-derives byte for byte from the fields it publishes, that
replaying the same identified call reproduces the identical receipt, and that
the inputs it was handed are never mutated in the process.  There is no clock
and no random draw on any identified path, so determinism here is a property of
the module rather than of the environment it ran in.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.operators.v4_j05 import (
    MutationOperatorRegistry,
    build_activation_record,
    build_prompt_genome,
    require_sealed_digest,
    verify_activation_record,
)
from fixtures import (
    TARGET_RUN,
    activation_arguments,
    active_genome,
    arguments,
    change,
    declared_parameters,
    operator_spec,
    released_proposal,
)


def _registered() -> tuple[MutationOperatorRegistry, dict]:
    registry = MutationOperatorRegistry()
    record = registry.register(
        spec=operator_spec(),
        declared_parameters=declared_parameters(),
        proposal=released_proposal(),
    )
    return registry, record


# --- each record re-derives its own digest -------------------------------


def test_the_registration_record_hash_covers_the_record() -> None:
    _, record = _registered()

    assert record["record_hash"] == hash_excluding(record, "record_hash")


def test_the_binding_hash_covers_the_binding() -> None:
    registry, _ = _registered()

    binding = registry.bind_parameters("MOP-J05-PROMPT", arguments())

    assert binding["binding_hash"] == hash_excluding(binding, "binding_hash")


def test_the_change_hash_covers_the_change() -> None:
    proposed = change()

    assert proposed["change_hash"] == hash_excluding(proposed, "change_hash")


def test_the_claim_hash_covers_the_claim() -> None:
    registry, _ = _registered()

    claim = registry.claim_active_prompt_operator(
        "MOP-J05-PROMPT", target_run_id=TARGET_RUN
    )

    assert claim["claim_hash"] == hash_excluding(claim, "claim_hash")


def test_the_activation_hash_covers_the_record_and_verifies() -> None:
    record = build_activation_record(**activation_arguments())

    assert record["activation_hash"] == hash_excluding(record, "activation_hash")
    assert verify_activation_record(record) == record["activation_hash"]


def test_a_constructed_genome_hash_covers_the_genome() -> None:
    genome = build_prompt_genome(
        prompt_genome_id="PG-PROV-1",
        task_class="hypothesis_mutation",
        template="restate {claim} with one fewer assumption",
        forbidden_authorities=["evaluator_bundle"],
    )

    assert genome["prompt_hash"] == hash_excluding(genome, "prompt_hash")


def test_a_successor_genome_hash_covers_the_successor() -> None:
    successor = change()["proposed_genome"]

    assert successor["prompt_hash"] == hash_excluding(successor, "prompt_hash")


def test_require_sealed_digest_returns_the_derived_digest() -> None:
    genome = active_genome()

    assert (
        require_sealed_digest(genome, "prompt_hash", "prompt-genome")
        == genome["prompt_hash"]
    )


# --- an identified call replays byte for byte ----------------------------


def test_registration_replays_byte_for_byte() -> None:
    _, first = _registered()
    _, second = _registered()

    assert first == second
    assert first["record_hash"] == second["record_hash"]


def test_two_registries_of_the_same_operators_hash_alike() -> None:
    first, _ = _registered()
    second, _ = _registered()

    assert first.registry_hash() == second.registry_hash()
    assert first.records() == second.records()


def test_an_identified_change_replays_byte_for_byte() -> None:
    first = change()
    second = change()

    assert first == second
    assert first["change_hash"] == second["change_hash"]


def test_an_identified_activation_replays_byte_for_byte() -> None:
    first = build_activation_record(**activation_arguments())
    second = build_activation_record(**activation_arguments())

    assert first == second
    assert first["activation_hash"] == second["activation_hash"]


# --- the receipt names its own provenance --------------------------------


def test_the_change_receipt_names_its_source_by_hash() -> None:
    source = active_genome()
    proposed = change(source_genome=source)

    assert proposed["source_prompt_hash"] == source["prompt_hash"]
    assert proposed["source_prompt_hash"] == hash_excluding(source, "prompt_hash")
    assert proposed["source_prompt_genome_id"] == source["prompt_genome_id"]


def test_the_activation_receipt_names_the_proposal_by_hash() -> None:
    proposal = released_proposal()
    record = build_activation_record(**activation_arguments(proposal=proposal))

    assert record["proposal_hash"] == proposal["proposal_hash"]
    assert record["proposal_id"] == proposal["proposal_id"]
    assert record["proposed_prompt_genome_id"] == proposal["proposed_prompt_genome_id"]


def test_the_registration_record_names_its_spec_and_parameters_by_hash() -> None:
    registry, record = _registered()

    assert record["spec_hash"] == sha256_of_payload(operator_spec())
    assert record["parameter_contract_hash"] == sha256_of_payload(declared_parameters())


# --- inputs are never mutated --------------------------------------------


def test_registration_never_mutates_the_spec_or_proposal_it_was_given() -> None:
    spec = operator_spec()
    parameters = declared_parameters()
    proposal = released_proposal()
    before = (copy.deepcopy(spec), copy.deepcopy(parameters), copy.deepcopy(proposal))

    MutationOperatorRegistry().register(
        spec=spec, declared_parameters=parameters, proposal=proposal
    )

    assert (spec, parameters, proposal) == before


def test_a_change_never_mutates_the_source_genome_it_was_given() -> None:
    source = active_genome()
    before = copy.deepcopy(source)

    change(source_genome=source)

    assert source == before


def test_an_activation_never_mutates_the_proposal_it_was_given() -> None:
    proposal = released_proposal()
    before = copy.deepcopy(proposal)

    build_activation_record(**activation_arguments(proposal=proposal))

    assert proposal == before


def test_binding_never_mutates_the_arguments_it_was_given() -> None:
    registry, _ = _registered()
    supplied = arguments()
    before = copy.deepcopy(supplied)

    registry.bind_parameters("MOP-J05-PROMPT", supplied)

    assert supplied == before


def test_the_registry_hands_back_copies_a_caller_cannot_use_to_edit_it() -> None:
    registry, _ = _registered()

    registry.record("MOP-J05-PROMPT")["prompt_affecting"] = False
    registry.proposal("MOP-J05-PROMPT")["status"] = "FORGED"

    assert registry.record("MOP-J05-PROMPT")["prompt_affecting"] is True
    assert (
        registry.proposal("MOP-J05-PROMPT")["status"] == released_proposal()["status"]
    )
