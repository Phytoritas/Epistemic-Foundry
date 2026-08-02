from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.ingest.registry import (
    ActionIntentEvidence,
    ArtifactPublication,
    ArtifactReceiptEvidence,
    ArtifactReservation,
    CasOutcome,
    CommittedRegistration,
    DocumentRegistryError,
    EffectReceiptEvidence,
    EffectReservation,
    LeaseAuthorization,
    LedgerPublication,
    LedgerReservation,
    RegistrationPorts,
    ResolvedArtifact,
    SourcePublication,
    compute_registration_hash,
    compute_request_hash,
    register_document,
    seal_registration_payload,
    seal_request_payload,
    verify_registration_payload,
    verify_request_payload,
)
from epistemic_foundry.ingest.registry.hash import canonical_payload_bytes, content_hash


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "k01"
SOURCE_BYTES = b"K01 deterministic immutable source bytes\n"
ZERO_HASH = "sha256:" + "0" * 64
RUN_ID = "RUN-K01-0001"
LEASE_TOKEN = 17
PRINCIPAL_ID = "principal:k01-fixture"
REGISTERED_AT = "2026-07-30T01:02:00Z"
EFFECT_STARTED_AT = "2026-07-30T01:01:30Z"
EFFECT_FINISHED_AT = "2026-07-30T01:02:30Z"


def load_fixture(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def make_request(**changes: Any) -> dict[str, Any]:
    payload = load_fixture("document-registration-request.valid.json")
    payload.pop("request_id")
    payload.pop("request_hash")
    payload.update(copy.deepcopy(changes))
    return seal_request_payload(payload)


def make_registration(**changes: Any) -> dict[str, Any]:
    payload = load_fixture("document-registration.valid.json")
    payload.pop("registration_id")
    payload.pop("registration_hash")
    payload.update(copy.deepcopy(changes))
    return seal_registration_payload(payload)


def make_artifact_receipt(
    *,
    receipt_id: str,
    artifact_id: str,
    content: bytes,
    media_type: str,
    action_intent_id: str | None,
    schema_ref: str | None,
    validation_status: str = "PASS",
) -> ArtifactReceiptEvidence:
    payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "artifact_id": artifact_id,
        "action_intent_id": action_intent_id,
        "media_type": media_type,
        "content_hash": content_hash(content),
        "byte_size": len(content),
        "created_by": {
            "actor_id": "service:k01-fixture",
            "actor_type": "service",
        },
        "created_at": "2026-07-30T01:01:00Z",
        "locator": f"artifact://k01/{artifact_id}",
        "schema_ref": schema_ref,
        "validation_results": [
            {
                "check": "canonical_contract",
                "status": validation_status,
                "details": "deterministic K01 fixture validation",
            }
        ],
    }
    payload["receipt_hash"] = hash_excluding(payload, "receipt_hash")
    return ArtifactReceiptEvidence.from_payload(payload)


def invocation_for(
    request: Mapping[str, Any], *, attempt: int = 1, lease_token: int = LEASE_TOKEN
) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "node_id": "register_document",
        "attempt": attempt,
        "run_spec_artifact_id": "ART-RUN-SPEC-K01-0001",
        "input_artifact_ids": [request["request_id"]],
        "context_manifest_id": None,
        "input_hash": request["request_hash"],
        "deadline_at": "2026-07-30T02:00:00Z",
        "lease_token": lease_token,
        "policy_bundle_id": "POLICY-K01-0001",
        "expected_output_schema_hash": "sha256:" + "1" * 64,
        "capability_grant_ids": ["GRANT-DOCUMENT-REGISTER-K01-0001"],
    }


