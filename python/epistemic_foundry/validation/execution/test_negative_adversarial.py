"""negative_and_adversarial_tests — every route past the door is tried.

An action is refused unless a valid capability lease authorizes exactly it, and
that refusal has to hold against every way a run could try to slip past it.  So
each denial the authorization gate can report is provoked on its own — an edited
intent, a stale or revoked or not-yet-valid lease, a capability or scope the
grant never covered, a superseded fencing token, a missing or unbacked approval,
a human principal no counter can fence, a policy bundle that moved, an
environment bound to another run — and the gate is shown to evaluate all of them
rather than stopping at the first, so a caller repairing a denied run sees the
whole gap in one pass.

The builders refuse a second family outright, and each one is a way a run could
be recorded as something other than what happened: an unpinned artifact set or
image, an uncaptured environment, an unrecorded seed, a capture missing a
channel or a metered dimension, an exit status that contradicts the observation,
a receipt edited after sealing, a run that finished before it started, a
duplicated effect id, an idempotency key that does not match the intent.  Each
fails with the code that stopped it rather than degrading into a permissive
default.

The adversarial axis is the authority boundary V03 must never cross: nothing in
this surface scores, promotes, ranks, or reaches evaluator or holdout state, a
denied authorization carries no execution evidence, and an allowed one that
cannot show the whole record is refused.
"""

from __future__ import annotations

import pytest

from . import contracts
from .contracts import (
    DENIAL_CODES,
    FINDING_CODES,
    ValidationExecutionError,
    authorize_execution,
    build_action_intent,
    build_effect_receipt,
    build_run_capture,
    reconcile_effects,
    seal_capture_channel,
    seal_execution_record,
    seal_run_environment,
    verify_effect_receipt,
)
from .fixtures import (
    APPROVAL_ID,
    EXPECTED_EFFECTS,
    FINISHED_AT,
    INTENT_ID,
    ROOT,
    STARTED_AT,
    WRITE_SCOPES,
    action_intent,
    arguments,
    authorization_arguments,
    capture_arguments,
    channel_receipt,
    channels,
    environment_arguments,
    lease,
    receipt_arguments,
    reconciliation,
    run_capture,
    run_environment,
    tampered_intent,
)

# The surface names that would mean V03 had reached into a neighbouring
# authority.  None of these may appear in the public API: execution neither
# scores a candidate nor promotes one nor reads the evaluator or holdout.
FORBIDDEN_AUTHORITY_MARKERS = (
    "promote",
    "promotion",
    "score",
    "scoring",
    "fitness",
    "rank",
    "ranking",
    "reward",
    "holdout",
    "evaluator",
)


def decision(**overrides: object) -> dict:
    return authorize_execution(ROOT, **authorization_arguments(**overrides))


def denials(**overrides: object) -> list[str]:
    return decision(**overrides)["denial_codes"]


# --------------------------------------------------------------------------
# Authorization denials — a run without a live, current, sufficient lease is
# refused, and the reason is exactly the one that stopped it.
# --------------------------------------------------------------------------


def test_a_well_leased_run_is_the_only_one_that_is_allowed() -> None:
    result = decision()

    assert result["allowed"] is True
    assert result["denial_codes"] == []


def test_an_intent_edited_after_approval_no_longer_verifies() -> None:
    result = decision(intent=tampered_intent(target_ref="validation_target:evil@9"))

    assert "INTENT_HASH_MISMATCH" in result["denial_codes"]
    assert result["allowed"] is False


def test_arguments_the_intent_never_hashed_are_refused() -> None:
    result = decision(arguments=arguments(action="delete_reservoir"))

    assert result["denial_codes"] == ["ARGUMENTS_HASH_MISMATCH"]


def test_a_lease_expired_at_the_run_start_instant_is_refused() -> None:
    result = decision(lease=lease(expires_at="2026-08-01T00:01:00Z"))

    assert result["denial_codes"] == ["LEASE_EXPIRED"]


