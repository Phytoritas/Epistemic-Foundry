"""negative_and_adversarial_tests — every refusal fires for the stated reason.

A typed registry earns the word "typed" only by what it refuses.  Each test
here drives one declared finding to its exact code, so a future change that
silences a guard, renames a code, or lets a candidate reach a run without
qualification fails here rather than shipping.  The most specific refusal wins,
so a case that could trip two guards asserts the one the module orders first.

Every code in :data:`FINDING_CODES` is exercised: the reachable guards through
their public entry points, and the five fail-closed contract-drift guards by
simulating the drift they exist to catch (the schemas and workflow are never
edited — the reader is redirected).  A final test asserts the exercised set is
exactly the declared set, so a new finding code without a test breaks the suite.
"""

from __future__ import annotations

import copy

import pytest

from epistemic_foundry.operators.v4_j05 import (
    FINDING_CODES,
    MutationOperatorError,
    MutationOperatorRegistry,
    active_prompt_status,
    build_activation_record,
    build_prompt_genome,
    governance_retroactivity_node,
    mutable_prompt_genome_kind,
    operator_contract,
    prompt_genome_contract,
    prompt_proposal_contract,
    require_sealed_digest,
    verify_activation_record,
)
from epistemic_foundry.operators.v4_j05 import declarations as declarations_module
from epistemic_foundry.operators.v4_j05 import prompt_workflow as workflow_module
from fixtures import (
    SOURCE_RUN,
    TARGET_RUN,
    activation_arguments,
    active_genome,
    change,
    declared_parameters,
    hypothesis_operator_spec,
    operator_spec,
    quarantined_proposal,
    released_proposal,
)

#: Every finding code an assertion in this module has driven to its refusal.
EXERCISED: set[str] = set()


def _run_refused(code: str, call) -> MutationOperatorError:
    with pytest.raises(MutationOperatorError) as caught:
        call()
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )
    EXERCISED.add(caught.value.code)
    return caught.value


def _registered() -> MutationOperatorRegistry:
    registry = MutationOperatorRegistry()
    registry.register(
        spec=operator_spec(),
        declared_parameters=declared_parameters(),
        proposal=released_proposal(),
    )
    return registry


# --- construction guards -------------------------------------------------


def test_a_non_positive_version_is_refused() -> None:
    _run_refused(
        "INPUT_INVALID",
        lambda: build_prompt_genome(
            prompt_genome_id="PG-BAD",
            task_class="hypothesis_mutation",
            template="restate {claim}",
            forbidden_authorities=["evaluator_bundle"],
            version=0,
        ),
    )


def test_a_genome_that_forbids_no_authority_is_refused() -> None:
    _run_refused(
        "PROMPT_AUTHORITY_UNDECLARED",
        lambda: build_prompt_genome(
            prompt_genome_id="PG-OPEN",
            task_class="hypothesis_mutation",
            template="restate {claim}",
            forbidden_authorities=[],
        ),
    )


# --- prompt-change guards ------------------------------------------------


def test_a_source_that_breaks_its_schema_is_refused() -> None:
    broken = active_genome()
    broken.pop("template")
    _run_refused(
        "PROMPT_GENOME_MALFORMED",
        lambda: change(source_genome=broken),
    )


def test_a_source_whose_digest_does_not_re_derive_is_refused() -> None:
    tampered = active_genome()
    tampered["template"] = "edited in place without re-sealing the digest"
    _run_refused("DIGEST_NOT_RE_DERIVABLE", lambda: change(source_genome=tampered))


def test_reusing_the_source_id_for_the_successor_is_refused() -> None:
    _run_refused(
        "PROMPT_IDENTITY_REUSED",
        lambda: change(proposed_prompt_genome_id="PG-J05-1"),
    )


def test_editing_a_lineage_field_the_lifecycle_derives_is_refused() -> None:
    _run_refused(
        "PROMPT_LINEAGE_FIELD_EDITED",
        lambda: change(changes={"version": 9}),
    )


def test_editing_an_authority_field_of_the_prompt_is_refused() -> None:
    # ``status`` is neither identity, version, parentage nor digest, so it
    # clears the lineage guard and reaches the evolution chamber's authority
    # refusal — the boundary that keeps a prompt from promoting itself.
    _run_refused(
        "PROMPT_AUTHORITY_MUTATION",
        lambda: change(changes={"status": active_prompt_status()}),
    )


def test_a_change_that_alters_nothing_is_refused() -> None:
    same = active_genome()["template"]
    _run_refused(
        "PROMPT_CHANGE_EMPTY",
        lambda: change(changes={"template": same}),
    )


