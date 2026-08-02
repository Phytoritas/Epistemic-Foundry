#!/usr/bin/env python3
"""A03 required check ``adr_index_check``.

Deterministic attestation that the architecture decision record set under
``docs/adr/`` is internally consistent: the index in ``docs/adr/README.md`` and
the ADR files it references agree on a set of unique, contiguous, correctly
numbered records; every indexed ADR resolves to an existing file and every ADR
file is indexed (no dangling or orphan record); each record carries the required
sections (status, context, decision, consequences, plus the rejected-
alternatives and verification sections the index promises); and the new records
continue the historical ``ADR-001..030`` sequence in
``docs/architecture_decisions.md`` without a gap or renumber.

This is attestation evidence over already-authored, load-bearing architecture
documents. It reads them and asserts their structure; it never edits them. Every
assertion is fail-closed: a missing, duplicated, malformed, dangling, or orphan
ADR makes the check exit non-zero.

Run as a pytest module::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A03/attempts/0001/test_adr_index_check.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A03/attempts/0001/test_adr_index_check.py \
        --output artifacts/work_packages/A03/attempts/0001/adr-index-check.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

ADR_DIR = ROOT / "docs/adr"
INDEX = ADR_DIR / "README.md"
#: Historical ADR-001..030 live here and are continued, not renumbered.
LEGACY_DECISIONS = ROOT / "docs/architecture_decisions.md"

#: The ``docs/adr/`` directory continues the sequence after this legacy id.
LAST_LEGACY_ID = 30

#: Every ADR file must carry these ``## Heading`` sections. ``Status`` is a bold
#: field rather than a heading and is validated separately.
REQUIRED_HEADINGS = (
    "Context",
    "Decision",
    "Consequences",
    "Rejected alternatives",
    "Verification",
)

#: Statuses an ADR may declare. A superseded record must name the superseding id.
KNOWN_STATUSES = frozenset(
    {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded"}
)

#: ``| [ADR-031](file.md) | Accepted | decision text |``
INDEX_ROW = re.compile(
    r"^\|\s*\[(?P<id>ADR-\d{3})\]\((?P<file>[^)]+)\)\s*\|"
    r"\s*(?P<status>[^|]+?)\s*\|"
    r"\s*(?P<decision>[^|]+?)\s*\|\s*$"
)

#: ``# ADR-031 — Title`` (em dash or hyphen).
ADR_HEADING = re.compile(r"^#\s+(?P<id>ADR-\d{3})\b")

#: ``**Status:** Accepted``
STATUS_FIELD = re.compile(r"^\*\*Status:\*\*\s*(?P<status>.+?)\s*$", re.MULTILINE)


class AdrError(AssertionError):
    """Fail-closed ADR-index violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdrError(message)


def read_text(path: Path) -> str:
    require(path.is_file(), f"required document missing: {path.relative_to(ROOT).as_posix()}")
    data = path.read_bytes()
    rel = path.relative_to(ROOT).as_posix()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {rel}")
    text = data.decode("utf-8", errors="strict")
    require("�" not in text, f"replacement character found: {rel}")
    return text


def id_number(adr_id: str) -> int:
    return int(adr_id.split("-", 1)[1])


def parse_index() -> list[dict[str, str]]:
    text = read_text(INDEX)
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = INDEX_ROW.match(line)
        if match:
            rows.append(
                {
                    "id": match.group("id"),
                    "file": match.group("file").strip(),
                    "status": match.group("status").strip(),
                    "decision": match.group("decision").strip(),
                }
            )
    require(bool(rows), "docs/adr/README.md: no ADR index rows parsed")
    return rows


def parse_adr_file(path: Path) -> dict[str, Any]:
    text = read_text(path)
    rel = path.relative_to(ROOT).as_posix()

    heading = ADR_HEADING.search(text)
    require(heading is not None, f"{rel}: missing '# ADR-NNN' heading")
    heading_id = heading.group("id")

    stem_match = re.match(r"^(ADR-\d{3})\b", path.stem)
    require(stem_match is not None, f"{rel}: filename does not start with 'ADR-NNN'")
    filename_id = stem_match.group(1)
    require(
        filename_id == heading_id,
        f"{rel}: filename id {filename_id} != heading id {heading_id}",
    )

    status_field = STATUS_FIELD.search(text)
    require(status_field is not None, f"{rel}: missing '**Status:** ...' field")
    status = status_field.group("status").strip()
    require(
        status in KNOWN_STATUSES,
        f"{rel}: unknown status {status!r} (allowed: {sorted(KNOWN_STATUSES)})",
    )

    headings = {
        m.group(1).strip()
        for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }
    missing = [h for h in REQUIRED_HEADINGS if h not in headings]
    require(not missing, f"{rel}: missing required section(s): {missing}")

    superseded_by: str | None = None
    if status == "Superseded":
        ref = re.search(r"[Ss]uperseded by\s+(ADR-\d{3})", text)
        require(
            ref is not None,
            f"{rel}: status Superseded but no 'superseded by ADR-NNN' reference",
        )
        superseded_by = ref.group(1)

    return {
        "id": heading_id,
        "path": rel,
        "status": status,
        "sections_present": sorted(headings & set(REQUIRED_HEADINGS)),
        "superseded_by": superseded_by,
    }


