from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.ingest.registry import register_document
from tests.ingest.test_k01_document_registration import RegistrationHarness


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "corpus_ingest.workflow.yaml"


def register_node() -> dict[str, object]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return next(
        node for node in workflow["nodes"] if node["node_id"] == "register_document"
    )


def test_register_document_workflow_binding_is_exact_and_deterministic() -> None:
    node = register_node()
    assert node["executor_type"] == "deterministic"
    assert node["executor_ref"] == "epistemic_foundry.ingest.registry:register_document"
    assert node["input_schema_ref"] == "schemas/node-invocation.schema.json"
    assert node["output_schema_ref"] == "schemas/result-envelope.schema.json"
    assert node["depends_on"] == []
    assert node["model_tier"] == "deterministic"
    assert node["determinism_class"] == "deterministic"
    assert node["idempotency_key_fields"] == ["idempotency_key", "request_hash"]
    assert node["capabilities"] == [
        "artifact_read",
        "artifact_write",
        "ledger_append",
        "document_register",
    ]
    assert node["read_scope"] == [
        "artifacts/staged_source/**",
        "artifacts/document_registration_requests/**",
        "policy/**",
    ]
    assert node["write_scope"] == [
        "artifacts/source/**",
        "artifacts/document_registrations/**",
        "ledger/events/document_registration/**",
        "state/document_registrations/**",
    ]


def test_workflow_requires_receipt_lineage_lease_and_cas_checks() -> None:
    checks = set(register_node()["acceptance_checks"])
    assert checks == {
        "DocumentRegistrationRequest hash and invocation input binding verified",
        "staged source bytes resolve through a PASS ArtifactReceipt without network or source-tree fallback",
        "source blob and immutable DocumentRegistration hashes verify",
        "license, access policy, confidentiality, and supersession lineage retained exactly",
        "ActionIntent and resolving EffectReceipt exist",
        "registration ArtifactReceipt and Noetic Ledger event exist",
        "current fencing token and expected revision CAS succeed",
        "retry identity and crash reconciliation hold",
    }


def test_success_envelope_references_business_artifact_and_resolving_evidence() -> None:
    harness = RegistrationHarness()
    result = harness.run()
    committed = harness.committed_by_key[harness.request["idempotency_key"]]

    assert result["status"] == "success"
    assert result["output_artifact_ids"][0] == committed.registration["registration_id"]
    assert result["output_artifact_ids"][1] == committed.source_publication.artifact_id
    assert result["effect_receipt_ids"] == [
        committed.source_publication.effect.receipt_id
    ]
    assert committed.registration["registration_id"] not in result["metrics"].values()
    assert result["terminal_reason"] == "DOCUMENT_REGISTERED"


def test_register_document_has_no_default_authority_ports() -> None:
    signature = inspect.signature(register_document)
    assert signature.parameters["ports"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        register_document({})  # type: ignore[call-arg]


def test_runtime_contains_no_network_cwd_or_repository_source_fallback() -> None:
    source = inspect.getsource(inspect.getmodule(register_document)).lower()
    forbidden = (
        "requests.",
        "urllib.request",
        "httpx.",
        "socket.",
        "getcwd(",
        "path.cwd(",
        "repo_root",
        "schemas/",
        "openapi/",
    )
    assert not [token for token in forbidden if token in source]

