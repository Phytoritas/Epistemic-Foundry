"""DURABLE_PLAN_ARTIFACT tool handlers: receipt-bound, non-executing plans.

A planning handler delegates compilation to the domain-owned
:class:`PlanCompilerPort`, validates the compiled artifact against the exact
canonical schema bound in the tool catalog, and stores it through the
append-only :class:`PlanArtifactStorePort` under the caller's idempotency key.
Planning never executes retrieval, deliberation, or validation and never
mutates canonical scientific state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...contracts.validation import artifact_errors
from ..mcp_common.contracts import (
    AuthContext,
    IdempotencyConflict,
    McpContractError,
    PlanArtifactStorePort,
    PlanCompilerPort,
    PlanRejected,
    ToolCatalog,
    ToolSpec,
    canonical_json_bytes,
    canonical_schema_name,
    plan_artifact_registry,
    result_envelope,
    sha256_id,
)


class PlanningToolHandler:
    """Uniform DURABLE_PLAN_ARTIFACT execution over injected domain ports."""

    def __init__(
        self,
        compiler: PlanCompilerPort,
        store: PlanArtifactStorePort,
    ) -> None:
        self._compiler = compiler
        self._store = store
        self._registry = plan_artifact_registry()

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
        idempotency_key = str(arguments["idempotency_key"])
        try:
            artifact = self._compiler.compile(
                spec.handler_operation, workspace_id, arguments
            )
        except PlanRejected as rejection:
            raise McpContractError(
                "PLAN_COMPILATION_REJECTED", str(rejection), rejection.details
            ) from rejection
        if not isinstance(artifact, Mapping):
            raise McpContractError(
                "INTERNAL", "plan compiler returned a non-object artifact"
            )
        schema_name = canonical_schema_name(spec.data_schema_refs[0])
        errors = artifact_errors(schema_name, dict(artifact), registry=self._registry)
        if errors:
            raise McpContractError(
                "PLAN_COMPILATION_REJECTED",
                f"compiled artifact violates canonical schema {schema_name}",
                {"schema_errors": errors},
            )
        content = canonical_json_bytes(dict(artifact))
        fingerprint = sha256_id(
            canonical_json_bytes(
                {
                    "tool": spec.name,
                    "workspace_id": workspace_id,
                    "arguments": {
                        key: value
                        for key, value in arguments.items()
                        if key != "idempotency_key"
                    },
                }
            )
        )
        try:
            stored = self._store.put(
                workspace_id=workspace_id,
                kind=schema_name,
                content=content,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except IdempotencyConflict as conflict:
            raise McpContractError(
                "IDEMPOTENCY_CONFLICT",
                "idempotency key reuse with a different canonical request",
            ) from conflict
        if stored.sha256 != sha256_id(content):
            raise McpContractError(
                "INTERNAL", "artifact store receipt does not address the stored bytes"
            )
        return result_envelope(
            spec,
            request_id=request_id,
            workspace_id=workspace_id,
            read_model_state="READY",
            data=dict(artifact),
            receipts=[
                {
                    "artifact_id": stored.artifact_id,
                    "receipt_id": stored.receipt_id,
                    "sha256": stored.sha256,
                }
            ],
            generated_at=generated_at,
        )


def build_planning_registry(
    catalog: ToolCatalog,
    compiler: PlanCompilerPort,
    store: PlanArtifactStorePort,
) -> dict[str, PlanningToolHandler]:
    """One handler per DURABLE_PLAN_ARTIFACT row; the catalog is the source."""

    handler = PlanningToolHandler(compiler, store)
    return {
        name: handler
        for name, spec in catalog.tools.items()
        if spec.side_effect_class == "DURABLE_PLAN_ARTIFACT"
    }
