"""Skill activation gating and dispatch reconciliation."""

from __future__ import annotations

import pytest

from epistemic_foundry.security import (
    DispatchRefused,
    SkillActivationRefused,
    build_role_dispatch_plan,
    build_skill_lockfile,
    reconcile_dispatch,
    require_activation_allowed,
)
from epistemic_foundry.security.dispatch import dispatch_succeeded
from epistemic_foundry.security.skills import activation_blockers

PIN = "sha256:" + "a" * 64


def _skill(**overrides) -> dict:
    skill = {
        "name": "third-party-analyzer",
        "content_hash": PIN,
        "inspected": True,
        "approved": True,
        "quarantined": False,
        "permissions": ["read_corpus"],
    }
    skill.update(overrides)
    return skill


def _role(**overrides) -> dict:
    role = {
        "role_id": "ROLE-scout",
        "host_agent_type": "codex_cli",
        "model_tier": "balanced",
        "tool_acl": ["retrieval"],
        "evidence_acl": ["public"],
        "read_scope": ["corpus/**"],
        "write_scope": ["artifacts/scout/**"],
        "depends_on": [],
        "budget_tokens": 10000,
        "timeout_seconds": 600,
        "independence_group": "scout-group",
    }
    role.update(overrides)
    return role


def _lock_entry(**overrides) -> dict:
    """A lockfile entry carrying every canonical field."""
    entry = {
        "skill_id": "third-party-analyzer",
        "source": "https://example.com/skills/analyzer",
        "revision": "9f2c1ab4d5e6f70819a2b3c4d5e6f708192a3b4c",
        "content_hash": PIN,
        "signature_status": "VERIFIED",
        "license": "Apache-2.0",
        "permissions": ["read_corpus"],
        "review_status": "APPROVED",
        "approved_by_ids": ["HUMAN-1"],
        "inspected": True,
        "quarantined": False,
    }
    entry.update(overrides)
    return entry


# -- EF4-I21 skill quarantine -------------------------------------------


def test_i21_fully_vetted_skill_may_activate() -> None:
    require_activation_allowed(_skill())


def test_i21_unpinned_skill_is_refused() -> None:
    """An unpinned skill can change after the approval that authorized it."""
    with pytest.raises(SkillActivationRefused) as excinfo:
        require_activation_allowed(_skill(content_hash=None))
    assert "unpinned" in str(excinfo.value)


def test_i21_non_sha256_pin_is_refused() -> None:
    with pytest.raises(SkillActivationRefused) as excinfo:
        require_activation_allowed(_skill(content_hash="v1.2.3"))
    assert "not a sha256 pin" in str(excinfo.value)


def test_i21_quarantined_skill_is_refused() -> None:
    with pytest.raises(SkillActivationRefused):
        require_activation_allowed(_skill(quarantined=True))


def test_i21_uninspected_and_unapproved_are_refused() -> None:
    with pytest.raises(SkillActivationRefused):
        require_activation_allowed(_skill(inspected=False))
    with pytest.raises(SkillActivationRefused):
        require_activation_allowed(_skill(approved=False))


def test_i21_absent_permissions_are_not_treated_as_none() -> None:
    """Missing permissions must not be assumed unprivileged."""
    skill = _skill()
    del skill["permissions"]
    with pytest.raises(SkillActivationRefused) as excinfo:
        require_activation_allowed(skill)
    assert "not the same as none" in str(excinfo.value)


def test_i21_empty_permission_list_is_an_explicit_choice() -> None:
    require_activation_allowed(_skill(permissions=[]))


def test_i21_every_blocker_is_reported_at_once() -> None:
    blockers = activation_blockers(
        {"name": "bad", "inspected": False, "approved": False, "quarantined": True}
    )
    assert len(blockers) >= 4


def test_i21_lockfile_refuses_a_non_activatable_entry() -> None:
    """The lockfile is the activation authority; it cannot launder a bad entry."""
    with pytest.raises(SkillActivationRefused) as excinfo:
        build_skill_lockfile(
            workspace_id="WS-1",
            skills=[_lock_entry(), _lock_entry(skill_id="unpinned", content_hash=None)],
            policy_hash="sha256:" + "b" * 64,
        )
    assert "non-activatable" in str(excinfo.value)


