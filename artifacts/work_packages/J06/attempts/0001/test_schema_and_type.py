"""schema_and_type_check — the gate is bound to the canonical schemas it reads.

J06 is an integration gate, so what this file checks is that the gate reads its
two direct contracts — the context assembly manifest and the budget envelope —
from the canonical schemas rather than from a private copy of their vocabulary
(EF4-I22), and that the qualification vocabulary it composes belongs to the
sealed J05/S05 surfaces rather than being restated here.  Because the gate
re-derives all of this on each call, a schema rename closes the gate here instead
of letting it meter a field the contract no longer declares.
"""

from __future__ import annotations

import pytest
from epistemic_foundry.contracts import default_registry
from epistemic_foundry.operators.v4_j06 import (
    BUDGET_ENVELOPE_KIND,
    CONTEXT_MANIFEST_KIND,
    FINDING_CODES,
    ContextBudgetGateError,
    budget_envelope_contract,
    context_accounting_contract,
)
from epistemic_foundry.operators.v4_j06.declarations import (
    COMPONENT_TOKEN_FIELDS,
    ENFORCEMENT_FIELD,
    HARD_LIMITS_FIELD,
    TOKEN_ACCOUNTING_FIELD,
    TOKENS_DIMENSION,
    TOTAL_TOKENS_FIELD,
)
from fixtures import budget_envelope, context_manifest


def test_the_finding_codes_are_documented_and_nonempty() -> None:
    assert FINDING_CODES
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert isinstance(reason, str) and reason.strip()


def test_the_four_core_refusals_are_declared() -> None:
    for code in (
        "OPERATOR_UNQUALIFIED",
        "PROMPT_QUARANTINED",
        "RETROACTIVE_APPLICATION",
        "CONTEXT_OVER_BUDGET",
    ):
        assert code in FINDING_CODES


def test_the_context_manifest_schema_declares_the_metered_token_fields() -> None:
    document = context_accounting_contract()
    accounting = document["properties"][TOKEN_ACCOUNTING_FIELD]["properties"]
    for field in (*COMPONENT_TOKEN_FIELDS, TOTAL_TOKENS_FIELD):
        assert field in accounting, field


def test_the_budget_schema_declares_the_token_ceiling_and_enforcement() -> None:
    document = budget_envelope_contract()
    assert TOKENS_DIMENSION in document["properties"][HARD_LIMITS_FIELD]["properties"]
    assert ENFORCEMENT_FIELD in document["properties"]


def test_the_gate_reads_the_canonical_schema_names_not_a_copy() -> None:
    # The gate names its contracts by schema name and the registry resolves them,
    # so a missing schema would fail here rather than being silently tolerated.
    names = set(default_registry().names())
    assert CONTEXT_MANIFEST_KIND in names
    assert BUDGET_ENVELOPE_KIND in names


def test_the_fixtures_validate_against_their_canonical_schemas() -> None:
    default_registry().document(CONTEXT_MANIFEST_KIND)
    # validate_artifact is exercised through the gate; here we prove the fixtures
    # are the shape the schema accepts so later suites test the gate, not them.
    from epistemic_foundry.contracts import validate_artifact

    validate_artifact(CONTEXT_MANIFEST_KIND, context_manifest())
    validate_artifact(BUDGET_ENVELOPE_KIND, budget_envelope())


def test_a_wrong_finding_code_is_itself_refused_as_invalid() -> None:
    from epistemic_foundry.operators.v4_j06.declarations import _fail

    with pytest.raises(ContextBudgetGateError) as caught:
        _fail("NOT_A_REAL_CODE", "should not classify")
    assert caught.value.code == "INPUT_INVALID"
