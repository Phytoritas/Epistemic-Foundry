#!/usr/bin/env python3
"""Run the Epistemic Foundry v4 288-lens evolution architecture audit.

This is a structured specification review: 24 failure-surface families ×
12 lenses. It verifies declared evidence paths and A–Z owners. It does not
claim 288 statistically independent human/model proofs or implemented
production behavior.
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


def evaluate_lens(
    root: Path,
    wp_ids: set[str],
    family: dict[str, Any],
    lens: dict[str, Any],
) -> dict[str, Any]:
    verification: list[str] = []
    valid = True

    paths = [str(x) for x in lens.get("evidence", [])]
    if not paths:
        valid = False
        verification.append("no evidence paths declared")
    for raw in paths:
        path = root / raw
        exists = path.exists() and (not path.is_file() or path.stat().st_size > 0)
        valid = valid and exists
        verification.append(f"{raw}: exists_and_nonempty={exists}")

    owner = str(lens.get("owner_work_package", ""))
    owner_ok = owner in wp_ids
    valid = valid and owner_ok
    verification.append(f"owner_work_package={owner}: declared={owner_ok}")

    expected = str(lens.get("status", "PASS"))
    if expected not in {"PASS", "CONDITIONAL"}:
        valid = False
        verification.append(f"invalid declared status={expected}")

    conditional = lens.get("conditional_requirement")
    if expected == "CONDITIONAL" and not conditional:
        valid = False
        verification.append("CONDITIONAL lens lacks conditional_requirement")

    status = expected if valid else "FAIL"
    return {
        "lens_id": str(lens.get("lens_id", "")),
        "family_id": family.get("family_id"),
        "family": family.get("name"),
        "kind": lens.get("kind"),
        "question": lens.get("question"),
        "status": status,
        "finding": lens.get("question"),
        "evidence": paths,
        "verification": verification,
        "owner_work_package": owner,
        "conditional_requirement": conditional,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("manifests/288_lens_evolution_audit_matrix.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/288_lens_evolution_audit_results.json"),
    )
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()

    root = args.root.resolve()
    matrix_path = args.matrix if args.matrix.is_absolute() else root / args.matrix
    output_path = args.output if args.output.is_absolute() else root / args.output

    matrix = load_yaml(matrix_path)
    families = matrix.get("families", [])
    pairs = [
        (family, lens)
        for family in families
        for lens in family.get("lenses", [])
    ]
    if len(families) != 24 or len(pairs) != 288:
        print(
            f"FAIL: expected 24 families/288 lenses, got "
            f"{len(families)}/{len(pairs)}",
            file=sys.stderr,
        )
        return 2

    ids = [str(lens.get("lens_id", "")) for _, lens in pairs]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        print("FAIL: missing or duplicate lens IDs", file=sys.stderr)
        return 2

    wp_ids = work_package_ids(root)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 288))) as executor:
        futures = [
            executor.submit(evaluate_lens, root, wp_ids, family, lens)
            for family, lens in pairs
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item["lens_id"])
    counts = {"PASS": 0, "CONDITIONAL": 0, "FAIL": 0}
    for result in results:
        counts[result["status"]] += 1

    payload = {
        "audit_id": matrix.get("audit_id"),
        "version": matrix.get("version"),
        "interpretation": matrix.get("method"),
        "families": len(families),
        "total": len(results),
        "summary": counts,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"288-LENS EVOLUTION AUDIT: {counts['PASS']} PASS / "
        f"{counts['CONDITIONAL']} CONDITIONAL / {counts['FAIL']} FAIL"
    )
    print(f"Report: {output_path}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
