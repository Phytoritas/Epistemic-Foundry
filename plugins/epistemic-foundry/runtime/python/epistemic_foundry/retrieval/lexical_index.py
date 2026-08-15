"""SQLite FTS5 lexical index over a document corpus.

Why this exists: a lane that re-scans every document with regexes on every query
pays the whole corpus cost per question, so retrieval breadth gets traded away
for latency and the `lexical` lane silently narrows. An inverted index moves the
corpus-scale work to build time, once, and makes the searched scope an artifact
instead of an assumption.

Three properties are load-bearing and are what the tests pin:

* **Content-addressed scope.** `build_index` returns a corpus snapshot identity
  computed from the per-document SHA-256 digests, following the convention in
  ``runs/forge-hexose-gs-20260802/retrieve.py``: documents sorted by
  ``document_id``, their hex digests concatenated, and that string hashed. A
  receipt naming this snapshot names exactly the documents that were searched,
  so `SEARCHED_NONE` is bounded and checkable rather than a claim about the
  world.
* **Verifiable offsets.** Document text is stored exactly as
  ``path.read_text(encoding="utf-8", errors="replace")`` produces it — the same
  read used by ``runs/forge-hexose-gs-20260802/quote_locator.py`` — so every
  returned ``char_start``/``char_end`` re-extracts its quote byte-exactly from
  the file. A span that cannot be re-extracted is not evidence.
* **Determinism.** No clock, no randomness, no locale-dependent ordering. Ranked
  output is ordered by ``(-bm25_score, document_id)`` in both SQL and Python, so
  an identical corpus produces byte-identical results.

Only the standard library is used: `sqlite3` with FTS5, which ships in CPython's
bundled SQLite. There is no service to run and no new production dependency.

Known bounds, stated rather than hidden:

* FTS5 tokenizes with ``unicode61 remove_diacritics 2``; the offset locator
  matches literal text, so a diacritic-folded index hit whose surface form
  differs from the query term yields no span. Such a term is simply absent from
  ``matched_terms`` — never reported as located.
* The citation extractor recognises author-year citation forms. Papers using
  numeric reference markers contribute few or no citation keys, and the
  per-document key count is reported so a caller can see that.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

#: Bumped whenever the on-disk layout changes; a mismatch forces a rebuild.
SCHEMA_VERSION = "1"
INDEX_KIND = "sqlite-fts5"
TOKENIZER = "unicode61 remove_diacritics 2"
#: Version of the citation-key extraction rules, bound into `index_versions`.
CITATION_EXTRACTOR_VERSION = "author-year-1"

DEFAULT_CONTEXT_CHARS = 320
DEFAULT_SNIPPETS_PER_DOCUMENT = 3
DEFAULT_LIMIT = 25

#: Nested layout used by the paper corpus: ``<root>/<document_id>/text.md``.
NESTED_DOCUMENT_NAME = "text.md"
#: Flat fallback layout: ``<root>/<document_id>.md`` or ``.txt``.
FLAT_SUFFIXES = (".md", ".txt")

_DDL = """
CREATE TABLE index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE documents (
    doc_rowid INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    body TEXT NOT NULL
);

CREATE VIRTUAL TABLE documents_fts USING fts5(
    body,
    content='documents',
    content_rowid='doc_rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE citations (
    document_id TEXT NOT NULL,
    citation_key TEXT NOT NULL,
    occurrences INTEGER NOT NULL,
    first_char_start INTEGER NOT NULL,
    first_char_end INTEGER NOT NULL,
    PRIMARY KEY (document_id, citation_key)
) WITHOUT ROWID;

