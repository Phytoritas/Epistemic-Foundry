"""`efoundry` CLI.

Canonical CLI name from `manifests/development_manifest.yaml`
(`execution_policy.canonical_cli: efoundry`).

Exit codes carry the typed vocabulary rather than a generic 0/1, because a
truthful stop is part of the product: a `BLOCKED` or `SPEC_GAP` outcome must be
distinguishable by a caller from both success and a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .. import __version__
from ..contracts import ContractViolation, default_registry
from ..contracts.validation import artifact_errors
from ..domain.status import CapabilityStatus, ExitStatus
from ..noetic_ledger import NoeticLedger
from ..noetic_ledger.ledger import LedgerIntegrityError
from ..retrieval import lanes as retrieval_lanes
from ..retrieval import lexical_index

#: Process exit codes for the typed outcomes the CLI can report.
EXIT_CODES: dict[ExitStatus, int] = {
    ExitStatus.PASS: 0,
    ExitStatus.CONDITIONAL: 10,
    ExitStatus.FAIL: 20,
    ExitStatus.BLOCKED: 30,
    ExitStatus.SPEC_GAP: 40,
    ExitStatus.UNDERDETERMINED: 50,
    ExitStatus.UNASSESSED: 60,
    ExitStatus.INVALIDATED: 70,
    ExitStatus.REPLICATION_FAILED: 80,
}

#: What this runtime actually implements. Kept explicit so `efoundry status`
#: cannot imply a working plugin the bundle does not ship.
#:
#: "Implemented" here means the package ships an executable surface whose
#: functions run and are gated by tests — NOT that the component's full
#: specification is delivered. Partial delivery is recorded where it is
#: measurable rather than hidden behind this label: the console, for example,
#: projects four of the ten views MASTER_SPEC section 36 requires, which is
#: tracked in the source-requirement coverage ledger, not here.
#:
#: The 15 phase packages below (adapters .. validation) were added 2026-08-02
#: after `test_implemented_list_matches_the_shipped_packages` was corrected and
#: immediately found them shipped but entirely absent from this report — the
#: maturity surface was silent about them in either direction.
IMPLEMENTED_COMPONENTS = (
    "adapters",
    "application",
    "cartography",
    "console",
    "effects",
    "evidence",
    "evolution",
    "intake",
    "operations",
    "operators",
    "parliament",
    "reasoning",
    "recovery",
    "retrieval",
    "scheduler",
    "validation",
    "contracts",
    "domain",
    "noetic_ledger",
    "foundry_kernel",
    "verifier_firewall",
    "governance",
    "claim_forge",
    "evidence_parliament",
    "validation_bay",
    "evolution_chamber",
    "red_queen_lab",
    "epistemic_species_archive",
    "aporia_engine",
    "hypothesis_passport",
    "epistemic_atlas",
    "plugin_shell",
    "ingest",
    "memory",
    "observability",
    "security",
    "budgets",
    "updates",
    "evaluation",
    "statistics",
    "release",
)

#: Capabilities the bundle specifies that this runtime does not implement.
#: Non-empty is the honest state: a component belongs here when its verification
#: half exists and its execution half does not, so listing it as implemented
#: would be a release-label claim the evidence does not support (EF4-I33 —
#: release labels are evidence-derived). Corrected 2026-08-02 after an audit
#: found all three below were reported as implemented by `efoundry status`:
#:   providers      — provider-neutrality assertions and untrusted-content
#:                    wrapping exist; there is no transport anywhere in the
#:                    repository, so no provider can be invoked or substituted
#:                    and neutrality is declared rather than demonstrated.
#:   shinka_adapter — the manifest, isolation and reconciliation contracts exist
#:                    and are tested; no backend is reachable and B05 records the
#:                    backend pin as BLOCKED with no digest to pin.
#: `retrieval` was listed here on 2026-08-02 and moved back to implemented the
#: same day once a SQLite FTS5 index, query execution and schema-valid lane
#: receipts shipped with tests. What it implements is bounded and stated in
#: `retrieval/lanes.py`: three of the eleven canonical lanes execute (LEXICAL,
#: CITATION_GRAPH, RELATION_GRAPH); the other eight emit explicit UNSEARCHED
#: sentinels with reasons rather than empty results, so lane coverage is never
#: overstated.
#: Advancing any of these requires execution evidence, not another unit test.
#: `PLUGIN_ALPHA` and above additionally require install-matrix, sandbox, UI and
#: deployment evidence that no unit test can supply
#: (`manifests/acceptance_matrix.yaml`).
#:
#: Corrected after review: the emitted note used to say these components remain
#: `SPECIFIED` or `REFERENCE_BLUEPRINT`, which was false of both. The taxonomy
#: defines `SPECIFIED` as production code not being implied and
#: `REFERENCE_BLUEPRINT` as a static layout, and each of these ships executable,
#: tested code. The accurate term for a capability that is partially available
#: with its limits surfaced is `DEGRADED`, so that is what the status reports.
#: The list name is kept because callers key on the `specified_only` field.
SPECIFIED_ONLY_COMPONENTS: tuple[str, ...] = (
    "providers",
    "shinka_adapter",
)


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            print(f"{key}:")
            for item in value:
                print(f"  - {item}")
        else:
            print(f"{key}: {value}")


def cmd_status(args: argparse.Namespace) -> ExitStatus:
    """Report maturity truthfully: implemented vs specified-only."""
    registry = default_registry()
    payload = {
        "version": __version__,
        "release_level": "SPEC_BUNDLE",
        "runtime_status": "PARTIAL_IMPLEMENTATION",
        "canonical_schemas_loaded": len(registry.names()),
        "implemented": list(IMPLEMENTED_COMPONENTS),
        "specified_only": list(SPECIFIED_ONLY_COMPONENTS),
        "specified_only_status": str(CapabilityStatus.DEGRADED),
        "note": (
            "Components under 'implemented' ship an executable surface that unit "
            "gates exercise. Components under 'specified_only' are "
            f"{CapabilityStatus.DEGRADED}: they also ship executable, tested code, "
            "but the capability that defines them is unreachable — no provider "
            "transport exists and no evolution backend is bound — so their gates "
            "prove the guard rails, not the capability. Neither list is a "
            "working-plugin or production-readiness claim."
        ),
    }
    _emit(payload, as_json=args.json)
    return ExitStatus.PASS


def cmd_validate(args: argparse.Namespace) -> ExitStatus:
    """Validate one artifact file against a named canonical schema."""
    path = Path(args.artifact)
    if not path.is_file():
        _emit({"outcome": str(ExitStatus.FAIL), "error": f"no such artifact: {path}"}, as_json=args.json)
        return ExitStatus.FAIL
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _emit(
            {"outcome": str(ExitStatus.FAIL), "error": f"{path} is not valid JSON: {exc}"},
            as_json=args.json,
        )
        return ExitStatus.FAIL
    try:
        errors = artifact_errors(args.schema, payload)
    except LookupError as exc:
        _emit({"outcome": str(ExitStatus.SPEC_GAP), "error": str(exc)}, as_json=args.json)
        return ExitStatus.SPEC_GAP
    outcome = ExitStatus.PASS if not errors else ExitStatus.FAIL
    _emit(
        {
            "outcome": str(outcome),
            "schema": args.schema,
            "artifact": str(path),
            "error_count": len(errors),
            "errors": errors,
        },
        as_json=args.json,
    )
    return outcome


def cmd_ledger_verify(args: argparse.Namespace) -> ExitStatus:
    """Replay a ledger's hash chain and report integrity."""
    ledger = NoeticLedger(Path(args.path))
    try:
        ledger.verify()
    except LedgerIntegrityError as exc:
        _emit(
            {"outcome": str(ExitStatus.INVALIDATED), "path": args.path, "error": str(exc)},
            as_json=args.json,
        )
        return ExitStatus.INVALIDATED
    except ContractViolation as exc:
        _emit(
            {"outcome": str(ExitStatus.FAIL), "path": args.path, "error": str(exc)},
            as_json=args.json,
        )
        return ExitStatus.FAIL
    _emit(
        {"outcome": str(ExitStatus.PASS), "path": args.path, "events": ledger.length()},
        as_json=args.json,
    )
    return ExitStatus.PASS


