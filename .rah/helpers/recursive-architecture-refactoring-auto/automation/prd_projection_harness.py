#!/usr/bin/env python3
"""Explicit-only PRD projection over RAH source coverage.

PRD is a planning view derived from source coverage plus deterministic
requirement atoms. It owns no evidence, review, pass/fail, or completion state;
the hard-gate contract lives in prd_mapping_audit.json, and completion
authority stays with source_requirement_coverage.json / RALPH readiness.

Exit codes follow the source_coverage_harness convention:
  0  success (validate/emit/ingest additionally require audit_ready=true)
  1  command ran and wrote artifacts, but the hard gate failed
  2  usage/precondition error (SystemExit)
"""
from __future__ import annotations

import argparse

try:
    from cli_suggestions import SuggestingArgumentParser as _SuggestingArgumentParser
except Exception:  # stale repo helper tree may predate cli_suggestions
    _SuggestingArgumentParser = argparse.ArgumentParser
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import source_coverage_harness as coverage_lib

ATOMS_SCHEMA_VERSION = 1
PRD_SCHEMA_VERSION = 4
AUDIT_SCHEMA_VERSION = 4
GENERATOR_NAME = "prd_projection_harness.extract_atoms"
GENERATOR_VERSION = 2

# Requirement phrases stay below LEAK_WINDOW so a verbatim echo inside an
# acceptance criterion can never contain a full leak-detection window.
REQUIREMENT_PHRASE_MAX_CHARS = 118
LEAK_WINDOW = 120
SOURCE_STRIDE = 80
WAIVER_RATIO_WARNING_THRESHOLD = 0.15

