#!/usr/bin/env python3
"""Source-material coverage surface for exhaustive RALPH work.

This helper turns user-provided source material into a durable coverage matrix
so Codex must process every section/chunk before claiming completion. It is
intended for implementation specs, papers, PDFs, long markdown files, and
pasted text.
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import managed_manifest
import state_lock


SCHEMA_VERSION = 2
DEFAULT_CHUNK_CHARS = 6000
DEFAULT_CHUNK_LINES = 80
DEFAULT_MAX_SOURCE_BYTES = 50_000_000
DEFAULT_MAX_UNITS = 5000
DEFAULT_OCR_DPI = 200
DEFAULT_OCR_MAX_PAGES = 100
DONE_STATUSES = {
    "implemented",
    "already_covered",
    "equivalent",
    "intentionally_excluded",
    "analyzed",
    "summarized",
    "synthesized",
    "processed",
    "covered",
}
BLOCKING_STATUSES = {"unstarted", "in_progress", "blocked", ""}
VALID_STATUSES = DONE_STATUSES | BLOCKING_STATUSES
PDF_BLOCKED_PREFIX = "[PDF page extraction blocked:"
REQUIREMENT_MARKER_RE = re.compile(
    r"^\s*(?:(?P<explicit>(?:R|REQ|REQUIREMENT|요구사항)\s*[-#:]?\s*\d+(?:\.\d+)*)|"
    r"(?P<number>\d{1,3})|(?P<bullet>[-*+]))[\).:\-\s]+(?P<body>\S.*)$",
    re.IGNORECASE,
)
# `- R1: ...` bullets and `1. R2: ...` numbered items carry their explicit
# requirement token inside the item body; the LEGACY extractor promotes it so
# mode gates that require explicit markers (analysis-mode atomization) see
# `R1` rather than the list marker. Deliberately NOT applied to the writing
# extractor: writing mode already atomizes every block, so promotion there
# would only rewrite marker/text/requirement_hash and invalidate existing
# writing-mode ledgers with zero benefit. Upgrading an OLD analysis ledger
# whose R-bullet source was stored as one reading_unit requires a re-ingest
# (see references/source.md, upgrade note).
_BULLET_EXPLICIT_BODY_RE = re.compile(
    r"^(?P<explicit>(?:R|REQ|REQUIREMENT|요구사항)\s*[-#:]?\s*\d+(?:\.\d+)*)[\).:\-\s]+(?P<body>\S.*)$",
    re.IGNORECASE,
)
ATOMIC_SPLIT_MODES = {"implementation", "writing"}
WRITING_NAVIGATION_LOCATORS = {
    "Contents",
    "Table of Contents",
    "List of Figures",
    "List of Tables",
    "List of Algorithms",
    "Index",
}
WRITING_BIBLIOGRAPHY_LOCATORS = {
    "References",
    "Bibliography",
    "Works Cited",
}
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
HORIZONTAL_RULE_RE = re.compile(
    r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})[ \t]*$"
)
DISPLAY_ENVIRONMENT_RE = re.compile(
    r"\\begin\{(?P<environment>equation|align|alignat|gather|multline|split|cases)(?P<star>\*)?\}"
)
TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass
class SourceText:
    source_id: str
    label: str
    source_type: str
    path: str | None
    text: str
    extraction_status: str
    extraction_notes: str | None = None
    page_count: int | None = None
    sha256: str | None = None
    size_bytes: int | None = None


@dataclass
class AtomicRequirement:
    index: int
    marker: str
    text: str
    line_start: int
    line_end: int
    explicit_marker: bool
    kind: str = "requirement"


SOURCE_UNITS_SUBDIR = ".rah/ralph/source_units"


def safe_unit_path(repo_root: Path, value: str, *, must_exist: bool = True) -> Path:
    """R21 containment: every ledger-supplied unit path resolves through the
    shared gate (absolute/UNC/../link refusal, source_units-root pinning)."""

    return managed_manifest.resolve_contained_file(
        repo_root, value, allowed_subdir=SOURCE_UNITS_SUBDIR, must_exist=must_exist
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ralph_root(repo_root: Path) -> Path:
    return repo_root / ".rah" / "ralph"


def coverage_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "source_requirement_coverage.json"


def coverage_md_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "source_requirement_coverage.md"


def sources_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "source_documents.json"


def source_units_root(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "source_units"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Patch checkpoints and the other machine-readable RAH artifacts must be
    # byte-stable across platforms.  Path.write_text() uses newline=None by
    # default, which rewrites Git's LF diff output to CRLF on Windows and makes
    # an otherwise valid patch require the unsafe ignore-whitespace fallback.
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def excerpt(value: str, limit: int = 700) -> str:
    text = compact_whitespace(value)
    return text[:limit] + ("..." if len(text) > limit else "")


def sanitize_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return slug[:32] or "source"


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "document-start"
    current_lines: list[str] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for line in lines:
        match = heading_pattern.match(line)
        if match and current_lines:
            sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = [line]
        elif match:
            current_title = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))
    return [(title, "\n".join(section_lines).strip()) for title, section_lines in sections if "\n".join(section_lines).strip()]


def split_text_chunks(text: str, *, chunk_chars: int, chunk_lines: int) -> list[tuple[str, str]]:
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    current_chars = 0
    chunk_idx = 1
    for line in lines:
        projected = current_chars + len(line) + 1
        if current and (projected > chunk_chars or len(current) >= chunk_lines):
            chunks.append((f"chunk-{chunk_idx:04d}", "\n".join(current).strip()))
            chunk_idx += 1
            current = []
            current_chars = 0
        current.append(line)
        current_chars += len(line) + 1
    if current:
        chunks.append((f"chunk-{chunk_idx:04d}", "\n".join(current).strip()))
    return [(title, chunk) for title, chunk in chunks if chunk]


def marker_is_explicit_requirement(marker: str) -> bool:
    return bool(re.search(r"(?:^|\b)(?:r|req|requirement)\b|요구사항", marker, re.IGNORECASE))


def classify_writing_unit_role(locator: str | None) -> str | None:
    if not locator:
        return None
    first_segment = re.sub(r"\s+", " ", str(locator).split(" / ", 1)[0]).strip()
    if first_segment in WRITING_NAVIGATION_LOCATORS:
        return "navigation"
    if first_segment in WRITING_BIBLIOGRAPHY_LOCATORS:
        return "bibliography"
    return None


def _has_unescaped_pipe(line: str) -> bool:
    for index, character in enumerate(line):
        if character != "|":
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and line[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return True
    return False


def _split_unescaped_pipes(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    for index, character in enumerate(line):
        if character == "|":
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cells.append("".join(current).strip())
                current = []
                continue
        current.append(character)
    cells.append("".join(current).strip())
    if cells and not cells[0]:
        cells = cells[1:]
    if cells and not cells[-1]:
        cells = cells[:-1]
    return cells


def _is_markdown_table_delimiter(line: str) -> bool:
    if not _has_unescaped_pipe(line):
        return False
    cells = _split_unescaped_pipes(line)
    return bool(cells) and all(TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in cells)


def writing_markdown_line_roles(text: str) -> list[str]:
    """Return deterministic Markdown roles for writing-mode marker filtering."""

    lines = text.splitlines()
    roles = ["normal"] * len(lines)

    fence_character: str | None = None
    fence_length = 0
    for index, line in enumerate(lines):
        opener = FENCE_OPEN_RE.match(line)
        if fence_character is not None:
            roles[index] = "fence"
            stripped = line.lstrip(" ")
            leading_spaces = len(line) - len(stripped)
            if leading_spaces <= 3:
                closing = re.match(rf"^{re.escape(fence_character)}{{{fence_length},}}[ \t]*$", stripped)
                if closing:
                    fence_character = None
                    fence_length = 0
            continue
        if opener:
            fence = opener.group("fence")
            roles[index] = "fence"
            fence_character = fence[0]
            fence_length = len(fence)

    math_close: str | None = None
    for index, line in enumerate(lines):
        if roles[index] == "fence":
            continue
        if math_close is not None:
            roles[index] = "display_math"
            if math_close in line:
                math_close = None
            continue

        dollar_count = line.count("$$")
        if dollar_count:
            roles[index] = "display_math"
            if dollar_count % 2 == 1:
                math_close = "$$"
            continue
        bracket_open = line.find(r"\[")
        if bracket_open >= 0:
            roles[index] = "display_math"
            if line.find(r"\]", bracket_open + 2) < 0:
                math_close = r"\]"
            continue
        environment_match = DISPLAY_ENVIRONMENT_RE.search(line)
        if environment_match:
            roles[index] = "display_math"
            environment = environment_match.group("environment")
            star = environment_match.group("star") or ""
            close_token = rf"\end{{{environment}{star}}}"
            if close_token not in line[environment_match.end() :]:
                math_close = close_token

    for index in range(max(0, len(lines) - 1)):
        if roles[index] != "normal" or roles[index + 1] != "normal":
            continue
        if not _has_unescaped_pipe(lines[index]) or not _is_markdown_table_delimiter(lines[index + 1]):
            continue
        roles[index] = "table"
        roles[index + 1] = "table"
        cursor = index + 2
        while cursor < len(lines) and roles[cursor] == "normal" and _has_unescaped_pipe(lines[cursor]):
            roles[cursor] = "table"
            cursor += 1

    for index, line in enumerate(lines):
        if roles[index] != "normal":
            continue
        if HORIZONTAL_RULE_RE.fullmatch(line):
            roles[index] = "horizontal_rule"
        elif ATX_HEADING_RE.match(line):
            roles[index] = "heading"
    return roles


def _legacy_atomic_requirement_blocks(text: str) -> list[AtomicRequirement]:
    lines = text.splitlines()
    raw_blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, line in enumerate(lines, start=1):
        match = REQUIREMENT_MARKER_RE.match(line)
        if match:
            if current is not None:
                current["line_end"] = line_number - 1
                raw_blocks.append(current)
            marker = match.group("explicit") or match.group("number") or match.group("bullet") or ""
            body = match.group("body").strip()
            explicit = bool(match.group("explicit"))
            if not explicit:
                promoted = _BULLET_EXPLICIT_BODY_RE.match(body)
                if promoted:
                    marker = promoted.group("explicit")
                    body = promoted.group("body").strip()
                    explicit = True
            current = {
                "marker": marker.strip(),
                "explicit_marker": explicit,
                "line_start": line_number,
                "line_end": line_number,
                "lines": [f"{marker.strip()}: {body}" if marker.strip() else body],
            }
            continue
        if current is not None:
            current["lines"].append(line)
            current["line_end"] = line_number
    if current is not None:
        raw_blocks.append(current)

    blocks: list[AtomicRequirement] = []
    for index, block in enumerate(raw_blocks, start=1):
        block_text = "\n".join(str(item) for item in block.get("lines", [])).strip()
        if not block_text:
            continue
        blocks.append(
            AtomicRequirement(
                index=index,
                marker=str(block.get("marker") or f"R{index}"),
                text=block_text,
                line_start=int(block.get("line_start") or 1),
                line_end=int(block.get("line_end") or block.get("line_start") or 1),
                explicit_marker=bool(block.get("explicit_marker")),
            )
        )
    return blocks


def _trim_preamble_candidate(
    entries: list[tuple[int, str, str]],
) -> tuple[int, int, list[str]] | None:
    retained = [(line_number, line, role) for line_number, line, role in entries if role != "horizontal_rule"]
    while retained and not retained[0][1].strip():
        retained.pop(0)
    while retained and not retained[-1][1].strip():
        retained.pop()
    if not retained:
        return None
    substantive = any(line.strip() and role not in {"heading", "horizontal_rule"} for _, line, role in retained)
    if not substantive:
        return None
    return retained[0][0], retained[-1][0], [line for _, line, _ in retained]


def _writing_atomic_requirement_blocks(text: str, *, locator: str | None) -> list[AtomicRequirement]:
    if classify_writing_unit_role(locator):
        return []

    lines = text.splitlines()
    roles = writing_markdown_line_roles(text)
    preamble_entries: list[tuple[int, str, str]] = []
    raw_requirements: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_marker = False

    for line_number, (line, role) in enumerate(zip(lines, roles), start=1):
        match = REQUIREMENT_MARKER_RE.match(line) if role == "normal" else None
        if match:
            seen_marker = True
            if current is not None:
                current["line_end"] = line_number - 1
                raw_requirements.append(current)
            marker = match.group("explicit") or match.group("number") or match.group("bullet") or ""
            body = match.group("body").strip()
            current = {
                "marker": marker.strip(),
                "explicit_marker": bool(match.group("explicit")),
                "line_start": line_number,
                "line_end": line_number,
                "lines": [f"{marker.strip()}: {body}" if marker.strip() else body],
            }
            continue

        if not seen_marker:
            preamble_entries.append((line_number, line, role))
        if current is None:
            continue
        if role == "horizontal_rule":
            current["line_end"] = line_number - 1
            raw_requirements.append(current)
            current = None
            continue
        current["lines"].append(line)
        current["line_end"] = line_number

    if current is not None:
        raw_requirements.append(current)
    if len(raw_requirements) < 2:
        return []

    blocks: list[AtomicRequirement] = []
    preamble = _trim_preamble_candidate(preamble_entries)
    if preamble is not None:
        line_start, line_end, preamble_lines = preamble
        blocks.append(
            AtomicRequirement(
                index=0,
                marker="PREAMBLE",
                text="\n".join(preamble_lines),
                line_start=line_start,
                line_end=line_end,
                explicit_marker=False,
                kind="preamble",
            )
        )

    for index, block in enumerate(raw_requirements, start=1):
        block_text = "\n".join(str(item) for item in block.get("lines", [])).strip()
        if not block_text:
            continue
        blocks.append(
            AtomicRequirement(
                index=index,
                marker=str(block.get("marker") or f"R{index}"),
                text=block_text,
                line_start=int(block.get("line_start") or 1),
                line_end=int(block.get("line_end") or block.get("line_start") or 1),
                explicit_marker=bool(block.get("explicit_marker")),
            )
        )
    return blocks


def extract_atomic_requirement_blocks(
    text: str,
    *,
    coverage_mode: str | None = None,
    locator: str | None = None,
) -> list[AtomicRequirement]:
    if str(coverage_mode or "").strip().lower() == "writing":
        return _writing_atomic_requirement_blocks(text, locator=locator)
    return _legacy_atomic_requirement_blocks(text)


def atomic_requirements_for_mode(
    text: str,
    coverage_mode: str,
    *,
    locator: str | None = None,
) -> list[AtomicRequirement]:
    blocks = extract_atomic_requirement_blocks(text, coverage_mode=coverage_mode, locator=locator)
    real_blocks = [block for block in blocks if block.kind == "requirement"]
    if len(real_blocks) < 2:
        return []
    if coverage_mode == "writing":
        return blocks
    if len(blocks) < 2:
        return []
    explicit_count = sum(1 for block in blocks if block.explicit_marker or marker_is_explicit_requirement(block.marker))
    if coverage_mode in ATOMIC_SPLIT_MODES:
        return blocks
    if explicit_count >= 2:
        return blocks
    return []


def split_pdf_pages(text: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, list[str]]] = []
    current_page: int | None = None
    current_lines: list[str] = []
    page_marker = re.compile(r"^\[PDF page (\d+)\]\s*$")
    for line in text.splitlines():
        match = page_marker.match(line.strip())
        if match:
            if current_page is not None:
                pages.append((current_page, current_lines))
            current_page = int(match.group(1))
            current_lines = []
            continue
        current_lines.append(line)
    if current_page is not None:
        pages.append((current_page, current_lines))
    return [
        (page_num, "\n".join(page_lines).strip())
        for page_num, page_lines in pages
        if "\n".join(page_lines).strip()
    ]


def page_has_readable_text(value: str) -> bool:
    content_lines = [
        line
        for line in value.splitlines()
        if not line.strip().startswith(PDF_BLOCKED_PREFIX)
    ]
    return bool(compact_whitespace("\n".join(content_lines)))


def pdf_has_readable_text(value: str) -> bool:
    pages = split_pdf_pages(value)
    if pages:
        return any(page_has_readable_text(page_text) for _, page_text in pages)
    return page_has_readable_text(value)


def pdf_has_blocked_pages(value: str) -> bool:
    return PDF_BLOCKED_PREFIX in value


def pdf_page_is_blocked(value: str) -> bool:
    return PDF_BLOCKED_PREFIX in value and not page_has_readable_text(value)


def format_pdf_pages(page_texts: list[tuple[int, str]], *, missing_note: str | None = None) -> tuple[str, list[int]]:
    blocks: list[str] = []
    missing_pages: list[int] = []
    for page_num, raw_text in page_texts:
        page_text = (raw_text or "").strip()
        if page_text:
            blocks.append(f"\n\n[PDF page {page_num}]\n{page_text}")
            continue
        if missing_note:
            missing_pages.append(page_num)
            blocks.append(f"\n\n[PDF page {page_num}]\n{PDF_BLOCKED_PREFIX} {missing_note}]")
    return "\n".join(blocks), missing_pages


def merge_pdf_text_with_ocr(primary_text: str, ocr_text: str) -> str:
    primary_pages = {page_num: page_text for page_num, page_text in split_pdf_pages(primary_text)}
    ocr_pages = {page_num: page_text for page_num, page_text in split_pdf_pages(ocr_text)}
    if not primary_pages:
        return ocr_text
    if not ocr_pages:
        if not pdf_has_readable_text(primary_text):
            return ocr_text
        if pdf_has_blocked_pages(primary_text) and page_has_readable_text(ocr_text):
            return ocr_text
        return primary_text
    merged: list[tuple[int, str]] = []
    for page_num in sorted(set(primary_pages) | set(ocr_pages)):
        primary_page = primary_pages.get(page_num, "")
        ocr_page = ocr_pages.get(page_num, "")
        if page_has_readable_text(primary_page) and not pdf_page_is_blocked(primary_page):
            merged.append((page_num, primary_page))
        elif page_has_readable_text(ocr_page):
            merged.append((page_num, ocr_page))
        else:
            merged.append((page_num, primary_page or ocr_page))
    return format_pdf_pages(merged, missing_note=None)[0]


def split_source_units(source: SourceText, *, chunk_chars: int, chunk_lines: int) -> list[tuple[str, str, str]]:
    if not source.text.strip():
        return [("extraction-blocker", "extraction-blocker", source.extraction_notes or "No extractable text was available.")]
    if source.source_type in {"markdown", "md"}:
        sections = split_markdown_sections(source.text)
        units: list[tuple[str, str, str]] = []
        for section_idx, (title, section_text) in enumerate(sections, start=1):
            if len(section_text) <= chunk_chars:
                units.append((f"S{section_idx:04d}", title, section_text))
                continue
            for chunk_idx, (chunk_title, chunk_text) in enumerate(
                split_text_chunks(section_text, chunk_chars=chunk_chars, chunk_lines=chunk_lines),
                start=1,
            ):
                units.append((f"S{section_idx:04d}-C{chunk_idx:03d}", f"{title} / {chunk_title}", chunk_text))
        return units
    if source.source_type == "pdf":
        pages = split_pdf_pages(source.text)
        if pages:
            units: list[tuple[str, str, str]] = []
            for page_num, page_text in pages:
                if len(page_text) <= chunk_chars:
                    units.append((f"P{page_num:04d}", f"PDF page {page_num}", page_text))
                    continue
                for chunk_idx, (chunk_title, chunk_text) in enumerate(
                    split_text_chunks(page_text, chunk_chars=chunk_chars, chunk_lines=chunk_lines),
                    start=1,
                ):
                    units.append((f"P{page_num:04d}-C{chunk_idx:03d}", f"PDF page {page_num} / {chunk_title}", chunk_text))
            return units
    return [
        (f"C{idx:04d}", title, chunk)
        for idx, (title, chunk) in enumerate(
            split_text_chunks(source.text, chunk_chars=chunk_chars, chunk_lines=chunk_lines),
            start=1,
        )
    ]


def unit_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def unit_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def contract_canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def contract_hash_of(value: Any) -> str:
    return hashlib.sha256(contract_canonical_json(value).encode("utf-8")).hexdigest()


def coverage_contract_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Requirement-identity view of a coverage payload.

    Mutable progress fields (row status including intentionally_excluded, evidence,
    validation, notes, timestamps, excerpt text) are excluded so working a row never
    invalidates downstream atoms/PRD/waiver artifacts. Text identity is carried by
    text_sha256/excerpt_hash/requirement_hash, so redaction mode does not change the
    hash either.
    """
    manifest = payload.get("source_unit_manifest") if isinstance(payload, dict) else {}
    units = manifest.get("units") if isinstance(manifest, dict) else []
    projected_units = [
        {
            "unit_id": unit.get("unit_id"),
            "source_id": unit.get("source_id"),
            "excerpt_hash": unit.get("excerpt_hash"),
            "text_sha256": unit.get("text_sha256"),
            "extraction_status": unit.get("extraction_status"),
        }
        for unit in (units or [])
        if isinstance(unit, dict)
    ]
    projected_rows = []
    for row in rows_from_payload(payload):
        if not isinstance(row, dict):
            continue
        span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
        projected_rows.append(
            {
                "requirement_id": row.get("requirement_id"),
                "source_unit_id": row.get("source_unit_id"),
                "coverage_type": row.get("coverage_type"),
                "requirement_type": row.get("requirement_type"),
                "source_span": {
                    "unit_id": span.get("unit_id"),
                    "excerpt_hash": span.get("excerpt_hash"),
                    "line_start": span.get("line_start"),
                    "line_end": span.get("line_end"),
                    "requirement_index": span.get("requirement_index"),
                    "requirement_hash": span.get("requirement_hash"),
                },
            }
        )
    return {
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
        "coverage_mode": payload.get("coverage_mode") if isinstance(payload, dict) else None,
        "units": projected_units,
        "rows": projected_rows,
    }


