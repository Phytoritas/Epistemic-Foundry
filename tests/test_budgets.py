"""Budget labels bound spend, loops terminate, secrets stay opaque."""

from __future__ import annotations

import pytest

from epistemic_foundry.budgets import (
    BudgetViolation,
    LoopContractViolation,
    SecretHandle,
    SecretLeak,
    assert_no_secret_material,
    build_budget_envelope,
    build_loop_contract,
    loop_should_continue,
    spend_is_bounded,
)
from epistemic_foundry.budgets.envelope import requires_escalation_on_breach
from epistemic_foundry.budgets.loops import nonconvergence_outcome
from epistemic_foundry.budgets.secrets import handle_is_opaque

#: A deliberately synthetic marker standing in for secret material. It is not a
#: credential of any format; the leak checks only need a distinctive string.
FAKE_SECRET_MARKER = "SYNTHETIC-LEAK-CANARY-0001"


def _envelope(**overrides) -> dict:
    kwargs = dict(
        enforcement="HARD_METERED",
        hard_limits={"tokens": 500000, "wall_seconds": 3600},
        soft_cost_currency="USD",
        soft_cost_amount=25.0,
        metering_authority="provider-usage-api",
        breach_policy="PAUSE_AND_ESCALATE",
    )
    kwargs.update(overrides)
    return build_budget_envelope(**kwargs)


def _contract(**overrides) -> dict:
    kwargs = dict(
        workflow_id="WF-1",
        entry_node_id="N-entry",
        exit_node_id="N-exit",
        state_artifact_id="ART-state",
        convergence_metric="novel_candidates_per_round",
        convergence_predicate="novel_candidates_per_round == 0",
        max_iterations=10,
        max_cost_units=100.0,
        max_wall_seconds=3600,
        dry_rounds_required=2,
        dedupe_key="canonical_claim_hash",
    )
    kwargs.update(overrides)
    return build_loop_contract(**kwargs)


# -- EF4-I28 budget labelling -------------------------------------------


def test_i28_hard_metered_budget_bounds_spend() -> None:
    assert spend_is_bounded(_envelope()) is True


def test_i28_soft_estimate_does_not_bound_spend() -> None:
    """An estimate is a forecast, not a ceiling."""
    envelope = _envelope(enforcement="SOFT_ESTIMATE", hard_limits={}, breach_policy="WARN")
    assert spend_is_bounded(envelope) is False


def test_i28_unmetered_does_not_bound_spend() -> None:
    envelope = _envelope(enforcement="UNMETERED", hard_limits={}, breach_policy="WARN")
    assert spend_is_bounded(envelope) is False


def test_i28_hard_label_without_limits_is_refused() -> None:
    """The label would claim a bound nothing enforces."""
    with pytest.raises(BudgetViolation) as excinfo:
        _envelope(hard_limits={})
    assert "nothing enforces" in str(excinfo.value)


def test_i28_unmetered_cannot_cancel_on_breach() -> None:
    """With no meter there is nothing to detect a breach."""
    with pytest.raises(BudgetViolation) as excinfo:
        _envelope(enforcement="UNMETERED", hard_limits={}, breach_policy="CANCEL")
    assert "nothing to detect a breach" in str(excinfo.value)


def test_i28_misnamed_limit_dimension_is_refused() -> None:
    """A typo would sit in the envelope looking like a bound while enforcing nothing."""
    with pytest.raises(BudgetViolation) as excinfo:
        _envelope(hard_limits={"max_tokens": 500000})
    assert "enforces nothing" in str(excinfo.value)


def test_i28_unspecified_dimensions_become_explicit_nulls() -> None:
    envelope = _envelope()
    assert envelope["hard_limits"]["tokens"] == 500000
    assert envelope["hard_limits"]["concurrency"] is None
    assert set(envelope["hard_limits"]) == {
        "tokens",
        "calls",
        "wall_seconds",
        "concurrency",
        "storage_bytes",
        "network_bytes",
    }


def test_i28_escalating_breach_policy_is_reported() -> None:
    assert requires_escalation_on_breach(_envelope()) is True
    warn_only = _envelope(enforcement="SOFT_ESTIMATE", hard_limits={}, breach_policy="WARN")
    assert requires_escalation_on_breach(warn_only) is False


# -- EF4-I27 loop termination -------------------------------------------


def test_i27_contract_carries_every_stop_condition() -> None:
    contract = _contract()
    for field in (
        "max_iterations",
        "max_cost_units",
        "max_wall_seconds",
        "dry_rounds_required",
        "dedupe_key",
        "seen_set_scope",
        "on_nonconvergence",
    ):
        assert field in contract


