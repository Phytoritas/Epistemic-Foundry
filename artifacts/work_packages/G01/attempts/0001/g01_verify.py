#!/usr/bin/env python3
"""Deterministic G01 manifest and asset-boundary verification."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any


ATTEMPT_ID = "G01-0001"
EXPECTED_NAME = "epistemic-foundry"
EXPECTED_VERSION = "4.0.0"
VERIFIER_VERSION = "g01-verifier/1.0.0"
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
COMPONENT_FIELDS = ("skills", "hooks", "mcpServers", "apps")
ASSET_FIELDS = ("composerIcon", "logo")
ALLOWED_SVG_ELEMENTS = {"svg", "rect", "path", "circle"}


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def error(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_asset_path(
    plugin_root: Path,
    raw_path: Any,
    field: str,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    errors: list[dict[str, str]] = []
    if not isinstance(raw_path, str) or not raw_path:
        return [error("ASSET_PATH_INVALID", f"{field} must be a non-empty string")], None
    if raw_path != raw_path.strip() or "\\" in raw_path:
        errors.append(error("ASSET_PATH_INVALID", f"{field} must use normalized POSIX syntax"))
    if not raw_path.startswith("./assets/"):
        errors.append(error("ASSET_PATH_PREFIX_INVALID", f"{field} must start with ./assets/"))
    if raw_path.startswith(("/", "//")) or WINDOWS_DRIVE_RE.match(raw_path):
        errors.append(error("ASSET_PATH_UNSAFE", f"{field} must not be absolute"))

    relative = raw_path[2:] if raw_path.startswith("./") else raw_path
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        errors.append(error("ASSET_PATH_UNSAFE", f"{field} contains unsafe traversal"))
    if errors:
        return errors, None

    resolved = (plugin_root / candidate.as_posix()).resolve()
    try:
        resolved.relative_to(plugin_root.resolve())
    except ValueError:
        return [error("ASSET_PATH_OUTSIDE_PLUGIN", f"{field} resolves outside plugin root")], None
    if not resolved.is_file():
        return [error("ASSET_FILE_MISSING", f"{field} references a missing file")], None
    if resolved.suffix.lower() != ".svg":
        return [error("ASSET_FORMAT_UNSUPPORTED", f"{field} must reference an SVG")], None

    raw = resolved.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [error("SVG_XML_MALFORMED", f"{field} is not well-formed XML")], None
    if local_name(root.tag) != "svg":
        errors.append(error("SVG_ROOT_INVALID", f"{field} root element must be svg"))
    view_box = root.attrib.get("viewBox", "").split()
    try:
        values = [float(value) for value in view_box]
    except ValueError:
        values = []
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        errors.append(error("SVG_DIMENSIONS_INVALID", f"{field} requires a numeric viewBox"))
        width = height = 0.0
    else:
        width, height = values[2], values[3]
        if width != height:
            errors.append(error("SVG_NOT_SQUARE", f"{field} must be square"))
        if not 48 <= width <= 4096 or not 48 <= height <= 4096:
            errors.append(error("SVG_DIMENSIONS_OUT_OF_RANGE", f"{field} must be 48..4096 square"))

    for element in root.iter():
        name = local_name(element.tag)
        if name not in ALLOWED_SVG_ELEMENTS:
            errors.append(error("SVG_ELEMENT_UNSAFE", f"{field} contains unsupported element {name}"))
        for attribute, value in element.attrib.items():
            attribute_name = local_name(attribute).lower()
            if attribute_name.startswith("on") or attribute_name in {"href", "src"}:
                errors.append(error("SVG_REFERENCE_UNSAFE", f"{field} contains active/external content"))
            if isinstance(value, str) and ("javascript:" in value.lower() or "data:" in value.lower()):
                errors.append(error("SVG_REFERENCE_UNSAFE", f"{field} contains an unsafe URI"))

    if errors:
        return errors, None
    return [], {
        "byte_size": len(raw),
        "height": int(height),
        "path": resolved.relative_to(repo_root()).as_posix(),
        "sha256": sha256_bytes(raw),
        "width": int(width),
    }


def validate_manifest(
    manifest: Any,
    plugin_root: Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    details: dict[str, Any] = {"assets": []}
    if not isinstance(manifest, dict):
        return [error("MANIFEST_ROOT_INVALID", "plugin.json root must be an object")], details

    if manifest.get("name") != EXPECTED_NAME:
        errors.append(error("PLUGIN_NAME_MISMATCH", "name must match the plugin directory"))
    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER_RE.fullmatch(version) is None:
        errors.append(error("VERSION_INVALID", "version must be strict semver"))
    elif version != EXPECTED_VERSION:
        errors.append(error("VERSION_MISMATCH", f"version must be {EXPECTED_VERSION}"))
    if not isinstance(manifest.get("description"), str) or not manifest["description"].strip():
        errors.append(error("DESCRIPTION_MISSING", "description must be non-empty"))
    author = manifest.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        errors.append(error("AUTHOR_MISSING", "author.name must be non-empty"))

    declared_components = [field for field in COMPONENT_FIELDS if field in manifest]
    details["declared_component_fields"] = declared_components
    if declared_components:
        errors.append(
            error(
                "UNGATED_COMPONENT_DECLARATION",
                "G01 must not declare skills, hooks, MCP servers, or apps before their gates pass",
            )
        )

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        return errors + [error("INTERFACE_MISSING", "interface must be an object")], details
    for field in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            errors.append(error("INTERFACE_FIELD_MISSING", f"interface.{field} must be non-empty"))
    capabilities = interface.get("capabilities")
    details["capabilities"] = capabilities
    if capabilities != []:
        errors.append(
            error(
                "CAPABILITY_OVERCLAIM",
                "G01 package identity exposes no runtime capability before downstream gates pass",
            )
        )
    prompts = interface.get("defaultPrompt")
    if (
        not isinstance(prompts, list)
        or not 1 <= len(prompts) <= 3
        or not all(isinstance(prompt, str) and 0 < len(prompt) <= 128 for prompt in prompts)
    ):
        errors.append(error("DEFAULT_PROMPT_INVALID", "defaultPrompt must contain 1..3 bounded strings"))
    if not isinstance(interface.get("brandColor"), str) or HEX_COLOR_RE.fullmatch(interface["brandColor"]) is None:
        errors.append(error("BRAND_COLOR_INVALID", "brandColor must be #RRGGBB"))

    asset_paths: list[str] = []
    for field in ASSET_FIELDS:
        asset_errors, asset = validate_asset_path(plugin_root, interface.get(field), f"interface.{field}")
        errors.extend(asset_errors)
        if asset is not None:
            details["assets"].append(asset)
            asset_paths.append(str(interface[field]))
    if len(asset_paths) != len(set(asset_paths)):
        errors.append(error("ASSET_PATH_DUPLICATE", "composerIcon and logo must be distinct assets"))
    return errors, details


def negative_cases(manifest: dict[str, Any], plugin_root: Path) -> list[dict[str, Any]]:
    cases: list[tuple[str, dict[str, Any], str]] = []

    traversal = deepcopy(manifest)
    traversal["interface"]["logo"] = "./assets/../outside.svg"
    cases.append(("parent_traversal", traversal, "ASSET_PATH_UNSAFE"))

    absolute = deepcopy(manifest)
    absolute["interface"]["logo"] = "C:/outside.svg"
    cases.append(("windows_absolute_path", absolute, "ASSET_PATH_UNSAFE"))

    missing = deepcopy(manifest)
    missing["interface"]["logo"] = "./assets/missing.svg"
    cases.append(("missing_asset", missing, "ASSET_FILE_MISSING"))

    components = deepcopy(manifest)
    components["skills"] = "./skills/"
    cases.append(("ungated_component", components, "UNGATED_COMPONENT_DECLARATION"))

    capabilities = deepcopy(manifest)
    capabilities["interface"]["capabilities"] = ["Skills"]
    cases.append(("capability_overclaim", capabilities, "CAPABILITY_OVERCLAIM"))

    version = deepcopy(manifest)
    version["version"] = "4.0.1"
    cases.append(("version_drift", version, "VERSION_MISMATCH"))

    active_svg = deepcopy(manifest)
    active_svg["interface"]["logo"] = "./assets/active.svg"
    cases.append(("missing_active_svg_fixture", active_svg, "ASSET_FILE_MISSING"))

    results: list[dict[str, Any]] = []
    for case_id, payload, expected_code in cases:
        found_errors, _ = validate_manifest(payload, plugin_root)
        observed_codes = sorted({entry["code"] for entry in found_errors})
        results.append(
            {
                "case_id": case_id,
                "expected_code": expected_code,
                "observed_codes": observed_codes,
                "status": "PASS" if expected_code in observed_codes else "FAIL",
            }
        )
    return results


def main() -> int:
    root = repo_root()
    plugin_root = root / "plugins" / EXPECTED_NAME
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    output_path = Path(__file__).with_name("g01-verification.json")
    parse_errors: list[dict[str, str]] = []
    try:
        raw_manifest = manifest_path.read_bytes()
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raw_manifest = b""
        manifest = None
        parse_errors.append(error("MANIFEST_UNREADABLE", str(exc)))

    manifest_errors, details = validate_manifest(manifest, plugin_root)
    cases = negative_cases(manifest, plugin_root) if isinstance(manifest, dict) else []
    negative_failures = [case for case in cases if case["status"] != "PASS"]
    inventory = []
    if plugin_root.is_dir():
        for path in sorted((entry for entry in plugin_root.rglob("*") if entry.is_file()), key=lambda item: item.as_posix()):
            data = path.read_bytes()
            inventory.append(
                {
                    "byte_size": len(data),
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_bytes(data),
                }
            )

    all_errors = parse_errors + manifest_errors
    status = "PASS" if not all_errors and not negative_failures else "FAIL"
    result = {
        "attempt_id": ATTEMPT_ID,
        "checks": {
            "asset_path_test": {
                "negative_case_count": len(cases),
                "negative_case_pass_count": len(cases) - len(negative_failures),
                "status": "PASS" if not negative_failures and not manifest_errors else "FAIL",
            },
            "plugin_manifest_validation": {
                "error_count": len(all_errors),
                "status": "PASS" if not all_errors else "FAIL",
            },
        },
        "errors": all_errors,
        "manifest": {
            "capabilities": details.get("capabilities"),
            "declared_component_fields": details.get("declared_component_fields", []),
            "name": manifest.get("name") if isinstance(manifest, dict) else None,
            "path": manifest_path.relative_to(root).as_posix(),
            "sha256": sha256_bytes(raw_manifest) if raw_manifest else None,
            "version": manifest.get("version") if isinstance(manifest, dict) else None,
        },
        "negative_cases": cases,
        "package_inventory": inventory,
        "resolved_assets": details.get("assets", []),
        "source_contracts": [
            "MASTER_SPEC.md#G01",
            "manifests/development_manifest.yaml#G01",
            "Codex Manual: Package your plugin / Plugin structure / Path rules",
        ],
        "status": status,
        "verifier_version": VERIFIER_VERSION,
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
