#!/usr/bin/env python3
"""Generate C02 transport projections from the canonical JSON Schemas.

The files below ``schemas/`` are the sole semantic authority.  This generator
does not translate conditional validation rules into a competing validator;
it emits language-level transport shapes plus a content-addressed manifest
that keeps every projection bound to the authoritative schema and example.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


GENERATOR_ID = "packages/contracts/codegen/generate.py"
MANIFEST_SCHEMA = "epistemic-foundry-contract-manifest/v1"
HASH_ALGORITHM = "sha256(path_utf8 + NUL + raw_bytes + NUL), path-sorted"
GENERATED_ROOTS = (
    Path("packages/contracts/src/generated"),
    Path("python/epistemic_foundry/contracts"),
    Path("web/src/generated"),
)
EXAMPLE_ALIASES = {
    "claim-card": "sample_claim.json",
    "context-assembly-manifest": "sample_context_manifest.json",
    "evidence-node": "sample_evidence.json",
    "hypothesis-passport": "sample_passport.json",
    "insight-card": "sample_insight.json",
    "validation-target-manifest": "sample_validation_target.json",
}


class GenerationError(RuntimeError):
    """Raised when the canonical source inventory is inconsistent."""


@dataclass(frozen=True)
class Contract:
    schema_file: str
    example_file: str
    title: str
    schema_id: str
    schema_sha256: str
    example_sha256: str
    schema: Mapping[str, Any]
    example: Any


def repository_root(start: Path | None = None) -> Path:
    candidate = (start or Path(__file__)).resolve()
    for parent in (candidate, *candidate.parents):
        if (parent / "MASTER_SPEC.md").is_file() and (parent / "schemas").is_dir():
            return parent
    raise GenerationError("Could not locate the Epistemic Foundry repository root")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Invalid UTF-8 JSON at {path}: {exc}") from exc


def bundle_hash(entries: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, raw in sorted(entries, key=lambda item: item[0]):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def load_contracts(root: Path) -> tuple[list[Contract], str, str]:
    schema_paths = sorted((root / "schemas").glob("*.schema.json"))
    if not schema_paths:
        raise GenerationError("No canonical schemas found")
    canonical_examples = set((root / "examples").glob("sample_*.json"))

    contracts: list[Contract] = []
    schema_entries: list[tuple[str, bytes]] = []
    example_entries: list[tuple[str, bytes]] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    mapped_examples: set[Path] = set()

    for schema_path in schema_paths:
        stem = schema_path.name.removesuffix(".schema.json")
        candidate_names = (
            EXAMPLE_ALIASES.get(stem),
            f"sample_{stem}.json",
            f"sample_{stem.replace('-', '_')}.json",
        )
        candidates = {
            root / "examples" / name
            for name in candidate_names
            if name is not None and (root / "examples" / name).is_file()
        }
        if len(candidates) != 1:
            raise GenerationError(f"Missing canonical example for {schema_path.name}")
        example_path = candidates.pop()
        if example_path in mapped_examples:
            raise GenerationError(f"Canonical example mapped more than once: {example_path.name}")
        mapped_examples.add(example_path)

        schema_raw, schema = read_json(schema_path)
        example_raw, example = read_json(example_path)
        if not isinstance(schema, dict):
            raise GenerationError(f"Schema is not an object: {schema_path.name}")
        title = schema.get("title")
        schema_id = schema.get("$id")
        if not isinstance(title, str) or not title:
            raise GenerationError(f"Schema has no non-empty title: {schema_path.name}")
        if not isinstance(schema_id, str) or not schema_id:
            raise GenerationError(f"Schema has no non-empty $id: {schema_path.name}")
        if schema_id in seen_ids:
            raise GenerationError(f"Duplicate canonical schema $id: {schema_id}")
        if title in seen_titles:
            raise GenerationError(f"Duplicate canonical schema title: {title}")
        seen_ids.add(schema_id)
        seen_titles.add(title)

        schema_relative = schema_path.relative_to(root).as_posix()
        example_relative = example_path.relative_to(root).as_posix()
        schema_entries.append((schema_relative, schema_raw))
        example_entries.append((example_relative, example_raw))
        contracts.append(
            Contract(
                schema_file=schema_relative,
                example_file=example_relative,
                title=title,
                schema_id=schema_id,
                schema_sha256=f"sha256:{sha256_bytes(schema_raw)}",
                example_sha256=f"sha256:{sha256_bytes(example_raw)}",
                schema=schema,
                example=example,
            )
        )

    if mapped_examples != canonical_examples:
        missing = sorted(path.name for path in canonical_examples - mapped_examples)
        extra = sorted(path.name for path in mapped_examples - canonical_examples)
        raise GenerationError(
            "Schema/example mapping is not one-to-one; "
            f"unmapped={missing}, noncanonical={extra}"
        )

    return contracts, bundle_hash(schema_entries), bundle_hash(example_entries)


def json_pointer(tokens: Sequence[str]) -> str:
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)


def collect_keyword_entries(
    value: Any,
    keyword_name: str,
    tokens: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if keyword_name in value:
            output.append(
                {
                    "pointer": json_pointer((*tokens, keyword_name)),
                    "value": value[keyword_name],
                }
            )
        for key in sorted(value):
            output.extend(collect_keyword_entries(value[key], keyword_name, (*tokens, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            output.extend(collect_keyword_entries(item, keyword_name, (*tokens, str(index))))
    return output


def property_descriptor(name: str, fragment: Any, required: bool) -> dict[str, Any]:
    return {
        "name": name,
        "required": required,
        "schema": fragment,
    }


def contract_record(contract: Contract) -> dict[str, Any]:
    properties = contract.schema.get("properties", {})
    required = contract.schema.get("required", [])
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []
    required_set = {item for item in required if isinstance(item, str)}
    return {
        "schema_file": contract.schema_file,
        "example_file": contract.example_file,
        "title": contract.title,
        "schema_id": contract.schema_id,
        "source_sha256": contract.schema_sha256,
        "example_sha256": contract.example_sha256,
        "required_fields": list(required),
        "properties": [
            property_descriptor(name, properties[name], name in required_set)
            for name in sorted(properties)
        ],
        "enum_entries": collect_keyword_entries(contract.schema, "enum"),
        "const_entries": collect_keyword_entries(contract.schema, "const"),
        "ref_entries": collect_keyword_entries(contract.schema, "$ref"),
    }


def build_manifest(
    contracts: Sequence[Contract],
    schema_bundle_sha256: str,
    example_bundle_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "generator": GENERATOR_ID,
        "source_authority": "schemas/*.schema.json",
        "example_authority": "examples/sample_*.json",
        "canonical_schema_draft": "https://json-schema.org/draft/2020-12/schema",
        "bundle_hash_algorithm": HASH_ALGORITHM,
        "schema_count": len(contracts),
        "example_count": len(contracts),
        "schema_bundle_sha256": schema_bundle_sha256,
        "example_bundle_sha256": example_bundle_sha256,
        "contracts": [contract_record(contract) for contract in contracts],
    }


def json_text(value: Any, *, indent: int = 2) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent) + "\n"


def pascal_identifier(value: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) and not keyword.iskeyword(value):
        if any(character.isupper() for character in value[1:]):
            return value
    parts = [part for part in re.split(r"[^A-Za-z0-9]+|_+", value) if part]
    result = "".join(part[:1].upper() + part[1:] for part in parts) or "Anonymous"
    if result[0].isdigit():
        result = f"N{result}"
    return result


def py_literal(value: Any) -> str:
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    return repr(value)


class SchemaTypes:
    def __init__(self, contracts: Sequence[Contract]):
        self.contracts = contracts
        self.by_file = {
            Path(contract.schema_file).name: contract for contract in contracts
        }
        self.root_names = {
            Path(contract.schema_file).name: pascal_identifier(contract.title)
            for contract in contracts
        }
        generated_names = list(self.root_names.values())
        for contract in contracts:
            definitions = contract.schema.get("$defs", {})
            if isinstance(definitions, dict):
                generated_names.extend(
                    self.local_name(contract, definition) for definition in definitions
                )
        duplicates = sorted(
            name for name in set(generated_names) if generated_names.count(name) > 1
        )
        if duplicates:
            raise GenerationError(f"Generated model name collision: {duplicates}")

    def local_name(self, contract: Contract, definition: str) -> str:
        return f"{pascal_identifier(contract.title)}{pascal_identifier(definition)}"

    def resolve_ref(self, contract: Contract, reference: str) -> tuple[Contract, Any, str | None]:
        if reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
            definitions = contract.schema.get("$defs", {})
            if not isinstance(definitions, dict) or name not in definitions:
                raise GenerationError(f"Unresolved local $ref {reference} in {contract.schema_file}")
            return contract, definitions[name], name
        file_part = reference.split("#", 1)[0]
        file_name = Path(file_part).name
        target = self.by_file.get(file_name)
        if target is None:
            raise GenerationError(f"Unresolved external $ref {reference} in {contract.schema_file}")
        if "#" in reference:
            fragment = reference.split("#", 1)[1]
            if fragment not in ("", "/"):
                raise GenerationError(
                    f"External fragment refs are not supported by C02 projection: {reference}"
                )
        return target, target.schema, None

    def ts_type(
        self,
        contract: Contract,
        fragment: Any,
        stack: tuple[str, ...] = (),
    ) -> str:
        if not isinstance(fragment, dict):
            return "JsonValue"
        if "$ref" in fragment and isinstance(fragment["$ref"], str):
            reference = fragment["$ref"]
            target, resolved, local = self.resolve_ref(contract, reference)
            if local is not None:
                return self.local_name(contract, local)
            return self.root_names[Path(target.schema_file).name]
        if "const" in fragment:
            return json.dumps(fragment["const"], ensure_ascii=False)
        enum = fragment.get("enum")
        if isinstance(enum, list) and enum:
            return " | ".join(json.dumps(value, ensure_ascii=False) for value in enum)
        for keyword_name, separator in (("oneOf", " | "), ("anyOf", " | "), ("allOf", " & ")):
            branches = fragment.get(keyword_name)
            if isinstance(branches, list) and branches:
                rendered: list[str] = []
                for branch in branches:
                    value = self.ts_type(contract, branch, (*stack, keyword_name))
                    if value not in rendered:
                        rendered.append(value)
                return separator.join(f"({value})" for value in rendered)
        schema_type = fragment.get("type")
        if isinstance(schema_type, list):
            rendered = []
            for member in schema_type:
                member_type = self.ts_type(contract, {**fragment, "type": member})
                if member_type not in rendered:
                    rendered.append(member_type)
            return " | ".join(rendered) or "JsonValue"
        if schema_type == "null":
            return "null"
        if schema_type == "boolean":
            return "boolean"
        if schema_type in ("number", "integer"):
            return "number"
        if schema_type == "string":
            return "string"
        if schema_type == "array" or "items" in fragment or "prefixItems" in fragment:
            prefix = fragment.get("prefixItems")
            if isinstance(prefix, list) and prefix:
                values = ", ".join(self.ts_type(contract, item, stack) for item in prefix)
                return f"readonly [{values}]"
            return f"ReadonlyArray<{self.ts_type(contract, fragment.get('items', {}), stack)}>"
        if schema_type == "object" or "properties" in fragment:
            properties = fragment.get("properties", {})
            required = set(fragment.get("required", []))
            members: list[str] = []
            if isinstance(properties, dict):
                for name in sorted(properties):
                    optional = "" if name in required else "?"
                    member_type = self.ts_type(contract, properties[name], stack)
                    members.append(
                        f"readonly {json.dumps(name, ensure_ascii=False)}{optional}: {member_type};"
                    )
            additional = fragment.get("additionalProperties")
            if isinstance(additional, dict):
                members.append(
                    f"readonly [key: string]: {self.ts_type(contract, additional, stack)};"
                )
            if not members and additional is not False:
                return "Readonly<Record<string, JsonValue>>"
            return "{ " + " ".join(members) + " }"
        return "JsonValue"

    def py_type(self, contract: Contract, fragment: Any) -> str:
        if not isinstance(fragment, dict):
            return "JsonValue"
        if "$ref" in fragment and isinstance(fragment["$ref"], str):
            target, resolved, local = self.resolve_ref(contract, fragment["$ref"])
            if local is not None:
                if isinstance(resolved, dict) and (
                    resolved.get("type") == "object" or "properties" in resolved
                ):
                    return f'ForwardRef("{self.local_name(contract, local)}")'
                return self.py_type(contract, resolved)
            return f'ForwardRef("{self.root_names[Path(target.schema_file).name]}")'
        if "const" in fragment:
            return f"Literal[{py_literal(fragment['const'])}]"
        enum = fragment.get("enum")
        if isinstance(enum, list) and enum:
            return "Literal[" + ", ".join(py_literal(value) for value in enum) + "]"
        for keyword_name in ("oneOf", "anyOf"):
            branches = fragment.get(keyword_name)
            if isinstance(branches, list) and branches:
                rendered: list[str] = []
                for branch in branches:
                    value = self.py_type(contract, branch)
                    if value not in rendered:
                        rendered.append(value)
                if len(rendered) == 1:
                    return rendered[0]
                return "Union[" + ", ".join(rendered) + "]"
        if isinstance(fragment.get("allOf"), list):
            # Python's type system has no structural intersection.  The exact
            # allOf semantics remain enforced by the hash-bound JSON Schema.
            return "JsonValue"
        schema_type = fragment.get("type")
        if isinstance(schema_type, list):
            rendered: list[str] = []
            for member in schema_type:
                value = self.py_type(contract, {**fragment, "type": member})
                if value not in rendered:
                    rendered.append(value)
            if len(rendered) == 1:
                return rendered[0]
            return "Union[" + ", ".join(rendered) + "]"
        if schema_type == "null":
            return "None"
        if schema_type == "boolean":
            return "bool"
        if schema_type == "integer":
            return "int"
        if schema_type == "number":
            return "float"
        if schema_type == "string":
            return "str"
        if schema_type == "array" or "items" in fragment or "prefixItems" in fragment:
            prefix = fragment.get("prefixItems")
            if isinstance(prefix, list) and prefix:
                rendered: list[str] = []
                for item in prefix:
                    value = self.py_type(contract, item)
                    if value not in rendered:
                        rendered.append(value)
                if len(rendered) == 1:
                    return f"list[{rendered[0]}]"
                return "list[Union[" + ", ".join(rendered) + "]]"
            return f"list[{self.py_type(contract, fragment.get('items', {}))}]"
        if schema_type == "object" or "properties" in fragment:
            return "dict[str, JsonValue]"
        return "JsonValue"


def ts_comment(text: str) -> str:
    return text.replace("*/", "* /").replace("\r", " ").replace("\n", " ")


def render_typescript(contracts: Sequence[Contract], manifest: Mapping[str, Any]) -> str:
    types = SchemaTypes(contracts)
    lines = [
        "// @generated by packages/contracts/codegen/generate.py; DO NOT EDIT.",
        "// Semantic validation remains the responsibility of the hash-bound Draft 2020-12 schemas.",
        "",
        "export type JsonValue =",
        "  | null",
        "  | boolean",
        "  | number",
        "  | string",
        "  | readonly JsonValue[]",
        "  | { readonly [key: string]: JsonValue };",
        "",
        "export interface GeneratedContractRecord {",
        '  readonly "schema_file": string;',
        '  readonly "example_file": string;',
        '  readonly "title": string;',
        '  readonly "schema_id": string;',
        '  readonly "source_sha256": `sha256:${string}`;',
        '  readonly "example_sha256": `sha256:${string}`;',
        "}",
        "",
    ]
    for contract in contracts:
        definitions = contract.schema.get("$defs", {})
        if isinstance(definitions, dict):
            for definition in sorted(definitions):
                name = types.local_name(contract, definition)
                value = types.ts_type(contract, definitions[definition])
                lines.extend((f"export type {name} = {value};", ""))

        properties = contract.schema.get("properties", {})
        required = set(contract.schema.get("required", []))
        description = contract.schema.get("description")
        if isinstance(description, str) and description:
            lines.append(f"/** {ts_comment(description)} */")
        root_name = types.root_names[Path(contract.schema_file).name]
        lines.append(f"export interface {root_name} {{")
        if isinstance(properties, dict):
            for field in sorted(properties):
                fragment = properties[field]
                field_description = fragment.get("description") if isinstance(fragment, dict) else None
                if isinstance(field_description, str) and field_description:
                    lines.append(f"  /** {ts_comment(field_description)} */")
                optional = "" if field in required else "?"
                lines.append(
                    f"  readonly {json.dumps(field, ensure_ascii=False)}{optional}: "
                    f"{types.ts_type(contract, fragment)};"
                )
        lines.extend(("}", ""))

    model_names = [types.root_names[Path(contract.schema_file).name] for contract in contracts]
    lines.extend(
        (
            f"export type CanonicalContract = {' | '.join(model_names)};",
            "",
            "export declare const contractManifest: {",
            f"  readonly schema_count: {manifest['schema_count']};",
            f"  readonly example_count: {manifest['example_count']};",
            f"  readonly schema_bundle_sha256: {json.dumps(manifest['schema_bundle_sha256'])};",
            f"  readonly example_bundle_sha256: {json.dumps(manifest['example_bundle_sha256'])};",
            "  readonly contracts: readonly GeneratedContractRecord[];",
            "};",
            "export declare const contractBySchemaFile: ReadonlyMap<string, GeneratedContractRecord>;",
            "export declare const contractByTitle: ReadonlyMap<string, GeneratedContractRecord>;",
            "",
        )
    )
    return "\n".join(lines)


def render_python_typed_dict(
    name: str,
    contract: Contract,
    fragment: Mapping[str, Any],
    types: SchemaTypes,
) -> list[str]:
    properties = fragment.get("properties", {})
    required = set(fragment.get("required", []))
    mapping: list[str] = []
    if isinstance(properties, dict):
        for field in sorted(properties):
            wrapper = "Required" if field in required else "NotRequired"
            mapping.append(
                f"        {field!r}: {wrapper}[{types.py_type(contract, properties[field])}],"
            )
    return [
        f"{name} = TypedDict(",
        f"    {name!r},",
        "    {",
        *mapping,
        "    },",
        "    total=False,",
        ")",
        "",
    ]


def render_python(contracts: Sequence[Contract], manifest: Mapping[str, Any]) -> str:
    types = SchemaTypes(contracts)
    lines = [
        '"""Generated canonical transport models.  Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import ForwardRef, Literal, NotRequired, Required, TypeAlias, TypedDict, Union",
        "",
        "JsonScalar: TypeAlias = Union[None, bool, int, float, str]",
        "JsonValue: TypeAlias = Union[JsonScalar, list[object], dict[str, object]]",
        "",
        f"CONTRACT_BUNDLE_SHA256 = {manifest['schema_bundle_sha256']!r}",
        f"EXAMPLE_BUNDLE_SHA256 = {manifest['example_bundle_sha256']!r}",
        "",
    ]
    helper_names: list[str] = []
    root_names: list[str] = []
    for contract in contracts:
        definitions = contract.schema.get("$defs", {})
        if isinstance(definitions, dict):
            for definition in sorted(definitions):
                fragment = definitions[definition]
                if isinstance(fragment, dict) and (
                    fragment.get("type") == "object" or "properties" in fragment
                ):
                    helper = types.local_name(contract, definition)
                    helper_names.append(helper)
                    lines.extend(render_python_typed_dict(helper, contract, fragment, types))
        root = types.root_names[Path(contract.schema_file).name]
        root_names.append(root)
        lines.extend(render_python_typed_dict(root, contract, contract.schema, types))

    lines.extend(
        (
            "MODEL_NAMES = (",
            *(f"    {name!r}," for name in root_names),
            ")",
            "",
            "SCHEMA_IDS = {",
            *(
                f"    {types.root_names[Path(contract.schema_file).name]!r}: {contract.schema_id!r},"
                for contract in contracts
            ),
            "}",
            "",
            "__all__ = [",
            "    'CONTRACT_BUNDLE_SHA256',",
            "    'EXAMPLE_BUNDLE_SHA256',",
            "    'MODEL_NAMES',",
            "    'SCHEMA_IDS',",
            "    *MODEL_NAMES,",
            "]",
            "",
        )
    )
    return "\n".join(lines)


