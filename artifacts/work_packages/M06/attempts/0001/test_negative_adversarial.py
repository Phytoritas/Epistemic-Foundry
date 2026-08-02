"""negative_and_adversarial_tests — every way an integration can be faked.

An integration gate fails quietly by design: the surfaces still look valid on
their own, so the lie is in the relationship between them.  A cell that lists
an occupant nobody archived, an entry filed against a cell that never existed,
a promotion request whose only reason is a number that was never allowed to be
a reason, a map served a generation after the population moved on, and a record
whose published hash no longer matches what it says.  Each attack below is
wrong in exactly one way and is refused by its own code.
"""

from __future__ import annotations

import copy

import pytest

from epistemic_foundry.cartography.v4_m05 import NicheMap
from epistemic_foundry.cartography.v4_m06 import (
    CartographyIntegrationError,
    audit_promotion_request,
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    build_staleness_cascade,
    map_agreement_findings,
    require_current_revision,
)
from epistemic_foundry.cartography.v4_m06 import gate as gate_module
from epistemic_foundry.domain.hashing import hash_excluding
from fixtures import (
    NON_AUTHORITY_SCHEMA,
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
    revision,
)


def refused(run, code: str) -> CartographyIntegrationError:
    with pytest.raises(CartographyIntegrationError) as caught:
        run()
    assert caught.value.code == code, caught.value.code
    return caught.value


def audit(citations, **overrides):
    surface = board()
    arguments = {
        "request": promotion_request(citations),
        "coverage_map": coverage(surface),
        "diversity_report": diversity(),
        "record_id": "RSR-N",
    }
    arguments.update(overrides)
    return lambda: audit_promotion_request(**arguments)


# --- map correctness -------------------------------------------------------


def test_an_entry_filed_against_a_cell_that_does_not_exist_is_refused() -> None:
    surface = board()
    rows = [*entries(surface), entry("Z9", "NI-0000000000000000")]

    error = refused(
        lambda: build_map_agreement_record(niche_map=surface, archive_entries=rows),
        "ENTRY_NICHE_UNMAPPED",
    )

    assert error.context["findings"][0]["candidate_id"] == "Z9"
    assert error.context["findings"][0]["entry_niche_id"] == "NI-0000000000000000"


def test_the_two_surfaces_disagreeing_about_a_cell_names_both_ids() -> None:
    surface = board()
    rows = entries(surface)
    elsewhere = next(
        niche_id for niche_id in surface.niche_ids() if niche_id != rows[0]["niche_id"]
    )
    rows[0] = entry(rows[0]["candidate_id"], elsewhere)

    error = refused(
        lambda: build_map_agreement_record(niche_map=surface, archive_entries=rows),
        "MAP_ENTRY_DIVERGENT",
    )
    finding = error.context["findings"][0]

    assert finding["entry_niche_id"] == elsewhere
    assert finding["map_niche_id"] == surface.niche_of(finding["candidate_id"])


def test_an_occupant_nobody_archived_is_refused() -> None:
    surface = NicheMap([niche("a", ["C1", "C2"])])
    rows = [entry("C1", surface.niche_ids()[0])]

    error = refused(
        lambda: build_map_agreement_record(niche_map=surface, archive_entries=rows),
        "OCCUPANT_UNARCHIVED",
    )

    assert error.context["findings"][0]["candidate_id"] == "C2"


def test_an_elite_with_no_archive_entry_is_refused() -> None:
    """A cell's best result existing only on the map is the map lying alone."""
    surface = NicheMap([niche("a", ["C1", "C2"], elite_id="C2")])
    rows = [entry("C1", surface.niche_ids()[0]), entry("C2", surface.niche_ids()[0])]
    rows = [row for row in rows if row["candidate_id"] != "C2"]

    error = refused(
        lambda: build_map_agreement_record(niche_map=surface, archive_entries=rows),
        "ELITE_UNARCHIVED",
    )
    codes = error.context["finding_codes"]

    assert "ELITE_UNARCHIVED" in codes and "OCCUPANT_UNARCHIVED" in codes


