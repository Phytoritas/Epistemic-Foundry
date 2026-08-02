from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from conftest import (
    GATE_ORDER,
    PROMOTION_LEVELS,
    RESOLVED_REF_FIELDS,
    RESOLVED_REF_KEYS,
    ROOT,
    canonical_hash,
    load_json,
    schema_errors,
)


ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}

DOCUMENT_REGISTRATION_REQUEST_HASH_FIELDS = [
    "workspace_id",
    "corpus_id",
    "staged_source_artifact_id",
    "declared_filename",
    "declared_media_type",
    "source_origin",
    "declared_license_status",
    "access_policy_ref",
    "confidentiality",
    "external_identifier_hints",
    "supersedes_registration_id",
    "idempotency_key",
]

DOCUMENT_REGISTRATION_HASH_FIELDS = [
    "schema_id",
    "schema_version",
    "workspace_id",
    "corpus_id",
    "source_blob_artifact_id",
    "source_content_hash",
    "byte_size",
    "detected_media_type",
    "original_filename",
    "source_origin",
    "license_status",
    "access_policy_ref",
    "confidentiality",
    "external_identifier_hints",
    "supersedes_registration_id",
    "initial_state",
    "submitted_by_principal_id",
    "request_hash",
    "idempotency_key",
]

RETRIEVAL_CANDIDATE_IDENTITY_FIELDS = [
    "plan_hash",
    "lane",
    "query_hash",
    "canonical_source_key",
    "source_version",
    "source_snapshot_hash",
]

RETRIEVAL_CHANNELS = [
    "LEXICAL",
    "SEMANTIC",
    "CITATION_GRAPH",
    "RELATION_GRAPH",
    "EXTERNAL_INDEX",
]


def _example_path(schema_name: str) -> Path:
    candidates = [
        ALIASES.get(schema_name),
        f"sample_{schema_name}.json",
        f"sample_{schema_name.replace('-', '_')}.json",
    ]
    return next(
        ROOT / "examples" / name
        for name in candidates
        if name is not None and (ROOT / "examples" / name).is_file()
    )


def test_all_127_schemas_meta_validate_and_have_unique_ids(schema_registry) -> None:
    schemas, _ = schema_registry
    assert len(schemas) == 127
    identifiers = []
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        identifiers.append(schema["$id"])
    assert len(identifiers) == len(set(identifiers)) == 127


def test_all_127_examples_validate_and_map_one_to_one(schema_registry) -> None:
    schemas, registry = schema_registry
    examples = sorted((ROOT / "examples").glob("*.json"))
    assert len(examples) == 127
    mapped: set[Path] = set()
    failures: list[str] = []
    for name, schema in sorted(schemas.items()):
        path = _example_path(name)
        mapped.add(path)
        instance = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(
            schema,
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        for error in validator.iter_errors(instance):
            location = "/".join(map(str, error.path)) or "<root>"
            failures.append(f"{path.name}:{location}: {error.message}")
    assert len(mapped) == 127
    assert mapped == set(examples)
    assert not failures, failures[:20]


def _hash_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _retrieval_candidate_errors(
    schema: dict[str, object],
    instance: dict[str, object],
    registry: object,
) -> list[str]:
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(instance), key=lambda item: list(item.path)
        )
    ]


def test_retrieval_candidate_identity_hash_and_closed_vocabularies() -> None:
    schema = load_json("schemas/retrieval-candidate.schema.json")
    fixture = load_json("examples/sample_retrieval-candidate.json")
    identity_fields = schema["x-canonical-identity"]["preimage_fields"]
    content_fields = schema["x-canonical-hash"]["preimage_fields"]
    assert identity_fields == RETRIEVAL_CANDIDATE_IDENTITY_FIELDS
    assert set(content_fields) == set(schema["required"]) - {
        "candidate_id",
        "candidate_hash",
    }
    identity_hash = _hash_payload({field: fixture[field] for field in identity_fields})
    assert fixture["candidate_id"] == "RC-" + identity_hash.removeprefix("sha256:")
    assert fixture["candidate_hash"] == _hash_payload(
        {field: fixture[field] for field in content_fields}
    )
    assert schema["$defs"]["query_family"]["enum"] == [
        "FORWARD",
        "REVERSE",
        "NULL",
        "BOUNDARY",
        "METHOD",
        "NOVELTY",
    ]
    assert schema["$defs"]["retrieval_channel"]["enum"] == RETRIEVAL_CHANNELS
    assert schema["properties"]["relation_direction"]["enum"] == [
        "SAME_DIRECTION",
        "REVERSE_DIRECTION",
        "INVERSE_PREDICATE",
        "BIDIRECTIONAL",
        "NO_DIRECTION",
        "UNRESOLVED",
    ]


