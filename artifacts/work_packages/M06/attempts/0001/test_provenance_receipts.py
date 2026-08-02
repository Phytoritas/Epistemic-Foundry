"""provenance_and_receipt_audit — every gate record proves itself.

An integration gate that cannot be re-checked is just another assertion.  So
each record here re-derives its own hash from exactly the fields it publishes,
a derived record's binding carries the source revision's hash rather than a
claim about it, and every refusal context is serialisable evidence rather than
a formatted sentence.  The gate reads no clock, so the same inputs produce
byte-identical records; the only non-determinism it may hold is minting an
identifier the caller declined to supply.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from epistemic_foundry.cartography.v4_m06 import (
    CartographyIntegrationError,
    audit_promotion_request,
    bind_derived_record,
    build_map_agreement_record,
    build_map_revision,
    build_staleness_cascade,
    require_current_revision,
)
from epistemic_foundry.cartography.v4_m06 import gate as gate_module
from epistemic_foundry.domain.hashing import hash_excluding
from fixtures import (
    RUN_ID,
    authority_citation,
    board,
    coverage,
    derived,
    diversity,
    entries,
    figure_citation,
    promotion_request,
    revision,
)

GATE = Path(gate_module.__file__)


def agreement(record_id: str = "MAR-P") -> dict:
    surface = board()
    return build_map_agreement_record(
        niche_map=surface, archive_entries=entries(surface), record_id=record_id
    )


def cascade(serving_generation: int = 4, cascade_id: str = "MSC-P") -> dict:
    surface = board()
    source = revision(surface, generation=3)
    return build_staleness_cascade(
        revision=source,
        serving_generation=serving_generation,
        derived_records=derived(surface, source),
        cascade_id=cascade_id,
    )


def separation(record_id: str = "RSR-P") -> dict:
    surface = board()
    coverage_map = coverage(surface)
    return audit_promotion_request(
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
        record_id=record_id,
    )


def test_every_record_re_derives_its_own_hash() -> None:
    surface = board()
    for record, field in (
        (agreement(), "record_hash"),
        (
            build_map_revision(
                niche_map=surface,
                evolution_run_id=RUN_ID,
                generation=3,
                revision_id="MRV-P",
            ),
            "revision_hash",
        ),
        (cascade(), "cascade_hash"),
        (separation(), "record_hash"),
    ):
        assert record[field] == hash_excluding(record, field)


def test_changing_one_published_field_changes_the_hash() -> None:
    record = agreement()
    altered = {**record, "archived_candidate_ids": []}

    assert hash_excluding(altered, "record_hash") != record["record_hash"]


def test_a_revision_hash_follows_the_cells_it_pins() -> None:
    from epistemic_foundry.cartography.v4_m05 import NicheMap
    from fixtures import niche

    first = build_map_revision(
        niche_map=NicheMap([niche("a", ["C1"], elite_id="C1")]),
        evolution_run_id=RUN_ID,
        generation=3,
        revision_id="MRV-P1",
    )
    second = build_map_revision(
        niche_map=NicheMap([niche("a", ["C1", "C2"], elite_id="C1")]),
        evolution_run_id=RUN_ID,
        generation=3,
        revision_id="MRV-P1",
    )

    assert first["revision_hash"] != second["revision_hash"]


def test_a_binding_carries_the_source_revision_hash_exactly() -> None:
    surface = board()
    source = revision(surface)
    coverage_map = coverage(surface)
    binding = bind_derived_record(
        record=coverage_map, record_kind="coverage_map", revision=source
    )

    assert binding["source_revision_hash"] == source["revision_hash"]
    assert binding["record_hash"] == coverage_map["map_hash"]


def test_the_cascade_rebuild_list_is_re_derivable_from_the_bindings() -> None:
    surface = board()
    source = revision(surface, generation=3)
    bindings = derived(surface, source)
    built = build_staleness_cascade(
        revision=source,
        serving_generation=4,
        derived_records=bindings,
        cascade_id="MSC-P2",
    )

    assert sorted(row["record_hash"] for row in built["rebuild_required"]) == sorted(
        row["record_hash"] for row in bindings
    )


def test_the_same_inputs_produce_byte_identical_records() -> None:
    assert agreement() == agreement()
    assert cascade() == cascade()
    assert separation() == separation()


def test_an_identifier_is_minted_only_when_the_caller_supplies_none() -> None:
    surface = board()
    minted = build_map_revision(
        niche_map=surface, evolution_run_id=RUN_ID, generation=3
    )
    named = build_map_revision(
        niche_map=surface,
        evolution_run_id=RUN_ID,
        generation=3,
        revision_id="MRV-P3",
    )

    assert minted["revision_id"] != named["revision_id"]
    assert minted["occupancy"] == named["occupancy"]


def test_the_gate_reads_no_clock() -> None:
    """A timestamp the caller did not supply makes a record unreproducible."""
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(str(node.module))
            imported.update(alias.name for alias in node.names)

    assert not imported & {"datetime", "time", "random", "utc_now_iso", "now"}


def test_every_refusal_context_is_serialisable_evidence() -> None:
    surface = board()
    source = revision(surface, generation=3)
    rows = [row for row in entries(surface) if row["candidate_id"] != "D1"]

    contexts = []
    with pytest.raises(CartographyIntegrationError) as caught:
        build_map_agreement_record(niche_map=surface, archive_entries=rows)
    contexts.append(caught.value.context)
    with pytest.raises(CartographyIntegrationError) as caught:
        require_current_revision(
            revision=source,
            serving_generation=9,
            derived_records=derived(surface, source),
        )
    contexts.append(caught.value.context)
    with pytest.raises(CartographyIntegrationError) as caught:
        audit_promotion_request(
            request=promotion_request([]),
            coverage_map=coverage(surface),
            diversity_report=diversity(),
        )
    contexts.append(caught.value.context)

    for context in contexts:
        assert json.loads(json.dumps(context, ensure_ascii=False, sort_keys=True)) == (
            context
        )


def test_a_refusal_carries_the_reason_its_code_exists() -> None:
    surface = board()
    rows = [row for row in entries(surface) if row["candidate_id"] != "C2"]

    with pytest.raises(CartographyIntegrationError) as caught:
        build_map_agreement_record(niche_map=surface, archive_entries=rows)

    for finding in caught.value.context["findings"]:
        assert finding["reason"] == gate_module.FINDING_CODES[finding["code"]]


def test_the_stale_cascade_is_the_same_evidence_whether_or_not_it_refused() -> None:
    """The pass case publishes the cascade too, so it can be checked at all."""
    surface = board()
    source = revision(surface, generation=3)
    bindings = derived(surface, source)
    served = require_current_revision(
        revision=source, serving_generation=3, derived_records=bindings
    )
    with pytest.raises(CartographyIntegrationError) as caught:
        require_current_revision(
            revision=source, serving_generation=4, derived_records=bindings
        )
    refused_cascade = caught.value.context["cascade"]

    assert served["bound_records"] == refused_cascade["bound_records"]
    assert served["revision_hash"] == refused_cascade["revision_hash"]
    assert served["rebuild_required"] == []
    assert refused_cascade["rebuild_required"] == served["bound_records"]
