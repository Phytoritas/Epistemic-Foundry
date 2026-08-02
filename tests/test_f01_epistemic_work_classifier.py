from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_DIR = ROOT / "packages/foundry-kernel/src/forge/classifier"
SCHEMA_PATH = ROOT / "schemas/epistemic-work-classification.schema.json"
EXAMPLE_PATH = ROOT / "examples/sample_epistemic-work-classification.json"
HASH_VECTOR_PATH = ROOT / "tests/golden/forge/f01_classifier_hash_vectors.json"

SIGNALS = [
    "TRANSFORM",
    "LOOKUP",
    "SYNTHESIS",
    "MECHANISM",
    "CAUSAL",
    "VALIDATION",
    "HIGH_STAKES",
    "EXPENSIVE",
    "NOVELTY",
    "AMBIGUOUS",
]
RISK_SIGNALS = [
    "AMBIGUOUS",
    "NOVELTY",
    "HIGH_STAKES",
    "EXPENSIVE",
    "CAUSAL",
    "VALIDATION",
    "MECHANISM",
]


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_node_test(filename: str) -> str:
    result = subprocess.run(
        ["node", "--test", str(CLASSIFIER_DIR / filename)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "fail 0" in output, output
    assert "skipped 0" in output, output
    return output


@pytest.mark.parametrize(
    "filename",
    [
        "classifier-gold.test.mjs",
        "classifier-adversarial.test.mjs",
        "classifier-hash-vector.test.mjs",
        "classifier-override.test.mjs",
        "classification-committer.test.mjs",
    ],
)
def test_f01_node_classifier_contract_suites_pass(filename: str) -> None:
    run_node_test(filename)


def test_canonical_schema_and_example_validate_without_count_drift() -> None:
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    examples = sorted((ROOT / "examples").glob("*.json"))
    assert len(schemas) == 127
    assert len(examples) == 127

    schema = load_json(SCHEMA_PATH)
    example = load_json(EXAMPLE_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert list(validator.iter_errors(example)) == []
    assert schema["additionalProperties"] is False
    assert schema["properties"]["risk_factors"]["items"]["enum"] == RISK_SIGNALS
    signal_pattern = schema["properties"]["reasons"]["items"]["pattern"]
    for signal in SIGNALS:
        assert signal in signal_pattern


@pytest.mark.parametrize(
    ("work_class", "phases", "role_count", "human_gate"),
    [
        ("E0", [], 0, False),
        ("E1", ["F", "O", "E"], 1, False),
        ("E2", ["F", "O", "R", "G", "E"], 3, False),
        ("E3", ["F", "O", "R", "G", "E"], 6, False),
        ("E4", ["F", "O", "R", "G", "E"], 10, True),
        ("E4", ["I", "F", "O", "R", "G", "E"], 10, True),
        ("E5", ["F", "O", "R", "G", "E"], 12, True),
        ("E5", ["I", "F", "O", "R", "G", "E"], 12, True),
    ],
)
def test_schema_enforces_each_exact_class_projection(
    work_class: str,
    phases: list[str],
    role_count: int,
    human_gate: bool,
) -> None:
    schema = load_json(SCHEMA_PATH)
    candidate = load_json(EXAMPLE_PATH)
    candidate.update(
        {
            "work_class": work_class,
            "required_phases": phases,
            "default_role_count": role_count,
            "human_gate_required": human_gate,
        }
    )
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(candidate)) == []

    invalid = copy.deepcopy(candidate)
    invalid["default_role_count"] = (role_count + 1) % 13
    assert list(validator.iter_errors(invalid))


def test_hash_vectors_recompute_independently_with_canonical_json() -> None:
    fixture = load_json(HASH_VECTOR_PATH)
    assert fixture["classifier_version"] == "4.0.1-f01.1"
    assert len(fixture["vectors"]) == 4

    for row in fixture["vectors"]:
        request_digest = hashlib.sha256(row["request_text"].encode("utf-8")).hexdigest()
        assert row["request_input_hash"] == f"sha256:{request_digest}"
        preimage = {
            "schema_id": fixture["schema_id"],
            "request_id": f"REQ-{row['vector_id']}",
            "request_input_hash": row["request_input_hash"],
            "classifier_version": fixture["classifier_version"],
            "policy_bundle_hash": row["policy_bundle_hash"],
            "accepted_signals": row["accepted_signals"],
            "reasons": row["reasons"],
            "risk_factors": row["risk_factors"],
            "work_class": row["work_class"],
            "required_phases": row["required_phases"],
            "default_role_count": row["default_role_count"],
            "human_gate_required": row["human_gate_required"],
            "supersedes_classification_hash": row["supersedes_classification_hash"],
            "human_decision_hash": row["human_decision_hash"],
        }
        canonical = json.dumps(
            preimage,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        assert row["expected_classification_hash"] == f"sha256:{digest}"
        assert row["expected_classification_id"] == f"EWC-{digest}"


def test_canonical_example_is_bound_to_the_frozen_mixed_hash_vector() -> None:
    example = load_json(EXAMPLE_PATH)
    fixture = load_json(HASH_VECTOR_PATH)
    vector = next(row for row in fixture["vectors"] if row["vector_id"] == "H02_MIXED")
    assert example["classification_id"] == vector["expected_classification_id"]
    assert example["classification_hash"] == vector["expected_classification_hash"]
    assert example["request_id"] == "REQ-H02_MIXED"
    assert example["work_class"] == vector["work_class"]
    assert example["reasons"] == vector["reasons"]
    assert example["risk_factors"] == vector["risk_factors"]
    assert example["required_phases"] == vector["required_phases"]
    assert example["classified_at"] == "2026-07-29T00:00:00.000Z"