def cmd_schemas(args: argparse.Namespace) -> ExitStatus:
    registry = default_registry()
    names = registry.names()
    _emit({"count": len(names), "schema_dir": str(registry.schema_dir), "schemas": names}, as_json=args.json)
    return ExitStatus.PASS


def cmd_retrieve_build(args: argparse.Namespace) -> ExitStatus:
    """Build or reuse the SQLite FTS5 lexical index over a corpus.

    The corpus is read-only. Output is deterministic and carries the
    content-addressed snapshot identity that later receipts bind to, so the
    searched scope of a run is auditable rather than assumed.
    """
    try:
        stats = lexical_index.build_index(
            Path(args.corpus_root),
            Path(args.db_path),
            rebuild=args.rebuild,
        )
    except lexical_index.LexicalIndexError as exc:
        _emit({"outcome": str(ExitStatus.FAIL), "error": str(exc)}, as_json=args.json)
        return ExitStatus.FAIL
    except OSError as exc:
        _emit({"outcome": str(ExitStatus.FAIL), "error": str(exc)}, as_json=args.json)
        return ExitStatus.FAIL
    _emit({"outcome": str(ExitStatus.PASS), **stats}, as_json=args.json)
    return ExitStatus.PASS


def _lane_binding_context(
    args: argparse.Namespace, stats: dict[str, Any]
) -> retrieval_lanes.LaneContext:
    return retrieval_lanes.LaneContext.from_index_stats(
        stats,
        run_id=args.run_id,
        query_plan_id=args.query_plan_id,
        plan_hash=args.plan_hash,
        policy_bundle_hash=args.policy_bundle_hash,
        capability_lease_id=args.capability_lease_id,
        cutoff_policy_id=args.cutoff_policy_id,
        lane_decision_evidence_ids=tuple(args.lane_decision_evidence_id),
        started_at=args.started_at,
        finished_at=args.finished_at,
        max_candidates=args.limit,
    )


