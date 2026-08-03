"""Build a deterministic content-hash -> bibliographic-identity map for the paper corpus.

Problem this solves
-------------------
`docs/papers/` contains one directory per "paper", each with a `text.md`. A number of
those directories share byte-identical `text.md` files under *different* directory
titles. At most one member of such a group can be correctly labelled, so a citation
that names the directory title is not trustworthy on its own.

This tool:
  1. hashes every `text.md` (sha256 over raw bytes),
  2. groups directories by content hash,
  3. for every duplicate group, tries to decide which candidate's bibliographic
     identity the *text itself* supports, using only evidence found inside the text
     (DOI string, title, author surnames),
  4. emits a machine-readable map marking every unresolvable group `UNRESOLVED` and
     every member of such a group non-citable,
  5. records a per-document text-quality block (flag only, never delete).

Guarantees
----------
* Read-only with respect to the corpus. Nothing outside the output directory is written.
* Deterministic: no clock, no randomness, no network, stdlib only. All collections
  are sorted before serialisation.
* Never guesses. A resolution is emitted only when a rule in RESOLUTION_RULES fires
  on exactly one candidate; the firing rule and its supporting evidence are recorded.

Usage (from the Epistemic-Foundry repo root):
    uv run --locked python -B runs/corpus-identity/build_corpus_identity_map.py
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------------------
# Configuration (all thresholds are constants so the output is reproducible)
# --------------------------------------------------------------------------------------

DEFAULT_CORPUS_ROOT = Path(r"C:\dev\insight\paper-curation\docs\papers")
DEFAULT_OUT = Path(__file__).resolve().parent / "corpus-identity-map.json"
INDEX_NAME = "_papers_index.json"
TEXT_NAME = "text.md"

HEAD_CHARS = 4000  # front-matter window searched for identity evidence
TITLE_STRONG_COV = 0.85  # windowed title-token coverage required for a "strong" title hit
TITLE_WEAK_COV = 0.60  # coverage accepted as corroboration for a body-DOI hit
TITLE_MIN_TOKENS = 6  # titles shorter than this are too generic to decide a group
AUTHOR_MIN_SURNAMES = 2  # need at least this many usable surnames to use author evidence
AUTHOR_STRONG_COV = 0.60  # surname coverage required for the winner
AUTHOR_MARGIN = 0.40  # winner must exceed every rival by this much

STUB_CHARS = 1200  # below this a text.md is a stub, not a paper
LOW_PRINTABLE_RATIO = 0.90  # below this the extraction is considered garbled
FORMFEED_HEAVY = 10  # absolute form-feed count required before flagging
FORMFEED_PER_10K = 1.0  # ...and this density, so long books are not flagged for page breaks

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
NULLISH_DOI = {"", "n/a", "na", "none", "null", "-"}
CONTROLish = {"Cc", "Cf", "Cs", "Co", "Cn"}  # non-printable categories for quality scoring
WHITESPACE_OK = "\n\r\t"

# --------------------------------------------------------------------------------------
# Normalisation helpers
# --------------------------------------------------------------------------------------


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric token stream, accent- and dash-normalised.

    PDF extraction routinely inserts line numbers, hyphenation, ligatures and
    subscript spacing into the title line, so comparison happens on tokens rather
    than on raw substrings.
    """
    text = _strip_accents(text)
    for dash in "\u2010\u2011\u2012\u2013\u2014\u2212":
        text = text.replace(dash, "-")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.lower() in NULLISH_DOI:
        return None
    match = DOI_RE.search(candidate)
    if not match:
        return None
    return match.group(0).lower().rstrip(".")


def extract_dois(text: str) -> set[str]:
    return {m.group(0).lower().rstrip(".") for m in DOI_RE.finditer(text)}