def test_a_change_with_no_risk_analysis_is_refused() -> None:
    _run_refused(
        "RISK_ANALYSIS_MISSING",
        lambda: change(risk_analysis=[]),
    )


def test_a_change_that_names_the_successor_as_already_active_is_refused() -> None:
    # The successor is born quarantined; naming it on the run's active surface
    # is activation before qualification, which the S05 gate refuses.
    _run_refused(
        "PROMPT_MUTATION_INERT",
        lambda: change(active_prompt_genome_ids=["PG-J05-2"]),
    )


# --- activation guards ---------------------------------------------------


def test_an_activation_binding_no_qualification_evidence_is_refused() -> None:
    _run_refused(
        "QUALIFICATION_EVIDENCE_MISSING",
        lambda: build_activation_record(
            **activation_arguments(qualification_evidence_ids=[])
        ),
    )


def test_activating_a_still_quarantined_proposal_is_refused() -> None:
    _run_refused(
        "PROMPT_MUTATION_INERT",
        lambda: build_activation_record(
            **activation_arguments(proposal=quarantined_proposal())
        ),
    )


def test_applying_a_proposal_to_the_run_that_produced_it_is_refused() -> None:
    _run_refused(
        "RETROACTIVE_ACTIVATION",
        lambda: build_activation_record(
            **activation_arguments(source_run_id=SOURCE_RUN, target_run_id=SOURCE_RUN)
        ),
    )


def test_an_activation_proposal_that_breaks_its_schema_is_refused() -> None:
    malformed = released_proposal()
    malformed.pop("motivation")
    _run_refused(
        "PROPOSAL_MALFORMED",
        lambda: build_activation_record(**activation_arguments(proposal=malformed)),
    )


def test_an_activation_record_whose_digest_was_altered_is_refused() -> None:
    record = build_activation_record(**activation_arguments())
    record["target_run_id"] = "ERUN-FORGED"
    _run_refused("ACTIVATION_RECORD_DRIFT", lambda: verify_activation_record(record))


def test_a_bare_document_whose_digest_does_not_re_derive_is_refused() -> None:
    _run_refused(
        "DIGEST_NOT_RE_DERIVABLE",
        lambda: require_sealed_digest(
            {"proposal_hash": "sha256:" + "0" * 64, "a": 1}, "proposal_hash", "proposal"
        ),
    )


# --- registration guards -------------------------------------------------


def test_a_spec_that_breaks_the_operator_schema_is_refused() -> None:
    spec = operator_spec()
    spec.pop("operator_class")
    _run_refused(
        "OPERATOR_SPEC_MALFORMED",
        lambda: MutationOperatorRegistry().register(
            spec=spec, declared_parameters=declared_parameters()
        ),
    )


def test_registering_the_same_operator_id_twice_is_refused() -> None:
    registry = _registered()
    _run_refused(
        "OPERATOR_ID_DUPLICATED",
        lambda: registry.register(
            spec=operator_spec(),
            declared_parameters=declared_parameters(),
            proposal=released_proposal(),
        ),
    )


def test_an_operator_outside_the_sealed_search_space_is_refused() -> None:
    # ``scope-genome`` is a valid free-form genome type per the operator schema
    # but is not one C05 sealed as mutable, so the boundary guard fires.
    _run_refused(
        "OPERATOR_KIND_OUTSIDE_SEARCH_SPACE",
        lambda: MutationOperatorRegistry().register(
            spec=operator_spec(operator_id="MOP-OUT", genome_kind="scope-genome"),
            declared_parameters=declared_parameters(),
        ),
    )


def test_a_parameter_that_is_not_a_usable_schema_fragment_is_refused() -> None:
    _run_refused(
        "PARAMETER_SCHEMA_MALFORMED",
        lambda: MutationOperatorRegistry().register(
            spec=hypothesis_operator_spec(),
            declared_parameters={"candidate_count": {}},
        ),
    )


def test_a_prompt_operator_registered_with_no_proposal_is_refused() -> None:
    _run_refused(
        "PROMPT_MUTATION_UNPROPOSED",
        lambda: MutationOperatorRegistry().register(
            spec=operator_spec(), declared_parameters=declared_parameters()
        ),
    )


def test_a_non_prompt_operator_handed_a_proposal_is_refused() -> None:
    _run_refused(
        "PROPOSAL_NOT_APPLICABLE",
        lambda: MutationOperatorRegistry().register(
            spec=hypothesis_operator_spec(),
            declared_parameters=declared_parameters(),
            proposal=released_proposal(),
        ),
    )


