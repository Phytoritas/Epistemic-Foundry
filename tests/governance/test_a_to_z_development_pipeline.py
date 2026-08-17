"""Cross-authority regression coverage for the A-to-Z development pipeline.

The repository already owns one structural implementation-graph validator in
``tools/validate_spec_bundle.py``.  These tests deliberately reuse that owner
instead of creating a second graph implementation, and make the existing
validator part of the ordinary pytest/PR path.

The final test protects a different boundary: bytes included in the installed
payload are not equivalent to an installed handler being reachable.  The
packaged tool catalog must therefore stay on the read-only T01 profile until
the installed MCP composition binds both the canonical write adapter and the
full Forge runtime.
"""

from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "tools" / "validate_spec_bundle.py"
MASTER_SPEC_PATH = ROOT / "MASTER_SPEC.md"
DEVELOPMENT_PATH = ROOT / "manifests" / "development_manifest.yaml"
ACCEPTANCE_PATH = ROOT / "manifests" / "acceptance_matrix.yaml"
INSTALLED_MCP_PATH = (
    ROOT / "plugins" / "epistemic-foundry" / "src" / "mcp-server.mjs"
)
PLUGIN_BUILD_PATH = (
    ROOT / "plugins" / "epistemic-foundry" / "scripts" / "build.mjs"
)

MASTER_INVENTORY_RE = re.compile(r"(?m)^- \*\*([A-Z]\d{2}) — ")
MASTER_TOTAL_RE = re.compile(r"Total: \*\*(\d+) work packages\*\*")
ACTIVE_DESCRIPTOR_RE = re.compile(
    r'const descriptorSource = requiredExpectedFile\(\s*'
    r'closedPluginHostFiles,\s*"([^"]+)"',
    re.MULTILINE,
)


def _load_yaml(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path} must contain a YAML object"
    return document


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "ef_a_to_z_validate_spec_bundle",
        VALIDATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _a_to_z_master_section() -> str:
    text = MASTER_SPEC_PATH.read_text(encoding="utf-8")
    marker = "# Part XIII — A–Z implementation graph"
    next_marker = "# Part XIV — Data and contract inventory"
    assert marker in text and next_marker in text
    return text.split(marker, 1)[1].split(next_marker, 1)[0]


def test_canonical_a_to_z_graph_validator_runs_inside_pytest() -> None:
    """CI must execute the existing graph validator, not merely ship it."""

    validator = _load_validator()
    errors: list[str] = []
    validator.EXPECTED.clear()
    validator.EXPECTED.update(validator.load_expected_counts(ROOT, errors))

    report: dict = {}
    work_package_ids = validator.validate_development(ROOT, errors, report)

    assert errors == [], "\n".join(errors)
    assert report["development"]["work_packages"] == len(work_package_ids)
    assert (
        report["development"]["work_packages"]
        == validator.EXPECTED["work_packages"]
    )


def test_master_spec_manifest_and_acceptance_inventory_stay_synchronized() -> None:
    """The three authorities must describe one A-to-Z package inventory."""

    development = _load_yaml(DEVELOPMENT_PATH)
    acceptance = _load_yaml(ACCEPTANCE_PATH)
    work_packages = development.get("work_packages")
    assert isinstance(work_packages, list) and work_packages

    manifest_ids = [item.get("id") for item in work_packages]
    assert all(isinstance(item, str) for item in manifest_ids)
    assert len(manifest_ids) == len(set(manifest_ids))

    master_section = _a_to_z_master_section()
    master_ids = MASTER_INVENTORY_RE.findall(master_section)
    assert Counter(master_ids) == Counter(manifest_ids)

    total_matches = MASTER_TOTAL_RE.findall(master_section)
    assert total_matches == [str(len(manifest_ids))]

    spec_bundle_gates = acceptance["release_levels"]["SPEC_BUNDLE"]["gates"]
    assert int(str(spec_bundle_gates["work_package_count"])) == len(manifest_ids)
    assert int(
        str(spec_bundle_gates["work_package_cycle_or_missing_dependency_errors"])
    ) == 0

    declared_work_package_gates = acceptance.get("work_package_gates", {})
    assert isinstance(declared_work_package_gates, dict)
    assert set(declared_work_package_gates) <= set(manifest_ids)


def test_installed_catalog_activation_tracks_canonical_write_reachability() -> None:
    """Packaging T02 bytes must not publish them before handlers are reachable."""

    mcp_source = INSTALLED_MCP_PATH.read_text(encoding="utf-8")
    build_source = PLUGIN_BUILD_PATH.read_text(encoding="utf-8")

    write_adapter_active = "./plugin-host/mcp/write/adapter.mjs" in mcp_source
    write_runtime_active = bool(
        re.search(r"\bopenPluginForgeRuntime\b", mcp_source)
    )
    assert write_adapter_active == write_runtime_active, (
        "installed write framing and the full Forge runtime must become "
        "reachable in the same composition change"
    )

    descriptor_match = ACTIVE_DESCRIPTOR_RE.search(build_source)
    assert descriptor_match is not None
    active_descriptor_source = descriptor_match.group(1)
    read_catalog_active = (
        active_descriptor_source == "mcp/generated/tool-descriptors.json"
    )

    if write_adapter_active:
        assert not read_catalog_active, (
            "the installed MCP write adapter is reachable but the packaged "
            "CLI catalog is still pinned to the T01-only descriptors"
        )
    else:
        assert read_catalog_active, (
            "the packaged catalog must stay on T01 until the installed MCP "
            "composition binds the canonical write adapter and Forge runtime"
        )
        assert "openPluginForgeReadRuntime" in mcp_source

    # T02 bytes may be package-reachable before activation.  Their mere
    # presence is not evidence that a canonical handler is callable.
    assert '"mcp/write/adapter.mjs"' in build_source
    assert '"mcp/write/catalog-set.mjs"' in build_source
    assert '"mcp/write/generated/t02-tool-descriptors.json"' in build_source
