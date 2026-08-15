"""V01 deterministic ValidationTarget manifest construction and eligibility.

A hypothesis can only be validated against something that declares what it is.
The ``ValidationTargetManifest`` is that declaration: the interface a target
exposes, the version of that interface, the safety class and approval policy it
runs under, the artifacts it is made of, and the scope its results are allowed
to bound.  This module is the door those manifests come through, and the screen
that decides which of them may enter validation planning at all.

Two layers, kept apart on purpose.  *Construction* refuses documents that are
internally incoherent no matter what anyone intends to do with them: an
entrypoint that is not one of the declared artifacts, two ports claiming one
id, a constraint written against a parameter or state variable the manifest
never declared, an artifact hash that is not in canonical ``sha256:`` form.
Those are raised, because a caller cannot proceed with a manifest that does not
describe a target.  *Eligibility* refuses documents that are well-formed but
cannot bound a claim: the top safety class running without approval, a
reproducibility contract too weak for what the target type does, no declared
action to take, or a scope vector whose every axis is null.  Those are
*reported* — a caller screening twenty targets needs the whole ledger, not the
first exception.

Every vocabulary is read from the canonical schemas at ``schemas/`` rather than
restated here: the target types, safety classes, approval policies, data
classes, port field set, reproducibility contract fields, the ``sha256``
pattern and the scope axes.  The two local decision tables — which approval
policy covers which safety class, and which target types are executed or
stochastic — are asserted against the schema that declares their keys, so a
schema edit breaks this module loudly instead of leaving a screen that quietly
passes on a vocabulary that no longer exists.

The eligibility rule this package owns is narrow and deliberately so: the
highest safety class may never carry the no-approval policy.  The finer
question of which individual invocation needs an approval record is T04's gate
at call time, not V01's question about whether a target may be planned against
at all.

No clock and no randomness.  The caller supplies report ids and timestamps,
inputs are never mutated, every derived list is sorted, and every record and
report re-derives its own hash from exactly the fields it publishes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

#: The canonical target declaration this package constructs and screens.
TARGET_SCHEMA_PATH: Final = "schemas/validation-target-manifest.schema.json"
#: The boundary vector a target's results are allowed to claim over.
SCOPE_SCHEMA_PATH: Final = "schemas/scope-vector.schema.json"

#: How a constraint names the port it bounds.  A constraint is a free-text
#: expression, so the only thing this module can verify is that every port it
#: names is a port the manifest actually declares; ``{name}`` is that hook.
CONSTRAINT_REFERENCE: Final = re.compile(r"\{([^{}]*)\}")

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ACTIONS_UNDECLARED": (
        "the target declares no supported action, so no validation plan could "
        "name anything to do with it and planning against it would be empty"
    ),
    "APPROVAL_INCOHERENT": (
        "the target declares the highest safety class together with an "
        "approval policy that gates nothing, so its most dangerous effects "
        "would run with no human decision anywhere in front of them"
    ),
    "ARTIFACT_HASH_MALFORMED": (
        "an artifact hash is not in the canonical sha256 form the manifest "
        "schema declares, so the artifact set cannot be content-addressed"
    ),
    "ARTIFACT_SET_EMPTY": (
        "the target declares no artifact at all, so nothing it runs could ever "
        "be pinned, re-derived, or attributed to a reviewed version"
    ),
    "CANONICALIZATION_FAILED": (
        "a value cannot be encoded as canonical JSON, so no stable digest of "
        "it exists and nothing derived from it could be replayed"
    ),
    "CONSTRAINT_UNBOUND": (
        "a constraint names a parameter or state variable the manifest never "
        "declares, so the bound it states applies to nothing that exists"
    ),
    "CONSTRAINT_UNGROUNDED": (
        "a constraint names no declared port at all, so it bounds nothing and "
        "cannot be checked against any input a validation run would supply"
    ),
    "ENTRYPOINT_UNDECLARED": (
        "the entrypoint is not one of the declared artifacts, so the code that "
        "would actually run is outside the set the manifest pins by hash"
    ),
    "FIELD_SET_INVALID": (
        "a record carries a field set the declaring schema does not allow, so "
        "some field is missing or some field would be silently ignored"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this contract accepts, so continuing would "
        "mean guessing what the caller meant instead of refusing plainly"
    ),
    "MANIFEST_MALFORMED": (
        "the screened document is not a valid ValidationTargetManifest, so no "
        "eligibility question about it can be answered from its own fields"
    ),
    "MANIFEST_SCHEMA_INVALID": (
        "the assembled manifest does not validate against its canonical "
        "schema, so this builder would be emitting a document nothing accepts"
    ),
    "PORT_ID_DUPLICATED": (
        "two declared ports claim the same id, so any constraint or plan that "
        "names that id resolves ambiguously and could bound the wrong port"
    ),
    "REPRODUCIBILITY_INSUFFICIENT": (
        "the reproducibility contract omits something this target type needs, "
        "so a result it produces could never be independently re-derived"
    ),
    "SCHEMA_UNREADABLE": (
        "a canonical schema this module reads its vocabulary from cannot be "
        "read or does not declare what is expected, so nothing may be screened"
    ),
    "SCOPE_VACUOUS": (
        "the validation scope leaves every declared axis null or empty, so a "
        "result from this target would bound no population, setting or time"
    ),
    "TARGET_ID_DUPLICATED": (
        "two screened manifests claim the same target id, so the report could "
        "not attribute an eligibility outcome to one target unambiguously"
    ),
    "VOCABULARY_DRIFT": (
        "a local decision table no longer matches the canonical schema that "
        "declares its keys, so some screened value has no governing rule"
    ),
}

#: Which safety classes each canonical approval policy actually gates.  Keys
#: are asserted against the schema's approval-policy enum and values against
#: its safety-class enum, so neither list may drift unnoticed.
APPROVAL_COVERAGE: Final = {
    "none": (),
    "high_risk_only": ("high_risk",),
    "all_effects": ("controlled_effect", "high_risk"),
}

#: Target types whose artifacts this system runs itself, so the exact image
#: they run in has to be pinned for a result to mean anything later.
EXECUTED_TARGET_TYPES: Final = (
    "analysis_pipeline",
    "benchmark_harness",
    "custom",
    "formal_solver",
    "simulation_model",
)
#: Target types whose output depends on a pseudo-random draw, so the draw has
#: to be controlled or two runs of the same plan are not comparable.
STOCHASTIC_TARGET_TYPES: Final = (
    "benchmark_harness",
    "custom",
    "simulation_model",
)
#: Reproducibility contract fields keyed by what makes them necessary.  Every
#: target type needs its environment captured; the other two are conditional.
ENVIRONMENT_FIELD: Final = "environment_capture"
CONTAINER_FIELD: Final = "container_digest_required"
SEED_FIELD: Final = "seed_control"

#: The eligibility questions, in the order a reader should ask them.
ELIGIBILITY_CRITERIA: Final = (
    "approval_coherent",
    "reproducibility_sufficient",
    "actions_declared",
    "scope_bounded",
)
#: The finding each criterion reports when it does not hold.
CRITERION_FINDING: Final = {
    "approval_coherent": "APPROVAL_INCOHERENT",
    "reproducibility_sufficient": "REPRODUCIBILITY_INSUFFICIENT",
    "actions_declared": "ACTIONS_UNDECLARED",
    "scope_bounded": "SCOPE_VACUOUS",
}

_PORT_COLLECTIONS: Final = ("inputs", "outputs", "parameters", "state_variables")
#: The collections a constraint may name.  A constraint bounds what a run may
#: set or what a run may reach, not what the target happens to emit.
_CONSTRAINABLE_COLLECTIONS: Final = ("parameters", "state_variables")


class ValidationTargetError(ValueError):
    """A manifest or screening batch that could not describe a real target."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ValidationTargetError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ValidationTargetError(code, message, context)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("CANONICALIZATION_FAILED", f"value is not canonical JSON: {error}")
        raise  # pragma: no cover - _fail always raises


