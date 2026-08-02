#!/usr/bin/env python3
"""Parse B04-0006 full Python JUnit into a stable failure inventory.

The fresh canonical projection is a packaging success, but it changes the
contract bytes consumed by handwritten runtime code.  This parser preserves
every failing/erroring pytest node and assigns only evidence-backed, bounded
fingerprints; unknown cases remain explicitly unclassified.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/B04/attempts/0006"
JUNIT = ATTEMPT / "full-python-suite.junit.xml"
OUTPUT = ATTEMPT / "full-python-failure-inventory.json"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_excerpt(text: str) -> str:
    """Return a stable, bounded diagnostic excerpt without machine paths."""

    text = text.replace(str(ROOT), "<ROOT>").replace(str(ROOT).lower(), "<ROOT>")
    text = text.replace("\\", "/")
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:24])[:6000]


def classify(node_id: str, problem_text: str) -> tuple[str, list[str], str]:
    haystack = f"{node_id}\n{problem_text}".lower().replace("\\", "/")
    if (
        "test_repository_dependency_lock_closes_exact_tiktoken_pin" in haystack
        or "tokenizer_contract_unavailable" in haystack
    ):
        return (
            "J02_TIKTOKEN_DEPENDENCY_DEBT",
            ["tests/test_j02_context_budget.py"],
            "J02",
        )
    if (
        "holdoutmanifest" in haystack
        or "holdout-manifest.schema.json" in haystack
        or "verifier_firewall/firewall.py" in haystack
        or "holdout_manifest_id" in haystack
        or "dataset_or_fixture_ids" in haystack
        or "access_principal_ids" in haystack
    ):
        return (
            "HOLDOUT_MANIFEST_RUNTIME_SCHEMA_DRIFT",
            ["src/epistemic_foundry/verifier_firewall/firewall.py"],
            "UNASSIGNED_RUNTIME_MIGRATION_OWNER",
        )
    if (
        "gatedecision" in haystack
        or "gate-decision.schema.json" in haystack
        or "foundry_kernel/gates.py" in haystack
        or "'gate_version' is a required property" in haystack
        or "'input_artifact_ids' is a required property" in haystack
        or "'policy_bundle_hash' is a required property" in haystack
        or "'blocker_ids' is a required property" in haystack
    ):
        return (
            "GATE_DECISION_RUNTIME_SCHEMA_DRIFT",
            ["src/epistemic_foundry/foundry_kernel/gates.py"],
            "UNASSIGNED_RUNTIME_MIGRATION_OWNER",
        )
    return ("UNCLASSIFIED_FULL_SUITE_FAILURE", [], "UNRESOLVED")


def suite_counts(root: ET.Element) -> dict[str, int]:
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "collected": sum(int(suite.get("tests", "0")) for suite in suites),
        "errors": sum(int(suite.get("errors", "0")) for suite in suites),
        "failed": sum(int(suite.get("failures", "0")) for suite in suites),
        "skipped": sum(int(suite.get("skipped", "0")) for suite in suites),
    }


def main() -> int:
    root = ET.parse(JUNIT).getroot()
    counts = suite_counts(root)
    rows: list[dict[str, Any]] = []
    kinds: Counter[str] = Counter()
    classifications: Counter[str] = Counter()

    for case in root.findall(".//testcase"):
        failure = case.find("failure")
        error = case.find("error")
        problem = failure if failure is not None else error
        if problem is None:
            continue
        kind = "failure" if failure is not None else "error"
        classname = case.get("classname", "")
        name = case.get("name", "")
        node_id = f"{classname}::{name}" if classname else name
        raw_text = "\n".join(
            value
            for value in (problem.get("message", ""), problem.text or "")
            if value
        )
        fingerprint, affected_paths, owner = classify(node_id, raw_text)
        kinds[kind] += 1
        classifications[fingerprint] += 1
        rows.append(
            {
                "affected_runtime_paths": affected_paths,
                "classification": fingerprint,
                "failure_kind": kind,
                "failure_type": problem.get("type", ""),
                "migration_owner": owner,
                "node_id": node_id,
                "normalized_diagnostic": normalized_excerpt(raw_text),
            }
        )

    observed_problem_count = len(rows)
    declared_problem_count = counts["failed"] + counts["errors"]
    if observed_problem_count != declared_problem_count:
        raise SystemExit(
            "JUnit problem count mismatch: "
            f"observed={observed_problem_count}, declared={declared_problem_count}"
        )
    counts["passed"] = (
        counts["collected"]
        - counts["failed"]
        - counts["errors"]
        - counts["skipped"]
    )
    result = {
        "attempt_id": "B04-0006",
        "classification_counts": dict(sorted(classifications.items())),
        "completion_ready": False,
        "junit_path": JUNIT.relative_to(ROOT).as_posix(),
        "junit_sha256": sha256(JUNIT),
        "problem_kind_counts": dict(sorted(kinds.items())),
        "problems": rows,
        "suite": counts,
        "unclassified_problem_count": classifications.get(
            "UNCLASSIFIED_FULL_SUITE_FAILURE", 0
        ),
    }
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({key: value for key, value in result.items() if key != "problems"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
