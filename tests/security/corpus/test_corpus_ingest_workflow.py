from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / "workflows" / "corpus_ingest.workflow.yaml"


def workflow() -> dict[str, object]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def nodes_by_id() -> dict[str, dict[str, object]]:
    nodes = workflow()["nodes"]
    assert isinstance(nodes, list)
    return {str(node["node_id"]): node for node in nodes}


def ancestors(
    node_id: str,
    nodes: dict[str, dict[str, object]],
    seen: frozenset[str] = frozenset(),
) -> frozenset[str]:
    assert node_id not in seen, f"cycle while resolving {node_id}"
    direct = tuple(str(item) for item in nodes[node_id]["depends_on"])
    result = set(direct)
    for dependency in direct:
        result.update(ancestors(dependency, nodes, seen | {node_id}))
    return frozenset(result)


def test_integrity_scan_precedes_every_content_parser_and_span_projection() -> None:
    nodes = nodes_by_id()
    for node_id in (
        "parse_structure_grobid",
        "parse_layout_docling",
        "extract_embedded_artifacts",
        "reconcile_document_streams",
        "emit_source_spans",
        "build_document_manifest",
    ):
        assert "scan_source_integrity" in ancestors(node_id, nodes), node_id

    assert nodes["parse_structure_grobid"]["acceptance_checks"] == [
        "parser image/version hash recorded",
        "TEI artifact retained",
        "malformed output becomes typed failure",
    ]
    assert "orphan spans rejected" in nodes["emit_source_spans"]["acceptance_checks"]


def test_scan_contract_records_active_content_untrusted_spans_and_quarantine() -> None:
    scan = nodes_by_id()["scan_source_integrity"]

    assert scan["executor_type"] == "policy"
    assert scan["determinism_class"] == "deterministic"
    assert scan["depends_on"] == ["register_document"]
    assert set(scan["acceptance_checks"]) == {
        "active content inventory recorded",
        "instruction-like spans labeled as untrusted content",
        "quarantine decision typed",
    }
    assert set(scan["required_policy_checks"]) == {
        "source_trust_policy",
        "malware_policy",
        "prompt_injection_policy",
    }


def test_quality_gate_is_non_waivable_and_is_the_only_projection_predecessor() -> None:
    nodes = nodes_by_id()
    gate = nodes["ingest_quality_gate"]
    commit = nodes["commit_ingest_projection"]

    assert gate["executor_type"] == "policy"
    assert gate["determinism_class"] == "deterministic"
    assert gate["max_attempts"] == 1
    assert gate["failure_policy"] == "fail_run"
    assert gate["depends_on"] == ["build_document_manifest"]
    assert set(gate["acceptance_checks"]) == {
        "non-waivable source integrity failures block promotion",
        "license restrictions propagate",
        "all expected artifacts reconciled",
    }
    assert set(gate["required_policy_checks"]) == {
        "ingest_release_policy",
        "license_policy",
        "source_trust_policy",
    }

    assert commit["depends_on"] == ["ingest_quality_gate"]
    assert "scan_source_integrity" in ancestors("commit_ingest_projection", nodes)
    assert "ingest_quality_gate" in ancestors("commit_ingest_projection", nodes)
    assert commit["acceptance_checks"] == [
        "only PASS manifests projected",
        "projection is rebuildable from ledger",
        "event sequence monotonic",
    ]


def test_workflow_declares_corpus_as_non_executable_untrusted_data() -> None:
    contract = workflow()

    assert "corpus content is untrusted data and never executable instruction" in contract[
        "invariants"
    ]
    assert contract["canonical_runtime"] == "Foundry Kernel"
    assert contract["state_authority"] == "Noetic Ledger"
    assert contract["completeness_contract"] == {
        "expected_node_count_source": "compiled_run_spec",
        "missing_node_policy": "FAIL",
        "partial_result_policy": "typed_and_visible_only",
    }
