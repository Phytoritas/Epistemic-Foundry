from __future__ import annotations

import itertools

import pytest

from .resolver import (
    ContextConstraints,
    MappingContext,
    MappingImpact,
    OntologyContractError,
    OntologyEntry,
    OntologyEntityKind,
    ResolutionPolicy,
    ResolutionStatus,
    resolve_construct,
)


def entry(
    construct_id: str,
    *,
    label: str = "engagement",
    aliases: tuple[str, ...] = (),
    methods: tuple[str, ...] = (),
    units: tuple[str, ...] = (),
    populations: tuple[str, ...] = (),
) -> OntologyEntry:
    return OntologyEntry(
        construct_id=construct_id,
        entity_kind=OntologyEntityKind.OPERATIONAL_MEASURE,
        canonical_label=label,
        aliases=aliases,
        definition=f"Definition for {construct_id}",
        ontology_version="ontology-2026-07",
        domain_pack_id="learning_science",
        domain_pack_version="1.2.3",
        authority_ref=f"AUTH-{construct_id}",
        constraints=ContextConstraints(
            method_ids=methods,
            units=units,
            population_or_entities=populations,
        ),
    )


def context(
    *,
    term: str = "engagement",
    method: str | None = "attendance-register",
    unit: str | None = "sessions",
    population: str | None = "students",
    count: int = 1,
    impact: MappingImpact = MappingImpact.ROUTINE,
) -> MappingContext:
    return MappingContext(
        raw_term=term,
        sentence_context="Engagement was recorded for each participating student.",
        method_id=method,
        unit=unit,
        population_or_entity=population,
        unit_of_analysis="student",
        section="methods",
        ontology_version="ontology-2026-07",
        domain_pack_id="learning_science",
        domain_pack_version="1.2.3",
        occurrence_count=count,
        impact=impact,
    )


POLICY = ResolutionPolicy(policy_version="POLICY-ONTOLOGY-1", high_frequency_threshold=10)