def usable_surnames(authors: object) -> list[str]:
    """Extract lowercase surnames, discarding initials and corrupt index values.

    Some index rows carry scraped junk in `authors` (e.g. a markdown table
    fragment). Requiring >=3 alphabetic characters and no digits filters those out
    instead of letting them fabricate an author match.
    """
    out: set[str] = set()
    if not isinstance(authors, list):
        return []
    for author in authors:
        if not isinstance(author, str):
            continue
        parts = [p for p in re.split(r"[\s,]+", _strip_accents(author)) if p]
        words = [p.strip(".") for p in parts]
        words = [w for w in words if len(w) >= 3 and w.replace("-", "").isalpha()]
        if words:
            out.add(words[-1].lower())
    return sorted(out)


def windowed_title_coverage(title_tokens: list[str], head_tokens: list[str]) -> float:
    """Best in-order coverage of the title inside any bounded window of the head.

    A plain longest-common-subsequence over the whole head lets a handful of common
    words ("of", "leaf", "photosynthesis") scattered across pages fake a full match.
    Restricting the alignment to a window of ~2x the title length keeps interleaved
    line numbers and hyphenation tolerated while refusing document-wide scatter.
    """
    n = len(title_tokens)
    if n == 0 or not head_tokens:
        return 0.0
    window = 2 * n + 10
    step = max(1, n // 2)
    best = 0.0
    for start in range(0, max(1, len(head_tokens) - window + step), step):
        chunk = head_tokens[start:start + window]
        if not chunk:
            break
        matcher = difflib.SequenceMatcher(None, title_tokens, chunk, autojunk=False)
        matched = sum(b.size for b in matcher.get_matching_blocks())
        best = max(best, matched / n)
        if best >= 1.0:
            break
    return best


def surname_coverage(surnames: list[str], head_lower: str) -> float:
    if not surnames:
        return 0.0
    hits = sum(1 for s in surnames if re.search(r"\b" + re.escape(s) + r"\b", head_lower))
    return hits / len(surnames)


def year_of(date_value: object) -> str | None:
    if not isinstance(date_value, str):
        return None
    match = re.search(r"(1[89]\d{2}|20\d{2})", date_value)
    return match.group(1) if match else None


# --------------------------------------------------------------------------------------
# Text quality
# --------------------------------------------------------------------------------------


def text_quality(text: str) -> dict:
    """Flag-only quality screen.

    `printable_ratio` counts control/format/surrogate/private-use/unassigned code
    points as non-printable, but treats CR, LF and TAB as printable whitespace.
    Non-breaking spaces and soft hyphens are ordinary typography and are NOT
    penalised, so the ratio tracks genuine extraction garbling rather than layout.

    `formfeed_heavy` needs both an absolute count and a density, because a long book
    legitimately carries one form feed per printed page; only a short document dense
    in form feeds indicates a broken extraction.
    """
    char_count = len(text)
    form_feed_count = text.count("\x0c")
    if char_count == 0:
        return {
            "char_count": 0,
            "printable_ratio": 0.0,
            "form_feed_count": 0,
            "form_feeds_per_10k_chars": 0.0,
            "quality_flag": "stub",
        }
    bad = sum(
        1
        for c in text
        if c not in WHITESPACE_OK and unicodedata.category(c) in CONTROLish
    )
    ratio = (char_count - bad) / char_count
    ff_density = form_feed_count * 10000 / char_count
    if char_count < STUB_CHARS:
        flag = "stub"
    elif ratio < LOW_PRINTABLE_RATIO:
        flag = "low_printable"
    elif form_feed_count >= FORMFEED_HEAVY and ff_density >= FORMFEED_PER_10K:
        flag = "formfeed_heavy"
    else:
        flag = "ok"
    return {
        "char_count": char_count,
        "printable_ratio": round(ratio, 4),
        "form_feed_count": form_feed_count,
        "form_feeds_per_10k_chars": round(ff_density, 3),
        "quality_flag": flag,
    }


# --------------------------------------------------------------------------------------
# Evidence collection and the resolution ladder
# --------------------------------------------------------------------------------------


def collect_signals(slug: str, entry: dict | None, head: str, head_tokens: list[str],
                    head_dois: set[str], full_dois: set[str], head_lower: str) -> dict:
    entry = entry or {}
    doi = normalize_doi(entry.get("doi"))
    title = entry.get("title") if isinstance(entry.get("title"), str) else None
    title_tokens = tokenize(title or "")
    surnames = usable_surnames(entry.get("authors"))
    year = year_of(entry.get("date"))
    return {
        "slug": slug,
        "in_index": bool(entry),
        "index_title": title,
        "index_doi": doi,
        "title_tokens": len(title_tokens),
        "doi_in_head": bool(doi and doi in head_dois),
        "doi_in_body": bool(doi and doi in full_dois),
        "title_coverage": round(windowed_title_coverage(title_tokens, head_tokens), 3),
        "surnames": surnames,
        "surname_coverage": round(surname_coverage(surnames, head_lower), 3),
        "year": year,
        "year_in_head": bool(year and year in head),
    }


def _fmt(sig: dict) -> str:
    return (
        f"doi_in_head={sig['doi_in_head']} doi_in_body={sig['doi_in_body']} "
        f"title_coverage={sig['title_coverage']} title_tokens={sig['title_tokens']} "
        f"surname_coverage={sig['surname_coverage']} ({len(sig['surnames'])} surnames)"
    )


def resolve_group(members: list[str], signals: dict[str, dict]) -> tuple[str | None, str, str]:
    """Return (winner_slug or None, rule_name, evidence_sentence).

    Rules are tried in decreasing evidential strength. A rule fires only when it
    selects exactly one candidate; otherwise the ladder continues. If no rule fires,
    the group is UNRESOLVED and no identity is asserted for any member.
    """
    # R1 - the DOI printed in the article front matter.
    hits = [m for m in members if signals[m]["doi_in_head"]]
    if len(hits) == 1:
        w = hits[0]
        return w, "doi_in_head", (
            f"DOI {signals[w]['index_doi']} of '{w}' appears in the first {HEAD_CHARS} "
            f"characters of text.md; no other candidate DOI does."
        )

    # R2 - the title printed in the article front matter.
    hits = [
        m for m in members
        if signals[m]["title_coverage"] >= TITLE_STRONG_COV
        and signals[m]["title_tokens"] >= TITLE_MIN_TOKENS
    ]
    if len(hits) == 1:
        w = hits[0]
        rivals = ", ".join(
            f"{m}={signals[m]['title_coverage']}" for m in members if m != w
        )
        return w, "title_in_head", (
            f"Title of '{w}' matches the head of text.md at token coverage "
            f"{signals[w]['title_coverage']} (>= {TITLE_STRONG_COV}); rivals: {rivals}."
        )

    # R3 - the DOI appears somewhere in the body and the title partially corroborates it.
    hits = [
        m for m in members
        if signals[m]["doi_in_body"] and signals[m]["title_coverage"] >= TITLE_WEAK_COV
    ]
    if len(hits) == 1:
        w = hits[0]
        return w, "doi_in_body_with_title", (
            f"DOI {signals[w]['index_doi']} of '{w}' appears in the body of text.md and "
            f"its title corroborates at coverage {signals[w]['title_coverage']}; no other "
            f"candidate meets both conditions."
        )

    # R4 - author surnames in the front matter, with a clear margin over every rival.
    eligible = [
        m for m in members
        if len(signals[m]["surnames"]) >= AUTHOR_MIN_SURNAMES
        and signals[m]["surname_coverage"] >= AUTHOR_STRONG_COV
    ]
    if eligible:
        best = max(eligible, key=lambda m: (signals[m]["surname_coverage"], m))
        rivals = [signals[m]["surname_coverage"] for m in members if m != best]
        corroborated = (
            signals[best]["title_coverage"] >= 0.5
            or signals[best]["doi_in_body"]
            or signals[best]["year_in_head"]
        )
        if all(signals[best]["surname_coverage"] - r >= AUTHOR_MARGIN for r in rivals) \
                and corroborated:
            hit_names = ", ".join(signals[best]["surnames"])
            return best, "authors_in_head", (
                f"Author surnames of '{best}' ({hit_names}) appear in the head of text.md "
                f"at coverage {signals[best]['surname_coverage']}, exceeding every rival by "
                f">= {AUTHOR_MARGIN}; corroborated by title coverage "
                f"{signals[best]['title_coverage']} / year_in_head="
                f"{signals[best]['year_in_head']}."
            )

    detail = "; ".join(f"{m}: {_fmt(signals[m])}" for m in members)
    return None, "none", (
        "No rule in the resolution ladder selected exactly one candidate. "
        f"Signals -- {detail}."
    )


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def build(corpus_root: Path, out_path: Path) -> dict:
    index_path = corpus_root / INDEX_NAME
    index_bytes = index_path.read_bytes()
    index_rows = json.loads(index_bytes.decode("utf-8"))
    by_slug: dict[str, dict] = {}
    for row in index_rows:
        slug = row.get("slug")
        if isinstance(slug, str):
            by_slug[slug] = row

    # Directories are the unit of citation. Hidden/staging directories and
    # directories without a text.md carry no citable text and are only counted.
    skipped: list[str] = []
    slugs: list[str] = []
    for child in sorted(corpus_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            skipped.append(child.name)
            continue
        if not (child / TEXT_NAME).is_file():
            skipped.append(child.name)
            continue
        slugs.append(child.name)

    signals: dict[str, dict] = {}
    quality: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    groups: dict[str, list[str]] = defaultdict(list)

    for slug in slugs:
        raw = (corpus_root / slug / TEXT_NAME).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        hashes[slug] = digest
        groups[digest].append(slug)
        text = raw.decode("utf-8", errors="replace")
        quality[slug] = text_quality(text)

    # Evidence is read once per distinct text, from the text itself.
    for digest, members in groups.items():
        members.sort()
        text = (corpus_root / members[0] / TEXT_NAME).read_bytes().decode(
            "utf-8", errors="replace"
        )
        head = text[:HEAD_CHARS]
        head_tokens = tokenize(head)
        head_lower = _strip_accents(head).lower()
        head_dois = extract_dois(head)
        full_dois = extract_dois(text)
        for slug in members:
            signals[slug] = collect_signals(
                slug, by_slug.get(slug), head, head_tokens, head_dois, full_dois, head_lower
            )

    documents: dict[str, dict] = {}
    rule_counter: Counter = Counter()
    unresolved_groups: list[dict] = []
    resolved_groups: list[dict] = []

    for digest in sorted(groups):
        members = groups[digest]
        if len(members) == 1:
            slug = members[0]
            sig = signals[slug]
            corroborated = sig["doi_in_head"] or (
                sig["title_coverage"] >= TITLE_STRONG_COV
                and sig["title_tokens"] >= TITLE_MIN_TOKENS
            )
            documents[slug] = {
                "content_sha256": digest,
                "canonical_title": sig["index_title"],
                "doi": sig["index_doi"],
                "resolution": "unique",
                "evidence": (
                    f"text.md is unique in the corpus; identity taken from {INDEX_NAME} "
                    f"entry for this directory. In-text corroboration: "
                    f"doi_in_head={sig['doi_in_head']}, "
                    f"title_coverage={sig['title_coverage']}."
                ),
                "duplicate_group": None,
                "citable": True,
                "index_title": sig["index_title"],
                "index_doi": sig["index_doi"],
                "in_index": sig["in_index"],
                "mislabelled": False,
                "identity_corroborated": bool(corroborated),
                "resolution_rule": "unique_text",
                "text_quality": quality[slug],
            }
            continue

        winner, rule, evidence = resolve_group(members, signals)
        rule_counter[rule] += 1
        if winner is None:
            unresolved_groups.append({
                "content_sha256": digest,
                "members": members,
                "candidate_titles": [signals[m]["index_title"] for m in members],
                "candidate_dois": [signals[m]["index_doi"] for m in members],
                "evidence": evidence,
            })
            for slug in members:
                sig = signals[slug]
                documents[slug] = {
                    "content_sha256": digest,
                    "canonical_title": None,
                    "doi": None,
                    "resolution": "UNRESOLVED",
                    "evidence": evidence,
                    "duplicate_group": members,
                    "citable": False,
                    "index_title": sig["index_title"],
                    "index_doi": sig["index_doi"],
                    "in_index": sig["in_index"],
                    "mislabelled": None,
                    "identity_corroborated": False,
                    "resolution_rule": rule,
                    "text_quality": quality[slug],
                }
            continue

        wsig = signals[winner]
        resolved_groups.append({
            "content_sha256": digest,
            "members": members,
            "winner": winner,
            "rule": rule,
            "evidence": evidence,
        })
        for slug in members:
            sig = signals[slug]
            documents[slug] = {
                "content_sha256": digest,
                "canonical_title": wsig["index_title"],
                "doi": wsig["index_doi"],
                "resolution": "resolved",
                "evidence": evidence,
                "duplicate_group": members,
                "citable": True,
                "index_title": sig["index_title"],
                "index_doi": sig["index_doi"],
                "in_index": sig["in_index"],
                "mislabelled": slug != winner,
                "identity_corroborated": True,
                "resolution_rule": rule,
                "text_quality": quality[slug],
            }

    quality_hist = Counter(documents[s]["text_quality"]["quality_flag"] for s in documents)
    dup_members = sorted(s for s in documents if documents[s]["duplicate_group"])
    group_size_hist = Counter(
        len(members) for members in groups.values() if len(members) > 1
    )

    payload = {
        "schema_version": "1.0.0",
        "generated_from": {
            "index_file": str(index_path),
            "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "index_entries": len(index_rows),
            "builder": str(Path(__file__).resolve()),
            "identity_fields_used": ["slug", "title", "doi", "authors", "date"],
            "head_window_chars": HEAD_CHARS,
        },
        "corpus_root": str(corpus_root),
        "counts": {
            "directories_scanned": len(slugs),
            "directories_skipped": len(skipped),
            "distinct_texts": len(groups),
            "duplicate_groups": sum(1 for m in groups.values() if len(m) > 1),
            "duplicate_group_size_histogram": {
                str(k): v for k, v in sorted(group_size_hist.items())
            },
            "directories_in_duplicate_groups": len(dup_members),
            "resolved_groups": len(resolved_groups),
            "unresolved_groups": len(unresolved_groups),
            "resolution_rule_histogram": {k: v for k, v in sorted(rule_counter.items())},
            "documents_citable": sum(1 for d in documents.values() if d["citable"]),
            "documents_not_citable": sum(1 for d in documents.values() if not d["citable"]),
            "documents_mislabelled": sum(
                1 for d in documents.values() if d["mislabelled"] is True
            ),
            "documents_not_in_index": sum(
                1 for d in documents.values() if not d["in_index"]
            ),
            "singletons_without_intext_corroboration": sum(
                1 for d in documents.values()
                if d["resolution"] == "unique" and not d["identity_corroborated"]
            ),
            "text_quality_histogram": {k: v for k, v in sorted(quality_hist.items())},
        },
        "skipped_directories": sorted(skipped),
        "unresolved_groups": sorted(unresolved_groups, key=lambda g: g["members"][0]),
        "resolved_groups": sorted(resolved_groups, key=lambda g: g["members"][0]),
        "documents": {slug: documents[slug] for slug in sorted(documents)},
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build(args.corpus_root.resolve(), args.out.resolve())
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
