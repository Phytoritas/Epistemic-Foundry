"""PURE_READ tool handlers: honest read-model projection, zero side effects.

A read handler consults one injected :class:`ReadModelPort` and reports the
provider's read-model state without improvement: a backend failure becomes
``UNAVAILABLE`` and can never be rendered as ``EMPTY_CONFIRMED`` (EF4-I23).
Concealing tools answer failed authorization scoping with the same
``NOT_FOUND`` as a genuinely absent resource.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..mcp_common.contracts import (
    AuthContext,
    McpContractError,
    ReadModelPort,
    ReadOutcome,
    ToolCatalog,
    ToolSpec,
    result_envelope,
)


class ReadToolHandler:
    """Uniform PURE_READ execution over one injected read-model provider."""

    def __init__(self, port: ReadModelPort) -> None:
        self._port = port

    def execute(
        self,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        auth: AuthContext,
        *,
        request_id: str,
        generated_at: str,
    ) -> dict[str, Any]:
        workspace_id = str(arguments["workspace_id"])
        try:
            outcome = self._port.fetch(spec.handler_operation, workspace_id, arguments)
        except McpContractError:
            raise
        except Exception as error:  # noqa: BLE001 - provider failure is a typed state
            return result_envelope(
                spec,
                request_id=request_id,
                workspace_id=workspace_id,
                read_model_state="UNAVAILABLE",
                data=None,
                degradation_reason=f"read-model provider failure: {type(error).__name__}",
                generated_at=generated_at,
            )
        if not isinstance(outcome, ReadOutcome):
            raise McpContractError(
                "INTERNAL", "read-model provider returned a non-canonical outcome"
            )
        if spec.confidentiality_concealment and not outcome.found:
            raise McpContractError(
                "NOT_FOUND",
                "the resource does not exist in the authorized scope",
            )
        if outcome.state == "EMPTY_CONFIRMED" and outcome.reason is not None:
            raise McpContractError(
                "INTERNAL",
                "EMPTY_CONFIRMED cannot carry a degradation reason",
            )
        if outcome.state == "READY" and outcome.data is None:
            raise McpContractError("INTERNAL", "READY requires a data payload")
        if outcome.state in {"EMPTY_CONFIRMED"} and outcome.data is not None:
            raise McpContractError(
                "INTERNAL", "EMPTY_CONFIRMED cannot carry a data payload"
            )
        return result_envelope(
            spec,
            request_id=request_id,
            workspace_id=workspace_id,
            read_model_state=outcome.state,
            data=outcome.data,
            degradation_reason=outcome.reason,
            generated_at=generated_at,
        )


def build_read_registry(
    catalog: ToolCatalog, port: ReadModelPort
) -> dict[str, ReadToolHandler]:
    """One handler per PURE_READ catalog row; the catalog is the only source."""

    handler = ReadToolHandler(port)
    return {
        name: handler
        for name, spec in catalog.tools.items()
        if spec.side_effect_class == "PURE_READ"
    }
