from __future__ import annotations

import json
from pathlib import Path

import pytest

from .compiler import FrameContractError, compile_frame


ROOT = Path(__file__).resolve().parents[4]


def eligible_sample() -> dict[str, object]:
    value = json.loads((ROOT / "examples/sample_insight.json").read_text(encoding="utf-8"))
    value["terms_to_define"] = []
    return value


def test_falsifier_gate_test_complete_card_is_council_ready() -> None:
    result = compile_frame(eligible_sample())

    assert result.council_ready is True
    assert result.council_blockers == ()


def test_falsifier_gate_test_missing_falsifier_fails_closed() -> None:
    proposal = eligible_sample()
    del proposal["falsifiers"]

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FALSIFIER_REQUIRED"


def test_falsifier_gate_test_empty_falsifier_array_fails_closed() -> None:
    proposal = eligible_sample()
    proposal["falsifiers"] = []

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FALSIFIER_REQUIRED"


def test_falsifier_gate_test_blank_falsifier_fails_closed() -> None:
    proposal = eligible_sample()
    proposal["falsifiers"] = ["   "]

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FALSIFIER_REQUIRED"


def test_falsifier_gate_test_scalar_falsifier_fails_closed() -> None:
    proposal = eligible_sample()
    proposal["falsifiers"] = "no effect"

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FALSIFIER_REQUIRED"


def test_falsifier_gate_test_prediction_is_also_mandatory() -> None:
    proposal = eligible_sample()
    proposal["predictions"] = []

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_INPUT_INVALID"


def test_falsifier_gate_test_mechanism_is_also_mandatory() -> None:
    proposal = eligible_sample()
    proposal["mechanism_path"] = []

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_INPUT_INVALID"


def test_falsifier_gate_test_eligible_card_cannot_hide_required_scope_unknowns() -> None:
    proposal = eligible_sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["population"] = None

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_ELIGIBILITY_CONFLICT"
    assert raised.value.details is not None
    assert raised.value.details["blockers"] == ["COUNCIL_SCOPE_POPULATION_UNKNOWN"]


def test_falsifier_gate_test_eligible_card_cannot_hide_undefined_constructs() -> None:
    proposal = eligible_sample()
    proposal["terms_to_define"] = ["durable retention"]

    with pytest.raises(FrameContractError) as raised:
        compile_frame(proposal)

    assert raised.value.code == "FRAME_ELIGIBILITY_CONFLICT"
    assert raised.value.details is not None
    assert raised.value.details["blockers"] == ["COUNCIL_UNDEFINED_CONSTRUCTS"]


def test_falsifier_gate_test_inbox_preserves_unknowns_but_cannot_enter_council() -> None:
    proposal = eligible_sample()
    proposal["registration_status"] = "inbox"
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["population"] = None

    result = compile_frame(proposal)

    assert result.council_ready is False
    assert result.council_blockers == (
        "COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE",
        "COUNCIL_SCOPE_POPULATION_UNKNOWN",
    )
    assert result.scope_vector["population"] is None


def test_falsifier_gate_test_withdrawn_card_never_reenters_council() -> None:
    proposal = eligible_sample()
    proposal["registration_status"] = "withdrawn"

    result = compile_frame(proposal)

    assert result.council_ready is False
    assert result.council_blockers == ("COUNCIL_REGISTRATION_STATUS_NOT_ELIGIBLE",)


def test_falsifier_gate_test_optional_unknown_scope_axes_do_not_broaden_claim() -> None:
    proposal = eligible_sample()
    scope = proposal["scope"]
    assert isinstance(scope, dict)
    scope["geography"] = None
    scope["jurisdiction"] = None

    result = compile_frame(proposal)

    assert result.council_ready is True
    assert result.scope_vector["geography"] is None
    assert result.scope_vector["jurisdiction"] is None
