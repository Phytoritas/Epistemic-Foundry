from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from jsonschema import Draft202012Validator

from conftest import ROOT, operations, resolve_internal_ref


MUTATIONS = {
    ("/runs", "post"),
    ("/runs/{run_id}/actions/pause", "post"),
    ("/runs/{run_id}/actions/resume", "post"),
    ("/runs/{run_id}/actions/cancel", "post"),
    ("/documents", "post"),
    ("/retrieval-runs", "post"),
    ("/deliberation-runs", "post"),
    ("/evolution-runs", "post"),
    ("/candidates/{candidate_id}/promotion-requests", "post"),
    ("/validation-runs", "post"),
    ("/replication-runs", "post"),
    ("/approvals", "post"),
}

ASYNC_202 = MUTATIONS - {("/approvals", "post")}

PAGINATED = {
    ("/runs", "get"),
    ("/runs/{run_id}/events", "get"),
    ("/evolution-runs/{evolution_run_id}/candidates", "get"),
}

STATE_TRANSITIONS = {
    ("/runs/{run_id}/actions/pause", "post"),
    ("/runs/{run_id}/actions/resume", "post"),
    ("/runs/{run_id}/actions/cancel", "post"),
    ("/candidates/{candidate_id}/promotion-requests", "post"),
    ("/approvals", "post"),
}

EXPECTED_SCIENTIFIC_REFS = {
    "../schemas/plugin-health-report.schema.json",
    "../schemas/host-capability-report.schema.json",
    "../schemas/run-spec.schema.json",
    "../schemas/event-record.schema.json",
    "../schemas/document-registration-request.schema.json",
    "../schemas/document-registration.schema.json",
    "../schemas/document-manifest.schema.json",
    "../schemas/claim-card.schema.json",
    "../schemas/evidence-node.schema.json",
    "../schemas/query-plan.schema.json",
    "../schemas/evidence-pack.schema.json",
    "../schemas/coverage-snapshot.schema.json",
    "../schemas/adjudication.schema.json",
    "../schemas/evolution-run-spec.schema.json",
    "../schemas/promotion-decision.schema.json",
    "../schemas/hypothesis-passport.schema.json",
    "../schemas/validation-plan.schema.json",
    "../schemas/replication-plan.schema.json",
    "../schemas/replication-result.schema.json",
    "../schemas/approval-record.schema.json",
    "../schemas/artifact-manifest.schema.json",
    "../schemas/result-envelope.schema.json",
    "../schemas/hypothesis-genome.schema.json",
    "../schemas/candidate-lineage.schema.json",
}


def _all_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                refs.append(child)
            else:
                refs.extend(_all_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_all_refs(child))
    return refs