# Mixed Korean/English text breaks \b at Latin-Hangul joints ("rollback을"):
# both sides are word chars, so \b never fires. Use ASCII-only boundaries so an
# attached Hangul particle still counts as a boundary.
MODAL_MUST_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:must|shall|required|needs?\s+to|have\s+to)(?![A-Za-z0-9_])"
    r"|반드시|필수|(?:해야|하여야|되어야|돼야|이어야)\s*(?:한다|합니다|함|하며|된다|됩니다)",
    re.IGNORECASE,
)
# English-only modal counter for the multi-modal review check: Korean pairs like
# "반드시 ... 해야 한다" are a single obligation and must not be double-counted.
MODAL_MUST_EN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:must|shall|required|needs?\s+to|have\s+to)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
PARALLEL_SPLIT_RE = re.compile(r"\s+and\s+|;\s+|\s+그리고\s+")
MODAL_SOFT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:should|may|recommended|prefer(?:red)?)(?![A-Za-z0-9_])|권장|가능하면",
    re.IGNORECASE,
)
NEGATIVE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:not|never|without|unless|except|fail(?:s|ed|ure)?|error|deny|denied|reject(?:s|ed)?|rollback|forbidden|prohibited)(?![A-Za-z0-9_])"
    r"|금지|제외|실패|오류|거부|롤백|하지\s*않|말아야|없어야|안\s*된다",
    re.IGNORECASE,
)
CONDITION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:if|when(?:ever)?|before|after|until|while|unless)(?![A-Za-z0-9_])"
    r"|경우|때에는|할\s*때|이전에|이후에|동안",
    re.IGNORECASE,
)
# Bare [<>] matched blockquote markers and "->" arrows; require an adjacent
# digit so only real comparisons count.
COMPARATOR_RE = re.compile(
    r"이상|이하|미만|초과|이내|최소|최대|at\s+least|at\s+most|no\s+more\s+than|fewer\s+than|less\s+than|greater\s+than"
    r"|(?<![A-Za-z0-9_])within(?![A-Za-z0-9_])|>=|<=|==|[<>]=?\s{0,3}\d|\d\s{0,3}[<>]",
    re.IGNORECASE,
)
NUMERIC_UNIT_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:ms|msec|s|sec|seconds?|분|초|시간|minutes?|hours?|%|percent|회|개|건|배|mb|gb|kb|mib|gib|px|tokens?|rows?|items?)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
# Trailing lookahead only rejects digit/decimal continuation so attached units
# ("3초", "100ms") still count as numbers; identifier prefixes are blocked by
# the lookbehind and versions/dates/IDs by the excluded spans.
NUMERIC_TOKEN_RE = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\d.])")
VERSION_RE = re.compile(r"\bv\d+(?:\.\d+)+\b|\b\d+\.\d+\.\d+\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ID_TOKEN_RE = re.compile(r"\b[A-Za-z][\w]*-\d+\b|\b(?:SRC|REQ|R|C|V|AC)\d{1,4}\b")
CODE_SPAN_RE = re.compile(r"`([^`\r\n]+)`")
CLI_FLAG_RE = re.compile(r"(?<![\w-])--[A-Za-z][\w-]+")
PATHLIKE_RE = re.compile(
    r"[\w.*-]+[\\/][\w./\\*-]+|\b[\w-]+\.(?:py|md|json|yaml|yml|toml|csv|tsv|txt|bin|cfg|ini)\b"
)
ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}\b")
CALLABLE_RE = re.compile(r"\b\w+\(\)")
TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s*\[( |x|X)\]\s+(?P<body>\S.*)$")
USER_STORY_RE = re.compile(r"^\s*As\s+an?\s+.+", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")

RISK_TAG_RES = {
    "security": re.compile(
        r"security|auth(?:entication|orization)?|permission|credential|token|password|암호|인증|권한|보안",
        re.IGNORECASE,
    ),
    "privacy": re.compile(
        r"privacy|(?<![A-Za-z0-9_])pii(?![A-Za-z0-9_])|personal\s+data|개인정보", re.IGNORECASE
    ),
    "data-loss": re.compile(
        r"data\s+loss|destructive|(?<![A-Za-z0-9_])delete(?![A-Za-z0-9_])|삭제|유실|손실", re.IGNORECASE
    ),
    "performance": re.compile(r"performance|latency|timeout|throughput|성능|지연", re.IGNORECASE),
    "migration": re.compile(r"migration|migrate|마이그레이션|이관", re.IGNORECASE),
    "compatibility": re.compile(r"backward|compatib|호환", re.IGNORECASE),
    "audit-logging": re.compile(
        r"(?<![A-Za-z0-9_])audit(?![A-Za-z0-9_])|logging|감사\s*로그", re.IGNORECASE
    ),
}

GENERIC_CRITERIA_RE = re.compile(
    r"^\s*(implementation\s+is\s+complete|code\s+compiles|tests?\s+pass(?:es)?|"
    r"review\s+completed|done|works\s+as\s+expected|all\s+requirements\s+met|"
    r"n/?a|tbd|완료|테스트\s*통과|리뷰\s*완료|요구사항\s*충족)\s*[.!。]*\s*$",
    re.IGNORECASE,
)
FORBIDDEN_STORY_KEYS = {"source_excerpt", "raw_source", "source_text", "full_text"}

EPIC_RULES = [
    ("tests/validation", re.compile(r"test|validation|verif|검증|테스트", re.IGNORECASE)),
    ("documentation/operations", re.compile(r"doc(?:s|umentation)?|readme|문서|운영", re.IGNORECASE)),
    ("architecture/design", re.compile(r"architecture|design|설계|구조", re.IGNORECASE)),
    ("data/interfaces", re.compile(r"\bdata\b|schema|interface|\bapi\b|데이터|인터페이스|입출력", re.IGNORECASE)),
    ("integration", re.compile(r"integrat|연동|통합", re.IGNORECASE)),
    ("release/closeout", re.compile(r"release|deploy|closeout|배포|릴리스|마무리", re.IGNORECASE)),
    ("requirements/scope", re.compile(r"requirement|scope|요구사항|범위", re.IGNORECASE)),
]
DEFAULT_EPIC = "implementation"


# ---------------------------------------------------------------------------
# Paths and shared helpers
# ---------------------------------------------------------------------------

def ralph_root(repo_root: Path) -> Path:
    return coverage_lib.ralph_root(repo_root)


def coverage_path(repo_root: Path) -> Path:
    return coverage_lib.coverage_path(repo_root)


def atoms_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "source_requirement_atoms.json"


def prd_json_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "prd.json"


def prd_md_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "prd.md"


def prd_audit_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "prd_mapping_audit.json"


def waivers_path(repo_root: Path) -> Path:
    return ralph_root(repo_root) / "prd_waivers.json"


def utc_now() -> str:
    return coverage_lib.utc_now()


def compact(value: str) -> str:
    return coverage_lib.compact_whitespace(value)


def canonical_json(value: Any) -> str:
    return coverage_lib.contract_canonical_json(value)


def sha256_of(value: Any) -> str:
    return coverage_lib.contract_hash_of(value)


def truncate_lists_for_display(value: Any, limit: int = 50) -> Any:
    """Human-mode output caps id lists at 50 entries (+overflow marker); --json
    output stays complete because the audit JSON is the machine contract."""
    if isinstance(value, dict):
        return {key: truncate_lists_for_display(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > limit and all(isinstance(item, str) for item in value):
            return value[:limit] + [f"... (+{len(value) - limit} more)"]
        return [truncate_lists_for_display(item, limit) for item in value]
    return value


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def read_json_strict(path: Path, label: str) -> Any:
    """Missing file -> None; unparsable file -> exit-2 SystemExit (never a traceback)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not parseable JSON: {path} ({exc})")


def read_json_lenient(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_source_coverage(repo_root: Path) -> dict[str, Any]:
    payload = read_json_strict(coverage_path(repo_root), "source coverage")
    if not isinstance(payload, dict):
        raise SystemExit(
            f"Missing source coverage: {coverage_path(repo_root)}. "
            "Run `rah.py source <repo-root> ingest ...` first; PRD is a projection over coverage."
        )
    return payload


def source_atoms_hash(atoms_payload: dict[str, Any]) -> str:
    """Canonical hash of the atoms decomposition.

    created_at_utc and the derived summary/review blocks are excluded;
    generator.version is included so an extractor upgrade deterministically
    invalidates downstream PRD/waivers.
    """
    projection = {
        "schema_version": atoms_payload.get("schema_version"),
        "source_coverage_contract_hash": atoms_payload.get("source_coverage_contract_hash"),
        "generator": atoms_payload.get("generator"),
        "atoms": atoms_payload.get("atoms"),
    }
    return sha256_of(projection)


def prd_payload_hash(prd: dict[str, Any]) -> str:
    projection = {key: value for key, value in prd.items() if key != "created_at_utc"}
    return sha256_of(projection)


def audit_input_fingerprint(
    prd: dict[str, Any],
    coverage: dict[str, Any],
    atoms: dict[str, Any],
    waivers: dict[str, Any],
) -> str:
    """Fingerprint of every audit input. The audit is a pure function of these,
    so a stored audit with a matching fingerprint can be reused on the hot
    assess path (every RALPH/drive cycle) without re-reading source unit files.
    The full coverage payload (including mutable row progress) is hashed so any
    row update invalidates the cache."""
    return sha256_of(
        {
            "coverage": coverage,
            "atoms_hash": source_atoms_hash(atoms),
            "prd_hash": prd_payload_hash(prd),
            "waivers": waivers,
            "generator": GENERATOR_VERSION,
            "audit_schema": AUDIT_SCHEMA_VERSION,
        }
    )


# ---------------------------------------------------------------------------
# Deterministic atom extraction
# ---------------------------------------------------------------------------

def _excluded_numeric_spans(text: str) -> list[tuple[int, int]]:
    spans = [match.span() for match in VERSION_RE.finditer(text)]
    spans += [match.span() for match in DATE_RE.finditer(text)]
    spans += [match.span() for match in ID_TOKEN_RE.finditer(text)]
    return spans


def numeric_constraints(text: str) -> list[str]:
    stripped = CODE_SPAN_RE.sub(" ", text)
    excluded = _excluded_numeric_spans(stripped)
    found: list[str] = []
    for match in NUMERIC_TOKEN_RE.finditer(stripped):
        start, end = match.span()
        if any(span_start <= start and end <= span_end for span_start, span_end in excluded):
            continue
        window = stripped[max(0, start - 24):min(len(stripped), end + 24)]
        if COMPARATOR_RE.search(window) or NUMERIC_UNIT_RE.search(window):
            snippet = compact(stripped[max(0, start - 16):min(len(stripped), end + 16)])
            found.append(snippet)
    return dedupe(found)


def interface_constraints(text: str) -> list[str]:
    found = [match.group(1) for match in CODE_SPAN_RE.finditer(text)]
    stripped = CODE_SPAN_RE.sub(" ", text)
    found += CLI_FLAG_RE.findall(stripped)
    found += [match.group(0) for match in PATHLIKE_RE.finditer(stripped)]
    found += ENV_VAR_RE.findall(stripped)
    found += CALLABLE_RE.findall(stripped)
    return dedupe([item[:80] for item in found])


def risk_tags_for(text: str) -> list[str]:
    return sorted(tag for tag, pattern in RISK_TAG_RES.items() if pattern.search(text))


def extract_condition(sentence: str) -> str:
    match = CONDITION_RE.search(sentence)
    if not match:
        return ""
    tail = sentence[match.start():]
    clause = re.split(r"[,.;。]", tail, maxsplit=1)[0]
    return compact(clause)[:120]


def split_requirement_blocks(text: str) -> tuple[list[str], list[str], bool]:
    """Split text into sentence blocks and table rows. Returns
    (sentences, table_rows, table_detected)."""
    sentences: list[str] = []
    table_rows: list[str] = []
    table_detected = False
    current: list[str] = []
    table_block: list[str] = []

    def flush() -> None:
        if not current:
            return
        joined = compact(" ".join(current))
        current.clear()
        if not joined:
            return
        for part in SENTENCE_SPLIT_RE.split(joined):
            part = part.strip()
            if part:
                sentences.append(part)

    def flush_table() -> None:
        if not table_block:
            return
        raw_rows = table_block[:]
        table_block.clear()
        start = 0
        # A markdown header row (first line followed by a separator) is a
        # caption, not a requirement; keep only data rows as atom candidates.
        if len(raw_rows) >= 2 and not TABLE_SEP_RE.match(raw_rows[0]) and TABLE_SEP_RE.match(raw_rows[1]):
            start = 2
        for raw in raw_rows[start:]:
            if TABLE_SEP_RE.match(raw):
                continue
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            row_text = " | ".join(cell for cell in cells if cell)
            if row_text:
                table_rows.append(row_text)

    in_fence = False
    for line in text.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("```") or stripped_line.startswith("~~~"):
            in_fence = not in_fence
            flush()
            flush_table()
            continue
        if in_fence:
            continue  # fenced example code is illustration, not requirements
        line = re.sub(r"^\s*>+\s?", "", line)  # blockquote markers are decoration
        if re.match(r"^\s*#{1,6}\s", line):
            flush()
            flush_table()
            continue  # markdown headings are structure, not requirements
        if TABLE_LINE_RE.match(line):
            table_detected = True
            flush()
            table_block.append(line)
            continue
        flush_table()
        if LIST_ITEM_RE.match(line):
            flush()
            current.append(LIST_ITEM_RE.sub("", line, count=1))
            continue
        if not line.strip():
            flush()
            continue
        current.append(line)
    flush()
    flush_table()
    return sentences, table_rows, table_detected


def split_parallel_modals(sentence: str) -> list[str]:
    """Split a sentence into separate atoms only when parallel modal clauses are
    unambiguous: EVERY coordinated part must carry its own modal. A partial
    split would sever guard clauses ("If the user is an admin and ...") from
    the obligation they scope."""
    parts = [part.strip() for part in PARALLEL_SPLIT_RE.split(sentence) if part.strip()]
    if len(parts) >= 2 and all(
        MODAL_MUST_RE.search(part) or MODAL_SOFT_RE.search(part) for part in parts
    ):
        return parts
    return [sentence]


def _atom_from_sentence(row: dict[str, Any], sentence: str, index: int) -> dict[str, Any]:
    row_id = str(row.get("requirement_id") or "")
    span = row.get("source_span") if isinstance(row.get("source_span"), dict) else {}
    modality = "must" if MODAL_MUST_RE.search(sentence) else ("should" if MODAL_SOFT_RE.search(sentence) else "statement")
    polarity = "negative" if NEGATIVE_RE.search(sentence) else "affirmative"
    numeric = numeric_constraints(sentence)
    interface = interface_constraints(sentence)
    risk = risk_tags_for(sentence)
    compatibility = ["compatibility"] if "compatibility" in risk else []
    requirement = compact(sentence)[:REQUIREMENT_PHRASE_MAX_CHARS]
    verification_required = bool(
        modality == "must" or polarity == "negative" or risk or numeric or interface
    )
    identity = {
        "modality": modality,
        "polarity": polarity,
        "condition": extract_condition(sentence),
        "requirement": requirement,
        "constraints": {"numeric": numeric, "interface": interface, "compatibility": compatibility},
        "risk_tags": risk,
    }
    return {
        "atom_id": f"{row_id}-A{index:02d}",
        "source_row_id": row_id,
        "source_unit_id": row.get("source_unit_id"),
        "source_span": {
            "source_id": span.get("source_id"),
            "unit_id": span.get("unit_id"),
            "line_start": span.get("line_start"),
            "line_end": span.get("line_end"),
            "excerpt_hash": span.get("excerpt_hash"),
        },
        **identity,
        "verification_required": verification_required,
        "negative_test_required": polarity == "negative",
        "provenance_required": bool(coverage_lib.row_requires_provenance_evidence(row)),
        "atom_hash": sha256_of(identity),
        "derived_from": "deterministic-rule",
    }


def extract_requirement_atoms(row: dict[str, Any], *, source_text: str | None = None) -> list[dict[str, Any]]:
    coverage_type = str(row.get("coverage_type") or "")
    atomic_mode = coverage_type == "atomic_requirement"
    base_text = str(row.get("requirement_text") or "") if atomic_mode else str(source_text or "")
    if not base_text.strip():
        return []
    sentences, table_rows, _table_detected = split_requirement_blocks(base_text)
    if atomic_mode:
        base_sentences = sentences or [compact(base_text)]
        candidates = [
            part for sentence in base_sentences for part in split_parallel_modals(sentence)
        ]
    else:
        candidates = [
            sentence
            for sentence in sentences
            if MODAL_MUST_RE.search(sentence)
            or MODAL_SOFT_RE.search(sentence)
            or NEGATIVE_RE.search(sentence)
            or numeric_constraints(sentence)
            or interface_constraints(sentence)
            or risk_tags_for(sentence)
        ]
    candidates = candidates + table_rows
    if not candidates:
        if not atomic_mode:
            # Signal-less reading units contribute no atoms; row-level coverage
            # still forces a story link, so nothing is silently dropped.
            return []
        candidates = [compact(base_text)[:REQUIREMENT_PHRASE_MAX_CHARS]]
    return [
        _atom_from_sentence(row, sentence, index)
        for index, sentence in enumerate(candidates, start=1)
    ]


def atom_is_required(atom: dict[str, Any]) -> bool:
    constraints = atom.get("constraints") if isinstance(atom.get("constraints"), dict) else {}
    return bool(
        atom.get("modality") == "must"
        or atom.get("polarity") == "negative"
        or atom.get("risk_tags")
        or constraints.get("numeric")
        or constraints.get("interface")
    )


def _unit_texts(coverage: dict[str, Any], repo_root: Path) -> dict[str, str]:
    manifest = coverage.get("source_unit_manifest") if isinstance(coverage, dict) else {}
    units = manifest.get("units") if isinstance(manifest, dict) else []
    texts: dict[str, str] = {}
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or "")
        text_path_value = str(unit.get("text_path") or "")
        if not unit_id or not text_path_value:
            continue
        text_file = repo_root / text_path_value
        if text_file.exists():
            try:
                texts[unit_id] = text_file.read_text(encoding="utf-8")
            except OSError:
                continue
    return texts


def build_atoms_payload(coverage: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rows = [row for row in coverage_lib.rows_from_payload(coverage) if isinstance(row, dict)]
    unit_texts = _unit_texts(coverage, repo_root)
    atoms: list[dict[str, Any]] = []
    review_reasons: list[str] = []
    atom_counts: dict[str, int] = {}
    for row in rows:
        row_id = str(row.get("requirement_id") or "")
        unit_id = str(row.get("source_unit_id") or "")
        source_text = unit_texts.get(unit_id)
        row_atoms = extract_requirement_atoms(row, source_text=source_text)
        atom_counts[row_id] = len(row_atoms)
        base_text = (
            str(row.get("requirement_text") or "")
            if str(row.get("coverage_type") or "") == "atomic_requirement"
            else str(source_text or "")
        )
        if (
            str(row.get("coverage_type") or "") == "atomic_requirement"
            and len(row_atoms) == 1
            and len(MODAL_MUST_EN_RE.findall(base_text)) >= 2
        ):
            review_reasons.append(
                f"{row_id}: multiple modal verbs detected but only one atom was produced"
            )
        atoms.extend(row_atoms)

    # Unit-level sweep: a table inside a unit whose rows are all atomic never
    # appears in any requirement_text, so its constraints would silently vanish.
    # Bind such table rows to the unit's first coverage row as extra atoms.
    rows_by_unit: dict[str, list[dict[str, Any]]] = {}
    unit_order: list[str] = []
    for row in rows:
        unit_id = str(row.get("source_unit_id") or "")
        if unit_id not in rows_by_unit:
            rows_by_unit[unit_id] = []
            unit_order.append(unit_id)
        rows_by_unit[unit_id].append(row)
    for unit_id in unit_order:
        unit_rows = rows_by_unit[unit_id]
        unit_text = unit_texts.get(unit_id)
        if not unit_text:
            continue
        _sentences, table_rows, table_detected = split_requirement_blocks(unit_text)
        if not table_detected:
            continue
        if not table_rows:
            review_reasons.append(f"{unit_id}: table-like source block produced no table atoms")
            continue
        if not all(str(row.get("coverage_type") or "") == "atomic_requirement" for row in unit_rows):
            continue  # reading-unit rows already scan the full unit text
        joined_requirements = compact(
            " ".join(str(row.get("requirement_text") or "") for row in unit_rows)
        )
        missing = [
            table_row for table_row in table_rows if compact(table_row) not in joined_requirements
        ]
        if not missing:
            continue
        anchor = unit_rows[0]
        anchor_id = str(anchor.get("requirement_id") or "")
        if not anchor_id:
            review_reasons.append(f"{unit_id}: table-like source block produced no table atoms")
            continue
        for offset, table_row in enumerate(missing, start=1):
            atoms.append(
                _atom_from_sentence(anchor, table_row, atom_counts.get(anchor_id, 0) + offset)
            )
        atom_counts[anchor_id] = atom_counts.get(anchor_id, 0) + len(missing)
    summary = {
        "row_count": len([row for row in rows if isinstance(row, dict)]),
        "atom_count": len(atoms),
        "must_atom_count": len([atom for atom in atoms if atom.get("modality") == "must"]),
        "negative_atom_count": len([atom for atom in atoms if atom.get("polarity") == "negative"]),
        "high_risk_atom_count": len([atom for atom in atoms if atom.get("risk_tags")]),
        "required_atom_count": len([atom for atom in atoms if atom_is_required(atom)]),
    }
    return {
        "schema_version": ATOMS_SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "source_coverage_path": coverage_lib.relative(coverage_path(repo_root), repo_root),
        "source_coverage_contract_hash": coverage_lib.coverage_contract_hash(coverage),
        "deterministic": True,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "llm_used": False},
        "atoms": atoms,
        "review_reasons": review_reasons,
        "summary": summary,
    }


def ensure_atoms_payload(coverage: dict[str, Any], repo_root: Path, *, write: bool) -> dict[str, Any]:
    """Load atoms if present and bound to the current coverage; otherwise
    regenerate deterministically (and persist when write=True). Atoms are a
    derived artifact, so a corrupt file is healed by regeneration."""
    existing = read_json_lenient(atoms_path(repo_root))
    current_hash = coverage_lib.coverage_contract_hash(coverage)
    if (
        isinstance(existing, dict)
        and existing.get("source_coverage_contract_hash") == current_hash
        and (existing.get("generator") or {}).get("version") == GENERATOR_VERSION
    ):
        return existing
    payload = build_atoms_payload(coverage, repo_root)
    if write:
        coverage_lib.write_json(atoms_path(repo_root), payload)
    return payload


# ---------------------------------------------------------------------------
# PRD emit / ingest
# ---------------------------------------------------------------------------

def classify_epic(text: str) -> str:
    for epic, pattern in EPIC_RULES:
        if pattern.search(text):
            return epic
    return DEFAULT_EPIC


def _verification_type(atom: dict[str, Any]) -> str:
    constraints = atom.get("constraints") if isinstance(atom.get("constraints"), dict) else {}
    if atom.get("polarity") == "negative":
        return "negative-test"
    if constraints.get("numeric"):
        return "numeric-check"
    if constraints.get("interface"):
        return "interface-check"
    if atom.get("risk_tags"):
        return "risk-verification"
    return "functional-test"


def _criterion_for_atom(story_id: str, index: int, atom: dict[str, Any]) -> dict[str, Any]:
    constraints = atom.get("constraints") if isinstance(atom.get("constraints"), dict) else {}
    echo_parts = list(constraints.get("numeric") or []) + list(constraints.get("interface") or [])
    echo = f" [constraints: {'; '.join(echo_parts)}]" if echo_parts else ""
    return {
        "id": f"AC-{story_id}-{index:02d}",
        "linked_source_atom_ids": [atom.get("atom_id")],
        "criterion": f"Satisfy source atom {atom.get('atom_id')}: {atom.get('requirement')}{echo}",
        "verification": {
            "required": bool(atom.get("verification_required")),
            "type": _verification_type(atom),
            "target": "verify_" + str(atom.get("atom_id") or "").lower().replace("-", "_"),
            "source_evidence_required": True,
            "provenance_required": bool(atom.get("provenance_required")),
        },
    }


def emit_prd_from_coverage(
    coverage: dict[str, Any],
    atoms: dict[str, Any],
    *,
    task: str = "",
) -> dict[str, Any]:
    rows = [row for row in coverage_lib.rows_from_payload(coverage) if isinstance(row, dict)]
    atom_list = [atom for atom in (atoms.get("atoms") or []) if isinstance(atom, dict)]
    atoms_by_row: dict[str, list[dict[str, Any]]] = {}
    for atom in atom_list:
        atoms_by_row.setdefault(str(atom.get("source_row_id") or ""), []).append(atom)

    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        unit_id = str(row.get("source_unit_id") or row.get("requirement_id") or "")
        if unit_id not in grouped:
            grouped[unit_id] = []
            order.append(unit_id)
        grouped[unit_id].append(row)

    stories: list[dict[str, Any]] = []
    for story_index, unit_id in enumerate(order, start=1):
        unit_rows = grouped[unit_id]
        story_id = f"PRD-{story_index:03d}"
        locator = compact(str(unit_rows[0].get("section") or unit_rows[0].get("locator") or unit_id))[:100]
        row_ids = [str(row.get("requirement_id") or "") for row in unit_rows]
        story_atoms = [atom for row_id in row_ids for atom in atoms_by_row.get(row_id, [])]
        atom_ids = [str(atom.get("atom_id") or "") for atom in story_atoms]
        risk_text = " ".join(tag for atom in story_atoms for tag in (atom.get("risk_tags") or []))
        criteria = [
            _criterion_for_atom(story_id, index, atom)
            for index, atom in enumerate(
                [atom for atom in story_atoms if atom_is_required(atom)], start=1
            )
        ]
        stories.append(
            {
                "id": story_id,
                "title": locator or story_id,
                "epic": classify_epic(f"{locator} {risk_text}"),
                "description": (
                    f"Cover {len(unit_rows)} source coverage row(s) and "
                    f"{len(story_atoms)} requirement atom(s) from section '{locator}'."
                ),
                "linked_source_row_ids": row_ids,
                "linked_source_atom_ids": atom_ids,
                "acceptance_criteria": criteria,
                "dependencies": [],
            }
        )
    return {
        "schema_version": PRD_SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "mode": "emit-from-coverage",
        "deterministic": True,
        "llm_used": False,
        "task": task or str(coverage.get("task") or ""),
        "source_coverage_contract_hash": coverage_lib.coverage_contract_hash(coverage),
        "source_atoms_hash": source_atoms_hash(atoms),
        "stories": stories,
    }


def _normalize_criterion(story_id: str, index: int, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
        return {
            "id": str(value.get("id") or f"AC-{story_id}-{index:02d}"),
            "linked_source_atom_ids": [
                str(item) for item in (value.get("linked_source_atom_ids") or []) if str(item).strip()
            ],
            "criterion": compact(str(value.get("criterion") or "")),
            "verification": {
                "required": bool(verification.get("required", False)),
                "type": str(verification.get("type") or "unspecified"),
                "target": str(verification.get("target") or ""),
                "source_evidence_required": bool(verification.get("source_evidence_required", True)),
                "provenance_required": bool(verification.get("provenance_required", False)),
            },
        }
    return _normalize_criterion(story_id, index, {"criterion": str(value)})


def _normalize_story(index: int, value: dict[str, Any]) -> dict[str, Any]:
    story_id = str(value.get("id") or f"PRD-{index:03d}")
    criteria = value.get("acceptance_criteria") if isinstance(value.get("acceptance_criteria"), list) else []
    normalized = {
        "id": story_id,
        "title": compact(str(value.get("title") or story_id))[:100],
        "epic": str(value.get("epic") or DEFAULT_EPIC),
        "description": compact(str(value.get("description") or "")),
        "linked_source_row_ids": [
            str(item) for item in (value.get("linked_source_row_ids") or []) if str(item).strip()
        ],
        "linked_source_atom_ids": [
            str(item) for item in (value.get("linked_source_atom_ids") or []) if str(item).strip()
        ],
        "acceptance_criteria": [
            _normalize_criterion(story_id, criterion_index, criterion)
            for criterion_index, criterion in enumerate(criteria, start=1)
        ],
        "dependencies": [str(item) for item in (value.get("dependencies") or []) if str(item).strip()],
    }
    for key in FORBIDDEN_STORY_KEYS:
        if key in value:
            normalized[key] = value[key]
    return normalized


def _parse_markdown_prd(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    stories: list[dict[str, Any]] = []
    review_reasons: list[str] = []
    epic = DEFAULT_EPIC
    story: dict[str, Any] | None = None

    def close_story() -> None:
        nonlocal story
        if story is not None:
            stories.append(story)
            story = None

    for line in text.splitlines():
        heading = re.match(r"^(#{1,2})\s+(?P<title>\S.*)$", line)
        if heading:
            title = compact(heading.group("title"))
            if heading.group(1) == "#":
                epic = classify_epic(title) if classify_epic(title) != DEFAULT_EPIC else compact(title)[:60]
                continue
            close_story()
            story = {
                "id": f"PRD-{len(stories) + 1:03d}",
                "title": title,
                "epic": epic,
                "description": "",
                "acceptance_criteria": [],
                "dependencies": [],
            }
            continue
        if TABLE_LINE_RE.match(line):
            review_reasons.append("table-like PRD block was ingested without atom mapping")
            continue
        checkbox = CHECKBOX_RE.match(line)
        if checkbox and story is not None:
            story["acceptance_criteria"].append(compact(checkbox.group("body")))
            continue
        if story is not None and USER_STORY_RE.match(line):
            story["description"] = compact(f"{story['description']} {line}".strip())
            continue
        if story is not None and line.strip() and not LIST_ITEM_RE.match(line):
            story["description"] = compact(f"{story['description']} {line.strip()}".strip())
    close_story()
    return stories, dedupe(review_reasons)


def ingest_prd(path: Path, coverage: dict[str, Any], atoms: dict[str, Any]) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Missing PRD source file: {path}")
    text = path.read_text(encoding="utf-8")
    review_reasons: list[str] = []
    if path.suffix.lower() == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"PRD JSON is not parseable: {path} ({exc})")
        raw_stories = raw.get("stories") if isinstance(raw, dict) else raw
        if not isinstance(raw_stories, list):
            raise SystemExit(f"PRD JSON has no stories list: {path}")
        stories = [
            _normalize_story(index, story)
            for index, story in enumerate(raw_stories, start=1)
            if isinstance(story, dict)
        ]
    else:
        parsed, review_reasons = _parse_markdown_prd(text)
        stories = [_normalize_story(index, story) for index, story in enumerate(parsed, start=1)]
    return {
        "schema_version": PRD_SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "mode": "ingest",
        "deterministic": True,
        "llm_used": False,
        "task": "",
        "ingest_source": path.name,
        "ingest_review_reasons": review_reasons,
        "source_coverage_contract_hash": coverage_lib.coverage_contract_hash(coverage),
        "source_atoms_hash": source_atoms_hash(atoms),
        "stories": stories,
    }


def render_prd_markdown(prd: dict[str, Any]) -> str:
    lines = ["# PRD Projection", ""]
    lines.append(f"- mode: {prd.get('mode')}")
    lines.append(f"- source_coverage_contract_hash: {prd.get('source_coverage_contract_hash')}")
    lines.append(f"- source_atoms_hash: {prd.get('source_atoms_hash')}")
    lines.append("- authority: planning view only; completion stays with source coverage + RALPH readiness")
    lines.append("")
    stories = prd.get("stories") or []
    by_epic: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        if isinstance(story, dict):
            by_epic.setdefault(str(story.get("epic") or DEFAULT_EPIC), []).append(story)
    for epic in sorted(by_epic):
        lines.append(f"## {epic}")
        lines.append("")
        for story in by_epic[epic]:
            lines.append(f"### {story.get('id')}: {story.get('title')}")
            lines.append("")
            if story.get("description"):
                lines.append(str(story.get("description")))
                lines.append("")
            row_ids = story.get("linked_source_row_ids") or []
            shown_rows = ", ".join(row_ids[:50])
            if len(row_ids) > 50:
                shown_rows += f" ... (+{len(row_ids) - 50} more)"
            lines.append(f"- linked source rows: {shown_rows or '(none)'}")
            atom_ids = story.get("linked_source_atom_ids") or []
            shown_atoms = ", ".join(atom_ids[:50])
            if len(atom_ids) > 50:
                shown_atoms += f" ... (+{len(atom_ids) - 50} more)"
            lines.append(f"- linked source atoms: {shown_atoms or '(none)'}")
            criteria = story.get("acceptance_criteria") or []
            for criterion in criteria[:50]:
                verification = criterion.get("verification") or {}
                lines.append(
                    f"- [ ] {criterion.get('id')}: {criterion.get('criterion')} "
                    f"(verify: {verification.get('type')} -> {verification.get('target')})"
                )
            if len(criteria) > 50:
                lines.append(f"- ... (+{len(criteria) - 50} more criteria)")
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------

def load_waivers(repo_root: Path) -> dict[str, Any]:
    payload = read_json_strict(waivers_path(repo_root), "prd_waivers.json")
    return payload if isinstance(payload, dict) else {}


def effective_waived_atom_ids(
    waivers: dict[str, Any],
    *,
    coverage_hash: str,
    atoms_hash: str,
    known_atom_ids: set[str] | None = None,
) -> tuple[set[str], list[str]]:
    """Return (waived atom ids, warnings). A waiver counts only when it is
    human-reviewed, has a reason, names a known atom, and both bound hashes
    match the current state."""
    waived: set[str] = set()
    warnings: list[str] = []
    for waiver in waivers.get("waivers") or []:
        if not isinstance(waiver, dict):
            continue
        waiver_id = str(waiver.get("waiver_id") or "?")
        atom_id = str(waiver.get("waived_atom_id") or "")
        if not atom_id:
            warnings.append(f"waiver {waiver_id} has no waived_atom_id and was ignored")
            continue
        if known_atom_ids is not None and atom_id not in known_atom_ids:
            warnings.append(f"waiver {waiver_id} names unknown atom id {atom_id} and was ignored")
            continue
        if str(waiver.get("reviewer") or "").lower() != "human" or not str(waiver.get("reason") or "").strip():
            warnings.append(f"waiver {waiver_id} is not human-reviewed with a reason and was ignored")
            continue
        if waiver.get("source_coverage_contract_hash") != coverage_hash or waiver.get("source_atoms_hash") != atoms_hash:
            warnings.append(f"waiver {waiver_id} is stale (source hashes changed) and was ignored")
            continue
        waived.add(atom_id)
    return waived, warnings


# ---------------------------------------------------------------------------
# Raw source leak detection
# ---------------------------------------------------------------------------

def leak_digest(window: str) -> bytes:
    # hashlib-based deterministic digest; built-in hash() is randomized per
    # process (PYTHONHASHSEED) and would break audit reproducibility.
    return hashlib.blake2b(window.encode("utf-8"), digest_size=8).digest()


def leak_ngrams(text: str, *, size: int = LEAK_WINDOW, stride: int = SOURCE_STRIDE) -> set[bytes]:
    normalized = compact(text)
    digests: set[bytes] = set()
    if len(normalized) < size:
        return digests
    last_start = len(normalized) - size
    for start in range(0, last_start + 1, stride):
        digests.add(leak_digest(normalized[start:start + size]))
    digests.add(leak_digest(normalized[last_start:]))
    return digests


def build_source_leak_index(
    coverage: dict[str, Any], repo_root: Path
) -> tuple[set[bytes], list[str], list[str], list[str]]:
    manifest = coverage.get("source_unit_manifest") if isinstance(coverage, dict) else {}
    units = manifest.get("units") if isinstance(manifest, dict) else []
    digests: set[bytes] = set()
    normalized_texts: list[str] = []
    warnings: list[str] = []
    skipped_unit_ids: list[str] = []
    ordered: list[tuple[str, str]] = []
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("unit_id") or "?")
        text_path_value = str(unit.get("text_path") or "")
        text_file = repo_root / text_path_value if text_path_value else None
        if text_file is None or not text_file.exists():
            warnings.append(f"leak check skipped for {unit_id}: source unit text missing")
            skipped_unit_ids.append(unit_id)
            continue
        try:
            text = text_file.read_text(encoding="utf-8")
        except OSError:
            warnings.append(f"leak check skipped for {unit_id}: source unit text unreadable")
            skipped_unit_ids.append(unit_id)
            continue
        normalized = compact(text)
        normalized_texts.append(normalized)
        ordered.append((str(unit.get("source_id") or ""), normalized))
        digests |= leak_ngrams(text)
    # A verbatim run straddling a chunk boundary would evade per-unit windows;
    # digest the seam of consecutive units of the same source as well.
    boundary_span = LEAK_WINDOW + SOURCE_STRIDE - 1
    for (prev_source, prev_text), (next_source, next_text) in zip(ordered, ordered[1:]):
        if prev_source != next_source:
            continue
        boundary = prev_text[-boundary_span:] + " " + next_text[:boundary_span]
        digests |= leak_ngrams(boundary)
        normalized_texts.append(boundary)
    return digests, normalized_texts, warnings, skipped_unit_ids


def _story_text_blob(value: Any) -> str:
    # Compare actual string values, not the JSON rendering: json escapes real
    # newlines to literal "\n" and would never align with the whitespace-
    # normalized source windows.
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_story_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_story_text_blob(item) for item in value)
    return ""


def story_leaks_raw_source(
    story: dict[str, Any],
    source_digests: set[bytes],
    normalized_source_texts: list[str],
) -> bool:
    if any(key in story for key in FORBIDDEN_STORY_KEYS):
        return True
    if not source_digests:
        return False
    rendered = compact(_story_text_blob(story))
    if len(rendered) < LEAK_WINDOW:
        return False
    for start in range(0, len(rendered) - LEAK_WINDOW + 1):
        window = rendered[start:start + LEAK_WINDOW]
        if leak_digest(window) in source_digests:
            if any(window in text for text in normalized_source_texts):
                return True
    return False


# ---------------------------------------------------------------------------
# Audit (hard gate contract)
# ---------------------------------------------------------------------------

def _source_coverage_ready(coverage: dict[str, Any], repo_root: Path) -> bool:
    validation = coverage_lib.validate_coverage_payload(
        coverage, repo_root=repo_root, verify_text_hashes=True
    )
    if not validation.get("valid", False):
        return False
    rows = [row for row in coverage_lib.rows_from_payload(coverage) if isinstance(row, dict)]
    return bool(rows) and all(coverage_lib.row_ready(row) for row in rows)


def goal_prd_required(repo_root: Path) -> bool:
    goal = read_json_lenient(ralph_root(repo_root) / "goal.json")
    return bool(goal.get("prd_required")) if isinstance(goal, dict) else False


def validate_prd_projection(
    prd: dict[str, Any],
    coverage: dict[str, Any],
    atoms: dict[str, Any],
    waivers: dict[str, Any],
    *,
    repo_root: Path,
    prd_required: bool = False,
) -> dict[str, Any]:
    rows = [row for row in coverage_lib.rows_from_payload(coverage) if isinstance(row, dict)]
    rows_by_id = {str(row.get("requirement_id") or ""): row for row in rows}
    atom_list = [atom for atom in (atoms.get("atoms") or []) if isinstance(atom, dict)]
    atoms_by_id = {str(atom.get("atom_id") or ""): atom for atom in atom_list}

    current_coverage_hash = coverage_lib.coverage_contract_hash(coverage)
    current_atoms_hash = source_atoms_hash(atoms)
    stale = bool(
        atoms.get("source_coverage_contract_hash") != current_coverage_hash
        or prd.get("source_coverage_contract_hash") != current_coverage_hash
        or prd.get("source_atoms_hash") != current_atoms_hash
        # An extractor upgrade must deterministically invalidate downstream
        # projections on the validate/assess path, not only on emit/ingest.
        or (atoms.get("generator") or {}).get("version") != GENERATOR_VERSION
    )

    stories = prd.get("stories") if isinstance(prd.get("stories"), list) else None
    schema_valid = stories is not None and all(
        isinstance(story, dict) and str(story.get("id") or "").strip() for story in stories
    )
    stories = [story for story in (stories or []) if isinstance(story, dict)]

    errors: list[str] = []
    warnings: list[str] = []
    review_reasons: list[str] = list(atoms.get("review_reasons") or [])
    review_reasons += list(prd.get("ingest_review_reasons") or [])
    if not schema_valid:
        errors.append("prd.json schema invalid: stories must be a list of objects with ids")

    story_ids: list[str] = []
    duplicate_story_ids: list[str] = []
    for story in stories:
        story_id = str(story.get("id") or "")
        if story_id in story_ids:
            duplicate_story_ids.append(story_id)
        story_ids.append(story_id)

    known_story_ids = set(story_ids)
    dependency_error_story_ids = sorted(
        {
            str(story.get("id") or "")
            for story in stories
            for dependency in (story.get("dependencies") or [])
            if str(dependency) not in known_story_ids
        }
    )

    linked_row_ids: set[str] = set()
    linked_atom_ids_by_story: set[str] = set()
    unknown_linked_source_row_ids: list[str] = []
    unknown_linked_source_atom_ids: list[str] = []
    stories_without_links: list[str] = []
    for story in stories:
        story_rows = [str(item) for item in (story.get("linked_source_row_ids") or [])]
        story_atoms = [str(item) for item in (story.get("linked_source_atom_ids") or [])]
        if not story_rows and not story_atoms:
            stories_without_links.append(str(story.get("id") or ""))
        for row_id in story_rows:
            if row_id in rows_by_id:
                linked_row_ids.add(row_id)
            else:
                unknown_linked_source_row_ids.append(row_id)
        for atom_id in story_atoms:
            if atom_id in atoms_by_id:
                linked_atom_ids_by_story.add(atom_id)
            else:
                unknown_linked_source_atom_ids.append(atom_id)

    criteria_ids: list[str] = []
    duplicate_acceptance_criteria_ids: list[str] = []
    criteria_without_atom_links: list[str] = []
    generic_criteria_story_ids: list[str] = []
    criterion_atoms: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        story_id = str(story.get("id") or "")
        story_generic = False
        for criterion in story.get("acceptance_criteria") or []:
            if not isinstance(criterion, dict):
                continue
            criterion_id = str(criterion.get("id") or "")
            if criterion_id in criteria_ids:
                duplicate_acceptance_criteria_ids.append(criterion_id)
            criteria_ids.append(criterion_id)
            text = str(criterion.get("criterion") or "")
            if GENERIC_CRITERIA_RE.match(text):
                story_generic = True
            linked = [str(item) for item in (criterion.get("linked_source_atom_ids") or [])]
            known_links = [atom_id for atom_id in linked if atom_id in atoms_by_id]
            for atom_id in linked:
                if atom_id not in atoms_by_id:
                    unknown_linked_source_atom_ids.append(atom_id)
            if not known_links:
                criteria_without_atom_links.append(criterion_id)
            for atom_id in known_links:
                criterion_atoms.setdefault(atom_id, []).append(criterion)
            verification = criterion.get("verification") if isinstance(criterion.get("verification"), dict) else {}
            if len(text.strip()) < 12 and not str(verification.get("target") or "").strip():
                warnings.append(f"criterion {criterion_id} is very short and has no verification target")
        if story_generic:
            generic_criteria_story_ids.append(story_id)

    non_excluded_rows = [
        row for row in rows if str(row.get("status") or "").strip().lower() != "intentionally_excluded"
    ]
    unmapped_source_row_ids = [
        str(row.get("requirement_id") or "")
        for row in non_excluded_rows
        if str(row.get("requirement_id") or "") not in linked_row_ids
    ]

    waived_atom_ids, waiver_warnings = effective_waived_atom_ids(
        waivers,
        coverage_hash=current_coverage_hash,
        atoms_hash=current_atoms_hash,
        known_atom_ids=set(atoms_by_id),
    )
    warnings.extend(waiver_warnings)

    def row_excluded(atom: dict[str, Any]) -> bool:
        row = rows_by_id.get(str(atom.get("source_row_id") or ""))
        return bool(
            row is not None
            and str(row.get("status") or "").strip().lower() == "intentionally_excluded"
        )

    required_atoms = [
        atom
        for atom in atom_list
        if atom_is_required(atom)
        and not row_excluded(atom)
        and str(atom.get("atom_id") or "") not in waived_atom_ids
    ]
    unmapped_required_atom_ids = [
        str(atom.get("atom_id") or "")
        for atom in required_atoms
        if str(atom.get("atom_id") or "") not in criterion_atoms
    ]
    must_atoms_without_acceptance_criteria = [
        str(atom.get("atom_id") or "")
        for atom in required_atoms
        if atom.get("modality") == "must" and str(atom.get("atom_id") or "") not in criterion_atoms
    ]
    informative_atoms_without_links = [
        str(atom.get("atom_id") or "")
        for atom in atom_list
        if not atom_is_required(atom)
        and str(atom.get("atom_id") or "") not in criterion_atoms
        and str(atom.get("atom_id") or "") not in linked_atom_ids_by_story
    ]
    if informative_atoms_without_links:
        warnings.append(
            f"{len(informative_atoms_without_links)} informative atom(s) have no criterion/story link (warning only)"
        )

    negative_atoms_without_negative_test: list[str] = []
    high_risk_atoms_without_verification: list[str] = []
    must_atoms_without_required_verification: list[str] = []
    numeric_atoms_without_explicit_constraint: list[str] = []
    interface_atoms_without_target: list[str] = []
    for atom in required_atoms:
        atom_id = str(atom.get("atom_id") or "")
        criteria = criterion_atoms.get(atom_id, [])
        if not criteria:
            constraints = atom.get("constraints") if isinstance(atom.get("constraints"), dict) else {}
            if atom.get("polarity") == "negative":
                negative_atoms_without_negative_test.append(atom_id)
            if atom.get("risk_tags"):
                high_risk_atoms_without_verification.append(atom_id)
            if constraints.get("numeric"):
                numeric_atoms_without_explicit_constraint.append(atom_id)
            if constraints.get("interface"):
                interface_atoms_without_target.append(atom_id)
            continue
        constraints = atom.get("constraints") if isinstance(atom.get("constraints"), dict) else {}
        verifications = [
            criterion.get("verification") if isinstance(criterion.get("verification"), dict) else {}
            for criterion in criteria
        ]
        if atom.get("modality") == "must" and not any(
            verification.get("required") for verification in verifications
        ):
            must_atoms_without_required_verification.append(atom_id)
        if atom.get("polarity") == "negative" and not any(
            verification.get("type") == "negative-test" and verification.get("required")
            for verification in verifications
        ):
            negative_atoms_without_negative_test.append(atom_id)
        if atom.get("risk_tags") and not any(
            verification.get("required") and str(verification.get("target") or "").strip()
            for verification in verifications
        ):
            high_risk_atoms_without_verification.append(atom_id)
        if constraints.get("numeric") and not any(
            any(snippet in str(criterion.get("criterion") or "") for snippet in constraints["numeric"])
            for criterion in criteria
        ):
            numeric_atoms_without_explicit_constraint.append(atom_id)
        if constraints.get("interface") and not any(
            any(
                identifier in str(criterion.get("criterion") or "")
                or identifier in str(verification.get("target") or "")
                for identifier in constraints["interface"]
            )
            for criterion, verification in zip(criteria, verifications)
        ):
            interface_atoms_without_target.append(atom_id)

    source_digests, normalized_source_texts, leak_warnings, leak_skipped_unit_ids = build_source_leak_index(
        coverage, repo_root
    )
    warnings.extend(leak_warnings)
    if stories and leak_skipped_unit_ids:
        # Fail closed: with source unit texts unreadable the leak gate cannot run,
        # so readiness must not be granted on an unverifiable projection.
        errors.append(
            f"leak_index_incomplete: {len(leak_skipped_unit_ids)} source unit(s) unreadable; "
            "raw-source leak gate cannot run"
        )
    raw_source_leak_story_ids = [
        str(story.get("id") or "")
        for story in stories
        if story_leaks_raw_source(story, source_digests, normalized_source_texts)
    ]

    row_coverage_ready = not unmapped_source_row_ids and not unknown_linked_source_row_ids
    atom_coverage_ready = not unmapped_required_atom_ids
    criteria_coverage_ready = bool(
        not criteria_without_atom_links
        and not generic_criteria_story_ids
        and not duplicate_acceptance_criteria_ids
    )
    verification_coverage_ready = bool(
        not negative_atoms_without_negative_test
        and not high_risk_atoms_without_verification
        and not must_atoms_without_required_verification
        and not numeric_atoms_without_explicit_constraint
        and not interface_atoms_without_target
    )

    for atom_id in negative_atoms_without_negative_test:
        review_reasons.append(f"negative atom {atom_id} has no negative-test verification")
    for atom_id in high_risk_atoms_without_verification:
        review_reasons.append(f"high-risk atom {atom_id} has no verification target")
    for atom_id in must_atoms_without_required_verification:
        review_reasons.append(f"must atom {atom_id} has no criterion with verification.required=true")

    required_atom_count = len(
        [atom for atom in atom_list if atom_is_required(atom) and not row_excluded(atom)]
    )
    waiver_ratio = (len(waived_atom_ids) / required_atom_count) if required_atom_count else 0.0
    if waiver_ratio > WAIVER_RATIO_WARNING_THRESHOLD:
        warnings.append(
            f"waiver ratio {waiver_ratio:.2f} exceeds threshold {WAIVER_RATIO_WARNING_THRESHOLD:.2f}; "
            "review extractor rules instead of waiving atoms"
        )

    audit_ready = bool(
        schema_valid
        and not stale
        and row_coverage_ready
        and atom_coverage_ready
        and criteria_coverage_ready
        and verification_coverage_ready
        and not duplicate_story_ids
        and not generic_criteria_story_ids
        and not raw_source_leak_story_ids
        and not dependency_error_story_ids
        and not unknown_linked_source_row_ids
        and not unknown_linked_source_atom_ids
        and not errors
    )
    source_coverage_ready = _source_coverage_ready(coverage, repo_root)
    prd_ready = bool(audit_ready and source_coverage_ready)
    if stale:
        review_reasons.append(
            "PRD projection is stale relative to source coverage/atoms; regenerate with `prd atoms` + `prd emit` or re-run `prd validate` after refresh"
        )

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "deterministic": True,
        "llm_used": False,
        "prd_present": True,
        "prd_required": bool(prd_required),
        "audit_ready": audit_ready,
        "prd_ready": prd_ready,
        "needs_review": bool(review_reasons),
        "source_coverage_present": True,
        "source_atoms_present": True,
        "source_coverage_ready": source_coverage_ready,
        "source_coverage_contract_hash": current_coverage_hash,
        "source_atoms_hash": current_atoms_hash,
        "prd_hash": prd_payload_hash(prd),
        "story_count": len(stories),
        "source_row_count": len(rows),
        "source_atom_count": len(atom_list),
        "required_atom_count": required_atom_count,
        "row_coverage_ready": row_coverage_ready,
        "atom_coverage_ready": atom_coverage_ready,
        "criteria_coverage_ready": criteria_coverage_ready,
        "verification_coverage_ready": verification_coverage_ready,
        "mapped_source_row_count": len(linked_row_ids),
        "mapped_required_atom_count": len(
            [atom for atom in required_atoms if str(atom.get("atom_id") or "") in criterion_atoms]
        ),
        "unmapped_source_row_ids": unmapped_source_row_ids,
        "unmapped_required_atom_ids": unmapped_required_atom_ids,
        "unknown_linked_source_row_ids": dedupe(unknown_linked_source_row_ids),
        "unknown_linked_source_atom_ids": dedupe(unknown_linked_source_atom_ids),
        "stories_without_links": stories_without_links,
        "criteria_without_atom_links": criteria_without_atom_links,
        "must_atoms_without_acceptance_criteria": must_atoms_without_acceptance_criteria,
        "must_atoms_without_required_verification": must_atoms_without_required_verification,
        "negative_atoms_without_negative_test": negative_atoms_without_negative_test,
        "high_risk_atoms_without_verification": high_risk_atoms_without_verification,
        "numeric_atoms_without_explicit_constraint": numeric_atoms_without_explicit_constraint,
        "interface_atoms_without_target": interface_atoms_without_target,
        "informative_atoms_without_links": informative_atoms_without_links,
        "duplicate_story_ids": duplicate_story_ids,
        "duplicate_acceptance_criteria_ids": duplicate_acceptance_criteria_ids,
        "generic_criteria_story_ids": generic_criteria_story_ids,
        "raw_source_leak_story_ids": raw_source_leak_story_ids,
        "leak_skipped_unit_ids": leak_skipped_unit_ids,
        "dependency_error_story_ids": dependency_error_story_ids,
        "waived_atom_ids": sorted(waived_atom_ids),
        "waiver_ratio": round(waiver_ratio, 4),
        "waiver_ratio_warning_threshold": WAIVER_RATIO_WARNING_THRESHOLD,
        "stale": stale,
        "errors": errors,
        "warnings": warnings,
        "review_reasons": review_reasons,
        "input_fingerprint": audit_input_fingerprint(prd, coverage, atoms, waivers),
    }


def derived_story_status(story: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> str:
    linked = [rows_by_id.get(str(row_id)) for row_id in (story.get("linked_source_row_ids") or [])]
    linked_rows = [row for row in linked if isinstance(row, dict)]
    if not linked_rows:
        return "unstarted"
    if all(coverage_lib.row_ready(row) for row in linked_rows):
        return "ready"
    statuses = {str(row.get("status") or "").strip().lower() for row in linked_rows}
    if "blocked" in statuses:
        return "blocked"
    if statuses - {"unstarted", ""}:
        return "in_progress"
    return "unstarted"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _repo_root(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise SystemExit(f"Missing repo root: {repo_root}")
    return repo_root


def atoms_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root(args)
    coverage = load_source_coverage(repo_root)
    payload = build_atoms_payload(coverage, repo_root)
    coverage_lib.write_json(atoms_path(repo_root), payload)
    return {
        "operation": "atoms",
        "atoms_path": coverage_lib.relative(atoms_path(repo_root), repo_root),
        "source_coverage_contract_hash": payload.get("source_coverage_contract_hash"),
        "source_atoms_hash": source_atoms_hash(payload),
        "summary": payload.get("summary"),
        "review_reasons": payload.get("review_reasons"),
    }


def _write_prd_artifacts(
    repo_root: Path,
    prd: dict[str, Any],
    coverage: dict[str, Any],
    atoms: dict[str, Any],
) -> dict[str, Any]:
    coverage_lib.write_json(prd_json_path(repo_root), prd)
    coverage_lib.write_text(prd_md_path(repo_root), render_prd_markdown(prd))
    audit = validate_prd_projection(
        prd,
        coverage,
        atoms,
        load_waivers(repo_root),
        repo_root=repo_root,
        prd_required=goal_prd_required(repo_root),
    )
    coverage_lib.write_json(prd_audit_path(repo_root), audit)
    return audit


def emit_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root(args)
    coverage = load_source_coverage(repo_root)
    atoms = ensure_atoms_payload(coverage, repo_root, write=True)
    prd = emit_prd_from_coverage(coverage, atoms, task=args.task or "")
    audit = _write_prd_artifacts(repo_root, prd, coverage, atoms)
    return {
        "operation": "emit",
        "prd_path": coverage_lib.relative(prd_json_path(repo_root), repo_root),
        "prd_md_path": coverage_lib.relative(prd_md_path(repo_root), repo_root),
        "audit_path": coverage_lib.relative(prd_audit_path(repo_root), repo_root),
        "story_count": len(prd.get("stories") or []),
        "audit": audit,
    }


def ingest_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root(args)
    if not coverage_path(repo_root).exists():
        raise SystemExit(
            "Standalone PRD cannot prove source-driven completion: source coverage is missing. "
            "Either ingest the PRD itself as source first "
            "(`rah.py source <repo-root> ingest --mode implementation --source <prd>`) "
            "or create source coverage before `prd ingest`."
        )
    coverage = load_source_coverage(repo_root)
    atoms = ensure_atoms_payload(coverage, repo_root, write=True)
    source = Path(args.source).expanduser()
    if not source.is_absolute():
        source = (repo_root / source).resolve()
    prd = ingest_prd(source, coverage, atoms)
    audit = _write_prd_artifacts(repo_root, prd, coverage, atoms)
    return {
        "operation": "ingest",
        "prd_path": coverage_lib.relative(prd_json_path(repo_root), repo_root),
        "prd_md_path": coverage_lib.relative(prd_md_path(repo_root), repo_root),
        "audit_path": coverage_lib.relative(prd_audit_path(repo_root), repo_root),
        "story_count": len(prd.get("stories") or []),
        "audit": audit,
    }


def validate_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root(args)
    coverage = load_source_coverage(repo_root)
    prd = read_json_strict(prd_json_path(repo_root), "prd.json")
    if not isinstance(prd, dict):
        raise SystemExit(
            f"Missing PRD projection: {prd_json_path(repo_root)}. Run `prd emit` or `prd ingest` first."
        )
    atoms = read_json_lenient(atoms_path(repo_root))
    if not isinstance(atoms, dict):
        atoms = ensure_atoms_payload(coverage, repo_root, write=True)
    audit = validate_prd_projection(
        prd,
        coverage,
        atoms,
        load_waivers(repo_root),
        repo_root=repo_root,
        prd_required=goal_prd_required(repo_root),
    )
    coverage_lib.write_json(prd_audit_path(repo_root), audit)
    return {
        "operation": "validate",
        "audit_path": coverage_lib.relative(prd_audit_path(repo_root), repo_root),
        "audit": audit,
    }


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root(args)
    coverage_payload = read_json_strict(coverage_path(repo_root), "source coverage")
    prd = read_json_strict(prd_json_path(repo_root), "prd.json")
    payload: dict[str, Any] = {
        "operation": "status",
        "prd_present": isinstance(prd, dict),
        "source_coverage_present": isinstance(coverage_payload, dict),
    }
    if not isinstance(prd, dict) or not isinstance(coverage_payload, dict):
        return payload
    atoms = read_json_lenient(atoms_path(repo_root))
    if not isinstance(atoms, dict):
        atoms = build_atoms_payload(coverage_payload, repo_root)
    audit = validate_prd_projection(
        prd,
        coverage_payload,
        atoms,
        load_waivers(repo_root),
        repo_root=repo_root,
        prd_required=goal_prd_required(repo_root),
    )
    rows_by_id = {
        str(row.get("requirement_id") or ""): row
        for row in coverage_lib.rows_from_payload(coverage_payload)
        if isinstance(row, dict)
    }
    payload["stories"] = [
        {
            "id": story.get("id"),
            "title": story.get("title"),
            "epic": story.get("epic"),
            "derived_status": derived_story_status(story, rows_by_id),
            "linked_source_row_count": len(story.get("linked_source_row_ids") or []),
            "criteria_count": len(story.get("acceptance_criteria") or []),
        }
        for story in (prd.get("stories") or [])
        if isinstance(story, dict)
    ]
    payload["audit"] = audit
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = _SuggestingArgumentParser(
        description=(
            "Explicit-only PRD projection over source coverage. PRD is a planning view; "
            "completion authority stays with source coverage and RALPH readiness."
        )
    )
    parser.add_argument("repo_root", help="Path to the repository or workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    atoms_parser = sub.add_parser("atoms", help="Decompose source coverage rows into requirement atoms.")
    atoms_parser.add_argument("--from-coverage", action="store_true", default=True, help=argparse.SUPPRESS)
    atoms_parser.add_argument("--json", action="store_true")

    emit_parser = sub.add_parser("emit", help="Emit prd.json/prd.md/prd_mapping_audit.json from coverage + atoms.")
    emit_parser.add_argument("--from-coverage", action="store_true", default=True, help=argparse.SUPPRESS)
    emit_parser.add_argument("--task", default="", help="Optional goal text stored on the PRD planning view.")
    emit_parser.add_argument("--json", action="store_true")

    ingest_parser = sub.add_parser("ingest", help="Normalize an existing markdown/JSON PRD into the projection.")
    ingest_parser.add_argument("--source", required=True, help="Existing PRD file (.md or .json).")
    ingest_parser.add_argument("--json", action="store_true")

    validate_parser = sub.add_parser("validate", help="Recompute the PRD mapping audit (hard gate).")
    validate_parser.add_argument("--json", action="store_true")

    status_parser = sub.add_parser("status", help="Report PRD readiness and derived story status (read-only).")
    status_parser.add_argument("--json", action="store_true")
    return parser


GATE_COMMANDS = {"emit", "ingest", "validate"}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "atoms":
            payload = atoms_command(args)
        elif args.command == "emit":
            payload = emit_command(args)
        elif args.command == "ingest":
            payload = ingest_command(args)
        elif args.command == "validate":
            payload = validate_command(args)
        else:
            payload = status_command(args)
    except SystemExit as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    display = payload if getattr(args, "json", False) else truncate_lists_for_display(payload)
    coverage_lib.print_payload(display, getattr(args, "json", False))
    if args.command in GATE_COMMANDS:
        audit = payload.get("audit") or {}
        if not audit.get("audit_ready") or audit.get("stale"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
