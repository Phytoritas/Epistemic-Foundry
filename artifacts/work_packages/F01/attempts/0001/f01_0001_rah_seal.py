#!/usr/bin/env python3
"""Append F01-0001 PASS evidence while global completion remains false.

Authoring note (read before running).  This seal genuinely appends the F01-0001
core and reserved-final evidence to the live RAH ledger and commits a new
generation for each, exactly as the R04/R05/H05 templates do.  It is NOT a
read-only prep sentinel: ``core`` and ``final`` mutate ``.rah/ralph`` and the
project state projections.

Because the seal must bind the live ledger tail, all SIX seal pins are left as
the ``FILL_FROM_LEDGER`` sentinel and the seal refuses to run until an
authorized parent fills them from ``.rah/ralph`` before sealing:

    EXPECTED_PARENT                  the currently committed generation id
    EXPECTED_PARENT_COUNT            the number of preserved generations
    EXPECTED_PARENT_EVIDENCE         the latest evidence id on that generation
    EXPECTED_PARENT_MANIFEST_SHA256  sha256 of that generation-manifest.json
    CORE_EVIDENCE_ID                 the next evidence id (F01 core)
    FINAL_EVIDENCE_ID                the following evidence id (F01 closeout)

``assert_parent_pins`` refuses fail-closed while any pin is still the sentinel,
before ``.rah/`` is opened, so a preflight in the shipped (unpinned) state
cannot advance RAH state.

The sibling ``build_f01_0001_evidence.py`` builder does not expose a
``bind_rah_state`` helper (unlike the R05/F06 builders), so this seal binds
``rah_state`` into ``report.json`` itself by reconstructing the builder's own
deterministic ``report_document`` with the sealed core generation.  Everything
else — evidence IDs, summaries, hashes, flat-snapshot verification — is derived
exactly as the templates do.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
ATTEMPT = ROOT / "artifacts/work_packages/F01/attempts/0001"
AUTOMATION = ROOT / ".rah/helpers/recursive-architecture-refactoring-auto/automation"
ATTEMPT_ID = "F01-0001"
WORK_PACKAGE_ID = "F01"

#: Sentinel for the six pins that can only be read from the live ledger tail.
PARENT_PIN_SENTINEL = "FILL_FROM_LEDGER"
#: All six pins are shipped as sentinels; the parent fills them from `.rah/ralph`
#: (the currently committed generation) before sealing, e.g.
#: EXPECTED_PARENT = "0002xx-xxxxxxxx"; EXPECTED_PARENT_COUNT = 2xx; ...
EXPECTED_PARENT = "000332-3485abac"
EXPECTED_PARENT_COUNT = 332
EXPECTED_PARENT_EVIDENCE = "E0334"
EXPECTED_PARENT_MANIFEST_SHA256 = "f364cf10df8fc342147c7c3636b017c0c502c413286b4176f9fa566777164099"
CORE_EVIDENCE_ID = "E0335"
FINAL_EVIDENCE_ID = "E0336"
sys.path.insert(0, str(ATTEMPT))
sys.path.insert(0, str(AUTOMATION))

import build_f01_0001_evidence as evidence  # noqa: E402
import ralph_harness as rh  # noqa: E402
import state_store  # noqa: E402


NEXT_ACTIONS = [
    "Recompute the DAG frontier after F01-0001 seals and select the next "
    "dependency-ready package.",
    "Launch the next dependency wave as packages become ready.",
    "Keep completion_ready=false until every objective, source-coverage, PRD, "
    "review, and closeout gate passes.",
]
NEXT_PACKAGE = "RECOMPUTE_DAG"
#: The live gate note is the only state this seal overwrites rather than
#: appends; it is checked against this attempt before anything is written.  It
#: is an f-string over the two evidence pins, so filling those constants keeps
#: it consistent automatically.
GATE_NOTE = (
    f"{ATTEMPT_ID} E0-E5 epistemic-work classifier, deterministic "
    "classification-committer, canonical epistemic-work-classification schema, "
    "workflow node and advisory-only prompt is evidence-sealed PASS "
    f"({CORE_EVIDENCE_ID}/{FINAL_EVIDENCE_ID}). The next package is "
    f"{NEXT_PACKAGE}; implementation_gate=fail and completion_ready=false."
)


def assert_parent_pins() -> None:
    pins = {
        "EXPECTED_PARENT": EXPECTED_PARENT,
        "EXPECTED_PARENT_COUNT": EXPECTED_PARENT_COUNT,
        "EXPECTED_PARENT_EVIDENCE": EXPECTED_PARENT_EVIDENCE,
        "EXPECTED_PARENT_MANIFEST_SHA256": EXPECTED_PARENT_MANIFEST_SHA256,
        "CORE_EVIDENCE_ID": CORE_EVIDENCE_ID,
        "FINAL_EVIDENCE_ID": FINAL_EVIDENCE_ID,
    }
    unpinned = sorted(
        name for name, value in pins.items() if value == PARENT_PIN_SENTINEL
    )
    if unpinned:
        raise SystemExit(
            "F01-0001 seal is not pinned: the following pins are still the "
            f"'{PARENT_PIN_SENTINEL}' sentinel and must be filled from the live "
            "ledger tail (the currently committed RAH generation) before "
            f"running: {', '.join(unpinned)}."
        )


def gate_note() -> str:
    if not GATE_NOTE.startswith(f"{ATTEMPT_ID} "):
        raise SystemExit("the live gate note must name this attempt first")
    if NEXT_PACKAGE not in GATE_NOTE:
        raise SystemExit("the live gate note must name the next package")
    if f"({CORE_EVIDENCE_ID}/{FINAL_EVIDENCE_ID})" not in GATE_NOTE:
        raise SystemExit("the live gate note must cite this attempt's evidence")
    return GATE_NOTE


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


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def numbered_generations(ralph_root: Path) -> list[str]:
    return sorted(
        path.name
        for path in (ralph_root / "generations").iterdir()
        if path.is_dir() and re.fullmatch(r"\d{6}-[0-9a-f]{8}", path.name)
    )


def current_state() -> tuple[Path, str, dict[str, Any]]:
    ralph_root = ROOT / ".rah/ralph"
    current = state_store.read_current(ralph_root)
    if current is None:
        raise SystemExit("no committed RAH generation")
    generation, payloads = current
    if state_store.verify_current(ralph_root).get("generation") != generation:
        raise SystemExit("RAH current pointer and verified generation disagree")
    return ralph_root, generation, payloads


def evidence_ids(payloads: dict[str, Any]) -> list[str]:
    ledger = payloads.get("evidence_ledger.json")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise SystemExit("invalid RAH evidence ledger")
    identifiers = [
        str(row.get("id")) for row in ledger["entries"] if isinstance(row, dict)
    ]
    expected = [f"E{index:04d}" for index in range(1, len(identifiers) + 1)]
    if identifiers != expected or int(ledger.get("issued_id_high_water", 0)) != len(
        identifiers
    ):
        raise SystemExit("RAH evidence ledger is not contiguous")
    return identifiers


def generation_number(generation: str) -> int:
    if re.fullmatch(r"\d{6}-[0-9a-f]{8}", generation) is None:
        raise SystemExit(f"malformed RAH generation: {generation}")
    return int(generation.split("-", 1)[0])


def artifact_hashes(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        path = ATTEMPT / name
        if not path.is_file():
            raise SystemExit(f"required F01-0001 artifact missing: {name}")
        result[name] = sha256(path)
    return result


def attempt_artifact_names() -> tuple[str, ...]:
    """Exactly the attempt-directory artifacts F01 report.json binds, minus
    report.json and rah-core-integrity.json (bound separately at closeout)."""
    junit = [f"{step}.junit.xml" for step in evidence.JUNIT_STEPS]
    runs = [f"{name}.run.json" for name in evidence.RUN_RESULTS]
    outputs = [name for name in evidence.OUTPUT_NAMES if name != "report.json"]
    return tuple(sorted(set(junit + runs + outputs)))


def product_hashes() -> dict[str, str]:
    #: The F01 product bytes, bound by path (classifier component, canonical
    #: schema/example, workflow node, advisory prompt, golden fixtures, python
    #: tests and the authoritative protocol doc).
    return {
        relative: sha256(ROOT / relative)
        for relative in sorted(evidence.EXPECTED_SRC_HASHES)
    }


def core_summary() -> str:
    hashes = {**artifact_hashes(attempt_artifact_names()), **product_hashes()}
    return (
        "F01-0001 PASS core verification: the E0-E5 epistemic-work classifier, "
        "its deterministic classification-committer, the canonical "
        "epistemic-work-classification schema and example, the "
        "classify_epistemic_work workflow node, the advisory-only plugin prompt "
        "and the golden gold/adversarial/hash-vector/override fixtures, "
        "implemented in packages/foundry-kernel/src/forge/classifier by a "
        "bounded implementation agent and reviewed by an independent "
        "contract-reviewer subagent (actor-independent from the author) under "
        "exact dependency bindings (C04 C04-0001, E04 E04-0001). Classification "
        "is a deterministic maximum floor over a closed signal vocabulary with "
        "no clock or random draw on the identified path; added signals can "
        "never reduce the work class or any protection (1023 non-empty subsets, "
        "every subset-to-superset pair preserving class, gate, Interview, role "
        "and phase); the identity preimage re-derives byte for byte from the "
        "record's own published fields; retry is idempotency-key bound "
        "(IDEMPOTENCY_CONFLICT), strict replay refuses any self-field mutation "
        "(REPLAY_DIVERGENCE), and override is upward-only, immutable and "
        "requires a resolved canonical correct HumanDecision. The advisory "
        "plugin prompt cannot change classification truth, and nothing scores, "
        "selects, promotes or evaluates. Gold 14/14, adversarial 16/16, hash "
        "vectors 4/4, override 6/6; canonical schema/example (Draft2020-12), "
        "canonical-projection-freshness, both underprocessing guards, the "
        "workflow-contract test, the wire-literal and A03-boundary regressions, "
        "full Python and full Node suites, and git diff --check all pass. "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Review is by an independent contract-reviewer subagent with "
        "actor_independence=true (author and reviewer are distinct actors; "
        "external actor-independent certification does not hold). "
        "The DAG frontier recomputes next; implementation_gate=fail and "
        "completion_ready=false."
    )


def final_summary(parent: str) -> tuple[str, dict[str, str]]:
    hashes = {
        **artifact_hashes(("report.json", "rah-core-integrity.json")),
        **artifact_hashes(attempt_artifact_names()),
        **product_hashes(),
    }
    summary = (
        f"F01-0001 PASS closeout is hash-sealed after core generation {parent}: "
        + "; ".join(f"{name}=sha256:{digest}" for name, digest in hashes.items())
        + ". Every prior RAH generation remains immutable. F01 classifies "
        "epistemic work into the closed E0-E5 vocabulary and records replayable "
        "classification lineage only: it does not score, select, promote or "
        "evaluate any candidate, makes no DSSAT or plant-model parity claim, "
        "treats policy_bundle_hash and policy_bundle_signals as opaque TRUSTED "
        "inputs whose authenticity is C04's responsibility, and promotion "
        "remains a governance decision. Author/reviewer separation holds while "
        "external actor-independent certification does not. The remaining DAG, "
        "source coverage, PRD, review and global closeout gates stay open; "
        "implementation_gate=fail and completion_ready=false."
    )
    return summary, hashes


def bind_rah_state(
    *,
    core_generation: str,
    core_evidence_id: str,
    final_closeout_evidence_id: str,
) -> None:
    """Bind the sealed core generation into report.json by reconstructing the
    builder's deterministic ``report_document`` (the F01 builder exposes no
    ``bind_rah_state`` helper of its own)."""
    integrity = read_json(ATTEMPT / "rah-core-integrity.json")
    stored = read_json(ATTEMPT / "report.json")
    if "rah_state" in stored:
        raise SystemExit("F01-0001 report is already RAH-bound")
    if integrity.get("current_generation") != core_generation:
        raise SystemExit("rah-core-integrity does not match the core generation")
    rah_state = {
        "completion_ready": False,
        "core_evidence_id": core_evidence_id,
        "core_generation": core_generation,
        "final_closeout_evidence_id": final_closeout_evidence_id,
        "flat_snapshot_content_matches": integrity["flat_snapshot_content_matches"],
        "flat_snapshot_stamps_verified": integrity["flat_snapshot_stamps_verified"],
        "generation_file_hashes_verified": integrity["generation_file_hashes_verified"],
        "implementation_gate": "fail",
        "retained_generation_count": integrity["retained_generation_count"],
        "status": "active",
    }
    regression = evidence.regression_evidence()
    fixtures, hashvectors, classifier_version = evidence.fixture_verification()
    schema = evidence.schema_contract_verification()
    dependencies = evidence.dependency_status()
    write_scope = evidence.read_json(ATTEMPT / "write-scope-verification.json")
    verification = evidence.package_verification(
        regression, fixtures, hashvectors, schema, classifier_version
    )
    report = evidence.report_document(
        regression, dependencies, write_scope, verification, rah_state=rah_state
    )
    evidence.write_json("report.json", report)


def assert_active(payloads: dict[str, Any]) -> None:
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        loop.get("status") != "active"
        or goal.get("status") != "active"
        or loop.get("blocked_reason") is not None
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("F01-0001 seal requires active/fail/completion_ready=false")


def commit_active_failed_generation(
    *, payloads: dict[str, Any], summary: str, expected_evidence_id: str
) -> str:
    now = rh.utc_now()
    goal = copy.deepcopy(payloads["goal.json"])
    loop = copy.deepcopy(payloads["loop_state.json"])
    ledger = copy.deepcopy(payloads["evidence_ledger.json"])
    identifier = rh.add_evidence_entry(
        ledger,
        now=now,
        goal_id=goal["goal_id"],
        iteration=int(loop.get("current_iteration") or loop.get("iteration") or 1),
        kind="evidence",
        summary=summary,
    )
    if identifier != expected_evidence_id:
        raise SystemExit(
            f"unexpected evidence ID {identifier}; expected {expected_evidence_id}"
        )
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
    loop["state_machine"] = {
        "allowed_next_states": ["verify", "plan", "blocked", "failed"],
        "current_state": "act",
        "states": [
            "intake",
            "plan",
            "act",
            "verify",
            "review",
            "decide",
            "done",
            "blocked",
            "cancelled",
            "failed",
        ],
    }
    previous_used = loop.get("progress_update", {}).get("used_evidence", [])
    loop["progress_update"] = {
        "created_evidence": [identifier],
        "missing_acceptance_ids": [],
        "missing_closeout_ids": [],
        "missing_evidence_ids": [],
        "missing_validation_ids": [],
        "used_evidence": list(
            dict.fromkeys([*previous_used, *evidence_ids(payloads), identifier])
        ),
    }
    plan = rh.build_plan_graph(goal, loop, payloads["plan_graph.json"], now)
    bridge = rh.build_goal_bridge(
        ROOT,
        goal,
        loop,
        payloads["goal_bridge.json"],
        SimpleNamespace(goal_status="active", goal_objective=str(goal["goal"])),
        now,
    )
    review = copy.deepcopy(payloads["review_gate.json"])
    review["updated_at_utc"] = now
    state_store.KEEP_GENERATIONS = 10_000
    generation = state_store.commit_generation(
        ROOT / ".rah/ralph",
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
    note = gate_note()
    status["implementation_gate"] = "fail"
    status["implementation_gate_note"] = note
    status["next_recommended_action"] = NEXT_ACTIONS[0]
    prior_ids = gates.get("implementation_gate", {}).get("evidence_ids", [])
    gates["implementation_gate"] = {
        "evidence_ids": list(dict.fromkeys([*prior_ids, identifier])),
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


def verify_generation_store(expected_count: int) -> dict[str, Any]:
    ralph_root, current, payloads = current_state()
    generations = numbered_generations(ralph_root)
    if (
        len(generations) != expected_count
        or not generations
        or generations[-1] != current
    ):
        raise SystemExit(
            f"expected {expected_count} generations ending at {current}, found {len(generations)}"
        )
    checked = 0
    for generation in generations:
        generation_root = ralph_root / "generations" / generation
        manifest = read_json(generation_root / "generation-manifest.json")
        files = manifest.get("files")
        if manifest.get("generation") != generation or not isinstance(files, dict):
            raise SystemExit(f"invalid generation manifest: {generation}")
        if set(files) != set(state_store.GENERATION_FILES):
            raise SystemExit(f"generation file set mismatch: {generation}")
        for name in state_store.GENERATION_FILES:
            if sha256(generation_root / name) != files[name]:
                raise SystemExit(
                    f"generation payload hash mismatch: {generation}/{name}"
                )
            checked += 1
    flat_stamps = 0
    flat_matches = 0
    for name in state_store.GENERATION_FILES:
        flat = read_json(ralph_root / name)
        if flat.get("state_generation") == current:
            flat_stamps += 1
        stripped = {
            key: value for key, value in flat.items() if key != "state_generation"
        }
        authority = payloads[name]
        if isinstance(authority, dict):
            authority = {
                key: value
                for key, value in authority.items()
                if key != "state_generation"
            }
        if state_store._dump(stripped) == state_store._dump(authority):
            flat_matches += 1
    loop = payloads["loop_state.json"]
    goal = payloads["goal.json"]
    if (
        flat_stamps != 6
        or flat_matches != 6
        or loop.get("status") != "active"
        or goal.get("status") != "active"
        or loop.get("implementation_gate") != "fail"
        or loop.get("completion_readiness", {}).get("ready") is not False
    ):
        raise SystemExit("RAH state is not active/fail with six matching projections")
    identifiers = evidence_ids(payloads)
    return {
        "attempt_id": ATTEMPT_ID,
        "completion_ready": False,
        "current_generation": current,
        "evidence_count": len(identifiers),
        "flat_snapshot_content_matches": flat_matches,
        "flat_snapshot_stamps_verified": flat_stamps,
        "generation_file_hashes_verified": checked,
        "generation_manifest_sha256": "sha256:"
        + sha256(ralph_root / "generations" / current / "generation-manifest.json"),
        "implementation_gate": "fail",
        "latest_evidence_id": identifiers[-1],
        "parse_errors": {},
        "ralph_status": "active",
        "retained_generation_count": len(generations),
        "status": "PASS",
        "work_package_id": WORK_PACKAGE_ID,
    }


def run_preflight() -> dict[str, Any]:
    assert_parent_pins()
    checked = evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active(payloads)
    if (
        generation != EXPECTED_PARENT
        or evidence_ids(payloads)[-1] != EXPECTED_PARENT_EVIDENCE
    ):
        raise SystemExit("F01-0001 parent is not the pinned ledger tail")
    generations = numbered_generations(ralph_root)
    if len(generations) != EXPECTED_PARENT_COUNT or generations[-1] != generation:
        raise SystemExit(
            f"F01 preflight requires exactly {EXPECTED_PARENT_COUNT} preserved generations"
        )
    manifest_path = ralph_root / "generations" / generation / "generation-manifest.json"
    if sha256(manifest_path) != EXPECTED_PARENT_MANIFEST_SHA256:
        raise SystemExit("F01 parent generation manifest hash mismatch")
    if "rah_state" in read_json(ATTEMPT / "report.json"):
        raise SystemExit("F01-0001 report is already RAH-bound; use verify")
    return {
        **checked,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": EXPECTED_PARENT_EVIDENCE,
        "mode": "preflight",
        "next_evidence_id": CORE_EVIDENCE_ID,
        "retained_generation_count": len(generations),
    }


def run_core() -> dict[str, Any]:
    run_preflight()
    ralph_root, parent, payloads = current_state()
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary = core_summary()
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=CORE_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if (
        current != generation
        or generation_number(current) != generation_number(parent) + 1
    ):
        raise SystemExit("F01 core generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, CORE_EVIDENCE_ID]:
        raise SystemExit(f"F01 core did not append exactly {CORE_EVIDENCE_ID}")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("F01 core evidence summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != EXPECTED_PARENT_COUNT + 1:
        raise SystemExit("F01 core did not preserve all prior generations")
    integrity = verify_generation_store(EXPECTED_PARENT_COUNT + 1)
    write_json(ATTEMPT / "rah-core-integrity.json", integrity)
    bind_rah_state(
        core_generation=generation,
        core_evidence_id=CORE_EVIDENCE_ID,
        final_closeout_evidence_id=FINAL_EVIDENCE_ID,
    )
    evidence.verify()
    return {
        "completion_ready": False,
        "evidence_id": CORE_EVIDENCE_ID,
        "final_closeout_evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "core",
        "parent_generation": parent,
        "state_verification": integrity,
        "status": "active",
    }


def run_final() -> dict[str, Any]:
    assert_parent_pins()
    evidence.verify()
    ralph_root, parent, payloads = current_state()
    assert_active(payloads)
    report = read_json(ATTEMPT / "report.json")
    rah_state = report.get("rah_state")
    if not isinstance(rah_state, dict) or rah_state.get("core_generation") != parent:
        raise SystemExit("F01 report does not bind current core generation")
    if (
        rah_state.get("core_evidence_id") != CORE_EVIDENCE_ID
        or rah_state.get("final_closeout_evidence_id") != FINAL_EVIDENCE_ID
        or evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID
    ):
        raise SystemExit("F01 report and live ledger evidence IDs disagree")
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != core_summary():
        raise SystemExit("stored F01 core summary changed before final seal")
    before = numbered_generations(ralph_root)
    prior_ids = evidence_ids(payloads)
    summary, hashes = final_summary(parent)
    generation = commit_active_failed_generation(
        payloads=payloads, summary=summary, expected_evidence_id=FINAL_EVIDENCE_ID
    )
    _, current, sealed = current_state()
    if (
        current != generation
        or generation_number(current) != generation_number(parent) + 1
    ):
        raise SystemExit("F01 final generation pointer mismatch")
    if evidence_ids(sealed) != [*prior_ids, FINAL_EVIDENCE_ID]:
        raise SystemExit(f"F01 final did not append exactly {FINAL_EVIDENCE_ID}")
    if sealed["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit("F01 final closeout summary mismatch")
    after = numbered_generations(ralph_root)
    if after[:-1] != before or len(after) != EXPECTED_PARENT_COUNT + 2:
        raise SystemExit("F01 final did not preserve all prior generations")
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "evidence_id": FINAL_EVIDENCE_ID,
        "generation": generation,
        "mode": "final",
        "parent_generation": parent,
        "state_verification": verify_generation_store(EXPECTED_PARENT_COUNT + 2),
        "status": "active",
    }


def run_verify() -> dict[str, Any]:
    assert_parent_pins()
    evidence.verify()
    ralph_root, generation, payloads = current_state()
    assert_active(payloads)
    count = len(numbered_generations(ralph_root))
    if count == EXPECTED_PARENT_COUNT:
        return run_preflight()
    if count == EXPECTED_PARENT_COUNT + 1:
        integrity = verify_generation_store(count)
        if evidence_ids(payloads)[-1] != CORE_EVIDENCE_ID:
            raise SystemExit(f"F01 core tail is not {CORE_EVIDENCE_ID}")
        return {
            "mode": "core-verify",
            "state_verification": integrity,
            "status": "PASS",
        }
    if (
        count != EXPECTED_PARENT_COUNT + 2
        or generation_number(generation) != EXPECTED_PARENT_COUNT + 2
    ):
        raise SystemExit(f"unexpected F01 generation count: {count}")
    identifiers = evidence_ids(payloads)
    if identifiers[-2:] != [CORE_EVIDENCE_ID, FINAL_EVIDENCE_ID]:
        raise SystemExit("sealed ledger does not end with F01 core/final evidence")
    report = read_json(ATTEMPT / "report.json")
    parent = str(report["rah_state"]["core_generation"])
    summary, hashes = final_summary(parent)
    if payloads["evidence_ledger.json"]["entries"][-1].get("summary") != summary:
        raise SystemExit(
            "stored F01 final evidence differs from current closeout bytes"
        )
    return {
        "artifact_hashes": hashes,
        "completion_ready": False,
        "generation": generation,
        "latest_evidence_id": FINAL_EVIDENCE_ID,
        "mode": "verify",
        "state_verification": verify_generation_store(count),
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "core", "final", "verify"))
    args = parser.parse_args()
    result = {
        "preflight": run_preflight,
        "core": run_core,
        "final": run_final,
        "verify": run_verify,
    }[args.mode]()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