def test_i21_review_without_a_named_approver_is_refused() -> None:
    """A review with no named approver leaves nobody accountable."""
    with pytest.raises(SkillActivationRefused) as excinfo:
        require_activation_allowed(_lock_entry(approved_by_ids=[]))
    assert "no approver" in str(excinfo.value)


def test_i21_pending_review_status_is_refused() -> None:
    with pytest.raises(SkillActivationRefused) as excinfo:
        require_activation_allowed(_lock_entry(review_status="PENDING"))
    assert "not APPROVED" in str(excinfo.value)


def test_i21_lockfile_seals_vetted_skills() -> None:
    lockfile = build_skill_lockfile(
        workspace_id="WS-1",
        skills=[_lock_entry()],
        policy_hash="sha256:" + "b" * 64,
    )
    assert lockfile["lock_hash"].startswith("sha256:")
    assert len(lockfile["skills"]) == 1


# -- EF4-I25 role dispatch ----------------------------------------------


def test_i25_plan_requires_a_complete_rolespec() -> None:
    role = _role()
    del role["evidence_acl"]
    with pytest.raises(DispatchRefused) as excinfo:
        build_role_dispatch_plan(session_id="FS-1", roles=[role], budget_envelope_id="BE-1")
    assert "evidence_acl" in str(excinfo.value)


@pytest.mark.parametrize(
    "field", ["tool_acl", "write_scope", "budget_tokens", "independence_group", "read_scope"]
)
def test_i25_every_acl_field_is_required(field: str) -> None:
    role = _role()
    del role[field]
    with pytest.raises(DispatchRefused) as excinfo:
        build_role_dispatch_plan(session_id="FS-1", roles=[role], budget_envelope_id="BE-1")
    assert field in str(excinfo.value)


def test_i25_expected_count_defaults_to_the_role_count() -> None:
    plan = build_role_dispatch_plan(
        session_id="FS-1", roles=[_role(), _role(role_id="ROLE-judge")], budget_envelope_id="BE-1"
    )
    assert plan["expected_count"] == 2


def test_i25_empty_plan_is_refused() -> None:
    with pytest.raises(DispatchRefused):
        build_role_dispatch_plan(session_id="FS-1", roles=[], budget_envelope_id="BE-1")


def _plan(**overrides) -> dict:
    kwargs = dict(
        session_id="FS-1",
        roles=[_role(), _role(role_id="ROLE-judge")],
        budget_envelope_id="BE-1",
    )
    kwargs.update(overrides)
    return build_role_dispatch_plan(**kwargs)


def test_i25_full_completion_reconciles() -> None:
    plan = _plan()
    summary = reconcile_dispatch(plan, completed_ids=["W1", "W2"])
    assert summary["reconciled"] is True
    assert dispatch_succeeded(plan, summary) is True


def test_i25_dropped_worker_is_reported_as_missing() -> None:
    """A silently dropped worker must not read as success."""
    plan = _plan()
    summary = reconcile_dispatch(plan, completed_ids=["W1"])
    assert summary["missing"] == 1
    assert summary["reconciled"] is False
    assert dispatch_succeeded(plan, summary) is False


def test_i25_failed_worker_is_accounted_but_not_success() -> None:
    plan = _plan()
    summary = reconcile_dispatch(plan, completed_ids=["W1"], failed_ids=["W2"])
    assert summary["reconciled"] is True
    assert dispatch_succeeded(plan, summary) is False


def test_i25_double_counted_identity_is_refused() -> None:
    plan = _plan()
    with pytest.raises(DispatchRefused) as excinfo:
        reconcile_dispatch(plan, completed_ids=["W1"], failed_ids=["W1"])
    assert "more than one outcome bucket" in str(excinfo.value)


def test_i25_over_reporting_is_not_success() -> None:
    plan = _plan()
    summary = reconcile_dispatch(plan, completed_ids=["W1", "W2", "W3"])
    assert summary["over_reported"] == 1
    assert dispatch_succeeded(plan, summary) is False


def test_i25_quorum_policy_accepts_partial_completion() -> None:
    plan = _plan(fan_in_policy="quorum_with_partial_label", missing_result_policy="partial_only")
    summary = reconcile_dispatch(plan, completed_ids=["W1"], failed_ids=["W2"])
    assert dispatch_succeeded(plan, summary) is True
