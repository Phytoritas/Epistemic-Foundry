"""Fixtures for the V03 validation-execution suites.

Every intent, receipt and capture here is built through this component rather
than written out by hand, so each fixture is a document the canonical schemas
actually accept — a fixture the schema would refuse tests nothing but the
fixture.  The one deliberately hand-mutated path is ``tampered``, which exists
so the negative suite can hand authorization an intent that was edited after it
was sealed.

The whole fixture set describes one run of the V01 reservoir target: a
simulation model, seed-controlled, container-pinned, executed by a service
principal under a fenced lease with no network reach.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    build_action_intent,
    build_run_capture,
    digest,
    hash_excluding,
    reconcile_effects,
    seal_capture_channel,
    seal_run_environment,
)

ROOT = Path(__file__).resolve().parents[4]

RUN_ID = "VRUN-V03-1"
INTENT_ID = "VAI-V03-1"
NODE_ID = "execute_validation_actions"
LEASE_ID = "LEASE-V03-1"
DECISION_ID = "VXD-V03-1"
RECORD_ID = "VXR-V03-1"
RECEIPT_ID = "VER-V03-1"
CAPTURE_ID = "VCAP-V03-1"
ENVIRONMENT_ID = "VENV-V03-1"
RECONCILIATION_ID = "VREC-V03-1"
IDEMPOTENCY_KEY = "VRUN-V03-1:execute_validation_actions:1"
APPROVAL_ID = "APPROVAL-V03-1"
POLICY_HASH = "sha256:" + "c" * 64
ARTIFACT_HASH = "sha256:" + "a" * 64
LIBRARY_HASH = "sha256:" + "b" * 64
CONTAINER_DIGEST = "sha256:" + "d" * 64
ENTRYPOINT = "targets/reservoir/run.py"
TARGET_ID = "vt-reservoir-sim"

ISSUED_AT = "2026-08-01T00:00:00Z"
STARTED_AT = "2026-08-01T00:05:00Z"
FINISHED_AT = "2026-08-01T00:35:00Z"
EXPIRES_AT = "2026-08-01T04:00:00Z"
SEALED_AT = "2026-08-01T00:40:00Z"

WRITE_SCOPES = ("object_store/validation_runs/VRUN-V03-1",)
LEASE_SCOPES = ("object_store/validation_runs/**",)
CAPABILITIES = ("object_store_read", "object_store_write", "sandbox_execute")
EXPECTED_EFFECTS = ("validation_execution_performed",)

STDOUT_PAYLOAD = b"storage_estimate=41.2\n"
STDERR_PAYLOAD = b""
EXIT_PAYLOAD = b'{"exit_code":0}\n'
USAGE_PAYLOAD = b'{"wall_seconds":1800}\n'

CHANNEL_PAYLOADS: dict[str, bytes] = {
    "exit_status": EXIT_PAYLOAD,
    "resource_usage": USAGE_PAYLOAD,
    "stderr": STDERR_PAYLOAD,
    "stdout": STDOUT_PAYLOAD,
}


def arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action": "simulate",
        "parameters": {"seed": 20260801},
        "target_id": TARGET_ID,
        "target_version": "1.4.0",
    }
    value.update(overrides)
    return value


def intent_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_type": "validation_target_invocation",
        "approval_record_ids": [APPROVAL_ID],
        "arguments": arguments(),
        "arguments_artifact_id": "ART-V03-args-1",
        "created_at": ISSUED_AT,
        "idempotency_key": IDEMPOTENCY_KEY,
        "intent_id": INTENT_ID,
        "node_id": NODE_ID,
        "required_capabilities": list(CAPABILITIES),
        "risk_class": "bounded_compute",
        "run_id": RUN_ID,
        "target_ref": f"validation_target:{TARGET_ID}@1.4.0",
    }
    value.update(overrides)
    return value


def action_intent(**overrides: Any) -> dict[str, Any]:
    return build_action_intent(ROOT, **intent_arguments(**overrides))


def tampered_intent(**overrides: Any) -> dict[str, Any]:
    """A sealed intent edited afterwards, so its published hash is stale."""

    intent = action_intent()
    intent.update(overrides)
    return intent


def lease(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "approval_ids": [APPROVAL_ID],
        "capabilities": sorted(CAPABILITIES),
        "expires_at": EXPIRES_AT,
        "fencing_token": 7,
        "issued_at": ISSUED_AT,
        "lease_id": LEASE_ID,
        "policy_hash": POLICY_HASH,
        "principal_id": "svc-validation-runner",
        "principal_type": "service",
        "resource_scopes": sorted(LEASE_SCOPES),
        "revocation_reason": None,
        "revoked": False,
    }
    value.update(overrides)
    value["lease_hash"] = hash_excluding(value, "lease_hash")
    return value


def reproducibility_contract(**overrides: Any) -> dict[str, bool]:
    value: dict[str, bool] = {
        "container_digest_required": True,
        "environment_capture": True,
        "seed_control": True,
    }
    value.update(overrides)
    return value


def environment_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "artifact_hashes": [ARTIFACT_HASH, LIBRARY_HASH],
        "container_digest": CONTAINER_DIGEST,
        "entrypoint": ENTRYPOINT,
        "environment_capture": {
            "interpreter": "CPython 3.12.7",
            "os": "linux-6.8-x86_64",
            "target_runtime": "reservoir-sim 1.4.0",
        },
        "environment_id": ENVIRONMENT_ID,
        "network_policy": "disabled",
        "recorded_at": ISSUED_AT,
        "reproducibility_contract": reproducibility_contract(),
        "run_id": RUN_ID,
        "sandbox_profile": "bounded-compute-v1",
        "seeds": {"numpy_global": 20260801, "target_stream": 4242},
        "target_id": TARGET_ID,
        "target_version": "1.4.0",
    }
    value.update(overrides)
    return value


def run_environment(**overrides: Any) -> dict[str, Any]:
    return seal_run_environment(ROOT, **environment_arguments(**overrides))


def channel_receipt(channel: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action_intent_id": INTENT_ID,
        "actor_id": "svc-validation-runner",
        "actor_type": "service",
        "artifact_id": f"ART-V03-{channel}",
        "channel": channel,
        "created_at": FINISHED_AT,
        "locator": f"object_store/validation_runs/{RUN_ID}/{channel}",
        "media_type": "application/octet-stream",
        "payload": CHANNEL_PAYLOADS[channel],
        "receipt_id": f"AR-V03-{channel}",
    }
    value.update(overrides)
    return seal_capture_channel(ROOT, **value)


def channels(**overrides: Any) -> dict[str, dict[str, Any]]:
    value = {name: channel_receipt(name) for name in sorted(CHANNEL_PAYLOADS)}
    value.update(overrides)
    return value


def resource_usage(**overrides: Any) -> dict[str, int]:
    value: dict[str, int] = {
        "calls": 1,
        "concurrency": 1,
        "network_bytes": 0,
        "storage_bytes": 4096,
        "tokens": 0,
        "wall_seconds": 1800,
    }
    value.update(overrides)
    return value


def capture_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "capture_id": CAPTURE_ID,
        "channels": channels(),
        "exit_code": 0,
        "intent_id": INTENT_ID,
        "observation": "succeeded",
        "resource_usage": resource_usage(),
        "run_id": RUN_ID,
    }
    value.update(overrides)
    return value


def run_capture(**overrides: Any) -> dict[str, Any]:
    return build_run_capture(ROOT, **capture_arguments(**overrides))


def reconciliation(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "expected_effects": list(EXPECTED_EFFECTS),
        "observed_effects": list(EXPECTED_EFFECTS),
        "reconciliation_id": RECONCILIATION_ID,
        "status": "SUCCEEDED",
    }
    value.update(overrides)
    return reconcile_effects(ROOT, **value)


def authorization_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "arguments": arguments(),
        "decided_at": STARTED_AT,
        "decision_id": DECISION_ID,
        "environment": run_environment(),
        "intent": action_intent(),
        "lease": lease(),
        "policy_hash": POLICY_HASH,
        "scope_fencing_heads": {WRITE_SCOPES[0]: 7},
        "started_at": STARTED_AT,
        "write_scopes": list(WRITE_SCOPES),
    }
    value.update(overrides)
    return value


def receipt_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "capture": run_capture(),
        "environment": run_environment(),
        "external_operation_id": None,
        "finished_at": FINISHED_AT,
        "intent": action_intent(),
        "receipt_id": RECEIPT_ID,
        "reconciliation": reconciliation(),
        "started_at": STARTED_AT,
    }
    value.update(overrides)
    return value


def arguments_digest() -> str:
    """The digest a well-formed intent publishes for the fixture arguments."""

    return digest(arguments())
