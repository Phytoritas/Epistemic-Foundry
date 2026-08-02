"""unit_and_contract_tests — the three gates agree with the surfaces they read.

Map correctness against an archive built from the map itself, ranking
separation against a request that cites real gate artifacts, and a staleness
cascade against records genuinely bound to the revision they came from.  The
point of each happy path is that it is composed, not asserted: every niche,
coverage figure and blast radius here was produced by M05's own builders.
"""

from __future__ import annotations

import copy

from epistemic_foundry.cartography.v4_m05 import NicheMap
from epistemic_foundry.cartography.v4_m06 import (
    audit_promotion_request,
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    build_staleness_cascade,
    map_agreement_findings,
    require_current_revision,
)
from fixtures import (
    RUN_ID,
    authority_citation,
    board,
    coverage,
    derived,
    diversity,
    entries,
    entry,
    figure_citation,
    niche,
    promotion_request,
    radius,
    revision,
)


def test_a_map_and_the_archive_it_was_built_from_agree_everywhere() -> None:
    surface = board()

    assert (
        map_agreement_findings(niche_map=surface, archive_entries=entries(surface))
        == ()
    )


def test_the_agreement_record_counts_both_surfaces() -> None:
    surface = board()
    record = build_map_agreement_record(
        niche_map=surface, archive_entries=entries(surface), record_id="MAR-U1"
    )

    assert record["counts"] == {
        "archive_entries": 5,
        "elites": 3,
        "niches": 3,
        "occupants": 5,
    }
    assert record["elite_candidate_ids"] == ["C1", "D1", "X1"]
    assert record["occupancy"] == dict(surface.occupants())


def test_an_empty_cell_needs_no_archive_entry() -> None:
    """Coverage counts cells; an unoccupied cell has nothing to account for."""
    surface = NicheMap([niche("a", ["C1"], elite_id="C1"), niche("b", [])])
    record = build_map_agreement_record(
        niche_map=surface, archive_entries=entries(surface), record_id="MAR-U2"
    )

    assert record["counts"]["niches"] == 2
    assert record["counts"]["occupants"] == 1


def test_a_cell_without_an_elite_is_still_correct() -> None:
    surface = NicheMap([niche("a", ["C1", "C2"])])

    assert (
        map_agreement_findings(niche_map=surface, archive_entries=entries(surface))
        == ()
    )


def test_the_archived_entry_hashes_are_carried_into_the_record() -> None:
    surface = NicheMap([niche("a", ["C1"], elite_id="C1")])
    rows = entries(surface)
    record = build_map_agreement_record(
        niche_map=surface, archive_entries=rows, record_id="MAR-U3"
    )

    assert record["entry_hashes"] == {"C1": rows[0]["artifact_hash"]}


def test_a_map_revision_binds_the_cells_and_the_occupancy_to_a_generation() -> None:
    surface = board()
    source = build_map_revision(
        niche_map=surface,
        evolution_run_id=RUN_ID,
        generation=7,
        revision_id="MRV-U1",
    )

    assert source["generation"] == 7
    assert sorted(source["niche_hashes"]) == list(surface.niche_ids())
    assert source["occupancy"] == dict(surface.occupants())


def test_binding_a_derived_record_names_the_revision_it_came_from() -> None:
    surface = board()
    source = revision(surface)
    binding = bind_derived_record(
        record=coverage(surface), record_kind="coverage_map", revision=source
    )

    assert binding["source_revision_hash"] == source["revision_hash"]
    assert binding["source_generation"] == source["generation"]
    assert binding["record_id"] == "QDM-M06-1"


def test_a_blast_radius_is_named_by_the_candidate_it_was_computed_for() -> None:
    surface = board()
    source = revision(surface)
    binding = bind_derived_record(
        record=radius(surface), record_kind="blast_radius", revision=source
    )

    assert binding["record_id"] == "C1"
    assert binding["record_kind"] == "blast_radius"


def test_a_current_revision_serves_and_asks_for_no_rebuild() -> None:
    surface = board()
    source = revision(surface, generation=3)
    cascade = require_current_revision(
        revision=source, serving_generation=3, derived_records=derived(surface, source)
    )

    assert cascade["is_current"] is True
    assert cascade["rebuild_required"] == []
    assert cascade["counts"] == {
        "bound_records": 2,
        "rebuild_required": 0,
        "unbound_records": 0,
    }


def test_a_stale_revision_names_every_record_built_from_it() -> None:
    surface = board()
    source = revision(surface, generation=3)
    cascade = build_staleness_cascade(
        revision=source,
        serving_generation=4,
        derived_records=derived(surface, source),
        cascade_id="MSC-U1",
    )

    assert cascade["is_current"] is False
    assert [row["record_kind"] for row in cascade["rebuild_required"]] == [
        "blast_radius",
        "coverage_map",
    ]
    assert cascade["revision_generation"] == 3
    assert cascade["serving_generation"] == 4


def test_the_cascade_names_the_niches_and_occupants_the_records_inherited() -> None:
    surface = board()
    source = revision(surface)
    cascade = build_staleness_cascade(
        revision=source, serving_generation=9, cascade_id="MSC-U2"
    )

    assert cascade["revision_niche_ids"] == list(surface.niche_ids())
    assert cascade["revision_occupant_ids"] == sorted(surface.occupants())


