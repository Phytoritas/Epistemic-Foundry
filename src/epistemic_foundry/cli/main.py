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
from ..contracts import ContractViolation, default_registry, repo_root
from ..contracts.validation import artifact_errors
from ..domain.status import CapabilityStatus, ExitStatus
from ..noetic_ledger import NoeticLedger
from ..noetic_ledger.ledger import LedgerIntegrityError

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
IMPLEMENTED_COMPONENTS = (
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
)

SPECIFIED_ONLY_COMPONENTS = (
    "plugin_shell",
    "epistemic_atlas",
    "aporia_engine",
    "hypothesis_passport",
    "red_queen_lab",
    "epistemic_species_archive",
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
        "note": (
            "Only the components under 'implemented' have passing gates. Everything under "
            f"'specified_only' remains {CapabilityStatus.SPECIFIED} or "
            f"{CapabilityStatus.REFERENCE_BLUEPRINT}; do not read this output as a "
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    outcome = args.handler(args)
    return EXIT_CODES[outcome]


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
