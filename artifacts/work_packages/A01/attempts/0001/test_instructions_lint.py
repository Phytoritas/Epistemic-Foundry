#!/usr/bin/env python3
"""A01 required check ``instructions_lint``.

Deterministic attestation that the repository authority chain is present,
single, and unambiguous across the top-of-chain instruction documents
(``MASTER_SPEC.md``, ``CLAUDE.md`` and ``AGENTS.md``), and that those
documents declare the ``SPEC_GAP`` / ``BLOCKED`` stop semantics.

This is attestation evidence over already-authored, load-bearing authority
files. It reads the documents and asserts their structure; it never edits
them. Every assertion is fail-closed: a missing, duplicated, reordered, or
contradictory authority order makes the check exit non-zero.

Run as a pytest module::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A01/attempts/0001/test_instructions_lint.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A01/attempts/0001/test_instructions_lint.py \
        --output artifacts/work_packages/A01/attempts/0001/instructions-lint.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

# Documents that must carry the identical, unambiguous authority order.
AUTHORITY_DOCS = ("MASTER_SPEC.md", "CLAUDE.md", "AGENTS.md")

# Canonical ordered authority chain. Each position pins the token that must
# appear in that numbered item; wording differs slightly per document
# (item 5 "schemas and workflows"; item 7 self-reference) so those positions
# accept an alternation.
POSITION_ANCHORS: tuple[tuple[int, str], ...] = (
    (1, r"MASTER_SPEC\.md"),
    (2, r"development_manifest\.yaml"),
    (3, r"acceptance_matrix\.yaml"),
    (4, r"product_invariants\.yaml"),
    (5, r"schema|workflow"),
    (6, r"role_registry\.yaml"),
    (7, r"AGENTS\.md|CLAUDE\.md|this file"),
    (8, r"notes"),
)

# Filenames that must appear exactly once inside the numbered list, proving no
# authority source is duplicated at two ranks.
UNIQUE_SOURCE_TOKENS = (
    "MASTER_SPEC.md",
    "development_manifest.yaml",
    "acceptance_matrix.yaml",
    "product_invariants.yaml",
    "role_registry.yaml",
)

# Per-document marker after which the first contiguous numbered list is the
# authority order.
ORDER_START_MARKER = {
    "MASTER_SPEC.md": "## 1. Authority order",
    "CLAUDE.md": "authority order",
    "AGENTS.md": "Read and obey in order",
}

# "A lower source cannot override / conflicts with a higher source".
PRECEDENCE_CLAUSE = re.compile(
    r"lower\s+\w+\s+(?:cannot\s+override|conflicts\s+with)\b[^.]*\bhigher",
    re.IGNORECASE,
)

# A SPEC_GAP stop clause tied to missing/inconsistent/conflicting semantics.
SPEC_GAP_CLAUSE = re.compile(
    r"(?:absent|inconsistent|conflict|missing|not\s+resolve|invent)[^.]{0,90}SPEC_GAP"
    r"|SPEC_GAP[^.]{0,90}(?:absent|inconsistent|conflict|missing|invent)",
    re.IGNORECASE,
)

# BLOCKED tied to an unavailable external prerequisite.
BLOCKED_CLAUSE = re.compile(
    r"BLOCKED[^.]{0,120}(?:external|prerequisite|unavailable|credential|"
    r"licensed|infrastructure|capability|service)"
    r"|(?:external|prerequisite|unavailable)[^.]{0,120}BLOCKED",
    re.IGNORECASE,
)


class LintError(AssertionError):
    """Fail-closed authority-lint violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LintError(message)


def read_doc(relative: str) -> str:
    path = ROOT / relative
    require(path.is_file(), f"authority document missing: {relative}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {relative}")
    text = data.decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {relative}")
    return text


def extract_numbered_order(relative: str, text: str) -> list[tuple[int, str]]:
    """Return the first contiguous ``N. ...`` block after the doc's marker."""
    marker = ORDER_START_MARKER[relative]
    start = text.lower().find(marker.lower())
    require(start >= 0, f"{relative}: authority-order marker not found: {marker!r}")
    items: list[tuple[int, str]] = []
    for raw in text[start:].splitlines():
        match = re.match(r"^\s*(\d+)\.\s+(.*)$", raw)
        if match:
            items.append((int(match.group(1)), match.group(2).strip()))
        elif items:
            # First non-numbered line after the list closes the block.
            break
    require(bool(items), f"{relative}: no numbered authority order found")
    return items