def test_a_malformed_proposal_for_a_prompt_operator_is_refused() -> None:
    malformed = released_proposal()
    malformed.pop("motivation")
    _run_refused(
        "PROPOSAL_MALFORMED",
        lambda: MutationOperatorRegistry().register(
            spec=operator_spec(),
            declared_parameters=declared_parameters(),
            proposal=malformed,
        ),
    )


# --- lookup and binding guards -------------------------------------------


def test_looking_up_an_unregistered_operator_is_refused() -> None:
    _run_refused(
        "OPERATOR_UNREGISTERED",
        lambda: MutationOperatorRegistry().record("MOP-ABSENT"),
    )


def test_binding_arguments_that_violate_the_contract_is_refused() -> None:
    registry = _registered()
    _run_refused(
        "PARAMETER_CONTRACT_VIOLATED",
        lambda: registry.bind_parameters("MOP-J05-PROMPT", {"candidate_count": 99}),
    )


def test_a_non_mapping_argument_bundle_is_refused() -> None:
    registry = _registered()
    _run_refused(
        "INPUT_INVALID",
        lambda: registry.bind_parameters("MOP-J05-PROMPT", ["not", "a", "mapping"]),
    )


def test_claiming_a_non_prompt_operator_through_the_gate_is_refused() -> None:
    registry = MutationOperatorRegistry()
    registry.register(
        spec=hypothesis_operator_spec(), declared_parameters=declared_parameters()
    )
    _run_refused(
        "PROPOSAL_NOT_APPLICABLE",
        lambda: registry.claim_active_prompt_operator(
            "MOP-J05-HYPOTHESIS", target_run_id=TARGET_RUN
        ),
    )


# --- fail-closed contract-drift guards -----------------------------------
#
# These five guards exist so this package refuses categorically the moment a
# governing contract it reads drifts out from under it.  The contracts are
# never edited; the reader is redirected to a drifted view so the refusal that
# protects the boundary is proven to fire rather than assumed.


class _RegistryMissing:
    """A canonical registry whose one named schema has lost one property."""

    def __init__(self, real, kind: str, dropped: str) -> None:
        self._real = real
        self._kind = kind
        self._dropped = dropped

    def document(self, kind: str) -> dict:
        document = copy.deepcopy(self._real.document(kind))
        if kind == self._kind:
            document.get("properties", {}).pop(self._dropped, None)
        return document

    def names(self):
        return self._real.names()


def _redirect_registry(monkeypatch, kind: str, dropped: str) -> None:
    real = declarations_module.default_registry()
    monkeypatch.setattr(
        declarations_module,
        "default_registry",
        lambda: _RegistryMissing(real, kind, dropped),
    )


def test_an_operator_schema_that_drops_a_read_field_is_refused(monkeypatch) -> None:
    _redirect_registry(monkeypatch, "mutation-operator-spec", "risk_class")
    _run_refused("OPERATOR_CONTRACT_DRIFT", operator_contract)


def test_a_prompt_genome_schema_that_drops_a_written_field_is_refused(
    monkeypatch,
) -> None:
    _redirect_registry(monkeypatch, "prompt-genome", "template")
    _run_refused("PROMPT_GENOME_CONTRACT_DRIFT", prompt_genome_contract)


def test_a_proposal_schema_that_drops_its_status_field_is_refused(monkeypatch) -> None:
    _redirect_registry(monkeypatch, "prompt-mutation-proposal", "status")
    _run_refused("STATUS_CONTRACT_DRIFT", prompt_proposal_contract)


def test_a_search_space_that_no_longer_lists_the_prompt_genome_is_refused(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        declarations_module, "_sealed_search_space", lambda: ("hypothesis-genome",)
    )
    _run_refused("SEARCH_SPACE_DRIFT", mutable_prompt_genome_kind)


def test_a_governance_workflow_without_the_retroactivity_node_is_refused(
    monkeypatch, tmp_path
) -> None:
    workflow = tmp_path / workflow_module.GOVERNANCE_WORKFLOW
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("nodes:\n  - node_id: some_other_node\n", encoding="utf-8")
    monkeypatch.setattr(workflow_module, "repo_root", lambda: tmp_path)
    _run_refused("WORKFLOW_CONTRACT_DRIFT", governance_retroactivity_node)


# --- completeness --------------------------------------------------------


def test_every_declared_finding_code_was_exercised() -> None:
    """No finding code is declared without an adversarial test driving it."""
    assert EXERCISED == set(FINDING_CODES), {
        "untested": sorted(set(FINDING_CODES) - EXERCISED),
        "unknown": sorted(EXERCISED - set(FINDING_CODES)),
    }