def digest(value: object) -> str:
    """The canonical sha256 of any JSON-encodable value."""

    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    """The digest a self-hashing record publishes in ``field``."""

    return digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings", {"label": label})
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean", {"label": label})
    return bool(value)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    entries = [
        _text(entry, f"{label}[{index}]")
        for index, entry in enumerate(_sequence(value, label))
    ]
    if len(set(entries)) != len(entries):
        _fail("INPUT_INVALID", f"{label} must not repeat an entry", {"label": label})
    return tuple(entries)


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _schema(repository_root: str | Path, relative: str) -> dict[str, Any]:
    path = Path(repository_root) / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, relative)


def _node(document: Mapping[str, Any], relative: str, *path: str) -> Any:
    node: Any = document
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            _fail(
                "SCHEMA_UNREADABLE",
                f"{relative} does not declare {'.'.join(path)}",
                {"schema": relative},
            )
        node = node[key]
    return node


def _enum(repository_root: str | Path, relative: str, *path: str) -> tuple[str, ...]:
    node = _node(_schema(repository_root, relative), relative, *path)
    if not isinstance(node, list) or not node:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares an empty {'.'.join(path)}",
            {"schema": relative},
        )
    return tuple(str(entry) for entry in node)  # type: ignore[union-attr]