def test_ontology_fixture_test_unique_exact_context_resolves() -> None:
    result = resolve_construct(
        context=context(),
        catalog=(
            entry(
                "attendance-engagement",
                methods=("attendance-register",),
                units=("sessions",),
            ),
        ),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected_construct_id == "attendance-engagement"
    assert result.proposed_construct_id == "attendance-engagement"
    assert result.review_queue_items == ()


def test_ontology_fixture_test_same_label_different_construct_is_not_merged() -> None:
    result = resolve_construct(
        context=context(method=None, unit=None),
        catalog=(
            entry("attendance-engagement", methods=("attendance-register",)),
            entry("click-engagement", methods=("click-log",)),
        ),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.selected_construct_id is None
    assert {candidate.construct_id for candidate in result.candidates if candidate.viable} == {
        "attendance-engagement",
        "click-engagement",
    }
    assert "MULTIPLE_VIABLE_CONSTRUCTS" in result.abstention_reasons


def test_ontology_fixture_test_explicit_method_disambiguates_same_label() -> None:
    result = resolve_construct(
        context=context(method="click-log", unit="events"),
        catalog=(
            entry("attendance-engagement", methods=("attendance-register",), units=("sessions",)),
            entry("click-engagement", methods=("click-log",), units=("events",)),
        ),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected_construct_id == "click-engagement"
    excluded = next(candidate for candidate in result.candidates if candidate.construct_id == "attendance-engagement")
    assert excluded.viable is False
    assert excluded.conflicting_dimensions == ("method_id", "unit")


def test_ontology_fixture_test_missing_required_context_for_one_candidate_abstains() -> None:
    result = resolve_construct(
        context=context(method=None),
        catalog=(entry("attendance-engagement", methods=("attendance-register",)),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.selected_construct_id is None
    assert result.candidates[0].missing_dimensions == ("method_id",)
    assert result.abstention_reasons == ("INSUFFICIENT_CONTEXT",)


def test_ontology_fixture_test_string_similarity_is_not_mapping_authority() -> None:
    result = resolve_construct(
        context=context(term="engaged"),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.UNKNOWN
    assert result.candidates == ()
    assert result.abstention_reasons == ("NO_EXACT_LABEL_MATCH",)


def test_ontology_fixture_test_nfkc_case_and_spacing_are_compatibility_normalization() -> None:
    result = resolve_construct(
        context=context(term="  ＥＮＧＡＧＥＭＥＮＴ  "),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected_construct_id == "attendance-engagement"


def test_ontology_fixture_test_alias_is_explicit_not_inferred() -> None:
    result = resolve_construct(
        context=context(term="class participation"),
        catalog=(entry("attendance-engagement", aliases=("class participation",)),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.RESOLVED


def test_ontology_fixture_test_high_impact_unique_mapping_waits_for_approval() -> None:
    result = resolve_construct(
        context=context(impact=MappingImpact.HIGH_IMPACT),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.PENDING_APPROVAL
    assert result.selected_construct_id is None
    assert result.proposed_construct_id == "attendance-engagement"
    assert len(result.review_queue_items) == 1
    item = result.review_queue_items[0]
    assert item.required_authority_artifact == "HumanDecision"
    assert item.proposed_construct_id == "attendance-engagement"
    assert "HIGH_IMPACT" in item.reasons


def test_ontology_fixture_test_high_frequency_ambiguous_mapping_enters_queue() -> None:
    result = resolve_construct(
        context=context(method=None, count=10),
        catalog=(
            entry("attendance-engagement", methods=("attendance-register",)),
            entry("click-engagement", methods=("click-log",)),
        ),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert len(result.review_queue_items) == 1
    assert result.review_queue_items[0].candidate_construct_ids == (
        "attendance-engagement",
        "click-engagement",
    )
    assert "HIGH_FREQUENCY" in result.review_queue_items[0].reasons


def test_ontology_fixture_test_routine_low_frequency_ambiguity_stays_visible() -> None:
    result = resolve_construct(
        context=context(method=None, count=9),
        catalog=(
            entry("attendance-engagement", methods=("attendance-register",)),
            entry("click-engagement", methods=("click-log",)),
        ),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.review_queue_items == ()
    assert result.selected_construct_id is None


def test_ontology_fixture_test_unknown_high_impact_term_enters_queue_not_catalog() -> None:
    result = resolve_construct(
        context=context(term="undefined construct", impact=MappingImpact.HIGH_IMPACT),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )

    assert result.status is ResolutionStatus.UNKNOWN
    assert result.selected_construct_id is None
    assert result.review_queue_items[0].candidate_construct_ids == ()
    assert "UNKNOWN_TERM" in result.review_queue_items[0].reasons


def test_ontology_fixture_test_catalog_order_does_not_change_resolution_or_ids() -> None:
    entries = (
        entry("attendance-engagement", methods=("attendance-register",)),
        entry("click-engagement", methods=("click-log",)),
    )
    outputs = [
        resolve_construct(
            context=context(method=None, count=12),
            catalog=permutation,
            policy=POLICY,
        )
        for permutation in itertools.permutations(entries)
    ]

    assert outputs[0] == outputs[1]
    assert outputs[0].mapping_key_hash == outputs[1].mapping_key_hash
    assert outputs[0].review_queue_items[0].review_item_id == outputs[1].review_queue_items[0].review_item_id


def test_ontology_fixture_test_other_domain_pack_does_not_supply_authority() -> None:
    foreign = OntologyEntry(
        construct_id="foreign-engagement",
        entity_kind=OntologyEntityKind.CONCEPT,
        canonical_label="engagement",
        aliases=(),
        definition="Foreign pack meaning",
        ontology_version="ontology-foreign",
        domain_pack_id="other",
        domain_pack_version="1.0.0",
        authority_ref="AUTH-FOREIGN",
    )

    with pytest.raises(OntologyContractError) as raised:
        resolve_construct(context=context(), catalog=(foreign,), policy=POLICY)

    assert raised.value.code == "ONTOLOGY_AUTHORITY_UNAVAILABLE"


def test_ontology_fixture_test_duplicate_construct_id_fails_closed() -> None:
    with pytest.raises(OntologyContractError) as raised:
        resolve_construct(
            context=context(),
            catalog=(entry("duplicate"), entry("duplicate", label="other")),
            policy=POLICY,
        )

    assert raised.value.code == "ONTOLOGY_CATALOG_DUPLICATE_ID"


def test_ontology_fixture_test_mutable_catalog_is_rejected() -> None:
    with pytest.raises(OntologyContractError) as raised:
        resolve_construct(  # type: ignore[arg-type]
            context=context(),
            catalog=[entry("attendance-engagement")],
            policy=POLICY,
        )

    assert raised.value.code == "ONTOLOGY_INPUT_INVALID"


def test_ontology_fixture_test_queue_id_binds_full_mapping_context() -> None:
    first = resolve_construct(
        context=context(count=10, population="students"),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )
    second = resolve_construct(
        context=context(count=10, population="teachers"),
        catalog=(entry("attendance-engagement"),),
        policy=POLICY,
    )

    assert first.mapping_key_hash != second.mapping_key_hash
    assert first.review_queue_items[0].review_item_id != second.review_queue_items[0].review_item_id

