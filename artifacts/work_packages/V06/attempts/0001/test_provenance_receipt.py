"""provenance_and_receipt_audit — every decision is an immutable, replayable receipt.

A gate whose decisions could not be reproduced would be a record of trust, not of
evidence.  These tests prove, for both an integrated path and a refused one, that
the receipt re-derives its own gate id and hash from its content, that two runs
over equal inputs — the crash/resume case, where the gate is re-driven from the
same sealed sub-receipts — produce byte-equal receipts, and that producing it
mutates none of the composed inputs.  They also prove the gate stays inside its
authority: no receipt grants promotion or carries a bare numeric score, and a
tampered integration receipt is detected by its own hash.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import (
    canonical_json,
    hash_excluding,
    is_schema_digest,
    sha256_hex,
)
from epistemic_foundry.validation.v4_v06 import (
    GATE_ID_PREFIX,
    derive_experiment_replication_integration as derive,
    integration_hash_matches,
)
from fixtures import (
    CANDIDATE_ID,
    GOVERNOR_ROLE,
    integration_arguments,
    p05_receipt,
    q05_receipt,
    v05_receipt,
)


def _refused_arguments() -> dict:
    """A genuine refused path (withheld docket), still a re-derivable receipt."""
    clearance = q05_receipt()
    return integration_arguments(
        statistical_admissibility_receipt=clearance,
        validation_advancement_receipt=v05_receipt(admissibility_receipt=clearance),
        promotion_parliament_receipt=p05_receipt(
            selective_admissibility=clearance, convene=False
        ),
    )


def _both_receipts() -> list[dict]:
    return [
        derive(**integration_arguments()),
        derive(**_refused_arguments()),
    ]


def test_every_receipt_re_derives_its_gate_id_and_hash() -> None:
    for receipt in _both_receipts():
        assert is_schema_digest(receipt["receipt_hash"])
        expected_id = GATE_ID_PREFIX + sha256_hex(
            canonical_json(
                {
                    "candidate_id": receipt["candidate_id"],
                    "created_at": receipt["created_at"],
                    "decision": receipt["decision"],
                    "statistical_admissibility_receipt_hash": receipt[
                        "statistical_admissibility_receipt_hash"
                    ],
                    "validation_advancement_receipt_hash": receipt[
                        "validation_advancement_receipt_hash"
                    ],
                    "promotion_parliament_receipt_hash": receipt[
                        "promotion_parliament_receipt_hash"
                    ],
                }
            )
        ).removeprefix("sha256:")
        assert receipt["gate_id"] == expected_id
        assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")
        assert integration_hash_matches(receipt) is True


def test_receipts_are_byte_equal_across_two_runs() -> None:
    """Replay/crash-resume determinism: no clock, no random draw."""
    assert _both_receipts() == _both_receipts()


def test_the_gate_mutates_none_of_its_composed_inputs() -> None:
    arguments = integration_arguments()
    snapshots = {key: copy.deepcopy(value) for key, value in arguments.items()}
    derive(**arguments)
    for key, before in snapshots.items():
        assert arguments[key] == before, key


def test_a_tampered_integration_receipt_is_detected() -> None:
    receipt = derive(**integration_arguments())
    tampered = dict(receipt)
    tampered["integrated"] = not tampered["integrated"]
    assert integration_hash_matches(tampered) is False


def test_no_receipt_grants_promotion() -> None:
    for receipt in _both_receipts():
        assert receipt["grants_promotion"] is False
        assert receipt["parliament_grants_promotion"] is False


def test_no_receipt_carries_a_bare_numeric_score() -> None:
    """A gate that owns no score never emits a float; ids, tokens and flags only."""
    for receipt in _both_receipts():
        for value in _flatten_values(receipt):
            assert not isinstance(value, float), value


def test_the_gate_id_changes_with_the_decision() -> None:
    """The refused and integrated receipts are distinct records, not the same one."""
    integrated = derive(**integration_arguments())
    refused = derive(**_refused_arguments())
    assert integrated["gate_id"] != refused["gate_id"]
    assert integrated["receipt_hash"] != refused["receipt_hash"]


def test_the_bound_fixture_names_stay_stable() -> None:
    assert CANDIDATE_ID and GOVERNOR_ROLE


def _flatten_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_values(item)
    else:
        yield value