class RegistrationHarness:
    """Canonical-evidence test double for all required shared-authority ports."""

    def __init__(self, request: Mapping[str, Any] | None = None) -> None:
        self.request = copy.deepcopy(dict(request or make_request()))
        self.source_bytes = SOURCE_BYTES
        self.calls: Counter[str] = Counter()
        self.committed_by_key: dict[str, CommittedRegistration] = {}
        self.action_intents: dict[str, ActionIntentEvidence] = {}
        self.history: dict[str, dict[str, Any]] = {}
        self.reconciled_by_key: dict[str, CommittedRegistration] = {}
        self.source_missing = False
        self.source_projection_hash_mismatch = False
        self.source_validation_status = "PASS"
        self.source_media_type = "text/plain"
        self.stale_lease = False
        self.effect_missing = False
        self.effect_status = "SUCCEEDED"
        self.effect_reconciliation_required = False
        self.wrong_receipt_intent = False
        self.wrong_event_actor = False
        self.cas_failure = False
        self.cas_revision_offset = 1

    @property
    def ports(self) -> RegistrationPorts:
        return RegistrationPorts(
            inputs=self,
            artifacts=self,
            effects=self,
            ledger=self,
            leases=self,
            state=self,
        )

    def resolve_registration_request(
        self, invocation: Mapping[str, Any]
    ) -> ResolvedArtifact:
        self.calls["resolve_registration_request"] += 1
        content = canonical_payload_bytes(self.request)
        artifact_id = str(self.request["request_id"])
        return ResolvedArtifact(
            artifact_id=artifact_id,
            content=content,
            content_hash=content_hash(content),
            byte_size=len(content),
            media_type="application/json",
            receipt=make_artifact_receipt(
                receipt_id="AR-REQUEST-K01-0001",
                artifact_id=artifact_id,
                content=content,
                media_type="application/json",
                action_intent_id=None,
                schema_ref="schemas/document-registration-request.schema.json",
            ),
        )

    def resolve_staged_source(self, artifact_id: str) -> ResolvedArtifact | None:
        self.calls["resolve_staged_source"] += 1
        if self.source_missing:
            return None
        receipt = make_artifact_receipt(
            receipt_id="AR-STAGED-SOURCE-K01-0001",
            artifact_id=artifact_id,
            content=self.source_bytes,
            media_type=self.source_media_type,
            action_intent_id="INTENT-STAGE-SOURCE-K01-0001",
            schema_ref=None,
            validation_status=self.source_validation_status,
        )
        return ResolvedArtifact(
            artifact_id=artifact_id,
            content=self.source_bytes,
            content_hash=(
                ZERO_HASH
                if self.source_projection_hash_mismatch
                else content_hash(self.source_bytes)
            ),
            byte_size=len(self.source_bytes),
            media_type=self.source_media_type,
            receipt=receipt,
        )

    def authorize_registration(
        self,
        *,
        invocation: Mapping[str, Any],
        request: Mapping[str, Any],
        capability: str,
        resource_scopes: tuple[str, ...],
    ) -> LeaseAuthorization:
        self.calls["authorize_registration"] += 1
        return LeaseAuthorization(
            lease_id="LEASE-K01-0001",
            principal_id=PRINCIPAL_ID,
            fencing_token=(LEASE_TOKEN + 1 if self.stale_lease else LEASE_TOKEN),
            capability=capability,
            resource_scopes=resource_scopes,
            policy_decision_ids=("POLICY-DECISION-K01-0001",),
            current=True,
        )

    def lookup_idempotent_registration(
        self, idempotency_key: str
    ) -> CommittedRegistration | None:
        self.calls["lookup_idempotent_registration"] += 1
        return self.committed_by_key.get(idempotency_key)

    def read_registration(self, registration_id: str) -> Mapping[str, Any] | None:
        self.calls["read_registration"] += 1
        value = self.history.get(registration_id)
        return copy.deepcopy(value) if value is not None else None

    def reserve_source_blob_id(self, *, idempotency_key: str, request_hash: str) -> str:
        self.calls["reserve_source_blob_id"] += 1
        return "ART-SOURCE-BLOB-" + request_hash.removeprefix("sha256:")[:24]

    def reserve_artifact_receipt(
        self, *, kind: str, idempotency_key: str
    ) -> ArtifactReservation:
        self.calls[f"reserve_artifact_receipt:{kind}"] += 1
        if kind == "source_blob":
            return ArtifactReservation("AR-SOURCE-BLOB-K01-0001")
        if kind == "document_registration":
            return ArtifactReservation("AR-DOCUMENT-REGISTRATION-K01-0001")
        raise AssertionError(f"unexpected artifact reservation kind: {kind}")

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
    ) -> EffectReservation:
        self.calls["reserve_source_registration_effect"] += 1
        assert run_id == RUN_ID
        assert node_id == "register_document"
        assert action_type == "register_document_source"
        assert target_ref.startswith("ART-SOURCE-BLOB-")
        assert arguments_artifact_id == self.request["request_id"]
        assert arguments_hash == self.request["request_hash"]
        assert idempotency_key == self.request["idempotency_key"]
        assert required_capabilities == ("artifact_write", "document_register")
        assert risk_class == "controlled_effect"
        payload: dict[str, Any] = {
            "intent_id": "INTENT-REGISTER-SOURCE-K01-0001",
            "run_id": run_id,
            "node_id": node_id,
            "action_type": action_type,
            "target_ref": target_ref,
            "arguments_artifact_id": arguments_artifact_id,
            "arguments_hash": arguments_hash,
            "idempotency_key": idempotency_key,
            "required_capabilities": list(required_capabilities),
            "approval_record_ids": [],
            "risk_class": risk_class,
            "created_at": EFFECT_STARTED_AT,
        }
        payload["intent_hash"] = hash_excluding(payload, "intent_hash")
        intent = ActionIntentEvidence.from_payload(payload)
        self.action_intents[intent.intent_id] = intent
        return EffectReservation(
            action_intent=intent,
            attempt_id="ATTEMPT-REGISTER-SOURCE-K01-0001",
            effect_receipt_id="EFF-SOURCE-K01-0001",
            started_at=EFFECT_STARTED_AT,
        )

    def resolve_action_intent(
        self, intent_id: str
    ) -> ActionIntentEvidence | None:
        self.calls["resolve_action_intent"] += 1
        return self.action_intents.get(intent_id)

    def reserve_registration_event(
        self, *, run_id: str, idempotency_key: str
    ) -> LedgerReservation:
        self.calls["reserve_registration_event"] += 1
        assert run_id == RUN_ID
        assert idempotency_key == self.request["idempotency_key"]
        return LedgerReservation(
            event_id="EV-DOCUMENT-REGISTERED-K01-0001",
            occurred_at=REGISTERED_AT,
        )

    def expected_revision(
        self,
        *,
        workspace_id: str,
        corpus_id: str,
        supersedes_registration_id: str | None,
    ) -> int:
        self.calls["expected_revision"] += 1
        return 1 if supersedes_registration_id is not None else 0

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
    ) -> ArtifactPublication:
        self.calls["publish_source_blob"] += 1
        assert bytes(content) == self.source_bytes
        assert confidentiality == self.request["confidentiality"]
        assert license_status == self.request["declared_license_status"]
        assert input_artifact_ids == (self.request["staged_source_artifact_id"],)
        receipt = make_artifact_receipt(
            receipt_id=receipt_id,
            artifact_id=artifact_id,
            content=bytes(content),
            media_type=media_type,
            action_intent_id=(
                "INTENT-WRONG-K01-0001" if self.wrong_receipt_intent else action_intent_id
            ),
            schema_ref=None,
        )
        publication = ArtifactPublication(
            artifact_id=artifact_id,
            content_hash=content_hash(bytes(content)),
            byte_size=len(content),
            media_type=media_type,
            receipt=receipt,
        )
        self._source_artifact_publication = publication
        return publication

    def record_source_registration_effect(
        self,
        *,
        reservation: EffectReservation,
        run_id: str,
        idempotency_key: str,
        source_publication: ArtifactPublication,
    ) -> EffectReceiptEvidence | None:
        self.calls["record_source_registration_effect"] += 1
        if self.effect_missing:
            return None
        payload: dict[str, Any] = {
            "receipt_id": reservation.effect_receipt_id,
            "intent_id": reservation.action_intent_id,
            "run_id": run_id,
            "external_operation_id": "fixture-operation:k01-source-publication",
            "status": self.effect_status,
            "result_artifact_ids": [source_publication.artifact_id],
            "error_artifact_ids": [],
            "observed_state_hash": source_publication.content_hash,
            "idempotency_key": idempotency_key,
            "started_at": reservation.started_at,
            "finished_at": EFFECT_FINISHED_AT,
            "reconciliation_required": self.effect_reconciliation_required,
        }
        payload["receipt_hash"] = hash_excluding(payload, "receipt_hash")
        return EffectReceiptEvidence.from_payload(payload)

    def publish_registration(
        self,
        *,
        artifact_id: str,
        content: bytes,
        action_intent_id: str,
        receipt_id: str,
        input_artifact_ids: tuple[str, ...],
    ) -> ArtifactPublication:
        self.calls["publish_registration"] += 1
        registration = json.loads(bytes(content).decode("utf-8"))
        assert artifact_id == registration["registration_id"]
        assert input_artifact_ids == (
            self.request["request_id"],
            registration["source_blob_artifact_id"],
        )
        receipt = make_artifact_receipt(
            receipt_id=receipt_id,
            artifact_id=artifact_id,
            content=bytes(content),
            media_type="application/json",
            action_intent_id=(
                "INTENT-WRONG-K01-0001" if self.wrong_receipt_intent else action_intent_id
            ),
            schema_ref="schemas/document-registration.schema.json",
        )
        publication = ArtifactPublication(
            artifact_id=artifact_id,
            content_hash=content_hash(bytes(content)),
            byte_size=len(content),
            media_type="application/json",
            receipt=receipt,
        )
        self._registration_artifact_publication = publication
        return publication

    def append_registration_event(
        self,
        *,
        reservation: LedgerReservation,
        run_id: str,
        actor_id: str,
        registration_id: str,
        registration_artifact_id: str,
        registration_artifact_hash: str,
    ) -> LedgerPublication:
        self.calls["append_registration_event"] += 1
        payload: dict[str, Any] = {
            "event_id": reservation.event_id,
            "run_id": run_id,
            "sequence": len(self.history) + 1,
            "event_type": "document.registration.created",
            "aggregate_type": "document_registration",
            "aggregate_id": registration_id,
            "actor_id": (
                "principal:wrong-k01-fixture" if self.wrong_event_actor else actor_id
            ),
            "payload_artifact_id": registration_artifact_id,
            "payload_hash": registration_artifact_hash,
            "previous_event_hash": None,
            "occurred_at": reservation.occurred_at,
            "schema_version": "4.0.0",
        }
        payload["event_hash"] = hash_excluding(payload, "event_hash")
        return LedgerPublication.from_payload(payload, status="APPENDED")

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
    ) -> CasOutcome:
        self.calls["compare_and_swap_registration"] += 1
        if self.cas_failure:
            return CasOutcome(
                ok=False,
                status="CONFLICT",
                expected_revision=expected_revision,
                current_revision=expected_revision,
                registration_id=None,
                registration_hash=None,
                request_hash=None,
                fencing_token=authorization.fencing_token,
            )
        current_revision = expected_revision + self.cas_revision_offset
        outcome = CasOutcome(
            ok=True,
            status="COMMITTED",
            expected_revision=expected_revision,
            current_revision=current_revision,
            registration_id=str(registration["registration_id"]),
            registration_hash=str(registration["registration_hash"]),
            request_hash=str(registration["request_hash"]),
            fencing_token=authorization.fencing_token,
        )
        committed = CommittedRegistration(
            registration=registration,
            source_publication=SourcePublication(
                artifact_id=source_publication.artifact_id,
                content_hash=source_publication.content_hash,
                byte_size=source_publication.byte_size,
                media_type=source_publication.media_type,
                receipt=source_publication.receipt,
                effect=effect_receipt,
            ),
            registration_publication=registration_publication,
            ledger_publication=ledger_publication,
            cas=outcome,
        )
        idempotency_key = str(registration["idempotency_key"])
        self.committed_by_key[idempotency_key] = committed
        self.history[str(registration["registration_id"])] = copy.deepcopy(
            dict(registration)
        )
        return outcome

    def reconcile_registration(
        self, *, idempotency_key: str, request_hash: str
    ) -> CommittedRegistration | None:
        self.calls["reconcile_registration"] += 1
        candidate = self.reconciled_by_key.get(idempotency_key)
        if candidate is None:
            return None
        if candidate.registration["request_hash"] != request_hash:
            return None
        return candidate

    def run(self, *, attempt: int = 1) -> dict[str, Any]:
        return register_document(
            invocation_for(self.request, attempt=attempt), ports=self.ports
        )


