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
    assert all(code != 0 for status, code in EXIT_CODES.items() if status is not ExitStatus.PASS)


def test_status_reports_partial_implementation(capsys) -> None:
    """`status` must not imply a working plugin."""
    assert main(["--json", "status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_status"] == "PARTIAL_IMPLEMENTATION"
    assert payload["release_level"] == "SPEC_BUNDLE"
    assert "evolution_chamber" in payload["specified_only"]
    assert "noetic_ledger" in payload["implemented"]
    assert payload["canonical_schemas_loaded"] == 124


def test_status_does_not_list_a_component_as_both_states(capsys) -> None:
    main(["--json", "status"])
    payload = json.loads(capsys.readouterr().out)
    assert not set(payload["implemented"]) & set(payload["specified_only"])


def test_validate_passes_a_conformant_artifact(capsys) -> None:
    sample = repo_root() / "examples" / "sample_forge-session-state.json"
    assert main(["--json", "validate", "forge-session-state", str(sample)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "PASS"
    assert payload["error_count"] == 0


def test_validate_fails_a_nonconformant_artifact(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"session_id": "FS-001"}), encoding="utf-8")
    assert main(["--json", "validate", "forge-session-state", str(bad)]) == EXIT_CODES[ExitStatus.FAIL]
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
    code = main(["--json", "validate", "forge-session-state", str(tmp_path / "absent.json")])
    assert code == EXIT_CODES[ExitStatus.FAIL]


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        main([])