def test_a_lease_not_yet_valid_at_the_run_start_instant_is_refused() -> None:
    result = decision(lease=lease(issued_at="2026-08-01T00:10:00Z"))

    assert result["denial_codes"] == ["LEASE_NOT_YET_VALID"]


def test_a_revoked_lease_is_refused_however_recently_it_was_issued() -> None:
    result = decision(lease=lease(revoked=True, revocation_reason="operator_cutoff"))

    assert result["denial_codes"] == ["LEASE_REVOKED"]
    assert result["detail"]["revocation_reason"] == "operator_cutoff"


def test_a_lease_edited_after_issue_no_longer_seals() -> None:
    unsealed = lease()
    unsealed["fencing_token"] = 999

    result = decision(lease=unsealed)

    assert result["denial_codes"] == ["LEASE_UNSEALED"]


def test_a_capability_the_lease_never_granted_is_refused() -> None:
    result = decision(lease=lease(capabilities=["object_store_read"]))

    assert result["denial_codes"] == ["CAPABILITY_UNLEASED"]
    assert result["detail"]["unleased_capabilities"] == [
        "object_store_write",
        "sandbox_execute",
    ]


def test_a_write_scope_the_lease_never_covered_is_refused() -> None:
    result = decision(
        write_scopes=["object_store/other_run/leak"],
        scope_fencing_heads={},
    )

    assert result["denial_codes"] == ["SCOPE_UNLEASED"]
    assert result["detail"]["uncovered_scopes"] == ["object_store/other_run/leak"]


def test_a_superseded_fencing_token_stops_a_split_brain_write() -> None:
    result = decision(scope_fencing_heads={WRITE_SCOPES[0]: 99})

    assert result["denial_codes"] == ["STALE_FENCING_TOKEN"]
    assert result["detail"]["superseded_scopes"] == [WRITE_SCOPES[0]]


def test_a_consequential_effect_with_no_approval_is_refused() -> None:
    result = decision(
        intent=action_intent(risk_class="controlled_effect", approval_record_ids=[])
    )

    assert result["denial_codes"] == ["APPROVAL_MISSING"]


def test_an_approval_the_lease_does_not_carry_is_refused() -> None:
    result = decision(intent=action_intent(approval_record_ids=["APPROVAL-GHOST"]))

    assert result["denial_codes"] == ["APPROVAL_UNLEASED"]
    assert result["detail"]["unleased_approvals"] == ["APPROVAL-GHOST"]


def test_a_human_principal_cannot_hold_an_unfenceable_run() -> None:
    result = decision(lease=lease(principal_type="human"))

    assert result["denial_codes"] == ["PRINCIPAL_UNFENCEABLE"]
    assert result["detail"]["principal_type"] == "human"


def test_a_lease_issued_under_another_policy_bundle_is_refused() -> None:
    result = decision(policy_hash="sha256:" + "f" * 64)

    assert result["denial_codes"] == ["POLICY_UNPINNED"]


def test_an_environment_bound_to_another_run_is_refused() -> None:
    result = decision(environment=run_environment(run_id="VRUN-OTHER"))

    assert result["denial_codes"] == ["ENVIRONMENT_UNBOUND"]
    assert result["detail"]["environment_run_id"] == "VRUN-OTHER"


def test_an_environment_edited_after_sealing_is_refused() -> None:
    tampered = run_environment()
    tampered["environment_hash"] = "sha256:" + "0" * 64

    result = decision(environment=tampered)

    assert result["denial_codes"] == ["ENVIRONMENT_UNBOUND"]


def test_authorization_evaluates_every_criterion_rather_than_the_first() -> None:
    result = decision(
        intent=tampered_intent(target_ref="validation_target:evil@9"),
        lease=lease(capabilities=["object_store_read"]),
    )

    assert {"INTENT_HASH_MISMATCH", "CAPABILITY_UNLEASED"} <= set(
        result["denial_codes"]
    )


