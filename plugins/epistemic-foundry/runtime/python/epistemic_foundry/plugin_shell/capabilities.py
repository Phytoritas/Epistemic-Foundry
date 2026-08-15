"""Capability manifests, host reports, and mode negotiation.

Contract sources: `schemas/plugin-capability-manifest.schema.json` and
`schemas/host-capability-report.schema.json`.

`negotiate_mode` is the substance here. It derives the operating mode from the
gap between required capabilities and observed host capabilities:

* a missing *required* capability yields `BLOCKED`;
* a missing *optional* capability yields `DEGRADED`;
* no write capability yields `READ_ONLY`;
* everything present yields `FULL`.

The mode is computed, not declared, because a shell that reports `FULL` while a
required capability is absent is exactly the silent fallback the constitution
forbids.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Capability that must be present for any state mutation.
WRITE_CAPABILITY = "workspace_write"

#: Capability states from `host-capability-report.schema.json`. Only `SUPPORTED`
#: counts as present: `UNKNOWN` is explicitly not a yes, because negotiating as
#: if an unobserved capability worked is the silent fallback this shell forbids.
PRESENT_CAPABILITY_STATES = frozenset({"SUPPORTED"})


def _present_names(observed: Mapping[str, Any] | Sequence[str]) -> set[str]:
    """Normalize the three shapes a host report may use into a present-set.

    Accepts `{name: {"state": ...}}` (schema shape), `{name: bool}`, and a bare
    sequence of names. Anything not explicitly SUPPORTED/True is absent.
    """
    if not isinstance(observed, Mapping):
        return set(observed)
    present: set[str] = set()
    for name, value in observed.items():
        if isinstance(value, Mapping):
            if str(value.get("state")) in PRESENT_CAPABILITY_STATES:
                present.add(str(name))
        elif value is True:
            present.add(str(name))
    return present


def _capability_entries(observed: Mapping[str, Any] | Sequence[str]) -> dict[str, Any]:
    """Render observed capabilities into the schema's object-per-capability form."""
    if not isinstance(observed, Mapping):
        return {
            str(name): {"state": "SUPPORTED", "evidence": "reported present by host detection"}
            for name in observed
        }
    entries: dict[str, Any] = {}
    for name, value in observed.items():
        if isinstance(value, Mapping):
            entries[str(name)] = dict(value)
        else:
            entries[str(name)] = {
                "state": "SUPPORTED" if value is True else "UNSUPPORTED",
                "evidence": "boolean probe result from host detection",
            }
    return entries


class CapabilityNegotiationFailure(RuntimeError):
    """The host cannot support the plugin's declared contract."""


def build_capability_manifest(
    *,
    plugin_id: str,
    version: str,
    schema_version: str,
    host_surfaces: Sequence[str],
    required_capabilities: Sequence[str],
    optional_capabilities: Sequence[str],
    degraded_modes: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    skills: Sequence[str],
    hook_bundles: Sequence[str],
    mcp_servers: Sequence[str],
    cli_commands: Sequence[str],
) -> dict[str, Any]:
    """Declare what the plugin needs and what it can do without.

    A capability listed as both required and optional is refused: the contract
    would then be satisfiable and unsatisfiable at once, and negotiation could
    pick whichever reading is convenient.
    """
    overlap = sorted(set(required_capabilities) & set(optional_capabilities))
    if overlap:
        raise CapabilityNegotiationFailure(
            f"capabilit(ies) {overlap} are declared both required and optional; "
            "negotiation would be ambiguous"
        )
    if not required_capabilities:
        raise CapabilityNegotiationFailure(
            "a plugin must declare at least one required capability; a plugin that needs "
            "nothing cannot be verified against a host"
        )
    manifest: dict[str, Any] = {
        "plugin_id": plugin_id,
        "version": version,
        "schema_version": schema_version,
        "host_surfaces": list(host_surfaces),
        "required_capabilities": list(required_capabilities),
        "optional_capabilities": list(optional_capabilities),
        "degraded_modes": degraded_modes
        if isinstance(degraded_modes, Mapping)
        else [dict(item) for item in degraded_modes],
        "skills": list(skills),
        "hook_bundles": list(hook_bundles),
        "mcp_servers": list(mcp_servers),
        "cli_commands": list(cli_commands),
    }
    validate_artifact("plugin-capability-manifest", manifest)
    return manifest


def negotiate_mode(
    manifest: Mapping[str, Any],
    observed_capabilities: Mapping[str, bool] | Sequence[str],
) -> tuple[str, list[str]]:
    """Return `(mode, blockers)` derived from the capability gap.

    Accepts either a mapping of capability -> bool or a sequence of present
    capability names, because hosts report both shapes in practice.
    """
    present = _present_names(observed_capabilities)

    required = list(manifest["required_capabilities"])
    optional = list(manifest.get("optional_capabilities", []))

    missing_required = sorted(set(required) - present)
    if missing_required:
        return "BLOCKED", [f"missing required capability: {name}" for name in missing_required]

    if WRITE_CAPABILITY in required or WRITE_CAPABILITY in optional:
        if WRITE_CAPABILITY not in present:
            return "READ_ONLY", [f"{WRITE_CAPABILITY} unavailable; state mutation is disabled"]

    missing_optional = sorted(set(optional) - present)
    if missing_optional:
        return "DEGRADED", [f"missing optional capability: {name}" for name in missing_optional]

    return "FULL", []


def build_host_report(
    *,
    host: str,
    host_version: str,
    plugin_version: str,
    manifest: Mapping[str, Any],
    observed_capabilities: Mapping[str, bool] | Sequence[str],
    hook_events: Sequence[str] = (),
    unobserved_tool_paths: Sequence[str] = (),
    report_id: str | None = None,
    detected_at: str | None = None,
) -> dict[str, Any]:
    """Record a host capability report with a derived mode.

    `mode` and `blockers` come from `negotiate_mode`, so a report cannot claim
    FULL while a required capability is absent.
    """
    mode, blockers = negotiate_mode(manifest, observed_capabilities)
    capabilities = _capability_entries(observed_capabilities)
    if not capabilities:
        raise CapabilityNegotiationFailure(
            "a host report must describe at least one capability; an empty report cannot "
            "justify any operating mode"
        )

    report: dict[str, Any] = {
        "report_id": report_id or new_id("HCR"),
        "host": host,
        "host_version": host_version,
        "plugin_version": plugin_version,
        "detected_at": detected_at or utc_now_iso(),
        "capabilities": capabilities,
        "hook_events": list(hook_events),
        "unobserved_tool_paths": list(unobserved_tool_paths),
        "mode": mode,
        "blockers": blockers,
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("host-capability-report", report)
    return report


def may_mutate_state(report: Mapping[str, Any]) -> bool:
    """True only in a mode that permits writes."""
    return str(report.get("mode")) == "FULL"
