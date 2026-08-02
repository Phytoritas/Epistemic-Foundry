"""negative_and_adversarial_tests — divergence and overreach are refused.

The gate exists to catch receipts that drifted apart, so it is attacked exactly
there: a projection built from a stale schema, two projections disagreeing, a
mutated canonical file, a missing or altered fixture, a re-sealed index, and a
bundle carrying a file no receipt covers.  The EF4-I41 boundary is attacked with
the repository's own fixtures — a genome-family record that merely describes
variation must be refused as a candidate — and the compatibility binding must
refuse a migration recorded without the matrix it applies under.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from c06_integration_gate import (
    BINDING_NAME,
    C05_INDEX_PATH,
    CANDIDATE_COMPOSITE,
    CANDIDATE_FAMILY,
    INDEX_NAME,
    OUTPUT_DIR,
    PARITY_NAME,
    PROJECTION_MANIFESTS,
    C06GateError,
    _hash_excluding,
    _registry,
    audit_fixtures,
    emit,
    family_members,
    mutable_search_space,
    reconcile_projections,
    render,
    verify,
)
from test_schema_and_type import ROOT, load
from test_unit_contract import composite_validator, example


def mirror(tmp_path: Path) -> Path:
    """A working copy of every input the gate reads."""

    for directory in ("schemas", "schemas/v4_c05", "examples"):
        source = ROOT / directory
        target = tmp_path / directory
        target.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file():
                shutil.copyfile(path, target / path.name)
    for relative in PROJECTION_MANIFESTS.values():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    emit(tmp_path)
    return tmp_path


def refused(base: Path, *, on_verify: bool = True) -> C06GateError:
    with pytest.raises(C06GateError) as caught:
        if on_verify:
            verify(base)
        else:
            reconcile_projections(base)
    return caught.value


def edit_json(path: Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_bytes(render(document))


def test_the_mirror_itself_verifies(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    assert verify(base)["status"] == "PASS"


def test_two_projections_disagreeing_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        for row in document["contracts"]:
            if row["schema_file"] == "schemas/hypothesis-genome.schema.json":
                row["source_sha256"] = "sha256:" + "1" * 64

    edit_json(base / PROJECTION_MANIFESTS["web"], mutate)
    assert refused(base).code in {"PROJECTION_DIVERGED", "SOURCE_DRIFT"}


def test_a_projection_built_from_a_stale_schema_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    stale = "sha256:" + "2" * 64

    def mutate(document: dict) -> None:
        for row in document["contracts"]:
            if row["schema_file"] == "schemas/evaluator-bundle.schema.json":
                row["source_sha256"] = stale

    for relative in PROJECTION_MANIFESTS.values():
        edit_json(base / relative, mutate)

    assert refused(base).code in {"PROJECTION_STALE", "SOURCE_DRIFT"}


def test_projections_disagreeing_on_the_bundle_hash_are_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["schema_bundle_sha256"] = "sha256:" + "3" * 64

    edit_json(base / PROJECTION_MANIFESTS["python"], mutate)
    assert refused(base).code in {"PROJECTION_BUNDLE_DIVERGED", "SOURCE_DRIFT"}


def test_a_projection_that_lost_a_member_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["contracts"] = [
            row
            for row in document["contracts"]
            if row["schema_file"] != "schemas/novelty-vector.schema.json"
        ]

    edit_json(base / PROJECTION_MANIFESTS["typescript"], mutate)
    assert refused(base).code in {"PROJECTION_MEMBER_MISSING", "SOURCE_DRIFT"}


def test_a_mutated_canonical_schema_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    target = base / "schemas/fitness-vector.schema.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["description"] = "drifted"
    target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    assert refused(base).code in {"C05_INDEX_STALE", "PROJECTION_STALE"}


def test_a_mutated_fixture_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    target = base / "examples/sample_island-state.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["island_id"] = "IS-drifted"
    target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    assert refused(base).code == "FIXTURE_STALE"


def test_a_deleted_fixture_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    (base / "examples/sample_epistemic-niche.json").unlink()

    assert refused(base).code == "FIXTURE_MISSING"


def test_a_deleted_canonical_member_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    (base / "schemas/prompt-genome.schema.json").unlink()

    assert refused(base).code == "MEMBER_MISSING"


def test_a_stale_c05_index_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        for record in document["families"].values():
            for entry in record["members"]:
                if entry["canonical"] == "schemas/island-state.schema.json":
                    entry["sha256"] = "sha256:" + "4" * 64

    edit_json(base / C05_INDEX_PATH, mutate)
    assert refused(base).code in {"C05_INDEX_STALE", "SOURCE_DRIFT"}


def test_a_c05_index_without_families_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["families"] = {}

    edit_json(base / C05_INDEX_PATH, mutate)
    assert refused(base).code in {"C05_INDEX_UNREADABLE", "SOURCE_DRIFT"}


def test_a_resealed_index_with_a_wrong_generator_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["generator"]["sha256"] = "sha256:" + "5" * 64
        document["index_hash"] = _hash_excluding(document, "index_hash")

    edit_json(base / OUTPUT_DIR / INDEX_NAME, mutate)
    assert refused(base).code == "GENERATOR_DRIFT"


def test_a_tampered_index_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["member_count"] = 41

    edit_json(base / OUTPUT_DIR / INDEX_NAME, mutate)
    assert refused(base).code == "INDEX_TAMPERED"


def test_a_tampered_parity_record_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["agreed_member_count"] = 41
        document["parity_hash"] = _hash_excluding(document, "parity_hash")

    edit_json(base / OUTPUT_DIR / PARITY_NAME, mutate)
    assert refused(base).code in {"INDEX_STALE", "OUTPUT_TAMPERED"}


def test_smuggled_vocabulary_in_the_binding_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["properties"]["migration"] = {"const": {"compatibility": "breaking"}}

    edit_json(base / OUTPUT_DIR / BINDING_NAME, mutate)
    assert refused(base).code in {"VOCABULARY_SMUGGLED", "INDEX_STALE"}


def test_an_unreceipted_file_in_the_bundle_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    (base / OUTPUT_DIR / "extra.json").write_text("{}", encoding="utf-8")

    assert refused(base).code == "OUTPUT_TAMPERED"


def test_a_deleted_output_is_refused_then_repaired(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    target = base / OUTPUT_DIR / PARITY_NAME
    before = target.read_bytes()
    target.unlink()

    assert refused(base).code == "OUTPUT_MISSING"
    emit(base)
    assert target.read_bytes() == before
    assert verify(base)["status"] == "PASS"


@pytest.mark.parametrize(
    "name",
    sorted(
        set(family_members(ROOT)[CANDIDATE_FAMILY]) - set(mutable_search_space(ROOT))
    ),
)
def test_a_non_candidate_genome_record_is_refused_as_a_candidate(
    name: str,
) -> None:
    with pytest.raises(ValidationError):
        composite_validator(CANDIDATE_COMPOSITE).validate(example(name))


def test_an_evaluator_fixture_is_refused_as_a_candidate() -> None:
    with pytest.raises(ValidationError):
        composite_validator(CANDIDATE_COMPOSITE).validate(example("evaluator-bundle"))


def test_a_holdout_fixture_is_refused_as_a_candidate() -> None:
    with pytest.raises(ValidationError):
        composite_validator(CANDIDATE_COMPOSITE).validate(example("holdout-manifest"))


def test_a_migration_without_its_matrix_is_refused() -> None:
    validator = Draft202012Validator(load(BINDING_NAME), registry=_registry(ROOT))

    with pytest.raises(ValidationError) as caught:
        validator.validate({"migration": example("schema-migration")})
    assert "compatibility_matrix" in caught.value.message


def test_a_binding_record_with_an_unknown_field_is_refused() -> None:
    validator = Draft202012Validator(load(BINDING_NAME), registry=_registry(ROOT))

    with pytest.raises(ValidationError):
        validator.validate(
            {
                "compatibility_matrix": example("compatibility-matrix"),
                "migration": example("schema-migration"),
                "waiver": {"granted": True},
            }
        )


def test_the_fixture_audit_refuses_a_widened_candidate_composite(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["oneOf"].append(
            {
                "$ref": "https://epistemic-foundry.local/schemas/"
                "candidate-lineage.schema.json"
            }
        )

    edit_json(base / "schemas/v4_c05" / CANDIDATE_COMPOSITE, mutate)
    with pytest.raises(C06GateError) as caught:
        audit_fixtures(base)
    assert caught.value.code == "AUTHORITY_IN_MUTABLE_SPACE"


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = C06GateError("PROJECTION_DIVERGED", "message", {"member": "x"})

    assert error.code == "PROJECTION_DIVERGED"
    assert str(error) == "message"
    assert error.context == {"member": "x"}