def test_a_run_broken_many_ways_reports_every_denial_in_one_pass() -> None:
    result = decision(
        lease=lease(
            revoked=True,
            revocation_reason="operator_cutoff",
            expires_at="2026-08-01T00:01:00Z",
            policy_hash="sha256:" + "e" * 64,
        )
    )

    assert {"LEASE_REVOKED", "LEASE_EXPIRED", "POLICY_UNPINNED"} <= set(
        result["denial_codes"]
    )
    assert result["allowed"] is False


def test_every_reported_denial_carries_the_reason_that_declares_it() -> None:
    result = decision(lease=lease(expires_at="2026-08-01T00:01:00Z"))

    assert set(result["denials"]) == set(result["denial_codes"])
    for code in result["denial_codes"]:
        assert result["denials"][code] == DENIAL_CODES[code]


# --------------------------------------------------------------------------
# Recording refusals — a run that cannot be re-derived is not sealed.
# --------------------------------------------------------------------------


def refusal_from(func) -> ValidationExecutionError:
    with pytest.raises(ValidationExecutionError) as error:
        func()
    return error.value


def test_a_run_pinning_no_artifact_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(ROOT, **environment_arguments(artifact_hashes=[]))
    )

    assert error.code == "ARTIFACTS_UNPINNED"


def test_an_artifact_hash_outside_canonical_form_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(
            ROOT, **environment_arguments(artifact_hashes=["not-a-hash"])
        )
    )

    assert error.code == "ARTIFACTS_UNPINNED"


def test_a_seed_controlled_target_that_records_no_seed_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(ROOT, **environment_arguments(seeds={}))
    )

    assert error.code == "SEEDS_UNRECORDED"


def test_a_target_requiring_environment_capture_that_records_none_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(
            ROOT, **environment_arguments(environment_capture={})
        )
    )

    assert error.code == "ENVIRONMENT_UNCAPTURED"


def test_a_pinned_image_target_with_no_container_digest_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(
            ROOT, **environment_arguments(container_digest=None)
        )
    )

    assert error.code == "CONTAINER_UNPINNED"


def test_a_container_digest_outside_canonical_form_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(
            ROOT, **environment_arguments(container_digest="latest")
        )
    )

    assert error.code == "CONTAINER_UNPINNED"


def test_a_network_policy_the_schema_does_not_declare_is_refused() -> None:
    error = refusal_from(
        lambda: seal_run_environment(
            ROOT, **environment_arguments(network_policy="open")
        )
    )

    assert error.code == "INPUT_INVALID"


@pytest.mark.parametrize(
    ("observation", "exit_code"),
    [
        ("succeeded", 1),
        ("failed", 0),
        ("succeeded", None),
        ("not_started", 0),
    ],
)
def test_an_exit_status_contradicting_the_observation_is_refused(
    observation: str, exit_code: object
) -> None:
    error = refusal_from(
        lambda: build_run_capture(
            ROOT, **capture_arguments(observation=observation, exit_code=exit_code)
        )
    )

    assert error.code == "STATUS_UNOBSERVED"


def test_an_observation_this_contract_does_not_recognise_is_refused() -> None:
    error = refusal_from(
        lambda: build_run_capture(
            ROOT, **capture_arguments(observation="mostly_fine", exit_code=0)
        )
    )

    assert error.code == "INPUT_INVALID"


def test_a_capture_missing_a_metered_dimension_is_refused() -> None:
    usage = {
        "calls": 1,
        "concurrency": 1,
        "network_bytes": 0,
        "storage_bytes": 4096,
        "wall_seconds": 1800,
    }
    error = refusal_from(
        lambda: build_run_capture(ROOT, **capture_arguments(resource_usage=usage))
    )

    assert error.code == "RESOURCE_USAGE_INCOMPLETE"
    assert error.context["missing"] == ["tokens"]


def test_a_capture_missing_a_channel_is_refused() -> None:
    partial = channels()
    del partial["stderr"]

    error = refusal_from(
        lambda: build_run_capture(ROOT, **capture_arguments(channels=partial))
    )

    assert error.code == "CAPTURE_INCOMPLETE"
    assert error.context["missing"] == ["stderr"]


