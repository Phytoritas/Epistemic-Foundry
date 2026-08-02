"""negative_and_adversarial_tests — every refusal fires for the stated reason.

The gate's value is in what it will not admit.  Each test here drives one
declared refusal and asserts the gate raises with exactly the finding code that
names it, so a future change that silences a guard or renames a code fails here
rather than shipping an application that applied an unqualified prompt, rewrote a
completed run, or overran its context budget.  Every finding code in
``FINDING_CODES`` is exercised by at least one test below.
"""

from __future__ import annotations

import copy

import pytest
from epistemic_foundry.operators.v4_j06 import (
    FINDING_CODES,
    ContextBudgetGateError,
    admit_operator_application,
    assess_context_budget,
    verify_gate_receipt,
)
from epistemic_foundry.operators.v4_j06 import declarations as decl
from fixtures import (
    SOURCE_RUN,
    admission_arguments,
    budget_envelope,
    context_manifest,
    hypothesis_admission_arguments,
    quarantined_registry,
    unmetered_budget,
)


def _refused(code: str, call) -> ContextBudgetGateError:
    with pytest.raises(ContextBudgetGateError) as caught:
        call()
    assert caught.value.code == code, (
        f"expected {code}, got {caught.value.code}: {caught.value}"
    )
    return caught.value


# --- qualification refusals ----------------------------------------------


def test_an_unregistered_operator_is_refused() -> None:
    _refused(
        "OPERATOR_UNREGISTERED",
        lambda: admit_operator_application(
            **admission_arguments(operator_id="MOP-J06-NONE")
        ),
    )


def test_a_quarantined_prompt_operator_is_refused() -> None:
    _refused(
        "PROMPT_QUARANTINED",
        lambda: admit_operator_application(
            **admission_arguments(registry=quarantined_registry())
        ),
    )


def test_a_prompt_operator_binding_no_evidence_is_unqualified() -> None:
    _refused(
        "OPERATOR_UNQUALIFIED",
        lambda: admit_operator_application(
            **admission_arguments(qualification_evidence_ids=[])
        ),
    )


def test_applying_a_prompt_to_the_run_that_produced_it_is_retroactive() -> None:
    # The proposal is released and the evidence is bound, so the only thing wrong
    # is that the target run is the source run: a future-run-only rule.
    _refused(
        "RETROACTIVE_APPLICATION",
        lambda: admit_operator_application(
            **admission_arguments(target_run_id=SOURCE_RUN, source_run_id=SOURCE_RUN)
        ),
    )


def test_a_prompt_operator_without_a_source_run_is_invalid() -> None:
    _refused(
        "INPUT_INVALID",
        lambda: admit_operator_application(**admission_arguments(source_run_id=None)),
    )


def test_a_non_prompt_operator_given_prompt_qualification_is_invalid() -> None:
    _refused(
        "INPUT_INVALID",
        lambda: admit_operator_application(
            **hypothesis_admission_arguments(
                source_run_id=SOURCE_RUN, qualification_evidence_ids=["Q-1"]
            )
        ),
    )


def test_a_registry_of_the_wrong_type_is_invalid() -> None:
    _refused(
        "INPUT_INVALID",
        lambda: admit_operator_application(
            **admission_arguments(registry={"not": "a registry"})
        ),
    )


# --- context-budget refusals ---------------------------------------------


def test_work_over_the_token_ceiling_is_refused() -> None:
    over = context_manifest(
        instruction_tokens=9000, evidence_tokens=2000, tool_tokens=100
    )
    error = _refused(
        "CONTEXT_OVER_BUDGET",
        lambda: assess_context_budget(
            context_manifest=over,
            budget_envelope=budget_envelope(hard_limits={"tokens": 1000}),
        ),
    )
    assert error.context["total_tokens"] == 11100


def test_the_gate_refuses_admission_when_work_is_over_budget() -> None:
    over = context_manifest(
        instruction_tokens=9000, evidence_tokens=2000, tool_tokens=100
    )
    _refused(
        "CONTEXT_OVER_BUDGET",
        lambda: admit_operator_application(
            **admission_arguments(
                context_manifest=over,
                budget_envelope=budget_envelope(hard_limits={"tokens": 1000}),
            )
        ),
    )


def test_an_unmetered_budget_bounds_nothing() -> None:
    _refused(
        "BUDGET_UNENFORCED",
        lambda: assess_context_budget(
            context_manifest=context_manifest(), budget_envelope=unmetered_budget()
        ),
    )


