"""unit_and_contract_tests — what a well-formed target actually gets.

The builder's contract is that the document it returns is one the canonical
schema accepts, carries exactly the declared field set, derives its artifact
hashes from the artifact map instead of trusting a parallel list, and leaves
every input the caller passed untouched.  The screen's contract is that an
eligible target satisfies every declared criterion by name, that a report's
counts reconcile with its records, and that the same set screened twice is the
same report — there is no clock and no randomness anywhere in the path.
"""

from __future__ import annotations

from .contracts import (
    ELIGIBILITY_CRITERIA,
    bound_scope_axes,
    build_eligibility_report,
    build_target_manifest,
    constraint_references,
    digest,
    empty_scope_vector,
    manifest_schema_errors,
    screen_target,
    target_manifest_fields,
)
from .fixtures import (
    ARTIFACT_HASH,
    ENTRYPOINT,
    LIBRARY_HASH,
    REPORT_ID,
    ROOT,
    SCREENED_AT,
    bounded_scope,
    manifest_arguments,
    port,
    target_manifest,
)


def report(*manifests: object) -> dict:
    return build_eligibility_report(
        ROOT, list(manifests), report_id=REPORT_ID, screened_at=SCREENED_AT
    )


def test_a_built_manifest_validates_against_its_canonical_schema() -> None:
    manifest = target_manifest()

    assert manifest_schema_errors(ROOT, manifest) == []


def test_a_built_manifest_carries_exactly_the_declared_field_set() -> None:
    manifest = target_manifest()

    assert set(manifest) == set(target_manifest_fields(ROOT))


def test_the_artifact_hashes_are_derived_from_the_artifact_map() -> None:
    manifest = target_manifest()

    assert manifest["artifact_hashes"] == sorted({ARTIFACT_HASH, LIBRARY_HASH})
    assert manifest["entrypoint"] == ENTRYPOINT


def test_two_artifacts_sharing_one_hash_are_pinned_once() -> None:
    manifest = target_manifest(
        artifacts={ENTRYPOINT: ARTIFACT_HASH, "targets/copy.py": ARTIFACT_HASH}
    )

    assert manifest["artifact_hashes"] == [ARTIFACT_HASH]


def test_the_builder_does_not_mutate_what_the_caller_passed() -> None:
    arguments = manifest_arguments()
    before = digest(
        {key: value for key, value in arguments.items() if key != "artifacts"}
    )
    artifacts_before = dict(arguments["artifacts"])

    build_target_manifest(ROOT, **arguments)

    after = digest(
        {key: value for key, value in arguments.items() if key != "artifacts"}
    )
    assert after == before
    assert arguments["artifacts"] == artifacts_before


def test_a_returned_manifest_is_a_fresh_document() -> None:
    first = target_manifest()
    first["supported_actions"].append("mutated")

    assert target_manifest()["supported_actions"] == ["simulate", "perturb"]


def test_a_constraint_names_the_ports_it_bounds() -> None:
    manifest = target_manifest()

    assert constraint_references(manifest["constraints"][0]) == ("seed",)
    assert constraint_references(manifest["constraints"][1]) == ("reservoir_level",)


def test_an_eligible_target_satisfies_every_declared_criterion() -> None:
    record = screen_target(ROOT, target_manifest())

    assert record["eligible"] is True
    assert record["criteria_satisfied"] == sorted(ELIGIBILITY_CRITERIA)
    assert record["reason_codes"] == []
    assert record["target_id"] == "vt-reservoir-sim"
    assert record["target_type"] == "simulation_model"


def test_the_bound_scope_axes_are_the_axes_the_vector_actually_carries() -> None:
    bound = bound_scope_axes(ROOT, bounded_scope())

    assert bound == (
        "domain",
        "entity_type",
        "population",
        "setting",
        "temporal_scale",
        "time_period",
        "unit_of_analysis",
    )
    assert bound_scope_axes(ROOT, empty_scope_vector(ROOT)) == ()


def test_a_single_screen_matches_that_target_s_record_in_a_report() -> None:
    manifest = target_manifest()

    assert screen_target(ROOT, manifest) == report(manifest)["records"][0]


def test_the_report_counts_reconcile_with_its_records() -> None:
    second = target_manifest(target_id="vt-second", supported_actions=[])
    result = report(target_manifest(), second)

    counts = result["counts"]
    assert counts["screened"] == len(result["records"]) == 2
    assert counts["eligible"] + counts["ineligible"] == counts["screened"]
    assert counts["eligible"] == 1
    assert result["eligible_target_ids"] == ["vt-reservoir-sim"]


def test_the_report_records_keep_the_order_they_were_screened_in() -> None:
    result = report(
        target_manifest(target_id="vt-b"), target_manifest(target_id="vt-a")
    )

    assert [record["target_id"] for record in result["records"]] == ["vt-b", "vt-a"]
    assert [record["screened_index"] for record in result["records"]] == [0, 1]


def test_the_same_target_set_screened_twice_is_the_same_report() -> None:
    manifests = [target_manifest(), target_manifest(target_id="vt-second")]

    assert report(*manifests) == report(*manifests)


def test_the_report_carries_only_the_ids_and_timestamps_the_caller_supplied() -> None:
    result = report(target_manifest())

    assert result["report_id"] == REPORT_ID
    assert result["screened_at"] == SCREENED_AT
    assert result["criteria"] == list(ELIGIBILITY_CRITERIA)


def test_an_empty_target_set_produces_an_empty_reconciled_report() -> None:
    result = report()

    assert result["counts"] == {"eligible": 0, "ineligible": 0, "screened": 0}
    assert result["records"] == []
    assert result["reason_totals"] == {}


def test_a_port_without_a_unit_keeps_its_declared_nulls() -> None:
    manifest = target_manifest(outputs=[port("bare", "number")])

    assert manifest["outputs"] == [
        {
            "data_type": "number",
            "id": "bare",
            "required": True,
            "schema_ref": None,
            "temporal_support": None,
            "unit": None,
        }
    ]
