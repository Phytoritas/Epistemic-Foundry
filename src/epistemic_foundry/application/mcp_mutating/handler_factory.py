"""Compound T02 mutation-runtime handler and exact-nine registry factory."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..mcp_common.contracts import (
    AuthContext,
    ToolSpec,
    canonical_json_bytes,
    result_envelope,
)
from .ports import (
    MutationRuntimePort,
    MutationRuntimeRequest,
    MutationRuntimeUnavailable,
)
from .service import MutatingToolCatalog, MutatingToolSpec, semantic_fingerprint


def _json_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a canonical JSON object from a caller- or runtime-owned mapping."""

    snapshot: dict[str, Any] = json.loads(canonical_json_bytes(dict(value)))
    return snapshot


class MutationHandler:
    """Delegate one validated mutation to the injected compound runtime."""

    def __init__(
        self,
        catalog: MutatingToolCatalog,
        *,
        runtime: MutationRuntimePort,
    ) -> None:
        self._catalog = catalog
        self._runtime = runtime

    def execute(
        self,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        auth: AuthContext,
        *,
        request_id: str,
        generated_at: str,
    ) -> dict[str, Any]:
        mutating: MutatingToolSpec = self._catalog.spec(spec.name)
        workspace_id = str(arguments["workspace_id"])
        validated_arguments = _json_snapshot(arguments)
        request = MutationRuntimeRequest(
            tool_name=mutating.name,
            handler_operation=mutating.handler_operation,
            capability=mutating.capability,
            risk_class=mutating.risk_class,
            approval_class=mutating.approval_class,
            expected_revision_required=mutating.expected_revision_required,
            validated_arguments=validated_arguments,
            auth=auth,
            semantic_fingerprint=semantic_fingerprint(
                tool=mutating.name,
                auth=auth,
                arguments=validated_arguments,
            ),
            request_id=request_id,
            generated_at=generated_at,
        )

        try:
            runtime_payload = self._runtime.execute(request)
        except MutationRuntimeUnavailable as error:
            return result_envelope(
                spec,
                request_id=request_id,
                workspace_id=workspace_id,
                read_model_state="UNAVAILABLE",
                data=None,
                receipts=(),
                degradation_reason=error.reason,
                generated_at=generated_at,
            )

        payload = _json_snapshot(runtime_payload)
        self._catalog.validate_result_payload(payload)
        effect_status = str(payload["mutation"]["effect_status"])
        succeeded = effect_status == "SUCCEEDED"
        return result_envelope(
            spec,
            request_id=request_id,
            workspace_id=workspace_id,
            read_model_state="READY" if succeeded else "DEGRADED",
            data=payload,
            receipts=(),
            degradation_reason=None if succeeded else f"effect status {effect_status}",
            generated_at=generated_at,
        )


def build_mutating_registry(
    catalog: MutatingToolCatalog,
    handler: MutationHandler,
) -> dict[str, MutationHandler]:
    """One handler per catalog row; the verified catalog contains exactly nine."""

    return {name: handler for name in catalog.tool_names}
