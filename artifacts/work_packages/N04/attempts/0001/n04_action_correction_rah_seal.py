#!/usr/bin/env python3
"""Append-only correction of the post-N03 live N04 action description."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/N04/attempts/0001"
N03_ATTEMPT = ROOT / "artifacts/work_packages/N03/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
sys.path.insert(0, str(N03_ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import n03_0001_rah_seal as n03_seal  # noqa: E402
import post_n03_0001_dag_reconciliation as reconciliation  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


EXPECTED_PARENT = "000074-64e60cb8"
EXPECTED_PARENT_MANIFEST_HASH = (
    "ea37b21c46d9b259d4f35dfe27c70b8e1926c804c1bfd6085e827b8ae536352b"
)
EXPECTED_EVIDENCE_ID = "E0075"
EXPECTED_TITLE = "N-phase fan-in, missing-node and independent-review gate"
EXPECTED_DEPENDENCIES = ["N02", "N03"]
EXPECTED_WRITE_SCOPE = [
    "tests/golden/multiagent/**",
    "artifacts/work_packages/N04/**",
]
EXPECTED_EXIT_CRITERIA = [
    "expected/actual counts reconcile",
    "author cannot self-approve",
]
EXPECTED_REQUIRED_CHECKS = [
    "missing_node_detection_test",
    "independent_review_test",
]
NEXT_ACTIONS = [
    "Execute N04-0001 N-phase fan-in, missing-node and independent-review gate under its exact manifest scope.",
    "Run missing_node_detection_test and independent_review_test with N02/N03 regressions and separate primary-session review.",
    "Seal N04 evidence and recompute the live 156-package DAG without setting completion_ready=true.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact is not an object: {path}")
    return value


def correction_summary() -> str:
    stored = read_json(N03_ATTEMPT / "post-n03-0001-dag-reconciliation.json")
    live = reconciliation.reconcile()
    stored_stable = {
        key: value
        for key, value in stored.items()
        if key not in {"current_package_evidence", "current_state_counts"}
    }
    live_stable = {
        key: value
        for key, value in live.items()
        if key not in {"current_package_evidence", "current_state_counts"}
    }
    stored_evidence = stored.get("current_package_evidence", {})
    live_evidence = live.get("current_package_evidence", {})
    if not (
        stored_stable == live_stable
        and {
            key: value for key, value in stored_evidence.items() if key != "N04"
        }
        == {key: value for key, value in live_evidence.items() if key != "N04"}
        and stored_evidence.get("N04", {}).get("current_state") == "NOT_STARTED"
        and live_evidence.get("N04", {}).get("current_state") == "IN_PROGRESS_NO_REPORT"
        and live_evidence.get("N04", {}).get("selected_attempt_id") == "N04-0001"
        and live_evidence.get("N04", {}).get("latest_attempt_directory")
        == "artifacts/work_packages/N04/attempts/0001"
        and stored.get("current_state_counts")
        == {"FAIL": 1, "NOT_STARTED": 94, "PASS": 60, "SPEC_GAP": 1}
        and live.get("current_state_counts")
        == {
            "FAIL": 1,
            "IN_PROGRESS_NO_REPORT": 1,
            "NOT_STARTED": 93,
            "PASS": 60,
            "SPEC_GAP": 1,
        }
    ):
        raise SystemExit(
            "post-N03 DAG changed beyond the expected N04-0001 in-progress transition"
        )
    if not (
        stored.get("next_package") == "N04"
        and stored.get("ready_packages_manifest_order") == ["N04", "O01", "T01", "A06"]
        and stored.get("ready_packages", {}).get("N04", {}).get("title") == EXPECTED_TITLE
    ):
        raise SystemExit("post-N03 reconciliation no longer selects canonical N04")

    order, dependencies, definitions = reconciliation.base.load_manifest()
    definition = definitions.get("N04")
    if not isinstance(definition, dict) or "N04" not in order:
        raise SystemExit("N04 is absent from the development manifest")
    if not (
        definition.get("title") == EXPECTED_TITLE
        and sorted(dependencies["N04"]) == EXPECTED_DEPENDENCIES
        and definition.get("write_scope") == EXPECTED_WRITE_SCOPE
        and definition.get("exit_criteria") == EXPECTED_EXIT_CRITERIA
        and definition.get("required_checks") == EXPECTED_REQUIRED_CHECKS
        and definition.get("independent_review") == "required"
    ):
        raise SystemExit("live N04 manifest contract differs from the correction authority")

    return (
        "Append-only correction to post-N03 live execution guidance: E0074 and its "
        "DAG artifact remain valid and immutable; both correctly select N04 from the "
        "manifest-order READY set N04, O01, T01, A06. The E0074 generation's "
        "loop_state.next_actions incorrectly described N04 as event bus and "
        "deterministic replay. The authoritative development manifest defines N04 "
        "as N-phase fan-in, missing-node and independent-review gate, depending on "
        "N02 and N03, with exact write scopes tests/golden/multiagent/** and "
        "artifacts/work_packages/N04/**, exit criteria expected/actual counts "
        "reconcile and author cannot self-approve, and required checks "
        "missing_node_detection_test and independent_review_test. This evidence "
        "supersedes only the live action-description strings; it does not alter "
        "E0074, the 60 PASS / 4 READY / 92 WAITING calculation, any prior report, "
        "or any prior generation. Global implementation_gate=fail and "
        "completion_ready=false."
    )


def commit(summary: str) -> str:
    base = n03_seal.sealed_base
    ralph_root, parent, payloads = base.current_state()
    if parent != EXPECTED_PARENT:
        raise SystemExit(f"unexpected RAH parent {parent}; expected {EXPECTED_PARENT}")
    parent_manifest = ralph_root / "generations" / parent / "generation-manifest.json"
    if sha256(parent_manifest) != EXPECTED_PARENT_MANIFEST_HASH:
        raise SystemExit("sealed E0074 parent generation manifest hash changed")
    identifiers = base.evidence_ids(payloads)
    if identifiers[-1] != "E0074" or len(base.numbered_generations(ralph_root)) != 74:
        raise SystemExit("N04 action correction requires exact E0074 / 74-generation state")

    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    now = rh.utc_now()
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != EXPECTED_EVIDENCE_ID:
        raise SystemExit(f"unexpected evidence ID {identifier}")

    objective = str(goal["goal"])
    goal.update({"status": "active", "updated_at_utc": now})
    loop.update(
        {
            "blocked_reason": None,
            "checkpoint_required": False,
            "current_stage": "ralph-active",
            "done": False,
            "generated_at_utc": now,
            "harness_phase": "execution",
            "implementation_gate": "fail",
            "loop_phase": "bounded-implementation",
            "mark_done_rejected": False,
            "next_actions": NEXT_ACTIONS,
            "status": "active",
            "updated_at_utc": now,
        }
    )
    readiness = loop.get("completion_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not False:
        raise SystemExit("completion readiness must remain explicitly false")
    readiness["evidence_count"] = len(ledger["entries"])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(dict.fromkeys([*identifiers, identifier])),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=objective),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ralph_root,
        {
            "evidence_ledger.json": ledger,
            "goal.json": goal,
            "goal_bridge.json": bridge,
            "loop_state.json": loop,
            "plan_graph.json": plan,
            "review_gate.json": review,
        },
    )

    status_path = ROOT / ".rah/state/status.json"
    gates_path = ROOT / ".rah/state/gates.json"
    status = read_json(status_path)
    gates = read_json(gates_path)
    note = (
        "The corrected post-N03 action executes N04 N-phase fan-in, missing-node "
        "and independent-review gates. Downstream work remains; "
        "implementation_gate=fail and completion_ready=false."
    )
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    existing = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*existing, identifier])),
        "note": note,
        "status": "fail",
    }
    rh.write_json(status_path, status)
    rh.write_json(gates_path, gates)
    rh.refresh_status_for_ralph(ROOT, ROOT / ".rah", goal, loop, now)
    rh.upsert_current_loop(
        ROOT / ".rah/plans/current_loop.md", rh.render_managed_current_loop(goal, loop)
    )
    rh.write_text(ROOT / ".rah/ralph/blockers.md", rh.render_blockers(goal, loop, now))
    return generation


def main() -> int:
    summary = correction_summary()
    base = n03_seal.sealed_base
    ralph_root, current, payloads = base.current_state()
    identifiers = base.evidence_ids(payloads)
    if current == EXPECTED_PARENT and identifiers[-1] == "E0074":
        before = base.numbered_generations(ralph_root)
        generation = commit(summary)
        after = base.numbered_generations(ralph_root)
        if after[:-1] != before or after[-1] != generation:
            raise SystemExit("correction seal did not preserve every prior generation")
    else:
        if identifiers[-1] != EXPECTED_EVIDENCE_ID:
            raise SystemExit("RAH state is neither pre-correction nor exact corrected state")
        generation = current
        if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
            raise SystemExit("stored E0075 summary differs from current correction")
    result = n03_seal.verify_generation_store(75)
    if result["latest_evidence_id"] != EXPECTED_EVIDENCE_ID:
        raise SystemExit("correction evidence is not the live RAH tail")
    result["generation"] = generation
    result["corrected_action"] = NEXT_ACTIONS[0]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
