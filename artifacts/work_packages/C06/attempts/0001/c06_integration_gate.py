#!/usr/bin/env python3
"""C06 generated types, fixtures and compatibility integration gate.

An integration gate reconciles receipts that were produced independently.  Four
of them cover the C05 evolution family and none of them derives from another:
the C05 family index, and the TypeScript, Python and UI contract manifests C02
emits.  If any two disagree about a schema's content hash, one of them is stale,
and this gate refuses rather than picking a winner.

Fixtures are proved against the real repository, not against themselves.  Every
family member must carry its canonical ``examples/sample_*.json`` and that
example must validate against its own canonical schema; where a C05 composite
governs the member, the same fixture must satisfy the composite too, which is
what turns C05's composites from plausible structure into structure the
repository's own fixtures satisfy.  The genome family is where this gets
interesting: only the four mutable genome kinds are candidates, so the eleven
records that merely describe variation are checked from the hostile side — each
must be *refused* by the candidate composite — and are then recorded as
schema-only with the reason, rather than silently skipped.

Compatibility is bound as structure.  ``evolution-compatibility-binding``
composes the canonical CompatibilityMatrix, SchemaMigration and
UpdateImpactReport by ``$ref`` alone, so a migration of an evolution schema
cannot be recorded without the matrix it applies under and the impact it
declares.  As in C05 the composite carries no enum, const, pattern or format of
its own: the canonical files stay the single declaring source (EF4-I22).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import jsonschema
from referencing import Registry, Resource

CANONICAL_ID_PREFIX: Final = "https://epistemic-foundry.local/schemas/"
BUNDLE_ID_PREFIX: Final = "https://epistemic-foundry.local/schemas/v4_c06/"
OUTPUT_DIR: Final = "schemas/v4_c06"
PARITY_NAME: Final = "generated-projection-parity.json"
INDEX_NAME: Final = "integration-index.json"
BINDING_NAME: Final = "evolution-compatibility-binding.schema.json"
GENERATOR_RELPATH: Final = (
    "artifacts/work_packages/C06/attempts/0001/c06_integration_gate.py"
)
C05_INDEX_PATH: Final = "schemas/v4_c05/family-index.json"
C05_BUNDLE_DIR: Final = "schemas/v4_c05"
#: The three independent generated projections C02 emits.  Each carries its own
#: manifest; the gate reconciles them rather than trusting any one.
PROJECTION_MANIFESTS: Final = {
    "python": "python/epistemic_foundry/contracts/contract-manifest.json",
    "typescript": "packages/contracts/src/generated/contract-manifest.json",
    "web": "web/src/generated/contract-manifest.json",
}
#: Which C05 composite a family's fixtures must validate against, for the
#: families whose composite is a one-of over the whole membership.  The genome
#: family is deliberately absent: its composite admits only the four mutable
#: genome kinds (EF4-I41), so the rest of the family is bound separately.
FAMILY_COMPOSITES: Final = {
    "archive": "archive-preservation-record.schema.json",
    "evaluator": "evaluator-authority-surface.schema.json",
}
#: The composite that binds exactly the mutable search space, whose membership
#: is read from the sealed C05 index rather than restated here.
CANDIDATE_COMPOSITE: Final = "evolution-candidate.schema.json"
#: The family whose members are not all candidates.  A record that describes
#: variation is not itself a thing the chamber may mutate.
CANDIDATE_FAMILY: Final = "genome"
#: Why a genome-family member outside the mutable space carries no composite.
SCHEMA_ONLY_REASON: Final = (
    "genome-family record that describes candidate variation without being a "
    "candidate the Evolution Chamber may mutate (EF4-I41)"
)
#: Assembled composites: the composite name mapped to the field each member
#: fills, so a fixture set is proved to satisfy the whole record.
ASSEMBLED_COMPOSITES: Final = {
    "adaptive-search-statistics.schema.json": {
        "decision-stability-report": "decision_stability_report",
        "multiple-testing-adjustment": "multiple_testing_adjustment",
        "selective-inference-report": "selective_inference_report",
        "sequential-testing-ledger": "sequential_testing_ledger",
        "surrogate-triage-report": "surrogate_triage_report",
    },
    "external-backend-binding.schema.json": {
        "backend-adapter-qualification": "qualification",
        "imported-run-record": "imported_run",
        "shinka-backend-manifest": "backend_manifest",
    },
}
#: Canonical contracts the compatibility binding composes, by field.
COMPATIBILITY_MEMBERS: Final = {
    "compatibility_matrix": "compatibility-matrix",
    "impact_report": "update-impact-report",
    "migration": "schema-migration",
}
#: A migration cannot be recorded without the matrix it applies under.
COMPATIBILITY_REQUIRED: Final = ("compatibility_matrix", "migration")
FORBIDDEN_COMPOSITE_KEYWORDS: Final = ("const", "enum", "pattern", "format")

_INDEX_FIELDS: Final = frozenset(
    {
        "bundle_id",
        "compatibility",
        "fixtures",
        "generator",
        "index_hash",
        "member_count",
        "outputs",
        "projections",
        "sources",
    }
)
_PARITY_FIELDS: Final = frozenset(
    {"agreed_member_count", "members", "parity_hash", "projections"}
)


class C06GateError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise C06GateError(code, message, context)


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
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _read_json(root: Path, relative: str, code: str) -> dict[str, Any]:
    path = root / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(code, f"{relative} could not be read: {error}", {"path": relative})
        raise  # pragma: no cover - _fail always raises
    if not isinstance(loaded, dict):
        _fail(code, f"{relative} is not a JSON object", {"path": relative})
    return loaded  # type: ignore[return-value]


def _canonical_ref(name: str) -> str:
    return f"{CANONICAL_ID_PREFIX}{name}.schema.json"


def _scan_forbidden(node: object) -> list[str]:
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in FORBIDDEN_COMPOSITE_KEYWORDS:
                found.add(str(key))
            found.update(_scan_forbidden(value))
    elif isinstance(node, list):
        for value in node:
            found.update(_scan_forbidden(value))
    return sorted(found)


def family_members(root: str | Path) -> dict[str, list[str]]:
    """Family membership as the sealed C05 index recorded it."""

    index = _read_json(Path(root), C05_INDEX_PATH, "C05_INDEX_UNREADABLE")
    families = index.get("families")
    if not isinstance(families, Mapping) or not families:
        _fail("C05_INDEX_UNREADABLE", "the C05 index declares no families")
    membership: dict[str, list[str]] = {}
    for family, record in families.items():  # type: ignore[union-attr]
        entries = record.get("members") if isinstance(record, Mapping) else None
        if not isinstance(entries, list) or not entries:
            _fail(
                "C05_INDEX_UNREADABLE",
                f"family {family} declares no members",
                {"family": family},
            )
        membership[str(family)] = sorted(
            str(entry["canonical"])
            .removeprefix("schemas/")
            .removesuffix(".schema.json")
            for entry in entries  # type: ignore[union-attr]
        )
    unknown = sorted(set(FAMILY_COMPOSITES) - set(membership))
    if unknown:
        _fail(
            "C05_INDEX_UNREADABLE",
            "the composite table names a family the C05 index does not carry",
            {"unknown": unknown},
        )
    return membership


def _all_members(membership: Mapping[str, list[str]]) -> list[str]:
    ordered = sorted({name for names in membership.values() for name in names})
    if not ordered:
        _fail("C05_INDEX_UNREADABLE", "the C05 index carries no members")
    return ordered


def reconcile_projections(root: str | Path) -> dict[str, Any]:
    """Refuse any disagreement between the four independent receipts."""

    base = Path(root)
    membership = family_members(base)
    names = _all_members(membership)
    index = _read_json(base, C05_INDEX_PATH, "C05_INDEX_UNREADABLE")
    c05_hashes = {
        str(entry["canonical"]): str(entry["sha256"])
        for record in index["families"].values()
        for entry in record["members"]
    }

    projections: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, dict[str, Any]]] = {}
    for language, relative in sorted(PROJECTION_MANIFESTS.items()):
        manifest = _read_json(base, relative, "PROJECTION_UNREADABLE")
        contracts = manifest.get("contracts")
        if not isinstance(contracts, list) or not contracts:
            _fail(
                "PROJECTION_UNREADABLE",
                f"{relative} records no contracts",
                {"language": language},
            )
        records[language] = {
            str(entry["schema_file"]): dict(entry)
            for entry in contracts  # type: ignore[union-attr]
        }
        projections[language] = {
            "contract_count": len(records[language]),
            "manifest": relative,
            "manifest_sha256": _file_sha(base / relative),
            "schema_bundle_sha256": str(manifest.get("schema_bundle_sha256", "")),
        }

    bundles = {entry["schema_bundle_sha256"] for entry in projections.values()}
    if len(bundles) != 1 or "" in bundles:
        _fail(
            "PROJECTION_BUNDLE_DIVERGED",
            "the generated projections disagree about the canonical bundle",
            {
                language: entry["schema_bundle_sha256"]
                for language, entry in projections.items()
            },
        )

    members: dict[str, dict[str, Any]] = {}
    for name in names:
        key = f"schemas/{name}.schema.json"
        live = base / key
        if not live.is_file():
            _fail("MEMBER_MISSING", f"{key} is gone", {"member": name})
        canonical_sha = _file_sha(live)
        if c05_hashes.get(key) != canonical_sha:
            _fail(
                "C05_INDEX_STALE",
                "the C05 index no longer matches the live canonical file",
                {"member": name},
            )
        declared = {}
        for language in records:
            entry = records[language].get(key)
            if entry is None:
                _fail(
                    "PROJECTION_MEMBER_MISSING",
                    f"the {language} projection does not cover {name}",
                    {"language": language, "member": name},
                )
            declared[language] = str(entry["source_sha256"])  # type: ignore[index]
        if len(set(declared.values())) != 1:
            _fail(
                "PROJECTION_DIVERGED",
                "the generated projections disagree about a member's hash",
                {"declared": declared, "member": name},
            )
        agreed = next(iter(declared.values()))
        if agreed != canonical_sha:
            _fail(
                "PROJECTION_STALE",
                "the generated projections were built from a different schema",
                {"canonical": canonical_sha, "declared": agreed, "member": name},
            )
        example_key = f"examples/sample_{name}.json"
        example = base / example_key
        if not example.is_file():
            _fail(
                "FIXTURE_MISSING",
                f"{name} has no canonical example",
                {"member": name},
            )
        example_declared = {
            language: str(records[language][key]["example_sha256"])
            for language in records
        }
        if len(set(example_declared.values())) != 1:
            _fail(
                "PROJECTION_DIVERGED",
                "the generated projections disagree about a fixture's hash",
                {"declared": example_declared, "member": name},
            )
        example_sha = _file_sha(example)
        if next(iter(example_declared.values())) != example_sha:
            _fail(
                "FIXTURE_STALE",
                "the generated projections were built from a different fixture",
                {"member": name},
            )
        members[name] = {
            "canonical": key,
            "canonical_sha256": canonical_sha,
            "example": example_key,
            "example_sha256": example_sha,
            "title": str(records["python"][key]["title"]),
        }

    parity: dict[str, Any] = {
        "agreed_member_count": len(members),
        "members": members,
        "projections": projections,
    }
    parity["parity_hash"] = _hash_excluding(parity, "parity_hash")
    return parity


def _registry(root: Path) -> Registry:
    resources = []
    for directory in ("schemas", C05_BUNDLE_DIR, OUTPUT_DIR):
        target = root / directory
        if not target.is_dir():
            continue
        for path in sorted(target.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            resources.append((str(document["$id"]), Resource.from_contents(document)))
    return Registry().with_resources(resources)


def mutable_search_space(root: str | Path) -> tuple[str, ...]:
    """The four genome kinds, as the sealed C05 index recorded them."""

    index = _read_json(Path(root), C05_INDEX_PATH, "C05_INDEX_UNREADABLE")
    declared = index.get("mutable_search_space")
    if not isinstance(declared, list) or not declared:
        _fail("C05_INDEX_UNREADABLE", "the C05 index declares no mutable space")
    return tuple(
        sorted(
            str(entry).removeprefix("schemas/").removesuffix(".schema.json")
            for entry in declared  # type: ignore[union-attr]
        )
    )


def audit_fixtures(root: str | Path) -> dict[str, Any]:
    """Prove the canonical fixtures satisfy their schemas and composites.

    Every member's fixture is validated against its own canonical schema.  A
    member is additionally validated against a C05 composite when one governs
    it; the genome-family records that are not candidates carry none by design,
    and are recorded as schema-only with that reason rather than silently
    skipped.
    """

    base = Path(root)
    membership = family_members(base)
    registry = _registry(base)
    checked = 0
    bindings: dict[str, str] = {}

    for name in _all_members(membership):
        schema_path = base / "schemas" / f"{name}.schema.json"
        example = json.loads(
            (base / f"examples/sample_{name}.json").read_text(encoding="utf-8")
        )
        validator = jsonschema.Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8")), registry=registry
        )
        errors = sorted(validator.iter_errors(example), key=lambda err: err.path)
        if errors:
            _fail(
                "FIXTURE_NONCONFORMANT",
                "a canonical fixture does not satisfy its own schema",
                {"error": errors[0].message[:200], "member": name},
            )
        checked += 1

    candidates = mutable_search_space(base)
    unknown = sorted(set(candidates) - set(membership[CANDIDATE_FAMILY]))
    if unknown:
        _fail(
            "C05_INDEX_UNREADABLE",
            "the mutable search space names a member outside the genome family",
            {"unknown": unknown},
        )
    candidate_path = base / C05_BUNDLE_DIR / CANDIDATE_COMPOSITE
    if not candidate_path.is_file():
        _fail(
            "COMPOSITE_MISSING",
            f"{CANDIDATE_COMPOSITE} is not in the C05 bundle",
            {"composite": CANDIDATE_COMPOSITE},
        )
    candidate_validator = jsonschema.Draft202012Validator(
        json.loads(candidate_path.read_text(encoding="utf-8")), registry=registry
    )
    for name in candidates:
        example = json.loads(
            (base / f"examples/sample_{name}.json").read_text(encoding="utf-8")
        )
        errors = sorted(
            candidate_validator.iter_errors(example), key=lambda err: err.path
        )
        if errors:
            _fail(
                "FIXTURE_NONCONFORMANT",
                "a canonical genome fixture is not admitted as a candidate",
                {
                    "composite": CANDIDATE_COMPOSITE,
                    "error": errors[0].message[:200],
                    "member": name,
                },
            )
        bindings[name] = CANDIDATE_COMPOSITE
        checked += 1

    # The boundary proved from the hostile side, with the repository's own
    # fixtures: a genome-family record that is not a candidate must be refused.
    schema_only: dict[str, str] = {}
    for name in membership[CANDIDATE_FAMILY]:
        if name in candidates:
            continue
        example = json.loads(
            (base / f"examples/sample_{name}.json").read_text(encoding="utf-8")
        )
        if candidate_validator.is_valid(example):
            _fail(
                "AUTHORITY_IN_MUTABLE_SPACE",
                "a non-candidate genome-family fixture is admitted as a candidate",
                {"member": name},
            )
        schema_only[name] = SCHEMA_ONLY_REASON
        checked += 1

    for family, composite in sorted(FAMILY_COMPOSITES.items()):
        path = base / C05_BUNDLE_DIR / composite
        if not path.is_file():
            _fail(
                "COMPOSITE_MISSING",
                f"{composite} is not in the C05 bundle",
                {"composite": composite},
            )
        validator = jsonschema.Draft202012Validator(
            json.loads(path.read_text(encoding="utf-8")), registry=registry
        )
        for name in membership[family]:
            example = json.loads(
                (base / f"examples/sample_{name}.json").read_text(encoding="utf-8")
            )
            errors = sorted(validator.iter_errors(example), key=lambda err: err.path)
            if errors:
                _fail(
                    "FIXTURE_NONCONFORMANT",
                    "a canonical fixture does not satisfy its C05 composite",
                    {
                        "composite": composite,
                        "error": errors[0].message[:200],
                        "member": name,
                    },
                )
            bindings[name] = composite
            checked += 1

    for composite, fields in sorted(ASSEMBLED_COMPOSITES.items()):
        path = base / C05_BUNDLE_DIR / composite
        if not path.is_file():
            _fail(
                "COMPOSITE_MISSING",
                f"{composite} is not in the C05 bundle",
                {"composite": composite},
            )
        validator = jsonschema.Draft202012Validator(
            json.loads(path.read_text(encoding="utf-8")), registry=registry
        )
        assembled = {
            field: json.loads(
                (base / f"examples/sample_{name}.json").read_text(encoding="utf-8")
            )
            for name, field in sorted(fields.items())
        }
        errors = sorted(validator.iter_errors(assembled), key=lambda err: err.path)
        if errors:
            _fail(
                "FIXTURE_NONCONFORMANT",
                "the assembled canonical fixtures do not satisfy their composite",
                {"composite": composite, "error": errors[0].message[:200]},
            )
        for name in fields:
            bindings[name] = composite
            checked += 1

    accounted = set(bindings) | set(schema_only)
    expected = set(_all_members(membership))
    missing = sorted(expected - accounted)
    unexpected = sorted(accounted - expected)
    if missing or unexpected:
        _fail(
            "FIXTURE_UNACCOUNTED",
            "the fixture audit does not account for exactly the C05 membership",
            {"missing": missing, "unexpected": unexpected},
        )
    return {
        "composite_bound": dict(sorted(bindings.items())),
        "composites": sorted(
            [CANDIDATE_COMPOSITE, *FAMILY_COMPOSITES.values(), *ASSEMBLED_COMPOSITES]
        ),
        "member_count": len(expected),
        "schema_only": dict(sorted(schema_only.items())),
        "status": "PASS",
        "validations": checked,
    }


def build_binding(root: str | Path) -> dict[str, Any]:
    """The compatibility composite; pure ``$ref`` structure, no vocabulary."""

    base = Path(root)
    for name in sorted(COMPATIBILITY_MEMBERS.values()):
        path = base / "schemas" / f"{name}.schema.json"
        if not path.is_file():
            _fail(
                "MEMBER_MISSING",
                f"{name} has no canonical file",
                {"member": name},
            )
        declared = json.loads(path.read_text(encoding="utf-8")).get("$id")
        if declared != _canonical_ref(name):
            _fail(
                "MEMBER_ID_MISMATCH",
                f"{name} does not declare the canonical $id this bundle references",
                {"declared": declared, "expected": _canonical_ref(name)},
            )
    unknown = sorted(set(COMPATIBILITY_REQUIRED) - set(COMPATIBILITY_MEMBERS))
    if unknown:
        _fail(
            "COMPATIBILITY_TABLE_INVALID",
            "a required compatibility field names no canonical member",
            {"unknown": unknown},
        )

    document = {
        "$id": f"{BUNDLE_ID_PREFIX}{BINDING_NAME}",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "description": "Compatibility binding for an evolution-family schema "
        "change: a migration cannot be recorded without the compatibility "
        "matrix it applies under, and the impact it declares travels with it. "
        "Every constraint is a reference to the canonical contract that owns "
        "it, so this composite adds no vocabulary of its own (EF4-I22).",
        "properties": {
            field: {"$ref": _canonical_ref(name)}
            for field, name in sorted(COMPATIBILITY_MEMBERS.items())
        },
        "required": sorted(COMPATIBILITY_REQUIRED),
        "title": "EvolutionCompatibilityBinding",
        "type": "object",
    }
    smuggled = _scan_forbidden(document)
    if smuggled:
        _fail(
            "VOCABULARY_SMUGGLED",
            f"{BINDING_NAME} declares vocabulary the canonical sources own",
            {"keywords": smuggled},
        )
    return document


def build_index(
    root: str | Path,
    parity: Mapping[str, Any],
    fixtures: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    base = Path(root)
    index: dict[str, Any] = {
        "bundle_id": "v4-c06-integration-gate",
        "compatibility": {
            "binding": f"{OUTPUT_DIR}/{BINDING_NAME}",
            "binding_sha256": "sha256:" + hashlib.sha256(render(binding)).hexdigest(),
            "members": dict(sorted(COMPATIBILITY_MEMBERS.items())),
            "required": sorted(COMPATIBILITY_REQUIRED),
        },
        "fixtures": dict(fixtures),
        "generator": {
            "path": GENERATOR_RELPATH,
            "sha256": _file_sha(Path(__file__)),
        },
        "member_count": int(parity["agreed_member_count"]),
        "outputs": {
            f"{OUTPUT_DIR}/{BINDING_NAME}": "sha256:"
            + hashlib.sha256(render(binding)).hexdigest(),
            f"{OUTPUT_DIR}/{PARITY_NAME}": "sha256:"
            + hashlib.sha256(render(parity)).hexdigest(),
        },
        "projections": dict(parity["projections"]),
        "sources": {
            C05_INDEX_PATH: _file_sha(base / C05_INDEX_PATH),
            **{
                relative: _file_sha(base / relative)
                for relative in sorted(PROJECTION_MANIFESTS.values())
            },
        },
    }
    index["index_hash"] = _hash_excluding(index, "index_hash")
    return index


def emit(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    target = base / OUTPUT_DIR
    parity = reconcile_projections(base)
    binding = build_binding(base)
    target.mkdir(parents=True, exist_ok=True)
    (target / BINDING_NAME).write_bytes(render(binding))
    fixtures = audit_fixtures(base)
    (target / PARITY_NAME).write_bytes(render(parity))
    index = build_index(base, parity, fixtures, binding)
    (target / INDEX_NAME).write_bytes(render(index))
    return {
        "fixtures_validated": fixtures["validations"],
        "member_count": index["member_count"],
        "outputs": sorted([BINDING_NAME, PARITY_NAME, INDEX_NAME]),
        "status": "PASS",
    }


def _load_output(target: Path, name: str) -> dict[str, Any]:
    path = target / name
    if not path.is_file():
        _fail("OUTPUT_MISSING", f"{name} is missing from the bundle")
    try:
        loaded = json.loads(path.read_bytes().decode("utf-8"))
    except ValueError as error:
        _fail("OUTPUT_TAMPERED", f"{name} is not parseable JSON: {error}")
        raise  # pragma: no cover - _fail always raises
    if not isinstance(loaded, dict):
        _fail("OUTPUT_TAMPERED", f"{name} is not a JSON object")
    return loaded  # type: ignore[return-value]


def verify(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    target = base / OUTPUT_DIR

    index = _load_output(target, INDEX_NAME)
    if set(index) != set(_INDEX_FIELDS):
        _fail("INDEX_TAMPERED", "the integration index lost its field set")
    if _hash_excluding(index, "index_hash") != index["index_hash"]:
        _fail("INDEX_TAMPERED", "the integration index does not match its own hash")
    generator = index["generator"]
    if generator.get("path") != GENERATOR_RELPATH or generator.get(
        "sha256"
    ) != _file_sha(Path(__file__)):
        _fail(
            "GENERATOR_DRIFT",
            "the index names a generator other than the one verifying it",
        )
    for relative, recorded in sorted(dict(index["sources"]).items()):
        if _file_sha(base / relative) != recorded:
            _fail(
                "SOURCE_DRIFT",
                f"{relative} changed after the bundle was emitted",
                {"source": relative},
            )

    parity = reconcile_projections(base)
    binding = build_binding(base)
    fixtures = audit_fixtures(base)
    expected = {
        f"{OUTPUT_DIR}/{BINDING_NAME}": render(binding),
        f"{OUTPUT_DIR}/{PARITY_NAME}": render(parity),
    }
    if set(dict(index["outputs"])) != set(expected):
        _fail("INDEX_TAMPERED", "the index does not list the bundle outputs")
    for relative, payload in sorted(expected.items()):
        name = relative.rsplit("/", 1)[1]
        path = target / name
        if not path.is_file():
            _fail("OUTPUT_MISSING", f"{name} is missing from the bundle")
        on_disk = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(on_disk).hexdigest()
        if index["outputs"][relative] != digest:
            _fail(
                "INDEX_STALE",
                f"the index does not record the on-disk {name}",
                {"output": relative},
            )
        if on_disk != payload:
            _fail(
                "OUTPUT_TAMPERED",
                f"{name} does not match what the live sources produce",
                {"output": relative},
            )

    stored = _load_output(target, PARITY_NAME)
    if set(stored) != set(_PARITY_FIELDS):
        _fail("OUTPUT_TAMPERED", "the parity record lost its field set")
    if _hash_excluding(stored, "parity_hash") != stored["parity_hash"]:
        _fail("OUTPUT_TAMPERED", "the parity record does not match its own hash")
    if index["fixtures"] != fixtures:
        _fail("INDEX_STALE", "the index does not record the fixture audit")

    smuggled = _scan_forbidden(_load_output(target, BINDING_NAME))
    if smuggled:
        _fail(
            "VOCABULARY_SMUGGLED",
            f"{BINDING_NAME} declares vocabulary the canonical sources own",
            {"keywords": smuggled},
        )

    unexpected = sorted(
        entry.name
        for entry in target.iterdir()
        if entry.name not in (BINDING_NAME, PARITY_NAME, INDEX_NAME)
    )
    if unexpected:
        _fail(
            "OUTPUT_TAMPERED",
            "the bundle holds files no receipt covers",
            {"unexpected": unexpected},
        )

    return {
        "fixtures_validated": fixtures["validations"],
        "member_count": int(parity["agreed_member_count"]),
        "projections_reconciled": len(PROJECTION_MANIFESTS),
        "sources_verified": len(index["sources"]),
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("emit", "verify"))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    try:
        result = emit(root) if arguments.mode == "emit" else verify(root)
    except C06GateError as error:
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
