"""Plugin Shell: host capability negotiation and honest degraded modes.

`AGENTS.md`: plugin shells, hooks, skills, UIs, model SDKs, and optional search
backends are adapters. The shell negotiates what the host can actually do and
reports the resulting mode truthfully — a missing capability produces `DEGRADED`
or `BLOCKED`, never a silent fallback that looks like full operation.
"""

from __future__ import annotations

from .alpha_evolve import AlphaInvocationError, alpha_check
from .capabilities import (
    CapabilityNegotiationFailure,
    build_capability_manifest,
    build_host_report,
    negotiate_mode,
)

__all__ = [
    "AlphaInvocationError",
    "CapabilityNegotiationFailure",
    "alpha_check",
    "build_capability_manifest",
    "build_host_report",
    "negotiate_mode",
]
