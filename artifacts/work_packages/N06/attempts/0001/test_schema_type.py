"""schema_and_type_check — the gate's vocabulary is derived, not invented.

Behaviour tests drive the gate; this file checks the shapes it is published
under.  Every lane the gate reasons about is a lane the sealed N05 scheduler
derives, every lane action it treats as progress is one of N05's four actions,
and every finding it can raise is documented under an uppercase code.  Because
the module composes N05's vocabulary rather than restating it (EF4-I22), a
change to the sealed lane set or action set surfaces here instead of leaving the
gate asserting a vocabulary the scheduler no longer uses.

The authority boundary is checked as a shape too: the gate takes no evaluator,
holdout, fitness or promotion input, names no such thing in its findings, and
derives ``integrated`` as a plain conjunction of "the schedule was valid" and
"no finding fired" — never from a score that could be optimised into a pass.
"""

from __future__ import annotations

import inspect

from epistemic_foundry.scheduler.v4_n05 import (
    ACTIONS,
    LANE_CONCLUDE,
    LANE_START,
    LANES,
    LaneEvent,
)
from epistemic_foundry.scheduler.v4_n06 import (
    ADMISSION_DEFERRAL,
    ADMISSION_POLICIES,
    ADMISSION_RECEIPTED_REFUSAL,
    FINDING_CODES,
    LOCK_ACQUIRE,
    LOCK_ACTIONS,
    LOCK_RELINQUISH,
    MAX_SCHEDULE_EVENTS,
    NO_REQUIREMENTS,
    NO_RESOURCES,
    PROGRESS_ACTIONS,
    LockEvent,
    WaitEdge,
    verify_integration,
)
from fixtures import ROOT, integration_arguments

#: Vocabulary that would signal the gate had reached into the search space it is
#: forbidden to judge.  A finding or a parameter naming any of these would mean
#: the integration gate had begun scoring, ranking or promoting candidates.
FORBIDDEN_AUTHORITY = (
    "evaluat",
    "holdout",
    "promot",
    "fitness",
    "score",
    "reward",
    "rank",
)


def test_the_two_backpressure_policies_are_the_only_two() -> None:
    assert ADMISSION_POLICIES == (ADMISSION_DEFERRAL, ADMISSION_RECEIPTED_REFUSAL)
    assert ADMISSION_DEFERRAL and ADMISSION_RECEIPTED_REFUSAL
    assert ADMISSION_DEFERRAL != ADMISSION_RECEIPTED_REFUSAL


def test_the_two_lock_actions_are_the_only_two() -> None:
    assert LOCK_ACTIONS == (LOCK_ACQUIRE, LOCK_RELINQUISH)
    assert LOCK_ACQUIRE and LOCK_RELINQUISH
    assert LOCK_ACQUIRE != LOCK_RELINQUISH


def test_progress_actions_are_lane_actions_the_scheduler_derives() -> None:
    # A required lock must be held at the moments a candidate makes progress, and
    # those moments are lane actions N05 owns, not a vocabulary this gate coins.
    assert PROGRESS_ACTIONS == (LANE_START, LANE_CONCLUDE)
    assert set(PROGRESS_ACTIONS) <= set(ACTIONS)


def test_the_lock_and_wait_records_key_on_the_scheduler_lane_vocabulary() -> None:
    # A lock/wait declaration is anchored to a candidate and a resource; the lane
    # a requirement guards is one of N05's derived lanes, so the gate composes the
    # sealed lane identities instead of declaring its own (EF4-I22).
    assert LaneEvent.__module__.endswith("v4_n05.lanes")
    assert {field for field in LockEvent.__dataclass_fields__} == {
        "instant",
        "resource_id",
        "holder_id",
        "action",
    }
    assert {field for field in WaitEdge.__dataclass_fields__} == {
        "instant",
        "holder_id",
        "resource_id",
    }


def test_every_finding_code_is_documented_and_uppercase() -> None:
    assert FINDING_CODES
    for field, (code, reason) in FINDING_CODES.items():
        assert isinstance(field, str) and field
        assert code == code.upper() and code
        assert isinstance(reason, str) and reason.strip()


def test_every_finding_field_is_a_real_report_field() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    for field in FINDING_CODES:
        assert field in report, field
        assert isinstance(report[field], list)


def test_no_finding_names_evaluator_holdout_or_promotion_authority() -> None:
    # The gate accounts for scheduling integrity; a finding that reached into
    # evaluation, holdout or promotion would mean it had taken authority it is
    # explicitly denied.
    for code, reason in FINDING_CODES.values():
        text = f"{code} {reason}".lower()
        for token in FORBIDDEN_AUTHORITY:
            assert token not in text, (code, token)


def test_the_gate_accepts_no_evaluator_or_promotion_input() -> None:
    parameters = " ".join(inspect.signature(verify_integration).parameters).lower()
    for token in FORBIDDEN_AUTHORITY:
        assert token not in parameters, token


def test_integrated_is_the_conjunction_of_valid_and_finding_free() -> None:
    report = verify_integration(ROOT, **integration_arguments())
    recomputed = bool(report["schedule"]["valid"]) and not any(
        report[field] for field in FINDING_CODES
    )
    assert report["integrated"] is recomputed
    assert report["integrated"] is True


def test_the_defaults_are_empty_and_cannot_be_mutated_into_the_next_run() -> None:
    assert dict(NO_RESOURCES) == {}
    assert dict(NO_REQUIREMENTS) == {}
    for default in (NO_RESOURCES, NO_REQUIREMENTS):
        try:
            default["x"] = 1  # type: ignore[index]
        except TypeError:
            continue
        raise AssertionError("a default declaration was mutable")


def test_the_schedule_length_bound_is_a_positive_whole_number() -> None:
    assert isinstance(MAX_SCHEDULE_EVENTS, int)
    assert not isinstance(MAX_SCHEDULE_EVENTS, bool)
    assert MAX_SCHEDULE_EVENTS >= len(LANES)