def coverage_contract_hash(payload: dict[str, Any]) -> str:
    return contract_hash_of(coverage_contract_projection(payload))


def extract_pdf_with_python(path: Path) -> tuple[str, int | None, str | None]:
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name)
            reader = module.PdfReader(str(path))
            pages: list[tuple[int, str]] = []
            for idx, page in enumerate(reader.pages, start=1):
                extracted = page.extract_text() or ""
                pages.append((idx, extracted))
            text, missing_pages = format_pdf_pages(pages, missing_note="no embedded text on this page")
            note = f"extracted_with_{module_name}"
            if missing_pages:
                note += f"; missing_text_pages={len(missing_pages)}"
            return text, len(reader.pages), note
        except Exception:
            continue
    return "", None, None


def load_pymupdf_module() -> Any | None:
    for module_name in ("pymupdf", "fitz"):
        try:
            return __import__(module_name)
        except Exception:
            continue
    return None


def extract_pdf_with_pymupdf(path: Path) -> tuple[str, int | None, str | None]:
    module = load_pymupdf_module()
    if module is None:
        return "", None, None
    doc = None
    try:
        doc = module.open(str(path))
        pages: list[tuple[int, str]] = []
        for idx, page in enumerate(doc, start=1):
            pages.append((idx, page.get_text("text") or ""))
        text, missing_pages = format_pdf_pages(pages, missing_note="no embedded text on this page")
        note = "extracted_with_pymupdf"
        if missing_pages:
            note += f"; missing_text_pages={len(missing_pages)}"
        return text, len(doc), note
    except Exception as exc:
        return "", None, f"pymupdf_failed: {str(exc)[:300]}"
    finally:
        if doc is not None:
            doc.close()