def test_an_elite_outside_its_own_cell_is_refused() -> None:
    """`NicheMap` accepts pre-built cells, so the rule is re-checked here."""
    cell = niche("a", ["C1"], elite_id="C1")
    cell["elite_id"] = "C9"
    cell["niche_hash"] = hash_excluding(cell, "niche_hash")
    surface = NicheMap([cell])

    findings = map_agreement_findings(
        niche_map=surface, archive_entries=[entry("C1", cell["niche_id"])]
    )

    assert [row["code"] for row in findings] == [
        "ELITE_NOT_OCCUPANT",
        "ELITE_UNARCHIVED",
    ]
    assert findings[0]["occupant_ids"] == ["C1"]


def test_two_entries_claiming_one_candidate_are_refused_before_comparison() -> None:
    surface = board()
    rows = entries(surface)
    duplicate = entry(
        rows[0]["candidate_id"], rows[0]["niche_id"], archive_entry_id="AE-DUP"
    )

    error = refused(
        lambda: map_agreement_findings(
            niche_map=surface, archive_entries=[*rows, duplicate]
        ),
        "ARCHIVE_ENTRY_DUPLICATED",
    )

    assert error.context["archive_entry_ids"] == ["AE-C1", "AE-DUP"]


def test_a_refusal_names_every_divergent_pair_at_once() -> None:
    surface = board()
    rows = [row for row in entries(surface) if row["candidate_id"] not in {"C2", "D1"}]

    error = refused(
        lambda: build_map_agreement_record(niche_map=surface, archive_entries=rows),
        "ELITE_UNARCHIVED",
    )

    assert len(error.context["findings"]) == 3
    assert sorted(
        row["candidate_id"]
        for row in error.context["findings"]
        if "candidate_id" in row
    ) == ["C2", "D1"]


def test_a_non_mapping_archive_entry_is_refused() -> None:
    surface = board()

    refused(
        lambda: map_agreement_findings(
            niche_map=surface, archive_entries=["not-an-entry"]
        ),
        "INPUT_INVALID",
    )


# --- ranking separation ----------------------------------------------------


def test_a_coverage_ratio_alone_cannot_promote() -> None:
    surface = board()
    coverage_map = coverage(surface)

    error = refused(
        audit(
            [
                figure_citation(
                    coverage_map["map_id"],
                    "coverage_ratio",
                    coverage_map["coverage_ratio"],
                )
            ],
            coverage_map=coverage_map,
        ),
        "PROMOTION_AUTHORITY_ABSENT",
    )

    assert error.context["cited_ranking_figures"] == ["coverage_ratio"]


def test_an_entropy_figure_alone_cannot_promote() -> None:
    report = diversity()

    error = refused(
        audit(
            [
                figure_citation(
                    report["report_id"], "lineage_entropy", report["lineage_entropy"]
                )
            ],
            diversity_report=report,
        ),
        "PROMOTION_AUTHORITY_ABSENT",
    )

    assert error.context["cited_ranking_figures"] == ["lineage_entropy"]


def test_a_combined_score_alone_cannot_promote() -> None:
    """The scalar EF4-I45 is actually about, cited from no map record at all."""
    error = refused(
        audit([figure_citation("SCORE-1", "combined_score", 0.97)]),
        "PROMOTION_AUTHORITY_ABSENT",
    )

    assert error.context["cited_ranking_figures"] == ["combined_score"]


def test_a_request_citing_nothing_cannot_promote() -> None:
    error = refused(audit([]), "PROMOTION_AUTHORITY_ABSENT")

    assert error.context["cited_ranking_figures"] == []


def test_a_canonical_artifact_that_is_not_a_gate_carries_no_authority() -> None:
    refused(
        audit([authority_citation("FV-1", NON_AUTHORITY_SCHEMA)]),
        "PROMOTION_AUTHORITY_ABSENT",
    )


def test_a_misquoted_coverage_ratio_is_refused() -> None:
    surface = board()
    coverage_map = coverage(surface)

    error = refused(
        audit(
            [
                authority_citation(),
                figure_citation(coverage_map["map_id"], "coverage_ratio", 0.5),
            ],
            coverage_map=coverage_map,
        ),
        "RANKING_FIGURE_FORGED",
    )

    assert error.context["published"] == coverage_map["coverage_ratio"]
    assert error.context["quoted"] == 0.5


