"""Z01 install/compatibility/uninstall matrix harness.

This module is the single deterministic engine behind the two Z01 required
checks -- ``install_matrix_test`` and ``uninstall_data_test``.  It reads the
declaring source ``manifests/compatibility_matrix.yaml`` and evaluates the
declared fresh-install, host/OS compatibility and uninstall lifecycle as pure
functions.  It never restates the host or platform lists (the matrix is the only
declaring source), spawns no host, and mutates nothing on disk.

Honesty boundary
----------------
These are DECLARED-matrix lifecycle proofs, not real multi-OS installs.  The one
real, single-host marketplace lifecycle is sealed as ``G04-0001``; this harness
COMPOSES that gate (see :func:`compose_g04_marketplace_lifecycle`) rather than
duplicating an installer, and every other host/OS cell is a declared-policy
proof over the in-repo payload.  Nothing here claims the v4 plugin is
executable, validated, or production-ready.

Determinism
-----------
The harness contains no clock or randomness.  Every record embeds a
caller-supplied ``generated_at`` timestamp and is hash-re-derivable through
:func:`record_sha256`: re-running any builder with the same matrix and timestamp
yields a byte-identical canonical record and hash.  Refusals are typed codes
whose human-readable reason is always longer than fifty characters.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "manifests" / "compatibility_matrix.yaml"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "epistemic-foundry"
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
G04_LIFECYCLE_TEST = (
    REPO_ROOT / "tests" / "install" / "local-marketplace" / "g04-lifecycle.test.mjs"
)

# Ground-truth Z01 sealed dependencies (package -> pinned attempt id) taken from
# the Z01 ``depends_on`` set in ``manifests/development_manifest.yaml``.  The
# matrix must declare exactly this provenance set; the harness refuses any
# citation that is not one of these sealed attempts.
EXPECTED_SEALED_DEPENDENCIES: dict[str, str] = {
    "G04": "G04-0001",
    "H04": "H04-0001",
    "L04": "L04-0001",
    "M04": "M04-0001",
    "P04": "P04-0001",
    "Q04": "Q04-0001",
    "S04": "S04-0005",
    "T04": "T04-0001",
    "U04": "U04-0001",
    "V04": "V04-0001",
    "W04": "W04-0001",
    "X04": "X04-0001",
    "Y04": "Y04-0001",
}

# Typed refusal codes -> reason builders.  Every reason is > 50 characters so a
# refused decision always carries an auditable, human-readable justification.
REFUSAL_REASONS: dict[str, str] = {
    "EF_Z01_ROW_UNCITED": (
        "host row cites no sealed dependency through establishing_evidence, so the "
        "fail-closed matrix refuses to treat any of its host/OS cells as installable"
    ),
    "EF_Z01_CITATION_NOT_SEALED": (
        "establishing citation is not one of the declared Z01 sealed dependencies, so "
        "its provenance chain is unverifiable and the citing host row is refused"
    ),
    "EF_Z01_CAP_UNCITED": (
        "capability has no sealed establishing citation on this host, so it can never "
        "reach SUPPORTED and a fresh install of the cell is refused fail-closed"
    ),
    "EF_Z01_STATUS_NOT_SUPPORTED": (
        "host/OS/capability cell status is not SUPPORTED, so a fresh install of that "
        "declared cell is refused fail-closed until verifying evidence is recorded"
    ),
    "EF_Z01_EVIDENCE_INCOMPLETE": (
        "cell claims SUPPORTED but is missing required install evidence items, so the "
        "over-claim is refused before any install of that host/OS cell can proceed"
    ),
    "EF_Z01_UNKNOWN_HOST": (
        "requested host is not declared in the compatibility matrix, so the install "
        "target cannot be resolved and the request is refused fail-closed"
    ),
    "EF_Z01_UNKNOWN_PLATFORM": (
        "requested platform is not a known platform in the compatibility matrix, so "
        "the install target cannot be resolved and the request is refused fail-closed"
    ),
    "EF_Z01_PLATFORM_NOT_OFFERED": (
        "requested platform is not offered by this host in the compatibility matrix, "
        "so the host/OS combination is unsupported and the request is refused"
    ),
    "EF_Z01_UNKNOWN_CAPABILITY": (
        "requested capability is not declared in the compatibility matrix, so the "
        "install decision has no cell to evaluate and the request is refused"
    ),
    "EF_Z01_UNINSTALL_RESIDUE": (
        "uninstall plan leaves declared removable state in place, which violates the "
        "zero-orphan-residue policy and fails the uninstall data-preservation gate"
    ),
    "EF_Z01_UNINSTALL_DELETES_USER_DATA": (
        "uninstall plan targets a declared user-data location, which the preserve "
        "user-data policy forbids, so the destructive plan is refused as a violation"
    ),
    "EF_Z01_UNINSTALL_UNDECLARED_TARGET": (
        "uninstall plan targets state that is not declared removable, so the plan is "
        "unverifiable against the lifecycle contract and is refused fail-closed"
    ),
}


def refusal(code: str) -> dict[str, str]:
    """Return a typed refusal object with a > 50 character reason."""

    reason = REFUSAL_REASONS[code]
    assert len(reason) > 50, f"refusal reason for {code} is too short"
    return {"code": code, "reason": reason}


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    assert isinstance(value, dict), f"{path} is not a mapping"
    return value


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict), f"{path} is not an object"
    return value


def load_matrix() -> dict:
    return load_yaml(MATRIX_PATH)


def load_plugin_manifest() -> dict:
    return load_json(PLUGIN_MANIFEST_PATH)


def record_sha256(record: object) -> str:
    """Canonical, hash-re-derivable digest of a harness record."""

    payload = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def payload_inventory() -> list[dict]:
    """Deterministic content-addressed inventory of the declared payload.

    This is the exact fresh-install layout that the sealed ``G04-0001`` real
    marketplace install produced byte-for-byte; recomputing it is stable because
    it hashes file bytes only and sorts by POSIX path.
    """

    entries = []
    for path in sorted(
        (p for p in PLUGIN_ROOT.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(PLUGIN_ROOT).as_posix(),
    ):
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(PLUGIN_ROOT).as_posix(),
                "byte_size": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    return entries


def compose_g04_marketplace_lifecycle(
    *, live: bool = False, node_executable: str | None = None
) -> dict:
    """Compose the sealed G04 lifecycle as Z01's marketplace-install proof.

    Z01 does not re-implement an installer.  In the default deterministic mode it
    returns the sealed-evidence citation Z01 relies on.  In ``live`` mode it
    delegates to the sealed G04 Node test module -- the one real, single-host
    marketplace lifecycle -- and reports its exit code.  Live mode is opt-in and
    is never used by the deterministic required-check path.
    """

    assert G04_LIFECYCLE_TEST.is_file(), "sealed G04 lifecycle test module missing"
    citation = {
        "mode": "sealed_evidence_citation",
        "attempt_id": EXPECTED_SEALED_DEPENDENCIES["G04"],
        "composed_module": G04_LIFECYCLE_TEST.relative_to(REPO_ROOT).as_posix(),
        "note": (
            "Z01 composes G04 rather than duplicating an installer; the real "
            "single-host marketplace lifecycle is sealed as G04-0001."
        ),
    }
    if not live:
        return citation
    node = node_executable or "node"
    completed = subprocess.run(
        [
            node,
            "--test",
            "--test-concurrency=1",
            G04_LIFECYCLE_TEST.relative_to(REPO_ROOT).as_posix(),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return {
        **citation,
        "mode": "live_delegation",
        "exit_code": completed.returncode,
        "delegated_status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def _citation_capabilities(matrix: dict, host: dict) -> dict[str, list[str]]:
    """Map each capability to the sealed attempts that cite it on this host."""

    coverage: dict[str, list[str]] = {cap: [] for cap in matrix["capabilities"]}
    for citation in host.get("establishing_evidence", []):
        for capability in citation.get("capabilities", []):
            if capability in coverage:
                coverage[capability].append(citation["attempt_id"])
    return {cap: sorted(set(ids)) for cap, ids in coverage.items()}


def row_citation_report(matrix: dict) -> dict:
    """Fail-closed provenance report: every host row must cite sealed evidence."""

    sealed_ids = {dep["attempt_id"] for dep in matrix["sealed_dependencies"]}
    hosts = []
    for host in matrix["hosts"]:
        citations = host.get("establishing_evidence", [])
        refusals = []
        if not citations:
            refusals.append({"host": host["host"], **refusal("EF_Z01_ROW_UNCITED")})
        for citation in citations:
            if citation["attempt_id"] not in sealed_ids:
                refusals.append(
                    {
                        "host": host["host"],
                        "attempt_id": citation["attempt_id"],
                        **refusal("EF_Z01_CITATION_NOT_SEALED"),
                    }
                )
        hosts.append(
            {
                "host": host["host"],
                "cited_attempts": sorted(
                    {citation["attempt_id"] for citation in citations}
                ),
                "capability_citations": _citation_capabilities(matrix, host),
                "refusals": refusals,
            }
        )
    return {"hosts": hosts}


def resolve_cell(matrix: dict, host_name: str, platform: str, capability: str) -> dict:
    """Pure fail-closed install decision for one host/OS/capability cell."""

    hosts = {host["host"]: host for host in matrix["hosts"]}
    if host_name not in hosts:
        return {"decision": "REFUSED", **refusal("EF_Z01_UNKNOWN_HOST")}
    host = hosts[host_name]
    if platform not in matrix["known_platforms"]:
        return {"decision": "REFUSED", **refusal("EF_Z01_UNKNOWN_PLATFORM")}
    if platform not in host["platforms"]:
        return {"decision": "REFUSED", **refusal("EF_Z01_PLATFORM_NOT_OFFERED")}
    if capability not in matrix["capabilities"]:
        return {"decision": "REFUSED", **refusal("EF_Z01_UNKNOWN_CAPABILITY")}
    citations = _citation_capabilities(matrix, host)[capability]
    if not citations:
        return {"decision": "REFUSED", **refusal("EF_Z01_CAP_UNCITED")}
    if host[capability] != "SUPPORTED":
        return {
            "decision": "REFUSED",
            "observed_status": host[capability],
            **refusal("EF_Z01_STATUS_NOT_SUPPORTED"),
        }
    missing = [
        item
        for item in matrix["required_evidence"]
        if item not in set(host.get("evidence", []))
    ]
    if missing:
        return {
            "decision": "REFUSED",
            "missing_evidence": sorted(missing),
            **refusal("EF_Z01_EVIDENCE_INCOMPLETE"),
        }
    return {"decision": "ALLOW"}


def build_install_matrix_report(matrix: dict, *, generated_at: str) -> dict:
    """Deterministic install/compatibility report over every declared cell."""

    plugin = matrix["plugin"]
    inventory = payload_inventory()
    declared_top = sorted(matrix["payload"]["expected_top_level"])
    actual_top = sorted(child.name for child in PLUGIN_ROOT.iterdir())
    cells = []
    allow_count = 0
    refuse_count = 0
    for host in matrix["hosts"]:
        for platform in host["platforms"]:
            for capability in matrix["capabilities"]:
                decision = resolve_cell(matrix, host["host"], platform, capability)
                if decision["decision"] == "ALLOW":
                    allow_count += 1
                else:
                    refuse_count += 1
                cells.append(
                    {
                        "host": host["host"],
                        "platform": platform,
                        "capability": capability,
                        **decision,
                    }
                )
    record = {
        "schema_version": "z01-install-matrix-report/v1",
        "work_package_id": "Z01",
        "generated_at": generated_at,
        "declaring_source": "manifests/compatibility_matrix.yaml",
        "matrix_status": matrix["status"],
        "plugin_identity_matches_manifest": (
            plugin["name"] == load_plugin_manifest()["name"] == "epistemic-foundry"
            and plugin["version"] == matrix["version"]
        ),
        "runtime_capabilities_declared": plugin["runtime_capabilities"],
        "payload_top_level_matches": declared_top == actual_top,
        "fresh_install_file_count": len(inventory),
        "fresh_install_inventory_sha256": record_sha256(inventory),
        "sealed_dependencies": sorted(
            dep["attempt_id"] for dep in matrix["sealed_dependencies"]
        ),
        "sealed_dependencies_match_expected": {
            dep["package"]: dep["attempt_id"] for dep in matrix["sealed_dependencies"]
        }
        == EXPECTED_SEALED_DEPENDENCIES,
        "row_citations": row_citation_report(matrix),
        "cell_count": len(cells),
        "allow_count": allow_count,
        "refuse_count": refuse_count,
        "cells": cells,
        "marketplace_install_composition": compose_g04_marketplace_lifecycle(),
        "honesty_note": (
            "Declared-matrix lifecycle proof; not a real multi-OS install. The one "
            "real single-host marketplace lifecycle is sealed as G04-0001."
        ),
    }
    record["record_sha256"] = record_sha256(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    return record


def uninstall_decision(
    removable: dict[str, str], removes: list[str], user_data: list[str]
) -> dict:
    """Pure fail-closed uninstall evaluation for one removal plan."""

    planned = list(removes)
    undeclared = sorted(set(planned) - set(removable))
    residue_ids = sorted(set(removable) - set(planned))
    planned_locations = {removable[i] for i in planned if i in removable}
    user_data_deleted = sorted(planned_locations & set(user_data))
    refusals = []
    if undeclared:
        refusals.append(
            {"targets": undeclared, **refusal("EF_Z01_UNINSTALL_UNDECLARED_TARGET")}
        )
    if residue_ids:
        refusals.append(
            {"residue_ids": residue_ids, **refusal("EF_Z01_UNINSTALL_RESIDUE")}
        )
    if user_data_deleted:
        refusals.append(
            {
                "user_data_deleted": user_data_deleted,
                **refusal("EF_Z01_UNINSTALL_DELETES_USER_DATA"),
            }
        )
    return {
        "residue_ids": residue_ids,
        "residue_count": len(residue_ids),
        "undeclared_targets": undeclared,
        "user_data_deleted": user_data_deleted,
        "refusals": refusals,
        "final_status": "PASS" if not refusals else "FAIL",
    }


def build_uninstall_report(matrix: dict, *, generated_at: str) -> dict:
    """Deterministic uninstall data-preservation report and negative proofs."""

    lifecycle = matrix["lifecycle"]
    removable = {
        entry["id"]: entry["location"] for entry in lifecycle["removable_state"]
    }
    removes = lifecycle["uninstall"]["removes"]
    user_data = lifecycle["user_data_locations"]

    complete = uninstall_decision(removable, removes, user_data)
    partial = uninstall_decision(removable, list(removes)[:-1], user_data)
    rogue = uninstall_decision({"rogue": user_data[0]}, ["rogue"], user_data)

    record = {
        "schema_version": "z01-uninstall-data-report/v1",
        "work_package_id": "Z01",
        "generated_at": generated_at,
        "declaring_source": "manifests/compatibility_matrix.yaml",
        "user_data_policy": lifecycle["user_data_policy"],
        "preserves_user_data": lifecycle["uninstall"]["preserves_user_data"],
        "orphan_residue_allowed": lifecycle["uninstall"]["orphan_residue_allowed"],
        "user_data_locations": list(user_data),
        "removable_state_ids": sorted(removable),
        "removable_and_user_data_disjoint": set(removable.values()).isdisjoint(
            set(user_data)
        ),
        "complete_uninstall": complete,
        "partial_uninstall_negative_proof": partial,
        "user_data_deletion_negative_proof": rogue,
        "honesty_note": (
            "Declared uninstall policy proof; the plan is evaluated as a pure "
            "function and nothing is removed on disk."
        ),
    }
    record["record_sha256"] = record_sha256(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    return record
