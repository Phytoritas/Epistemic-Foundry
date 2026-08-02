"""provenance_and_receipt_audit — every record on the map proves itself.

A niche is bound to its coordinates by a derived id and to its content by a
hash; a diversity report and a blast radius re-derive their own hashes from
exactly the fields they publish, and the pair of entropy figures re-derives
one from the other.  Nothing carries a clock the caller did not supply.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

from epistemic_foundry.cartography.v4_m05 import (
    NicheMap,
    build_coverage_map,
    build_lineage_diversity_report,
    compute_blast_radius,
    niche_id_for,
)
from epistemic_foundry.domain.hashing import hash_excluding
from fixtures import RUN_ID, THRESHOLDS, models, niche, population

ROOT = Path(__file__).resolve().parents[5]
MAPPER = ROOT / "src/epistemic_foundry/cartography/v4_m05/mapper.py"


def report() -> dict:
    memory = population()
    return build_lineage_diversity_report(
        lineage=memory,
        evolution_run_id=RUN_ID,
        generation=3,
        model_attribution=models(memory),
        thresholds=THRESHOLDS,
        report_id="LDR-M05-P",
    )


def radius() -> dict:
    return compute_blast_radius(
        lineage=population(),
        niche_map=NicheMap([niche("a", ["C1", "C2"], elite_id="C1")]),
        candidate_id="C1",
    )


def test_the_niche_hash_re_derives_from_the_published_fields() -> None:
    record = niche("a", ["C1"], elite_id="C1")

    assert record["niche_hash"] == hash_excluding(dict(record), "niche_hash")


def test_the_niche_id_re_derives_from_the_published_coordinates() -> None:
    record = niche("a", ["C1"])

    assert record["niche_id"] == niche_id_for(record["axis_values"])


def test_the_report_hash_re_derives_from_the_published_fields() -> None:
    record = report()

    assert record["report_hash"] == hash_excluding(dict(record), "report_hash")


def test_the_radius_hash_re_derives_from_the_published_fields() -> None:
    record = radius()

    assert record["radius_hash"] == hash_excluding(dict(record), "radius_hash")


def test_the_map_hash_re_derives_from_the_published_fields() -> None:
    record = build_coverage_map(
        niche_map=NicheMap([niche("a", ["C1"])]),
        evolution_run_id=RUN_ID,
        generation=1,
        lineage_entropy=0.25,
        map_id="QDM-M05-P",
    )

    assert record["map_hash"] == hash_excluding(dict(record), "map_hash")


def test_the_entropy_pair_re_derives_one_from_the_other() -> None:
    record = report()

    assert record["effective_lineage_count"] == round(
        math.exp(record["lineage_entropy"]), 6
    )


def test_the_recommended_actions_re_derive_from_the_alerts() -> None:
    from epistemic_foundry.cartography.v4_m05 import INBREEDING_RULES

    record = report()

    assert record["recommended_actions"] == [
        INBREEDING_RULES[alert] for alert in record["inbreeding_alerts"]
    ]


def test_the_radius_counts_reconcile_with_its_lists() -> None:
    record = radius()

    assert record["counts"]["affected_candidates"] == len(
        record["affected_candidate_ids"]
    )
    assert record["counts"]["affected_niches"] == len(record["affected_niche_ids"])
    assert record["counts"]["affected_islands"] == len(record["affected_islands"])
    assert record["counts"]["elites_at_risk"] == len(record["elites_at_risk_niche_ids"])
    assert set(record["descendant_ids"]) | {record["candidate_id"]} == set(
        record["affected_candidate_ids"]
    )


def test_supplied_identifiers_make_every_record_reproducible() -> None:
    assert report() == report()
    assert radius() == radius()


def test_the_inputs_are_not_mutated() -> None:
    memory = population()
    attribution = models(memory)
    before = dict(attribution)
    cell = niche("a", ["C1"])
    cell_before = dict(cell)

    build_lineage_diversity_report(
        lineage=memory,
        evolution_run_id=RUN_ID,
        generation=1,
        model_attribution=attribution,
        thresholds=THRESHOLDS,
    )
    NicheMap([cell])

    assert attribution == before
    assert cell == cell_before


def test_the_mapper_holds_no_clock_and_no_randomness() -> None:
    tree = ast.parse(MAPPER.read_text(encoding="utf-8"))
    called = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }

    assert "utc_now_iso" not in called
    assert not any(name.startswith("random.") for name in called)
    # `new_id` runs only when the caller declines to supply an identifier, so
    # determinism is in the caller's hands and the hash covers the identifier.
    assert "new_id" in called
