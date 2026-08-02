"""sandbox_escape_test — an adapter reaches only what its manifest declares.

EF4-I64 under test: candidate code executes only under declared capabilities,
resource quotas, network policy, effect receipts and evaluator/holdout
isolation.  Every route out of the sandbox is tried here — a path that leaves
its root, a capability the manifest never asked for, a lease that no longer
holds, egress the policy forbids, and reach into the evaluator or a hidden
partition — and each one has to fail with the code that stopped it rather than
degrade into a permissive default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .contracts import (
    APPROVAL_RULE,
    BREACH_ACTION,
    ENFORCEMENT_STRENGTH,
    NETWORK_POLICY_RULE,
    SAFETY_CLASS_METERING,
    Denial,
    SandboxGateError,
    approval_policies,
    authorize_invocation,
    breach_policies,
    data_classes,
    enforcement_modes,
    isolation_boundaries,
    network_policies,
    safety_classes,
    seal_adapter,
    seal_quota_envelope,
    target_manifest_fields,
    unblinding_requires_approval,
    verify_isolation,
)

ROOT = Path(__file__).resolve().parents[4]
NOW = "2026-08-01T12:00:00Z"
EVALUATOR = "EVAL-1"
HIDDEN = "holdout-hidden-1"


def manifest(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "allowed_data_classes": ["internal", "public"],
        "approval_policy": "high_risk_only",
        "artifact_hashes": ["sha256:" + "a" * 64],
        "capability_requirements": ["fs.read", "net.fetch"],
        "constraints": [],
        "entrypoint": "run.py",
        "identifiability_notes": [],
        "inputs": [],
        "interface_version": "1.0.0",
        "network_policy": "allowlist",
        "outputs": [],
        "parameters": [],
        "provenance_manifest_id": "PROV-1",
        "reproducibility_contract": {
            "container_digest_required": True,
            "environment_capture": True,
            "seed_control": True,
        },
        "safety_class": "bounded_compute",
        "sandbox_profile": "profile-strict",
        "state_variables": [],
        "supply_chain_attestation_artifact_id": "ATT-1",
        "supported_actions": ["simulate"],
        "target_id": "solver-a",
        "target_type": "simulation_model",
        "validation_scope": {},
        "version": "1.2.3",
    }
    payload.update(overrides)
    return payload


def envelope(**overrides: Any) -> dict[str, Any]:
    limits: dict[str, Any] = {
        "calls": 4,
        "concurrency": 1,
        "network_bytes": 1_024,
        "storage_bytes": 4_096,
        "tokens": None,
        "wall_seconds": 30,
    }
    limits.update(overrides.pop("hard_limits", {}))
    payload: dict[str, Any] = {
        "breach_policy": "CANCEL",
        "budget_id": "BUD-1",
        "enforcement": "HARD_METERED",
        "hard_limits": limits,
    }
    payload.update(overrides)
    return payload


def holdout(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "adversarial_partition_handles": ["holdout-adv-1"],
        "backend_access": False,
        "candidate_access": False,
        "evaluator_id": EVALUATOR,
        "hidden_partition_handles": [HIDDEN],
        "holdout_id": "HOLD-1",
        "mutation_model_access": False,
        "ood_partition_handles": ["holdout-ood-1"],
        "prompt_access": False,
    }
    payload.update(overrides)
    return payload


def lease(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "approval_ids": ["APR-1"],
        "capabilities": ["fs.read", "net.fetch"],
        "expires_at": "2026-08-01T18:00:00Z",
        "lease_id": "LEASE-1",
        "principal_id": "tool-runner",
        "principal_type": "tool",
        "resource_scopes": ["workspace"],
        "revoked": False,
    }
    payload.update(overrides)
    return payload


def request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "approval_record_ids": [],
        "capabilities": ["fs.read"],
        "data_class": "internal",
        "network_url": None,
        "paths": [
            {
                "operation": "read",
                "relative_path": "inputs/run.json",
                "root_id": "workspace",
            }
        ],
        "principal_id": "tool-runner",
        "principal_type": "tool",
    }
    payload.update(overrides)
    return payload


def authorize(**overrides: Any):
    return authorize_invocation(
        ROOT,
        adapter=overrides.pop("adapter", None) or seal_adapter(ROOT, manifest()),
        lease=overrides.pop("lease", None) or lease(),
        holdout=overrides.pop("holdout", None) or holdout(),
        request=overrides.pop("request", None) or request(),
        now=overrides.pop("now", NOW),
    )


def denied(**overrides: Any) -> SandboxGateError:
    with pytest.raises(SandboxGateError) as caught:
        authorize(**overrides)
    return caught.value


def test_a_declared_invocation_is_admitted_and_names_what_it_allowed() -> None:
    decision = authorize()

    assert decision.adapter_id == "solver-a"
    assert decision.sandbox_profile == "profile-strict"
    assert decision.granted_capabilities == ("fs.read",)
    assert decision.granted_roots == ("workspace",)
    assert decision.egress_origin is None


def test_the_decision_reports_the_boundaries_the_holdout_schema_pins() -> None:
    decision = authorize()

    assert decision.isolation_verified == isolation_boundaries(ROOT)
    assert "candidate_access" in decision.isolation_verified


def test_the_local_decision_tables_match_the_schemas_that_declare_them() -> None:
    assert set(NETWORK_POLICY_RULE) == set(network_policies(ROOT))
    assert set(APPROVAL_RULE) == set(approval_policies(ROOT))
    assert set(SAFETY_CLASS_METERING) == set(safety_classes(ROOT))
    assert set(ENFORCEMENT_STRENGTH) == set(enforcement_modes(ROOT))
    assert set(BREACH_ACTION) == set(breach_policies(ROOT))
    for gated in APPROVAL_RULE.values():
        assert set(gated) <= set(safety_classes(ROOT))


def test_a_holdout_that_grants_candidate_access_contradicts_its_own_schema() -> None:
    with pytest.raises(SandboxGateError) as caught:
        verify_isolation(ROOT, holdout(candidate_access=True))

    assert caught.value.code == Denial.ISOLATION_BREACH.value
    assert caught.value.context["boundary"] == "candidate_access"


def test_a_sandboxed_principal_cannot_reach_a_hidden_partition() -> None:
    error = denied(
        lease=lease(resource_scopes=["workspace", HIDDEN]),
        request=request(
            paths=[{"operation": "read", "relative_path": "x.json", "root_id": HIDDEN}]
        ),
    )

    assert error.code == Denial.ISOLATION_BREACH.value
    assert error.context["root_id"] == HIDDEN


def test_a_sandboxed_principal_cannot_reach_the_evaluator() -> None:
    error = denied(
        lease=lease(resource_scopes=["workspace", EVALUATOR]),
        request=request(
            paths=[
                {"operation": "read", "relative_path": "x.json", "root_id": EVALUATOR}
            ]
        ),
    )

    assert error.code == Denial.ISOLATION_BREACH.value


def test_an_approval_does_not_buy_a_sandboxed_principal_past_isolation() -> None:
    error = denied(
        lease=lease(resource_scopes=["workspace", HIDDEN]),
        request=request(
            approval_record_ids=["APR-1"],
            paths=[{"operation": "read", "relative_path": "x.json", "root_id": HIDDEN}],
        ),
    )

    assert error.code == Denial.ISOLATION_BREACH.value


def test_a_human_principal_still_needs_an_approval_to_unblind() -> None:
    assert unblinding_requires_approval(ROOT) is True
    error = denied(
        lease=lease(
            principal_id="reviewer-1",
            principal_type="human",
            resource_scopes=["workspace", HIDDEN],
        ),
        request=request(
            principal_id="reviewer-1",
            principal_type="human",
            paths=[{"operation": "read", "relative_path": "x.json", "root_id": HIDDEN}],
        ),
    )

    assert error.code == Denial.APPROVAL_MISSING.value
    assert error.context["root_id"] == HIDDEN


def test_an_approved_human_unblinding_is_admitted() -> None:
    decision = authorize(
        lease=lease(
            principal_id="reviewer-1",
            principal_type="human",
            resource_scopes=["workspace", HIDDEN],
        ),
        request=request(
            approval_record_ids=["APR-1"],
            principal_id="reviewer-1",
            principal_type="human",
            paths=[{"operation": "read", "relative_path": "x.json", "root_id": HIDDEN}],
        ),
    )

    assert decision.granted_roots == (HIDDEN,)


@pytest.mark.parametrize(
    "relative_path",
    [
        "../secrets.json",
        "inputs/../../secrets.json",
        "/etc/passwd",
        "C:\\Windows\\system32",
        "inputs\\run.json",
        "inputs/run.json:stream",
        "~/.ssh/id_rsa",
        "inputs//run.json",
        "inputs/./run.json",
        "inputs/run.json ",
        "inputs/run.",
        "CON",
        "inputs/NUL.txt",
        "inputs/lpt1.log",
    ],
)
def test_a_path_that_leaves_its_root_is_refused(relative_path: str) -> None:
    error = denied(
        request=request(
            paths=[
                {
                    "operation": "read",
                    "relative_path": relative_path,
                    "root_id": "workspace",
                }
            ]
        )
    )

    assert error.code == Denial.PATH_ESCAPE.value


def test_a_root_the_lease_does_not_scope_is_refused() -> None:
    error = denied(
        request=request(
            paths=[
                {"operation": "read", "relative_path": "x.json", "root_id": "elsewhere"}
            ]
        )
    )

    assert error.code == Denial.LEASE_SCOPE_DENIED.value
    assert error.context["root_id"] == "elsewhere"


def test_a_capability_the_adapter_never_declared_is_refused() -> None:
    error = denied(request=request(capabilities=["fs.read", "proc.spawn"]))

    assert error.code == Denial.CAPABILITY_UNDECLARED.value
    assert error.context["undeclared"] == ["proc.spawn"]


def test_an_invocation_that_names_no_capability_is_refused() -> None:
    error = denied(request=request(capabilities=[]))

    assert error.code == Denial.CAPABILITY_UNDECLARED.value


def test_a_lease_that_does_not_cover_the_adapter_is_refused() -> None:
    error = denied(lease=lease(capabilities=["fs.read"]))

    assert error.code == Denial.LEASE_INSUFFICIENT.value
    assert error.context["missing"] == ["net.fetch"]


def test_a_revoked_lease_is_refused() -> None:
    assert denied(lease=lease(revoked=True)).code == Denial.LEASE_REVOKED.value


def test_an_expired_lease_is_refused() -> None:
    error = denied(lease=lease(expires_at="2026-08-01T11:59:59Z"))

    assert error.code == Denial.LEASE_EXPIRED.value


def test_a_lease_that_expires_exactly_now_is_already_gone() -> None:
    assert denied(lease=lease(expires_at=NOW)).code == Denial.LEASE_EXPIRED.value


def test_a_principal_that_is_not_the_lease_holder_is_refused() -> None:
    error = denied(request=request(principal_id="other-runner"))

    assert error.code == Denial.LEASE_SCOPE_DENIED.value


def test_a_data_class_outside_the_allowlist_is_refused() -> None:
    error = denied(request=request(data_class="restricted"))

    assert error.code == Denial.DATA_CLASS_DENIED.value
    assert "restricted" in data_classes(ROOT)


def test_egress_is_refused_when_the_adapter_declares_none() -> None:
    error = denied(
        adapter=seal_adapter(ROOT, manifest(network_policy="disabled")),
        request=request(network_url="https://example.test/run"),
    )

    assert error.code == Denial.EGRESS_DENIED.value


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.test/run",
        "https://user:pass@example.test/run",
        "example.test/run",
        "https:///run",
        "https://example.test/run#fragment",
    ],
)
def test_an_unusable_egress_url_is_refused(url: str) -> None:
    assert denied(request=request(network_url=url)).code == Denial.EGRESS_DENIED.value


def test_unrestricted_egress_without_an_approval_is_refused() -> None:
    error = denied(
        adapter=seal_adapter(
            ROOT, manifest(network_policy="unrestricted_with_approval")
        ),
        request=request(network_url="https://example.test/run"),
    )

    assert error.code == Denial.APPROVAL_MISSING.value


def test_unrestricted_egress_with_an_approval_is_admitted() -> None:
    decision = authorize(
        adapter=seal_adapter(
            ROOT, manifest(network_policy="unrestricted_with_approval")
        ),
        request=request(
            approval_record_ids=["APR-1"], network_url="https://Example.test/run"
        ),
    )

    assert decision.egress_origin == "https://example.test"


def test_egress_may_not_reach_the_evaluator() -> None:
    error = denied(
        request=request(network_url="https://eval.internal.test/collect"),
        holdout=holdout(evaluator_id="eval.internal.test"),
    )

    assert error.code == Denial.ISOLATION_BREACH.value
    assert error.context["origin"] == "https://eval.internal.test"


def test_egress_to_a_hidden_partition_host_is_refused() -> None:
    error = denied(
        request=request(network_url="https://holdout.hidden.test/partition"),
        holdout=holdout(hidden_partition_handles=["holdout.hidden.test"]),
    )

    assert error.code == Denial.ISOLATION_BREACH.value


def test_an_approval_the_lease_does_not_carry_authorizes_nothing() -> None:
    error = denied(request=request(approval_record_ids=["APR-9"]))

    assert error.code == Denial.APPROVAL_UNLEASED.value
    assert error.context["unleased"] == ["APR-9"]


def test_a_high_risk_adapter_without_an_approval_is_refused() -> None:
    error = denied(
        adapter=seal_adapter(
            ROOT, manifest(safety_class="high_risk", approval_policy="high_risk_only")
        )
    )

    assert error.code == Denial.APPROVAL_MISSING.value
    assert error.context["safety_class"] == "high_risk"


def test_a_controlled_effect_adapter_is_gated_by_all_effects() -> None:
    error = denied(
        adapter=seal_adapter(
            ROOT,
            manifest(
                approval_policy="all_effects",
                safety_class="controlled_effect",
            ),
        )
    )

    assert error.code == Denial.APPROVAL_MISSING.value


def test_an_unsealed_adapter_cannot_authorize_anything() -> None:
    with pytest.raises(SandboxGateError) as caught:
        authorize_invocation(
            ROOT,
            adapter=manifest(),
            lease=lease(),
            holdout=holdout(),
            request=request(),
            now=NOW,
        )

    assert caught.value.code == Denial.ADAPTER_UNSEALED.value


def test_a_tampered_seal_is_refused() -> None:
    sealed = seal_adapter(ROOT, manifest())
    payload = sealed.payload
    payload["sandbox_profile"] = "profile-open"
    forged = type(sealed)(
        "tool_adapter", __import__("json").dumps(payload).encode("utf-8")
    )

    with pytest.raises(SandboxGateError) as caught:
        authorize(adapter=forged)

    assert caught.value.code == Denial.ADAPTER_UNSEALED.value


def test_the_manifest_field_set_comes_from_the_schema() -> None:
    fields = target_manifest_fields(ROOT)

    assert "sandbox_profile" in fields
    assert set(manifest()) == set(fields)


def test_a_manifest_missing_a_declared_field_is_refused() -> None:
    payload = manifest()
    del payload["sandbox_profile"]

    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(ROOT, payload)

    assert caught.value.code == "FIELD_SET_INVALID"
    assert caught.value.context["missing"] == ["sandbox_profile"]


def test_an_adapter_that_pins_no_artifact_hash_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(ROOT, manifest(artifact_hashes=[]))

    assert caught.value.code == "ADAPTER_UNPINNED"


def test_an_adapter_that_pins_a_non_sha256_hash_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(ROOT, manifest(artifact_hashes=["md5:" + "a" * 32]))

    assert caught.value.code == "ADAPTER_UNPINNED"


def test_an_effect_taking_adapter_must_be_reproducibly_pinned() -> None:
    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(
            ROOT,
            manifest(
                safety_class="high_risk",
                reproducibility_contract={
                    "container_digest_required": False,
                    "environment_capture": True,
                    "seed_control": True,
                },
            ),
        )

    assert caught.value.code == "REPRODUCIBILITY_UNPINNED"


def test_an_adapter_that_requires_no_capability_is_refused() -> None:
    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(ROOT, manifest(capability_requirements=[]))

    assert caught.value.code == Denial.CAPABILITY_UNDECLARED.value


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("network_policy", "unrestricted", "NETWORK_POLICY_INVALID"),
        ("safety_class", "mostly_safe", "SAFETY_CLASS_INVALID"),
        ("approval_policy", "sometimes", "APPROVAL_POLICY_INVALID"),
        ("target_type", "vibes", "TARGET_TYPE_INVALID"),
        ("allowed_data_classes", ["confidential"], "DATA_CLASS_INVALID"),
        ("allowed_data_classes", [], "DATA_CLASS_UNDECLARED"),
        ("target_id", "Solver A", "ADAPTER_ID_INVALID"),
    ],
)
def test_a_non_canonical_manifest_value_is_refused(
    field: str, value: object, code: str
) -> None:
    with pytest.raises(SandboxGateError) as caught:
        seal_adapter(ROOT, manifest(**{field: value}))

    assert caught.value.code == code


def test_the_seal_is_deterministic_and_content_addressed() -> None:
    first = seal_adapter(ROOT, manifest())
    second = seal_adapter(ROOT, manifest())

    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["adapter_hash"].startswith("sha256:")


def test_the_quota_envelope_seals_the_same_way() -> None:
    sealed = seal_quota_envelope(ROOT, envelope())

    assert sealed.artifact_type == "quota_envelope"
    assert sealed.payload["quota_hash"].startswith("sha256:")