def test_retrieval_candidate_rejects_missing_unknown_and_tampered_content(
    schema_registry,
) -> None:
    schema = load_json("schemas/retrieval-candidate.schema.json")
    fixture = load_json("examples/sample_retrieval-candidate.json")
    _, registry = schema_registry
    for field in schema["required"]:
        candidate = copy.deepcopy(fixture)
        candidate.pop(field)
        assert _retrieval_candidate_errors(schema, candidate, registry), field

    for field, hostile in (
        ("query_family", "MAYBE"),
        ("relation_direction", "PROBABLY_FORWARD"),
    ):
        candidate = copy.deepcopy(fixture)
        candidate[field] = hostile
        assert _retrieval_candidate_errors(schema, candidate, registry), field

    extra = copy.deepcopy(fixture)
    extra["scientific_support_score"] = 1.0
    assert _retrieval_candidate_errors(schema, extra, registry)

    content_fields = schema["x-canonical-hash"]["preimage_fields"]
    tampered = copy.deepcopy(fixture)
    tampered["raw_rank"] = fixture["raw_rank"] + 1
    assert _hash_payload({field: tampered[field] for field in content_fields}) != fixture[
        "candidate_hash"
    ]


@pytest.mark.parametrize(
    ("lane", "accepted_family", "rejected_family"),
    [
        ("lexical", "FORWARD", "REVERSE"),
        ("counterevidence", "REVERSE", "NULL"),
        ("null", "NULL", "FORWARD"),
        ("boundary", "BOUNDARY", "FORWARD"),
        ("method", "METHOD", "FORWARD"),
        ("external_novelty", "NOVELTY", "FORWARD"),
    ],
)
def test_retrieval_candidate_lane_family_binding_is_fail_closed(
    lane: str, accepted_family: str, rejected_family: str, schema_registry
) -> None:
    schema = load_json("schemas/retrieval-candidate.schema.json")
    fixture = load_json("examples/sample_retrieval-candidate.json")
    _, registry = schema_registry
    fixture["lane"] = lane
    fixture["query_family"] = accepted_family
    assert not _retrieval_candidate_errors(schema, fixture, registry)
    fixture["query_family"] = rejected_family
    assert _retrieval_candidate_errors(schema, fixture, registry)


def test_retrieval_candidate_channel_nullability_rrf_and_metadata_boundary(
    schema_registry,
) -> None:
    schema = load_json("schemas/retrieval-candidate.schema.json")
    fixture = load_json("examples/sample_retrieval-candidate.json")
    _, registry = schema_registry
    observed = set(fixture["retrieval_channels"])
    assert observed == {
        channel for channel, rank in fixture["channel_ranks"].items() if rank is not None
    }
    assert observed == {
        channel for channel, score in fixture["raw_scores"].items() if score is not None
    }
    expected_rrf = sum(1 / (60 + fixture["channel_ranks"][channel]) for channel in observed)
    assert fixture["fusion_method"] == "RRF_K60"
    assert fixture["fusion_score"] == pytest.approx(expected_rrf, rel=0, abs=1e-15)
    assert fixture["multi_channel_verified"] is True
    assert fixture["source_span_id"] is None
    assert any(
        "cannot directly become EvidenceNode" in invariant
        for invariant in schema["x-semantic-invariants"]
    )

    single = copy.deepcopy(fixture)
    single["retrieval_channels"] = ["SEMANTIC"]
    single["raw_scores"] = {channel: None for channel in RETRIEVAL_CHANNELS}
    single["raw_scores"]["SEMANTIC"] = 0.9
    single["channel_ranks"] = {channel: None for channel in RETRIEVAL_CHANNELS}
    single["channel_ranks"]["SEMANTIC"] = 1
    single["fusion_method"] = "SINGLE_CHANNEL"
    single["fusion_score"] = None
    single["multi_channel_verified"] = False
    assert not _retrieval_candidate_errors(schema, single, registry)

    falsely_verified = copy.deepcopy(single)
    falsely_verified["multi_channel_verified"] = True
    assert _retrieval_candidate_errors(schema, falsely_verified, registry)