def test_i27_loop_runs_within_all_bounds() -> None:
    keep, reason = loop_should_continue(
        _contract(), iteration=1, cost_units=5.0, wall_seconds=60, consecutive_dry_rounds=0
    )
    assert keep is True
    assert reason == "within all bounds"


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"iteration": 10}, "max_iterations"),
        ({"cost_units": 100.0}, "max_cost_units"),
        ({"wall_seconds": 3600}, "max_wall_seconds"),
        ({"consecutive_dry_rounds": 2}, "dry round"),
    ],
)
def test_i27_each_bound_independently_stops_the_loop(kwargs: dict, expected: str) -> None:
    base = {"iteration": 0, "cost_units": 0.0, "wall_seconds": 0, "consecutive_dry_rounds": 0}
    base.update(kwargs)
    keep, reason = loop_should_continue(_contract(), **base)
    assert keep is False
    assert expected in reason


def test_i27_dry_rounds_catch_a_spinning_loop() -> None:
    """Rediscovering seen candidates is spinning, not progress."""
    keep, reason = loop_should_continue(
        _contract(), iteration=1, cost_units=1.0, wall_seconds=1, consecutive_dry_rounds=5
    )
    assert keep is False
    assert "no novel candidate" in reason


def test_i27_missing_dedupe_key_is_refused() -> None:
    with pytest.raises(LoopContractViolation) as excinfo:
        _contract(dedupe_key="  ")
    assert "novelty cannot be distinguished from rediscovery" in str(excinfo.value)


@pytest.mark.parametrize("field", ["max_iterations", "max_cost_units", "max_wall_seconds"])
def test_i27_non_positive_bound_is_refused(field: str) -> None:
    with pytest.raises(LoopContractViolation) as excinfo:
        _contract(**{field: 0})
    assert "leaves the loop unbounded" in str(excinfo.value)


def test_i27_zero_dry_rounds_is_refused() -> None:
    with pytest.raises(LoopContractViolation):
        _contract(dry_rounds_required=0)


def test_i27_nonconvergence_outcome_is_declared() -> None:
    assert nonconvergence_outcome(_contract()) == "ESCALATE"
    assert nonconvergence_outcome(_contract(on_nonconvergence="BLOCK")) == "BLOCK"


# -- EF4-I29 secret opacity ---------------------------------------------


def test_i29_handle_never_renders_the_material() -> None:
    """The usual leak path is an f-string or a log line."""
    handle = SecretHandle("PROVIDER_TOKEN_REF")
    assert handle_is_opaque(handle, FAKE_SECRET_MARKER) is True
    assert FAKE_SECRET_MARKER not in f"{handle}"
    assert FAKE_SECRET_MARKER not in repr(handle)


def test_i29_handle_stores_no_value() -> None:
    handle = SecretHandle("PROVIDER_TOKEN_REF")
    assert not hasattr(handle, "value")
    assert set(SecretHandle.__slots__) == {"_reference", "_provider"}


def test_i29_empty_reference_is_refused() -> None:
    with pytest.raises(ValueError):
        SecretHandle("   ")


def test_i29_material_in_an_outbound_prompt_is_refused() -> None:
    payload = {"prompt": f"authenticate with {FAKE_SECRET_MARKER}"}
    with pytest.raises(SecretLeak) as excinfo:
        assert_no_secret_material(payload, known_secret_values=[FAKE_SECRET_MARKER])
    assert "opaque handles" in str(excinfo.value)


def test_i29_material_nested_in_an_artifact_is_refused() -> None:
    payload = {"evidence": {"notes": ["see config", f"ref={FAKE_SECRET_MARKER}"]}}
    with pytest.raises(SecretLeak):
        assert_no_secret_material(payload, known_secret_values=[FAKE_SECRET_MARKER])


def test_i29_handle_in_a_payload_is_allowed() -> None:
    payload = {"credential_ref": str(SecretHandle("PROVIDER_TOKEN_REF"))}
    assert_no_secret_material(payload, known_secret_values=[FAKE_SECRET_MARKER])


def test_i29_leak_raises_rather_than_redacting() -> None:
    """Silent redaction would hide that a path tried to send secret material."""
    payload = {"log": FAKE_SECRET_MARKER}
    with pytest.raises(SecretLeak):
        assert_no_secret_material(payload, known_secret_values=[FAKE_SECRET_MARKER])
    assert payload["log"] == FAKE_SECRET_MARKER  # unchanged: the caller must fix the path
