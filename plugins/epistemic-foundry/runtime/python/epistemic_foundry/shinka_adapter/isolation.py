"""External backend authority isolation (EF4-I63).

Contract sources: `schemas/shinka-backend-manifest.schema.json`,
`schemas/backend-adapter-qualification.schema.json` and
`schemas/imported-run-record.schema.json`.

"ShinkaEvolve and other search engines are optional pinned adapters; their
scores, archives, novelty and state never become Foundry authority."

`backend.py` already refuses an unpinned or unqualified backend and classifies
every signal as advisory. This module adds the two boundary properties that
refusal alone does not give:

* *Optionality is demonstrable.* `foundry_runs_without_backend` returns True
  unconditionally, and `require_optional` refuses a RunSpec that names the
  backend as required. A backend the Foundry cannot run without is not an
  adapter; it is a dependency that has acquired authority by being load-bearing.
* *Import is a translation, not an adoption.* Backend state enters through
  `import_backend_state`, which records what could not be converted and never
  manufactures receipts for effects the Foundry did not observe. The alternative,
  filling gaps with plausible values, produces a run history that reads as
  Foundry-verified while resting on another engine's bookkeeping.

The asymmetry is intentional: a backend may say where to look next, and may not
say what is true.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.status import ForgePhase
from ..domain.time import utc_now_iso
from .backend import ADVISORY_BACKEND_SIGNALS

#: Foundry surfaces a backend signal may never write to. Each is an authority the
#: constitution assigns to the kernel or to a deterministic gate.
FOUNDRY_AUTHORITY_SURFACES: tuple[str, ...] = (
    "promotion_decision",
    "gate_decision",
    "hypothesis_passport",
    "evidence_node",
    "claim_card",
    "evaluator_bundle",
    "holdout_manifest",
    "policy_bundle",
    "release_state",
    "noetic_ledger",
)


class BackendAuthorityRefused(PermissionError):
    """A backend signal was routed at a Foundry authority surface."""


def foundry_runs_without_backend() -> bool:
    """Always True: no Foundry capability requires an external search backend.

    Stated as an executable answer rather than as prose. If this ever needs to
    become conditional, the test pinning it fails, which is the point at which the
    optionality claim in `AGENTS.md` would have to be revised rather than quietly
    outgrown.
    """
    return True


def require_optional(run_spec: Mapping[str, Any]) -> None:
    """Refuse a RunSpec that makes an external backend mandatory."""
    backend = run_spec.get("search_backend")
    if isinstance(backend, Mapping) and bool(backend.get("required")):
        raise BackendAuthorityRefused(
            f"RunSpec {run_spec.get('evolution_run_id') or run_spec.get('run_id')} declares its "
            "search backend required; a backend the Foundry cannot proceed without has become "
            "authority rather than an adapter"
        )


def require_no_authority_routing(routes: Mapping[str, str]) -> None:
    """Refuse any mapping from a backend signal onto a Foundry authority surface.

    `routes` maps signal name to destination surface. The check is on the
    destination rather than on the signal's value, because the failure is
    structural: a `combined_score` written into a promotion decision is wrong at
    every magnitude.
    """
    violations = sorted(
        f"{signal} -> {surface}"
        for signal, surface in routes.items()
        if surface in FOUNDRY_AUTHORITY_SURFACES
    )
    if violations:
        raise BackendAuthorityRefused(
            "refusing to route backend signals into Foundry authority: "
            + "; ".join(violations)
        )
    unknown = sorted(set(routes) - ADVISORY_BACKEND_SIGNALS)
    if unknown:
        raise BackendAuthorityRefused(
            f"backend signals {unknown} are not classified as advisory; an unclassified signal "
            "cannot be shown to stay outside Foundry authority"
        )


def import_backend_state(
    *,
    source_version: str,
    target_version: str,
    source_run_id: str,
    target_session_id: str,
    source_snapshot_hash: str,
    migration_plan_id: str,
    unconverted_fields: Sequence[str],
    import_id: str | None = None,
    imported_at: str | None = None,
) -> dict[str, Any]:
    """Import backend state as a translated record, never as Foundry history.

    Two fields are derived rather than accepted:

    * `derived_phase` is always the idle phase. An imported run has produced no Foundry
      receipts, so placing it at a later FORGE phase would credit it with
      transitions the kernel never authorized.
    * `manufactured_receipts` is always False. The field exists so an importer can
      never claim receipts it did not observe, and letting a caller set it True
      would make the honest case indistinguishable from the dishonest one.
    """
    record: dict[str, Any] = {
        "import_id": import_id or new_id("IMP"),
        "source_version": source_version,
        "target_version": target_version,
        "source_run_id": source_run_id,
        "target_session_id": target_session_id,
        "source_snapshot_hash": source_snapshot_hash,
        "migration_plan_id": migration_plan_id,
        "derived_phase": str(ForgePhase.IDLE),
        "unconverted_fields": list(unconverted_fields),
        "manufactured_receipts": False,
        "imported_at": imported_at or utc_now_iso(),
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    validate_artifact("imported-run-record", record)
    return record


def imported_state_is_authoritative(record: Mapping[str, Any]) -> bool:
    """Always False: an imported run never becomes Foundry authority.

    A complete, clean import with no unconverted fields still returns False. The
    import records what another engine did; standing in the Foundry comes from
    Foundry receipts, and this record contains none.
    """
    return False
