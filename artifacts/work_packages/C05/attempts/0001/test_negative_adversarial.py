"""negative_and_adversarial_tests — authority cannot enter the mutable space.

The boundary EF4-I41 draws is exercised from the hostile side: evaluator,
holdout, promotion and archive documents are refused as candidates, adaptive
search evidence missing its correction records is refused (EF4-I53), an
unqualified backend import is refused (EF4-I63), and a bundle edited to widen
the mutable space or smuggle vocabulary is refused at verification with the
code that names the attempt.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from c05_schema_bundle import (
    INDEX_NAME,
    OUTPUT_DIR,
    C05BundleError,
    _hash_excluding,
    emit,
    members,
    render,
    verify,
)
from instance_synthesis import SynthesisError, synthesize
from test_schema_and_type import ROOT
from test_unit_contract import canonical, instance, validator


def refused_instance(schema_name: str, payload: object) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        validator(schema_name).validate(payload)
    return caught.value


@pytest.mark.parametrize(
    "intruder",
    [
        "evaluator-bundle",
        "holdout-manifest",
        "fitness-vector",
        "epistemic-archive-entry",
        "shinka-backend-manifest",
        "mutation-receipt",
        "candidate-lineage",
    ],
)
def test_a_non_genome_document_is_not_a_candidate(intruder: str) -> None:
    refused_instance("evolution-candidate.schema.json", instance(intruder))


def test_a_promotion_shaped_document_is_not_a_candidate() -> None:
    refused_instance(
        "evolution-candidate.schema.json",
        {
            "decision": "PROMOTE",
            "decision_id": "PD-0001",
            "promotion_level": "L4_VALIDATED",
        },
    )


def test_a_genome_with_a_smuggled_authority_field_is_refused() -> None:
    payload = dict(instance("hypothesis-genome"))
    payload["evaluator_override"] = True

    refused_instance("evolution-candidate.schema.json", payload)


def test_a_candidate_is_not_on_the_evaluator_surface() -> None:
    refused_instance(
        "evaluator-authority-surface.schema.json", instance("hypothesis-genome")
    )


def test_statistics_without_the_sequential_ledger_are_refused() -> None:
    error = refused_instance(
        "adaptive-search-statistics.schema.json",
        {
            "multiple_testing_adjustment": instance("multiple-testing-adjustment"),
            "selective_inference_report": instance("selective-inference-report"),
        },
    )

    assert "sequential_testing_ledger" in error.message


def test_statistics_with_an_unknown_record_are_refused() -> None:
    refused_instance(
        "adaptive-search-statistics.schema.json",
        {
            "combined_score": 0.99,
            "multiple_testing_adjustment": instance("multiple-testing-adjustment"),
            "selective_inference_report": instance("selective-inference-report"),
            "sequential_testing_ledger": instance("sequential-testing-ledger"),
        },
    )


def test_an_import_without_qualification_is_refused() -> None:
    error = refused_instance(
        "external-backend-binding.schema.json",
        {
            "backend_manifest": instance("shinka-backend-manifest"),
            "imported_run": instance("imported-run-record"),
        },
    )

    assert "qualification" in error.message


def test_an_import_from_an_unpinned_backend_is_refused() -> None:
    manifest = dict(instance("shinka-backend-manifest"))
    manifest["backend_name"] = "OtherEvolve"

    refused_instance(
        "external-backend-binding.schema.json",
        {
            "backend_manifest": manifest,
            "imported_run": instance("imported-run-record"),
            "qualification": instance("backend-adapter-qualification"),
        },
    )


def test_an_import_under_a_foreign_license_is_refused() -> None:
    manifest = dict(instance("shinka-backend-manifest"))
    manifest["license"] = "MIT"

    refused_instance(
        "external-backend-binding.schema.json",
        {
            "backend_manifest": manifest,
            "imported_run": instance("imported-run-record"),
            "qualification": instance("backend-adapter-qualification"),
        },
    )


def mirror(tmp_path: Path) -> Path:
    for name in members():
        target = tmp_path / "schemas" / f"{name}.schema.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "schemas" / f"{name}.schema.json", target)
    emit(tmp_path)
    return tmp_path


def refused_verify(base: Path) -> C05BundleError:
    with pytest.raises(C05BundleError) as caught:
        verify(base)
    return caught.value


def edit_bundle(base: Path, name: str, mutate) -> None:
    path = base / OUTPUT_DIR / name
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_bytes(render(document))


def test_a_widened_mutable_space_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["oneOf"].append(
            {
                "$ref": (
                    "https://epistemic-foundry.local/schemas/"
                    "evaluator-bundle.schema.json"
                )
            }
        )

    edit_bundle(base, "evolution-candidate.schema.json", mutate)
    error = refused_verify(base)
    assert error.code == "AUTHORITY_IN_MUTABLE_SPACE"


def test_a_narrowed_mutable_space_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["oneOf"] = document["oneOf"][:-1]

    edit_bundle(base, "evolution-candidate.schema.json", mutate)
    assert refused_verify(base).code == "MUTABLE_SPACE_MISMATCH"


def test_smuggled_vocabulary_in_a_composite_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["properties"]["backend_manifest"] = {
            "const": {"backend_name": "ShinkaEvolve"}
        }

    edit_bundle(base, "external-backend-binding.schema.json", mutate)
    error = refused_verify(base)
    assert error.code in {"VOCABULARY_SMUGGLED", "INDEX_STALE"}


def test_a_tampered_index_hash_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["member_count"] = 41

    edit_bundle(base, INDEX_NAME, mutate)
    assert refused_verify(base).code == "INDEX_TAMPERED"


def test_a_resealed_index_with_a_wrong_generator_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["generator"]["sha256"] = "sha256:" + "0" * 64
        document["index_hash"] = _hash_excluding(document, "index_hash")

    edit_bundle(base, INDEX_NAME, mutate)
    assert refused_verify(base).code == "GENERATOR_DRIFT"


def test_a_canonical_member_drift_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    target = base / "schemas/hypothesis-genome.schema.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["description"] = "drifted"
    target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    assert refused_verify(base).code == "INDEX_STALE"


def test_a_missing_canonical_member_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    (base / "schemas/novelty-vector.schema.json").unlink()

    assert refused_verify(base).code == "MEMBER_MISSING"


def test_a_deleted_composite_is_refused_then_repaired(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    target = base / OUTPUT_DIR / "archive-preservation-record.schema.json"
    before = target.read_bytes()
    target.unlink()

    assert refused_verify(base).code == "OUTPUT_MISSING"
    emit(base)
    assert target.read_bytes() == before
    assert verify(base)["status"] == "PASS"


def test_an_unreceipted_file_in_the_bundle_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    (base / OUTPUT_DIR / "extra.schema.json").write_text("{}", encoding="utf-8")

    assert refused_verify(base).code == "OUTPUT_TAMPERED"


def test_the_synthesizer_fails_loudly_on_an_unknown_pattern() -> None:
    with pytest.raises(SynthesisError):
        synthesize({"pattern": "^unmodelled$", "type": "string"}, "$")


def test_the_synthesizer_fails_loudly_on_combinators() -> None:
    with pytest.raises(SynthesisError):
        synthesize({"oneOf": [{"type": "string"}]}, "$")


def test_an_invalid_instance_really_fails_its_own_schema() -> None:
    payload = dict(instance("sequential-testing-ledger"))
    payload.pop(sorted(payload)[0])

    with pytest.raises(ValidationError):
        Draft202012Validator(canonical("sequential-testing-ledger")).validate(payload)
