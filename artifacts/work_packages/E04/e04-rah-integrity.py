#!/usr/bin/env python3
"""Read-only integrity verification for retained E04 RAH generations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RAH_ROOT = ROOT / ".rah" / "ralph"
PACKAGE = ROOT / "artifacts" / "work_packages" / "E04"
GENERATION_FILES = (
    "goal.json",
    "loop_state.json",
    "evidence_ledger.json",
    "plan_graph.json",
    "goal_bridge.json",
    "review_gate.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read JSON {path}: {error}")
    if not isinstance(document, dict):
        raise SystemExit(f"JSON document is not an object: {path}")
    return document


def canonical_without_stamp(document: dict[str, Any]) -> str:
    stripped = {key: value for key, value in document.items() if key != "state_generation"}
    return json.dumps(stripped, ensure_ascii=False, indent=2)


def verify(
    *,
    expected_generation_count: int,
    expected_generation: str | None,
    expected_generation_sequence: int,
    expected_evidence_id: str,
) -> dict[str, Any]:
    pointer = read_json(RAH_ROOT / "current.json")
    current = pointer.get("generation")
    if not isinstance(current, str) or not re.fullmatch(
        rf"{expected_generation_sequence:06d}-[0-9a-f]{{8}}", current
    ):
        raise SystemExit(f"unexpected current generation sequence: {current}")
    if expected_generation is not None and current != expected_generation:
        raise SystemExit(f"unexpected current generation: {current}")

    generations = sorted(
        path.name
        for path in (RAH_ROOT / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )
    if len(generations) != expected_generation_count or generations[-1] != current:
        raise SystemExit(
            f"expected {expected_generation_count} retained generations ending at "
            f"{current}, found {generations}"
        )

    verified_hashes = 0
    generation_manifests: list[dict[str, Any]] = []
    for generation in generations:
        generation_root = RAH_ROOT / "generations" / generation
        manifest_path = generation_root / "generation-manifest.json"
        manifest = read_json(manifest_path)
        files = manifest.get("files")
        if manifest.get("generation") != generation:
            raise SystemExit(f"generation ID mismatch: {generation}")
        if not isinstance(files, dict) or set(files) != set(GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in GENERATION_FILES:
            actual = sha256(generation_root / name)
            if actual != files[name]:
                raise SystemExit(f"payload hash mismatch: {generation}/{name}")
            verified_hashes += 1
        generation_manifests.append(
            {
                "generation": generation,
                "manifest_sha256": sha256(manifest_path),
                "payload_hash_count": len(files),
            }
        )

    current_root = RAH_ROOT / "generations" / current
    flat_stamps = 0
    flat_matches = 0
    projections: list[dict[str, Any]] = []
    for name in GENERATION_FILES:
        authority = read_json(current_root / name)
        flat = read_json(RAH_ROOT / name)
        stamp_matches = flat.get("state_generation") == current
        content_matches = canonical_without_stamp(flat) == canonical_without_stamp(authority)
        flat_stamps += int(stamp_matches)
        flat_matches += int(content_matches)
        projections.append(
            {
                "path": f".rah/ralph/{name}",
                "state_generation_matches": stamp_matches,
                "content_matches": content_matches,
            }
        )
    if flat_stamps != len(GENERATION_FILES) or flat_matches != len(GENERATION_FILES):
        raise SystemExit(
            f"flat projection mismatch: stamps={flat_stamps}, content={flat_matches}"
        )

    ledger = read_json(current_root / "evidence_ledger.json")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise SystemExit("evidence ledger entries are not a list")
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    if not re.fullmatch(r"E\d{4}", expected_evidence_id):
        raise SystemExit(f"invalid expected evidence ID: {expected_evidence_id}")
    expected_high_water = int(expected_evidence_id[1:])
    expected_ids = [f"E{index:04d}" for index in range(1, expected_high_water + 1)]
    if ids != expected_ids or ledger.get("issued_id_high_water") != expected_high_water:
        raise SystemExit(
            f"evidence ledger is not the continuous E0001-{expected_evidence_id} sequence"
        )

    loop = read_json(current_root / "loop_state.json")
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion_ready must remain false")

    return {
        "schema_version": 1,
        "status": "PASS",
        "mode": "READ_ONLY",
        "current_generation": current,
        "latest_evidence_id": ids[-1],
        "evidence_count": len(ids),
        "issued_id_high_water": ledger.get("issued_id_high_water"),
        "retained_generation_manifest_count": len(generations),
        "generation_file_hashes_verified": verified_hashes,
        "flat_snapshot_stamps_verified": flat_stamps,
        "flat_snapshot_content_matches": flat_matches,
        "generation_manifests": generation_manifests,
        "flat_projections": projections,
        "parse_errors": {},
        "completion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PACKAGE / "rah-integrity.json")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--expected-generation-count", type=int, required=True)
    parser.add_argument("--expected-generation", default="")
    parser.add_argument("--expected-generation-sequence", type=int, required=True)
    parser.add_argument("--expected-evidence-id", required=True)
    args = parser.parse_args()
    result = verify(
        expected_generation_count=args.expected_generation_count,
        expected_generation=args.expected_generation or None,
        expected_generation_sequence=args.expected_generation_sequence,
        expected_evidence_id=args.expected_evidence_id,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not args.no_write:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
