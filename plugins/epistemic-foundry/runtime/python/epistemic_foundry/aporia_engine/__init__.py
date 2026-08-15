"""Aporia Engine: hidden assumptions and unresolved objections stay visible.

`AGENTS.md`: an Insight requires scope, prediction, falsifier, and searched-scope
accounting; `UNDERDETERMINED` is a valid truthful outcome. The Aporia Engine is
where a reasoning chain admits what it does not know.

The rule enforced here is that an argument graph cannot be reported as resolved
while objections remain open. Quietly closing an objection to produce a clean
conclusion is the failure this component prevents.
"""

from __future__ import annotations

from .argument import (
    AporiaViolation,
    build_argument_graph,
    is_resolved,
    reasoning_mode_separation_holds,
)

__all__ = [
    "AporiaViolation",
    "build_argument_graph",
    "is_resolved",
    "reasoning_mode_separation_holds",
]
