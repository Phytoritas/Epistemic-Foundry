"""blindness_test — first-round isolation is measured, not asserted.

Exit criterion under test: "first-round isolation measured".  Every ordered
pair of first-round briefs is examined, the isolation ratio is a computed fact,
and a single cross-reference or a shared context manifest drops it below one and
fails the seal.
"""

from __future__ import annotations

import pytest

from .contracts import (
    BLIND_ROUND,
    BriefRole,
    ParliamentBlindError,
    measure_first_round_isolation,
    seal_brief,
    seal_dispatch,
    validate_dispatch,
)
from .test_evidence_acl import (
    CREATED_AT,
    RUN,
    adversarial_panel,
    assertion,
    brief,
    context_for,
)


def sealed(round_number: int = 1):
    contexts, briefs = adversarial_panel()
    if round_number != 1:
        contexts = [
            context_for(BriefRole.DEFENDER.value, round_number=round_number),
            context_for(BriefRole.PROSECUTOR.value, round_number=round_number),
        ]
        briefs = [
            brief(
                "CB-defender",
                BriefRole.DEFENDER.value,
                contexts[0],
                blind=False,
                round_number=round_number,
            ),
            brief(
                "CB-prosecutor",
                BriefRole.PROSECUTOR.value,
                contexts[1],
                blind=False,
                round_number=round_number,
            ),
        ]
    return seal_dispatch(
        contexts, briefs, created_at=CREATED_AT, round_number=round_number, run_id=RUN
    ).payload


def test_a_blind_first_round_measures_full_isolation() -> None:
    record = sealed()

    isolation = record["isolation"]
    assert BLIND_ROUND == 1
    assert isolation["isolation_ratio"] == 1.0
    assert isolation["pairs_examined"] == 2
    assert isolation["cross_references"] == []
    assert isolation["non_blind_brief_ids"] == []
    assert isolation["measured_brief_ids"] == ["CB-defender", "CB-prosecutor"]


def test_every_ordered_pair_is_examined_not_just_neighbours() -> None:
    briefs = [
        {
            "assertions": [assertion(f"A{index}", [])],
            "blind": True,
            "brief_id": f"CB-{index}",
            "context_manifest_id": f"CM-{index}",
            "round": 1,
        }
        for index in range(4)
    ]

    isolation = measure_first_round_isolation(briefs)

    assert isolation["brief_count"] == 4
    assert isolation["pairs_examined"] == 12
    assert isolation["isolation_ratio"] == 1.0


def test_a_non_blind_first_round_brief_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0] = brief("CB-defender", BriefRole.DEFENDER.value, contexts[0], blind=False)

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "BLINDNESS_VIOLATION"
    assert caught.value.context["brief_id"] == "CB-defender"


def test_one_cross_reference_drops_the_measured_ratio_below_one() -> None:
    briefs = [
        {
            "assertions": [assertion("A0", []) | {"argument_node_ids": ["CB-1"]}],
            "blind": True,
            "brief_id": "CB-0",
            "context_manifest_id": "CM-0",
            "round": 1,
        },
        {
            "assertions": [assertion("A1", [])],
            "blind": True,
            "brief_id": "CB-1",
            "context_manifest_id": "CM-1",
            "round": 1,
        },
    ]

    isolation = measure_first_round_isolation(briefs)

    assert isolation["cross_references"] == [
        {"cited_brief_id": "CB-1", "source_brief_id": "CB-0"}
    ]
    assert isolation["isolation_ratio"] == 0.5


def test_a_first_round_brief_citing_another_brief_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[0]["assertions"][0]["argument_node_ids"] = ["CB-prosecutor"]
    briefs[0] = seal_brief(briefs[0])

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "BLINDNESS_VIOLATION"
    assert (
        caught.value.context["cross_references"][0]["cited_brief_id"] == "CB-prosecutor"
    )


