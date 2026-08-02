#!/usr/bin/env python3
"""C05 evolution genome, evaluator, archive, statistics and adapter schema bundle.

``schemas/v4_c05/`` implements the evolution schema family as a composition
layer over the sealed canonical contracts, never as a restatement of them.  The
canonical files under ``schemas/`` stay the single declaring source (C01
authority, EF4-I22): every composite here is pure ``$ref`` structure — no enum,
no const, no pattern — so a vocabulary can never fork.

The bundle draws the one boundary evolution integrity depends on.  The mutable
search space is exactly the four candidate genome kinds (EF4-I41: the chamber
may propose, mutate, challenge and rank candidates but cannot own evidence
truth, evaluator authority, policy, hidden holdout, promotion or release), and
the evaluator surface, the archive, the adaptive-search statistics and the
external backend binding sit outside it.  ``adaptive-search-statistics``
encodes EF4-I53 structurally: an adaptive search result cannot validate
without its multiplicity, sequential and selective-inference records.
``external-backend-binding`` encodes EF4-I63: an imported result cannot
validate without the pinned backend manifest and its qualification.

``family-index.json`` is the receipt: every member and composite is content-
addressed, regeneration is byte-identical, and verification re-derives the
whole bundle from the live canonical files with typed refusals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

CANONICAL_ID_PREFIX: Final = "https://epistemic-foundry.local/schemas/"
BUNDLE_ID_PREFIX: Final = "https://epistemic-foundry.local/schemas/v4_c05/"
OUTPUT_DIR: Final = "schemas/v4_c05"
INDEX_NAME: Final = "family-index.json"
GENERATOR_RELPATH: Final = (
    "artifacts/work_packages/C05/attempts/0001/c05_schema_bundle.py"
)
#: JSON Schema keywords that would declare vocabulary or shape locally.  A
#: composite carrying any of these has forked the canonical source (EF4-I22).
FORBIDDEN_COMPOSITE_KEYWORDS: Final = ("const", "enum", "pattern", "format")

#: The five families the package title names, each bound to the invariants it
#: implements.  Membership is exhaustive over the evolution schema family.
FAMILIES: Final = {
    "genome": {
        "invariants": ("EF4-I41", "EF4-I42", "EF4-I55"),
        "members": (
            "candidate-generation-record",
            "candidate-lineage",
            "challenge-genome",
            "crossover-compatibility-report",
            "experiment-genome",
            "falsifier-gene",
            "hypothesis-genome",
            "model-routing-receipt",
            "mutation-operator-spec",
            "mutation-receipt",
            "operator-bandit-state",
            "parent-selection-receipt",
            "prediction-gene",
            "prompt-genome",
            "prompt-mutation-proposal",
        ),
    },
    "evaluator": {
        "invariants": ("EF4-I43", "EF4-I44", "EF4-I56"),
        "members": (
            "challenge-result",
            "evaluation-run",
            "evaluator-bundle",
            "evaluator-mutation-proposal",
            "evaluator-qualification-report",
            "fitness-evidence-receipt",
            "fitness-vector",
            "holdout-manifest",
            "leakage-audit",
            "stage-evaluation-result",
        ),
    },
    "archive": {
        "invariants": ("EF4-I48", "EF4-I49", "EF4-I50"),
        "members": (
            "archive-rebalance-plan",
            "epistemic-archive-entry",
            "epistemic-niche",
            "island-state",
            "lineage-diversity-report",
            "novelty-assessment",
            "novelty-vector",
            "pareto-front-snapshot",
            "quality-diversity-map",
        ),
    },
    "statistics": {
        "invariants": ("EF4-I53", "EF4-I59"),
        "members": (
            "decision-stability-report",
            "multiple-testing-adjustment",
            "selective-inference-report",
            "sequential-testing-ledger",
            "surrogate-triage-report",
        ),
    },
    "adapter": {
        "invariants": ("EF4-I63",),
        "members": (
            "backend-adapter-qualification",
            "imported-run-record",
            "shinka-backend-manifest",
        ),
    },
}

#: Exactly what the Evolution Chamber may mutate (EF4-I41).  Genes ride inside
#: genomes; operator and routing records describe variation but are not
#: themselves candidates.
MUTABLE_SEARCH_SPACE: Final = (
    "challenge-genome",
    "experiment-genome",
    "hypothesis-genome",
    "prompt-genome",
)

#: Evolution-adjacent canonical schemas this bundle deliberately leaves out,
#: each with the owner that consumes it.  Exclusion is explicit, not silent.
EXCLUDED_WITH_REASONS: Final = {
    "evolution-checkpoint": (
        "atomic resume surface of the EVOLVE subprotocol; the F05 state "
        "machine and D05 checkpoint store own it (EF4-I61)"
    ),
    "evolution-run-spec": (
        "run-level protocol contract consumed by the F05 EVOLVE state machine"
    ),
    "evolution-stop-certificate": (
        "typed stop surface of the EVOLVE subprotocol; F05 owns it (EF4-I62)"
    ),
    "red-queen-round": (
        "co-evolution round protocol record consumed by the F05 state machine (EF4-I52)"
    ),
}

_INDEX_FIELDS: Final = frozenset(
    {
        "bundle_id",
        "composites",
        "excluded",
        "families",
        "generator",
        "index_hash",
        "member_count",
        "mutable_search_space",
    }
)


class C05BundleError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise C05BundleError(code, message, context)


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


def members() -> tuple[str, ...]:
    ordered: list[str] = []
    for family in FAMILIES.values():
        ordered.extend(family["members"])
    return tuple(sorted(ordered))


def _canonical_ref(name: str) -> str:
    return f"{CANONICAL_ID_PREFIX}{name}.schema.json"


def _one_of_composite(
    file_name: str, title: str, description: str, member_names: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "$id": f"{BUNDLE_ID_PREFIX}{file_name}",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "description": description,
        "oneOf": [{"$ref": _canonical_ref(name)} for name in member_names],
        "title": title,
    }


def build_composites(root: str | Path) -> dict[str, dict[str, Any]]:
    """Derive the five composites; the canonical files stay untouched."""

    base = Path(root)
    for name in members():
        path = base / "schemas" / f"{name}.schema.json"
        if not path.is_file():
            _fail(
                "MEMBER_MISSING",
                f"{name} is named by the family table but has no canonical file",
                {"member": name},
            )
        declared = json.loads(path.read_text(encoding="utf-8")).get("$id")
        if declared != _canonical_ref(name):
            _fail(
                "MEMBER_ID_MISMATCH",
                f"{name} does not declare the canonical $id this bundle references",
                {"declared": declared, "expected": _canonical_ref(name)},
            )

    listed = list(members())
    if len(listed) != len(set(listed)):
        _fail("FAMILY_OVERLAP", "a canonical schema is claimed by two families")
    missing_mutable = sorted(
        set(MUTABLE_SEARCH_SPACE) - set(FAMILIES["genome"]["members"])
    )
    if missing_mutable:
        _fail(
            "MUTABLE_SPACE_MISMATCH",
            "the mutable search space must live inside the genome family",
            {"missing": missing_mutable},
        )
    overlap = sorted(set(EXCLUDED_WITH_REASONS) & set(listed))
    if overlap:
        _fail(
            "FAMILY_OVERLAP",
            "an excluded schema cannot also be a family member",
            {"overlap": overlap},
        )

    composites = {
        "evolution-candidate.schema.json": _one_of_composite(
            "evolution-candidate.schema.json",
            "EvolutionCandidate",
            "The mutable search space, exactly (EF4-I41, EF4-I42): the "
            "Evolution Chamber may mutate candidate genomes only, so a "
            "document is a candidate if and only if it is one of the four "
            "canonical genome kinds. Evaluator, holdout, policy, promotion "
            "and archive documents can never validate here.",
            MUTABLE_SEARCH_SPACE,
        ),
        "evaluator-authority-surface.schema.json": _one_of_composite(
            "evaluator-authority-surface.schema.json",
            "EvaluatorAuthoritySurface",
            "The evaluator-owned surface, outside the mutable search space "
            "(EF4-I43, EF4-I44, EF4-I56): one content-addressed evaluator "
            "bundle per run, a hidden holdout no candidate path may read, "
            "and defect proposals that apply to future runs only.",
            FAMILIES["evaluator"]["members"],
        ),
        "archive-preservation-record.schema.json": _one_of_composite(
            "archive-preservation-record.schema.json",
            "ArchivePreservationRecord",
            "The quality-diversity archive surface (EF4-I48, EF4-I49, "
            "EF4-I50): niches and trade-offs rather than a single top score, "
            "with negative, null, unsafe and minority memory protected from "
            "fitness-only eviction.",
            FAMILIES["archive"]["members"],
        ),
        "adaptive-search-statistics.schema.json": {
            "$id": f"{BUNDLE_ID_PREFIX}adaptive-search-statistics.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "description": "Adaptive best-of-many search evidence (EF4-I53, "
            "EF4-I59): a search result cannot validate without its "
            "multiplicity adjustment, its sequential-testing ledger and its "
            "selective-inference report; stability and surrogate-triage "
            "records may accompany them but replace nothing.",
            "properties": {
                "decision_stability_report": {
                    "$ref": _canonical_ref("decision-stability-report")
                },
                "multiple_testing_adjustment": {
                    "$ref": _canonical_ref("multiple-testing-adjustment")
                },
                "selective_inference_report": {
                    "$ref": _canonical_ref("selective-inference-report")
                },
                "sequential_testing_ledger": {
                    "$ref": _canonical_ref("sequential-testing-ledger")
                },
                "surrogate_triage_report": {
                    "$ref": _canonical_ref("surrogate-triage-report")
                },
            },
            "required": [
                "multiple_testing_adjustment",
                "selective_inference_report",
                "sequential_testing_ledger",
            ],
            "title": "AdaptiveSearchStatistics",
            "type": "object",
        },
        "external-backend-binding.schema.json": {
            "$id": f"{BUNDLE_ID_PREFIX}external-backend-binding.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "description": "External backend isolation (EF4-I63): an imported "
            "run cannot validate without the exact pinned backend manifest "
            "and its qualification, and nothing a backend reports becomes "
            "Foundry authority by validating here.",
            "properties": {
                "backend_manifest": {"$ref": _canonical_ref("shinka-backend-manifest")},
                "imported_run": {"$ref": _canonical_ref("imported-run-record")},
                "qualification": {
                    "$ref": _canonical_ref("backend-adapter-qualification")
                },
            },
            "required": ["backend_manifest", "imported_run", "qualification"],
            "title": "ExternalBackendBinding",
            "type": "object",
        },
    }

    for file_name, document in composites.items():
        smuggled = _scan_forbidden(document)
        if smuggled:
            _fail(
                "VOCABULARY_SMUGGLED",
                f"{file_name} declares vocabulary the canonical sources own",
                {"file": file_name, "keywords": smuggled},
            )
    return composites


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


def build_index(
    root: str | Path, composites: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    base = Path(root)
    index: dict[str, Any] = {
        "bundle_id": "v4-c05-evolution-schema-bundle",
        "composites": {
            file_name: "sha256:" + hashlib.sha256(render(document)).hexdigest()
            for file_name, document in composites.items()
        },
        "excluded": [
            {
                "canonical": f"schemas/{name}.schema.json",
                "reason": reason,
            }
            for name, reason in sorted(EXCLUDED_WITH_REASONS.items())
        ],
        "families": {
            family_name: {
                "invariants": list(family["invariants"]),
                "members": [
                    {
                        "canonical": f"schemas/{name}.schema.json",
                        "sha256": _file_sha(base / "schemas" / f"{name}.schema.json"),
                    }
                    for name in family["members"]
                ],
            }
            for family_name, family in FAMILIES.items()
        },
        "generator": {
            "path": GENERATOR_RELPATH,
            "sha256": _file_sha(Path(__file__)),
        },
        "member_count": len(members()),
        "mutable_search_space": [
            f"schemas/{name}.schema.json" for name in MUTABLE_SEARCH_SPACE
        ],
    }
    index["index_hash"] = _hash_excluding(index, "index_hash")
    return index


def emit(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    target = base / OUTPUT_DIR
    composites = build_composites(base)
    target.mkdir(parents=True, exist_ok=True)
    for file_name, document in composites.items():
        (target / file_name).write_bytes(render(document))
    index = build_index(base, composites)
    (target / INDEX_NAME).write_bytes(render(index))
    return {
        "member_count": index["member_count"],
        "outputs": sorted([*composites, INDEX_NAME]),
        "status": "PASS",
    }


def _load(target: Path, name: str) -> dict[str, Any]:
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

    candidate = _load(target, "evolution-candidate.schema.json")
    refs = sorted(str(entry.get("$ref", "")) for entry in candidate.get("oneOf", []))
    expected_refs = sorted(_canonical_ref(name) for name in MUTABLE_SEARCH_SPACE)
    extra = sorted(set(refs) - set(expected_refs))
    missing = sorted(set(expected_refs) - set(refs))
    if extra:
        _fail(
            "AUTHORITY_IN_MUTABLE_SPACE",
            "the candidate composite admits a document outside the four genome kinds",
            {"extra": extra},
        )
    if missing:
        _fail(
            "MUTABLE_SPACE_MISMATCH",
            "the candidate composite no longer covers the mutable search space",
            {"missing": missing},
        )

    index = _load(target, INDEX_NAME)
    if set(index) != set(_INDEX_FIELDS):
        _fail("INDEX_TAMPERED", "the family index lost its field set")
    if _hash_excluding(index, "index_hash") != index["index_hash"]:
        _fail("INDEX_TAMPERED", "the family index does not match its own hash")
    generator = index["generator"]
    if generator.get("path") != GENERATOR_RELPATH or generator.get(
        "sha256"
    ) != _file_sha(Path(__file__)):
        _fail(
            "GENERATOR_DRIFT",
            "the index names a generator other than the one verifying it",
        )

    composites = build_composites(base)
    for file_name, document in composites.items():
        payload = render(document)
        path = target / file_name
        if not path.is_file():
            _fail("OUTPUT_MISSING", f"{file_name} is missing from the bundle")
        on_disk = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(on_disk).hexdigest()
        if index["composites"].get(file_name) != digest:
            _fail(
                "INDEX_STALE",
                f"the index does not record the on-disk {file_name}",
                {"file": file_name},
            )
        if on_disk != payload:
            _fail(
                "OUTPUT_TAMPERED",
                f"{file_name} does not match what the canonical sources produce",
                {"file": file_name},
            )
        smuggled = _scan_forbidden(json.loads(on_disk.decode("utf-8")))
        if smuggled:
            _fail(
                "VOCABULARY_SMUGGLED",
                f"{file_name} declares vocabulary the canonical sources own",
                {"file": file_name, "keywords": smuggled},
            )

    recorded_members: dict[str, str] = {}
    for family in index["families"].values():
        for entry in family["members"]:
            recorded_members[str(entry["canonical"])] = str(entry["sha256"])
    expected_members = {f"schemas/{name}.schema.json" for name in members()}
    if set(recorded_members) != expected_members:
        _fail("INDEX_TAMPERED", "the index does not list the family membership")
    for canonical, recorded in sorted(recorded_members.items()):
        live = base / canonical
        if not live.is_file():
            _fail("MEMBER_MISSING", f"{canonical} is gone", {"member": canonical})
        if _file_sha(live) != recorded:
            _fail(
                "INDEX_STALE",
                f"{canonical} changed after the bundle was emitted",
                {"member": canonical},
            )

    unexpected = sorted(
        entry.name
        for entry in target.iterdir()
        if entry.name != INDEX_NAME and entry.name not in composites
    )
    if unexpected:
        _fail(
            "OUTPUT_TAMPERED",
            "the bundle holds files no receipt covers",
            {"unexpected": unexpected},
        )

    return {
        "composites_verified": len(composites),
        "member_count": len(recorded_members),
        "mutable_search_space": len(MUTABLE_SEARCH_SPACE),
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("emit", "verify"))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    try:
        result = emit(root) if arguments.mode == "emit" else verify(root)
    except C05BundleError as error:
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