def test_a_bounded_budget_with_no_token_ceiling_is_unenforced() -> None:
    # HARD_METERED with a non-token limit bounds spend in general but names no
    # token ceiling, so the context-token gate has nothing to meter against.
    envelope = budget_envelope(hard_limits={"wall_seconds": 600})
    _refused(
        "BUDGET_UNENFORCED",
        lambda: assess_context_budget(
            context_manifest=context_manifest(), budget_envelope=envelope
        ),
    )


def test_an_understated_total_is_inconsistent_accounting() -> None:
    # The three components sum to 350 but the manifest claims 100: an adversary
    # understating the total to slip under the ceiling is caught by re-derivation.
    manifest = context_manifest(
        instruction_tokens=100, evidence_tokens=200, tool_tokens=50, total_tokens=100
    )
    _refused(
        "CONTEXT_ACCOUNTING_INCONSISTENT",
        lambda: assess_context_budget(
            context_manifest=manifest, budget_envelope=budget_envelope()
        ),
    )


def test_a_malformed_context_manifest_is_refused() -> None:
    manifest = context_manifest()
    del manifest["token_accounting"]
    _refused(
        "CONTEXT_MANIFEST_MALFORMED",
        lambda: assess_context_budget(
            context_manifest=manifest, budget_envelope=budget_envelope()
        ),
    )


def test_a_schema_invalid_budget_is_malformed() -> None:
    envelope = budget_envelope()
    del envelope["enforcement"]
    _refused(
        "BUDGET_MALFORMED",
        lambda: assess_context_budget(
            context_manifest=context_manifest(), budget_envelope=envelope
        ),
    )


def test_a_budget_whose_digest_does_not_re_derive_is_malformed() -> None:
    # Schema-valid but tampered after sealing: the soft cost was raised without
    # re-hashing, so the digest no longer covers the fields it publishes.
    envelope = budget_envelope()
    envelope["soft_cost_amount"] = envelope["soft_cost_amount"] + 1.0
    _refused(
        "BUDGET_MALFORMED",
        lambda: assess_context_budget(
            context_manifest=context_manifest(), budget_envelope=envelope
        ),
    )


def test_a_non_mapping_manifest_is_invalid() -> None:
    _refused(
        "INPUT_INVALID",
        lambda: assess_context_budget(
            context_manifest=["not", "a", "mapping"], budget_envelope=budget_envelope()
        ),
    )


# --- receipt and contract-drift refusals ---------------------------------


def test_a_tampered_receipt_is_refused() -> None:
    receipt = admit_operator_application(**admission_arguments())
    receipt["target_run_id"] = "ERUN-FORGED"
    _refused("GATE_RECEIPT_DRIFT", lambda: verify_gate_receipt(receipt))


def test_a_context_schema_missing_a_token_field_is_contract_drift(monkeypatch) -> None:
    real = decl.default_registry()
    stripped = copy.deepcopy(real.document(decl.CONTEXT_MANIFEST_KIND))
    del stripped["properties"][decl.TOKEN_ACCOUNTING_FIELD]["properties"][
        decl.TOTAL_TOKENS_FIELD
    ]

    class Stub:
        def document(self, kind):
            return (
                stripped if kind == decl.CONTEXT_MANIFEST_KIND else real.document(kind)
            )

    monkeypatch.setattr(decl, "default_registry", lambda: Stub())
    _refused("CONTEXT_CONTRACT_DRIFT", decl.context_accounting_contract)


def test_a_budget_schema_missing_the_token_ceiling_is_contract_drift(
    monkeypatch,
) -> None:
    real = decl.default_registry()
    stripped = copy.deepcopy(real.document(decl.BUDGET_ENVELOPE_KIND))
    del stripped["properties"][decl.HARD_LIMITS_FIELD]["properties"][
        decl.TOKENS_DIMENSION
    ]

    class Stub:
        def document(self, kind):
            return (
                stripped if kind == decl.BUDGET_ENVELOPE_KIND else real.document(kind)
            )

    monkeypatch.setattr(decl, "default_registry", lambda: Stub())
    _refused("BUDGET_CONTRACT_DRIFT", decl.budget_envelope_contract)


# --- completeness ---------------------------------------------------------


def test_every_declared_finding_code_is_exercised_here() -> None:
    # A guard rail on the suite itself: the source of this module must name every
    # finding code, so a code added without a negative test fails here.
    from pathlib import Path

    source = Path(__file__).read_text(encoding="utf-8")
    unexercised = sorted(code for code in FINDING_CODES if f'"{code}"' not in source)
    assert not unexercised, unexercised