def test_an_integer_figure_quoted_as_a_float_is_refused() -> None:
    """Canonical comparison, so 1 and 1.0 are not silently the same figure."""
    surface = board()
    coverage_map = coverage(surface)

    refused(
        audit(
            [
                authority_citation(),
                figure_citation(
                    coverage_map["map_id"],
                    "total_niches",
                    float(coverage_map["total_niches"]),
                ),
            ],
            coverage_map=coverage_map,
        ),
        "RANKING_FIGURE_FORGED",
    )


def test_a_figure_from_a_record_the_gate_was_not_given_is_unresolved() -> None:
    refused(
        audit(
            [
                authority_citation(),
                figure_citation("QDM-ELSEWHERE", "coverage_ratio", 0.5),
            ]
        ),
        "CITATION_UNRESOLVED",
    )


def test_a_figure_a_record_does_not_publish_is_unresolved() -> None:
    report = diversity()

    refused(
        audit(
            [authority_citation(), figure_citation(report["report_id"], "map_id", "x")],
            diversity_report=report,
        ),
        "CITATION_UNRESOLVED",
    )


def test_a_schema_the_registry_does_not_declare_is_unresolved() -> None:
    refused(
        audit([authority_citation("X-1", "not-a-canonical-schema")]),
        "CITATION_UNRESOLVED",
    )


def test_a_citation_that_is_both_a_figure_and_an_artifact_is_refused() -> None:
    refused(
        audit(
            [
                {
                    "artifact_id": "GD-1",
                    "figure": "coverage_ratio",
                    "schema": "gate-decision",
                }
            ]
        ),
        "INPUT_INVALID",
    )


def test_a_citation_that_is_neither_is_refused() -> None:
    refused(audit([{"note": "trust me"}]), "INPUT_INVALID")


def test_a_figure_citation_without_a_value_is_refused() -> None:
    surface = board()
    coverage_map = coverage(surface)

    refused(
        audit(
            [
                authority_citation(),
                {"figure": "coverage_ratio", "source_id": coverage_map["map_id"]},
            ],
            coverage_map=coverage_map,
        ),
        "INPUT_INVALID",
    )


def test_a_schema_citation_without_an_artifact_is_refused() -> None:
    refused(audit([{"schema": "gate-decision"}]), "INPUT_INVALID")


def test_a_request_missing_a_declared_field_is_refused() -> None:
    surface = board()

    refused(
        lambda: audit_promotion_request(
            request={"candidate_id": "C1", "citations": []},
            coverage_map=coverage(surface),
            diversity_report=diversity(),
        ),
        "INPUT_INVALID",
    )


def test_citations_that_are_not_a_sequence_are_refused() -> None:
    surface = board()

    refused(
        lambda: audit_promotion_request(
            request={"candidate_id": "C1", "citations": "GD-1", "request_id": "PR-1"},
            coverage_map=coverage(surface),
            diversity_report=diversity(),
        ),
        "INPUT_INVALID",
    )


def test_an_authority_schema_the_registry_dropped_fails_loudly(monkeypatch) -> None:
    """A silently un-guarded separation check is worse than a broken one."""
    monkeypatch.setattr(
        gate_module, "AUTHORITY_SCHEMA_NAMES", ("gate-decision", "no-such-schema")
    )

    error = refused(audit([authority_citation()]), "AUTHORITY_SCHEMA_UNKNOWN")

    assert error.context["missing"] == ["no-such-schema"]


def test_a_coverage_map_and_report_from_different_generations_are_refused() -> None:
    surface = board()

    error = refused(
        audit(
            [authority_citation()],
            coverage_map=coverage(surface, generation=4),
            diversity_report=diversity(generation=3),
        ),
        "MAP_GENERATION_STALE",
    )

    assert error.context == {"coverage_generation": 4, "report_generation": 3}


def test_a_tampered_coverage_map_is_refused_before_any_figure_is_read() -> None:
    surface = board()
    coverage_map = coverage(surface)
    coverage_map["coverage_ratio"] = 0.5

    refused(
        audit([authority_citation()], coverage_map=coverage_map),
        "RECORD_IDENTITY_FORGED",
    )


# --- stale propagation -----------------------------------------------------