def _document_manifest_lineage_errors(
    manifest: dict[str, object], registration: dict[str, object]
) -> list[str]:
    """Evaluate cross-artifact equalities that Draft 2020-12 cannot express."""
    bindings = {
        "derived_from_registration_id": "registration_id",
        "registration_id": "registration_id",
        "registration_hash": "registration_hash",
        "source_blob_artifact_id": "source_blob_artifact_id",
        "source_artifact_receipt_id": "source_artifact_receipt_id",
        "registration_artifact_receipt_id": "registration_artifact_receipt_id",
    }
    errors = []
    for manifest_field, registration_field in bindings.items():
        if manifest.get(manifest_field) != registration.get(registration_field):
            errors.append(f"{manifest_field}!={registration_field}")
    return errors


def test_document_registration_request_hash_id_and_staging_contract() -> None:
    schema = load_json("schemas/document-registration-request.schema.json")
    fixture = load_json("examples/sample_document-registration-request.json")
    preimage_fields = schema["x-canonical-hash"]["preimage_fields"]
    assert preimage_fields == DOCUMENT_REGISTRATION_REQUEST_HASH_FIELDS
    expected_hash = _hash_payload({field: fixture[field] for field in preimage_fields})
    assert fixture["request_hash"] == expected_hash
    assert fixture["request_id"] == "DREQ-" + expected_hash.removeprefix("sha256:")
    assert fixture["staged_source_artifact_id"]
    assert all(hint["verified"] is False for hint in fixture["external_identifier_hints"])

    missing_stage = copy.deepcopy(fixture)
    missing_stage.pop("staged_source_artifact_id")
    assert schema_errors(schema, missing_stage)

    for forbidden_name in ("C:\\private\\paper.pdf", "../paper.pdf", "folder/paper.pdf"):
        candidate = copy.deepcopy(fixture)
        candidate["declared_filename"] = forbidden_name
        assert schema_errors(schema, candidate), forbidden_name

    file_uri = copy.deepcopy(fixture)
    file_uri["source_origin"]["original_uri"] = "file:///private/paper.pdf"
    assert schema_errors(schema, file_uri)


def test_document_registration_hash_id_and_immutable_initial_state() -> None:
    schema = load_json("schemas/document-registration.schema.json")
    fixture = load_json("examples/sample_document-registration.json")
    preimage_fields = schema["x-canonical-hash"]["preimage_fields"]
    assert preimage_fields == DOCUMENT_REGISTRATION_HASH_FIELDS
    preimage = {
        field: schema["$id"] if field == "schema_id" else fixture[field]
        for field in preimage_fields
    }
    expected_hash = _hash_payload(preimage)
    assert fixture["registration_hash"] == expected_hash
    assert fixture["registration_id"] == "DREG-" + expected_hash.removeprefix("sha256:")
    assert fixture["initial_state"] == "REGISTERED_UNSCREENED"
    assert fixture["request_id"] == "DREQ-" + fixture["request_hash"].removeprefix("sha256:")

    mutated = copy.deepcopy(fixture)
    mutated["initial_state"] = "RELEASED"
    assert schema_errors(schema, mutated)


def test_document_manifest_is_lineage_bound_to_registration() -> None:
    schema = load_json("schemas/document-manifest.schema.json")
    fixture = load_json("examples/sample_document-manifest.json")
    registration = load_json("examples/sample_document-registration.json")
    assert not _document_manifest_lineage_errors(fixture, registration)
    assert "derived_from_registration_id == registration_id" in schema["x-semantic-invariants"]

    mutations = {
        "derived_from_registration_id": "DREG-" + "0" * 64,
        "registration_hash": "sha256:" + "0" * 64,
        "source_blob_artifact_id": "ART-SOURCE-BLOB-WRONG",
        "source_artifact_receipt_id": "AR-SOURCE-BLOB-WRONG",
        "registration_artifact_receipt_id": "AR-DOCUMENT-REGISTRATION-WRONG",
    }
    for field, hostile_value in mutations.items():
        candidate = copy.deepcopy(fixture)
        candidate[field] = hostile_value
        assert _document_manifest_lineage_errors(candidate, registration), field


