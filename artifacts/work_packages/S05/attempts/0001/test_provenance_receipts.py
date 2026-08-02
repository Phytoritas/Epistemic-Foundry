"""provenance_and_receipt_audit — every gate decision proves itself.

A qualification, a coverage record and a leakage audit each re-derive their
own hash from exactly the fields they publish; the audit validates against
its canonical schema and never converts an exposure into a score; and the
controls hold no clock and no randomness of their own.
"""

from __future__ import annotations

import ast
from pathlib import Path

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.security.v4_s05 import (
    INCIDENT_ACTIONS,
    build_leakage_audit,
    build_threat_coverage,
    qualify_candidate_execution,
    threat_register,
)
from fixtures import (
    HIDDEN_HANDLE,
    RUN_ID,
    firewall,
    qualification_arguments,
    sealed_bundle,
)

ROOT = Path(__file__).resolve().parents[5]
CONTROLS = ROOT / "src/epistemic_foundry/security/v4_s05/threat_controls.py"


def qualification() -> dict:
    return qualify_candidate_execution(**qualification_arguments())


def coverage() -> dict:
    register = threat_register()
    return build_threat_coverage(
        run_id=RUN_ID,
        control_evidence={threat: ["EV-1"] for threat in register},
        coverage_id="ETC-S05-P",
    )


def audit(observed: list[str]) -> dict:
    return build_leakage_audit(
        firewall=firewall(),
        run_or_bundle_id=RUN_ID,
        surfaces_checked=["cache", "log", "tool"],
        observed_artifact_ids=observed,
        access_log_artifact_id="AL-1",
        leakage_audit_id="LKA-P",
    )


def test_the_qualification_re_derives_its_own_hash() -> None:
    record = qualification()

    assert record["qualification_hash"] == hash_excluding(
        dict(record), "qualification_hash"
    )


def test_the_coverage_re_derives_its_own_hash() -> None:
    record = coverage()

    assert record["coverage_hash"] == hash_excluding(dict(record), "coverage_hash")


def test_the_audit_re_derives_its_own_hash() -> None:
    record = audit([])

    assert record["audit_hash"] == hash_excluding(dict(record), "audit_hash")


def test_the_audit_validates_against_its_canonical_schema() -> None:
    validate_artifact("leakage-audit", audit([]))
    validate_artifact("leakage-audit", audit([HIDDEN_HANDLE]))


def test_the_qualification_binds_the_evaluator_by_content_hash() -> None:
    record = qualification()
    bundle = sealed_bundle()

    assert record["evaluator_bundle_hash"] == hash_excluding(
        dict(bundle), "bundle_hash"
    )


def test_an_exposure_changes_the_audit_hash_and_status() -> None:
    clean = audit([])
    exposed = audit([HIDDEN_HANDLE])

    assert clean["audit_hash"] != exposed["audit_hash"]
    assert clean["status"] != exposed["status"]
    assert exposed["required_actions"] == list(INCIDENT_ACTIONS)


def test_an_exposure_is_never_a_score_adjustment() -> None:
    exposed = audit([HIDDEN_HANDLE])

    for key in exposed:
        assert "score" not in key
        assert "fitness" not in key


def test_the_coverage_names_its_declaring_document() -> None:
    record = coverage()

    assert record["threat_model_path"] == "docs/evolution_security_threat_model.md"
    assert record["run_id"] == RUN_ID


def test_supplied_identifiers_make_every_record_reproducible() -> None:
    assert qualification() == qualification()
    assert coverage() == coverage()
    assert audit([HIDDEN_HANDLE]) == audit([HIDDEN_HANDLE])


def test_the_inputs_are_not_mutated() -> None:
    arguments = qualification_arguments()
    manifest_before = dict(arguments["target_manifest"])
    limits_before = dict(arguments["hard_limits"])

    qualify_candidate_execution(**arguments)

    assert arguments["target_manifest"] == manifest_before
    assert arguments["hard_limits"] == limits_before


def test_the_controls_hold_no_clock_and_no_randomness() -> None:
    tree = ast.parse(CONTROLS.read_text(encoding="utf-8"))
    called = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }

    assert "utc_now_iso" not in called
    assert not any(name.startswith("random.") for name in called)
    # `new_id` runs only when the caller declines to supply an identifier, so
    # determinism is in the caller's hands and the hash covers the identifier.
    assert "new_id" in called