def extract_pdf_with_pdftotext(path: Path) -> tuple[str, int | None, str | None]:
    tool = shutil.which("pdftotext")
    if not tool:
        return "", None, None
    completed = subprocess.run([tool, "-layout", str(path), "-"], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        return "", None, f"pdftotext_failed: {completed.stderr[:300]}"
    raw_text = completed.stdout or ""
    if "\f" not in raw_text:
        return raw_text, None, "extracted_with_pdftotext"
    page_parts = raw_text.split("\f")
    if page_parts and not page_parts[-1].strip():
        page_parts = page_parts[:-1]
    pages = [(idx, page_text) for idx, page_text in enumerate(page_parts, start=1)]
    text, missing_pages = format_pdf_pages(pages, missing_note="pdftotext produced no text on this page")
    note = "extracted_with_pdftotext"
    if missing_pages:
        note += f"; missing_text_pages={len(missing_pages)}"
    return text, len(pages), note


def extract_pdf_with_pymupdf_ocr(path: Path, *, lang: str, max_pages: int, dpi: int, tessdata: str | None) -> tuple[str, int | None, str | None]:
    module = load_pymupdf_module()
    if module is None:
        return "", None, "pymupdf_unavailable_for_ocr"
    doc = None
    try:
        doc = module.open(str(path))
        page_count = len(doc)
        if max_pages > 0 and page_count > max_pages:
            return "", page_count, f"ocr_skipped_page_count_{page_count}_exceeds_max_{max_pages}"
        page_texts: list[tuple[int, str]] = []
        failed_pages: list[int] = []
        for idx, page in enumerate(doc, start=1):
            if not hasattr(page, "get_textpage_ocr"):
                return "", page_count, "pymupdf_ocr_api_unavailable"
            try:
                ocr_kwargs: dict[str, Any] = {"language": lang, "dpi": dpi, "full": True}
                if tessdata:
                    ocr_kwargs["tessdata"] = tessdata
                text_page = page.get_textpage_ocr(**ocr_kwargs)
                page_texts.append((idx, page.get_text("text", textpage=text_page) or ""))
            except Exception as exc:
                failed_pages.append(idx)
                page_texts.append((idx, f"{PDF_BLOCKED_PREFIX} pymupdf_ocr_failed: {str(exc)[:300]}]"))
        text, missing_pages = format_pdf_pages(page_texts, missing_note="PyMuPDF OCR produced no text on this page")
        note = f"ocr_with_pymupdf_tesseract; lang={lang}; dpi={dpi}"
        if tessdata:
            note += "; tessdata=custom"
        if missing_pages:
            note += f"; empty_ocr_pages={len(missing_pages)}"
        if failed_pages:
            note += f"; failed_ocr_pages={len(failed_pages)}"
        return text, page_count, note
    except Exception as exc:
        return "", None, f"pymupdf_ocr_failed: {str(exc)[:300]}"
    finally:
        if doc is not None:
            doc.close()


def extract_pdf_with_tesseract(path: Path, *, lang: str, max_pages: int, dpi: int, tessdata: str | None) -> tuple[str, int | None, str | None]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", None, "tesseract_unavailable"
    module = load_pymupdf_module()
    if module is None:
        return "", None, "pymupdf_unavailable_for_ocr_rendering"
    doc = None
    try:
        doc = module.open(str(path))
        page_count = len(doc)
        if max_pages > 0 and page_count > max_pages:
            return "", page_count, f"ocr_skipped_page_count_{page_count}_exceeds_max_{max_pages}"
        page_texts: list[tuple[int, str]] = []
        failed_pages: list[int] = []
        env = os.environ.copy()
        if tessdata:
            env["TESSDATA_PREFIX"] = tessdata
        with tempfile.TemporaryDirectory(prefix="rah_pdf_ocr_") as temp_dir:
            temp_root = Path(temp_dir)
            for idx, page in enumerate(doc, start=1):
                image_path = temp_root / f"page-{idx:04d}.png"
                pixmap = page.get_pixmap(dpi=dpi)
                pixmap.save(str(image_path))
                completed = subprocess.run(
                    [tesseract, str(image_path), "stdout", "-l", lang],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                    env=env,
                )
                if completed.returncode == 0:
                    page_texts.append((idx, completed.stdout or ""))
                else:
                    failed_pages.append(idx)
                    page_texts.append((idx, f"{PDF_BLOCKED_PREFIX} tesseract_failed: {completed.stderr[:300]}]"))
        text, missing_pages = format_pdf_pages(page_texts, missing_note="OCR produced no text on this page")
        note = f"ocr_with_tesseract; lang={lang}; dpi={dpi}"
        if tessdata:
            note += "; tessdata=custom"
        if missing_pages:
            note += f"; empty_ocr_pages={len(missing_pages)}"
        if failed_pages:
            note += f"; failed_ocr_pages={len(failed_pages)}"
        return text, page_count, note
    except subprocess.TimeoutExpired:
        return "", len(doc) if doc is not None else None, "tesseract_timeout"
    except Exception as exc:
        return "", None, f"tesseract_ocr_failed: {str(exc)[:300]}"
    finally:
        if doc is not None:
            doc.close()


def combine_notes(notes: list[str | None]) -> str | None:
    cleaned = [note for note in notes if note]
    return " | ".join(cleaned) if cleaned else None


def default_ocr_tessdata() -> str | None:
    for value in (os.environ.get("RAH_OCR_TESSDATA"), os.environ.get("TESSDATA_PREFIX")):
        if value:
            path = Path(value).expanduser()
            if path.exists():
                return str(path)
    local_path = Path.home() / ".codex" / "tools" / "tessdata"
    if (local_path / "eng.traineddata").exists():
        return str(local_path)
    return None


def read_source_file(
    path: Path,
    source_id: str,
    *,
    ocr_mode: str = "auto",
    ocr_lang: str = "eng",
    ocr_max_pages: int = DEFAULT_OCR_MAX_PAGES,
    ocr_dpi: int = DEFAULT_OCR_DPI,
    ocr_tessdata: str | None = None,
) -> SourceText:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    source_type = {
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".rst": "text",
        ".csv": "text",
        ".tsv": "text",
        ".pdf": "pdf",
    }.get(suffix, "text")
    if suffix == ".pdf":
        notes: list[str | None] = []
        text = ""
        page_count: int | None = None
        blocker_text = ""
        if ocr_mode != "force":
            for extractor in (extract_pdf_with_python, extract_pdf_with_pymupdf, extract_pdf_with_pdftotext):
                extracted_text, extracted_page_count, note = extractor(path)
                notes.append(note)
                if extracted_page_count is not None:
                    page_count = extracted_page_count
                if extracted_text.strip() and not blocker_text:
                    blocker_text = extracted_text
                if pdf_has_readable_text(extracted_text):
                    text = merge_pdf_text_with_ocr(text, extracted_text) if text else extracted_text
                    if not pdf_has_blocked_pages(text):
                        break
        if ocr_mode in {"auto", "force"} and (ocr_mode == "force" or not pdf_has_readable_text(text) or pdf_has_blocked_pages(text)):
            ocr_text, ocr_page_count, ocr_note = extract_pdf_with_pymupdf_ocr(
                path,
                lang=ocr_lang,
                max_pages=ocr_max_pages,
                dpi=ocr_dpi,
                tessdata=ocr_tessdata,
            )
            notes.append(ocr_note)
            if ocr_page_count is not None:
                page_count = ocr_page_count
            if not pdf_has_readable_text(ocr_text):
                ocr_text, ocr_page_count, ocr_note = extract_pdf_with_tesseract(
                    path,
                    lang=ocr_lang,
                    max_pages=ocr_max_pages,
                    dpi=ocr_dpi,
                    tessdata=ocr_tessdata,
                )
                notes.append(ocr_note)
                if ocr_page_count is not None:
                    page_count = ocr_page_count
            if pdf_has_readable_text(ocr_text):
                text = merge_pdf_text_with_ocr(text, ocr_text) if text else ocr_text
        if not pdf_has_readable_text(text):
            return SourceText(
                source_id=source_id,
                label=path.name,
                source_type="pdf",
                path=str(path),
                text=blocker_text,
                extraction_status="blocked",
                extraction_notes=combine_notes(notes)
                or "PDF text extraction unavailable; install PyMuPDF/pypdf/pdftotext and Tesseract OCR, or provide a text export.",
                page_count=page_count,
                sha256=sha256_bytes(data),
                size_bytes=len(data),
            )
        extraction_status = "partial" if pdf_has_blocked_pages(text) else "extracted"
        return SourceText(
            source_id=source_id,
            label=path.name,
            source_type="pdf",
            path=str(path),
            text=text,
            extraction_status=extraction_status,
            extraction_notes=combine_notes(notes),
            page_count=page_count,
            sha256=sha256_bytes(data),
            size_bytes=len(data),
        )
    try:
        text = data.decode("utf-8-sig")
        note = "utf-8"
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        note = "utf-8-with-replacement"
    return SourceText(
        source_id=source_id,
        label=path.name,
        source_type=source_type,
        path=str(path),
        text=text,
        extraction_status="extracted",
        extraction_notes=note,
        sha256=sha256_bytes(data),
        size_bytes=len(data),
    )


def source_records(
    sources: list[SourceText],
    repo_root: Path,
    *,
    coverage_mode: str,
    task: str | None,
    redact_excerpts: bool,
) -> dict[str, Any]:
    def source_path_record(source: SourceText) -> tuple[str | None, bool]:
        if not source.path:
            return None, False
        source_path = Path(source.path)
        try:
            return str(source_path.resolve().relative_to(repo_root)).replace("\\", "/"), False
        except ValueError:
            return None, True

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "coverage_mode": coverage_mode,
        "task": task,
        "source_units_dir": relative(source_units_root(repo_root), repo_root),
        "tracking_policy": {
            "source_units_local_only": True,
            "excerpts_redacted_for_tracking": redact_excerpts,
            "raw_text_location": relative(source_units_root(repo_root), repo_root),
        },
        "sources": [
            {
                "source_id": source.source_id,
                "label": source.label,
                "source_type": source.source_type,
                "path": source_path_record(source)[0],
                "external_path_redacted": source_path_record(source)[1],
                "sha256": source.sha256,
                "size_bytes": source.size_bytes,
                "page_count": source.page_count,
                "extraction_status": source.extraction_status,
                "extraction_notes": source.extraction_notes,
                "privacy_tracking": "derived-coverage-only",
            }
            for source in sources
        ],
    }


def unit_extraction_status(source: SourceText, unit_text: str) -> str:
    if source.extraction_status == "blocked" or pdf_page_is_blocked(unit_text):
        return "blocked"
    return source.extraction_status


def row_status_for_unit(source: SourceText, unit_text: str) -> str:
    return "blocked" if unit_extraction_status(source, unit_text) == "blocked" else "unstarted"


def semantic_contract_required_for_mode(coverage_mode: str) -> bool:
    return coverage_mode == "implementation"


def row_source_excerpt(text: str, *, redact_excerpts: bool) -> str:
    if redact_excerpts:
        return "[redacted; see source_unit_text_path locally and excerpt_hash for identity]"
    return excerpt(text)


def atomic_requirement_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def expected_coverage_row_ids_for_unit(
    unit_id: str,
    unit_text: str,
    coverage_mode: str,
    *,
    locator: str | None = None,
) -> list[str]:
    atomic_requirements = atomic_requirements_for_mode(unit_text, coverage_mode, locator=locator)
    if atomic_requirements:
        return [f"{unit_id}-R{atomic.index:03d}" for atomic in atomic_requirements]
    return [unit_id]


