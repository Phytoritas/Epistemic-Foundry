"""Recall scope, workspace isolation, honest result states, ranking integrity."""

from __future__ import annotations

import pytest

from epistemic_foundry.memory import (
    MemoryScopeViolation,
    build_memory_policy,
    build_retrieval_receipt,
    require_recall_permitted,
)
from epistemic_foundry.observability import (
    RankingIntegrityError,
    ResultState,
    classify_result,
    is_empty_research_finding,
    require_declared_ranking,
)
from epistemic_foundry.observability.result_state import (
    ResultStateViolation,
    require_honest_state,
    supports_absence_claim,
)


def _policy(**overrides) -> dict:
    kwargs = dict(
        workspace_id="WS-1",
        allowed_classes=["SESSION", "WORKSPACE"],
        default_retention_days=90,
        class_rules=[
            {
                "class": "SESSION",
                "retention_days": 30,
                "requires_consent": False,
                "external_sync": "DENY",
                "redaction_profile": "none",
            },
            {
                "class": "WORKSPACE",
                "retention_days": 90,
                "requires_consent": True,
                "external_sync": "DENY",
                "redaction_profile": "pii-strip",
            },
        ],
        effective_at="2026-01-01T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return build_memory_policy(**kwargs)


def _recall(policy: dict, **overrides) -> None:
    kwargs = dict(
        workspace_id="WS-1",
        requested_classes=["WORKSPACE"],
        purpose="reconstruct prior reasoning for this hypothesis",
        consent_id="CONSENT-1",
        age_days=10,
    )
    kwargs.update(overrides)
    require_recall_permitted(policy, **kwargs)


# -- EF4-I18 recall scope -----------------------------------------------


def test_i18_in_scope_recall_is_permitted() -> None:
    _recall(_policy())


def test_i18_disallowed_class_is_refused() -> None:
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _recall(_policy(), requested_classes=["REGULATED"])
    assert "not in the policy allowed set" in str(excinfo.value)


def test_i18_unknown_memory_class_cannot_be_declared() -> None:
    """A plausible-sounding class the policy cannot express is refused."""
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _policy(allowed_classes=["episodic"])
    assert "unknown memory class" in str(excinfo.value)


def test_i18_expired_memory_is_out_of_scope() -> None:
    """Retention is checked even for an allowed class."""
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _recall(_policy(), age_days=400)
    assert "retention window" in str(excinfo.value)


def test_i18_recall_without_consent_is_refused() -> None:
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _recall(_policy(), consent_id=None)
    assert "consent id" in str(excinfo.value)


def test_i18_recall_without_purpose_is_refused() -> None:
    with pytest.raises(MemoryScopeViolation):
        _recall(_policy(), purpose="   ")


def test_i18_empty_allowed_class_list_is_a_construction_bug() -> None:
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _policy(allowed_classes=[])
    assert "construction bug" in str(excinfo.value)


# -- EF4-I19 workspace isolation ----------------------------------------


def test_i19_cross_workspace_recall_is_denied_by_default() -> None:
    policy = _policy()
    assert policy["cross_workspace_retrieval"] == "DENY"
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _recall(policy, target_workspace_id="WS-other")
    assert "denied by policy" in str(excinfo.value)


def test_i19_explicit_only_requires_naming_the_foreign_workspace() -> None:
    policy = _policy(cross_workspace_retrieval="EXPLICIT_ONLY")
    _recall(policy, target_workspace_id="WS-other")
    with pytest.raises(MemoryScopeViolation) as excinfo:
        _recall(policy, workspace_id="WS-other", target_workspace_id=None)
    assert "named explicitly" in str(excinfo.value)


def test_i19_allow_by_policy_permits_cross_workspace() -> None:
    _recall(_policy(cross_workspace_retrieval="ALLOW_BY_POLICY"), target_workspace_id="WS-other")


def test_retrieval_receipt_records_excluded_classes() -> None:
    """A reader must see the boundary of the search, not only its yield."""
    receipt = build_retrieval_receipt(
        query="prior spacing findings",
        workspace_id="WS-1",
        purpose="recall",
        searched_classes=["WORKSPACE"],
        excluded_classes=["REGULATED", "USER"],
        hits=[],
        consent_id="CONSENT-1",
        context_capsule_id="CC-1",
    )
    assert receipt["excluded_classes"] == ["REGULATED", "USER"]
    assert receipt["result_hash"].startswith("sha256:")


# -- EF4-I23 result-state honesty ---------------------------------------


def test_i23_four_result_states_stay_distinct() -> None:
    assert len({state.value for state in ResultState}) == 4


def test_i23_backend_failure_is_unavailable_not_empty() -> None:
    """An empty list from a failed call carries no information about the world."""
    state = classify_result(backend_reachable=False, backend_error="connection reset", results=[])
    assert state is ResultState.UNAVAILABLE
    assert is_empty_research_finding(state) is False


def test_i23_confirmed_empty_is_a_real_finding() -> None:
    state = classify_result(backend_reachable=True, backend_error=None, results=[])
    assert state is ResultState.EMPTY_CONFIRMED
    assert is_empty_research_finding(state) is True


def test_i23_degraded_does_not_support_an_absence_claim() -> None:
    state = classify_result(
        backend_reachable=True, backend_error=None, results=["r1"], partial=True
    )
    assert state is ResultState.DEGRADED
    assert supports_absence_claim(state) is False


def test_i23_reporting_a_failure_as_a_finding_is_refused() -> None:
    with pytest.raises(ResultStateViolation) as excinfo:
        require_honest_state(ResultState.EMPTY_CONFIRMED, backend_error="timeout")
    assert "must not be presented as a research finding" in str(excinfo.value)


def test_i23_honest_unavailable_passes_the_check() -> None:
    require_honest_state(ResultState.UNAVAILABLE, backend_error="timeout")


# -- EF4-I24 ranking integrity ------------------------------------------


def _entry(**overrides) -> dict:
    entry = {"baseline_centrality": 0.4, "query_relevance": 0.8, "risk": 0.1}
    entry.update(overrides)
    return entry


def test_i24_declared_algorithm_with_separate_signals_is_accepted() -> None:
    require_declared_ranking(labeled_ranked=True, algorithm="pagerank", entries=[_entry()])


def test_i24_unranked_output_needs_no_algorithm() -> None:
    require_declared_ranking(labeled_ranked=False, algorithm=None, entries=[{}])


def test_i24_ranked_label_without_an_algorithm_is_refused() -> None:
    with pytest.raises(RankingIntegrityError) as excinfo:
        require_declared_ranking(labeled_ranked=True, algorithm=None, entries=[_entry()])
    assert "cannot be reproduced or challenged" in str(excinfo.value)


def test_i24_insertion_order_is_not_a_ranking() -> None:
    """Calling arrival order a ranking invents authority the ordering lacks."""
    with pytest.raises(RankingIntegrityError) as excinfo:
        require_declared_ranking(labeled_ranked=True, algorithm="insertion_order", entries=[_entry()])
    assert "invents an" in str(excinfo.value)


def test_i24_unknown_algorithm_is_refused() -> None:
    with pytest.raises(RankingIntegrityError):
        require_declared_ranking(labeled_ranked=True, algorithm="vibes", entries=[_entry()])


@pytest.mark.parametrize("dropped", ["baseline_centrality", "query_relevance", "risk"])
def test_i24_blended_score_hiding_a_signal_is_refused(dropped: str) -> None:
    entry = _entry()
    del entry[dropped]
    with pytest.raises(RankingIntegrityError) as excinfo:
        require_declared_ranking(labeled_ranked=True, algorithm="pagerank", entries=[entry])
    assert dropped in str(excinfo.value)
