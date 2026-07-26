#!/usr/bin/env python3
"""Run the Epistemic Foundry v3 216-lens plugin architecture audit.

The audit is a structured specification review: 18 failure-surface families ×
12 lenses. It verifies traceability to concrete artifacts and A–Z work-package
owners. It does not claim 216 statistically independent human/model proofs or
that the reference blueprint is already a working production plugin.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def work_package_ids(root: Path) -> set[str]:
    manifest = load_yaml(root / "manifests/development_manifest.yaml")
    return {str(item["id"]) for item in manifest.get("work_packages", [])}


def evaluate_lens(root: Path, wp_ids: set[str], family: dict[str, Any], lens: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    ok = True

    paths = lens.get("evidence_paths", [])
    if not paths:
        ok = False
        evidence.append("no evidence_paths declared")
    for raw in paths:
        path = root / str(raw)
        exists = path.exists() and (not path.is_file() or path.stat().st_size > 0)
        ok = ok and exists
        evidence.append(f"{raw}: exists_and_nonempty={exists}")

    owner = str(lens.get("owner_work_package", ""))
    owner_ok = owner in wp_ids
    ok = ok and owner_ok
    evidence.append(f"owner_work_package={owner}: declared={owner_ok}")

    expected = str(lens.get("expected_status", "PASS"))
    if expected not in {"PASS", "CONDITIONAL"}:
        ok = False
        evidence.append(f"invalid expected_status={expected}")

    status = "FAIL" if not ok else expected
    return {
        "lens_id": lens["id"],
        "family": family["name"],
        "question": lens["question"],
        "approach": lens["approach"],
        "status": status,
        "finding": lens["finding"],
        "evidence": paths,
        "verification": evidence,
        "owner_work_package": owner,
        "release_effect": lens.get("release_effect", "none"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--matrix", type=Path, default=Path("manifests/216_lens_plugin_audit_matrix.yaml"))
    parser.add_argument("--output", type=Path, default=Path("reports/216_lens_plugin_audit_results.json"))
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()

    root = args.root.resolve()
    matrix_path = args.matrix if args.matrix.is_absolute() else root / args.matrix
    output_path = args.output if args.output.is_absolute() else root / args.output

    matrix = load_yaml(matrix_path)
    families = matrix.get("families", [])
    pairs = [(family, lens) for family in families for lens in family.get("lenses", [])]
    if len(families) != 18 or len(pairs) != 216:
        print(f"FAIL: expected 18 families/216 lenses, got {len(families)}/{len(pairs)}", file=sys.stderr)
        return 2

    ids = [str(lens["id"]) for _, lens in pairs]
    if len(ids) != len(set(ids)):
        print("FAIL: duplicate lens IDs", file=sys.stderr)
        return 2

    wp_ids = work_package_ids(root)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 216))) as executor:
        futures = [executor.submit(evaluate_lens, root, wp_ids, family, lens) for family, lens in pairs]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item["lens_id"])
    counts = {"PASS": 0, "CONDITIONAL": 0, "FAIL": 0}
    for result in results:
        counts[result["status"]] += 1

    payload = {
        "audit_id": matrix.get("audit_id"),
        "version": matrix.get("version"),
        "interpretation": matrix.get("audit_method"),
        "total": len(results),
        "summary": counts,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"216-LENS PLUGIN AUDIT: {counts['PASS']} PASS / "
        f"{counts['CONDITIONAL']} CONDITIONAL / {counts['FAIL']} FAIL"
    )
    print(f"Report: {output_path}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
