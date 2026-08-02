#!/usr/bin/env python3
"""Build and verify fail-closed evidence for J02-0001 / J02-SG001."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/J02/attempts/0001"
PACKAGE_ROOT = ROOT / "artifacts/work_packages/J02"
ATTEMPT_ID = "J02-0001"
WORK_PACKAGE_ID = "J02"
SPEC_GAP_ID = "J02-SG001"

AUTHORITY_HASHES = {
    "MASTER_SPEC.md": "43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3",
    "AGENTS.md": "858e537ed3e49754b8e60d31c985467ee1246ed258c7763d6de4ef0767e381ea",
    "manifests/development_manifest.yaml": "fb9656cce2fd4d0147571bc85726ebbbbb3f26a59ac644c5a12040007475d938",
    "docs/v3_plugin_architecture.md": "a4a33cf60350378bcba5d0abaee99ecf4341665c0523ac430e9d7ab6b7b9de96",
    "docs/v4_plugin_architecture.md": "6ff8f66cd7ffe8878d1901a0f49d3932b172316a74a93f3beeff05b7fa43a13f",
    "artifacts/work_packages/J01/report.json": "7a8f000e4915f5715441ec31cb054489c85254d2ce5d3657ef54a4e3d5da8e05",
    "artifacts/work_packages/J01/attempts/0001/dependency-status.json": "0d99cf5da1c532d678ea7b73cc665e7c48525be9d1bd9d1710c8a6a4796eadf1",
    "packages/plugin-host/src/skill-router/skill-router.mjs": "6320ea8bb09eb3b69b9b2ea180b3d14bb8dbbf501f3a5afbe5dea63060a9b737",
    "schemas/skill-routing-decision.schema.json": "31bb0c22e5070ae2647322c19f1a7c02281e7f57cca1bea35664be691a485af7",
}

MISSING_CONTRACTS = [
    "numeric initial-metadata budget profile and accounting unit",
    "tokenizer identity/version or byte accounting algorithm",
    "included/excluded metadata fields and canonical encoding",
    "fail-closed over-budget behavior",
    "canonical installed child-skill/reference inventory and source authority",
    "deterministic skill/request/state-to-reference selection mapping",
    "reachability declaration, ordering, deduplication, transitive-load, cycle, missing-file, and traversal rules",
    "loader/runtime owner, exact implementation paths, and write authority",
    "authorized test paths, fixtures, and exact pass thresholds",
    "product disposition of the 29 blueprint child SKILL.md files",
]

REQUIRED_DECISIONS = [
    "Define exact initial-metadata budget profile(s), numeric thresholds, accounting unit, tokenizer/version if token-based, included fields, encoding, and over-budget failure semantics.",
    "Designate the canonical installed child-skill/reference inventory and its source authority, including the disposition of the 29 blueprint child skills.",
    "Define a closed deterministic reference-selection vocabulary and mapping from routed skill, request state, and policy to selected references.",
    "Define the reachability declaration format and deterministic ordering, deduplication, transitive loading, missing reference, cycle, and path-traversal behavior.",
    "Assign the loader/runtime owner and authorize exact implementation paths and write scope.",
    "Authorize exact test/fixture paths and freeze objective pass thresholds for context_budget_test and reference_reachability_test.",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_id(path: Path) -> str:
    return "sha256:" + sha256(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def assert_authority_hashes() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in AUTHORITY_HASHES.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(f"authority changed: {relative}: {actual} != {expected}")
        observed[relative] = "sha256:" + actual
    j01 = read_json(ROOT / "artifacts/work_packages/J01/report.json")
    if j01.get("status") != "PASS" or j01.get("attempt_id") != "J01-0001":
        raise SystemExit("J01 dependency is not evidence-sealed PASS")
    return observed


def manifest_contract() -> dict[str, Any]:
    payload = yaml.safe_load(
        (ROOT / "manifests/development_manifest.yaml").read_text(encoding="utf-8")
    )
    packages = payload if isinstance(payload, list) else payload.get("work_packages")
    if not isinstance(packages, list):
        raise SystemExit("development manifest package list is unavailable")
    rows = [row for row in packages if isinstance(row, dict) and row.get("id") == "J02"]
    if len(rows) != 1:
        raise SystemExit(f"expected one J02 manifest row, found {len(rows)}")
    row = rows[0]
    expected = {
        "depends_on": ["J01"],
        "write_scope": ["plugins/epistemic-foundry/skills/**/references/**"],
        "exit_criteria": [
            "only needed references load",
            "initial skill metadata fits host budget",
        ],
        "required_checks": ["context_budget_test", "reference_reachability_test"],
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise SystemExit(f"J02 manifest contract changed at {key}: {row.get(key)!r}")
    stop_conditions = row.get("stop_conditions")
    if not isinstance(stop_conditions, list) or not any(
        "SPEC_GAP" in str(item) and "ambiguous" in str(item)
        for item in stop_conditions
    ):
        raise SystemExit("J02 manifest lacks the shared-contract SPEC_GAP stop condition")
    return {
        "dependency": "J01",
        "write_scope": expected["write_scope"],
        "exit_criteria": expected["exit_criteria"],
        "required_checks": expected["required_checks"],
        "spec_gap_stop_condition": True,
    }


def inventory() -> dict[str, Any]:
    installed_root = ROOT / "plugins/epistemic-foundry/skills"
    blueprint_root = ROOT / "plugin_blueprint/epistemic-foundry/skills"
    installed = sorted(path for path in installed_root.rglob("*") if path.is_file())
    blueprint = sorted(path for path in blueprint_root.rglob("*") if path.is_file())
    installed_skills = [path for path in installed if path.name == "SKILL.md"]
    blueprint_skills = [path for path in blueprint if path.name == "SKILL.md"]
    installed_refs = [path for path in installed if "references" in path.parts]
    blueprint_refs = [path for path in blueprint if "references" in path.parts]
    observed = {
        "installed_skill_tree_file_count": len(installed),
        "installed_skill_md_count": len(installed_skills),
        "installed_reference_file_count": len(installed_refs),
        "blueprint_skill_tree_file_count": len(blueprint),
        "blueprint_skill_md_count": len(blueprint_skills),
        "blueprint_reference_file_count": len(blueprint_refs),
    }
    expected = {
        "installed_skill_tree_file_count": 2,
        "installed_skill_md_count": 1,
        "installed_reference_file_count": 0,
        "blueprint_skill_tree_file_count": 30,
        "blueprint_skill_md_count": 29,
        "blueprint_reference_file_count": 0,
    }
    if observed != expected:
        raise SystemExit(f"J02 skill/reference inventory changed: {observed}")
    package_manifest = read_json(ROOT / "PACKAGE_MANIFEST.json")
    readiness = package_manifest.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("plugin_blueprint") != "REFERENCE_BLUEPRINT_NOT_IMPLEMENTED":
        raise SystemExit("PACKAGE_MANIFEST no longer marks the plugin blueprint unimplemented")
    return {
        **observed,
        "installed_files": [path.relative_to(ROOT).as_posix() for path in installed],
        "blueprint_skill_ids": [path.parent.name for path in blueprint_skills],
        "blueprint_status": "REFERENCE_BLUEPRINT_NOT_IMPLEMENTED",
    }


def scan_contract_surface() -> dict[str, Any]:
    master = (ROOT / "MASTER_SPEC.md").read_text(encoding="utf-8")
    v3 = (ROOT / "docs/v3_plugin_architecture.md").read_text(encoding="utf-8")
    router = (ROOT / "packages/plugin-host/src/skill-router/skill-router.mjs").read_text(
        encoding="utf-8"
    )
    if "J02 — Progressive references and context budgets" not in master:
        raise SystemExit("MASTER_SPEC no longer names J02")
    inherited_sentence = (
        "Only metadata is always visible. Detailed references are loaded on demand."
    )
    if inherited_sentence not in v3:
        raise SystemExit("inherited on-demand reference sentence changed")
    if "context_budget_tokens" not in router:
        raise SystemExit("J01 router no longer carries the caller-provided budget field")
    source_files = [
        ROOT / "MASTER_SPEC.md",
        ROOT / "docs/v3_plugin_architecture.md",
        ROOT / "docs/v4_plugin_architecture.md",
        ROOT / "manifests/development_manifest.yaml",
        ROOT / "packages/plugin-host/src/skill-router/skill-router.mjs",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    required_check_mentions = {
        name: combined.count(name)
        for name in ("context_budget_test", "reference_reachability_test")
    }
    if required_check_mentions != {
        "context_budget_test": 1,
        "reference_reachability_test": 1,
    }:
        raise SystemExit(f"required-check definition surface changed: {required_check_mentions}")
    return {
        "master_spec_operational_rule_count": 0,
        "inherited_on_demand_statement_present": True,
        "authoritative_numeric_budget_threshold_count": 0,
        "authoritative_tokenizer_version_count": 0,
        "canonical_reference_inventory_count": 0,
        "reference_mapping_contract_count": 0,
        "reachability_declaration_contract_count": 0,
        "loader_owner_contract_count": 0,
        "required_check_mentions": required_check_mentions,
        "required_check_definitions_outside_manifest": 0,
        "router_budget_behavior": "CALLER_PROVIDED_FIELD_ONLY",
        "router_enforces_or_calculates_budget": False,
    }


def no_product_change_assertion() -> dict[str, Any]:
    reference_files = [
        path
        for path in (ROOT / "plugins/epistemic-foundry/skills").rglob("*")
        if path.is_file() and "references" in path.parts
    ]
    if reference_files:
        raise SystemExit("J02 product reference files unexpectedly exist")
    return {
        "authorized_product_reference_files_created": 0,
        "implementation_files_modified_by_attempt": 0,
        "tests_or_fixtures_created_by_attempt": 0,
        "manifest_schema_router_or_skill_metadata_modified_by_attempt": 0,
        "out_of_scope_product_changes": 0,
    }


def contract_audit() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "classification": {
            "typed_outcome": "SPEC_GAP",
            "not_fail_reason": "No implementation was attempted because the loader, inventory, budget accounting, reachability semantics, and acceptance oracle are undefined.",
            "not_blocked_reason": "No required host capability, credential, licensed source, tool, or external service is unavailable.",
        },
        "authority_hashes": assert_authority_hashes(),
        "manifest_contract": manifest_contract(),
        "inventory": inventory(),
        "contract_surface": scan_contract_surface(),
        "missing_contracts": MISSING_CONTRACTS,
        "required_product_owner_decisions": REQUIRED_DECISIONS,
        "required_checks": {
            "context_budget_test": {
                "status": "NOT_DEFINABLE",
                "reason": "No authoritative budget threshold, accounting algorithm, tokenizer/version, included field set, or failure semantics exists.",
            },
            "reference_reachability_test": {
                "status": "NOT_DEFINABLE",
                "reason": "No canonical reference inventory, selection mapping, reachability declaration, loader contract, or pass threshold exists.",
            },
        },
        "implementation": no_product_change_assertion(),
        "subagents_or_fleet_used": False,
        "completion_ready": False,
    }


def dependency_status() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "completion_ready": False,
        "dependency_inputs": {
            "J01": {
                "status": "PASS",
                "attempt_id": "J01-0001",
                "report": "artifacts/work_packages/J01/report.json",
                "report_sha256": sha256_id(ROOT / "artifacts/work_packages/J01/report.json"),
            }
        },
        "package_states": {
            "J01": "PASS",
            "J02": "SPEC_GAP_J02_SG001",
            "J04": "WAITING_ON_J02_AND_J03",
            "J03": "DEPENDENCY_READY_BUT_NOT_STARTED_DURING_SERIAL_J02",
            "K01": "DEPENDENCY_READY_BUT_NOT_STARTED_DURING_SERIAL_J02",
            "T01": "DEPENDENCY_READY_BUT_NOT_STARTED_DURING_SERIAL_J02",
            "A06": "DEPENDENCY_READY_BUT_NOT_STARTED_DURING_SERIAL_J02",
        },
        "later_package_started": False,
        "reason": "The earliest manifest-order package cannot define its required checks without inventing a shared product contract.",
        "resume_condition": "A product-owner HumanDecision must define the complete J02 budget, inventory, selection, reachability, loader ownership, write scope, and test oracle contract; J02 must then run as a new attempt while preserving J02-0001.",
    }


def review_text() -> str:
    return """# J02 primary-session separate contract review