def validate_unit_coverage_rows(
    unit_id: str,
    unit_text: str,
    coverage_mode: str,
    locator: str | None,
    rows: list[dict[str, Any]],
) -> list[str]:
    """Validate immutable row identity for one source unit.

    This pure validator is shared with RALPH readiness so source validation and
    completion readiness cannot disagree about writing-mode atom boundaries.
    """

    issues: list[str] = []
    actual_ids = [
        str(row.get("requirement_id") or row.get("id") or "").strip()
        for row in rows
        if isinstance(row, dict)
    ]
    expected_ids = expected_coverage_row_ids_for_unit(
        unit_id,
        unit_text,
        coverage_mode,
        locator=locator,
    )
    if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(expected_ids):
        issues.append(
            f"expected row IDs {expected_ids!r}, found {actual_ids!r}"
        )

    unit_role = classify_writing_unit_role(locator) if coverage_mode == "writing" else None
    atomic_requirements = atomic_requirements_for_mode(unit_text, coverage_mode, locator=locator)
    if atomic_requirements:
        expected_by_id = {
            f"{unit_id}-R{atomic.index:03d}": atomic
            for atomic in atomic_requirements
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("requirement_id") or row.get("id") or "").strip()
            atomic = expected_by_id.get(row_id)
            if atomic is None:
                continue
            span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
            expected_hash = atomic_requirement_hash(atomic.text)
            expected_locator = f"{locator} / {atomic.marker}" if locator else atomic.marker
            if str(row.get("coverage_type") or "") != "atomic_requirement":
                issues.append(f"{row_id}: coverage_type is not atomic_requirement")
            if str(row.get("requirement_type") or "") != "atomic_requirement":
                issues.append(f"{row_id}: requirement_type is not atomic_requirement")
            if str(row.get("locator") or "") != expected_locator:
                issues.append(f"{row_id}: locator does not match atomizer output")
            if str(row.get("requirement_text") or "") != atomic.text:
                issues.append(f"{row_id}: requirement_text does not match atomizer output")
            if span.get("requirement_id") != row_id:
                issues.append(f"{row_id}: source_span.requirement_id mismatch")
            if span.get("requirement_index") != atomic.index:
                issues.append(f"{row_id}: source_span.requirement_index mismatch")
            if span.get("requirement_hash") != expected_hash:
                issues.append(f"{row_id}: source_span.requirement_hash mismatch")
            if span.get("line_start") != atomic.line_start or span.get("line_end") != atomic.line_end:
                issues.append(f"{row_id}: source_span line range does not match atomizer output")

        if coverage_mode == "writing":
            roles = writing_markdown_line_roles(unit_text)
            covered = [0] * len(roles)
            for atomic in atomic_requirements:
                for line_number in range(atomic.line_start, atomic.line_end + 1):
                    if 1 <= line_number <= len(covered) and roles[line_number - 1] != "horizontal_rule":
                        covered[line_number - 1] += 1
            for line_number, (line, role, count) in enumerate(
                zip(unit_text.splitlines(), roles, covered),
                start=1,
            ):
                if not line.strip() or role in {"heading", "horizontal_rule"}:
                    continue
                if count != 1:
                    issues.append(
                        f"line {line_number}: substantive source line has coverage count {count}"
                    )
    else:
        expected_type = (
            "reading_unit"
            if coverage_mode in {"analysis", "paper", "summary", "synthesis"} or unit_role
            else "requirement_or_reading_unit"
        )
        if len(rows) == 1 and isinstance(rows[0], dict):
            row = rows[0]
            row_id = str(row.get("requirement_id") or row.get("id") or "").strip()
            if row_id == unit_id:
                if str(row.get("coverage_type") or "") != expected_type:
                    issues.append(f"{row_id}: coverage_type is not {expected_type}")
                if str(row.get("requirement_type") or "") != expected_type:
                    issues.append(f"{row_id}: requirement_type is not {expected_type}")
                if unit_role and str(row.get("unit_role") or "") != unit_role:
                    issues.append(f"{row_id}: unit_role is not {unit_role}")
    return issues


def build_unit_coverage_rows(
    source_unit: dict[str, Any],
    unit_text: str,
    *,
    coverage_mode: str,
    task: str | None,
    redact_excerpts: bool,
    row_status: str,
) -> list[dict[str, Any]]:
    """Build the coverage rows for one source unit from its manifest entry.

    Single canonical row shape shared by ingest (`coverage_rows_and_units`)
    and `migrate` (ledger healing), so a healed ledger can never fork from
    the identity a fresh ingest would produce.
    """

    base_requirement_id = str(source_unit["unit_id"])
    title = source_unit.get("locator")
    extraction_status = str(source_unit.get("extraction_status") or "")
    extraction_notes = source_unit.get("extraction_notes")
    unit_role = source_unit.get("unit_role")
    relative_text_path = str(source_unit.get("text_path") or "")
    unit_excerpt = row_source_excerpt(unit_text, redact_excerpts=redact_excerpts)
    atomic_requirements = (
        []
        if extraction_status == "blocked"
        else atomic_requirements_for_mode(unit_text, coverage_mode, locator=title)
    )
    row_specs: list[dict[str, Any]]
    if atomic_requirements:
        row_specs = [
            {
                "requirement_id": f"{base_requirement_id}-R{atomic.index:03d}",
                "coverage_type": "atomic_requirement",
                "requirement_type": "atomic_requirement",
                "locator": f"{title} / {atomic.marker}" if title else atomic.marker,
                "requirement_text": atomic.text,
                "source_excerpt": row_source_excerpt(atomic.text, redact_excerpts=redact_excerpts),
                "line_start": atomic.line_start,
                "line_end": atomic.line_end,
                "requirement_index": atomic.index,
                "requirement_hash": atomic_requirement_hash(atomic.text),
            }
            for atomic in atomic_requirements
        ]
    else:
        reading_unit = coverage_mode in {"analysis", "paper", "summary", "synthesis"} or bool(unit_role)
        row_specs = [
            {
                "requirement_id": base_requirement_id,
                "coverage_type": "reading_unit" if reading_unit else "requirement_or_reading_unit",
                "requirement_type": "reading_unit" if reading_unit else "requirement_or_reading_unit",
                "locator": title,
                "requirement_text": default_task_for_mode(coverage_mode),
                "source_excerpt": unit_excerpt,
                "line_start": 1,
                "line_end": max(1, len(unit_text.splitlines())),
                "requirement_index": None,
                "requirement_hash": None,
            }
        ]
    semantic_required = semantic_contract_required_for_mode(coverage_mode)
    rows: list[dict[str, Any]] = []
    for spec in row_specs:
        source_span = {
            "source_id": source_unit.get("source_id"),
            "unit_id": base_requirement_id,
            "locator": spec["locator"],
            "excerpt_hash": source_unit.get("excerpt_hash"),
            "line_start": spec["line_start"],
            "line_end": spec["line_end"],
        }
        if spec["requirement_index"] is not None:
            source_span["requirement_id"] = spec["requirement_id"]
            source_span["requirement_index"] = spec["requirement_index"]
            source_span["requirement_hash"] = spec["requirement_hash"]
        rows.append(
            {
                "requirement_id": spec["requirement_id"],
                "source_document": source_unit.get("source_label"),
                "source_id": source_unit.get("source_id"),
                "source_label": source_unit.get("source_label"),
                "source_type": source_unit.get("source_type"),
                "source_section": title,
                "source_unit_id": base_requirement_id,
                "source_unit_text_path": relative_text_path,
                "source_span": source_span,
                "coverage_mode": coverage_mode,
                "coverage_type": spec["coverage_type"],
                "requirement_type": spec["requirement_type"],
                "locator": spec["locator"],
                "section": title,
                "requirement_text": spec["requirement_text"],
                "source_excerpt": spec["source_excerpt"],
                "task": task or default_task_for_mode(coverage_mode),
                "status": row_status,
                "evidence": [],
                "source_evidence_required": True,
                "source_evidence": [],
                "validation": [],
                "source_validation": [],
                "semantic_contract_required": semantic_required,
                "semantic_validation": [],
                "negative_tests": [],
                "provenance_evidence_required": semantic_required,
                "provenance_evidence": [],
                "notes": extraction_notes if extraction_status == "blocked" else "",
                "char_count": len(str(spec["requirement_text"])),
                "line_count": max(1, spec["line_end"] - spec["line_start"] + 1),
            }
        )
        if unit_role:
            rows[-1]["unit_role"] = unit_role
    return rows


