"""Honest degraded UI and operator usability integration gate (U06).

This package composes the sealed U05 Evolution Chamber console projection into
an operator dashboard that is *honest about what it cannot show*.  Each panel
resolves to one of the four canonical honest-UI states (EF4-I23) — ``POPULATED``,
``EMPTY_CONFIRMED``, ``DEGRADED`` or ``UNAVAILABLE`` — read from the module that
owns that vocabulary, never named here (EF4-I22).  A surface that U05 refuses, or
that was not supplied, becomes an ``UNAVAILABLE`` panel carrying the reason it
cannot be trusted; it is never fabricated into a healthy panel and never silently
defaulted into a confirmed emptiness.  The composed dashboard confers no
evaluator, holdout or promotion authority on anyone, refuses any authority
request, and never overstates completeness: a screen is ``complete`` only when
every requested surface is populated, and that verdict is independently
recomputable from the panels the dashboard embeds.
"""

from __future__ import annotations

from .usability_gate import (
    DASHBOARD_ID_PREFIX,
    DEFAULT_REQUESTING_ROLE,
    FINDING_CODES,
    PANEL_ID_PREFIX,
    ConsoleProjectionRefused,
    ResultState,
    UsabilityGateError,
    audit_dashboard_completeness,
    build_console_projection,
    build_operator_panel,
    compose_operator_dashboard,
    declared_panel_surfaces,
    declared_surfaces,
    require_dashboard_identity,
    require_panel_identity,
    require_view_identity,
)

__all__ = [
    "DASHBOARD_ID_PREFIX",
    "DEFAULT_REQUESTING_ROLE",
    "FINDING_CODES",
    "PANEL_ID_PREFIX",
    "ConsoleProjectionRefused",
    "ResultState",
    "UsabilityGateError",
    "audit_dashboard_completeness",
    "build_console_projection",
    "build_operator_panel",
    "compose_operator_dashboard",
    "declared_panel_surfaces",
    "declared_surfaces",
    "require_dashboard_identity",
    "require_panel_identity",
    "require_view_identity",
]