def _required(repository_root: str | Path, relative: str, *path: str) -> frozenset[str]:
    document = _schema(repository_root, relative)
    node = _node(document, relative, *path) if path else document
    required = node.get("required") if isinstance(node, Mapping) else None
    if not isinstance(required, list) or not required:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares no required set at {'.'.join(path) or 'root'}",
            {"schema": relative},
        )
    return frozenset(str(entry) for entry in required)  # type: ignore[union-attr]


def _assert_table(
    table: Mapping[str, Any], declared: Sequence[str], label: str
) -> None:
    """A local decision table must cover the declaring schema exactly."""

    missing = sorted(set(declared) - set(table))
    unknown = sorted(set(table) - set(declared))
    if missing or unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} table no longer matches the schema that declares it",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _assert_subset(values: Sequence[str], declared: Sequence[str], label: str) -> None:
    unknown = sorted(set(values) - set(declared))
    if unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} set names a value the schema does not declare",
            {"label": label, "unknown": unknown},
        )


def target_manifest_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a ValidationTargetManifest must carry."""

    return _required(repository_root, TARGET_SCHEMA_PATH)


def target_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "target_type", "enum"
    )


def safety_classes(repository_root: str | Path) -> tuple[str, ...]:
    """Safety classes as the schema declares them, weakest first."""

    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "safety_class", "enum"
    )


def approval_policies(repository_root: str | Path) -> tuple[str, ...]:
    """Approval policies as the schema declares them, weakest first."""

    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "approval_policy", "enum"
    )


def network_policies(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "network_policy", "enum"
    )


def data_classes(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        TARGET_SCHEMA_PATH,
        "properties",
        "allowed_data_classes",
        "items",
        "enum",
    )


def port_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, TARGET_SCHEMA_PATH, "$defs", "port")


def reproducibility_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(
        repository_root, TARGET_SCHEMA_PATH, "properties", "reproducibility_contract"
    )


def sha256_pattern(repository_root: str | Path) -> re.Pattern[str]:
    node = _node(
        _schema(repository_root, TARGET_SCHEMA_PATH),
        TARGET_SCHEMA_PATH,
        "$defs",
        "sha256",
        "pattern",
    )
    if not isinstance(node, str) or not node:
        _fail("SCHEMA_UNREADABLE", "the manifest schema declares no sha256 pattern")
    return re.compile(str(node))


def scope_axes(repository_root: str | Path) -> tuple[str, ...]:
    """Every boundary axis the canonical scope vector declares."""

    return tuple(sorted(_required(repository_root, SCOPE_SCHEMA_PATH)))


def highest_safety_class(repository_root: str | Path) -> str:
    """The strongest safety class the schema declares.

    The enum is ordered weakest to strongest, which the schema-and-type suite
    pins explicitly; taking the last entry means a schema that adds a class
    above ``high_risk`` moves this rule up with it rather than leaving the new
    top class ungoverned.
    """

    return safety_classes(repository_root)[-1]


def unapproved_approval_policy(repository_root: str | Path) -> str:
    """The approval policy that gates nothing, read from its own coverage."""

    coverage = approval_coverage(repository_root)
    empty = tuple(sorted(name for name, gated in coverage.items() if not gated))
    if len(empty) != 1:
        _fail(
            "VOCABULARY_DRIFT",
            "the approval coverage table does not name exactly one policy that "
            "gates nothing",
            {"candidates": list(empty)},
        )
    return empty[0]


def approval_coverage(repository_root: str | Path) -> dict[str, tuple[str, ...]]:
    """Which safety classes each declared approval policy actually gates."""

    policies = approval_policies(repository_root)
    classes = safety_classes(repository_root)
    _assert_table(APPROVAL_COVERAGE, policies, "approval coverage")
    for policy, gated in APPROVAL_COVERAGE.items():
        _assert_subset(gated, classes, f"approval coverage for {policy}")
    return {policy: tuple(APPROVAL_COVERAGE[policy]) for policy in sorted(policies)}


def reproducibility_requirements(
    repository_root: str | Path,
) -> dict[str, tuple[str, ...]]:
    """The reproducibility contract fields each target type must set true.

    Composed rather than tabulated: every target type must capture its
    environment, a type this system executes itself must pin the image it runs
    in, and a type whose output depends on a pseudo-random draw must control
    the seed.  ``custom`` is in both conditional sets because an unclassified
    target is the one case where nothing is known well enough to relax.
    """

    types = target_types(repository_root)
    fields = reproducibility_fields(repository_root)
    _assert_subset(EXECUTED_TARGET_TYPES, types, "executed target types")
    _assert_subset(STOCHASTIC_TARGET_TYPES, types, "stochastic target types")
    _assert_subset(
        (ENVIRONMENT_FIELD, CONTAINER_FIELD, SEED_FIELD),
        tuple(sorted(fields)),
        "reproducibility contract fields",
    )
    table: dict[str, tuple[str, ...]] = {}
    for target_type in types:
        required = {ENVIRONMENT_FIELD}
        if target_type in EXECUTED_TARGET_TYPES:
            required.add(CONTAINER_FIELD)
        if target_type in STOCHASTIC_TARGET_TYPES:
            required.add(SEED_FIELD)
        table[target_type] = tuple(sorted(required))
    _assert_table(table, types, "reproducibility requirement")
    return table


def _resource(document: Mapping[str, Any]) -> tuple[str, Resource[Any]]:
    identifier = document.get("$id")
    if not isinstance(identifier, str) or not identifier:
        _fail("SCHEMA_UNREADABLE", "a canonical schema declares no $id")
    return str(identifier), Resource.from_contents(
        dict(document), default_specification=DRAFT202012
    )


def manifest_validator(repository_root: str | Path) -> Draft202012Validator:
    """A validator for the canonical manifest with its scope vector resolved.

    The manifest schema references ``scope-vector.schema.json`` relatively, so
    both documents are registered under their own ``$id`` and the reference
    resolves against the canonical identifiers rather than the filesystem.
    """

    documents = [
        _schema(repository_root, TARGET_SCHEMA_PATH),
        _schema(repository_root, SCOPE_SCHEMA_PATH),
    ]
    registry: Registry[Any] = Registry().with_resources(
        _resource(document) for document in documents
    )
    return Draft202012Validator(documents[0], registry=registry)


def manifest_schema_errors(repository_root: str | Path, manifest: object) -> list[str]:
    """Every canonical schema error in a candidate manifest, sorted."""

    validator = manifest_validator(repository_root)
    return sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in validator.iter_errors(manifest)
    )


def _validate_port(
    value: object, collection: str, index: int, fields: frozenset[str]
) -> dict[str, Any]:
    label = f"{collection}[{index}]"
    port = _mapping(value, label)
    _exact_fields(port, fields, label)
    identifier = _text(port.get("id"), f"{label}.id")
    result: dict[str, Any] = {
        "id": identifier,
        "data_type": _text(port.get("data_type"), f"{label}.data_type"),
        "required": _boolean(port.get("required"), f"{label}.required"),
    }
    for optional in ("unit", "schema_ref", "temporal_support"):
        entry = port.get(optional)
        if entry is not None:
            entry = _text(entry, f"{label}.{optional}")
        result[optional] = entry
    return result


def _duplicate_port_context(
    ports: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any] | None:
    """The first duplicate port id in canonical declaration order, if any."""

    seen: dict[str, str] = {}
    for collection in _PORT_COLLECTIONS:
        for entry in ports.get(collection, ()):
            identifier = entry["id"]
            if identifier in seen:
                return {
                    "port_id": identifier,
                    "collections": sorted({seen[identifier], collection}),
                }
            seen[identifier] = collection
    return None


def _validate_ports(
    ports: Mapping[str, Any], fields: frozenset[str]
) -> dict[str, list[dict[str, Any]]]:
    """Every declared port, with one id naming exactly one port."""

    declared: dict[str, list[dict[str, Any]]] = {}
    for collection in _PORT_COLLECTIONS:
        entries = [
            _validate_port(entry, collection, index, fields)
            for index, entry in enumerate(_sequence(ports[collection], collection))
        ]
        declared[collection] = entries
        duplicate = _duplicate_port_context(declared)
        if duplicate is not None:
            _fail(
                "PORT_ID_DUPLICATED",
                f"port id {duplicate['port_id']} is declared more than once",
                duplicate,
            )
    return declared


def constraint_references(constraint: str) -> tuple[str, ...]:
    """The declared port ids a constraint names, in order of appearance."""

    return tuple(CONSTRAINT_REFERENCE.findall(constraint))


def _validate_constraints(
    constraints: object, declared: Mapping[str, list[dict[str, Any]]]
) -> list[str]:
    bindable = {
        entry["id"]
        for collection in _CONSTRAINABLE_COLLECTIONS
        for entry in declared[collection]
    }
    result: list[str] = []
    for index, value in enumerate(_sequence(constraints, "constraints")):
        text = _text(value, f"constraints[{index}]")
        references = constraint_references(text)
        if not references:
            _fail(
                "CONSTRAINT_UNGROUNDED",
                f"constraints[{index}] names no declared port",
                {"constraint": text, "bindable": sorted(bindable)},
            )
        unknown = sorted({name for name in references if name not in bindable})
        if unknown:
            _fail(
                "CONSTRAINT_UNBOUND",
                f"constraints[{index}] names an undeclared port",
                {"constraint": text, "unknown": unknown, "bindable": sorted(bindable)},
            )
        result.append(text)
    return result


def _validate_artifacts(
    artifacts: object, entrypoint: str, pattern: re.Pattern[str]
) -> tuple[str, ...]:
    declared = _mapping(artifacts, "artifacts")
    if not declared:
        _fail("ARTIFACT_SET_EMPTY", "the target declares no artifact")
    hashes: set[str] = set()
    for path in sorted(declared):
        _text(path, f"artifacts[{path}]")
        value = _text(declared[path], f"artifacts[{path}]")
        if pattern.fullmatch(value) is None:
            _fail(
                "ARTIFACT_HASH_MALFORMED",
                f"the hash declared for {path} is not canonical sha256",
                {"artifact": path, "value": value},
            )
        hashes.add(value)
    if entrypoint not in declared:
        _fail(
            "ENTRYPOINT_UNDECLARED",
            f"the entrypoint {entrypoint} is not a declared artifact",
            {"entrypoint": entrypoint, "artifacts": sorted(declared)},
        )
    return tuple(sorted(hashes))


def _validate_reproducibility(value: object, fields: frozenset[str]) -> dict[str, bool]:
    contract = _mapping(value, "reproducibility_contract")
    _exact_fields(contract, fields, "reproducibility_contract")
    return {
        field: _boolean(contract[field], f"reproducibility_contract.{field}")
        for field in sorted(fields)
    }


def _validate_enum(value: object, declared: Sequence[str], label: str) -> str:
    text = _text(value, label)
    if text not in declared:
        _fail(
            "INPUT_INVALID",
            f"{label} is not a value the canonical schema declares",
            {"label": label, "value": text, "allowed": list(declared)},
        )
    return text


def build_target_manifest(
    repository_root: str | Path,
    *,
    target_id: str,
    version: str,
    target_type: str,
    interface_version: str,
    entrypoint: str,
    artifacts: Mapping[str, str],
    inputs: Sequence[Any],
    outputs: Sequence[Any],
    parameters: Sequence[Any],
    state_variables: Sequence[Any],
    constraints: Sequence[Any],
    supported_actions: Sequence[Any],
    validation_scope: Mapping[str, Any],
    identifiability_notes: Sequence[Any],
    capability_requirements: Sequence[Any],
    safety_class: str,
    approval_policy: str,
    provenance_manifest_id: str,
    sandbox_profile: str,
    network_policy: str,
    supply_chain_attestation_artifact_id: str,
    reproducibility_contract: Mapping[str, Any],
    allowed_data_classes: Sequence[Any],
) -> dict[str, Any]:
    """Assemble one canonical ValidationTargetManifest from explicit inputs.

    ``artifacts`` maps each artifact path to its canonical ``sha256:`` digest.
    The entrypoint has to be one of those paths, because an entrypoint outside
    the pinned set is code that runs without ever having been hashed; the
    manifest's ``artifact_hashes`` are then derived from that map rather than
    supplied separately, so the two can never disagree.

    Nothing here is mutated: every port, constraint and scope value is copied
    into a fresh document, and the caller's inputs come back unchanged.
    """

    root = Path(repository_root)
    pattern = sha256_pattern(root)
    declared_ports = _validate_ports(
        {
            "inputs": inputs,
            "outputs": outputs,
            "parameters": parameters,
            "state_variables": state_variables,
        },
        port_fields(root),
    )
    manifest: dict[str, Any] = {
        "allowed_data_classes": sorted(
            {
                _validate_enum(entry, data_classes(root), f"allowed_data_classes[{i}]")
                for i, entry in enumerate(_sequence(allowed_data_classes, "classes"))
            }
        ),
        "approval_policy": _validate_enum(
            approval_policy, approval_policies(root), "approval_policy"
        ),
        "artifact_hashes": list(
            _validate_artifacts(artifacts, _text(entrypoint, "entrypoint"), pattern)
        ),
        "capability_requirements": sorted(
            _string_tuple(capability_requirements, "capability_requirements")
        ),
        "constraints": _validate_constraints(constraints, declared_ports),
        "entrypoint": _text(entrypoint, "entrypoint"),
        "identifiability_notes": [
            _text(entry, f"identifiability_notes[{index}]")
            for index, entry in enumerate(
                _sequence(identifiability_notes, "identifiability_notes")
            )
        ],
        "inputs": declared_ports["inputs"],
        "interface_version": _text(interface_version, "interface_version"),
        "network_policy": _validate_enum(
            network_policy, network_policies(root), "network_policy"
        ),
        "outputs": declared_ports["outputs"],
        "parameters": declared_ports["parameters"],
        "provenance_manifest_id": _text(
            provenance_manifest_id, "provenance_manifest_id"
        ),
        "reproducibility_contract": _validate_reproducibility(
            reproducibility_contract, reproducibility_fields(root)
        ),
        "safety_class": _validate_enum(
            safety_class, safety_classes(root), "safety_class"
        ),
        "sandbox_profile": _text(sandbox_profile, "sandbox_profile"),
        "state_variables": declared_ports["state_variables"],
        "supply_chain_attestation_artifact_id": _text(
            supply_chain_attestation_artifact_id,
            "supply_chain_attestation_artifact_id",
        ),
        "supported_actions": list(_string_tuple(supported_actions, "actions")),
        "target_id": _text(target_id, "target_id"),
        "target_type": _validate_enum(target_type, target_types(root), "target_type"),
        "validation_scope": json.loads(
            _canonical_json(_mapping(validation_scope, "validation_scope"))
        ),
        "version": _text(version, "version"),
    }
    _exact_fields(manifest, target_manifest_fields(root), "manifest")
    errors = manifest_schema_errors(root, manifest)
    if errors:
        _fail(
            "MANIFEST_SCHEMA_INVALID",
            "the assembled manifest does not validate against its schema",
            {"errors": errors},
        )
    return manifest


@dataclass(frozen=True)
class _Screen:
    """One snapshot of every canonical vocabulary a screening run reads."""

    highest_safety_class: str
    unapproved_policy: str
    approval_coverage: dict[str, tuple[str, ...]]
    reproducibility: dict[str, tuple[str, ...]]
    scope_properties: dict[str, Any]
    vocabulary_hash: str
    validator: Draft202012Validator


def _open_screen(repository_root: str | Path) -> _Screen:
    root = Path(repository_root)
    target_schema = _schema(root, TARGET_SCHEMA_PATH)
    scope_schema = _schema(root, SCOPE_SCHEMA_PATH)
    properties = _mapping(
        _node(scope_schema, SCOPE_SCHEMA_PATH, "properties"), "scope properties"
    )
    axes = scope_axes(root)
    missing = sorted(set(axes) - set(properties))
    if missing:
        _fail(
            "SCHEMA_UNREADABLE",
            "the scope vector requires an axis it does not declare",
            {"missing": missing},
        )
    return _Screen(
        highest_safety_class=highest_safety_class(root),
        unapproved_policy=unapproved_approval_policy(root),
        approval_coverage=approval_coverage(root),
        reproducibility=reproducibility_requirements(root),
        scope_properties={axis: properties[axis] for axis in axes},
        vocabulary_hash=digest(
            {
                SCOPE_SCHEMA_PATH: scope_schema,
                TARGET_SCHEMA_PATH: target_schema,
            }
        ),
        validator=manifest_validator(root),
    )


def _axis_is_bound(node: object, value: object) -> bool:
    declared = node.get("type") if isinstance(node, Mapping) else None
    if declared == "array":
        return (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
            and (len(value) > 0)
        )
    if declared == "object":
        return isinstance(value, Mapping) and len(value) > 0
    return value is not None


def empty_scope_vector(repository_root: str | Path) -> dict[str, Any]:
    """A structurally complete scope vector that bounds nothing.

    Useful as the base a caller fills in, and as the exact document the
    ``SCOPE_VACUOUS`` screen must refuse.  The shape of each axis comes from
    the canonical scope schema, so an axis added there appears here too.
    """

    screen = _open_screen(repository_root)
    scope: dict[str, Any] = {}
    for axis, node in screen.scope_properties.items():
        declared = node.get("type") if isinstance(node, Mapping) else None
        if declared == "array":
            scope[axis] = []
        elif declared == "object":
            scope[axis] = {}
        else:
            scope[axis] = None
    return scope


def bound_scope_axes(
    repository_root: str | Path, scope: Mapping[str, Any]
) -> tuple[str, ...]:
    """The scope axes a vector actually carries, sorted.

    A nullable axis is carried when it is not null; a list or object axis is
    carried when it is not empty.  Which axes exist and which shape each one
    has are both read from the canonical scope schema.
    """

    screen = _open_screen(repository_root)
    return _bound_axes(screen, _mapping(scope, "validation_scope"))


def _bound_axes(screen: _Screen, scope: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            axis
            for axis, node in screen.scope_properties.items()
            if axis in scope and _axis_is_bound(node, scope[axis])
        )
    )


def _screen_manifest(screen: _Screen, manifest: object, index: int) -> dict[str, Any]:
    codes: list[str] = []
    satisfied: list[str] = []
    detail: dict[str, Any] = {}

    document: dict[str, Any] | None = None
    if isinstance(manifest, Mapping):
        document = dict(manifest)
    errors = (
        ["manifest: not a mapping"]
        if document is None
        else sorted(
            "/".join(str(part) for part in error.absolute_path) + ": " + error.message
            for error in screen.validator.iter_errors(document)
        )
    )
    if errors:
        codes.append("MANIFEST_MALFORMED")
        detail["schema_errors"] = errors
    else:
        assert document is not None  # narrowed by the empty error list
        if _duplicate_port_context(document) is not None:
            codes.append("PORT_ID_DUPLICATED")

        gated = screen.approval_coverage[document["approval_policy"]]
        if (
            document["safety_class"] == screen.highest_safety_class
            and document["safety_class"] not in gated
        ):
            codes.append(CRITERION_FINDING["approval_coherent"])
            detail["approval_policy"] = document["approval_policy"]
            detail["unapproved_policy"] = screen.unapproved_policy
        else:
            satisfied.append("approval_coherent")

        contract = document["reproducibility_contract"]
        required = screen.reproducibility[document["target_type"]]
        unmet = sorted(field for field in required if contract.get(field) is not True)
        if unmet:
            codes.append(CRITERION_FINDING["reproducibility_sufficient"])
            detail["reproducibility_unmet"] = unmet
            detail["reproducibility_required"] = list(required)
        else:
            satisfied.append("reproducibility_sufficient")

        if not document["supported_actions"]:
            codes.append(CRITERION_FINDING["actions_declared"])
        else:
            satisfied.append("actions_declared")

        bound = _bound_axes(screen, document["validation_scope"])
        if not bound:
            codes.append(CRITERION_FINDING["scope_bounded"])
        else:
            satisfied.append("scope_bounded")
            detail["bound_scope_axes"] = list(bound)

    reason_codes = sorted(set(codes))
    record: dict[str, Any] = {
        "criteria_satisfied": sorted(satisfied),
        "eligible": not reason_codes,
        "manifest_hash": None if document is None else digest(document),
        "reason_codes": reason_codes,
        "reasons": {code: FINDING_CODES[code] for code in reason_codes},
        "screen_detail": detail,
        "screened_index": index,
        "target_id": (
            str(document["target_id"])
            if document is not None and isinstance(document.get("target_id"), str)
            else None
        ),
        "target_type": (
            str(document["target_type"])
            if document is not None and isinstance(document.get("target_type"), str)
            else None
        ),
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record


def screen_target(
    repository_root: str | Path, manifest: object, *, screened_index: int = 0
) -> dict[str, Any]:
    """Screen one manifest for validation-planning eligibility.

    Every failing criterion is reported rather than only the first, so a caller
    repairing a target sees the whole gap in one pass.  A document the schema
    refuses is reported as malformed and not additionally screened against
    criteria it never claimed to satisfy.
    """

    if not isinstance(screened_index, int) or isinstance(screened_index, bool):
        _fail("INPUT_INVALID", "screened_index must be an integer")
    return _screen_manifest(_open_screen(repository_root), manifest, screened_index)


def build_eligibility_report(
    repository_root: str | Path,
    manifests: Sequence[Any],
    *,
    report_id: str,
    screened_at: str,
) -> dict[str, Any]:
    """Screen a whole target set into one reconciled, re-derivable report.

    Records keep submission order so a caller can line the report up against
    what it sent, every derived list is sorted, and the counts always
    reconcile: screened equals eligible plus ineligible equals the number of
    records.  Two manifests claiming one target id is refused outright, because
    a report that cannot attribute an outcome to a target is not a report.
    """

    if isinstance(manifests, (str, bytes, Mapping)):
        _fail(
            "INPUT_INVALID",
            "manifests must be a sequence of manifest documents",
            {"submitted_type": type(manifests).__name__},
        )
    screen = _open_screen(repository_root)
    records = [
        _screen_manifest(screen, manifest, index)
        for index, manifest in enumerate(_sequence(manifests, "manifests"))
    ]
    seen: dict[str, int] = {}
    for record in records:
        identifier = record["target_id"]
        if identifier is None:
            continue
        if identifier in seen:
            _fail(
                "TARGET_ID_DUPLICATED",
                f"target id {identifier} is screened more than once",
                {
                    "target_id": identifier,
                    "positions": [seen[identifier], record["screened_index"]],
                },
            )
        seen[identifier] = record["screened_index"]

    eligible = [record for record in records if record["eligible"]]
    reason_totals: dict[str, int] = {}
    for record in records:
        for code in record["reason_codes"]:
            reason_totals[code] = reason_totals.get(code, 0) + 1

    report: dict[str, Any] = {
        "counts": {
            "eligible": len(eligible),
            "ineligible": len(records) - len(eligible),
            "screened": len(records),
        },
        "criteria": list(ELIGIBILITY_CRITERIA),
        "eligible_target_ids": sorted(
            str(record["target_id"])
            for record in eligible
            if record["target_id"] is not None
        ),
        "reason_totals": {code: reason_totals[code] for code in sorted(reason_totals)},
        "records": records,
        "report_id": _text(report_id, "report_id"),
        "screened_at": _text(screened_at, "screened_at"),
        "vocabulary_hash": screen.vocabulary_hash,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    return report
