#!/usr/bin/env python3
"""B05 deterministic v4 build profile, dependency pinning and Shinka feature gate.

``build/v4_b05/`` is generated, reproducible build output, never tracked source
(HD-EF4-B05-SCOPE-20260801-001).  Everything in it derives from exactly five
tracked inputs — ``pyproject.toml``, ``uv.lock``, the ShinkaEvolve research
manifest, the canonical ShinkaBackendManifest schema and the sealed B04
canonical registry — and regenerating it must be byte-identical, so the output
need not be committed to be verifiable.

Dependency pinning is proved, not asserted: the build backend must be pinned
exactly, every locked external package must carry at least one artifact hash,
every declared dependency must resolve in the lock, and the lock's Python floor
must match the project's.  The ShinkaEvolve optional feature is emitted
``DISABLED`` and ``UNQUALIFIED``: the public source study observed a short
release commit only, MASTER_SPEC forbids treating it as an endorsement of a
floating dependency, and EF4-I63 keeps every backend outside Foundry authority.
The profile therefore grants no evaluator, holdout, promotion, novelty, archive
or prompt authority, and a profile edited toward enablement is refused with the
code that names the attempt rather than re-emitted around.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

#: The only files the generator may read.  Everything else is out of scope.
INPUT_PATHS: Final = (
    "pyproject.toml",
    "research/shinkaevolve_source_manifest.json",
    "schemas/shinka-backend-manifest.schema.json",
    "src/epistemic_foundry/_canonical/canonical-registry.json",
    "uv.lock",
)
BACKEND_SCHEMA_PATH: Final = "schemas/shinka-backend-manifest.schema.json"
RESEARCH_PATH: Final = "research/shinkaevolve_source_manifest.json"
REGISTRY_PATH: Final = "src/epistemic_foundry/_canonical/canonical-registry.json"
GENERATOR_RELPATH: Final = "artifacts/work_packages/B05/attempts/0001/b05_profile.py"
OUTPUT_DIR: Final = "build/v4_b05"
PROFILE_NAME: Final = "build-profile.json"
FEATURE_NAME: Final = "shinka-optional-feature.json"
MANIFEST_NAME: Final = "build-manifest.json"

#: B04's sealed exit criteria pin the canonical snapshot at exactly 127 JSON
#: Schemas plus one OpenAPI document; a registry that says otherwise is not a
#: drifted expectation but a broken build input.
EXPECTED_SCHEMA_COUNT: Final = 127
EXPECTED_OPENAPI_COUNT: Final = 1
EXPECTED_RESOURCE_COUNT: Final = 128

#: Each disabled feature must be grounded in the recorded public observation;
#: a feature name this table cannot evidence is refused rather than listed.
FEATURE_EVIDENCE: Final = {
    "archive_islands": "global archive and islands",
    "bandit_model_selection": "bandit model selection",
    "executable_program_evolution": "population of programs",
    "llm_ensemble_mutation": "LLM ensemble mutation operators",
    "novelty_judgment": "novelty controls",
    "prompt_co_evolution": "prompt co-evolution",
}

#: EF4-I63: no backend acquires evaluator, holdout or promotion authority.
AUTHORITY_FLAGS: Final = (
    "archive_authority",
    "evaluator_authority",
    "holdout_access",
    "novelty_authority",
    "promotion_authority",
    "prompt_genome_activation",
)

#: What enabling the feature would take.  None of it exists yet.
ENABLEMENT_REQUIREMENTS: Final = (
    "a sealed B06 reproducible build and backend-pin integration gate PASS attempt",
    "a sealed T06 external-backend qualification gate PASS attempt",
    "a sealed ShinkaBackendManifest conforming to "
    "schemas/shinka-backend-manifest.schema.json",
    "a capability lease issued under the T04 sandbox and external tool adapter gate",
)

#: Canonical-manifest fields the public observation can already pin, versus
#: the fields that stay blocked with the reason they cannot be pinned yet.
BLOCKED_FIELD_REASONS: Final = {
    "adapter_version": "no adapter implementation exists yet; T05 owns it",
    "backend_manifest_id": "issued when a qualification run seals the manifest",
    "disabled_features": "feature selection is decided by the B06/T06 gates",
    "enabled_features": "feature selection is decided by the B06/T06 gates",
    "manifest_hash": "computed when the sealed manifest exists",
    "package_version": (
        "the release tag was observed but the built package version was not "
        "verified from package metadata"
    ),
    "sandbox_profile_id": (
        "a sandbox profile is issued under the T04 gate at qualification time"
    ),
    "source_revision": (
        "the public observation recorded a short release commit only; pinning "
        "requires a verified full revision"
    ),
    "supported_candidate_types": "adapter candidate-type mapping is T05 scope",
}

_PROFILE_FIELDS: Final = frozenset(
    {
        "build_system",
        "canonical_resources",
        "dependency_groups",
        "direct_dependencies",
        "inputs",
        "locked_packages",
        "profile_hash",
        "profile_id",
        "project",
        "reproducibility",
    }
)
_FEATURE_FIELDS: Final = frozenset(
    {
        "authority",
        "canonical_manifest_readiness",
        "enablement_requirements",
        "feature_hash",
        "feature_id",
        "features",
        "install_extra_present",
        "observation",
        "qualification",
        "status",
    }
)
_MANIFEST_FIELDS: Final = frozenset(
    {"build_id", "generator", "inputs", "manifest_hash", "outputs", "reproducible"}
)


class B05BuildError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise B05BuildError(code, message, context)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def render(document: Mapping[str, Any]) -> bytes:
    """The exact bytes a document is written as; byte-identical on re-emit."""

    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(specifier: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", specifier)
    if match is None:
        _fail("DEPENDENCY_UNPARSEABLE", f"unparseable requirement: {specifier!r}")
    return match.group(1)  # type: ignore[union-attr]


def _read_input(root: Path, relative: str) -> bytes:
    path = Path(root) / relative
    try:
        return path.read_bytes()
    except OSError as error:
        _fail("INPUT_MISSING", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises


def _load_pyproject(root: Path) -> dict[str, Any]:
    data = tomllib.loads(_read_input(root, "pyproject.toml").decode("utf-8"))

    build_system = data.get("build-system", {})
    requires = build_system.get("requires")
    backend = build_system.get("build-backend")
    if not isinstance(requires, list) or not requires or not backend:
        _fail("BUILD_BACKEND_UNPINNED", "pyproject declares no build backend pin")
    for entry in requires:
        if "==" not in str(entry):
            _fail(
                "BUILD_BACKEND_UNPINNED",
                "a build-system requirement must be pinned exactly",
                {"requirement": entry},
            )

    project = data.get("project", {})
    for field in ("name", "version", "requires-python", "dependencies"):
        if field not in project:
            _fail("PROJECT_UNDECLARED", f"pyproject project.{field} is missing")

    groups: dict[str, list[str]] = {}
    for group, entries in (
        data.get("project", {}).get("optional-dependencies", {}) or {}
    ).items():
        groups[str(group)] = [str(entry) for entry in entries]
    for group, entries in (data.get("dependency-groups", {}) or {}).items():
        groups[str(group)] = [str(entry) for entry in entries]

    every_requirement = [str(entry) for entry in project["dependencies"]]
    for entries in groups.values():
        every_requirement.extend(entries)
    for requirement in every_requirement:
        if "shinka" in _normalize(_requirement_name(requirement)):
            _fail(
                "SHINKA_PREINSTALLED",
                "ShinkaEvolve must stay an optional, unqualified feature; it "
                "may not be a declared dependency of the v4 build",
                {"requirement": requirement},
            )

    return {
        "backend": str(backend),
        "dependencies": [str(entry) for entry in project["dependencies"]],
        "groups": groups,
        "name": str(project["name"]),
        "requires": [str(entry) for entry in requires],
        "requires_python": str(project["requires-python"]),
        "version": str(project["version"]),
    }


def _load_lock(root: Path, pyproject: Mapping[str, Any]) -> dict[str, Any]:
    data = tomllib.loads(_read_input(root, "uv.lock").decode("utf-8"))
    lock_python = str(data.get("requires-python", ""))
    if lock_python != pyproject["requires_python"]:
        _fail(
            "PYTHON_PIN_MISMATCH",
            "uv.lock and pyproject.toml disagree on the Python floor",
            {"lock": lock_python, "pyproject": pyproject["requires_python"]},
        )

    packages: dict[str, dict[str, Any]] = {}
    project_entry: dict[str, Any] | None = None
    for package in data.get("package", []):
        name = _normalize(str(package.get("name", "")))
        if not name:
            _fail("LOCK_UNPARSEABLE", "a locked package has no name")
        if name in packages or (
            project_entry is not None and name == project_entry["name"]
        ):
            _fail("LOCK_DUPLICATE", f"{name} is locked more than once")
        if "shinka" in name:
            _fail(
                "SHINKA_PREINSTALLED",
                "ShinkaEvolve may not be locked into the v4 build",
                {"package": name},
            )
        version = str(package.get("version", ""))
        source = package.get("source", {})
        if isinstance(source, Mapping) and source.get("editable") == ".":
            if name != _normalize(pyproject["name"]):
                _fail("LOCK_UNPARSEABLE", "the editable entry is not the project")
            if version != pyproject["version"]:
                _fail(
                    "VERSION_MISMATCH",
                    "the locked project version is not the declared version",
                    {"lock": version, "pyproject": pyproject["version"]},
                )
            project_entry = {"name": name, "version": version}
            continue

        sdist = package.get("sdist", {})
        sdist_hash = sdist.get("hash") if isinstance(sdist, Mapping) else None
        wheel_hashes = sorted(
            str(wheel["hash"])
            for wheel in package.get("wheels", [])
            if isinstance(wheel, Mapping) and "hash" in wheel
        )
        hashes = ([str(sdist_hash)] if sdist_hash else []) + wheel_hashes
        if not hashes:
            _fail(
                "PIN_UNPINNED",
                f"{name} is locked without any artifact hash",
                {"package": name, "version": version},
            )
        for value in hashes:
            if not value.startswith("sha256:"):
                _fail(
                    "PIN_UNPINNED",
                    f"{name} carries a non-sha256 artifact hash",
                    {"hash": value, "package": name},
                )
        packages[name] = {
            "artifact_hash_digest": _digest(
                {"sdist": sdist_hash, "wheels": wheel_hashes}
            ),
            "name": name,
            "sdist_sha256": str(sdist_hash) if sdist_hash else None,
            "version": version,
            "wheel_count": len(wheel_hashes),
        }

    if project_entry is None:
        _fail("LOCK_UNPARSEABLE", "uv.lock does not lock the project itself")
    return {"packages": packages, "project": project_entry}


def _resolve(
    requirements: list[str], packages: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    resolved = []
    for requirement in requirements:
        name = _normalize(_requirement_name(requirement))
        locked = packages.get(name)
        if locked is None:
            _fail(
                "DEPENDENCY_UNLOCKED",
                f"{name} is declared but not locked",
                {"requirement": requirement},
            )
        resolved.append(
            {
                "locked_version": locked["version"],  # type: ignore[index]
                "name": name,
                "specifier": requirement,
            }
        )
    return sorted(resolved, key=lambda entry: entry["name"])


def _load_registry(root: Path) -> dict[str, Any]:
    data = json.loads(_read_input(root, REGISTRY_PATH).decode("utf-8"))
    counts = (
        data.get("schema_count"),
        data.get("openapi_document_count"),
        data.get("resource_count"),
        data.get("file_count"),
        len(data.get("resources", [])),
    )
    if counts != (
        EXPECTED_SCHEMA_COUNT,
        EXPECTED_OPENAPI_COUNT,
        EXPECTED_RESOURCE_COUNT,
        EXPECTED_RESOURCE_COUNT,
        EXPECTED_RESOURCE_COUNT,
    ):
        _fail(
            "CANONICAL_COUNT_MISMATCH",
            "the canonical registry does not carry the sealed B04 counts",
            {
                "expected": [
                    EXPECTED_SCHEMA_COUNT,
                    EXPECTED_OPENAPI_COUNT,
                    EXPECTED_RESOURCE_COUNT,
                ],
                "observed": list(counts),
            },
        )
    return {
        "openapi_document_count": EXPECTED_OPENAPI_COUNT,
        "registry_sha256": _file_sha(root / REGISTRY_PATH),
        "resource_count": EXPECTED_RESOURCE_COUNT,
        "schema_count": EXPECTED_SCHEMA_COUNT,
    }


def _load_backend_schema(root: Path) -> dict[str, Any]:
    schema = json.loads(_read_input(root, BACKEND_SCHEMA_PATH).decode("utf-8"))
    required = schema.get("required")
    properties = schema.get("properties", {})
    backend_name = properties.get("backend_name", {}).get("const")
    license_const = properties.get("license", {}).get("const")
    if not isinstance(required, list) or not backend_name or not license_const:
        _fail(
            "SCHEMA_UNREADABLE",
            "the backend manifest schema declares no usable contract",
        )
    return {
        "backend_name": str(backend_name),
        "license": str(license_const),
        "required": tuple(str(entry) for entry in required),  # type: ignore[union-attr]
    }


def _load_research(root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    raw = _read_input(root, RESEARCH_PATH).decode("utf-8")
    data = json.loads(raw)
    repository = data.get("repository")
    release = data.get("latest_release_observed", {})
    tag = release.get("tag") if isinstance(release, Mapping) else None
    commit = release.get("commit_short") if isinstance(release, Mapping) else None
    if not repository or not tag or not commit:
        _fail(
            "PIN_UNOBSERVED",
            "the research manifest does not record a usable pin observation",
            {"commit_short": commit, "repository": repository, "tag": tag},
        )
    license_observed = data.get("license")
    if license_observed != contract["license"]:
        _fail(
            "LICENSE_MISMATCH",
            "the observed license is not the license the canonical schema pins",
            {"observed": license_observed, "pinned": contract["license"]},
        )
    for feature, evidence in FEATURE_EVIDENCE.items():
        if evidence not in raw:
            _fail(
                "PIN_UNOBSERVED",
                f"feature {feature} has no recorded observation",
                {"evidence": evidence, "feature": feature},
            )
    return {
        "commit_short": str(commit),
        "repository": str(repository),
        "tag": str(tag),
    }


def build_documents(root: str | Path) -> dict[str, dict[str, Any]]:
    """Derive both profile documents from the tracked inputs, deterministically."""

    base = Path(root)
    pyproject = _load_pyproject(base)
    lock = _load_lock(base, pyproject)
    registry = _load_registry(base)
    contract = _load_backend_schema(base)
    observation = _load_research(base, contract)
    inputs = {relative: _file_sha(base / relative) for relative in INPUT_PATHS}

    profile: dict[str, Any] = {
        "build_system": {
            "backend": pyproject["backend"],
            "exact_pin": True,
            "requires": sorted(pyproject["requires"]),
        },
        "canonical_resources": registry,
        "dependency_groups": {
            group: _resolve(entries, lock["packages"])
            for group, entries in sorted(pyproject["groups"].items())
        },
        "direct_dependencies": _resolve(pyproject["dependencies"], lock["packages"]),
        "inputs": inputs,
        "locked_packages": [
            lock["packages"][name] for name in sorted(lock["packages"])
        ],
        "profile_id": "v4-b05-build-profile",
        "project": {
            "name": pyproject["name"],
            "requires_python": pyproject["requires_python"],
            "version": pyproject["version"],
        },
        "reproducibility": {
            "canonical_json": True,
            "regeneration": "byte_identical",
            "timestamp_free": True,
        },
    }
    profile["profile_hash"] = _hash_excluding(profile, "profile_hash")

    pinnable = {
        "backend_name": contract["backend_name"],
        "license": contract["license"],
        "source_repository": observation["repository"],
    }
    uncovered = sorted(
        set(contract["required"]) - set(pinnable) - set(BLOCKED_FIELD_REASONS)
    )
    overlap = sorted(set(pinnable) & set(BLOCKED_FIELD_REASONS))
    if uncovered or overlap:
        _fail(
            "SCHEMA_COVERAGE_GAP",
            "the readiness map no longer covers the canonical manifest schema",
            {"overlap": overlap, "uncovered": uncovered},
        )

    feature: dict[str, Any] = {
        "authority": dict.fromkeys(AUTHORITY_FLAGS, False),
        "canonical_manifest_readiness": {
            "blocked_fields": dict(BLOCKED_FIELD_REASONS),
            "pinnable_fields": pinnable,
            "schema": BACKEND_SCHEMA_PATH,
            "schema_sha256": inputs[BACKEND_SCHEMA_PATH],
        },
        "enablement_requirements": list(ENABLEMENT_REQUIREMENTS),
        "feature_id": "shinka-backend",
        "features": {
            "disabled_pending_qualification": sorted(FEATURE_EVIDENCE),
            "enabled": [],
        },
        "install_extra_present": False,
        "observation": {
            "commit_short": observation["commit_short"],
            "full_revision_verified": False,
            "release_tag": observation["tag"],
            "source": RESEARCH_PATH,
            "verification_state": "PUBLIC_SOURCE_OBSERVATION_ONLY",
        },
        "qualification": "UNQUALIFIED",
        "status": "DISABLED",
    }
    feature["feature_hash"] = _hash_excluding(feature, "feature_hash")
    return {"feature": feature, "profile": profile}


def emit(root: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
    """Write the build output; a rerun rewrites byte-identical files."""

    base = Path(root)
    target = Path(out_dir) if out_dir is not None else base / OUTPUT_DIR
    documents = build_documents(base)
    target.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    for name, document in (
        (PROFILE_NAME, documents["profile"]),
        (FEATURE_NAME, documents["feature"]),
    ):
        payload = render(document)
        (target / name).write_bytes(payload)
        outputs[f"{OUTPUT_DIR}/{name}"] = (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )

    manifest: dict[str, Any] = {
        "build_id": "v4-b05",
        "generator": {
            "path": GENERATOR_RELPATH,
            "sha256": _file_sha(Path(__file__)),
        },
        "inputs": documents["profile"]["inputs"],
        "outputs": outputs,
        "reproducible": True,
    }
    manifest["manifest_hash"] = _hash_excluding(manifest, "manifest_hash")
    (target / MANIFEST_NAME).write_bytes(render(manifest))
    return {
        "outputs": sorted([*outputs, f"{OUTPUT_DIR}/{MANIFEST_NAME}"]),
        "status": "PASS",
    }


def _load_output(target: Path, name: str) -> dict[str, Any]:
    path = target / name
    if not path.is_file():
        _fail("OUTPUT_MISSING", f"{name} is missing from the build output")
    try:
        loaded = json.loads(path.read_bytes().decode("utf-8"))
    except ValueError as error:
        _fail("OUTPUT_TAMPERED", f"{name} is not parseable JSON: {error}")
        raise  # pragma: no cover - _fail always raises
    if not isinstance(loaded, dict):
        _fail("OUTPUT_TAMPERED", f"{name} is not a JSON object")
    return loaded  # type: ignore[return-value]


def _assert_feature_disabled(feature: Mapping[str, Any]) -> None:
    try:
        status = feature["status"]
        qualification = feature["qualification"]
        enabled = feature["features"]["enabled"]
        authority = feature["authority"]
        extra = feature["install_extra_present"]
    except (KeyError, TypeError):
        _fail("OUTPUT_TAMPERED", "the feature document lost its contract fields")
        raise  # pragma: no cover - _fail always raises
    if status != "DISABLED" or enabled:
        _fail(
            "SHINKA_ENABLED_WITHOUT_QUALIFICATION",
            "no sealed B06/T06 qualification exists, so the feature cannot be enabled",
            {"enabled": list(enabled), "status": status},
        )
    if qualification != "UNQUALIFIED":
        _fail(
            "QUALIFICATION_OVERCLAIM",
            "no qualification evidence exists for the declared level",
            {"qualification": qualification},
        )
    granted = sorted(
        flag
        for flag in AUTHORITY_FLAGS
        if not isinstance(authority, Mapping) or authority.get(flag) is not False
    )
    if granted:
        _fail(
            "AUTHORITY_GRANTED",
            "a backend may hold no evaluator, holdout or promotion authority",
            {"granted": granted},
        )
    if extra is not False:
        _fail(
            "SHINKA_PREINSTALLED",
            "the build may not ship a ShinkaEvolve install extra",
        )


def verify(root: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
    """Re-derive everything and refuse any divergence with a typed code."""

    base = Path(root)
    target = Path(out_dir) if out_dir is not None else base / OUTPUT_DIR

    disk_feature = _load_output(target, FEATURE_NAME)
    _assert_feature_disabled(disk_feature)

    manifest = _load_output(target, MANIFEST_NAME)
    if set(manifest) != set(_MANIFEST_FIELDS):
        _fail("MANIFEST_TAMPERED", "the build manifest lost its field set")
    if _hash_excluding(manifest, "manifest_hash") != manifest["manifest_hash"]:
        _fail("MANIFEST_TAMPERED", "the build manifest does not match its hash")
    generator = manifest["generator"]
    if generator.get("path") != GENERATOR_RELPATH or generator.get(
        "sha256"
    ) != _file_sha(Path(__file__)):
        _fail(
            "GENERATOR_DRIFT",
            "the manifest names a generator other than the one verifying it",
        )
    for relative, recorded in sorted(dict(manifest["inputs"]).items()):
        if relative not in INPUT_PATHS:
            _fail("MANIFEST_TAMPERED", f"undeclared input recorded: {relative}")
        if _file_sha(base / relative) != recorded:
            _fail(
                "INPUT_DRIFT",
                f"{relative} changed after the build output was emitted",
                {"input": relative},
            )

    documents = build_documents(base)
    expected = {
        f"{OUTPUT_DIR}/{PROFILE_NAME}": render(documents["profile"]),
        f"{OUTPUT_DIR}/{FEATURE_NAME}": render(documents["feature"]),
    }
    recorded_outputs = dict(manifest["outputs"])
    if set(recorded_outputs) != set(expected):
        _fail("MANIFEST_TAMPERED", "the manifest does not list the build outputs")
    for relative, payload in sorted(expected.items()):
        name = relative.rsplit("/", 1)[1]
        path = target / name
        if not path.is_file():
            _fail("OUTPUT_MISSING", f"{name} is missing from the build output")
        on_disk = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(on_disk).hexdigest()
        if recorded_outputs[relative] != digest or on_disk != payload:
            _fail(
                "OUTPUT_TAMPERED",
                f"{name} does not match what the tracked inputs produce",
                {"output": relative},
            )

    unexpected = sorted(
        entry.name
        for entry in target.iterdir()
        if entry.name not in (PROFILE_NAME, FEATURE_NAME, MANIFEST_NAME)
    )
    if unexpected:
        _fail(
            "OUTPUT_TAMPERED",
            "the build output holds files no receipt covers",
            {"unexpected": unexpected},
        )

    return {
        "generator_sha256": generator["sha256"],
        "inputs_verified": len(INPUT_PATHS),
        "outputs_verified": len(expected) + 1,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("emit", "verify"))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    try:
        result = emit(root) if arguments.mode == "emit" else verify(root)
    except B05BuildError as error:
        print(
            json.dumps(
                {
                    "code": error.code,
                    "context": error.context,
                    "message": str(error),
                    "status": "FAIL",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
