"""Injected authority ports used by K01.

These protocols are adapters over D03 and E01-E03.  They intentionally contain
no in-memory implementation: production registration cannot silently replace
the artifact store, ledger, effect coordinator, capability authority, or CAS
state with process-local state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .models import (
    ActionIntentEvidence,
    ArtifactPublication,
    ArtifactReservation,
    CasOutcome,
    CommittedRegistration,
    EffectReceiptEvidence,
    EffectReservation,
    LeaseAuthorization,
    LedgerPublication,
    LedgerReservation,
    ResolvedArtifact,
)


@runtime_checkable
class InputArtifactPort(Protocol):
    def resolve_registration_request(self, invocation: Mapping[str, Any]) -> ResolvedArtifact: ...

    def resolve_staged_source(self, artifact_id: str) -> ResolvedArtifact: ...


@runtime_checkable
class ArtifactPublicationPort(Protocol):
    def reserve_artifact_receipt(self, *, kind: str, idempotency_key: str) -> ArtifactReservation: ...

    def publish_source_blob(
        self,
        *,
        artifact_id: str,
        content: bytes,
        media_type: str,
        confidentiality: str,
        license_status: str,
        action_intent_id: str,
        receipt_id: str,
        input_artifact_ids: tuple[str, ...],
    ) -> ArtifactPublication: ...

    def publish_registration(
        self,
        *,
        artifact_id: str,
        content: bytes,
        action_intent_id: str,
        receipt_id: str,
        input_artifact_ids: tuple[str, ...],
    ) -> ArtifactPublication: ...


@runtime_checkable
class EffectCoordinationPort(Protocol):
    def resolve_action_intent(self, intent_id: str) -> ActionIntentEvidence | None: ...

    def reserve_source_registration_effect(
        self,
        *,
        run_id: str,
        node_id: str,
        action_type: str,
        target_ref: str,
        arguments_artifact_id: str,
        arguments_hash: str,
        idempotency_key: str,
        required_capabilities: tuple[str, ...],
        risk_class: str,
    ) -> EffectReservation: ...

    def record_source_registration_effect(
        self,
        *,
        reservation: EffectReservation,
        run_id: str,
        idempotency_key: str,
        source_publication: ArtifactPublication,
    ) -> EffectReceiptEvidence: ...


@runtime_checkable
class LedgerPort(Protocol):
    def reserve_registration_event(
        self, *, run_id: str, idempotency_key: str
    ) -> LedgerReservation: ...

    def append_registration_event(
        self,
        *,
        reservation: LedgerReservation,
        run_id: str,
        actor_id: str,
        registration_id: str,
        registration_artifact_id: str,
        registration_artifact_hash: str,
    ) -> LedgerPublication: ...


@runtime_checkable
class LeaseAuthorizationPort(Protocol):
    def authorize_registration(
        self,
        *,
        invocation: Mapping[str, Any],
        request: Mapping[str, Any],
        capability: str,
        resource_scopes: tuple[str, ...],
    ) -> LeaseAuthorization: ...


@runtime_checkable
class RegistrationStatePort(Protocol):
    def lookup_idempotent_registration(self, idempotency_key: str) -> CommittedRegistration | None: ...

    def read_registration(self, registration_id: str) -> Mapping[str, Any] | None: ...

    def reserve_source_blob_id(self, *, idempotency_key: str, request_hash: str) -> str: ...

    def expected_revision(
        self, *, workspace_id: str, corpus_id: str, supersedes_registration_id: str | None
    ) -> int: ...

    def compare_and_swap_registration(
        self,
        *,
        registration: Mapping[str, Any],
        expected_revision: int,
        authorization: LeaseAuthorization,
        source_publication: ArtifactPublication,
        registration_publication: ArtifactPublication,
        effect_receipt: EffectReceiptEvidence,
        ledger_publication: LedgerPublication,
    ) -> CasOutcome: ...

    def reconcile_registration(
        self, *, idempotency_key: str, request_hash: str
    ) -> CommittedRegistration | None: ...


@dataclass(frozen=True)
class RegistrationPorts:
    """Required D03/E01-E03 and CAS adapters for one registration attempt."""

    inputs: InputArtifactPort
    artifacts: ArtifactPublicationPort
    effects: EffectCoordinationPort
    ledger: LedgerPort
    leases: LeaseAuthorizationPort
    state: RegistrationStatePort


__all__ = [
    "ArtifactPublicationPort",
    "EffectCoordinationPort",
    "InputArtifactPort",
    "LeaseAuthorizationPort",
    "LedgerPort",
    "RegistrationPorts",
    "RegistrationStatePort",
]