def render_ui(contracts: Sequence[Contract], manifest: Mapping[str, Any]) -> str:
    ui_contracts: dict[str, Any] = {}
    for contract in contracts:
        properties = contract.schema.get("properties", {})
        required = set(contract.schema.get("required", []))
        ui_contracts[contract.title] = {
            "schemaId": contract.schema_id,
            "schemaFile": contract.schema_file,
            "sourceSha256": contract.schema_sha256,
            "requiredFields": list(contract.schema.get("required", [])),
            "fields": {
                name: {
                    "required": name in required,
                    "schema": properties[name],
                }
                for name in sorted(properties)
            }
            if isinstance(properties, dict)
            else {},
        }
    payload = json.dumps(ui_contracts, ensure_ascii=False, indent=2)
    return "\n".join(
        (
            "// @generated by packages/contracts/codegen/generate.py; DO NOT EDIT.",
            "// These UI descriptors project canonical schemas; they are not a replacement validator.",
            "",
            f"export const contractBundleSha256 = {json.dumps(manifest['schema_bundle_sha256'])} as const;",
            f"export const exampleBundleSha256 = {json.dumps(manifest['example_bundle_sha256'])} as const;",
            f"export const uiContracts = {payload} as const;",
            "",
            "export type UiContractName = keyof typeof uiContracts;",
            "export type UiContractDescriptor = (typeof uiContracts)[UiContractName];",
            "",
        )
    )


