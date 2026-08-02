#!/usr/bin/env python3
"""A02 required check ``invariant_schema_check``.

Deterministic attestation that ``manifests/product_invariants.yaml`` is
well-formed and that every declared product invariant and non-goal conforms to
the shape the file's own ``validation_contract`` promises. This is the
structural half of the A02 exit criterion "v4 invariants are atomic and
testable".

The check is fail-closed: a malformed document, a missing required binding, a
duplicated or non-contiguous ID, a malformed ID, an empty binding, a non-goal
guard that points at a non-existent invariant, or a statement that does not
match the corresponding ``MASTER_SPEC.md`` / ``docs/product_constitution.md``
invariant all make the check exit non-zero. It reads the canonical files and
asserts their structure; it never edits them.

Run as a pytest module::

    .venv/Scripts/python.exe -B -m pytest \
        artifacts/work_packages/A02/attempts/0001/test_invariant_schema_check.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe -B \
        artifacts/work_packages/A02/attempts/0001/test_invariant_schema_check.py \
        --output artifacts/work_packages/A02/attempts/0001/invariant-schema-check.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]

INVARIANTS_YAML = "manifests/product_invariants.yaml"
CONSTITUTION_DOC = "docs/product_constitution.md"
MASTER_SPEC = "MASTER_SPEC.md"

# Bindings the file's own validation_contract promises for every invariant.
REQUIRED_BINDINGS = ("category", "statement", "evidence_artifacts", "work_packages")

INVARIANT_ID = re.compile(r"^EF4-I(\d{2})$")
NON_GOAL_ID = re.compile(r"^EF4-NG(\d{2})$")
WORK_PACKAGE_ID = re.compile(r"^[A-Z]\d{2}$")

# Total canonical invariants declared by MASTER_SPEC Part II.
EXPECTED_INVARIANT_COUNT = 64


class SchemaError(AssertionError):
    """Fail-closed invariant-schema violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def read_bytes(relative: str) -> bytes:
    path = ROOT / relative
    require(path.is_file(), f"required file missing: {relative}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {relative}")
    return data


def read_text(relative: str) -> str:
    text = read_bytes(relative).decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {relative}")
    return text