def test_a_map_built_for_another_generation_is_not_served() -> None:
    surface = board()
    source = revision(surface, generation=3)

    error = refused(
        lambda: require_current_revision(
            revision=source,
            serving_generation=5,
            derived_records=derived(surface, source),
        ),
        "MAP_GENERATION_STALE",
    )
    cascade = error.context["cascade"]

    assert cascade["counts"]["rebuild_required"] == 2
    assert [row["record_kind"] for row in cascade["rebuild_required"]] == [
        "blast_radius",
        "coverage_map",
    ]


def test_serving_an_older_generation_is_also_a_mismatch() -> None:
    surface = board()
    source = revision(surface, generation=5)

    error = refused(
        lambda: require_current_revision(revision=source, serving_generation=4),
        "MAP_GENERATION_STALE",
    )

    assert error.context["cascade"]["serving_generation"] == 4


def test_a_downstream_record_with_no_declared_source_is_refused() -> None:
    surface = board()
    source = revision(surface)
    binding = bind_derived_record(
        record=coverage(surface), record_kind="coverage_map", revision=source
    )
    del binding["source_revision_hash"]

    error = refused(
        lambda: build_staleness_cascade(
            revision=source, serving_generation=4, derived_records=[binding]
        ),
        "DERIVATION_UNRECORDED",
    )

    assert error.context["missing"] == ["source_revision_hash"]


def test_a_downstream_record_naming_an_empty_source_is_refused() -> None:
    surface = board()
    source = revision(surface)
    binding = bind_derived_record(
        record=coverage(surface), record_kind="coverage_map", revision=source
    )
    binding["source_revision_hash"] = "   "

    refused(
        lambda: build_staleness_cascade(
            revision=source, serving_generation=4, derived_records=[binding]
        ),
        "DERIVATION_UNRECORDED",
    )


def test_a_revision_that_does_not_re_derive_its_hash_is_refused() -> None:
    surface = board()
    source = revision(surface)
    source["generation"] = 99

    refused(
        lambda: require_current_revision(revision=source, serving_generation=99),
        "RECORD_IDENTITY_FORGED",
    )


def test_a_derived_record_that_does_not_re_derive_its_hash_cannot_be_bound() -> None:
    surface = board()
    source = revision(surface)
    coverage_map = coverage(surface)
    coverage_map["occupied_niches"] = 99

    refused(
        lambda: bind_derived_record(
            record=coverage_map, record_kind="coverage_map", revision=source
        ),
        "RECORD_IDENTITY_FORGED",
    )


def test_an_untracked_derived_record_kind_is_refused() -> None:
    surface = board()
    source = revision(surface)

    error = refused(
        lambda: bind_derived_record(
            record=coverage(surface), record_kind="hunch", revision=source
        ),
        "INPUT_INVALID",
    )

    assert "coverage_map" in error.context["declared"]


def test_a_revision_without_an_integer_generation_is_refused() -> None:
    surface = board()

    refused(
        lambda: build_map_revision(
            niche_map=surface, evolution_run_id=RUN_ID, generation="3"
        ),
        "INPUT_INVALID",
    )


def test_a_cascade_served_a_non_integer_generation_is_refused() -> None:
    surface = board()
    source = revision(surface)

    refused(
        lambda: build_staleness_cascade(revision=source, serving_generation=True),
        "INPUT_INVALID",
    )


def test_a_revision_that_publishes_no_hash_is_refused() -> None:
    surface = board()
    source = revision(surface)
    del source["revision_hash"]

    refused(
        lambda: build_staleness_cascade(revision=source, serving_generation=3),
        "INPUT_INVALID",
    )


def test_a_refused_gate_leaves_every_input_untouched() -> None:
    surface = board()
    source = revision(surface, generation=3)
    rows = [row for row in entries(surface) if row["candidate_id"] != "D1"]
    bindings = derived(surface, source)
    before = copy.deepcopy((rows, source, bindings))

    with pytest.raises(CartographyIntegrationError):
        build_map_agreement_record(niche_map=surface, archive_entries=rows)
    with pytest.raises(CartographyIntegrationError):
        require_current_revision(
            revision=source, serving_generation=4, derived_records=bindings
        )

    assert (rows, source, bindings) == before
