#!/usr/bin/env python3
"""Deterministically verify the A05 attempt-0002 authority contract.

This is contract evidence, not the production promotion implementation. It
checks the product-owner decision, immutable attempt-0001 evidence, the A05
charter's normative tables and ordered workflow, negative-test requirements,
and unchanged canonical inputs that A05 is forbidden to edit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[5]
CHARTER_PATH = ROOT / "docs/v4_a05/evolution_authority_and_promotion_charter.md"
NEGATIVE_PATH = ROOT / "docs/v4_a05/adversarial_contract_tests.md"

AUTHORITY_HASHES = {
    "MASTER_EXECUTION_PROMPT.md": "9b6cff656c62383229c5836c260b48a6f3fd024db7dc71ff04521ab7b539b855",
    "MASTER_SPEC.md": "43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3",
    "artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.human-decision.json": "436a69bfebf374e78e3f52711c52f2f2c02cb429fb8c0a8a5e4988720cdca2d1",
    "artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.md": "61e1be8c66491843845d5cac4d7446f4110fe679a64ab6560443abd3c83dd874",
    "manifests/development_manifest.yaml": "9ae9090a8d02973198492f271a9e46a352ca030eaa8b272e696bf6cd9ec1896e",
}

HISTORICAL_HASHES = {
    "artifacts/work_packages/A04/report.json": "f34f72c561a6eb1696a524c1910d83a338847536e3c497c5d3038e7a1d2855ab",
    "artifacts/work_packages/A05/report.json": "9454f609060d652bcb4073e2da85dccfdfce79298337dbf8ae0233ff5c651b13",
    "artifacts/work_packages/A05/review.md": "5a83fb5f75916e9da53d82fc3fa93c14920f24cec9a30a0923802b32418a2b57",
    "artifacts/work_packages/A05/commands.jsonl": "65393532c41415b187e98dee1d8759e0e9df1c24a11f711637d12ff2e66a5e18",
    "artifacts/work_packages/A05/authority-contract-probe.json": "f02b6cf0abc0f53bac6099f5e524acb11d376ddc768871e8589946610fe769e0",
    "artifacts/work_packages/A05/authority_contract_probe.py": "ad5e5650a05260379fbce9f0ce769e914ff5e5fb459aa41a341ff86cbba7ff40",
    "docs/v4_a05/authority_contract_gap.md": "7f66f22f8964cb53d3cb89eafeaf4b080e6abcdc9ad0470f85607015c3766f9f",
}

CANONICAL_INPUT_HASHES = {
    "prompts/promotion_attestor.md": "cba0bf56de963541abb5231e7ac3d7ae213bcdab856ebd825dc3efaba4f0b224",
    "schemas/evolution-run-spec.schema.json": "29fe472309463865f58413c9e6566d6b3bcb71be7f6f7c74dfe1176f6a407ee9",
    "schemas/promotion-decision.schema.json": "a71a125155f5690f7367b800d88ef7c49ef1f132cb607b37abb04e820924ebdc",
    "schemas/run-spec.schema.json": "91a8ee9e05bb3fb264f355b93ddad07d1e47b2829f6f960ade4c46a04011c64c",
    "src/epistemic_foundry/governance/promotion.py": "a05013fdd9ea83a51071f376075b540a2fc371bb7e9f2ff12f786feb0ba90e71",
    "workflows/evolution_chamber_cycle.workflow.yaml": "d3a611dc7c18dfdd8353cc49fa73bf0145465a245b00d22c945e5aa55ab40688",
}

TUPLE_FIELDS = [
    "logical_id",
    "exact_version_or_revision",
    "content_hash",
    "resolver_id",
    "resolver_version",
    "resolved_artifact_locator",
    "resolved_at",
    "authority_source_class",
    "reproducibility_class",
]

RESOLVED_REF_KEYS = [
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
    "external_backend_manifest",
]

PROMOTION_LEVELS = [
    "INBOX",
    "CANDIDATE",
    "LITERATURE_GROUNDED",
    "VALIDATION_SCREENED",
    "EMPIRICALLY_TESTED",
    "REPLICATED",
]

GATES = [
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

APPLICABILITY = {
    "G00_PIN_RESOLUTION": ["R", "R", "R", "R", "R", "R"],
    "G01_POLICY_AUTHORITY": ["R", "R", "R", "R", "R", "R"],
    "G02_EVALUATOR_HOLDOUT_FIREWALL": ["R", "R", "R", "R", "R", "R"],
    "G03_SCHEMA_LINEAGE_COUNT": ["P", "R", "R", "R", "R", "R"],
    "G04_SOURCE_PROVENANCE": ["R", "R", "R", "R", "R", "R"],
    "G05_SEARCH_COVERAGE": ["P", "P", "R", "R", "R", "R"],
    "G06_METHOD_SCOPE_DEPENDENCY": ["P", "P", "R", "R", "R", "R"],
    "G07_VALIDATION_LEAKAGE": ["P", "P", "P", "R", "R", "R"],
    "G08_ADAPTIVE_STATISTICS": ["P", "P", "R", "R", "R", "R"],
    "G09_RED_QUEEN": ["P", "P", "R", "R", "R", "R"],
    "G10_REPLICATION_CEILING": ["R", "R", "R", "R", "R", "R"],
    "G11_PARLIAMENT": ["P", "P", "R", "R", "R", "R"],
    "G12_INDEPENDENT_ATTESTATION": ["P", "P", "P", "R", "R", "R"],
    "G13_HUMAN_POLICY_APPROVAL": ["C", "C", "C", "C", "C", "C"],
    "G14_ATOMIC_PROMOTION_COMMIT": ["R", "R", "R", "R", "R", "R"],
}

NEGATIVE_EXPECTATIONS = {
    "A05-NEG-001": ["G00", "FAIL", "floating"],
    "A05-NEG-002": ["G00", "FAIL", "hash mismatch"],
    "A05-NEG-003": ["G00", "BLOCK", "BLOCKED"],
    "A05-NEG-004": ["SPEC_GAP", "ordering"],
    "A05-NEG-005": ["G00", "FAIL", "new spec revision"],
    "A05-NEG-006": ["G02_EVALUATOR_HOLDOUT_FIREWALL", "FAIL"],
    "A05-NEG-007": ["G02_EVALUATOR_HOLDOUT_FIREWALL", "FAIL", "approval cannot override"],
    "A05-NEG-008": ["G01", "scalar-only", "FAIL"],
    "A05-NEG-009": ["G03", "FAIL", "partial fan-in"],
    "A05-NEG-010": ["G04", "FAIL"],
    "A05-NEG-011": ["G05", "FAIL"],
    "A05-NEG-012": ["G08", "FAIL"],
    "A05-NEG-013": ["G10", "FAIL", "empty result array"],
    "A05-NEG-014": ["G10", "FAIL", "LITERATURE_GROUNDED", "LOWER", "BLOCK"],
    "A05-NEG-015": ["G11", "FAIL", "majority"],
    "A05-NEG-016": ["G12", "FAIL", "non-independent"],
    "A05-NEG-017": ["G01/G13", "FAIL", "self-approval"],
    "A05-NEG-018": ["G13", "cannot convert", "PASS"],
    "A05-NEG-019": ["G13", "FAIL", "BLOCK", "NOT_REQUIRED"],
    "A05-NEG-020": ["G14", "FAIL", "completion"],
    "A05-NEG-021": ["G14", "conflict", "no state change"],
    "A05-NEG-022": ["existing logical result", "no duplicate"],
    "A05-NEG-023": ["unknown", "reconciled", "FAIL", "BLOCKED"],
    "A05-NEG-024": ["G14", "rejects", "new immutable revision"],
}

POSITIVE_IDS = ["A05-POS-001", "A05-POS-002", "A05-POS-003", "A05-POS-004"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def hash_map(expected: dict[str, str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in expected.items():
        path = ROOT / relative
        require(path.is_file(), f"missing bound artifact: {relative}")
        actual = sha256(path)
        require(actual == expected_hash, f"hash mismatch for {relative}: {actual}")
        result[relative] = {
            "sha256": actual,
            "byte_size": path.stat().st_size,
            "status": "PASS",
        }
    return result


def canonical_json_hash_excluding(document: dict[str, Any], field: str) -> str:
    payload = {key: value for key, value in document.items() if key != field}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_table_row(text: str, key: str) -> list[str]:
    pattern = re.compile(rf"^\|\s*`{re.escape(key)}`\s*\|(.+)$", re.MULTILINE)
    match = pattern.search(text)
    require(match is not None, f"missing table row: {key}")
    return [cell.strip() for cell in match.group(1).split("|") if cell.strip()]


def section(text: str, heading: str, next_heading_prefix: str = "## ") -> str:
    start = text.find(heading)
    require(start >= 0, f"missing heading: {heading}")
    next_start = text.find("\n" + next_heading_prefix, start + len(heading))
    if next_start < 0:
        return text[start:]
    return text[start:next_start]


def validate_decision() -> dict[str, Any]:
    path = ROOT / "artifacts/authority_decisions/EF4-A05-C01-B04-SHARED-CONTRACT.human-decision.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    require(document["decision_id"] == "HD-EF4-A05-C01-B04-20260727-001", "wrong decision id")
    require(document["decision_type"] == "correct", "decision is not correct")
    require(document["authority_role"] == "product_owner", "wrong authority role")
    require(document["non_mutation_acknowledgement"] is True, "non-mutation acknowledgement missing")
    computed = canonical_json_hash_excluding(document, "decision_hash")
    require(computed == document["decision_hash"], "HumanDecision decision_hash mismatch")
    return {
        "decision_id": document["decision_id"],
        "decision_hash": document["decision_hash"],
        "non_mutation_acknowledgement": True,
        "status": "PASS",
    }


def validate_charter(text: str) -> dict[str, Any]:
    require("A05-SG001" in text and "A05-SG002" in text, "prior gaps not superseded explicitly")
    require("A05 does not modify a schema, workflow, or runtime file" in text, "A05 scope boundary missing")

    for field in TUPLE_FIELDS:
        parse_table_row(text, field)
    for key in RESOLVED_REF_KEYS:
        parse_table_row(text, key)

    promotion_vocabulary = section(text, "## 3. Promotion vocabulary")
    first_positions = [promotion_vocabulary.find(f"`{level}`") for level in PROMOTION_LEVELS]
    require(all(position >= 0 for position in first_positions), "promotion level missing")
    require(first_positions == sorted(first_positions), "promotion level order is not canonical")
    require("`BLOCK` is a promotion decision/effect semantic, not a seventh level" in text, "BLOCK/level separation missing")

    gate_semantics = section(text, "### 4.1 Canonical gate order and semantics", "### ")
    gate_positions = [gate_semantics.find(f"`{gate}`") for gate in GATES]
    require(all(position >= 0 for position in gate_positions), "canonical gate missing")
    require(gate_positions == sorted(gate_positions), "gate order differs from G00-G14")

    parsed_applicability: dict[str, list[str]] = {}
    for gate, expected in APPLICABILITY.items():
        cells = parse_table_row(text, gate)
        require(cells == expected, f"wrong applicability for {gate}: {cells}")
        parsed_applicability[gate] = cells

    workflow = section(text, "## 8. Receipt-bound promotion workflow")
    steps = re.findall(r"^(\d+)\.\s+(.+)$", workflow, flags=re.MULTILINE)
    require([int(number) for number, _ in steps] == list(range(1, 19)), "workflow is not exactly steps 1-18")
    workflow_text = "\n".join(item for _, item in steps)
    for token in [
        "request_promotion",
        "phase-E",
        "G00 through G10",
        "Evidence Parliament",
        "G11",
        "G12",
        "Recheck G10",
        "G13",
        "commit_promotion",
        "promotion:commit",
        "Compare-and-swap",
        "PromotionDecision",
        "HypothesisPassport",
        "EventRecord",
        "EffectReceipt",
        "ArtifactReceipt",
        "G14",
    ]:
        require(token in workflow_text, f"workflow token missing: {token}")

    required_phrases = [
        "RFC 8785 JCS",
        "UTF-8 bytes",
        "`spec_hash` is excluded",
        "both a new\n`EvolutionRunSpec` revision and a new `evolution_run_id`",
        "provider_versioned_not_byte_pinned",
        "candidate_id + candidate_revision + requested_level + promotion_pack_hash + policy_bundle_hash",
        "absence of an `EffectReceipt` means success is not proven",
        "Every gate executes in this order and emits one immutable `GateDecision`",
        "`input_hash`, `decision_hash`, `policy_version`, and evidence IDs",
        "`WAIVE` is forbidden for a non-waivable gate",
    ]
    for phrase in required_phrases:
        require(phrase in text, f"required charter phrase missing: {phrase}")

    replication_controls = {
        "not_run_or_blocked": all(token in text for token in ["Not run or `BLOCKED`", "`EMPIRICALLY_TESTED`", "`CONDITIONAL`", "`UNDERDETERMINED`"]),
        "partial": "`PARTIAL`" in text and "unresolved issues and limitations are required" in text,
        "inconclusive": "`INCONCLUSIVE`" in text,
        "failed_core": all(token in text for token in ["core empirical effect failed", "`LITERATURE_GROUNDED`", "`LOWER` or `BLOCK`"]),
        "replicated_eligible_only": "`REPLICATED` is eligible, not automatic" in text,
        "formal_exception": "two independent formal-verifier paths" in text and "forbidden for an ordinary empirical claim" in text,
    }
    require(all(replication_controls.values()), "replication ceiling matrix incomplete")

    approval_triggers = [
        "E4 or E5 work class",
        "High-risk or controlled external effect",
        "Hidden-holdout unblinding",
        "External publication/release",
        "Policy or evaluator change proposal",
        "Non-local data export",
        "Publication-grade novelty claim",
        "Low-risk `CANDIDATE` or `LITERATURE_GROUNDED` internal promotion",
    ]
    for trigger in approval_triggers:
        require(trigger in text, f"approval trigger missing: {trigger}")

    return {
        "tuple_fields": TUPLE_FIELDS,
        "resolved_ref_keys": RESOLVED_REF_KEYS,
        "promotion_levels": PROMOTION_LEVELS,
        "gate_order": GATES,
        "applicability_matrix": parsed_applicability,
        "workflow_step_count": len(steps),
        "replication_controls": replication_controls,
        "approval_trigger_count": len(approval_triggers),
        "status": "PASS",
    }


def validate_negative_registry(text: str) -> dict[str, Any]:
    results = []
    for test_id, tokens in NEGATIVE_EXPECTATIONS.items():
        cells = parse_table_row(text, test_id)
        row = " | ".join(cells)
        missing = [token for token in tokens if token not in row]
        require(not missing, f"{test_id} misses required outcome tokens: {missing}")
        results.append({
            "test_id": test_id,
            "expected_tokens": tokens,
            "observed": "contract row contains every required rejection token",
            "status": "PASS",
        })
    for test_id in POSITIVE_IDS:
        parse_table_row(text, test_id)
    require(
        re.search(
            r"untyped exception or\s+returns a scalar false does not satisfy",
            text,
        )
        is not None,
        "typed GateDecision test requirement missing",
    )
    return {
        "negative_test_count": len(results),
        "positive_boundary_control_count": len(POSITIVE_IDS),
        "results": results,
        "status": "PASS",
    }


def validate_schema_meta() -> dict[str, str]:
    schema_paths = [
        "schemas/evolution-run-spec.schema.json",
        "schemas/gate-decision.schema.json",
        "schemas/promotion-decision.schema.json",
        "schemas/adjudication.schema.json",
        "schemas/phase-artifact-set.schema.json",
        "schemas/replication-result.schema.json",
        "schemas/attestation.schema.json",
        "schemas/approval-record.schema.json",
    ]
    result: dict[str, str] = {}
    for relative in schema_paths:
        schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        result[relative] = "PASS"
    return result


def validate_text_integrity(paths: list[Path]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for path in paths:
        data = path.read_bytes()
        require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {path}")
        text = data.decode("utf-8", errors="strict")
        require("\ufffd" not in text, f"replacement character found: {path}")
        relative = path.relative_to(ROOT).as_posix()
        results[relative] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_size": len(data),
            "line_count": len(text.splitlines()),
            "utf8_without_bom": True,
            "replacement_character_absent": True,
        }
    return results


def build_evidence() -> dict[str, Any]:
    charter = CHARTER_PATH.read_text(encoding="utf-8")
    negative = NEGATIVE_PATH.read_text(encoding="utf-8")
    a04 = json.loads((ROOT / "artifacts/work_packages/A04/report.json").read_text(encoding="utf-8"))
    prior = json.loads((ROOT / "artifacts/work_packages/A05/report.json").read_text(encoding="utf-8"))
    require(a04["status"] == "PASS", "A04 dependency is not PASS")
    require(prior["status"] == "SPEC_GAP", "prior A05 result was changed")
    require({gap["id"] for gap in prior["spec_gaps"]} == {"A05-SG001", "A05-SG002"}, "prior gap set changed")

    evidence = {
        "schema_version": 1,
        "work_package_id": "A05",
        "attempt_id": "A05-0002",
        "status": "PASS",
        "authority_decision": validate_decision(),
        "authority_bindings": hash_map(AUTHORITY_HASHES),
        "dependency_checkpoint": {
            "work_package_id": "A04",
            "status": a04["status"],
            "report_sha256": HISTORICAL_HASHES["artifacts/work_packages/A04/report.json"],
        },
        "historical_integrity": {
            "prior_attempt_status": prior["status"],
            "prior_gap_ids": ["A05-SG001", "A05-SG002"],
            "bound_artifacts": hash_map(HISTORICAL_HASHES),
            "preserved_not_overwritten": True,
        },
        "a05_forbidden_input_integrity": hash_map(CANONICAL_INPUT_HASHES),
        "charter_contract": validate_charter(charter),
        "adversarial_contract_tests": validate_negative_registry(negative),
        "schema_meta_validation": validate_schema_meta(),
        "text_integrity": validate_text_integrity([CHARTER_PATH, NEGATIVE_PATH]),
        "scope_statement": {
            "a05_writes_only": ["docs/v4_a05/**", "artifacts/work_packages/A05/**"],
            "schema_workflow_runtime_changes": 0,
            "production_runtime_claimed": False,
        },
        "decision": {
            "typed_outcome": "PASS",
            "resolved_prior_gaps": ["A05-SG001", "A05-SG002"],
            "reason": "The product-owner decision is fully expressed as a deterministic authority charter, matrices, ordered receipt workflow, and adversarial contract-test registry without changing schema, workflow, or runtime files.",
        },
    }
    return evidence


def encoded_evidence(evidence: dict[str, Any]) -> bytes:
    return (json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--check",
        type=Path,
        help="Compare generated evidence byte-for-byte with this file",
    )
    output_group.add_argument(
        "--output",
        type=Path,
        help="Write deterministic evidence to this path",
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
        rendered = encoded_evidence(evidence)
        if args.check:
            expected = args.check if args.check.is_absolute() else ROOT / args.check
            require(expected.is_file(), f"checked evidence missing: {expected}")
            actual = expected.read_bytes()
            require(actual == rendered, "checked evidence does not byte-match deterministic verifier output")
            print(
                "PASS: A05 attempt 0002 authority contract, immutable history, "
                "15-gate order, 6-level matrices, 18-step workflow, and 24 "
                "negative requirements byte-match checked evidence"
            )
        elif args.output:
            output = args.output if args.output.is_absolute() else ROOT / args.output
            output = output.resolve()
            root = ROOT.resolve()
            require(output.is_relative_to(root), "output must remain inside the repository")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(rendered)
            print(f"PASS: wrote deterministic A05 evidence to {output.relative_to(root).as_posix()}")
        else:
            sys.stdout.buffer.write(rendered)
        return 0
    except (AssertionError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