def test_a_record_bound_to_another_revision_is_reported_unjudged() -> None:
    surface = board()
    current = revision(surface, generation=4, revision_id="MRV-U2")
    earlier = revision(surface, generation=3, revision_id="MRV-U3")
    cascade = build_staleness_cascade(
        revision=current,
        serving_generation=5,
        derived_records=[
            *derived(surface, current),
            bind_derived_record(
                record=coverage(surface, map_id="QDM-U-OLD"),
                record_kind="coverage_map",
                revision=earlier,
            ),
        ],
        cascade_id="MSC-U3",
    )

    assert cascade["counts"] == {
        "bound_records": 2,
        "rebuild_required": 2,
        "unbound_records": 1,
    }
    assert cascade["unbound_records"][0]["record_id"] == "QDM-U-OLD"


def test_a_request_backed_by_a_gate_artifact_passes_with_its_figure_recorded() -> None:
    surface = board()
    coverage_map = coverage(surface)
    record = audit_promotion_request(
        request=promotion_request(
            [
                authority_citation(),
                figure_citation(
                    coverage_map["map_id"],
                    "coverage_ratio",
                    coverage_map["coverage_ratio"],
                ),
            ]
        ),
        coverage_map=coverage_map,
        diversity_report=diversity(),
        record_id="RSR-U1",
    )

    assert record["authority_citations"] == [
        {"artifact_id": "GD-M06-1", "schema": "gate-decision"}
    ]
    assert record["cited_ranking_figures"] == ["coverage_ratio"]
    assert record["informing_figures"][0]["value"] == coverage_map["coverage_ratio"]


def test_a_parliament_adjudication_carries_authority_too() -> None:
    surface = board()
    record = audit_promotion_request(
        request=promotion_request([authority_citation("ADJ-M06-1", "adjudication")]),
        coverage_map=coverage(surface),
        diversity_report=diversity(),
        record_id="RSR-U2",
    )

    assert record["authority_citations"][0]["schema"] == "adjudication"
    assert record["cited_ranking_figures"] == []


def test_an_entropy_figure_may_inform_a_request_that_cites_authority() -> None:
    surface = board()
    report = diversity()
    record = audit_promotion_request(
        request=promotion_request(
            [
                authority_citation(),
                figure_citation(
                    report["report_id"],
                    "lineage_entropy",
                    report["lineage_entropy"],
                ),
                figure_citation(
                    report["report_id"],
                    "effective_lineage_count",
                    report["effective_lineage_count"],
                ),
            ]
        ),
        coverage_map=coverage(surface),
        diversity_report=report,
        record_id="RSR-U3",
    )

    assert record["counts"] == {"authority_citations": 1, "informing_figures": 2}
    assert record["cited_ranking_figures"] == [
        "effective_lineage_count",
        "lineage_entropy",
    ]


def test_a_non_ranking_figure_is_recorded_without_being_flagged() -> None:
    surface = board()
    coverage_map = coverage(surface)
    record = audit_promotion_request(
        request=promotion_request(
            [
                authority_citation(),
                figure_citation(
                    coverage_map["map_id"],
                    "total_niches",
                    coverage_map["total_niches"],
                ),
            ]
        ),
        coverage_map=coverage_map,
        diversity_report=diversity(),
        record_id="RSR-U4",
    )

    assert record["cited_ranking_figures"] == []
    assert record["informing_figures"][0]["figure"] == "total_niches"


def test_the_record_pins_the_map_records_the_request_was_checked_against() -> None:
    surface = board()
    coverage_map = coverage(surface)
    report = diversity()
    record = audit_promotion_request(
        request=promotion_request([authority_citation()]),
        coverage_map=coverage_map,
        diversity_report=report,
        record_id="RSR-U5",
    )

    assert record["coverage_map_hash"] == coverage_map["map_hash"]
    assert record["diversity_report_hash"] == report["report_hash"]
    assert record["generation"] == coverage_map["generation"]


def test_no_input_is_modified_by_any_gate() -> None:
    surface = board()
    source = revision(surface)
    rows = entries(surface)
    coverage_map = coverage(surface)
    report = diversity()
    request = promotion_request([authority_citation()])
    before = copy.deepcopy((rows, source, coverage_map, report, request))

    build_map_agreement_record(
        niche_map=surface, archive_entries=rows, record_id="MAR-U9"
    )
    build_staleness_cascade(
        revision=source,
        serving_generation=4,
        derived_records=derived(surface, source),
        cascade_id="MSC-U9",
    )
    audit_promotion_request(
        request=request,
        coverage_map=coverage_map,
        diversity_report=report,
        record_id="RSR-U9",
    )

    assert (rows, source, coverage_map, report, request) == before


def test_an_unarchived_occupant_is_a_finding_rather_than_an_exception() -> None:
    """The survey is complete so a caller can see every divergence at once."""
    surface = board()
    rows = [row for row in entries(surface) if row["candidate_id"] != "D1"]
    findings = map_agreement_findings(niche_map=surface, archive_entries=rows)

    assert [row["code"] for row in findings] == [
        "ELITE_UNARCHIVED",
        "OCCUPANT_UNARCHIVED",
    ]
    assert findings[1]["candidate_id"] == "D1"


def test_an_entry_for_an_unoccupied_cell_is_named_with_both_cell_ids() -> None:
    surface = NicheMap([niche("a", ["C1"], elite_id="C1"), niche("b", [])])
    stray = entry("C1", surface.niche_ids()[1])
    findings = map_agreement_findings(niche_map=surface, archive_entries=[stray])

    assert findings[0]["code"] == "MAP_ENTRY_DIVERGENT"
    assert findings[0]["entry_niche_id"] == surface.niche_ids()[1]
    assert findings[0]["map_niche_id"] == surface.niche_of("C1")
