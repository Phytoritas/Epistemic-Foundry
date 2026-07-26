"""Receipt builders.

Contract sources: `schemas/artifact-receipt.schema.json` and
`schemas/effect-receipt.schema.json`.

The evidence rule in `manifests/development_manifest.yaml` is blunt: no
implementation, test, migration, install, security, novelty, or completion
claim without a resolving artifact or effect receipt. These builders are the
only sanctioned way to mint one, and each validates before returning so an
unusable receipt fails at creation instead of at audit time.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import canonical_json, hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.status import ActorType
from ..domain.time import utc_now_iso

#: Actor vocabulary comes from `domain.status.ActorType`; the Literal alias below
#: exists only for type checking and is kept in step with that enum by
#: `tests/test_wire_literal_discipline.py`.
ArtifactActorType = Literal["human", "agent", "service", "tool"]
EffectStatus = Literal["SUCCEEDED", "FAILED", "UNKNOWN", "ROLLED_BACK", "NOT_EXECUTED"]
ValidationStatus = Literal["PASS", "FAIL", "NOT_RUN"]


def build_artifact_receipt(
    *,
    artifact_id: str,
    payload: Any,
    locator: str,
    media_type: str,
    actor_id: str,
    actor_type: ArtifactActorType = ActorType.SERVICE.value,  # type: ignore[assignment]
    schema_ref: str | None = None,
    action_intent_id: str | None = None,
    validation_results: Sequence[dict[str, str]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Mint an `ArtifactReceipt` resolving `payload`.

    `validation_results` must carry at least one entry (schema `minItems: 1`).
    When the caller supplies none, a single `NOT_RUN` entry is recorded rather
    than a fabricated `PASS`: an unverified artifact must read as unverified.
    """
    canonical = sha256_of_payload(payload)
    results: list[dict[str, str]] = list(validation_results or [])
    if not results:
        results = [
            {
                "check": "schema_validation",
                "status": "NOT_RUN",
                "details": "no validation was executed for this artifact",
            }
        ]
    receipt: dict[str, Any] = {
        "receipt_id": new_id("AR"),
        "artifact_id": artifact_id,
        "action_intent_id": action_intent_id,
        "media_type": media_type,
        "content_hash": canonical,
        "byte_size": len(canonical_json(payload)),
        "created_by": {"actor_id": actor_id, "actor_type": actor_type},
        "created_at": created_at or utc_now_iso(),
        "locator": locator,
        "schema_ref": schema_ref,
        "validation_results": results,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    validate_artifact("artifact-receipt", receipt)
    return receipt


def build_effect_receipt(
    *,
    intent_id: str,
    run_id: str,
    status: EffectStatus,
    idempotency_key: str,
    started_at: str,
    finished_at: str | None = None,
    external_operation_id: str | None = None,
    result_artifact_ids: Sequence[str] | None = None,
    error_artifact_ids: Sequence[str] | None = None,
    observed_state_hash: str | None = None,
) -> dict[str, Any]:
    """Mint an `EffectReceipt` for one attempted external effect.

    `reconciliation_required` is derived, not caller-supplied: `UNKNOWN` means
    the runtime could not observe the outcome, so reconciliation is mandatory
    and must not be waivable by the caller that just failed to observe it.
    """
    receipt: dict[str, Any] = {
        "receipt_id": new_id("EF"),
        "intent_id": intent_id,
        "run_id": run_id,
        "external_operation_id": external_operation_id,
        "status": status,
        "result_artifact_ids": list(result_artifact_ids or []),
        "error_artifact_ids": list(error_artifact_ids or []),
        "observed_state_hash": observed_state_hash,
        "idempotency_key": idempotency_key,
        "started_at": started_at,
        "finished_at": finished_at or utc_now_iso(),
        "reconciliation_required": status == "UNKNOWN",
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    validate_artifact("effect-receipt", receipt)
    return receipt
