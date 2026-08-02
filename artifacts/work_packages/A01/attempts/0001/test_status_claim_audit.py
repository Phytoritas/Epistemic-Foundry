#!/usr/bin/env python3
"""A01 required check ``status_claim_audit``.

Deterministic attestation that no authority document confuses ``SPECIFIED``
with ``IMPLEMENTED``. The status taxonomy plus the maturity clauses of
``MASTER_SPEC.md``, ``CLAUDE.md`` and ``AGENTS.md`` must explicitly separate a
specified contract from an implemented capability and must forbid deriving a
``PASS`` / product-maturity claim from tests alone.

Two independent guards run:

1. Required-guard-clause presence: the distinguishing sentences that keep
   ``SPECIFIED`` and ``IMPLEMENTED`` disjoint must exist verbatim (structure).
2. Overclaim scan: every sentence in an authority document that contains a
   maturity-overclaim phrase (``production-ready``, ``fully implemented`` ...)
   must also carry a negation/qualifier, so no bare product-maturity claim can
   survive.

Attestation evidence only; the authority documents are read, never edited.

Run as pytest::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A01/attempts/0001/test_status_claim_audit.py \
        -p no:cacheprovider

Standalone evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A01/attempts/0001/test_status_claim_audit.py \
        --output artifacts/work_packages/A01/attempts/0001/status-claim-audit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

AUTHORITY_DOCS = (
    "MASTER_SPEC.md",
    "CLAUDE.md",
    "AGENTS.md",
    "docs/status_taxonomy.md",
)

# Required guard clauses, keyed by document. Each pattern is matched against the
# whitespace-normalized document text so soft line wraps do not break it.
REQUIRED_CLAUSES: dict[str, dict[str, str]] = {
    "docs/status_taxonomy.md": {
        "specified_no_production_code":
            r"`SPECIFIED`\s*\|\s*A normative contract exists;\s*production code is not implied",
        "implemented_requires_gates":
            r"`IMPLEMENTED`\s*\|\s*Source code exists and declared unit/integration gates pass",
        "specified_not_alias_of_implemented":
            r"`SPECIFIED` and `REFERENCE_BLUEPRINT` are never aliases for\s+`IMPLEMENTED`",
        "implemented_requires_runtime_gates":
            r"`IMPLEMENTED` requires the declared runtime and\s+integration gates",
        "pass_not_from_tests_alone":
            r"`PASS` must not be emitted\s+from tests alone",
    },
    "MASTER_SPEC.md": {
        "implementation_not_claimed":
            r"Implementation status:\*\*\s*`NOT CLAIMED`",
        "does_not_claim_runtime":
            r"It does not claim that a working v4 runtime",
        "spec_file_not_execution_evidence":
            r"A specification file is not execution evidence",
        "status_honesty_invariant":
            r"EF4-I33 — Status honesty",
        "status_label_vocabulary":
            r"SPECIFIED, IMPLEMENTED, EXPERIMENTAL, DEFERRED or UNSUPPORTED",
    },
    "CLAUDE.md": {
        "maturity_guard":
            r"Do not state that the v4 plugin.{0,80}is\s+executable,\s*validated, "
            r"or production-ready until the corresponding implementation and\s+release gates pass",
        "spec_and_blueprint":
            r"specification and fail-closed reference blueprint",
    },
    "AGENTS.md": {
        "spec_bundle_reference_blueprint":
            r"SPEC_BUNDLE / REFERENCE_BLUEPRINT",
        "not_implemented_because_contracts_exist":
            r"Do not claim that the\s+plugin runtime.{0,300}"
            r"are\s+implemented merely because their contracts exist",
    },
}

# Maturity-overclaim phrases. Any sentence containing one of these must also
# contain a negation/qualifier; an un-negated occurrence is a hard failure.
OVERCLAIM_PATTERNS = (
    r"production[- ]?ready",
    r"production readiness",
    r"fully implemented",
    r"fully operational",
    r"ready for production",
    r"already implemented",
    r"is production[- ]grade",
)

NEGATION_PATTERN = re.compile(
    r"\b(?:not|never|no|until|cannot|can't|forbidden|forbid|do not|don't|does not|"
    r"doesn't|is not|isn't|are not|aren't|without|merely|remains?|remain|stub|"
    r"fail-closed|blueprint|specification|claimed|claim)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.:!])\s+")


class AuditError(AssertionError):
    """Fail-closed status-claim-audit violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def read_doc(relative: str) -> str:
    path = ROOT / relative
    require(path.is_file(), f"authority document missing: {relative}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {relative}")
    text = data.decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {relative}")
    return text


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def sentences(text: str) -> list[str]:
    return [chunk.strip() for chunk in _SENTENCE_SPLIT.split(normalize(text)) if chunk.strip()]


