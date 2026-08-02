from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = ROOT / "openapi/epistemic-foundry-v1.openapi.yaml"

PROMOTION_LEVELS = [
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
]

GATE_ORDER = [
    "G00_PIN_RESOLUTION",
    "G01_POLICY_AUTHORITY",
    "G02_EVALUATOR_HOLDOUT_FIREWALL",
    "G03_SCHEMA_LINEAGE_COUNT",
    "G04_SOURCE_PROVENANCE",
    "G05_SEARCH_COVERAGE",
    "G06_METHOD_SCOPE_DEPENDENCY",
    "G07_VALIDATION_LEAKAGE",
    "G08_ADAPTIVE_STATISTICS",
    "G09_RED_QUEEN",
    "G10_REPLICATION_CEILING",
    "G11_PARLIAMENT",
    "G12_INDEPENDENT_ATTESTATION",
    "G13_HUMAN_POLICY_APPROVAL",
    "G14_ATOMIC_PROMOTION_COMMIT",
]

RESOLVED_REF_KEYS = {
    "base_run_spec",
    "schema_bundle",
    "workflow",
    "policy_bundle",
    "corpus_evidence_snapshot",
    "ontology",
    "domain_pack",
    "evaluator_bundle",
    "holdout_manifest",
    "operator_registry",
    "prompt_bundle",
    "model_routing_policy",
    "provider_adapter_manifest",
    "statistical_plan",
    "selection_policy",
    "stop_policy",
    "replication_policy",
    "archive_niche_policy",
    "budget_envelope",
    "execution_environment_toolchain_manifest",
}

RESOLVED_REF_FIELDS = {
    "logical_id",
    "exact_version_or_revision",
    "content_hash",
    "resolver_id",
    "resolver_version",
    "resolved_artifact_locator",
    "resolved_at",
    "authority_source_class",
    "reproducibility_class",
}


def load_json(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def canonical_hash(document: dict[str, Any], excluded_field: str) -> str:
    payload = copy.deepcopy(document)
    payload.pop(excluded_field, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def schema_errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def operations(document: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                yield path, method, operation


def resolve_internal_ref(document: dict[str, Any], ref: str) -> Any:
    assert ref.startswith("#/"), ref
    current: Any = document
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[token]
    return current


@pytest.fixture(scope="session")
def openapi_document() -> dict[str, Any]:
    value = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="session")
def schema_registry() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.stem.removesuffix(".schema")] = document
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return schemas, registry
