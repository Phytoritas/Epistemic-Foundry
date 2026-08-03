"""Fail-closed citation guard over the corpus identity map.

The paper corpus contains directories whose `text.md` is byte-identical to another
directory's under a *different* bibliographic title. For those, the directory name is
not evidence of what the text is. This module is the enforcement point: nothing should
cite a corpus directory without passing through it.

Two failure modes it exists to stop:

1. **Unresolvable identity.** The text belongs to one of N candidate papers and the
   text itself does not say which. `assert_citable` raises and names every candidate.
2. **Silently mislabelled directories.** The identity is known, but it is *not* the one
   the directory name advertises. `canonical_citation` returns the corrected identity
   and marks `directory_label_is_wrong`.

Deterministic: no clock, no randomness, no network, standard library only.

    from citation_guard import assert_citable, canonical_citation

    assert_citable("857_A_methodology_for_model-based_greenhouse_design_Part_2_descr")
    cite = canonical_citation("1276_Validation_of_a_building_energy_model_of_a_hydroponi")
    cite["canonical_title"]          # the paper the text is actually from
    cite["directory_label_is_wrong"] # True - do not cite the directory name
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "corpus-identity-map.json"

# Quality flags that indicate the extracted text may not support verbatim quotation.
DEGRADED_QUALITY = frozenset({"low_printable", "stub", "formfeed_heavy"})

__all__ = [
    "CitationGuardError",
    "UnknownDocumentError",
    "UncitableDocumentError",
    "MislabelledDocumentError",
    "DegradedTextError",
    "load_map",
    "assert_citable",
    "canonical_citation",
    "duplicate_group_of",
    "iter_uncitable",
    "iter_mislabelled",
]


class CitationGuardError(Exception):
    """Base class for every refusal raised by this module."""


class UnknownDocumentError(CitationGuardError, KeyError):
    """The document id is not present in the identity map."""

    def __str__(self) -> str:  # KeyError would otherwise repr() the message
        return self.args[0] if self.args else ""


class UncitableDocumentError(CitationGuardError):
    """The document's bibliographic identity could not be established."""


class MislabelledDocumentError(CitationGuardError):
    """The directory name does not name the paper the text actually comes from."""


class DegradedTextError(CitationGuardError):
    """The extracted text is a stub or garbled enough to make quotation unsafe."""


_CACHE: dict[str, dict[str, Any]] = {}


def load_map(map_path: str | Path | None = None) -> dict[str, Any]:
    """Load and cache the identity map. Cached by resolved path, so it is idempotent."""
    path = Path(map_path) if map_path is not None else DEFAULT_MAP_PATH
    key = str(path.resolve())
    cached = _CACHE.get(key)
    if cached is None:
        with open(path, encoding="utf-8") as handle:
            cached = json.load(handle)
        if "documents" not in cached:
            raise CitationGuardError(f"{path} is not a corpus identity map (no 'documents').")
        _CACHE[key] = cached
    return cached


def _record(document_id: str, map_path: str | Path | None) -> dict[str, Any]:
    data = load_map(map_path)
    record = data["documents"].get(document_id)
    if record is None:
        raise UnknownDocumentError(
            f"Unknown document id {document_id!r}. It is not in the corpus identity map "
            f"({data.get('corpus_root', '?')}). Do not cite it: the map covers "
            f"{len(data['documents'])} directories, and an id outside that set has no "
            f"verified provenance."
        )
    return record


