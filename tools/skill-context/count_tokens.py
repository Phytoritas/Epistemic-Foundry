#!/usr/bin/env python3
"""Canonical J02 token accounting for o200k_base with tiktoken 0.13.0."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
import tomllib
import unicodedata
from pathlib import Path
from typing import Any


TOKENIZER_PACKAGE = "tiktoken"
TOKENIZER_VERSION = "0.13.0"
TOKENIZER_ENCODING = "o200k_base"
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CANONICAL_BUDGETS = {
    "initial_metadata_max_utf8_bytes": 6400,
    "initial_metadata_max_o200k_tokens": 1600,
    "skill_body_max_utf8_bytes": 4096,
    "skill_body_max_o200k_tokens": 1024,
    "reference_file_max_utf8_bytes": 4096,
    "reference_file_max_o200k_tokens": 1024,
    "reference_closure_max_count": 12,
    "reference_closure_max_depth": 5,
    "reference_closure_max_utf8_bytes": 24576,
    "reference_closure_max_o200k_tokens": 6144,
    "activation_max_utf8_bytes": 28672,
    "activation_max_o200k_tokens": 7168,
}
TOKENIZER_SDIST_SHA256 = (
    "sha256:c9435714c3a84c2319499de9a300c0e604449dd0799ff246458b3bb6a7f433c1"
)


class TokenizerContractError(RuntimeError):
    """A typed fail-closed token-accounting error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require_tokenizer():
    try:
        version = importlib.metadata.version(TOKENIZER_PACKAGE)
        import tiktoken
    except (importlib.metadata.PackageNotFoundError, ImportError) as exc:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            f"{TOKENIZER_PACKAGE}=={TOKENIZER_VERSION} is required",
        ) from exc
    if version != TOKENIZER_VERSION:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            f"expected {TOKENIZER_PACKAGE}=={TOKENIZER_VERSION}, observed {version}",
        )
    try:
        encoding = tiktoken.get_encoding(TOKENIZER_ENCODING)
    except Exception as exc:  # pragma: no cover - library boundary
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            f"encoding {TOKENIZER_ENCODING} is unavailable",
        ) from exc
    if encoding.name != TOKENIZER_ENCODING:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE", "tokenizer returned a different encoding"
        )
    return encoding


def count_text(text: str, encoding) -> tuple[int, list[int]]:
    tokens = encoding.encode(text, disallowed_special=())
    return len(tokens), tokens


def require_non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID", f"{label} must be a non-negative integer"
        )
    return value


def assert_metadata_budget(byte_count: int, token_count: int, skill_count: int = 29) -> None:
    byte_count = require_non_negative_integer(byte_count, "metadata byte_count")
    token_count = require_non_negative_integer(token_count, "metadata token_count")
    skill_count = require_non_negative_integer(skill_count, "metadata skill_count")
    if (
        skill_count != 29
        or byte_count > CANONICAL_BUDGETS["initial_metadata_max_utf8_bytes"]
        or token_count > CANONICAL_BUDGETS["initial_metadata_max_o200k_tokens"]
    ):
        raise TokenizerContractError(
            "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
            "all 29 skill metadata entries must fit both canonical budgets",
        )


def assert_description_budget(description: str) -> None:
    normalized = normalize_description(description)
    if len(normalized.encode("utf-8")) > 140:
        raise TokenizerContractError(
            "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
            "metadata description exceeds 140 UTF-8 bytes",
        )