def test_a_capture_carrying_an_unknown_channel_is_refused() -> None:
    extra = channels()
    extra["telemetry"] = channel_receipt("stdout")

    error = refusal_from(
        lambda: build_run_capture(ROOT, **capture_arguments(channels=extra))
    )

    assert error.code == "CAPTURE_INCOMPLETE"
    assert error.context["unknown"] == ["telemetry"]


def test_a_capture_receipt_edited_after_sealing_is_refused() -> None:
    tampered = channels()
    tampered["stdout"]["receipt_id"] = "AR-V03-stdout-forged"

    error = refusal_from(
        lambda: build_run_capture(ROOT, **capture_arguments(channels=tampered))
    )

    assert error.code == "RECEIPT_HASH_MISMATCH"
    assert error.context["channel"] == "stdout"


def test_a_capture_channel_the_contract_does_not_name_is_refused() -> None:
    error = refusal_from(
        lambda: seal_capture_channel(
            ROOT,
            receipt_id="AR-V03-telemetry",
            artifact_id="ART-V03-telemetry",
            action_intent_id=INTENT_ID,
            channel="telemetry",
            payload=b"anything",
            media_type="application/octet-stream",
            locator="object_store/validation_runs/telemetry",
            actor_id="svc-validation-runner",
            actor_type="service",
            created_at=FINISHED_AT,
        )
    )

    assert error.code == "INPUT_INVALID"


def test_a_capture_actor_the_schema_does_not_declare_is_refused() -> None:
    error = refusal_from(lambda: channel_receipt("stdout", actor_type="daemon"))

    assert error.code == "INPUT_INVALID"


# --------------------------------------------------------------------------
# Reconciliation and receipt refusals.
# --------------------------------------------------------------------------


def test_a_duplicated_expected_effect_id_is_refused() -> None:
    error = refusal_from(
        lambda: reconcile_effects(
            ROOT,
            reconciliation_id="VREC-dup",
            expected_effects=["a", "a"],
            observed_effects=["a"],
            status="SUCCEEDED",
        )
    )

    # A repeated id in one effect set makes the reconciliation counts unable to
    # attribute an outcome to a single effect; it is refused before the set
    # arithmetic runs, so the caller cannot smuggle a double-counted effect in.
    assert error.code == "INPUT_INVALID"


def test_a_duplicated_observed_effect_id_is_refused() -> None:
    error = refusal_from(
        lambda: reconcile_effects(
            ROOT,
            reconciliation_id="VREC-dup",
            expected_effects=["a"],
            observed_effects=["a", "a"],
            status="SUCCEEDED",
        )
    )

    assert error.code == "INPUT_INVALID"


def test_a_status_the_schema_does_not_declare_is_refused() -> None:
    error = refusal_from(
        lambda: reconcile_effects(
            ROOT,
            reconciliation_id="VREC-bad",
            expected_effects=list(EXPECTED_EFFECTS),
            observed_effects=list(EXPECTED_EFFECTS),
            status="MOSTLY_OK",
        )
    )

    assert error.code == "INPUT_INVALID"


def test_a_receipt_whose_run_finished_before_it_started_is_refused() -> None:
    error = refusal_from(
        lambda: build_effect_receipt(
            ROOT,
            **receipt_arguments(started_at=FINISHED_AT, finished_at=STARTED_AT),
        )
    )

    assert error.code == "TIMESTAMP_DISORDERED"


def test_a_receipt_reconciled_against_a_different_status_is_refused() -> None:
    error = refusal_from(
        lambda: build_effect_receipt(
            ROOT, **receipt_arguments(reconciliation=reconciliation(status="FAILED"))
        )
    )

    assert error.code == "STATUS_UNOBSERVED"


def test_a_receipt_built_over_an_edited_environment_is_refused() -> None:
    tampered = run_environment()
    tampered["environment_hash"] = "sha256:" + "0" * 64

    error = refusal_from(
        lambda: build_effect_receipt(ROOT, **receipt_arguments(environment=tampered))
    )

    assert error.code == "RECEIPT_HASH_MISMATCH"


