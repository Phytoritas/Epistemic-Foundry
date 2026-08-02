"""provider_parity_eval — both adapters resolve the same canonical roles.

Required check: ``provider_parity_eval``.  The Codex adapter (X01) and the
Claude Code adapter (X02) are measured against the canonical role registry.  The
committed surfaces are evaluated as they stand; the role vocabulary is read from
the registry rather than restated here; and a role dropped, a canonical output
schema rebound, a host descriptor the registry does not name, or worktree
isolation that stops tracking a registry write scope is each refused with its own
typed finding.  The refusal cases mutate an in-memory copy of the loaded maps, so
the sealed adapter files on disk are never touched.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from provider_parity_harness import (
    CLAUDE_ADAPTER_RELATIVE_PATH,
    CODEX_ADAPTER_RELATIVE_PATH,
    ProviderParityError,
    evaluate_parity,
    load_adapter_roles,
    load_registry,
    parity_from,
    parity_surface,
)

ROOT = Path(__file__).resolve().parents[2]


def maps() -> tuple[dict, dict, dict]:
    return (
        copy.deepcopy(load_registry(ROOT)),
        copy.deepcopy(load_adapter_roles(ROOT, CODEX_ADAPTER_RELATIVE_PATH)),
        copy.deepcopy(load_adapter_roles(ROOT, CLAUDE_ADAPTER_RELATIVE_PATH)),
    )


def refused(registry: dict, codex: dict, claude: dict, code: str) -> ProviderParityError:
    with pytest.raises(ProviderParityError) as caught:
        parity_from(registry, codex, claude)
    assert caught.value.code == code, caught.value.code
    return caught.value


def test_both_adapters_are_in_parity_over_the_committed_surfaces() -> None:
    report = evaluate_parity(ROOT)

    assert report["status"] == "PASS"
    assert report["role_count"] == 28
    assert report["checks"] == {
        "claude_surface_aligned": 28,
        "codex_agent_type_aligned": 28,
        "isolation_aligned": 28,
        "result_schema_aligned": 28,
        "role_set_aligned": True,
    }


def test_the_parity_surface_is_exactly_the_canonical_role_set() -> None:
    registry_ids = set(load_registry(ROOT))

    assert set(parity_surface(ROOT)) == registry_ids
    assert len(registry_ids) == 28


def test_every_role_carries_the_registry_output_schema_on_both_adapters() -> None:
    registry = load_registry(ROOT)
    report = evaluate_parity(ROOT)

    for role in report["roles"]:
        assert role["output_schema_ref"] == registry[role["role_id"]]["output_schema_ref"]


def test_a_role_dropped_by_one_adapter_is_refused() -> None:
    registry, codex, claude = maps()
    victim = sorted(codex)[0]
    del codex[victim]

    error = refused(registry, codex, claude, "ROLE_SET_DIVERGENCE")

    assert error.context["adapter"] == "codex"
    assert victim in error.context["dropped"]


def test_a_rebound_canonical_output_schema_is_refused() -> None:
    registry, codex, claude = maps()
    victim = sorted(claude)[0]
    claude[victim]["result_schema"] = "schemas/some-other-contract.schema.json"

    error = refused(registry, codex, claude, "RESULT_SCHEMA_DIVERGENCE")

    assert error.context["adapter"] == "claude-code"
    assert error.context["role_id"] == victim


def test_a_codex_host_agent_type_the_registry_does_not_name_is_refused() -> None:
    registry, codex, claude = maps()
    victim = sorted(codex)[0]
    codex[victim]["agent_type"] = "orchestrator"

    error = refused(registry, codex, claude, "CODEX_AGENT_TYPE_DIVERGENCE")

    assert error.context["role_id"] == victim
    assert error.context["found"] == "orchestrator"


def test_a_non_uniform_claude_surface_is_refused() -> None:
    registry, codex, claude = maps()
    victim = sorted(claude)[0]
    claude[victim]["surface"] = "builtin_agent"

    error = refused(registry, codex, claude, "CLAUDE_SURFACE_DIVERGENCE")

    assert error.context["role_id"] == victim


def test_isolation_that_stops_tracking_a_write_scope_is_refused() -> None:
    registry, codex, claude = maps()
    # A write-capable role demoted to a shared, non-isolated surface.
    writable = next(
        role_id
        for role_id, record in registry.items()
        if record.get("write_scope")
    )
    claude[writable]["isolation"] = "shared"

    error = refused(registry, codex, claude, "ISOLATION_DIVERGENCE")

    assert error.context["role_id"] == writable
    assert error.context["writable"] is True
