"""Z03 upgrade / downgrade / migration / rollback matrix harness.

This module is the single deterministic engine behind the two Z03 required
checks -- ``upgrade_matrix_test`` and ``rollback_test``. It reads the declaring
source ``tests/migration/fixtures/upgrade_rollback_matrix.yaml`` and evaluates
the declared upgrade paths, hook re-trust obligations, rollback records and
backfill batches as pure functions. It composes -- by citation, never by copy --
the read-only cross-version contract
``migrations/contracts/compatibility-matrix.json`` and honours exactly its
declared ``rollback`` and ``backfill`` semantics.

Honesty boundary
----------------
These are DECLARED-matrix lifecycle proofs, not real cross-version runtime
migrations. Nothing here upgrades a live install, mutates a database, or executes
a transform against real persisted artifacts. Every path, record and batch is a
declared fixture evaluated as a pure fail-closed function; no clock and no
randomness are involved and nothing is written to disk by the engine.

Determinism
-----------
The harness contains no clock or randomness. Every report embeds a
caller-supplied ``generated_at`` timestamp and is hash-re-derivable through
:func:`record_sha256`: re-running any builder with the same inputs and timestamp
yields a byte-identical canonical record and hash. Refusals are typed codes whose
human-readable reason is always longer than fifty characters.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "upgrade_rollback_matrix.yaml"
)
CONTRACT_PATH = REPO_ROOT / "migrations" / "contracts" / "compatibility-matrix.json"
MIGRATION_CONTRACT_PATH = (
    REPO_ROOT
    / "migrations"
    / "contracts"
    / "evolution-run-spec-v3-to-v4.migration.json"
)
MIGRATION_GUIDE_PATH = REPO_ROOT / "docs" / "migration_v2_to_v4.md"

#: The exact terminal outcome the harness assigns a fully-evidenced, hook-re-
#: trusted upgrade path. It is a Z03-local lifecycle label, deliberately not a
#: canonical schema-enum value, so it never re-declares a wire vocabulary.
TERMINAL_MIGRATED = "MIGRATED_EXPLICITLY"
TERMINAL_UNSUPPORTED = "UNSUPPORTED"
TERMINAL_BLOCKED = "BLOCKED"

# Typed refusal codes -> reason builders. Every reason is > 50 characters so a
# refused decision always carries an auditable, human-readable justification.
REFUSAL_REASONS: dict[str, str] = {
    "EF_Z03_STEP_EVIDENCE_INCOMPLETE": (
        "an applied upgrade step is missing required lifecycle evidence, so the "
        "fail-closed matrix refuses to reconcile the step to a migrated outcome"
    ),
    "EF_Z03_HOOK_TRUST_NOT_REESTABLISHED": (
        "an upgrade changed hook definitions but the host did not re-establish hook "
        "trust, so silent trust inheritance is refused until re-trust is recorded"
    ),
    "EF_Z03_DOWNGRADE_UNSUPPORTED": (
        "a downgrade would require forward compatibility that the contract does not "
        "claim, so the fail-closed matrix refuses it rather than silently falling back"
    ),
    "EF_Z03_TERMINAL_RECONCILIATION_MISMATCH": (
        "the declared path terminal does not match the terminal recomputed from its "
        "declared steps, so the upgrade path fails exact reconciliation fail-closed"
    ),
    "EF_Z03_ROLLBACK_SOURCE_DISCARDED": (
        "the rollback plan does not restore or retain the exact prior source payload, "
        "which violates the retained-source contract and is refused fail-closed"
    ),
    "EF_Z03_ROLLBACK_HASH_MISMATCH": (
        "the restored source payload hash does not equal the exact prior source hash, "
        "so the rollback did not restore the prior state and is refused fail-closed"
    ),
    "EF_Z03_ROLLBACK_MIGRATION_RECORDS_LOST": (
        "the rollback plan deletes retained migration records, which the migration-"
        "records-retained contract forbids, so the destructive plan is refused"
    ),
    "EF_Z03_ROLLBACK_HISTORY_REWRITTEN": (
        "the rollback plan rewrites append-only promotion or effect history, which the "
        "history-preservation contract forbids, so the plan is refused fail-closed"
    ),
    "EF_Z03_UNRESOLVED_RECORDS_FAIL_CLOSED": (
        "one or more records cannot be resolved during rollback, so the fail-closed "
        "contract refuses the whole operation rather than leaving partial state"
    ),
    "EF_Z03_BACKFILL_DRY_RUN_MISSING": (
        "the backfill batch was not preceded by the required dry-run, so writing it "
        "would violate the dry-run-before-write contract and is refused fail-closed"
    ),
    "EF_Z03_BACKFILL_UNRESOLVED_RECORD": (
        "the backfill batch contains an unresolved record, so the whole batch fails "
        "closed and is never committed as a partial success under the contract"
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
    return load_yaml(FIXTURE_PATH)


def load_contract() -> dict:
    return load_json(CONTRACT_PATH)


def load_migration_contract() -> dict:
    return load_json(MIGRATION_CONTRACT_PATH)


def record_sha256(record: object) -> str:
    """Canonical, hash-re-derivable digest of a harness record."""

    payload = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Upgrade / downgrade matrix
# --------------------------------------------------------------------------- #


def hook_retrust_decision(step: dict) -> dict:
    """Pure fail-closed hook re-trust decision for one applied upgrade step.

    An upgrade that changes hook definitions must re-establish host trust; an
    upgraded host can never silently inherit the prior trust decision.
    """

    hooks_changed = bool(step.get("hooks_changed"))
    reestablished = bool(step.get("hook_trust_reestablished"))
    if hooks_changed and not reestablished:
        return {
            "hooks_changed": True,
            "trust_reestablished": False,
            "decision": "REFUSED",
            **refusal("EF_Z03_HOOK_TRUST_NOT_REESTABLISHED"),
        }
    return {
        "hooks_changed": hooks_changed,
        "trust_reestablished": reestablished,
        "decision": "OK",
    }


def evaluate_upgrade_step(matrix: dict, step: dict) -> dict:
    """Pure fail-closed evaluation of one applied (upgrade) migration step."""

    required = set(matrix["required_step_evidence"])
    present = set(step.get("evidence", []))
    missing = sorted(required - present)
    refusals: list[dict] = []
    if missing:
        refusals.append(
            {"missing_evidence": missing, **refusal("EF_Z03_STEP_EVIDENCE_INCOMPLETE")}
        )
    hook = hook_retrust_decision(step)
    if hook["decision"] == "REFUSED":
        refusals.append({k: v for k, v in hook.items() if k in {"code", "reason"}})
    return {
        "step_id": step["step_id"],
        "from": step["from"],
        "to": step["to"],
        "missing_evidence": missing,
        "hook_retrust": hook,
        "refusals": refusals,
        "outcome": TERMINAL_MIGRATED if not refusals else TERMINAL_BLOCKED,
    }


def evaluate_upgrade_path(matrix: dict, path: dict) -> dict:
    """Reconcile the declared terminal of one path with its recomputed terminal."""

    steps = []
    if path["kind"] == "downgrade":
        computed_terminal = TERMINAL_UNSUPPORTED
        for step in path["steps"]:
            steps.append(
                {
                    "step_id": step["step_id"],
                    "from": step["from"],
                    "to": step["to"],
                    "decision": "REFUSED",
                    **refusal("EF_Z03_DOWNGRADE_UNSUPPORTED"),
                }
            )
    else:
        step_results = [evaluate_upgrade_step(matrix, step) for step in path["steps"]]
        steps = step_results
        if all(result["outcome"] == TERMINAL_MIGRATED for result in step_results):
            computed_terminal = TERMINAL_MIGRATED
        else:
            computed_terminal = TERMINAL_BLOCKED

    declared_terminal = path["declared_terminal"]
    reconciled = declared_terminal == computed_terminal
    result = {
        "path_id": path["path_id"],
        "kind": path["kind"],
        "source": path["source"],
        "target": path["target"],
        "declared_terminal": declared_terminal,
        "computed_terminal": computed_terminal,
        "reconciled": reconciled,
        "steps": steps,
    }
    if not reconciled:
        result["refusal"] = refusal("EF_Z03_TERMINAL_RECONCILIATION_MISMATCH")
    return result


def build_upgrade_matrix_report(matrix: dict, *, generated_at: str) -> dict:
    """Deterministic upgrade/downgrade reconciliation report over every path."""

    contract = load_contract()
    migration_contract = load_migration_contract()
    paths = [evaluate_upgrade_path(matrix, path) for path in matrix["paths"]]
    upgrades = [p for p in paths if p["kind"] == "upgrade"]
    downgrades = [p for p in paths if p["kind"] == "downgrade"]
    record = {
        "schema_version": "z03-upgrade-matrix-report/v1",
        "work_package_id": "Z03",
        "generated_at": generated_at,
        "declaring_source": "tests/migration/fixtures/upgrade_rollback_matrix.yaml",
        "composed_contract": matrix["composed_contract"],
        "composed_migration_contract": matrix["composed_migration_contract"],
        "matrix_status": matrix["status"],
        "write_window": contract["compatibility_window"]["write_window"],
        "silent_fallback": contract["compatibility_window"]["silent_fallback"],
        "migration_change_class": migration_contract["change_class"],
        "required_step_evidence": sorted(matrix["required_step_evidence"]),
        "path_count": len(paths),
        "upgrade_count": len(upgrades),
        "downgrade_count": len(downgrades),
        "all_paths_reconciled": all(p["reconciled"] for p in paths),
        "all_upgrades_migrated": all(
            p["computed_terminal"] == TERMINAL_MIGRATED for p in upgrades
        ),
        "all_downgrades_unsupported": all(
            p["computed_terminal"] == TERMINAL_UNSUPPORTED for p in downgrades
        ),
        "paths": paths,
        "honesty_note": (
            "Declared-matrix lifecycle proof; not a real cross-version runtime "
            "migration. Each per-step outcome is evaluated as a pure function."
        ),
    }
    record["record_sha256"] = record_sha256(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    return record


# --------------------------------------------------------------------------- #
# Rollback matrix
# --------------------------------------------------------------------------- #


def _prior_state(case: dict) -> dict:
    return {
        "source_version": case["source_version"],
        "source_payload": case["source_payload"],
        "migration_records": sorted(case["migration_records"]),
        "promotion_history": list(case["promotion_history"]),
        "effect_history": list(case["effect_history"]),
    }


def rollback_decision(case: dict) -> dict:
    """Pure fail-closed rollback evaluation for one FAILED-migration record.

    A PASS requires the plan to restore the exact prior source payload (its hash
    matches the prior source hash), retain the source and its migration records,
    leave append-only promotion/effect history untouched, and carry no unresolved
    records. Any deviation is a typed fail-closed refusal.
    """

    prior = _prior_state(case)
    source_hash = record_sha256(case["source_payload"])
    plan = case["rollback_plan"]
    refusals: list[dict] = []

    restores = bool(plan.get("restores_source_payload", True))
    retains_source = bool(plan.get("retains_source", True))
    if not restores or not retains_source:
        refusals.append(refusal("EF_Z03_ROLLBACK_SOURCE_DISCARDED"))
        restored_payload = None
    else:
        restored_payload = dict(case["source_payload"])
        if plan.get("mutate_restored_payload"):
            restored_payload["_tampered"] = True

    restored_hash = None
    if restored_payload is not None:
        restored_hash = record_sha256(restored_payload)
        if restored_hash != source_hash:
            refusals.append(refusal("EF_Z03_ROLLBACK_HASH_MISMATCH"))

    retains_records = bool(plan.get("retains_migration_records", True))
    restored_records = sorted(case["migration_records"]) if retains_records else []
    if not retains_records:
        refusals.append(refusal("EF_Z03_ROLLBACK_MIGRATION_RECORDS_LOST"))

    rewrites_history = bool(plan.get("rewrites_promotion_or_effect_history", False))
    if rewrites_history:
        refusals.append(refusal("EF_Z03_ROLLBACK_HISTORY_REWRITTEN"))
        restored_promotion = [*prior["promotion_history"], "REWRITTEN"]
        restored_effect = [*prior["effect_history"], "REWRITTEN"]
    else:
        restored_promotion = list(prior["promotion_history"])
        restored_effect = list(prior["effect_history"])

    unresolved = sorted(plan.get("unresolved_records", []))
    if unresolved:
        refusals.append(
            {
                "unresolved_records": unresolved,
                **refusal("EF_Z03_UNRESOLVED_RECORDS_FAIL_CLOSED"),
            }
        )

    restored_state = {
        "source_version": prior["source_version"],
        "source_payload": restored_payload,
        "migration_records": restored_records,
        "promotion_history": restored_promotion,
        "effect_history": restored_effect,
    }
    restores_exact_prior_state = (
        not refusals and restored_hash == source_hash and restored_state == prior
    )
    return {
        "case_id": case["case_id"],
        "migration_status": case["migration_status"],
        "source_hash": source_hash,
        "restored_hash": restored_hash,
        "prior_state_hash": record_sha256(prior),
        "restored_state_hash": record_sha256(restored_state),
        "restores_exact_prior_state": restores_exact_prior_state,
        "unresolved_records": unresolved,
        "refusals": refusals,
        "final_status": "PASS" if not refusals else "FAIL",
    }


def backfill_decision(case: dict, contract: dict) -> dict:
    """Pure fail-closed backfill batch evaluation cited against the contract."""

    policy = contract["backfill"]
    refusals: list[dict] = []
    if policy["dry_run_before_write"] and not case.get("dry_run_performed"):
        refusals.append(refusal("EF_Z03_BACKFILL_DRY_RUN_MISSING"))
    unresolved = sorted(
        record["record_id"] for record in case["records"] if not record.get("resolved")
    )
    if unresolved and policy["unresolved_records_fail_closed"]:
        refusals.append(
            {
                "unresolved_records": unresolved,
                **refusal("EF_Z03_BACKFILL_UNRESOLVED_RECORD"),
            }
        )
    committed = not refusals
    # partial_success_is_not_batch_success: any unresolved record => whole batch
    # is refused, never committed as a partial success.
    return {
        "case_id": case["case_id"],
        "record_count": len(case["records"]),
        "unresolved_records": unresolved,
        "committed_as_batch": committed,
        "refusals": refusals,
        "final_status": "PASS" if committed else "FAIL",
    }


def build_rollback_report(matrix: dict, *, generated_at: str) -> dict:
    """Deterministic rollback and backfill data-preservation report."""

    contract = load_contract()
    rollbacks = [rollback_decision(case) for case in matrix["rollback_cases"]]
    backfills = [backfill_decision(case, contract) for case in matrix["backfill_cases"]]
    record = {
        "schema_version": "z03-rollback-report/v1",
        "work_package_id": "Z03",
        "generated_at": generated_at,
        "declaring_source": "tests/migration/fixtures/upgrade_rollback_matrix.yaml",
        "composed_contract": matrix["composed_contract"],
        "contract_rollback_policy": contract["rollback"],
        "contract_backfill_policy": contract["backfill"],
        "rollback_case_count": len(rollbacks),
        "backfill_case_count": len(backfills),
        "rollback_cases": rollbacks,
        "backfill_cases": backfills,
        "honesty_note": (
            "Declared rollback policy proof; each plan is evaluated as a pure "
            "function and nothing is restored, written, or deleted on disk."
        ),
    }
    record["record_sha256"] = record_sha256(
        {k: v for k, v in record.items() if k != "record_sha256"}
    )
    return record