def test_a_receipt_claiming_a_foreign_idempotency_key_is_refused() -> None:
    receipt = build_effect_receipt(ROOT, **receipt_arguments())

    error = refusal_from(
        lambda: verify_effect_receipt(
            ROOT, receipt, action_intent(idempotency_key="VRUN-OTHER:node:1")
        )
    )

    assert error.code == "IDEMPOTENCY_KEY_MISMATCH"


def test_an_intent_risk_class_the_schema_does_not_declare_is_refused() -> None:
    from .fixtures import intent_arguments

    error = refusal_from(
        lambda: build_action_intent(ROOT, **intent_arguments(risk_class="omnipotent"))
    )

    assert error.code == "INPUT_INVALID"


# --------------------------------------------------------------------------
# Sealed-record refusals and the authority boundary.
# --------------------------------------------------------------------------


def denied_decision() -> dict:
    return decision(lease=lease(revoked=True, revocation_reason="operator_cutoff"))


def test_a_denied_authorization_cannot_carry_execution_evidence() -> None:
    error = refusal_from(
        lambda: seal_execution_record(
            ROOT,
            record_id="VXR-denied",
            sealed_at="2026-08-01T00:40:00Z",
            authorization=denied_decision(),
            environment=run_environment(),
        )
    )

    assert error.code == "INPUT_INVALID"
    assert "environment" in error.context["present"]


def test_an_allowed_authorization_missing_part_of_the_record_is_refused() -> None:
    error = refusal_from(
        lambda: seal_execution_record(
            ROOT,
            record_id="VXR-partial",
            sealed_at="2026-08-01T00:40:00Z",
            authorization=authorize_execution(ROOT, **authorization_arguments()),
            environment=run_environment(),
            capture=run_capture(),
            reconciliation=reconciliation(),
        )
    )

    assert error.code == "INPUT_INVALID"
    assert "receipt" in error.context["missing"]


def test_an_authorization_edited_after_sealing_is_refused() -> None:
    tampered = authorize_execution(ROOT, **authorization_arguments())
    tampered["allowed"] = False

    error = refusal_from(
        lambda: seal_execution_record(
            ROOT,
            record_id="VXR-forged",
            sealed_at="2026-08-01T00:40:00Z",
            authorization=tampered,
        )
    )

    assert error.code == "RECEIPT_HASH_MISMATCH"


def test_a_denied_run_seals_a_record_that_receipts_no_effect() -> None:
    record = seal_execution_record(
        ROOT,
        record_id="VXR-denied",
        sealed_at="2026-08-01T00:40:00Z",
        authorization=denied_decision(),
    )

    assert record["gate"] == "DENIED"
    assert record["effect_receipt_hash"] is None
    assert record["environment_hash"] is None
    assert record["criteria_satisfied"] == []


def test_execution_surface_reaches_no_scoring_or_promotion_authority() -> None:
    from . import contracts as module

    exported = {name.lower() for name in module.__dict__ if not name.startswith("_")}
    for marker in FORBIDDEN_AUTHORITY_MARKERS:
        assert not any(marker in name for name in exported), marker


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(ValidationExecutionError) as error:
        contracts._fail("SOMETHING_ELSE", "a code nobody declared")

    assert error.value.code == "INPUT_INVALID"
    assert "SOMETHING_ELSE" not in FINDING_CODES


def test_an_undeclared_decision_table_key_is_drift_not_a_default() -> None:
    with pytest.raises(ValidationExecutionError) as error:
        contracts._assert_table({"succeeded": None}, ["succeeded", "added"], "status")

    assert error.value.code == "VOCABULARY_DRIFT"
    assert error.value.context["missing"] == ["added"]


def test_a_denial_code_and_a_finding_code_are_disjoint_vocabularies() -> None:
    # A denial is *reported* on a decision; a finding is *raised*.  Collapsing
    # the two would let a refusal to authorize masquerade as a malformed input.
    assert set(DENIAL_CODES) & set(FINDING_CODES) == set()
    assert APPROVAL_ID  # the fixture approval the lease actually carries
    assert INTENT_ID