def audit_required_clauses(relative: str) -> dict[str, Any]:
    normalized = normalize(read_doc(relative))
    found: dict[str, bool] = {}
    for clause_id, pattern in REQUIRED_CLAUSES[relative].items():
        present = re.search(pattern, normalized) is not None
        require(
            present,
            f"{relative}: required status guard clause missing: {clause_id}",
        )
        found[clause_id] = True
    return {"path": relative, "required_clauses": found, "status": "PASS"}


def audit_overclaims(relative: str) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    checked = 0
    for sentence in sentences(read_doc(relative)):
        for pattern in OVERCLAIM_PATTERNS:
            if re.search(pattern, sentence, re.IGNORECASE):
                checked += 1
                if NEGATION_PATTERN.search(sentence) is None:
                    violations.append({"pattern": pattern, "sentence": sentence})
    require(
        not violations,
        f"{relative}: un-negated maturity overclaim(s): {violations}",
    )
    return {
        "path": relative,
        "overclaim_sentences_checked": checked,
        "un_negated_overclaims": 0,
        "status": "PASS",
    }


def build_evidence() -> dict[str, Any]:
    clause_audit = {relative: audit_required_clauses(relative) for relative in REQUIRED_CLAUSES}
    overclaim_audit = {relative: audit_overclaims(relative) for relative in AUTHORITY_DOCS}

    total_overclaims_checked = sum(item["overclaim_sentences_checked"] for item in overclaim_audit.values())
    require(total_overclaims_checked > 0, "overclaim scan matched no sentences; guard is inert")

    return {
        "schema_version": 1,
        "work_package_id": "A01",
        "attempt_id": "A01-0001",
        "check": "status_claim_audit",
        "status": "PASS",
        "exit_criterion": "SPECIFIED is not confused with IMPLEMENTED",
        "authority_documents": list(AUTHORITY_DOCS),
        "required_clause_audit": clause_audit,
        "overclaim_audit": overclaim_audit,
        "overclaim_sentences_checked": total_overclaims_checked,
        "un_negated_overclaims": 0,
        "specified_distinct_from_implemented": True,
        "pass_from_tests_alone_forbidden": True,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_status_taxonomy_separates_specified_and_implemented() -> None:
    assert audit_required_clauses("docs/status_taxonomy.md")["status"] == "PASS"


def test_master_spec_maturity_clauses() -> None:
    assert audit_required_clauses("MASTER_SPEC.md")["status"] == "PASS"


def test_claude_maturity_clause() -> None:
    assert audit_required_clauses("CLAUDE.md")["status"] == "PASS"


def test_agents_maturity_clause() -> None:
    assert audit_required_clauses("AGENTS.md")["status"] == "PASS"


def test_no_un_negated_maturity_overclaim() -> None:
    for relative in AUTHORITY_DOCS:
        assert audit_overclaims(relative)["un_negated_overclaims"] == 0


def test_status_claim_audit_overall() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert evidence["specified_distinct_from_implemented"] is True
    assert evidence["pass_from_tests_alone_forbidden"] is True


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A01 status_claim_audit check")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except AuditError as exc:
        print(f"A01_STATUS_CLAIM_AUDIT_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"A01_STATUS_CLAIM_AUDIT_PASS: wrote {output.relative_to(ROOT.resolve()).as_posix()}")
    else:
        sys.stdout.write(rendered)
        print("A01_STATUS_CLAIM_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