def load_yaml(relative: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(read_bytes(relative).decode("utf-8", errors="strict"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via require below
        raise SchemaError(f"{relative}: YAML is not well-formed: {exc}") from exc
    require(isinstance(document, dict), f"{relative}: top-level document must be a mapping")
    return document


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- #
# statement extraction from the prose documents
# --------------------------------------------------------------------------- #
def markdown_invariant_statements(relative: str) -> dict[str, str]:
    """Map ``EF4-Ixx`` -> normalized statement from a markdown doc.

    A statement is the first non-empty line after an ``EF4-Ixx — Title`` heading.
    """
    statements: dict[str, str] = {}
    lines = read_text(relative).splitlines()
    heading = re.compile(r"^#{2,3}\s+(EF4-I\d{2})\s+[—-]\s+.+$")
    for index, line in enumerate(lines):
        match = heading.match(line.strip())
        if not match:
            continue
        invariant_id = match.group(1)
        for follow in lines[index + 1:]:
            if follow.strip():
                statements[invariant_id] = norm(follow)
                break
    return statements


def build_evidence() -> dict[str, Any]:
    document = load_yaml(INVARIANTS_YAML)

    # --- top-level shape ---------------------------------------------------- #
    for key in ("version", "architecture_name", "validation_contract", "non_goals", "invariants"):
        require(key in document, f"{INVARIANTS_YAML}: missing top-level key {key!r}")

    contract = document["validation_contract"]
    require(isinstance(contract, dict), f"{INVARIANTS_YAML}: validation_contract must be a mapping")
    require(
        contract.get("atomic_unit") == "invariant_id",
        f"{INVARIANTS_YAML}: atomic_unit must be 'invariant_id' (atomicity anchor)",
    )
    require(
        isinstance(contract.get("atomicity_rule"), str) and contract["atomicity_rule"].strip(),
        f"{INVARIANTS_YAML}: atomicity_rule statement missing (atomicity is undeclared)",
    )
    require(
        isinstance(contract.get("verification_registry"), str)
        and contract["verification_registry"].strip(),
        f"{INVARIANTS_YAML}: verification_registry missing (testability is undeclared)",
    )
    declared_bindings = contract.get("required_bindings")
    require(
        isinstance(declared_bindings, list) and set(REQUIRED_BINDINGS) <= set(declared_bindings),
        f"{INVARIANTS_YAML}: required_bindings must declare at least {list(REQUIRED_BINDINGS)}",
    )
    pass_conditions = contract.get("pass_conditions")
    require(
        isinstance(pass_conditions, list) and len(pass_conditions) >= 1,
        f"{INVARIANTS_YAML}: pass_conditions must be a non-empty list (testability rules)",
    )
    require(
        any("runtime effectiveness" in norm(str(item)).lower()
            or "never proves runtime" in norm(str(item)).lower()
            for item in pass_conditions),
        f"{INVARIANTS_YAML}: pass_conditions must state that traceability alone never "
        f"proves runtime effectiveness (maturity honesty)",
    )

    # --- invariants: atomic, unique, contiguous, fully bound ---------------- #
    invariants = document["invariants"]
    require(isinstance(invariants, list) and invariants, f"{INVARIANTS_YAML}: invariants must be a non-empty list")

    seen_ids: list[str] = []
    numbers: list[int] = []
    for entry in invariants:
        require(isinstance(entry, dict), f"{INVARIANTS_YAML}: each invariant must be a mapping")
        invariant_id = entry.get("id")
        require(isinstance(invariant_id, str), f"{INVARIANTS_YAML}: invariant id must be a string")
        match = INVARIANT_ID.match(invariant_id)
        require(match is not None, f"{INVARIANTS_YAML}: malformed invariant id {invariant_id!r}")
        require(invariant_id not in seen_ids, f"{INVARIANTS_YAML}: duplicate invariant id {invariant_id!r}")
        seen_ids.append(invariant_id)
        numbers.append(int(match.group(1)))

        for binding in REQUIRED_BINDINGS:
            require(
                binding in entry,
                f"{INVARIANTS_YAML}: {invariant_id} missing required binding {binding!r}",
            )
        require(
            isinstance(entry["category"], str) and entry["category"].strip(),
            f"{INVARIANTS_YAML}: {invariant_id} category must be a non-empty string",
        )
        require(
            isinstance(entry["statement"], str) and entry["statement"].strip(),
            f"{INVARIANTS_YAML}: {invariant_id} statement must be a non-empty string",
        )
        for listy in ("evidence_artifacts", "work_packages"):
            value = entry[listy]
            require(
                isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value),
                f"{INVARIANTS_YAML}: {invariant_id} {listy} must be a non-empty list of strings",
            )
        for wp in entry["work_packages"]:
            require(
                WORK_PACKAGE_ID.match(wp) is not None,
                f"{INVARIANTS_YAML}: {invariant_id} references malformed work package id {wp!r}",
            )

    require(
        numbers == list(range(1, EXPECTED_INVARIANT_COUNT + 1)),
        f"{INVARIANTS_YAML}: invariant numbers must be contiguous EF4-I01..EF4-I"
        f"{EXPECTED_INVARIANT_COUNT:02d}; got {numbers}",
    )

    # --- non-goals: well-formed and each guard resolves --------------------- #
    non_goals = document["non_goals"]
    require(isinstance(non_goals, list) and non_goals, f"{INVARIANTS_YAML}: non_goals must be a non-empty list")
    ng_ids: list[str] = []
    ng_numbers: list[int] = []
    ng_statements: list[str] = []
    for entry in non_goals:
        require(isinstance(entry, dict), f"{INVARIANTS_YAML}: each non_goal must be a mapping")
        ng_id = entry.get("id")
        match = NON_GOAL_ID.match(ng_id) if isinstance(ng_id, str) else None
        require(match is not None, f"{INVARIANTS_YAML}: malformed non_goal id {ng_id!r}")
        require(ng_id not in ng_ids, f"{INVARIANTS_YAML}: duplicate non_goal id {ng_id!r}")
        ng_ids.append(ng_id)
        ng_numbers.append(int(match.group(1)))
        require(
            isinstance(entry.get("statement"), str) and entry["statement"].strip(),
            f"{INVARIANTS_YAML}: {ng_id} statement must be a non-empty string",
        )
        ng_statements.append(norm(entry["statement"]))
        guards = entry.get("guards")
        require(
            isinstance(guards, list) and guards,
            f"{INVARIANTS_YAML}: {ng_id} guards must be a non-empty list (a non-goal must be enforced)",
        )
        for guard in guards:
            require(
                guard in seen_ids,
                f"{INVARIANTS_YAML}: {ng_id} guard {guard!r} does not resolve to a declared invariant",
            )
    require(
        ng_numbers == list(range(1, len(non_goals) + 1)),
        f"{INVARIANTS_YAML}: non_goal numbers must be contiguous EF4-NG01..; got {ng_numbers}",
    )

    # non-goals must cover overclaim and provider lock-in (A02 exit criterion).
    joined_ng = " ".join(ng_statements).lower()
    require(
        "production" in joined_ng,
        f"{INVARIANTS_YAML}: non_goals do not disclaim production performance (overclaim guard)",
    )
    require(
        "shinkaevolve" in joined_ng or "search backend" in joined_ng,
        f"{INVARIANTS_YAML}: non_goals do not disclaim a required search backend (provider lock-in guard)",
    )

    # --- statement fidelity vs the two prose authorities -------------------- #
    yaml_statements = {entry["id"]: norm(entry["statement"]) for entry in invariants}
    spec_statements = markdown_invariant_statements(MASTER_SPEC)
    constitution_statements = markdown_invariant_statements(CONSTITUTION_DOC)

    mismatches: list[dict[str, str]] = []
    for invariant_id, statement in yaml_statements.items():
        for doc_name, doc_map in ((MASTER_SPEC, spec_statements), (CONSTITUTION_DOC, constitution_statements)):
            require(
                invariant_id in doc_map,
                f"{doc_name}: invariant {invariant_id} has no matching heading/statement",
            )
            if doc_map[invariant_id] != statement:
                mismatches.append(
                    {"id": invariant_id, "doc": doc_name, "doc_statement": doc_map[invariant_id], "yaml_statement": statement}
                )
    require(not mismatches, f"invariant statement mismatch between yaml and authority docs: {mismatches}")

    return {
        "schema_version": 1,
        "work_package_id": "A02",
        "attempt_id": "A02-0001",
        "check": "invariant_schema_check",
        "status": "PASS",
        "exit_criterion": "v4 invariants are atomic and testable",
        "source_file": INVARIANTS_YAML,
        "atomic_unit": contract["atomic_unit"],
        "required_bindings": list(REQUIRED_BINDINGS),
        "invariant_count": len(seen_ids),
        "invariant_ids_contiguous": True,
        "invariant_ids_unique": True,
        "all_required_bindings_present": True,
        "non_goal_count": len(ng_ids),
        "non_goals_guarded": True,
        "non_goals_cover_overclaim_and_lock_in": True,
        "statements_match_master_spec": True,
        "statements_match_product_constitution": True,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_invariants_yaml_is_well_formed_and_conformant() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert evidence["invariant_count"] == EXPECTED_INVARIANT_COUNT
    assert evidence["invariant_ids_contiguous"] is True
    assert evidence["invariant_ids_unique"] is True
    assert evidence["all_required_bindings_present"] is True


def test_non_goals_are_guarded_and_cover_overclaim_and_lock_in() -> None:
    evidence = build_evidence()
    assert evidence["non_goals_guarded"] is True
    assert evidence["non_goals_cover_overclaim_and_lock_in"] is True


def test_invariant_statements_match_authority_docs() -> None:
    evidence = build_evidence()
    assert evidence["statements_match_master_spec"] is True
    assert evidence["statements_match_product_constitution"] is True


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A02 invariant_schema_check")
    parser.add_argument("--output", type=Path, help="Write deterministic JSON evidence to this path")
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except SchemaError as exc:
        print(f"A02_INVARIANT_SCHEMA_CHECK_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"A02_INVARIANT_SCHEMA_CHECK_PASS: wrote {output.relative_to(ROOT.resolve()).as_posix()}")
    else:
        sys.stdout.write(rendered)
        print("A02_INVARIANT_SCHEMA_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