def test_evaluator_bundle_is_immutable_and_candidate_inaccessible() -> None:
    schema = load_json("schemas/evaluator-bundle.schema.json")
    fixture = load_json("examples/sample_evaluator-bundle.json")
    assert fixture["immutable"] is True
    assert fixture["candidate_access"] is False
    assert fixture["mutation_allowed_for_current_run"] is False
    for field, hostile in (
        ("immutable", False),
        ("candidate_access", True),
        ("mutation_allowed_for_current_run", True),
    ):
        candidate = copy.deepcopy(fixture)
        candidate[field] = hostile
        assert schema_errors(schema, candidate), field

    # A06-F001 reproduced these legacy wire names. They must not survive as
    # permissive aliases beside the canonical fail-closed fields.
    for legacy_field in ("readable_by_candidates", "mutable_during_run"):
        candidate = copy.deepcopy(fixture)
        candidate[legacy_field] = True
        assert schema_errors(schema, candidate), legacy_field


def test_holdout_manifest_rejects_candidate_model_prompt_and_backend_access() -> None:
    schema = load_json("schemas/holdout-manifest.schema.json")
    fixture = load_json("examples/sample_holdout-manifest.json")
    for field in ("candidate_access", "mutation_model_access", "prompt_access", "backend_access"):
        assert fixture[field] is False
        candidate = copy.deepcopy(fixture)
        candidate[field] = True
        assert schema_errors(schema, candidate), field
    for legacy_access in ("METADATA_ONLY", "AGGREGATE_ONLY"):
        candidate = copy.deepcopy(fixture)
        candidate["candidate_access"] = legacy_access
        assert schema_errors(schema, candidate), legacy_access
    assert fixture["unblinding_approval_required"] is True
    candidate = copy.deepcopy(fixture)
    candidate["unblinding_approval_required"] = False
    assert schema_errors(schema, candidate)


def test_gate_decision_binds_version_inputs_policy_evidence_and_blockers() -> None:
    schema = load_json("schemas/gate-decision.schema.json")
    fixture = load_json("examples/sample_gate_decision.json")
    required = {
        "gate_id",
        "gate_version",
        "non_waivable",
        "status",
        "input_artifact_ids",
        "input_hash",
        "evidence_ids",
        "policy_bundle_hash",
        "decision",
        "blocker_ids",
        "created_at",
        "decision_hash",
    }
    assert required <= set(schema["required"])
    for field in required:
        candidate = copy.deepcopy(fixture)
        candidate.pop(field)
        assert schema_errors(schema, candidate), field


def test_legacy_promotion_values_are_absent_from_canonical_json() -> None:
    forbidden = {'"PILOT"', '"HYPOTHESIS_PASSPORT_ONLY"'}
    hits: list[str] = []
    for directory in (ROOT / "schemas", ROOT / "examples"):
        for path in directory.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT).as_posix()}: {token}")
    assert not hits


def test_evolution_fixture_has_complete_resolved_reference_inventory() -> None:
    fixture = load_json("examples/sample_evolution-run-spec.json")
    refs = fixture["resolved_refs"]
    assert set(refs) == RESOLVED_REF_KEYS
    for key, reference in refs.items():
        assert RESOLVED_REF_FIELDS <= set(reference), key
    assert fixture["external_backend_enabled"] is False


def test_evolution_fixture_hash_recomputes_after_schema_declared_sorting() -> None:
    fixture = load_json("examples/sample_evolution-run-spec.json")
    assert fixture["population_types"] == sorted(fixture["population_types"])
    assert fixture["seed_genome_ids"] == sorted(fixture["seed_genome_ids"])
    assert fixture["spec_hash"] == canonical_hash(fixture, "spec_hash")