def _parameters(document: dict[str, Any], path: str, operation: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = [*document["paths"][path].get("parameters", []), *operation.get("parameters", [])]
    return [resolve_internal_ref(document, item["$ref"]) if "$ref" in item else item for item in parameters]


def _request_schema(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    request_body = operation["requestBody"]
    if "$ref" in request_body:
        request_body = resolve_internal_ref(document, request_body["$ref"])
    schema = request_body["content"]["application/json"]["schema"]
    if "$ref" in schema and schema["$ref"].startswith("#/"):
        schema = resolve_internal_ref(document, schema["$ref"])
    return schema


def test_openapi_version_base_path_and_operation_inventory(openapi_document) -> None:
    document = openapi_document
    assert document["openapi"] == "3.1.1"
    assert document["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["servers"] == [{"url": "/api/v1", "description": "Canonical v1 base path"}]
    operation_list = list(operations(document))
    assert len(operation_list) == 33
    operation_ids = [operation["operationId"] for _, _, operation in operation_list]
    assert len(operation_ids) == len(set(operation_ids)) == 33


def test_every_operation_has_explicit_security_and_capability(openapi_document) -> None:
    for path, method, operation in operations(openapi_document):
        assert "security" in operation, (path, method)
        assert "x-required-capabilities" in operation, (path, method)
    liveness = openapi_document["paths"]["/health/live"]["get"]
    assert liveness["security"] == []
    assert liveness["x-required-capabilities"] == []


def test_all_mutations_require_idempotency_key(openapi_document) -> None:
    observed = {
        (path, method)
        for path, method, _ in operations(openapi_document)
        if method != "get"
    }
    assert observed == MUTATIONS
    for path, method in sorted(MUTATIONS):
        operation = openapi_document["paths"][path][method]
        parameters = _parameters(openapi_document, path, operation)
        key = next(item for item in parameters if item["name"] == "Idempotency-Key")
        assert key["in"] == "header"
        assert key["required"] is True


def test_state_transitions_have_revision_preconditions(openapi_document) -> None:
    for path, method in sorted(STATE_TRANSITIONS):
        operation = openapi_document["paths"][path][method]
        schema = _request_schema(openapi_document, operation)
        required = set(schema.get("required", []))
        if path.startswith("/runs/"):
            assert "expected_revision" in required
        elif "promotion-requests" in path:
            assert "expected_candidate_revision" in required
        else:
            assert "expected_revision" in required


def test_async_operations_share_location_retry_after_and_run_handle(openapi_document) -> None:
    observed = {
        (path, method)
        for path, method, operation in operations(openapi_document)
        if "202" in operation["responses"]
    }
    assert observed == ASYNC_202
    response = resolve_internal_ref(
        openapi_document,
        openapi_document["components"]["responses"]["AsyncAccepted"]["$ref"],
    ) if "$ref" in openapi_document["components"]["responses"]["AsyncAccepted"] else openapi_document["components"]["responses"]["AsyncAccepted"]
    assert set(response["headers"]) == {"Location", "Retry-After"}
    schema_ref = response["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref == "#/components/schemas/RunHandle"
    for path, method in observed:
        assert openapi_document["paths"][path][method]["responses"]["202"]["$ref"] == (
            "#/components/responses/AsyncAccepted"
        )


def test_transport_envelopes_are_openapi_only(openapi_document) -> None:
    required = {
        "RunHandle",
        "RunView",
        "CommandRequest",
        "ApiProblem",
        "CursorPageMetadata",
        "CandidateEnvelope",
        "ApprovalCommand",
    }
    assert required <= set(openapi_document["components"]["schemas"])
    schema_titles = {
        json.loads(path.read_text(encoding="utf-8"))["title"]
        for path in (ROOT / "schemas").glob("*.schema.json")
    }
    assert not required & schema_titles
    assert len(schema_titles) == 127


def test_every_external_scientific_ref_resolves_to_canonical_schema(openapi_document) -> None:
    refs = set(_all_refs(openapi_document))
    external_refs = {ref.split("#", 1)[0] for ref in refs if not ref.startswith("#/")}
    assert external_refs == EXPECTED_SCIENTIFIC_REFS
    for ref in external_refs:
        target = (ROOT / "openapi" / unquote(ref)).resolve()
        assert target.is_relative_to((ROOT / "schemas").resolve())
        assert target.is_file(), ref
        schema = json.loads(target.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_cursor_contract_is_snapshot_bound_and_offset_free(openapi_document) -> None:
    for path, method in PAGINATED:
        operation = openapi_document["paths"][path][method]
        names = {item["name"] for item in _parameters(openapi_document, path, operation)}
        assert {"cursor", "limit", "snapshot_id"} <= names
        assert "offset" not in names
    limit = resolve_internal_ref(openapi_document, "#/components/parameters/Limit")
    assert limit["schema"] == {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}
    metadata = openapi_document["components"]["schemas"]["CursorPageMetadata"]
    assert set(metadata["required"]) == {"next_cursor", "snapshot_id", "has_more"}
    assert "total_count" not in metadata["required"]
    assert openapi_document["x-canonical-pagination-order"] == [
        "created_at DESC",
        "immutable_resource_id DESC",
    ]
    docs = (ROOT / "docs/api_contract.md").read_text(encoding="utf-8")
    assert "Malformed cursors return\n400" in docs
    assert "query or snapshot mismatch returns 409" in docs
    assert "expiry returns 410" in docs


def test_problem_json_contract_and_status_mapping(openapi_document) -> None:
    problem_response = openapi_document["components"]["responses"]["Problem"]
    assert set(problem_response["content"]) == {"application/problem+json"}
    schema = openapi_document["components"]["schemas"]["ApiProblem"]
    assert set(schema["required"]) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "request_id",
        "retryable",
        "details",
        "evidence_artifact_ids",
    }
    docs = (ROOT / "docs/api_contract.md").read_text(encoding="utf-8")
    for status in (400, 401, 403, 404, 409, 410, 412, 413, 415, 422, 429, 500, 502, 503, 504):
        assert f"| {status} |" in docs
    assert "Scientific verdicts are never translated into 4xx or 5xx" in docs


def test_candidate_and_backend_identities_cannot_receive_authority_capabilities(openapi_document) -> None:
    forbidden = set(openapi_document["x-forbidden-candidate-capabilities"])
    assert forbidden == {
        "holdout:read",
        "evaluator:write",
        "policy:write",
        "promotion:approve",
        "promotion:commit",
        "approval:issue",
        "ledger:rewrite",
    }
    assert "promotion:commit" in openapi_document["x-promotion-commit-lease"]
    promotion = openapi_document["paths"]["/candidates/{candidate_id}/promotion-requests"]["post"]
    assert promotion["x-required-capabilities"] == ["promotion:request"]
    assert not forbidden & set(promotion["x-required-capabilities"])


def test_approval_command_cannot_assert_authority_role(openapi_document) -> None:
    schema = openapi_document["components"]["schemas"]["ApprovalCommand"]
    assert "authority_role" not in schema["properties"]
    assert "authority_id" not in schema["properties"]
    assert schema["additionalProperties"] is False


def test_document_registration_uses_canonical_staged_request_and_result(openapi_document) -> None:
    operation = openapi_document["paths"]["/documents"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref == "../schemas/document-registration-request.schema.json"
    assert operation["x-async-result-artifact"]["$ref"] == (
        "../schemas/document-registration.schema.json"
    )
    assert "DocumentRegistrationRequest" not in openapi_document["components"]["schemas"]

    schema = json.loads(
        (ROOT / "schemas/document-registration-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    example = json.loads(
        (ROOT / "examples/sample_document-registration-request.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    assert not list(validator.iter_errors(example))
    assert "staged_source_artifact_id" in schema["required"]
    assert "source_uri" not in schema["properties"]
    assert "uploaded_artifact_id" not in schema["properties"]

    missing_stage = dict(example)
    missing_stage.pop("staged_source_artifact_id")
    assert list(validator.iter_errors(missing_stage))

    local_path = dict(example)
    local_path["declared_filename"] = "C:\\private\\fixture.txt"
    assert list(validator.iter_errors(local_path))


def test_embedded_transport_examples_validate(openapi_document) -> None:
    examples = [
        ("Liveness", openapi_document["paths"]["/health/live"]["get"]["responses"]["200"]["content"]["application/json"]["example"]),
        ("RunHandle", openapi_document["components"]["responses"]["AsyncAccepted"]["content"]["application/json"]["example"]),
        ("ApiProblem", openapi_document["components"]["responses"]["Problem"]["content"]["application/problem+json"]["example"]),
        ("CommandRequest", openapi_document["components"]["requestBodies"]["Command"]["content"]["application/json"]["example"]),
    ]
    for schema_name, example in examples:
        schema = openapi_document["components"]["schemas"][schema_name]
        errors = list(
            Draft202012Validator(
                schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            ).iter_errors(example)
        )
        assert not errors, (schema_name, [error.message for error in errors])


def test_json_polling_is_canonical_and_sse_is_projection(openapi_document) -> None:
    content = openapi_document["paths"]["/runs/{run_id}/events"]["get"]["responses"]["200"]["content"]
    assert set(content) == {"application/json", "text/event-stream"}
    assert content["text/event-stream"]["x-delivery-projection-of"] == "application/json"


def test_get_operations_have_no_mutating_query_parameters(openapi_document) -> None:
    forbidden = {"pause", "resume", "cancel", "promote", "approve", "action"}
    for path, method, operation in operations(openapi_document):
        if method != "get":
            continue
        names = {item["name"].lower() for item in _parameters(openapi_document, path, operation)}
        assert not names & forbidden, (path, names & forbidden)


def test_api_docs_do_not_claim_master_spec_section_18_authority() -> None:
    docs = (ROOT / "docs/api_contract.md").read_text(encoding="utf-8")
    assert "MASTER_SPEC.md" not in docs
    assert "§18" not in docs
    assert "does not\nclaim that API handlers" in docs
