from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows/forge_research_cycle.workflow.yaml"
PROMPT_PATH = ROOT / "prompts/plugin/classify_epistemic_work.md"
MANIFEST_PATH = ROOT / "manifests/development_manifest.yaml"
ACCEPTANCE_PATH = ROOT / "manifests/acceptance_matrix.yaml"

EXPECTED_F01_WRITE_SCOPE = [
    "packages/foundry-kernel/src/forge/classifier/**",
    "docs/forge_protocol.md",
    "schemas/epistemic-work-classification.schema.json",
    "examples/sample_epistemic-work-classification.json",
    "workflows/forge_research_cycle.workflow.yaml",
    "prompts/plugin/classify_epistemic_work.md",
    "manifests/acceptance_matrix.yaml",
    "tests/golden/forge/f01_classifier_gold_cases.json",
    "tests/golden/forge/f01_classifier_adversarial_cases.json",
    "tests/golden/forge/f01_classifier_hash_vectors.json",
    "tests/golden/forge/f01_classifier_override_cases.json",
    "tests/test_f01_epistemic_work_classifier.py",
    "tests/test_f01_underprocessing_guard.py",
    "tests/test_f01_workflow_contract.py",
    "artifacts/work_packages/F01/**",
]


def load_yaml(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_classifier_node_is_deterministic_and_directly_binds_the_business_artifact() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    assert workflow["output_schema_ref"] == "schemas/result-envelope.schema.json"
    node = next(row for row in workflow["nodes"] if row["node_id"] == "classify_epistemic_work")
    assert node == {
        "node_id": "classify_epistemic_work",
        "purpose": "Deterministically classify the request E0-E5 from sealed typed signals and commit the canonical classification artifact",
        "executor_type": "policy",
        "executor_ref": "epistemic_foundry.forge.classifier:classify_epistemic_work",
        "input_schema_ref": "schemas/node-invocation.schema.json",
        "output_schema_ref": "schemas/epistemic-work-classification.schema.json",
        "depends_on": [],
        "read_scope": [
            "request",
            "policy/**",
            "artifacts/work_classification/proposals/**",
        ],
        "write_scope": ["artifacts/work_classification/**"],
        "capabilities": ["artifact_read", "artifact_write"],
        "model_tier": "deterministic",
        "timeout_seconds": 300,
        "max_attempts": 2,
        "failure_policy": "fail_run",
        "acceptance_checks": [
            "closed signal vocabulary",
            "deterministic maximum-floor rule",
            "monotonic underprocessing guard",
            "class-specific exact projection",
            "direct EpistemicWorkClassification output",
            "ArtifactReceipt exists",
            "replay identity holds",
        ],
        "resource_dependencies": [],
        "determinism_class": "deterministic",
        "idempotency_key_fields": [
            "request_id",
            "input_hash",
            "classifier_version",
            "policy_bundle_hash",
        ],
        "loop_contract_ref": None,
        "expected_effects": [],
        "required_policy_checks": ["policy_bundle_valid", "capability_scope_valid"],
    }


def test_signal_prompt_is_advisory_only_and_denies_final_classification_authority() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())
    assert "optional, non-authoritative `SignalProposal` helper" in normalized
    assert "Foundry Kernel deterministic classifier" in normalized
    assert "Do not output or decide `work_class`" in normalized
    for field in (
        "required_phases",
        "default_role_count",
        "human_gate_required",
        "classification_id",
        "classified_at",
        "classification_hash",
    ):
        assert field in prompt
    assert "zero-based UTF-8 byte offset" in prompt
    assert "Return a JSON array of proposal objects" in prompt


def test_f01_manifest_scope_and_checks_are_exactly_the_authorized_correction() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    package = next(row for row in manifest["work_packages"] if row["id"] == "F01")
    assert package["depends_on"] == ["C04", "E04"]
    assert package["write_scope"] == EXPECTED_F01_WRITE_SCOPE
    assert package["independent_review"] == "required"
    assert package["required_checks"] == [
        "classifier_gold_test",
        "underprocessing_guard",
        "classifier_adversarial_test",
        "classifier_hash_vector_test",
        "classifier_retry_replay_test",
        "classifier_immutable_override_test",
        "classifier_workflow_contract_test",
        "canonical_schema_example_validation",
        "canonical_projection_freshness",
        "full_repository_regression",
        "independent_implementation_review",
    ]


def test_acceptance_matrix_uses_exact_zero_tolerance_f01_thresholds() -> None:
    matrix = load_yaml(ACCEPTANCE_PATH)
    gate = matrix["work_package_gates"]["F01"]
    assert gate == {
        "classifier_version": "4.0.1-f01.1",
        "canonical_signal_count": "10",
        "fixed_gold_case_count": "14",
        "fixed_gold_exact_pass_count": "14",
        "work_class_exact_match_accuracy": "1.000",
        "required_phases_exact_match_accuracy": "1.000",
        "default_role_count_exact_match_accuracy": "1.000",
        "human_gate_exact_match_accuracy": "1.000",
        "accepted_signal_normalization_accuracy": "1.000",
        "interview_routing_exact_match_accuracy": "1.000",
        "hash_vector_exact_match_accuracy": "1.000",
        "classification_id_exact_match_accuracy": "1.000",
        "adversarial_case_count": "16",
        "adversarial_exact_pass_count": "16",
        "nonempty_signal_subset_count": "1023",
        "underclassification_count": "0",
        "monotonicity_violation_count": "0",
        "protection_regression_count": "0",
        "unknown_signal_acceptance_count": "0",
        "replay_divergence_count": "0",
        "hash_vector_mismatch_count": "0",
        "immutable_history_mutation_count": "0",
        "workflow_output_binding_error_count": "0",
        "skipped_or_xfailed_guard_cases": "0",
        "live_llm_or_external_network_dependency_count": "0",
        "repository_regression_new_failure_count": "0",
        "repository_regression_new_skip_or_xfail_count": "0",
    }


def test_active_f01_contract_uses_only_canonical_capability_vocabulary() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    node = next(row for row in workflow["nodes"] if row["node_id"] == "classify_epistemic_work")
    serialized = json.dumps(node, sort_keys=True)
    assert "artifact.read" not in serialized
    assert "artifact.write" not in serialized
    assert "artifact:read" not in serialized
    assert "artifact:write" not in serialized
    assert node["capabilities"] == ["artifact_read", "artifact_write"]