def lint_document(relative: str) -> dict[str, Any]:
    text = read_doc(relative)
    order = extract_numbered_order(relative, text)

    numbers = [n for n, _ in order]
    require(
        numbers == list(range(1, 9)),
        f"{relative}: authority order must be exactly items 1..8, got {numbers}",
    )

    items = {n: body for n, body in order}
    for position, anchor in POSITION_ANCHORS:
        require(
            re.search(anchor, items[position]) is not None,
            f"{relative}: item {position} does not match expected authority "
            f"source /{anchor}/ (got: {items[position]!r})",
        )

    joined = "\n".join(body for _, body in order)
    for token in UNIQUE_SOURCE_TOKENS:
        count = len(re.findall(re.escape(token), joined))
        require(
            count == 1,
            f"{relative}: authority source {token!r} appears {count} times in "
            f"the numbered order; each source must appear exactly once",
        )

    require(
        PRECEDENCE_CLAUSE.search(text) is not None,
        f"{relative}: missing 'lower source cannot override/conflicts with "
        f"higher source' precedence clause",
    )
    require(
        SPEC_GAP_CLAUSE.search(text) is not None,
        f"{relative}: missing SPEC_GAP stop clause for missing/inconsistent "
        f"shared semantics",
    )
    require(
        "BLOCKED" in text,
        f"{relative}: does not mention BLOCKED stop outcome",
    )

    return {
        "path": relative,
        "authority_order_item_count": len(order),
        "authority_order": items,
        "top_authority": items[1],
        "each_source_unique": True,
        "precedence_clause_present": True,
        "spec_gap_stop_clause_present": True,
        "blocked_outcome_present": True,
        "status": "PASS",
    }


def build_evidence() -> dict[str, Any]:
    per_doc = {relative: lint_document(relative) for relative in AUTHORITY_DOCS}

    # Cross-document consistency: identical ranks for the pinned sources.
    for position, anchor in POSITION_ANCHORS:
        bodies = [per_doc[doc]["authority_order"][position] for doc in AUTHORITY_DOCS]
        require(
            all(re.search(anchor, body) for body in bodies),
            f"authority item {position} is inconsistent across documents",
        )

    # MASTER_SPEC.md is the single top authority in every document.
    require(
        all(re.search(r"MASTER_SPEC\.md", per_doc[doc]["top_authority"]) for doc in AUTHORITY_DOCS),
        "MASTER_SPEC.md is not the unambiguous top authority in every document",
    )

    # BLOCKED-as-external-prerequisite is stated by the two full-precedence docs.
    for relative in ("MASTER_SPEC.md", "CLAUDE.md"):
        require(
            BLOCKED_CLAUSE.search(read_doc(relative)) is not None,
            f"{relative}: missing BLOCKED external-prerequisite clause",
        )

    return {
        "schema_version": 1,
        "work_package_id": "A01",
        "attempt_id": "A01-0001",
        "check": "instructions_lint",
        "status": "PASS",
        "exit_criterion": "authority order is unambiguous",
        "authority_documents": list(AUTHORITY_DOCS),
        "canonical_order_tokens": [anchor for _, anchor in POSITION_ANCHORS],
        "per_document": per_doc,
        "cross_document_order_consistent": True,
        "single_top_authority": "MASTER_SPEC.md",
        "spec_gap_stop_declared": True,
        "blocked_stop_declared": True,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_master_spec_authority_order() -> None:
    assert lint_document("MASTER_SPEC.md")["status"] == "PASS"


def test_claude_authority_order() -> None:
    assert lint_document("CLAUDE.md")["status"] == "PASS"


def test_agents_authority_order() -> None:
    assert lint_document("AGENTS.md")["status"] == "PASS"


def test_authority_order_is_unambiguous_and_consistent() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert evidence["single_top_authority"] == "MASTER_SPEC.md"
    assert evidence["cross_document_order_consistent"] is True
    assert evidence["spec_gap_stop_declared"] is True


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A01 instructions_lint check")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except LintError as exc:
        print(f"A01_INSTRUCTIONS_LINT_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"A01_INSTRUCTIONS_LINT_PASS: wrote {output.relative_to(ROOT.resolve()).as_posix()}")
    else:
        sys.stdout.write(rendered)
        print("A01_INSTRUCTIONS_LINT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
