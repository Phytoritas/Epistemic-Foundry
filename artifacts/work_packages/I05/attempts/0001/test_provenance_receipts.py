"""provenance_and_receipt_audit — every intake record proves itself.

A screening record, a screening report and a seed population each re-derive
their own hash from exactly the fields they publish; a genome hash re-derives
from the submitted document; the counts reconcile against the lists beside
them; and nothing carries a clock or a random draw the caller did not supply.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.intake.v4_i05 import (
    GENOME_KIND,
    bootstrap_seed_population,
    genome_signature,
    screen_genome,
    screen_submissions,
)
from fixtures import (
    SCREENED_AT,
    bootstrap_arguments,
    diverse_batch,
    genome,
    submission,
)

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/intake/v4_i05/screening.py"


def mixed_batch() -> list:
    return [*diverse_batch(), submission(genome("HG-4", falsifier_gene_ids=[]))]


def test_the_record_hash_re_derives_from_the_published_fields() -> None:
    record = screen_genome(genome(), genome_kind=GENOME_KIND)

    assert record["record_hash"] == hash_excluding(dict(record), "record_hash")


def test_the_report_hash_re_derives_from_the_published_fields() -> None:
    report = screen_submissions(
        mixed_batch(), screened_at=SCREENED_AT, report_id="GSR-P-1"
    )

    assert report["report_hash"] == hash_excluding(dict(report), "report_hash")


def test_the_population_hash_re_derives_from_the_published_fields() -> None:
    population = bootstrap_seed_population(**bootstrap_arguments())

    assert population["population_hash"] == hash_excluding(
        dict(population), "population_hash"
    )


def test_the_genome_hash_re_derives_from_the_submitted_document() -> None:
    document = genome("HG-7")

    record = screen_genome(document, genome_kind=GENOME_KIND)

    assert record["genome_hash"] == sha256_of_payload(document)


def test_the_signature_re_derives_from_the_submitted_document() -> None:
    document = genome("HG-7")

    record = screen_genome(document, genome_kind=GENOME_KIND)

    assert record["signature"] == genome_signature(document)


def test_the_report_counts_reconcile_with_its_own_records() -> None:
    report = screen_submissions(
        mixed_batch(), screened_at=SCREENED_AT, report_id="GSR-P-2"
    )

    admitted = [record for record in report["records"] if record["admitted"]]
    refused = [record for record in report["records"] if not record["admitted"]]
    assert report["counts"]["submitted"] == len(report["records"])
    assert report["counts"]["admitted"] == len(admitted)
    assert report["counts"]["refused"] == len(refused)
    assert report["counts"]["submitted"] == len(admitted) + len(refused)


def test_the_population_counts_reconcile_with_its_own_lineages() -> None:
    population = bootstrap_seed_population(
        **bootstrap_arguments(submissions=mixed_batch(), minimum_signature_diversity=3)
    )

    assert population["counts"]["seeded"] == len(population["seed_lineages"])
    assert population["counts"]["seeded"] == len(population["seed_genome_ids"])
    assert population["counts"]["admitted"] == population["counts"]["seeded"]
    assert (
        population["counts"]["submitted"]
        == population["counts"]["admitted"] + population["counts"]["refused"]
    )


def test_every_refusal_publishes_the_reason_its_code_declares() -> None:
    from epistemic_foundry.intake.v4_i05 import FINDING_CODES

    report = screen_submissions(
        mixed_batch(), screened_at=SCREENED_AT, report_id="GSR-P-3"
    )

    for record in report["records"]:
        assert record["reasons"] == {
            code: FINDING_CODES[code] for code in record["reason_codes"]
        }


def test_supplied_identifiers_make_every_record_reproducible() -> None:
    first = bootstrap_seed_population(**bootstrap_arguments())
    second = bootstrap_seed_population(**bootstrap_arguments())

    assert first == second
    assert first["population_hash"] == second["population_hash"]


def test_the_inputs_are_not_mutated() -> None:
    batch = mixed_batch()
    before = json.dumps(batch, sort_keys=True)

    bootstrap_seed_population(
        **bootstrap_arguments(submissions=batch, minimum_signature_diversity=3)
    )

    assert json.dumps(batch, sort_keys=True) == before


def test_the_engine_holds_no_clock_and_no_randomness() -> None:
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    called = {
        ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }

    assert "utc_now_iso" not in called
    assert not any(name.startswith("random.") for name in called)
    # `new_id` runs only when the caller declines to supply an identifier, so
    # determinism is in the caller's hands and the hash covers the identifier.
    assert "new_id" in called
