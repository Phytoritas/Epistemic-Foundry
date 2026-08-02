"""negative_and_adversarial_tests — every route around the pin is refused.

A build that cannot be talked into weaker pins: unpinned artifacts, drifted
Python floors, unlocked dependencies and smuggled ShinkaEvolve installs are
refused at derivation time, and an emitted profile edited toward enablement,
authority or a re-sealed forgery is refused at verification time with the code
that names the attempt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from b05_profile import (
    FEATURE_NAME,
    MANIFEST_NAME,
    OUTPUT_DIR,
    REGISTRY_PATH,
    RESEARCH_PATH,
    B05BuildError,
    _hash_excluding,
    build_documents,
    emit,
    render,
    verify,
)
from test_build_determinism import mirror


def refused(base: Path, *, on_verify: bool = False) -> B05BuildError:
    with pytest.raises(B05BuildError) as caught:
        if on_verify:
            verify(base)
        else:
            build_documents(base)
    return caught.value


def rewrite(base: Path, relative: str, old: str, new: str, count: int = -1) -> None:
    path = base / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="")


def edit_json(base: Path, relative: str, mutate) -> None:
    path = base / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def reseal(document: dict, hash_field: str) -> dict:
    document[hash_field] = _hash_excluding(document, hash_field)
    return document


def test_a_locked_package_without_hashes_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "uv.lock",
        'sdist = { url = "https://files.pythonhosted.org/packages/9a/8e',
        'ignored = { url = "https://files.pythonhosted.org/packages/9a/8e',
        1,
    )
    rewrite(
        base,
        "uv.lock",
        'wheels = [\n    { url = "https://files.pythonhosted.org/packages/64/b4',
        'ignored_wheels = [\n    { url = "https://files.pythonhosted.org/packages/64/b4',
        1,
    )

    error = refused(base)
    assert error.code == "PIN_UNPINNED"
    assert error.context["package"] == "attrs"


def test_a_python_floor_drift_between_lock_and_project_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    rewrite(
        base, "uv.lock", 'requires-python = ">=3.12"', 'requires-python = ">=3.11"', 1
    )

    assert refused(base).code == "PYTHON_PIN_MISMATCH"


def test_an_unpinned_build_backend_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "pyproject.toml",
        'requires = ["setuptools==82.0.1"]',
        'requires = ["setuptools>=82"]',
    )

    assert refused(base).code == "BUILD_BACKEND_UNPINNED"


def test_a_declared_dependency_missing_from_the_lock_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "pyproject.toml",
        '"PyYAML>=6.0,<7",',
        '"PyYAML>=6.0,<7",\n    "orjson>=3",',
    )

    error = refused(base)
    assert error.code == "DEPENDENCY_UNLOCKED"
    assert "orjson" in error.context["requirement"]


def test_a_shinka_dependency_in_pyproject_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "pyproject.toml",
        '"PyYAML>=6.0,<7",',
        '"PyYAML>=6.0,<7",\n    "shinka-evolve>=0.0.7",',
    )

    assert refused(base).code == "SHINKA_PREINSTALLED"


def test_a_shinka_optional_extra_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "pyproject.toml",
        'dev = ["pytest>=8.0,<9"]',
        'dev = ["pytest>=8.0,<9"]\nshinka = ["Shinka_Evolve==0.0.7"]',
    )

    assert refused(base).code == "SHINKA_PREINSTALLED"


def test_a_shinka_package_in_the_lock_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(
        base,
        "uv.lock",
        '[[package]]\nname = "idna"',
        '[[package]]\nname = "shinka"\nversion = "0.0.7"\n\n[[package]]\nname = "idna"',
        1,
    )

    assert refused(base).code == "SHINKA_PREINSTALLED"


def test_a_duplicated_lock_entry_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    lock = (base / "uv.lock").read_text(encoding="utf-8")
    start = lock.index('[[package]]\nname = "iniconfig"')
    end = lock.index("[[package]]", start + 1)
    (base / "uv.lock").write_text(
        lock[:end] + lock[start:end] + lock[end:], encoding="utf-8", newline=""
    )

    assert refused(base).code == "LOCK_DUPLICATE"


def test_a_project_version_drift_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(base, "pyproject.toml", 'version = "4.0.0"', 'version = "4.0.1"', 1)

    assert refused(base).code == "VERSION_MISMATCH"


def test_a_registry_that_lost_a_schema_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["schema_count"] = 126

    edit_json(base, REGISTRY_PATH, mutate)
    error = refused(base)
    assert error.code == "CANONICAL_COUNT_MISMATCH"
    assert error.context["observed"][0] == 126


def test_an_observed_license_other_than_the_pinned_one_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        document["license"] = "MIT"

    edit_json(base, RESEARCH_PATH, mutate)
    error = refused(base)
    assert error.code == "LICENSE_MISMATCH"
    assert error.context == {"observed": "MIT", "pinned": "Apache-2.0"}


def test_a_missing_release_observation_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)

    def mutate(document: dict) -> None:
        del document["latest_release_observed"]["tag"]

    edit_json(base, RESEARCH_PATH, mutate)
    assert refused(base).code == "PIN_UNOBSERVED"


def test_a_feature_without_recorded_evidence_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    rewrite(base, RESEARCH_PATH, "prompt co-evolution", "prompt evolution")

    error = refused(base)
    assert error.code == "PIN_UNOBSERVED"
    assert error.context["feature"] == "prompt_co_evolution"


def test_an_emitted_profile_flipped_to_enabled_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["status"] = "ENABLED"
        reseal(document, "feature_hash")

    edit_json(base, f"{OUTPUT_DIR}/{FEATURE_NAME}", mutate)
    assert refused(base, on_verify=True).code == (
        "SHINKA_ENABLED_WITHOUT_QUALIFICATION"
    )


def test_an_enabled_feature_list_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["features"]["enabled"] = ["archive_islands"]
        reseal(document, "feature_hash")

    edit_json(base, f"{OUTPUT_DIR}/{FEATURE_NAME}", mutate)
    assert refused(base, on_verify=True).code == (
        "SHINKA_ENABLED_WITHOUT_QUALIFICATION"
    )


def test_a_qualification_overclaim_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["qualification"] = "QUALIFIED"
        reseal(document, "feature_hash")

    edit_json(base, f"{OUTPUT_DIR}/{FEATURE_NAME}", mutate)
    assert refused(base, on_verify=True).code == "QUALIFICATION_OVERCLAIM"


@pytest.mark.parametrize(
    "flag",
    [
        "evaluator_authority",
        "holdout_access",
        "promotion_authority",
        "prompt_genome_activation",
    ],
)
def test_a_granted_authority_flag_is_refused(tmp_path: Path, flag: str) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["authority"][flag] = True
        reseal(document, "feature_hash")

    edit_json(base, f"{OUTPUT_DIR}/{FEATURE_NAME}", mutate)
    error = refused(base, on_verify=True)
    assert error.code == "AUTHORITY_GRANTED"
    assert error.context["granted"] == [flag]


def test_a_smuggled_install_extra_is_refused_at_verify(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["install_extra_present"] = True
        reseal(document, "feature_hash")

    edit_json(base, f"{OUTPUT_DIR}/{FEATURE_NAME}", mutate)
    assert refused(base, on_verify=True).code == "SHINKA_PREINSTALLED"


def test_input_drift_after_emit_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)
    (base / "uv.lock").write_text(
        (base / "uv.lock").read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
        newline="",
    )

    assert refused(base, on_verify=True).code == "INPUT_DRIFT"


def test_a_resealed_manifest_with_a_wrong_generator_is_refused(
    tmp_path: Path,
) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["generator"]["sha256"] = "sha256:" + "0" * 64
        reseal(document, "manifest_hash")

    edit_json(base, f"{OUTPUT_DIR}/{MANIFEST_NAME}", mutate)
    assert refused(base, on_verify=True).code == "GENERATOR_DRIFT"


def test_a_manifest_whose_hash_does_not_match_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)

    def mutate(document: dict) -> None:
        document["build_id"] = "v4-b05-forged"

    edit_json(base, f"{OUTPUT_DIR}/{MANIFEST_NAME}", mutate)
    assert refused(base, on_verify=True).code == "MANIFEST_TAMPERED"


def test_an_unreceipted_file_in_the_build_output_is_refused(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    emit(base)
    (base / OUTPUT_DIR / "extra.json").write_text("{}", encoding="utf-8")

    assert refused(base, on_verify=True).code == "OUTPUT_TAMPERED"


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = B05BuildError("PIN_UNPINNED", "message", {"package": "x"})

    assert error.code == "PIN_UNPINNED"
    assert str(error) == "message"
    assert error.context == {"package": "x"}


def test_a_tampered_committed_document_would_not_re_render(tmp_path: Path) -> None:
    base = mirror(tmp_path)
    documents = build_documents(base)
    forged = json.loads(render(documents["profile"]).decode("utf-8"))
    forged["project"]["version"] = "9.9.9"
    reseal(forged, "profile_hash")

    assert render(forged) != render(documents["profile"])