@pytest.mark.parametrize(
    "floating_value",
    ["main", "MAIN", "latest", "release/latest", ">=4.0", "^4.0", "4.*"],
)
def test_floating_reference_versions_are_rejected(floating_value: str) -> None:
    schema = load_json("schemas/evolution-run-spec.schema.json")
    fixture = load_json("examples/sample_evolution-run-spec.json")
    fixture["resolved_refs"]["workflow"]["exact_version_or_revision"] = floating_value
    assert schema_errors(schema, fixture)


def test_cwd_and_repo_relative_locators_are_rejected() -> None:
    schema = load_json("schemas/evolution-run-spec.schema.json")
    fixture = load_json("examples/sample_evolution-run-spec.json")
    for locator in ("./schemas/run-spec.schema.json", "../schemas/run-spec.schema.json", "C:\\repo\\schema.json"):
        candidate = copy.deepcopy(fixture)
        candidate["resolved_refs"]["base_run_spec"]["resolved_artifact_locator"] = locator
        assert schema_errors(schema, candidate), locator


def test_external_backend_requires_an_immutable_source_pin() -> None:
    schema = load_json("schemas/evolution-run-spec.schema.json")
    fixture = load_json("examples/sample_evolution-run-spec.json")
    fixture["external_backend_enabled"] = True
    assert schema_errors(schema, fixture)

    backend = copy.deepcopy(fixture["resolved_refs"]["workflow"])
    backend["source_pin"] = {
        "immutable_container_digest": "sha256:" + "b" * 64,
    }
    fixture["resolved_refs"]["external_backend_manifest"] = backend
    assert not schema_errors(schema, fixture)


def test_provider_without_snapshot_discloses_reproducibility_ceiling() -> None:
    schema = load_json("schemas/evolution-run-spec.schema.json")
    fixture = load_json("examples/sample_evolution-run-spec.json")
    model = fixture["resolved_refs"]["provider_adapter_manifest"]["remote_models"][0]
    model["exposed_snapshot_or_revision"] = None
    model["reproducibility_class"] = "provider_snapshot_pinned"
    assert schema_errors(schema, fixture)
    model["reproducibility_class"] = "provider_versioned_not_byte_pinned"
    assert not schema_errors(schema, fixture)


def test_sealed_evaluator_mutation_invalidates_spec_hash() -> None:
    fixture = load_json("examples/sample_evolution-run-spec.json")
    sealed_hash = fixture["spec_hash"]
    fixture["resolved_refs"]["evaluator_bundle"]["content_hash"] = "sha256:" + "f" * 64
    assert canonical_hash(fixture, "spec_hash") != sealed_hash


def test_promotion_fixture_is_conditional_at_partial_replication_ceiling() -> None:
    fixture = load_json("examples/sample_promotion-decision.json")
    assert fixture["requested_level"] == "REPLICATED"
    assert fixture["granted_level"] == "EMPIRICALLY_TESTED"
    assert fixture["promotion_ceiling"] == "EMPIRICALLY_TESTED"
    assert fixture["replication_status"] == "PARTIAL"
    assert fixture["decision"] == "CONDITIONAL"
    assert fixture["gate_decision_ids"] == GATE_ORDER
    assert fixture["unresolved_limitations"]
    assert fixture["decision_hash"] == canonical_hash(fixture, "decision_hash")


def test_promote_requires_and_accepts_an_exact_requested_level_grant() -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.update(
        {
            "requested_level": "EMPIRICALLY_TESTED",
            "granted_level": "EMPIRICALLY_TESTED",
            "promotion_ceiling": "EMPIRICALLY_TESTED",
            "replication_status": "REPLICATED",
            "decision": "PROMOTE",
            "unresolved_limitations": [],
        }
    )
    assert not schema_errors(schema, fixture)

    fixture["requested_level"] = "REPLICATED"
    assert schema_errors(schema, fixture)


@pytest.mark.parametrize("granted_level", [None, "EMPIRICALLY_TESTED"])
def test_conditional_rejects_null_or_requested_level_grants(granted_level: object) -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.update(
        {
            "requested_level": "EMPIRICALLY_TESTED",
            "granted_level": granted_level,
            "promotion_ceiling": "EMPIRICALLY_TESTED",
            "replication_status": "REPLICATED",
            "decision": "CONDITIONAL",
        }
    )
    assert schema_errors(schema, fixture)