def coverage_rows_and_units(
    sources: list[SourceText],
    *,
    repo_root: Path,
    coverage_mode: str,
    task: str | None,
    chunk_chars: int,
    chunk_lines: int,
    redact_excerpts: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    for source_idx, source in enumerate(sources, start=1):
        for unit_idx, (unit_id, title, unit_text) in enumerate(
            split_source_units(source, chunk_chars=chunk_chars, chunk_lines=chunk_lines),
            start=1,
        ):
            base_requirement_id = f"SRC{source_idx:03d}-{unit_id}"
            text_path = source_units_root(repo_root) / f"{base_requirement_id}.txt"
            relative_text_path = relative(text_path, repo_root)
            extraction_status = unit_extraction_status(source, unit_text)
            extraction_notes = source.extraction_notes
            unit_excerpt = row_source_excerpt(unit_text, redact_excerpts=redact_excerpts)
            unit_role = classify_writing_unit_role(title) if coverage_mode == "writing" else None
            atomic_requirements = (
                []
                if extraction_status == "blocked"
                else atomic_requirements_for_mode(unit_text, coverage_mode, locator=title)
            )
            source_unit = {
                "unit_id": base_requirement_id,
                "source_id": source.source_id,
                "source_label": source.label,
                "source_type": source.source_type,
                "locator": title,
                "unit_index": unit_idx,
                "atomic_requirement_count": len(atomic_requirements),
                "char_count": len(unit_text),
                "line_count": len(unit_text.splitlines()),
                "excerpt_hash": unit_hash(unit_text),
                "excerpt": unit_excerpt,
                "text_path": relative_text_path,
                "text_sha256": unit_text_sha256(unit_text),
                "extraction_status": extraction_status,
                "extraction_notes": extraction_notes,
                "_source_text": unit_text,
            }
            if unit_role:
                source_unit["unit_role"] = unit_role
            units.append(source_unit)
            rows.extend(
                build_unit_coverage_rows(
                    source_unit,
                    unit_text,
                    coverage_mode=coverage_mode,
                    task=task,
                    redact_excerpts=redact_excerpts,
                    row_status=row_status_for_unit(source, unit_text),
                )
            )
    return rows, units


def default_task_for_mode(mode: str) -> str:
    if mode in {"analysis", "paper"}:
        return "Read this unit fully, extract claims/methods/evidence/limitations, and incorporate it into the final analysis."
    if mode == "summary":
        return "Read this unit fully and summarize all important points without omissions."
    if mode == "synthesis":
        return "Read this unit fully and synthesize its claims into the cross-source answer."
    if mode == "writing":
        return "Read this unit fully and apply all relevant constraints to the writing task."
    return "Read this unit fully and implement or verify every actionable requirement."


def render_coverage_md(payload: dict[str, Any]) -> str:
    rows = payload.get("requirements", [])
    lines = [
        "# Source Requirement Coverage",
        "",
        f"- generated_at_utc: `{payload.get('generated_at_utc')}`",
        f"- coverage_mode: `{payload.get('coverage_mode')}`",
        f"- task: {payload.get('task') or 'not specified'}",
        f"- row_count: `{len(rows) if isinstance(rows, list) else 0}`",
        "",
        "| ID | Source | Locator | Text | Status | Evidence | Source Evidence | Validation | Semantic | Provenance | Negative |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if isinstance(rows, list):
        for row in rows:
            evidence = row.get("evidence")
            source_evidence = row.get("source_evidence")
            validation = row.get("validation")
            semantic_validation = row.get("semantic_validation")
            provenance_evidence = row.get("provenance_evidence")
            negative_tests = row.get("negative_tests")
            evidence_count = len(evidence) if isinstance(evidence, list) else int(bool(evidence))
            source_evidence_count = len(source_evidence) if isinstance(source_evidence, list) else int(bool(source_evidence))
            validation_count = len(validation) if isinstance(validation, list) else int(bool(validation))
            semantic_count = len(semantic_validation) if isinstance(semantic_validation, list) else int(bool(semantic_validation))
            provenance_count = len(provenance_evidence) if isinstance(provenance_evidence, list) else int(bool(provenance_evidence))
            negative_count = len(negative_tests) if isinstance(negative_tests, list) else int(bool(negative_tests))
            lines.append(
                "| {id} | {source} | {locator} | {text_path} | {status} | {evidence} | {source_evidence} | {validation} | {semantic} | {provenance} | {negative} |".format(
                    id=str(row.get("requirement_id") or ""),
                    source=str(row.get("source_label") or row.get("source_id") or "").replace("|", "\\|"),
                    locator=str(row.get("locator") or "").replace("|", "\\|")[:120],
                    text_path=str(row.get("source_unit_text_path") or "").replace("|", "\\|"),
                    status=str(row.get("status") or ""),
                    evidence=evidence_count,
                    source_evidence=source_evidence_count,
                    validation=validation_count,
                    semantic=semantic_count,
                    provenance=provenance_count,
                    negative=negative_count,
                )
            )
    lines.append("")
    return "\n".join(lines)


def build_coverage_payload(
    sources: list[SourceText],
    *,
    repo_root: Path,
    coverage_mode: str,
    task: str | None,
    chunk_chars: int,
    chunk_lines: int,
    redact_excerpts: bool,
) -> dict[str, Any]:
    rows, units = coverage_rows_and_units(
        sources,
        repo_root=repo_root,
        coverage_mode=coverage_mode,
        task=task,
        chunk_chars=chunk_chars,
        chunk_lines=chunk_lines,
        redact_excerpts=redact_excerpts,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "coverage_mode": coverage_mode,
        "task": task,
        "source_unit_manifest": {
            "total_units": len(units),
            "processed_unit_count": 0,
            "text_dir": relative(source_units_root(repo_root), repo_root),
            "units": units,
        },
        "completion_contract": {
            "must_process_every_row": True,
            "done_statuses": sorted(DONE_STATUSES),
            "row_requires_evidence": True,
            "row_requires_source_evidence": True,
            "evidence_must_anchor_to_source_unit": True,
            "row_requires_validation": True,
            "implementation_row_requires_semantic_validation": True,
            "implementation_row_requires_provenance_evidence": True,
            "implementation_row_requires_negative_test": True,
            "final_answer_requires_all_rows_ready": True,
            "evidence_contract": "Every done row must carry evidence anchored to its original source_unit_id, source_unit_text_path, source_span, and excerpt_hash so no original source unit can be skipped silently.",
            "semantic_contract": "Implementation rows must prove the intended algorithm/data path, not only the presence of labels, files, columns, or output names.",
            "source_text_policy": "raw source text stays in ignored source_units; tracked coverage JSON may use redacted excerpts",
            "excerpts_redacted_for_tracking": redact_excerpts,
        },
        "source_documents_path": relative(sources_path(repo_root), repo_root),
        "requirements": rows,
    }


def write_source_unit_texts(repo_root: Path, coverage_payload: dict[str, Any]) -> None:
    manifest = coverage_payload.get("source_unit_manifest") if isinstance(coverage_payload, dict) else {}
    units = manifest.get("units") if isinstance(manifest, dict) else []
    if not isinstance(units, list):
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        text = str(unit.pop("_source_text", ""))
        text_path_value = str(unit.get("text_path") or "").strip()
        if not text_path_value:
            continue
        try:
            text_path = safe_unit_path(repo_root, text_path_value, must_exist=False)
        except managed_manifest.ManifestError as exc:
            raise SystemExit(f"unsafe source unit path refused: {exc}")
        write_text(text_path, text)


def ingest(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise SystemExit(f"Missing repo root: {repo_root}")
    if args.ocr_dpi <= 0:
        raise SystemExit("--ocr-dpi must be positive.")
    if args.ocr_max_pages < 0:
        raise SystemExit("--ocr-max-pages must be 0 or greater.")
    sources: list[SourceText] = []
    for idx, source_value in enumerate(args.source or [], start=1):
        path = Path(source_value).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if not path.exists() or not path.is_file():
            raise SystemExit(f"Missing source file: {path}")
        if path.stat().st_size > args.max_source_bytes:
            raise SystemExit(f"Source file exceeds --max-source-bytes ({args.max_source_bytes}): {path}")
        sources.append(
            read_source_file(
                path,
                f"SRC{idx:03d}",
                ocr_mode=args.ocr,
                ocr_lang=args.ocr_lang,
                ocr_max_pages=args.ocr_max_pages,
                ocr_dpi=args.ocr_dpi,
                ocr_tessdata=args.ocr_tessdata,
            )
        )
    if args.text_file:
        path = Path(args.text_file).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if not path.exists() or not path.is_file():
            raise SystemExit(f"Missing text file: {path}")
        if path.stat().st_size > args.max_source_bytes:
            raise SystemExit(f"Text file exceeds --max-source-bytes ({args.max_source_bytes}): {path}")
        sources.append(
            read_source_file(
                path,
                f"SRC{len(sources)+1:03d}",
                ocr_mode=args.ocr,
                ocr_lang=args.ocr_lang,
                ocr_max_pages=args.ocr_max_pages,
                ocr_dpi=args.ocr_dpi,
                ocr_tessdata=args.ocr_tessdata,
            )
        )
    if args.stdin:
        text = sys.stdin.read()
        if len(text.encode("utf-8")) > args.max_source_bytes:
            raise SystemExit(f"stdin exceeds --max-source-bytes ({args.max_source_bytes})")
        sources.append(
            SourceText(
                source_id=f"SRC{len(sources)+1:03d}",
                label=args.label or "pasted-stdin",
                source_type="pasted_text",
                path=None,
                text=text,
                extraction_status="extracted" if text.strip() else "blocked",
                extraction_notes=None if text.strip() else "stdin was empty",
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                size_bytes=len(text.encode("utf-8")),
            )
        )
    if not sources:
        raise SystemExit("Provide at least one --source, --text-file, or --stdin input.")

    source_payload = source_records(
        sources,
        repo_root,
        coverage_mode=args.mode,
        task=args.task,
        redact_excerpts=args.redact_excerpts_for_tracking,
    )
    coverage_payload = build_coverage_payload(
        sources,
        repo_root=repo_root,
        coverage_mode=args.mode,
        task=args.task,
        chunk_chars=args.chunk_chars,
        chunk_lines=args.chunk_lines,
        redact_excerpts=args.redact_excerpts_for_tracking,
    )
    if coverage_path(repo_root).exists() and not args.force:
        raise SystemExit(f"Coverage already exists: {coverage_path(repo_root)}. Use --force to replace it.")
    total_units = (coverage_payload.get("source_unit_manifest") or {}).get("total_units")
    if isinstance(total_units, int) and total_units > args.max_units:
        raise SystemExit(f"Source ingest would create {total_units} units, exceeding --max-units ({args.max_units}).")
    if args.force and source_units_root(repo_root).exists():
        shutil.rmtree(source_units_root(repo_root))
    write_source_unit_texts(repo_root, coverage_payload)
    write_json(sources_path(repo_root), source_payload)
    write_json(coverage_path(repo_root), coverage_payload)
    write_text(coverage_md_path(repo_root), render_coverage_md(coverage_payload))
    manifest_units = (coverage_payload.get("source_unit_manifest") or {}).get("units") or []
    blocked_unit_count = len(
        [
            unit
            for unit in manifest_units
            if isinstance(unit, dict) and str(unit.get("extraction_status") or "").lower() == "blocked"
        ]
    )
    return {
        "operation": "ingest",
        "source_documents_path": relative(sources_path(repo_root), repo_root),
        "coverage_path": relative(coverage_path(repo_root), repo_root),
        "coverage_md_path": relative(coverage_md_path(repo_root), repo_root),
        "source_count": len(sources),
        "row_count": len(coverage_payload["requirements"]),
        "blocked_source_count": len([source for source in sources if source.extraction_status == "blocked"]),
        "partial_source_count": len([source for source in sources if source.extraction_status == "partial"]),
        "blocked_unit_count": blocked_unit_count,
        "excerpts_redacted_for_tracking": args.redact_excerpts_for_tracking,
    }


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("requirements") or payload.get("rows") or payload.get("coverage") or payload.get("items")
        return value if isinstance(value, list) else []
    return payload if isinstance(payload, list) else []


def row_requires_source_evidence(row: dict[str, Any]) -> bool:
    return bool(row.get("source_evidence_required"))


def row_requires_semantic_contract(row: dict[str, Any]) -> bool:
    return bool(row.get("semantic_contract_required")) or str(row.get("coverage_mode") or "").strip().lower() == "implementation"


def row_requires_provenance_evidence(row: dict[str, Any]) -> bool:
    return bool(row.get("provenance_evidence_required")) or row_requires_semantic_contract(row)


def source_evidence_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("source_evidence")
    return value if isinstance(value, list) else []


def row_list_entries(row: dict[str, Any], key: str) -> list[Any]:
    value = row.get(key)
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    if str(value or "").strip():
        return [value]
    return []


def row_ready(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status not in DONE_STATUSES:
        return False
    if status == "intentionally_excluded":
        return bool(row.get("evidence")) and bool(row.get("reason") or row.get("exclusion_reason"))
    if row_requires_source_evidence(row) and not source_evidence_entries(row):
        return False
    if row_requires_semantic_contract(row):
        if not row_list_entries(row, "semantic_validation"):
            return False
        if not row_list_entries(row, "negative_tests"):
            return False
    if row_requires_provenance_evidence(row) and not row_list_entries(row, "provenance_evidence"):
        return False
    return bool(row.get("evidence")) and bool(row.get("validation"))


def build_source_evidence_entry(row: dict[str, Any], summary: str, *, now: str) -> dict[str, Any]:
    row_id = str(row.get("requirement_id") or row.get("id") or "").strip()
    span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
    unit_id = str(row.get("source_unit_id") or span.get("unit_id") or row_id).strip()
    text_path = str(row.get("source_unit_text_path") or "").strip()
    existing_count = len(source_evidence_entries(row))
    return {
        "id": f"SE{existing_count + 1:04d}",
        "created_at_utc": now,
        "row_id": row_id,
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "source_document": row.get("source_document"),
        "source_label": row.get("source_label"),
        "locator": row.get("locator") or row.get("section"),
        "source_unit_id": unit_id,
        "source_unit_text_path": text_path,
        "source_span": {
            "source_id": span.get("source_id") or row.get("source_id"),
            "unit_id": unit_id,
            "locator": span.get("locator") or row.get("locator") or row.get("section"),
            "excerpt_hash": span.get("excerpt_hash"),
        },
        "source_excerpt_hash": span.get("excerpt_hash"),
    }


def append_source_evidence(row: dict[str, Any], summaries: list[str], *, now: str) -> list[dict[str, Any]]:
    result = list(source_evidence_entries(row))
    for summary in summaries:
        if not str(summary).strip():
            continue
        row_for_index = dict(row)
        row_for_index["source_evidence"] = result
        result.append(build_source_evidence_entry(row_for_index, str(summary), now=now))
    return result


def validate_coverage_payload(payload: Any, *, repo_root: Path | None = None, verify_text_hashes: bool = False, check_row_readiness: bool = True) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["coverage payload is not an object"], "warnings": []}
    rows = rows_from_payload(payload)
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    manifest = payload.get("source_unit_manifest")
    manifest_units = manifest.get("units") if isinstance(manifest, dict) else []
    if not isinstance(manifest, dict):
        errors.append("coverage missing source_unit_manifest")
        manifest_units = []
    elif not isinstance(manifest_units, list):
        errors.append("source_unit_manifest.units is not a list")
        manifest_units = []
    known_units = {
        str(unit.get("unit_id"))
        for unit in manifest_units
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    manifest_by_id = {
        str(unit.get("unit_id")): unit
        for unit in manifest_units
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    row_unit_ids: set[str] = set()
    rows_by_unit: dict[str, list[dict[str, Any]]] = {}
    if not rows:
        errors.append("coverage has no rows")
    if isinstance(manifest, dict) and manifest.get("total_units") != len(manifest_units):
        errors.append("source_unit_manifest total_units does not match units length")
    for unit in manifest_units:
        if not isinstance(unit, dict):
            errors.append("source_unit_manifest contains a non-object unit")
            continue
        unit_id = str(unit.get("unit_id") or "").strip() or "unknown-unit"
        text_path_value = str(unit.get("text_path") or "").strip()
        if not text_path_value:
            errors.append(f"{unit_id}: missing source unit text_path")
            continue
        if repo_root is not None:
            try:
                text_path = safe_unit_path(repo_root, text_path_value)
            except managed_manifest.ManifestError as exc:
                errors.append(f"{unit_id}: unsafe or missing source unit path ({exc})")
                continue
            if verify_text_hashes:
                text = text_path.read_text(encoding="utf-8")
                expected_sha = str(unit.get("text_sha256") or "").strip()
                if expected_sha and unit_text_sha256(text) != expected_sha:
                    errors.append(f"{unit_id}: source unit text_sha256 mismatch at {text_path_value}")
                expected_excerpt_hash = str(unit.get("excerpt_hash") or "").strip()
                if expected_excerpt_hash and unit_hash(text) != expected_excerpt_hash:
                    errors.append(f"{unit_id}: source unit excerpt_hash mismatch at {text_path_value}")
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"row-{idx:04d}: row is not an object")
            continue
        row_id = str(row.get("requirement_id") or row.get("id") or "").strip()
        if not row_id:
            errors.append(f"row-{idx:04d}: missing requirement_id")
            continue
        if row_id in seen_ids:
            errors.append(f"{row_id}: duplicate requirement_id")
        seen_ids.add(row_id)
        status = str(row.get("status") or "").strip().lower()
        if status not in VALID_STATUSES:
            errors.append(f"{row_id}: invalid status {status!r}")
        if not row.get("source_id"):
            errors.append(f"{row_id}: missing source_id")
        if not row.get("source_document"):
            errors.append(f"{row_id}: missing source_document")
        if not row.get("source_unit_text_path"):
            errors.append(f"{row_id}: missing source_unit_text_path")
        elif repo_root is not None:
            try:
                safe_unit_path(repo_root, str(row.get("source_unit_text_path")))
            except managed_manifest.ManifestError as exc:
                errors.append(f"{row_id}: unsafe or missing source unit path ({exc})")
        if not row.get("locator") and not row.get("section"):
            errors.append(f"{row_id}: missing locator/section")
        span = row.get("source_span")
        row_unit_id = str(row.get("source_unit_id") or (span.get("unit_id") if isinstance(span, dict) else "") or "").strip()
        if row_unit_id:
            row_unit_ids.add(row_unit_id)
            rows_by_unit.setdefault(row_unit_id, []).append(row)
        if not isinstance(span, dict) or not span.get("unit_id") or not span.get("excerpt_hash"):
            errors.append(f"{row_id}: missing source_span.unit_id/excerpt_hash")
        elif known_units and str(span.get("unit_id")) not in known_units:
            errors.append(f"{row_id}: source_span unit_id not present in manifest")
        elif isinstance(span, dict):
            unit = manifest_by_id.get(str(span.get("unit_id")))
            if unit and str(span.get("excerpt_hash")) != str(unit.get("excerpt_hash")):
                errors.append(f"{row_id}: source_span excerpt_hash does not match manifest unit")
            unit_text_path = str((unit or {}).get("text_path") or "").strip()
            row_text_path = str(row.get("source_unit_text_path") or "").strip()
            if unit_text_path and row_text_path and unit_text_path != row_text_path:
                errors.append(f"{row_id}: source_unit_text_path does not match manifest unit")
        source_evidence = row.get("source_evidence")
        valid_source_evidence_count = 0
        if source_evidence is not None and not isinstance(source_evidence, list):
            errors.append(f"{row_id}: source_evidence must be a list")
        elif isinstance(source_evidence, list):
            for evidence_idx, entry in enumerate(source_evidence, start=1):
                if not isinstance(entry, dict):
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] is not an object")
                    continue
                if not str(entry.get("summary") or "").strip():
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] missing summary")
                entry_row_id = str(entry.get("row_id") or "").strip()
                if entry_row_id and entry_row_id != row_id:
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] row_id mismatch")
                entry_unit_id = str(entry.get("source_unit_id") or ((entry.get("source_span") or {}).get("unit_id") if isinstance(entry.get("source_span"), dict) else "") or "").strip()
                if row_unit_id and entry_unit_id and entry_unit_id != row_unit_id:
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] source_unit_id mismatch")
                entry_text_path = str(entry.get("source_unit_text_path") or "").strip()
                row_text_path = str(row.get("source_unit_text_path") or "").strip()
                if row_text_path and entry_text_path and entry_text_path != row_text_path:
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] source_unit_text_path mismatch")
                entry_hash = str(entry.get("source_excerpt_hash") or ((entry.get("source_span") or {}).get("excerpt_hash") if isinstance(entry.get("source_span"), dict) else "") or "").strip()
                row_hash = str((span or {}).get("excerpt_hash") if isinstance(span, dict) else "").strip()
                if row_hash and entry_hash and entry_hash != row_hash:
                    errors.append(f"{row_id}: source_evidence[{evidence_idx}] excerpt_hash mismatch")
                valid_source_evidence_count += 1
        row_span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
        if (
            str(row.get("coverage_type") or "") == "atomic_requirement"
            and str(row_span.get("requirement_hash") or "")
            and atomic_requirement_hash(str(row.get("requirement_text") or "")) != row_span.get("requirement_hash")
        ):
            # requirement_hash carries requirement identity in the contract hash;
            # an unverified hand-edit would otherwise stay invisible to every gate.
            errors.append(f"{row_id}: requirement_text does not match source_span.requirement_hash")
        if row_ready(row):
            continue
        # Readiness-class checks (proof completeness on done rows) are
        # completion gates, not integrity gates: migrate's transactional
        # validation must not refuse to HEAL a mid-work ledger whose rows are
        # legitimately still gathering proof (check_row_readiness=False).
        if not check_row_readiness:
            continue
        if status in DONE_STATUSES:
            if not row.get("evidence"):
                errors.append(f"{row_id}: done row missing evidence")
            if status != "intentionally_excluded" and row_requires_source_evidence(row) and valid_source_evidence_count == 0:
                errors.append(f"{row_id}: done row missing source_evidence anchored to original source unit")
            if status != "intentionally_excluded" and not row.get("validation"):
                errors.append(f"{row_id}: done row missing validation")
            if status != "intentionally_excluded" and row_requires_semantic_contract(row):
                if not row_list_entries(row, "semantic_validation"):
                    errors.append(f"{row_id}: implementation row missing semantic_validation")
                if not row_list_entries(row, "negative_tests"):
                    errors.append(f"{row_id}: implementation row missing negative_tests")
            if status != "intentionally_excluded" and row_requires_provenance_evidence(row) and not row_list_entries(row, "provenance_evidence"):
                errors.append(f"{row_id}: implementation row missing provenance_evidence")
            if status == "intentionally_excluded" and not (row.get("reason") or row.get("exclusion_reason")):
                errors.append(f"{row_id}: exclusion row missing reason")
    if isinstance(manifest, dict):
        missing_rows_for_units = sorted(known_units - row_unit_ids)
        unknown_row_units = sorted(row_unit_ids - known_units) if known_units else []
        for unit_id in missing_rows_for_units[:50]:
            errors.append(f"{unit_id}: manifest unit has no coverage row")
        for unit_id in unknown_row_units[:50]:
            errors.append(f"{unit_id}: coverage row unit is not present in manifest")
        processed = manifest.get("processed_unit_count")
        total = manifest.get("total_units")
        if processed is not None and total is not None:
            try:
                if int(processed) > int(total):
                    errors.append("source_unit_manifest processed_unit_count exceeds total_units")
            except (TypeError, ValueError):
                errors.append("source_unit_manifest processed_unit_count/total_units must be integers")
        unreadable = [
            str(unit.get("unit_id"))
            for unit in manifest_units
            if isinstance(unit, dict) and str(unit.get("extraction_status") or "").lower() == "blocked"
        ]
        if unreadable:
            warnings.append("unreadable_or_blocked_units: " + ", ".join(unreadable[:20]))
        coverage_mode = str(payload.get("coverage_mode") or "").strip().lower()
        if repo_root is not None and coverage_mode:
            for unit_id in sorted(known_units):
                unit = manifest_by_id.get(unit_id) or {}
                if str(unit.get("extraction_status") or "").strip().lower() == "blocked":
                    continue
                text_path_value = str(unit.get("text_path") or "").strip()
                if not text_path_value:
                    continue
                try:
                    text_path = safe_unit_path(repo_root, text_path_value)
                except managed_manifest.ManifestError:
                    continue
                try:
                    unit_text = text_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                locator = str(unit.get("locator") or "").strip() or None
                expected_role = classify_writing_unit_role(locator) if coverage_mode == "writing" else None
                actual_role = str(unit.get("unit_role") or "").strip() or None
                if actual_role != expected_role:
                    errors.append(
                        f"{unit_id}: manifest unit_role {actual_role!r} does not match expected {expected_role!r}"
                    )
                for issue in validate_unit_coverage_rows(
                    unit_id,
                    unit_text,
                    coverage_mode,
                    locator,
                    rows_by_unit.get(unit_id, []),
                ):
                    errors.append(
                        f"{unit_id}: atomic requirements/reading row identity mismatch: {issue}"
                    )
    return {"valid": not errors, "errors": errors, "warnings": warnings, "blocked_unit_ids": unreadable if isinstance(manifest, dict) else []}


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    payload = read_json(coverage_path(repo_root))
    if payload is None:
        return {"operation": "status", "present": False, "ready": False, "reason": "missing source_requirement_coverage.json"}
    rows = rows_from_payload(payload)
    validation = validate_coverage_payload(payload, repo_root=repo_root)
    manifest = payload.get("source_unit_manifest") if isinstance(payload, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    missing = [str(row.get("requirement_id") or row.get("id")) for row in rows if isinstance(row, dict) and not row_ready(row)]
    blocked_units = validation.get("blocked_unit_ids") if isinstance(validation.get("blocked_unit_ids"), list) else []
    return {
        "operation": "status",
        "present": True,
        "ready": bool(rows) and not missing and bool(validation.get("valid")) and not blocked_units,
        "row_count": len(rows),
        "missing_count": len(missing),
        "missing_ids": missing[:50],
        "source_unit_total": manifest.get("total_units"),
        "source_unit_processed": manifest.get("processed_unit_count"),
        "source_unit_blocked_ids": blocked_units[:50],
        "schema_valid": validation.get("valid"),
        "schema_errors": validation.get("errors"),
        "schema_warnings": validation.get("warnings"),
        "coverage_path": relative(coverage_path(repo_root), repo_root),
    }


def next_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    payload = read_json(coverage_path(repo_root))
    if payload is None:
        raise SystemExit("Missing source_requirement_coverage.json")
    for row in rows_from_payload(payload):
        if isinstance(row, dict) and not row_ready(row):
            result = {"operation": "next", "row": row}
            if getattr(args, "include_text", False):
                text_path_value = str(row.get("source_unit_text_path") or "").strip()
                if not text_path_value:
                    raise SystemExit(f"Coverage row lacks source_unit_text_path: {row.get('requirement_id')}")
                try:
                    text_path = safe_unit_path(repo_root, text_path_value)
                except managed_manifest.ManifestError as exc:
                    raise SystemExit(f"unsafe or missing source unit path refused: {exc}")
                result["source_unit_text"] = text_path.read_text(encoding="utf-8")
            return result
    return {"operation": "next", "row": None, "ready": True}


def append_value(existing: Any, values: list[str]) -> list[str]:
    result: list[str] = []
    if isinstance(existing, list):
        result.extend(str(item) for item in existing if str(item).strip())
    elif existing:
        result.append(str(existing))
    result.extend(value for value in values if value)
    return result


def row_source_unit_id(row: dict[str, Any]) -> str:
    span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
    return str(row.get("source_unit_id") or span.get("unit_id") or "").strip()


def processed_source_unit_ids(rows: list[dict[str, Any]]) -> set[str]:
    rows_by_unit: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        unit_id = row_source_unit_id(row)
        if unit_id:
            rows_by_unit.setdefault(unit_id, []).append(row)
    return {
        unit_id
        for unit_id, unit_rows in rows_by_unit.items()
        if unit_rows and all(row_ready(row) for row in unit_rows)
    }


def update_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    path = coverage_path(repo_root)
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("Missing or invalid source_requirement_coverage.json")
    rows = rows_from_payload(payload)
    updated: dict[str, Any] | None = None
    now = utc_now()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("requirement_id") or row.get("id") or "")
        if row_id != args.row_id:
            continue
        if args.status:
            row["status"] = args.status
        if args.evidence:
            row["evidence"] = append_value(row.get("evidence"), args.evidence)
            if row_requires_source_evidence(row):
                row["source_evidence"] = append_source_evidence(row, args.evidence, now=now)
        if args.validation:
            row["validation"] = append_value(row.get("validation"), args.validation)
            if row_requires_source_evidence(row):
                row["source_validation"] = append_value(row.get("source_validation"), args.validation)
        if args.semantic_validation:
            row["semantic_validation"] = append_value(row.get("semantic_validation"), args.semantic_validation)
        if args.provenance:
            row["provenance_evidence"] = append_value(row.get("provenance_evidence"), args.provenance)
        if args.negative_test:
            row["negative_tests"] = append_value(row.get("negative_tests"), args.negative_test)
        if args.reason:
            row["reason"] = args.reason
        if args.notes:
            row["notes"] = "\n".join(item for item in [str(row.get("notes") or ""), args.notes] if item)
        row["updated_at_utc"] = now
        updated = row
        break
    if updated is None:
        raise SystemExit(f"Unknown coverage row id: {args.row_id}")
    payload["updated_at_utc"] = now
    if isinstance(payload.get("source_unit_manifest"), dict):
        rows = rows_from_payload(payload)
        processed_unit_ids = processed_source_unit_ids(rows)
        payload["source_unit_manifest"]["processed_unit_count"] = len(processed_unit_ids)
    write_json(path, payload)
    write_text(coverage_md_path(repo_root), render_coverage_md(payload))
    return {"operation": "update", "row": updated, "ready": row_ready(updated)}