def render_registry(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    return "\n".join(
        (
            "// @generated by packages/contracts/codegen/generate.py; DO NOT EDIT.",
            f"export const contractManifest = Object.freeze({payload});",
            "export const contractBySchemaFile = new Map(",
            "  contractManifest.contracts.map((record) => [record.schema_file, record]),",
            ");",
            "export const contractByTitle = new Map(",
            "  contractManifest.contracts.map((record) => [record.title, record]),",
            ");",
            "",
        )
    )


def expected_files(root: Path) -> dict[Path, bytes]:
    contracts, schema_bundle, example_bundle = load_contracts(root)
    manifest = build_manifest(contracts, schema_bundle, example_bundle)
    manifest_bytes = json_text(manifest).encode("utf-8")
    init_text = "\n".join(
        (
            '"""Generated Epistemic Foundry contract projection."""',
            "",
            "from .models import *  # noqa: F401,F403",
            "",
        )
    )
    return {
        Path("packages/contracts/src/generated/models.d.ts"): render_typescript(
            contracts, manifest
        ).encode("utf-8"),
        Path("packages/contracts/src/generated/registry.mjs"): render_registry(manifest).encode(
            "utf-8"
        ),
        Path("packages/contracts/src/generated/contract-manifest.json"): manifest_bytes,
        Path("python/epistemic_foundry/contracts/__init__.py"): init_text.encode("utf-8"),
        Path("python/epistemic_foundry/contracts/models.py"): render_python(
            contracts, manifest
        ).encode("utf-8"),
        Path("python/epistemic_foundry/contracts/contract-manifest.json"): manifest_bytes,
        Path("python/epistemic_foundry/contracts/py.typed"): b"",
        Path("web/src/generated/contracts.ts"): render_ui(contracts, manifest).encode("utf-8"),
        Path("web/src/generated/contract-manifest.json"): manifest_bytes,
    }


def generated_inventory(root: Path) -> set[Path]:
    inventory: set[Path] = set()
    for relative_root in GENERATED_ROOTS:
        absolute_root = root / relative_root
        if not absolute_root.exists():
            continue
        for path in absolute_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                inventory.add(path.relative_to(root))
    return inventory


def write_files(root: Path, files: Mapping[Path, bytes]) -> None:
    expected = set(files)
    for extra in sorted(generated_inventory(root) - expected):
        (root / extra).unlink()
    for relative, content in sorted(files.items(), key=lambda item: item[0].as_posix()):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for relative_root in GENERATED_ROOTS:
        absolute_root = root / relative_root
        if absolute_root.exists():
            for cache in absolute_root.rglob("__pycache__"):
                if cache.is_dir():
                    shutil.rmtree(cache)


def check_files(root: Path, files: Mapping[Path, bytes]) -> list[str]:
    failures: list[str] = []
    expected = set(files)
    actual = generated_inventory(root)
    for missing in sorted(expected - actual):
        failures.append(f"missing generated file: {missing.as_posix()}")
    for extra in sorted(actual - expected):
        failures.append(f"unexpected generated file: {extra.as_posix()}")
    for relative in sorted(expected & actual):
        actual_bytes = (root / relative).read_bytes()
        if actual_bytes != files[relative]:
            failures.append(f"stale generated file: {relative.as_posix()}")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args(argv)
    root = (args.repo_root.resolve() if args.repo_root else repository_root())
    files = expected_files(root)
    if args.write:
        write_files(root, files)
        result = {
            "check": "canonical_contract_codegen",
            "status": "PASS",
            "mode": "write",
            "generated_file_count": len(files),
        }
        print(json.dumps(result, indent=2))
        return 0
    failures = check_files(root, files)
    result = {
        "check": "canonical_contract_codegen",
        "status": "FAIL" if failures else "PASS",
        "mode": "check",
        "generated_file_count": len(files),
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GenerationError as exc:
        print(json.dumps({"check": "canonical_contract_codegen", "status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
