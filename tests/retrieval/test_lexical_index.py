"""Tests for the FTS5 lexical index and the lanes built on it.

The corpus here is synthetic and lives in ``tmp_path``. Nothing in this file
reads the paper corpus: a test that depends on 1,281 real documents would stop
being a test of the index and start being a test of whatever those documents
happen to say this week.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epistemic_foundry.cli.main import EXIT_CODES
from epistemic_foundry.cli.main import main as cli_main
from epistemic_foundry.contracts import ContractViolation, validate_artifact
from epistemic_foundry.domain.status import ExitStatus
from epistemic_foundry.retrieval import lanes, lexical_index
from epistemic_foundry.retrieval.search_state import LaneCoverageFailure, SearchState

STARTED_AT = "2026-08-02T12:00:00Z"
FINISHED_AT = "2026-08-02T12:00:01Z"
PLAN_HASH = "sha256:" + "a" * 64
POLICY_HASH = "sha256:" + "b" * 64

DOC_HEXOSE_STOMATA = (
    "# Hexose and guard cells\n\n"
    "Hexose accumulation in the apoplast reduces stomatal conductance in the "
    "morning. Hexose sensing by hexokinase links sugar status to stomatal "
    "aperture (Farquhar et al., 1980). Later work on hexose transport confirmed "
    "the hexose effect (Kim and Lieth, 2003).\n"
)
DOC_STARCH = (
    "# Overnight starch turnover\n\n"
    "Night temperature limits structural carbohydrate conversion. A single "
    "mention of hexose appears here, far from any stomatal discussion. "
    + ("Filler sentence about starch mobilisation and sink activity. " * 40)
    + "Stomatal conductance is discussed only at the very end of this document "
    "(Farquhar et al., 1980).\n"
)
DOC_UNRELATED = (
    "# Root hydraulics\n\n"
    "Aquaporin expression governs root hydraulic conductivity under drought "
    "(Steudle and Peterson, 1998). No sugar chemistry is discussed.\n"
)


def write_corpus(root: Path, documents: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for document_id, body in documents.items():
        (root / f"{document_id}.md").write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return write_corpus(
        tmp_path / "corpus",
        {
            "doc_hexose": DOC_HEXOSE_STOMATA,
            "doc_starch": DOC_STARCH,
            "doc_unrelated": DOC_UNRELATED,
        },
    )


@pytest.fixture
def index(corpus: Path, tmp_path: Path) -> tuple[Path, dict]:
    db_path = tmp_path / "index" / "lexical.db"
    stats = lexical_index.build_index(corpus, db_path)
    return db_path, stats


def make_context(stats: dict, **overrides) -> lanes.LaneContext:
    kwargs = {
        "run_id": "RUN-TEST",
        "query_plan_id": "QP-TEST",
        "plan_hash": PLAN_HASH,
        "policy_bundle_hash": POLICY_HASH,
        "capability_lease_id": "LEASE-TEST",
        "cutoff_policy_id": "CUTOFF-TOP-K",
        "lane_decision_evidence_ids": ("EV-LANE-DECISION-1",),
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
    }
    kwargs.update(overrides)
    return lanes.LaneContext.from_index_stats(stats, **kwargs)


# --------------------------------------------------------------------------
# Build determinism and corpus snapshot identity
# --------------------------------------------------------------------------


def test_build_reports_the_documents_it_actually_indexed(index) -> None:
    _, stats = index
    assert stats["document_count"] == 3
    assert stats["total_chars"] == sum(
        len(body) for body in (DOC_HEXOSE_STOMATA, DOC_STARCH, DOC_UNRELATED)
    )
    assert stats["snapshot_id"].startswith("CSNAP-")
    assert stats["corpus_snapshot_hash"].startswith("sha256:")
    assert len(stats["corpus_snapshot_hash"]) == len("sha256:") + 64
    assert stats["rebuilt"] is True


def test_same_corpus_yields_the_same_snapshot_id(corpus: Path, tmp_path: Path) -> None:
    first = lexical_index.build_index(corpus, tmp_path / "a.db")
    second = lexical_index.build_index(corpus, tmp_path / "b.db")

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["corpus_snapshot_hash"] == second["corpus_snapshot_hash"]
    # Every deterministic statistic must agree, not only the snapshot.
    for key in ("document_count", "total_chars", "citation_edge_count"):
        assert first[key] == second[key]


def test_editing_one_document_changes_the_snapshot(
    corpus: Path, tmp_path: Path
) -> None:
    before = lexical_index.build_index(corpus, tmp_path / "a.db")
    (corpus / "doc_unrelated.md").write_text(
        DOC_UNRELATED + "One more line.\n", encoding="utf-8"
    )
    after = lexical_index.build_index(corpus, tmp_path / "b.db")

    assert before["corpus_snapshot_hash"] != after["corpus_snapshot_hash"]


def test_snapshot_id_follows_the_run_script_convention(corpus: Path) -> None:
    documents = lexical_index.load_corpus(corpus)
    digest = lexical_index.corpus_snapshot_digest(documents)
    snapshot_id, snapshot_hash = lexical_index.snapshot_identifiers(documents)

    assert snapshot_id == f"CSNAP-{digest[:32]}"
    assert snapshot_hash == f"sha256:{digest}"


def test_unchanged_corpus_reuses_the_index_instead_of_rebuilding(
    corpus: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "lexical.db"
    first = lexical_index.build_index(corpus, db_path)
    second = lexical_index.build_index(corpus, db_path)

    assert first["rebuilt"] is True
    assert second["rebuilt"] is False
    assert first["corpus_snapshot_hash"] == second["corpus_snapshot_hash"]


def test_changed_corpus_forces_a_rebuild_of_an_existing_index(
    corpus: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "lexical.db"
    lexical_index.build_index(corpus, db_path)
    (corpus / "doc_new.md").write_text(
        "A brand new hexose document.\n", encoding="utf-8"
    )
    rebuilt = lexical_index.build_index(corpus, db_path)

    assert rebuilt["rebuilt"] is True
    assert rebuilt["document_count"] == 4
    assert lexical_index.read_index_stats(db_path)["document_count"] == 4


def test_nested_paper_layout_is_indexed_by_directory_name(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    (root / "001_first_paper").mkdir(parents=True)
    (root / "001_first_paper" / "text.md").write_text(
        DOC_HEXOSE_STOMATA, encoding="utf-8"
    )
    stats = lexical_index.build_index(root, tmp_path / "nested.db")

    assert stats["document_count"] == 1
    rows = lexical_index.query(tmp_path / "nested.db", "hexose", limit=5)
    assert [row["document_id"] for row in rows] == ["001_first_paper"]


def test_empty_corpus_fails_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(lexical_index.LexicalIndexError):
        lexical_index.build_index(empty, tmp_path / "empty.db")


# --------------------------------------------------------------------------
# Query determinism, ranking, and offsets
# --------------------------------------------------------------------------


def test_query_is_byte_identical_across_repeated_runs(index) -> None:
    db_path, _ = index
    first = lexical_index.query(db_path, "hexose", limit=10)
    second = lexical_index.query(db_path, "hexose", limit=10)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_query_over_two_identical_builds_agrees(corpus: Path, tmp_path: Path) -> None:
    lexical_index.build_index(corpus, tmp_path / "a.db")
    lexical_index.build_index(corpus, tmp_path / "b.db")
    first = lexical_index.query(tmp_path / "a.db", "hexose", limit=10)
    second = lexical_index.query(tmp_path / "b.db", "hexose", limit=10)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_bm25_ranks_the_denser_shorter_document_first(index) -> None:
    db_path, _ = index
    rows = lexical_index.query(db_path, "hexose", limit=10)

    assert [row["document_id"] for row in rows] == ["doc_hexose", "doc_starch"]
    assert rows[0]["bm25_score"] > rows[1]["bm25_score"]
    assert [row["rank"] for row in rows] == [1, 2]


def test_a_term_absent_from_the_corpus_returns_no_rows(index) -> None:
    db_path, _ = index
    assert lexical_index.query(db_path, "abscisic", limit=10) == []


def test_ranking_is_ordered_by_score_then_document_id(index) -> None:
    db_path, _ = index
    rows = lexical_index.query(db_path, "hexose OR stomatal", limit=10)
    ordering = [(-row["bm25_score"], row["document_id"]) for row in rows]

    assert ordering == sorted(ordering)


def test_offsets_re_extract_the_matched_text_exactly(index, corpus: Path) -> None:
    db_path, _ = index
    rows = lexical_index.query(db_path, '"stomatal conductance"', limit=10)
    assert rows

    for row in rows:
        body = lexical_index.read_document_text(corpus / f"{row['document_id']}.md")
        assert row["snippets"]
        for span in row["snippets"]:
            assert body[span["char_start"] : span["char_end"]] == span["text"]
            assert body[span["context_start"] : span["context_end"]] == span["context"]
            assert span["text"].lower() == "stomatal conductance"


def test_context_windows_are_not_normalised(index, corpus: Path) -> None:
    db_path, _ = index
    row = lexical_index.query(db_path, "hexose", limit=1)[0]
    body = lexical_index.read_document_text(corpus / f"{row['document_id']}.md")
    span = row["snippets"][0]

    # Newlines are preserved; a "cleaned" context would no longer re-extract.
    assert body[span["context_start"] : span["context_end"]] == span["context"]


def test_matched_terms_only_lists_terms_that_were_located(index) -> None:
    db_path, _ = index
    rows = lexical_index.query(db_path, "hexose OR aquaporin", limit=10)
    located = {row["document_id"]: row["matched_terms"] for row in rows}

    # Each document reports only the query term it actually contains; a term the
    # locator could not find is absent rather than listed as matched.
    assert located["doc_hexose"] == ["hexose"]
    assert located["doc_unrelated"] == ["aquaporin"]


def test_prefix_terms_are_located(index) -> None:
    db_path, _ = index
    rows = lexical_index.query(db_path, "stomat*", limit=10)

    assert rows
    assert all(row["snippets"] for row in rows)


def test_invalid_fts_expression_fails_closed(index) -> None:
    db_path, _ = index
    with pytest.raises(lexical_index.LexicalIndexError):
        lexical_index.query(db_path, "hexose AND AND", limit=5)


def test_query_against_a_missing_index_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(lexical_index.LexicalIndexError):
        lexical_index.query(tmp_path / "nope.db", "hexose", limit=5)


def test_extract_query_terms_drops_operators_and_column_filters() -> None:
    terms = lexical_index.extract_query_terms('body:hexose AND "guard cell" OR stomat*')

    assert [(term.text, term.is_phrase, term.is_prefix) for term in terms] == [
        ("hexose", False, False),
        ("guard cell", True, False),
        ("stomat", False, True),
    ]


# --------------------------------------------------------------------------
# Citation extraction
# --------------------------------------------------------------------------


def test_citation_keys_are_normalised_and_span_bearing() -> None:
    keys = lexical_index.extract_citation_keys(DOC_HEXOSE_STOMATA)

    # The key is the first author, so "Kim and Lieth, 2003" normalises to kim:2003.
    assert set(keys) == {"farquhar:1980", "kim:2003"}
    entry = keys["farquhar:1980"]
    assert DOC_HEXOSE_STOMATA[
        entry["first_char_start"] : entry["first_char_end"]
    ].startswith("Farquhar")


def test_documents_are_coupled_by_a_shared_cited_work(index) -> None:
    db_path, _ = index
    coupled = lexical_index.documents_sharing_citation_keys(
        db_path, ["farquhar:1980"], exclude=["doc_hexose"], limit=10
    )

    assert [row["document_id"] for row in coupled] == ["doc_starch"]
    assert coupled[0]["shared_citation_keys"] == ["farquhar:1980"]


# --------------------------------------------------------------------------
# Lane-local exact deduplication
# --------------------------------------------------------------------------


def _hit(document_id: str, rank: int, *, locator: str = "p.md") -> dict:
    return {
        "canonical_source_key": document_id,
        "source_record_id": document_id,
        "source_locator": locator,
        "source_version": "v1",
        "source_snapshot_hash": "sha256:" + "c" * 64,
        "source_span_id": None,
        "raw_rank": rank,
        "raw_score": 1.0,
        "matched_terms": [],
        "matched_edges": [],
        "relation_direction": "NO_DIRECTION",
        "retrieval_explanation": "test hit",
    }


def test_exact_duplicates_are_collapsed_and_ranks_restamped() -> None:
    unique, duplicates = lanes.deduplicate_exact(
        [_hit("a", 1), _hit("b", 2), _hit("a", 3), _hit("c", 4)]
    )

    assert duplicates == 1
    assert [hit["canonical_source_key"] for hit in unique] == ["a", "b", "c"]
    assert [hit["raw_rank"] for hit in unique] == [1, 2, 3]


def test_a_different_locator_is_not_an_exact_duplicate() -> None:
    unique, duplicates = lanes.deduplicate_exact(
        [_hit("a", 1, locator="p.md#1"), _hit("a", 2, locator="p.md#2")]
    )

    assert duplicates == 0
    assert len(unique) == 2


# --------------------------------------------------------------------------
# RRF k=60
# --------------------------------------------------------------------------


def test_rrf_matches_a_hand_computed_example() -> None:
    fused = lanes.rrf_fuse(
        {
            "LEXICAL": ["doc_a", "doc_b", "doc_c"],
            "CITATION_GRAPH": ["doc_b", "doc_a"],
        }
    )

    expected = {
        "doc_a": 1 / 61 + 1 / 62,
        "doc_b": 1 / 62 + 1 / 61,
        "doc_c": 1 / 63,
    }
    scores = {
        row["document_id"] if "document_id" in row else row["key"]: row["rrf_score"]
        for row in fused
    }
    for key, value in expected.items():
        assert scores[key] == pytest.approx(value, rel=0, abs=1e-15)
    # doc_a and doc_b tie exactly; the tie breaks on the key, not on input order.
    assert [row["key"] for row in fused] == ["doc_a", "doc_b", "doc_c"]
    assert [row["rank"] for row in fused] == [1, 2, 3]


def test_rrf_k_is_sixty_by_default() -> None:
    assert lanes.RRF_K == 60
    fused = lanes.rrf_fuse({"LEXICAL": ["only"]})
    assert fused[0]["rrf_score"] == pytest.approx(1 / 61, rel=0, abs=1e-15)


def test_rrf_rejects_a_ranking_that_was_not_deduplicated() -> None:
    with pytest.raises(lanes.LaneContractError):
        lanes.rrf_fuse({"LEXICAL": ["doc_a", "doc_a"]})


def test_rrf_ranking_is_independent_of_channel_iteration_order() -> None:
    forward = lanes.rrf_fuse({"A": ["x", "y"], "B": ["y", "x"]})
    backward = lanes.rrf_fuse({"B": ["y", "x"], "A": ["x", "y"]})

    assert forward == backward


# --------------------------------------------------------------------------
# Lane execution, candidates, and receipts
# --------------------------------------------------------------------------


def test_lexical_lane_emits_schema_valid_candidates_and_receipt(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.lexical(db_path, context, expression="hexose")

    assert result.search_state is SearchState.SEARCHED_WITH_RESULTS
    assert result.candidates
    validate_artifact("search-lane-receipt", result.receipt)
    for candidate in result.candidates:
        validate_artifact("retrieval-candidate", candidate)
        assert candidate["lane"] == "lexical"
        assert candidate["retrieval_channels"] == ["LEXICAL"]
        assert candidate["fusion_method"] == "SINGLE_CHANNEL"
        assert candidate["multi_channel_verified"] is False


def test_lexical_candidates_carry_a_span_id_and_a_resolvable_locator(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.lexical(db_path, context, expression='"stomatal conductance"')

    for candidate in result.candidates:
        assert candidate["source_span_id"] is not None
        assert "#char=" in candidate["source_locator"]
        assert candidate["ranking_features"]["extraction_grounding_confidence"] == 1.0


def test_candidate_id_and_hash_are_content_addressed(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    first = lanes.lexical(db_path, context, expression="hexose").candidates
    second = lanes.lexical(db_path, context, expression="hexose").candidates

    assert [row["candidate_id"] for row in first] == [
        row["candidate_id"] for row in second
    ]
    assert [row["candidate_hash"] for row in first] == [
        row["candidate_hash"] for row in second
    ]
    assert all(row["candidate_id"].startswith("RC-") for row in first)


def test_a_lane_that_finds_nothing_reports_searched_none(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.lexical(db_path, context, expression="abscisic")

    assert result.search_state is SearchState.SEARCHED_NONE
    assert result.is_absence_of_evidence is True
    assert result.receipt["result_ids"] == []
    assert result.receipt["result_count"] == 0
    validate_artifact("search-lane-receipt", result.receipt)


def test_receipt_hash_covers_the_receipt_contents(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    receipt = lanes.lexical(db_path, context, expression="hexose").receipt
    tampered = dict(receipt)
    tampered["result_count"] = 99
    preimage = {k: v for k, v in tampered.items() if k != "receipt_hash"}

    assert lanes._sha256_object(preimage) != receipt["receipt_hash"]


def test_citation_lane_couples_documents_through_a_shared_reference(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.citation(db_path, context, seed_document_ids=["doc_hexose"])

    assert result.search_state is SearchState.SEARCHED_WITH_RESULTS
    assert [row["document_id"] for row in result.documents] == ["doc_starch"]
    validate_artifact("search-lane-receipt", result.receipt)
    for candidate in result.candidates:
        validate_artifact("retrieval-candidate", candidate)
        assert candidate["retrieval_channels"] == ["CITATION_GRAPH"]
        assert candidate["matched_edges"] == ["BIBLIOGRAPHIC_COUPLING:farquhar:1980"]


def test_citation_lane_excludes_its_own_seed(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.citation(db_path, context, seed_document_ids=["doc_hexose"])

    assert "doc_hexose" not in [row["document_id"] for row in result.documents]


def test_citation_lane_without_a_seed_or_key_fails_closed(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    with pytest.raises(lanes.LaneContractError):
        lanes.citation(db_path, context)


def test_entity_variable_requires_proximity_not_mere_co_membership(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.entity_variable(
        db_path,
        context,
        term_groups=[["hexose"], ["stomatal conductance"]],
        window_chars=200,
    )

    # Both documents contain both groups; only one has them within the window.
    assert result.diagnostics["documents_prefiltered"] == 2
    assert [row["document_id"] for row in result.documents] == ["doc_hexose"]
    validate_artifact("search-lane-receipt", result.receipt)
    for candidate in result.candidates:
        validate_artifact("retrieval-candidate", candidate)
        assert candidate["retrieval_channels"] == ["RELATION_GRAPH"]
        # Co-occurrence is symmetric; it never asserts an orientation.
        assert candidate["relation_direction"] == "UNRESOLVED"


def test_entity_variable_spans_re_extract_exactly(index, corpus: Path) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.entity_variable(
        db_path, context, term_groups=[["hexose"], ["stomatal conductance"]]
    )

    for row in result.documents:
        body = lexical_index.read_document_text(corpus / f"{row['document_id']}.md")
        for pair in row["cooccurrence_spans"]:
            assert body[pair["char_start"] : pair["char_end"]] == pair["text"]


def test_entity_variable_needs_two_groups(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    with pytest.raises(lanes.LaneContractError):
        lanes.entity_variable(db_path, context, term_groups=[["hexose"]])


def test_cutoff_and_duplicates_are_both_counted_as_excluded(index) -> None:
    db_path, stats = index
    context = make_context(stats, max_candidates=1)
    result = lanes.lexical(db_path, context, expression="hexose", limit=10)

    assert len(result.candidates) == 1
    assert result.cutoff_count == 1
    assert (
        result.receipt["excluded_count"] == result.duplicate_count + result.cutoff_count
    )


def test_multi_channel_candidates_use_rrf_k60(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    shared = _hit("doc_hexose", 1)
    candidates, _ = lanes.build_lane_candidates(
        context,
        "lexical",
        ["hexose"],
        {
            "LEXICAL": [shared],
            # Ranked second in the citation channel, behind a document that
            # channel found on its own.
            "CITATION_GRAPH": [_hit("doc_other", 1), dict(shared, raw_rank=2)],
        },
    )

    assert len(candidates) == 2
    candidate = next(
        row for row in candidates if row["canonical_source_key"] == "doc_hexose"
    )
    validate_artifact("retrieval-candidate", candidate)
    assert candidate["retrieval_channels"] == ["LEXICAL", "CITATION_GRAPH"]
    assert candidate["fusion_method"] == "RRF_K60"
    assert candidate["multi_channel_verified"] is True
    assert candidate["fusion_score"] == pytest.approx(1 / 61 + 1 / 62, rel=0, abs=1e-15)


# --------------------------------------------------------------------------
# Eleven-lane reconciliation
# --------------------------------------------------------------------------


def test_all_eleven_lanes_are_reconciled_in_canonical_order(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    results = [
        lanes.lexical(db_path, context, expression="hexose"),
        lanes.citation(db_path, context, seed_document_ids=["doc_hexose"]),
        lanes.entity_variable(
            db_path, context, term_groups=[["hexose"], ["stomatal conductance"]]
        ),
    ]
    reconciliation = lanes.reconcile_lanes(context, results)

    assert reconciliation["all_lane_reconciliation_count"] == 11
    assert reconciliation["lane_order"] == list(lanes.CANONICAL_LANES)
    assert [receipt["lane"] for receipt in reconciliation["receipts"]] == list(
        lanes.CANONICAL_LANES
    )
    for receipt in reconciliation["receipts"]:
        validate_artifact("search-lane-receipt", receipt)


def test_unimplemented_lanes_are_unsearched_sentinels_not_empty_results(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    reconciliation = lanes.reconcile_lanes(
        context, [lanes.lexical(db_path, context, expression="hexose")]
    )
    sentinels = {
        receipt["lane"]: receipt
        for receipt in reconciliation["receipts"]
        if receipt["receipt_kind"] == "SENTINEL"
    }

    assert set(sentinels) == set(lanes.CANONICAL_LANES) - {"lexical"}
    for lane, receipt in sentinels.items():
        assert receipt["search_state"] == "UNSEARCHED"
        # A sentinel with result_count 0 would be indistinguishable from a real
        # SEARCHED_NONE, which is exactly the inference this blocks.
        assert receipt["result_count"] is None
        assert receipt["result_ids"] is None
        assert receipt["corpus_snapshot_hash"] is None
        assert reconciliation["absence_explanations"][lane]


def test_unsearched_lanes_are_not_absence_of_evidence(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    reconciliation = lanes.reconcile_lanes(
        context,
        [
            lanes.lexical(db_path, context, expression="abscisic"),
            lanes.citation(db_path, context, citation_keys=["nobody:1899"]),
        ],
    )

    assert reconciliation["absence_of_evidence_lanes"] == ["lexical", "citation"]
    assert set(reconciliation["unsearched_lanes"]) == set(lanes.CANONICAL_LANES) - {
        "lexical",
        "citation",
    }
    assert reconciliation["coverage_summary"]["UNSEARCHED"] == 9
    assert reconciliation["coverage_summary"]["SEARCHED_NONE"] == 2


def test_release_origins_are_non_vector(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    reconciliation = lanes.reconcile_lanes(
        context,
        [
            lanes.lexical(db_path, context, expression="hexose"),
            lanes.citation(db_path, context, seed_document_ids=["doc_hexose"]),
        ],
    )

    assert reconciliation["released_channels"] == ["LEXICAL", "CITATION_GRAPH"]
    assert (
        set(reconciliation["non_vector_release_origins"])
        <= lanes.NON_VECTOR_RELEASE_ORIGINS
    )
    assert "SEMANTIC" not in reconciliation["released_channels"]
    assert reconciliation["run_ceiling"] == "PASS"


def test_missing_mandatory_lane_coverage_is_refused(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    reconciliation = lanes.reconcile_lanes(
        context, [lanes.lexical(db_path, context, expression="hexose")]
    )

    lanes.assert_lane_coverage(reconciliation, applicable=["lexical"])
    with pytest.raises(LaneCoverageFailure):
        lanes.assert_lane_coverage(
            reconciliation, applicable=["lexical", "counterevidence", "null"]
        )


def test_a_lane_cannot_file_two_receipts(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    result = lanes.lexical(db_path, context, expression="hexose")
    with pytest.raises(lanes.LaneContractError):
        lanes.reconcile_lanes(context, [result, result])


def test_sentinel_reason_must_come_from_the_closed_vocabulary(index) -> None:
    _, stats = index
    context = make_context(stats)
    with pytest.raises(lanes.LaneContractError):
        lanes.absent_lane_receipt(context, "semantic", sentinel_reason="NO_BACKEND")


def test_lane_decisions_must_cite_evidence(index) -> None:
    _, stats = index
    with pytest.raises(lanes.LaneContractError):
        make_context(stats, lane_decision_evidence_ids=())


def test_scope_vector_helper_is_schema_valid(index) -> None:
    _, stats = index
    context = make_context(stats)
    receipt = lanes.absent_lane_receipt(context, "semantic")
    validate_artifact("search-lane-receipt", receipt)

    execution = lanes.build_execution_receipt(
        context,
        "lexical",
        search_state=SearchState.SEARCHED_NONE,
        query_text='{"lane":"lexical"}',
        query_hash="sha256:" + "d" * 64,
        result_ids=[],
        excluded_count=0,
    )
    validate_artifact("search-lane-receipt", execution)


def test_a_hand_broken_receipt_is_rejected_by_the_schema(index) -> None:
    _, stats = index
    context = make_context(stats)
    receipt = lanes.absent_lane_receipt(context, "semantic")
    receipt["result_count"] = 0  # a sentinel claiming a real zero-result search

    with pytest.raises(ContractViolation):
        validate_artifact("search-lane-receipt", receipt)


def test_cross_lane_fusion_uses_every_executed_channel(index) -> None:
    db_path, stats = index
    context = make_context(stats)
    fused = lanes.fuse_lane_documents(
        [
            lanes.lexical(db_path, context, expression="hexose"),
            lanes.citation(db_path, context, seed_document_ids=["doc_hexose"]),
        ]
    )
    channels = {channel for row in fused for channel in row["channel_ranks"]}

    assert channels == {"LEXICAL", "CITATION_GRAPH"}
    assert [row["rank"] for row in fused] == list(range(1, len(fused) + 1))


# --------------------------------------------------------------------------
# CLI surface and typed exit codes
# --------------------------------------------------------------------------


LANE_BINDINGS = [
    "--run-id",
    "RUN-CLI",
    "--query-plan-id",
    "QP-CLI",
    "--plan-hash",
    PLAN_HASH,
    "--policy-bundle-hash",
    POLICY_HASH,
    "--lane-decision-evidence-id",
    "EV-1",
    "--started-at",
    STARTED_AT,
    "--finished-at",
    FINISHED_AT,
]


def test_cli_build_reports_the_snapshot(corpus: Path, tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "cli.db"
    code = cli_main(["--json", "retrieve", "build", str(corpus), str(db_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == EXIT_CODES[ExitStatus.PASS]
    assert payload["document_count"] == 3
    assert payload["corpus_snapshot_hash"].startswith("sha256:")
    assert db_path.is_file()


def test_cli_build_on_a_missing_corpus_fails(tmp_path: Path, capsys) -> None:
    code = cli_main(
        ["--json", "retrieve", "build", str(tmp_path / "nope"), str(tmp_path / "x.db")]
    )
    capsys.readouterr()
    assert code == EXIT_CODES[ExitStatus.FAIL]


def test_cli_query_without_an_index_is_blocked(tmp_path: Path, capsys) -> None:
    code = cli_main(
        [
            "--json",
            "retrieve",
            "query",
            str(tmp_path / "absent.db"),
            "--expression",
            "x",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    # Nothing is wrong with the request; the prerequisite is simply not there.
    assert code == EXIT_CODES[ExitStatus.BLOCKED]
    assert payload["outcome"] == "BLOCKED"


def test_cli_raw_query_returns_ranked_spans(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        ["--json", "retrieve", "query", str(db_path), "--expression", "hexose"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == EXIT_CODES[ExitStatus.PASS]
    assert payload["result_count"] == 2
    assert payload["results"][0]["document_id"] == "doc_hexose"
    assert payload["results"][0]["snippets"]


def test_cli_invalid_expression_fails(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        ["--json", "retrieve", "query", str(db_path), "--expression", "hexose AND AND"]
    )
    capsys.readouterr()
    assert code == EXIT_CODES[ExitStatus.FAIL]


def test_cli_lane_query_without_plan_bindings_fails(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        [
            "--json",
            "retrieve",
            "query",
            str(db_path),
            "--lane",
            "lexical",
            "--expression",
            "hexose",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == EXIT_CODES[ExitStatus.FAIL]
    assert "run_id" in payload["missing"]


def test_cli_lane_query_emits_receipts_for_all_eleven_lanes(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        [
            "--json",
            "retrieve",
            "query",
            str(db_path),
            "--lane",
            "lexical",
            "--expression",
            "hexose",
            *LANE_BINDINGS,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == EXIT_CODES[ExitStatus.PASS]
    assert payload["all_lane_reconciliation_count"] == 11
    assert payload["search_state"] == "SEARCHED_WITH_RESULTS"
    assert payload["non_vector_release_origins"] == ["LEXICAL"]
    assert len(payload["receipts"]) == 11
    assert payload["candidates"]


def test_cli_reports_an_unserved_lane_as_unsearched(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        [
            "--json",
            "retrieve",
            "query",
            str(db_path),
            "--lane",
            "semantic",
            *LANE_BINDINGS,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    # Asking for a lane this backend cannot serve is answered truthfully, not
    # with an empty result set that would license an absence claim.
    assert code == EXIT_CODES[ExitStatus.PASS]
    assert payload["search_state"] == "UNSEARCHED"
    assert payload["absence_of_evidence"] is False
    assert payload["candidates"] == []
    assert payload["diagnostics"]["absence_explanation"]


def test_cli_entity_variable_lane_accepts_pipe_separated_groups(index, capsys) -> None:
    db_path, _ = index
    code = cli_main(
        [
            "--json",
            "retrieve",
            "query",
            str(db_path),
            "--lane",
            "entity_variable",
            "--term-group",
            "hexose|glucose",
            "--term-group",
            "stomatal conductance",
            *LANE_BINDINGS,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == EXIT_CODES[ExitStatus.PASS]
    assert payload["lane"] == "entity_variable"
    assert payload["diagnostics"]["term_groups"] == [
        ["hexose", "glucose"],
        ["stomatal conductance"],
    ]