def assert_activation_budget(candidate: dict[str, Any]) -> None:
    expected_keys = {
        "skill_bytes",
        "skill_tokens",
        "reference_count",
        "reference_depth",
        "reference_bytes",
        "reference_tokens",
    }
    if set(candidate) != expected_keys:
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID",
            "activation budget candidate has missing or unexpected fields",
        )
    values = {
        key: require_non_negative_integer(value, key) for key, value in candidate.items()
    }
    if values["reference_depth"] > CANONICAL_BUDGETS["reference_closure_max_depth"]:
        raise TokenizerContractError(
            "REFERENCE_DEPTH_EXCEEDED",
            "reference dependency depth exceeds the canonical maximum",
        )
    total_bytes = values["skill_bytes"] + values["reference_bytes"]
    total_tokens = values["skill_tokens"] + values["reference_tokens"]
    if (
        values["skill_bytes"] > CANONICAL_BUDGETS["skill_body_max_utf8_bytes"]
        or values["skill_tokens"] > CANONICAL_BUDGETS["skill_body_max_o200k_tokens"]
        or values["reference_count"] > CANONICAL_BUDGETS["reference_closure_max_count"]
        or values["reference_bytes"]
        > CANONICAL_BUDGETS["reference_closure_max_utf8_bytes"]
        or values["reference_tokens"]
        > CANONICAL_BUDGETS["reference_closure_max_o200k_tokens"]
        or total_bytes > CANONICAL_BUDGETS["activation_max_utf8_bytes"]
        or total_tokens > CANONICAL_BUDGETS["activation_max_o200k_tokens"]
    ):
        raise TokenizerContractError(
            "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
            "skill and reference closure exceed a canonical activation budget",
        )


def verify_repository_tokenizer_lock(root: Path) -> dict[str, Any]:
    """Verify that the executable repository environment closes the tokenizer pin."""

    pyproject_path = root / "pyproject.toml"
    lock_path = root / "uv.lock"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "pyproject.toml and uv.lock must provide readable tokenizer lock evidence",
        ) from exc

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE", "pyproject project table is missing"
        )
    dependency_groups = pyproject.get("dependency-groups")
    skill_context_group = (
        dependency_groups.get("skill-context")
        if isinstance(dependency_groups, dict)
        else None
    )
    normalized_group = (
        [value.replace(" ", "") for value in skill_context_group]
        if isinstance(skill_context_group, list)
        and all(isinstance(value, str) for value in skill_context_group)
        else None
    )
    if normalized_group != ["tiktoken==0.13.0"]:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "pyproject.toml dependency-group skill-context must contain exactly "
            "tiktoken==0.13.0",
        )
    runtime_declarations: list[str] = []
    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list):
        runtime_declarations.extend(
            value for value in dependencies if isinstance(value, str)
        )
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for values in optional.values():
            if isinstance(values, list):
                runtime_declarations.extend(
                    value for value in values if isinstance(value, str)
                )
    if any(
        re.match(r"^\s*tiktoken(?:\s|[<>=!~@\[]|$)", value, re.IGNORECASE)
        for value in runtime_declarations
    ):
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "tiktoken must not be exposed as a runtime or optional dependency",
        )

    packages = lock.get("package")
    if not isinstance(packages, list):
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE", "uv.lock package table is missing"
        )
    tokenizer_packages = [
        entry for entry in packages if isinstance(entry, dict) and entry.get("name") == "tiktoken"
    ]
    if len(tokenizer_packages) != 1:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "uv.lock must contain exactly one tiktoken package",
        )
    tokenizer = tokenizer_packages[0]
    sdist = tokenizer.get("sdist")
    if (
        tokenizer.get("version") != TOKENIZER_VERSION
        or not isinstance(sdist, dict)
        or sdist.get("hash") != TOKENIZER_SDIST_SHA256
        or not str(sdist.get("url", "")).endswith("/tiktoken-0.13.0.tar.gz")
    ):
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "uv.lock tokenizer version or sdist digest differs from the canonical pin",
        )

    root_packages = [
        entry
        for entry in packages
        if isinstance(entry, dict) and entry.get("name") == "epistemic-foundry"
    ]
    if len(root_packages) != 1:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE", "uv.lock root package is missing or duplicated"
        )
    root_package = root_packages[0]
    dev_dependencies = root_package.get("dev-dependencies", {})
    locked_group = (
        dev_dependencies.get("skill-context")
        if isinstance(dev_dependencies, dict)
        else None
    )
    exact_locked_group = (
        isinstance(locked_group, list)
        and len(locked_group) == 1
        and locked_group[0] == {"name": "tiktoken"}
    )
    metadata = root_package.get("metadata", {})
    requires_dev = metadata.get("requires-dev", {}) if isinstance(metadata, dict) else {}
    metadata_group = (
        requires_dev.get("skill-context") if isinstance(requires_dev, dict) else None
    )
    exact_requires_dev = metadata_group == [
        {"name": "tiktoken", "specifier": "==0.13.0"}
    ]
    runtime_locked = root_package.get("dependencies", [])
    runtime_locked_exposure = (
        isinstance(runtime_locked, list)
        and any(
            isinstance(entry, dict) and entry.get("name") == "tiktoken"
            for entry in runtime_locked
        )
    )
    requires_dist = metadata.get("requires-dist", []) if isinstance(metadata, dict) else []
    metadata_runtime_exposure = (
        isinstance(requires_dist, list)
        and any(
            isinstance(entry, dict) and entry.get("name") == "tiktoken"
            for entry in requires_dist
        )
    )
    if (
        not exact_locked_group
        or not exact_requires_dev
        or runtime_locked_exposure
        or metadata_runtime_exposure
    ):
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE",
            "uv.lock skill-context dependency-group closure does not bind exactly "
            "tiktoken==0.13.0 without runtime exposure",
        )
    return {
        "dependency_group": "skill-context",
        "pyproject_requirement": "tiktoken==0.13.0",
        "lock_package_count": 1,
        "locked_version": TOKENIZER_VERSION,
        "runtime_dependency_exposure": False,
        "sdist_sha256": TOKENIZER_SDIST_SHA256,
        "status": "PASS",
    }