def assert_citable(
    document_id: str,
    *,
    map_path: str | Path | None = None,
    strict_label: bool = False,
    require_quality: bool = False,
) -> None:
    """Raise unless `document_id` may be cited.

    Always raises for a document whose identity is UNRESOLVED, listing every candidate
    directory sharing the identical text so the caller can see the ambiguity.

    strict_label
        Also raise when the identity is known but differs from the directory name.
        Use this when the caller cites by directory title rather than by the map.
    require_quality
        Also raise when the extracted text is a stub or garbled.
    """
    record = _record(document_id, map_path)

    if not record.get("citable", False) or record.get("resolution") == "UNRESOLVED":
        members = record.get("duplicate_group") or [document_id]
        data = load_map(map_path)
        lines = []
        for member in members:
            other = data["documents"].get(member, {})
            marker = " <- requested" if member == document_id else ""
            lines.append(f"    - {member}{marker}\n        index title: {other.get('index_title')!r}"
                         f"\n        index doi  : {other.get('index_doi')!r}")
        raise UncitableDocumentError(
            f"{document_id!r} is NOT citable: its text.md is byte-identical "
            f"(sha256 {record.get('content_sha256')}) to {len(members) - 1} other "
            f"director{'y' if len(members) == 2 else 'ies'}, and the text contains no "
            f"evidence deciding which paper it is. Candidates:\n"
            + "\n".join(lines)
            + f"\n  Resolution attempt: {record.get('evidence')}"
        )

    if strict_label and record.get("mislabelled"):
        raise MislabelledDocumentError(
            f"{document_id!r} is citable but MISLABELLED: the directory name advertises "
            f"{record.get('index_title')!r}, while the text is actually "
            f"{record.get('canonical_title')!r} (doi {record.get('doi')!r}). "
            f"Cite canonical_citation()['canonical_title'], never the directory name. "
            f"Evidence: {record.get('evidence')}"
        )

    if require_quality:
        quality = record.get("text_quality") or {}
        flag = quality.get("quality_flag")
        if flag in DEGRADED_QUALITY:
            raise DegradedTextError(
                f"{document_id!r} has degraded extracted text (quality_flag={flag!r}, "
                f"char_count={quality.get('char_count')}, "
                f"printable_ratio={quality.get('printable_ratio')}, "
                f"form_feed_count={quality.get('form_feed_count')}). Verbatim quotation "
                f"from it is unsafe; check the source PDF."
            )


def canonical_citation(
    document_id: str,
    *,
    map_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return the verified bibliographic identity for `document_id`.

    Raises UncitableDocumentError when the identity is unresolved, so the returned dict
    always carries a title backed by in-text evidence.
    """
    assert_citable(document_id, map_path=map_path)
    record = _record(document_id, map_path)
    quality = record.get("text_quality") or {}

    warnings: list[str] = []
    if record.get("mislabelled"):
        warnings.append(
            f"directory name advertises {record.get('index_title')!r} but the text is "
            f"{record.get('canonical_title')!r}; cite canonical_title"
        )
    if record.get("resolution") == "unique" and not record.get("identity_corroborated"):
        warnings.append(
            "identity comes from the corpus index only; the text head does not repeat "
            "the title or DOI, so the attribution is unverified in-text"
        )
    if quality.get("quality_flag") in DEGRADED_QUALITY:
        warnings.append(f"text quality flag: {quality.get('quality_flag')}")
    if not record.get("in_index", True):
        warnings.append("this directory has no entry in the corpus index")

    return {
        "document_id": document_id,
        "canonical_title": record.get("canonical_title"),
        "doi": record.get("doi"),
        "content_sha256": record.get("content_sha256"),
        "resolution": record.get("resolution"),
        "resolution_rule": record.get("resolution_rule"),
        "evidence": record.get("evidence"),
        "duplicate_group": record.get("duplicate_group"),
        "directory_label": record.get("index_title"),
        "directory_label_is_wrong": bool(record.get("mislabelled")),
        "identity_corroborated": bool(record.get("identity_corroborated")),
        "text_quality": dict(quality),
        "warnings": warnings,
    }


def duplicate_group_of(
    document_id: str,
    *,
    map_path: str | Path | None = None,
) -> list[str]:
    """Every directory sharing this document's exact text (including itself), or []."""
    record = _record(document_id, map_path)
    return list(record.get("duplicate_group") or [])


def iter_uncitable(*, map_path: str | Path | None = None) -> Iterator[str]:
    """Document ids that must never be cited, in sorted order."""
    documents = load_map(map_path)["documents"]
    for document_id in sorted(documents):
        if not documents[document_id].get("citable", False):
            yield document_id


def iter_mislabelled(*, map_path: str | Path | None = None) -> Iterator[str]:
    """Document ids whose directory name names the wrong paper, in sorted order."""
    documents = load_map(map_path)["documents"]
    for document_id in sorted(documents):
        if documents[document_id].get("mislabelled"):
            yield document_id
