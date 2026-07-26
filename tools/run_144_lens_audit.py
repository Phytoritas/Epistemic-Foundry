#!/usr/bin/env python3
"""Run the Epistemic Foundry 144-lens specification audit.

The lenses are independent architecture review questions executed concurrently.
They do not claim 144 independent human or model proofs. Each lens resolves to
PASS, CONDITIONAL, or FAIL with machine-readable evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def workflow_node_ids(path: Path) -> set[str]:
    doc = load_yaml(path)
    return {n["node_id"] for n in doc.get("nodes", [])}


def check_one(root: Path, check: dict[str, Any]) -> tuple[bool, str]:
    kind = check["type"]

    if kind == "path_exists":
        path = root / check["path"]
        return path.exists(), f"{check['path']} exists={path.exists()}"

    if kind == "contains_all":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [token for token in check["tokens"] if token not in text]
        return not missing, (
            f"{check['path']} contains all {len(check['tokens'])} tokens"
            if not missing else f"{check['path']} missing tokens: {missing}"
        )

    if kind == "contains_none":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        text = path.read_text(encoding="utf-8", errors="replace")
        found = [token for token in check["tokens"] if token in text]
        return not found, (
            f"{check['path']} contains none of forbidden tokens"
            if not found else f"{check['path']} contains forbidden tokens: {found}"
        )

    if kind == "json_has_properties":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        doc = load_json(path)
        properties = set(doc.get("properties", {}))
        missing = [name for name in check["properties"] if name not in properties]
        return not missing, (
            f"{check['path']} has properties {check['properties']}"
            if not missing else f"{check['path']} missing properties: {missing}"
        )

    if kind == "workflow_has_nodes":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        node_ids = workflow_node_ids(path)
        missing = [node for node in check["nodes"] if node not in node_ids]
        return not missing, (
            f"{check['path']} has nodes {check['nodes']}"
            if not missing else f"{check['path']} missing nodes: {missing}"
        )

    if kind == "glob_count":
        count = len(list(root.glob(check["pattern"])))
        minimum = int(check.get("minimum", 0))
        maximum = check.get("maximum")
        ok = count >= minimum and (maximum is None or count <= int(maximum))
        return ok, f"glob {check['pattern']} count={count}, expected >= {minimum}" + (
            "" if maximum is None else f" and <= {maximum}"
        )

    if kind == "yaml_list_count":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        doc = load_yaml(path)
        value = doc
        for key in check["key"].split("."):
            if not isinstance(value, dict) or key not in value:
                return False, f"{check['path']} missing key {check['key']}"
            value = value[key]
        count = len(value) if isinstance(value, list) else -1
        expected = int(check["expected"])
        return count == expected, f"{check['path']} {check['key']} count={count}, expected={expected}"

    if kind == "yaml_family_shape":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        doc = load_yaml(path)
        families = doc.get("families", [])
        expected_families = int(check["families"])
        expected_per = int(check["lenses_per_family"])
        bad = [(f.get("id"), len(f.get("lenses", []))) for f in families if len(f.get("lenses", [])) != expected_per]
        ok = len(families) == expected_families and not bad
        return ok, f"families={len(families)}, bad_family_sizes={bad}"

    if kind == "conditional":
        path = root / check["path"]
        if not path.exists():
            return False, f"missing file {check['path']}"
        text = path.read_text(encoding="utf-8", errors="replace")
        present = check["condition"] in text
        return present, (
            f"external decision is explicitly tracked: {check['condition']}"
            if present else f"conditional decision not tracked: {check['condition']}"
        )

    return False, f"unknown check type: {kind}"


def evaluate_lens(root: Path, family: dict[str, Any], lens: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    passed = True
    for check in lens.get("checks", []):
        try:
            ok, detail = check_one(root, check)
        except Exception as exc:
            ok, detail = False, f"{check.get('type')}: exception {type(exc).__name__}: {exc}"
        passed = passed and ok
        evidence.append(detail)

    expected = lens.get("expected_status", "PASS")
    if not passed:
        status = "FAIL"
    elif expected == "CONDITIONAL":
        status = "CONDITIONAL"
    else:
        status = "PASS"

    return {
        "id": lens["id"],
        "family_id": family["id"],
        "family": family["name"],
        "name": lens["name"],
        "question": lens["question"],
        "approach": lens["approach"],
        "expected_status": expected,
        "status": status,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("manifests/144_lens_audit_matrix.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/144_lens_audit_results.json"),
    )
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    root = args.root.resolve()
    matrix_path = args.matrix if args.matrix.is_absolute() else root / args.matrix
    output_path = args.output if args.output.is_absolute() else root / args.output

    matrix = load_yaml(matrix_path)
    families = matrix.get("families", [])
    lenses = [(family, lens) for family in families for lens in family.get("lenses", [])]

    if len(families) != 12 or len(lenses) != 144:
        print(f"FAIL: expected 12 families/144 lenses, got {len(families)}/{len(lenses)}", file=sys.stderr)
        return 2
    ids = [lens["id"] for _, lens in lenses]
    if len(ids) != len(set(ids)):
        print("FAIL: duplicate lens IDs", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 144))) as executor:
        futures = [executor.submit(evaluate_lens, root, family, lens) for family, lens in lenses]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item["id"])
    counts = {"PASS": 0, "CONDITIONAL": 0, "FAIL": 0}
    for result in results:
        counts[result["status"]] += 1

    payload = {
        "architecture_name": matrix.get("architecture_name"),
        "version": matrix.get("version"),
        "method": matrix.get("audit_method"),
        "summary": {
            "families": len(families),
            "lenses": len(results),
            **{key.lower(): value for key, value in counts.items()},
        },
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"144-LENS AUDIT: {counts['PASS']} PASS / "
        f"{counts['CONDITIONAL']} CONDITIONAL / {counts['FAIL']} FAIL"
    )
    print(f"Report: {output_path}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
