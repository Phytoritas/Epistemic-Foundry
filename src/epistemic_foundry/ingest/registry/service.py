"""Receipt-bound K01 document registration orchestration."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from enum import Enum
from typing import Any

from ...contracts import ContractViolation, default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from .errors import (
    DOCUMENT_ARTIFACT_RECEIPT_MISMATCH,
    DOCUMENT_AUTHORIZATION_FAILED,
    DOCUMENT_CAS_CONFLICT,
    DOCUMENT_CONTRACT_INVALID,
    DOCUMENT_EFFECT_RECEIPT_MISSING,
    DOCUMENT_IDEMPOTENCY_CONFLICT,
    DOCUMENT_INPUT_BINDING_MISMATCH,
    DOCUMENT_LEDGER_EVENT_MISMATCH,
    DOCUMENT_MEDIA_TYPE_MISMATCH,
    DOCUMENT_RECONCILIATION_REQUIRED,
    DOCUMENT_REGISTRATION_INCOMPLETE,
    DOCUMENT_SOURCE_ARTIFACT_MISSING,
    DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
    DOCUMENT_SOURCE_INTEGRITY_FAILED,
    DOCUMENT_SOURCE_RECEIPT_MISSING,
    DOCUMENT_STALE_FENCING_TOKEN,
    DocumentRegistryError,
    fail,
)
from .hash import (
    DOCUMENT_REGISTRATION_SCHEMA_VERSION,
    content_hash,
    parse_json_object,
    seal_registration_payload,
    verify_request_payload,
)
from .lineage import validate_registration_lineage, validate_registration_predecessor
from .models import (
    ActionIntentEvidence,
    ArtifactPublication,
    ArtifactReceiptEvidence,
    CasOutcome,
    CommittedRegistration,
    DocumentRegistration,
    DocumentRegistrationRequest,
    EFFECT_SUCCEEDED,
    EffectReceiptEvidence,
    LeaseAuthorization,
    LedgerPublication,
    RegistrationReservation,
    ResolvedArtifact,
    SourcePublication,
)
from .repository import RegistrationPorts

REGISTER_DOCUMENT_NODE_ID = "register_document"
REGISTER_CAPABILITY = "document_register"
REGISTER_SOURCE_ACTION_TYPE = "register_document_source"
REGISTER_SOURCE_REQUIRED_CAPABILITIES = ("artifact_write", REGISTER_CAPABILITY)
REGISTRATION_EVENT_TYPE = "document.registration.created"


def _schema_enum(name: str, *path: str) -> type[Enum]:
    """Derive a runtime enum from the verified package canonical schema."""
    node: object = default_registry().document(name)
    for part in path:
        if not isinstance(node, Mapping) or part not in node:
            raise RuntimeError(f"canonical enum path is missing: {name}:{'/'.join(path)}")
        node = node[part]
    if not isinstance(node, list) or not node or any(
        not isinstance(value, str) for value in node
    ):
        raise RuntimeError(f"canonical enum is not a closed string list: {name}:{'/'.join(path)}")
    return Enum(name.title().replace("-", "") + "RuntimeEnum", {value.upper(): value for value in node}, type=str)


_ActionIntentRiskClass = _schema_enum(
    "action-intent", "properties", "risk_class", "enum"
)
_ResultEnvelopeStatus = _schema_enum(
    "result-envelope", "properties", "status", "enum"
)
CONTROLLED_EFFECT_RISK_CLASS = _ActionIntentRiskClass.CONTROLLED_EFFECT.value
RESULT_ENVELOPE_SUCCESS = _ResultEnvelopeStatus.SUCCESS.value


def _validate_invocation(invocation: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(invocation))
    try:
        validate_artifact("node-invocation", candidate)
    except ContractViolation as error:
        fail(
            DOCUMENT_CONTRACT_INVALID,
            "register_document requires a canonical NodeInvocation",
            {"errors": list(error.errors)},
        )
    if candidate["node_id"] != REGISTER_DOCUMENT_NODE_ID:
        fail(
            DOCUMENT_INPUT_BINDING_MISMATCH,
            "NodeInvocation.node_id is not register_document",
            {"node_id": candidate["node_id"]},
        )
    return candidate


def _verify_resolved_artifact(
    artifact: ResolvedArtifact | None,
    *,
    expected_id: str | None = None,
    label: str,
) -> bytes:
    if artifact is None:
        fail(
            DOCUMENT_SOURCE_ARTIFACT_MISSING,
            f"{label} did not resolve to an immutable artifact",
        )
    _verify_artifact_receipt(artifact.receipt)
    if expected_id is not None and artifact.artifact_id != expected_id:
        fail(
            DOCUMENT_SOURCE_ARTIFACT_MISSING,
            f"{label} resolved under a different artifact ID",
            {"actual": artifact.artifact_id, "expected": expected_id},
        )
    immutable_bytes = bytes(artifact.content)
    observed_hash = content_hash(immutable_bytes)
    if (
        artifact.content_hash != observed_hash
        or artifact.byte_size != len(immutable_bytes)
        or artifact.receipt.content_hash != observed_hash
        or artifact.receipt.byte_size != len(immutable_bytes)
        or artifact.receipt.artifact_id != artifact.artifact_id
        or artifact.receipt.media_type != artifact.media_type
    ):
        fail(
            DOCUMENT_SOURCE_INTEGRITY_FAILED,
            f"{label} bytes, manifest projection, and ArtifactReceipt do not reconcile",
        )
    if not artifact.receipt.receipt_id or not artifact.receipt.validation_passed:
        fail(DOCUMENT_SOURCE_RECEIPT_MISSING, f"{label} has no resolving PASS ArtifactReceipt")
    return immutable_bytes


def _verify_artifact_receipt(receipt: ArtifactReceiptEvidence) -> None:
    payload = receipt.to_dict()
    try:
        validate_artifact("artifact-receipt", payload)
    except ContractViolation as error:
        fail(
            DOCUMENT_ARTIFACT_RECEIPT_MISMATCH,
            "ArtifactReceipt violates its canonical contract",
            {"errors": list(error.errors)},
        )
    expected_hash = hash_excluding(payload, "receipt_hash")
    if receipt.receipt_hash != expected_hash:
        fail(
            DOCUMENT_ARTIFACT_RECEIPT_MISMATCH,
            "ArtifactReceipt self-hash does not match its canonical fields",
        )


def _verify_effect_receipt_contract(effect: EffectReceiptEvidence) -> None:
    payload = effect.to_dict()
    try:
        validate_artifact("effect-receipt", payload)
    except ContractViolation as error:
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "EffectReceipt violates its canonical contract",
            {"errors": list(error.errors)},
        )
    expected_hash = hash_excluding(payload, "receipt_hash")
    if effect.receipt_hash != expected_hash:
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "EffectReceipt self-hash does not match its canonical fields",
        )


def _verify_action_intent(
    intent: Any,
    *,
    run_id: str,
    target_ref: str,
    request: Mapping[str, Any],
) -> None:
    if not isinstance(intent, ActionIntentEvidence):
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "source publication reservation has no canonical ActionIntent",
        )
    payload = intent.to_dict()
    try:
        validate_artifact("action-intent", payload)
    except ContractViolation as error:
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "source registration ActionIntent violates its canonical contract",
            {"errors": list(error.errors)},
        )
    if intent.intent_hash != hash_excluding(payload, "intent_hash"):
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "source registration ActionIntent self-hash does not match its canonical fields",
        )
    if (
        intent.run_id != run_id
        or intent.node_id != REGISTER_DOCUMENT_NODE_ID
        or intent.action_type != REGISTER_SOURCE_ACTION_TYPE
        or intent.target_ref != target_ref
        or intent.arguments_artifact_id != request["request_id"]
        or intent.arguments_hash != request["request_hash"]
        or intent.idempotency_key != request["idempotency_key"]
        or intent.required_capabilities != REGISTER_SOURCE_REQUIRED_CAPABILITIES
        or intent.risk_class != CONTROLLED_EFFECT_RISK_CLASS
    ):
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "source registration ActionIntent is bound to another effect or request",
        )


def _verify_ledger_event(event: LedgerPublication) -> None:
    payload = event.to_dict()
    try:
        validate_artifact("event-record", payload)
    except ContractViolation as error:
        fail(
            DOCUMENT_LEDGER_EVENT_MISMATCH,
            "registration EventRecord violates its canonical contract",
            {"errors": list(error.errors)},
        )
    expected_hash = hash_excluding(payload, "event_hash")
    if event.event_hash != expected_hash:
        fail(
            DOCUMENT_LEDGER_EVENT_MISMATCH,
            "registration EventRecord self-hash does not match its canonical fields",
        )


def _resource_scopes(request: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        f"workspace/{request['workspace_id']}",
        f"corpus/{request['corpus_id']}",
        f"artifact/{request['staged_source_artifact_id']}",
    )


def _authorize(
    ports: RegistrationPorts,
    invocation: Mapping[str, Any],
    request: Mapping[str, Any],
) -> LeaseAuthorization:
    authorization = ports.leases.authorize_registration(
        invocation=invocation,
        request=request,
        capability=REGISTER_CAPABILITY,
        resource_scopes=_resource_scopes(request),
    )
    if (
        not authorization.current
        or authorization.capability != REGISTER_CAPABILITY
        or authorization.fencing_token != invocation["lease_token"]
        or not set(_resource_scopes(request)).issubset(authorization.resource_scopes)
    ):
        fail(
            DOCUMENT_STALE_FENCING_TOKEN,
            "registration lease is stale, incomplete, or bound to another invocation",
        )
    if not authorization.principal_id:
        fail(DOCUMENT_AUTHORIZATION_FAILED, "registration lease has no authenticated principal")
    return authorization


def _reserve(
    ports: RegistrationPorts,
    invocation: Mapping[str, Any],
    request: Mapping[str, Any],
) -> RegistrationReservation:
    idempotency_key = str(request["idempotency_key"])
    source_blob_artifact_id = ports.state.reserve_source_blob_id(
        idempotency_key=idempotency_key,
        request_hash=str(request["request_hash"]),
    )
    source_artifact = ports.artifacts.reserve_artifact_receipt(
        kind="source_blob", idempotency_key=idempotency_key
    )
    registration_artifact = ports.artifacts.reserve_artifact_receipt(
        kind="document_registration", idempotency_key=idempotency_key
    )
    effect = ports.effects.reserve_source_registration_effect(
        run_id=str(invocation["run_id"]),
        node_id=REGISTER_DOCUMENT_NODE_ID,
        action_type=REGISTER_SOURCE_ACTION_TYPE,
        target_ref=source_blob_artifact_id,
        arguments_artifact_id=str(request["request_id"]),
        arguments_hash=str(request["request_hash"]),
        idempotency_key=idempotency_key,
        required_capabilities=REGISTER_SOURCE_REQUIRED_CAPABILITIES,
        risk_class=CONTROLLED_EFFECT_RISK_CLASS,
    )
    _verify_action_intent(
        effect.action_intent,
        run_id=str(invocation["run_id"]),
        target_ref=source_blob_artifact_id,
        request=request,
    )
    ledger = ports.ledger.reserve_registration_event(
        run_id=str(invocation["run_id"]), idempotency_key=idempotency_key
    )
    expected_revision = ports.state.expected_revision(
        workspace_id=str(request["workspace_id"]),
        corpus_id=str(request["corpus_id"]),
        supersedes_registration_id=request["supersedes_registration_id"],
    )
    if expected_revision < 0:
        fail(DOCUMENT_CAS_CONFLICT, "registration expected revision cannot be negative")
    if not all(
        (
            source_blob_artifact_id,
            source_artifact.artifact_receipt_id,
            registration_artifact.artifact_receipt_id,
            effect.action_intent_id,
            effect.attempt_id,
            effect.effect_receipt_id,
            ledger.event_id,
            ledger.occurred_at,
        )
    ):
        fail(DOCUMENT_REGISTRATION_INCOMPLETE, "shared authorities returned an incomplete reservation")
    return RegistrationReservation(
        source_blob_artifact_id=source_blob_artifact_id,
        source_artifact=source_artifact,
        registration_artifact=registration_artifact,
        effect=effect,
        ledger=ledger,
        registered_at=ledger.occurred_at,
        expected_revision=expected_revision,
        schema_validation_report_id=(
            f"SVR-{str(request['request_hash']).removeprefix('sha256:')}"
        ),
    )


def _publish_source(
    ports: RegistrationPorts,
    request: Mapping[str, Any],
    staged_source: ResolvedArtifact,
    source_bytes: bytes,
    reservation: RegistrationReservation,
    run_id: str,
) -> SourcePublication:
    if staged_source.media_type != request["declared_media_type"]:
        fail(
            DOCUMENT_MEDIA_TYPE_MISMATCH,
            "declared_media_type differs from the immutable staged-source media type",
            {"declared": request["declared_media_type"], "detected": staged_source.media_type},
        )
    publication = ports.artifacts.publish_source_blob(
        artifact_id=reservation.source_blob_artifact_id,
        content=source_bytes,
        media_type=staged_source.media_type,
        confidentiality=str(request["confidentiality"]),
        license_status=str(request["declared_license_status"]),
        action_intent_id=reservation.effect.action_intent_id,
        receipt_id=reservation.source_artifact.artifact_receipt_id,
        input_artifact_ids=(staged_source.artifact_id,),
    )
    _verify_artifact_publication(
        publication,
        expected_artifact_id=reservation.source_blob_artifact_id,
        expected_receipt_id=reservation.source_artifact.artifact_receipt_id,
        expected_action_intent_id=reservation.effect.action_intent_id,
        expected_content=source_bytes,
        expected_media_type=staged_source.media_type,
    )
    effect = ports.effects.record_source_registration_effect(
        reservation=reservation.effect,
        run_id=run_id,
        idempotency_key=str(request["idempotency_key"]),
        source_publication=publication,
    )
    _verify_effect(
        effect,
        reservation=reservation,
        run_id=run_id,
        idempotency_key=str(request["idempotency_key"]),
        source_publication=publication,
    )
    return SourcePublication(
        artifact_id=publication.artifact_id,
        content_hash=publication.content_hash,
        byte_size=publication.byte_size,
        media_type=publication.media_type,
        receipt=publication.receipt,
        effect=effect,
    )


def _verify_artifact_publication(
    publication: ArtifactPublication,
    *,
    expected_artifact_id: str,
    expected_receipt_id: str,
    expected_action_intent_id: str,
    expected_content: bytes,
    expected_media_type: str,
) -> None:
    _verify_artifact_receipt(publication.receipt)
    expected_hash = content_hash(expected_content)
    if (
        publication.artifact_id != expected_artifact_id
        or publication.content_hash != expected_hash
        or publication.byte_size != len(expected_content)
        or publication.media_type != expected_media_type
        or publication.receipt.receipt_id != expected_receipt_id
        or publication.receipt.artifact_id != expected_artifact_id
        or publication.receipt.action_intent_id != expected_action_intent_id
        or publication.receipt.content_hash != expected_hash
        or publication.receipt.byte_size != len(expected_content)
        or publication.receipt.media_type != expected_media_type
        or not publication.receipt.validation_passed
    ):
        fail(
            DOCUMENT_ARTIFACT_RECEIPT_MISMATCH,
            "published artifact and resolving ArtifactReceipt do not match reserved bytes",
        )


def _verify_effect(
    effect: EffectReceiptEvidence,
    *,
    reservation: RegistrationReservation,
    run_id: str,
    idempotency_key: str,
    source_publication: ArtifactPublication,
) -> None:
    if effect is None:
        fail(DOCUMENT_EFFECT_RECEIPT_MISSING, "source publication has no EffectReceipt")
    _verify_effect_receipt_contract(effect)
    if not effect.receipt_id:
        fail(DOCUMENT_EFFECT_RECEIPT_MISSING, "source publication has no EffectReceipt")
    if (
        effect.receipt_id != reservation.effect.effect_receipt_id
        or effect.intent_id != reservation.effect.action_intent_id
        or effect.run_id != run_id
        or effect.idempotency_key != idempotency_key
        or effect.started_at != reservation.effect.started_at
        or effect.status != EFFECT_SUCCEEDED
        or effect.reconciliation_required
        or source_publication.artifact_id not in effect.result_artifact_ids
        or effect.observed_state_hash != source_publication.content_hash
    ):
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "source publication EffectReceipt is missing, unresolved, or bound to another effect",
        )


def _build_registration(
    request: Mapping[str, Any],
    source: SourcePublication,
    authorization: LeaseAuthorization,
    reservation: RegistrationReservation,
) -> DocumentRegistration:
    payload = seal_registration_payload(
        {
            "schema_version": DOCUMENT_REGISTRATION_SCHEMA_VERSION,
            "workspace_id": request["workspace_id"],
            "corpus_id": request["corpus_id"],
            "source_blob_artifact_id": source.artifact_id,
            "source_content_hash": source.content_hash,
            "byte_size": source.byte_size,
            "detected_media_type": source.media_type,
            "original_filename": request["declared_filename"],
            "source_origin": copy.deepcopy(request["source_origin"]),
            "license_status": request["declared_license_status"],
            "access_policy_ref": request["access_policy_ref"],
            "confidentiality": request["confidentiality"],
            "external_identifier_hints": copy.deepcopy(request["external_identifier_hints"]),
            "supersedes_registration_id": request["supersedes_registration_id"],
            "initial_state": "REGISTERED_UNSCREENED",
            "submitted_by_principal_id": authorization.principal_id,
            "request_id": request["request_id"],
            "request_hash": request["request_hash"],
            "idempotency_key": request["idempotency_key"],
            "action_intent_id": reservation.effect.action_intent_id,
            "source_effect_receipt_id": source.effect.receipt_id,
            "source_artifact_receipt_id": source.receipt.receipt_id,
            "registration_artifact_receipt_id": (
                reservation.registration_artifact.artifact_receipt_id
            ),
            "ledger_event_id": reservation.ledger.event_id,
            "registered_at": reservation.registered_at,
        }
    )
    return DocumentRegistration.from_payload(payload)


def _publish_registration(
    ports: RegistrationPorts,
    request_artifact: ResolvedArtifact,
    registration: DocumentRegistration,
    reservation: RegistrationReservation,
) -> ArtifactPublication:
    content = registration.canonical_bytes()
    publication = ports.artifacts.publish_registration(
        artifact_id=registration.registration_id,
        content=content,
        action_intent_id=reservation.effect.action_intent_id,
        receipt_id=reservation.registration_artifact.artifact_receipt_id,
        input_artifact_ids=(request_artifact.artifact_id, registration["source_blob_artifact_id"]),
    )
    _verify_artifact_publication(
        publication,
        expected_artifact_id=registration.registration_id,
        expected_receipt_id=reservation.registration_artifact.artifact_receipt_id,
        expected_action_intent_id=reservation.effect.action_intent_id,
        expected_content=content,
        expected_media_type="application/json",
    )
    return publication


def _append_event(
    ports: RegistrationPorts,
    invocation: Mapping[str, Any],
    authorization: LeaseAuthorization,
    registration: DocumentRegistration,
    publication: ArtifactPublication,
    reservation: RegistrationReservation,
) -> LedgerPublication:
    event = ports.ledger.append_registration_event(
        reservation=reservation.ledger,
        run_id=str(invocation["run_id"]),
        actor_id=authorization.principal_id,
        registration_id=registration.registration_id,
        registration_artifact_id=publication.artifact_id,
        registration_artifact_hash=publication.content_hash,
    )
    _verify_ledger_event(event)
    if (
        event.event_id != reservation.ledger.event_id
        or event.run_id != invocation["run_id"]
        or event.event_type != REGISTRATION_EVENT_TYPE
        or event.aggregate_type != "document_registration"
        or event.aggregate_id != registration.registration_id
        or event.actor_id != authorization.principal_id
        or event.payload_artifact_id != publication.artifact_id
        or event.payload_hash != publication.content_hash
        or event.occurred_at != reservation.ledger.occurred_at
        or event.occurred_at != registration["registered_at"]
        or event.status not in {"APPENDED", "EXISTING"}
    ):
        fail(DOCUMENT_LEDGER_EVENT_MISMATCH, "registration ledger event does not bind the artifact")
    return event


def _commit(
    ports: RegistrationPorts,
    registration: DocumentRegistration,
    authorization: LeaseAuthorization,
    source: SourcePublication,
    publication: ArtifactPublication,
    event: LedgerPublication,
    reservation: RegistrationReservation,
) -> CasOutcome:
    outcome = ports.state.compare_and_swap_registration(
        registration=registration.to_dict(),
        expected_revision=reservation.expected_revision,
        authorization=authorization,
        source_publication=ArtifactPublication(
            artifact_id=source.artifact_id,
            content_hash=source.content_hash,
            byte_size=source.byte_size,
            media_type=source.media_type,
            receipt=source.receipt,
        ),
        registration_publication=publication,
        effect_receipt=source.effect,
        ledger_publication=event,
    )
    if (
        not outcome.ok
        or outcome.status not in {"COMMITTED", "EXISTING"}
        or outcome.expected_revision != reservation.expected_revision
        or outcome.current_revision != outcome.expected_revision + 1
        or outcome.registration_id != registration.registration_id
        or outcome.registration_hash != registration.registration_hash
        or outcome.request_hash != registration["request_hash"]
        or outcome.fencing_token != authorization.fencing_token
    ):
        fail(DOCUMENT_CAS_CONFLICT, "registration compare-and-swap did not commit the sealed revision")
    return outcome


def _verify_committed(
    committed: CommittedRegistration,
    *,
    request: Mapping[str, Any],
    ports: RegistrationPorts,
    authorization: LeaseAuthorization | None = None,
) -> DocumentRegistration:
    registration = DocumentRegistration.from_payload(committed.registration)
    if registration["request_hash"] != request["request_hash"]:
        fail(
            DOCUMENT_IDEMPOTENCY_CONFLICT,
            "idempotency key is bound to a different canonical request hash",
        )
    source = committed.source_publication
    publication = committed.registration_publication
    event = committed.ledger_publication
    cas = committed.cas

    intent = ports.effects.resolve_action_intent(
        str(registration["action_intent_id"])
    )
    _verify_action_intent(
        intent,
        run_id=source.effect.run_id,
        target_ref=source.artifact_id,
        request=request,
    )
    if intent.intent_id != registration["action_intent_id"]:
        fail(
            DOCUMENT_SOURCE_EFFECT_UNRESOLVED,
            "resolved ActionIntent ID does not match the committed registration",
        )

    _verify_artifact_receipt(source.receipt)
    _verify_effect_receipt_contract(source.effect)
    _verify_ledger_event(event)

    request_bindings = {
        "workspace_id": "workspace_id",
        "corpus_id": "corpus_id",
        "declared_filename": "original_filename",
        "declared_media_type": "detected_media_type",
        "source_origin": "source_origin",
        "declared_license_status": "license_status",
        "access_policy_ref": "access_policy_ref",
        "confidentiality": "confidentiality",
        "external_identifier_hints": "external_identifier_hints",
        "supersedes_registration_id": "supersedes_registration_id",
        "idempotency_key": "idempotency_key",
        "request_id": "request_id",
        "request_hash": "request_hash",
    }
    mismatches = [
        request_field
        for request_field, registration_field in request_bindings.items()
        if request[request_field] != registration[registration_field]
    ]
    if mismatches:
        fail(
            DOCUMENT_INPUT_BINDING_MISMATCH,
            "committed registration is not bound to the canonical request",
            {"mismatched_fields": mismatches},
        )

    # Exact replay must reopen the immutable predecessor chain as well as the
    # registration's receipts and CAS evidence.  Otherwise a committed child
    # could be replayed successfully after its predecessor history disappeared
    # or was replaced by a cross-scope/cyclic chain.
    validate_registration_lineage(
        registration.to_dict(),
        ports.state.read_registration,
    )

    if (
        source.artifact_id != registration["source_blob_artifact_id"]
        or source.content_hash != registration["source_content_hash"]
        or source.byte_size != registration["byte_size"]
        or source.media_type != registration["detected_media_type"]
        or source.receipt.receipt_id != registration["source_artifact_receipt_id"]
        or source.receipt.artifact_id != source.artifact_id
        or source.receipt.action_intent_id != registration["action_intent_id"]
        or source.receipt.content_hash != source.content_hash
        or source.receipt.byte_size != source.byte_size
        or source.receipt.media_type != source.media_type
        or not source.receipt.validation_passed
        or source.effect.receipt_id != registration["source_effect_receipt_id"]
        or source.effect.intent_id != registration["action_intent_id"]
        or source.effect.idempotency_key != registration["idempotency_key"]
        or source.effect.status != EFFECT_SUCCEEDED
        or source.effect.reconciliation_required
        or source.artifact_id not in source.effect.result_artifact_ids
        or source.effect.observed_state_hash != source.content_hash
    ):
        fail(DOCUMENT_REGISTRATION_INCOMPLETE, "committed source evidence is incomplete")
    registration_bytes = registration.canonical_bytes()
    _verify_artifact_publication(
        publication,
        expected_artifact_id=registration.registration_id,
        expected_receipt_id=registration["registration_artifact_receipt_id"],
        expected_action_intent_id=registration["action_intent_id"],
        expected_content=registration_bytes,
        expected_media_type="application/json",
    )
    if (
        event.event_id != registration["ledger_event_id"]
        or event.aggregate_type != "document_registration"
        or event.aggregate_id != registration.registration_id
        or event.actor_id != registration["submitted_by_principal_id"]
        or event.payload_artifact_id != publication.artifact_id
        or event.payload_hash != publication.content_hash
        or event.event_type != REGISTRATION_EVENT_TYPE
        or event.run_id != source.effect.run_id
        or event.occurred_at != registration["registered_at"]
        or event.status not in {"APPENDED", "EXISTING"}
    ):
        fail(DOCUMENT_LEDGER_EVENT_MISMATCH, "committed ledger evidence is incomplete")
    if (
        not cas.ok
        or cas.status not in {"COMMITTED", "EXISTING"}
        or cas.expected_revision < 0
        or cas.current_revision is None
        or cas.current_revision != cas.expected_revision + 1
        or cas.registration_id != registration.registration_id
        or cas.registration_hash != registration.registration_hash
        or cas.request_hash != request["request_hash"]
        or cas.fencing_token is None
    ):
        fail(DOCUMENT_REGISTRATION_INCOMPLETE, "committed CAS evidence is incomplete")
    if authorization is not None and cas.fencing_token != authorization.fencing_token:
        fail(DOCUMENT_STALE_FENCING_TOKEN, "committed registration used another fencing token")
    return registration


def _result_envelope(
    *,
    invocation: Mapping[str, Any],
    request: Mapping[str, Any],
    registration: DocumentRegistration,
    committed: CommittedRegistration,
    policy_decision_ids: tuple[str, ...],
    replayed: bool,
    schema_validation_report_id: str,
) -> dict[str, Any]:
    source = committed.source_publication
    artifact = committed.registration_publication
    event = committed.ledger_publication
    result = {
        "run_id": invocation["run_id"],
        "node_id": invocation["node_id"],
        "attempt": invocation["attempt"],
        "status": RESULT_ENVELOPE_SUCCESS,
        "output_artifact_ids": [registration.registration_id, source.artifact_id],
        "evidence_ids": [source.receipt.receipt_id, artifact.receipt.receipt_id, event.event_id],
        "errors": [],
        "metrics": {
            "source_byte_size": source.byte_size,
            "registration_revision": committed.cas.current_revision,
            "replayed": replayed,
        },
        "input_hash": invocation["input_hash"],
        "output_hash": sha256_of_payload(registration.to_dict()),
        "started_at": source.effect.started_at,
        "finished_at": source.effect.finished_at,
        "completeness": {
            "expected_count": 1,
            "terminal_count": 1,
            "missing_node_ids": [],
            "partial_allowed": False,
        },
        "effect_receipt_ids": [source.effect.receipt_id],
        "policy_decision_ids": list(policy_decision_ids),
        "schema_validation_report_id": schema_validation_report_id,
        "terminal_reason": "DOCUMENT_REGISTRATION_REPLAYED" if replayed else "DOCUMENT_REGISTERED",
    }
    try:
        validate_artifact("result-envelope", result)
    except ContractViolation as error:
        fail(
            DOCUMENT_REGISTRATION_INCOMPLETE,
            "successful registration did not produce a canonical ResultEnvelope",
            {"errors": list(error.errors)},
        )
    return result


def register_document(
    invocation: Mapping[str, Any],
    *,
    ports: RegistrationPorts,
) -> dict[str, Any]:
    """Register staged bytes and return a receipt-bound ResultEnvelope.

    There is deliberately no default ``ports`` value.  A caller must inject
    the D03/E01-E03 and CAS adapters; otherwise the workflow cannot claim a
    durable registration.
    """
    node = _validate_invocation(invocation)
    request_artifact = ports.inputs.resolve_registration_request(node)
    request_bytes = _verify_resolved_artifact(request_artifact, label="registration request")
    if request_artifact.artifact_id not in node["input_artifact_ids"]:
        fail(
            DOCUMENT_INPUT_BINDING_MISMATCH,
            "resolved DocumentRegistrationRequest is absent from NodeInvocation inputs",
        )
    request_payload = verify_request_payload(
        parse_json_object(request_bytes, label="DocumentRegistrationRequest")
    )
    request = DocumentRegistrationRequest.from_payload(request_payload)
    if node["input_hash"] != request.request_hash:
        fail(
            DOCUMENT_INPUT_BINDING_MISMATCH,
            "NodeInvocation.input_hash does not equal the sealed request_hash",
        )

    authorization = _authorize(ports, node, request_payload)
    existing = ports.state.lookup_idempotent_registration(request.idempotency_key)
    if existing is not None:
        try:
            registration = _verify_committed(
                existing,
                request=request_payload,
                ports=ports,
                authorization=authorization,
            )
        except DocumentRegistryError as error:
            if error.code == DOCUMENT_IDEMPOTENCY_CONFLICT:
                raise
            reconciled = ports.state.reconcile_registration(
                idempotency_key=request.idempotency_key,
                request_hash=request.request_hash,
            )
            if reconciled is None:
                fail(
                    DOCUMENT_RECONCILIATION_REQUIRED,
                    "existing registration lacks resolving receipts, ledger evidence, or CAS state",
                )
            existing = reconciled
            registration = _verify_committed(
                existing,
                request=request_payload,
                ports=ports,
                authorization=authorization,
            )
        return _result_envelope(
            invocation=node,
            request=request_payload,
            registration=registration,
            committed=existing,
            policy_decision_ids=authorization.policy_decision_ids,
            replayed=True,
            schema_validation_report_id=(
                f"SVR-{request.request_hash.removeprefix('sha256:')}"
            ),
        )

    # Reject a missing, cross-scope, or cyclic predecessor before reserving or
    # publishing any controlled effect.  The completed registration is checked
    # again below so the sealed artifact and the preflight use the same lineage
    # rule without treating this check as a commit.
    validate_registration_predecessor(request_payload, ports.state.read_registration)
    staged_source = ports.inputs.resolve_staged_source(request.staged_source_artifact_id)
    source_bytes = _verify_resolved_artifact(
        staged_source,
        expected_id=request.staged_source_artifact_id,
        label="staged source",
    )
    reservation = _reserve(ports, node, request_payload)
    source = _publish_source(
        ports, request_payload, staged_source, source_bytes, reservation, str(node["run_id"])
    )
    if content_hash(source_bytes) != source.content_hash:
        fail(DOCUMENT_SOURCE_INTEGRITY_FAILED, "source bytes changed during registration")
    registration = _build_registration(request_payload, source, authorization, reservation)
    validate_registration_lineage(registration.to_dict(), ports.state.read_registration)
    publication = _publish_registration(ports, request_artifact, registration, reservation)
    event = _append_event(
        ports, node, authorization, registration, publication, reservation
    )
    cas = _commit(
        ports, registration, authorization, source, publication, event, reservation
    )
    committed = CommittedRegistration(
        registration=registration.to_dict(),
        source_publication=source,
        registration_publication=publication,
        ledger_publication=event,
        cas=cas,
    )
    verified = _verify_committed(
        committed,
        request=request_payload,
        ports=ports,
        authorization=authorization,
    )
    return _result_envelope(
        invocation=node,
        request=request_payload,
        registration=verified,
        committed=committed,
        policy_decision_ids=authorization.policy_decision_ids,
        replayed=cas.status == "EXISTING",
        schema_validation_report_id=reservation.schema_validation_report_id,
    )


__all__ = [
    "REGISTER_CAPABILITY",
    "REGISTER_DOCUMENT_NODE_ID",
    "REGISTER_SOURCE_ACTION_TYPE",
    "REGISTER_SOURCE_REQUIRED_CAPABILITIES",
    "REGISTRATION_EVENT_TYPE",
    "register_document",
]
