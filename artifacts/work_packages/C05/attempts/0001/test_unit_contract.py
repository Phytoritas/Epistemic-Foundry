"""unit_and_contract_tests — synthesized instances validate across the family.

One minimal instance is synthesized for every canonical member and validated
against its own schema, and the composites accept exactly what they claim to:
each genome kind is a candidate, each evaluator document belongs to the
authority surface, each archive document to the preservation record, and the
statistics and backend composites accept their assembled evidence objects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from c05_schema_bundle import FAMILIES, MUTABLE_SEARCH_SPACE, members
from instance_synthesis import synthesize
from test_schema_and_type import ROOT, load, registry


def canonical(name: str) -> dict:
    return json.loads(
        (ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
    )


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load(name), registry=registry())


def instance(name: str, salt: int = 0) -> object:
    return synthesize(canonical(name), name, salt=salt)


@pytest.mark.parametrize("name", sorted(members()))
def test_a_synthesized_instance_validates_against_its_own_schema(
    name: str,
) -> None:
    Draft202012Validator(canonical(name)).validate(instance(name))


@pytest.mark.parametrize("name", sorted(MUTABLE_SEARCH_SPACE))
def test_every_genome_kind_is_an_evolution_candidate(name: str) -> None:
    validator("evolution-candidate.schema.json").validate(instance(name))


@pytest.mark.parametrize("name", sorted(FAMILIES["evaluator"]["members"]))
def test_every_evaluator_document_is_on_the_authority_surface(name: str) -> None:
    validator("evaluator-authority-surface.schema.json").validate(instance(name))


@pytest.mark.parametrize("name", sorted(FAMILIES["archive"]["members"]))
def test_every_archive_document_is_a_preservation_record(name: str) -> None:
    validator("archive-preservation-record.schema.json").validate(instance(name))


def test_the_statistics_composite_accepts_the_full_correction_record() -> None:
    validator("adaptive-search-statistics.schema.json").validate(
        {
            "decision_stability_report": instance("decision-stability-report"),
            "multiple_testing_adjustment": instance("multiple-testing-adjustment"),
            "selective_inference_report": instance("selective-inference-report"),
            "sequential_testing_ledger": instance("sequential-testing-ledger"),
            "surrogate_triage_report": instance("surrogate-triage-report"),
        }
    )


def test_the_statistics_composite_accepts_the_minimum_correction_record() -> None:
    validator("adaptive-search-statistics.schema.json").validate(
        {
            "multiple_testing_adjustment": instance("multiple-testing-adjustment"),
            "selective_inference_report": instance("selective-inference-report"),
            "sequential_testing_ledger": instance("sequential-testing-ledger"),
        }
    )


def test_the_backend_composite_accepts_a_fully_pinned_import() -> None:
    validator("external-backend-binding.schema.json").validate(
        {
            "backend_manifest": instance("shinka-backend-manifest"),
            "imported_run": instance("imported-run-record"),
            "qualification": instance("backend-adapter-qualification"),
        }
    )


def test_synthesis_is_deterministic() -> None:
    for name in sorted(members()):
        assert instance(name) == instance(name), name


def test_salted_synthesis_still_validates() -> None:
    for name in sorted(MUTABLE_SEARCH_SPACE):
        Draft202012Validator(canonical(name)).validate(instance(name, salt=3))


def test_the_registry_resolves_every_member_id(tmp_path: Path) -> None:
    resolver = registry().resolver()

    for name in sorted(members()):
        ref = f"https://epistemic-foundry.local/schemas/{name}.schema.json"
        assert resolver.lookup(ref).contents["$id"] == ref
