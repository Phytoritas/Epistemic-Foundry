"""Process-local composition of the S06 evolution-security gate path."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from ...domain.hashing import hash_excluding, sha256_of_payload
from ...verifier_firewall import VerifierFirewall
from .governance_gate import (
    CONCERN_EVALUATOR_UPDATE,
    CONCERN_FEEDBACK_ISOLATION,
    CONCERN_REWARD_HACKING,
    EVALUATOR_RECEIPT_PREFIX,
    INTEGRATION_RECEIPT_PREFIX,
    LEAKAGE_AUDIT_PREFIX,
    REWARD_RECEIPT_PREFIX,
    GovernanceGateError,
    govern_evaluator_update,
    integrate_evolution_security_gate,
    refuse_reward_hacking,
)


_AUDIT_FIELDS = frozenset(
    {
        "access_log_artifact_id",
        "audit_hash",
        "detected_exposures",
        "leakage_audit_id",
        "required_actions",
        "run_or_bundle_id",
        "similarity_alerts",
        "status",
        "surfaces_checked",
    }
)
_REWARD_FIELDS = frozenset(
    {
        "candidate_id",
        "fitness_vector_id",
        "hard_gate_status",
        "leakage_audit",
        "leakage_audit_id",
        "receipt_hash",
        "receipt_id",
        "reward_basis",
        "routing_receipt_id",
        "run_or_bundle_id",
    }
)
_UPDATE_FIELDS = frozenset(
    {
        "current_evaluator_bundle_id",
        "future_evaluator_bundle_id",
        "governance_node_id",
        "leakage_audit_id",
        "proposal_hash",
        "proposal_id",
        "qualification_report_id",
        "qualification_status",
        "receipt_hash",
        "receipt_id",
        "source_run_id",
        "status",
        "target_run_id",
    }
)
_INTEGRATION_FIELDS = frozenset(
    {
        "components",
        "concerns_gated",
        "receipt_hash",
        "receipt_id",
        "run_id",
    }
)
_INTEGRITY_PREFIX = "evolution security path composition integrity failure"


def _input_error(message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise GovernanceGateError("INPUT_INVALID", message, context)


def _snapshot(value: object, *, label: str, active: set[int]) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _input_error(
                f"{label} contains a non-finite number",
                {"label": label},
            )
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            _input_error(f"{label} contains a cycle", {"label": label})
        active.add(identity)
        try:
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _input_error(
                        f"{label} contains a non-string mapping key",
                        {"key_type": type(key).__name__, "label": label},
                    )
                copied[key] = _snapshot(
                    item,
                    label=f"{label}.{key}",
                    active=active,
                )
            return copied
        finally:
            active.remove(identity)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in active:
            _input_error(f"{label} contains a cycle", {"label": label})
        active.add(identity)
        try:
            return [
                _snapshot(item, label=f"{label}[{position}]", active=active)
                for position, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    _input_error(
        f"{label} contains a non-JSON-compatible value",
        {"label": label, "value_type": type(value).__name__},
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip():
        _input_error(
            f"{label} must be a non-empty string",
            {"label": label},
        )
    return value


def _require_integrity(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: {message}")


def _verified_receipt(
    value: Mapping[str, Any],
    *,
    fields: frozenset[str],
    prefix: str,
    label: str,
) -> dict[str, Any]:
    document = dict(value)
    _require_integrity(
        frozenset(document) == fields,
        f"{label} field set mismatch",
    )
    body = {
        key: item
        for key, item in document.items()
        if key not in {"receipt_id", "receipt_hash"}
    }
    expected_id = prefix + sha256_of_payload(body)[len("sha256:") :]
    _require_integrity(
        document["receipt_id"] == expected_id,
        f"{label} identifier mismatch",
    )
    _require_integrity(
        document["receipt_hash"] == hash_excluding(document, "receipt_hash"),
        f"{label} hash mismatch",
    )
    return document


def _verify_reward(
    *,
    reward_receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    run_id: str,
) -> dict[str, Any]:
    reward = _verified_receipt(
        reward_receipt,
        fields=_REWARD_FIELDS,
        prefix=REWARD_RECEIPT_PREFIX,
        label="reward receipt",
    )
    audit = dict(reward["leakage_audit"])
    _require_integrity(
        frozenset(audit) == _AUDIT_FIELDS,
        "embedded leakage audit field set mismatch",
    )
    _require_integrity(
        audit["audit_hash"] == hash_excluding(audit, "audit_hash"),
        "embedded leakage audit hash mismatch",
    )
    expected_audit_id = LEAKAGE_AUDIT_PREFIX + sha256_of_payload(
        {
            "observed_artifact_ids": sorted(snapshot["feedback_artifact_ids"]),
            "run_or_bundle_id": run_id,
        }
    )[len("sha256:") :]
    _require_integrity(
        reward["leakage_audit_id"]
        == audit["leakage_audit_id"]
        == expected_audit_id,
        "leakage audit identifier mismatch",
    )
    _require_integrity(
        audit["run_or_bundle_id"] == reward["run_or_bundle_id"] == run_id,
        "reward run binding mismatch",
    )
    _require_integrity(
        audit["detected_exposures"] == [] and audit["required_actions"] == [],
        "reward receipt embeds a non-clean leakage audit",
    )
    _require_integrity(
        audit["surfaces_checked"]
        == sorted(set(map(str, snapshot["surfaces_checked"])))
        and audit["similarity_alerts"]
        == sorted(map(str, snapshot["similarity_alerts"]))
        and audit["access_log_artifact_id"] == snapshot["access_log_artifact_id"],
        "leakage audit input binding mismatch",
    )
    fitness = snapshot["fitness_vector"]
    routing = snapshot["routing_receipt"]
    _require_integrity(
        reward["candidate_id"] == str(fitness["candidate_id"])
        and reward["fitness_vector_id"] == str(fitness["fitness_vector_id"])
        and reward["hard_gate_status"] == str(fitness["hard_gate_status"])
        and reward["reward_basis"] == str(routing["reward_basis"])
        and reward["routing_receipt_id"] == str(routing["receipt_id"]),
        "reward source binding mismatch",
    )
    return reward


def _verify_update(
    *,
    update_receipt: Mapping[str, Any],
    proposal: Mapping[str, Any],
    target_run_id: str,
    qualification_report: Mapping[str, Any],
    firewall: VerifierFirewall,
    run_id: str,
) -> dict[str, Any]:
    update = _verified_receipt(
        update_receipt,
        fields=_UPDATE_FIELDS,
        prefix=EVALUATOR_RECEIPT_PREFIX,
        label="evaluator update receipt",
    )
    _require_integrity(
        update["source_run_id"] == proposal["source_run_id"] == run_id,
        "evaluator update source-run binding mismatch",
    )
    _require_integrity(
        update["target_run_id"] == target_run_id,
        "evaluator update target-run binding mismatch",
    )
    _require_integrity(
        update["current_evaluator_bundle_id"]
        == proposal["current_evaluator_bundle_id"]
        == firewall.bundle_id,
        "current evaluator bundle binding mismatch",
    )
    _require_integrity(
        update["future_evaluator_bundle_id"]
        == qualification_report["evaluator_bundle_id"],
        "future evaluator bundle binding mismatch",
    )
    _require_integrity(
        update["proposal_id"] == proposal["proposal_id"]
        and update["proposal_hash"] == proposal["proposal_hash"]
        and update["status"] == proposal["status"],
        "evaluator proposal binding mismatch",
    )
    _require_integrity(
        update["qualification_report_id"] == qualification_report["report_id"]
        and update["qualification_status"]
        == qualification_report["qualification_status"]
        and update["leakage_audit_id"]
        == qualification_report["leakage_audit_id"],
        "evaluator qualification binding mismatch",
    )
    return update


def _verify_integration(
    *,
    integration_receipt: Mapping[str, Any],
    reward_receipt: Mapping[str, Any],
    update_receipt: Mapping[str, Any] | None,
    run_id: str,
) -> dict[str, Any]:
    integration = _verified_receipt(
        integration_receipt,
        fields=_INTEGRATION_FIELDS,
        prefix=INTEGRATION_RECEIPT_PREFIX,
        label="integration receipt",
    )
    expected_components = {
        "leakage_audit_id": reward_receipt["leakage_audit_id"],
        "reward_hacking_receipt_id": reward_receipt["receipt_id"],
    }
    expected_concerns = [CONCERN_FEEDBACK_ISOLATION, CONCERN_REWARD_HACKING]
    if update_receipt is not None:
        expected_components["evaluator_update_receipt_id"] = update_receipt[
            "receipt_id"
        ]
        expected_concerns.append(CONCERN_EVALUATOR_UPDATE)
    _require_integrity(
        integration["run_id"] == run_id,
        "integration run binding mismatch",
    )
    _require_integrity(
        integration["components"] == dict(sorted(expected_components.items())),
        "integration component binding mismatch",
    )
    _require_integrity(
        integration["concerns_gated"] == sorted(expected_concerns),
        "integration concern set mismatch",
    )
    return integration


def derive_evolution_security_path(
    *,
    run_id: str,
    fitness_vector: Mapping[str, Any],
    routing_receipt: Mapping[str, Any],
    firewall: VerifierFirewall,
    feedback_artifact_ids: Sequence[str],
    surfaces_checked: Sequence[str],
    access_log_artifact_id: str,
    similarity_alerts: Sequence[str] = (),
    proposal: Mapping[str, Any] | None = None,
    target_run_id: str | None = None,
    qualification_report: Mapping[str, Any] | None = None,
) -> MappingProxyType:
    """Derive immutable reward, optional update and integration receipts once.

    This function neither applies rewards nor activates an evaluator update.  It
    only composes the existing S06 owners over one detached input snapshot.
    """
    if type(firewall) is not VerifierFirewall:
        _input_error(
            "firewall must be an exact VerifierFirewall instance",
            {"value_type": type(firewall).__name__},
        )

    optional_group = (
        proposal is not None,
        target_run_id is not None,
        qualification_report is not None,
    )
    if any(optional_group) and not all(optional_group):
        _input_error(
            "proposal, target_run_id and qualification_report must be provided together"
        )

    snapshot = _snapshot(
        {
            "access_log_artifact_id": access_log_artifact_id,
            "feedback_artifact_ids": feedback_artifact_ids,
            "fitness_vector": fitness_vector,
            "proposal": proposal,
            "qualification_report": qualification_report,
            "routing_receipt": routing_receipt,
            "run_id": run_id,
            "similarity_alerts": similarity_alerts,
            "surfaces_checked": surfaces_checked,
            "target_run_id": target_run_id,
        },
        label="evolution security inputs",
        active=set(),
    )
    run = _require_text(snapshot["run_id"], "run_id")
    access_log = _require_text(
        snapshot["access_log_artifact_id"], "access_log_artifact_id"
    )
    target = (
        _require_text(snapshot["target_run_id"], "target_run_id")
        if all(optional_group)
        else None
    )
    fingerprint = sha256_of_payload(snapshot)

    reward_inputs = _thaw(snapshot)
    reward_receipt = refuse_reward_hacking(
        fitness_vector=reward_inputs["fitness_vector"],
        routing_receipt=reward_inputs["routing_receipt"],
        firewall=firewall,
        run_or_bundle_id=run,
        feedback_artifact_ids=reward_inputs["feedback_artifact_ids"],
        surfaces_checked=reward_inputs["surfaces_checked"],
        access_log_artifact_id=access_log,
        similarity_alerts=reward_inputs["similarity_alerts"],
    )
    _require_integrity(
        sha256_of_payload(snapshot) == fingerprint,
        "reward gate mutated the detached input snapshot",
    )
    try:
        reward = _verify_reward(
            reward_receipt=reward_receipt,
            snapshot=snapshot,
            run_id=run,
        )
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed reward output") from error

    update: dict[str, Any] | None = None
    if all(optional_group):
        update_inputs = _thaw(snapshot)
        update_receipt = govern_evaluator_update(
            proposal=update_inputs["proposal"],
            target_run_id=target,
            qualification_report=update_inputs["qualification_report"],
            firewall=firewall,
        )
        _require_integrity(
            sha256_of_payload(snapshot) == fingerprint,
            "evaluator-update gate mutated the detached input snapshot",
        )

        proposal_snapshot = snapshot["proposal"]
        report_snapshot = snapshot["qualification_report"]
        if proposal_snapshot["source_run_id"] != run:
            _input_error(
                "proposal.source_run_id must equal run_id",
                {
                    "run_id": run,
                    "source_run_id": proposal_snapshot["source_run_id"],
                },
            )
        if proposal_snapshot["current_evaluator_bundle_id"] != firewall.bundle_id:
            _input_error(
                "proposal.current_evaluator_bundle_id must equal firewall.bundle_id",
                {
                    "current_evaluator_bundle_id": proposal_snapshot[
                        "current_evaluator_bundle_id"
                    ],
                    "firewall_bundle_id": firewall.bundle_id,
                },
            )
        try:
            update = _verify_update(
                update_receipt=update_receipt,
                proposal=proposal_snapshot,
                target_run_id=target,
                qualification_report=report_snapshot,
                firewall=firewall,
                run_id=run,
            )
        except RuntimeError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"{_INTEGRITY_PREFIX}: malformed evaluator-update output"
            ) from error

    integration_receipt = integrate_evolution_security_gate(
        run_id=run,
        reward_receipt=reward,
        evaluator_update_receipt=update,
    )
    _require_integrity(
        sha256_of_payload(snapshot) == fingerprint,
        "integration gate mutated the detached input snapshot",
    )
    try:
        integration = _verify_integration(
            integration_receipt=integration_receipt,
            reward_receipt=reward,
            update_receipt=update,
            run_id=run,
        )
    except RuntimeError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"{_INTEGRITY_PREFIX}: malformed integration output") from error

    return MappingProxyType(
        {
            "reward_hacking_receipt": _freeze(reward),
            "evaluator_update_receipt": _freeze(update) if update is not None else None,
            "integration_receipt": _freeze(integration),
        }
    )