def _run_lane(
    args: argparse.Namespace, stats: dict[str, Any]
) -> retrieval_lanes.LaneResult:
    context = _lane_binding_context(args, stats)
    db_path = Path(args.db_path)
    if args.lane == "lexical":
        return retrieval_lanes.lexical(db_path, context, expression=args.expression)
    if args.lane == "citation":
        return retrieval_lanes.citation(
            db_path,
            context,
            seed_document_ids=args.seed_document_id,
            citation_keys=args.citation_key,
        )
    if args.lane == "entity_variable":
        groups = [group.split("|") for group in args.term_group]
        return retrieval_lanes.entity_variable(
            db_path, context, term_groups=groups, window_chars=args.window_chars
        )
    # A canonical lane this backend does not serve is reported as the single
    # UNSEARCHED sentinel it is entitled to — never as an empty result set.
    return retrieval_lanes.absent_lane_result(context, args.lane)


def cmd_retrieve_query(args: argparse.Namespace) -> ExitStatus:
    """Query the lexical index, optionally through a canonical retrieval lane.

    Without ``--lane`` this is a raw index read: ranked documents with
    re-extractable offsets and no sealed receipt, because a receipt would have to
    invent the plan bindings it claims to bind. With ``--lane`` the caller
    supplies those bindings and gets schema-valid candidates and a receipt.
    """
    db_path = Path(args.db_path)
    try:
        stats = lexical_index.read_index_stats(db_path)
    except lexical_index.LexicalIndexError as exc:
        _emit(
            {
                "outcome": str(ExitStatus.BLOCKED),
                "error": str(exc),
                "remedy": "run `efoundry retrieve build <corpus_root> <db_path>` first",
            },
            as_json=args.json,
        )
        return ExitStatus.BLOCKED

    if args.lane is None:
        if not args.expression:
            _emit(
                {
                    "outcome": str(ExitStatus.FAIL),
                    "error": "--expression is required without --lane",
                },
                as_json=args.json,
            )
            return ExitStatus.FAIL
        try:
            rows = lexical_index.query(db_path, args.expression, limit=args.limit)
        except lexical_index.LexicalIndexError as exc:
            _emit(
                {"outcome": str(ExitStatus.FAIL), "error": str(exc)}, as_json=args.json
            )
            return ExitStatus.FAIL
        _emit(
            {
                "outcome": str(ExitStatus.PASS),
                "corpus_snapshot_hash": stats["corpus_snapshot_hash"],
                "index_versions": stats["index_versions"],
                "expression": args.expression,
                "result_count": len(rows),
                "results": rows,
            },
            as_json=args.json,
        )
        return ExitStatus.PASS

    missing = [
        name
        for name in (
            "run_id",
            "query_plan_id",
            "plan_hash",
            "policy_bundle_hash",
            "started_at",
            "finished_at",
        )
        if not getattr(args, name)
    ]
    if missing or not args.lane_decision_evidence_id:
        _emit(
            {
                "outcome": str(ExitStatus.FAIL),
                "error": (
                    "a sealed lane receipt binds the plan it executed; supply "
                    "--run-id, --query-plan-id, --plan-hash, --policy-bundle-hash, "
                    "--started-at, --finished-at and at least one "
                    "--lane-decision-evidence-id"
                ),
                "missing": missing,
            },
            as_json=args.json,
        )
        return ExitStatus.FAIL

    try:
        result = _run_lane(args, stats)
    except (retrieval_lanes.LaneContractError, lexical_index.LexicalIndexError) as exc:
        _emit({"outcome": str(ExitStatus.FAIL), "error": str(exc)}, as_json=args.json)
        return ExitStatus.FAIL

    context = _lane_binding_context(args, stats)
    reconciliation = retrieval_lanes.reconcile_lanes(context, [result])
    try:
        for receipt in reconciliation["receipts"]:
            artifact_errors_found = artifact_errors("search-lane-receipt", receipt)
            if artifact_errors_found:
                raise ContractViolation("search-lane-receipt", artifact_errors_found)
        for candidate in result.candidates:
            candidate_errors = artifact_errors("retrieval-candidate", candidate)
            if candidate_errors:
                raise ContractViolation("retrieval-candidate", candidate_errors)
    except LookupError as exc:
        _emit(
            {"outcome": str(ExitStatus.SPEC_GAP), "error": str(exc)}, as_json=args.json
        )
        return ExitStatus.SPEC_GAP
    except ContractViolation as exc:
        _emit({"outcome": str(ExitStatus.FAIL), "error": str(exc)}, as_json=args.json)
        return ExitStatus.FAIL

    _emit(
        {
            "outcome": str(ExitStatus.PASS),
            "lane": result.lane,
            "search_state": result.search_state.value,
            "absence_of_evidence": result.is_absence_of_evidence,
            "run_ceiling": reconciliation["run_ceiling"],
            "all_lane_reconciliation_count": reconciliation[
                "all_lane_reconciliation_count"
            ],
            "non_vector_release_origins": reconciliation["non_vector_release_origins"],
            "unsearched_lanes": reconciliation["unsearched_lanes"],
            "diagnostics": result.diagnostics,
            "candidates": list(result.candidates),
            "receipts": reconciliation["receipts"],
        },
        as_json=args.json,
    )
    return ExitStatus.PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="efoundry",
        description=(
            "Epistemic Foundry v4 runtime CLI. Exit codes encode the typed outcome "
            "vocabulary (PASS=0, FAIL=20, BLOCKED=30, SPEC_GAP=40, INVALIDATED=70, ...)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"efoundry {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="report version and honest maturity")
    status.set_defaults(handler=cmd_status)

    schemas = sub.add_parser("schemas", help="list canonical schemas")
    schemas.set_defaults(handler=cmd_schemas)

    validate = sub.add_parser("validate", help="validate an artifact against a canonical schema")
    validate.add_argument("schema", help="canonical schema name, e.g. forge-session-state")
    validate.add_argument("artifact", help="path to a JSON artifact")
    validate.set_defaults(handler=cmd_validate)

    ledger = sub.add_parser("ledger", help="Noetic Ledger operations")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    verify = ledger_sub.add_parser("verify", help="replay a ledger hash chain")
    verify.add_argument("path", help="path to a ledger JSONL file")
    verify.set_defaults(handler=cmd_ledger_verify)

    retrieve = sub.add_parser("retrieve", help="lexical index and retrieval lanes")
    retrieve_sub = retrieve.add_subparsers(dest="retrieve_command", required=True)

    build = retrieve_sub.add_parser("build", help="build the SQLite FTS5 lexical index")
    build.add_argument("corpus_root", help="corpus directory (read-only)")
    build.add_argument("db_path", help="index database path to write")
    build.add_argument(
        "--rebuild",
        action="store_true",
        help="rebuild even when the recorded corpus snapshot is unchanged",
    )
    build.set_defaults(handler=cmd_retrieve_build)

    query = retrieve_sub.add_parser("query", help="query the lexical index")
    query.add_argument("db_path", help="index database path")
    query.add_argument("--expression", help="FTS5 MATCH expression (lexical lane)")
    query.add_argument(
        "--lane",
        choices=retrieval_lanes.CANONICAL_LANES,
        help="run a canonical retrieval lane and emit receipts; lanes this backend "
        "does not serve return their UNSEARCHED sentinel",
    )
    query.add_argument(
        "--limit", type=int, default=retrieval_lanes.DEFAULT_MAX_CANDIDATES
    )
    query.add_argument(
        "--seed-document-id", action="append", default=[], help="citation lane seed"
    )
    query.add_argument(
        "--citation-key", action="append", default=[], help="citation lane key"
    )
    query.add_argument(
        "--term-group",
        action="append",
        default=[],
        help="entity_variable term group, terms separated by '|'",
    )
    query.add_argument(
        "--window-chars",
        type=int,
        default=retrieval_lanes.DEFAULT_COOCCURRENCE_WINDOW,
        help="entity_variable co-occurrence window",
    )
    query.add_argument("--run-id", default="")
    query.add_argument("--query-plan-id", default="")
    query.add_argument("--plan-hash", default="")
    query.add_argument("--policy-bundle-hash", default="")
    query.add_argument("--capability-lease-id", default="CLI-LOCAL-READ")
    query.add_argument("--cutoff-policy-id", default="CLI-TOP-K")
    query.add_argument("--lane-decision-evidence-id", action="append", default=[])
    query.add_argument(
        "--started-at",
        default="",
        help="caller-supplied RFC 3339 start time; nothing here reads a clock",
    )
    query.add_argument(
        "--finished-at", default="", help="caller-supplied RFC 3339 end time"
    )
    query.set_defaults(handler=cmd_retrieve_query)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    outcome = args.handler(args)
    return EXIT_CODES[outcome]


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
