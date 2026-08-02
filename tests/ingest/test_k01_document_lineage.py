from __future__ import annotations

import copy
from typing import Any

import pytest

from epistemic_foundry.ingest.registry import (
    DocumentRegistryError,
    assert_registration_immutable,
    seal_registration_payload,
    validate_registration_lineage,
)
from tests.ingest.test_k01_document_registration import (
    RegistrationHarness,
    load_fixture,
    make_request,
)


LINEAGE_ORACLE = load_fixture("document-lineage-cases.json")


def registration(
    *,
    marker: str,
    workspace_id: str = "WS-FIXTURE-0001",
    corpus_id: str = "CORPUS-FIXTURE-0001",
    predecessor: str | None = None,
) -> dict[str, Any]:
    payload = load_fixture("document-registration.valid.json")
    payload.pop("registration_id")
    payload.pop("registration_hash")
    payload.update(
        {
            "workspace_id": workspace_id,
            "corpus_id": corpus_id,
            "source_blob_artifact_id": f"ART-SOURCE-{marker}",
            "source_content_hash": "sha256:" + marker.lower()[0] * 64,
            "original_filename": f"fixture-{marker.lower()}.txt",
            "supersedes_registration_id": predecessor,
            "idempotency_key": f"document-registration-{marker.lower()}",
        }
    )
    return seal_registration_payload(payload)


def assert_code(code: str, operation: Any) -> None:
    with pytest.raises(DocumentRegistryError) as caught:
        operation()
    assert caught.value.code == code


def test_lineage_fixture_has_the_exact_five_stable_cases() -> None:
    cases = LINEAGE_ORACLE["cases"]
    assert LINEAGE_ORACLE["fixture_version"] == "K01-0002"
    assert [case["case_id"] for case in cases] == [
        "VALID_SUPERSESSION",
        "UNKNOWN_PREDECESSOR",
        "CROSS_SCOPE_PREDECESSOR",
        "CYCLIC_PREDECESSOR",
        "IMMUTABLE_HISTORY_REWRITE",
    ]


def test_valid_supersession_returns_nearest_predecessor_first() -> None:
    first = registration(marker="A")
    second = registration(marker="B", predecessor=first["registration_id"])
    third = registration(marker="C", predecessor=second["registration_id"])
    history = {
        first["registration_id"]: first,
        second["registration_id"]: second,
    }

    assert validate_registration_lineage(third, history.get) == (
        second["registration_id"],
        first["registration_id"],
    )


def test_unknown_predecessor_fails_closed() -> None:
    current = registration(marker="D", predecessor="DREG-" + "a" * 64)
    assert_code(
        "DOCUMENT_LINEAGE_UNKNOWN",
        lambda: validate_registration_lineage(current, {}.get),
    )


def test_cross_workspace_or_corpus_predecessor_is_rejected() -> None:
    predecessor = registration(marker="E", workspace_id="WS-OTHER")
    current = registration(marker="F", predecessor=predecessor["registration_id"])
    history = {predecessor["registration_id"]: predecessor}

    assert_code(
        "DOCUMENT_LINEAGE_SCOPE_MISMATCH",
        lambda: validate_registration_lineage(current, history.get),
    )


@pytest.mark.parametrize(
    ("request_payload", "history", "expected_code"),
    [
        (
            make_request(
                idempotency_key="doc-register-unknown-predecessor-preflight",
                supersedes_registration_id="DREG-" + "a" * 64,
            ),
            {},
            "DOCUMENT_LINEAGE_UNKNOWN",
        ),
        (
            None,
            None,
            "DOCUMENT_LINEAGE_SCOPE_MISMATCH",
        ),
    ],
    ids=["unknown-predecessor", "cross-scope-predecessor"],
)
def test_invalid_lineage_is_rejected_before_controlled_effect(
    request_payload: dict[str, Any] | None,
    history: dict[str, dict[str, Any]] | None,
    expected_code: str,
) -> None:
    if request_payload is None:
        predecessor = registration(marker="9", workspace_id="WS-OTHER")
        request_payload = make_request(
            idempotency_key="doc-register-cross-scope-preflight",
            supersedes_registration_id=predecessor["registration_id"],
        )
        history = {predecessor["registration_id"]: predecessor}
    harness = RegistrationHarness(request_payload)
    harness.history.update(history or {})

    assert_code(expected_code, harness.run)

    assert harness.calls["resolve_staged_source"] == 0
    assert harness.calls["reserve_source_blob_id"] == 0
    assert harness.calls["reserve_source_registration_effect"] == 0
    assert harness.calls["publish_source_blob"] == 0
    assert harness.calls["record_source_registration_effect"] == 0
    assert harness.calls["publish_registration"] == 0
    assert harness.calls["append_registration_event"] == 0
    assert harness.calls["compare_and_swap_registration"] == 0


def test_cycle_is_rejected_by_the_bounded_traversal_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # Content-derived registration IDs make a cryptographically valid circular
    # fixture require a SHA-256 fixed point.  Isolate the graph traversal here;
    # schema/hash validation is covered separately by the contract tests.
    from epistemic_foundry.ingest.registry import lineage as lineage_module

    current = {
        "registration_id": "DREG-A",
        "supersedes_registration_id": "DREG-B",
        "workspace_id": "WS-FIXTURE-0001",
        "corpus_id": "CORPUS-FIXTURE-0001",
    }
    predecessor = {
        "registration_id": "DREG-B",
        "supersedes_registration_id": "DREG-A",
        "workspace_id": "WS-FIXTURE-0001",
        "corpus_id": "CORPUS-FIXTURE-0001",
    }
    monkeypatch.setattr(
        lineage_module,
        "verify_registration_payload",
        lambda payload: dict(payload),
    )
    assert_code(
        "DOCUMENT_LINEAGE_CYCLE",
        lambda: validate_registration_lineage(
            current,
            {"DREG-B": predecessor}.get,
        ),
    )


def test_existing_registration_cannot_be_rewritten_in_place() -> None:
    before = registration(marker="7")
    after = copy.deepcopy(before)
    after["license_status"] = "restricted"

    assert_code(
        "DOCUMENT_IMMUTABLE_HISTORY_MUTATION",
        lambda: assert_registration_immutable(before, after),
    )
    assert_registration_immutable(before, copy.deepcopy(before))


def test_exact_replay_fails_closed_when_predecessor_history_disappears() -> None:
    harness = RegistrationHarness()
    first = harness.run()
    predecessor_id = first["output_artifact_ids"][0]

    harness.request = make_request(
        declared_filename="fixture-v2.txt",
        idempotency_key="doc-register-lineage-replay-0002",
        supersedes_registration_id=predecessor_id,
    )
    harness.run()
    controlled_effect_counts = {
        name: harness.calls[name]
        for name in (
            "resolve_staged_source",
            "publish_source_blob",
            "publish_registration",
            "append_registration_event",
            "compare_and_swap_registration",
        )
    }

    del harness.history[predecessor_id]

    assert_code(
        "DOCUMENT_RECONCILIATION_REQUIRED",
        lambda: harness.run(attempt=2),
    )
    assert {
        name: harness.calls[name]
        for name in controlled_effect_counts
    } == controlled_effect_counts
