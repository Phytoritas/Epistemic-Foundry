"""Immutable value projections crossing the K01 authority ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias, get_args

from ...noetic_ledger.receipts import EffectStatus, ValidationStatus
from .hash import canonical_payload_bytes, verify_registration_payload, verify_request_payload


JsonScalar: TypeAlias = str | int | float | bool | None
FrozenJson: TypeAlias = JsonScalar | tuple["FrozenJson", ...] | Mapping[str, "FrozenJson"]


def _literal_enum(name: str, values: tuple[object, ...]) -> type[Enum]:
    """Project a declaring module's ``Literal`` vocabulary into runtime values."""
    if not values or any(not isinstance(value, str) for value in values):
        raise RuntimeError(f"{name} has no closed string vocabulary")
    return Enum(name, {value.upper(): value for value in values}, type=str)


_ArtifactValidationStatus = _literal_enum(
    "ArtifactValidationStatus", get_args(ValidationStatus)
)
_EffectReceiptStatus = _literal_enum("EffectReceiptStatus", get_args(EffectStatus))
_VALIDATION_PASS = _ArtifactValidationStatus.PASS.value
EFFECT_SUCCEEDED = _EffectReceiptStatus.SUCCEEDED.value


def _freeze_json(value: Any) -> FrozenJson:
    """Recursively freeze JSON-shaped data without exposing mutable children."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value is not JSON-shaped: {type(value).__name__}")


def _thaw_json(value: FrozenJson) -> Any:
    """Return a detached mutable JSON projection from an immutable value."""
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _mapping(value: Mapping[str, Any]) -> Mapping[str, FrozenJson]:
    # ``_freeze_json`` constructs a detached tree recursively, so it is safe
    # for mutable mappings and can also reopen an already-frozen mappingproxy.
    # ``copy.deepcopy`` cannot pickle nested mappingproxy instances and would
    # make immutable replay/reconciliation records impossible to reconstruct.
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - mapping input guarantees this
        raise TypeError("expected a JSON object")
    return frozen


@dataclass(frozen=True)
class ActionIntentEvidence:
    intent_id: str
    run_id: str
    node_id: str
    action_type: str
    target_ref: str
    arguments_artifact_id: str
    arguments_hash: str
    idempotency_key: str
    required_capabilities: tuple[str, ...]
    approval_record_ids: tuple[str, ...]
    risk_class: str
    created_at: str
    intent_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ActionIntentEvidence":
        return cls(
            intent_id=str(payload["intent_id"]),
            run_id=str(payload["run_id"]),
            node_id=str(payload["node_id"]),
            action_type=str(payload["action_type"]),
            target_ref=str(payload["target_ref"]),
            arguments_artifact_id=str(payload["arguments_artifact_id"]),
            arguments_hash=str(payload["arguments_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            required_capabilities=tuple(payload["required_capabilities"]),
            approval_record_ids=tuple(payload["approval_record_ids"]),
            risk_class=str(payload["risk_class"]),
            created_at=str(payload["created_at"]),
            intent_hash=str(payload["intent_hash"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "action_type": self.action_type,
            "target_ref": self.target_ref,
            "arguments_artifact_id": self.arguments_artifact_id,
            "arguments_hash": self.arguments_hash,
            "idempotency_key": self.idempotency_key,
            "required_capabilities": list(self.required_capabilities),
            "approval_record_ids": list(self.approval_record_ids),
            "risk_class": self.risk_class,
            "created_at": self.created_at,
            "intent_hash": self.intent_hash,
        }


@dataclass(frozen=True)
class ArtifactReceiptEvidence:
    receipt_id: str
    artifact_id: str
    action_intent_id: str | None
    content_hash: str
    byte_size: int
    media_type: str
    created_by: Mapping[str, Any]
    created_at: str
    locator: str
    schema_ref: str | None
    validation_results: tuple[Mapping[str, Any], ...]
    receipt_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_by", _mapping(self.created_by))
        object.__setattr__(
            self,
            "validation_results",
            tuple(_mapping(result) for result in self.validation_results),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ArtifactReceiptEvidence":
        return cls(
            receipt_id=str(payload["receipt_id"]),
            artifact_id=str(payload["artifact_id"]),
            action_intent_id=payload["action_intent_id"],
            content_hash=str(payload["content_hash"]),
            byte_size=int(payload["byte_size"]),
            media_type=str(payload["media_type"]),
            created_by=payload["created_by"],
            created_at=str(payload["created_at"]),
            locator=str(payload["locator"]),
            schema_ref=payload["schema_ref"],
            validation_results=tuple(payload["validation_results"]),
            receipt_hash=str(payload["receipt_hash"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "artifact_id": self.artifact_id,
            "action_intent_id": self.action_intent_id,
            "media_type": self.media_type,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size,
            "created_by": _thaw_json(self.created_by),
            "created_at": self.created_at,
            "locator": self.locator,
            "schema_ref": self.schema_ref,
            "validation_results": [
                _thaw_json(result) for result in self.validation_results
            ],
            "receipt_hash": self.receipt_hash,
        }

    @property
    def validation_passed(self) -> bool:
        return bool(self.validation_results) and all(
            result["status"] == _VALIDATION_PASS for result in self.validation_results
        )


@dataclass(frozen=True)
class EffectReceiptEvidence:
    receipt_id: str
    intent_id: str
    run_id: str
    external_operation_id: str | None
    status: str
    result_artifact_ids: tuple[str, ...]
    error_artifact_ids: tuple[str, ...]
    idempotency_key: str
    reconciliation_required: bool
    observed_state_hash: str | None
    started_at: str
    finished_at: str
    receipt_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EffectReceiptEvidence":
        return cls(
            receipt_id=str(payload["receipt_id"]),
            intent_id=str(payload["intent_id"]),
            run_id=str(payload["run_id"]),
            external_operation_id=payload["external_operation_id"],
            status=str(payload["status"]),
            result_artifact_ids=tuple(payload["result_artifact_ids"]),
            error_artifact_ids=tuple(payload["error_artifact_ids"]),
            observed_state_hash=payload["observed_state_hash"],
            idempotency_key=str(payload["idempotency_key"]),
            started_at=str(payload["started_at"]),
            finished_at=str(payload["finished_at"]),
            reconciliation_required=bool(payload["reconciliation_required"]),
            receipt_hash=str(payload["receipt_hash"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "external_operation_id": self.external_operation_id,
            "status": self.status,
            "result_artifact_ids": list(self.result_artifact_ids),
            "error_artifact_ids": list(self.error_artifact_ids),
            "observed_state_hash": self.observed_state_hash,
            "idempotency_key": self.idempotency_key,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "reconciliation_required": self.reconciliation_required,
            "receipt_hash": self.receipt_hash,
        }


@dataclass(frozen=True)
class ResolvedArtifact:
    artifact_id: str
    content: bytes
    content_hash: str
    byte_size: int
    media_type: str
    receipt: ArtifactReceiptEvidence

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", bytes(self.content))


@dataclass(frozen=True)
class LeaseAuthorization:
    lease_id: str
    principal_id: str
    fencing_token: int
    capability: str
    resource_scopes: tuple[str, ...]
    policy_decision_ids: tuple[str, ...] = ()
    current: bool = True


@dataclass(frozen=True)
class EffectReservation:
    action_intent: ActionIntentEvidence
    attempt_id: str
    effect_receipt_id: str
    started_at: str

    @property
    def action_intent_id(self) -> str:
        return self.action_intent.intent_id


@dataclass(frozen=True)
class ArtifactReservation:
    artifact_receipt_id: str


@dataclass(frozen=True)
class LedgerReservation:
    event_id: str
    occurred_at: str


@dataclass(frozen=True)
class RegistrationReservation:
    source_blob_artifact_id: str
    source_artifact: ArtifactReservation
    registration_artifact: ArtifactReservation
    effect: EffectReservation
    ledger: LedgerReservation
    registered_at: str
    expected_revision: int
    schema_validation_report_id: str


@dataclass(frozen=True)
class SourcePublication:
    artifact_id: str
    content_hash: str
    byte_size: int
    media_type: str
    receipt: ArtifactReceiptEvidence
    effect: EffectReceiptEvidence


@dataclass(frozen=True)
class ArtifactPublication:
    artifact_id: str
    content_hash: str
    byte_size: int
    media_type: str
    receipt: ArtifactReceiptEvidence


@dataclass(frozen=True)
class LedgerPublication:
    event_id: str
    run_id: str
    sequence: int
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_id: str
    payload_artifact_id: str
    payload_hash: str
    previous_event_hash: str | None
    event_hash: str
    occurred_at: str
    schema_version: str
    status: str

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, status: str
    ) -> "LedgerPublication":
        return cls(
            event_id=str(payload["event_id"]),
            run_id=str(payload["run_id"]),
            sequence=int(payload["sequence"]),
            event_type=str(payload["event_type"]),
            aggregate_type=str(payload["aggregate_type"]),
            aggregate_id=str(payload["aggregate_id"]),
            actor_id=str(payload["actor_id"]),
            payload_artifact_id=str(payload["payload_artifact_id"]),
            payload_hash=str(payload["payload_hash"]),
            previous_event_hash=payload["previous_event_hash"],
            event_hash=str(payload["event_hash"]),
            occurred_at=str(payload["occurred_at"]),
            schema_version=str(payload["schema_version"]),
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "actor_id": self.actor_id,
            "payload_artifact_id": self.payload_artifact_id,
            "payload_hash": self.payload_hash,
            "previous_event_hash": self.previous_event_hash,
            "event_hash": self.event_hash,
            "occurred_at": self.occurred_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class CasOutcome:
    ok: bool
    status: str
    expected_revision: int
    current_revision: int | None
    registration_id: str | None
    registration_hash: str | None
    request_hash: str | None
    fencing_token: int | None


@dataclass(frozen=True)
class DocumentRegistrationRequest:
    """An immutable, validated request backed by sealed canonical bytes."""

    _payload: Mapping[str, FrozenJson] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_payload",
            _mapping(verify_request_payload(_thaw_json(self._payload))),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DocumentRegistrationRequest":
        return cls(payload)

    def to_dict(self) -> dict[str, Any]:
        return _thaw_json(self._payload)

    def canonical_bytes(self) -> bytes:
        return canonical_payload_bytes(self.to_dict())

    def __getitem__(self, key: str) -> Any:
        return _thaw_json(self._payload[key])

    @property
    def request_id(self) -> str:
        return str(self._payload["request_id"])

    @property
    def request_hash(self) -> str:
        return str(self._payload["request_hash"])

    @property
    def idempotency_key(self) -> str:
        return str(self._payload["idempotency_key"])

    @property
    def staged_source_artifact_id(self) -> str:
        return str(self._payload["staged_source_artifact_id"])


@dataclass(frozen=True)
class DocumentRegistration:
    """An immutable, validated initial registration artifact."""

    _payload: Mapping[str, FrozenJson] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_payload",
            _mapping(verify_registration_payload(_thaw_json(self._payload))),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DocumentRegistration":
        return cls(payload)

    def to_dict(self) -> dict[str, Any]:
        return _thaw_json(self._payload)

    def canonical_bytes(self) -> bytes:
        return canonical_payload_bytes(self.to_dict())

    def __getitem__(self, key: str) -> Any:
        return _thaw_json(self._payload[key])

    @property
    def registration_id(self) -> str:
        return str(self._payload["registration_id"])

    @property
    def registration_hash(self) -> str:
        return str(self._payload["registration_hash"])


@dataclass(frozen=True)
class CommittedRegistration:
    registration: Mapping[str, Any]
    source_publication: SourcePublication
    registration_publication: ArtifactPublication
    ledger_publication: LedgerPublication
    cas: CasOutcome

    def __post_init__(self) -> None:
        object.__setattr__(self, "registration", _mapping(self.registration))


__all__ = [
    "ActionIntentEvidence",
    "ArtifactPublication",
    "ArtifactReceiptEvidence",
    "ArtifactReservation",
    "CasOutcome",
    "CommittedRegistration",
    "DocumentRegistration",
    "DocumentRegistrationRequest",
    "EffectReceiptEvidence",
    "EffectReservation",
    "LeaseAuthorization",
    "LedgerPublication",
    "LedgerReservation",
    "RegistrationReservation",
    "ResolvedArtifact",
    "SourcePublication",
]