@pytest.mark.parametrize("decision", ["REJECT", "UNDERDETERMINED", "BLOCKED"])
def test_non_granting_decisions_require_null_and_accept_no_new_level(decision: str) -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.update(
        {
            "granted_level": None,
            "replication_status": "REPLICATED",
            "decision": decision,
        }
    )
    assert not schema_errors(schema, fixture)

    fixture["granted_level"] = "EMPIRICALLY_TESTED"
    assert schema_errors(schema, fixture)


def test_granted_level_remains_required_and_null_is_decision_scoped() -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.pop("granted_level")
    assert any("granted_level" in error for error in schema_errors(schema, fixture))

    granted = schema["properties"]["granted_level"]
    assert granted["oneOf"] == [
        {"$ref": "#/$defs/promotion_level"},
        {"type": "null"},
    ]
    non_grant_rule = next(
        rule
        for rule in schema["allOf"]
        if rule.get("if", {}).get("properties", {}).get("decision", {}).get("enum")
        == ["REJECT", "UNDERDETERMINED", "BLOCKED"]
    )
    assert non_grant_rule["then"]["properties"]["granted_level"] == {"type": "null"}


def test_promotion_gate_decisions_must_follow_the_canonical_order() -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture["gate_decision_ids"][0], fixture["gate_decision_ids"][1] = (
        fixture["gate_decision_ids"][1],
        fixture["gate_decision_ids"][0],
    )
    assert schema_errors(schema, fixture)


@pytest.mark.parametrize("hard_gate_status", ["FAIL", "PARTIAL"])
def test_nonpassing_hard_gates_cannot_promote(hard_gate_status: str) -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.update(
        {
            "requested_level": "EMPIRICALLY_TESTED",
            "granted_level": "EMPIRICALLY_TESTED",
            "promotion_ceiling": "EMPIRICALLY_TESTED",
            "hard_gate_status": hard_gate_status,
            "replication_status": "REPLICATED",
            "decision": "PROMOTE",
            "unresolved_limitations": [],
        }
    )
    assert schema_errors(schema, fixture)


def test_promotion_level_vocabulary_is_closed_and_shared_with_adjudication() -> None:
    promotion = load_json("schemas/promotion-decision.schema.json")
    adjudication = load_json("schemas/adjudication.schema.json")
    assert promotion["$defs"]["promotion_level"]["enum"] == PROMOTION_LEVELS
    recommendation = adjudication["properties"]["promotion_recommendation"]["enum"]
    assert recommendation == ["BLOCK", *PROMOTION_LEVELS]


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        ({"requested_level": "CANDIDATE", "granted_level": "REPLICATED"}, "granted_level"),
        ({"promotion_ceiling": "CANDIDATE", "granted_level": "EMPIRICALLY_TESTED"}, "granted_level"),
        ({"replication_status": "PARTIAL", "promotion_ceiling": "REPLICATED"}, "promotion_ceiling"),
        ({"replication_status": "PARTIAL", "decision": "PROMOTE"}, "decision"),
        ({"replication_status": "PARTIAL", "unresolved_limitations": []}, "unresolved_limitations"),
        ({"granted_level": "REPLICATED", "replication_status": "PARTIAL"}, "replication_status"),
    ],
)
def test_promotion_order_and_replication_ceiling_are_schema_enforced(
    mutation: dict[str, object], expected_fragment: str
) -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.update(mutation)
    errors = schema_errors(schema, fixture)
    assert errors
    assert any(expected_fragment in error for error in errors)


@pytest.mark.parametrize(
    "missing_field",
    [
        "promotion_ceiling",
        "phase_e_artifact_set_id",
        "promotion_pack_artifact_ids",
        "gate_decision_ids",
        "artifact_receipt_ids",
        "effect_receipt_id",
        "request_action_intent_id",
        "commit_action_intent_id",
        "policy_bundle_hash",
        "idempotency_key",
    ],
)
def test_promotion_rejects_missing_ceiling_pack_gate_or_receipt_link(missing_field: str) -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    fixture = load_json("examples/sample_promotion-decision.json")
    fixture.pop(missing_field)
    assert any(missing_field in error for error in schema_errors(schema, fixture))