MIGRATE_PRESERVED_ROW_FIELDS = (
    "status",
    "evidence",
    "source_evidence",
    "validation",
    "source_validation",
    "semantic_validation",
    "negative_tests",
    "provenance_evidence",
    "notes",
    "reason",
    "updated_at_utc",
)


def migrate_command(args: argparse.Namespace) -> dict[str, Any]:
    """Heal an existing ledger whose row identity predates the current extractor.

    Dry-run by default. Per unit:
    - identical: current rows already match the extractor; untouched.
    - identity_remap: same positional row-ID list but identity fields drifted
      (e.g. the 2026-07-19 marker promotion changed `-` rows to `R<n>` rows in
      implementation mode). Rows are rebuilt from the extractor and the
      operator-owned fields (status/evidence/validation/... ) are preserved.
    - reingest: the row-ID set itself changed (e.g. an analysis reading_unit
      that now atomizes). Rows are rebuilt fresh with status unstarted —
      statuses are deliberately NOT copied because the old row does not
      correspond to any single new row.
    `--apply` backs up the ledger file first, then writes and re-validates.
    """

    repo_root = Path(args.repo_root).expanduser().resolve()
    path = coverage_path(repo_root)
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("Missing or invalid source_requirement_coverage.json")
    coverage_mode = str(payload.get("coverage_mode") or "implementation")
    task = payload.get("task")
    contract = payload.get("completion_contract") if isinstance(payload.get("completion_contract"), dict) else {}
    redact_excerpts = bool(contract.get("excerpts_redacted_for_tracking"))
    rows = rows_from_payload(payload)
    manifest = payload.get("source_unit_manifest") if isinstance(payload.get("source_unit_manifest"), dict) else None
    units = manifest.get("units") if manifest and isinstance(manifest.get("units"), list) else []
    if not units:
        raise SystemExit("coverage payload has no source_unit_manifest.units; re-ingest the source instead")

    rows_by_unit: dict[str, list[dict[str, Any]]] = {}
    leftovers: list[dict[str, Any]] = []
    for row in rows:
        unit_id = row_source_unit_id(row) if isinstance(row, dict) else ""
        if unit_id:
            rows_by_unit.setdefault(unit_id, []).append(row)
        else:
            leftovers.append(row)

    actions: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    reingest_replaced: list[dict[str, Any]] = []
    changed = False
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or "").strip()
        locator = unit.get("locator")
        unit_rows = rows_by_unit.pop(unit_id, [])
        try:
            text_path = safe_unit_path(repo_root, str(unit.get("text_path") or ""))
        except managed_manifest.ManifestError as exc:
            actions.append(
                {
                    "unit_id": unit_id,
                    "action": "text_missing",
                    "text_path": str(unit.get("text_path")),
                    "detail": str(exc),
                }
            )
            new_rows.extend(unit_rows)
            continue
        unit_text = text_path.read_text(encoding="utf-8")
        issues = validate_unit_coverage_rows(unit_id, unit_text, coverage_mode, locator, unit_rows)
        if not issues:
            actions.append({"unit_id": unit_id, "action": "identical", "rows": len(unit_rows)})
            new_rows.extend(unit_rows)
            continue
        expected_ids = expected_coverage_row_ids_for_unit(unit_id, unit_text, coverage_mode, locator=locator)
        actual_ids = [
            str(row.get("requirement_id") or row.get("id") or "").strip()
            for row in unit_rows
            if isinstance(row, dict)
        ]
        unit["atomic_requirement_count"] = len(
            atomic_requirements_for_mode(unit_text, coverage_mode, locator=locator)
        )
        changed = True
        if expected_ids == actual_ids:
            rebuilt = build_unit_coverage_rows(
                unit,
                unit_text,
                coverage_mode=coverage_mode,
                task=task,
                redact_excerpts=redact_excerpts,
                row_status="unstarted",
            )
            rebuilt_by_id = {str(row["requirement_id"]): row for row in rebuilt}
            merged: list[dict[str, Any]] = []
            semantic_resets = 0
            for stored in unit_rows:
                stored_id = str(stored.get("requirement_id") or stored.get("id") or "").strip()
                fresh = rebuilt_by_id[stored_id]
                # Reviewer finding: an unchanged ID list must not carry old
                # done/evidence onto semantically different requirement text.
                # The requirement TEXT is what the operator completed against
                # (span hashes can be stale or attacker-chosen), so operator
                # fields survive only when the marker-stripped normalized
                # texts agree. Leading list/R-number markers are formatting,
                # not meaning — strip them iteratively on both sides so the
                # 2026-07 marker-promotion healing still preserves progress.
                stored_text = str(stored.get("requirement_text") or "")
                fresh_text = str(fresh.get("requirement_text") or "")

                def _semantic_key(text: str) -> str:
                    stripped = text.strip()
                    while True:
                        reduced = re.sub(r"^\s*(?:[-*]|R\d+)\s*:\s*", "", stripped, count=1)
                        if reduced == stripped:
                            break
                        stripped = reduced
                    return " ".join(stripped.split())

                same_semantics = bool(
                    stored_text.strip()
                    and _semantic_key(stored_text) == _semantic_key(fresh_text)
                )
                if same_semantics:
                    for key in MIGRATE_PRESERVED_ROW_FIELDS:
                        if key in stored:
                            fresh[key] = stored[key]
                else:
                    semantic_resets += 1
                if stored.get("task"):
                    fresh["task"] = stored["task"]
                merged.append(fresh)
            new_rows.extend(merged)
            actions.append(
                {
                    "unit_id": unit_id,
                    "action": "identity_remap",
                    "rows": len(merged),
                    "issues_before": len(issues),
                    "statuses_preserved": semantic_resets == 0,
                    "semantic_reset_rows": semantic_resets,
                }
            )
        else:
            fresh_status = "blocked" if str(unit.get("extraction_status") or "") == "blocked" else "unstarted"
            rebuilt = build_unit_coverage_rows(
                unit,
                unit_text,
                coverage_mode=coverage_mode,
                task=task,
                redact_excerpts=redact_excerpts,
                row_status=fresh_status,
            )
            new_rows.extend(rebuilt)
            done_lost = sum(
                1
                for row in unit_rows
                if isinstance(row, dict) and str(row.get("status") or "").lower() in DONE_STATUSES
            )
            reingest_replaced.append({"unit_id": unit_id, "rows": unit_rows})
            actions.append(
                {
                    "unit_id": unit_id,
                    "action": "reingest",
                    "rows_before": len(unit_rows),
                    "rows_after": len(rebuilt),
                    "issues_before": len(issues),
                    "statuses_reset": True,
                    "statuses_lost_estimate": done_lost,
                }
            )
    for orphan_unit_id, orphan_rows in rows_by_unit.items():
        actions.append(
            {"unit_id": orphan_unit_id, "action": "unknown_unit_rows_preserved", "rows": len(orphan_rows)}
        )
        leftovers.extend(orphan_rows)
    new_rows.extend(leftovers)

    blocking_actions = [
        action
        for action in actions
        if action.get("action") in ("text_missing", "unknown_unit_rows_preserved")
    ]
    reingest_actions = [action for action in actions if action.get("action") == "reingest"]
    result: dict[str, Any] = {
        "operation": "migrate",
        "coverage_mode": coverage_mode,
        "dry_run": not args.apply,
        "changed": changed,
        "row_count_before": len(rows),
        "row_count_after": len(new_rows),
        "actions": actions,
        "blocking_actions": blocking_actions,
        "statuses_lost_estimate": sum(
            int(action.get("statuses_lost_estimate") or 0) for action in reingest_actions
        ),
    }
    # R20: anomalies are blockers, not warnings — a ledger with unreadable
    # units or orphan rows must never be reported or rewritten as a success.
    # This check runs BEFORE the not-changed early return (reviewer finding:
    # a text_missing-only ledger used to return rc 0 under --apply).
    if args.apply and blocking_actions:
        raise SystemExit(
            "migrate blocked: text_missing/unknown-unit rows present "
            f"({[a.get('unit_id') for a in blocking_actions]}); heal them first — nothing was written"
        )
    if not args.apply or not changed:
        if changed:
            result["apply_hint"] = (
                "re-run with --apply to write the migrated ledger (a backup is created first)"
            )
            if reingest_actions:
                result["apply_hint"] += "; row-set changes additionally require --accept-status-reset"
        return result
    if reingest_actions and not getattr(args, "accept_status_reset", False):
        raise SystemExit(
            "migrate blocked: row-set changes would reset operator status on "
            f"{[a.get('unit_id') for a in reingest_actions]} "
            f"(done rows lost: {result['statuses_lost_estimate']}); review the dry-run and re-run with --accept-status-reset"
        )

    now = utc_now()
    stamp = re.sub(r"[^0-9TZ]", "", now)
    md_path = coverage_md_path(repo_root)
    original_json = path.read_bytes()
    original_md = md_path.read_bytes() if md_path.exists() else None
    backup_path = path.with_name(f"source_requirement_coverage.pre-migrate-{stamp}.json")
    backup_path.write_bytes(original_json)
    md_backup_path = None
    if original_md is not None:
        md_backup_path = md_path.with_name(f"source_requirement_coverage.pre-migrate-{stamp}.md")
        md_backup_path.write_bytes(original_md)

    payload["requirements"] = new_rows
    payload["updated_at_utc"] = now
    payload["migrated_at_utc"] = now
    if reingest_replaced:
        history = payload.get("migration_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "at_utc": now,
                "kind": "reingest",
                "units": [item["unit_id"] for item in reingest_replaced],
                "replaced_rows": [row for item in reingest_replaced for row in item["rows"]],
            }
        )
        payload["migration_history"] = history
    if isinstance(manifest, dict):
        manifest["processed_unit_count"] = len(processed_source_unit_ids(new_rows))

    # R19: stage -> re-read from DISK -> validate -> commit under the state
    # lock -> re-verify committed bytes; any failure restores both files.
    staged_path = path.with_name(path.name + f".staged-{stamp}")
    write_json(staged_path, payload)
    try:
        reread = json.loads(staged_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        staged_path.unlink(missing_ok=True)
        raise SystemExit(f"migrate staging re-read failed; nothing committed: {exc}")
    md_rendered = render_coverage_md(reread)
    pre_commit = validate_coverage_payload(reread, repo_root=repo_root, verify_text_hashes=True, check_row_readiness=False)
    if not pre_commit.get("valid"):
        staged_path.unlink(missing_ok=True)
        raise SystemExit(
            "migrate candidate failed disk-level validation; nothing committed: "
            + "; ".join(list(pre_commit.get("errors", []))[:5])
        )

    lock_path = state_lock.acquire_state_lock(repo_root, "source_coverage")
    try:
        # Compare-and-swap (reviewer finding): the candidate was built from a
        # pre-lock read; a writer that committed in between must not be
        # silently overwritten by a stale candidate. Round 2: the markdown
        # side gets the same CAS.
        current_md = md_path.read_bytes() if md_path.exists() else None
        if path.read_bytes() != original_json or current_md != original_md:
            staged_path.unlink(missing_ok=True)
            raise SystemExit(
                "migrate aborted: the coverage ledger or its markdown changed while the candidate "
                "was being built — nothing was written; re-run migrate against the current ledger"
            )
        try:
            os.replace(staged_path, path)
            write_text(md_path, md_rendered)
            committed = json.loads(path.read_text(encoding="utf-8"))
            post = validate_coverage_payload(committed, repo_root=repo_root, verify_text_hashes=True, check_row_readiness=False)
            if os.environ.get("RAH_MIGRATE_FAULT") == "post-commit":
                # explicit fault-injection seam: the post-commit restore path is
                # otherwise unreachable from outside a race, and the rollback
                # contract (R19) must stay executable in tests
                post = {"valid": False, "errors": ["fault-injected: RAH_MIGRATE_FAULT=post-commit"]}
            md_now = md_path.read_text(encoding="utf-8")
        except (SystemExit, Exception) as exc:
            # Round 2 reviewer finding: a SystemExit AFTER the JSON replace
            # also has to restore bytes — no exception class is exempt once
            # the ledger file has been swapped.
            # Reviewer finding: an exception AFTER the JSON os.replace (md
            # write, re-read, validator crash) had no rollback path — only
            # the post.valid==False control flow restored bytes.
            path.write_bytes(original_json)
            if original_md is not None:
                md_path.write_bytes(original_md)
            else:
                md_path.unlink(missing_ok=True)
            restored = path.read_bytes() == original_json and (
                (original_md is None and not md_path.exists())
                or (original_md is not None and md_path.read_bytes() == original_md)
            )
            raise SystemExit(
                "migrate commit raised mid-transaction; ledger and markdown were "
                f"restored byte-for-byte (verified={restored}): {exc}"
            )
        if not post.get("valid") or md_now != md_rendered:
            path.write_bytes(original_json)
            if original_md is not None:
                md_path.write_bytes(original_md)
            else:
                md_path.unlink(missing_ok=True)
            restored = path.read_bytes() == original_json and (
                (original_md is None and not md_path.exists())
                or (original_md is not None and md_path.read_bytes() == original_md)
            )
            raise SystemExit(
                "migrate post-commit validation failed; ledger and markdown were "
                f"restored byte-for-byte (verified={restored}): "
                + "; ".join(list(post.get("errors", []))[:5])
            )
    finally:
        state_lock.release_state_lock(lock_path)

    result["backup_path"] = relative(backup_path, repo_root)
    if md_backup_path is not None:
        result["md_backup_path"] = relative(md_backup_path, repo_root)
    result["post_valid"] = True
    result["post_errors"] = []
    return result


def print_payload(payload: dict[str, Any], json_only: bool) -> None:
    if json_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"# Source Coverage: {payload.get('operation')}\n")
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            print(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"- {key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = _SuggestingArgumentParser(description="Create and maintain exhaustive source-material coverage for RALPH.")
    parser.add_argument("repo_root", help="Path to the repository root")
    sub = parser.add_subparsers(dest="operation", required=True)

    ingest_parser = sub.add_parser("ingest", help="Ingest files, PDFs, text files, or pasted stdin into coverage rows.")
    ingest_parser.add_argument("--source", action="append", default=[], help="Source file path. Can repeat. Supports md/txt/pdf best-effort.")
    ingest_parser.add_argument("--text-file", default=None, help="Additional text file path.")
    ingest_parser.add_argument("--stdin", action="store_true", help="Read source text from stdin.")
    ingest_parser.add_argument("--label", default=None, help="Label for stdin/pasted text.")
    ingest_parser.add_argument("--mode", choices=["implementation", "analysis", "paper", "summary", "synthesis", "writing"], default="analysis")
    ingest_parser.add_argument("--task", default=None, help="Task instruction attached to every row.")
    ingest_parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    ingest_parser.add_argument("--chunk-lines", type=int, default=DEFAULT_CHUNK_LINES)
    ingest_parser.add_argument("--max-source-bytes", type=int, default=DEFAULT_MAX_SOURCE_BYTES)
    ingest_parser.add_argument("--max-units", type=int, default=DEFAULT_MAX_UNITS)
    ingest_parser.add_argument(
        "--ocr",
        choices=["auto", "off", "force"],
        default="auto",
        help="PDF OCR fallback: auto uses PyMuPDF/Tesseract OCR when embedded text is missing, off disables OCR, force OCRs even text-layer PDFs.",
    )
    ingest_parser.add_argument("--ocr-lang", default=os.environ.get("RAH_OCR_LANG", "eng"), help="Tesseract language code(s), e.g. eng, kor, or eng+kor.")
    ingest_parser.add_argument("--ocr-dpi", type=int, default=DEFAULT_OCR_DPI, help="DPI for PyMuPDF-rendered OCR page images.")
    ingest_parser.add_argument("--ocr-max-pages", type=int, default=DEFAULT_OCR_MAX_PAGES, help="Maximum pages to OCR; 0 disables the cap.")
    ingest_parser.add_argument(
        "--ocr-tessdata",
        default=default_ocr_tessdata(),
        help="Optional Tesseract tessdata directory for PyMuPDF OCR or external Tesseract.",
    )
    ingest_parser.add_argument(
        "--redact-excerpts-for-tracking",
        action="store_true",
        help="Keep raw source text only in ignored source_units and replace coverage JSON excerpts with a redaction marker.",
    )
    ingest_parser.add_argument("--force", action="store_true", help="Replace existing source coverage files.")
    ingest_parser.add_argument("--json", action="store_true")

    status_parser = sub.add_parser("status", help="Show coverage readiness.")
    status_parser.add_argument("--json", action="store_true")

    next_parser = sub.add_parser("next", help="Show the next incomplete coverage row.")
    next_parser.add_argument("--include-text", action="store_true", help="Include the full source-unit text for the next row.")
    next_parser.add_argument("--json", action="store_true")

    update_parser = sub.add_parser("update", help="Update one coverage row.")
    update_parser.add_argument("row_id")
    update_parser.add_argument("--status", default=None, help=f"Row status. Done statuses include: {', '.join(sorted(DONE_STATUSES))}.")
    update_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence note/path grounded to this source row. Can repeat; source_evidence is auto-anchored to source_unit_id/path/hash.",
    )
    update_parser.add_argument("--validation", action="append", default=[], help="Validation note/path. Can repeat.")
    update_parser.add_argument(
        "--semantic-validation",
        action="append",
        default=[],
        help="Proof that the implementation/analysis satisfies the requirement semantics, not just labels, files, or output names.",
    )
    update_parser.add_argument(
        "--provenance",
        action="append",
        default=[],
        help="Generator/data-path provenance proving produced values or claims came from the intended algorithm/source path.",
    )
    update_parser.add_argument(
        "--negative-test",
        action="append",
        default=[],
        help="A failing-before/fails-if-superficial test or audit that would catch label/file-only compliance.",
    )
    update_parser.add_argument("--reason", default=None, help="Policy or user-decision reason for intentionally_excluded rows.")
    update_parser.add_argument("--notes", default=None)
    update_parser.add_argument("--json", action="store_true")

    validate_parser = sub.add_parser("validate", help="Validate source coverage schema and readiness constraints.")
    validate_parser.add_argument("--json", action="store_true")

    migrate_parser = sub.add_parser(
        "migrate",
        help="Heal an old ledger to the current extractor identity (dry-run by default; statuses/evidence preserved when row IDs are unchanged).",
    )
    migrate_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the migrated ledger after creating timestamped backups (JSON and Markdown); commits transactionally and auto-restores on post-commit validation failure.",
    )
    migrate_parser.add_argument(
        "--accept-status-reset",
        action="store_true",
        help="Required when row-set changes (reingest) would reset operator status; replaced rows are preserved in migration_history.",
    )
    migrate_parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.operation == "ingest":
            payload = ingest(args)
        elif args.operation == "status":
            payload = status_command(args)
        elif args.operation == "next":
            payload = next_command(args)
        elif args.operation == "update":
            payload = update_command(args)
        elif args.operation == "migrate":
            payload = migrate_command(args)
        else:
            repo_root = Path(args.repo_root).expanduser().resolve()
            coverage = read_json(coverage_path(repo_root))
            validation = validate_coverage_payload(coverage, repo_root=repo_root, verify_text_hashes=True)
            payload = {"operation": "validate", **validation}
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print_payload(payload, getattr(args, "json", False))
    if args.operation == "validate" and not payload.get("valid"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
