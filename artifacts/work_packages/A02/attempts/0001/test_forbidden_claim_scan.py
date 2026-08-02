#!/usr/bin/env python3
"""A02 required check ``forbidden_claim_scan``.

Deterministic attestation that the two A02 write-scope files —
``docs/product_constitution.md`` and ``manifests/product_invariants.yaml`` —
contain no forbidden maturity overclaim. Per the CLAUDE.md maturity clause the
v4 package is a specification and fail-closed reference blueprint: it must not
claim that the v4 plugin or ShinkaEvolve integration is executable, validated,
or production-ready.

Every sentence that contains an overclaim phrase must also carry a negation or
qualifier; any un-negated occurrence is a hard failure. The guard must not be
inert: at least one overclaim phrase must be matched (the constitution and the
non-goals deliberately mention production performance in negated form), proving
the scanner actually inspects the maturity language rather than silently
passing. The files are read, never edited.

Run as a pytest module::

    .venv/Scripts/python.exe -B -m pytest \
        artifacts/work_packages/A02/attempts/0001/test_forbidden_claim_scan.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe -B \
        artifacts/work_packages/A02/attempts/0001/test_forbidden_claim_scan.py \
        --output artifacts/work_packages/A02/attempts/0001/forbidden-claim-scan.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

SCANNED_FILES = (
    "docs/product_constitution.md",
    "manifests/product_invariants.yaml",
)

# Forbidden maturity-overclaim phrases. Any sentence containing one of these
# must also contain a negation/qualifier; an un-negated occurrence is a hard
# failure. These target runtime-readiness claims the reference blueprint must
# not make about the v4 plugin or the ShinkaEvolve backend.
OVERCLAIM_PATTERNS = (
    r"production[- ]?ready",
    r"production readiness",
    r"production performance",
    r"production[- ]grade",
    r"fully implemented",
    r"fully operational",
    r"ready for production",
    r"already implemented",
    r"is executable",
    r"is validated",
    r"is production",
    r"guarantee[sd]? truth",
    r"autonomous scientific discovery",
)

NEGATION_PATTERN = re.compile(
    r"\b(?:not|never|no|nor|until|cannot|can't|forbidden|forbid|do not|don't|does not|"
    r"doesn't|is not|isn't|are not|aren't|without|merely|remains?|remain|stub|"
    r"fail-closed|blueprint|specification|specified|claimed|claim|conditional|deferred|"
    r"not_?claimed|unsupported)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.:;!\n])\s+")


class ScanError(AssertionError):
    """Fail-closed forbidden-claim violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScanError(message)


def read_doc(relative: str) -> str:
    path = ROOT / relative
    require(path.is_file(), f"scanned file missing: {relative}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {relative}")
    text = data.decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {relative}")
    return text


def normalize(text: str) -> str:
    # Preserve newlines as sentence boundaries but collapse other whitespace,
    # so YAML list items and wrapped markdown lines scan as independent units.
    text = re.sub(r"[ \t]+", " ", text)
    return text


def sentences(text: str) -> list[str]:
    return [chunk.strip() for chunk in _SENTENCE_SPLIT.split(normalize(text)) if chunk.strip()]


def scan_file(relative: str) -> dict[str, Any]:
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
    per_file = {relative: scan_file(relative) for relative in SCANNED_FILES}
    total_checked = sum(item["overclaim_sentences_checked"] for item in per_file.values())
    require(
        total_checked > 0,
        "forbidden-claim scan matched no overclaim phrase; the guard is inert",
    )
    return {
        "schema_version": 1,
        "work_package_id": "A02",
        "attempt_id": "A02-0001",
        "check": "forbidden_claim_scan",
        "status": "PASS",
        "exit_criterion": "non-goals prevent overclaim and provider lock-in",
        "scanned_files": list(SCANNED_FILES),
        "overclaim_patterns": list(OVERCLAIM_PATTERNS),
        "per_file": per_file,
        "overclaim_sentences_checked": total_checked,
        "un_negated_overclaims": 0,
        "reference_blueprint_maturity_preserved": True,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_product_constitution_has_no_un_negated_overclaim() -> None:
    assert scan_file("docs/product_constitution.md")["un_negated_overclaims"] == 0


def test_product_invariants_yaml_has_no_un_negated_overclaim() -> None:
    assert scan_file("manifests/product_invariants.yaml")["un_negated_overclaims"] == 0


def test_forbidden_claim_scan_overall() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert evidence["un_negated_overclaims"] == 0
    # Guard must not be inert: it must actually inspect maturity language.
    assert evidence["overclaim_sentences_checked"] > 0
    assert evidence["reference_blueprint_maturity_preserved"] is True


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A02 forbidden_claim_scan")
    parser.add_argument("--output", type=Path, help="Write deterministic JSON evidence to this path")
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except ScanError as exc:
        print(f"A02_FORBIDDEN_CLAIM_SCAN_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"A02_FORBIDDEN_CLAIM_SCAN_PASS: wrote {output.relative_to(ROOT.resolve()).as_posix()}")
    else:
        sys.stdout.write(rendered)
        print("A02_FORBIDDEN_CLAIM_SCAN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