def assert_code(code: str, operation: Any) -> DocumentRegistryError:
    with pytest.raises(DocumentRegistryError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


def run_oracle_case(case_id: str) -> str:
    if case_id == "K01-ORACLE-01-VALID-REQUEST-HASH-ID":
        request = verify_request_payload(load_fixture("document-registration-request.valid.json"))
        assert request["request_hash"] == compute_request_hash(request)
        return "PASS"
    if case_id == "K01-ORACLE-02-CANONICAL-HINT-ORDER":
        request = make_request(
            external_identifier_hints=[
                {
                    "scheme": "URL",
                    "value": "https://z.example/k01",
                    "declared_by": PRINCIPAL_ID,
                    "verified": False,
                },
                {
                    "scheme": "DOI",
                    "value": "10.0000/k01",
                    "declared_by": PRINCIPAL_ID,
                    "verified": False,
                },
            ]
        )
        assert request["external_identifier_hints"][0]["scheme"] == "DOI"
        return "PASS"
    if case_id == "K01-ORACLE-03-UNKNOWN-REQUEST-FIELD":
        request = make_request()
        request["unknown"] = True
        return assert_code("DOCUMENT_CONTRACT_INVALID", lambda: verify_request_payload(request)).code
    if case_id == "K01-ORACLE-04-PATH-FILENAME":
        request = make_request()
        request["declared_filename"] = "../fixture.txt"
        return assert_code("DOCUMENT_CONTRACT_INVALID", lambda: verify_request_payload(request)).code
    if case_id == "K01-ORACLE-05-FILE-URI":
        request = make_request()
        request["source_origin"]["original_uri"] = "file:///private/fixture.txt"
        return assert_code("DOCUMENT_CONTRACT_INVALID", lambda: verify_request_payload(request)).code
    if case_id == "K01-ORACLE-06-REQUEST-HASH-MISMATCH":
        request = make_request()
        request["request_hash"] = ZERO_HASH
        return assert_code("DOCUMENT_REQUEST_HASH_MISMATCH", lambda: verify_request_payload(request)).code
    if case_id == "K01-ORACLE-07-REQUEST-ID-MISMATCH":
        request = make_request()
        request["request_id"] = "DREQ-" + "0" * 64
        return assert_code("DOCUMENT_REQUEST_ID_MISMATCH", lambda: verify_request_payload(request)).code
    if case_id == "K01-ORACLE-08-VALID-REGISTRATION-HASH-ID":
        registration = verify_registration_payload(
            load_fixture("document-registration.valid.json")
        )
        assert registration["registration_hash"] == compute_registration_hash(registration)
        return "PASS"
    if case_id == "K01-ORACLE-09-FIXED-INITIAL-STATE":
        invalid = load_fixture("document-registration.invalid.json")
        return assert_code(
            "DOCUMENT_CONTRACT_INVALID", lambda: verify_registration_payload(invalid)
        ).code
    if case_id == "K01-ORACLE-10-REGISTRATION-HASH-MISMATCH":
        registration = make_registration()
        registration["registration_hash"] = ZERO_HASH
        return assert_code(
            "DOCUMENT_REGISTRATION_HASH_MISMATCH",
            lambda: verify_registration_payload(registration),
        ).code

    harness = RegistrationHarness()
    if case_id == "K01-ORACLE-11-STAGED-SOURCE-MISSING":
        harness.source_missing = True
        return assert_code("DOCUMENT_SOURCE_ARTIFACT_MISSING", harness.run).code
    if case_id == "K01-ORACLE-12-SOURCE-BYTE-HASH-MISMATCH":
        harness.source_projection_hash_mismatch = True
        return assert_code("DOCUMENT_SOURCE_INTEGRITY_FAILED", harness.run).code
    if case_id == "K01-ORACLE-13-SOURCE-RECEIPT-NOT-PASS":
        harness.source_validation_status = "NOT_RUN"
        return assert_code("DOCUMENT_SOURCE_RECEIPT_MISSING", harness.run).code
    if case_id == "K01-ORACLE-14-MEDIA-TYPE-MISMATCH":
        harness.source_media_type = "application/pdf"
        return assert_code("DOCUMENT_MEDIA_TYPE_MISMATCH", harness.run).code
    if case_id == "K01-ORACLE-15-STALE-FENCING-TOKEN":
        harness.stale_lease = True
        return assert_code("DOCUMENT_STALE_FENCING_TOKEN", harness.run).code
    if case_id == "K01-ORACLE-16-EXACT-IDEMPOTENT-REPLAY":
        first = harness.run()
        first_counts = harness.calls.copy()
        second = harness.run(attempt=2)
        assert first["output_artifact_ids"] == second["output_artifact_ids"]
        assert second["metrics"]["replayed"] is True
        assert harness.calls["publish_source_blob"] == first_counts["publish_source_blob"]
        assert harness.calls["compare_and_swap_registration"] == first_counts[
            "compare_and_swap_registration"
        ]
        return "PASS"
    if case_id == "K01-ORACLE-17-IDEMPOTENCY-CONFLICT":
        harness.run()
        harness.request = make_request(declared_filename="changed-fixture.txt")
        return assert_code("DOCUMENT_IDEMPOTENCY_CONFLICT", harness.run).code
    if case_id == "K01-ORACLE-18-VALID-SUPERSESSION":
        first = harness.run()
        predecessor = first["output_artifact_ids"][0]
        harness.request = make_request(
            declared_filename="fixture-v2.txt",
            idempotency_key="doc-register-fixture-0002",
            supersedes_registration_id=predecessor,
        )
        second = harness.run()
        assert second["metrics"]["registration_revision"] == 2
        return "PASS"
    if case_id == "K01-ORACLE-19-UNKNOWN-PREDECESSOR":
        harness.request = make_request(
            idempotency_key="doc-register-unknown-predecessor",
            supersedes_registration_id="DREG-" + "a" * 64,
        )
        return assert_code("DOCUMENT_LINEAGE_UNKNOWN", harness.run).code
    if case_id == "K01-ORACLE-20-CROSS-SCOPE-OR-CYCLE":
        harness.request = make_request(
            workspace_id="WS-OTHER-K01",
            idempotency_key="doc-register-other-scope",
        )
        first = harness.run()
        predecessor = first["output_artifact_ids"][0]
        harness.request = make_request(
            idempotency_key="doc-register-cross-scope",
            supersedes_registration_id=predecessor,
        )
        return assert_code("DOCUMENT_LINEAGE_SCOPE_MISMATCH", harness.run).code
    if case_id == "K01-ORACLE-21-MISSING-EFFECT-OR-CRASH-RECONCILIATION":
        harness.effect_missing = True
        return assert_code("DOCUMENT_EFFECT_RECEIPT_MISSING", harness.run).code
    if case_id == "K01-ORACLE-22-CAS-OR-ENVELOPE-ONLY":
        harness.cas_failure = True
        return assert_code("DOCUMENT_CAS_CONFLICT", harness.run).code
    raise AssertionError(f"unknown K01 oracle case: {case_id}")


ORACLE = load_fixture("document-effect-cases.json")


def test_oracle_fixture_has_exactly_22_stable_unique_cases() -> None:
    cases = ORACLE["cases"]
    assert ORACLE["fixture_version"] == "K01-0002"
    assert ORACLE["case_count"] == len(cases) == 22
    assert len({case["case_id"] for case in cases}) == 22
    for number, case in enumerate(cases, start=1):
        assert case["case_id"].startswith(f"K01-ORACLE-{number:02d}-")


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case_id"])
def test_document_registration_oracle_22(case: dict[str, str]) -> None:
    observed = run_oracle_case(case["case_id"])
    assert observed in case["expected"].split("|")


def test_request_and_registration_wrappers_are_recursively_immutable() -> None:
    from epistemic_foundry.ingest.registry import (
        DocumentRegistration,
        DocumentRegistrationRequest,
    )

    request_payload = make_request()
    request = DocumentRegistrationRequest.from_payload(request_payload)
    request_payload["source_origin"]["kind"] = "UPLOAD"
    assert request["source_origin"]["kind"] == "REMOTE_FETCH"
    detached_request = request.to_dict()
    detached_request["source_origin"]["kind"] = "UPLOAD"
    assert request["source_origin"]["kind"] == "REMOTE_FETCH"

    registration_payload = make_registration()
    registration = DocumentRegistration.from_payload(registration_payload)
    registration_payload["source_origin"]["kind"] = "UPLOAD"
    assert registration["source_origin"]["kind"] == "REMOTE_FETCH"
    detached_registration = registration.to_dict()
    detached_registration["external_identifier_hints"].clear()
    assert len(registration["external_identifier_hints"]) == 1


def test_publication_receipt_must_bind_the_reserved_action_intent() -> None:
    harness = RegistrationHarness()
    harness.wrong_receipt_intent = True
    assert_code("DOCUMENT_ARTIFACT_RECEIPT_MISMATCH", harness.run)


def test_success_is_not_emitted_before_the_receipt_bound_cas() -> None:
    harness = RegistrationHarness()
    result = harness.run()
    registration_id = result["output_artifact_ids"][0]
    committed = harness.committed_by_key[harness.request["idempotency_key"]]

    assert result["status"] == "success"
    assert result["effect_receipt_ids"] == [committed.source_publication.effect.receipt_id]
    assert registration_id == committed.registration["registration_id"]
    assert committed.cas.ok is True
    assert harness.calls["compare_and_swap_registration"] == 1


@pytest.mark.parametrize("revision_offset", [0, 2])
def test_commit_rejects_cas_without_exactly_one_revision_advance(
    revision_offset: int,
) -> None:
    harness = RegistrationHarness()
    harness.cas_revision_offset = revision_offset

    assert_code("DOCUMENT_CAS_CONFLICT", harness.run)


def test_replay_rejects_a_registration_artifact_from_another_intent() -> None:
    harness = RegistrationHarness()
    harness.run()
    key = str(harness.request["idempotency_key"])
    committed = harness.committed_by_key[key]
    publication = committed.registration_publication
    payload = publication.receipt.to_dict()
    payload["action_intent_id"] = "INTENT-OTHER-K01-0001"
    payload["receipt_hash"] = hash_excluding(payload, "receipt_hash")
    bad_publication = replace(
        publication, receipt=ArtifactReceiptEvidence.from_payload(payload)
    )
    harness.committed_by_key[key] = replace(
        committed, registration_publication=bad_publication
    )

    assert_code("DOCUMENT_RECONCILIATION_REQUIRED", lambda: harness.run(attempt=2))
