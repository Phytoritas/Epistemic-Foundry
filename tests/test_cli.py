"""CLI surface: typed exit codes and honest maturity reporting."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.cli.main import EXIT_CODES, main
from epistemic_foundry.contracts import repo_root
from epistemic_foundry.domain.status import ExitStatus
from epistemic_foundry.noetic_ledger import NoeticLedger


def test_every_typed_outcome_has_a_distinct_exit_code() -> None:
    """A caller must be able to tell BLOCKED from FAIL from success."""
    assert set(EXIT_CODES) == set(ExitStatus)
    assert len(set(EXIT_CODES.values())) == len(EXIT_CODES)
    assert EXIT_CODES[ExitStatus.PASS] == 0
    assert all(
        code != 0
        for status, code in EXIT_CODES.items()
        if status is not ExitStatus.PASS
    )


def test_status_reports_partial_implementation(capsys) -> None:
    """`status` must not imply a working plugin."""
    assert main(["--json", "status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_status"] == "PARTIAL_IMPLEMENTATION"
    assert payload["release_level"] == "SPEC_BUNDLE"
    assert "noetic_ledger" in payload["implemented"]
    assert payload["canonical_schemas_loaded"] == 127


def test_status_still_refuses_to_claim_plugin_alpha(capsys) -> None:
    """Having a package for every component does not advance the release level.

    PLUGIN_ALPHA requires install-matrix, sandbox, hook-degradation, and UI
    evidence that no unit test supplies, so the runtime must keep reporting
    SPEC_BUNDLE and PARTIAL_IMPLEMENTATION.

    Corrected 2026-08-02: this test previously also asserted
    ``specified_only == []``. That assertion did not test the refusal its name
    describes — it *required* the maturity report to claim that nothing is
    specified-only, which is how `retrieval`, `providers` and `shinka_adapter`
    came to be reported as implemented while none of them could execute. An
    empty specified-only list is a claim about the world, not an invariant, and
    a test must not pin it.
    """
    main(["--json", "status"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["release_level"] == "SPEC_BUNDLE"
    assert payload["runtime_status"] == "PARTIAL_IMPLEMENTATION"
    assert "production" in payload["note"] or "working-plugin" in payload["note"]


def test_status_does_not_list_a_component_as_both_states(capsys) -> None:
    main(["--json", "status"])
    payload = json.loads(capsys.readouterr().out)
    assert not set(payload["implemented"]) & set(payload["specified_only"])


def test_implemented_list_matches_the_shipped_packages(capsys) -> None:
    """The maturity report must track the code, not a stale hand-edited list.

    Claiming a component is implemented when no package exists is exactly the
    overclaim `docs/status_taxonomy.md` separates SPECIFIED from IMPLEMENTED to
    prevent, so the claim is checked against the filesystem.

    Corrected 2026-08-02: the previous version also asserted that a
    specified-only component has NO package directory. That encoded
    "a package exists therefore the component is implemented", which is false
    and was the mechanism by which the overclaim was enforced: a component can
    ship its verification half (contracts, gates, refusals) while its execution
    half does not exist at all. `retrieval` has lane-coverage gates but no
    index, `providers` has neutrality assertions but no transport. Both have
    packages and neither is implemented.

    The invariant kept is the one that is actually true: every shipped component
    package must be classified, so a new package cannot silently escape the
    maturity report in either direction.

    Corrected again after review: an earlier version of this docstring called
    that "strictly stronger than before". It is not. The old assertion said
    ``specified_only`` and the package listing are disjoint; the new one says
    ``specified_only`` is drawn from it. Those are close to negations of each
    other, so the claim is incomparable, not stronger, and describing it as a
    strengthening overstated the change in the same direction the correction was
    supposed to fix. The same review also removed a check that ``specified_only``
    may only name shipped packages: `docs/status_taxonomy.md` defines SPECIFIED
    as a normative contract with production code *not* implied, so a
    specified-only capability with no package at all is exactly the case the
    taxonomy exists to express, and forbidding it would have made the maturity
    report a pure function of the directory listing.
    """
    main(["--json", "status"])
    payload = json.loads(capsys.readouterr().out)
    package_root = repo_root() / "src" / "epistemic_foundry"
    implemented = set(payload["implemented"])
    specified_only = set(payload["specified_only"])

    for name in implemented:
        assert (package_root / name).is_dir(), (
            f"{name} is claimed implemented but has no package"
        )

    shipped = {
        entry.name
        for entry in package_root.iterdir()
        if entry.is_dir()
        and (entry / "__init__.py").is_file()
        and not entry.name.startswith("_")
        and entry.name != "cli"
    }
    unclassified = shipped - implemented - specified_only
    assert not unclassified, (
        f"shipped component packages missing from the maturity report: {sorted(unclassified)}"
    )
    # No converse assertion. A specified-only component is permitted to have no
    # package: that is what SPECIFIED means. Constraining it to shipped names
    # would quietly convert this report into a directory listing.


def test_validate_passes_a_conformant_artifact(capsys) -> None:
    sample = repo_root() / "examples" / "sample_forge-session-state.json"
    assert main(["--json", "validate", "forge-session-state", str(sample)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "PASS"
    assert payload["error_count"] == 0


def test_validate_fails_a_nonconformant_artifact(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"session_id": "FS-001"}), encoding="utf-8")
    assert (
        main(["--json", "validate", "forge-session-state", str(bad)])
        == EXIT_CODES[ExitStatus.FAIL]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "FAIL"
    assert payload["error_count"] > 0


def test_validate_unknown_schema_is_spec_gap(tmp_path, capsys) -> None:
    """An undefined contract is a SPEC_GAP, not a generic failure."""
    artifact = tmp_path / "a.json"
    artifact.write_text("{}", encoding="utf-8")
    code = main(["--json", "validate", "no-such-contract", str(artifact)])
    assert code == EXIT_CODES[ExitStatus.SPEC_GAP]
    assert json.loads(capsys.readouterr().out)["outcome"] == "SPEC_GAP"


def test_ledger_verify_passes_an_intact_chain(tmp_path, capsys) -> None:
    ledger = NoeticLedger(tmp_path / "ledger.jsonl")
    ledger.append(
        event_type="t",
        aggregate_type="a",
        aggregate_id="A-1",
        actor_id="ACTOR-1",
        run_id="RUN-1",
        payload={"n": 1},
    )
    assert main(["--json", "ledger", "verify", str(tmp_path / "ledger.jsonl")]) == 0
    assert json.loads(capsys.readouterr().out)["events"] == 1


def test_ledger_verify_reports_invalidated_on_tampering(tmp_path, capsys) -> None:
    """A broken chain is INVALIDATED: previously accepted output is void."""
    path = tmp_path / "ledger.jsonl"
    ledger = NoeticLedger(path)
    for index in range(2):
        ledger.append(
            event_type="t",
            aggregate_type="a",
            aggregate_id="A-1",
            actor_id="ACTOR-1",
            run_id="RUN-1",
            payload={"n": index},
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload_hash"] = "sha256:" + "0" * 64
    lines[0] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code = main(["--json", "ledger", "verify", str(path)])
    assert code == EXIT_CODES[ExitStatus.INVALIDATED]
    assert json.loads(capsys.readouterr().out)["outcome"] == "INVALIDATED"


def test_missing_artifact_fails_without_traceback(tmp_path, capsys) -> None:
    code = main(
        ["--json", "validate", "forge-session-state", str(tmp_path / "absent.json")]
    )
    assert code == EXIT_CODES[ExitStatus.FAIL]


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        main([])
