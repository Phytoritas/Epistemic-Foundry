"""Evolution backend adapter surface (T05).

The package pins and qualifies an optional external evolution backend, binds
that qualification to an S05 execution qualification, bounds imported runs on
both sides of EF4-I63, and refuses to register an executor for a command the
sealed G05 tool surface does not project.

It qualifies and gates.  It does not run ShinkaEvolve, and nothing here scores,
promotes or executes a candidate.
"""

from __future__ import annotations

from .backend_adapter import (
    COMMIT_DIGEST,
    CONTENT_DIGEST,
    EXACT_RELEASE,
    EXECUTION_FIELDS,
    QUALIFICATION_ARTIFACT,
    assert_backend_pinned,
    import_shinka_run,
    pin_backend,
    qualification_statuses,
    qualify_backend_adapter,
    require_no_imported_authority,
)
from .findings import (
    FINDING_CODES,
    AdapterGateError,
    assert_hash_rederives,
)
from .tool_surface import (
    EVOLUTION_SURFACE_PATH,
    build_executor_registry,
    command_projection,
    load_evolution_surface,
    registrable_commands,
    tool_descriptors,
)

__all__ = [
    "COMMIT_DIGEST",
    "CONTENT_DIGEST",
    "EVOLUTION_SURFACE_PATH",
    "EXACT_RELEASE",
    "EXECUTION_FIELDS",
    "FINDING_CODES",
    "QUALIFICATION_ARTIFACT",
    "AdapterGateError",
    "assert_backend_pinned",
    "assert_hash_rederives",
    "build_executor_registry",
    "command_projection",
    "import_shinka_run",
    "load_evolution_surface",
    "pin_backend",
    "qualification_statuses",
    "qualify_backend_adapter",
    "registrable_commands",
    "require_no_imported_authority",
    "tool_descriptors",
]
