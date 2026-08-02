"""provenance_and_receipt_audit — every decision is an immutable, replayable receipt.

A gate whose decisions could not be reproduced would be a record of trust, not
of evidence.  These tests prove three things about every receipt the gate emits:
it re-derives its own identifier and hash from its content, two runs over equal
inputs produce byte-equal receipts, and producing it mutates none of the sealed
inputs.  They also prove the gate stays inside its authority — no receipt carries
a scalar score or a promotion grant — and that the embedded S05 leakage audit is
still the canonical artifact its own owner would accept.
"""

from __future__ import annotations

import copy

from epistemic_foundry.contracts import validate_artifact
from epistemic_foundry.domain.hashing import (
    hash_excluding,
    is_schema_digest,
    sha256_of_payload,
)
from epistemic_foundry.security.v4_s06 import (
    govern_evaluator_update,
    integrate_evolution_security_gate,
    refuse_reward_hacking,
)
from fixtures import evaluator_arguments, reward_arguments

#: Substrings a scoring or promotion authority would introduce; the gate owns
#: none of them, so no receipt key may carry one.  ``reward_basis`` and
#: ``fitness_vector_id`` are references the gate legitimately names, so the match
#: is on the authority verbs, not on the words reward or fitness themselves.
FORBIDDEN_AUTHORITY_KEYS = (
    "score",
    "granted",
    "promote",
    "promotion",
    "promoted",
    "verdict",
)


def _all_receipts():
    reward = refuse_reward_hacking(**reward_arguments())
    update = govern_evaluator_update(**evaluator_arguments())
    integration = integrate_evolution_security_gate(
        run_id="ER-S06-7", reward_receipt=reward, evaluator_update_receipt=update
    )
    return [reward, update, integration]


def test_every_receipt_re_derives_its_identifier_and_hash() -> None:
    for receipt in _all_receipts():
        assert is_schema_digest(receipt["receipt_hash"])
        body = {
            key: value
            for key, value in receipt.items()
            if key not in {"receipt_id", "receipt_hash"}
        }
        prefix = str(receipt["receipt_id"]).split("-", 1)[0] + "-"
        expected_id = prefix + sha256_of_payload(body).removeprefix("sha256:")
        assert receipt["receipt_id"] == expected_id
        assert receipt["receipt_hash"] == hash_excluding(receipt, "receipt_hash")


def test_receipts_are_byte_equal_across_two_runs() -> None:
    assert _all_receipts() == _all_receipts()


def test_reward_gate_mutates_none_of_its_inputs() -> None:
    arguments = reward_arguments()
    snapshots = {
        key: copy.deepcopy(value)
        for key, value in arguments.items()
        if key != "firewall"
    }
    sealed_before = arguments["firewall"].sealed_hash
    refuse_reward_hacking(**arguments)
    for key, before in snapshots.items():
        assert arguments[key] == before, key
    assert arguments["firewall"].sealed_hash == sealed_before


def test_evaluator_gate_mutates_none_of_its_inputs() -> None:
    arguments = evaluator_arguments()
    snapshots = {
        key: copy.deepcopy(value)
        for key, value in arguments.items()
        if key != "firewall"
    }
    govern_evaluator_update(**arguments)
    for key, before in snapshots.items():
        assert arguments[key] == before, key


def test_no_receipt_carries_a_scoring_or_promotion_field() -> None:
    for receipt in _all_receipts():
        for key in _flatten_keys(receipt):
            lowered = key.lower()
            assert not any(bad in lowered for bad in FORBIDDEN_AUTHORITY_KEYS), key


def test_no_receipt_carries_a_bare_numeric_score() -> None:
    """A gate that owns no score never emits a float; ids and tokens only."""
    for receipt in _all_receipts():
        for value in _flatten_values(receipt):
            assert not isinstance(value, float), value


def test_the_embedded_leakage_audit_validates_against_its_schema() -> None:
    reward = refuse_reward_hacking(**reward_arguments())
    # The gate embeds the S05 audit verbatim rather than paraphrasing it, so it
    # must still be the canonical artifact its own owner would accept.
    validate_artifact("leakage-audit", reward["leakage_audit"])
    assert reward["leakage_audit"]["detected_exposures"] == []


def _flatten_keys(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _flatten_keys(item, prefix)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_keys(item, prefix)


def _flatten_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_values(item)
    else:
        yield value