def read_canonical_text(path: Path) -> tuple[bytes, str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TokenizerContractError(
            "REFERENCE_TARGET_MISSING", f"cannot read {path.as_posix()}: {exc}"
        ) from exc
    if data.startswith(b"\xef\xbb\xbf"):
        raise TokenizerContractError(
            "REFERENCE_CONTENT_DRIFT", f"{path.as_posix()} contains a UTF-8 BOM"
        )
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TokenizerContractError(
            "REFERENCE_CONTENT_DRIFT", f"{path.as_posix()} is not valid UTF-8"
        ) from exc
    if "\r" in text or not text.endswith("\n"):
        raise TokenizerContractError(
            "REFERENCE_CONTENT_DRIFT",
            f"{path.as_posix()} must use LF and end with one newline",
        )
    return data, text


def normalize_description(value: str) -> str:
    normalized = re.sub(r"[ \f\v]+", " ", value.strip())
    if "\t" in normalized or "\n" in normalized or "\r" in normalized:
        raise TokenizerContractError(
            "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
            "metadata descriptions cannot contain tabs or newlines",
        )
    return unicodedata.normalize("NFC", normalized)


def serialize_metadata(skills: list[dict[str, Any]]) -> str:
    if len(skills) != 29:
        raise TokenizerContractError(
            "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
            "metadata requires exactly 29 skill entries",
        )
    parents = [entry for entry in skills if entry.get("skill_id") == "foundry"]
    if len(parents) != 1:
        raise TokenizerContractError(
            "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED", "metadata requires one foundry parent"
        )
    children = sorted(
        (entry for entry in skills if entry.get("skill_id") != "foundry"),
        key=lambda entry: str(entry.get("name", "")).encode("utf-8"),
    )
    lines: list[str] = []
    for entry in [parents[0], *children]:
        name = str(entry.get("name", ""))
        description = normalize_description(str(entry.get("description", "")))
        relative_path = str(entry.get("path", ""))
        if not name.isascii() or not relative_path.isascii():
            raise TokenizerContractError(
                "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
                "skill names and metadata paths must be ASCII",
            )
        if len(name.encode("ascii")) > 64 or len(relative_path.encode("ascii")) > 128:
            raise TokenizerContractError(
                "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
                "skill name or metadata path exceeds its limit",
            )
        if len(description.encode("utf-8")) > 140:
            raise TokenizerContractError(
                "INITIAL_SKILL_METADATA_BUDGET_EXCEEDED",
                f"description exceeds 140 bytes: {name}",
            )
        lines.append(f"{name}\t{description}\t{relative_path}\n")
    return unicodedata.normalize("NFC", "".join(lines))


def inventory_report(root: Path, inventory_path: Path) -> dict[str, Any]:
    repository_lock = verify_repository_tokenizer_lock(root)
    encoding = require_tokenizer()
    raw = inventory_path.read_bytes()
    try:
        inventory = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID", "inventory is not valid BOM-less UTF-8 JSON"
        ) from exc
    if raw.startswith(b"\xef\xbb\xbf") or not isinstance(inventory, dict):
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID", "inventory is not a canonical JSON object"
        )
    tokenizer = inventory.get("tokenizer")
    if not isinstance(tokenizer, dict) or tokenizer != {
        "package": "tiktoken",
        "version": "0.13.0",
        "encoding": "o200k_base",
        "disallowed_special": [],
        "dependency_artifact": {
            "artifact_kind": "sdist",
            "filename": "tiktoken-0.13.0.tar.gz",
            "sha256": TOKENIZER_SDIST_SHA256,
            "source_url": "https://files.pythonhosted.org/packages/source/t/tiktoken/tiktoken-0.13.0.tar.gz",
        },
    }:
        raise TokenizerContractError(
            "TOKENIZER_CONTRACT_UNAVAILABLE", "inventory tokenizer lock evidence is invalid"
        )

    skills = inventory.get("skills")
    references = inventory.get("references")
    if inventory.get("budgets") != CANONICAL_BUDGETS:
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID",
            "inventory budgets differ from the canonical J02 budget contract",
        )
    if not isinstance(skills, list) or not isinstance(references, list):
        raise TokenizerContractError(
            "INVENTORY_CONTRACT_INVALID", "inventory skills and references must be arrays"
        )
    metadata = serialize_metadata(skills)
    metadata_tokens, _ = count_text(metadata, encoding)
    metadata_bytes = metadata.encode("utf-8")
    metadata_seal = inventory.get("metadata_projection")
    expected_metadata = {
        "sha256": sha256_bytes(metadata_bytes),
        "byte_count": len(metadata_bytes),
        "token_count": metadata_tokens,
    }
    if metadata_seal != expected_metadata:
        raise TokenizerContractError(
            "INVENTORY_HASH_MISMATCH", "metadata projection seal does not match"
        )
    assert_metadata_budget(len(metadata_bytes), metadata_tokens, len(skills))

    skill_results: list[dict[str, Any]] = []
    for entry in skills:
        if not isinstance(entry, dict):
            raise TokenizerContractError("INVENTORY_CONTRACT_INVALID", "invalid skill entry")
        path = root / "plugins/epistemic-foundry" / str(entry["path"])
        data, text = read_canonical_text(path)
        token_count, _ = count_text(text, encoding)
        actual = {
            "sha256": sha256_bytes(data),
            "byte_count": len(data),
            "token_count": token_count,
        }
        expected = {
            "sha256": entry.get("sha256"),
            "byte_count": entry.get("byte_count"),
            "token_count": entry.get("token_count"),
        }
        if actual != expected:
            raise TokenizerContractError(
                "REFERENCE_CONTENT_DRIFT", f"skill seal differs: {entry.get('skill_id')}"
            )
        if (
            actual["byte_count"] > CANONICAL_BUDGETS["skill_body_max_utf8_bytes"]
            or actual["token_count"] > CANONICAL_BUDGETS["skill_body_max_o200k_tokens"]
        ):
            raise TokenizerContractError(
                "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
                f"skill exceeds activation budget: {entry.get('skill_id')}",
            )
        skill_results.append({"skill_id": entry["skill_id"], **actual})

    reference_results: list[dict[str, Any]] = []
    for entry in references:
        if not isinstance(entry, dict):
            raise TokenizerContractError("INVENTORY_CONTRACT_INVALID", "invalid reference entry")
        path = root / "plugins/epistemic-foundry" / str(entry["path"])
        data, text = read_canonical_text(path)
        token_count, _ = count_text(text, encoding)
        actual = {
            "sha256": sha256_bytes(data),
            "byte_count": len(data),
            "token_count": token_count,
        }
        expected = {
            "sha256": entry.get("sha256"),
            "byte_count": entry.get("byte_count"),
            "token_count": entry.get("token_count"),
        }
        if actual != expected:
            raise TokenizerContractError(
                "REFERENCE_CONTENT_DRIFT",
                f"reference seal differs: {entry.get('reference_id')}",
            )
        if (
            actual["byte_count"] > CANONICAL_BUDGETS["reference_file_max_utf8_bytes"]
            or actual["token_count"] > CANONICAL_BUDGETS["reference_file_max_o200k_tokens"]
        ):
            raise TokenizerContractError(
                "REFERENCE_CONTEXT_BUDGET_EXCEEDED",
                f"reference exceeds atomic budget: {entry.get('reference_id')}",
            )
        reference_results.append({"reference_id": entry["reference_id"], **actual})

    asserted_hash = inventory.get("inventory_hash")
    preimage = dict(inventory)
    preimage.pop("inventory_hash", None)
    computed_hash = sha256_bytes(canonical_json(preimage).encode("utf-8"))
    if not isinstance(asserted_hash, str) or not HASH_PATTERN.fullmatch(asserted_hash):
        raise TokenizerContractError("INVENTORY_HASH_MISMATCH", "inventory hash is invalid")
    if asserted_hash != computed_hash:
        raise TokenizerContractError("INVENTORY_HASH_MISMATCH", "inventory hash mismatch")
    return {
        "status": "PASS",
        "tokenizer": {
            "package": TOKENIZER_PACKAGE,
            "version": TOKENIZER_VERSION,
            "encoding": TOKENIZER_ENCODING,
            "disallowed_special": [],
        },
        "inventory_hash": computed_hash,
        "repository_lock": repository_lock,
        "budgets": CANONICAL_BUDGETS,
        "metadata_projection": expected_metadata,
        "skills": skill_results,
        "references": reference_results,
    }


def count_command(text: str) -> dict[str, Any]:
    encoding = require_tokenizer()
    count, token_ids = count_text(text, encoding)
    return {
        "status": "PASS",
        "tokenizer": {
            "package": TOKENIZER_PACKAGE,
            "version": TOKENIZER_VERSION,
            "encoding": TOKENIZER_ENCODING,
            "disallowed_special": [],
        },
        "utf8_bytes": len(text.encode("utf-8")),
        "token_count": count,
        "token_ids": token_ids,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    count_parser = subparsers.add_parser("count", help="count one exact string")
    source = count_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--file", type=Path)
    inventory_parser = subparsers.add_parser("verify-inventory")
    inventory_parser.add_argument("--root", type=Path, default=Path.cwd())
    inventory_parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("plugins/epistemic-foundry/skills/skill-inventory.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "count":
            if args.text is not None:
                text = args.text
            else:
                _, text = read_canonical_text(args.file)
            result = count_command(text)
        else:
            root = args.root.resolve()
            inventory = args.inventory
            if not inventory.is_absolute():
                inventory = root / inventory
            result = inventory_report(root, inventory.resolve())
    except TokenizerContractError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": {"code": exc.code, "message": str(exc)}},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