CREATE INDEX citations_by_key ON citations(citation_key, document_id);
"""

_SURNAME = r"[A-Z][A-Za-zÀ-ɏ’'\-]{2,}"
_COAUTHOR = rf"(?:\s+et\s+al\.?|,?\s+(?:and|&)\s+{_SURNAME})?"
#: ``Farquhar et al. (1980)`` / ``Kim and Lieth (2003,``
_NARRATIVE_CITATION = re.compile(
    rf"\b({_SURNAME}){_COAUTHOR}\s*\(\s*(\d{{4}})[a-z]?\s*[,;)]"
)
#: ``(Farquhar et al., 1980)`` / ``; de Pury and Farquhar, 1997)``
_PARENTHETICAL_CITATION = re.compile(
    rf"({_SURNAME}){_COAUTHOR}\s*,\s*(\d{{4}})[a-z]?\s*[;)]"
)
_MIN_CITATION_YEAR = 1500
_MAX_CITATION_YEAR = 2100

#: FTS5 boolean operators, never treated as searchable terms.
_FTS5_OPERATORS = frozenset({"AND", "OR", "NOT", "NEAR"})
_EXPRESSION_TOKEN = re.compile(r'"([^"]*)"|([^\s()"*:^,]+)(:?)(\*?)')


class LexicalIndexError(RuntimeError):
    """The index is missing, stale, or structurally unusable."""


@dataclass(frozen=True)
class QueryTerm:
    """One locatable unit of an FTS5 MATCH expression."""

    text: str
    is_phrase: bool
    is_prefix: bool


@dataclass(frozen=True)
class CorpusDocument:
    """One corpus unit as read, hashed, and stored."""

    document_id: str
    source_path: str
    body: str
    content_sha256: str

    @property
    def char_count(self) -> int:
        return len(self.body)


def read_document_text(path: Path) -> str:
    """Read a document exactly as the grounding verifier re-reads it.

    Offsets are indices into this string, so this decode must stay identical to
    ``quote_locator.py``; changing it would silently invalidate every span the
    index has ever emitted.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_text(text: str) -> str:
    """Bare lowercase hex digest, matching the run-script corpus convention."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def iter_corpus_paths(corpus_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(document_id, path)`` in ``document_id`` order.

    The nested ``<root>/<document_id>/text.md`` layout wins when present so the
    paper corpus is indexed by its directory name; a flat ``<root>/<id>.md``
    layout is the fallback for small fixture corpora.
    """
    root = Path(corpus_root)
    if not root.is_dir():
        raise LexicalIndexError(f"corpus root is not a directory: {root}")
    nested = {
        path.parent.name: path
        for path in root.glob(f"*/{NESTED_DOCUMENT_NAME}")
        if path.is_file()
    }
    if nested:
        for document_id in sorted(nested):
            yield document_id, nested[document_id]
        return
    flat = {
        path.stem: path
        for path in root.iterdir()
        if path.is_file() and path.suffix in FLAT_SUFFIXES
    }
    for document_id in sorted(flat):
        yield document_id, flat[document_id]


def load_corpus(corpus_root: Path) -> list[CorpusDocument]:
    """Read every corpus document once, in deterministic ``document_id`` order."""
    documents: list[CorpusDocument] = []
    for document_id, path in iter_corpus_paths(corpus_root):
        body = read_document_text(path)
        documents.append(
            CorpusDocument(
                document_id=document_id,
                source_path=path.as_posix(),
                body=body,
                content_sha256=sha256_text(body),
            )
        )
    return documents


def corpus_snapshot_digest(documents: Sequence[CorpusDocument]) -> str:
    """Hex digest binding the exact set and content of indexed documents.

    Follows ``runs/forge-hexose-gs-20260802/retrieve.py``: units sorted by
    ``document_id``, their hex digests concatenated, and the concatenation
    hashed. Adding, removing, or editing any document changes this value, which
    is why a receipt carrying it bounds an absence claim.
    """
    ordered = sorted(documents, key=lambda unit: unit.document_id)
    joined = "".join(unit.content_sha256 for unit in ordered)
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def snapshot_identifiers(documents: Sequence[CorpusDocument]) -> tuple[str, str]:
    """Return ``(snapshot_id, corpus_snapshot_hash)`` for one corpus reading.

    ``snapshot_id`` keeps the run-script ``CSNAP-`` short form; the second value
    is the full ``sha256:<64 hex>`` form the canonical schemas require.
    """
    digest = corpus_snapshot_digest(documents)
    return f"CSNAP-{digest[:32]}", f"sha256:{digest}"