def build_evidence() -> dict[str, Any]:
    require(ADR_DIR.is_dir(), "docs/adr directory missing")

    index_rows = parse_index()
    index_ids = [row["id"] for row in index_rows]
    require(
        len(index_ids) == len(set(index_ids)),
        f"docs/adr/README.md: duplicate ADR id in index: {index_ids}",
    )

    # Files physically present in docs/adr (excluding the index itself).
    adr_files = sorted(
        p for p in ADR_DIR.glob("ADR-*.md") if p.is_file()
    )
    require(bool(adr_files), "docs/adr: no ADR-*.md files found")

    parsed = [parse_adr_file(p) for p in adr_files]
    file_ids = [rec["id"] for rec in parsed]
    require(
        len(file_ids) == len(set(file_ids)),
        f"docs/adr: duplicate ADR id across files: {sorted(file_ids)}",
    )

    file_by_id = {rec["id"]: rec for rec in parsed}
    filename_by_id = {rec["id"]: Path(rec["path"]).name for rec in parsed}

    # No dangling index reference: every indexed row resolves to an existing
    # file whose id and status match the index.
    for row in index_rows:
        target = (ADR_DIR / row["file"]).resolve()
        require(
            target.is_file(),
            f"docs/adr/README.md: dangling reference {row['file']!r} for {row['id']}",
        )
        require(
            target.name == filename_by_id.get(row["id"]),
            f"docs/adr/README.md: {row['id']} links {row['file']!r} but file id "
            f"maps to {filename_by_id.get(row['id'])!r}",
        )
        require(
            row["status"] == file_by_id[row["id"]]["status"],
            f"{row['id']}: index status {row['status']!r} != file status "
            f"{file_by_id[row['id']]['status']!r}",
        )

    # No orphan file: every ADR file is indexed.
    indexed = set(index_ids)
    orphans = sorted(rec["id"] for rec in parsed if rec["id"] not in indexed)
    require(not orphans, f"docs/adr: ADR file(s) not present in index: {orphans}")
    require(
        set(file_ids) == indexed,
        f"docs/adr: index/file id mismatch — index={sorted(indexed)} "
        f"files={sorted(file_ids)}",
    )

    # Unique, contiguous, ascending ids that continue the legacy sequence.
    numbers = sorted(id_number(i) for i in file_ids)
    require(
        numbers == list(range(numbers[0], numbers[-1] + 1)),
        f"docs/adr: ADR ids are not contiguous: {numbers}",
    )
    require(
        numbers[0] == LAST_LEGACY_ID + 1,
        f"docs/adr: sequence starts at ADR-{numbers[0]:03d}, expected "
        f"ADR-{LAST_LEGACY_ID + 1:03d} (continue after legacy ADR-{LAST_LEGACY_ID:03d})",
    )

    # Any superseding reference must resolve to a known record.
    for rec in parsed:
        if rec["superseded_by"] is not None:
            require(
                rec["superseded_by"] in file_by_id,
                f"{rec['id']}: superseded by unknown {rec['superseded_by']}",
            )

    # The legacy tail is intact so the continuation has no gap.
    legacy = read_text(LEGACY_DECISIONS)
    require(
        f"ADR-{LAST_LEGACY_ID:03d}" in legacy,
        f"docs/architecture_decisions.md: missing tail ADR-{LAST_LEGACY_ID:03d}",
    )

    # Exit-criterion anchors: authority separation and import boundaries are the
    # subjects of ADR-031 and ADR-032 respectively.
    require("ADR-031" in file_by_id, "missing ADR-031 (plugin shell / kernel authority)")
    require("ADR-032" in file_by_id, "missing ADR-032 (component import boundaries)")

    return {
        "schema_version": 1,
        "work_package_id": "A03",
        "attempt_id": "A03-0001",
        "check": "adr_index_check",
        "status": "PASS",
        "exit_criterion_anchors": {
            "plugin_shell_and_kernel_authority_separated": "ADR-031",
            "component_import_boundaries_documented": "ADR-032",
        },
        "index_row_count": len(index_rows),
        "adr_file_count": len(parsed),
        "adr_ids": sorted(file_ids),
        "contiguous_from": numbers[0],
        "contiguous_to": numbers[-1],
        "continues_legacy_last_id": LAST_LEGACY_ID,
        "required_sections": list(REQUIRED_HEADINGS),
        "records": {rec["id"]: rec for rec in parsed},
        "no_dangling_reference": True,
        "no_orphan_file": True,
        "ids_unique": True,
        "ids_contiguous": True,
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_index_and_files_agree() -> None:
    evidence = build_evidence()
    assert evidence["status"] == "PASS"
    assert evidence["no_dangling_reference"] is True
    assert evidence["no_orphan_file"] is True


def test_ids_unique_and_contiguous() -> None:
    evidence = build_evidence()
    assert evidence["ids_unique"] is True
    assert evidence["ids_contiguous"] is True
    assert evidence["contiguous_from"] == evidence["continues_legacy_last_id"] + 1


def test_every_adr_has_required_sections() -> None:
    for record in build_evidence()["records"].values():
        assert set(record["sections_present"]) == set(REQUIRED_HEADINGS)


def test_exit_criterion_anchors_present() -> None:
    anchors = build_evidence()["exit_criterion_anchors"]
    assert anchors["plugin_shell_and_kernel_authority_separated"] == "ADR-031"
    assert anchors["component_import_boundaries_documented"] == "ADR-032"


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A03 adr_index_check")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except AdrError as exc:
        print(f"A03_ADR_INDEX_CHECK_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"A03_ADR_INDEX_CHECK_PASS: wrote {output.relative_to(ROOT.resolve()).as_posix()}")
    else:
        sys.stdout.write(rendered)
        print("A03_ADR_INDEX_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