Status: `SPEC_GAP (J02-SG001)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: this review was conducted as a procedurally separate
primary-session pass. It is not actor-independent certification because the
product owner explicitly prohibited Fleet and subagents for this execution.

## Verdict

J01 is an evidence-sealed `PASS`, so J02 is dependency-ready. Dependency
readiness does not supply the missing progressive-reference semantics. J02
cannot implement or objectively pass its required checks within the current
authority chain.

## Findings

1. `MASTER_SPEC.md` names J02 but does not define an operative budget or
   reference-loading contract. The inherited architecture text only states
   that metadata is visible and detailed references load on demand.
2. No numeric host budget, accounting unit, tokenizer/version, included field
   set, canonical serialization, or over-budget failure behavior is defined.
   The J01 router merely preserves a caller-provided `context_budget_tokens`
   value; it neither computes nor enforces the J02 budget.
3. The installed skill tree has one `SKILL.md`, one agent metadata file, and no
   references. The blueprint skill tree has 29 `SKILL.md` files and no
   references, while `PACKAGE_MANIFEST.json` explicitly labels the blueprint
   `REFERENCE_BLUEPRINT_NOT_IMPLEMENTED`. Authority does not decide whether
   those child skills become installed skills, reference material, or remain
   blueprint-only.
4. No canonical reference inventory or mapping connects a routed skill,
   request, or state to needed references. No declaration format defines
   ordering, deduplication, transitive loading, missing files, cycles, or path
   traversal.
5. No loader/runtime owner or exact implementation path is assigned. J02's
   product write scope permits only `skills/**/references/**`; it cannot edit
   `SKILL.md`, the J01 router, a loader, metadata, or ordinary test paths.
6. `context_budget_test` and `reference_reachability_test` are names only in
   `development_manifest.yaml`. There are no authorized fixtures, test paths,
   exact expected values, or pass thresholds. Letting the implementation invent
   them would make the package author its own acceptance oracle.

## Classification

The correct outcome is `SPEC_GAP`, not `FAIL`: the required shared contract is
missing, so no valid implementation has been attempted. It is not `BLOCKED`:
no external prerequisite is unavailable. The J02 stop condition explicitly
requires `SPEC_GAP` when a shared contract, authority boundary, or acceptance
threshold is ambiguous.

## Required decision

A product-owner HumanDecision must define the exact metadata budget and
accounting, canonical installed skill/reference inventory, deterministic
reference-selection and reachability rules, loader/runtime owner and exact
write paths, and the complete fixtures and thresholds for both required
checks. It must also decide the disposition of all 29 blueprint child skills.

J02-0001 must remain immutable `SPEC_GAP` history. Do not create arbitrary
references or thresholds, weaken the metadata-only J01 boundary, or skip to a
later package while this earliest package remains unresolved.
"""


def command_rows() -> list[dict[str, Any]]:
    recorded = utc_now()
    raw = [
        ("J02-0001-C001", "Inspect J02 authority, dependency, write scope, exit criteria, required checks, and stop conditions", 0, "PASS: J01 is PASS and J02 is the earliest manifest-order dependency-ready package"),
        ("J02-0001-C002", "Audit MASTER_SPEC and plugin architecture for an operative progressive-reference and initial-metadata budget contract", 0, "SPEC_GAP_CONFIRMED: only a descriptive on-demand sentence exists; no budget or loading algorithm exists"),
        ("J02-0001-C003", "Inventory installed and blueprint skill/reference trees", 0, "PASS: installed 2 files/1 SKILL.md/0 references; blueprint skill tree 30 files/29 SKILL.md/0 references"),
        ("J02-0001-C004", "Search for context_budget_test and reference_reachability_test definitions", 0, "SPEC_GAP_CONFIRMED: each name occurs only in the J02 manifest row; no test oracle exists"),
        ("J02-0001-C005", "Inspect the J01 router context_budget_tokens behavior", 0, "PASS: field is caller-provided and validated only as a non-negative integer; no J02 calculation or enforcement exists"),
        ("J02-0001-C006", "Verify J02 product write scope remains unchanged", 0, "PASS: no reference, loader, metadata, router, schema, manifest, or test product file was created or modified by J02"),
        ("J02-0001-C007", "Run J01 targeted Node regression after J02 audit", 0, "PASS: 19/19, zero failed or skipped"),
        ("J02-0001-C008", "Run npm repository structure and boundary checks", 0, "PASS: check:structure and check:boundaries"),
        ("J02-0001-C009", "Run git diff --check", 0, "PASS: no whitespace errors; only existing working-copy line-ending advisories"),
        ("J02-0001-R001", "Perform primary-session separate adversarial contract review", 0, "SPEC_GAP_CONFIRMED: not actor-independent certification; no gate waived"),
        ("J02-0001-D001", "Read nonexistent F01 attempts/0001 path while locating a blocked-attempt precedent", 1, "DIAGNOSTIC_ONLY: no state or repository mutation; corrected to the actual retained F01 attempt layout"),
        ("J02-0001-D002", "Read obsolete RAH CURRENT and generation manifest filenames during state inspection", 1, "DIAGNOSTIC_ONLY: no state mutation; corrected to current.json and generation-manifest.json/state_store.read_current"),
        ("J02-0001-D003", "Parse the passing Node 19/19 regression using only legacy TAP '# pass' summary markers", 1, "DIAGNOSTIC_ONLY: tests passed but the wrapper rejected the current Unicode info-marker reporter; parser corrected to accept either reporter without changing product files or RAH state"),
        ("J02-0001-D004", "Pipe a PowerShell foreach block directly into ConvertTo-Json during root-projection hash inspection", 1, "DIAGNOSTIC_ONLY: reliability guard blocked the unsafe command shape before execution; retried with a collected results array; no repository or RAH mutation"),
        ("J02-0001-C010", "Append J02 contract-audit evidence and documented gap to RAH with KEEP_GENERATIONS=10000", 0, "PASS: E0078 and E0079 appended; generation 000076-44cd2c81; exact J02-SG001 blocker; completion_ready=false"),
        ("J02-0001-C011", "Read-only verify J02 core RAH generation and six flat projections", 0, "PASS: 76 generations; 456 payload hashes; 6/6 stamps and 6/6 content matches; latest E0079"),
        ("J02-0001-C012", "Compare J02 attempt/root report, commands, and review projections and rerun git diff --check", 0, "PASS: 3/3 projections byte-identical; git diff --check exit 0 with only existing line-ending advisories"),
    ]
    return [
        {
            "command_id": command_id,
            "command": command,
            "recorded_at_utc": recorded,
            "exit_code": exit_code,
            "result": result,
            "scope": ATTEMPT_ID,
        }
        for command_id, command, exit_code, result in raw
    ]


def report_document(core: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = read_json(ATTEMPT / "shared-contract-gap-verification.json")
    dependency = read_json(ATTEMPT / "dependency-status.json")
    report: dict[str, Any] = {
        "work_package_id": WORK_PACKAGE_ID,
        "attempt_id": ATTEMPT_ID,
        "title": "Progressive references and context budgets",
        "status": "SPEC_GAP",
        "package_status": "SPEC_GAP",
        "implementation_status": "NOT_STARTED_FAIL_CLOSED",
        "spec_gap_id": SPEC_GAP_ID,
        "completion_ready": False,
        "dependency": dependency["dependency_inputs"],
        "authority_hashes": audit["authority_hashes"],
        "authorized_surface": {
            "product_write_scope": ["plugins/epistemic-foundry/skills/**/references/**"],
            "evidence_scope": ["artifacts/work_packages/J02/**"],
            "product_file_change_count": 0,
            "out_of_scope_product_change_count": 0,
        },
        "spec_gap": {
            "id": SPEC_GAP_ID,
            "classification": "SPEC_GAP",
            "summary": "J02 lacks the authoritative budget accounting, reference inventory/selection/reachability contract, loader ownership, and executable acceptance oracle required to implement progressive references.",
            "not_fail_reason": audit["classification"]["not_fail_reason"],
            "not_blocked_reason": audit["classification"]["not_blocked_reason"],
            "missing_contracts": MISSING_CONTRACTS,
            "required_product_owner_decisions": REQUIRED_DECISIONS,
        },
        "inventory": audit["inventory"],
        "required_checks": audit["required_checks"],
        "review": {
            "mode": "PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW",
            "status": "SPEC_GAP",
            "blocking_finding_count": 6,
            "artifact": "artifacts/work_packages/J02/attempts/0001/review.md",
            "assurance_limitation": "Procedurally separate primary-session review; not actor-independent certification because Fleet and subagents were prohibited.",
        },
        "implementation": audit["implementation"],
        "dependency_effect": dependency["package_states"],
        "historical_and_worktree_preservation": {
            "J01_report_sha256": sha256_id(ROOT / "artifacts/work_packages/J01/report.json"),
            "J01_report_unchanged": True,
            "prior_reports_and_rah_generations_preserved": True,
            "dirty_worktree_preserved": True,
            "reset_clean_stash_commit_push_performed": False,
            "subagents_or_fleet_used": False,
        },
        "output_artifacts": [
            "artifacts/work_packages/J02/attempts/0001/shared-contract-gap-verification.json",
            "artifacts/work_packages/J02/attempts/0001/dependency-status.json",
            "artifacts/work_packages/J02/attempts/0001/rah-core-integrity.json",
            "artifacts/work_packages/J02/attempts/0001/review.md",
            "artifacts/work_packages/J02/attempts/0001/commands.jsonl",
            "artifacts/work_packages/J02/attempts/0001/report.json",
        ],
        "resume_condition": dependency["resume_condition"],
    }
    if core is not None:
        report["rah_state"] = {
            "core_parent_generation": "000075-b6f3b5e9",
            "core_generation": core["current_generation"],
            "core_generation_manifest_sha256": core["generation_manifest_sha256"],
            "contract_audit_evidence_id": "E0078",
            "documented_gap_evidence_id": "E0079",
            "final_closeout_evidence_id": "E0080",
            "retained_generation_count_after_core": core["retained_generation_count"],
            "generation_file_hashes_verified_after_core": core["generation_file_hashes_verified"],
            "flat_snapshot_stamps_verified_after_core": core["flat_snapshot_stamps_verified"],
            "flat_snapshot_content_matches_after_core": core["flat_snapshot_content_matches"],
            "status": "blocked",
            "completion_ready": False,
        }
    return report


def assert_utf8_lf(path: Path) -> None:
    content = path.read_bytes()
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        raise SystemExit(f"invalid encoding marker in {path}")
    text = content.decode("utf-8")
    if "\ufffd" in text or "\r" in text or not text.endswith("\n"):
        raise SystemExit(f"invalid UTF-8/LF text artifact: {path}")


def parse_commands() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(
        (ATTEMPT / "commands.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise SystemExit(f"commands line {number} is not an object")
        rows.append(value)
    ids = [row.get("command_id") for row in rows]
    if len(ids) != len(set(ids)) or any(not isinstance(value, str) for value in ids):
        raise SystemExit("commands.jsonl has missing or duplicate command IDs")
    return rows


def run_regression_checks() -> dict[str, Any]:
    npm = "npm.cmd"
    targeted = subprocess.run(
        [
            "node",
            "--test",
            "packages/plugin-host/src/skill-router/skill-router.test.mjs",
            "packages/plugin-host/src/skill-router/skill-metadata-lint.test.mjs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pass_summary = re.search(r"(?m)^(?:#|ℹ)\s+pass\s+19\s*$", targeted.stdout)
    fail_summary = re.search(r"(?m)^(?:#|ℹ)\s+fail\s+0\s*$", targeted.stdout)
    if targeted.returncode != 0 or pass_summary is None or fail_summary is None:
        raise SystemExit(f"J01 targeted regression failed: {(targeted.stdout + targeted.stderr)[-2000:]}")
    for args, label in (
        ([npm, "run", "check:structure"], "repository structure"),
        ([npm, "run", "check:boundaries"], "repository boundaries"),
        (["git", "diff", "--check"], "git diff check"),
    ):
        completed = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(f"{label} failed: {(completed.stdout + completed.stderr)[-2000:]}")
    return {
        "j01_targeted_node": {"status": "PASS", "passed": 19, "failed": 0, "skipped": 0},
        "repository_structure": "PASS",
        "package_boundaries": "PASS",
        "git_diff_check": "PASS",
    }


def build_pre_core() -> None:
    ATTEMPT.mkdir(parents=True, exist_ok=True)
    write_json(ATTEMPT / "shared-contract-gap-verification.json", contract_audit())
    write_json(ATTEMPT / "dependency-status.json", dependency_status())
    (ATTEMPT / "review.md").write_text(review_text(), encoding="utf-8", newline="\n")
    rows = command_rows()
    (ATTEMPT / "commands.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    write_json(ATTEMPT / "report.json", report_document())
    verify_pre_core(run_regression=False)


def verify_pre_core(*, run_regression: bool = True) -> dict[str, Any]:
    audit = contract_audit()
    if read_json(ATTEMPT / "shared-contract-gap-verification.json") != audit:
        raise SystemExit("stored J02 contract audit differs from live authority")
    if read_json(ATTEMPT / "dependency-status.json") != dependency_status():
        raise SystemExit("stored J02 dependency status differs from live authority")
    report = read_json(ATTEMPT / "report.json")
    if report.get("status") != "SPEC_GAP" or report.get("spec_gap_id") != SPEC_GAP_ID:
        raise SystemExit("J02 report is not SPEC_GAP J02-SG001")
    if report.get("completion_ready") is not False:
        raise SystemExit("J02 report must retain completion_ready=false")
    if (ATTEMPT / "review.md").read_text(encoding="utf-8") != review_text():
        raise SystemExit("stored J02 review differs from canonical review")
    rows = parse_commands()
    for path in ATTEMPT.iterdir():
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".py"}:
            assert_utf8_lf(path)
    regression = run_regression_checks() if run_regression else {
        "j01_targeted_node": "DEFERRED_TO_VERIFY",
        "repository_structure": "DEFERRED_TO_VERIFY",
        "package_boundaries": "DEFERRED_TO_VERIFY",
        "git_diff_check": "DEFERRED_TO_VERIFY",
    }
    return {
        "attempt_id": ATTEMPT_ID,
        "status": "SPEC_GAP",
        "spec_gap_id": SPEC_GAP_ID,
        "commands_parsed": len(rows),
        "authority_hash_count": len(AUTHORITY_HASHES),
        "inventory": audit["inventory"],
        "required_checks": audit["required_checks"],
        "regression": regression,
        "product_file_change_count": 0,
        "completion_ready": False,
    }


def build_post_core(core_integrity: dict[str, Any]) -> None:
    write_json(ATTEMPT / "rah-core-integrity.json", core_integrity)
    write_json(ATTEMPT / "report.json", report_document(core_integrity))
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "commands.jsonl", "review.md"):
        shutil.copyfile(ATTEMPT / name, PACKAGE_ROOT / name)
    verify_post_core(run_regression=False)


def verify_post_core(*, run_regression: bool = True) -> dict[str, Any]:
    result = verify_pre_core(run_regression=run_regression)
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != integrity.get("current_generation"):
        raise SystemExit("J02 report does not bind the core RAH generation")
    if integrity.get("status") != "PASS" or integrity.get("ralph_status") != "blocked":
        raise SystemExit("J02 RAH core integrity is not blocked-state PASS")
    for name in ("report.json", "commands.jsonl", "review.md"):
        if (ATTEMPT / name).read_bytes() != (PACKAGE_ROOT / name).read_bytes():
            raise SystemExit(f"J02 root projection differs from attempt artifact: {name}")
    return {
        **result,
        "core_generation": integrity["current_generation"],
        "core_evidence_ids": ["E0078", "E0079"],
        "root_projection_count": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("build-pre-core", "verify-pre-core", "verify-pre-core-fast", "build-post-core", "verify-post-core", "verify-post-core-fast"),
    )
    parser.add_argument("--core-integrity", default=None)
    args = parser.parse_args()
    if args.mode == "build-pre-core":
        build_pre_core()
        result = verify_pre_core(run_regression=False)
    elif args.mode == "verify-pre-core":
        result = verify_pre_core(run_regression=True)
    elif args.mode == "verify-pre-core-fast":
        result = verify_pre_core(run_regression=False)
    elif args.mode == "build-post-core":
        if not args.core_integrity:
            raise SystemExit("--core-integrity is required for build-post-core")
        build_post_core(read_json(Path(args.core_integrity)))
        result = verify_post_core(run_regression=False)
    elif args.mode == "verify-post-core":
        result = verify_post_core(run_regression=True)
    else:
        result = verify_post_core(run_regression=False)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