def extract_citation_keys(body: str) -> dict[str, dict[str, int]]:
    """Extract normalised ``surname:year`` citation keys and their first span.

    This recognises author-year citation forms only. A paper using numeric
    reference markers yields few or no keys; the caller sees that as a low key
    count rather than as an assertion that the paper cites nothing.
    """
    found: dict[str, dict[str, int]] = {}
    for pattern in (_NARRATIVE_CITATION, _PARENTHETICAL_CITATION):
        for match in pattern.finditer(body):
            year = int(match.group(2))
            if not _MIN_CITATION_YEAR <= year <= _MAX_CITATION_YEAR:
                continue
            key = f"{match.group(1).lower()}:{year}"
            entry = found.get(key)
            if entry is None:
                found[key] = {
                    "occurrences": 1,
                    "first_char_start": match.start(),
                    "first_char_end": match.end(),
                }
                continue
            entry["occurrences"] += 1
            if match.start() < entry["first_char_start"]:
                entry["first_char_start"] = match.start()
                entry["first_char_end"] = match.end()
    return found


def _connect_writable(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    return connection


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file():
        raise LexicalIndexError(f"no lexical index at {path}; run a build first")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _read_meta(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM index_meta").fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def index_versions(meta: dict[str, str]) -> dict[str, str]:
    """Version bindings recorded in every receipt and candidate this index feeds."""
    return {
        "lexical_fts5": f"{meta['schema_version']}+{meta['tokenizer']}",
        "citation_keys": meta["citation_extractor_version"],
        "sqlite": meta["sqlite_version"],
    }


def _build_stats(
    meta: dict[str, str], db_path: Path, *, rebuilt: bool
) -> dict[str, Any]:
    return {
        "db_path": Path(db_path).as_posix(),
        "index_kind": meta["index_kind"],
        "schema_version": meta["schema_version"],
        "tokenizer": meta["tokenizer"],
        "citation_extractor_version": meta["citation_extractor_version"],
        "sqlite_version": meta["sqlite_version"],
        "corpus_root": meta["corpus_root"],
        "document_count": int(meta["document_count"]),
        "total_chars": int(meta["total_chars"]),
        "citation_edge_count": int(meta["citation_edge_count"]),
        "distinct_citation_key_count": int(meta["distinct_citation_key_count"]),
        "documents_with_citation_keys": int(meta["documents_with_citation_keys"]),
        "snapshot_id": meta["snapshot_id"],
        "corpus_snapshot_hash": meta["corpus_snapshot_hash"],
        "index_versions": index_versions(meta),
        "rebuilt": rebuilt,
    }


def read_index_stats(db_path: Path) -> dict[str, Any]:
    """Return the build stats recorded in an existing index."""
    connection = _connect_read_only(db_path)
    try:
        meta = _read_meta(connection)
    except sqlite3.DatabaseError as error:
        raise LexicalIndexError(f"{db_path} is not a usable lexical index") from error
    finally:
        connection.close()
    return _build_stats(meta, db_path, rebuilt=False)


def _existing_snapshot(db_path: Path) -> dict[str, str] | None:
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        connection = _connect_read_only(path)
    except LexicalIndexError:
        return None
    try:
        return _read_meta(connection)
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()


def build_index(
    corpus_root: Path,
    db_path: Path,
    *,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Build (or reuse) the FTS5 index over ``corpus_root`` at ``db_path``.

    Returns deterministic build statistics including the content-addressed
    corpus snapshot identity. When an index already carries that exact snapshot
    and schema version, the build is skipped and the recorded stats are returned
    with ``rebuilt=False`` — reuse is safe precisely because the snapshot is
    content-addressed.

    The index is written to a sibling temporary file and moved into place, so an
    interrupted build never leaves a half-populated index that would understate
    the searched scope.
    """
    corpus_root = Path(corpus_root)
    db_path = Path(db_path)
    documents = load_corpus(corpus_root)
    if not documents:
        raise LexicalIndexError(f"no indexable documents under {corpus_root}")
    snapshot_id, corpus_snapshot_hash = snapshot_identifiers(documents)

    if not rebuild:
        existing = _existing_snapshot(db_path)
        if (
            existing is not None
            and existing.get("corpus_snapshot_hash") == corpus_snapshot_hash
            and existing.get("schema_version") == SCHEMA_VERSION
            and existing.get("citation_extractor_version") == CITATION_EXTRACTOR_VERSION
        ):
            return _build_stats(existing, db_path, rebuilt=False)

    citation_rows: list[tuple[str, str, int, int, int]] = []
    documents_with_keys = 0
    distinct_keys: set[str] = set()
    for document in documents:
        keys = extract_citation_keys(document.body)
        if keys:
            documents_with_keys += 1
        for key in sorted(keys):
            entry = keys[key]
            distinct_keys.add(key)
            citation_rows.append(
                (
                    document.document_id,
                    key,
                    entry["occurrences"],
                    entry["first_char_start"],
                    entry["first_char_end"],
                )
            )

    meta = {
        "index_kind": INDEX_KIND,
        "schema_version": SCHEMA_VERSION,
        "tokenizer": TOKENIZER,
        "citation_extractor_version": CITATION_EXTRACTOR_VERSION,
        "sqlite_version": sqlite3.sqlite_version,
        "corpus_root": corpus_root.as_posix(),
        "document_count": str(len(documents)),
        "total_chars": str(sum(document.char_count for document in documents)),
        "citation_edge_count": str(len(citation_rows)),
        "distinct_citation_key_count": str(len(distinct_keys)),
        "documents_with_citation_keys": str(documents_with_keys),
        "snapshot_id": snapshot_id,
        "corpus_snapshot_hash": corpus_snapshot_hash,
    }

    db_path.parent.mkdir(parents=True, exist_ok=True)
    staging = db_path.with_name(f"{db_path.name}.building")
    staging.unlink(missing_ok=True)
    connection = _connect_writable(staging)
    try:
        connection.executescript(_DDL)
        connection.executemany(
            "INSERT INTO documents"
            " (doc_rowid, document_id, source_path, content_sha256, char_count, body)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    position,
                    document.document_id,
                    document.source_path,
                    document.content_sha256,
                    document.char_count,
                    document.body,
                )
                for position, document in enumerate(documents, start=1)
            ],
        )
        connection.execute(
            "INSERT INTO documents_fts(rowid, body)"
            " SELECT doc_rowid, body FROM documents ORDER BY doc_rowid"
        )
        connection.executemany(
            "INSERT INTO citations"
            " (document_id, citation_key, occurrences, first_char_start, first_char_end)"
            " VALUES (?, ?, ?, ?, ?)",
            citation_rows,
        )
        connection.executemany(
            "INSERT INTO index_meta (key, value) VALUES (?, ?)",
            sorted(meta.items()),
        )
        connection.commit()
        connection.execute("PRAGMA optimize")
    finally:
        connection.close()
    os.replace(staging, db_path)
    return _build_stats(meta, db_path, rebuilt=True)


def extract_query_terms(expression: str) -> tuple[QueryTerm, ...]:
    """Split an FTS5 MATCH expression into locatable terms, in first-use order.

    Boolean operators are dropped and column filters are reduced to their term,
    because these are used only to find spans in the matched text; the ranking
    itself is done by FTS5 over the real expression.
    """
    terms: list[QueryTerm] = []
    seen: set[tuple[str, bool, bool]] = set()
    for match in _EXPRESSION_TOKEN.finditer(expression):
        phrase, bareword, colon, star = match.groups()
        if phrase is not None:
            text, is_phrase, is_prefix = phrase.strip(), True, False
        else:
            if colon:
                # ``body:hexose`` — the column name is not a searchable term.
                continue
            if bareword in _FTS5_OPERATORS:
                continue
            text, is_phrase, is_prefix = bareword, False, bool(star)
        if not text:
            continue
        identity = (text.lower(), is_phrase, is_prefix)
        if identity in seen:
            continue
        seen.add(identity)
        terms.append(QueryTerm(text=text, is_phrase=is_phrase, is_prefix=is_prefix))
    return tuple(terms)


def _term_pattern(term: QueryTerm) -> re.Pattern[str]:
    if term.is_phrase:
        body = r"\s+".join(re.escape(part) for part in term.text.split())
        return re.compile(body, re.IGNORECASE)
    escaped = re.escape(term.text)
    tail = r"\w*" if term.is_prefix else r"\b"
    return re.compile(rf"\b{escaped}{tail}", re.IGNORECASE)


def locate_terms(
    body: str,
    terms: Sequence[QueryTerm],
    *,
    max_spans: int = DEFAULT_SNIPPETS_PER_DOCUMENT,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
) -> list[dict[str, Any]]:
    """Locate query terms in ``body`` and return re-extractable spans.

    Every returned span satisfies ``body[char_start:char_end] == text`` and
    ``body[context_start:context_end] == context``. Nothing is normalised on the
    way out: a span whose quote does not re-extract byte-exactly is not usable
    as evidence, so the offsets and the text must agree exactly.
    """
    spans: list[dict[str, Any]] = []
    for term in terms:
        match = _term_pattern(term).search(body)
        if match is None:
            continue
        start, end = match.start(), match.end()
        context_start = max(0, start - context_chars)
        context_end = min(len(body), end + context_chars)
        spans.append(
            {
                "term": term.text,
                "char_start": start,
                "char_end": end,
                "text": body[start:end],
                "context_start": context_start,
                "context_end": context_end,
                "context": body[context_start:context_end],
            }
        )
    spans.sort(key=lambda span: (span["char_start"], span["char_end"], span["term"]))
    return spans[:max_spans]


def locate_term_positions(
    body: str,
    terms: Sequence[QueryTerm],
    *,
    max_per_term: int = 64,
) -> dict[str, list[tuple[int, int]]]:
    """Return every occurrence span of each term, keyed by the term text.

    Used by co-occurrence lanes, which need positions rather than one example
    span: proximity is the claim being tested, so a single first hit per term
    would decide the window question by accident.
    """
    positions: dict[str, list[tuple[int, int]]] = {}
    for term in terms:
        spans = [
            (match.start(), match.end()) for match in _term_pattern(term).finditer(body)
        ]
        if spans:
            positions[term.text] = spans[:max_per_term]
    return positions


def query(
    db_path: Path,
    expression: str,
    *,
    limit: int = DEFAULT_LIMIT,
    snippets_per_document: int = DEFAULT_SNIPPETS_PER_DOCUMENT,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
) -> list[dict[str, Any]]:
    """Run one FTS5 MATCH query and return ranked, span-bearing candidates.

    Ordering is ``(-bm25_score, document_id)`` in both SQL and Python, so the
    result is byte-identical across runs and platforms for the same index.
    SQLite's ``bm25()`` returns smaller-is-better values; the sign is flipped
    here so a larger ``bm25_score`` means a better match.
    """
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    terms = extract_query_terms(expression)
    connection = _connect_read_only(db_path)
    try:
        try:
            rows = connection.execute(
                "SELECT d.document_id AS document_id,"
                " d.source_path AS source_path,"
                " d.content_sha256 AS content_sha256,"
                " d.char_count AS char_count,"
                " d.body AS body,"
                " bm25(documents_fts) AS bm25"
                " FROM documents_fts"
                " JOIN documents d ON d.doc_rowid = documents_fts.rowid"
                " WHERE documents_fts MATCH ?"
                " ORDER BY bm25(documents_fts) ASC, d.document_id ASC"
                " LIMIT ?",
                (expression, limit),
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise LexicalIndexError(
                f"invalid FTS5 query {expression!r}: {error}"
            ) from error
    finally:
        connection.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        body = row["body"]
        spans = locate_terms(
            body,
            terms,
            max_spans=snippets_per_document,
            context_chars=context_chars,
        )
        results.append(
            {
                "document_id": row["document_id"],
                "source_path": row["source_path"],
                "content_sha256": row["content_sha256"],
                "char_count": row["char_count"],
                "bm25_score": -float(row["bm25"]),
                "matched_terms": sorted({span["term"] for span in spans}),
                "snippets": spans,
            }
        )
    results.sort(key=lambda item: (-item["bm25_score"], item["document_id"]))
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
    return results


def fetch_documents(
    db_path: Path, document_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Return stored records for named documents, keyed by ``document_id``."""
    if not document_ids:
        return {}
    unique = sorted(set(document_ids))
    connection = _connect_read_only(db_path)
    try:
        placeholders = ",".join("?" * len(unique))
        rows = connection.execute(
            "SELECT document_id, source_path, content_sha256, char_count, body"
            f" FROM documents WHERE document_id IN ({placeholders})"
            " ORDER BY document_id ASC",
            unique,
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["document_id"]): {
            "document_id": str(row["document_id"]),
            "source_path": str(row["source_path"]),
            "content_sha256": str(row["content_sha256"]),
            "char_count": int(row["char_count"]),
            "body": str(row["body"]),
        }
        for row in rows
    }


def citation_keys_for(
    db_path: Path, document_ids: Sequence[str]
) -> dict[str, list[str]]:
    """Return the citation keys extracted from each named document."""
    if not document_ids:
        return {}
    unique = sorted(set(document_ids))
    connection = _connect_read_only(db_path)
    try:
        placeholders = ",".join("?" * len(unique))
        rows = connection.execute(
            "SELECT document_id, citation_key FROM citations"
            f" WHERE document_id IN ({placeholders})"
            " ORDER BY document_id ASC, citation_key ASC",
            unique,
        ).fetchall()
    finally:
        connection.close()
    grouped: dict[str, list[str]] = {document_id: [] for document_id in unique}
    for row in rows:
        grouped[str(row["document_id"])].append(str(row["citation_key"]))
    return grouped


def documents_sharing_citation_keys(
    db_path: Path,
    citation_keys: Sequence[str],
    *,
    exclude: Sequence[str] = (),
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Rank documents by how many of ``citation_keys`` they also cite.

    This is bibliographic coupling: a shared cited work is a real edge in the
    corpus citation graph, computed without any external index. Ties break on
    ``document_id`` so the ordering is total and reproducible.
    """
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    keys = sorted(set(citation_keys))
    if not keys:
        return []
    excluded = set(exclude)
    connection = _connect_read_only(db_path)
    try:
        placeholders = ",".join("?" * len(keys))
        rows = connection.execute(
            "SELECT c.document_id AS document_id,"
            " COUNT(*) AS shared_key_count,"
            " SUM(c.occurrences) AS shared_occurrences,"
            " d.source_path AS source_path,"
            " d.content_sha256 AS content_sha256,"
            " d.char_count AS char_count"
            " FROM citations c"
            " JOIN documents d ON d.document_id = c.document_id"
            f" WHERE c.citation_key IN ({placeholders})"
            " GROUP BY c.document_id"
            " ORDER BY shared_key_count DESC, c.document_id ASC",
            keys,
        ).fetchall()
        # The GROUP BY ordering is already total, so the cut can be taken before
        # the per-document span lookup instead of after it. Fetching spans for
        # every coupled document would cost one query per document for a result
        # the cutoff then discards.
        rows = [row for row in rows if str(row["document_id"]) not in excluded][:limit]
        shared_lookup: dict[str, list[str]] = {}
        for row in rows:
            document_id = str(row["document_id"])
            shared = connection.execute(
                "SELECT citation_key, first_char_start, first_char_end FROM citations"
                f" WHERE document_id = ? AND citation_key IN ({placeholders})"
                " ORDER BY citation_key ASC",
                (document_id, *keys),
            ).fetchall()
            shared_lookup[document_id] = shared
    finally:
        connection.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        document_id = str(row["document_id"])
        shared = shared_lookup[document_id]
        results.append(
            {
                "document_id": document_id,
                "source_path": str(row["source_path"]),
                "content_sha256": str(row["content_sha256"]),
                "char_count": int(row["char_count"]),
                "shared_key_count": int(row["shared_key_count"]),
                "shared_occurrences": int(row["shared_occurrences"]),
                "shared_citation_keys": [str(item["citation_key"]) for item in shared],
                "citation_spans": [
                    {
                        "citation_key": str(item["citation_key"]),
                        "char_start": int(item["first_char_start"]),
                        "char_end": int(item["first_char_end"]),
                    }
                    for item in shared
                ],
            }
        )
    results.sort(key=lambda item: (-item["shared_key_count"], item["document_id"]))
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
    return results[:limit]


__all__ = [
    "CITATION_EXTRACTOR_VERSION",
    "CorpusDocument",
    "INDEX_KIND",
    "LexicalIndexError",
    "QueryTerm",
    "SCHEMA_VERSION",
    "TOKENIZER",
    "build_index",
    "citation_keys_for",
    "corpus_snapshot_digest",
    "documents_sharing_citation_keys",
    "extract_citation_keys",
    "extract_query_terms",
    "fetch_documents",
    "index_versions",
    "iter_corpus_paths",
    "load_corpus",
    "locate_terms",
    "query",
    "read_document_text",
    "read_index_stats",
    "sha256_text",
    "snapshot_identifiers",
]