def test_two_roles_sharing_one_context_manifest_break_blindness() -> None:
    context = context_for(BriefRole.DEFENDER.value)
    briefs = [
        brief("CB-a", BriefRole.DEFENDER.value, context),
        brief("CB-b", BriefRole.DEFENDER.value, context),
    ]

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            [context], briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DISPATCH_TOO_NARROW"


def test_the_isolation_report_names_the_shared_manifest_when_one_exists() -> None:
    briefs = [
        {
            "assertions": [assertion("A0", [])],
            "blind": True,
            "brief_id": "CB-0",
            "context_manifest_id": "CM-shared",
            "round": 1,
        },
        {
            "assertions": [assertion("A1", [])],
            "blind": True,
            "brief_id": "CB-1",
            "context_manifest_id": "CM-shared",
            "round": 1,
        },
    ]

    isolation = measure_first_round_isolation(briefs)

    assert isolation["shared_context_manifest_ids"] == ["CM-shared"]


def test_later_rounds_may_cross_examine_openly() -> None:
    record = sealed(round_number=2)

    assert record["round"] == 2
    assert record["isolation"]["brief_count"] == 0
    assert record["isolation"]["isolation_ratio"] == 1.0


def test_a_brief_from_another_round_cannot_join_this_dispatch() -> None:
    contexts, briefs = adversarial_panel()
    briefs[1]["round"] = 2
    briefs[1] = seal_brief(briefs[1])

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DISPATCH_INCOHERENT"


def test_a_context_from_another_run_cannot_join_this_dispatch() -> None:
    from .contracts import _hash_excluding

    contexts, briefs = adversarial_panel()
    contexts[0]["run_id"] = "RUN-other"
    contexts[0]["manifest_hash"] = _hash_excluding(contexts[0], "manifest_hash")

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DISPATCH_INCOHERENT"


def test_a_duplicate_brief_id_is_refused() -> None:
    contexts, briefs = adversarial_panel()
    briefs[1] = brief("CB-defender", BriefRole.PROSECUTOR.value, contexts[1])

    with pytest.raises(ParliamentBlindError) as caught:
        seal_dispatch(
            contexts, briefs, created_at=CREATED_AT, round_number=1, run_id=RUN
        )

    assert caught.value.code == "DUPLICATE_BRIEF"


def test_a_sealed_first_round_may_not_record_a_non_blind_brief() -> None:
    from .contracts import _hash_excluding

    record = sealed()
    record["isolation"]["non_blind_brief_ids"] = ["CB-defender"]
    record["dispatch_hash"] = _hash_excluding(record, "dispatch_hash")

    with pytest.raises(ParliamentBlindError) as caught:
        validate_dispatch(record)

    assert caught.value.code == "BLINDNESS_VIOLATION"


def test_a_sealed_first_round_may_not_record_partial_isolation() -> None:
    from .contracts import _hash_excluding

    record = sealed()
    record["isolation"]["isolation_ratio"] = 0.5
    record["dispatch_hash"] = _hash_excluding(record, "dispatch_hash")

    with pytest.raises(ParliamentBlindError) as caught:
        validate_dispatch(record)

    assert caught.value.code == "BLINDNESS_VIOLATION"


def test_an_isolation_report_that_skips_a_brief_is_refused() -> None:
    from .contracts import _hash_excluding

    record = sealed()
    record["isolation"]["brief_count"] = 1
    record["dispatch_hash"] = _hash_excluding(record, "dispatch_hash")

    with pytest.raises(ParliamentBlindError) as caught:
        validate_dispatch(record)

    assert caught.value.code == "ISOLATION_UNMEASURED"


def test_a_tampered_dispatch_is_rejected() -> None:
    record = sealed()
    record["run_id"] = "RUN-other"

    with pytest.raises(ParliamentBlindError) as caught:
        validate_dispatch(record)

    assert caught.value.code == "DISPATCH_HASH_MISMATCH"


def test_the_dispatch_is_deterministic_and_content_addressed() -> None:
    first = sealed()
    second = sealed()

    assert first == second
    assert first["dispatch_hash"].startswith("sha256:")
