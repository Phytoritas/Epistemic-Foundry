"""A missing capability degrades or blocks; it never silently falls back."""

from __future__ import annotations

import json

import pytest

from epistemic_foundry.contracts import repo_root
from epistemic_foundry.plugin_shell import (
    CapabilityNegotiationFailure,
    build_capability_manifest,
    build_host_report,
    negotiate_mode,
)
from epistemic_foundry.plugin_shell.capabilities import WRITE_CAPABILITY, may_mutate_state


def _manifest(**overrides) -> dict:
    sample = json.loads(
        (repo_root() / "examples" / "sample_plugin-capability-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    kwargs = dict(
        plugin_id=sample["plugin_id"],
        version=sample["version"],
        schema_version=sample["schema_version"],
        host_surfaces=sample["host_surfaces"],
        required_capabilities=sample["required_capabilities"],
        optional_capabilities=sample["optional_capabilities"],
        degraded_modes=sample["degraded_modes"],
        skills=sample["skills"],
        hook_bundles=sample["hook_bundles"],
        mcp_servers=sample["mcp_servers"],
        cli_commands=sample["cli_commands"],
    )
    kwargs.update(overrides)
    return build_capability_manifest(**kwargs)


ALL_CAPS = ["local_state", "artifact_hashing", "plugin_hooks", "mcp", "worktrees"]


# -- manifest -----------------------------------------------------------


def test_shipped_manifest_shape_validates() -> None:
    manifest = _manifest()
    assert manifest["plugin_id"] == "epistemic-foundry"


def test_capability_declared_both_required_and_optional_is_refused() -> None:
    """Negotiation must not be able to pick the convenient reading."""
    with pytest.raises(CapabilityNegotiationFailure) as excinfo:
        _manifest(required_capabilities=["local_state"], optional_capabilities=["local_state"])
    assert "both required and optional" in str(excinfo.value)


def test_manifest_without_required_capabilities_is_refused() -> None:
    with pytest.raises(CapabilityNegotiationFailure):
        _manifest(required_capabilities=[])


# -- negotiation --------------------------------------------------------


def test_all_capabilities_present_is_full() -> None:
    mode, blockers = negotiate_mode(_manifest(), ALL_CAPS)
    assert mode == "FULL"
    assert blockers == []


def test_missing_required_capability_blocks() -> None:
    """A shell must not report FULL while a requirement is absent."""
    mode, blockers = negotiate_mode(_manifest(), ["artifact_hashing", "plugin_hooks", "mcp", "worktrees"])
    assert mode == "BLOCKED"
    assert any("local_state" in reason for reason in blockers)


def test_missing_optional_capability_degrades() -> None:
    mode, blockers = negotiate_mode(_manifest(), ["local_state", "artifact_hashing", "mcp", "worktrees"])
    assert mode == "DEGRADED"
    assert any("plugin_hooks" in reason for reason in blockers)


def test_absent_write_capability_yields_read_only() -> None:
    manifest = _manifest(
        required_capabilities=["local_state"],
        optional_capabilities=[WRITE_CAPABILITY],
    )
    mode, blockers = negotiate_mode(manifest, ["local_state"])
    assert mode == "READ_ONLY"
    assert any("state mutation is disabled" in reason for reason in blockers)


def test_blocked_outranks_degraded() -> None:
    """A missing requirement is not softened by other gaps."""
    mode, _ = negotiate_mode(_manifest(), [])
    assert mode == "BLOCKED"


def test_mapping_form_of_observed_capabilities_is_accepted() -> None:
    observed = {name: True for name in ALL_CAPS}
    observed["plugin_hooks"] = False
    mode, _ = negotiate_mode(_manifest(), observed)
    assert mode == "DEGRADED"


def test_schema_shaped_capability_states_are_accepted() -> None:
    """Hosts report `{name: {state, evidence}}`; that shape must negotiate too."""
    observed = {
        name: {"state": "SUPPORTED", "evidence": "probed"} for name in ALL_CAPS
    }
    mode, _ = negotiate_mode(_manifest(), observed)
    assert mode == "FULL"


def test_unknown_capability_state_is_not_treated_as_present() -> None:
    """UNKNOWN is not a yes; negotiating as if it worked is a silent fallback."""
    observed = {name: {"state": "SUPPORTED", "evidence": "probed"} for name in ALL_CAPS}
    observed["local_state"] = {"state": "UNKNOWN", "evidence": "probe timed out"}
    mode, blockers = negotiate_mode(_manifest(), observed)
    assert mode == "BLOCKED"
    assert any("local_state" in reason for reason in blockers)


def test_disabled_capability_is_absent() -> None:
    observed = {name: {"state": "SUPPORTED", "evidence": "probed"} for name in ALL_CAPS}
    observed["plugin_hooks"] = {"state": "DISABLED", "evidence": "hooks turned off by policy"}
    mode, _ = negotiate_mode(_manifest(), observed)
    assert mode == "DEGRADED"


def test_empty_host_report_is_refused() -> None:
    with pytest.raises(CapabilityNegotiationFailure):
        build_host_report(
            host="other",
            host_version="0",
            plugin_version="4.0.0",
            manifest=_manifest(),
            observed_capabilities={},
        )


# -- host report --------------------------------------------------------


def test_report_mode_is_derived_not_declared() -> None:
    import inspect

    params = inspect.signature(build_host_report).parameters
    assert "mode" not in params
    assert "blockers" not in params


def test_report_records_the_negotiated_mode() -> None:
    report = build_host_report(
        host="codex_cli",
        host_version="0.145.0",
        plugin_version="4.0.0",
        manifest=_manifest(),
        observed_capabilities=ALL_CAPS,
    )
    assert report["mode"] == "FULL"
    assert report["blockers"] == []
    assert may_mutate_state(report) is True


def test_blocked_report_does_not_permit_mutation() -> None:
    report = build_host_report(
        host="codex_cli",
        host_version="0.145.0",
        plugin_version="4.0.0",
        manifest=_manifest(),
        observed_capabilities=["artifact_hashing"],
    )
    assert report["mode"] == "BLOCKED"
    assert may_mutate_state(report) is False


def test_degraded_report_does_not_permit_mutation() -> None:
    report = build_host_report(
        host="claude_code",
        host_version="2.1.218",
        plugin_version="4.0.0",
        manifest=_manifest(),
        observed_capabilities=["local_state", "artifact_hashing"],
    )
    assert report["mode"] == "DEGRADED"
    assert may_mutate_state(report) is False
