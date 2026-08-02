"""schema_and_type_check — the gate reads its vocabulary, never restates it.

The build epoch, the lockfile names and the pinned build backend come from
``toolchains/toolchain-lock.json``; the backend pin requirements from the
canonical ShinkaBackendManifest schema; the PostgreSQL image digest from the
sealed D05 harness; the build flags and the environment normalization from
B02's own double-build script; and the source snapshot list from what B04's
build hooks declare a build reads.  Every one of those positional assumptions
is asserted here against the declaring text, so it cannot rot in silence, and
the module source is checked to make sure none of those values was copied into
it as a literal.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import b06_gate
from b06_gate import (
    BACKEND_SCHEMA_PATH,
    BUILD_HOOKS_PATH,
    BUILD_OUTPUT_PLACEHOLDER,
    CANONICAL_DOUBLE_BUILD_PATH,
    DECLARED_NORMALIZATIONS,
    DISTRIBUTION_SUFFIXES,
    FINDING_CODES,
    INHERITED_BUILD_FLAGS,
    NORMALIZATION_VARIABLES,
    POSTGRES_PIN_PATH,
    SNAPSHOT_DIRECTORIES,
    SNAPSHOT_FILES,
    TOOLCHAIN_LOCK_PATH,
    BuildGateError,
    backend_pin_requirements,
    build_command,
    epoch_timestamp,
    read_toolchain_lock,
    sealed_container_pin,
)
from fixtures import EPOCH, ROOT, TOOLCHAIN

GATE = Path(b06_gate.__file__)
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"


def gate_source() -> str:
    return GATE.read_text(encoding="utf-8")


def failed_codes() -> set[str]:
    tree = ast.parse(gate_source())
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_fail"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def test_every_finding_code_is_upper_snake_with_a_stated_reason() -> None:
    assert FINDING_CODES

    for code, reason in FINDING_CODES.items():
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*[A-Z0-9]", code), code
        assert len(reason) > 50, code
        assert reason == reason.strip()
    assert len(set(FINDING_CODES.values())) == len(FINDING_CODES)


def test_the_gate_refuses_with_exactly_the_codes_it_declares() -> None:
    used = failed_codes()

    assert used <= set(FINDING_CODES), sorted(used - set(FINDING_CODES))
    assert set(FINDING_CODES) <= used, sorted(set(FINDING_CODES) - used)


def test_an_undeclared_code_cannot_be_raised() -> None:
    with pytest.raises(BuildGateError) as caught:
        b06_gate._fail("NOT_A_DECLARED_CODE", "should never be raised")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context["code"] == "NOT_A_DECLARED_CODE"


def test_the_toolchain_lock_is_read_rather_than_restated() -> None:
    document = json.loads((ROOT / TOOLCHAIN_LOCK_PATH).read_text(encoding="utf-8"))
    lock = read_toolchain_lock(ROOT)

    assert lock["source_date_epoch"] == document["source_date_epoch"]
    assert lock["lockfiles"] == document["lockfiles"]
    assert lock["backend"]["name"] == document["python_build_backend"]["name"]
    assert lock["backend"]["version"] == document["python_build_backend"]["version"]
    assert str(document["source_date_epoch"]) not in gate_source()


def test_the_ci_workflow_exports_the_same_build_epoch() -> None:
    exported = re.search(
        r'SOURCE_DATE_EPOCH:\s*"(\d+)"', CI_WORKFLOW.read_text(encoding="utf-8")
    )

    assert exported is not None
    assert int(exported.group(1)) == EPOCH
    assert epoch_timestamp(EPOCH).endswith("Z")
    assert epoch_timestamp(0) == "1970-01-01T00:00:00Z"


def test_the_backend_pin_requirements_come_from_the_canonical_schema() -> None:
    schema = json.loads((ROOT / BACKEND_SCHEMA_PATH).read_text(encoding="utf-8"))

    assert backend_pin_requirements(ROOT) == tuple(sorted(schema["required"]))
    assert "source_revision" in backend_pin_requirements(ROOT)
    assert "manifest_hash" in backend_pin_requirements(ROOT)
    assert schema["properties"]["manifest_hash"]["pattern"] == "^sha256:[0-9a-f]{64}$"


def test_the_container_pin_comes_from_the_sealed_d05_attempt() -> None:
    pin = sealed_container_pin(ROOT)
    sealed = (ROOT / POSTGRES_PIN_PATH).read_text(encoding="utf-8")
    verification = (
        ROOT / "artifacts/work_packages/D05/attempts/0001/d05-verification.json"
    ).read_text(encoding="utf-8")

    reference = f"{pin['repository']}@{pin['digest']}"
    assert reference in verification
    assert pin["digest"].split(":")[1] in sealed
    assert pin["source_path"] == POSTGRES_PIN_PATH
    assert pin["digest"] not in gate_source()


def test_the_snapshot_covers_every_input_the_build_hooks_declare() -> None:
    hooks = (ROOT / BUILD_HOOKS_PATH).read_text(encoding="utf-8")
    declared = set(re.findall(r'root / "([A-Za-z0-9_]+)"', hooks))

    assert declared, "the build hooks declare no canonical source root"
    assert declared <= set(SNAPSHOT_DIRECTORIES), sorted(
        declared - set(SNAPSHOT_DIRECTORIES)
    )
    for relative in (*SNAPSHOT_FILES, *SNAPSHOT_DIRECTORIES):
        assert (ROOT / relative).exists(), relative


def test_the_snapshot_covers_every_root_pyproject_maps_a_package_into() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    mapped = {
        value.strip('"').replace(".", "/").split("/")[0]
        for value in re.findall(r'=\s*("(?:src|scripts)[^"]*")', pyproject)
    }

    assert mapped
    assert mapped <= set(SNAPSHOT_DIRECTORIES), sorted(mapped)
    assert "pyproject.toml" in SNAPSHOT_FILES
    assert TOOLCHAIN["lockfiles"]["python"] in SNAPSHOT_FILES


def test_the_build_flags_are_inherited_from_the_canonical_double_build() -> None:
    canonical = (ROOT / CANONICAL_DOUBLE_BUILD_PATH).read_text(encoding="utf-8")
    flags = set(re.findall(r'"(--[a-z-]+)"', canonical))
    command = build_command("toolchains/python-build-constraints.txt", "out")

    assert set(INHERITED_BUILD_FLAGS) <= flags, sorted(
        set(INHERITED_BUILD_FLAGS) - flags
    )
    assert set(INHERITED_BUILD_FLAGS) <= set(command)
    # The one deliberate deviation: B02 builds only the wheel, so its script
    # never compares an sdist.  This gate compares both distributions.
    assert "--wheel" in flags
    assert "--wheel" not in command
    assert command[:2] == ["uv", "build"]
    assert command[-1] == "."
    # The recorded output path is B02's placeholder, not this machine's path.
    assert BUILD_OUTPUT_PLACEHOLDER in canonical
    assert BUILD_OUTPUT_PLACEHOLDER in build_command(
        "toolchains/python-build-constraints.txt", BUILD_OUTPUT_PLACEHOLDER
    )


def test_every_normalization_is_declared_with_the_variable_it_sets() -> None:
    canonical = (ROOT / CANONICAL_DOUBLE_BUILD_PATH).read_text(encoding="utf-8")

    assert set(DECLARED_NORMALIZATIONS) == set(NORMALIZATION_VARIABLES)
    for name, reason in DECLARED_NORMALIZATIONS.items():
        assert len(reason) > 40, name
        assert NORMALIZATION_VARIABLES[name] in canonical, name


def test_the_comparator_recognises_the_distributions_the_build_emits() -> None:
    document = json.loads((ROOT / TOOLCHAIN_LOCK_PATH).read_text(encoding="utf-8"))

    assert document["build_outputs"]["python"] == "wheel"
    assert ".whl" in DISTRIBUTION_SUFFIXES
    assert ".tar.gz" in DISTRIBUTION_SUFFIXES
    assert all(suffix.startswith(".") for suffix in DISTRIBUTION_SUFFIXES)