def test_scalar_only_promotion_is_not_schema_valid() -> None:
    schema = load_json("schemas/promotion-decision.schema.json")
    scalar_only = {
        "decision_id": "PD-UNSAFE",
        "candidate_id": "HG-UNSAFE",
        "requested_level": "REPLICATED",
        "granted_level": "REPLICATED",
        "combined_score": 1.0,
    }
    errors = schema_errors(schema, scalar_only)
    assert errors
    assert any("combined_score" in error for error in errors)
    assert any("promotion_pack" in error or "gate_decision" in error for error in errors)


def test_phase_e_annotation_declares_receipt_bound_promotion_pack() -> None:
    schema = load_json("schemas/phase-artifact-set.schema.json")
    annotation = schema["x-phase-e-promotion-pack"]
    required = set(annotation["core_required_kinds"])
    assert {
        "EvolutionRunSpec",
        "ResolvedReferenceInventory",
        "CandidateGenome",
        "CandidateLineage",
        "EvidencePack",
        "SearchCompletenessCertificate",
        "FitnessVector",
        "GateDecisionsG00ThroughG10",
        "SequentialTestingLedger",
        "MultipleTestingAdjustment",
        "SelectiveInferenceReport",
        "LeakageAudit",
        "RedQueenResult",
        "ReplicationResultOrExplicitStatus",
        "Adjudication",
        "MinorityReports",
        "RequestPromotionActionIntent",
        "CommitPromotionActionIntent",
        "ArtifactReceipts",
        "EffectReceipt",
    } <= required
    assert annotation["gate_sequence"] == GATE_ORDER
    assert annotation["conditional_required_kinds"]["VALIDATION_SCREENED_OR_HIGHER"] == [
        "IndependentAttestation"
    ]


def test_cross_artifact_self_approval_is_a_non_waivable_rejection() -> None:
    candidate_actor_id = "ACTOR-MAKER-1"
    approval_record = {
        "authority_id": "ACTOR-MAKER-1",
        "decision": "APPROVE",
    }
    allowed = approval_record["authority_id"] != candidate_actor_id
    assert allowed is False
    charter = (ROOT / "docs/v4_a05/evolution_authority_and_promotion_charter.md").read_text(
        encoding="utf-8"
    )
    assert "self-approval" in charter
    assert "Human or policy approval cannot" in charter
    assert "into PASS" in charter


def test_non_waivable_gate_decision_cannot_be_waived() -> None:
    schema = load_json("schemas/gate-decision.schema.json")
    fixture = load_json("examples/sample_gate_decision.json")
    fixture.update(
        {
            "status": "WAIVE",
            "non_waivable": True,
            "waiver_authority": "ACTOR-FIXTURE-0001",
            "waiver_reason": "Attempted unsafe override.",
        }
    )
    assert schema_errors(schema, fixture)


def test_waivable_gate_requires_explicit_waiver_evidence() -> None:
    schema = load_json("schemas/gate-decision.schema.json")
    fixture = load_json("examples/sample_gate_decision.json")
    fixture.update(
        {
            "status": "WAIVE",
            "non_waivable": False,
            "waiver_authority": None,
            "waiver_reason": None,
        }
    )
    assert schema_errors(schema, fixture)


def test_a05_negative_registry_covers_all_required_c01_rejections() -> None:
    registry = (ROOT / "docs/v4_a05/adversarial_contract_tests.md").read_text(encoding="utf-8")
    required = {
        "A05-NEG-006": "evaluator",
        "A05-NEG-007": "holdout:read",
        "A05-NEG-008": "scalar",
        "A05-NEG-013": "replication ceiling",
        "A05-NEG-016": "attestor",
        "A05-NEG-017": "ApprovalRecord",
        "A05-NEG-020": "EffectReceipt",
    }
    for test_id, token in required.items():
        row = next(line for line in registry.splitlines() if f"`{test_id}`" in line)
        assert token in row
