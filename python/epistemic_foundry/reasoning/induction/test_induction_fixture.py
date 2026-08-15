"""induction_fixture_test — end-to-end synthesis over a real O03 EvidencePack.

Exit criterion under test: "independence adjustment applied".  The fixture pack
clusters EVN-0001 and EVN-0002 as one dependent pair, so a synthesis that
counted them as two independent supporting votes would be visibly wrong here.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.retrieval.evidence_pack.contracts import assemble_evidence_pack
from epistemic_foundry.retrieval.evidence_pack.test_pack_diversity import (
    default_units,
    pack_inputs,
)
from .contracts import (
    CAUSAL_IDENTIFICATION,
    RELATION_KIND,
    Direction,
    InductiveSynthesisError,
    SynthesisStatus,
    independence_weights,
    synthesize,
    validate_synthesis,
)

CREATED_AT = "2026-08-01T09:00:00Z"
CLUSTERED = ("EVN-0001", "EVN-0002")


def sealed_pack():
    pack, clusters = assemble_evidence_pack(default_units(), **pack_inputs())
    return pack.payload, [cluster.payload for cluster in clusters]


def finding(
    evidence_id: str,
    direction: str,
    *,
    effect_size: float | None = None,
    standard_error: float | None = None,
    sample_size: int | None = None,
    moderator_levels: dict[str, str] | None = None,
    scope_id: str = "SCOPE-1",
) -> dict[str, object]:
    return {
        "direction": direction,
        "effect_size": effect_size,
        "evidence_id": evidence_id,
        "moderator_levels": dict(moderator_levels or {}),
        "provenance_ref": f"prov:{evidence_id}",
        "sample_size": sample_size,
        "scope_id": scope_id,
        "standard_error": standard_error,
    }


def default_findings() -> list[dict[str, object]]:
    return [
        finding(
            "EVN-0001", Direction.POSITIVE.value, effect_size=0.40, standard_error=0.10
        ),
        finding(
            "EVN-0002", Direction.POSITIVE.value, effect_size=0.44, standard_error=0.10
        ),
        finding(
            "EVN-0003", Direction.POSITIVE.value, effect_size=0.38, standard_error=0.12
        ),
        finding(
            "EVN-0101", Direction.NEGATIVE.value, effect_size=-0.20, standard_error=0.15
        ),
        finding(
            "EVN-0201", Direction.NULL.value, effect_size=0.01, standard_error=0.09
        ),
        finding(
            "EVN-0301", Direction.POSITIVE.value, effect_size=0.30, standard_error=0.20
        ),
        finding("EVN-0401", Direction.UNKNOWN.value),
    ]


def test_cluster_members_share_one_independent_vote() -> None:
    pack, clusters = sealed_pack()

    weights = independence_weights(pack, clusters)

    assert sorted(weights) == list(CLUSTERED)
    assert weights["EVN-0001"] == weights["EVN-0002"] == 0.5
    assert sum(weights.values()) == 1.0


def test_synthesis_weights_direction_by_independence_not_by_head_count() -> None:
    pack, clusters = sealed_pack()

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    positive = payload["direction_summary"][Direction.POSITIVE.value]

    # Four positive findings, but two of them are one dependent pair.
    assert positive["raw_count"] == 4.0
    assert positive["adjusted_weight"] == 3.0
    assert payload["independence"]["raw_finding_count"] == 7
    assert payload["independence"]["adjusted_finding_weight"] == 6.0
    assert payload["independence"]["effective_independent_count"] == 6.0
    assert payload["independence"]["clustered_evidence_count"] == 2


def test_the_recomputed_effective_count_must_match_the_pack() -> None:
    pack, clusters = sealed_pack()
    pack["effective_independent_count"] = 7.0

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "INDEPENDENCE_MISMATCH"
    assert caught.value.context["recomputed"] == 6.0


def test_a_cluster_set_that_disagrees_with_the_pack_fails_closed() -> None:
    pack, clusters = sealed_pack()
    pack["dependency_clusters"] = [["EVN-0001", "EVN-0003"]]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "CLUSTER_MISMATCH"


def test_a_scalar_dependency_cluster_member_list_is_rejected() -> None:
    pack, clusters = sealed_pack()
    pack["dependency_clusters"] = ["EVN-0001"]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "PACK_INVALID"


def test_dominant_direction_and_agreement_are_adjusted(  # noqa: D103
) -> None:
    pack, clusters = sealed_pack()

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["dominant_direction"] == Direction.POSITIVE.value
    # 3.0 adjusted positive out of 6.0 total adjusted weight.
    assert payload["direction_agreement"] == 0.5


def test_every_declared_null_must_carry_a_finding() -> None:
    pack, clusters = sealed_pack()
    findings = [row for row in default_findings() if row["evidence_id"] != "EVN-0201"]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "NULL_EVIDENCE_DROPPED"
    assert caught.value.context["missing"] == ["EVN-0201"]


def test_nulls_counters_and_boundaries_stay_visible_in_the_output() -> None:
    pack, clusters = sealed_pack()

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["null_evidence_ids"] == ["EVN-0201"]
    assert payload["counter_evidence_ids"] == ["EVN-0101"]
    assert payload["boundary_evidence_ids"] == ["EVN-0301"]
    assert payload["direction_summary"][Direction.NULL.value]["adjusted_weight"] == 1.0
    assert (
        payload["direction_summary"][Direction.NEGATIVE.value]["adjusted_weight"] == 1.0
    )


def test_a_finding_outside_the_pack_is_rejected() -> None:
    pack, clusters = sealed_pack()
    findings = [*default_findings(), finding("EVN-9999", Direction.POSITIVE.value)]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "UNKNOWN_EVIDENCE"


def test_an_alternative_only_unit_is_not_evidence_bearing() -> None:
    pack, clusters = sealed_pack()
    pack["alternative_ids"] = ["EVN-0501"]
    findings = [*default_findings(), finding("EVN-0501", Direction.POSITIVE.value)]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "UNKNOWN_EVIDENCE"


def test_a_duplicated_finding_is_rejected() -> None:
    pack, clusters = sealed_pack()
    findings = [*default_findings(), finding("EVN-0003", Direction.NEGATIVE.value)]

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "DUPLICATE_FINDING"


@pytest.mark.parametrize(
    ("effect_size", "standard_error"),
    [(0.3, None), (None, 0.1), (0.3, 0.0), (0.3, -0.1)],
)
def test_incoherent_quantities_fail_closed(effect_size, standard_error) -> None:
    pack, clusters = sealed_pack()
    findings = default_findings()
    findings[2] = finding(
        "EVN-0003",
        Direction.POSITIVE.value,
        effect_size=effect_size,
        standard_error=standard_error,
    )

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "QUANTITATIVE_INCONSISTENT"


def test_a_non_canonical_direction_is_rejected() -> None:
    pack, clusters = sealed_pack()
    findings = default_findings()
    findings[0] = finding("EVN-0001", "strongly_positive")

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, findings, created_at=CREATED_AT)

    assert caught.value.code == "DIRECTION_INVALID"


def test_the_synthesis_never_promotes_association_to_causation() -> None:
    pack, clusters = sealed_pack()

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["relation_kind"] == RELATION_KIND == "ASSOCIATION"
    assert payload["causal_identification"] == CAUSAL_IDENTIFICATION == "NOT_ASSESSED"


@pytest.mark.parametrize(
    ("field", "value"),
    [("relation_kind", "CAUSATION"), ("causal_identification", "IDENTIFIED")],
)
def test_a_causal_verdict_cannot_be_injected(field: str, value: str) -> None:
    pack, clusters = sealed_pack()
    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    payload[field] = value

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "CAUSAL_PROMOTION_FORBIDDEN"


def test_incomplete_lanes_and_unsearched_scopes_degrade_the_status() -> None:
    pack, clusters = sealed_pack()

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["status"] == SynthesisStatus.PARTIAL.value
    assert "incomplete:novelty_lane_complete" in payload["degradation_reasons"]
    assert "unsearched_scopes_present" in payload["degradation_reasons"]
    assert payload["unsearched_scopes"] == sorted(pack["unsearched_scopes"])


def test_an_empty_completeness_projection_cannot_claim_a_complete_synthesis() -> None:
    pack, clusters = sealed_pack()
    pack["completeness"] = {}
    pack["unsearched_scopes"] = []

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "FIELD_SET_INVALID"


def test_completeness_flags_must_be_actual_booleans() -> None:
    pack, clusters = sealed_pack()
    pack["completeness"]["support_lane_complete"] = "true"

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "PACK_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [("stale", "false"), ("unsearched_scopes", "SCOPE-1")],
)
def test_status_inputs_do_not_use_truthiness_or_scalar_iteration(
    field: str, value: object
) -> None:
    pack, clusters = sealed_pack()
    pack[field] = value

    with pytest.raises(InductiveSynthesisError) as caught:
        synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert caught.value.code == "PACK_INVALID"


def test_schema_valid_duplicate_and_empty_unsearched_scopes_are_projected() -> None:
    pack, clusters = sealed_pack()
    pack["unsearched_scopes"] = ["SCOPE-b", "", "SCOPE-b", "SCOPE-a"]

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["unsearched_scopes"] == ["", "SCOPE-a", "SCOPE-b"]
    assert "unsearched_scopes_present" in payload["degradation_reasons"]


def test_a_rehashed_complete_status_cannot_hide_recorded_degradation() -> None:
    from .contracts import _hash_excluding

    pack, clusters = sealed_pack()
    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    payload["status"] = SynthesisStatus.COMPLETE.value
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "STATUS_MISMATCH"


def test_rehashing_cannot_replace_completeness_with_an_empty_object() -> None:
    from .contracts import _hash_excluding

    pack, clusters = sealed_pack()
    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    payload["completeness"] = {}
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "FIELD_SET_INVALID"


def test_rehashing_cannot_forge_the_raw_finding_count() -> None:
    from .contracts import _hash_excluding

    pack, clusters = sealed_pack()
    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    payload["independence"]["raw_finding_count"] = 1
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "INDEPENDENCE_MISMATCH"


def test_a_stale_pack_is_recorded_as_a_degradation() -> None:
    pack, clusters = sealed_pack()
    pack["stale"] = True

    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload

    assert payload["stale"] is True
    assert "pack_stale" in payload["degradation_reasons"]
    assert payload["status"] == SynthesisStatus.PARTIAL.value


def test_the_synthesis_is_deterministic_and_content_addressed() -> None:
    pack, clusters = sealed_pack()

    first = synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)
    second = synthesize(pack, clusters, default_findings(), created_at=CREATED_AT)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.payload["synthesis_id"].startswith("IS-")
    assert first.payload["synthesis_hash"].startswith("sha256:")
    assert validate_synthesis(first.payload).canonical_bytes == first.canonical_bytes


def test_a_tampered_synthesis_is_rejected() -> None:
    pack, clusters = sealed_pack()
    payload = synthesize(
        pack, clusters, default_findings(), created_at=CREATED_AT
    ).payload
    payload["dominant_direction"] = Direction.NEGATIVE.value

    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "SYNTHESIS_HASH_MISMATCH"


def test_a_rehashed_tampered_synthesis_is_still_rejected() -> None:
    from .contracts import _hash_excluding

    pack, clusters = sealed_pack()
    findings = default_findings()
    findings[0] = finding(
        "EVN-0001",
        Direction.POSITIVE.value,
        effect_size=0.40,
        standard_error=0.10,
        moderator_levels={"population": "adult"},
    )
    payload = synthesize(pack, clusters, findings, created_at=CREATED_AT).payload
    payload["moderators"] = []
    payload["synthesis_hash"] = _hash_excluding(payload, "synthesis_hash")

    # Recomputing the self-hash repairs integrity but not the content address.
    with pytest.raises(InductiveSynthesisError) as caught:
        validate_synthesis(payload)

    assert caught.value.code == "SYNTHESIS_ID_MISMATCH"
