"""X04 cross-provider parity and diversity gate.

Two things are proved here, and neither of them invokes a model.

**Parity.**  The canonical role registry (``manifests/role_registry.yaml``) is
the one place a role's name and its output contract are declared.  The two
provider adapters sealed by X01 and X02 — the Codex adapter at
``adapters/codex/role_mapping.yaml`` and the Claude Code adapter at
``adapters/claude-code/role_mapping.yaml`` — each re-express those canonical
roles in their own host vocabulary.  This gate reads all three and refuses the
moment the two adapters stop agreeing with the registry: a role either adapter
drops or invents (``ROLE_SET_DIVERGENCE``), or a canonical output schema either
adapter rebinds (``RESULT_SCHEMA_DIVERGENCE``).  The host-specific descriptor is
allowed to differ — that is the whole point of an adapter — but it must still be
the descriptor the registry names for that host (``CODEX_AGENT_TYPE_DIVERGENCE``,
``CLAUDE_SURFACE_DIVERGENCE``), and a Claude role that can write must run
isolated exactly when the registry gives it a write scope
(``ISOLATION_DIVERGENCE``).  The role vocabulary is never restated in this
module; it is read from the registry, so a relabelled role breaks the gate
instead of silently passing it.

**Diversity without an independence claim.**  MASTER_SPEC section 19 is explicit
that "different providers are not assumed statistically independent."  Two
vendors are not two independent draws, and a gate that treated cross-provider
agreement as free error-cancellation would be overclaiming.  So the correlation
side takes a committed fixture of *declared* per-provider outcomes — never a live
run — over roles drawn from the parity surface, and measures how far the two
providers' errors actually co-occur.  It publishes the 2x2 contingency, the
observed joint-error rate beside the rate independence would predict, the excess
between them, and the phi coefficient, so the diversity of the two providers is a
number rather than an assumption.  The fixture must declare its providers
synthetic (``PROVIDER_OVERCLAIM`` otherwise, mirroring the sibling harnesses) and
must not assert independence (``INDEPENDENCE_OVERCLAIM``); the report records
``independence_assumed: false`` as a fact it enforced, not a hope.

This gate acquires no authority: a ``PASS`` means the adapters are in parity and
the diversity number was computed and the independence overclaim was refused — it
promotes nothing and it certifies no live provider.  The dataset carries its own
content hash, the report re-derives its own, and both are computed over canonical
JSON with the hash field removed — the same rule the canonical receipt writers
use.  No clock and no randomness live in this module: ``evaluated_at`` and
``report_id`` are supplied by the dataset.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import yaml

#: The canonical registry both adapters are measured against.
REGISTRY_RELATIVE_PATH: Final = "manifests/role_registry.yaml"
#: The X01 Codex adapter role mapping (a sealed parity surface).
CODEX_ADAPTER_RELATIVE_PATH: Final = "adapters/codex/role_mapping.yaml"
#: The X02 Claude Code adapter role mapping (a sealed parity surface).
CLAUDE_ADAPTER_RELATIVE_PATH: Final = "adapters/claude-code/role_mapping.yaml"
#: The committed correlation fixture this harness governs.
DATASET_RELATIVE_PATH: Final = "evals/provider_parity/provider_parity_cases.json"
#: The machine-readable results artifact this harness re-derives.
RESULTS_RELATIVE_PATH: Final = "evals/provider_parity/provider_parity_results.json"

#: The two provider ids this gate knows, each bound to its sealed adapter.
PROVIDER_ADAPTERS: Final = {
    "codex": CODEX_ADAPTER_RELATIVE_PATH,
    "claude-code": CLAUDE_ADAPTER_RELATIVE_PATH,
}
#: The one uniform host surface the Claude adapter declares for every role.
CLAUDE_UNIFORM_SURFACE: Final = "custom_agent"
#: The only diversity position the spec permits: independence is not assumed.
DIVERSITY_POSITION_ALLOWED: Final = "not_assumed_independent"
#: The declared outcome vocabulary of a correlation trial.
OUTCOME_VOCABULARY: Final = ("correct", "error")

_DATASET_FIELDS: Final = frozenset(
    {
        "canonical_registry_ref",
        "claude_adapter_ref",
        "codex_adapter_ref",
        "dataset_hash",
        "dataset_id",
        "diversity_position",
        "evaluated_at",
        "providers",
        "report_id",
        "trials",
        "version",
    }
)
_REF_FIELDS: Final = frozenset({"path", "version"})
_PROVIDER_FIELDS: Final = frozenset({"adapter_path", "provider_id", "synthetic"})
_TRIAL_FIELDS: Final = frozenset(
    {"claude_outcome", "codex_outcome", "role_id", "trial_id"}
)

#: Every way this gate refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ADAPTER_FIELD_INVALID": (
        "an adapter role record is missing the result schema or host descriptor "
        "this gate compares, so parity for that role cannot be established at all"
    ),
    "ADAPTER_UNREADABLE": (
        "a sealed provider adapter mapping could not be read or parsed, so the "
        "role vocabulary it is supposed to expose cannot be checked"
    ),
    "CLAUDE_SURFACE_DIVERGENCE": (
        "the Claude adapter binds a role to a host surface other than the uniform "
        "custom-agent surface it declares, so its host descriptor no longer "
        "matches the one the registry expects for that host"
    ),
    "CODEX_AGENT_TYPE_DIVERGENCE": (
        "the Codex adapter binds a role to a built-in agent type the registry "
        "does not name for that role, so the two adapters would resolve the same "
        "canonical role to different host behaviour"
    ),
    "DATASET_HASH_MISMATCH": (
        "the correlation fixture content no longer matches the hash it publishes, "
        "which means a trial or an outcome was edited after the seal"
    ),
    "DATASET_UNREADABLE": (
        "the committed correlation fixture could not be read or parsed, so no "
        "diversity number can be grounded in the trials it names"
    ),
    "DUPLICATE_TRIAL": (
        "one trial id appears twice, so the same declared outcome would be "
        "counted more than once in the contingency table"
    ),
    "FIELD_SET_INVALID": (
        "a fixture record carries an unknown or missing field, and a dataset "
        "whose shape drifts silently stops measuring what it claims to measure"
    ),
    "INDEPENDENCE_OVERCLAIM": (
        "the fixture asserts the two providers are statistically independent, the "
        "exact assumption MASTER_SPEC section 19 forbids a diversity gate to make"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this harness requires, and continuing would "
        "publish a diversity number over material it never validated"
    ),
    "PROVIDER_ADAPTER_MISMATCH": (
        "a declared provider cites an adapter path other than the sealed mapping "
        "bound to its provider id, so its outcomes would trace to the wrong host"
    ),
    "PROVIDER_OVERCLAIM": (
        "the recorded outcomes are a committed fixture; a dataset claiming a live "
        "provider requires recorded runs this repository does not carry"
    ),
    "PROVIDER_SET_INVALID": (
        "the fixture does not declare exactly the two providers this gate binds, "
        "so a correlation between them could not be formed as claimed"
    ),
    "REGISTRY_UNREADABLE": (
        "the canonical role registry could not be read, so neither the role "
        "vocabulary nor the per-role output contract can be bound to their source"
    ),
    "RESULTS_STALE": (
        "the committed results artifact does not equal the report re-derived from "
        "the sealed surfaces and the committed fixture, so the published metrics "
        "describe some other version of the gate"
    ),
    "RESULTS_UNREADABLE": (
        "the committed results artifact could not be read or parsed, so the "
        "published metrics cannot be checked against their sources at all"
    ),
    "RESULT_SCHEMA_DIVERGENCE": (
        "an adapter binds a canonical role to an output schema other than the one "
        "the registry declares, so the two providers would emit results against "
        "different contracts and could not be compared"
    ),
    "ISOLATION_DIVERGENCE": (
        "a write-capable Claude role is not run in an isolated worktree, or a "
        "role with no write scope is, so parallel-writer isolation no longer "
        "tracks the write scopes the registry grants"
    ),
    "ROLE_NOT_IN_PARITY_SURFACE": (
        "a correlation trial names a role that is not carried in parity by both "
        "adapters, so its declared outcomes are not anchored to a shared role"
    ),
    "ROLE_SET_DIVERGENCE": (
        "an adapter drops a canonical role or invents one the registry does not "
        "carry, so the two providers no longer cover the same role vocabulary"
    ),
    "OUTCOME_INVALID": (
        "a declared outcome lies outside the correct/error vocabulary, so the "
        "error indicator that feeds the contingency table is undefined"
    ),
    "TIMESTAMP_INVALID": (
        "a timestamp is not an offset-aware RFC3339 instant, so the evaluation "
        "time the report records is undefined"
    ),
}


class ProviderParityError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ProviderParityError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ProviderParityError(code, message, context)


@dataclass(frozen=True)
class SealedReport:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed report is not an object")
        return value


def canonical_json(value: object) -> bytes:
    """The one canonical byte form used for every digest in this harness."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    """The schema-shaped digest (``sha256:<64 lowercase hex>``)."""

    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    """Digest a record while omitting the field that carries the digest."""

    return digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings")
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    return list(value)  # type: ignore[arg-type]


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _instant_text(value: object, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _fail("TIMESTAMP_INVALID", f"{label} is not an RFC3339 instant", {"value": text})
        raise  # pragma: no cover - _fail always raises
    if parsed.tzinfo is None:
        _fail("TIMESTAMP_INVALID", f"{label} must carry a UTC offset", {"value": text})
    return text


def _read_json(path: Path, code: str, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(code, f"{label} could not be read: {error}", {"path": str(path)})
        raise  # pragma: no cover - _fail always raises


def _read_yaml(path: Path, code: str, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        _fail(code, f"{label} could not be read: {error}", {"path": str(path)})
        raise  # pragma: no cover - _fail always raises


# --------------------------------------------------------------------------- #
# Parity: the sealed surfaces measured against the canonical registry.
# --------------------------------------------------------------------------- #


def load_registry(repository_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read the canonical role registry as ``role_id`` to its record."""

    path = Path(repository_root) / REGISTRY_RELATIVE_PATH
    loaded = _mapping(
        _read_yaml(path, "REGISTRY_UNREADABLE", "the canonical role registry"),
        "role registry",
    )
    roles: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(_sequence(loaded.get("roles"), "registry roles")):
        record = _mapping(entry, f"registry roles[{index}]")
        role_id = _text(record.get("role_id"), "role_id")
        if role_id in roles:
            _fail(
                "REGISTRY_UNREADABLE",
                "the registry declares a role twice",
                {"role_id": role_id},
            )
        roles[role_id] = record
    if not roles:
        _fail("REGISTRY_UNREADABLE", "the registry declares no role")
    return roles


def load_adapter_roles(
    repository_root: str | Path, relative_path: str
) -> dict[str, dict[str, Any]]:
    """Read one adapter's ``role_id`` to its host-mapping record."""

    path = Path(repository_root) / relative_path
    loaded = _mapping(
        _read_yaml(path, "ADAPTER_UNREADABLE", f"the adapter {relative_path}"),
        f"adapter {relative_path}",
    )
    roles = _mapping(loaded.get("roles"), f"adapter {relative_path} roles")
    return {key: _mapping(value, f"{relative_path}#{key}") for key, value in roles.items()}


def evaluate_parity(repository_root: str | Path) -> dict[str, Any]:
    """Measure both sealed adapters against the canonical registry."""

    registry = load_registry(repository_root)
    codex = load_adapter_roles(repository_root, CODEX_ADAPTER_RELATIVE_PATH)
    claude = load_adapter_roles(repository_root, CLAUDE_ADAPTER_RELATIVE_PATH)
    return parity_from(registry, codex, claude)


def parity_from(
    registry: Mapping[str, Mapping[str, Any]],
    codex: Mapping[str, Mapping[str, Any]],
    claude: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure two adapter role maps against the registry, in memory."""

    registry_ids = set(registry)
    for name, adapter in (("codex", codex), ("claude-code", claude)):
        adapter_ids = set(adapter)
        if adapter_ids != registry_ids:
            _fail(
                "ROLE_SET_DIVERGENCE",
                f"the {name} adapter role set differs from the registry",
                {
                    "adapter": name,
                    "dropped": sorted(registry_ids - adapter_ids),
                    "invented": sorted(adapter_ids - registry_ids),
                },
            )

    roles: list[dict[str, Any]] = []
    for role_id in sorted(registry_ids):
        registry_role = registry[role_id]
        expected_schema = _text(
            registry_role.get("output_schema_ref"), f"{role_id}.output_schema_ref"
        )
        expected_agent_type = _text(
            registry_role.get("codex_agent_type"), f"{role_id}.codex_agent_type"
        )
        writable = bool(registry_role.get("write_scope") or [])

        codex_role = codex[role_id]
        claude_role = claude[role_id]
        if "result_schema" not in codex_role or "agent_type" not in codex_role:
            _fail(
                "ADAPTER_FIELD_INVALID",
                "the codex adapter role is missing result_schema or agent_type",
                {"role_id": role_id},
            )
        if "result_schema" not in claude_role or "surface" not in claude_role:
            _fail(
                "ADAPTER_FIELD_INVALID",
                "the claude adapter role is missing result_schema or surface",
                {"role_id": role_id},
            )
        if "isolation" not in claude_role:
            _fail(
                "ADAPTER_FIELD_INVALID",
                "the claude adapter role is missing isolation",
                {"role_id": role_id},
            )

        codex_schema = _text(codex_role["result_schema"], f"codex {role_id} schema")
        claude_schema = _text(claude_role["result_schema"], f"claude {role_id} schema")
        for name, schema in (("codex", codex_schema), ("claude-code", claude_schema)):
            if schema != expected_schema:
                _fail(
                    "RESULT_SCHEMA_DIVERGENCE",
                    f"the {name} adapter rebinds the canonical output schema",
                    {
                        "adapter": name,
                        "expected": expected_schema,
                        "found": schema,
                        "role_id": role_id,
                    },
                )

        codex_agent_type = _text(codex_role["agent_type"], f"codex {role_id} agent_type")
        if codex_agent_type != expected_agent_type:
            _fail(
                "CODEX_AGENT_TYPE_DIVERGENCE",
                "the codex adapter binds a host agent type the registry does not name",
                {
                    "expected": expected_agent_type,
                    "found": codex_agent_type,
                    "role_id": role_id,
                },
            )

        claude_surface = _text(claude_role["surface"], f"claude {role_id} surface")
        if claude_surface != CLAUDE_UNIFORM_SURFACE:
            _fail(
                "CLAUDE_SURFACE_DIVERGENCE",
                "the claude adapter binds a host surface other than the uniform one",
                {
                    "expected": CLAUDE_UNIFORM_SURFACE,
                    "found": claude_surface,
                    "role_id": role_id,
                },
            )

        claude_isolation = _text(claude_role["isolation"], f"claude {role_id} isolation")
        if writable != (claude_isolation == "worktree"):
            _fail(
                "ISOLATION_DIVERGENCE",
                "claude worktree isolation does not track the registry write scope",
                {
                    "isolation": claude_isolation,
                    "role_id": role_id,
                    "writable": writable,
                },
            )

        roles.append(
            {
                "claude_isolation": claude_isolation,
                "claude_surface": claude_surface,
                "codex_agent_type": codex_agent_type,
                "output_schema_ref": expected_schema,
                "role_id": role_id,
                "writable": writable,
            }
        )

    return {
        "adapters": {
            "claude_code": CLAUDE_ADAPTER_RELATIVE_PATH,
            "codex": CODEX_ADAPTER_RELATIVE_PATH,
        },
        "canonical_registry_ref": REGISTRY_RELATIVE_PATH,
        "checks": {
            "claude_surface_aligned": len(roles),
            "codex_agent_type_aligned": len(roles),
            "isolation_aligned": len(roles),
            "result_schema_aligned": len(roles),
            "role_set_aligned": True,
        },
        "eval_id": "X04-PROVIDER-PARITY",
        "parity_surface": [role["role_id"] for role in roles],
        "role_count": len(roles),
        "roles": roles,
        "status": "PASS",
        "writable_role_count": sum(1 for role in roles if role["writable"]),
    }


def parity_surface(repository_root: str | Path) -> tuple[str, ...]:
    """Roles carried in parity by both adapters — the shared correlation anchor."""

    return tuple(evaluate_parity(repository_root)["parity_surface"])


# --------------------------------------------------------------------------- #
# Diversity: declared per-provider outcomes, correlated without an independence
# claim.
# --------------------------------------------------------------------------- #


def load_dataset(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed correlation fixture."""

    path = Path(repository_root) / DATASET_RELATIVE_PATH
    loaded = _read_json(path, "DATASET_UNREADABLE", "the correlation fixture")
    return _mapping(loaded, "dataset")


def load_results(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed machine-readable results artifact."""

    path = Path(repository_root) / RESULTS_RELATIVE_PATH
    loaded = _read_json(path, "RESULTS_UNREADABLE", "the results artifact")
    return _mapping(loaded, "results")


def _validate_ref(value: object, expected_path: str, label: str) -> dict[str, str]:
    record = _mapping(value, label)
    _exact_fields(record, _REF_FIELDS, label)
    path = _text(record["path"], f"{label}.path")
    if path != expected_path:
        _fail(
            "INPUT_INVALID",
            f"{label} must cite the sealed source it is bound to",
            {"expected": expected_path, "found": path},
        )
    return {"path": path, "version": _text(record["version"], f"{label}.version")}


def _validate_providers(payload: Mapping[str, Any]) -> None:
    seen: set[str] = set()
    for index, entry in enumerate(_sequence(payload["providers"], "providers")):
        record = _mapping(entry, f"providers[{index}]")
        _exact_fields(record, _PROVIDER_FIELDS, f"providers[{index}]")
        provider_id = _text(record["provider_id"], "provider_id")
        if provider_id not in PROVIDER_ADAPTERS:
            _fail(
                "PROVIDER_SET_INVALID",
                "a provider id is not one of the two adapters this gate binds",
                {"allowed": sorted(PROVIDER_ADAPTERS), "provider_id": provider_id},
            )
        if provider_id in seen:
            _fail(
                "PROVIDER_SET_INVALID",
                "a provider id is declared twice",
                {"provider_id": provider_id},
            )
        seen.add(provider_id)
        if record["synthetic"] is not True:
            _fail(
                "PROVIDER_OVERCLAIM",
                "a provider must declare itself synthetic; no live run is carried",
                {"provider_id": provider_id},
            )
        adapter_path = _text(record["adapter_path"], "adapter_path")
        if adapter_path != PROVIDER_ADAPTERS[provider_id]:
            _fail(
                "PROVIDER_ADAPTER_MISMATCH",
                "a provider cites an adapter path other than its sealed mapping",
                {
                    "expected": PROVIDER_ADAPTERS[provider_id],
                    "found": adapter_path,
                    "provider_id": provider_id,
                },
            )
    if seen != set(PROVIDER_ADAPTERS):
        _fail(
            "PROVIDER_SET_INVALID",
            "the fixture must declare exactly the two bound providers",
            {"declared": sorted(seen), "required": sorted(PROVIDER_ADAPTERS)},
        )


def _outcome(value: object, label: str) -> str:
    text = _text(value, label)
    if text not in OUTCOME_VOCABULARY:
        _fail(
            "OUTCOME_INVALID",
            f"{label} must be one of {OUTCOME_VOCABULARY}",
            {"allowed": list(OUTCOME_VOCABULARY), "value": text},
        )
    return text


def _phi_coefficient(n11: int, n10: int, n01: int, n00: int) -> float:
    denominator_squared = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    if denominator_squared == 0:
        return 0.0
    return (n11 * n00 - n10 * n01) / math.sqrt(denominator_squared)


def evaluate_correlation(
    payload: Mapping[str, Any], repository_root: str | Path
) -> dict[str, Any]:
    """Validate the fixture and measure cross-provider error correlation."""

    dataset = _mapping(payload, "dataset")
    _exact_fields(dataset, _DATASET_FIELDS, "dataset")
    declared_hash = _text(dataset["dataset_hash"], "dataset_hash")
    recomputed = hash_excluding(dataset, "dataset_hash")
    if declared_hash != recomputed:
        _fail(
            "DATASET_HASH_MISMATCH",
            "the fixture content does not match the hash it publishes",
            {"declared": declared_hash, "recomputed": recomputed},
        )

    diversity_position = _text(dataset["diversity_position"], "diversity_position")
    if diversity_position != DIVERSITY_POSITION_ALLOWED:
        # Any assertion of independence is the specific overclaim the spec forbids;
        # any other unexpected value is a plain shape error.
        if diversity_position in {"assumed_independent", "independent"}:
            _fail(
                "INDEPENDENCE_OVERCLAIM",
                "the fixture asserts the providers are statistically independent",
                {"diversity_position": diversity_position},
            )
        _fail(
            "INPUT_INVALID",
            "diversity_position must be the not-assumed-independent position",
            {
                "allowed": DIVERSITY_POSITION_ALLOWED,
                "diversity_position": diversity_position,
            },
        )

    registry_ref = _validate_ref(
        dataset["canonical_registry_ref"], REGISTRY_RELATIVE_PATH, "canonical_registry_ref"
    )
    codex_ref = _validate_ref(
        dataset["codex_adapter_ref"], CODEX_ADAPTER_RELATIVE_PATH, "codex_adapter_ref"
    )
    claude_ref = _validate_ref(
        dataset["claude_adapter_ref"], CLAUDE_ADAPTER_RELATIVE_PATH, "claude_adapter_ref"
    )
    _validate_providers(dataset)

    surface = set(parity_surface(repository_root))

    n11 = n10 = n01 = n00 = 0
    seen: set[str] = set()
    trial_ids: list[str] = []
    for index, entry in enumerate(_sequence(dataset["trials"], "trials")):
        record = _mapping(entry, f"trials[{index}]")
        _exact_fields(record, _TRIAL_FIELDS, f"trials[{index}]")
        trial_id = _text(record["trial_id"], "trial_id")
        if trial_id in seen:
            _fail("DUPLICATE_TRIAL", "trial ids must be unique", {"trial_id": trial_id})
        seen.add(trial_id)
        trial_ids.append(trial_id)
        role_id = _text(record["role_id"], "role_id")
        if role_id not in surface:
            _fail(
                "ROLE_NOT_IN_PARITY_SURFACE",
                "a trial role must be carried in parity by both adapters",
                {"role_id": role_id, "trial_id": trial_id},
            )
        codex_error = _outcome(record["codex_outcome"], "codex_outcome") == "error"
        claude_error = _outcome(record["claude_outcome"], "claude_outcome") == "error"
        if codex_error and claude_error:
            n11 += 1
        elif codex_error:
            n10 += 1
        elif claude_error:
            n01 += 1
        else:
            n00 += 1

    total = n11 + n10 + n01 + n00
    if total == 0:
        _fail("INPUT_INVALID", "the fixture declares no trial")

    codex_error_rate = (n11 + n10) / total
    claude_error_rate = (n11 + n01) / total
    joint_error_observed = n11 / total
    joint_error_expected = codex_error_rate * claude_error_rate
    excess_joint_error = joint_error_observed - joint_error_expected

    return {
        "codex_error_rate": codex_error_rate,
        "claude_error_rate": claude_error_rate,
        "contingency": {
            "both_error": n11,
            "claude_only_error": n01,
            "codex_only_error": n10,
            "neither_error": n00,
        },
        "dataset_hash": declared_hash,
        "dataset_id": _text(dataset["dataset_id"], "dataset_id"),
        "diversity_position": diversity_position,
        "eval_id": "X04-ERROR-CORRELATION",
        "evaluated_at": _instant_text(dataset["evaluated_at"], "evaluated_at"),
        "excess_joint_error": excess_joint_error,
        "independence_assumed": False,
        "joint_error_expected_if_independent": joint_error_expected,
        "joint_error_observed": joint_error_observed,
        "phi_coefficient": _phi_coefficient(n11, n10, n01, n00),
        "positively_correlated": excess_joint_error > 0,
        "report_id": _text(dataset["report_id"], "report_id"),
        "sources": {
            "canonical_registry_ref": registry_ref,
            "claude_adapter_ref": claude_ref,
            "codex_adapter_ref": codex_ref,
        },
        "status": "PASS",
        "synthetic": True,
        "trial_count": total,
        "trial_ids": sorted(trial_ids),
        "version": _text(dataset["version"], "version"),
    }


# --------------------------------------------------------------------------- #
# The sealed combined report both required checks re-derive.
# --------------------------------------------------------------------------- #


def evaluate(payload: Mapping[str, Any], repository_root: str | Path) -> SealedReport:
    """Seal the combined parity-and-correlation report."""

    parity = evaluate_parity(repository_root)
    correlation = evaluate_correlation(payload, repository_root)
    report: dict[str, Any] = {
        "correlation": correlation,
        "eval_id": "X04-CROSS-PROVIDER-PARITY-AND-DIVERSITY",
        "parity": parity,
        "status": "PASS",
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    return SealedReport(canonical_json(report))


def evaluate_dataset(repository_root: str | Path) -> SealedReport:
    """Evaluate the fixture exactly as it is committed."""

    return evaluate(load_dataset(repository_root), repository_root)


def verify_results(repository_root: str | Path) -> dict[str, Any]:
    """Re-derive the committed results artifact and refuse any drift."""

    committed = load_results(repository_root)
    derived = evaluate_dataset(repository_root).payload
    if committed != derived:
        _fail(
            "RESULTS_STALE",
            "the committed results artifact is not the report the sealed surfaces "
            "and committed fixture produce",
            {
                "committed_hash": committed.get("report_hash"),
                "derived_hash": derived["report_hash"],
            },
        )
    return derived
